# -*- coding: utf-8 -*-
"""
PDF 可用性检测 —— 判断一份 PDF 能不能直接抽文本，还是必须走 OCR。

核心判据（按重要性排序）：
  1. **有无文字层**：能 extract_text 出字 → 有；返回空 → 纯图片（必须 OCR）
  2. **文字层质量**：字数/页 是否正常；有无大量替换符、拉丁混入
  3. **繁简**：繁体原文通常比简体译本更接近史书原貌
  4. **OCR 典型错误**：形近字（人名地名最易错）—— 抽样人工核

用法：
    python check_pdf.py "D:/path/to/旧五代史.pdf"
"""
import re
import sys
from pathlib import Path

REPL = "\ufffd"
RE_LATIN = re.compile(r"[\u4e00-\u9fff][A-Za-z]{1,3}[\u4e00-\u9fff]")
TRAD = "國學說書時間們這樣經濟龍齊趙無與雲漢後唐晉為"
SIMP = "国学说书时间们这样经济龙齐赵无与云汉后唐晋为"


def load_pdf_text(path: Path, max_pages: int = 0):
    """返回 (每页文本列表, 引擎名)。优先 pdfplumber，退回 pypdf。"""
    pages = []
    engine = None
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(path)) as pdf:
            n = len(pdf.pages) if max_pages <= 0 else min(max_pages, len(pdf.pages))
            for i in range(n):
                pages.append(pdf.pages[i].extract_text() or "")
        engine = "pdfplumber"
    except ImportError:
        try:
            from pypdf import PdfReader  # type: ignore
            r = PdfReader(str(path))
            n = len(r.pages) if max_pages <= 0 else min(max_pages, len(r.pages))
            for i in range(n):
                pages.append(r.pages[i].extract_text() or "")
            engine = "pypdf"
        except ImportError:
            return None, None
    return pages, engine


def analyze(pages):
    joined = "\n".join(pages)
    total_chars = len(re.sub(r"\s", "", joined))
    empty_pages = sum(1 for p in pages if len(re.sub(r"\s", "", p)) < 10)
    per_page = total_chars / max(1, len(pages))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", joined))
    repl = joined.count(REPL)
    latin = len(RE_LATIN.findall(joined))
    trad = sum(joined.count(c) for c in TRAD)
    simp = sum(joined.count(c) for c in SIMP)
    return {
        "pages": len(pages),
        "chars": total_chars,
        "cjk": cjk,
        "perPage": per_page,
        "emptyPages": empty_pages,
        "replacement": repl,
        "latinMixed": latin,
        "tradScore": trad,
        "simpScore": simp,
        "sample": re.sub(r"\s+", "", joined)[:260],
    }


def verdict(st):
    if st["cjk"] == 0:
        return "❌ **纯图片 PDF**，无文字层 —— 必须走 OCR，成本高。建议改用其他版本。"
    if st["perPage"] < 60:
        return ("⚠️ **文字层过稀**（%.0f 字/页）—— 可能是图片 + 少量页码文字层。"
                "建议抽查内页，多半仍需 OCR。" % st["perPage"])
    if st["emptyPages"] / max(1, st["pages"]) > 0.3:
        return ("⚠️ **%.0f%% 的页无文字** —— 文字层不完整，混合型 PDF。"
                % (st["emptyPages"] / st["pages"] * 100))
    issues = []
    if st["replacement"] > 50:
        issues.append("替换符 %d 处" % st["replacement"])
    if st["latinMixed"] > 20:
        issues.append("拉丁混入 %d 处" % st["latinMixed"])
    base = "✅ **有可用文字层**（%.0f 字/页），可直接抽取。" % st["perPage"]
    if issues:
        base += " 但有质量问题：" + "、".join(issues) + "，抽取时须对库校验兜底。"
    return base


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit("✗ 找不到文件：%s" % path)
    print("文件：%s（%.1f MB）" % (path.name, path.stat().st_size / 1048576))

    pages, engine = load_pdf_text(path, max_pages=40)
    if pages is None:
        raise SystemExit("✗ 未安装 pdfplumber / pypdf。\n"
                         "  安装：python -m pip install pdfplumber")
    print("引擎：%s ｜ 采样 %d 页\n" % (engine, len(pages)))

    st = analyze(pages)
    print("=== 检测结果（采样前 %d 页）===" % st["pages"])
    print("  汉字数        %8d" % st["cjk"])
    print("  平均字数/页   %8.0f" % st["perPage"])
    print("  空页数        %8d  (%.0f%%)" % (st["emptyPages"], st["emptyPages"] / st["pages"] * 100))
    print("  替换符 U+FFFD %8d" % st["replacement"])
    print("  拉丁混入      %8d" % st["latinMixed"])
    print("  繁/简         %8d / %d  → %s"
          % (st["tradScore"], st["simpScore"],
             "繁体" if st["tradScore"] > st["simpScore"] else "简体"))
    print()
    print("=== 判定 ===")
    print(" ", verdict(st))
    print()
    print("=== 文本抽样（确认 OCR 质量）===")
    print(" ", st["sample"])
    print()
    print("=== 人工必查（OCR 最易错处）===")
    for kw in ["人名", "地名", "数字"]:
        print("  · %s：抽样比对纸质/权威版本" % kw)
    print("  · 特别注意形近字：趟/赵、遹/通、颙/颐、乂/义")


if __name__ == "__main__":
    main()
