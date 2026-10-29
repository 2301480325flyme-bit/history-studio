# -*- coding: utf-8 -*-
"""
叙事模板 → 分镜骨架生成器。

把三份模板（事件序列 / 节奏骨架 / 运镜句式）合成一份 director.json 骨架。
这一步是「复用叙事结构」的落地：给定谓词，直接产出可渲染的分镜。

用法：
    python compile_story.py \
        --template raise-and-march \
        --actor sima_jiong --from xuchang_approx --to luoyang_han_wei \
        --rival sima_lun --year 301 \
        --pacing short-60 \
        --title "齐王冏起兵" --subtitle "许昌 → 洛阳" \
        --out ../../05_项目/生成/qi-wang-jiong.director.json

产出结构：沿用既有 director.json schema（view/regions/labels/routes/markers/camera/
sources/beats），**外加 actions[]** —— 供 Remotion 的 ActionLayer 消费。
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REUSE = HERE / "reuse"


def load(name):
    return json.loads((REUSE / name).read_text(encoding="utf-8"))


# 运镜句式 → 镜头关键帧生成规则。
# 与 cameraPhrase.json 的 id 对应；只做几何参数，不做缓动曲线（缓动由运行时负责）。
CAMERA_RULES = {
    "hold":      {"zoomFrom": 1.0, "zoomTo": 1.0},
    "dolly_in":  {"zoomFrom": 1.0, "zoomTo": 1.35},
    "dolly_out": {"zoomFrom": 1.35, "zoomTo": 1.0},
    "track":     {"zoomFrom": 1.15, "zoomTo": 1.15, "panRatio": 1.0},
    "shake":     {"zoomFrom": 1.3, "zoomTo": 1.3, "shake": True},
    "fade":      {"zoomFrom": 1.0, "zoomTo": 1.0, "transition": "fade"},
}

# verb → 中文名（模板未给 note 时用作镜头标题与旁白占位，避免画面出现英文动词）
VERB_CN = {
    "raise": "起兵", "march": "进兵", "defeat": "交战", "capture": "攻取",
    "siege": "围城", "fall": "陷落", "kill": "诛杀", "ascend": "即位",
    "depose": "废黜", "usurp": "篡位", "defect": "归降", "flee": "出奔",
    "enfeoff": "册封", "ally": "会盟", "move_capital": "迁都", "aftermath": "余波",
}

# verb → 该动词适合的默认运镜（模板未指定时用）
VERB_CAMERA = {
    "raise": "dolly_in", "march": "track", "defeat": "shake",
    "capture": "hold", "siege": "dolly_in", "fall": "shake",
    "kill": "hold", "ascend": "hold", "depose": "hold",
    "usurp": "dolly_in", "defect": "hold", "flee": "track",
    "enfeoff": "hold", "ally": "hold", "move_capital": "track",
}


def resolve_places(md, ids):
    """placeId → 坐标；解析不了的如实报告，不编造。"""
    out, missing = {}, []
    for pid in ids:
        if not pid:
            continue
        e = md.place(pid)
        if e and e.get("coordinates"):
            out[pid] = e
        else:
            missing.append(pid)
    return out, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--pacing", default="short-60")
    ap.add_argument("--actor"), ap.add_argument("--rival")
    ap.add_argument("--from", dest="frm"), ap.add_argument("--to")
    ap.add_argument("--place"), ap.add_argument("--victim")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--dynasty", default="")
    ap.add_argument("--title", default="未命名")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tpls = {t["id"]: t for t in load("eventSequence.json")["templates"]}
    pacings = {p["id"]: p for p in load("pacingProfile.json")["profiles"]}
    phrases = {p["id"]: p for p in load("cameraPhrase.json")["phrases"]}

    if args.template not in tpls:
        raise SystemExit("✗ 未知模板 %s；可用：%s" % (args.template, "、".join(tpls)))
    if args.pacing not in pacings:
        raise SystemExit("✗ 未知节奏 %s；可用：%s" % (args.pacing, "、".join(pacings)))
    tpl, pacing = tpls[args.template], pacings[args.pacing]

    # 谓词校验（模板声明了必需参数，缺一不可 —— 不猜）
    ctx = {"actor": args.actor, "rival": args.rival, "from": args.frm, "to": args.to,
           "place": args.place, "victim": args.victim, "capital": args.place}
    lack = [k for k in tpl["required"] if not ctx.get(k)]
    if lack:
        raise SystemExit("✗ 模板「%s」缺少必需谓词：%s" % (tpl["name"], "、".join(lack)))

    # 载入主表（解析坐标与人物）
    import sys
    sys.path.insert(0, str(HERE))
    from maindata import MainData
    md = MainData()

    # 分配时长：模板 beats 总数 → 节奏骨架里 beat/chapter 类槽位
    steps = tpl["sequence"]
    total_beats = sum(s.get("beats", 1) for s in steps)
    slots = pacing["slots"]
    content_slots = [s for s in slots if s["role"] in ("beat", "chapter")]
    total_sec = pacing["totalSec"]

    if content_slots:
        per_beat = sum(s["sec"] for s in content_slots) / total_beats
    else:
        per_beat = total_sec / max(1, total_beats)

    # 逐步骤生成
    actions, beats, camera = [], [], []
    t = 0.0
    for st in steps:
        n = st.get("beats", 1)
        dur = per_beat * n
        cam = st.get("camera") or VERB_CAMERA.get(st["verb"], "hold")
        rule = CAMERA_RULES.get(cam, CAMERA_RULES["hold"])

        # 参数替换 {actor} 等
        params = {k: (ctx.get(v.strip("{}")) if isinstance(v, str) and v.startswith("{") else v)
                  for k, v in (st.get("params") or {}).items()}
        params = {k: v for k, v in params.items() if v}

        spec = {"verb": st["verb"], "startSec": round(t, 2), "durSec": round(dur, 2),
                "camera": cam}
        spec.update(params)

        # 坐标解析
        places, missing = resolve_places(md, [params.get("from"), params.get("to"),
                                              params.get("place")])
        if places:
            spec["resolvedPlaces"] = {k: v["coordinates"] for k, v in places.items()}
        if missing:
            spec["unresolvedPlaces"] = missing

        actions.append(spec)

        # 镜头关键帧
        camera.append({"t": round(t, 2), "zoom": rule["zoomFrom"],
                       "x": 0, "y": 0, "camera": cam})
        camera.append({"t": round(t + dur, 2), "zoom": rule["zoomTo"],
                       "x": 0, "y": 0, "camera": cam,
                       **({"shake": True} if rule.get("shake") else {}),
                       **({"transition": rule["transition"]} if rule.get("transition") else {})})

        # 字幕（模板未提供文案时留占位，**不自动编造历史叙述**）
        beats.append({
            "start": round(t, 2), "end": round(t + dur, 2),
            "verb": st["verb"],
            "camera": cam,
            "subtitle": st.get("note") or "【待填旁白】%s" % st["verb"],
            "illustrative": True,
        })
        t += dur

    duration_sec = round(t, 2)

    # 地点标注（只标已解析的）
    # ⚠️ tier 必须按 storyYear 解析：许昌在 196–220 是都城，301 年只是州郡治。
    #    取 tiers[0] 会得到错的时代等级。
    labels = []
    for pid in [args.frm, args.to, args.place]:
        if not pid:
            continue
        v = md.place(pid, args.year)          # 带年代的解析
        if not v or not v.get("coordinates"):
            continue
        labels.append({
            "id": v["id"],
            "text": v.get("activeName") or (v["names"][0]["text"] if v.get("names") else pid),
            "lon": v["coordinates"][0], "lat": v["coordinates"][1],
            "tier": v.get("activeTier") or "county",
            "start": 0, "end": duration_sec,
        })

    # ---------- 转成 episode 格式（供 Remotion 的 DirectorComposition 直接消费）----------
    # 每个模板步骤 = 一个镜头；焦点取该步涉及地点的重心
    shots = []
    for st, a in zip(steps, actions):
        dur_f = max(1, round(a["durSec"] * 30))
        rp = a.get("resolvedPlaces") or {}
        pts = [v for v in rp.values() if isinstance(v, (list, tuple)) and len(v) >= 2]
        focus = ([sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)]
                 if pts else [113.5, 35.2])
        keys = list(rp.keys())
        act = {"verb": a["verb"], "startSec": 0,
               "durSec": round(a["durSec"] * 0.8, 2),
               "color": a.get("color"),
               "label": st.get("note") or VERB_CN.get(a["verb"], a["verb"])}
        if a["verb"] in ("march", "defeat", "flee", "ally", "enfeoff", "move_capital") and len(keys) >= 2:
            act["from"], act["to"] = keys[0], keys[-1]
        elif keys:
            act["at"] = keys[-1]
        shots.append({
            "title": args.title if not shots else (st.get("note") or VERB_CN.get(a["verb"], a["verb"])),
            "subtitle": args.subtitle if not shots else "",
            "year": args.year,
            "yearLabel": "%d 年" % args.year,
            "focus": [round(focus[0], 4), round(focus[1], 4)],
            "zoom": 1.2,
            "basemap": "wide",
            "durationInFrames": dur_f,
            "narration": st.get("note") or "【待填旁白】%s" % VERB_CN.get(a["verb"], a["verb"]),
            "places": [{"placeId": k} for k in keys],
            "actions": [act],
        })

    episode = {
        "id": args.template,
        "title": args.title,
        "dynasty": args.dynasty or "",
        "year": args.year,
        "fps": 30,
        "sourceNote": "⚠️ 本文件由模板生成，**旁白、史料出处、疆域均未填写**。"
                      "须人工补齐 sources / narrationText 后方可发布。",
        "generatedFrom": {"template": tpl["id"], "pacing": pacing["id"],
                          "predicates": {k: v for k, v in ctx.items() if v}},
        "shots": shots,
        "labels": labels,
        "camera": camera,
        "beats": beats,
        "actionsFlat": actions,
        "narrationText": "",
        "sources": [],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8")

    total_f = sum(s["durationInFrames"] for s in shots)
    print("=== 分镜骨架已生成（episode 格式，可直接渲染）===")
    print(" 模板 %s（%s）｜ 节奏 %s ｜ 总时长 %.1fs ｜ 镜头 %d 个"
          % (tpl["id"], tpl["name"], pacing["id"], duration_sec, len(shots)))
    print("\n 镜头序列：")
    acc = 0
    for i, sh in enumerate(shots, 1):
        act = sh["actions"][0] if sh["actions"] else {}
        loc = act.get("at") or ("%s→%s" % (act.get("from", "?"), act.get("to", "?")))
        print("  %d. %5.1fs  %-10s %-24s %s" % (i, acc / 30, act.get("verb", "-"), loc, sh["title"]))
        acc += sh["durationInFrames"]
    print("\n 输出：%s（总 %d 帧）" % (out, total_f))
    print(" ⚠️ 旁白与史料出处为空白，须人工补齐 —— 模板不编造历史内容。")
    print(" 渲染：复制到 remotion-shuihong/public/scripts/ 后由 DirectorComposition 读取")


if __name__ == "__main__":
    main()
