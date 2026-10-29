"""Commandery cells: terrain-aware territories grown from county seats.

Every county seat located on Wikidata seeds a multi-source least-cost
expansion over an ETOPO terrain grid. Steep slopes, high ground and major
rivers are expensive and the sea is impassable, so the resulting borders
follow ridges and rivers the way historical atlas boundaries do. Cells far
from any county stay unassigned (steppe, plateau). Grid cells are labelled by
commandery and traced into smooth polygons; provinces are their unions.

These are *schematic* ranges derived from county locations and terrain — not
surveyed historical borders — and every output says so.

    python cells.py han-140      # data/cells/han-140.geojson (+ zhou outlines)
    python cells.py han-219      # 建安郡（derive_219.py 先生成郡表）

Each set also writes `cities`: every located county seat as a point (rank 1 = 郡治, rank 2 = 县治), for the
always-on city layer. Positions are the same approximate seeds the cells grow from.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import contourpy
import numpy as np
import shapefile
from PIL import Image, ImageDraw
from scipy import ndimage, sparse
from scipy.sparse.csgraph import dijkstra

import basemap_dem
from regions import T2S, label_anchor, norm

HERE = Path(__file__).resolve().parent
NE = basemap_dem.NE

SETS = {
    'han-140': {
        'commanderies': HERE / 'data' / 'han-commanderies.json',
        'counties': HERE / 'data' / 'han-county-coords.json',
        'bbox': (94.0, 15.0, 128.0, 44.5),
        'res': 0.025,
        'limit_km': 340.0,
        'epoch': '东汉·永和五年（140）郡国志',
    },
    'han-219': {
        'commanderies': HERE / 'data' / 'han-219-commanderies.json',
        'counties': HERE / 'data' / 'han-219-county-coords.json',
        'bbox': (94.0, 15.0, 128.0, 44.5),
        'res': 0.025,
        'limit_km': 340.0,
        'epoch': '东汉末·建安二十四年（219）前后郡国（140 年郡国志 + 建安新设郡）',
    },
}


def simplify(points: np.ndarray, tol: float) -> np.ndarray:
    """Douglas–Peucker on a closed ring (in degrees)."""
    if len(points) < 5:
        return points

    def rdp(pts):
        a, b = pts[0], pts[-1]
        ab = b - a
        n = np.hypot(*ab) or 1e-12
        d = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / n
        i = int(np.argmax(d))
        if d[i] > tol:
            return np.vstack([rdp(pts[:i + 1])[:-1], rdp(pts[i:])])
        return np.vstack([a, b])
    sys.setrecursionlimit(10000)
    # Closed ring: split at the vertex farthest from the start, simplify both halves.
    k = int(np.argmax(np.hypot(*(points - points[0]).T)))
    if k == 0:
        return points
    return np.vstack([rdp(points[:k + 1])[:-1], rdp(points[k:])])


def rasterize_lines(shp: Path, to_px, size, max_rank: int) -> np.ndarray:
    img = Image.new('L', size, 0)
    d = ImageDraw.Draw(img)
    r = shapefile.Reader(str(shp), encoding='utf-8')
    for sr in r.iterShapeRecords():
        if (sr.record.as_dict().get('scalerank') or 99) > max_rank:
            continue
        pts, parts = sr.shape.points, list(sr.shape.parts) + [len(sr.shape.points)]
        for a, b in zip(parts, parts[1:]):
            line = [to_px(x, y) for x, y in pts[a:b]]
            if len(line) > 1:
                d.line(line, fill=255, width=2)
    return np.asarray(img) > 0


def build(name: str) -> dict:
    cfg = SETS[name]
    lon0, lat0, lon1, lat1 = cfg['bbox']
    res = cfg['res']
    nx, ny = int(round((lon1 - lon0) / res)), int(round((lat1 - lat0) / res))
    lons = lon0 + (np.arange(nx) + 0.5) * res
    lats = lat1 - (np.arange(ny) + 0.5) * res          # row 0 = north
    to_px = lambda x, y: ((x - lon0) / res, (lat1 - y) / res)

    # Terrain on the grid.
    dem, dlats, dlons = basemap_dem.load_dem(lon0 - 0.2, lat0 - 0.2, lon1 + 0.2, lat1 + 0.2, step=max(1, int(res / (15 / 3600))))
    LA, LO = np.meshgrid(lats, lons, indexing='ij')
    z = ndimage.map_coordinates(np.nan_to_num(dem), [(LA - dlats[0]) / (dlats[1] - dlats[0]), (LO - dlons[0]) / (dlons[1] - dlons[0])], order=1)
    land = np.asarray(basemap_dem.rasterize(NE / 'ne_10m_land' / 'ne_10m_land.shp', to_px, (nx, ny), (lon0, lat0, lon1, lat1))) > 0
    lakes = np.asarray(basemap_dem.rasterize(NE / 'ne_10m_lakes' / 'ne_10m_lakes.shp', to_px, (nx, ny), (lon0, lat0, lon1, lat1))) > 0
    passable = land & ~lakes
    rivers = rasterize_lines(NE / 'ne_10m_rivers_lake_centerlines' / 'ne_10m_rivers_lake_centerlines.shp', to_px, (nx, ny), 4)

    km_y = res * 111.2
    km_x = km_y * np.cos(np.radians(LA))
    gy, gx = np.gradient(z)
    slope = np.hypot(gx / (km_x * 1000), gy / (km_y * 1000))
    cost = 1 + 18 * np.clip(slope, 0, 0.6) + np.clip((z - 1200) / 900, 0, 3) + 5 * rivers
    cost[~passable] = np.inf

    # 8-neighbour graph with edge weight = mean cost × step length (km).
    idx = np.arange(nx * ny).reshape(ny, nx)
    rows, cols, wts = [], [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        # a = cells that have a neighbour at (+dy, +dx); b = those neighbours.
        r0, r1 = 0, ny - dy
        c0, c1 = max(0, -dx), nx - max(0, dx)
        a = idx[r0:r1, c0:c1]
        b = idx[r0 + dy:r1 + dy, c0 + dx:c1 + dx]
        ca, cb = cost.ravel()[a.ravel()], cost.ravel()[b.ravel()]
        lat_mid = LA.ravel()[a.ravel()]
        step = np.hypot(dx * km_y * np.cos(np.radians(lat_mid)), dy * km_y)
        w = (ca + cb) / 2 * step
        ok = np.isfinite(w)
        rows.append(a.ravel()[ok])
        cols.append(b.ravel()[ok])
        wts.append(w[ok])
    G = sparse.coo_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(nx * ny, nx * ny)).tocsr()

    comm = json.loads(cfg['commanderies'].read_text(encoding='utf-8'))['commanderies']
    cdata = json.loads(cfg['counties'].read_text(encoding='utf-8'))
    counties = cdata['counties'] + [{**e, 'seat': False, 'qid': 'extra', 'why': ['relocated-county']} for e in cdata.get('extra_seeds', []) if 'lon' in e]
    jun_ids = {j['jun']: k for k, j in enumerate(comm)}
    seats_file = HERE / 'data' / 'han-seats-geocoded.json'
    if seats_file.exists():
        # Commandery seats (modern-location approximations) are always seeds.
        for jun, v in json.loads(seats_file.read_text(encoding='utf-8'))['seats'].items():
            counties = counties + [{'jun': jun, 'qid': v['qid'], 'lon': v['lon'], 'lat': v['lat'], 'seat': True, 'why': ['seat-table']}]
    man_file = HERE / 'data' / 'han-seeds-manual.json'
    if man_file.exists():
        # hand-checked seeds for regions Wikidata barely covers (Fujian, Lingnan, Yunnan-Guizhou)
        counties = counties + [{**m, 'qid': 'manual', 'why': ['manual']} for m in json.loads(man_file.read_text(encoding='utf-8'))['seeds']]
    rej_file = HERE / 'data' / 'han-county-rejects.json'
    rejects = {(r['jun'], r['county']) for r in json.loads(rej_file.read_text(encoding='utf-8'))['rejects']} if rej_file.exists() else set()
    seeds, seed_jun, taken = [], [], set()
    for c in counties:
        if not c.get('qid') or 'far-from-jun' in c.get('why', []) or (c['jun'], c.get('county')) in rejects:
            continue
        px, py = to_px(c['lon'], c['lat'])
        i, j = int(py), int(px)
        if not (0 <= i < ny and 0 <= j < nx):
            continue
        if not passable[i, j]:
            # snap to nearest passable cell within ~10 km
            win = passable[max(0, i - 4):i + 5, max(0, j - 4):j + 5]
            if not win.any():
                continue
            ii, jj = np.argwhere(win)[0]
            i, j = max(0, i - 4) + ii, max(0, j - 4) + jj
        if idx[i, j] in taken:          # two seeds on one pixel (a seat-table point on a county town): nudge the later one
            free = [(i + di, j + dj) for di in (-2, 0, 2) for dj in (-2, 0, 2)
                    if 0 <= i + di < ny and 0 <= j + dj < nx and passable[i + di, j + dj] and idx[i + di, j + dj] not in taken]
            if not free:
                continue
            i, j = free[0]
        taken.add(idx[i, j])
        seeds.append(idx[i, j])
        seed_jun.append(jun_ids[c['jun']])
    seeds = np.array(seeds)
    dist, _, src = dijkstra(G, directed=False, indices=seeds, min_only=True, return_predecessors=True, limit=cfg['limit_km'])
    seed_label = dict(zip(seeds.tolist(), seed_jun))
    label = np.full(nx * ny, -1)
    reached = src >= 0
    label[reached] = [seed_label[s] for s in src[reached]]
    label = label.reshape(ny, nx)
    # Stray pieces: a county point placed by its modern successor town can sit inside the next commandery and
    # grow a detached island there. Each commandery keeps its largest piece (and any piece at least a third of
    # it, e.g. across a strait); smaller islands go to the commandery that surrounds most of their border.
    for _ in range(3):
        changed = 0
        for k in np.unique(label[label >= 0]):
            comp, n = ndimage.label(label == k)
            if n < 2:
                continue
            sizes = ndimage.sum(np.ones_like(comp), comp, range(1, n + 1))
            big = sizes.max()
            for ci, sz in enumerate(sizes, start=1):
                if sz >= big or sz >= big / 3:
                    continue
                piece = comp == ci
                ring = ndimage.binary_dilation(piece) & ~piece
                around = label[ring]
                around = around[(around >= 0) & (around != k)]
                if around.size:
                    label[piece] = np.bincount(around).argmax()
                    changed += 1
        if not changed:
            break
    # Lakes belong to the commanderies around them: give each lake pixel the nearest commandery,
    # so cells and dissolved polity outlines have no holes (and no outlines) around inland water.
    if (label >= 0).any():
        near = ndimage.distance_transform_edt(label < 0, return_distances=False, return_indices=True)
        inland = lakes & (label < 0)
        label[inland] = label[near[0][inland], near[1][inland]]

    def trace(mask: np.ndarray) -> list[list[list[float]]]:
        """Smooth binary mask → list of polygons (rings of [lon, lat])."""
        f = ndimage.gaussian_filter(mask.astype(np.float32), 0.9)
        gen = contourpy.contour_generator(z=f, fill_type=contourpy.FillType.OuterOffset)
        polys = []
        filled, offsets = gen.filled(0.5, 2.0)
        for pts, offs in zip(filled, offsets):
            rings = []
            for a, b in zip(offs[:-1], offs[1:]):
                ring = pts[a:b]
                if len(ring) < 4:
                    continue
                geo = np.column_stack([lon0 + (ring[:, 0] + 0.5) * res, lat1 - (ring[:, 1] + 0.5) * res])
                geo = simplify(geo, res * 0.6)
                if len(geo) >= 4:
                    rings.append(np.round(geo, 4).tolist())
            if rings and abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(rings[0], rings[0][1:] + rings[0][:1]))) / 2 > (res * 3) ** 2:
                polys.append(rings)
        return polys

    feats = []
    for k, j in enumerate(comm):
        m = label == k
        if not m.any():
            continue
        polys = trace(m)
        if not polys:
            continue
        seat = next((c for c in counties if c['jun'] == j['jun'] and c.get('county') and norm(c['county']) == norm(j['seat'] or '') and c.get('qid')), None)             or next((c for c in counties if c['jun'] == j['jun'] and c['seat'] and c.get('qid')), None)
        located = sum(1 for c in counties if c['jun'] == j['jun'] and c.get('qid'))
        feats.append({'type': 'Feature', 'geometry': {'type': 'MultiPolygon', 'coordinates': polys},
                      'properties': {'id': norm(j['jun']), 'name': norm(j['jun']), 'zhou': norm(j['zhou'] or ''),
                                     'seat': norm(j['seat'] or ''), 'seat_lonlat': [seat['lon'], seat['lat']] if seat else None,
                                     'anchor': list(label_anchor(polys)), 'counties_total': len(j['counties']), 'counties_located': located,
                                     'parent': j.get('parent') or norm(j['jun']), 'index': k, 'kind': 'jun'}})
    # Provinces: union of their commanderies.
    for zhou in sorted({j['zhou'] for j in comm if j['zhou']}):
        ks = [k for k, j in enumerate(comm) if j['zhou'] == zhou]
        polys = trace(np.isin(label, ks))
        if polys:
            feats.append({'type': 'Feature', 'geometry': {'type': 'MultiPolygon', 'coordinates': polys},
                          'properties': {'id': 'zhou:' + norm(zhou), 'name': norm(zhou), 'anchor': list(label_anchor(polys)), 'kind': 'zhou'}})
    # City layer: one point per located county (seat-table/manual seeds are commandery anchors, not cities).
    # Several counties often share one modern successor town: keep one dot per ~4 km, the commandery seat first.
    seat_of = {j['jun']: norm(j['seat'] or '') for j in comm}
    try:                              # display names fully simplified (郡国志 text mixes 輪/潁/鄲… and variants 髙/卽/鄕)
        from opencc import OpenCC
        t2s = OpenCC('t2s').convert
    except ImportError:
        t2s = norm
    VARIANT = str.maketrans('髙卽鄕靑塲', '高即乡青场')
    simp = lambda x: t2s(norm(x)).translate(VARIANT)
    pts = []
    for c in counties:
        if not c.get('county') or not c.get('qid') or 'far-from-jun' in c.get('why', []) or (c['jun'], c.get('county')) in rejects:
            continue
        rank = 1 if norm(c['county']) == seat_of.get(c['jun']) else 2
        pts.append({'name': simp(c['county']), 'jun': norm(c['jun']), 'rank': rank, 'lon': round(c['lon'], 4), 'lat': round(c['lat'], 4),
                    'precision': 'ancient' if c.get('precision') == 'ancient' else 'modern-successor'})
    pts.sort(key=lambda p: p['rank'])
    cities = []
    for p in pts:
        if all(math.hypot(p['lon'] - q['lon'], p['lat'] - q['lat']) > 0.04 for q in cities):
            cities.append(p)
    out = HERE / 'data' / 'cells' / f'{name}.geojson'
    out.parent.mkdir(exist_ok=True)
    meta = {'set': name, 'epoch': cfg['epoch'], 'method': 'multi-source least-cost expansion from Wikidata county seats over ETOPO 2022 terrain; Natural Earth land/lakes/rivers',
            'precision': '郡界为按县治位置与地形自动推算的示意范围，非实测或考订疆界',
            'sources': ['《后汉书·郡国志》（公有领域）', 'Wikidata 县治坐标（CC0）', 'NOAA ETOPO 2022（公有领域）', 'Natural Earth（公有领域）'],
            'seeds': int(len(seeds)), 'commanderies': sum(1 for f in feats if f['properties']['kind'] == 'jun'), 'grid': [nx, ny, res],
            'units': [norm(j['jun']) for j in comm], 'cities': len(cities),
            'cities_precision': '城邑位置取县治今址近似（Wikidata 现代驻地或古城址，CC0），示意'}
    out.write_text(json.dumps({'type': 'FeatureCollection', 'meta': meta, 'features': feats, 'cities': cities}, ensure_ascii=False), encoding='utf-8')
    np.savez_compressed(out.with_suffix('.npz'), label=label, bbox=np.array(cfg['bbox']), res=res)
    print(json.dumps(meta, ensure_ascii=False))
    missing = [j['jun'] for k, j in enumerate(comm) if not (label == k).any()]
    print('commanderies without cells:', missing)
    return meta


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else 'han-140')
