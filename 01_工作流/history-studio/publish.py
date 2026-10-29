"""Publish pack for one built episode: covers (16:9 B站, 4:3 + 3:4 抖音), 发布信息.md, captions .srt.

usage: python history-studio/publish.py projects/<id>/episode.yaml [--build B2026…] [--at SECONDS]

Reads the optional `publish:` block of episode.yaml:

    publish:
      hook: 一个道士，如何喊垮四百年大汉？      # cover line + 抖音 title
      big: [苍天已死, 黄天当立]                # 1–2 brush lines on the cover (≤5 字 each)
      hero: 张角                               # person whose portrait stands on the cover
      at: 100.5                                # second whose map (territory) is the cover background
      summary: |                               # 2–4 sentences for the description
        …
      tags: [黄巾起义, 张角, 汉灵帝]           # topic tags besides the series defaults
      next: 何进召董卓                         # next episode, for the last line

Everything has a fallback, so a pack can be made before the block is written; the sheet says what was guessed.
Output: <build>/发布/ — tied to the exact build that was rendered (chapter times match it).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / '01_工作流'
STUDIO = ROOT / '05_项目' / 'Remotion' / 'studio'
REMOTION = WF / 'remotion-shuihong'
SERIES = '三国到隋'
BASE_TAGS = ['历史', '三国', '东汉', '人文历史', '历史地图', SERIES]
CN = '零一二三四五六七八九十'


def latest_build(pid: str) -> Path:
    builds = sorted((p for p in (STUDIO / pid).iterdir() if (p / 'public' / 'episode.json').exists()), key=lambda p: p.stat().st_mtime)
    if not builds:
        sys.exit(f'no build for {pid}; run studio.py build first')
    return builds[-1]


def ts(sec: float, srt: bool = False) -> str:
    h, m, s = int(sec // 3600), int(sec % 3600 // 60), sec % 60
    if srt:
        return f'{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}'
    return f'{m}:{int(s):02d}' if not h else f'{h}:{m:02d}:{int(s):02d}'


def lines_of(ep: dict) -> list[tuple[float, float, str, str | None]]:
    out = []
    for g in ep['segments']:
        for c in g.get('captions') or []:
            out.append((c['t0'], c['t1'], c['text'], g.get('speaker')))
        if not g.get('captions') and g.get('caption'):
            out.append((g['voice_onset'], g['voice_offset'], g['caption'], g.get('speaker')))
    return out


# ---------- covers ----------
def fonts(pub: Path) -> tuple[str, str]:
    return str(pub / 'fonts' / 'Brush.ttf'), str(pub / 'fonts' / 'Serif.ttf')


def background(src: Image.Image, w: int, h: int) -> Image.Image:
    m = src.convert('RGB'); k = max(w / m.width, h / m.height) * 1.08
    m = m.resize((int(m.width * k), int(m.height * k)), Image.LANCZOS)
    x0 = (m.width - w) // 2 + int(w * 0.05); y0 = (m.height - h) // 2
    m = m.crop((x0, y0, x0 + w, y0 + h)).filter(ImageFilter.GaussianBlur(2.5))
    m = ImageEnhance.Brightness(m).enhance(0.62)
    a = np.array(m).astype(float); yy, xx = np.mgrid[0:h, 0:w]
    v = 1 - 0.45 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / 2
    return Image.fromarray(np.clip(a * v[..., None], 0, 255).astype('uint8')).convert('RGBA')


class Cover:
    def __init__(self, bg_src: Image.Image, hero: Image.Image | None, big: list[str], hook: str, badge: str, brush: str, serif: str):
        self.src, self.hero, self.big, self.hook, self.badge, self.brush, self.serif = bg_src, hero, big, hook, badge, brush, serif

    def _text(self, im, xy, s, size, fill, font=None, stroke=0, sfill=(20, 12, 6)):
        ImageDraw.Draw(im).text(xy, s, font=ImageFont.truetype(font or self.brush, size), fill=fill, anchor='mm', stroke_width=stroke, stroke_fill=sfill)

    def _glow(self, im, xy, s, size):
        L = Image.new('RGBA', im.size); self._text(L, xy, s, size, (255, 170, 60, 255), stroke=10, sfill=(255, 140, 40))
        im.alpha_composite(L.filter(ImageFilter.GaussianBlur(18)))
        self._text(im, xy, s, size, (255, 236, 168), stroke=6)

    def _fit(self, s: str, size: int, maxw: float) -> int:
        f = ImageFont.truetype(self.brush, size)
        w = ImageDraw.Draw(Image.new('L', (1, 1))).textlength(s, font=f)
        return int(size * min(1, maxw / max(1, w)))

    def _hero(self, im, h, x, y):
        if not self.hero:
            return
        p = self.hero.resize((int(self.hero.width * h / self.hero.height), h), Image.LANCZOS)
        sh = Image.new('RGBA', p.size, (0, 0, 0, 0)); sh.putalpha(p.getchannel('A').point(lambda v: int(v * 0.6)))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(20)), (x + 12, y + 16)); im.alpha_composite(p, (x, y))

    def _badge(self, im, x, y, size):
        d = ImageDraw.Draw(im); f = ImageFont.truetype(self.serif, size)
        w = d.textlength(self.badge, font=f) + size * 1.2
        d.rectangle((x, y, x + w, y + size * 1.7), fill=(150, 34, 24, 235))
        d.text((x + w / 2, y + size * 0.85), self.badge, font=f, fill=(250, 238, 212), anchor='mm')

    def landscape(self, w: int, h: int) -> Image.Image:
        im = background(self.src, w, h); s = h / 1080; narrow = w / h < 1.5
        self._hero(im, int(h * 1.02), int(w - h * (0.70 if narrow else 0.78)), int(h * 0.02))
        cx = int(w * (0.33 if narrow else 0.36)); maxw = w * (0.56 if narrow else 0.6)
        ys = [0.34, 0.56] if len(self.big) > 1 else [0.45]
        for line, y in zip(self.big, ys):
            self._glow(im, (cx, int(h * y)), line, self._fit(line, int((170 if narrow else 200) * s), maxw))
        self._text(im, (cx, int(h * 0.76)), self.hook, self._fit_serif(self.hook, int((46 if narrow else 56) * s), maxw), (250, 240, 220), font=self.serif, stroke=4)
        self._badge(im, int(w * 0.05), int(h * 0.06), int(40 * s))
        return im

    def portrait(self, w: int, h: int) -> Image.Image:
        im = background(self.src, w, h); s = w / 1080
        if self.hero:
            hh = int(h * 0.66); self._hero(im, hh, int(w / 2 - hh * self.hero.width / self.hero.height / 2), int(h * 0.36))
        ys = [0.14, 0.27] if len(self.big) > 1 else [0.2]
        for line, y in zip(self.big, ys):
            self._glow(im, (w // 2, int(h * y)), line, self._fit(line, int(190 * s), w * 0.88))
        d = ImageDraw.Draw(im); d.rectangle((0, int(h * 0.86), w, h), fill=(20, 14, 10, 200))
        self._text(im, (w // 2, int(h * 0.905)), self.hook, self._fit_serif(self.hook, int(52 * s), w * 0.9), (250, 240, 220), font=self.serif, stroke=3)
        self._text(im, (w // 2, int(h * 0.955)), self.badge, int(40 * s), (240, 200, 120), font=self.serif)
        return im

    def _fit_serif(self, s: str, size: int, maxw: float) -> int:
        f = ImageFont.truetype(self.serif, size)
        w = ImageDraw.Draw(Image.new('L', (1, 1))).textlength(s, font=f)
        return int(size * min(1, maxw / max(1, w)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script', type=Path)
    ap.add_argument('--build')
    ap.add_argument('--at', type=float, help='cover background second (overrides publish.at)')
    a = ap.parse_args()
    script = a.script.resolve()
    y = yaml.safe_load(script.read_text(encoding='utf-8'))
    pid = y['id']; pub_cfg = y.get('publish') or {}
    build = STUDIO / pid / a.build if a.build else latest_build(pid)
    pub = build / 'public'
    ep = json.loads((pub / 'episode.json').read_text(encoding='utf-8'))
    out = build / '发布'; out.mkdir(exist_ok=True)
    guessed = []

    m = re.search(r'第\s*(\d+)\s*集', str(y.get('series', '')))
    num = int(m.group(1)) if m else 0
    title = y.get('title', pid)
    badge = f'{SERIES} · 第{num}集　{title}'

    # chapters: first beat of each phase
    chapters = []
    for b, g in zip(y['beats'], ep['segments']):
        if b.get('phase'):
            chapters.append((0.0 if not chapters else max(0.0, g['voice_onset'] - 0.5), b['phase']))
    # finer platform chapters without touching the on-screen phases: publish.chapters: [{beat: 10, title: 酸枣会盟}, …]
    if pub_cfg.get('chapters'):
        chapters = [(0.0 if c['beat'] == 1 else max(0.0, ep['segments'][c['beat'] - 1]['voice_onset'] - 0.5), c['title']) for c in pub_cfg['chapters']]

    # cover inputs
    people = y.get('people') or {}
    speakers = [b['speaker'] for b in y['beats'] if b.get('speaker')]
    hero_name = pub_cfg.get('hero') or (speakers[0] if speakers else next(iter(people), None))
    if not pub_cfg.get('hero'):
        guessed.append(f'封面人物 → {hero_name}（第一个亲口说话的人物）')
    hero_img = None
    if hero_name and (people.get(hero_name) or {}).get('image'):
        hero_img = Image.open(ROOT / people[hero_name]['image']).convert('RGBA')
    big = pub_cfg.get('big')
    if not big:
        quote = next((b['say'] for b in y['beats'] if b.get('speaker')), title)
        parts = [p for p in re.split(r'[，。！？、；：]', quote) if p][:2]
        big = parts if all(len(p) <= 6 for p in parts) else [title]
        guessed.append(f'封面大字 → {"／".join(big)}')
    hook = pub_cfg.get('hook') or y['beats'][0]['say'].rstrip('。')
    if not pub_cfg.get('hook'):
        guessed.append('钩子 → 第一句旁白')
    at = a.at if a.at is not None else pub_cfg.get('at')
    if at is None:
        # the moment the map is busiest: most territory-changing elements alive
        at = max((g['voice_offset'] for g in ep['segments']), key=lambda t: sum(1 for e in ep['elements'] if e.get('start', 0) <= t <= e.get('end', 0))) if ep['segments'] else 1.0
        guessed.append(f'封面底图 → 第 {at:.1f} 秒的地图')
    frame = int(round(float(at) * ep['fps']))
    stills = out / '_bg'
    subprocess.run(['node', 'scripts/stills.mjs', str(pub), str(stills), str(frame), '--map-only', '--scale=1', '--png'], cwd=REMOTION, check=True, shell=False)
    bg_src = Image.open(stills / f'f{frame}.png')
    brush, serif = fonts(pub)
    cv = Cover(bg_src, hero_img, big, hook, badge, brush, serif)
    cv.landscape(1920, 1080).convert('RGB').save(out / '封面-16x9-B站.jpg', quality=94)
    cv.landscape(1440, 1080).convert('RGB').save(out / '封面-4x3-抖音横.jpg', quality=94)
    cv.portrait(1080, 1440).convert('RGB').save(out / '封面-3x4-抖音竖.jpg', quality=94)

    # captions
    srt = []
    for k, (t0, t1, text, spk) in enumerate(lines_of(ep), 1):
        srt += [str(k), f'{ts(t0, True)} --> {ts(t1, True)}', f'{spk}：「{text}」' if spk else text, '']
    (out / f'{pid}.srt').write_text('\n'.join(srt), encoding='utf-8-sig')

    # sheet
    srcs = '、'.join(dict.fromkeys(f"{s['work']}·{s['volume'].split('·')[-1].split('（')[0]}" for s in y.get('sources_local') or []))
    summary = (pub_cfg.get('summary') or '').strip()
    if not summary:
        summary = ''.join(b['say'] for b in y['beats'][:3])
        guessed.append('简介 → 开头三句旁白（建议在 publish.summary 里写）')
    nxt = pub_cfg.get('next')
    tags = list(dict.fromkeys([*(pub_cfg.get('tags') or []), title, *BASE_TAGS]))[:10]
    chap = '\n'.join(f'{ts(t)} {n}' for t, n in chapters)
    note = '按正史讲述，人物台词据史书原话改写为白话；立绘、配音为 AI 生成，地图为示意。'
    credits = list(dict.fromkeys(m['credit'] for m in ep.get('music') or [] if m.get('credit')))
    music_line = ('\n【配乐】' + '；'.join(credits)) if credits else ''
    tail = f'《{SERIES}》第{num}集' + (f'，下集：{nxt}' + ('' if str(nxt)[-1:] in '。？！?!…' else '。') if nxt else '。')
    bili_title = f'【{SERIES}{num:02d}】{hook}｜{title}'
    dy_title = f'{hook}｜{title}'
    sheet = f"""# 发布信息 · {SERIES} 第{num}集《{title}》

构建：`{build.name}`（章节时间按这一版；上传的必须是这一版渲染的成片）
时长：{ts(ep['duration'])}

## 共用
- 封面：`封面-16x9-B站.jpg`（B 站）、`封面-4x3-抖音横.jpg` + `封面-3x4-抖音竖.jpg`（抖音横竖各一）
- 字幕文件：`{pid}.srt`（画面里已压字幕；平台要外挂字幕时用）
- **声明：必须勾选"含 AI 生成内容 / 内容由 AI 生成"**（立绘、配音为 AI）。能多选时加"含演绎内容"。
- 合集：《{SERIES}》

## B 站
- 标题（{len(bili_title)}/80）：`{bili_title}`
- 分区：知识 → 人文历史
- 标签：{'、'.join(tags)}
- 简介：

```
{summary}

【史料】{srcs}
【说明】{note}{music_line}
【系列】{tail}
```

## 抖音
- 作品标题（{len(dy_title)}/30）：`{dy_title}`{'  ⚠ 超过 30 字，请删减' if len(dy_title) > 30 else ''}
- 简介 + 话题：

```
{summary}
{note}{music_line}
{tail}
{' '.join('#' + t for t in tags[:8])}
```

## 视频章节（两个平台都可填）

```
{chap}
```
"""
    if guessed:
        sheet += '\n## 自动推断（建议在 episode.yaml 的 publish: 里写定）\n' + '\n'.join(f'- {g}' for g in guessed) + '\n'
    (out / '发布信息.md').write_text(sheet, encoding='utf-8')
    # the same, structured, for the web Studio's 发布 page (copy buttons, no need to ask anyone at upload time)
    bili_desc = f'{summary}\n\n【史料】{srcs}\n【说明】{note}{music_line}\n【系列】{tail}'
    dy_desc = f'{summary}\n{note}{music_line}\n{tail}\n' + ' '.join('#' + t for t in tags[:8])
    info = {'series': SERIES, 'num': num, 'title': title, 'build': build.name, 'duration': ts(ep['duration']),
            'douyin': {'title': dy_title, 'title_len': len(dy_title), 'desc': dy_desc},
            'bili': {'title': bili_title, 'title_len': len(bili_title), 'zone': '知识 → 人文历史', 'tags': tags, 'desc': bili_desc},
            'chapters': chap,
            'checks': ['勾选「内容由 AI 生成 / 含 AI 生成内容」（立绘、配音为 AI）', '能多选时加「含演绎内容」', f'加入合集《{SERIES}》', f'上传的成片必须是 {build.name} 这一版（章节时间按它算）'],
            'covers': {k: v for k, v in (('16x9', '封面-16x9-B站.jpg'), ('4x3', '封面-4x3-抖音横.jpg'), ('3x4', '封面-3x4-抖音竖.jpg')) if (out / v).exists()},
            'srt': f'{pid}.srt', 'guessed': guessed}
    (out / '发布信息.json').write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'publish pack → {out}')
    for g in guessed:
        print('  guessed:', g)


if __name__ == '__main__':
    main()
