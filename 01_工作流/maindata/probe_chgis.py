# -*- coding: utf-8 -*-
"""
CHGIS 州级数据诊断 —— 报告**实际字段**，不做层级推断。

⚠️ 为什么必须这样：
   「CHGIS 里查到的面」**不等于**州界。
   CHGIS 的 pref 图层混合了「州 / 郡 / 府 / 其他」等不同层级，
   同一次检索里既有 zhou 也有 commandery。
   如果把检索结果笼统称作「州级 polygon」，就会把「郡界」当成「州界」用 ——
   这是**层级混淆**，画出来的地图是错的，而且错得很隐蔽（看着像那么回事）。

本脚本只做一件事：把每条记录的**原始字段**摊开，不解释、不合并、不推断。
看的人自己判断这个面是什么层级、能不能用。

用法：
    python probe_chgis.py                      # 看文件与字段概况
    python probe_chgis.py --layers             # 列出所有图层
    python probe_chgis.py --type 郡            # 按 TYPE_CH 精确筛选
    python probe_chgis.py --type 州 --yr 301    # 只看层级=州 且 覆盖 301
    python probe_chgis.py --coverage 301 311    # 看覆盖某年份的所有记录（含层级）
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
V6 = ROOT / "02_数据" / "CHGIS解压与坐标校验" / "v6check"

# 图层 → 行政层级的大致含义（**仅供参照，不作为层级判定**）
# ⚠️ CHGIS 的 TYPE_CH 才是权威字段；这里只是帮助阅读者建立预期。
LAYER_HINT = {
    "pref": "州级层面（但内含多种层级，须看 TYPE_CH）",
    "pre": "府级层面",
    "pgn": "郡级层面（但内含多种层级，须看 TYPE_CH）",
    "county": "县级",
}


def reader(path):
    import shapefile
    return shapefile.Reader(str(path))


def flds_of(r):
    return [f[0] for f in r.fields[1:]]


def dump(path, type_ch=None, yr=None, limit=40, show_geom=True):
    r = reader(path)
    flds = flds_of(r)
    print("文件：%s" % path.name)
    print("字段：%s" % ", ".join(flds))
    print("记录数：%d" % len(r))
    print()
    if "TYPE_CH" not in flds or "BEG_YR" not in flds:
        print("⚠️ 该图层缺 TYPE_CH / BEG_YR，无法按层级或年代筛选 —— 逐条列出：")
        for i, sr in enumerate(r.iterShapeRecords()):
            if i >= limit:
                print("  …（截断）")
                break
            print("  ", dict(zip(flds, sr.record)))
        return

    rows = []
    for sr in r.iterShapeRecords():
        p = dict(zip(flds, sr.record))
        if type_ch and str(p.get("TYPE_CH") or "").strip() != type_ch:
            continue
        if yr is not None:
            b, e = p.get("BEG_YR"), p.get("END_YR")
            if b is None or e is None:
                continue
            if not (int(b) <= yr[1] and int(e) >= yr[0]):
                continue
        rows.append((p, sr))

    if not rows:
        print("没有符合条件的记录。")
        return

    # 层级分布（不合并、不推断，只统计原始 TYPE_CH）
    dist = Counter(str(p.get("TYPE_CH") or "").strip() or "(空)" for p, _ in rows)
    print("=== 命中 %d 条，TYPE_CH 实际分布 ===" % len(rows))
    for k, v in dist.most_common():
        print("  TYPE_CH = %-14s %d 条" % (k, v))
    print()
    print("=== 逐条原始字段（name / type / beg_yr / end_yr / 几何）===")
    print("%-16s %-10s %-8s %-8s %-8s %s" % ("NAME_CH", "TYPE_CH", "BEG_YR", "END_YR", "点数", "几何"))
    for p, sr in rows[:limit]:
        n = len(sr.shape.points) if sr.shape.points else 0
        st = {1: "Point", 3: "PolyLine", 5: "Polygon", 8: "MultiPoint"}.get(
            sr.shape.shapeType, "type%s" % sr.shape.shapeType)
        print("%-16s %-10s %-8s %-8s %-8d %s"
              % (str(p.get("NAME_CH") or "")[:16], str(p.get("TYPE_CH") or ""),
                 p.get("BEG_YR"), p.get("END_YR"), n, st))
    if len(rows) > limit:
        print("  …（另有 %d 条未显示）" % (len(rows) - limit))
    print()
    print("⚠️ 提醒：以上 TYPE_CH 是**权威层级字段**。")
    print("   同一图层里可能同时有州与郡，**不要把它们统称为「州界」**。")
    print("   使用前逐条确认：几何是否为该层级的完整辖域、年代是否覆盖目标年份。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", action="store_true", help="列出所有可读图层")
    ap.add_argument("--file", default="v6_time_pref_pgn_utf_wgs84.shp")
    ap.add_argument("--type", dest="type_ch", default=None, help="按 TYPE_CH 精确筛选")
    ap.add_argument("--yr", nargs=2, type=int, metavar=("A", "B"), help="覆盖年份区间")
    ap.add_argument("--coverage", nargs=2, type=int, metavar=("A", "B"), help="同 --yr")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    if not V6.is_dir():
        raise SystemExit("✗ 找不到目录：%s" % V6)

    if args.layers:
        print("=== CHGIS v6 可读图层 ===")
        for shp in sorted(V6.glob("*.shp")):
            stem = shp.stem
            key = next((k for k in LAYER_HINT if k in stem), "—")
            try:
                r = reader(shp)
                print("  %-44s %5d 记录  [%s]" % (shp.name, len(r), LAYER_HINT.get(key, "?")))
            except Exception as e:
                print("  %-44s 读取失败：%s" % (shp.name, e))
        print()
        print("层级含义仅供参照，**判定层级请看 TYPE_CH 字段**。")
        return

    p = V6 / args.file
    if not p.is_file():
        raise SystemExit("✗ 找不到 %s\n  用 --layers 看可用的" % p)
    dump(p, args.type_ch, args.yr or args.coverage, args.limit)


if __name__ == "__main__":
    main()
