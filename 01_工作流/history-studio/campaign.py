"""Campaign ledger check (2026-10-25).

Each episode that tells a war keeps a `战事.yaml` next to its episode.yaml: every army's start, camps, passes and
mountains crossed, fights, captures and surrenders, with dates and source quotes (compiled by Codex, checked by
Claude). The user found ep27 drawing 邓艾 at 涪 while 蜀汉 was still whole, and his route as two bare arrows, and
said a rule that lives only in the storyboard notes is no rule: the studio has to catch it. So the compiled episode
is checked against the ledger here, and a miss is a build error.

What "told" means: a beat lists the ledger events it tells, `tells: [e29, e30]` (2026-10-25: matching by place
name went wrong at once — the cold open names 七百多里 before the march, 阴平/剑阁 recur, the epilogue names 成都).
Told events must be drawn. Captures and surrenders must move the map whether told or not. An event whose place the
narration names but that no beat tags is warned about, so nothing slips by unnoticed.

Rules
- 攻占 / 投降 with `territory: {jun, to}`: that commandery turns `to` (or turns hatched, for `to: 争夺`) no earlier
  than the beat that tells it, and no later than the beat after it. Untold: somewhere between the told events
  around it.
- 行军 / 撤退 / 退守 / 出发 (told): an arrow of the army's faction from `from` to `place`, passing every `via`.
- 翻越 / 途经 (told): the place is a point on an arrow of the army's faction, or something is drawn at it.
- 屯驻 (told): a camp or a flag at the place while the beat runs.
- 交战 (told): a battle, clash, tactic, fire, or a flood / arrow volley / catapult act at the place.
- A beat may waive one rule with `campaign_skip: {e07: 理由}`; the reason goes into the review sheet.
"""
from __future__ import annotations

from pathlib import Path

import yaml

MOVE = {'出发', '行军', '撤退', '退守', '会合'}
PASS = {'翻越', '途经'}
TAKE = {'攻占', '投降'}


def load(script_path: Path) -> dict | None:
    f = script_path.parent / '战事.yaml'
    return yaml.safe_load(f.read_text(encoding='utf-8')) if f.exists() else None


def check(c, ep: dict, script_path: Path) -> list[str]:
    """Adds errors / warnings to the compiler `c`; returns review-sheet lines (event → beat → what is drawn)."""
    led = load(script_path)
    beats = [b for b in c.s.get('beats') or [] if isinstance(b, dict)]
    segs = ep['segments']
    if len(segs) != len(beats):
        c.warn(f'战事账：{len(segs)} 段配音对不上 {len(beats)} 拍，跳过检查')
        return []
    verbs_said(c, ep, beats, segs)
    if not led:
        if any(e['type'] == 'arrow' and e.get('troops') for e in ep['elements']) and str(c.s.get('id', '')).startswith('s0'):
            c.warn('有行军却没有战事.yaml：屯兵、翻山、攻占没法核对（派 Codex 整理战事账，见 协作-Codex.md）')
        return []
    name_of = {p['id']: p['name'] for p in ep['places']}
    id_of = {}
    for p in ep['places']:
        id_of[p['name']] = p['id']
        id_of[p['id']] = p['id']
    armies = led.get('armies') or {}
    events = led.get('events') or []
    terr = ep.get('territory')
    cell_id = {x['name']: x['id'] for x in terr['cells']} if terr else {}

    def owner_at(jun: str, t: float):
        if not terr or jun not in cell_id:
            return None, False
        cur = None
        for st in terr['states']:
            if st['t'] <= t + 1e-6:
                cur = st
        if not cur:
            return None, False
        return cur['owners'].get(cell_id[jun]), cell_id[jun] in (cur.get('uncertain') or [])

    def change_time(jun: str, to: str, t_from: float) -> float | None:
        """First state at or after `t_from` (and the state in force at t_from) where jun is `to` / hatched."""
        if not terr or jun not in cell_id:
            return None
        cid = cell_id[jun]
        for st in terr['states']:
            if st['t'] < t_from:
                continue
            hatched = cid in (st.get('uncertain') or [])
            # a revolt put down: the owner never changed, the hatching clears (南中, 225; 2026-10-25)
            ok = hatched if to == '争夺' else st['owners'].get(cid) == to and not hatched
            if ok:
                return st['t']
        return None

    # the beat that tells each event: explicit `tells:` on the beat
    told: dict[str, int] = {}
    ids = {ev.get('id') for ev in events}
    for i, b in enumerate(beats):
        for eid in b.get('tells') or []:
            if eid not in ids:
                c.err(f'第{i + 1}拍 tells: {eid} 不在战事账里')
            elif eid in told:
                c.err(f'战事账 {eid} 被第{told[eid] + 1}拍和第{i + 1}拍重复讲')
            else:
                told[eid] = i
    said = ''.join(str(b.get('say', '')) for b in beats)
    for ev in events:
        if ev.get('id') not in told and ev.get('kind') not in TAKE and ev.get('place') and ev['place'] in said and not ev.get('skip'):
            c.warn(f"战事账 {ev['id']} {ev['kind']}·{ev['place']}：旁白提到了{ev['place']}，但没有哪一拍 tells 它（要画就标上，不画就在账里写 skip: 理由）")
    els = ep['elements']

    def live(e, i, spread=1):
        a = segs[max(0, i - spread)]['start'] if i - spread >= 0 else 0
        b = segs[min(len(segs) - 1, i + spread)]['end']
        return e.get('start', 0) < b and e.get('end', 1e9) > a

    def skip(ev, i):
        why = (beats[i].get('campaign_skip') or {}).get(ev['id']) if i is not None else None
        return why

    lines = []
    for k, ev in enumerate(events):
        eid, kind, place = ev.get('id'), ev.get('kind'), ev.get('place')
        army = armies.get(ev.get('army')) or {}
        fac = army.get('faction')
        i = told.get(eid)
        where = f"第{i + 1}拍「{str(beats[i].get('say', ''))[:14]}…」" if i is not None else '旁白未讲'
        tag = f'战事账 {eid} {kind}·{place}（{where}）'
        why = skip(ev, i) or (ev.get('skip') if i is None else None)
        if why:
            lines.append(f'- {eid} {kind} {place}：{where}，按分镜决定不画：{why}')
            continue
        drawn = []
        # territory
        tr = ev.get('territory')
        if kind in TAKE and tr and tr.get('jun') and tr.get('to'):
            jun, to = tr['jun'], tr['to']
            if jun not in cell_id:
                c.err(f'{tag}：郡名 {jun} 不在本集郡格子里')
            else:
                if i is not None:
                    lo, hi = segs[i]['start'] - 0.3, segs[min(i + 1, len(segs) - 1)]['end']
                else:   # untold: between the told events around it
                    prev_i = max((told[e['id']] for e in events[:k] if e['id'] in told), default=0)
                    nxt = [told[e['id']] for e in events[k + 1:] if e['id'] in told]
                    lo, hi = segs[prev_i]['start'] - 0.3, segs[min(nxt) if nxt else len(segs) - 1]['end']
                own, hatched = owner_at(jun, lo)
                already = hatched if to == '争夺' else own == to and not hatched
                t = change_time(jun, to, lo)
                if already and lo > 0.5:
                    c.err(f'{tag}：{jun} 在 {lo:.1f}s 之前就已是「{to}」，疆域变得太早')
                elif t is None:
                    c.err(f'{tag}：{jun} 始终没有变成「{to}」——疆域漏变（在疆域.yaml 加事件，并在这一拍写 map: 与 owners_cue:）')
                elif t > hi + 0.05:
                    c.err(f'{tag}：{jun} 到 {t:.1f}s 才变「{to}」，晚于 {hi:.1f}s')
                else:
                    drawn.append(f'疆域 {jun}→{to} @{t:.1f}s')
        if i is not None:
            pts_of = lambda e: [id_of.get(p, p) for p in e.get('points') or [] if isinstance(p, str)]
            arrows = [e for e in els if e['type'] == 'arrow' and live(e, i) and (not fac or e.get('faction') in (fac, None))]
            at_place = id_of.get(place)
            if place and not at_place and kind not in TAKE:
                c.err(f'{tag}：地名「{place}」没在 episode.yaml 的 places 里声明，画不出来')
            elif kind == '出发':
                gone = [a for a in arrows if pts_of(a) and pts_of(a)[0] == at_place]
                if not gone:
                    c.err(f'{tag}：没有从 {place} 出发的{fac or ""}箭头')
                else:
                    drawn.append('出发箭头')
            elif kind in MOVE:
                src = id_of.get(ev.get('from')) if ev.get('from') and ev.get('from') != '未核' else None
                vias = [id_of.get(v) for v in ev.get('via') or []]
                miss_v = [v for v, vid in zip(ev.get('via') or [], vias) if not vid]
                if miss_v:
                    c.err(f'{tag}：途经点 {"、".join(miss_v)} 没在 places 里声明')
                hit = [a for a in arrows if at_place in pts_of(a) and (not src or (src in pts_of(a) and pts_of(a).index(src) < pts_of(a).index(at_place)))]
                if not hit:
                    c.err(f'{tag}：找不到{fac or ""}从 {ev.get("from") or "？"} 到 {place} 的行军箭头')
                else:
                    lack = [v for v, vid in zip(ev.get('via') or [], vias) if vid and not any(vid in pts_of(a) for a in hit)]
                    if lack:
                        c.err(f'{tag}：行军箭头没经过 {"、".join(lack)}（写进 via:）')
                    elif miss_v:
                        drawn.append('行军箭头（途经点未声明）')
                    else:
                        drawn.append('行军箭头' + (f'（经 {"、".join(ev.get("via"))}）' if ev.get('via') else ''))
            elif kind in PASS:
                on_arrow = any(at_place in pts_of(a) for a in arrows)
                marked = any(e.get('place') == at_place and live(e, i, 0) for e in els if e['type'] in ('act', 'card', 'stamp', 'flag', 'spot', 'city'))
                if not (on_arrow or marked):
                    c.err(f'{tag}：{place} 既不在行军箭头上，也没有标记')
                else:
                    drawn.append('箭头途经' if on_arrow else '地点标记')
            elif kind == '屯驻':
                camp = [e for e in els if e['type'] in ('camp', 'garrison', 'flag') and e.get('place') == at_place and live(e, i)]
                if not camp:
                    c.err(f'{tag}：{place} 没有营帐或旗（屯驻要看得见）')
                else:
                    drawn.append(camp[0]['type'])
            elif kind == '交战':
                # a fight drawn as what decided it counts too: 水淹七军 is a flood at 樊城, 火烧连营 a fire (2026-10-25)
                fight = [e for e in els if (e['type'] in ('battle', 'clash', 'tactic', 'campaign', 'fire')
                                            or (e['type'] == 'act' and e.get('act') in ('flood', 'arrows', 'catapult')))
                         and (e.get('place') == at_place or e.get('at') == at_place) and live(e, i)]
                if not fight:
                    c.err(f'{tag}：{place} 没有交战标记')
                else:
                    drawn.append(fight[0]['type'])
        lines.append(f"- {eid} {ev.get('date', '')} {kind} {place}：{where}；{'、'.join(drawn) or '—'}")
    return lines


TAKE_WORDS = ('投降', '出降', '归降', '攻下', '攻占', '拿下', '打下', '占领', '夺取', '夺了', '陷落', '失守', '开城')


def verbs_said(c, ep: dict, beats: list, segs: list) -> None:
    """Without a ledger too: a line that says a named place was taken or surrendered, with no territory change in
    that beat or the next, is flagged (the map must move when the narration says so). `territory_hold: 理由` on the
    beat waives it (a city taken while its commandery stays, a surrender told in advance in a cold open).
    A warning only: words alone cannot tell 于禁投降 (a man) or 能打下长安吗 (a question) from a city changing hands;
    the ledger rules above are the hard ones."""
    terr = ep.get('territory')
    if not terr:
        return
    names = sorted({p['name'] for p in ep['places']}, key=len, reverse=True)
    times = [st['t'] for st in terr['states']]
    for i, b in enumerate(beats):
        say = str(b.get('say', ''))
        if b.get('territory_hold') or not any(w in say for w in TAKE_WORDS):
            continue
        place = next((n for n in names if n in say), None)
        if not place:
            continue
        lo, hi = segs[i]['start'] - 0.3, segs[min(i + 1, len(segs) - 1)]['end']
        if not any(lo <= t <= hi for t in times):
            c.warn(f'第{i + 1}拍「{say[:16]}…」可能说到{place}易手，这一拍和下一拍疆域都没变（加 map:/owners_cue:，确实不该变就写 territory_hold: 理由）')
