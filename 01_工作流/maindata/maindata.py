# -*- coding: utf-8 -*-
"""
HistoryMap 主表装载器 + 校验器。

用法：
    python maindata.py check                  # 校验全部集数据
    python maindata.py check <集目录名>        # 校验单集
    python maindata.py place 洛阳 301          # 解析地名（含年代）
    python maindata.py person 司马越            # 解析人物（含别名归一）
    python maindata.py power 晋 300            # 解析政权（含年代）
    python maindata.py ganzhi 301              # 干支换算
    python maindata.py era 永康元年             # 年号换算

设计原则：
  1. 只读不改 —— 校验器不修改任何数据文件。
  2. 发现问题全部报告，不静默修正 —— 符合项目准则。
  3. 别名归一是防幻觉的核心：同一实体多个写法必须收敛到一个 id。
"""
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLOW = HERE.parent
DYNASTY = FLOW / "remotion-shuihong" / "public" / "dynasty"


def normalize(v):
    return "".join(str(v).casefold().split())


def load(name):
    p = HERE / name
    if not p.is_file():
        raise SystemExit("✗ 主表缺失：%s（先跑 build_maindata.py）" % p)
    return json.loads(p.read_text(encoding="utf-8"))


class MainData:
    def __init__(self, include_approximate: bool = True):
        # 正式层：只放可考证的坐标
        self.places = load("places.json")["places"]
        # 临时近似层：单独文件、单独状态，运行时叠加、随时可弃。
        # ⚠️ 这层的 coordinateStatus 一律 approximate，不得当作已考证坐标。
        self.approx_layer = HERE / "places_approximate.json"
        self.approx_count = 0
        if include_approximate and self.approx_layer.is_file():
            apx = json.loads(self.approx_layer.read_text(encoding="utf-8"))["places"]
            known = {e["id"] for e in self.places}
            for e in apx:
                if e.get("coordinateStatus") != "approximate":
                    raise SystemExit("✗ 近似层 %s 的 coordinateStatus 不是 approximate，"
                                     "近似层不得混入已确认坐标" % e.get("id"))
                if e["id"] not in known:
                    self.places.append(e)
                    self.approx_count += 1
        self.persons = load("persons.json")["persons"]
        # 人物近似层（同地名近似层，单独文件、单独状态）
        self.papprox_layer = HERE / "persons_approximate.json"
        self.papprox_count = 0
        if include_approximate and self.papprox_layer.is_file():
            pax = json.loads(self.papprox_layer.read_text(encoding="utf-8"))["persons"]
            pknown = {e["names"]["formal"] for e in self.persons}
            for e in pax:
                if e.get("verificationStatus") != "unverified":
                    raise SystemExit("✗ 人物近似层 %s 状态异常：%s"
                                     % (e.get("id"), e.get("verificationStatus")))
                nm = e["names"]["formal"]
                if nm not in pknown:
                    # ⚠️ 显式打标：近似层人物**默认不得进正片**。
                    #    画面上「抽出来了所以画上去了」是最容易犯的错，
                    #    所以这里做成显式字段，由渲染端过滤，而不是靠"恰好没用到"。
                    e = dict(e)
                    e["fromApproxLayer"] = True
                    e["identityStatus"] = "unverified"
                    self.persons.append(e)
                    self.papprox_count += 1
        # 可进正片的人物：仅正式层（不含近似层）。
        # 渲染端（DirectorComposition / KingPanel / KingMarker）必须用这个列表。
        self.persons_verified = [p for p in self.persons
                                 if not p.get("fromApproxLayer")]
        self.powers = load("powers.json")["powers"]
        self.chronology = load("chronology.json")
        self.citations = load("citations.json")["citations"]

        self.place_by_key = {}
        for e in self.places:
            self.place_by_key[normalize(e["id"])] = e
            for a in e.get("aliases", []):
                self.place_by_key.setdefault(normalize(a), e)
            for n in e.get("names", []):
                self.place_by_key.setdefault(normalize(n["text"]), e)

        self.person_by_key = {}
        for e in self.persons:
            self.person_by_key[normalize(e["id"])] = e
            for a in e.get("aliases", []):
                self.person_by_key.setdefault(normalize(a), e)
            for v in e.get("names", {}).values():
                if v:
                    self.person_by_key.setdefault(normalize(v), e)

        self.power_by_key = {}
        for e in self.powers:
            self.power_by_key[normalize(e["id"])] = e
            for a in e.get("aliases", []):
                self.power_by_key.setdefault(normalize(a), []).append(e) \
                    if isinstance(self.power_by_key.get(normalize(a)), list) \
                    else self.power_by_key.setdefault(normalize(a), [e])

        self.citation_by_key = {}
        for e in self.citations:
            self.citation_by_key[normalize(e["id"])] = e
            for a in e.get("aliases", []):
                self.citation_by_key.setdefault(normalize(a), e)

    # ---------- 解析 ----------
    def place(self, query, year=None):
        e = self.place_by_key.get(normalize(query))
        if not e:
            return None
        if year is not None:
            active = [n for n in e.get("names", [])
                      if (n.get("from") is None or year >= n["from"])
                      and (n.get("to") is None or year <= n["to"])]
            if e.get("names") and not active:
                return {"_error": "%s 在 %s 年无审定的名称" % (query, year), "entry": e}
            if active:
                e = {**e, "activeName": active[0]["text"]}
            tiers = [t for t in e.get("tiers", [])
                     if (t.get("from") is None or year >= t["from"])
                     and (t.get("to") is None or year <= t["to"])]
            e = {**e, "activeTier": tiers[0]["tier"] if tiers else None}
        return e

    def person(self, query):
        return self.person_by_key.get(normalize(query))

    def power(self, query, year=None):
        e = self.power_by_key.get(normalize(query))
        if isinstance(e, list):
            return {"_ambiguous": [x["id"] for x in e],
                    "resolved": [x for x in e
                                 if year is None or (x["life"]["from"] <= year <= x["life"]["to"])]}
        return e

    def citation(self, cid):
        return self.citation_by_key.get(normalize(cid))

    # ---------- 换算 ----------
    def year_to_ganzhi(self, year):
        st = self.chronology["ganzhi"]
        return st["cycle"][(int(year) - 4) % 60]

    def era_to_year(self, era_name, ordinal=1):
        hits = [e for e in self.chronology["eras"] if normalize(e["name"]) == normalize(era_name)]
        if not hits:
            return None
        return {"candidates": [{"id": h["id"], "year": h["from"] + int(ordinal) - 1,
                                "ruler": h["ruler"]} for h in hits]}

    # ---------- 校验 ----------
    def km(self, a, b):
        lat = math.radians((a[1] + b[1]) / 2)
        return math.hypot((a[0] - b[0]) * 111.32 * math.cos(lat), (a[1] - b[1]) * 111.32)

    def check_doc(self, ep, src, d):
        """校验一份文档（kings.json 或 labels.json）里的 cities/kings/events。"""
        issues = []

        # 1. 城池：能否解析 + 坐标是否与主表一致
        for c in d.get("cities", []) or []:
            e = self.place(c["name"])
            if not e:
                issues.append("[%s][地名] 「%s」不在主表中 —— 需登记后使用" % (src, c["name"]))
                continue
            if "lon" in c and e.get("coordinates"):
                dev = self.km(e["coordinates"], [c["lon"], c["lat"]])
                if dev > 0.05:
                    issues.append("[%s][坐标] 「%s」与主表偏差 %.2f km（集 %s / 主表 %s）"
                                  % (src, c["name"], dev, [c["lon"], c["lat"]], e["coordinates"]))
            ctrl = c.get("control", [])
            for i in range(len(ctrl) - 1):
                if ctrl[i][1] < ctrl[i + 1][0] - 1:
                    issues.append("[%s][时间线] 「%s」控制权 %s–%s 与 %s–%s 之间有断档"
                                  % (src, c["name"], ctrl[i][0], ctrl[i][1],
                                     ctrl[i + 1][0], ctrl[i + 1][1]))

        # 2. 人物 id
        for k in d.get("kings", []) or []:
            if not self.person(k["id"]):
                issues.append("[%s][人物] id「%s」不在人物主表中" % (src, k["id"]))

        # 3. 事件里的 actor / 地点
        known_city = {normalize(c["name"]) for c in (d.get("cities", []) or [])}
        for ev in d.get("events", []) or []:
            if ev.get("actor") and not self.person(ev["actor"]):
                issues.append("[%s][事件] actor「%s」不在人物主表" % (src, ev["actor"]))
            for fld in ("target", "from", "to"):
                v = ev.get(fld)
                if v and normalize(v) not in known_city and not self.place(v):
                    issues.append("[%s][事件] %s「%s」既不在本集城池也不在主表" % (src, fld, v))

        # 4. 控制者 id
        for c in d.get("cities", []) or []:
            for a, b, who in c.get("control", []):
                if who and not self.person(who):
                    issues.append("[%s][归属] 「%s」的控制者 id「%s」不在人物主表"
                                  % (src, c["name"], who))
        return issues

    def check_episode(self, ep_dir):
        """校验一集的两份副本文档；返回 {shape, issues}。"""
        ep_dir = Path(ep_dir)
        all_issues, shapes = [], []
        for src in ("kings.json", "labels.json"):
            f = ep_dir / src
            if not f.is_file():
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            if not d.get("cities"):
                shapes.append(src + "(无 cities)")
                continue
            shapes.append(src)
            all_issues += self.check_doc(ep_dir.name, src, d)
        return {"shape": "+".join(shapes) if shapes else "empty", "issues": all_issues}

    def check_all(self):
        report = {}
        for d in sorted(DYNASTY.iterdir()):
            if d.is_dir():
                report[d.name] = self.check_episode(d)
        return report

    # ---------- 资产自校验（模板 / 纪年 / 引文 / 政权） ----------
    # 合法动词表 —— 与 remotion-shuihong/src/ActionLayer.tsx 的 ActionVerb 保持一致
    KNOWN_VERBS = {
        "march", "capture", "defeat", "kill", "siege", "fall",
        "ascend", "depose", "usurp", "raise", "defect", "flee",
        "enfeoff", "ally", "move_capital", "aftermath",
    }
    KNOWN_CAMERAS = {"dolly_in", "dolly_out", "pan", "track", "orbit",
                     "crane", "shake", "hold", "fade", "ink_bleed",
                     "scroll_unfurl", "year_flip", "map_fold", "wipe"}

    def check_assets(self):
        """校验模板、纪年、引文、政权的内部一致性。返回问题列表。"""
        issues = []
        reuse = HERE / "reuse"

        # 1. 事件序列模板
        if (reuse / "eventSequence.json").is_file():
            tpls = json.loads((reuse / "eventSequence.json").read_text(encoding="utf-8"))["templates"]
            seen_ids = set()
            for t in tpls:
                if t["id"] in seen_ids:
                    issues.append("[模板] 重复 id：%s" % t["id"])
                seen_ids.add(t["id"])
                for st in t.get("sequence", []):
                    if st["verb"] not in self.KNOWN_VERBS:
                        issues.append("[模板] %s 使用了未知动词「%s」（不在 ActionLayer 定义中）"
                                      % (t["id"], st["verb"]))
                    cam = st.get("camera")
                    if cam and cam not in self.KNOWN_CAMERAS:
                        issues.append("[模板] %s 使用了未知运镜「%s」" % (t["id"], cam))
                # 参数占位符必须都在 required/optional 里声明
                declared = set(t.get("required", [])) | set(t.get("optional", []))
                for st in t.get("sequence", []):
                    for v in (st.get("params") or {}).values():
                        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
                            name = v[1:-1]
                            if name not in declared:
                                issues.append("[模板] %s 引用了未声明的谓词「{%s}」" % (t["id"], name))

        # 2. 节奏骨架
        if (reuse / "pacingProfile.json").is_file():
            profs = json.loads((reuse / "pacingProfile.json").read_text(encoding="utf-8"))["profiles"]
            for p in profs:
                total = sum(s["sec"] for s in p["slots"])
                if total != p["totalSec"]:
                    issues.append("[节奏] %s 槽位合计 %ds ≠ 声明总长 %ds"
                                  % (p["id"], total, p["totalSec"]))
                if not any(s["role"] == "hook" for s in p["slots"]):
                    issues.append("[节奏] %s 缺少 hook 槽位（爆款必备 0–3s 钩子）" % p["id"])

        # 3. 运镜句式
        if (reuse / "cameraPhrase.json").is_file():
            phs = json.loads((reuse / "cameraPhrase.json").read_text(encoding="utf-8"))["phrases"]
            for ph in phs:
                for sh in ph.get("shots", []):
                    cam = sh.get("camera")
                    if cam and cam not in self.KNOWN_CAMERAS:
                        issues.append("[运镜] %s 使用了未知镜头「%s」" % (ph["id"], cam))
                    if sh.get("verb") and sh["verb"] not in self.KNOWN_VERBS:
                        issues.append("[运镜] %s 引用了未知动词「%s」" % (ph["id"], sh["verb"]))

        # 4. 纪年表
        eras = self.chronology["eras"]
        ids = [e["id"] for e in eras]
        for dup in {i for i in ids if ids.count(i) > 1}:
            issues.append("[纪年] 重复 id：%s" % dup)
        for e in eras:
            if e["from"] > e["to"]:
                issues.append("[纪年] %s 起始年 %d 晚于结束年 %d" % (e["id"], e["from"], e["to"]))
            if not self.power(e.get("dynasty") or "", e["from"]):
                issues.append("[纪年] %s 的 dynasty「%s」不在政权主表中" % (e["id"], e.get("dynasty")))

        # 5. 引文库
        cids = [c["id"] for c in self.citations]
        for dup in {i for i in cids if cids.count(i) > 1}:
            issues.append("[引文] 重复 id：%s" % dup)
        alias_seen = {}
        for c in self.citations:
            for a in c.get("aliases", []):
                if a in alias_seen:
                    issues.append("[引文] 别名「%s」被 %s 与 %s 同时占用"
                                  % (a, alias_seen[a], c["id"]))
                alias_seen[a] = c["id"]
                if a in cids:
                    issues.append("[引文] 别名「%s」与某个 canonical id 冲突" % a)

        # 6. 政权主表
        pids = [p["id"] for p in self.powers]
        for dup in {i for i in pids if pids.count(i) > 1}:
            issues.append("[政权] 重复 id：%s" % dup)
        for p in self.powers:
            if p["life"]["from"] >= p["life"]["to"]:
                issues.append("[政权] %s 生命周期不合法：%d–%d"
                              % (p["id"], p["life"]["from"], p["life"]["to"]))
            cap = p.get("capital")
            if cap and not self.place(cap):
                issues.append("[政权] %s 的都城「%s」不在地名主表中" % (p["id"], cap))

        # 7. 地名主表：tiers 时间线不得有重叠或倒置
        for pl in self.places:
            tiers = pl.get("tiers") or []
            for i, t in enumerate(tiers):
                if t.get("from") is not None and t.get("to") is not None and t["from"] >= t["to"]:
                    issues.append("[地名] %s 的 tiers[%d] 区间不合法：%s–%s"
                                  % (pl["id"], i, t["from"], t["to"]))
                if i and tiers[i - 1].get("to") is not None and t.get("from") is not None \
                        and t["from"] < tiers[i - 1]["to"]:
                    issues.append("[地名] %s 的 tiers[%d] 与上一段重叠" % (pl["id"], i))
        # 8. 正片人物白名单：近似层人物不得混入 persons_verified
        approx_p = [p for p in self.persons if p.get("fromApproxLayer")]
        for p in approx_p:
            if p in self.persons_verified:
                issues.append("[人物] %s 来自近似层（unverified），不得进入正片白名单"
                              % p["names"]["formal"])
            if p.get("identityStatus") != "unverified":
                issues.append("[人物] 近似层 %s 缺 identityStatus=unverified 标记"
                              % p["names"]["formal"])
        # 9. 坐标状态：approximate 必须带出处；confirmed 必须带证据
        #    ⚠️ 这是防止「临时近似值被悄悄升级为已确认」的守门规则。
        for pl in self.places:
            st = pl.get("coordinateStatus")
            pid = pl.get("id")
            if st is None:
                issues.append("[坐标] %s 缺 coordinateStatus（缺标记一律按未确认处理）" % pid)
            elif st == "approximate":
                if not (pl.get("coordinatePrecision") or pl.get("provenance")):
                    issues.append("[坐标] %s 标为 approximate 但缺 coordinatePrecision/provenance" % pid)
            elif st == "confirmed":
                if not pl.get("coordinateEvidence"):
                    issues.append("[坐标] %s 标为 confirmed 但缺 coordinateEvidence —— "
                                  "无证据不得升级为已确认" % pid)
            elif st != "unregistered":
                issues.append("[坐标] %s 的 coordinateStatus 取值非法：%s" % (pid, st))

        return issues


def main():
    md = MainData()
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]

    if cmd == "check":
        if len(sys.argv) > 2:
            r = md.check_episode(DYNASTY / sys.argv[2])
            print("形态: %s" % r["shape"])
            for i in r["issues"]:
                print(" -", i)
            return
        rep = md.check_all()
        total = 0
        skipped = []
        for ep, r in rep.items():
            issues = r["issues"]
            if not issues and "json" not in r["shape"]:
                skipped.append(ep)
                continue
            print("\n【%s】%s" % (ep, "无问题" if not issues else "%d 项" % len(issues)))
            for i in issues:
                print("  -", i)
            total += len(issues)
        if skipped:
            print("\n跳过（无 cities 数据）：%s" % "、".join(skipped))
        print("\n=== 资产自校验 ===")
        assets = md.check_assets()
        if not assets:
            print("  ✓ 模板 / 节奏 / 运镜 / 纪年 / 引文 / 政权 / 地名 tiers 全部通过")
        for i in assets:
            print("  -", i)
        print("\n合计 %d 项待处理（集数据 %d + 资产 %d）" % (total + len(assets), total, len(assets)))

    elif cmd == "assets":
        iss = md.check_assets()
        print("=== 资产自校验 ===")
        if not iss:
            print("  ✓ 模板 / 节奏 / 运镜 / 纪年 / 引文 / 政权 / 地名 tiers 全部通过")
        for i in iss:
            print("  -", i)
        print("\n合计 %d 项" % len(iss))

    elif cmd == "place":
        yr = int(sys.argv[3]) if len(sys.argv) > 3 else None
        print(json.dumps(md.place(sys.argv[2], yr), ensure_ascii=False, indent=2))
    elif cmd == "person":
        print(json.dumps(md.person(sys.argv[2]), ensure_ascii=False, indent=2))
    elif cmd == "power":
        yr = int(sys.argv[3]) if len(sys.argv) > 3 else None
        print(json.dumps(md.power(sys.argv[2], yr), ensure_ascii=False, indent=2))
    elif cmd == "ganzhi":
        print("%s 年 = %s" % (sys.argv[2], md.year_to_ganzhi(int(sys.argv[2]))))
    elif cmd == "era":
        m = re.match(r"(.+?)([元一二三四五六七八九十]+)年?$", sys.argv[2])
        name = m.group(1) if m else sys.argv[2]
        cn = {"元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        ordinal = cn.get(m.group(2), 1) if m else 1
        print(json.dumps(md.era_to_year(name, ordinal), ensure_ascii=False, indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
