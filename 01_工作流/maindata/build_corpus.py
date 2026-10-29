# -*- coding: utf-8 -*-
"""
语料构建器 v2 —— 支持 .doc（word 版）与 .txt（全译本）两种源。

为什么主源改用 word 版（实测结论）：
  word 版是 **文言原文**，带 **完整卷结构**（晋书 130/130），无扫描、无 OCR、无损坏；
  而全译本 TXT 是**白话译文**，卷题只剩 10 个，且有 ≈12,351 处字符损坏。

.doc 解析方式：
  用 olefile 读 OLE 的 WordDocument 流 → 按 FIB 的 fcMin/fcMac 取文本区
  → **UTF-16LE** 解码（实测汉字数 115.8 万，GBK 只有 48.8 万，故确认 UTF-16LE）

产出：
  corpus/<书>.txt      L1 清洗后纯文本（保留段落与卷题）
  corpus/<书>.jsonl    L2 分段 JSONL，一条 = 一个自然段
  corpus/构建报告.md    体量 / 卷题 / 质量统计

用法：
    python build_corpus.py --doc 5晋书.doc
    python build_corpus.py --txt 二十四史全译05.晋书.txt
    python build_corpus.py --doc-all
"""
import argparse
import json
import re
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DOC_DIR = ROOT / "02_数据" / "史料文献" / "word版"
TXT_DIR = ROOT / "02_数据" / "史料文献"
OUT = ROOT / "01_工作流" / "corpus"

CN = "一二三四五六七八九十百零"
META_RE = re.compile(r"^[　\s]*(作品|作者|内容简介|正文|目录)[：:]?[　\s]*$")
REPL = "\ufffd"
RE_LATIN = re.compile(r"[\u4e00-\u9fff][A-Za-z]{1,3}[\u4e00-\u9fff]")

# 卷题格式实测有四种，各不相同：
#   晋书/隋书  帝纪第一　高祖上
#   北齐书     卷一 帝纪第一
#   史记       史记卷一　五帝本纪　第一
#   宋史等     （同上变体）
# 统一判据：整行短、无句读、且含「第N」或「卷N」。
RE_VOLNUM = re.compile(r"(?:第|卷)[%s]+" % CN)


def is_vol_title(s: str) -> bool:
    if not s or len(s) > 32:
        return False
    if "。" in s or "，" in s:
        return False
    return bool(RE_VOLNUM.search(s))


def unit_from_voltitle(s: str):
    """从卷题行里尽力提取篇名。

    史记  史记卷一　五帝本纪　第一  → 五帝本纪
    隋书  帝纪第一　高祖上          → 高祖上
    北齐书 卷一 帝纪第一             → None（无独立篇名）
    """
    parts = [p for p in re.split(r"[　\s]+", s.strip()) if p]
    cand = [p for p in parts if not RE_VOLNUM.search(p) and not p.startswith("史记")
            and not re.match(r"^[一-鿿]{1,4}卷$", p)]
    if len(cand) == 1:
        return cand[0]
    return None


def extract_doc_text(path: Path) -> str:
    """.doc → 文本。OLE → WordDocument 流 → UTF-16LE。"""
    import olefile
    ole = olefile.OleFileIO(str(path))
    d = ole.openstream("WordDocument").read()
    fc_min, = struct.unpack("<i", d[24:28])
    fc_mac, = struct.unpack("<i", d[28:32])
    return d[fc_min:fc_mac].decode("utf-16-le", errors="replace")


def extract_txt_text(path: Path) -> str:
    return path.read_text(encoding="gbk", errors="replace")


def clean(raw: str) -> str:
    """去掉 Word 控制字符，统一段落分隔。"""
    t = raw.replace("\r\n", "\r").replace("\n", "\r")
    # \x07=单元格结束符, \x0b=软换行, \x0c=分页, \x13..\x15=域代码
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    t = re.sub(r"\r{2,}", "\r\r", t)
    return t


def build_records(text: str, book: str, source: str):
    """切段并识别卷题/篇题。

    实测：25 部 word 版里存在 **4 种不同结构**，不能一套规则打天下：
      A 行格式   单 \\r 即段落（晋书/史记/宋史…）—— 记录粒度 = 段落  ← 主流
      B 句读格式 正文几乎无 \\r（北齐书 59 个 / 周书 119 个）—— 粒度 = 句子
      C 字段格式 \\r\\r 分隔，卷题在「标题:」正文在「内容:」（汉书）—— 粒度 = 段落
      D 无编号篇名（三国志，篇名直接写「武帝纪」）—— 由 A 的篇名分支覆盖
    """
    records, seq = [], 0
    cur_vol, cur_unit = None, None
    in_body = False

    def emit(flat: str, rtype: str):
        nonlocal seq
        flat = flat.strip()
        if len(flat) < 6:
            return
        seq += 1
        damage = []
        if REPL in flat:
            damage.append("replacement")
        if RE_LATIN.search(flat):
            damage.append("latin-mixed")
        records.append({
            "id": "%s-p%05d" % (book, seq),
            "book": book, "source": source,
            "juanTitle": cur_vol, "unitTitle": cur_unit,
            "type": rtype,
            "text": flat,
            "charLen": len(flat),
            "sentCount": len(re.findall(r"[。！？；]", flat)),
            "damaged": damage,
        })

    if source != "doc":
        # ── txt：先重排硬换行，再按句读切句 ──
        def flush(buf):
            """把缓冲区的硬换行文本重排后按句读切句输出。"""
            if not buf:
                return
            joined = "".join(buf)
            start = 0
            for mm in re.finditer(r"[。；]", joined):
                emit(joined[start:mm.end()], "sentence")
                start = mm.end()
            if len(joined) - start >= 6:          # 尾部无句读的残句
                emit(joined[start:], "sentence")

        buf = []
        # ⚠️ clean() 会把 CRLF 统一成 \r，所以这里必须按 [\r\n]+ 分割。
        #    若只按 \n 分，整篇会变成一个巨型「行」，卷题与正文粘连。
        for raw_line in re.split(r"[\r\n]+", text):
            flat = raw_line.strip()
            if not flat:
                continue
            # 卷题：旧五代史卷一 / 卷三 / 志第一…（含书名前缀也可）
            if len(flat) <= 20 and re.search(r"卷[%s]+" % CN, flat):
                flush(buf)
                cur_vol, cur_unit, in_body = flat, None, True
                buf = []
                continue
            if re.match(r"^(纪第|志第|列传第|载记第|表第)[%s]+$" % CN, flat):
                # ⚠️ 换卷前必须先把上一卷累积的内容吐出来，
                #    否则每遇卷题就清空缓冲，只留最后一卷 —— 内容会大量丢失。
                flush(buf)
                cur_vol, cur_unit, in_body = flat, None, True
                buf = []
                continue
            # 篇名：太祖纪一 / 末帝纪上 / XX传（短行、无句读）
            if len(flat) <= 12 and "。" not in flat and "，" not in flat \
                    and re.search(r"(纪|传|志|表)[上中下一二三四五六七八九十]*$", flat):
                flush(buf)
                cur_unit = flat
                buf = []
                continue
            if re.match(r"^(作品|作者|内容简介|正文|目录)[：:]?$", flat):
                continue
            buf.append(flat)
        flush(buf)                                # 收尾
        return records

    # ── C 字段格式：标题: / 内容: ──
    if re.search(r"标题[:：]", text) and re.search(r"内容[:：]", text):
        for block in re.split(r"\r\r+", text):
            # ⚠️ 标题与「声明:」常在同一行，必须截断，否则整行超长被判为非卷题
            mt = re.search(r"标题[:：]\s*([^\r]{1,40}?)(?=声明|内容[:：]|版权|\r|$)", block)
            mc = re.search(r"内容[:：]\s*([\s\S]+)", block)
            if mt:
                t = mt.group(1).strip()
                if is_vol_title(t) or re.match(r"^[一-鿿]{1,8}(纪|传|志|表)", t):
                    cur_vol, cur_unit = t, None
            if mc:
                body = mc.group(1).replace("\r", "").strip()
                for piece in re.split(r"[　]{1,}", body):
                    if piece.strip():
                        emit(piece, "paragraph")
        return records

    cr_count = text.count("\r")

    # ── B 句读格式：正文无段落分隔，只能切句 ──
    if cr_count < 300:
        for raw_line in text.split("\r"):
            flat = raw_line.replace("\u3000", " ").strip()
            if not flat:
                continue
            if is_vol_title(flat):
                cur_vol, cur_unit, in_body = flat, unit_from_voltitle(raw_line), True
                continue
            if not in_body:
                continue
            start = 0
            for mm in re.finditer(r"[。；]", flat):
                emit(flat[start:mm.end()], "sentence")
                start = mm.end()
        return records

    # ── A 行格式（主流）──
    for raw_line in text.split("\r"):
        flat = raw_line.replace("\u3000", " ").strip()
        if not flat:
            continue
        if META_RE.match(flat):
            if "正文" in flat:
                in_body = True
            continue
        if is_vol_title(flat):
            cur_vol = flat
            cur_unit = unit_from_voltitle(raw_line)
            in_body = True
            continue
        # 篇名：短、无句读（晋书「宣帝」/ 三国志「武帝纪」）
        if len(flat) <= 12 and "。" not in flat and "，" not in flat:
            if in_body:
                cur_unit = flat
            continue
        if "。" in flat and len(flat) >= 20:
            in_body = True
        if not in_body:
            continue
        emit(flat, "paragraph")

    return records


def run(name: str, source: str, path: Path):
    raw = extract_doc_text(path) if source == "doc" else extract_txt_text(path)
    recs = build_records(clean(raw), name, source)
    if not recs:
        print("  ⚠️ %-8s 未提取到正文（格式可能不同，需单独检查）" % name)
        return None

    OUT.mkdir(parents=True, exist_ok=True)
    l1 = OUT / ("%s.txt" % name)
    l1.write_text("\n\n".join(r["text"] for r in recs) + "\n", encoding="utf-8")
    l2 = OUT / ("%s.jsonl" % name)
    with l2.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 卷题数：把「篇题」也算上（三国志这类只有篇名如「武帝纪」，无「卷N」）
    vols = list(dict.fromkeys(
        (r["juanTitle"] or r["unitTitle"]) for r in recs
        if (r["juanTitle"] or r["unitTitle"])
    ))
    dmg = sum(1 for r in recs if r["damaged"])
    no_vol = sum(1 for r in recs if not r["juanTitle"] and not r["unitTitle"])
    chars = sum(r["charLen"] for r in recs)
    print("  %-8s 段 %6d ｜ 卷/篇 %4d ｜ %7.1f 万字 ｜ 损坏 %4d ｜ 无锚点 %5d ｜ %.2f MB"
          % (name, len(recs), len(vols), chars / 10000, dmg, no_vol, l1.stat().st_size / 1048576))
    return {"book": name, "source": source, "paragraphs": len(recs), "chars": chars,
            "volumes": len(vols), "damaged": dmg, "noVolume": no_vol,
            "bytes": l1.stat().st_size, "jsonlBytes": l2.stat().st_size,
            "firstVols": vols[:6]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc")
    ap.add_argument("--txt")
    ap.add_argument("--doc-all", action="store_true")
    ap.add_argument("--out-name")
    args = ap.parse_args()

    if args.doc_all:
        jobs = [("doc", f) for f in sorted(DOC_DIR.glob("*.doc"))]
    elif args.doc:
        jobs = [("doc", DOC_DIR / args.doc)]
    elif args.txt:
        jobs = [("txt", TXT_DIR / args.txt)]
    else:
        ap.error("需指定 --doc / --txt / --doc-all")

    stats, report = [], ["# 语料构建报告 v2", "",
                         "> 由 `build_corpus.py` 生成。**只做结构化与损坏标记，不修复内容。**", "",
                         "| 书 | 源 | 段数 | 卷题 | 字数 | 损坏段 | 无卷题段 | L1 |",
                         "|---|---|---|---|---|---|---|---|"]
    for src, path in jobs:
        name = args.out_name or re.sub(r"^[0-9]+|[ .]", "", path.stem).strip()
        st = run(name, src, path)
        if st:
            stats.append(st)
            report.append("| %s | %s | %d | %d | %.1f 万 | %d | %d | %.2f MB |"
                          % (st["book"], st["source"], st["paragraphs"], st["volumes"],
                             st["chars"] / 10000, st["damaged"], st["noVolume"],
                             st["bytes"] / 1048576))

    if stats:
        report += ["", "## 合计", "",
                   "- 书 **%d** 部 ｜ 段 **%d** ｜ 字 **%.1f 万** ｜ 卷题 **%d**"
                   % (len(stats), sum(s["paragraphs"] for s in stats),
                      sum(s["chars"] for s in stats) / 10000, sum(s["volumes"] for s in stats)),
                   "", "## 卷题样例", ""]
        for s in stats[:10]:
            report.append("- **%s**：%s" % (s["book"], "、".join(s["firstVols"]) or "（无）"))
        (OUT / "构建报告.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        print("\n报告：%s" % (OUT / "构建报告.md"))


if __name__ == "__main__":
    main()
