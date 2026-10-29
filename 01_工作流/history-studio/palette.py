"""Polity palette for History Studio map fills.

Colours are generated in OKLCH so every polity sits at the same perceived
lightness: dark ink labels stay readable on any fill, and no polity looks
"heavier" than another by accident. The main (central) polity of an episode
uses the muted variant, neighbours use the accent variant — the same
foreground/background balance as the reference atlas videos.

    python palette.py            # write data/palette.json and print checks
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'data' / 'palette.json'
INK = '#2b2118'

# Hue order is chosen so consecutive entries differ strongly; polities take
# slots in order of first appearance, so early (usually adjacent) polities
# never get neighbouring hues. Names describe the colour, not a dynasty.
SLOTS = [
    ('salmon', 45, 0.80, 0.105),
    ('sky', 235, 0.80, 0.090),
    ('lemon', 100, 0.88, 0.140),
    ('rose', 10, 0.74, 0.130),
    ('lime', 130, 0.84, 0.140),
    ('violet', 315, 0.78, 0.100),
    ('teal', 180, 0.79, 0.090),
    ('orange', 65, 0.80, 0.130),
    ('blue', 250, 0.73, 0.095),
    ('olive', 110, 0.76, 0.100),
    ('pink', 345, 0.80, 0.095),
    ('jade', 155, 0.80, 0.100),
    ('tan', 75, 0.76, 0.070),
    ('lavender', 285, 0.84, 0.060),
    ('aqua', 205, 0.84, 0.080),
    ('brick', 30, 0.73, 0.110),
    # neutral, for 'nominally the court's / no warlord' land (汉室): never handed out automatically
    ('stone', 80, 0.86, 0.018),
]
RESERVED = {'stone'}


def oklch_to_srgb(L: float, C: float, h: float) -> tuple[float, float, float]:
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    lin = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    return tuple(max(0.0, min(1.0, 1.055 * c ** (1 / 2.4) - 0.055 if c > 0.0031308 else 12.92 * c)) for c in lin)


def hex_of(rgb) -> str:
    return '#' + ''.join(f'{round(c * 255):02x}' for c in rgb)


def rgb_of(hx: str) -> tuple[float, float, float]:
    return tuple(int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5))


def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklab(rgb):
    r, g, b = (linear(c) for c in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def luminance(rgb):
    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# Machado et al. 2009 severity-1.0 matrices (linear RGB).
CVD = {
    'deuteranopia': ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    'protanopia': ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
}


def simulate(rgb, kind):
    lin = [linear(c) for c in rgb]
    out = [max(0.0, min(1.0, sum(m * v for m, v in zip(row, lin)))) for row in CVD[kind]]
    return tuple(1.055 * c ** (1 / 2.4) - 0.055 if c > 0.0031308 else 12.92 * c for c in out)


def dist(a, b):
    return math.dist(oklab(a), oklab(b))


def build() -> dict:
    entries = []
    for name, h, L, C in SLOTS:
        accent = oklch_to_srgb(L, C, h)
        muted = oklch_to_srgb(min(0.86, L + 0.03), C * 0.62, h)
        edge = oklch_to_srgb(max(0.35, L - 0.32), min(0.16, C * 1.2), h)
        flag = oklch_to_srgb(0.48, min(0.15, C * 1.3), h)
        entries.append({'slot': name, 'hue': h, 'fill': hex_of(accent), 'muted': hex_of(muted), 'edge': hex_of(edge), 'flag': hex_of(flag),
                        'ink_contrast': round(contrast(accent, rgb_of(INK)), 2)})
    return {'version': 1, 'ink': INK, 'note': 'OKLCH-generated polity fills. Main polity uses `muted`; others `fill`. Edges and flags derive from the same hue.', 'slots': entries}


def checks(p: dict) -> list[str]:
    fills = [rgb_of(e['fill']) for e in p['slots']]
    report = [f"ink contrast min {min(e['ink_contrast'] for e in p['slots']):.2f} (want ≥ 7 for small labels)"]
    for n in (8, 12, 16):
        pairs = list(itertools.combinations(range(n), 2))
        normal = min(dist(fills[i], fills[j]) for i, j in pairs)
        line = f'first {n:>2} slots: min ΔOKLab {normal:.3f}'
        for kind in CVD:
            sim = [simulate(c, kind) for c in fills[:n]]
            i, j = min(pairs, key=lambda q: dist(sim[q[0]], sim[q[1]]))
            line += f' · {kind} {dist(sim[i], sim[j]):.3f} ({p["slots"][i]["slot"]}/{p["slots"][j]["slot"]})'
        report.append(line)
    return report


def pair_distance(a: str, b: str) -> float:
    """Worst-case perceptual distance across normal, deuteranope and protanope vision."""
    ra, rb = rgb_of(a), rgb_of(b)
    return min(dist(ra, rb), *(dist(simulate(ra, k), simulate(rb, k)) for k in CVD))


def assign(names: list[str], neighbours: dict[str, set[str]], main: str | None = None,
           fixed: dict[str, str] | None = None) -> dict[str, dict]:
    """Give each polity a slot so that neighbours differ as much as possible.

    `fixed` pins slots by name (e.g. from the cross-episode registry); `main`
    gets the muted variant. Highest-degree polities are coloured first."""
    slots = {e['slot']: e for e in build()['slots']}
    fixed = dict(fixed or {})
    chosen: dict[str, str] = {}
    order = sorted(names, key=lambda n: (n not in fixed, n != main, -len(neighbours.get(n, ()))))
    for n in order:
        if n in fixed:
            chosen[n] = fixed[n]
            continue
        used = set(chosen.values())

        def score(slot):
            nb = [chosen[m] for m in neighbours.get(n, ()) if m in chosen]
            near = min((pair_distance(slots[slot]['fill'], slots[o]['fill']) for o in nb), default=1.0)
            return (slot not in used, near)
        chosen[n] = max((k for k in slots if k not in RESERVED), key=score)
    out = {}
    for n, sl in chosen.items():
        e = slots[sl]
        out[n] = {'slot': sl, 'fill': e['muted'] if n == main else e['fill'], 'edge': e['edge'], 'flag': e['flag']}
    return out


if __name__ == '__main__':
    p = build()
    p['checks'] = checks(p)
    OUT.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding='utf-8')
    for e in p['slots']:
        print(f"{e['slot']:<9} fill {e['fill']}  muted {e['muted']}  edge {e['edge']}  flag {e['flag']}  ink×{e['ink_contrast']}")
    print('\n'.join(p['checks']))
