# -*- coding: utf-8 -*-
"""
批量补州级地名 —— 让「沙盘」能锚定。

背景（实测）：抽取出的候选事件里 **85% 没有地点可锚定**，因为主表只有 13 个地点。
沙盘视频的核心是「地图上的动作」，没地点就没有沙盘。

做法：
  「州」是历史政治地理的稳定单元，数量有限（20–30 个覆盖大部分），
  **粒度恰好匹配沙盘宏观视野** —— 不需要精确到县城。

⚠️ 坐标来源与精度（必须诚实）：
  本表用的是**现代同名城市坐标**，作为「州级示意点」，
  不是当时州治的精确位置、也不是州域范围。
  理由：项目内无西晋州级坐标源（CHGIS v6 的西晋条目只有 51 个南方郡，
  北方大州缺失；郡县坐标更无从取得）。
  这与项目既有惯例一致 —— 如 `xuchang_approx` 自述为
  「approximate modern Xuchang locality」。

⚠️ **不写入正式主表**。
   正式主表 places.json 只放**可考证**的坐标；本脚本产出的州级示意点属于
   **临时近似层**，单独写到 places_approximate.json，运行时叠加、随时可弃。
   理由（实测）：build_maindata.py 每次重建主表会覆盖手工追加的条目 ——
   写进主表等于随时会被抹掉，且会混淆「已考证」与「暂用」两类数据。

用法：
    python add_region_places.py --dry-run          # 先看会加什么
    python add_region_places.py                    # 写 places_approximate.json
    python add_region_places.py --merge            # ⚠️ 强行并入主表（会随重建丢失）
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACES = HERE / "places.json"
APPROX = HERE / "places_approximate.json"

PRECISION = "州级示意——取现代同名城市坐标；非当时州治位置，非州域范围"

# 州名 → (现代城市坐标, 今日对应)
# 这些城市与历史上的州名同源（多数州名即由该地沿用至今）
REGIONS = {
    "荆州": ([112.2394, 30.3352], "湖北荆州"),
    "豫州": ([114.3542, 32.9800], "河南汝南"),
    "扬州": ([116.7857, 32.5762], "安徽寿县"),
    "徐州": ([117.2840, 34.2618], "江苏徐州"),
    "益州": ([104.0665, 30.5723], "四川成都"),
    "雍州": ([108.9398, 34.3416], "陕西西安"),
    "兖州": ([116.8263, 35.5521], "山东兖州"),
    "凉州": ([102.6380, 37.9283], "甘肃武威"),
    "并州": ([112.5489, 37.8706], "山西太原"),
    "幽州": ([116.4074, 39.9042], "北京"),
    "冀州": ([115.5794, 37.5509], "河北衡水冀州"),
    "秦州": ([105.7249, 34.5809], "甘肃天水"),
    "青州": ([118.4797, 36.6846], "山东青州"),
    "梁州": ([107.0319, 33.0776], "陕西汉中"),
    "江州": ([115.9928, 29.7125], "江西九江"),
    "广州": ([113.2644, 23.1291], "广东广州"),
    "司州": ([112.6183, 34.7195], "河南洛阳"),
    "平州": ([118.1802, 39.6304], "河北卢龙"),
    "宁州": ([102.7123, 25.0406], "云南昆明"),
    "交州": ([105.8342, 21.0278], "越南河内（境外，标注用）"),
    "武陵": ([111.6915, 29.0402], "湖南常德"),
    "吴郡": ([120.6196, 31.2994], "江苏苏州"),
    "彭城": ([117.2840, 34.2618], "江苏徐州（同徐州）"),
    "广陵": ([119.4129, 32.3942], "江苏扬州"),
    "宣城": ([118.7588, 30.9456], "安徽宣城"),
    "魏郡": ([114.5391, 36.6300], "河北邯郸临漳"),
    "会稽": ([120.5820, 29.9970], "浙江绍兴"),
    "丹阳": ([118.7969, 32.0584], "江苏南京"),
    "南郡": ([112.1906, 30.3503], "湖北荆州（江陵）"),
    "襄阳": ([112.1220, 32.0090], "湖北襄阳"),
}

# 排除：现代同名但历史语义完全不同的，或境外不宜作州级示意的
EXCLUDE = {"交州"}   # 河内在境外，标注可用但不作默认入表


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-cross-border", action="store_true",
                    help="是否加入境外示意点（如交州→河内）")
    ap.add_argument("--merge", action="store_true",
                    help="⚠️ 强行并入正式主表 places.json（不推荐：重建即丢失）")
    args = ap.parse_args()

    doc = json.loads(PLACES.read_text(encoding="utf-8"))
    existing = {p["id"] for p in doc["places"]}
    existing_alias = set()
    for p in doc["places"]:
        existing_alias.update(p.get("aliases", []))

    added, skipped = [], []
    for name, (coord, modern) in REGIONS.items():
        if name in EXCLUDE and not args.include_cross_border:
            skipped.append((name, "境外示意点，默认不入表"))
            continue
        if name in existing_alias or name in existing:
            skipped.append((name, "已存在"))
            continue
        pid = "region_" + name
        if pid in existing:
            skipped.append((name, "id 已存在"))
            continue
        added.append({
            "id": pid,
            "aliases": [name],
            "coordinates": coord,
            "coordinatePrecision": PRECISION,
            "coordinateSource": "现代同名城市坐标（地名同源）；非历史州治考证结论",
            "nameSource": "《%s》原文（corpus/*.jsonl 高频地名）" % "二十四史",
            "names": [{"text": name, "from": None, "to": None,
                       "note": "州级；年代范围未单独考证"}],
            "tiers": [],
            "roles": ["州级示意点（%s）" % modern],
            "usedIn": [],
            "coordinateConflict": "region-schematic",
            "coordinateStatus": "approximate",   # ⚠️ 临时近似，永不升级为 confirmed
            "provenance": {
                "kind": "temporary-approximation",
                "method": "现代同名城市坐标",
                "reason": "项目内无西晋州级坐标源（CHGIS v6 西晋条目仅 51 个南方郡，"
                          "北方大州缺失；郡县坐标更无从取得）",
                "notAHistoricalClaim": "本条**不是**历史州治/州域的考证结论，仅为沙盘锚定用的示意点",
                "promoteTo": "confirmed 前必须补：文物局公布坐标 / CHGIS 州级几何 / Wikidata listed 坐标",
                "sourceFile": "add_region_places.py",
            },
            "reviewNote": "州级示意点。坐标取现代同名城市，用于沙盘宏观锚定；"
                          "如需精确州治/州域，须另找西晋政区数据源。",
        })

    print("=== 批量补州级地名 ===")
    print("候选 %d 个 ｜ 将新增 %d 个 ｜ 跳过 %d 个"
          % (len(REGIONS), len(added), len(skipped)))
    print()
    print("%-8s %-22s %s" % ("州名", "示意坐标", "现代对应"))
    for a in added:
        print("%-8s %-22s %s"
              % (a["aliases"][0], "%.4f,%.4f" % tuple(a["coordinates"]),
                 a["roles"][0][6:-1]))
    if skipped:
        print()
        print("跳过：%s" % "、".join("%s(%s)" % s for s in skipped))
    print()
    print("⚠️ 精度声明：%s" % PRECISION)

    if args.dry_run:
        print("\n（--dry-run，未写入）")
        return

    if args.merge:
        doc["places"].extend(added)
        PLACES.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n⚠️ 已并入主表 %s（现共 %d 个）—— **重建主表时会丢失**" % (PLACES, len(doc["places"])))
        return

    base = json.loads(APPROX.read_text(encoding="utf-8")) if APPROX.is_file() else {
        "layer": "approximate",
        "note": "⚠️ 临时近似坐标层。与 places.json（可考证层）分开管理，"
                "运行时叠加、随时可弃。**本层所有条目 coordinateStatus=approximate，"
                "不得当作已考证坐标使用或升级为 confirmed。**",
        "places": [],
    }
    known = {p["id"] for p in base["places"]}
    base["places"].extend(a for a in added if a["id"] not in known)
    APPROX.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已写入临时近似层 %s（本层 %d 条，状态全部为 approximate）"
          % (APPROX, len(base["places"])))
    print("下一步：")
    print("  1. cp places.json ../remotion-shuihong/public/maindata/")
    print("  2. python extract_events.py extract 晋书 --juan 帝纪第四 --out cand.json")
    print("  3. python auto_episode.py cand.json --out-dir ... （看锚定率提升多少）")


if __name__ == "__main__":
    main()
