# -*- coding: utf-8 -*-
"""
从现有零散数据汇总生成主表（places / persons）。

设计原则：
  1. 机械汇总，不手抄 —— 避免引入新错误。
  2. 坐标冲突如实记录，不静默取舍 —— 符合项目「源数据异常如实记录」准则。
  3. 权威值来自 places_curated.json（有 coordinateSource / reviewNote 的策展源）；
     每集数据里的值写入 coordinatesAlt，并标注与权威值的偏差。
  4. 输出到 maindata/，不覆盖任何原文件。

⚠️ 数据现状（本脚本据此设计）：
    同一份 cities/events 数据在项目里存了 **三份**：
      - maindata 主表（策展）
      - dynasty/<集>/kings.json
      - dynasty/<集>/labels.json 的内嵌字段  ← Remotion 渲染实际读的是这一份
    三处必须同时汇总与统一，否则修了一处仍是分叉。
"""
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLOW = HERE.parent
REMOTION = FLOW / "remotion-shuihong" / "public" / "dynasty"
CURATED = FLOW / "places_curated.json"

# 人工覆盖项：无策展记录的次要地点，在此登记规范 id、备注。
# 这些值未经策展，坐标沿用各集数据，需后续补 coordinateSource。
OVERRIDES = {
    "阳翟": {"id": "yangzhai_approx", "note": "颍川属县，司马冏屯兵处。坐标未策展。"},
    "河内": {"id": "henei_approx", "note": "河内郡治，司马颙镇所。坐标未策展。"},
    "温县": {"id": "wenxian_approx", "note": "河内属县，司马氏故里。坐标未策展。"},
    "成皋": {"id": "chenggao_approx", "note": "洛阳东门户（虎牢）。坐标未策展。"},
    "濮阳": {"id": "puyang_approx", "note": "兖州濮阳，司马颖系据点。坐标未策展。"},
    "徐州": {"id": "xuzhou_region",
             "note": "州名，非城池点。八王之乱事件中作司马越起兵方向示意（illustrative）；"
                     "如需标点应补彭城坐标与出处。"},
    "成都": {"id": "chengdu_approx", "note": "蜀汉 / 成汉都城。坐标未策展，由政权主表引用。"},
    # ⚠️ 坐标覆盖：策展值经查证为错，改用手上有据的值
    "许昌": {
        "id": "xuchang_approx",
        "coordinates": [114.00971, 33.99189],
        "coordinateEvidence": {
            "decision": "adopt-kings-value",
            "authority": "汉魏许都故城，第七批全国重点文物保护单位（编号 7-0328-1-328）",
            "authorityCoordinate": [114.01926194, 33.98937194],
            "adoptedDeviationKm": 0.92,
            "rejectedValue": [113.85, 34.03],
            "rejectedReason": "该点位于现代许昌市区，距汉魏许都故城遗址约 16.2 km，"
                              "非汉代城址；原 places_curated 的 reviewNote 亦自述为"
                              "「legacy pilot approximation」",
            "source": "维基百科「汉魏许都故城」（引全国重点文物保护单位公布坐标）"
                      " + 许昌市建安区张潘镇古城村（村坐标 114.013258, 33.999383）",
        },
        "note": "汉魏许都故城（张潘故城）。曹操于建安元年（196）迎汉献帝都此。"
                "坐标已按国保单位公布值核正，见 coordinateEvidence。",
    },
    "平阳": {"id": "pingyang_approx", "note": "汉赵（前赵）都城。坐标未策展，由政权主表引用。"},
}

# 等级时间线（接符号库的 upgraded/downgraded morph）
# ⚠️ 必须覆盖全部年代区间：落在空档会退回默认值，画出错误的等级符号。
# 区间为「该地作为某等级治所的年代」，按史实沿革填写，缺口一律补 seat（治所）。
PERSON_CORRECTIONS = {
    "sima_you": {
        "title": "齐王",
        "note": "司马昭之子、晋武帝司马炎之弟，封齐王，官至大司马。太康四年薨。"
                "其子司马冏嗣齐王爵 —— 父子先后为齐王，注意区分。",
        "originalValues": {"title": "常山王", "note": "司马越之子，300年遇害"},
        "evidence": [
            "镇军大将军齐王攸为司空",
            "以司空齐王攸为大司马、督青州诸军事",
            "癸丑，大司马齐王攸薨",
            "以武帝的弟弟司马攸为继嗣",
        ],
        "sourceIds": ["jinshu-004"],
    },
    "sima_chi": {
        "title": "豫章王",
        "note": "先封豫章王，后立为皇太弟，继惠帝即位为晋怀帝。311 年永嘉之乱被俘遇害。",
        "originalValues": {"title": "河内王", "note": "继惠帝为怀帝，307年遇害"},
        "evidence": [
            "立皇子乂为长沙王，颍为成都王，晏为吴王，炽为豫章王",
            "豫章王炽先帝爱子，令闻日新，四海注意，今以为皇太弟",
            "唯豫章王炽、司徒王戎、仆射荀籓从",
        ],
        "sourceIds": ["jinshu-004", "jinshu-005"],
    },
    "sima_jiong": {
        "title": "齐王",
        "note": "齐献王司马攸之子，嗣齐王爵。301 年起兵讨赵王伦，302 年为长沙王乂所杀。",
        "originalValues": {"note": "301年起兵讨伦，302年被乂杀"},
        "evidence": [
            "齐王冏，字景治，献王攸之子也",
            "冏弟北海王寔",
        ],
        "sourceIds": ["jinshu-059"],
    },
}


# 坐标状态机 —— 决定一个坐标能否被称为「已确认」。
# ⚠️ 只有带权威证据的才能是 confirmed；临时近似必须留在 approximate。
COORD_STATUS = {
    "resolved-with-evidence": "confirmed",   # 有外部权威依据（如国保单位公布坐标）
    "region-schematic":       "approximate", # 州级示意点：现代同名城市坐标
    "single-source-unverified": "approximate",
    "recorded-not-resolved":  "approximate",
    "referenced-but-unregistered": "unregistered",   # 尚无坐标
}
DEFAULT_COORD_STATUS = "approximate"   # ⚠️ 缺标记一律按未确认处理，不默认 confirmed


def coord_status(conflict_kind):
    return COORD_STATUS.get(conflict_kind or "", DEFAULT_COORD_STATUS)


def make_aliases(formal: str, title: str):
    """生成别名，**封号优先**。

    实测结论：晋书原文几乎不用全名，一律称封号 ——
    《晋书》中「司马颙/司马乂/司马攸/司马炽」全名各 0 次，
    而「河间王」89、「长沙王」69、「齐王攸」40、「豫章王」15。
    → 别名必须以封号及其组合为主，否则抽取器命中率极低。
    """
    out = set()
    if title:
        out.add(title)                      # 河间王
        # 「司马X」是 3 字（司马+单名），取名字部分拼封号
        given = formal[2:] if formal.startswith("司马") else formal
        if given:
            out.add(title + given)          # 齐王攸 / 豫章王炽 / 河间王颙
    if formal:
        out.add(formal)                     # 司马攸
    return sorted(a for a in out if len(a) >= 2)



TIERS = {
    "luoyang_han_wei": [
        {"from": -202, "to": 316, "tier": "capital"},   # 东汉 / 曹魏 / 西晋都城
        {"from": 316, "to": 494, "tier": "seat"},       # 十六国时期
        {"from": 494, "to": 534, "tier": "capital"},    # 北魏孝文帝迁都后
        {"from": 534, "to": 9999, "tier": "seat"},      # 东魏以后降为州治
    ],
    "changan_han_city": [
        {"from": -202, "to": 25, "tier": "capital"},    # 西汉都城
        {"from": 25, "to": 313, "tier": "seat"},        # 东汉 / 魏晋为京兆治所
        {"from": 313, "to": 316, "tier": "capital"},    # 愍帝都长安
        {"from": 316, "to": 618, "tier": "seat"},       # 十六国 / 北朝
        {"from": 618, "to": 904, "tier": "capital"},    # 唐都
        {"from": 904, "to": 9999, "tier": "seat"},
    ],
    "ye_city": [
        {"from": -202, "to": 204, "tier": "seat"},
        {"from": 204, "to": 266, "tier": "capital"},    # 曹魏五都之一
        {"from": 266, "to": 335, "tier": "seat"},       # 西晋为魏郡治
        {"from": 335, "to": 370, "tier": "capital"},    # 后燕 / 前燕都
        {"from": 370, "to": 494, "tier": "seat"},
        {"from": 494, "to": 577, "tier": "capital"},    # 东魏 / 北齐都
        {"from": 577, "to": 9999, "tier": "seat"},
    ],
    "nanjing_ancient_city": [
        {"from": -202, "to": 229, "tier": "seat"},
        {"from": 229, "to": 280, "tier": "capital"},    # 孙吴都建业
        {"from": 280, "to": 317, "tier": "seat"},       # 西晋为丹阳郡治
        {"from": 317, "to": 589, "tier": "capital"},    # 东晋 / 南朝都建康
        {"from": 589, "to": 9999, "tier": "seat"},
    ],
    "xuchang_approx": [
        {"from": -202, "to": 196, "tier": "seat"},
        {"from": 196, "to": 220, "tier": "capital"},    # 汉献帝都许
        {"from": 220, "to": 9999, "tier": "seat"},      # 魏晋以下为颍川郡治
    ],
}


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def normalize(v):
    return "".join(str(v).casefold().split())


def km_between(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111.32 * math.cos(lat), (a[1] - b[1]) * 111.32)


def episode_sources():
    """产出 (集名, 来源文件, 数据) —— 覆盖 kings.json 与 labels.json 两份副本。"""
    for kf in sorted(REMOTION.glob("*/kings.json")):
        yield kf.parent.name, "kings.json", load_json(kf)
    for lf in sorted(REMOTION.glob("*/labels.json")):
        d = load_json(lf)
        if any(k in d for k in ("cities", "kings", "events")):
            yield lf.parent.name, "labels.json", d


# ---------- 1. 收集各集数据 ----------
curated = load_json(CURATED)["places"]
curated_by_alias = {}
for e in curated:
    curated_by_alias[normalize(e["id"])] = e
    for a in e.get("aliases", []):
        curated_by_alias[normalize(a)] = e
    for n in e.get("names", []):
        curated_by_alias[normalize(n["text"])] = e

cities = {}     # name(normalized) -> {...}
persons = {}    # id -> {...}
ev_refs = {}    # 事件引用但不在 cities 中的地点
episodes = set()
src_copies = {}  # (集, 地点) -> [(来源文件, coords)]

for ep, src, d in episode_sources():
    episodes.add(ep)
    for c in d.get("cities", []) or []:
        if "lon" not in c or "lat" not in c:
            continue
        key = normalize(c["name"])
        rec = cities.setdefault(key, {"name": c["name"], "coords": [c["lon"], c["lat"]],
                                      "roles": [], "usedIn": []})
        if c.get("role") and c["role"] not in rec["roles"]:
            rec["roles"].append(c["role"])
        if ep not in rec["usedIn"]:
            rec["usedIn"].append(ep)
        src_copies.setdefault((ep, rec["name"]), []).append((src, [c["lon"], c["lat"]]))

    for k in d.get("kings", []) or []:
        pid = k["id"]
        if pid not in persons:
            persons[pid] = {**k, "appearsIn": [], "_variants": {}}
        rec = persons[pid]
        if ep not in rec["appearsIn"]:
            rec["appearsIn"].append(ep)
        for fld, val in k.items():
            if fld == "id" or val is None or val == "":
                continue
            if rec.get(fld) in (None, "", []):
                rec[fld] = val
            elif rec[fld] != val:
                rec["_variants"].setdefault(fld, []).append(
                    {"episode": ep, "source": src, "value": val})

# 政权主表引用的都城 —— 也应纳入地名主表，否则政权指向了不存在的地点
_pw = HERE / "powers.json"
if _pw.is_file():
    for _p in load_json(_pw).get("powers", []):
        _cap = _p.get("capital")
        if not _cap:
            continue
        _key = normalize(_cap)
        if _key in cities:
            continue
        _r = ev_refs.setdefault(_key, {"name": _cap, "usedIn": [], "fields": set()})
        _r["fields"].add("power.capital")
        _r["usedIn"].append("（政权都城引用）")

for ev in d.get("events", []) or []:
    for fld in ("target", "from", "to"):
        v = ev.get(fld)
        if not v:
            continue
        key = normalize(v)
        if key in cities:
            continue
        r = ev_refs.setdefault(key, {"name": v, "usedIn": [], "fields": set()})
        if ep not in r["usedIn"]:
            r["usedIn"].append(ep)
        r["fields"].add(fld)

# 同一集内 kings.json 与 labels.json 坐标是否自相矛盾 —— 这是隐藏最深的重复源
intra_episode_conflicts = []
for (ep, name), copies in src_copies.items():
    vals = {tuple(v) for _, v in copies}
    if len(vals) > 1:
        intra_episode_conflicts.append((ep, name, copies))

# ---------- 2. 建 places 主表 ----------
places_out = []
conflicts = []

for key, rec in sorted(cities.items(), key=lambda x: x[1]["name"]):
    cur = curated_by_alias.get(key)
    ov = OVERRIDES.get(rec["name"], {})
    place_id = cur["id"] if cur else ov.get("id") or "TO_BE_ASSIGNED_" + re.sub(r"\W", "_", rec["name"])
    # 坐标优先级：人工覆盖 > 策展 > 各集数据
    if ov.get("coordinates"):
        coords_final = ov["coordinates"]
    elif cur:
        coords_final = cur["coordinates"]
    else:
        coords_final = rec["coords"]
    entry = {
        "id": place_id,
        "aliases": sorted({rec["name"]} | set(cur.get("aliases", []) if cur else [])),
        "coordinates": coords_final,
        "coordinatePrecision": cur.get("coordinatePrecision") if cur else
            "UNVERIFIED — 仅在各集数据中出现，未经策展；需补 coordinateSource",
        "coordinateSource": cur.get("coordinateSource") if cur else None,
        "nameSource": cur.get("nameSource") if cur else None,
        "names": cur.get("names") if cur else [{"text": rec["name"], "from": None, "to": None,
                                                "note": "年代范围未考证"}],
        "tiers": TIERS.get(place_id, []),
        "roles": rec["roles"],
        "usedIn": rec["usedIn"],
        "reviewNote": cur.get("reviewNote") if cur else ov.get("note", ""),
    }
    # 坐标状态：无坐标 → unregistered；否则按冲突类型映射，缺标记一律 approximate
    entry["coordinateStatus"] = (
        "unregistered" if not entry.get("coordinates")
        else coord_status(entry.get("coordinateConflict"))
    )
    if ov.get("coordinateEvidence"):
        entry["coordinateConflict"] = "resolved-with-evidence"
        entry["coordinateEvidence"] = ov["coordinateEvidence"]
        entry["coordinateStatus"] = coord_status("resolved-with-evidence")
    elif cur:
        d_km = km_between(cur["coordinates"], rec["coords"])
        if d_km > 0.05:
            entry["coordinatesAlt"] = [{
                "value": rec["coords"],
                "source": "dynasty/*/{kings,labels}.json（各集数据）",
                "deviationKm": round(d_km, 2),
                "adopted": False,
            }]
            entry["coordinateConflict"] = "recorded-not-resolved"
            conflicts.append((rec["name"], round(d_km, 2), cur["coordinates"], rec["coords"]))
    else:
        entry["coordinateConflict"] = "single-source-unverified"
    places_out.append(entry)

used_ids = {e["id"] for e in places_out if not e["id"].startswith("TO_BE_ASSIGNED")}
for e in curated:
    if e["id"] not in used_ids:
        places_out.append({**e, "tiers": TIERS.get(e["id"], []), "roles": [], "usedIn": [],
                           "coordinateConflict": "curated-not-yet-used"})

registered = set()
for e in places_out:
    registered.add(normalize(e["id"]))
    for a in e.get("aliases", []):
        registered.add(normalize(a))

for key, r in sorted(ev_refs.items()):
    if key in registered:
        continue
    ov = OVERRIDES.get(r["name"], {})
    places_out.append({
        "id": ov.get("id") or "UNREGISTERED_" + re.sub(r"\W", "_", r["name"]),
        "aliases": [r["name"]],
        "coordinates": None,
        "coordinatePrecision": "NONE — 仅被事件引用，尚无审定坐标",
        "coordinateSource": None, "nameSource": None,
        "names": [{"text": r["name"], "from": None, "to": None, "note": "年代范围未考证"}],
        "tiers": [], "roles": [], "usedIn": r["usedIn"],
        "referencedInFields": sorted(r["fields"]),
        "coordinateConflict": "referenced-but-unregistered",
        "coordinateStatus": "unregistered",
        "reviewNote": ov.get("note") or "被事件引用但未登记坐标；需补点，或改为方向示意（illustrative）。",
    })

(HERE / "places.json").write_text(
    json.dumps({"version": 1,
                "note": "地名主表。coordinates 为采纳值；coordinatesAlt 记录冲突来源，不静默丢弃。",
                "places": places_out}, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------- 3. 建 persons 主表 ----------
persons_out = []
corrections_applied = []
for pid, k in sorted(persons.items()):
    formal = k["name"]
    title = k.get("title", "")
    note = k.get("note", "")
    corr = PERSON_CORRECTIONS.get(pid)
    if corr:
        if corr.get("title"):
            title = corr["title"]
        if corr.get("note"):
            note = corr["note"]
        corrections_applied.append((formal, corr))
    entry = {
        "id": pid,
        "names": {"formal": formal, "title": title},
        "aliases": make_aliases(formal, title),
        "color": k.get("color"),
        "portrait": "portraits/%s_sq.png" % pid,
        "realm": k.get("realm"),
        "realm_valid": k.get("realm_valid"),
        "realm_note": k.get("realm_note"),
        "realmSeat": [k["lon"], k["lat"]] if "lon" in k else None,
        "note": note,
        "appearsIn": k.get("appearsIn", []),
        "fieldVariants": k.get("_variants", {}),
    }
    if corr:
        entry["correction"] = {
            "originalValues": corr["originalValues"],
            "evidence": corr["evidence"],
            "sourceIds": corr["sourceIds"],
            "note": "项目原数据与《晋书》原文冲突，按原文订正。见 史料查证.md。",
        }
    persons_out.append(entry)

(HERE / "persons.json").write_text(
    json.dumps({"version": 1,
                "note": "人物主表。aliases 用于别名归一（防 LLM 把同一人抽成多人）；"
                        "fieldVariants 记录跨集字段差异，不静默覆盖。",
                "persons": persons_out}, ensure_ascii=False, indent=2), encoding="utf-8")

# ⚠️ 人物订正表：项目原数据与《晋书》原文冲突时在此登记。
# **不静默修改** —— 每条都记录「原值 / 订正值 / 原文依据 / 出处 id」。
# 原文核验方式：corpus/晋书.jsonl（word 版原文，已重建）
# ---------- 4. 数据质量扫描 ----------
REPL = "\ufffd"
quality = []
for f in sorted(REMOTION.glob("*/*.json")):
    raw = f.read_text(encoding="utf-8")
    if REPL in raw:
        for m in re.finditer(r'"[^"]*' + REPL + r'[^"]*"', raw):
            quality.append((f.parent.name + "/" + f.name, m.group(0)))

# ---------- 5. 报告 ----------
L = ["# 主表汇总 · 冲突与数据质量报告", "",
     "由 `build_maindata.py` 自动生成。**本报告只记录，不修改任何源数据。**", "",
     "扫描集数：%d（%s）" % (len(episodes), "、".join(sorted(episodes))), "",
     "> ⚠️ 前置事实：同一份 `cities/kings/events` 在项目里存了 **三份** ——",
     "> 主表、`kings.json`、`labels.json` 内嵌字段（**Remotion 渲染实际读最后一份**）。",
     "> 三处必须同时统一，只修一处等于没修。", "",
     "## 一、坐标冲突（%d 处）" % len(conflicts), "",
     "采纳 `places_curated.json` 的策展值；各集值保留在 `coordinatesAlt`，未丢弃。", "",
     "| 地点 | 偏差 | 采纳值 | 各集值 |", "|---|---|---|---|"]
for name, d, c, r in sorted(conflicts, key=lambda x: -x[1]):
    L.append("| %s | **%.2f km** | `%s` | `%s` |" % (name, d, c, r))
L += ["", "> ⚠️ **许昌偏差 15.34 km 已超出制图误差范围，需人工判定哪套坐标正确。**", ""]

L += ["## 二、单源未验证地点", "",
      "| 地点 | id | 出现于 | 待办 |", "|---|---|---|---|"]
for e in places_out:
    if e.get("coordinateConflict") == "single-source-unverified":
        L.append("| %s | `%s` | %s | 补 coordinateSource 与策展值 |"
                 % (e.get("names", [{}])[0].get("text", e["id"]), e["id"], "、".join(e.get("usedIn", []))))

L += ["", "## 三、被事件引用但未登记坐标", ""]
for e in places_out:
    if e.get("coordinateConflict") == "referenced-but-unregistered":
        L.append("- **%s**（`%s`）被 %s 引用（字段：%s）→ %s"
                 % (e["aliases"][0], e["id"], "、".join(e["usedIn"]),
                    "、".join(e.get("referencedInFields", [])), e.get("reviewNote", "")))

L += ["", "## 四、人物跨集字段不一致", "",
      "已按「优先非空」合并，差异全部保留在 `persons.json` 的 `fieldVariants`。", "",
      "| 人物 | 字段 | 差异 |", "|---|---|---|"]
for pid, p in sorted(persons.items()):
    for fld, vs in p.get("_variants", {}).items():
        for v in vs:
            L.append("| %s | `%s` | %s 写 `%s`（主表取 `%s`）|"
                     % (p["name"], fld, v["episode"], v["value"], p.get(fld)))

L += ["", "## 五、同集内两份副本自相矛盾（%d 处）" % len(intra_episode_conflicts), ""]
if intra_episode_conflicts:
    L += ["同一集的 `kings.json` 与 `labels.json` 对同一地点写了不同坐标：", ""]
    for ep, name, copies in intra_episode_conflicts:
        detail = "；".join("%s → `%s`" % (s, v) for s, v in copies)
        L.append("- **%s** / %s：%s" % (ep, name, detail))
else:
    L.append("未发现 —— `kings.json` 与 `labels.json` 的坐标一致（但重复本身仍是隐患）。")

L += ["", "## 六、乱码字符（%d 处）" % len(quality), ""]
for ep, text in quality:
    L.append("- **%s**：%s" % (ep, text))
L += ["", "> 源文件存在 U+FFFD 替换字符，说明写入时已丢字。**须回源核对原文，不能猜。**", "",
      "## 七、已订正的史实（按《晋书》原文核实）", "",
      "新语料（word 版原文，见 `corpus/晋书.jsonl`）已能直接核实，**不再需要影印本**。", "",
      "| 人物 | 项目原写 | 订正为 | 原文依据 |", "|---|---|---|---|"]
for name, corr in corrections_applied:
    ov = corr["originalValues"]
    L.append("| %s | %s · %s | **%s** | 「%s」 |"
             % (name, ov.get("title", ""), ov.get("note", ""),
                corr.get("title", ""), corr["evidence"][0]))
L += ["", "> 完整证据链见 `persons.json` 的 `correction` 字段。", "",
      "### 仍未解决", "",
      "- `司马颙`：两集矛盾 —— 一版记「**镇河内**」，一版记「**镇关中**」。",
      "  新语料已确认「太原王颙为河间王」（改封关系），但**驻地证据不足，暂不改**。",
      "- `司马乂`：记「303年洛阳宫变杀贾后」。杀贾后者为赵王司马伦（300年），",
      "  司马乂杀齐王司马冏在 302 年。**待补证据后订正**。", "",
      "## 八、别名体系（已改为封号优先）", "",
      "实测：**《晋书》原文几乎不用全名，一律称封号**。同一语料词频 ——", "",
      "| 全名 | 次数 | 封号 | 次数 |", "|---|---|---|---|",
      "| 司马颙 | **0** | 河间王 | 89 |",
      "| 司马乂 | **0** | 长沙王 | 69 |",
      "| 司马攸 | **0** | 齐王攸 | 40 |",
      "| 司马炽 | **0** | 豫章王 | 15 |", "",
      "→ 别名已改为「封号 / 封号+名 / 全名」三层生成，见 `make_aliases()`。",
      "→ 旧别名错一个（司马炽写「河内王」）会导致抽取命中率差 **15 倍**。", "",
      "---", "",
      "## 处置建议", "",
      "1. **判定许昌坐标**（15.34 km 偏差过大，不能自动选）。",
      "2. `司马颙` / `司马乂` 补足原文证据后登记进 `PERSON_CORRECTIONS`。",
      "3. 跑 `resolve_dynasty.py` 产出 `*.resolved.json` 与 `*.byid.json`。"]

(HERE / "冲突报告.md").write_text("\n".join(L) + "\n", encoding="utf-8")

# ---------- 输出 ----------
print("集数:", sorted(episodes))
print("地名主表条目:", len(places_out))
print("人物主表条目:", len(persons_out))
print("坐标冲突:", len(conflicts))
for name, d, c, r in sorted(conflicts, key=lambda x: -x[1]):
    print("  %-6s 偏差 %6.2f km  采纳 %s  各集 %s" % (name, d, c, r))
bad = [e["id"] for e in places_out if e["id"].startswith("TO_BE_ASSIGNED")]
if bad:
    raise SystemExit("✗ 以下地点未登记规范 id，请在 OVERRIDES 中补上：%s" % bad)
print("✓ 全部地点均已登记规范 id")
if corrections_applied:
    print("✓ 已订正史实 %d 处：" % len(corrections_applied))
    for name, corr in corrections_applied:
        print("    %s：%s → %s（依据《晋书》原文）"
              % (name, corr["originalValues"].get("title", ""), corr.get("title", "")))
# 别名体系自检：确认封号类别名已生成
_p = {x["id"]: x for x in persons_out}
for _pid in ("sima_chi", "sima_you"):
    if _pid in _p:
        print("    别名 %s: %s" % (_p[_pid]["names"]["formal"], _p[_pid]["aliases"]))
