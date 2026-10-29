"""Map consistency check across a series: does every banner stand in its own territory, and does each episode
start where the previous one ended?

usage: python history-studio/consistency.py projects/s01e03-taodong/episode.yaml [more …]
       python history-studio/consistency.py --series s01e      (all projects whose id starts with s01e, in order)

For every beat it carries the `owners` state forward (commandery level, han-140 cells) and checks:
  · flag / enter(settle) of faction F at place P → the commandery containing P should be owned by F
    (skipped when F is not a declared polity, e.g. 宦官; mark a deliberate guest with `guest: true` on the item)
  · takeover / defect `to: F` at P → after the beat, P's commandery should be F's (else the map contradicts the words)
  · polity label_at must lie inside the polity whenever it is shown
  · consecutive episodes: the last owners of episode N must equal the first owners of episode N+1
  · (--series) 飞地: at every date of the series timeline, a patch of 1–2 commanderies wholly surrounded by one
    other polity is reported — usually a commandery the timeline forgot to hand over (河南尹 stuck on 汉室)
Prints one line per problem; exit code 1 if any.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studio  # noqa: E402

CELLS_DIR = HERE / 'data' / 'cells'
SERIES_CELLS = 'han-219'          # the 疆域 timeline is checked for 飞地 on the 建安 commanderies
_LOADED = {}


def load_cells(cells: str = 'han-140'):
    if cells in _LOADED:
        return _LOADED[cells]
    g = json.loads((CELLS_DIR / f'{cells}.geojson').read_text(encoding='utf-8'))
    jun, zhou = {}, {}
    for f in g['features']:
        p = f['properties']
        if p.get('kind') != 'jun':
            continue
        polys = f['geometry']['coordinates'] if f['geometry']['type'] == 'MultiPolygon' else [f['geometry']['coordinates']]
        jun[p['id']] = polys
        zhou.setdefault(p['zhou'], []).append(p['id'])
    _LOADED[cells] = (jun, zhou)
    return jun, zhou


def inside(lon, lat, ring):
    c = False
    for k in range(len(ring)):
        x1, y1 = ring[k - 1][:2]
        x2, y2 = ring[k][:2]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1:
            c = not c
    return c


def jun_at(lon, lat, jun):
    for jid, polys in jun.items():
        for poly in polys:
            if inside(lon, lat, poly[0]) and not any(inside(lon, lat, h) for h in poly[1:]):
                return jid
    return None


def expand(names, jun, zhou):
    out = set()
    for n in names or []:
        if n in zhou:
            out |= set(zhou[n])
        elif n in jun:
            out.add(n)
        elif n + '郡' in jun:
            out.add(n + '郡')
        elif n + '国' in jun:
            out.add(n + '国')
    return out


def state_of(owners, jun, zhou):
    st = {}
    for pol, names in (owners or {}).items():
        for j in expand(names, jun, zhou):
            st[j] = pol
    return st


def adjacency(cells: str = SERIES_CELLS):
    """Commanderies that share a border, read off the cell set's label raster (>=3 touching pixels)."""
    import collections
    import numpy as np
    from territory import norm
    lab = np.load(CELLS_DIR / f'{cells}.npz')['label']
    meta = json.loads((CELLS_DIR / f'{cells}.geojson').read_text(encoding='utf-8'))['meta']
    ids = meta.get('units') or [norm(j['jun']) for j in json.loads((HERE / 'data' / 'han-commanderies.json').read_text(encoding='utf-8'))['commanderies']]
    cnt = collections.Counter()
    for x, y in ((lab[:, :-1], lab[:, 1:]), (lab[:-1, :], lab[1:, :])):
        m = (x >= 0) & (y >= 0) & (x != y)
        for p, q in zip(x[m].tolist(), y[m].tolist()):
            cnt[(p, q) if p < q else (q, p)] += 1
    adj = collections.defaultdict(set)
    for (p, q), n in cnt.items():
        if n >= 3:
            adj[ids[p]].add(ids[q])
            adj[ids[q]].add(ids[p])
    return adj


def enclaves(tl: dict, jun, zhou, adj) -> list[str]:
    """飞地 at each timeline date: a 1–2 commandery patch of polity P that is either wholly surrounded by one other
    polity, or cut off from the rest of P with one other polity on most of its border (河南尹 left on 汉室 inside 曹操)."""
    import collections
    allow = {(a.get('jun'), a.get('polity')) for a in tl.get('allow_enclaves') or []}
    probs, seen = [], set()
    for ev in tl.get('events') or []:
        d = str(ev['date'])
        st = state_of(studio.map_owners(tl, d, SERIES_CELLS), jun, zhou)
        comps = collections.defaultdict(list)
        done = set()
        for j, pol in st.items():
            if j in done:
                continue
            comp, stack = {j}, [j]
            while stack:
                for n in adj.get(stack.pop(), ()):
                    if n not in comp and st.get(n) == pol:
                        comp.add(n)
                        stack.append(n)
            done |= comp
            comps[pol].append(comp)
        for pol, cs in comps.items():
            biggest = max(len(c) for c in cs)
            for comp in cs:
                if len(comp) > 2 or any((c, pol) in allow for c in comp):
                    continue
                border = [st.get(n) for c in comp for n in adj.get(c, ()) if n not in comp]
                if not border:
                    continue
                top, n_top = collections.Counter(border).most_common(1)[0]
                if top is None or top == pol:
                    continue
                whole = n_top == len(border)
                fragment = len(comp) < biggest and n_top / len(border) >= 0.5
                if whole or fragment:
                    key = (tuple(sorted(comp)), pol, top)
                    if key not in seen:
                        seen.add(key)
                        how = '四周全是' if whole else '和本家不相连，周边多是'
                        probs.append(f'{d} 起 {"、".join(sorted(comp))} 归 {pol}，{how} {top}（飞地？时间线漏了交接，或在 allow_enclaves 里注明）')
    return probs


def check(path: Path, reg, prev_final: dict | None):
    y = studio.load_script(path)          # resolves `map:` from the series timeline
    eid = y['id']
    cells = (y.get('territory') or {}).get('cells') or 'han-140'
    jun, zhou = load_cells(cells)
    probs = []
    polities = set((y.get('territory') or {}).get('polities') or {})
    people = y.get('people') or {}
    places = y.get('places') or {}

    def where(name):
        spec = places.get(name)
        if isinstance(spec, dict) and spec.get('lon') is not None:
            return spec['lon'], spec['lat']
        pid = spec.get('id') if isinstance(spec, dict) else None
        p = reg.places.get(pid) if pid else None
        if not p:
            for q in reg.places.values():
                labels = [*q.get('aliases', []), *(n.get('text', '') for n in q.get('names', []))]
                if name in labels:
                    p = q
                    break
        return (p['coordinates'][0], p['coordinates'][1]) if p else None

    jun_of = {}
    for name in places:
        ll = where(name)
        jun_of[name] = jun_at(*ll, jun) if ll else None

    start = (y.get('territory') or {}).get('start_owners')
    state = state_of(start, jun, zhou) if start else None
    first = dict(state) if state else None
    # 地图滞后: the story has moved on a year or more but the map still shows an older date while the series
    # timeline has hand-overs in between (2026-10-13: 第7集 sat on the 196-06 map through 197–198, so 梁国/陈国/鲁国
    # stayed 汉室 though 曹操 held them)
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    tl = yaml.safe_load((HERE.parent / 'series' / '三国到隋' / '疆域.yaml').read_text(encoding='utf-8'))
    ev_dates = sorted(str(e['date']) for e in tl.get('events') or [])
    map_d, year, warned = None, None, set()
    ys = [(i, b['year']) for i, b in enumerate(raw.get('beats') or []) if isinstance(b.get('year'), int)]
    # a cold open jumps ahead and then flashes back: its beats are exempt
    flash = next((i for (i, y1), (_, y0) in zip(ys[1:], ys) if y1 < y0), None)
    for i, b in enumerate(raw.get('beats') or []):
        if flash is not None and i < flash:
            if b.get('map'):
                map_d = str(b['map'])
            continue
        if b.get('map'):
            map_d = str(b['map'])
        if isinstance(b.get('year'), int):
            year = b['year']
        if map_d and year:
            missed = [d for d in ev_dates if map_d < d < f'{year}-01']
            if missed and (map_d, year) not in warned and i < len(raw.get('beats') or []) - 1:
                warned.add((map_d, year))
                probs.append(f'{eid} 第{i + 1}拍「{b["say"][:14]}…」: 旁白已到 {year} 年，地图还停在 {map_d}，中间有 {len(missed)} 次易手没画（{"、".join(missed)}）；在这里写 map')
    for i, b in enumerate(y.get('beats') or []):
        ctx = f'{eid} 第{i + 1}拍「{b["say"][:14]}…」'
        before = dict(state or {})
        if b.get('owners'):
            state = state_of(b['owners'], jun, zhou)
            if first is None:
                first = dict(state)
        after = dict(state or {})
        for item in b.get('show') or []:
            if not isinstance(item, dict) or len(item) != 1:
                continue
            kind, spec = next(iter(item.items()))
            if not isinstance(spec, dict) or spec.get('guest'):
                continue
            at = spec.get('at')
            if kind in ('flag', 'enter') and at:
                if kind == 'enter' and not spec.get('settle'):
                    continue
                fac = spec.get('faction') or (people.get(spec.get('who')) or {}).get('faction')
                if fac in polities and jun_of.get(at):
                    j = jun_of[at]
                    if before.get(j) != fac and after.get(j) != fac:
                        who = spec.get('name') or spec.get('who')
                        probs.append(f'{ctx}: {kind}「{who}」({fac}) 立在 {at}（{j}），可这时 {j} 归 {after.get(j) or before.get(j) or "无主"}')
            if kind == 'takeover' and at and spec.get('to') in polities and jun_of.get(at):
                j = jun_of[at]
                if after.get(j) != spec['to']:
                    probs.append(f'{ctx}: {kind} 到 {spec["to"]}，可 {at}（{j}）这拍之后仍归 {after.get(j) or "无主"}（owners 没跟上）')
    # duplicates of the same label message are noise: keep the first per polity
    seen, uniq = set(), []
    for p in probs:
        key = re.sub(r'第\d+拍「[^」]*」', '', p) if 'label_at' in p else p
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    probs = uniq
    if prev_final is not None and first is not None and prev_final[0] == cells:
        prev_final = prev_final[1]
        diff = sorted(j for j in set(prev_final) | set(first) if prev_final.get(j) != first.get(j))
        if diff:
            show = '、'.join(f'{j}({prev_final.get(j) or "无"}→{first.get(j) or "无"})' for j in diff[:12])
            probs.insert(0, f'{eid} 开场地图和上一集结尾不一致 {len(diff)} 处：{show}{" …" if len(diff) > 12 else ""}')
    return probs, (cells, state)


def main(argv):
    reg = studio.Registry()
    if argv and argv[0] == '--series':
        paths = sorted((HERE.parent / 'projects').glob(f'{argv[1]}*/episode.yaml'))
    else:
        paths = [Path(a) for a in argv]
    prev, total = None, 0
    for p in paths:
        probs, prev = check(p, reg, prev)
        total += len(probs)
        print(f'## {p.parent.name}：{len(probs)} 处')
        for x in probs:
            print('  -', x)
    if argv and argv[0] == '--series':
        tl = yaml.safe_load((HERE.parent / 'series' / '三国到隋' / '疆域.yaml').read_text(encoding='utf-8'))
        jun, zhou = load_cells(SERIES_CELLS)
        en = enclaves(tl, jun, zhou, adjacency(SERIES_CELLS))
        total += len(en)
        print(f'## 疆域时间线飞地：{len(en)} 处')
        for x in en:
            print('  -', x)
    print(f'\n合计 {total} 处')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
