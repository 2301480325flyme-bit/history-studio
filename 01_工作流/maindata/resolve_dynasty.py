# -*- coding: utf-8 -*-
"""
把各集数据的坐标统一到主表，产出行生文件 *.resolved.json。

⚠️ 必须同时处理两份副本：
    dynasty/<集>/kings.json
    dynasty/<集>/labels.json  ← 内嵌 cities/kings/routes/events，Remotion 渲染实际读这一份

原则：
  1. 不覆盖原文件 —— 输出 `*.resolved.json`，与源文件并存。
  2. 结构完全兼容 —— 字段不变，仅坐标改为主表采纳值，并新增 placeId / 溯源信息。
     因此可直接替换 Remotion 的读取路径，渲染代码零改动。
  3. 每次坐标改写都留痕 —— `_provenance` 记录原值与偏差。
"""
import json
from pathlib import Path
from maindata import MainData, DYNASTY

md = MainData()


def apply_person_corrections(d, md):
    """用人物主表覆盖各集的 kings 字段 —— 让史实订正传导到渲染。

    否则主表改了「司马炽 → 豫章王」，各集 labels.json 仍写「河内王」，
    画面就会显示错封号。
    """
    pmap = {p["id"]: p for p in md.persons}
    changed = []
    for k in d.get("kings", []) or []:
        p = pmap.get(k.get("id"))
        if not p:
            continue
        t = p["names"].get("title")
        if t and k.get("title") != t:
            changed.append({"person": p["names"]["formal"], "field": "title",
                            "from": k.get("title"), "to": t})
            k["title"] = t
        if p.get("note") and k.get("note") != p["note"]:
            if not any(c["person"] == p["names"]["formal"] and c["field"] == "note" for c in changed):
                changed.append({"person": p["names"]["formal"], "field": "note",
                                "from": k.get("note"), "to": p["note"]})
            k["note"] = p["note"]
        if p.get("aliases"):
            k["aliases"] = p["aliases"]
    return changed


def resolve_doc(d, src_name):
    """把 doc 里的 cities 坐标统一到主表，并把人物订正传导下去。"""
    prov, changed = [], 0
    prov += [{"action": "person-corrected", **c} for c in apply_person_corrections(d, md)]
    for c in d.get("cities", []) or []:
        e = md.place(c["name"])
        if not e:
            prov.append({"place": c["name"], "action": "unresolved",
                         "note": "主表中无此地点，坐标保留原值"})
            continue
        if not e.get("coordinates"):
            c["placeId"] = e["id"]
            prov.append({"place": c["name"], "placeId": e["id"], "action": "no-maindata-coord",
                         "note": "主表无坐标（仅被事件引用），保留原值"})
            continue
        old = [c.get("lon"), c.get("lat")]
        new = e["coordinates"]
        c["placeId"] = e["id"]
        if old != new:
            dev = md.km(old, new) if all(v is not None for v in old) else None
            c["lon"], c["lat"] = new[0], new[1]
            changed += 1
            prov.append({"place": c["name"], "placeId": e["id"], "action": "coord-unified",
                         "from": old, "to": new,
                         "deviationKm": round(dev, 2) if dev else None})
    d["_provenance"] = {
        "source": src_name,
        "resolvedBy": "maindata/resolve_dynasty.py",
        "mainTable": "maindata/places.json",
        "coordsChanged": changed,
        "changes": prov,
    }
    return changed, prov


def strip_to_ids(d, src_name):
    """把 cities 精简为只留 placeId + role + control —— **去掉 lon/lat**。

    这就是「id 引用」形态：坐标唯一来源于 maindata/places.json，
    各集数据不再持有坐标，从根本上消除分叉的可能。
    """
    out = dict(d)
    out["cities"] = [
        {k: v for k, v in c.items() if k not in ("lon", "lat")}
        for c in d.get("cities", []) or []
    ]
    out["_provenance"] = {
        **(d.get("_provenance") or {}),
        "source": src_name,
        "coordinatesStripped": True,
        "coordinatesSource": "maindata/places.json（由渲染层按 placeId 解析）",
        "note": "本文件不含坐标；渲染前须用主表补全 lon/lat",
    }
    return out


summary = []
for ep_dir in sorted(DYNASTY.iterdir()):
    if not ep_dir.is_dir():
        continue
    for src_name in ("kings.json", "labels.json"):
        src = ep_dir / src_name
        if not src.is_file():
            continue
        d = json.loads(src.read_text(encoding="utf-8"))
        if not d.get("cities"):
            continue          # labels.json 若不内嵌 cities，则无需处理
        # ① 坐标统一版（当前渲染输入，兼容）
        changed, prov = resolve_doc(d, src_name)
        out = ep_dir / src_name.replace(".json", ".resolved.json")
        out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        # ② id 引用版（目标形态：不含坐标）
        byid = strip_to_ids(d, src_name)
        (ep_dir / src_name.replace(".json", ".byid.json")).write_text(
            json.dumps(byid, ensure_ascii=False, indent=1), encoding="utf-8")
        summary.append((ep_dir.name, src_name, changed, len(prov)))

print("=== 坐标统一 + id 剥离完成 ===")
for name, src, ch, n in summary:
    print(" %-20s %-13s 改写 %d 处，溯源 %d 条" % (name, src, ch, n))
print("\n产出：")
print("  dynasty/*/{kings,labels}.resolved.json  坐标统一版（当前渲染输入）")
print("  dynasty/*/{kings,labels}.byid.json      纯 id 引用版（不含坐标，目标形态）")
print("  Remotion 端已支持按 placeId 从主表解析坐标，见 src/MainData.ts")
