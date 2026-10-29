# -*- coding: utf-8 -*-
"""
影印 PDF 按页查工具 —— 把指定页导出为图片，供人工核对。

适用场景：语料里遇到存疑的字/人/地名（如「趟王」是否应为「赵王」），
翻到中华书局点校本原书那一页核对。**这是无文字层 PDF 最实用的用法**，
比全量 OCR（1458 页 / 1–4 小时 / 2–5% 错字）划算得多。

用法：
    # 按 PDF 页序导出单页（0 基）
    python pdf_lookup.py "<pdf>" --page 121

    # 按印刷页码导出（自动按当前偏移换算，偏移可用 --probe 校准）
    python pdf_lookup.py "<pdf>" --printed 79

    # 批量导出区间
    python pdf_lookup.py "<pdf>" --range 120 125

    # 校准「PDF 页序 ↔ 印刷页码」的偏移：导出若干页自己看一眼
    python pdf_lookup.py "<pdf>" --probe 100 110 120

    # 全文检索页码索引（需 OCR，可选；无 OCR 时用 --probe 人工定位）
    python pdf_lookup.py "<pdf>" --ocr-page 121
"""
import argparse
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "_pdf_pages"


def open_pdf(path: str):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise SystemExit("✗ 缺 pypdfium2：python -m pip install pypdfium2")
    return pdfium.PdfDocument(path)


def render(doc, idx: int, scale: float, tag: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    img = doc[idx].render(scale=scale).to_pil()
    p = OUT / ("%s.png" % tag)
    img.save(p)
    return p


def ocr_page(doc, idx: int, scale: float = 3.0) -> str:
    """可选：对单页做 OCR（需 pytesseract + 中文包）。失败则返回提示。"""
    try:
        import pytesseract  # type: ignore
    except ImportError:
        return "（未安装 pytesseract，跳过 OCR）"
    img = doc[idx].render(scale=scale).to_pil()
    try:
        return pytesseract.image_to_string(img, lang="chi_sim")
    except Exception as e:
        return "（OCR 失败：%s）" % e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, help="PDF 页序（0 基）")
    ap.add_argument("--printed", type=int, help="印刷页码（需配合 --offset）")
    ap.add_argument("--offset", type=int, default=None,
                    help="印刷页码 → PDF 页序 的偏移（PDF页序 = 印刷页码 - 1 + offset）")
    ap.add_argument("--range", nargs=2, type=int, metavar=("A", "B"), help="PDF 页序区间")
    ap.add_argument("--probe", nargs="+", type=int, help="导出若干页用于人工校准偏移")
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--ocr-page", type=int, help="对某页做 OCR 试验")
    args = ap.parse_args()

    p = Path(args.pdf)
    if not p.is_file():
        raise SystemExit("✗ 找不到：%s" % p)
    doc = open_pdf(str(p))
    print("文件：%s ｜ 共 %d 页" % (p.name, len(doc)))

    if args.probe:
        for i in args.probe:
            if 0 <= i < len(doc):
                f = render(doc, i, args.scale, "probe-%04d" % i)
                print("  导出 PDF 页 %-5d → %s" % (i, f))
        print("\n打开图片看页眉/页脚上的印刷页码，据此算出 offset：")
        print("  offset = 印刷页码 - 1 - PDF页序")
        return

    if args.ocr_page is not None:
        print("\n=== PDF 页 %d 的 OCR 试验 ===" % args.ocr_page)
        print(ocr_page(doc, args.ocr_page))
        return

    if args.page is not None:
        print("  导出 → %s" % render(doc, args.page, args.scale, "p%04d" % args.page))
        return

    if args.range:
        a, b = args.range
        for i in range(a, min(b + 1, len(doc))):
            print("  导出 → %s" % render(doc, i, args.scale, "p%04d" % i))
        return

    if args.printed is not None:
        if args.offset is None:
            raise SystemExit("✗ --printed 需要 --offset（先用 --probe 校准）")
        idx = args.printed - 1 + args.offset
        if not (0 <= idx < len(doc)):
            raise SystemExit("✗ 换算得 PDF 页序 %d，超出范围 0–%d" % (idx, len(doc) - 1))
        print("  印刷页 %d → PDF 页序 %d → %s"
              % (args.printed, idx, render(doc, idx, args.scale, "p%04d" % idx)))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
