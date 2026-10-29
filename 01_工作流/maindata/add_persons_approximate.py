# -*- coding: utf-8 -*-
"""
人物候选 → 近似层 persons_approximate.json。

与 add_region_places.py 同款思路：**不写进正式 persons.json**。
理由实测：build_maindata.py 每次重建会覆盖手工追加的条目；
而且人物比地名更敏感 —— 「同一个人」都还没确认（「冏」是齐王冏还是别的？）。

⚠️ 近似层里的人物**只解决「让镜头出得了人」**，不解决身份考据：
  - 封号/全名/父子关系都可能错
  - territory（势力范围）一律为空
  - 颜色是自动分配的，**不代表真实势力**
  - 一律 verificationStatus = "unverified"

用法：
    python add_persons_approximate.py --candidates 待补人物.json --dry-run
    python add_persons_approximate.py --candidates 待补人物.json
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "persons_approximate.json"

# 自动配色：按频次从高到低分配，保证相邻候选视觉可区分。
# ⚠️ 这是**占位色**，不代表真实势力归属；确认后应逐个改。
PALETTE = [
    "#8c3424", "#1565c0", "#c2185b", "#6a1b9a", "#00695c",
    "#b8860b", "#4e342e", "#37474f", "#00838f", "#5d4037",
    "#ad1457", "#283593", "#00796b", "#795548", "#4527a0",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default="待补人物.json")
    ap.add_argument("--min-freq", type=int, default=4,
                    help="低于此频次不入表（噪声风险高）")
    ap.add_argument("--top", type=int, default=24)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = HERE / args.candidates
    if not src.is_file():
        raise SystemExit("✗ 找不到 %s（先跑 find_persons.py --out）" % src)
    cands = json.loads(src.read_text(encoding="utf-8"))["candidates"]
    # 人名优先，但**纯封号也要收** —— 实测帝纪第四里大量是「下邳王晃」「东平王楙」
    # 这种形式，能被匹配的其实是封号；只收人名的话覆盖率几乎不涨。
    people = [c for c in cands if c.get("freq", 0) >= args.min_freq]
    people = people[:args.top]

    # 抽取封号上下文（【齐王】这种），作为待确认线索
    import re
    out = []
    for i, c in enumerate(people):
        title = ""
        m = re.search(r"【([^】]+)】", c.get("sample") or "")
        if m:
            title = m.group(1)
        is_title_only = bool(c.get("isTitleOnly"))
        out.append({
            "id": "person_approx_%d" % i,
            "names": {"formal": c["name"], "title": title or (c["name"] if is_title_only else None)},
            # ⚠️ 纯封号条目只有封号别名 —— 父子同爵时会与具体人名条目抢匹配
            #    （如「齐王攸」与「齐王冏」都带「齐王」）。这在近似层是可接受的代价：
            #    认不出人就出不了旗标，认错人的代价只是颜色/说明文字待人工修。
            "aliases": ([c["name"]] + ([title + c["name"]] if title else [])) if not is_title_only
                        else [c["name"]],
            "matchGranularity": "title-only" if is_title_only else "title+name",
            "color": PALETTE[i % len(PALETTE)],
            "portrait": None,
            "realm": None,
            "realmSeat": None,
            "note": "⚠️ 近似人物：仅由语料词频发现，**身份未核实**。"
                    "封号/全名/关系/势力范围均待人工确认。",
            "appearsIn": [],
            "freq": c["freq"],
            "firstYear": c.get("firstYear"),
            "evidenceSample": c.get("sample"),
            "verificationStatus": "unverified",
            "provenance": {
                "kind": "frequency-derived-candidate",
                "method": "find_persons.py 两阶段（封号白名单 → 白名单后抽名）",
                "notAHistoricalClaim": "本条**不是**人物考证结论，只是词频候选。"
                                      "可能是同一人、也可能是误抽或同名异人。",
                "confirmBefore": "进入正式 persons.json 前必须确认：全名、封号、"
                                 "父子/兄弟关系、所属势力、颜色含义",
                "sourceFile": args.candidates,
            },
        })

    print("=== 人物近似层 ===")
    print("候选 %d 个（频次 ≥%d）｜ 将生成 %d 条" % (len(cands), args.min_freq, len(out)))
    print()
    print("%-4s %-10s %6s %-10s %s" % ("#", "名", "频次", "封号线索", "首见年"))
    for i, p in enumerate(out):
        print("%-4d %-10s %6d %-10s %s"
              % (i, p["names"]["formal"], p["freq"],
                 p["names"]["title"] or "—", p["firstYear"] or "—"))
    print()
    print("⚠️ 全部标记 verificationStatus=unverified：")
    print("   · 颜色是**自动占位色**，不代表真实势力")
    print("   · territory（势力范围）一律为空")
    print("   · 同一个人可能被拆成多条（如同名异人）")
    print("   用途仅限：**让镜头出得了人物旗标**，不作为考据依据。")

    if args.dry_run:
        print("\n（--dry-run，未写入）")
        return

    OUT.write_text(json.dumps({
        "layer": "approximate",
        "note": "⚠️ 人物近似层。由语料词频发现，身份未核实。"
                "与 persons.json（正式层）分开管理，运行时叠加、随时可弃。"
                "**本层所有条目 verificationStatus=unverified，不得当作已考证人物使用。**",
        "persons": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已写入 %s（本层 %d 条，全部 unverified）" % (OUT, len(out)))
    print("下一步：python extract_events.py extract 晋书 --juan 帝纪第四 --out cand.json")
    print("        看人物覆盖率是否提升")


if __name__ == "__main__":
    main()
