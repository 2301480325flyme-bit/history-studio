"""Polity regions from territory snapshot GeoJSON.

One snapshot file holds several polities (e.g. 五代十国 has 13). This module
groups features by name, finds which polities touch, picks colours with
`palette.assign`, and computes a label anchor inside each polity. Pure Python:
adjacency is approximated by boundary vertices that come within `touch_deg`.
"""

from __future__ import annotations

import math
from collections import defaultdict

from palette import assign

# Small traditional→simplified table for polity names in the snapshot files.
T2S = str.maketrans('東晉後趙涼漢齊韓魯鄒鄧吳呉陳閩遼衛鄭書國蘭歸為與黃嶺寧強陝劉會長亂陸兩隴關張貴鄴陽陰鄉縣門開馬臨溫潁鉅濟樂萊荊揚廬雲鳳黽盧間靑兗隸嶲譙滎潛歷觀蒼鬱風馮農鹽穎葉興義紀綏師臺賓郟壽櫟麗龍聖蘇區單僕廣廟',
                    '东晋后赵凉汉齐韩鲁邹邓吴吴陈闽辽卫郑书国兰归为与黄岭宁强陕刘会长乱陆两陇关张贵邺阳阴乡县门开马临温颍巨济乐莱荆扬庐云凤黾卢间青兖隶巂谯荥潜历观苍郁风冯农盐颍叶兴义纪绥师台宾郏寿栎丽龙圣苏区单仆广庙')


def norm(s: str) -> str:
    """Simplified-Chinese key for matching place/polity names across sources."""
    return (s or '').translate(T2S)


def polygons(geom) -> list[list[list[tuple[float, float]]]]:
    if geom['type'] == 'Polygon':
        return [geom['coordinates']]
    if geom['type'] == 'MultiPolygon':
        return geom['coordinates']
    return []


def ring_area(r) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]))


def inside(pt, rings) -> bool:
    x, y = pt
    hit = False
    for ring in rings:
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
            if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / ((y1 - y0) or 1e-12) + x0:
                hit = not hit
    return hit


def edge_distance(pt, rings) -> float:
    best = math.inf
    px, py = pt
    for ring in rings:
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
            dx, dy = x1 - x0, y1 - y0
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / ((dx * dx + dy * dy) or 1e-12)))
            best = min(best, math.hypot(px - x0 - t * dx, py - y0 - t * dy))
    return best


def label_anchor(polys) -> tuple[float, float]:
    """Point well inside the largest polygon (coarse pole of inaccessibility)."""
    rings = max(polys, key=lambda p: abs(ring_area(p[0])))
    xs = [x for x, _ in rings[0]]
    ys = [y for _, y in rings[0]]
    best, best_d = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2), -1.0
    for step in (24, 12):
        for i in range(step + 1):
            for j in range(step + 1):
                pt = (min(xs) + (max(xs) - min(xs)) * i / step, min(ys) + (max(ys) - min(ys)) * j / step)
                if inside(pt, rings):
                    d = edge_distance(pt, rings)
                    if d > best_d:
                        best, best_d = pt, d
    return best


def neighbours(groups: dict[str, list], touch_deg: float = 0.12) -> dict[str, set[str]]:
    cell = touch_deg
    grid = defaultdict(set)
    for name, polys in groups.items():
        for poly in polys:
            for ring in poly:
                for x, y in ring:
                    grid[(int(x // cell), int(y // cell))].add(name)
    nb: dict[str, set[str]] = defaultdict(set)
    for (gx, gy), names in grid.items():
        near = set(names)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near |= grid.get((gx + dx, gy + dy), set())
        for n in names:
            nb[n] |= near - {n}
    return nb


def load_snapshot(geo: dict, name_field: str, rename: dict | None = None, main: str | None = None,
                  fixed: dict | None = None, simplify_names=True):
    """Return [{name, polys, fill, edge, flag, slot, anchor_lonlat}] grouped by polity name."""
    rename = rename or {}
    groups: dict[str, list] = defaultdict(list)
    for f in geo['features']:
        raw = str((f.get('properties') or {}).get(name_field) or '').strip()
        if not raw:
            continue
        name = rename.get(raw) or (raw.translate(T2S) if simplify_names else raw)
        if name == '-':  # rename to '-' drops a feature
            continue
        groups[name].extend(polygons(f['geometry']))
    nb = neighbours(groups)
    colours = assign(list(groups), nb, main=main, fixed=fixed)
    return [{'name': n, 'polys': polys, **colours[n], 'anchor': label_anchor(polys), 'neighbours': sorted(nb.get(n, ()))}
            for n, polys in groups.items()]
