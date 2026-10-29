# -*- coding: utf-8 -*-
"""
人物候选自动发现 —— 从语料捞出主表没有、但高频出现的人物。

为什么需要它：
  沙盘视频的另一半是**人**——旗标、肖像、势力范围都挂在人物上。
  但 persons 主表只有 8 人（八王），抽取时人物覆盖率仅 32.6%，
  大量「X王」「X公」识别不出来，镜头只能出地点、出不了人。

两阶段识别（中文没有词边界，单靠正则会把「敢距王命」里的「王」当封号）：
  阶段一  统计所有「X王 / X公 / X侯 / X伯」的出现频次，取高频者建**封号白名单**
  阶段二  **只在白名单封号后面**抽人名 —— 这样「凡此公卿」的「卿」就不会被误抽

用法：
    python find_persons.py 晋书 --top 40
    python find_persons.py --all --top 80 --out 待补人物.json
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpus"

# ⚠️ 只保留真正的爵位。「子」「君」会大量误抽：
#    「天子/太子/世子/中庶子」是亲属称谓，「君子/诸君」是泛称。
TITLES = ["王", "公", "侯", "伯"]
# 封号前缀不能是这些（指代/数量词，不构成专名）
BAD_PREFIX = ("此", "凡", "诸", "各", "二", "三", "前", "旧", "新")
# 明确排除：官职 / 机构 / 泛称 / 亲属称谓
BLACKLIST = {
    "诸侯", "天王", "上王", "下王", "先王", "大王", "王公", "王子", "王后",
    "公爵", "侯爵", "公卿", "王侯", "君臣", "父子", "兄弟", "夫妇",
    "太后", "皇后", "夫人", "嫔", "宫女", "群臣", "百官", "朝廷",
    "诸王", "诸公", "列侯", "列王", "藩王", "亲王",
    "相国", "丞相", "太尉", "司徒", "司空", "大司马", "大将军",
    "尚书", "仆射", "侍中", "中书令", "光禄", "卫尉", "廷尉",
    "刺史", "太守", "长史", "司马", "从事", "别驾", "祭酒", "国相",
    "将军", "校尉", "武职", "文官", "官职", "爵位", "封爵",
    "天子", "太子", "皇太子", "世子", "中庶子", "庶子", "嫡子", "二子", "三子",
    "君子", "小人", "明公", "王室", "帝王", "宗室", "公族", "勋贵",
    "无子", "字子", "时王", "及王", "王师", "王师败", "为王", "为皇太子",
    "女王", "王妃", "王孙", "先主", "后主", "本主", "业主", "元主",
    "汉", "魏", "晋", "楚", "秦", "齐", "周", "隋", "唐", "宋", "清",
    "汉主", "魏主", "晋主", "蜀主", "吴主", "虏", "贼", "寇",
}
SURNAMES = ["司马", "欧阳", "夏侯", "诸葛", "东方", "皇甫", "尉迟",
            "公孙", "慕容", "宇文", "李", "赵", "张", "王", "刘", "杨"]
# 「名」后面必须跟的边界 —— 避免把后续实词吃进名字
BOUND = r"(?=[\s，。、；：？！「」『』（）《》]|$)"

CN_ORD = {"元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}

_T = "|".join(TITLES)
_BP = "|".join(BAD_PREFIX)
# 封号：1–2 字前缀 + 爵位（如 赵王 / 琅邪王 / 菑阳公），左边界断言防误吃
PAT_TITLE = re.compile(r"(?<![\u4e00-\u9fff])"
                       r"((?:" + _BP + r")?[\u4e00-\u9fff]{1,2}(?:" + _T + r"))" + BOUND)
# 姓氏 + 名
PAT_SUR = re.compile(r"(?<![\u4e00-\u9fff])(司马|欧阳|夏侯|诸葛|东方|皇甫|尉迟|"
                     r"公孙|慕容|宇文|李|赵|张|王|刘|杨)"
                     r"([\u4e00-\u9fff]{1,2})" + BOUND)


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


def scan_book(book, md, known, min_title=3):
    fp = CORPUS / ("%s.jsonl" % book)
    if not fp.is_file():
        print("  跳过（无 %s）" % fp.name)
        return Counter(), {"first_year": {}, "sample": {}}
    recs = [json.loads(l) for l in fp.open(encoding="utf-8")]
    years = year_of(recs, md)

    # ── 阶段一：封号频次 → 白名单 ──
    title_freq = Counter()
    for r in recs:
        for m in PAT_TITLE.finditer(r["text"]):
            c = m.group(1)
            if c not in BLACKLIST:
                title_freq[c] += 1
    whitelist = sorted([t for t, n in title_freq.items() if n >= min_title],
                       key=len, reverse=True)
    if not whitelist:
        print("  ⚠️ %s 未找到高频封号，跳过" % book)
        return Counter(), {"first_year": {}, "sample": {}}
    pat_kn = re.compile("(" + "|".join(re.escape(t) for t in whitelist) + r")"
                        r"([\u4e00-\u9fff]{1,2})" + BOUND)
    print("  %-8s 段 %6d ｜ 封号白名单 %3d 个：%s"
          % (book, len(recs), len(whitelist), "、".join(whitelist[:10])))

    # ── 阶段二：白名单封号后抽人名 ──
    freq, first, sample = Counter(), {}, {}

    def add(key, rid, txt, m, label=None):
        if not key or key in BLACKLIST or key in known:
            return
        freq[key] += 1
        y = years.get(rid)
        if y is not None and (key not in first or y < first[key]):
            first[key] = y
        if key not in sample:
            a = max(0, m.start() - 14)
            sample[key] = (("【%s】" % label) + txt[a:m.end() + 20]) if label \
                else txt[a:m.end() + 20]

    for r in recs:
        txt = r["text"]
        for m in pat_kn.finditer(txt):          # ★ 白名单封号 + 名
            add(m.group(2), r["id"], txt, m, label=m.group(1))
        for m in PAT_SUR.finditer(txt):        # 姓氏 + 名
            add(m.group(1) + m.group(2), r["id"], txt, m)
        for m in PAT_TITLE.finditer(txt):      # 纯封号（参考用，前缀 ※）
            c = m.group(1)
            if c in title_freq and c not in BLACKLIST and c not in known:
                add("※" + c, r["id"], txt, m)
    return freq, {"first_year": first, "sample": sample}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--min-freq", type=int, default=3)
    ap.add_argument("--min-title", type=int, default=3, help="封号入白名单的最低频次")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    books = (sorted(x.stem for x in CORPUS.glob("*.jsonl"))
             if args.all else ([args.book] if args.book else None))
    if not books:
        ap.error("需给出书名或用 --all")

    md = load_maindata()
    known = set()
    for p in md.persons:
        known.add(p["names"]["formal"])
        known.update(p.get("aliases", []))

    total = Counter()
    meta = {"first_year": {}, "sample": {}}
    print("=== 扫描语料（两阶段）===")
    for b in books:
        f, m = scan_book(b, md, known, args.min_title)
        total.update(f)
        meta["first_year"].update(m["first_year"])
        meta["sample"].update(m["sample"])

    rows = [c for c, n in total.items() if n >= args.min_freq]
    rows.sort(key=lambda c: (c.startswith("※"), -total[c]))   # 人名优先
    rows = rows[:args.top]

    print()
    print("=== 主表缺失的高频人物候选 Top %d（频次 ≥%d）===" % (len(rows), args.min_freq))
    print("（※ = 纯封号；其余为「白名单封号+名」抽出的人名）")
    print("%-10s %6s %8s  %s" % ("候选", "频次", "首见年", "上下文"))
    for c in rows:
        print("%-10s %6d %8s  %s"
              % (c, total[c], meta["first_year"].get(c, "—"), meta["sample"].get(c, "")[:48]))

    print()
    print("合计 %d 个候选 ｜ 主表现有 %d 人" % (len(rows), len(md.persons)))
    print()
    print("⚠️ 这些只是**候选**。入表前必须确认：")
    print("   · 全名与封号（晋书原文几乎不用全名，一律称封号）")
    print("   · 父子/兄弟关系（如同「齐王攸」与「齐王冏」是父子，两代同爵）")
    print("   · 颜色与势力范围（用于旗标与势力色块）")
    print("   拿不准的先入**近似层**（与 places_approximate.json 同款做法），不要进正式主表。")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "note": "人物候选。须确认全名/封号/关系后入 persons.json；"
                    "不确定者入 persons_approximate.json（近似层）。",
            "method": "两阶段：封号频次建白名单 → 只在白名单后抽人名",
            "scannedBooks": books,
            "candidates": [{"name": c.lstrip("※"), "isTitleOnly": c.startswith("※"),
                            "freq": total[c], "firstYear": meta["first_year"].get(c),
                            "sample": meta["sample"].get(c)} for c in rows],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n已写出 %s" % args.out)


if __name__ == "__main__":
    main()
