"""画面审查：旁白说了什么，画面有没有跟上（2026-10-27，第19集水淹七军用户发现的四处毛病）。

    python history-studio/audit.py projects/<id>/episode.yaml [--build B2026…]
    python history-studio/audit.py --all s01e18 s01e43      # 一段集数，汇总成报告

`studio.py build` 每次构建后自动跑，结果写进 <build>/画面审查.md。只读已构建的 episode.json，不改任何东西。

规则（一拍 = 一句旁白）：
  死亡   旁白说某人死了/被杀，这一拍没有 exit（人物退场）
  投降   旁白说投降/开城，这一拍没有 defect / turn / exit(降) / capture / 疆域变化
  易手   旁白说攻下/占领/进了某城，这一拍疆域没变，也没有 capture / takeover / defect
  立绘   主要人物死了，只在地图上盖了戳，没有立绘退场；或立绘退场不到 2.5 秒、被片尾截断
  音效   立绘退场没有退场钟，或钟声和退场差了 1.5 秒以上
  残留   旁白已说某部队的主将死了/降了，他的营地或来路还留在地图上
  遗忘   某部队最后被提到之后，营地或来路又在地图上留了 6 拍以上（观众会问：这是谁？）
  战后   战事账（战事.yaml）写了某郡战后归谁，讲到这件事的那一拍（含下一拍）地图没变过去；或还没讲到就先变了
  无声   疆域变色、交战、围城、火攻时没有任何音效（引擎会自动补默认音效，这条报的是补了还被冷却规则吞掉的）
  来路   部队来路虚线在到达后留了两拍以上
  静止   一拍里超过 9 秒画面没有任何新动作（镜头不动、没有新元素）
旁白里确实不该有画面的（诈降、劝降、假设），在那一拍写 `audit_ok: [投降]` 跳过该条。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / '01_工作流'
STUDIO = ROOT / '05_项目' / 'Remotion' / 'studio'

DEATH = re.compile(r'病逝|病死|去世|逝世|驾崩|身亡|被杀|被斩|斩了|杀了|处死|自杀|自尽|战死|阵亡|遇害|死了|死在|被害|被毒死|毒死')
SURRENDER = re.compile(r'(?<!假装)(?<!诈)(?<!劝)(?<!不肯)(?<!不愿)(?<!什么叫)(?<!逼他)(?<!打)(投降|归降|降了|请降|开城)')
TAKE = re.compile(r'攻下|攻占|攻破|攻陷|拿下|占领|占了|夺取|夺下|失守|陷落|收复|攻进|打进|杀进|攻入|入主|进占')
INTENT = re.compile(r'[叫让要想逼劝准备打算]')   # 叫太子投降、准备收复：said, not done
FALL_VERBS = {'卒', '诛', '亡', '降', '囚'}
LOOK = 1.5     # 退场钟和退场相差多少秒算对不上
FORGET = 6     # 部队最后被提到之后再留多少拍算被遗忘


def latest_build(pid: str) -> Path:
    builds = sorted((p for p in (STUDIO / pid).iterdir() if (p / 'public' / 'episode.json').exists()), key=lambda p: p.stat().st_mtime)
    return builds[-1]


def mmss(t: float) -> str:
    return f'{int(t // 60)}:{int(t % 60):02d}'


def audit(script: dict, ep: dict, ledger: dict | None = None) -> list[dict]:
    if ledger is None:
        lf = WF / 'projects' / script['id'] / '战事.yaml'
        ledger = yaml.safe_load(lf.read_text(encoding='utf-8')) if lf.exists() else {}
    beats, segs, els = script['beats'], ep['segments'], ep['elements']
    n = min(len(beats), len(segs))
    people = script.get('people') or {}
    units = {e['unit'] for e in els if e['type'] in ('camp',) and e.get('unit')}
    names = sorted(set(people) | units, key=len, reverse=True)
    states = [s['t'] for s in ((ep.get('territory') or {}).get('states') or [])]
    sfx = ep.get('sfx') or []
    out = []

    def beat_at(t: float) -> int:
        for i in range(n):
            if t < segs[i]['end']:
                return i
        return n - 1

    def flag(i: int, rule: str, msg: str, t: float | None = None):
        if rule in (beats[i].get('audit_ok') or []):
            return
        out.append({'beat': i + 1, 't': round(segs[i]['start'] if t is None else t, 2), 'rule': rule, 'msg': msg})

    def in_beat(i: int, *types) -> list[dict]:
        a, b = segs[i]['start'] - 0.2, segs[i]['end'] + 0.2
        return [e for e in els if e['type'] in types and a <= e.get('start', -1) <= b]

    def who_in(text: str) -> list[str]:
        found, rest = [], text
        for nm in names:
            if nm in rest:
                found.append(nm)
                rest = rest.replace(nm, '')
        return found

    def subject(text: str, m: re.Match) -> str | None:
        """Who the verb happens to: the object after 杀了/斩了/毒死…, else the nearest name before it in the clause."""
        a = max([text.rfind(c, 0, m.start()) for c in '。！？；'] + [-1]) + 1
        z = min([k for k in (text.find(c, m.end()) for c in '。！？；，') if k >= 0] + [len(text)])
        hits = []
        for nm in names:
            for k in [x.start() for x in re.finditer(re.escape(nm), text[a:z])]:
                if text[k + a - 1:k + a] in ('被', '向', '奔', '给'):   # 被孙权的部将抓住、向钟会投降、投奔刘曜：not the one it happens to
                    continue
                if text[k + a + len(nm):k + a + len(nm) + 1] == '的':     # 杀了石勒的使者：the 使者 died, not 石勒
                    continue
                if not any(h[0] <= k + a < h[0] + len(h[1]) for h in hits):
                    hits.append((k + a, nm))
        if m.group() in ('杀了', '斩了', '处死', '毒死'):
            after = sorted(h for h in hits if h[0] >= m.end())
            return after[0][1] if after else None
        before = sorted(h for h in hits if h[0] < m.start())
        return before[-1][1] if before else None

    def turned(i: int) -> list[dict]:   # defect / turn end up as a flag that flips colour at turn_at
        a, b = segs[i]['start'] - 0.2, segs[i]['end'] + 0.2
        return [e for e in els if e['type'] == 'flag' and e.get('turn_at') is not None and a <= e['turn_at'] <= b]

    def stage_dies(i: int) -> set:
        return {a['who'] for st in in_beat(i, 'stage') for a in st.get('actors', []) if a.get('die_at') is not None}

    told_fall = {}   # unit -> time the narration says he died / surrendered
    mention = {}     # unit -> last beat index he is named
    for i in range(n):
        text = str(beats[i].get('say') or '')
        who = who_in(text)
        for u in who:
            mention[u] = i
        exits = in_beat(i, 'exit')
        exit_who = {e.get('who') for e in exits} | {e.get('name') for e in exits} | stage_dies(i)
        for m in DEATH.finditer(text):
            if re.search(r'[要想]|打算|准备', text[max(0, m.start() - 6):m.start()]):   # 我要去冀州杀了石宣：a threat
                continue
            if re.match(r'[了得]?[一二三四五六七八九十百千万几上数好多]', text[m.end():m.end() + 2]):   # 死了上万人、杀了几万人：a toll, not a person
                continue
            u = subject(text, m)
            if not u:
                continue
            if u not in exit_who:
                flag(i, '死亡', f'旁白说 {u}「{m.group()}」，这一拍没有他的退场（exit）')
            told_fall.setdefault(u, segs[i]['end'])
        m = SURRENDER.search(text)
        if m and INTENT.search(text[max(0, m.start() - 5):m.start()]):
            m = None
        if m:
            moved = turned(i) or in_beat(i, 'capture', 'takeover') or [e for e in exits if e.get('verb') == '降'] \
                or [e for e in in_beat(i, 'stamp') if e.get('text') == '降'] \
                or any(segs[i]['start'] - 0.2 <= t <= segs[i]['end'] + 0.2 for t in states[1:])
            if not moved:
                flag(i, '投降', f'旁白说「{m.group()}」，画面上没有倒戈（defect）、易手或「降」的退场')
            u = subject(text, m)
            if u in units:
                told_fall.setdefault(u, segs[i]['end'])
        m = TAKE.search(text)
        if m and (INTENT.search(text[max(0, m.start() - 6):m.start()]) or text[m.end():m.end() + 1] == '不'
                  or any(text.startswith(nm, m.end()) for nm in people)):   # 收复不了；拿下张华 is an arrest
            m = None
        if m:
            moved = turned(i) or in_beat(i, 'capture', 'takeover') or any(segs[i]['start'] - 0.2 <= t <= segs[i]['end'] + 0.2 for t in states[1:])
            if not moved:
                flag(i, '易手', f'旁白说「{m.group()}」，这一拍疆域没变色，也没有 capture / takeover')

    dur = ep['duration']
    for e in els:
        if e['type'] != 'exit':
            continue
        i = beat_at(e['start'])
        nm = e.get('who') or e.get('name')
        on_stage = nm in stage_dies(i)
        if e.get('verb') in ('卒', '诛') and not e.get('show_portrait') and not on_stage and (people.get(nm) or {}).get('image'):
            flag(i, '立绘', f'{nm} 退场只在地图上盖戳，没有立绘退场（主要人物写 portrait: true）', e['start'])
        if e.get('show_portrait'):
            if e['end'] - e['start'] < 2.5:
                flag(i, '立绘', f'{nm} 的立绘退场只有 {e["end"] - e["start"]:.1f} 秒（写 for: 4）', e['start'])
            if e['start'] > dur - 2.5:
                flag(i, '立绘', f'{nm} 的立绘退场离片尾不到 2.5 秒，会被截掉', e['start'])
            # the bell rings on the exit; one that rang up to 6.5 s before also counts (the sfx cooldown keeps two
            # deaths a few seconds apart from ringing twice)
            bells = [s['start'] for s in sfx if s.get('name') == '退场钟' and -6.5 <= s['start'] - e['start'] <= 6]
            if not bells:
                flag(i, '音效', f'{nm} 立绘退场没有退场钟', e['start'])
            elif not any(-6.5 <= b - e['start'] <= LOOK for b in bells):
                b = min(bells, key=lambda b: abs(b - e['start']))
                flag(i, '音效', f'{nm} 的退场钟在 {mmss(b)}，退场在 {mmss(e["start"])}，晚了 {b - e["start"]:.1f} 秒（sfx 写同一个 cue）', e['start'])

    for e in els:
        if e['type'] not in ('camp', 'trail'):
            continue
        u = e.get('unit') or (e.get('label') or '').split('自')[0].split('败走')[0]
        if not u or e['end'] <= e['start']:
            continue
        what = '营地' if e['type'] == 'camp' else '来路'
        if u in told_fall and e['start'] < told_fall[u] and e['end'] > told_fall[u] + 3:
            i = beat_at(told_fall[u] - 0.01)
            flag(i, '残留', f'旁白在第 {i + 1} 拍已说 {u} 死了或降了，他的{what}还留到 {mmss(e["end"])}', told_fall[u])
            continue
        last = mention.get(u)
        if last is None:
            continue
        end_beat = beat_at(min(e['end'], dur) - 0.01)
        if end_beat - last > FORGET and e['start'] < segs[last]['end'] + 1:
            flag(last, '遗忘', f'{u} 最后一次出现在第 {last + 1} 拍，他的{what}一直留到第 {end_beat + 1} 拍（{mmss(e["end"])}）', segs[last]['end'])
    # ---- 战后疆域 / 无声 / 来路 / 静止 (2026-10-28) ----
    st = (ep.get('territory') or {}).get('states') or []
    snd = [x['start'] for x in sfx]

    def owner(jun: str, t: float):
        o = (None, False)
        for k, x in enumerate(st):
            if x['t'] <= t + 1e-6 or k == 0:
                o = (x['owners'].get(jun), jun in x.get('uncertain', []))
        return o

    tell = {}
    for i in range(n):
        for eid in beats[i].get('tells') or []:
            tell.setdefault(eid, i)
    for ev in (ledger or {}).get('events') or []:
        ter = ev.get('territory')
        if not ter or ev.get('skip') or ev['id'] not in tell or not st:
            continue
        i = tell[ev['id']]
        want = ter['to']
        hit = (lambda o: o[1]) if want == '争夺' else (lambda o: o[0] == want)
        after = owner(ter['jun'], segs[min(i + 1, n - 1)]['end'] - 0.05)
        if after[0] is None and not after[1]:
            continue
        if not hit(after):
            flag(i, '战后', f"战事账 {ev['id']}：{ter['jun']} 战后应归{want}，讲到第 {i + 1} 拍之后地图仍是{after[0]}{'（斜纹）' if after[1] else ''}")
        elif i > 0 and hit(owner(ter['jun'], segs[i]['start'] - 0.05)) and not hit(owner(ter['jun'], 0)):
            flag(i, '战后', f"战事账 {ev['id']}：{ter['jun']} 还没讲到（第 {i + 1} 拍）就已经变成{want}")
    for a, b in zip(st, st[1:]):
        if a['owners'] != b['owners'] and not any(abs(x - b['t']) <= 1.5 for x in snd):
            flag(beat_at(b['t']), '无声', f"疆域变色（{mmss(b['t'])}）没有音效", b['t'])
    for e in els:
        if e['type'] in ('battle', 'clash', 'siege', 'fire') and not any(-1.0 <= x - e['start'] <= 2.0 for x in snd):
            flag(beat_at(e['start']), '无声', f"{ {'battle': '交战', 'clash': '交锋', 'siege': '围城', 'fire': '火攻'}[e['type']]}（{e.get('place')}）没有音效", e['start'])
    for e in els:
        if e['type'] == 'trail' and beat_at(e['end'] - 0.01) - beat_at(e['start']) > 4:
            flag(beat_at(e['start']), '来路', f"{e.get('label')} 的虚线留到第 {beat_at(e['end'] - 0.01) + 1} 拍", e['start'])
    acts = sorted([e['start'] for e in els if e['type'] not in ('city', 'trail', 'camp')] + [k['t'] for k in ep.get('camera') or []])
    for i in range(n):
        pts = [segs[i]['start']] + [a for a in acts if segs[i]['start'] < a < segs[i]['end']] + [segs[i]['end']]
        gap = max(b - a for a, b in zip(pts, pts[1:]))
        if gap > 9:
            flag(i, '静止', f'画面 {gap:.1f} 秒没有新动作（加镜头推移、插画或示意）')
    out.sort(key=lambda x: (x['beat'], x['t']))
    return out


def report(script: dict, items: list[dict]) -> str:
    if not items:
        return f'# 画面审查：{script.get("title", script["id"])}\n\n没有发现问题。\n'
    lines = [f'# 画面审查：{script.get("title", script["id"])}', '', f'{len(items)} 处。逐条看画面，确实没问题的在那一拍写 `audit_ok: [规则名]`。', '',
             '| 拍 | 时间 | 规则 | 问题 |', '|---|---|---|---|']
    lines += [f'| {x["beat"]} | {mmss(x["t"])} | {x["rule"]} | {x["msg"]} |' for x in items]
    return '\n'.join(lines) + '\n'


def run(script_path: Path, build: str | None = None, write: bool = True) -> list[dict]:
    script = yaml.safe_load(script_path.read_text(encoding='utf-8'))
    b = STUDIO / script['id'] / build if build else latest_build(script['id'])
    ep = json.loads((b / 'public' / 'episode.json').read_text(encoding='utf-8'))
    items = audit(script, ep)
    if write:
        (b / '画面审查.md').write_text(report(script, items), encoding='utf-8')
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script', nargs='?', type=Path)
    ap.add_argument('--build')
    ap.add_argument('--all', nargs=2, metavar=('FROM', 'TO'), help='集号区间，如 s01e18 s01e43')
    ap.add_argument('--out', type=Path, help='--all 的汇总报告路径')
    a = ap.parse_args()
    if a.all:
        lo, hi = a.all
        projs = sorted(p for p in (WF / 'projects').iterdir() if p.name[:6] >= lo and p.name[:6] <= hi and re.match(r's\d\de\d\d-[a-z]+$', p.name))
        parts, total = [], 0
        for p in projs:
            try:
                items = run(p / 'episode.yaml')
            except (FileNotFoundError, IndexError, StopIteration):
                continue
            script = yaml.safe_load((p / 'episode.yaml').read_text(encoding='utf-8'))
            total += len(items)
            print(f'{p.name}: {len(items)}')
            parts.append(report(script, items).replace('# 画面审查：', f'## {p.name[:6]} '))
        text = f'# 画面审查汇总 {lo}–{hi}\n\n共 {total} 处。\n\n' + '\n'.join(parts)
        if a.out:
            a.out.write_text(text, encoding='utf-8')
            print(f'-> {a.out}')
        return
    items = run(a.script.resolve(), a.build)
    for x in items:
        print(f'  第 {x["beat"]} 拍 {mmss(x["t"])} [{x["rule"]}] {x["msg"]}')
    print(f'{len(items)} 处' if items else '画面审查：没有发现问题')


if __name__ == '__main__':
    main()
