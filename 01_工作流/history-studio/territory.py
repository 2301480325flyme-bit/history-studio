"""Territory timeline: who holds which commandery, beat by beat.

Script form (episode.yaml):

    territory:
      cells: han-140                 # cell set from cells.py
      polities:
        曹操: {slot: salmon, main: true}
        袁绍: {slot: sky}
      zhou_labels: true              # large province names (atlas style)
      jun_labels: true               # small commandery names when zoomed in
      cities: true                   # always-on city layer: 郡治 dots + names, 县治 dots (default on when the set has cities)

    beats:
      - say: …
        owners:                      # full state from this beat on
          曹操: [兖州, 豫州, 河南尹]   # 州 expands to its 郡; 郡 by name
          袁绍: [冀州, 青州]
        uncertain: [泰山郡]          # drawn hatched: control not clearly recorded
        sources: [...]

Every state must be backed by the beat's sources; unknown names are errors.
Outlines and labels are computed per state by dissolving the cell raster.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import contourpy
import numpy as np
from scipy import ndimage

from palette import build as palette_slots
from regions import label_anchor, norm

HERE = Path(__file__).resolve().parent
CELLS = HERE / 'data' / 'cells'


def simplify_ring(ring: list, tol: float) -> list:
    """Douglas-Peucker on one closed ring (degrees). Keeps the map shape, drops redundant points:
    territory paths are re-rasterized every frame while the camera moves, so point count = render time."""
    pts = np.asarray(ring, dtype=float)
    if len(pts) < 8 or tol <= 0:
        return ring
    keep = np.zeros(len(pts), bool)
    keep[0] = keep[-1] = True
    far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))   # closed ring: start == end, so split at the farthest point
    keep[far] = True
    stack = [(0, far), (far, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        seg = pts[b] - pts[a]
        n = np.hypot(*seg) or 1e-12
        d = np.abs(seg[0] * (pts[a + 1:b, 1] - pts[a, 1]) - seg[1] * (pts[a + 1:b, 0] - pts[a, 0])) / n
        k = int(np.argmax(d))
        if d[k] > tol:
            m = a + 1 + k
            keep[m] = True
            stack += [(a, m), (m, b)]
    out = pts[keep].tolist()
    return out if len(out) >= 4 else ring


def inside(x: float, y: float, ring) -> bool:
    """Point in polygon (ray casting) for one ring of (lon, lat) points."""
    hit = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            hit = not hit
    return hit


def trace(mask: np.ndarray, bbox, res, sigma=0.9, tol: float = 0.015) -> list:
    lon0, lat0, lon1, lat1 = bbox
    f = ndimage.gaussian_filter(mask.astype(np.float32), sigma)
    filled, offsets = contourpy.contour_generator(z=f, fill_type=contourpy.FillType.OuterOffset).filled(0.5, 2.0)
    polys = []
    for pts, offs in zip(filled, offsets):
        rings = []
        for a, b in zip(offs[:-1], offs[1:]):
            ring = pts[a:b]
            if len(ring) >= 4:
                rings.append(simplify_ring(np.column_stack([lon0 + (ring[:, 0] + 0.5) * res, lat1 - (ring[:, 1] + 0.5) * res])[::2].tolist(), tol))
        if rings and len(rings[0]) >= 4:
            polys.append(rings)
    return polys


def atlas_colour(fill: str, edge: str, warm: bool = False) -> str:
    """atlas look (after 史图记忆簿): a deeper, slightly greyed polity colour — fill and edge mixed, then pulled toward grey.
    warm (map.palette: warm, 2026-10-24): half fill, half edge and no greying — mid-deep and clean over the pale base
    (a lighter 70/30 mix read as candy pastel next to the reference), with 15% warm sand so every hue turns earthy."""
    f = [int(fill[i:i + 2], 16) for i in (1, 3, 5)]
    e = [int(edge[i:i + 2], 16) for i in (1, 3, 5)]
    if warm:
        return '#' + ''.join(f'{int(round(0.85 * (0.5 * a + 0.5 * b) + 0.15 * s)):02x}' for a, b, s in zip(f, e, (210, 180, 150)))
    m = [0.42 * a + 0.58 * b for a, b in zip(f, e)]
    g = sum(m) / 3
    return '#' + ''.join(f'{int(round(0.78 * c + 0.22 * g)):02x}' for c in m)


class Territory:
    def __init__(self, spec: dict, compiler):
        self.spec = spec
        self.c = compiler
        name = spec.get('cells')
        f = CELLS / f'{name}.geojson'
        if not f.exists():
            compiler.err(f'territory: cell set `{name}` not built (run cells.py {name})')
            self.ok = False
            return
        self.ok = True
        geo = json.loads(f.read_text(encoding='utf-8'))
        self.meta = geo['meta']
        self.jun = {x['properties']['id']: x for x in geo['features'] if x['properties']['kind'] == 'jun'}
        self.zhou = {x['properties']['name']: x for x in geo['features'] if x['properties']['kind'] == 'zhou'}
        self.zhou_members = {}
        for jid, x in self.jun.items():
            self.zhou_members.setdefault(x['properties']['zhou'], []).append(jid)
        npz = np.load(f.with_suffix('.npz'))
        self.label, self.bbox, self.res = npz['label'], tuple(npz['bbox']), float(npz['res'])
        self.jun_order = [x['properties']['id'] for x in geo['features'] if x['properties']['kind'] == 'jun']
        # label raster indexes the set's full commandery list; map index → id through names
        units = self.meta.get('units')
        if not units:   # sets built before 2026-10-15 carry no unit list: they are the 140 郡国志 order
            units = [norm(j['jun']) for j in json.loads((HERE / 'data' / 'han-commanderies.json').read_text(encoding='utf-8'))['commanderies']]
        self.index_of = {u: k for k, u in enumerate(units)}
        self.cities = geo.get('cities') or []
        slots = {e['slot']: e for e in palette_slots()['slots']}
        self.polities = {}
        warm = (compiler.s.get('map') or {}).get('palette') == 'warm'
        for i, (pname, p) in enumerate((spec.get('polities') or {}).items()):
            p = p or {}
            e = slots.get(p.get('slot')) or list(slots.values())[i % len(slots)]
            self.polities[pname] = {'fill': e['muted'] if p.get('main') else e['fill'], 'edge': e['edge'], 'flag': e['flag'], 'main': bool(p.get('main')),
                                    'atlas': atlas_colour(e['fill'], e['edge'], warm)}

    def expand(self, names, ctx) -> list[str]:
        out = []
        for raw in names or []:
            n = norm(raw)
            if n in self.zhou_members:
                out += self.zhou_members[n]
            elif n in self.jun:
                out.append(n)
            elif n + '郡' in self.jun or n + '国' in self.jun:
                out.append(n + '郡' if n + '郡' in self.jun else n + '国')
            else:
                self.c.err(f'{ctx}: territory name `{raw}` is neither a 州 nor a 郡 of {self.spec.get("cells")}')
        return out

    def is_zhou(self, raw) -> bool:
        return norm(raw) in self.zhou_members

    def compile(self, beats, beats_t, proj) -> dict | None:
        if not self.ok:
            return None
        states = []
        pairs = list(zip(beats, beats_t))
        if self.spec.get('start_owners'):          # opening map before the first `owners` beat (series timeline)
            pairs.insert(0, ({'owners': self.spec['start_owners'], 'say': ''}, {'voice_onset': 0.0, 'voice_offset': 0.0}))
        for i, (b, bt) in enumerate(pairs):
            if 'owners' not in b:
                continue
            ctx = f'beat {i + 1} owners'
            # Two passes: whole provinces first, then named commanderies override them.
            owners, explicit = {}, {}
            for whole in (True, False):
                for pname, names in (b['owners'] or {}).items():
                    if pname not in self.polities:
                        if whole:
                            self.c.err(f'{ctx}: polity `{pname}` not declared in territory.polities')
                        continue
                    for raw in names or []:
                        if self.is_zhou(raw) != whole:
                            continue
                        for jid in self.expand([raw], ctx):
                            if not whole and jid in explicit and explicit[jid] != pname:
                                self.c.err(f'{ctx}: {jid} named for both {explicit[jid]} and {pname}')
                            if whole and jid in owners and owners[jid] != pname:
                                self.c.err(f'{ctx}: province overlap - {jid} in both {owners[jid]} and {pname}')
                            owners[jid] = pname
                            if not whole:
                                explicit[jid] = pname
            uncertain = self.expand(b.get('uncertain'), f'beat {i + 1} uncertain')
            t0 = bt['voice_onset'] + float(b.get('owners_delay', 0))
            if b.get('owners_cue'):
                from studio import cue_time
                ct = cue_time(b.get('say', ''), str(b['owners_cue']), bt['voice_onset'], bt['voice_offset'])
                if ct is None:
                    self.c.err(f'beat {i + 1}: owners_cue「{b["owners_cue"]}」not found in narration')
                else:
                    t0 = ct + float(b.get('owners_delay', 0))
            st = {'t': round(t0, 3), 'owners': owners, 'uncertain': uncertain}
            org = self.c.places.get(b.get('owners_origin')) if b.get('owners_origin') else None
            if org:
                st['origin'] = [org['x'], org['y']]   # spread the new colour from this city
            if b.get('owners_ghost'):
                st['ghost'] = float(b['owners_ghost'])   # old borders linger this many seconds
            states.append(st)
        if not states:
            self.c.warn('territory declared but no beat sets `owners`')
        world = lambda lon, lat: proj.world(lon, lat)

        def path_of(polys):
            return ' '.join('M ' + ' L '.join('%.1f %.1f' % world(x, y) for x, y in ring) + ' Z' for poly in polys for ring in poly)

        cells = []
        for jid, f in self.jun.items():
            ax, ay = world(*f['properties']['anchor'])
            cells.append({'id': jid, 'name': f['properties']['name'], 'zhou': f['properties']['zhou'], 'path': path_of(f['geometry']['coordinates']),
                          'anchor': [round(ax, 1), round(ay, 1)]})
        # which commanderies touch (raster neighbours, >=3 shared pixels): used to group a polity's land into
        # connected patches, so each patch is named once (2026-10-13: one big 曹操 area got two names)
        import collections
        lab = self.label
        cnt = collections.Counter()
        for x, y in ((lab[:, :-1], lab[:, 1:]), (lab[:-1, :], lab[1:, :])):
            m = (x >= 0) & (y >= 0) & (x != y)
            for p, q in zip(x[m].tolist(), y[m].tolist()):
                cnt[(p, q) if p < q else (q, p)] += 1
        id_of = {k: j for j, k in self.index_of.items()}
        touch = collections.defaultdict(set)
        for (p, q), n in cnt.items():
            if n >= 3 and p in id_of and q in id_of:
                touch[id_of[p]].add(id_of[q])
                touch[id_of[q]].add(id_of[p])
        # which commandery each declared place lies in, so its city icon takes the holder's colour (第12批)
        lon0, lat0, lon1, lat1 = self.bbox
        cell_of = {}
        for key, p in self.c.places.items():
            r, c = int((lat1 - p['lat']) / self.res), int((p['lon'] - lon0) / self.res)
            if 0 <= r < self.label.shape[0] and 0 <= c < self.label.shape[1] and self.label[r, c] >= 0:
                cell_of[key] = id_of.get(int(self.label[r, c]))
        # Per-state polity outlines and label anchors by dissolving the raster.
        for st in states:
            st['places'] = {k: st['owners'][j] for k, j in cell_of.items() if j in st['owners'] and j not in st['uncertain']}
            groups: dict[str, list[list[str]]] = {}
            seen = set()
            for j, o in st['owners'].items():
                if j in seen or o not in self.polities:
                    continue
                comp, stack = [], [j]
                seen.add(j)
                while stack:
                    c = stack.pop()
                    comp.append(c)
                    for n in touch.get(c, ()):
                        if n not in seen and st['owners'].get(n) == o:
                            seen.add(n)
                            stack.append(n)
                groups.setdefault(o, []).append(comp)
            st['groups'] = groups
            st['outlines'], st['labels'] = {}, {}
            for pname in self.polities:
                ks = [self.index_of[j] for j, o in st['owners'].items() if o == pname and j in self.index_of]
                if not ks:
                    continue
                m = np.isin(self.label, ks)
                m |= ndimage.binary_fill_holes(m) & (self.label < 0)   # enclosed water / gaps are part of the polity
                polys = trace(m, self.bbox, self.res, sigma=1.2)
                if not polys:
                    continue
                st['outlines'][pname] = path_of(polys)
                at = (self.spec.get('polities') or {}).get(pname, {}) or {}
                place = self.c.places.get(at.get('label_at')) if at.get('label_at') else None
                if at.get('label_at') and not place:
                    self.c.err(f"territory.polities.{pname}.label_at: place `{at['label_at']}` not declared")
                # the capital anchors the label only while the polity still holds it (董卓 taking 洛阳 moves 汉室's label off it)
                if place and any(inside(place['lon'], place['lat'], poly[0]) for poly in polys if len(poly)):
                    lx, ly = place['x'], place['y']  # pill sits above the capital
                else:
                    lx, ly = world(*label_anchor(polys))
                st['labels'][pname] = [round(lx, 1), round(ly, 1)]
        # 州界: thin dashed province boundaries, always visible (user 2026-10-08: 州要有边缘)
        zlines = []
        if self.spec.get('zhou_lines', True):
            for zname, members in self.zhou_members.items():
                ks = [self.index_of[j] for j in members if j in self.index_of]
                if not ks:
                    continue
                m = np.isin(self.label, ks)
                m |= ndimage.binary_fill_holes(m) & (self.label < 0)
                polys = trace(m, self.bbox, self.res, sigma=1.2)
                if polys:
                    zlines.append(path_of(polys))
        zl = []
        if self.spec.get('zhou_labels', True):
            for zname, f in self.zhou.items():
                x, y = world(*f['properties']['anchor'])
                zl.append({'name': zname, 'x': round(x, 1), 'y': round(y, 1)})
        # City layer (2026-10-15): every located county town, so the map reads like an atlas. Towns the episode
        # already declares as places are left to the episode's own city marks (no double names).
        cities = []
        if self.spec.get('cities', True) and self.cities:
            declared = list(self.c.places.values())
            names = {norm(n) for n in self.c.places} | {norm(p.get('name') or '') for p in declared}
            for ct in self.cities:
                x, y = world(ct['lon'], ct['lat'])
                if ct['name'] in names or any(math.hypot(p['x'] - x, p['y'] - y) < 30 for p in declared):
                    continue
                c = {'name': ct['name'], 'x': round(x, 1), 'y': round(y, 1), 'rank': ct['rank']}
                # atlases name a 郡治 by its commandery (南阳 ◎, not 宛); a one-character stem keeps its suffix (蜀郡)
                if ct['rank'] == 1 and ct.get('jun'):
                    j = ct['jun']
                    # 属国 stays whole (蜀郡属国 was cut to 蜀郡属, 2026-10-25)
                    c['jun'] = j[:-1] if j[-1] in '郡国' and len(j) > 2 and not j.endswith('属国') else j
                cities.append(c)
        return {'cells': cells, 'polities': self.polities, 'states': states, 'zhou_labels': zl, 'zhou_lines': zlines, 'cities': cities,
                'jun_labels': 'always' if self.spec.get('jun_labels') == 'always' else bool(self.spec.get('jun_labels', True)), 'precision': self.meta['precision']}
