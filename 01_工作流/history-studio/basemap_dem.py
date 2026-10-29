"""Open-data basemap: ETOPO 2022 relief + Natural Earth land/lakes, atlas style.

Public-domain inputs only (NOAA ETOPO 2022 15 arc-second surface elevation,
Natural Earth 10m), so the rendered map can be used in monetised videos.
Look follows the reference atlas videos: light grey land with strong
multi-directional hillshade, dark slate-blue sea with a soft coastal glow,
blue lakes. Political colour is added later by the engine (multiply).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import h5py
import numpy as np
import shapefile
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
OPEN = ROOT / '02_数据' / '开放地理数据'
ETOPO = OPEN / 'etopo2022_15s'
NE = OPEN / 'naturalearth'
CACHE = Path(__file__).resolve().parent / 'cache'
W, H = 1920, 1080

STYLE = {
    'land': (207, 203, 194),      # light warm grey, like unclaimed land in the reference
    'high': (232, 229, 222),      # high ground slightly lighter
    'sea_shallow': (88, 106, 128),
    'sea_deep': (58, 72, 92),
    'coast_glow': (150, 166, 182),
    'lake': (112, 146, 182),
    # 'soft' look (2026-10-08, user: ridges too harsh): generalised terrain like printed atlases —
    # the DEM is blurred before shading, lower exaggeration and contrast, no harsh black valleys.
    'relief_strength': 1.45,
    'exaggeration': 2.4,
    'valley_shadow': 0.22,
    'smooth': 1.0,          # Gaussian sigma (output px) applied to the DEM before hillshade; 0 = raw
    'shade_floor': 0.5,     # darkest relief multiplier
}
STRONG = {'relief_strength': 1.9, 'exaggeration': 3.2, 'valley_shadow': 0.35, 'smooth': 0, 'shade_floor': 0.3}
# map.look presets. 'light' (default since 2026-10-08) follows printed-atlas style history maps:
# pale land with gentle relief, bright light-blue sea and lakes. 'classic' = the old dark-sea, sharp relief.
LOOKS = {
    'light': {'land': (233, 232, 228), 'high': (246, 246, 244), 'sea_shallow': (166, 205, 238), 'sea_deep': (140, 186, 228),
              'coast_glow': (206, 228, 246), 'lake': (146, 194, 234), 'relief_strength': 1.35, 'shade_floor': 0.56},
    'classic': {**STRONG},
    # 'atlas' (2026-10-15, after 史图记忆簿): neutral grey-olive land with strong relief so the dark translucent
    # polity colours read like a printed atlas; slate-grey sea; rivers come as a separate pale band layer.
    'atlas': {'land': (176, 178, 166), 'high': (196, 197, 188), 'sea_shallow': (118, 132, 140), 'sea_deep': (96, 110, 120),
              'coast_glow': (150, 162, 168), 'lake': (150, 165, 172), 'relief_strength': 2.5, 'exaggeration': 4.2,
              'valley_shadow': 0.45, 'smooth': 0.4, 'shade_floor': 0.28},
}
# map.palette: warm (2026-10-24, after 地图知天下): the atlas look on a light base. Measured against the reference,
# 'atlas' was ~20% darker, 1.6x (mountains) to 3.5x (unclaimed land) stronger in mid-scale relief and greyer, which
# read as wrinkled skin. Pale grey-white land (polity fills colour it), gentle relief, slate sea with a pale shelf.
WARM = {'land': (232, 230, 223), 'high': (243, 242, 237), 'sea_shallow': (76, 98, 124), 'sea_deep': (64, 86, 110),
        'coast_glow': (178, 198, 212), 'lake': (92, 132, 166), 'relief_strength': 1.3, 'exaggeration': 2.6,
        'valley_shadow': 0.15, 'smooth': 0.6, 'shade_floor': 0.62, 'high_fade': 0.55}
# atlas rivers: wide pale bands with a dark rim, widths by Natural Earth scalerank (big rivers first)
RIVER_BANDS = {0: 13, 1: 12, 2: 10, 3: 9, 4: 7.5, 5: 6, 6: 5, 7: 4, 8: 3.2}


def tile_name(lat_top: int, lon_left: int) -> str:
    return f"ETOPO_2022_v1_15s_N{lat_top:02d}E{lon_left:03d}_surface.nc"


def load_dem(lon0, lat0, lon1, lat1, step: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mosaic ETOPO tiles over the bbox, decimated by `step` (1 = 15 arc-seconds)."""
    per = 3600 // step
    lats_top = range(int(math.floor(lat0 / 15) * 15) + 15, int(math.ceil(lat1 / 15) * 15) + 15, 15)
    lons_left = range(int(math.floor(lon0 / 15) * 15), int(math.ceil(lon1 / 15) * 15), 15)
    rows = []
    for top in lats_top:
        row = []
        for left in lons_left:
            f = ETOPO / tile_name(top, left)
            if f.exists():
                with h5py.File(f, 'r') as h:
                    z = h['z'][::step, ::step].astype(np.float32)
                z[z < -20000] = np.nan
            else:
                z = np.full((per, per), np.nan, np.float32)
            row.append(z)
        rows.append(np.hstack(row))
    dem = np.vstack(rows)  # south → north rows
    lat_min = min(lats_top) - 15
    lon_min = min(lons_left)
    res = 15 / per
    lats = lat_min + (np.arange(dem.shape[0]) + 0.5) * res
    lons = lon_min + (np.arange(dem.shape[1]) + 0.5) * res
    return dem, lats, lons


def rasterize(shp: Path, to_px, size, bbox, skip_reservoirs: bool = True) -> Image.Image:
    lon0, lat0, lon1, lat1 = bbox
    mask = Image.new('L', size, 0)
    d = ImageDraw.Draw(mask)
    r = shapefile.Reader(str(shp))
    fields = [f[0] for f in r.fields[1:]]
    # modern dam reservoirs (e.g. 小浪底) are not historical water bodies
    keep = [not (skip_reservoirs and 'featurecla' in fields and rec[fields.index('featurecla')] == 'Reservoir') for rec in r.iterRecords()]
    for k, s in enumerate(r.iterShapes()):
        if not keep[k]:
            continue
        x0, y0, x1, y1 = s.bbox
        if x1 < lon0 - 1 or x0 > lon1 + 1 or y1 < lat0 - 1 or y0 > lat1 + 1:
            continue
        parts = list(s.parts) + [len(s.points)]
        for a, b in zip(parts, parts[1:]):
            ring = [to_px(x, y) for x, y in s.points[a:b]]
            if len(ring) > 2:
                # Fill every ring: land holes are mostly inland seas/lakes, drawn separately.
                d.polygon(ring, fill=255)
    return mask


def build(center, scale, extent, res=1.0, style=None) -> tuple[Image.Image, dict]:
    style = {**STYLE, **(style or {})}
    lon_c, lat_c = center
    merc = lambda lat: np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    m0 = float(merc(lat_c))
    lon_w, lat_s, lon_e, lat_n = extent
    wx = lambda lon: W / 2 + math.radians(lon - lon_c) * scale
    wy = lambda lat: H / 2 - scale * (float(merc(lat)) - m0)
    x0, x1, y0, y1 = wx(lon_w), wx(lon_e), wy(lat_n), wy(lat_s)
    ow, oh = int((x1 - x0) * res), int((y1 - y0) * res)
    key = hashlib.sha256(json.dumps([center, scale, extent, res, style, 'dem-v5']).encode()).hexdigest()[:16]
    cached = CACHE / f'dem-{key}.jpg'
    meta = {'x': round(x0, 2), 'y': round(y0, 2), 'width': round(x1 - x0, 2), 'height': round(y1 - y0, 2), 'pixels': [ow, oh]}
    if cached.exists():
        return Image.open(cached), {**meta, **json.loads(cached.with_suffix('.json').read_text(encoding='utf-8'))}

    # Pick a DEM step close to the output resolution (output px per degree).
    px_per_deg = math.radians(1) * scale * res
    step = max(1, min(12, int(240 / px_per_deg / 1.2) or 1))
    dem, lats, lons = load_dem(lon_w - 0.5, lat_s - 0.5, lon_e + 0.5, lat_n + 0.5, step)

    # Output pixel → lon/lat (Mercator inverse), then → DEM indices.
    cols = np.arange(ow) / res + x0
    rows = np.arange(oh) / res + y0
    lon_o = lon_c + np.degrees((cols - W / 2) / scale)
    lat_o = np.degrees(2 * np.arctan(np.exp(m0 - (rows - H / 2) / scale)) - np.pi / 2)
    ci = (lon_o - lons[0]) / (lons[1] - lons[0])
    ri = (lat_o - lats[0]) / (lats[1] - lats[0])
    RI, CI = np.meshgrid(ri, ci, indexing='ij')
    filled = np.where(np.isnan(dem), 0, dem)
    z = ndimage.map_coordinates(filled, [RI, CI], order=1, mode='nearest').astype(np.float32)

    # Hillshade in projected pixel space: metres per output pixel varies with latitude.
    m_per_px = 6378137 / (scale * res) * np.cos(np.radians(lat_o))[:, None]
    zs = ndimage.gaussian_filter(z, style['smooth'] * res) if style.get('smooth') else z
    zz = zs * style['exaggeration']
    gy, gx = np.gradient(zz)
    gx /= m_per_px
    gy /= m_per_px
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    shade = np.zeros_like(z)
    for az, alt, w in ((315, 45, 0.55), (270, 40, 0.2), (360, 40, 0.15), (225, 55, 0.1)):
        a, e = math.radians(az), math.radians(alt)
        shade += w * (np.sin(e) * np.cos(slope) + np.cos(e) * np.sin(slope) * np.cos(a - aspect))
    shade = np.clip(shade, 0, 1)
    flat = math.sin(math.radians(45))
    rel = np.clip((shade - flat) * style['relief_strength'] + 1.0, style.get('shade_floor', 0.3), 1.12)  # 1.0 on flat ground
    # Local relief: valleys below their surroundings get a soft shadow, ridges a lift.
    local = zs - ndimage.gaussian_filter(z, 9 * res)
    rel *= np.clip(1 + style['valley_shadow'] * np.tanh(local / 400), 0.6, 1.15)
    if style.get('high_fade'):
        # plateaus and snow ranges (mostly outside the story's polities) shade loudest; soften them like printed atlases
        rel = 1 + (rel - 1) * (1 - style['high_fade'] * np.clip((z - 2500) / 2000, 0, 1))

    to_px = lambda lon, lat: ((wx(lon) - x0) * res, (wy(lat) - y0) * res)
    bbox = (lon_w, lat_s, lon_e, lat_n)
    land = np.asarray(rasterize(NE / 'ne_10m_land' / 'ne_10m_land.shp', to_px, (ow, oh), bbox), np.float32) / 255
    lakes = np.asarray(rasterize(NE / 'ne_10m_lakes' / 'ne_10m_lakes.shp', to_px, (ow, oh), bbox), np.float32) / 255
    land = np.asarray(Image.fromarray((land * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255

    # Land colour: grey base, high ground slightly lighter, modulated by relief.
    hi = np.clip(z / 4500, 0, 1)[..., None]
    base = np.array(style['land'], np.float32) * (1 - hi) + np.array(style['high'], np.float32) * hi
    land_rgb = np.clip(base * rel[..., None], 0, 255)

    # Sea: deepen with depth, soft glow along coasts.
    depth = np.clip(-z / 3000, 0, 1)[..., None]
    sea = np.array(style['sea_shallow'], np.float32) * (1 - depth) + np.array(style['sea_deep'], np.float32) * depth
    glow = ndimage.gaussian_filter(land, 6 * res)[..., None] * (1 - land[..., None])
    sea = sea * (1 - 0.55 * glow) + np.array(style['coast_glow'], np.float32) * 0.55 * glow

    img = land_rgb * land[..., None] + sea * (1 - land[..., None])
    lake_rgb = np.array(style['lake'], np.float32)
    img = img * (1 - lakes[..., None]) + lake_rgb * lakes[..., None]
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    CACHE.mkdir(exist_ok=True)
    out.save(cached, quality=93)
    info = {'source': 'NOAA ETOPO 2022 15s surface (public domain) + Natural Earth 10m land/lakes (public domain)', 'dem_step': step,
            'missing_dem_fraction': round(float(np.isnan(dem).mean()), 4)}
    cached.with_suffix('.json').write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
    return out, {**meta, **info}


def river_overlay(center, scale, extent, res=1.0) -> Image.Image:
    """Transparent layer of pale river bands (atlas look), drawn over the polity colours so rivers stay light."""
    lon_c, lat_c = center
    merc = lambda lat: math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    m0 = merc(lat_c)
    lon_w, lat_s, lon_e, lat_n = extent
    wx = lambda lon: W / 2 + math.radians(lon - lon_c) * scale
    wy = lambda lat: H / 2 - scale * (merc(lat) - m0)
    x0, y0 = wx(lon_w), wy(lat_n)
    ow, oh = int((wx(lon_e) - x0) * res), int((wy(lat_s) - y0) * res)
    key = hashlib.sha256(json.dumps([center, scale, extent, res, RIVER_BANDS, 'rivers-v2']).encode()).hexdigest()[:16]
    cached = CACHE / f'rivers-{key}.png'
    if cached.exists():
        return Image.open(cached)
    rim = Image.new('L', (ow, oh), 0)
    core = Image.new('L', (ow, oh), 0)
    dr, dc = ImageDraw.Draw(rim), ImageDraw.Draw(core)
    r = shapefile.Reader(str(NE / 'ne_10m_rivers_lake_centerlines' / 'ne_10m_rivers_lake_centerlines.shp'), encoding='utf-8')
    k = res * scale / 3500        # band width follows the map scale (3500 = whole-China view)
    for sr in r.iterShapeRecords():
        rank = sr.record.as_dict().get('scalerank') or 99
        if rank not in RIVER_BANDS:
            continue
        bx0, by0, bx1, by1 = sr.shape.bbox
        if bx1 < lon_w or bx0 > lon_e or by1 < lat_s or by0 > lat_n:
            continue
        w = max(2.0, RIVER_BANDS[rank] * k)
        pts, parts = sr.shape.points, list(sr.shape.parts) + [len(sr.shape.points)]
        for a, b in zip(parts, parts[1:]):
            line = [((wx(x) - x0) * res, (wy(y) - y0) * res) for x, y in pts[a:b]]
            if len(line) > 1:
                dr.line(line, fill=255, width=int(round(w + 3 * res)), joint='curve')
                dc.line(line, fill=255, width=int(round(w)), joint='curve')
    rim = rim.filter(ImageFilter.GaussianBlur(0.8 * res))
    core = core.filter(ImageFilter.GaussianBlur(0.6 * res))
    out = np.zeros((oh, ow, 4), np.uint8)
    rm, cm = np.asarray(rim, np.float32) / 255, np.asarray(core, np.float32) / 255
    col = np.array([92, 98, 96], np.float32) * (1 - cm[..., None]) + np.array([214, 218, 212], np.float32) * cm[..., None]
    out[..., :3] = col.astype(np.uint8)
    out[..., 3] = (np.maximum(rm * 0.55, cm * 0.92) * 255).astype(np.uint8)
    img = Image.fromarray(out, 'RGBA')
    CACHE.mkdir(exist_ok=True)
    img.save(cached)
    return img
