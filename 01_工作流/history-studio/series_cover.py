"""Series (合集) cover for 《三国到隋》: three leading figures over a wide territory map, big brush title.

usage: python history-studio/series_cover.py <map-background.png> [--out 03_素材/封面/合集]
Writes 合集封面-16x9.jpg (B站), 合集封面-4x3.jpg / 合集封面-3x4.jpg (抖音), 合集封面-1x1.jpg (合集方图).
The background is a map-only still (stills.mjs --map-only), ideally zoomed out to show the whole of China.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from publish import Cover, background  # noqa: E402

TITLE = '三国到隋'
SUB = '一张地图 · 讲透四百年分合'
TAG = '第一季 · 汉末群雄（184–208）'
HEROES = ['cao_cao', 'liu_bei', 'sun_quan']   # middle, left, right
FONTS = HERE / 'assets' / 'fonts'


def heroes():
    return [Image.open(ROOT / '03_素材' / '人物立绘' / f'{n}.png').convert('RGBA') for n in HERO_ORDER]


HERO_ORDER = ['liu_bei', 'cao_cao', 'sun_quan']


def place(im, p, h, cx, top, flip=False, dim=1.0):
    p = p.resize((int(p.width * h / p.height), h), Image.LANCZOS)
    if flip:
        p = p.transpose(Image.FLIP_LEFT_RIGHT)
    if dim < 1:
        r, g, b, a = p.split()
        p = Image.merge('RGBA', (r.point(lambda v: int(v * dim)), g.point(lambda v: int(v * dim)), b.point(lambda v: int(v * dim)), a))
    from PIL import ImageFilter
    sh = Image.new('RGBA', p.size, (0, 0, 0, 0)); sh.putalpha(p.getchannel('A').point(lambda v: int(v * 0.6)))
    x = int(cx - p.width / 2)
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)), (x + 10, top + 14))
    im.alpha_composite(p, (x, top))


def make(bg, w, h, cv: Cover):
    im = background(bg, w, h)
    s = min(w / 1920, h / 1080) if w >= h else w / 1080
    hs = heroes()
    tall = h > w
    # three figures: 曹操 centre and largest, 刘备 left, 孙权 right (mirrored to face inward)
    if tall:
        base = int(h * 0.50)
        place(im, hs[0], int(base * 0.86), int(w * 0.20), int(h * 0.50), dim=0.82)
        place(im, hs[2], int(base * 0.86), int(w * 0.80), int(h * 0.50), flip=True, dim=0.82)
        place(im, hs[1], base, int(w * 0.50), int(h * 0.45))
    else:
        base = int(h * 0.80)
        base = int(h * 0.72)
        place(im, hs[0], int(base * 0.9), int(w * 0.20), int(h * 0.30), dim=0.82)
        place(im, hs[2], int(base * 0.9), int(w * 0.80), int(h * 0.30), flip=True, dim=0.82)
        place(im, hs[1], base, int(w * 0.50), int(h * 0.30))
    # dark band at the bottom for the subtitle
    d = ImageDraw.Draw(im)
    band = int(h * (0.86 if tall else 0.82))
    d.rectangle((0, band, w, h), fill=(18, 12, 8, 215))
    ty = int(h * (0.19 if tall else 0.15))
    cv._glow(im, (w // 2, ty), TITLE, cv._fit(TITLE, int((230 if tall else 190) * (w / 1080 if tall else h / 1080)), w * 0.9))
    fs = int((48 if tall else 50) * (w / 1080 if tall else h / 1080))
    cv._text(im, (w // 2, int(band + (h - band) * 0.36)), SUB, cv._fit_serif(SUB, fs, w * 0.9), (250, 240, 220), font=cv.serif, stroke=3)
    cv._text(im, (w // 2, int(band + (h - band) * 0.74)), TAG, int(fs * 0.72), (240, 200, 120), font=cv.serif)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bg', type=Path)
    ap.add_argument('--out', type=Path, default=ROOT / '03_素材' / '封面' / '合集')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    bg = Image.open(a.bg)
    cv = Cover(bg, None, [TITLE], SUB, TAG, str(FONTS / 'Brush.ttf'), str(FONTS / 'Serif.ttf'))
    for name, (w, h) in {'16x9': (1920, 1080), '4x3': (1440, 1080), '3x4': (1080, 1440), '1x1': (1080, 1080)}.items():
        make(bg, w, h, cv).convert('RGB').save(a.out / f'合集封面-{name}.jpg', quality=94)
    print('series cover →', a.out)


if __name__ == '__main__':
    main()
