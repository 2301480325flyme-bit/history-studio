# -*- coding: utf-8 -*-
"""
auto_episode.py —— 批量候选事件 → 批量可渲染 episode。

这是「Studio」的核心：把 extract_events.py 的产物**自动**转成分镜脚本，
不再需要人工把每条事件抄成命令行参数。

用法：
    # 1) 先从语料抽候选
    python extract_events.py extract 晋书 --juan 帝纪第四 --out cand.json

    # 2) 自动转成 episode（可指定集数）
    python auto_episode.py cand.json --episodes 3 --out-dir "../remotion-shuihong/public/scripts"

    # 3) 注册到清单后即可渲染
    remotion render <episodeId>

设计原则（重要）：
  1. **不编造** —— 旁白留占位、缺实体不猜，全部进「待人工补」清单。
  2. **降级而非丢弃** —— 没有地点的镜头用全景 + 字幕，仍然出片；
     不能因为"缺实体"就把 96% 的候选扔掉。
  3. **每集一个文件 + 一条清单项** —— 保持「改数据不改代码」。
"""
import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# verb → 中文名（画面标题与旁白占位）
VERB_CN = {
    "raise": "起兵", "march": "进兵", "defeat": "交战", "capture": "攻取",
    "siege": "围城", "fall": "陷落", "kill": "诛杀", "ascend": "即位",
    "depose": "废黜", "usurp": "篡位", "defect": "归降", "flee": "出奔",
    "enfeoff": "册封", "ally": "会盟", "move_capital": "迁都", "aftermath": "余波",
}
# verb → 该动词的主色（沿用诸王配色语义）
VERB_COLOR = {
    "raise": "#c2185b", "march": "#8c3424", "defeat": "#8c3424",
    "capture": "#c62828", "siege": "#1565c0", "fall": "#37474f",
    "kill": "#4a3a34", "ascend": "#b8860b", "depose": "#6b5a49",
    "usurp": "#8e24aa", "defect": "#c62828", "flee": "#6b5a49",
    "enfeoff": "#8c3424", "ally": "#8c3424", "move_capital": "#8c3424",
}
# 需要 from→to 的动词
TWO_POINT = {"march", "defeat", "flee", "ally", "enfeoff", "move_capital"}
# 只要一个点的动词
ONE_POINT = {"raise", "capture", "siege", "fall", "kill", "ascend",
             "depose", "usurp", "defect"}

DEFAULT_FOCUS = [113.5, 35.2]
FPS = 30

# 三层底图视野（与 remotion-shuihong/src/geo.ts 的 VIEW_BOUNDS 完全一致，勿单边改动）
# national 为本轮新增：69.06–139.07°E / 16.64–48.92°N，由 z6 瓦片范围反算（scale 1571.5）
VIEW_BOUNDS = {
    "core":     {"lon": (109.4, 117.6), "lat": (33.3, 37.1)},
    "wide":     {"lon": (104.3, 122.7), "lat": (30.9, 39.3)},
    "national": {"lon": (69.06, 139.07), "lat": (16.64, 48.92)},
}
# 由紧到松：core（最清晰）→ wide（区域）→ national（全覆盖）
BASEMAP_ORDER = ["core", "wide", "national"]
# 各层的默认 zoom（层级越松，zoom 越接近 1）
TIER_ZOOM = {"core": 1.45, "wide": 1.2, "national": 1.0}


def pick_basemap_for_points(points, margin=0.0):
    """取能**同时装下所有点**的最紧层级。

    与 src/geo.ts 的 pickBasemapForPoints 同一逻辑、同一张表 —— 两边必须同步改。
    """
    if not points:
        return "national"
    for k in BASEMAP_ORDER:
        b = VIEW_BOUNDS[k]
        ok = all(b["lon"][0] + margin <= lon <= b["lon"][1] - margin and
                 b["lat"][0] + margin <= lat <= b["lat"][1] - margin
                 for lon, lat in points)
        if ok:
            return k
    return "national"


def is_covered(lon, lat):
    b = VIEW_BOUNDS["national"]
    return b["lon"][0] <= lon <= b["lon"][1] and b["lat"][0] <= lat <= b["lat"][1]


def pick_basemap(focus, anchored, extra_points=None):
    """兼容旧签名：单焦点（可附带多点）→ 三层选择。"""
    pts = []
    if anchored:
        pts.append(tuple(focus))
    for p in (extra_points or []):
        pts.append(tuple(p))
    if not pts:
        return "wide"
    return pick_basemap_for_points(pts)


def load_maindata():
    import sys
    sys.path.insert(0, str(HERE))
    from maindata import MainData
    return MainData()


# ⚠️ 不做机械化台词改写。
# 分工：自动化负责**骨架**（事件、锚点、底图层级、镜头串联）；
#       表达（旁白、台词、节奏）留到真正做那一集时，由撰写者读史料原文后落笔。
# 机械改写史料只会产出「原文 + 标点」这种没人看的东西。
def build_narration_materials(raw, year, ev, book, juan):
    """只提供**素材**，不代写。

    narration       —— 留空
    narrationHint   —— 原文 + 出处 + 纪年，写作者据此发挥
    """
    return "", {
        "verbatim": raw,
        "year": year,
        "era": ev.get("era"),
        "source": ("%s·%s" % (book, juan)) if juan else book,
        "sourceId": ev.get("sourceId"),
        "note": "旁白/台词待撰。素材已备好（原文+出处+纪年），"
                "撰写时须核对史料、确认人名地名后再落笔。",
    }


def build_shot(ev, md, year_fallback, book="史书", juan=""):
    """一条候选事件 → 一个镜头。**缺实体时降级为全景 + 字幕，不丢弃。**"""
    verbs = ev.get("verbs") or []
    primary = verbs[0] if verbs else "march"
    places = ev.get("placeIds") or []
    people = ev.get("personIds") or []
    year = ev.get("year") or year_fallback

    # 焦点与层级：把本镜涉及的**所有点**交给三层选择（行军要同时装下起终点）
    focus, zoom, anchored = DEFAULT_FOCUS, TIER_ZOOM["wide"], False
    coords = []
    for pid in places[:2]:
        e = md.place(pid, year)
        if e and e.get("coordinates"):
            coords.append((pid, e["coordinates"]))
    basemap = "wide"
    if coords:
        anchored = True
        focus = [round(sum(c[0] for _, c in coords) / len(coords), 4),
                 round(sum(c[1] for _, c in coords) / len(coords), 4)]
        basemap = pick_basemap_for_points([tuple(c) for _, c in coords])
        zoom = TIER_ZOOM[basemap]

    # 动作：按动词类型挂定位字段（缺实体则不带位置，仅出标题与字幕）
    act = {"verb": primary, "startSec": 0.4, "durSec": 3.2,
           "color": VERB_COLOR.get(primary, "#8c3424"),
           "label": VERB_CN.get(primary, primary)}
    if coords:
        ids = [pid for pid, _ in coords]
        if primary in TWO_POINT and len(ids) >= 2:
            act["from"], act["to"] = ids[0], ids[1]
        elif primary in TWO_POINT:
            act["at"] = ids[0]
        else:
            act["at"] = ids[-1]
    if primary == "kill":
        act["stamp"] = "诛"

    # ── 旁白：从史料原文转成解说词 ──
    # 直接甩原文（"【待审定】荆州刺史宋岱击特，斩之"）不是解说词，
    # 观众看到的是史料而不是解说。改成：公元纪年 + 事件核心 + 出处。
    raw = (ev.get("text") or "").strip()
    narration, narration_hint = build_narration_materials(raw, year, ev, book, juan)

    shot = {
        "title": VERB_CN.get(primary, primary) + (("（%d）" % year) if year else ""),
        "subtitle": ev.get("juanTitle") or "",
        "year": year,
        "yearLabel": ("%d 年" % year) if year else None,
        "focus": focus,
        "zoom": zoom,
        "basemap": basemap,
        "durationInFrames": int(4.0 * FPS),
        "narration": narration,
        "narrationHint": narration_hint,
        "disclaimer": "地名点位：正式层为审定坐标，示意层为近似点（见 places 标注）。",
        "places": [{"placeId": pid} for pid in places[:2]],
        "actions": [act],
        "_anchored": anchored,
        "_sourceId": ev.get("sourceId"),
        "_rawText": raw,
    }
    if primary in ("siege", "defeat") and anchored:
        shot["shake"] = True
    return shot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", help="extract_events.py 的产出 JSON")
    ap.add_argument("--episodes", type=int, default=3, help="切成几集")
    ap.add_argument("--shots-per-episode", type=int, default=6)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--anchor-only", action="store_true",
                    help="只取有地点锚点的候选（沙盘镜头需要地点；数量少但成片质量高）")
    ap.add_argument("--prefer-anchor", action="store_true",
                    help="同年份内有地点的优先（保持时间线，同时提高锚定率）")
    args = ap.parse_args()

    doc = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    events = doc.get("events") or []
    if not events:
        raise SystemExit("✗ 候选中没有事件")

    # 只保留有动词、有年份的，按年份排序
    events = [e for e in events if e.get("verbs")]
    if args.anchor_only:
        before = len(events)
        events = [e for e in events if e.get("placeIds")]
        print("--anchor-only：%d → %d 条（筛掉 %d 条无地点）"
              % (before, len(events), before - len(events)))
    if args.prefer_anchor:
        # 同年份内有地点的排前面，但跨年份仍按时间线
        events.sort(key=lambda e: (e.get("year") or 0, 0 if e.get("placeIds") else 1))
    else:
        events.sort(key=lambda e: (e.get("year") or 0))
    book = doc.get("book") or "史书"
    juan = doc.get("juan") or ""
    md = load_maindata()

    # 按「每集 N 个镜头」切片
    per = max(1, args.shots_per_episode)
    chunks = [events[i:i + per] for i in range(0, len(events), per)]
    if args.episodes > 0:
        chunks = chunks[:args.episodes]

    outdir = Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_path = outdir / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file() else {"note": "脚本清单", "episodes": []})

    report = []
    for ci, chunk in enumerate(chunks, 1):
        y0 = chunk[0].get("year") or 0
        y1 = chunk[-1].get("year") or y0
        ep_id = "%s-%s-%d" % (
            (args.prefix or re.sub(r"\W", "", book[:4]) or "ep"),
            re.sub(r"\W", "", juan) or "all", ci)
        shots = [build_shot(e, md, y0, book, juan) for e in chunk]
        # 去掉内部字段前先取出来做统计
        stats = [{"anchored": s.pop("_anchored"), "sourceId": s.pop("_sourceId"),
                  "rawText": s.pop("_rawText")} for s in shots]
        ep = {
            "id": ep_id,
            "title": "%s · %s（%s）" % (book, juan or "选段", ci),
            "dynasty": "",
            "year": y0,
            "fps": FPS,
            "sourceNote": "⚠️ 本集由 auto_episode.py 自动生成：旁白取自史料原文**未经审定**，"
                          "地名仅为示意。发布前须人工审读。",
            "generatedFrom": {"candidates": str(args.candidates), "book": book, "juan": juan},
            "shots": shots,
        }
        f = outdir / ("%s.json" % ep_id)
        f.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")

        if not any(e["id"] == ep_id for e in manifest["episodes"]):
            manifest["episodes"].append({"id": ep_id, "episodeId": ep_id,
                                         "title": ep["title"]})
        anchored = sum(1 for s in stats if s["anchored"])
        report.append((ep_id, len(shots), anchored, y0, y1))

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    print("=== 批量生成完成 ===")
    print("候选事件 %d 条 → %d 集（每集 ≤%d 镜头）" % (len(events), len(chunks), per))
    print()
    print("%-22s %6s %8s %s" % ("episodeId", "镜头", "有锚点", "年份区间"))
    tot_s = tot_a = 0
    for eid, n, a, y0, y1 in report:
        print("%-22s %6d %8d %d–%d" % (eid, n, a, y0, y1))
        tot_s += n
        tot_a += a
    print()
    print("合计 %d 镜头 ｜ 有地点锚点 %d (%.0f%%) ｜ 纯全景+字幕 %d (%.0f%%)"
          % (tot_s, tot_a, tot_a / max(1, tot_s) * 100,
             tot_s - tot_a, (tot_s - tot_a) / max(1, tot_s) * 100))
    print()
    print("清单已更新：%s" % manifest_path)
    print("渲染：remotion render <episodeId>")
    print()
    print("📝 待处理（自动化只到骨架为止，表达留给具体制作时）：")
    print("  1. **旁白/台词全部留空** —— narrationHint 里备好了原文+出处+纪年，")
    print("     真正做这一集时由撰写者读史料后落笔，不要机械拼装")
    print("  2. %d 个镜头无地点锚点（用全景呈现），如需聚焦须补主表实体" % (tot_s - tot_a))
    print("  3. 人物覆盖有限 —— 需要人物旗标/势力色块时再扩 persons 层")


if __name__ == "__main__":
    main()
