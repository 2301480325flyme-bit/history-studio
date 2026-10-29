# -*- coding: utf-8 -*-
"""
二十四史 → 事件候选抽取器 v2（基于 corpus/*.jsonl）

v1 直接读 GBK TXT，问题：
  - 卷题只剩 10 个，无法定位；语料有 ≈12,351 处字符损坏
v2 改读 `01_工作流/corpus/*.jsonl`（由 build_corpus.py 从 word 版原文生成）：
  - **每条记录自带稳定 id**（如 晋书-p01234）→ 直接作为 source_ids 引用
  - **带 juanTitle / unitTitle** → 可按卷过滤、可产出「《晋书》卷四惠帝纪」
  - 损坏率 0.676%（v1 语料是 ≈12,351 处）

设计原则：
  1. **只扫描，不创作** —— 不做史实判断，不改写原文。
  2. **对库校验** —— 实体必须命中主表；命中不了进待审队列。
  3. **如实标记** —— 损坏、未登记实体全部标注，不隐藏。
  4. **不猜字** —— 不做「智能修复」，正则猜字会把正确内容改错。

用法：
    python extract_events.py scan 晋书 --top 30
    python extract_events.py scan 晋书 --juan 帝纪第四
    python extract_events.py entities 晋书
    python extract_events.py extract 晋书 --juan 帝纪第四 --out cand.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpus"

# 动作词表：史书动词 → 事件原语（见 视觉符号与动画库-v1.md L1）
ACTION_WORDS = {
    "raise": ["起兵", "举兵", "举义", "称兵"],
    "march": ["北征", "北伐", "东征", "西讨", "进军", "进兵", "引兵", "出师", "伐", "征", "讨"],
    "defeat": ["大破", "破之", "击败", "败之", "大败", "败绩", "大溃", "溃"],
    "capture": ["陷之", "入据", "攻", "拔", "克", "取", "据"],
    "siege": ["围城", "环攻", "急攻", "围"],
    "fall": ["陷落", "城陷", "失守", "没于"],
    "kill": ["赐死", "伏诛", "遇害", "杀", "诛", "斩", "弑"],
    "ascend": ["立为皇太弟", "即位", "践阼", "称帝", "称王", "即帝位", "继位"],
    "depose": ["废为庶人", "废", "幽"],
    "usurp": ["篡", "自立", "僭"],
    "defect": ["以城降", "归顺", "降"],
    "flee": ["出走", "北走", "南奔", "奔", "逃", "遁"],
    "enfeoff": ["徙封", "进爵", "封"],
    "ally": ["会盟", "结盟", "连和"],
    "move_capital": ["迁都", "徙都", "迁于", "都于"],
}
ACTION_INDEX = sorted([(v, w) for v, ws in ACTION_WORDS.items() for w in ws],
                      key=lambda x: -len(x[1]))


def load_corpus(book: str):
    p = CORPUS / ("%s.jsonl" % book)
    if not p.is_file():
        av = sorted(x.stem for x in CORPUS.glob("*.jsonl"))
        raise SystemExit("✗ 找不到语料 %s；可用：%s" % (p, "、".join(av)))
    return [json.loads(l) for l in p.open(encoding="utf-8")]


def detect_actions(text):
    """返回 {verb: 首个命中词}。长词优先，并屏蔽已被长词占用的位置。"""
    hit, used = {}, []
    for verb, word in ACTION_INDEX:
        if verb in hit:
            continue
        for m in re.finditer(re.escape(word), text):
            s = m.start()
            if any(s >= a and s < b for a, b in used):
                continue
            hit[verb] = word
            used.append((s, s + len(word)))
            break
    return hit


def split_sentences(text):
    out, start = [], 0
    for m in re.finditer(r"[。！？；]", text):
        out.append((text[start:m.end()], start))
        start = m.end()
    if start < len(text):
        out.append((text[start:], start))
    return out


def load_maindata():
    sys.path.insert(0, str(HERE))
    from maindata import MainData
    return MainData()


# 中文数字 → 序数（年号纪年用）
CN_ORD = {"元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
          "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
          "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20}


def build_era_index(md):
    """年号 → 起始公元年。只用 2 字年号，避免与普通词冲突。"""
    return {e["name"]: e for e in md.chronology["eras"] if len(e["name"]) == 2}


def find_years(records, md):
    """识别记录里的年号纪年 → 公元年。

    《晋书》帝纪的写法：「永康元年春正月…」「二年春…」（后续段落省年号）。
    因此需要**上下文追踪**：记住当前年号，遇到无年号的「N年」时沿用。

    返回 {record_id: {"year": int, "era": str, "ordinal": int, "inferred": bool}}
    """
    eras = build_era_index(md)
    era_names = sorted(eras, key=len, reverse=True)
    out, cur = {}, None
    pat_full = re.compile("(%s)(元|[一二三四五六七八九十]{1,3})年" % "|".join(era_names))
    pat_ord = re.compile(r"(元|[一二三四五六七八九十]{1,3})年")

    for r in records:
        m = pat_full.search(r["text"])
        if m:
            era, ordn_s = m.group(1), m.group(2)
            cur = eras[era]
            n = CN_ORD.get(ordn_s, 1)
            out[r["id"]] = {"year": cur["from"] + n - 1, "era": era,
                            "ordinal": n, "inferred": False}
            continue
        m2 = pat_ord.search(r["text"])
        if m2 and cur:
            n = CN_ORD.get(m2.group(1), 1)
            out[r["id"]] = {"year": cur["from"] + n - 1, "era": cur["name"],
                            "ordinal": n, "inferred": True}
    return out


def make_matcher(md):
    """别名 → (kind, id) 的最长匹配索引。别名现已封号优先。"""
    keys = {}
    for p in md.places:
        for a in set([p["id"]] + list(p.get("aliases", []))):
            if len(a) >= 2 and re.fullmatch(r"[\u4e00-\u9fff]+", a):
                keys[a] = ("place", p["id"])
    for p in md.persons:
        for a in set(list(p.get("aliases", [])) + [p["names"]["formal"]]):
            if a and len(a) >= 2 and re.fullmatch(r"[\u4e00-\u9fff]+", a):
                keys[a] = ("person", p["id"])
    if not keys:
        return None, {}
    pat = re.compile("|".join(re.escape(k) for k in sorted(keys, key=len, reverse=True)))
    return pat, keys


def in_juan(r, juan):
    if not juan:
        return True
    return juan in (r.get("juanTitle") or "") or juan in (r.get("unitTitle") or "")


def scan(records, top, juan=None, min_len=20):
    out = []
    for r in records:
        if not in_juan(r, juan):
            continue
        for sent, _ in split_sentences(r["text"]):
            s = sent.strip()
            if len(s) < min_len:
                continue
            acts = detect_actions(s)
            if not acts:
                continue
            out.append({
                "sourceId": r["id"],
                "juanTitle": r.get("juanTitle"),
                "unitTitle": r.get("unitTitle"),
                "text": s,
                "verbs": sorted(acts.keys()),
                "verbWords": acts,
                "score": len(acts),
                "damaged": r.get("damaged", []),
            })
    out.sort(key=lambda x: (-x["score"], len(x["text"])))
    return out[:top]


def extract(records, juan, matcher, keys, years=None):
    years = years or {}
    pool = [r for r in records if in_juan(r, juan)]
    if not pool:
        av = sorted({r.get("juanTitle") for r in records if r.get("juanTitle")})
        raise SystemExit("✗ 无匹配卷。可用卷题：%s" % "、".join(av[:30]))

    events, unknown = [], set()
    for r in pool:
        for sent, _ in split_sentences(r["text"]):
            s = sent.strip()
            if len(s) < 15:
                continue
            acts = detect_actions(s)
            if not acts:
                continue
            ents = {"place": [], "person": []}
            if matcher:
                for m in matcher.finditer(s):
                    kind, eid = keys[m.group(0)]
                    if eid not in ents[kind]:
                        ents[kind].append(eid)
            for m in re.finditer(r"[\u4e00-\u9fff]{2,4}(王|公|侯|州|郡|县|城|关)", s):
                if matcher and not matcher.search(m.group(0)):
                    unknown.add(m.group(0))
            events.append({
                "sourceId": r["id"],                 # ← 可直接作为 source_ids
                "juanTitle": r.get("juanTitle"),
                "unitTitle": r.get("unitTitle"),
                "year": (years.get(r["id"]) or {}).get("year"),
                "era": (years.get(r["id"]) or {}).get("era"),
                "yearInferred": (years.get(r["id"]) or {}).get("inferred"),
                "verbs": sorted(acts.keys()),
                "verbWords": acts,
                "placeIds": ents["place"],
                "personIds": ents["person"],
                "text": s,
                "damaged": r.get("damaged", []),
            })
    return pool, events, sorted(unknown)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "extract", "entities"])
    ap.add_argument("book", help="语料名，如 晋书")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--juan", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    recs = load_corpus(args.book)
    vols = sorted({r.get("juanTitle") for r in recs if r.get("juanTitle")})
    dmg = sum(1 for r in recs if r.get("damaged"))
    print("语料：%s.jsonl ｜ 段 %d ｜ 卷题 %d ｜ 损坏段 %d (%.2f%%)"
          % (args.book, len(recs), len(vols), dmg, dmg / max(1, len(recs)) * 100))

    if args.cmd == "scan":
        rows = scan(recs, args.top, args.juan)
        title = "=== 事件密度 Top %d%s ===" % (
            len(rows), ("（卷：%s）" % args.juan) if args.juan else "")
        print("\n" + title)
        for i, r in enumerate(rows, 1):
            flag = " ⚠损坏" if r["damaged"] else ""
            print("%2d. [%s / %s] 事件%d %s%s"
                  % (i, r["juanTitle"], r["unitTitle"], r["score"], "+".join(r["verbs"]), flag))
            print("    %s" % r["text"][:110])
            print("    来源：%s" % r["sourceId"])
        if args.out:
            Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print("\n已写出 %s" % args.out)

    elif args.cmd == "entities":
        md = load_maindata()
        matcher, keys = make_matcher(md)
        if not matcher:
            raise SystemExit("✗ 主表为空，先跑 build_maindata.py")
        counts = {"place": {}, "person": {}}
        for r in recs:
            for m in matcher.finditer(r["text"]):
                kind, eid = keys[m.group(0)]
                counts[kind][eid] = counts[kind].get(eid, 0) + 1
        print("\n=== 命中主表的实体（Top 20）===")
        for kind in ("place", "person"):
            print(" [%s]" % kind)
            for eid, n in sorted(counts[kind].items(), key=lambda x: -x[1])[:20]:
                print("   %-24s %d 次" % (eid, n))

    else:
        md = load_maindata()
        matcher, keys = make_matcher(md)
        years = find_years(recs, md)
        print("年号识别：%d 段有年号（其中 %d 段为上下文推断）"
              % (len(years), sum(1 for v in years.values() if v["inferred"])))
        pool, events, unknown = extract(recs, args.juan, matcher, keys, years)
        print("\n=== 抽取（卷：%s）===" % (args.juan or "全部"))
        print("命中段 %d ｜ 事件候选 %d ｜ 含损坏 %d ｜ 带年份 %d"
              % (len(pool), len(events), sum(1 for e in events if e["damaged"]),
                 sum(1 for e in events if e["year"])))
        print("\n前 12 条：")
        for e in events[:12]:
            flag = " ⚠" if e["damaged"] else ""
            yr = ("%d年" % e["year"]) if e["year"] else "—"
            print("  [%s]%s %s %s" % ("+".join(e["verbs"]), flag, yr, e["text"][:80]))
            print("        来源 %s ｜ 人 %s ｜ 地 %s"
                  % (e["sourceId"], ",".join(e["personIds"]) or "-",
                     ",".join(e["placeIds"]) or "-"))
        if unknown:
            print("\n未命中主表的实体候选（需人工核）：%s" % "、".join(unknown[:20]))
        if args.out:
            Path(args.out).write_text(json.dumps(
                {"book": args.book, "juan": args.juan, "events": events,
                 "unmatchedEntityCandidates": unknown},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print("\n已写出 %s" % args.out)


if __name__ == "__main__":
    main()
