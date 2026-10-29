# -*- coding: utf-8 -*-
"""
从语料实测地名的出现年份范围，扩写 places.json 的 names.from/to。

背景：主表当前 names 年代范围只有 291–306（八王之乱窗口），
跨出这个范围 `place(name, year)` 就解析不了。本脚本用 33 万段语料
**实测**每个地名的出现年份，把范围扩到真实值。

⚠️ 只**扩展**范围，不缩小；已有的人工审定范围一律保留。

用法：
    python extend_ranges.py 晋书
    python extend_ranges.py --all
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpus"

CN_ORD = {"元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
          "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
          "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20}


def load_maindata():
    sys.path.insert(0, str(HERE))
    from maindata import MainData
    return MainData()


def year_of_records(records, md):
    """识别每段的公元年（年号 + 上下文推断）。"""
    eras = {e["name"]: e for e in md.chronology["eras"] if len(e["name"]) == 2}
    if not eras:
        return {}
    names = sorted(eras, key=len, reverse=True)
    pat_full = re.compile("(%s)(元|[一二三四五六七八九十]{1,3})年" % "|".join(names))
    pat_ord = re.compile(r"(元|[一二三四五六七八九十]{1,3})年")
    out, cur = {}, None
    for r in records:
        m = pat_full.search(r["text"])
        if m:
            cur = eras[m.group(1)]
            out[r["id"]] = cur["from"] + CN_ORD.get(m.group(2), 1) - 1
            continue
        m2 = pat_ord.search(r["text"])
        if m2 and cur:
            out[r["id"]] = cur["from"] + CN_ORD.get(m2.group(1), 1) - 1
    return out


def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    books = (sorted(x.stem for x in CORPUS.glob("*.jsonl"))
             if args[0] == "--all" else [args[0]])

    md = load_maindata()
    # 别名 → placeId
    alias2id = {}
    for p in md.places:
        for a in p.get("aliases", []):
            if len(a) >= 2:
                alias2id.setdefault(a, p["id"])

    span = {}   # placeId -> {min, max, count}
    for book in books:
        fp = CORPUS / ("%s.jsonl" % book)
        if not fp.is_file():
            print("  跳过（无 %s）" % fp.name)
            continue
        recs = [json.loads(l) for l in fp.open(encoding="utf-8")]
        years = year_of_records(recs, md)
        hits = 0
        for r in recs:
            y = years.get(r["id"])
            if y is None:
                continue
            for a in sorted(alias2id, key=len, reverse=True):
                if a in r["text"]:
                    pid = alias2id[a]
                    s = span.setdefault(pid, {"min": 9999, "max": -9999, "count": 0, "aliases": set()})
                    s["min"] = min(s["min"], y)
                    s["max"] = max(s["max"], y)
                    s["count"] += 1
                    s["aliases"].add(a)
                    hits += 1
        print("  %-8s 段 %6d ｜ 有年份 %6d ｜ 地名命中 %6d" % (book, len(recs), len(years), hits))

    if not span:
        raise SystemExit("✗ 未收集到任何地名年份")

    # 写回 places.json
    pf = HERE / "places.json"
    doc = json.loads(pf.read_text(encoding="utf-8"))
    changed = 0
    print("\n=== 年代范围扩写 ===")
    print("%-24s %-16s %-16s %s" % ("placeId", "原范围", "实测范围", "动作"))
    for p in doc["places"]:
        s = span.get(p["id"])
        if not s or not p.get("names"):
            continue
        names = p["names"]
        first, last = names[0], names[-1]
        old_from, old_to = first.get("from"), last.get("to")
        # ⚠️ 只扩「首段起点」与「末段终点」，**中间段一律不动**。
        #    否则像建康这种「建邺 282–312 / 建康 313–589」的双名地点，
        #    把首段 to 扩到 410 会覆盖掉后段，400 年就错显示成「建邺」。
        new_from = s["min"] if old_from is None else min(old_from, s["min"])
        new_to = s["max"] if old_to is None else max(old_to, s["max"])
        if (new_from, new_to) != (old_from, old_to):
            first["from"] = new_from
            last["to"] = new_to
            for nm in names:
                nm["rangeSource"] = "语料实测（%s）" % "、".join(books)
            first["rangeEvidence"] = "%d 次命中" % s["count"]
            changed += 1
            print("%-24s %-16s %-16s %s" % (p["id"], "%s–%s" % (old_from, old_to),
                                            "%s–%s" % (new_from, new_to),
                                            "扩写" + ("（%d 段名）" % len(names) if len(names) > 1 else "")))
        else:
            print("%-24s %-16s %-16s 不变" % (p["id"], "%s–%s" % (old_from, old_to),
                                            "%s–%s" % (new_from, new_to)))
    pf.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n扩写 %d 条 → %s" % (changed, pf))
    print("提示：把 places.json 复制到 remotion-shuihong/public/maindata/ 后生效")


if __name__ == "__main__":
    main()
