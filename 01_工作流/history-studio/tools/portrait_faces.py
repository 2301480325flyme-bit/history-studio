"""Face comparison sheet for portraits (立绘撞脸检查, 2026-10-23).

Crops the head of each portrait (the top quarter of the figure) and lays them out side by side with their ids,
so a new portrait can be compared, face to face, with the ones it is most likely to be confused with.

    python tools/portrait_faces.py --new yuan_tan yuan_shang --near yuan_shao yuan_shu   # a batch vs. its look-alikes
    python tools/portrait_faces.py --episode 18                                          # everyone in one episode
    python tools/portrait_faces.py --all                                                 # the whole library

New portraits get a red label. The sheet goes to 03_素材/人物立绘/对照/ (path printed at the end).
"""
import argparse
import datetime
import glob
import os
import re

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
LIB = os.path.join(ROOT, '03_素材', '人物立绘')
TILE, CAP = 180, 26

# Face-only comparison windows; the oval mask removes headwear, props and shoulder armor.
# Coordinates are normalized to the full 1024x1536 portrait canvas: left, top, right, bottom,
# and optional absolute y-coordinate at which headwear is masked out of the crop.
# Add a calibrated window when adding a newly reviewed portrait; unmatched files retain the
# legacy alpha-bounds crop so the tool still works across the full library.
FACE_ROIS = {
    'cao_cao': (0.40, 0.08, 0.71, 0.31, 0.17),
    'liu_bei': (0.40, 0.08, 0.71, 0.31, None),
    'guan_yu': (0.43, 0.08, 0.74, 0.31, 0.18),
    'zhuge_liang': (0.43, 0.09, 0.74, 0.32, 0.17),
    'huang_zhong': (0.45, 0.13, 0.76, 0.36, 0.20),
    'xiahou_yuan': (0.435, 0.18, 0.68, 0.344),
    'zhang_he': (0.45, 0.09, 0.76, 0.30, 0.16),
    'fa_zheng': (0.45, 0.09, 0.76, 0.30, 0.17),
    'guo_huai': (0.45, 0.10, 0.76, 0.31, 0.18),
    'yang_xiu': (0.40, 0.08, 0.71, 0.31, None),
    'li_dian': (0.45, 0.11, 0.74, 0.31, None),
    'xu_huang': (0.47, 0.12, 0.74, 0.31, 0.20),
    'cao_pi': (0.43, 0.10, 0.74, 0.31, 0.18),
    'li_sheng': (0.41, 0.07, 0.71, 0.28, None),
    'ding_yuan': (0.45, 0.17, 0.75, 0.34, None),
    'cao_ren': (0.45, 0.13, 0.74, 0.31, 0.18),
}
FACE_OVALS = {
    # Ellipses are relative to the face crop and remove headwear, props and shoulder armor.
    'cao_cao': (0.06, 0.20, 0.94, 0.98),
    'liu_bei': (0.04, 0.04, 0.96, 0.98),
    'guan_yu': (0.04, 0.24, 0.96, 0.98),
    'zhuge_liang': (0.04, 0.14, 0.96, 0.98),
    'huang_zhong': (0.05, 0.22, 0.95, 0.98),
    'xiahou_yuan': (0.03, 0.10, 0.97, 0.98),
    'zhang_he': (0.05, 0.24, 0.95, 0.98),
    'fa_zheng': (0.05, 0.30, 0.95, 0.98),
    'guo_huai': (0.05, 0.24, 0.95, 0.98),
    'yang_xiu': (0.04, 0.04, 0.96, 0.98),
    'li_dian': (0.04, 0.04, 0.96, 0.98),
    'xu_huang': (0.05, 0.20, 0.95, 0.98),
    'cao_pi': (0.05, 0.18, 0.95, 0.98),
    'li_sheng': (0.04, 0.04, 0.96, 0.98),
    'ding_yuan': (0.04, 0.06, 0.96, 0.98),
    'cao_ren': (0.05, 0.18, 0.95, 0.98),
}


def head(path, portrait_id):
    im = Image.open(path).convert('RGBA')
    if portrait_id in FACE_ROIS:
        roi = FACE_ROIS[portrait_id]
        left, top, right, bottom = roi[:4]
        box = (int(im.width * left), int(im.height * top),
               int(im.width * right), int(im.height * bottom))
        crop = im.crop(box)
        oval = FACE_OVALS.get(portrait_id, (0.04, 0.08, 0.96, 0.98))
        mask = Image.new('L', crop.size, 0)
        ImageDraw.Draw(mask).ellipse((int(crop.width * oval[0]), int(crop.height * oval[1]),
                                      int(crop.width * oval[2]), int(crop.height * oval[3])), fill=255)
        # keep the portrait's own transparency: replacing it shows the black RGB of empty pixels
        crop.putalpha(ImageChops.multiply(crop.getchannel('A'), mask))
        bg = Image.new('RGB', crop.size, (230, 226, 214))
        bg.paste(crop, (0, 0), crop)
        bg = bg.resize((TILE, TILE))
        return bg
    x0, y0, x1, y1 = im.getchannel('A').getbbox() or (0, 0, im.width, im.height)
    # skip most of a tall cap or helmet and keep the whole face down to the chin
    top = y0 + int((y1 - y0) * 0.07)
    h = int((y1 - y0) * 0.30)
    cx = (x0 + x1) // 2
    box = (max(0, cx - h // 2), top, min(im.width, cx + h // 2), min(im.height, top + h))
    bg = Image.new('RGB', (box[2] - box[0], box[3] - box[1]), (230, 226, 214))
    crop = im.crop(box)
    bg.paste(crop, (0, 0), crop)
    return bg.resize((TILE, TILE))


def episode_ids(n):
    """Portrait ids of everyone in an episode's people table."""
    p = glob.glob(os.path.join(ROOT, '01_工作流', 'projects', f's01e{n:02d}-*', 'episode.yaml'))
    if not p:
        raise SystemExit(f'episode {n} not found')
    text = open(p[0], encoding='utf-8').read()
    return sorted(set(re.findall(r'人物立绘/([a-z0-9_]+)\.png', text)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--new', nargs='*', default=[], help='ids of the new portraits (red labels)')
    ap.add_argument('--near', nargs='*', default=[], help='ids of the portraits they must not look like')
    ap.add_argument('--episode', type=int, help='everyone in this episode')
    ap.add_argument('--all', action='store_true', help='the whole library')
    ap.add_argument('--out', help='output jpg')
    a = ap.parse_args()
    ids = list(a.new) + list(a.near)
    if a.episode:
        ids += episode_ids(a.episode)
    if a.all:
        ids += [os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(LIB, '*.png'))
                if not re.search(r'-v\d+$', os.path.splitext(f)[0])]
    seen, order = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            order.append(i)
    if not order:
        raise SystemExit('nothing to compare: give --new/--near, --episode or --all')
    font = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 17)
    cols = min(10, len(order))
    sheet = Image.new('RGB', (TILE * cols, (TILE + CAP) * ((len(order) + cols - 1) // cols)), (200, 196, 186))
    missing = []
    for k, i in enumerate(order):
        p = os.path.join(LIB, i + '.png')
        if not os.path.exists(p):
            missing.append(i)
            continue
        t = Image.new('RGB', (TILE, TILE + CAP), (230, 226, 214))
        t.paste(head(p, i), (0, 0))
        ImageDraw.Draw(t).text((5, TILE + 3), i, fill=(190, 30, 30) if i in a.new else (20, 20, 20), font=font)
        sheet.paste(t, ((k % cols) * TILE, (k // cols) * (TILE + CAP)))
    out = a.out or os.path.join(LIB, '对照', f'脸部对照-{datetime.datetime.now():%Y%m%d-%H%M}.jpg')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out, quality=88)
    print(out)
    if missing:
        print('no portrait for:', ' '.join(missing))


if __name__ == '__main__':
    main()
