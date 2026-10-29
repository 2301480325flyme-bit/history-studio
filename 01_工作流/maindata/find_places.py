# -*- coding: utf-8 -*-
"""
地名候选自动发现 —— 从语料里捞出主表没有、但高频出现的地名。

为什么需要它：
  「沙盘视频」的核心是**地图上的动作**。但主表只有 13 个地点，
  抽取出的候选事件里 **85% 没有地点可锚定** —— 成片只能全景 + 字幕，
  沙盘感就没了。扩表是根本解法，而扩表的第一步是**知道缺哪些**。

做法：
  1. 用「通名后缀」模式捞候选：X州 / X郡 / X县 / X城 / X关 / X镇 …
  2. 统计频次与首次出现年份
  3. 与主表已有条目比对，输出**缺失清单**（按频次排序，便于按性价比补）

⚠️ 只产出**候选**，不自动入表 —— 地名坐标必须有出处（CHGIS / 文物局 / Wikidata）。
   坐标宁可缺，不可编。

用法：
    python find_places.py 晋书 --top 60
    python find_places.py --all --top 100 --out 待补地名.json
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpus"

# 通名后缀（按可信度排序）。只收 2–4 字的地名，避免把「XX刺史」这类误当专名。
SUFFIXES = ["州", "郡", "县", "城", "关", "镇", "邑", "津", "渡", "仓", "陵", "台", "宫", "殿"]
# 明确排除：官职/机构/泛称，避免污染
BLACKLIST = {
    "刺史", "太守", "都尉", "内史", "将军", "太守", "尚书", "仆射", "侍中",
    "诸州", "八州", "二州", "三州", "四州", "五州", "六州", "九州", "天下",
    "郡县", "州郡", "城县", "宫城", "皇城", "京城", "都城", "西城", "东城",
    "南城", "北城", "中城", "外城", "内城", "边城", "孤城", "空城",
}

CN_ORD = {"元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}


def load_maindata():
    sys.path.insert(0, str(HERE))
    from maindata import MainData
    return MainData()


def year_of(records, md):
    """段 → 公元年（年号 + 上下文推断）。"""
    eras = {e["name"]: e for e in md.chronology["eras"] if len(e["name"]) == 2}
    if not eras:
        return {}
    names = sorted(eras, key=len, reverse=True)
    full = re.compile("(%s)(元|[一二三四五六七八九十]{1,3})年" % "|".join(names))
    ordn = re.compile(r"(元|[一二三四五六七八九十]{1,3})年")
    out, cur = {}, None
    for r in records:
        m = full.search(r["text"])
        if m:
            cur = eras[m.group(1)]
            out[r["id"]] = cur["from"] + CN_ORD.get(m.group(2), 1) - 1
            continue
        m2 = ordn.search(r["text"])
        if m2 and cur:
            out[r["id"]] = cur["from"] + CN_ORD.get(m2.group(1), 1) - 1
    return out


def scan_book(book, md, known):
    fp = CORPUS / ("%s.jsonl" % book)
    if not fp.is_file():
        print("  跳过（无 %s）" % fp.name)
        return Counter(), {}
    recs = [json.loads(l) for l in fp.open(encoding="utf-8")]
    years = year_of(recs, md)

    freq = Counter()
    first_year = {}
    sample = {}
    pat = re.compile(r"[\u4e00-\u9fff]{1,3}(?:" + "|".join(SUFFIXES) + ")")
    for r in recs:
        for m in pat.finditer(r["text"]):
            cand = m.group(0)
            if len(cand) < 2 or cand in BLACKLIST or cand in known:
                continue
            # 排除「XX州刺史」这类官职残留（后一个字也是官名用字）
            if re.match(r"^.{2,3}(州刺史|郡太守|县令)$", cand):
                continue
            freq[cand] += 1
            y = years.get(r["id"])
            if y is not None:
                if cand not in first_year or y < first_year[cand]:
                    first_year[cand] = y
            if cand not in sample:
                sample[cand] = r["text"][:70]
    print("  %-8s 段 %6d ｜ 候选 %5d 个（去重前 %d）"
          % (book, len(recs), len(freq), sum(freq.values())))
    return freq, {"first_year": first_year, "sample": sample}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--min-freq", type=int, default=3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    books = (sorted(x.stem for x in CORPUS.glob("*.jsonl"))
             if args.all else ([args.book] if args.book else None))
    if not books:
        ap.error("需给出书名或用 --all")

    md = load_maindata()
    known = set()
    for p in md.places:
        known.update(p.get("aliases", []))
        known.update(n["text"] for n in p.get("names", []))

    total = Counter()
    meta = {"first_year": {}, "sample": {}}
    print("=== 扫描语料 ===")
    for b in books:
        f, m = scan_book(b, md, known)
        total.update(f)
        meta["first_year"].update(m["first_year"])
        meta["sample"].update(m["sample"])

    rows = [c for c, n in total.items() if n >= args.min_freq]
    rows.sort(key=lambda c: -total[c])
    rows = rows[:args.top]

    print()
    print("=== 主表缺失的高频地名 Top %d（频次 ≥%d）===" % (len(rows), args.min_freq))
    print("%-10s %6s %8s  %s" % ("候选", "频次", "首见年", "上下文"))
    for c in rows:
        print("%-10s %6d %8s  %s"
              % (c, total[c], meta["first_year"].get(c, "—"),
                 meta["sample"].get(c, "")[:40]))

    print()
    print("合计 %d 个候选 ｜ 主表现有 %d 个地名" % (len(rows), len(md.places)))
    print()
    print("⚠️ 这些只是**候选**，入表前必须补坐标出处：")
    print("   · CHGIS / 中国历史地图集（郡县级以上）")
    print("   · 文物局全国重点文物保护单位公布坐标")
    print("   · Wikidata（有 listed 坐标的遗址）")
    print("   坐标宁可缺，不可编 —— 见 maindata/README.md 的两条铁律。")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "note": "地名候选。须补坐标出处后方可入 places.json。",
            "scannedBooks": books,
            "candidates": [{"name": c, "freq": total[c],
                            "firstYear": meta["first_year"].get(c),
                            "sample": meta["sample"].get(c)} for c in rows],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n已写出 %s" % args.out)


if __name__ == "__main__":
    main()
