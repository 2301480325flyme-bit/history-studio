"""快节奏重写工具（2026-10-13）：从一集原稿里挑拍、改台词、并拍，生成快节奏版 episode.yaml。

    from fastcut import Episode
    ep = Episode('s01e05-changan')          # reads projects/<id>/episode.yaml (backed up once to episode.orig.yaml)
    ep.beat(3, '新台词', merge=[4], sets={'phase': '…'}, extra=['sfx: 低音转场'], no_show=False)
    ep.write(hook='…', big='[…]')

Each new beat copies an original beat (its camera, map, show items, sources…), replaces the line, and can pull in the
show items of other beats (`merge`). Cues that no longer occur in the new line are dropped. The header switches the
voice to the fast settings, removes background music and keeps the map continuous (the first beat carries the map
date of the original first map beat).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2] / 'projects'
FAST_VOICE = {'pause_cap': '0.2', 'tempo_target': '5.0', 'gap': '0.3', 'speaker_min_rate': '5.0', 'bed': 'none'}


class Episode:
    def __init__(self, eid: str):
        self.dir = PROJ / eid
        self.f = self.dir / 'episode.yaml'
        orig = self.dir / 'episode.orig.yaml'
        if not orig.exists():
            shutil.copy2(self.f, orig)
        s = orig.read_text(encoding='utf-8')
        i = s.index('\nbeats:\n') + len('\nbeats:\n')
        self.head, body = s[:i], s[i:]
        parts = re.split(r'(?m)^(?=  - say:)', body)
        self.pre, self.old = parts[0], parts[1:]
        self.out: list[str] = []
        self.first_map = next((re.search(r"(?m)^    map: (.*)$", b).group(1) for b in self.old if re.search(r'(?m)^    map: ', b)), None)

    # -------------------------------------------------------------- helpers
    def blk(self, n: int) -> str:
        return self.old[n - 1].rstrip('\n') + '\n'

    def say(self, n: int) -> str:
        return re.search(r'(?m)^  - say: (.*)$', self.old[n - 1]).group(1)

    @staticmethod
    def _show(b: str) -> str:
        m = re.search(r'(?ms)^    show:\n((?:      .*\n)+)', b)
        return m.group(1) if m else ''

    @staticmethod
    def _set(b: str, key: str, val) -> str:
        if re.search(rf'(?m)^    {key}: ', b):
            return re.sub(rf'(?m)^    {key}: .*$', f'    {key}: {val}', b, count=1)
        i = b.index('\n') + 1
        return b[:i] + f'    {key}: {val}\n' + b[i:]

    @staticmethod
    def _fix_cues(b: str, say: str) -> str:
        def fix(m):
            line = m.group(0)
            for c in re.findall(r'(?:cue|arrive|end_cue|clash): ([^,}\n]+)', line):
                if c.strip() not in say:
                    line = re.sub(r',\s*(?:cue|arrive|end_cue): ' + re.escape(c) + r'(?=[,}])', '', line)
                    line = re.sub(r'(?:cue|arrive|end_cue): ' + re.escape(c) + r',\s*', '', line)
            return line
        b = re.sub(r'(?m)^      .*$', fix, b)
        b = re.sub(r'(?m)^(    camera: .*?),\s*cue: ([^,}]+)', lambda m: m.group(0) if m.group(2).strip() in say else m.group(1), b)
        oc = re.search(r'(?m)^    owners_cue: (.*)$', b)
        if oc and oc.group(1).strip() not in say:
            b = re.sub(r'(?m)^    owners_cue: .*\n', '', b)
        # multi-line campaign `clash:` must be in the line too
        cl = re.search(r'(?m)^          clash: (.*)$', b)
        if cl and cl.group(1).strip() not in say:
            # a campaign can't play without its clash word: drop the whole item
            b = re.sub(r'(?m)^      - campaign:\n(?:        .*\n)+', '', b)
        return b

    # -------------------------------------------------------------- building
    def beat(self, src, say: str, merge=(), sets=None, extra=(), drop=(), no_show=False, keep=('phase', 'year', 'map', 'scene')):
        """New beat from original beat `src` with line `say`. `keep` lists original keys kept unless overridden."""
        b = re.sub(r'(?m)^  - say: .*$', '  - say: ' + say, self.blk(src), count=1)
        # voice_text is what TTS reads: keep its (tags) but take the new line, or it would speak the old text
        vt = re.search(r'(?m)^    voice_text: (.*)$', b)
        if vt:
            tags = ''.join(re.findall(r'（[^）]*）', vt.group(1))[:1])
            b = b.replace(vt.group(0), f'    voice_text: {tags}{say}')
        for k in ('phase', 'year', 'map', 'scene', 'music', 'owners_cue'):
            if k not in keep and k not in (sets or {}):
                b = re.sub(rf'(?m)^    {k}: .*\n', '', b)
        b = re.sub(r'(?m)^    music: .*\n', '', b)
        for k in drop:
            b = re.sub(rf'(?m)^    {k}: .*\n', '', b)
        for k, v in (sets or {}).items():
            b = self._set(b, k, v)
        if no_show:
            b = re.sub(r'(?ms)^    show:\n(?:      .*\n)+', '', b)
        add = ''.join(self._show(self.blk(n)) for n in merge) + ''.join(f'      - {x}\n' for x in extra)
        if add:
            if re.search(r'(?m)^    show:\n', b):
                it = self._show(b)
                b = b.replace('    show:\n' + it, '    show:\n' + it + add, 1)
            else:
                b = b.rstrip('\n') + '\n    show:\n' + add
        self.out.append(self._fix_cues(b, say).rstrip('\n') + '\n\n')
        return self

    def line(self, src, say: str, **kw):
        """Keep a speaker beat with a (shortened) line; quote/style/speaker stay."""
        return self.beat(src, say, **kw)

    # -------------------------------------------------------------- output
    def write(self, hook: str | None = None, big: str | None = None, hero: str | None = None, note: str = '', next_: str | None = None):
        h = self.head
        for k, v in FAST_VOICE.items():
            if re.search(rf'(?m)^  {k}: ', h):
                h = re.sub(rf'(?m)^  {k}: [^#\n]*', f'  {k}: {v}', h, count=1)
            else:
                h = re.sub(r'(?m)^voice:\n', f'voice:\n  {k}: {v}\n', h, count=1)
        h = re.sub(r'(?m)^music: .*\n', '', h)
        if hook:
            h = re.sub(r'(?m)^  hook: .*$', f'  hook: {hook}', h, count=1)
        if big:
            h = re.sub(r'(?m)^  big: .*$', f'  big: {big}', h, count=1)
        if hero:
            h = re.sub(r'(?m)^  hero: .*$', f'  hero: {hero}', h, count=1)
        if next_:
            h = re.sub(r'(?m)^  next: .*$', f'  next: {next_}', h, count=1)
        h = re.sub(r'(?m)^  chapters:\n(?:    - .*\n)+', '', h)
        h = f'# 快节奏版（2026-10-13，按抖音数据：冷开场、只讲有戏的、无背景音乐）{(" " + note) if note else ""}\n' + h
        out = self.out
        # map continuity: the cold open carries the episode's opening map state
        if self.first_map and not re.search(r'(?m)^    map: ', out[0]):
            out[0] = self._set(out[0], 'map', self.first_map)
        self.f.write_text(h + self.pre + ''.join(out), encoding='utf-8')
        return len(out)
