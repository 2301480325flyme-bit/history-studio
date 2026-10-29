"""Review sheet for one built episode: a keyframe per beat + every line the user should listen to first.

usage: python history-studio/review.py projects/<id>/episode.yaml [--build B2026…]

Output in <build>/审片单/:
  审片单-1.jpg, 审片单-2.jpg …   contact sheets, 12 beats per page (frame at the middle of each beat's voice)
  审片单.md                      flagged beats with times: misheard words, rushed or dragging lines, long beats
The idea: glance at the sheets for picture problems, then listen only to the flagged times.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / '01_工作流'
STUDIO = ROOT / '05_项目' / 'Remotion' / 'studio'
REMOTION = WF / 'remotion-shuihong'
PER_PAGE, COLS, TW, TH = 12, 3, 640, 360


def latest_build(pid: str) -> Path:
    builds = sorted((p for p in (STUDIO / pid).iterdir() if (p / 'public' / 'episode.json').exists()), key=lambda p: p.stat().st_mtime)
    return builds[-1]


def mmss(t: float) -> str:
    return f'{int(t // 60)}:{int(t % 60):02d}'


def hanzi(s: str) -> int:
    return len(re.sub(r'[\W_]', '', s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script', type=Path)
    ap.add_argument('--build')
    a = ap.parse_args()
    script = a.script.resolve()
    y = yaml.safe_load(script.read_text(encoding='utf-8'))
    pid = y['id']
    build = STUDIO / pid / a.build if a.build else latest_build(pid)
    pub = build / 'public'
    ep = json.loads((pub / 'episode.json').read_text(encoding='utf-8'))
    timing_f = script.parent / 'voice' / 'timing.json'
    timing = json.loads(timing_f.read_text(encoding='utf-8')) if timing_f.exists() else {}
    out = build / '审片单'; out.mkdir(exist_ok=True)

    beats, segs = y['beats'], ep['segments']
    mids = [round((g['voice_onset'] + g['voice_offset']) / 2 * ep['fps']) for g in segs]
    shots = out / '_frames'
    todo = [m for m in mids if not (shots / f'f{m}.jpg').exists()]
    if todo:
        subprocess.run(['node', 'scripts/stills.mjs', str(pub), str(shots), ','.join(map(str, todo)), '--scale=0.3333'], cwd=REMOTION, check=True)

    # flags per beat
    flags: dict[int, list[str]] = {}
    add = lambda i, s: flags.setdefault(i, []).append(s)
    for r in timing.get('asr', []):
        if r.get('unchecked'):
            add(r['beat'] - 1, '读音未能自动核对（识别服务拒绝），请人工听')
        if r.get('ratio', 1) < 0.9 and r.get('diff'):
            add(r['beat'] - 1, f"读音存疑（识别 {r['ratio']:.2f}）：{'；'.join(r['diff'][:4])}")
    for r in timing.get('speaker_pace', []):
        if r['speed'] >= 1.3:
            add(r['beat'] - 1, f"{r['speaker']} 台词被提速到 {r['speed']}×（原 {r['rate_before']} 字/秒），听是否太赶")
    for i, (b, g) in enumerate(zip(beats, segs)):
        dur = g['voice_offset'] - g['voice_onset']
        n = hanzi(b['say'])
        if b.get('speaker'):
            continue
        if dur > 1 and n / dur < 3.6:
            add(i, f'旁白偏慢 {n / dur:.1f} 字/秒')
        if n > 40:
            add(i, f'旁白一拍 {n} 字，偏长')

    # contact sheets
    try:
        f_big = ImageFont.truetype(str(pub / 'fonts' / 'Sans.ttf'), 22)
        f_small = ImageFont.truetype(str(pub / 'fonts' / 'Sans.ttf'), 18)
    except OSError:
        f_big = f_small = ImageFont.load_default()
    pages = []
    for p0 in range(0, len(segs), PER_PAGE):
        idx = list(range(p0, min(len(segs), p0 + PER_PAGE)))
        rows = (len(idx) + COLS - 1) // COLS
        sheet = Image.new('RGB', (COLS * (TW + 16) + 16, rows * (TH + 96) + 16), (236, 232, 224))
        d = ImageDraw.Draw(sheet)
        for k, i in enumerate(idx):
            x, yy = 16 + (k % COLS) * (TW + 16), 16 + (k // COLS) * (TH + 96)
            f = shots / f'f{mids[i]}.jpg'
            if f.exists():
                sheet.paste(Image.open(f).convert('RGB').resize((TW, TH)), (x, yy))
            red = i in flags
            if red:
                d.rectangle((x - 4, yy - 4, x + TW + 3, yy + TH + 3), outline=(190, 40, 30), width=5)
            b = beats[i]
            head = f"#{i + 1}  {mmss(segs[i]['voice_onset'])}" + (f"  {b['phase']}" if b.get('phase') else '') + (f"  【{b['speaker']}】" if b.get('speaker') else '')
            d.text((x, yy + TH + 6), head, font=f_big, fill=(150, 30, 20) if red else (40, 30, 20))
            say = b['say'] if len(b['say']) <= 34 else b['say'][:33] + '…'
            d.text((x, yy + TH + 36), say, font=f_small, fill=(60, 50, 40))
            if red:
                d.text((x, yy + TH + 62), '▲ ' + flags[i][0][:34], font=f_small, fill=(170, 40, 30))
        name = f'审片单-{len(pages) + 1}.jpg'
        sheet.save(out / name, quality=86)
        pages.append(name)

    lines = [f'# 审片单 · {y.get("title", pid)}', '', f'构建 `{build.name}`，时长 {mmss(ep["duration"])}，{len(segs)} 拍。', '',
             '先扫一遍缩略图（' + '、'.join(f'`{p}`' for p in pages) + '），红框是需要听的拍；再按下表跳到时间点听。', '']
    if flags:
        lines += ['| 拍 | 时间 | 内容 | 要听什么 |', '|---|---|---|---|']
        for i in sorted(flags):
            b = beats[i]
            who = f"【{b['speaker']}】" if b.get('speaker') else ''
            lines.append(f"| {i + 1} | {mmss(segs[i]['voice_onset'])} | {who}{b['say'][:24]}{'…' if len(b['say']) > 24 else ''} | {'；'.join(flags[i])} |")
    else:
        lines.append('没有自动标记的问题。仍需通听一遍，读音、节奏和观感由你判断。')
    # map consistency (series timeline): banners on the wrong ground, openings that don't match the last episode
    try:
        import consistency
        jun, zhou = consistency.load_cells()
        reg = __import__('studio').Registry()
        series = sorted(script.parent.parent.glob(re.sub(r'\d+-.*$', '', pid) + '*/episode.yaml'))
        prev, mine = None, []
        for sp in series:
            probs, prev = consistency.check(sp, reg, jun, zhou, prev)
            if sp.resolve() == script:
                mine = probs
                break
        lines += ['', '## 地图一致性', '']
        tl = __import__('yaml').safe_load((script.parent.parent.parent / 'series' / '三国到隋' / '疆域.yaml').read_text(encoding='utf-8'))
        mine += consistency.enclaves(tl, jun, zhou, consistency.adjacency())   # series-wide: should always be empty
        lines += [f'- {x}' for x in mine] if mine else ['没有发现旗牌落在别人地盘、飞地、或开场地图和上一集结尾对不上的问题。']
    except Exception as e:   # the check must never stop a review sheet
        lines += ['', f'（地图一致性检查失败：{e}）']
    lines += ['', '## 人物台词（全部建议听一遍）', '']
    for i, b in enumerate(beats):
        if b.get('speaker'):
            lines.append(f"- {mmss(segs[i]['voice_onset'])}　【{b['speaker']}】「{b['say']}」")
    (out / '审片单.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'review sheet → {out}  ({len(pages)} pages, {len(flags)} flagged beats)')


if __name__ == '__main__':
    main()
