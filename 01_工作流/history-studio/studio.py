"""History Studio: episode script (YAML) -> checked IR -> Remotion render.

    python studio.py new    <id>                  scaffold 01_工作流/projects/<id>/episode.yaml
    python studio.py check  <episode.yaml>        validate script (placeholder timing, no audio)
    python studio.py voice  <episode.yaml>        synthesize / measure narration -> voice/timing.json
    python studio.py build  <episode.yaml>        stage public dir (IR, basemap, audio, fonts, portraits)
    python studio.py preview <episode.yaml>       open Remotion Studio on the staged build
    python studio.py still  <episode.yaml> -t 5   render single frames for review
    python studio.py render <episode.yaml>        render MP4 + media check + contact sheet

The script format is documented in 01_工作流/history-studio/SCRIPT.md.
Places, persons and citations come from 01_工作流/maindata; unknown names are
errors, not guesses. Builds go to 05_项目/Remotion/studio/<id>/<build>/ and
are never overwritten.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
import yaml

import campaign
from PIL import Image, ImageEnhance

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parent
ROOT = WORKFLOW.parent
MAINDATA = WORKFLOW / 'maindata'
REMOTION = WORKFLOW / 'remotion-shuihong'
TILES = ROOT / '.workbuddy'
OUT_ROOT = ROOT / '05_项目' / 'Remotion' / 'studio'
PROJECTS = WORKFLOW / 'projects'
CACHE = HERE / 'cache'
GAZETTEER = HERE / 'data' / 'gazetteer.json'
CORPUS = WORKFLOW / 'corpus'

W, H = 1920, 1080
TILE_DIRS = {6: ['national_relief_z6_cache'], 8: ['basemap_z8_cache', 'wide2_cache'], 9: ['relief_z9_v2_cache', 'relief_z9_core_cache']}
COLORS = {'red': '#8a281c', 'blue': '#27587e', 'gold': '#8a6a1c', 'green': '#2f5d3a', 'purple': '#4f2f6e', 'gray': '#4a4a48', 'black': '#2a2420'}
THEME = {'paper': '#d6c4a9', 'ink': '#392c23', 'red': '#c8241b', 'blue': '#2878ac', 'gold': '#dec083', 'river': '#2878ac', 'captionBg': '#1e1e1bd9', 'yearBg': '#38555dde', 'ui': 'clean'}
ELEMENT_TYPES = {'tactic', 'forces', 'sfx', 'act', 'fire', 'flag', 'arrow', 'battle', 'stamp', 'card', 'portrait', 'headline', 'region',
                 'enter', 'person_card', 'versus', 'exit', 'title_bar', 'quote', 'faction_bar',
                 'march', 'army', 'chase', 'camp', 'vignette', 'takeover', 'retire', 'campaign', 'clash', 'rout', 'defect', 'turn', 'yearshift', 'yearflip', 'meanwhile', 'multi_march', 'flee', 'siege', 'capture', 'alliance', 'replay', 'spot', 'breathe'}
RENDER_CONCURRENCY = int(os.environ.get('HISTORY_STUDIO_CONCURRENCY', 8))
# 对话舞台的场景底图（03_素材/动画素材/第6、7批）：`scene:` 写任一别名
SCENES = {'军帐|帐|营帐|大帐': 'scene_tent', '朝堂|殿|大殿|朝廷|议事': 'scene_court', '城楼|城墙|城头|白门楼': 'scene_citywall',
          '辕门|营门': 'scene_campgate', '楼船|战船|船|江上': 'scene_warship', '草庐|茅庐|隆中': 'scene_cottage',
          '宴席|宴|酒宴': 'scene_banquet', '刑场|法场': 'scene_execution', '宫门|宫中|掖门': 'scene_palacegate',
          # 第7批（2026-10-14）
          '病榻|寝殿|托孤': 'scene_sickbed', '祭坛|登坛|受禅|称帝': 'scene_altar', '陵屋|陵|墓': 'scene_tomb',
          '栈道|山道|祁山': 'scene_mountainpass', '渡口|江边': 'scene_riverbank', '书房|相府': 'scene_study'}
FIGHT_SFX = {'battle': ['刀剑交击', '兵器碰撞', '挥刀'], 'clash': ['刀剑交击', '兵器碰撞', '挥刀'], 'siege': ['战鼓', '集结鼓'], 'fire': ['火攻', '点火']}
EXIT_STAMP = {'卒': '卒', '死': '卒', '诛': '诛', '杀': '诛', '败': '败', '囚': '囚', '亡': '亡', '奔': '奔', '逃': '奔', '废': '废', '降': '降'}


SFX_DIR = ROOT / '03_素材' / '音效'


def sfx_cues() -> dict:
    """The sound vocabulary (03_素材/音效/cues.json): cue name -> sound, hit/bed, length, level, when to use."""
    f = SFX_DIR / 'cues.json'
    return read_json(f) if f.exists() else {'cues': {}, 'rules': {}}


def load_sfx(key: str) -> np.ndarray:
    """Decode one library sound to 48 kHz mono, leading silence cut, peak 1 (cached)."""
    item = next(i for i in read_json(SFX_DIR / 'catalog.json')['items'] if i['key'] == key)
    out = CACHE / 'sfx' / f'{key}.wav'
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_pcm(ROOT / item['file'], out)
    x = read_pcm(out)
    x = x / (np.max(np.abs(x)) or 1)
    loud = np.nonzero(np.abs(x) > 0.03)[0]
    return x[max(0, int(loud[0]) - 240):] if len(loud) else x


class ScriptError(Exception):
    pass


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_json(p: Path):
    return json.loads(p.read_text(encoding='utf-8'))


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')


# ---------------------------------------------------------------- registries

class Registry:
    """Read-only view of maindata. Episodes reference ids, never raw coordinates,
    except explicitly declared local places that carry their own source."""

    def __init__(self) -> None:
        self.places: dict[str, dict] = {}
        for f in ['places.json', 'places_approximate.json']:
            for p in read_json(MAINDATA / f)['places']:
                if not p['id'].startswith('UNREGISTERED'):
                    self.places.setdefault(p['id'], p)
        for p in read_json(WORKFLOW / 'places_curated.json')['places']:
            self.places.setdefault(p['id'], p)
        # Studio gazetteer: places confirmed by agents/editors for earlier episodes.
        # Every entry carries its own coordinate source and precision.
        if GAZETTEER.exists():
            for p in read_json(GAZETTEER)['places']:
                old = self.places.setdefault(p['id'], p)
                # researched tiers (第12批 城邑等级, auditBatch) win over the coarse ones of maindata/curated,
                # while the earlier record keeps its curated coordinates
                if old is not p and any('auditBatch' in t for t in p.get('tiers') or []):
                    self.places[p['id']] = {**old, **{k: p[k] for k in ('tiers', 'tierTransitions', 'politicalRoles') if k in p}}
        self.alias = {}
        for pid, p in self.places.items():
            for a in [*p.get('aliases', []), *(n.get('text') for n in p.get('names', []) if n.get('text'))]:
                self.alias.setdefault(a, pid)
        self.persons = {p['id']: p for p in read_json(MAINDATA / 'persons.json')['persons']}
        self.citations = {}
        for c in read_json(MAINDATA / 'citations.json')['citations']:
            self.citations[c['id']] = c
            for a in c.get('aliases', []):
                self.citations.setdefault(a, c)

    def place(self, ref: str) -> dict | None:
        return self.places.get(ref) or self.places.get(self.alias.get(ref, ''))


# City tiers (第12批, 2026-10-24). Administrative rank and the ruler's seat are separate: 许 is the Han capital
# while 曹操 sits at 邺 (a commandery seat with the ruler badge). Older records say city / seat.
CITY_TIERS = ('capital', 'province', 'commandery', 'county', 'stronghold')
TIERS = (*CITY_TIERS, 'pass', 'ferry', 'region')
LEGACY_TIER = {'seat': 'commandery', 'city': 'county'}


def tier_at(rec, y, m, default='county'):
    """A place's rank in year y, month m: the year's value, except in a year with a dated change (武昌 229:
    capital from the 4th month to the 9th), where the changes up to month m are applied in order."""
    tier = year_value(rec.get('tiers'), y, 'tier')
    changes = sorted((t for t in rec.get('tierTransitions') or [] if t.get('year') == y), key=lambda t: t.get('month') or 12)
    if changes:
        tier = changes[0].get('fromTier') or tier
        for t in changes:
            if (t.get('month') or 12) <= m:
                tier = t.get('toTier') or tier
    tier = LEGACY_TIER.get(tier, tier) or default
    return tier if tier in TIERS else default


def seat_at(rec, y, m):
    """Is a ruler (not as emperor) seated here: 刘备 at 成都 before 221, 孙权 at 武昌 221–229."""
    for r in rec.get('politicalRoles') or []:
        if r.get('kind') not in ('ruler_seat', 'temporary_court'):
            continue
        if r.get('startMonth'):
            end = r.get('endMonthExclusive') or [9999, 1]
            if tuple(r['startMonth']) <= (y, m) < tuple(end):
                return True
        elif (r.get('from') is None or r['from'] <= y) and (r.get('to') is None or y <= r['to']):
            return True
    return False


def year_value(entries, year, key):
    for e in entries or []:
        lo, hi = e.get('from'), e.get('to')
        if (lo is None or lo <= year) and (hi is None or year <= hi):
            return e.get(key)
    return None


# ---------------------------------------------------------------- projection

class Projection:
    def __init__(self, center, scale):
        self.lon0, self.lat0 = center
        self.s = scale
        self.m0 = self.merc(self.lat0)

    @staticmethod
    def merc(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    def world(self, lon, lat):
        return (W / 2 + math.radians(lon - self.lon0) * self.s, H / 2 - self.s * (self.merc(lat) - self.m0))


# ---------------------------------------------------------------- voice

def ffmpeg_pcm(src: Path, dst: Path) -> None:
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-ac', '1', '-ar', '48000', '-sample_fmt', 's16', str(dst)], check=True)


def read_pcm(p: Path) -> np.ndarray:
    with wave.open(str(p)) as w:
        assert w.getframerate() == 48000 and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def write_pcm(p: Path, x: np.ndarray) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def voice_bounds(x: np.ndarray) -> tuple[float, float]:
    """10 ms RMS > 0.004 after peak normalisation: phrase-level, not forced alignment."""
    peak = float(np.max(np.abs(x))) or 1.0
    n = 480
    frames = x[: len(x) // n * n].reshape(-1, n) / peak
    rms = np.sqrt((frames ** 2).mean(axis=1))
    on = np.nonzero(rms > 0.004)[0]
    if not len(on):
        return 0.0, len(x) / 48000
    return on[0] * 0.01, (on[-1] + 1) * 0.01


def clean_voice(x: np.ndarray, sr: int = 48000, tail: bool = True) -> tuple[np.ndarray, int, bool]:
    """Silence breaths, clicks and room noise in one TTS clip, and trim its dead air.

    Islands = runs of 10 ms frames above -48 dB (re peak). Speech islands reach about -22 dB and are
    periodic (voiced). An island is removed when it is very quiet (< -32 dB), or quiet (< -23 dB) and
    aperiodic with a high spectral centroid, i.e. an inhale or exhale. Everything outside the kept
    islands is gated to silence with 8 ms ramps, so clip edges no longer click.
    """
    n = sr // 100
    peak = float(np.max(np.abs(x))) or 1.0
    fr = x[: len(x) // n * n].reshape(-1, n) / peak
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    on = db > -48
    keep = np.zeros(len(db), bool)
    removed = 0
    tail_cut = False
    spans = []
    i = 0
    while i < len(db):
        if not on[i]:
            i += 1
            continue
        j = i
        while j < len(db) and on[j]:
            j += 1
        spans.append((i, j))
        i = j
    for k, (i, j) in enumerate(spans):
        # silence (in 10 ms frames) to the neighbouring islands; a clip edge counts as isolated
        gap_b = i - spans[k - 1][1] if k else 999
        gap_a = spans[k + 1][0] - j if k + 1 < len(spans) else 999
        top = db[i:j].max()
        # whispered sentence-final syllables (许县, 五十四岁) are also quiet and aperiodic, so only an
        # island cut off from the speech by real pauses on both sides counts as a breath
        drop = top < -34 and min(gap_b, gap_a) >= 15
        # a short, soft sound tacked on after the sentence has ended (TTS adds a sigh like "哎")
        # (a real last word can follow a pause too — 他说：这里挺快乐，不想 — so the caller re-checks with ASR)
        sigh = tail and k == len(spans) - 1 and k > 0 and gap_b >= 50 and top <= -20 and j - i < 45
        tail_cut = tail_cut or sigh
        drop = drop or sigh
        if not drop and top < -23 and j - i >= 6 and min(gap_b, gap_a) >= 35:
            seg = x[i * n:j * n] - x[i * n:j * n].mean()
            per = []
            for k in range(0, len(seg) - 2 * n * 2, 2 * n):
                w = seg[k:k + 4 * n]
                a = np.correlate(w, w, 'full')[len(w) - 1:]
                if a[0] > 0:
                    per.append(a[sr // 400:sr // 70].max() / a[0])
            spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
            cen = float((spec * np.fft.rfftfreq(len(seg), 1 / sr)).sum() / (spec.sum() or 1))
            drop = (np.median(per) if per else 0) < 0.26 and cen > 2200
        if drop:
            removed += 1
        else:
            keep[max(0, i - 3):j + 3] = True   # 30 ms margin keeps soft onsets and word tails
    g = np.repeat(keep.astype(np.float32), n)
    g = np.concatenate([g, np.full(len(x) - len(g), g[-1] if len(g) else 1.0, np.float32)])
    ramp = int(0.008 * sr)
    g = np.convolve(g, np.ones(ramp) / ramp, mode='same')
    y = (x * g).astype(np.float32)
    # dead air: some clips end with seconds of silence (then a breath), or pause > 0.7 s mid-sentence
    idx = np.nonzero(keep)[0]
    if len(idx):
        parts, prev = [y[: idx[0] * n]], idx[0]
        for a, b in zip(idx[:-1], idx[1:]):
            if b - a > 60:                      # pause longer than 0.6 s → 0.6 s
                parts.append(y[prev * n:(a + 1) * n])
                parts.append(np.zeros(60 * n, np.float32))
                prev = b
        parts.append(y[prev * n:min(len(y), (idx[-1] + 1) * n + int(0.2 * sr))])   # 0.2 s tail after the last word
        y = np.concatenate(parts)
    return y, removed, tail_cut


PAUSE_AFTER = {'，': 0.2, '、': 0.16, '：': 0.24, '；': 0.26, '——': 0.24, '。': 0.3, '！': 0.3, '？': 0.3, '…': 0.3}


def even_out(x: np.ndarray, text: str, rate: float, tmp: Path, sr: int = 48000, pause: float = 1.0) -> tuple[np.ndarray, dict]:
    """Re-time one cleaned TTS clip phrase by phrase.

    TTS rushes some phrases and drags others inside one sentence (5.8 vs 9.0 字/秒 measured), pauses
    0.09–0.27 s at commas, and pads 0.2 s before / 0.3–0.5 s after. Split the speech at its pauses;
    when the pieces match the punctuated phrases, time-stretch each phrase to `rate` (0.75–1.5×,
    pitch kept) and rebuild with standard pauses per punctuation mark; otherwise stretch the whole
    sentence. Short punch lines (≤8 字) keep part of their slowness. Lead 0.06 s, tail 0.1 s.
    `pause` scales every pause (1.8 ≈ the unhurried breathing of a documentary narrator).
    """
    n = sr // 100
    fr = x[: len(x) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    idx = np.nonzero(db > -40)[0]
    if not len(idx):
        return x, {'mode': 'empty'}
    segs, s0 = [], idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a > 12:                       # a pause of more than 0.12 s
            segs.append((s0, a + 1))
            s0 = b
    segs.append((s0, idx[-1] + 1))
    parts = [m for m in re.finditer(r'([^，、：；。！？…—]+)(——|[，、：；。！？…]*)', text) if re.sub(r'[\W_]', '', m.group(1))]
    total = len(re.sub(r'[\W_]', '', text))
    soften = total <= 8

    def stretch(seg: np.ndarray, f: float) -> np.ndarray:
        f = min(max(f ** 0.5 if soften else f, 0.75), 1.5)   # slowing harder sounds spelled-out
        if abs(f - 1) < 0.02:
            return seg
        a, b = tmp.with_suffix('.in.wav'), tmp.with_suffix('.out.wav')
        write_pcm(a, seg)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(a), '-filter:a', f'atempo={f:.3f}', '-ac', '1', '-ar', str(sr), '-sample_fmt', 's16', str(b)], check=True)
        out = read_pcm(b)
        a.unlink()
        b.unlink()
        return out

    def cut(s, e):  # 30 ms margins keep soft onsets and word tails; 5 ms fades avoid clicks
        # Inside one phrase the model often leaves 40–90 ms gaps between words (曹爽 · 陪着 · 小皇帝);
        # slowing the phrase down would stretch them into audible word-by-word breaks, so squeeze
        # every silence within the phrase to 30 ms first.
        a, z = max(0, s - 3), min(len(db), e + 3)
        keep = np.ones(z - a, bool)
        quiet = db[a:z] <= -40
        k = 0
        while k < len(quiet):
            if quiet[k]:
                j = k
                while j < len(quiet) and quiet[j]:
                    j += 1
                if k > 0 and j < len(quiet) and j - k > 3:
                    keep[k + 1:j - 2] = False      # leave 10 ms + 20 ms around the join
                k = j
            else:
                k += 1
        seg = np.concatenate([x[(a + f) * n:(a + f + 1) * n] for f in np.nonzero(keep)[0]]).copy()
        k = min(len(seg) // 2, int(0.005 * sr))
        if k:
            seg[:k] *= np.linspace(0, 1, k)
            seg[-k:] *= np.linspace(1, 0, k)
        return seg

    lead, tail = np.zeros(int(0.06 * sr), np.float32), np.zeros(int(0.1 * sr), np.float32)
    if len(segs) == len(parts):
        out, rates = [lead], []
        for (s, e), m in zip(segs, parts):
            seg = cut(s, e)
            c = len(re.sub(r'[\W_]', '', m.group(1)))
            r = c / max(0.12, (e - s) / 100)
            rates.append(round(r, 1))
            out.append(stretch(seg, rate / r))
            punct = m.group(2)
            if m is not parts[-1]:
                out.append(np.zeros(int(PAUSE_AFTER.get(punct[:2] if punct.startswith('——') else punct[:1], 0.12) * pause * sr), np.float32))
        out.append(tail)
        return np.concatenate(out).astype(np.float32), {'mode': 'phrase', 'raw_rates': rates}
    # pieces do not line up with the punctuation: stretch the whole sentence, cap its pauses
    body = []
    for k, (s, e) in enumerate(segs):
        body.append(cut(s, e))
        if k + 1 < len(segs):
            body.append(np.zeros(int(min(max((segs[k + 1][0] - e) / 100, 0.12), 0.3) * pause * sr), np.float32))
    body = np.concatenate(body)
    r = total / max(0.3, (segs[-1][1] - segs[0][0]) / 100)
    return np.concatenate([lead, stretch(body, rate / r), tail]).astype(np.float32), {'mode': 'sentence', 'raw_rate': round(r, 1)}


def original_bed(seconds: float, hits: list[float], seed: int = 301) -> np.ndarray:
    """Locally synthesised drone + soft low hits at beat starts. Original, no samples."""
    sr = 48000
    t = np.arange(int(seconds * sr)) / sr
    swell = 0.6 + 0.4 * np.sin(2 * math.pi * t / 11.0) ** 2
    bed = sum(a * np.sin(2 * math.pi * f * t + ph) for f, a, ph in [(110, .5, 0), (146.832, .32, 1.1), (220, .18, 2.3), (293.665, .1, .7)])
    bed = bed * swell
    rng = np.random.default_rng(seed)
    for h in hits[:1]:   # one soft hit at the very start only; a hit at every beat read as noise between sentences
        i = int(h * sr)
        k = np.arange(int(0.9 * sr)) / sr
        hit = np.sin(2 * math.pi * (62 + 20 * np.exp(-k * 9)) * k) * np.exp(-k * 5.5) + 0.04 * rng.standard_normal(len(k)) * np.exp(-k * 30)
        j = min(len(bed), i + len(hit))
        if i < len(bed):
            bed[i:j] += 1.2 * hit[: j - i]
    fade = np.minimum(1, np.minimum(t / 1.5, (seconds - t) / 2.0))
    bed *= np.clip(fade, 0, 1)
    return bed / (np.max(np.abs(bed)) or 1)


CN_DIGITS = '零一二三四五六七八九'


def cn_number(n: int) -> str:
    if n < 10:
        return CN_DIGITS[n]
    out = ''
    for unit, val in (('千', 1000), ('百', 100), ('十', 10)):
        q, n = divmod(n, val)
        if q:
            out += ('' if (unit == '十' and q == 1 and not out) else CN_DIGITS[q]) + unit
        elif out and n and not out.endswith('零'):
            out += '零'
    return out + (CN_DIGITS[n] if n else '')


def speech_norm(t: str) -> str:
    t = re.sub(r'\d+', lambda m: cn_number(int(m.group())) if len(m.group()) <= 4 else m.group(), t)
    return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', t)


def asr_check(wav: Path, text: str) -> dict:
    """Transcribe a synthesized line with MiMo ASR and diff it against the script."""
    import base64
    import difflib
    import urllib.error
    import urllib.request
    sys.path.insert(0, str(WORKFLOW))
    import mimo_tts  # noqa: E402
    cache = wav.with_suffix('.asr.json')
    if cache.exists():
        heard = read_json(cache)['heard']
    else:
        tmp = wav.with_suffix('.16k.wav')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wav), '-ac', '1', '-ar', '16000', str(tmp)], check=True)
        body = {'model': 'mimo-v2.5-asr', 'messages': [{'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {'data': base64.b64encode(tmp.read_bytes()).decode(), 'format': 'wav'}}]}]}
        req = urllib.request.Request(mimo_tts.API_URL, data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + mimo_tts.get_api_key(), 'Content-Type': 'application/json'})
        try:
            heard = with_backoff(lambda: json.load(urllib.request.urlopen(req, timeout=120)), 'ASR')['choices'][0]['message']['content'].strip()
        except urllib.error.HTTPError as e:
            # the ASR service occasionally refuses a clip (400, e.g. violent wording); don't fail the build —
            # pass it through as unchecked so the review sheet asks a human to listen
            if e.code != 400:
                raise
            print(f'  ⚠ ASR refused {wav.name} (HTTP 400); marked unchecked', flush=True)
            tmp.unlink(missing_ok=True)
            return {'text': text, 'heard': '', 'ratio': 1.0, 'diff': [], 'unchecked': True}
        tmp.unlink()
        write_json(cache, {'heard': heard})
    a, b = speech_norm(text), speech_norm(heard)
    sm = difflib.SequenceMatcher(None, a, b)
    diff = [f'「{a[i1:i2]}」→「{b[j1:j2]}」' for op, i1, i2, j1, j2 in sm.get_opcodes() if op != 'equal']
    return {'text': text, 'heard': heard, 'ratio': round(sm.ratio(), 3), 'diff': diff}


def placeholder_len(text: str) -> float:
    chars = len(re.sub(r'[\s，。、；：！？“”‘’（）《》,.;:!?]', '', text))
    pauses = len(re.findall(r'[，。、；：！？,.;:!?]', text))
    return 0.24 * chars + 0.28 * pauses + 0.2


def with_backoff(fn, what: str, tries: int = 7):
    """MiMo answers HTTP 429 when requests come too fast: wait and retry (5, 10, 20 … s)."""
    for k in range(tries):
        try:
            return fn()
        except Exception as e:   # urllib HTTPError or the wrapper's RuntimeError
            if '429' not in str(e) and 'Too Many' not in str(e) or k == tries - 1:
                raise
            if 'PerDay' in str(e) or 'per day' in str(e):   # Gemini free tier: the daily quota is spent, waiting minutes won't help
                raise RuntimeError(f'{what}: 今天的免费额度用完了（每天太平洋时间零点重置），明天再继续。{str(e)[:200]}') from None
            wait = 5 * 2 ** k
            print(f'  … {what}: MiMo 限流（429），{wait} 秒后重试', flush=True)
            time.sleep(wait)


def synthesize(beat_text: str, out: Path, cfg: dict, style: str) -> None:
    with_backoff(lambda: _synthesize(beat_text, out, cfg, style), 'TTS')


def _synthesize(beat_text: str, out: Path, cfg: dict, style: str) -> None:
    sys.path.insert(0, str(WORKFLOW))
    import mimo_tts  # noqa: E402  (reads MIMO_API_KEY; key never written)
    provider = cfg.get('provider', 'preset')
    if provider == 'gemini':
        import gemini_tts  # noqa: E402  (reads GEMINI_API; key never written)
        gemini_tts.synthesize(beat_text, out, cfg.get('voice', 'Algenib'), style, cfg.get('model', gemini_tts.DEFAULT_MODEL))
        return
    if provider == 'clone':
        ref = (ROOT / cfg['reference']).resolve() if not Path(cfg['reference']).is_absolute() else Path(cfg['reference'])
        mimo_tts.synthesize_voice_clone(beat_text, out, ref, style)
    elif provider == 'design':
        mimo_tts.synthesize_voice_design(beat_text, out, cfg['description'])
    else:
        mimo_tts.synthesize_preset(beat_text, out, cfg.get('voice', '茉莉'), style)


def stutter(heard: str, text: str) -> str | None:
    """A phrase the voice said twice in a row that the script doesn't repeat (「就在就在这时」); ASR ratio barely notices."""
    h = re.sub(r'[\W_]', '', heard)
    t = re.sub(r'[\W_]', '', text)
    for n in (4, 3, 2):
        for i in range(len(h) - 2 * n + 1):
            w = h[i:i + n]
            if h[i + n:i + 2 * n] == w and w + w not in t:
                return w + w
    return None


def cap_pauses(x: np.ndarray, cap: float, sr: int = 48000) -> np.ndarray:
    """Shorten every silence longer than `cap` seconds to `cap` (speech itself untouched)."""
    n = sr // 100
    fr = x[: len(x) // n * n].reshape(-1, n)
    quiet = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9) <= -40
    keep = np.ones(len(quiet), bool)
    k = 0
    while k < len(quiet):
        if not quiet[k]:
            k += 1
            continue
        j = k
        while j < len(quiet) and quiet[j]:
            j += 1
        if k > 0 and j < len(quiet) and j - k > cap * 100:
            half = int(cap * 50)
            keep[k + half:j - half] = False
        k = j
    return np.concatenate([x[f * n:(f + 1) * n] for f in np.nonzero(keep)[0]] + [x[len(quiet) * n:]])


def atempo(x: np.ndarray, f: float, tmp: Path, sr: int = 48000) -> np.ndarray:
    """Uniform tempo change of a whole passage (pitch kept), so its intonation stays intact."""
    if abs(f - 1) < 0.01:
        return x
    a, b = tmp.with_suffix('.in.wav'), tmp.with_suffix('.out.wav')
    write_pcm(a, x)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(a), '-filter:a', f'atempo={f:.4f}', '-ac', '1', '-ar', str(sr), '-sample_fmt', 's16', str(b)], check=True)
    y = read_pcm(b)
    a.unlink()
    b.unlink()
    return y


def split_by_pauses(x: np.ndarray, texts: list[str], sr: int = 48000) -> list[tuple[int, int]]:
    """Cut one narrated paragraph back into its sentences. Sentence boundaries are the pauses that
    best fit, together, the positions predicted by each sentence's share of characters, favouring
    long pauses (a full stop pauses longer than a comma). Chosen jointly by dynamic programming."""
    n = sr // 100
    fr = x[: len(x) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    idx = np.nonzero(db > -40)[0]
    speech = idx.tolist()
    gaps = [(int(a), int(b)) for a, b in zip(idx[:-1], idx[1:]) if b - a > 8]
    chars = [max(1, len(re.sub(r'[\W_]', '', t))) for t in texts]
    need = len(texts) - 1
    if need == 0:
        return [(0, len(x))]
    exp = [speech[min(len(speech) - 1, int(c * len(speech)))] for c in np.cumsum(chars)[:-1] / sum(chars)]
    span = max(1, speech[-1] - speech[0])
    if len(gaps) < need:
        gaps += [(e, e + 1) for e in exp][: need - len(gaps)]
        gaps.sort()

    def score(g, k):   # long pause near the expected boundary
        return min(g[1] - g[0], 60) / 10 - abs((g[0] + g[1]) / 2 - exp[k]) / (span * 0.05)
    G = len(gaps)
    best = np.full((need, G), -1e9)
    back = np.zeros((need, G), int)
    for gi in range(G):
        best[0, gi] = score(gaps[gi], 0)
    for k in range(1, need):
        run, arg = -1e9, -1
        for gi in range(G):
            if gi - 1 >= 0 and best[k - 1, gi - 1] > run:
                run, arg = best[k - 1, gi - 1], gi - 1
            if arg >= 0:
                best[k, gi] = run + score(gaps[gi], k)
                back[k, gi] = arg
    gi = int(np.argmax(best[need - 1]))
    chosen = []
    for k in range(need - 1, -1, -1):
        chosen.append(gaps[gi])
        gi = back[k, gi]
    chosen.reverse()
    cuts = [0] + [((a + b) // 2) * n for a, b in chosen] + [len(x)]
    return [(cuts[k], cuts[k + 1]) for k in range(len(texts))]


def refine_cuts(x: np.ndarray, texts: list[str], bounds: list[tuple[int, int]], tmp: Path, sr: int = 48000) -> list[tuple[int, int]]:
    """ASR-check each cut piece; where two neighbours do not read as their sentences, try the
    pauses within ±3 s of that cut and keep the one under which both read best."""
    n = sr // 100
    fr = x[: len(x) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    idx = np.nonzero(db > -40)[0]
    mids = [((a + b) // 2) * n for a, b in zip(idx[:-1], idx[1:]) if b - a > 8]
    cuts = [b0 for b0, _ in bounds] + [bounds[-1][1]]

    def ratio(a, b, text, tag):
        f = tmp.with_name(f'{tmp.stem}-{tag}-{a}-{b}.wav')
        write_pcm(f, x[a:b])
        r = asr_check(f, text)['ratio']
        f.unlink()
        return r
    for k in range(1, len(cuts) - 1):
        left, right = ratio(cuts[k - 1], cuts[k], texts[k - 1], 'l'), ratio(cuts[k], cuts[k + 1], texts[k], 'r')
        if min(left, right) >= 0.9:
            continue
        best = (min(left, right), cuts[k])
        for m in mids:
            if cuts[k - 1] < m < cuts[k + 1] and abs(m - cuts[k]) <= 3 * sr and m != cuts[k]:
                sc = min(ratio(cuts[k - 1], m, texts[k - 1], 'l'), ratio(m, cuts[k + 1], texts[k], 'r'))
                if sc > best[0]:
                    best = (sc, m)
        if best[1] != cuts[k]:
            print(f'  cut {k} moved {(best[1] - cuts[k]) / sr:+.2f}s (ASR {min(left, right):.2f} → {best[0]:.2f})')
            cuts[k] = best[1]
    return [(cuts[k], cuts[k + 1]) for k in range(len(texts))]


def voiced_level(x: np.ndarray) -> float:
    """Median level of the voiced 10 ms frames (dBFS) ≈ how loud the speaking voice sounds."""
    fr = x[: len(x) // 480 * 480].reshape(-1, 480)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    return float(np.median(db[db > db.max() - 40]))


def soft_limit(y: np.ndarray, knee: float = 0.8, ceil: float = 0.97) -> np.ndarray:
    a = np.abs(y)
    over = a > knee
    y = y.copy()
    y[over] = np.sign(y[over]) * (knee + (ceil - knee) * np.tanh((a[over] - knee) / (ceil - knee)))
    return y


CHAR_REFS = ROOT / '03_素材' / '配音参考' / '人物'


def speaker_clip(i: int, b: dict, person: dict, cfg: dict, vdir: Path, timing: dict) -> np.ndarray:
    """A line spoken by the historical figure himself (`speaker:` on the beat), not by the narrator.
    The character's voice is designed once from `people.<name>.voice` (a description) and kept in
    03_素材/配音参考/人物/, so the same person sounds the same in every episode; each line is then
    voice-cloned from that sample with the beat's `style` (or `people.<name>.voice_style`)."""
    sys.path.insert(0, str(WORKFLOW))
    import mimo_tts  # noqa: E402
    name = b['speaker']
    desc = person['voice'] if isinstance(person.get('voice'), str) else (person.get('voice') or {}).get('desc', '')
    style = b.get('style') or person.get('voice_style', '')
    # the sample line sets the manner the clone imitates: a calm sample gives calm lines (张角 sounded flat,
    # 2026-10-10), so a fiery character gets a fiery `voice_sample`
    sample = person.get('voice_sample', '此事关系天下安危，诸位务必用心。')
    ref = CHAR_REFS / f"{name}-{hashlib.sha256((desc + '|' + sample).encode()).hexdigest()[:8]}.wav"
    if not ref.exists():
        CHAR_REFS.mkdir(parents=True, exist_ok=True)
        print(f'  designing the voice of {name}', flush=True)
        with_backoff(lambda: mimo_tts.synthesize_voice_design(sample, ref, desc), 'TTS')
    text = spoken_form(b['say'])
    spoken = spoken_form(b.get('voice_text', b['say']))    # may carry MiMo tags (（激动地高喊）…); the caption stays `say`
    key = hashlib.sha256(json.dumps([spoken, desc, style, 'speaker-v1'], ensure_ascii=False).encode()).hexdigest()[:12]
    raw = vdir / f'speaker-{i:02d}-{key}.wav'

    def make():
        print(f'  TTS line of {name} (beat {i + 1})', flush=True)
        with_backoff(lambda: mimo_tts.synthesize_voice_clone(spoken, raw, ref, style), 'TTS')
    if not raw.exists():
        make()
    check = asr_check(raw, text)
    kept = raw.with_suffix('.kept')         # retries already spent on this take: keep it, don't burn API calls every build
    for attempt in range(0 if kept.exists() else int(cfg.get('asr_retries', 2))):
        if check['ratio'] >= 0.9 and not stutter(check.get('heard', ''), text):
            break
        print(f"  ↻ {name}'s line ASR {check['ratio']:.2f}, re-synthesizing ({attempt + 1})")
        raw.unlink()
        make()
        check = asr_check(raw, text)
    kept.write_text(f"{check['ratio']:.2f}", encoding='utf-8')
    timing.setdefault('asr', []).append({'beat': i + 1, 'speaker': name, **check})
    pcm = vdir / f'{raw.stem}.pcm.wav'
    ffmpeg_pcm(raw, pcm)
    x = read_pcm(pcm)
    x = x / (np.max(np.abs(x)) or 1) * 0.89
    x, _, _ = clean_voice(x, tail=False)
    # pace: pauses inside the line kept short, then `speed` (beat or person; pitch kept)
    x = cap_pauses(x, float(b.get('pause_cap', 0.25)))
    speed = float(b.get('speed', person.get('voice_speed', 1.0)))
    # a character's line may carry feeling, but must not drag: lift it to at least `speaker_min_rate` 字/秒 (≤1.35×)
    chars = len(re.sub(r'[\W_]', '', b['say']))
    env = np.convolve(np.abs(x), np.ones(960) / 960, mode='same')          # 20 ms envelope; measure the voiced span only
    on = np.flatnonzero(env > 0.02 * (env.max() or 1))
    span = (on[-1] - on[0]) / 48000 if len(on) else len(x) / 48000
    rate = chars / max(0.5, span / speed)
    floor = float(cfg.get('speaker_min_rate', 4.3))
    if rate < floor and chars >= 8:          # a short shout (吕布何在！) is meant to be drawn out: leave it
        lifted = min(1.35, speed * floor / rate)
        if lifted > speed + 0.01:
            print(f"  ⏩ {name}'s line {rate:.1f} 字/秒 → speed {lifted:.2f}")
            speed = lifted
    timing.setdefault('speaker_pace', []).append({'beat': i + 1, 'speaker': name, 'rate_before': round(rate, 2), 'speed': round(speed, 2),
                                                  'rate': round(chars / max(0.5, span / speed), 2)})
    if abs(speed - 1) > 0.01:
        x = atempo(x, speed, vdir / f'{raw.stem}.tempo-{speed:.2f}')
    # same loudness as the narration; a touch of room so it reads as a voice "in the scene"
    # `gain_db` trims one line (a sob or a dying whisper should sit under the narration, not on top of it)
    x = x * 10 ** ((float(cfg.get('voice_level', -24.0)) + float(b.get('gain_db', 0)) - voiced_level(x)) / 20)
    y = np.concatenate([x, np.zeros(int(0.25 * 48000))])
    for d, g in [(0.023, 0.18), (0.041, 0.12), (0.067, 0.08)]:
        k = int(d * 48000)
        y[k:k + len(x)] += g * x
    return soft_limit(y).astype(np.float32)


def match_chapters(xs: list, timing: dict, sr: int = 48000, max_db: float = 5.0) -> None:
    """Make separately voiced chapters sound like one take: an EQ toward the episode's average long-term
    spectrum (1/3-octave, at most ±max_db), then equal speech loudness. Modifies the arrays in place."""
    n = 4096
    freqs = np.fft.rfftfreq(n, 1 / sr)
    def speech_frames(x):
        fr = x[: len(x) // n * n].reshape(-1, n)
        rms = np.sqrt((fr ** 2).mean(axis=1))
        return fr[rms > np.percentile(rms, 40)] if len(fr) else fr
    def ltas(x):
        fr = speech_frames(x)
        return np.log10((np.abs(np.fft.rfft(fr * np.hanning(n), axis=1)) ** 2).mean(axis=0) + 1e-12)
    spectra = [ltas(x) for x in xs]
    target = np.mean(spectra, axis=0)
    # 1/3-octave smoothing of the correction, 60 Hz – 12 kHz only
    centres = 60 * 2 ** (np.arange(0, 24) / 3)        # 60 Hz … 12 kHz (higher bands would pass Nyquist and be empty)
    report = []
    for k, x in enumerate(xs):
        diff_db = 10 * (target - spectra[k])
        band = np.array([diff_db[(freqs >= c / 2 ** (1 / 6)) & (freqs < c * 2 ** (1 / 6))].mean() for c in centres])
        band = np.clip(band - np.median(band), -max_db, max_db)        # tone only; level is matched below
        curve = np.interp(np.log(np.maximum(freqs, 1)), np.log(centres), band, left=0, right=0)
        h = np.fft.irfft(10 ** (curve / 20), n)
        h = np.roll(h, n // 2) * np.hanning(n)                          # linear-phase FIR
        from scipy.signal import fftconvolve
        y = fftconvolve(x, h, mode='same')
        xs[k][:] = y
        report.append(round(float(np.abs(band).max()), 1))
    levels = []
    for x in xs:
        # median level of the voiced 10 ms frames ≈ how loud the speaking voice sounds (soft tails count less)
        fr = x[: len(x) // 480 * 480].reshape(-1, 480)
        db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
        levels.append(float(np.median(db[db > db.max() - 40])))
    ref = float(np.mean(levels))
    for x, lv in zip(xs, levels):
        x *= 10 ** ((ref - lv) / 20)
    timing['chapter_match'] = {'eq_max_db': report, 'level_before_db': [round(v, 1) for v in levels], 'level_after_db': round(ref, 1)}


def chapter_voice(beats: list, cfg: dict, vdir: Path, proj: Path, timing: dict, people: dict | None = None) -> tuple[list, list]:
    """`voice.unit: chapter` — narrate each chapter (a `phase:` starts one) as ONE passage, the way a
    person tells a story: the model handles phrasing and intonation across sentences. Then only
    breaths are removed, long silences capped (`pause_cap`), the whole passage given one uniform
    tempo (`tempo_target` 字/秒 overall), and it is cut back into beats at its sentence pauses,
    each piece ASR-verified. The voice is never stretched piece by piece or squeezed for visuals."""
    groups: list[list[int]] = []
    for i, b in enumerate(beats):
        # unit: episode — the whole narration in ONE take, so the voice cannot drift between chapters
        # (2026-10-09: MiMo's chapter-2 take of 第1集 sounded like a different speaker from 苍天已死 on)
        speaker_before = bool(groups) and bool(beats[groups[-1][0]].get('speaker'))
        if not groups or b.get('speaker') or speaker_before or (b.get('phase') and cfg.get('unit') != 'episode'):
            groups.append([])
        groups[-1].append(i)
    clips: list = [None] * len(beats)
    joined = [False] * len(beats)
    tag = cfg.get('tag', '')
    style = '' if tag else cfg.get('style', '')
    vdir.mkdir(parents=True, exist_ok=True)
    done: list[dict] = []
    anchor = None      # voice-clone only: chapters 2… clone chapter 1's own take, so voice and manner stay continuous
    for gi, g in enumerate(groups):
        if beats[g[0]].get('speaker'):
            i = g[0]
            clips[i] = speaker_clip(i, beats[i], (people or {}).get(beats[i]['speaker'], {}), cfg, vdir, timing)
            continue
        texts = [spoken_form(beats[i]['say']) for i in g]
        ccfg = cfg
        if anchor is not None:
            ccfg = {**cfg, 'reference': str(anchor)}
        sents = [t if re.search(r'[。！？…”：]$', t) else t + '。' for t in texts]
        para = ''.join(sents)
        spoken = para
        ident = [para, cfg.get('provider'), cfg.get('reference'), tag, style]
        if cfg.get('provider') in ('preset', None):
            ident.append(['preset', cfg.get('voice', '茉莉')])   # built-in MiMo voice: the name is part of the take
        if cfg.get('provider') == 'gemini':
            ident += [cfg.get('voice'), cfg.get('model')]   # a different voice must never reuse a cached take
            # Gemini runs sentences together; a short pause tag between beats gives the splitter a clean cut
            # at every beat boundary (otherwise 「…点头。主簿陈琳」 was cut after 陈琳)
            spoken = '<short pause>'.join(sents)
            ident.append('beat-pause-v1')
        if anchor is not None:
            ident.append(['anchor', anchor.name])
        key = hashlib.sha256(json.dumps(ident, ensure_ascii=False).encode()).hexdigest()[:12]
        raw = vdir / f'chapter-{g[0]:02d}-{key}.wav'
        if not raw.exists():
            report_progress(proj.name, '配音', gi + 1, len(groups), f'第 {gi + 1} 章')
            print(f'  TTS chapter {gi + 1}/{len(groups)} ({len(g)} beats)', flush=True)
            synthesize(tag + spoken, raw, ccfg, style)
        check = asr_check(raw, para)
        for attempt in range(int(cfg.get('asr_retries', 2))):
            rep = stutter(check.get('heard', ''), para)
            if check['ratio'] >= 0.92 and not rep:
                break
            why = f"repeated 「{rep}」" if rep else f"ASR {check['ratio']:.2f}"
            print(f"  ↻ chapter {gi + 1} {why}, re-synthesizing ({attempt + 1})")
            for f in vdir.glob(f'{raw.stem}*'):
                f.unlink()
            synthesize(tag + spoken, raw, ccfg, style)
            check = asr_check(raw, para)
        timing.setdefault('asr', []).append({'beat': g[0] + 1, 'chapter': gi + 1, **check})
        if anchor is None and cfg.get('provider') == 'clone' and cfg.get('anchor', True) and len(groups) > 1:
            # 20 s of chapter 1 (from 0.5 s in) becomes the clone reference for every later chapter
            anchor = vdir / f'anchor-{raw.stem}.wav'
            if not anchor.exists():
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '0.5', '-t', '20', '-i', str(raw), '-ac', '1', str(anchor)], check=True)
        pcm = vdir / f'{raw.stem}.pcm.wav'
        ffmpeg_pcm(raw, pcm)
        x = read_pcm(pcm)
        x = x / (np.max(np.abs(x)) or 1) * 0.89
        x, _, _ = clean_voice(x, tail=False)
        bounds = split_by_pauses(x, texts)          # cut on the natural pauses (full stops pause longest)
        bounds = refine_cuts(x, texts, bounds, vdir / f'{raw.stem}.cut')
        cap = float(cfg.get('pause_cap', 0) or 0)
        whole = cap_pauses(x, cap) if cap else x
        done.append({'g': g, 'gi': gi, 'texts': texts, 'raw': raw, 'x': x, 'bounds': bounds,
                     'chars': len(re.sub(r'[\W_]', '', para)), 'secs': len(whole) / 48000})

    # Second pass, across chapters. Each chapter is a separate take: the model reads it at its own pace, level
    # and tone, so episode 1 sounded different from start to end (2026-10-09: speed-up ×1.16…×1.35, level
    # −22.6…−27.2 dB, brightness 1770…2359 Hz). One tempo factor for the whole episode, then tone and
    # loudness matched to the episode average.
    cap = float(cfg.get('pause_cap', 0) or 0)
    if cfg.get('tempo_target'):
        lo_hi = (0.85, 1.35)
        if cfg.get('tempo_scope', 'episode') == 'episode':
            rate = sum(d['chars'] for d in done) / sum(d['secs'] for d in done)
            f_all = min(max(float(cfg['tempo_target']) / rate, lo_hi[0]), lo_hi[1])
        for d in done:
            rate_c = d['chars'] / d['secs']
            d['f'] = f_all if cfg.get('tempo_scope', 'episode') == 'episode' else min(max(float(cfg['tempo_target']) / rate_c, lo_hi[0]), lo_hi[1])
            timing.setdefault('tempo', []).append({'chapter': d['gi'] + 1, 'raw_rate': round(rate_c, 2), 'factor': round(d['f'], 3)})
    if cfg.get('match_chapters', True) and len(done) > 1:
        match_chapters([d['x'] for d in done], timing)
    # one gain for every chapter (keeps them matched): voiced level to `voice_level` (median of voiced 10 ms
    # frames, dBFS), the rare loud syllable caught by a soft limiter instead of turning the whole voice down
    level = float(np.median([voiced_level(d['x']) for d in done])) if done else -24.0
    gain = 10 ** ((float(cfg.get('voice_level', -24.0)) - level) / 20)
    for d in done:
        g, texts, raw, x = d['g'], d['texts'], d['raw'], d['x']
        for (a, b), i, text in zip(d['bounds'], g, texts):
            piece = x[a:b]
            if cap:
                piece = cap_pauses(piece, cap)
            piece = atempo(piece, d.get('f', 1.0), vdir / f'{raw.stem}.tempo')
            piece = soft_limit(piece * gain).astype(np.float32)
            seg = vdir / f'{raw.stem}-s{i - g[0] + 1}.wav'
            write_pcm(seg, piece)
            ok = asr_check(seg, text)
            if ok['ratio'] < 0.85:
                print(f"  ⚠ beat {i + 1}: chapter cut heard 「{ok['heard']}」 ({ok['ratio']:.2f}); check the split")
            timing.setdefault('splits', []).append({'beat': i + 1, 'ratio': ok['ratio']})
            clips[i] = piece
            joined[i] = i != g[0]
    return clips, joined


def run_voice(script: dict, proj: Path, mode_override: str | None = None) -> dict:
    """Return timing: per-beat file/voice windows plus optional narration path."""
    cfg = script.get('voice') or {}
    mode = mode_override or cfg.get('mode', 'placeholder')
    beats = script['beats']
    lead, gap_default = float(cfg.get('lead', 0.3)), float(cfg.get('gap', 0.18))
    vdir = proj / 'voice'
    timing = {'mode': mode, 'beats': [], 'narration': None}

    if mode == 'imported':
        # Pre-mixed audio with measured segments (e.g. a frozen earlier build).
        segs = read_json((proj / cfg['timing']).resolve())
        segs = segs.get('segments', segs)
        if len(segs) != len(beats):
            raise ScriptError(f'imported timing has {len(segs)} segments, script has {len(beats)} beats')
        timing['beats'] = [{k: s[k] for k in ['file_start', 'file_end', 'voice_onset', 'voice_offset']} for s in segs]
        timing['mix'] = str((proj / cfg['mix']).resolve())
        timing['measurement'] = 'imported from frozen build'
        return timing

    clips: list[np.ndarray | None] = []
    joined = [False] * len(beats)
    chapter_mode = mode == 'mimo' and cfg.get('unit') in ('chapter', 'episode')
    if chapter_mode:
        clips, joined = chapter_voice(beats, cfg, vdir, proj, timing, script.get('people') or {})
    if mode == 'mimo' and not chapter_mode:
        # Synthesize (and ASR-check) missing clips in parallel: both are network-bound, so a few
        # concurrent requests cut a 95-line episode from ~11 minutes to a few. The loop below then
        # finds them cached and only handles retries.
        from concurrent.futures import ThreadPoolExecutor
        todo = []
        for i, b in enumerate(beats):
            st = b.get('style', cfg.get('style', ''))
            key = hashlib.sha256(json.dumps([b['say'], cfg.get('provider'), cfg.get('voice'), cfg.get('reference'), st], ensure_ascii=False).encode()).hexdigest()[:12]
            raw = vdir / f'beat-{i:02d}-{key}.wav'
            if not raw.exists():
                todo.append((i, b['say'], raw, st))
        if todo:
            vdir.mkdir(parents=True, exist_ok=True)
            done_n = [0]
            def job(t):
                i, text, raw, st = t
                synthesize(text, raw, cfg, st)
                if cfg.get('asr_check', True):
                    asr_check(raw, text)
                done_n[0] += 1
                report_progress(proj.name, '配音', done_n[0], len(todo), text)
                print(f'  TTS beat {i}: {text}', flush=True)
            with ThreadPoolExecutor(max_workers=int(cfg.get('parallel', 2))) as pool:
                list(pool.map(job, todo))
    breaths = 0
    for i, b in enumerate(beats):
        text = b['say']
        if chapter_mode:
            continue
        if mode == 'placeholder':
            clips.append(None)
            continue
        key = hashlib.sha256(json.dumps([text, cfg.get('provider'), cfg.get('voice'), cfg.get('reference'), b.get('style', cfg.get('style', ''))], ensure_ascii=False).encode()).hexdigest()[:12]
        raw = vdir / f'beat-{i:02d}-{key}.wav'
        if mode == 'files':
            src = (proj / b['audio']).resolve()
            if not src.exists():
                raise ScriptError(f'beat {i}: audio file missing {src}')
            raw = src
        elif not raw.exists():
            vdir.mkdir(parents=True, exist_ok=True)
            report_progress(proj.name, '配音', i, len(beats), text)
            print(f'  TTS beat {i}: {text}', flush=True)
            synthesize(text, raw, cfg, b.get('style', cfg.get('style', '')))
        check = None
        if mode == 'mimo' and cfg.get('asr_check', True):
            check = asr_check(raw, text)
            # TTS sometimes repeats or drops a sentence; re-synthesize instead of shipping it.
            for attempt in range(int(cfg.get('asr_retries', 2))):
                if check['ratio'] >= 0.92:
                    break
                print(f"  ↻ beat {i} ASR {check['ratio']:.2f}, re-synthesizing ({attempt + 1})")
                for f in vdir.glob(f'{raw.stem}*'):
                    f.unlink()
                synthesize(text, raw, cfg, b.get('style', cfg.get('style', '')))
                check = asr_check(raw, text)
        pcm = vdir / f'{raw.stem}.pcm.wav'
        ffmpeg_pcm(raw, pcm)
        speed = float(b.get('speed', cfg.get('speed', 1.0)))
        even = bool(cfg.get('rate')) and 'speed' not in b and mode == 'mimo'
        if even:
            speed = 1.0   # phrase-level re-timing below replaces the fixed speed-up
        if abs(speed - 1.0) > 0.01:
            fast = vdir / f'{raw.stem}.x{speed:.2f}.pcm.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(pcm), '-filter:a', f'atempo={speed}', '-ac', '1', '-ar', '48000', '-sample_fmt', 's16', str(fast)], check=True)
            pcm = fast
        clip = read_pcm(pcm)
        clip = clip / (np.max(np.abs(clip)) or 1) * 0.89
        if cfg.get('clean', mode == 'mimo'):
            cleaned, nb, tail_cut = clean_voice(clip)
            if tail_cut and check:
                # make sure the dropped tail was a sigh, not the last word
                tmp = vdir / f'{raw.stem}.clean.wav'
                write_pcm(tmp, cleaned)
                again = asr_check(tmp, text)
                if again['ratio'] < check['ratio'] - 0.005:
                    print(f"  voice clean: beat {i + 1} tail kept (ASR {again['ratio']:.2f} < {check['ratio']:.2f})")
                    cleaned, nb, _ = clean_voice(clip, tail=False)
            clip = cleaned
            breaths += nb
        if even:
            clip, info = even_out(clip, text, float(cfg['rate']), vdir / f'{raw.stem}.even', pause=float(cfg.get('pause_scale', 1.0)))
            timing.setdefault('speeds', []).append({'beat': i + 1, **info})
        clips.append(clip)
        if check:
            timing.setdefault('asr', []).append({'beat': i + 1, **check})

    t = lead
    pieces = []
    for i, (b, clip) in enumerate(zip(beats, clips)):
        if i and not joined[i]:
            t += float(b.get('pause', gap_default))   # chapter mode: sentences inside a chapter keep their own spoken pauses
        if clip is None:
            d = placeholder_len(b['say'])
            on, off = 0.15, d - 0.12
        else:
            d = len(clip) / 48000
            on, off = voice_bounds(clip)
            pieces.append((t, clip))
        timing['beats'].append({'file_start': round(t, 3), 'file_end': round(t + d, 3), 'voice_onset': round(t + on, 3), 'voice_offset': round(t + off, 3)})
        t += d
    if pieces:
        total = t + 0.05
        nar = np.zeros(int(total * 48000) + 1, dtype=np.float32)
        for start, clip in pieces:
            i = int(round(start * 48000))
            nar[i:i + len(clip)] += clip
        write_pcm(vdir / 'narration.wav', nar)
        timing['narration'] = str(vdir / 'narration.wav')
        timing['measurement'] = '10ms RMS>.004 after peak normalisation; phrase-level, not forced syllable alignment'
        timing['cleaned'] = f'{breaths} breath/noise islands gated out'
        print(f'  voice clean: gated {breaths} breath/noise islands', flush=True)
    else:
        timing['measurement'] = 'placeholder estimate: 0.24 s/char + 0.28 s/pause; NO AUDIO'
    # a placeholder estimate (studio.py check) must never replace a real voice's timing (2026-10-25: a check over
    # eps 18–29 overwrote their MiMo timing.json with estimates)
    old_t = vdir / 'timing.json'
    keep = mode == 'placeholder' and old_t.exists() and json.loads(old_t.read_text(encoding='utf-8')).get('mode') not in (None, 'placeholder')
    if not keep:
        write_json(old_t, timing)
    if timing.get('asr'):
        bad = [a for a in timing['asr'] if a['ratio'] < 0.92]
        lines = ['# 配音听写校对（MiMo ASR）', '', '机器听写与原稿逐句比对；不一致处需真人试听确认（ASR 自身也会出错）。', '',
                 '| 拍 | 一致度 | 原稿 | 听写 | 差异 |', '|---|---|---|---|---|']
        for a in timing['asr']:
            lines.append(f"| {a['beat']} | {a['ratio']:.2f}{' ⚠' if a['ratio'] < 0.92 else ''} | {a['text']} | {a['heard']} | {'；'.join(a['diff'])} |")
        (vdir / 'asr-report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f"  ASR: {len(timing['asr']) - len(bad)}/{len(timing['asr'])} beats match; report {vdir / 'asr-report.md'}")
        for a in bad:
            print(f"  ⚠ beat {a['beat']} heard 「{a['heard']}」 ({'；'.join(a['diff'])})")
    return timing


MUSIC_DIR = ROOT / '03_素材' / '音乐'


def smooth_env(x: np.ndarray, k: int) -> np.ndarray:
    """Moving average (same length, centred) via a cumulative sum: O(n), unlike np.convolve with a long kernel."""
    c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])
    h = k // 2
    i = np.arange(len(x))
    lo, hi = np.clip(i - h, 0, len(x)), np.clip(i - h + k, 0, len(x))
    return ((c[hi] - c[lo]) / k).astype(np.float32)


def music_library() -> dict:
    f = MUSIC_DIR / 'library.json'
    return read_json(f).get('moods', {}) if f.exists() else {}


def music_plan(script: dict, timing: dict) -> list[tuple[float, str]]:
    """[(start_sec, mood)] from `music: {default: 权谋}` plus beat-level `music: 战争` / `music: none` switches."""
    m = script.get('music')
    if not m:
        return []
    m = m if isinstance(m, dict) else {'default': m}
    plan = [(0.0, m.get('default', 'none'))]
    for b, t in zip(script['beats'], timing['beats']):
        if b.get('music'):
            plan.append((max(0.0, t['voice_onset'] - 0.6), b['music']))
    return plan


def music_track(plan: list, n: int, speak: np.ndarray, cfg: dict, sr: int = 48000) -> tuple[np.ndarray, list]:
    """Background music: each mood's track level-matched, looped, crossfaded at switches, ducked under speech."""
    lib = music_library()
    out = np.zeros(n, dtype=np.float32)
    used = []
    fade = int(float(cfg.get('fade', 2.5)) * sr)
    for k, (t0, mood) in enumerate(plan):
        if mood in (None, 'none') or mood not in lib:
            if mood not in (None, 'none'):
                print(f'  ⚠ music mood {mood!r} not in 03_素材/音乐/library.json; silent')
            continue
        i = int(t0 * sr)
        j = int(plan[k + 1][0] * sr) if k + 1 < len(plan) else n
        if i >= n:
            continue
        src_path = MUSIC_DIR / lib[mood]['file']
        tmp = CACHE / 'music' / (src_path.stem + '.pcm.wav')
        tmp.parent.mkdir(parents=True, exist_ok=True)
        if not tmp.exists():
            ffmpeg_pcm(src_path, tmp)
        x = read_pcm(tmp)
        x = x / (float(np.sqrt(np.mean(x[np.abs(x) > 1e-4] ** 2))) or 1) * 10 ** (-20 / 20)   # every track to −20 dBFS RMS first
        seg = np.resize(x, min(n, j + fade) - i).astype(np.float32)
        a = min(fade, len(seg)); seg[:a] *= np.linspace(0, 1, a)
        if j < n:
            b = min(fade, len(seg)); seg[len(seg) - b:] *= np.linspace(1, 0, b)
        out[i:i + len(seg)] += seg
        used.append({'mood': mood, 'file': lib[mood]['file'], 'credit': lib[mood].get('credit', ''), 'start': round(t0, 2)})
    duck = 10 ** (float(cfg.get('duck_db', -8)) / 20)
    out *= 10 ** (float(cfg.get('db', -12)) / 20) * (1 - speak * (1 - duck))
    return out, used


def loudnorm_wav(path: Path, target: float = -16.0, tp: float = -1.5) -> dict | None:
    """Bring the finished mix to one loudness (2026-10-28: the peak-only scaling left 第43集 at -20.5 LUFS, quiet on a
    phone next to other clips, and every episode a few dB apart). One fixed gain to `target` LUFS, then a fast limiter
    at `tp` dB that only shaves the loudest sound-effect peaks, so the voice keeps its dynamics (loudnorm's dynamic
    mode rides the gain and pumps around hits). `voice: loudness:` / `true_peak:` override."""
    def integrated(src):
        r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(src), '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                           capture_output=True, text=True, errors='replace')
        tail = r.stderr[r.stderr.rindex('Integrated loudness'):]
        return float(re.search(r'I:\s*(-?[\d.]+) LUFS', tail).group(1)), float(re.search(r'Peak:\s*(-?[\d.inf]+) dBFS', tail).group(1))
    try:
        before, _ = integrated(path)
        tmp = path.with_name(path.stem + '.norm.wav')
        af = f'volume={target - before:.2f}dB,alimiter=limit={10 ** (tp / 20):.4f}:attack=5:release=60:level=false'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-af', af, '-ar', '48000', '-ac', '1', '-sample_fmt', 's16', str(tmp)], check=True)
        after, peak = integrated(tmp)
        tmp.replace(path)
        return {'target': target, 'before': before, 'after': after, 'true_peak': peak, 'gain_db': round(target - before, 2)}
    except (subprocess.SubprocessError, ValueError, AttributeError, OSError) as e:   # keep the peak-scaled mix rather than fail the build
        print(f"  ⚠ loudness normalisation skipped: {type(e).__name__}", flush=True)
        return None


def mix_audio(timing: dict, duration: float, cfg: dict, out: Path, sfx: list | None = None, music: tuple | None = None) -> dict | None:
    if timing.get('mix'):
        shutil.copy2(timing['mix'], out)
        return {'source': 'imported', 'path': timing['mix'], 'sha256': sha256(out)}
    if not timing.get('narration'):
        return None
    nar = read_pcm(Path(timing['narration']))
    n = int(duration * 48000)
    voice = np.zeros(n, dtype=np.float32)
    voice[: min(n, len(nar))] = nar[:n]
    bed_cfg = cfg.get('bed', 'original')
    gain = 10 ** (float(cfg.get('bed_db', -18)) / 20)
    if bed_cfg == 'none':
        bed = np.zeros(n)
    elif bed_cfg == 'original':
        bed = original_bed(duration, [b['file_start'] for b in timing['beats']])[:n]
    else:
        tmp = out.with_name('bed.pcm.wav')
        ffmpeg_pcm((ROOT / bed_cfg) if not Path(bed_cfg).is_absolute() else Path(bed_cfg), tmp)
        b = read_pcm(tmp)
        bed = np.resize(b, n)
        tmp.unlink()
    # Duck the bed under speech so narration stays on top.
    env = np.ones(n)
    for b in timing['beats']:
        i, j = int(b['voice_onset'] * 48000), int(b['voice_offset'] * 48000)
        env[max(0, i - 9600):j + 9600] = 0.55
    env = smooth_env(env, 4800)
    mix = voice * 0.92 + bed * gain * env
    if sfx:
        # library sounds: trimmed to `len`, faded, and pulled down while someone is speaking
        rules = sfx_cues().get('rules', {})
        speak = np.zeros(n)
        for b in timing['beats']:
            speak[int(b['voice_onset'] * 48000):int(b['voice_offset'] * 48000)] = 1
        speak = smooth_env(speak, 9600)
        for x in sfx:
            src = load_sfx(x['sound'])
            m = int(x['len'] * 48000)
            seg = np.resize(src, m) if x['kind'] == 'bed' and len(src) < m else src[:m].copy()
            bed_like = x['kind'] == 'bed'
            fi = int(float(rules.get('fade_in_bed' if bed_like else 'fade_in', 0.05)) * 48000)
            fo = int(float(rules.get('fade_out_bed' if bed_like else 'fade_out', 0.35)) * 48000)
            if fi:
                seg[:fi] *= np.linspace(0, 1, min(fi, len(seg)))[:len(seg[:fi])]
            if fo:
                k = min(fo, len(seg))
                seg[len(seg) - k:] *= np.linspace(1, 0, k)
            i = int(x['start'] * 48000)
            j = min(n, i + len(seg))
            if i >= n:
                continue
            d = 10 ** (float(rules.get('duck_bed_db' if bed_like else 'duck_hit_db', -4)) / 20)
            mix[i:j] += seg[:j - i] * 10 ** (x['db'] / 20) * (1 - speak[i:j] * (1 - d))
    used = []
    if music and music[0]:
        speak_m = np.zeros(n)
        for b in timing['beats']:
            speak_m[int(b['voice_onset'] * 48000):int(b['voice_offset'] * 48000)] = 1
        speak_m = smooth_env(speak_m, 19200)     # 0.4 s ramps
        mtrack, used = music_track(music[0], n, speak_m, music[1])
        mix = mix + mtrack
    peak = float(np.max(np.abs(mix)))
    if peak > 0.95:
        mix *= 0.95 / peak
    write_pcm(out, mix)
    loud = loudnorm_wav(out, float(cfg.get('loudness', -16)), float(cfg.get('true_peak', -1.5)))
    v_rms = float(np.sqrt(np.mean(voice[np.abs(voice) > 1e-4] ** 2))) if np.any(np.abs(voice) > 1e-4) else 0
    b_rms = float(np.sqrt(np.mean((bed * gain) ** 2))) or 1e-9
    return {'source': 'narration + ' + bed_cfg + (' + music' if used else ''), 'music': used, 'peak': round(min(peak, .95), 4), 'loudness': loud, 'voice_rms_dbfs': round(20 * math.log10(v_rms or 1e-9), 2), 'bed_rms_dbfs': round(20 * math.log10(b_rms), 2), 'sha256': sha256(out)}


# ---------------------------------------------------------------- basemap

def build_raster(proj: Projection, extent, res: float, tone: dict) -> tuple[Image.Image, dict]:
    lon_w, lat_s, lon_e, lat_n = extent
    x0, y0 = proj.world(lon_w, lat_n)
    x1, y1 = proj.world(lon_e, lat_s)
    ow, oh = int((x1 - x0) * res), int((y1 - y0) * res)
    key = hashlib.sha256(json.dumps([proj.lon0, proj.lat0, proj.s, extent, res, tone]).encode()).hexdigest()[:16]
    cached = CACHE / f'relief-{key}.png'
    meta = {'x': round(x0, 2), 'y': round(y0, 2), 'width': round(x1 - x0, 2), 'height': round(y1 - y0, 2), 'pixels': [ow, oh]}
    if cached.exists():
        return Image.open(cached), {**meta, **read_json(cached.with_suffix('.json'))}
    canvas = Image.new('RGBA', (ow, oh))
    used = []
    for z, dirs in TILE_DIRS.items():
        n = 256 * 2 ** z
        k = n / (2 * math.pi * proj.s)
        gx0 = n * (proj.lon0 + 180) / 360 + k * (x0 - W / 2)
        gy0 = n * (math.pi - proj.m0) / (2 * math.pi) + k * (y0 - H / 2)
        gx1, gy1 = gx0 + k * ow / res, gy0 + k * oh / res
        tx0, tx1, ty0, ty1 = int(gx0 // 256), int(gx1 // 256), int(gy0 // 256), int(gy1 // 256)
        files = {}
        for d in dirs:
            for p in (TILES / d).glob(f'*_{z}_*_*.jpg'):
                tx, ty = map(int, p.stem.split('_')[-2:])
                if tx0 <= tx <= tx1 and ty0 <= ty <= ty1:
                    files.setdefault((tx, ty), p)
        if not files:
            continue
        mx, my = min(t[0] for t in files), min(t[1] for t in files)
        sheet = Image.new('RGBA', ((max(t[0] for t in files) - mx + 1) * 256, (max(t[1] for t in files) - my + 1) * 256))
        for (tx, ty), p in files.items():
            sheet.paste(Image.open(p).convert('RGBA'), ((tx - mx) * 256, (ty - my) * 256))
            used.append({'path': str(p.relative_to(ROOT)), 'z': z})
        layer = sheet.transform((ow, oh), Image.Transform.AFFINE, (k / res, 0, gx0 - mx * 256, 0, k / res, gy0 - my * 256), Image.Resampling.BICUBIC)
        canvas = Image.alpha_composite(canvas, layer)
    alpha = np.asarray(canvas.getchannel('A'))
    uncovered = float((alpha < 255).mean())
    paper = Image.new('RGB', canvas.size, THEME['paper'])
    rgb = Image.composite(canvas.convert('RGB'), paper, canvas.getchannel('A'))
    rgb = ImageEnhance.Color(rgb).enhance(tone.get('saturation', 0.28))
    rgb = ImageEnhance.Contrast(rgb).enhance(tone.get('contrast', 1.1))
    rgb = Image.blend(rgb, Image.new('RGB', rgb.size, tone.get('tint', '#d8bda0')), tone.get('tint_mix', 0.22))
    CACHE.mkdir(exist_ok=True)
    rgb.save(cached)
    info = {'uncovered_fraction': round(uncovered, 4), 'tiles': len(used), 'zooms': sorted({u['z'] for u in used})}
    write_json(cached.with_suffix('.json'), info)
    return rgb, {**meta, **info}


def project_lines(proj: Projection, geo: dict, extent, simplify=1.5) -> list[dict]:
    lon_w, lat_s, lon_e, lat_n = extent
    out = []
    for f in geo['features']:
        g = f['geometry']
        lines = [g['coordinates']] if g['type'] == 'LineString' else g['coordinates']
        parts = []
        for line in lines:
            if not any(lon_w - 2 <= x <= lon_e + 2 and lat_s - 2 <= y <= lat_n + 2 for x, y in line):
                continue
            pts, last = [], None
            for x, y in line:
                q = proj.world(x, y)
                if last is None or math.hypot(q[0] - last[0], q[1] - last[1]) >= simplify:
                    pts.append(q)
                    last = q
            if len(pts) > 1:
                parts.append('M ' + ' L '.join(f'{a:.1f} {b:.1f}' for a, b in pts))
        if parts:
            out.append({'name': (f.get('properties') or {}).get('name', ''), 'path': ' '.join(parts)})
    return out


def ne10_rivers(max_rank: int = 6) -> dict:
    """Natural Earth 10m rivers as GeoJSON-like dict, major channels only (scalerank ≤ max_rank)."""
    import shapefile
    r = shapefile.Reader(str(ROOT / '02_数据' / '开放地理数据' / 'naturalearth' / 'ne_10m_rivers_lake_centerlines' / 'ne_10m_rivers_lake_centerlines.shp'), encoding='utf-8')
    feats = []
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        if (rec.get('scalerank') or 99) > max_rank:
            continue
        pts, parts = sr.shape.points, list(sr.shape.parts) + [len(sr.shape.points)]
        lines = [[list(p) for p in pts[a:b]] for a, b in zip(parts, parts[1:])]
        feats.append({'properties': {'name': rec.get('name_zh') or rec.get('name') or ''}, 'geometry': {'type': 'MultiLineString', 'coordinates': lines}})
    return {'features': feats}


def project_polygons(proj: Projection, geo: dict) -> str:
    rings = []
    for f in geo['features']:
        g = f['geometry']
        polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates'] if g['type'] == 'MultiPolygon' else []
        for poly in polys:
            for ring in poly:
                rings.append('M ' + ' L '.join('%.1f %.1f' % proj.world(x, y) for x, y in ring) + ' Z')
    return ' '.join(rings)


# ---------------------------------------------------------------- compiler

PUNCT = '，。！？；：、,.!?;:'


def split_captions(say: str, max_len: int = 16, min_len: int = 5) -> list[str]:
    """Clause-level subtitle chunks like the reference videos (avg ~9 chars)."""
    parts, cur = [], ''
    for ch in say:
        cur += ch
        if ch in '，。！？；：,.!?;:':
            parts.append(cur)
            cur = ''
    if cur.strip():
        parts.append(cur)
    out = []
    for p in parts:
        if out and len(out[-1].rstrip(PUNCT)) + len(p.rstrip(PUNCT)) <= max_len and len(out[-1].rstrip(PUNCT)) < min_len:
            out[-1] += p
        else:
            out.append(p)
    final = []
    for p in out:
        while len(p.rstrip(PUNCT)) > max_len + 2:   # hard-wrap very long clauses
            final.append(p[:max_len])
            p = p[max_len:]
        final.append(p)
    clean = lambda t: re.sub(r'[，。；：、,.;:]+$', '', t).strip()
    return [caption_digits(clean(p)) for p in final if clean(p)]


CN_NUM = {c: i for i, c in enumerate('零一二三四五六七八九')}


def cn_to_int(t: str) -> int | None:
    if not t or any(c not in '零一二三四五六七八九十百千两' for c in t):
        return None
    if '十' not in t and '百' not in t and '千' not in t:   # 一九零 style
        return int(''.join(str(CN_NUM.get(c, 2)) for c in t))
    total, cur = 0, 0
    for c in t:
        if c in '十百千':
            total += (cur or 1) * {'十': 10, '百': 100, '千': 1000}[c]
            cur = 0
        else:
            cur = 2 if c == '两' else CN_NUM[c]
    return total + cur


def caption_digits(text: str) -> str:
    """Spoken '公元一百九十年' → on-screen '公元190年' (also 月, 万)."""
    def sub(m):
        if m.group(1) in ('一', '两'):          # 这一年 / 一年之内 / 两年后 read better as words
            return m.group(0)
        # years: digits only for 公元/前 years or long numbers (一百八十九年); 中平六年, 六年后 stay words
        if m.group(2) == '年' and len(m.group(1)) < 3 and not text[max(0, m.start() - 2):m.start()].endswith(('公元', '前')):
            return m.group(0)
        n = cn_to_int(m.group(1))
        return (str(n) if n is not None else m.group(1)) + m.group(2)
    # not after 几/数/好/上/多: 几十年、数十年 stay words (else 几10年)
    return re.sub(r'(?<![几数好上多])([零一二三四五六七八九十百千两]{1,6})(年|月)', sub, text)


def cue_time(say: str, word: str, onset: float, offset: float) -> float | None:
    """Approximate time a word is spoken: proportional position within the line."""
    i = say.find(word)
    if i < 0:
        return None
    spoken = [c for c in say if c not in PUNCT and not c.isspace()]
    before = len([c for c in say[:i] if c not in PUNCT and not c.isspace()])
    return onset + (offset - onset) * before / max(1, len(spoken))


class Compiler:
    def __init__(self, script: dict, path: Path, reg: Registry):
        self.s, self.path, self.reg = script, path, reg
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.year = int(script.get('year', 0))
        self.place_recs: dict[str, dict | None] = {}   # place key -> gazetteer record whose rank changes by date
        m = script.get('map') or {}
        self.proj_center = m.get('center', [111.5, 34.0])
        self.proj = Projection(self.proj_center, float(m.get('scale', 12000)))
        self.places: dict[str, dict] = {}
        self.used_sources: set[str] = set()
        self.last_focus = None
        self.sfx: list[dict] = []

    def add_sfx(self, item, start: float, end: float, ctx: str) -> None:
        """Queue a sound from the vocabulary. `item` is a cue name or {name, delay, len, db, at: end}."""
        spec = {'name': item} if isinstance(item, str) else dict(item or {})
        name = spec.get('name') or spec.get('text')
        voc = sfx_cues()
        cue = voc['cues'].get(name)
        if not cue:
            self.err(f'{ctx}: unknown sfx「{name}」(see 03_素材/音效/cues.json)')
            return
        t0 = (end if spec.get('at') == 'end' else start) + float(spec.get('delay', 0))
        length = float(spec.get('len') or cue['len'] or max(1.0, end - t0))
        if cue['kind'] == 'bed':
            length = min(length, float(voc['rules'].get('max_bed', 8)))
        self.sfx.append({'name': name, 'sound': cue['sound'], 'kind': cue['kind'], 'start': round(max(0.0, t0), 3),
                         'len': round(length, 3), 'db': float(spec.get('db', cue['db']))})

    def sfx_after_cooldown(self) -> list[dict]:
        """The sounds that survive the cooldown (same sound twice within `cooldown` s: the later one is dropped)."""
        cool = float(sfx_cues().get('rules', {}).get('cooldown', 6))
        kept: list[dict] = []
        for x in sorted(self.sfx, key=lambda x: x['start']):
            if not any(k['sound'] == x['sound'] and x['start'] - k['start'] < cool for k in kept):
                kept.append(x)
        return kept

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    # -- places
    def resolve_places(self):
        for key, spec in (self.s.get('places') or {}).items():
            spec = {'id': spec} if isinstance(spec, str) else dict(spec or {})
            if 'lon' in spec:
                for need in ['lat', 'precision', 'source']:
                    if not spec.get(need):
                        self.err(f'place {key}: local coordinates need `{need}`')
                rec = {'id': f'local:{key}', 'coordinates': [spec.get('lon', 0), spec.get('lat', 0)], 'coordinatePrecision': spec.get('precision', ''), 'coordinateSource': spec.get('source', ''), 'coordinateStatus': 'approximate'}
            else:
                rec = self.reg.place(spec.get('id', key))
                if not rec:
                    self.err(f'place {key}: not in maindata places (id/alias `{spec.get("id", key)}`); add it to maindata or declare lon/lat/precision/source')
                    continue
            lon, lat = rec['coordinates']
            x, y = self.proj.world(lon, lat)
            # Script's own key wins when it is Chinese (the author chose it, usually simplified);
            # then the period name for this year; then any Chinese alias.
            name = (spec.get('name') or year_value(rec.get('names'), self.year, 'text')
                    or (key if re.match(r'[一-鿿]', key) else None)
                    or next((a for a in rec.get('aliases', []) if re.match(r'[一-鿿]', a)), key))
            # researched ranks (auditBatch) beat the episode's own `tier:` — the old scripts marked 成都、长安 capital
            # for whole episodes; an episode tier is kept for places nobody has researched yet
            audited = any('auditBatch' in t for t in rec.get('tiers') or [])
            in_year = {tier_at(rec, self.year, mo) for mo in range(1, 13)}
            if spec.get('tier') and audited and LEGACY_TIER.get(spec['tier'], spec['tier']) not in in_year:
                self.warn(f"place {key}: 脚本写 tier: {spec['tier']}，地点库（第12批考证）这一年是 {'/'.join(sorted(in_year))}，以地点库为准；"
                          f"确有事件依据就去掉脚本里的 tier 并补进 gazetteer")
            if rec['id'].startswith('region_'):
                tier = 'region'
            elif spec.get('tier') and not audited:
                tier = LEGACY_TIER.get(spec['tier'], spec['tier'])
                tier = tier if tier in TIERS else 'county'
            else:
                tier = tier_at(rec, self.year, 12)
            self.place_recs[key] = None if spec.get('tier') and not audited else rec
            if 'UNVERIFIED' in rec.get('coordinatePrecision', '') or not rec.get('coordinateSource'):
                self.warn(f'place {key}: coordinate not curated ({rec["id"]}); shown as 示意点, verify before release')
            approx = rec.get('coordinateStatus') == 'approximate' or 'approx' in rec['id'] or 'approximate' in rec.get('coordinatePrecision', '')
            self.places[key] = {
                'id': key, 'ref': rec['id'], 'name': name, 'x': round(x, 2), 'y': round(y, 2), 'lon': lon, 'lat': lat,
                'precision': rec.get('coordinatePrecision', ''), 'source': rec.get('coordinateSource', ''), 'tier': tier, 'approx': approx,
                'detail': spec.get('detail', ''), 'label': spec.get('label', 'right'), 'show': spec.get('show', 'always'),
            }

    def P(self, key, ctx) -> str | None:
        if key in self.places:
            return key
        self.err(f'{ctx}: place `{key}` is not declared in `places`')
        return None

    # -- sources
    def check_sources(self, ids, ctx, required=True):
        local = {s['id']: s for s in self.s.get('sources_local', []) or []}
        if not ids and required:
            self.err(f'{ctx}: missing `sources`')
        for i in ids or []:
            if i in local or i in self.reg.citations:
                self.used_sources.add(i)
            else:
                self.err(f'{ctx}: source `{i}` not in maindata/citations.json or sources_local')

    def source_label(self):
        local = {s['id']: s for s in self.s.get('sources_local', []) or []}
        works: dict[str, list[str]] = {}
        for i in sorted(self.used_sources):
            c = local.get(i) or self.reg.citations[i]
            if c.get('type', '史书') != '史书' and i not in local:
                continue
            works.setdefault(c['work'], [])
            vol = re.sub(r'^卷', '', (c.get('volume') or '').split('·')[0]).strip()
            if vol and vol not in works[c['work']]:
                works[c['work']].append(vol)
        # Compact for the footer: 《三国志》卷一、九、四十六. Full titles are in review.md.
        return ' '.join(f'《{w}》' + ('卷' + '、'.join(v) if v else '') for w, v in works.items())

    # -- time helpers
    def until(self, spec, i, beats_t, duration, start, ctx):
        if spec is None or spec == 'beat':
            return beats_t[i]['end']
        if spec == 'end':
            return duration
        if isinstance(spec, (int, float)):
            return start + float(spec)
        m = re.fullmatch(r'beat\+(\d+)', str(spec))
        if m:
            j = i + int(m.group(1))
            if j >= len(beats_t):
                self.err(f'{ctx}: until `{spec}` runs past the last beat')
                return duration
            return beats_t[j]['end']
        self.err(f'{ctx}: bad until `{spec}` (beat | beat+N | end | seconds)')
        return beats_t[i]['end']

    # -- camera
    def focus_state(self, cam, prev, ctx):
        keys = cam.get('focus')
        keys = [keys] if isinstance(keys, str) else list(keys or [])
        pts = [self.places[k] for k in keys if self.P(k, ctx)]
        if not pts:
            return prev
        xs, ys = [p['x'] for p in pts], [p['y'] for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        z = cam.get('zoom')
        if z is None or z == 'fit':
            if len(pts) > 1:
                bw, bh = max(80, max(xs) - min(xs)), max(60, max(ys) - min(ys))
                z = min((W - 420) / bw, (H - 400) / bh, 3.2)   # never punch in harder than battle scale
            else:
                z = prev['z']
        z = max(0.3, min(30.0, float(z)))   # up to 30x for very local events (高平陵 ~20 km from 洛阳; 小平津→北邙 ~15 km)
        sx, sy = cam.get('shift', [0, 0])
        return {'cx': round(cx - sx / z, 2), 'cy': round(cy - sy / z, 2), 'z': round(z, 4)}

    DYNASTY_ALIAS = {'魏': 'cao_wei', '曹魏': 'cao_wei', '蜀': 'shu_han', '蜀汉': 'shu_han', '汉': 'eastern_han', '东汉': 'eastern_han',
                     '吴': 'sun_wu', '孙吴': 'sun_wu', '东吴': 'sun_wu', '晋': 'western_jin', '西晋': 'western_jin', '东晋': 'eastern_jin'}

    def era_text(self, year: int, dynasty: str | None = None) -> str:
        """301 → '永宁元年|公元301年' from maindata/chronology.json.

        Concurrent states (三国) each have their own eras: `dynasty` (魏/蜀/吴…, from the
        script's era_dynasty or a beat's) picks one; otherwise the era still in use at year end."""
        if not hasattr(self, '_eras'):
            self._eras = read_json(MAINDATA / 'chronology.json')['eras']
        hits = [e for e in self._eras if e['from'] <= year <= e['to']]
        want = self.DYNASTY_ALIAS.get(dynasty, dynasty) if dynasty else None
        if want and any(e.get('dynasty') == want for e in hits):
            hits = [e for e in hits if e.get('dynasty') == want]
        elif not want:
            # Default to the 汉→魏→晋 sequence used by 《资治通鉴》 when states run in parallel.
            main = [e for e in hits if e.get('dynasty') in ('eastern_han', 'cao_wei', 'western_jin', 'eastern_jin')]
            hits = main or hits
        ce = f'公元{year}年' if year > 0 else f'公元前{-year}年'
        if not hits:
            return ce
        # Several eras in one year (改元/僭号): prefer the one still in use at year end, then the later start.
        e = max(hits, key=lambda x: (x['to'], x['from']))
        n = year - e['from'] + 1
        num = '元' if n == 1 else cn_number(n)
        return f"{e['name']}{num}年|{ce}"

    def atlas_rivers(self, extent) -> list:
        """atlas look: Natural Earth river centrelines (public domain) as vector paths, so they keep a fixed screen
        width at any zoom; `rank` = scalerank (0 = biggest)."""
        import shapefile
        import basemap_dem
        lon_w, lat_s, lon_e, lat_n = extent or [100, 24, 124, 42]
        out = []
        r = shapefile.Reader(str(basemap_dem.NE / 'ne_10m_rivers_lake_centerlines' / 'ne_10m_rivers_lake_centerlines.shp'), encoding='utf-8')
        for sr in r.iterShapeRecords():
            rank = sr.record.as_dict().get('scalerank') or 99
            if rank > 9:
                continue
            bx0, by0, bx1, by1 = sr.shape.bbox
            if bx1 < lon_w or bx0 > lon_e or by1 < lat_s or by0 > lat_n:
                continue
            pts, parts = sr.shape.points, list(sr.shape.parts) + [len(sr.shape.points)]
            for a, b in zip(parts, parts[1:]):
                line, last = [], None
                for lon, lat in pts[a:b]:
                    x, y = self.proj.world(lon, lat)
                    if last is None or abs(x - last[0]) + abs(y - last[1]) > 1.5:
                        line.append((x, y))
                        last = (x, y)
                if len(line) > 1:
                    out.append({'name': str(sr.record.as_dict().get('name') or ''), 'rank': rank, 'path': 'M' + 'L'.join(f'{x:.1f} {y:.1f}' for x, y in line)})
        man = HERE / 'data' / 'atlas-rivers-manual.json'      # 泗、沂、汴、涡、济: 汉末 waterways Natural Earth lacks (示意)
        if man.exists():
            for rv in json.loads(man.read_text(encoding='utf-8'))['rivers']:
                if any(lon_w <= lon <= lon_e and lat_s <= lat <= lat_n for lon, lat in rv['points']):
                    raw = [self.proj.world(lon, lat) for lon, lat in rv['points']]
                    # Catmull-Rom through the hand points, so the waterway curves like a river instead of a ruled line
                    pts = []
                    for i in range(len(raw) - 1):
                        p0, p1, p2, p3 = raw[max(0, i - 1)], raw[i], raw[i + 1], raw[min(len(raw) - 1, i + 2)]
                        for k in range(8):
                            u = k / 8
                            pts.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * u + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * u * u
                                                     + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * u ** 3) for j in (0, 1)))
                    pts.append(raw[-1])
                    out.append({'name': rv['name'], 'rank': rv['rank'], 'path': 'M' + 'L'.join(f'{x:.1f} {y:.1f}' for x, y in pts)})
        return out

    def atlas_features(self) -> list:
        """atlas look: big spaced mountain / river / sea names (data/atlas-labels.json) in world coordinates."""
        f = HERE / 'data' / 'atlas-labels.json'
        if not f.exists():
            return []
        out = []
        for L in json.loads(f.read_text(encoding='utf-8'))['labels']:
            x, y = self.proj.world(L['lon'], L['lat'])
            out.append({'name': L['name'], 'kind': L['kind'], 'x': round(x, 1), 'y': round(y, 1), 'v': bool(L.get('v'))})
        return out

    def person(self, ref, ctx) -> dict:
        """Resolve `who:` → {key, name, title, role, faction, image, base}.

        Order: episode `people:` table → maindata persons (id / alias) → plain name."""
        people = self.s.get('people') or {}
        if isinstance(ref, dict):
            spec = dict(ref)
            key = spec.get('who') or spec.get('name')
        else:
            spec, key = {}, ref
        base = dict(people.get(key) or {})
        pid = base.get('person') or spec.get('person') or key
        rec = self.reg.persons.get(pid) or next((p for p in self.reg.persons.values() if key in p.get('aliases', [])), None)
        out = {'key': key, 'name': key, 'title': '', 'role': '', 'faction': None, 'image': None, 'base': None, 'faces': 'right'}
        if rec:
            out.update(name=rec['names']['formal'], title=rec['names'].get('title', ''), image=f"portraits/{rec['id']}.png")
        out.update({k: v for k, v in base.items() if k in out or k in ('display',)})
        out.update({k: v for k, v in spec.items() if k in ('name', 'title', 'role', 'faction', 'image', 'base', 'display', 'faces')})
        if out.get('display'):
            out['name'] = out['display']
        if not out['name']:
            self.err(f'{ctx}: person `{key}` has no name')
        return out

    def faction_color(self, faction) -> dict:
        terr = (self.s.get('territory') or {}).get('polities') or {}
        if faction in terr:
            from palette import build as _pal
            slots = {e['slot']: e for e in _pal()['slots']}
            e = slots.get((terr[faction] or {}).get('slot')) or {}
            return {'fill': e.get('fill', '#c9a27e'), 'edge': e.get('edge', '#6d4b12'), 'flag': e.get('flag', '#8a281c')}
        col = (self.s.get('factions') or {}).get(faction)
        if col:
            hx = COLORS.get(col, col)
            return {'fill': hx, 'edge': hx, 'flag': hx}
        return {'fill': '#c9a27e', 'edge': '#7a5a32', 'flag': '#8a281c'}

    # -- composite narrative actions: one script line -> a timed sequence of
    #    flags, marks, territory change and camera moves
    def expand_composites(self, beats: list) -> list:
        import copy
        out, last_owners, last_year = [], None, None
        m = self.s.get('map') or {}
        for i, b in enumerate(beats):
            b = copy.deepcopy(b)
            show, extra = [], []
            for item in b.get('show') or []:
                if not (isinstance(item, dict) and len(item) == 1 and 'takeover' in item):
                    show.append(item)
                    continue
                sp = dict(item['takeover'] or {})
                ctx = f'beat {i + 1} takeover'
                at, to, frm = sp.get('at'), sp.get('to'), sp.get('from')
                if not at or not to:
                    self.err(f'{ctx}: needs `at` (城) and `to` (新控制者)')
                    continue
                cue = sp.get('cue')
                anchor = {'cue': cue} if cue else {'delay': 0.4}
                d0 = 0.0 if cue else 0.4
                col_to = self.faction_color(to)['flag']
                # 1 old banner sinks
                if frm:
                    show.append({'retire': {'at': at, 'name': sp.get('from_name', frm), 'color': self.faction_color(frm)['flag'], **anchor}})
                # 2 the city flashes into the new colour and keeps it
                show.append({'capture': {'at': at, 'faction': to, 'text': sp.get('text', '易手'), **anchor, 'delay': d0 + 0.5, 'until': sp.get('until', 'end')}})
                # 3 new banner rises
                show.append({'flag': {'at': at, 'name': sp.get('name', to), 'sub': sp.get('sub'), 'color': col_to, 'side': sp.get('side', 'right'),
                                      **anchor, 'delay': d0 + 1.3, 'until': sp.get('hold', 'beat+2' if i + 2 < len(beats) else 'end')}})
                # 4 territory: only commanderies named in `gain` change hands (no invented borders)
                gain = sp.get('gain') or []
                if gain:
                    if last_owners is None and 'owners' not in b:
                        self.err(f'{ctx}: `gain` needs an earlier beat with `owners`')
                    else:
                        base = copy.deepcopy(b.get('owners') or last_owners)
                        for k in base:
                            base[k] = [n for n in (base[k] or []) if n not in gain]
                        base.setdefault(to, [])
                        base[to] = list(base[to]) + list(gain)
                        b['owners'] = base
                        if cue:
                            b['owners_cue'] = cue
                        b['owners_delay'] = d0 + 0.8
                        b['owners_origin'] = at
                # 5 camera: push in on the city before the moment, pull back after it
                if sp.get('camera', True) is not False and 'camera' not in b:
                    close = float(sp.get('zoom', float(m.get('focus_zoom', 2.0)) + 0.4))
                    pull = sp.get('pull', max(0.9, close - 1.2))
                    pull_focus = sp.get('pull_focus') or ([at] + [x for x in (sp.get('context') or [])])
                    b['camera'] = [{'focus': at, 'zoom': close, 'move': 1.2, **({'cue': cue, 'delay': -1.3} if cue else {})},
                                   {'focus': pull_focus if len(pull_focus) > 1 else at, 'zoom': pull, 'move': 2.0, **({'cue': cue, 'delay': 2.6} if cue else {'delay': 3.0})}]
            # meanwhile: hand the viewer's eye from one place to another along a line
            showm = []
            for item in show:
                if not (isinstance(item, dict) and len(item) == 1 and 'meanwhile' in item):
                    showm.append(item)
                    continue
                sp = dict(item['meanwhile'] or {})
                ctx = f'beat {i + 1} meanwhile'
                frm, to = sp.get('from'), sp.get('to')
                if not frm or not to or not self.P(frm, ctx) or not self.P(to, ctx):
                    self.err(f'{ctx}: needs `from` (当前地点) and `to` (另一边)')
                    continue
                cue = sp.get('cue')
                anchor = {'cue': cue} if cue else {}
                col = self.faction_color(sp['faction'])['flag'] if sp.get('faction') else None
                showm.append({'arrow': {'from': frm, 'to': to, 'kind': 'relation', 'grow': 1.7, 'stop': 'near', 'bend': 0.1, 'label': sp.get('text'),
                                        **({'color': col} if col else {}), **anchor, 'delay': 0.1, 'until': sp.get('hold', 'beat')}})
                showm.append({'spot': {'at': to, **({'text': sp['spot']} if sp.get('spot') else {}), **anchor, 'delay': 1.6, 'for': 2.6}})
                if sp.get('flag'):
                    fl = dict(sp['flag'])
                    showm.append({'flag': {'at': to, **fl, **anchor, 'delay': 2.0, 'until': fl.get('until', 'beat+1' if i + 1 < len(beats) else 'end')}})
                if 'camera' not in b:
                    a, z = self.places[frm], self.places[to]
                    dx, dy = a['x'] - z['x'], a['y'] - z['y']
                    n = math.hypot(dx, dy) or 1
                    # end on the new place but keep the old one at the frame's edge
                    b['camera'] = [{'focus': frm, 'zoom': 'x1', 'move': 0.6},
                                   {'focus': to, 'zoom': 'x1', 'shift': [round(-dx / n * 470), round(-dy / n * 250)], 'move': 1.9, **anchor, 'delay': 0.3 if not cue else 0.2}]
            show = showm

            # yearshift: hold the camera, flip the year, let the old borders linger as a ghost
            show0 = []
            for item in show:
                if not (isinstance(item, dict) and len(item) == 1 and 'yearshift' in item):
                    show0.append(item)
                    continue
                sp = dict(item['yearshift'] or {})
                ctx = f'beat {i + 1} yearshift'
                to = sp.get('to') or b.get('year')
                frm = sp.get('from') or last_year
                if not to or not frm:
                    self.err(f'{ctx}: needs `to` (新年份); `from` defaults to the previous beat\'s year')
                    continue
                if 'owners' not in b:
                    self.err(f'{ctx}: put the new `owners` on this beat')
                b.setdefault('year', to)
                cue = sp.get('cue')
                anchor = {'cue': cue} if cue else {}
                show0.append({'yearflip': {'from': frm, 'to': to, **anchor, 'for': float(sp.get('card', 3.0))}})
                if cue:
                    b['year_cue'] = cue
                b['year_delay'] = 0.9
                if cue:
                    b['owners_cue'] = cue
                b['owners_delay'] = 1.0
                b['owners_ghost'] = float(sp.get('ghost', 6.0))
                if 'camera' not in b:
                    b['camera'] = []          # the map stays put so viewers compare like with like
            show = show0

            show1 = []
            for item in show:
                if not (isinstance(item, dict) and len(item) == 1 and 'defect' in item):
                    show1.append(item)
                    continue
                sp = dict(item['defect'] or {})
                ctx = f'beat {i + 1} defect'
                who, at, to = sp.get('who'), sp.get('at'), sp.get('to')
                if not who or not at or not to:
                    self.err(f'{ctx}: needs `who` (人物/旗牌名), `at` (所在地) and `to` (新归属)')
                    continue
                cue = sp.get('cue')
                anchor = {'cue': cue} if cue else {}
                d0 = 0.0 if cue else 0.5
                col_to = self.faction_color(to)['flag']
                col_from = self.faction_color(sp.get('from', who))['flag']
                hold = sp.get('hold', 'beat+2' if i + 2 < len(beats) else 'end')
                # 1 a line to the side they join (its leader's seat), labelled with what happened
                if sp.get('joins'):
                    show1.append({'arrow': {'from': at, 'to': sp['joins'], 'kind': 'relation', 'color': col_to, 'label': sp.get('text'), 'grow': 1.2, 'stop': 'near', 'bend': 0.12, **anchor, 'delay': d0, 'until': hold}})
                # 2 the banner turns over into the new colour
                show1.append({'turn': {'at': at, 'name': sp.get('name', who), 'color': col_to, 'from_color': col_from, 'sub': sp.get('sub'), 'from_sub': sp.get('from_sub'), **anchor, 'delay': d0 + 0.7, 'until': hold}})
                # 3 a small seal on the place: 归 / 降 / 叛 / 让 …
                if sp.get('verb', '归'):
                    show1.append({'stamp': {'at': at, 'text': sp.get('verb', '归'), **anchor, 'delay': d0 + 1.1, 'for': 2.2}})
                # 4 territory, only where sources support it
                gain = sp.get('gain') or []
                if gain:
                    if last_owners is None and 'owners' not in b:
                        self.err(f'{ctx}: `gain` needs an earlier beat with `owners`')
                    else:
                        base = copy.deepcopy(b.get('owners') or last_owners)
                        for k in base:
                            base[k] = [n for n in (base[k] or []) if n not in gain]
                        base = {k: v for k, v in base.items() if v}
                        base[to] = list(base.get(to, [])) + list(gain)
                        b['owners'] = base
                        if cue:
                            b['owners_cue'] = cue
                        b['owners_delay'] = d0 + 1.0
                        b['owners_origin'] = at
                # 5 camera: frame both sides, then settle on the new bloc
                if 'camera' not in b and sp.get('camera', True) is not False:
                    pair = [at] + ([sp['joins']] if sp.get('joins') else [])
                    b['camera'] = [{'focus': pair, 'zoom': 'fit', 'move': 1.4, **({'cue': cue, 'delay': -1.4} if cue else {})}]
            show = show1

            show2 = []
            for item in show:
                if not (isinstance(item, dict) and len(item) == 1 and 'campaign' in item):
                    show2.append(item)
                    continue
                sp = dict(item['campaign'] or {})
                ctx = f'beat {i + 1} campaign'
                at, sides, clash_cue = sp.get('at'), sp.get('sides') or [], sp.get('clash')
                if not at or len(sides) < 2 or not clash_cue:
                    self.err(f'{ctx}: needs `at` (战场), two `sides` [{{from, faction}}…] and `clash` (交战时的台词关键词)')
                    continue
                for k, sd in enumerate(sides):
                    if sd.get('from'):
                        show2.append({'army': {'from': sd['from'], 'to': at, 'faction': sd['faction'], 'banner': sd.get('banner'), 'troops': sd.get('troops', 'infantry'),
                                               **{k: sd[k] for k in ('head', 'unit') if sd.get(k)},
                                               'size': sd.get('size', 2.5), 'stop': 'approach', 'delay': 0.2 + 0.35 * k, 'arrive': clash_cue, 'end_cue': clash_cue, 'end_delay': 0.35}})
                show2.append({'clash': {'at': at, 'sides': [{'faction': sd['faction'], 'from': sd.get('from'), 'troops': sd.get('troops', 'infantry'), 'banner': sd.get('banner')} for sd in sides], 'trace': sp.get('trace', 14),
                                        'title': sp.get('title'), 'cue': clash_cue, 'until': sp.get('hold', 'beat+1' if i + 1 < len(beats) else 'end')}})
                loser = sp.get('loser')
                if loser and sp.get('rout_cue'):
                    lsd = next((sd for sd in sides if sd['faction'] == loser), None)
                    if lsd:
                        show2.append({'rout': {'at': at, 'to': sp.get('retreat') or lsd.get('from'), 'faction': loser, 'troops': lsd.get('troops', 'infantry'), 'banner': lsd.get('banner'), 'cue': sp['rout_cue'], 'delay': 0.2,
                                               **{k: lsd[k] for k in ('head', 'unit') if lsd.get(k)}}})
                if 'camera' not in b and sp.get('camera', True) is not False:
                    starts = [sd['from'] for sd in sides if sd.get('from')]
                    b['camera'] = [{'focus': [at, *starts], 'zoom': 'fit', 'move': 1.4},
                                   {'focus': at, 'zoom': sp.get('zoom', 'x1.35'), 'move': 1.0, 'cue': clash_cue, 'delay': -0.6}]
            show = show2
            # a `rout` without its own camera: widen to show where the survivors run
            for item in show:
                if isinstance(item, dict) and len(item) == 1 and 'rout' in item and 'camera' not in b:
                    rs = item['rout'] or {}
                    if rs.get('at') and rs.get('to'):
                        b['camera'] = {'focus': [rs['at'], rs['to']], 'zoom': 'fit', 'move': 1.8, **({'cue': rs['cue'], 'delay': 0.6} if rs.get('cue') else {})}
            if show or b.get('show'):
                b['show'] = show
            if 'owners' in b:
                last_owners = b['owners']
            if str(b.get('year', '')).isdigit():
                last_year = int(b['year'])
            out.append(b)
        return out

    def minimap_box(self):
        """World box for the corner overview map (shown when the camera pushes in to battle scale).
        `map.minimap: false` turns it off; `{zoom: 2.6, focus: [..]}` tunes when and what it shows."""
        mm = (self.s.get('map') or {}).get('minimap', True)
        if mm is False:
            return None
        mm = mm if isinstance(mm, dict) else {}
        keys = mm.get('focus') or list(self.places)
        pts = [self.places[k] for k in keys if k in self.places]
        if not pts:
            return None
        xs, ys = [p['x'] for p in pts], [p['y'] for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        w = max((max(xs) - min(xs)) * 2.4, (max(ys) - min(ys)) * 2.4 * 1.45, float(mm.get('min_width', 1500)))
        h = w / 1.45
        return {'x': round(cx - w / 2, 1), 'y': round(cy - h / 2, 1), 'width': round(w, 1), 'height': round(h, 1), 'zoom': float(mm.get('zoom', 2.3))}

    ARROW_PX_S = 170   # warm: steady drawing speed on screen (地图知天下 draws ~110–150 px/s; 2026-10-24)

    def pace_arrows(self, elements, keys, duration):
        """map.palette: warm — an arrow draws at a steady on-screen speed instead of a fixed 1.6–2 s, so a long march
        takes longer than a short hop (ours measured 250–970 px/s against the reference's ~130). Never faster than
        before (a script's `grow:` counts as the minimum), at most 4.5 s, and still done before the arrow leaves; an army
        whose stay follows its arrival stays on. Arrows that must land on a word (`arrive:`) are left alone."""
        warm = (self.s.get('map') or {}).get('palette') == 'warm'
        for e in elements:
            tag = e.pop('_auto_grow', None)
            if not warm or not tag or e['type'] != 'arrow':
                continue
            pts = [(self.places[p]['x'], self.places[p]['y']) if isinstance(p, str) else tuple(p) for p in e['points']]
            z = [k for k in keys if k['t'] <= e['start'] + 0.3][-1]['z']
            px = z * sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            old = float(e['grow'])
            g = min(4.5, max(old, px / self.ARROW_PX_S))
            if tag == 'hold':
                e['end'] = round(min(duration, max(e['end'], e['start'] + g + 1.5)), 3)
            else:
                g = max(old, min(g, e['end'] - e['start'] - 0.8))
            e['grow'] = round(g, 2)

    def follow_armies(self, elements, keys):
        """`army: {follow: true}`: the camera trails the column (slightly behind, looking ahead
        toward the target), then settles on the destination just before the army arrives."""
        def cam_at(t):
            prev = keys[0]
            for k in keys:
                if k['t'] <= t:
                    prev = k
            return prev
        for e in elements:
            fol = e.pop('_follow', None)
            if not fol or e['type'] != 'arrow':
                continue
            pts = [(self.places[k]['x'], self.places[k]['y']) for k in e['points']]
            if len(pts) == 2:
                (ax, ay), (bx, by) = pts
                bend = e.get('bend', 0.18)
                cx, cy = (ax + bx) / 2 - (by - ay) * bend, (ay + by) / 2 + (bx - ax) * bend
                path = lambda u: ((1 - u) ** 2 * ax + 2 * (1 - u) * u * cx + u * u * bx, (1 - u) ** 2 * ay + 2 * (1 - u) * u * cy + u * u * by)
            else:
                segs = list(zip(pts, pts[1:]))
                def path(u, segs=segs):
                    k = min(len(segs) - 1, int(u * len(segs)))
                    r = u * len(segs) - k
                    (x0, y0), (x1, y1) = segs[k]
                    return (x0 + (x1 - x0) * r, y0 + (y1 - y0) * r)
            t0, g = e['start'], e['grow']
            base = cam_at(t0)
            z = base['z'] * (float(fol) if not isinstance(fol, bool) else 1.25)
            smooth = lambda x: x * x * (3 - 2 * x)
            tx, ty = pts[-1]
            new = []
            n = max(3, int(g / 0.4))
            for j in range(n + 1):
                t = t0 + 0.3 + (g - 0.9) * j / n         # finish 0.6 s before arrival
                u = smooth(max(0.0, min(1.0, (t - t0 - 0.35) / g)))   # a little behind the column
                hx, hy = path(u)
                look = 0.25 + 0.5 * j / n               # look further ahead as the target nears
                new.append({'t': round(t, 3), 'cx': round(hx + (tx - hx) * look, 2), 'cy': round(hy + (ty - hy) * look, 2), 'z': round(z, 4)})
            end_t = new[-1]['t']
            held = cam_at(end_t)
            same = lambda k: (k['cx'], k['cy'], k['z']) == (held['cx'], held['cy'], held['z'])
            after = [k for k in keys if k['t'] > end_t]
            # keyframes that merely hold the pre-follow view now hold where the follow ended,
            # so the camera does not drift back; the next real move starts from there
            for j, k in enumerate(after):
                if not same(k):
                    break
                after[j] = {**k, 'cx': new[-1]['cx'], 'cy': new[-1]['cy'], 'z': new[-1]['z']}
            keys = [k for k in keys if k['t'] < t0 + 0.3] + new + after
            keys.sort(key=lambda k: k['t'])
        return keys

    def auto_camera(self, b) -> dict | None:
        """Follow the places this beat talks about: highlights first, then element anchors."""
        keys = list(b.get('highlight') or [])
        for item in b.get('show') or []:
            if isinstance(item, dict) and len(item) == 1:
                spec = next(iter(item.values()))
                if isinstance(spec, dict):
                    keys += [spec.get('at'), spec.get('from'), *(spec.get('via') or []), spec.get('to')]
        keys = [x for k in keys for x in (k if isinstance(k, list) else [k])]   # alliance `from` is a list
        keys = [k for i, k in enumerate(keys) if isinstance(k, str) and k in self.places and k not in keys[:i]]
        last = self.last_focus if isinstance(self.last_focus, list) else [self.last_focus]
        if not keys or sorted(keys) == sorted(k for k in last if k):
            return None
        m = self.s.get('map') or {}
        if len(keys) == 1:
            return {'focus': keys[0], 'zoom': float(m.get('focus_zoom', 2.0)), 'move': 1.6}
        return {'focus': keys, 'zoom': 'fit', 'move': 1.8}

    # -- main
    # 对话舞台 (2026-10-12, after 安州牧《两晋十六国》): a run of characters' own lines leaves the map for an old-book
    # paper stage — big portraits facing each other, the speaker lit, his words (原文 `quote` if given) in brush script.
    STAGE_BREAK = {'army', 'march', 'campaign', 'clash', 'arrow', 'flag', 'siege', 'fire', 'takeover', 'defect', 'flee',
                   'rout', 'battle', 'replay', 'alliance', 'meanwhile'}

    def stage_runs(self, beats) -> list[dict]:
        """Group beats into stages: >=2 speaker lines in a row (narration lead-ins ending in '：' may sit between or
        before them), or any beat with `scene:`. `scene: none` on a beat keeps it on the map."""
        def mappy(b):
            return any(isinstance(it, dict) and len(it) == 1 and next(iter(it)) in self.STAGE_BREAK for it in b.get('show') or [])

        def kind(i):
            b = beats[i]
            sc = b.get('scene')
            if sc in ('none', False) or mappy(b):
                return None
            if b.get('speaker'):
                return 'line'
            if sc:
                return 'scene'
            if re.search(r'[：:]\s*$', b.get('say', '')) and i + 1 < len(beats) and beats[i + 1].get('speaker'):
                return 'lead'
            return None

        runs, cur = [], []
        for i in range(len(beats)):
            if kind(i):
                cur.append(i)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        # a run whose speakers change camp is two scenes (2026-10-14: 袁绍帐下的淳于琼 and 曹操这边的毛玠 were put
        # face to face): split before the first beat — lead-ins included — of the new camp's speaker
        people = self.s.get('people') or {}
        camp = lambda who: (people.get(who) or {}).get('faction') if isinstance(people.get(who), dict) else None
        split = []
        for r in runs:
            part, last = [], None
            for i in r:
                sp = beats[i].get('speaker')
                if sp and camp(sp) and last and camp(sp) != last:
                    j = len(part)   # keep the new camp's lead-in narration with it
                    while j > 0 and not beats[part[j - 1]].get('speaker') and re.search(r'[：:]\s*$', beats[part[j - 1]].get('say', '')):
                        j -= 1
                    if part[:j]:
                        split.append(part[:j])
                    part = part[j:]
                if sp and camp(sp):
                    last = camp(sp)
                part.append(i)
            if part:
                split.append(part)
        runs = split
        out = []
        for r in runs:
            lines = [i for i in r if beats[i].get('speaker')]
            if len(lines) < 2 and not any(beats[i].get('scene') for i in r):
                continue
            cast = []
            for i in r:
                for who in [beats[i].get('speaker'), beats[i].get('to')]:
                    if who and who not in cast:
                        cast.append(who)
            scene = next((beats[i]['scene'] for i in r if beats[i].get('scene')), '古籍')
            out.append({'beats': r, 'cast': cast, 'scene': scene})
        return out

    def stage_element(self, st, beats, beats_t, duration) -> dict:
        r = st['beats']
        t0, t1 = beats_t[r[0]]['start'], min(beats_t[r[-1]]['end'], duration)
        lines = []
        for i in r:
            b, bt = beats[i], beats_t[i]
            if b.get('speaker'):
                q = b.get('quote')
                orig = isinstance(q, str) and bool(q.strip())
                lines.append({'who': b['speaker'], 't0': round(bt['voice_onset'], 3), 't1': round(bt['voice_offset'], 3),
                              'text': q if orig else b.get('say', ''), 'original': orig})
        # two places on stage: the first two people take them; a newcomer replaces whoever is not the person he
        # answers (the previous speaker), like actors coming on and going off
        actors = []
        prev = None

        def enter(who, at):
            used = {a['side'] for a in actors if a['end'] is None}
            side = 'left' if 'left' not in used else 'right' if 'right' not in used else None
            if side is None:
                gone = next(a for a in actors if a['end'] is None and a['who'] != prev)
                gone['end'] = at
                side = gone['side']
            p = self.person(who, f'stage {who}')
            actors.append({'who': who, 'name': p['name'], 'title': p['title'], 'image': p['image'], 'faces': p.get('faces', 'right'),
                           'color': self.faction_color(p.get('faction')), 'side': side, 'start': round(at, 3), 'end': None})

        for w in st['cast'][:2]:
            enter(w, t0)
        for ln in lines:
            if not any(a['who'] == ln['who'] and a['end'] is None for a in actors):
                enter(ln['who'], ln['t0'] - 0.6)
            prev = ln['who']
        for a in actors:
            if a['end'] is None:
                a['end'] = round(t1, 3)
        scene = str(st['scene'])
        image = None
        if scene != '古籍':
            stem = next((v for k, v in SCENES.items() if scene in k.split('|')), None)
            if stem and any((ROOT / '03_素材' / '动画素材').glob(f'第*批/{stem}.png')):
                image = f'anim/{stem}.jpg'
            else:
                self.warn(f"stage scene「{scene}」没有底图（可用：{'、'.join(k.split('|')[0] for k in SCENES)}），用古籍纸")
        return {'type': 'stage', 'start': round(t0, 3), 'end': round(t1, 3), 'scene': scene, 'image': image, 'actors': actors, 'lines': lines}

    @staticmethod
    def carry_over(name, bt, elements) -> bool:
        """The speaker's portrait (enter / person_card / face-off) is already up from an earlier beat: stretch it to the
        end of his line (2026-10-12: 荀彧回信说： brought him in for 2.4 s and he vanished as soon as he spoke)."""
        hit = False
        for e in elements:
            if not e.get('start', 0) <= bt['voice_onset'] + 0.3 < e.get('end', 0):
                continue
            if e.get('type') in ('enter', 'person_card') and e.get('name') == name \
                    or e.get('type') == 'versus' and name in ((e.get('left') or {}).get('name'), (e.get('right') or {}).get('name')):
                if not e.get('settle'):
                    e['end'] = round(max(e['end'], bt['voice_offset'] + 0.5), 3)
                hit = True
        return hit

    def speaker_coverage(self, segments, elements):
        """Every line a person speaks should show that person: warn when his face is up for under 80 % of it."""
        for g in segments:
            who = g.get('speaker')
            if not who:
                continue
            t0, t1 = g['voice_onset'], g['voice_offset']
            # a portrait of him that is up when he starts talking stays until he has finished
            for e in elements:
                if e['type'] in ('enter', 'person_card', 'versus') and not e.get('settle') and e['start'] <= t0 + 0.5 < e['end'] < t1 + 0.5                         and who in (e.get('name'), e.get('who'), (e.get('left') or {}).get('name'), (e.get('right') or {}).get('name')):
                    e['end'] = round(t1 + 0.5, 3)
            spans = []
            for e in elements:
                if e['type'] in ('enter', 'person_card', 'exit') and who in (e.get('name'), e.get('who')) and (e['type'] != 'exit' or e.get('show_portrait')):
                    spans.append((e['start'], e['end']))
                elif e['type'] == 'versus' and who in ((e.get('left') or {}).get('name'), (e.get('right') or {}).get('name'), (e.get('left') or {}).get('who'), (e.get('right') or {}).get('who')):
                    spans.append((e['start'], e['end']))
                elif e['type'] == 'stage':
                    spans += [(a['start'], a['end']) for a in e['actors'] if who in (a['who'], a['name'])]
            covered = sum(max(0.0, min(t1, b) - max(t0, a)) for a, b in spans)
            if t1 > t0 and covered / (t1 - t0) < 0.8:
                self.warn(f"{g['id']}: {who} 在说话（{t0:.1f}–{t1:.1f}s），画面上却只有 {covered / (t1 - t0):.0%} 的时间有他的立绘")

    def compile(self, timing: dict, build_id: str) -> dict:
        s = self.s
        for k in ['id', 'title', 'year', 'beats']:
            if k not in s:
                self.err(f'missing top-level `{k}`')
        if self.errors:
            raise ScriptError('\n'.join(self.errors))
        self.resolve_places()
        # 发布信息写在稿子里，发布时不用再问（2026-10-13 用户）：hook 标题钩子、summary 简介、tags 话题、next 下集预告
        if str(s.get('id', '')).startswith('s0'):
            pub = s.get('publish') or {}
            miss = [k for k in ('hook', 'summary', 'tags', 'next') if not pub.get(k)]
            if miss:
                self.warn(f"publish: 缺 {'、'.join(miss)}（标题钩子 / 简介 / 话题 / 下集预告），发布页会空着")
        beats = self.expand_composites(s['beats'])
        tb = timing['beats']
        duration = max(float(s.get('duration', 0)), tb[-1]['file_end'] + float(s.get('tail', 1.2)))
        duration = math.ceil(round(duration * 30, 6)) / 30
        beats_t = []
        for i, t in enumerate(tb):
            beats_t.append({'start': 0.0 if i == 0 else t['file_start'], 'end': tb[i + 1]['file_start'] if i + 1 < len(tb) else duration, **t})

        segments, phases, years, elements = [], [], [], []
        highlights: dict[str, list] = {k: [] for k in self.places}
        cam0 = s.get('camera') or {}
        self.last_focus = cam0.get('focus')
        z0 = cam0.get('zoom', 0.65)
        state = self.focus_state({'zoom': 0.65, **cam0}, {'cx': W / 2, 'cy': H / 2, 'z': 0.65 if z0 == 'fit' else float(z0)}, 'camera')
        keys = [{'t': 0.0, **state}]
        legend_kinds = set()
        phase_text = year_text = None
        stages = self.stage_runs(beats)
        stage_of = {i: k for k, st in enumerate(stages) for i in st['beats']}

        for i, (b, bt) in enumerate(zip(beats, beats_t)):
            ctx = f'beat {i + 1}'
            if not b.get('say'):
                self.err(f'{ctx}: missing `say` (narration line)')
            say = b.get('say', '')
            if isinstance(b.get('caption'), list):
                chunks = [str(x) for x in b['caption']]
            elif b.get('caption') and s.get('captions', 'clause') != 'clause':
                chunks = [b['caption']]
            else:
                chunks = split_captions(say)
            for ch in chunks:
                if len(ch) > 18:
                    self.warn(f'{ctx}: caption chunk「{ch}」{len(ch)} chars; keep ≤16')
            # time each chunk by its share of spoken characters
            total = sum(len(re.sub(r'[\W_]', '', c)) for c in chunks) or 1
            t, caps = bt['voice_onset'], []
            for ch in chunks:
                dt = (bt['voice_offset'] - bt['voice_onset']) * len(re.sub(r'[\W_]', '', ch)) / total
                caps.append({'t0': round(t - 0.07, 3), 't1': round(t + dt + 0.07, 3), 'text': ch})
                t += dt
            cap = b.get('caption') if isinstance(b.get('caption'), str) else '，'.join(chunks)
            self.check_sources(b.get('sources'), ctx)
            # Narration lint (history-narration skill): spoken modern Chinese, not classical text.
            spoken = re.sub(r'几乎|似乎|在乎|不在乎|合乎|关乎|热乎|胖乎乎|乃至|韩遂|郭汜|曹髦|司马昭|孙乾|孙夫人|大乔|小乔|刘焉', '', say)
            classical = re.findall(r'[曰焉矣哉乎兮]|乃[^至]|遂[^宁平]|之于|其后|是时', spoken)
            if classical:
                self.warn(f'{ctx}: 旁白疑似文言（{"、".join(sorted(set(classical)))}），改成口语；原文放进 quote')
            if len(re.sub(r'[\W_]', '', say)) > 40:
                self.warn(f'{ctx}: 旁白 {len(say)} 字偏长，拆成两拍（每拍 15–35 字）')
            if timing.get('mode') not in ('placeholder', 'imported') and bt['voice_offset'] > bt['voice_onset']:
                rate = len(re.sub(r'[\W_]', '', say)) / (bt['voice_offset'] - bt['voice_onset'])
                if rate < 4.0:
                    self.warn(f'{ctx}: 实测语速 {rate:.1f} 字/秒，低于 4.0（参考片约 4.8）；见 history-voice')
            segments.append({'id': f'b{i + 1}', 'text': say, 'caption': cap, 'captions': caps, 'start': bt['start'], 'end': bt['end'], 'voice_onset': bt['voice_onset'], 'voice_offset': bt['voice_offset'],
                             **({'speaker': b['speaker']} if b.get('speaker') else {})})
            if b.get('phase') and b['phase'] != phase_text:
                if phases:
                    phases[-1]['end'] = bt['start']
                phases.append({'start': bt['start'], 'end': duration, 'text': b['phase']})
                phase_text = b['phase']
            if b.get('year') is not None and str(b['year']).isdigit():
                txt = self.era_text(int(b['year']), b.get('era_dynasty') or s.get('era_dynasty'))
                if b.get('era'):  # explicit override, e.g. era: 建始元年
                    txt = f"{b['era']}|{txt.split('|')[-1]}"
                b = {**b, 'year': txt}
            if b.get('year') and str(b['year']) != year_text:
                ys = bt['start']
                if b.get('year_cue'):   # e.g. yearshift: the badge turns when the big year card flips
                    yc = cue_time(b.get('say', ''), str(b['year_cue']), bt['voice_onset'], bt['voice_offset'])
                    ys = (yc if yc is not None else bt['voice_onset']) + float(b.get('year_delay', 0))
                if years:
                    years[-1]['end'] = ys
                ytext = str(b['year'])
                era, _, ce = ytext.partition('|')
                years.append({'start': ys, 'end': duration, 'text': ce or era, 'era': era if ce else None})
                year_text = str(b['year'])
            for k in b.get('highlight', []) or []:
                if self.P(k, ctx):
                    highlights[k].append([bt['voice_onset'] - 0.2, bt['end']])
            c = b.get('camera')
            if c is None and s.get('auto_camera', True):
                c = self.auto_camera(b)
            for c in (c if isinstance(c, list) else [c] if c else []):
                if isinstance(c.get('zoom'), str) and c['zoom'].startswith('x'):
                    c = {**c, 'zoom': round(state['z'] * float(c['zoom'][1:]), 3)}   # relative push-in, e.g. x1.4
                self.last_focus = c.get('focus')
                new = self.focus_state(c, state, ctx)
                base_t = bt['start']
                if c.get('cue'):
                    ct = cue_time(b.get('say', ''), str(c['cue']), bt['voice_onset'], bt['voice_offset'])
                    if ct is None:
                        self.err(f'{ctx}: camera cue「{c["cue"]}」not found in narration')
                    else:
                        base_t = ct - 0.3
                t_a = max(keys[-1]['t'] + 0.01, base_t + float(c.get('delay', 0)))
                if t_a > keys[-1]['t'] + 0.02:
                    keys.append({'t': round(t_a, 3), **state})
                keys.append({'t': round(t_a + float(c.get('move', 1.4)), 3), **new})
                state = new

            show_items = list(b.get('show', []) or [])
            if i in stage_of:
                cast = set(stages[stage_of[i]]['cast'])
                kept = []
                for it in show_items:
                    dropped = (isinstance(it, dict) and len(it) == 1 and next(iter(it)) in ('enter', 'versus', 'person_card')
                               and isinstance(next(iter(it.values())), dict)
                               and {next(iter(it.values())).get(k) for k in ('who', 'left', 'right')} & cast)
                    if dropped:   # the stage already shows these people, so the card is left out on purpose; say so
                        self.warn(f"{ctx}: 对话舞台已有 {'、'.join(sorted(cast))}，「{next(iter(it))}」不单独出现（只出现在舞台里）")
                    else:
                        kept.append(it)
                show_items = kept
            if b.get('speaker') and i not in stage_of:
                person = (s.get('people') or {}).get(b['speaker'])
                if not person or not person.get('voice'):
                    self.err(f"{ctx}: speaker `{b['speaker']}` needs a `people` entry with `voice:` (a description of how he sounds)")
                # the speaker's portrait is on screen while he talks, unless the beat already brings him in
                elif not any(isinstance(it, dict) and any(k in it and isinstance(it[k], dict) and b['speaker'] in (it[k].get('who'), it[k].get('left'), it[k].get('right'))
                                                         for k in ('enter', 'person_card', 'versus', 'exit')) for it in show_items)                         and not self.carry_over(b['speaker'], bt, elements):   # still on screen from an earlier beat: kept up until he finishes
                    show_items.append({'enter': {'who': b['speaker'], 'side': 'left'}})
            # a portrait exit (death) rings the 退场钟 on the same word; a bell written without a cue used to ring at
            # the start of the sentence, several seconds early, and some exits had none (2026-10-27, 关羽 in 第19集)
            # every portrait exit gets its own bell; two deaths a few seconds apart ring once (the sfx cooldown drops the second)
            pxs = [it['exit'] for it in show_items if isinstance(it, dict) and isinstance(it.get('exit'), dict) and it['exit'].get('portrait')]
            if pxs:
                bells = [it for it in show_items if isinstance(it, dict) and 'sfx' in it
                         and (it['sfx'] == '退场钟' or isinstance(it['sfx'], dict) and it['sfx'].get('name') == '退场钟')]
                for it in bells:
                    if not isinstance(it['sfx'], dict) or 'cue' not in it['sfx']:
                        it['sfx'] = {'name': '退场钟', **{k: pxs[0][k] for k in ('cue', 'delay') if k in pxs[0]}}
                cued = {(it['sfx'].get('cue'), it['sfx'].get('delay')) for it in bells}
                for px in pxs:
                    if (px.get('cue'), px.get('delay')) not in cued:
                        show_items.append({'sfx': {'name': '退场钟', **{k: px[k] for k in ('cue', 'delay') if k in px}}})
            for j, item in enumerate(show_items):
                ectx = f'{ctx} show[{j + 1}]'
                if not isinstance(item, dict) or len(item) != 1:
                    self.err(f'{ectx}: each show item is one `type: {{...}}` mapping')
                    continue
                kind, spec = next(iter(item.items()))
                spec = dict(spec or {}) if not isinstance(spec, str) else {'text': spec}
                if kind not in ELEMENT_TYPES:
                    self.err(f'{ectx}: unknown element `{kind}` (one of {sorted(ELEMENT_TYPES)})')
                    continue
                cue = spec.pop('cue', None)
                delay = float(spec.pop('delay', 0))
                start = bt['voice_onset'] + delay
                if cue:
                    ct = cue_time(b.get('say', ''), str(cue), bt['voice_onset'], bt['voice_offset'])
                    if ct is None:
                        self.err(f'{ectx}: cue「{cue}」not found in this beat\'s narration')
                    else:
                        start = ct + delay
                # armies and retreats leave with their sentence (they used to linger through the next one);
                # one that arrives late still stays ~1.5 s after arriving so the move reads
                auto_hold = kind in ('army', 'rout') and 'until' not in spec and 'for' not in spec and 'end_cue' not in spec
                arrive = spec.pop('arrive', None)
                if arrive:
                    at_t = cue_time(b.get('say', ''), str(arrive), bt['voice_onset'], bt['voice_offset'])
                    if at_t is None:
                        self.err(f'{ectx}: arrive「{arrive}」not found in this beat\'s narration')
                    else:
                        spec['grow'] = round(max(0.8, at_t - start), 3)
                end_cue = spec.pop('end_cue', None)
                end = self.until(spec.pop('until', None), i, beats_t, duration, start, ectx)
                if end_cue:
                    et = cue_time(b.get('say', ''), str(end_cue), bt['voice_onset'], bt['voice_offset'])
                    if et is None:
                        self.err(f'{ectx}: end_cue「{end_cue}」not found in this beat\'s narration')
                    else:
                        end = et + float(spec.pop('end_delay', 0))
                if spec.get('for') is not None:
                    end = start + float(spec.pop('for'))
                if auto_hold:
                    end = max(end, start + float(spec.get('grow', 2.0)) + 1.5)
                if cue and not end_cue and 'until' not in item[kind] and 'for' not in item[kind] and end - start < 2.4:
                    end = start + 2.4   # a late cue must still stay on screen long enough to read
                if kind == 'exit' and spec.get('portrait') and not end_cue and 'until' not in item[kind] and 'for' not in item[kind]:
                    end = max(end, start + 4.0)   # the portrait greys over ~1 s; 2.4 s was gone before it registered
                if end <= start:
                    self.err(f'{ectx}: ends before it starts')
                if kind == 'sfx':
                    self.add_sfx(spec, start, min(end, duration), ectx)
                    continue
                if 'sfx' in spec:
                    att = spec.pop('sfx')
                    for one_sfx in (att if isinstance(att, list) else [att]):
                        self.add_sfx(one_sfx, start, min(end, duration), ectx)
                el = self.element(kind, spec, ectx, legend_kinds)
                for one in (el if isinstance(el, list) else [el] if el else []):
                    off = one.pop('_offset', 0)
                    st = one.pop('_settle', None)
                    e_end = end
                    if one.get('type') == 'camp' and one.get('unit') and 'until' not in item[kind] and 'for' not in item[kind]:
                        e_end = duration   # a unit's camp stays until the unit marches off, routs or merges (march_units closes it)
                    if one.get('type') == 'arrow' and not arrive:   # a `grow:` in the script is a floor here, `arrive:` is exact
                        one['_auto_grow'] = 'hold' if auto_hold else True
                    elements.append({**one, 'start': round(start + off, 3), 'end': round(min(e_end, duration), 3)})
                    if st:
                        # the portrait shrinks onto its city and becomes that person's banner
                        f_end = self.until(st['until'] or ('beat+2' if i + 2 < len(beats) else 'end'), i, beats_t, duration, end, ectx)
                        elements.append({'type': 'flag', 'place': one['place'], 'name': one['name'], 'sub': st['sub'], 'color': one['color']['flag'],
                                         'side': 'right', 'note': None, 'start': round(min(end, duration) - 0.25, 3), 'end': round(min(f_end, duration), 3)})

        if keys[-1]['t'] < duration:
            keys.append({'t': duration, **state})
        # a fight on the map is heard: battle / clash / siege / fire with no sound of its own get the default one
        # (2026-10-28: 35 silent fights in 第19–43集; steel, not war cries — user, 2026-10-13)
        heard = self.sfx_after_cooldown()   # a nearby sound the cooldown will drop does not count
        for e in elements:
            opts = FIGHT_SFX.get(e['type'])
            if opts and not any(-1.0 <= x['start'] - e['start'] <= 2.0 for x in heard):
                # back-to-back fights take the next sound, so the cooldown does not swallow the second one
                fresh = [o for o in opts if not any(x['name'] == o and abs(x['start'] - e['start']) < 6.5 for x in self.sfx)]
                self.add_sfx((fresh or opts)[0], e['start'], min(e['end'], duration), f"auto {e['type']}@{e.get('place')}")
        self.pace_arrows(elements, keys, duration)
        keys = self.follow_armies(elements, keys)
        # tactic phases of one fight run back to back: each holds until the next phase starts
        tac = sorted([e for e in elements if e['type'] == 'tactic'], key=lambda e: e['start'])
        for k, e in enumerate(tac):
            nxt = tac[k + 1] if k + 1 < len(tac) and tac[k + 1]['layout'] == e['layout'] and tac[k + 1]['start'] - e['end'] < 3 else None
            prv = tac[k - 1] if k > 0 and tac[k - 1]['layout'] == e['layout'] and e['start'] - tac[k - 1]['end'] < 3 else None
            if nxt:
                e['end'] = nxt['start']
            e['first'], e['last'] = prv is None, nxt is None
        for st in stages:
            stage = self.stage_element(st, beats, beats_t, duration)
            # someone on stage dies (exit) during the scene: his figure greys there, not in a map-side portrait
            for ex in [e for e in elements if e['type'] == 'exit' and stage['start'] <= e['start'] <= stage['end']]:
                for a in stage['actors']:
                    if a['who'] in (ex['who'], ex['name']) and a['start'] <= ex['start'] <= a['end'] + 0.5:
                        a['die_at'], a['verb'] = ex['start'], ex['verb']
                        a['end'] = round(max(a['end'], min(stage['end'], ex['start'] + 1.6)), 3)
                        ex['show_portrait'] = False
            elements.append(stage)
        self.speaker_coverage(segments, elements)

        # Exit animation: matching flags sink and grey out; a stamp lands on the place.
        for ex in [e for e in elements if e['type'] == 'exit']:
            for f in elements:
                if f['type'] == 'flag' and f['name'] in (ex['name'], ex['who']) and f['start'] <= ex['start'] <= f['end'] + 0.5:
                    f['exit_at'] = ex['start']
                    f['end'] = round(ex['start'] + 1.6, 3)  # sink + grey over 1.6 s, then gone
                    if not ex['place']:
                        ex['place'] = f['place']
            if ex['place']:
                elements.append({'type': 'stamp', 'place': ex['place'], 'text': ex['verb'], 'start': round(ex['start'] + 0.35, 3), 'end': round(min(ex['end'] + 1.0, duration), 3)})

        for r in [e for e in elements if e['type'] == 'arrow' and e.get('rout_of')]:
            for c in elements:
                if c['type'] == 'clash' and c['place'] == r['rout_of'] and c['start'] <= r['start'] <= c['end'] + 1.0:
                    for k, sd in enumerate(c['sides']):
                        if sd['faction'] == r['faction']:
                            c['loser'], c['loser_at'] = k, r['start']
                    c['end'] = round(max(c['end'], r['start'] + 2.4), 3)
            r.pop('rout_of'), r.pop('faction')
        # fire on a battlefield: only the burnt side's soldiers catch fire (no city-wide blaze), then that side breaks
        for fe in [e for e in elements if e['type'] == 'fire']:
            for c in elements:
                if c['type'] != 'clash' or c['place'] != fe['place'] or not (c['start'] - 1 <= fe['start'] <= c['end'] + 1):
                    continue
                names = [sd['faction'] for sd in c['sides']]
                target = fe.get('on') or c.get('_loser')
                side = names.index(target) if target in names else (c['loser'] if c.get('loser') is not None else 1)
                c['burn_side'], c['burn_at'] = side, fe['start']
                if c.get('loser') is None:
                    c['loser'], c['loser_at'] = side, round(fe['start'] + 2.2, 3)
                c['end'] = round(max(c['end'], c['loser_at'] + 2.4), 3)
                if not fe.get('flash'):
                    fe['type'] = '_drop'
        elements[:] = [e for e in elements if e['type'] != '_drop']
        for c in [e for e in elements if e['type'] == 'clash']:
            c.pop('_loser', None)
            tr = c.pop('_trace', 14)
            if tr:   # the battle leaves a small mark on the site for a while (seconds, or `end`)
                c['trace_end'] = duration if tr == 'end' else round(min(duration, c['end'] + float(tr)), 3)

        # turn: the person's banner flips to the new side's colour; if none is up, one is raised first
        for tn in [e for e in elements if e['type'] == 'turn']:
            hit = False
            for f in list(elements):
                if f['type'] == 'flag' and f['name'] == tn['name'] and f['start'] <= tn['start'] <= f['end'] + 0.5:
                    if f.get('turn_at') is not None and f['turn_at'] < tn['start']:
                        # turned before (降 … 复反): this banner ends here and a new one carries on in the earlier
                        # turn's colour and flips again, so both changes of side stay on screen (2026-10-15 张绣)
                        old_end = f['end']
                        f['end'] = round(tn['start'], 3)
                        elements.append({'type': 'flag', 'place': f['place'], 'name': f['name'], 'sub': f.get('turn_sub') or f.get('sub'), 'color': f['turn_color'],
                                         'side': f.get('side', 'right'), 'note': f.get('note'), 'start': round(tn['start'], 3), 'end': round(max(old_end, tn['end']), 3),
                                         'turn_at': round(tn['start'] + 0.3, 3), 'turn_color': tn['color'], **({'turn_sub': tn['sub']} if tn.get('sub') else {})})
                        hit = True
                        break
                    f.update({'turn_at': tn['start'], 'turn_color': tn['color'], **({'turn_sub': tn['sub']} if tn.get('sub') else {})})
                    f['end'] = round(max(f['end'], tn['end']), 3)
                    hit = True
            if not hit:
                elements.append({'type': 'flag', 'place': tn['place'], 'name': tn['name'], 'sub': tn.get('from_sub'), 'color': tn['from_color'], 'side': 'right', 'note': None,
                                 'start': round(max(0, tn['start'] - 2.0), 3), 'end': tn['end'], 'turn_at': tn['start'], 'turn_color': tn['color'], **({'turn_sub': tn['sub']} if tn.get('sub') else {})})
        elements = [e for e in elements if e['type'] != 'turn']

        for rt in [e for e in elements if e['type'] == 'retire']:
            hit = False
            for f in elements:
                if f['type'] == 'flag' and f['name'] == rt['name'] and f['place'] == rt['place'] and f['start'] <= rt['start'] <= f['end'] + 0.5:
                    f['exit_at'] = rt['start']
                    f['end'] = round(rt['start'] + 1.6, 3)
                    hit = True
            if not hit:
                elements.append({'type': 'flag', 'place': rt['place'], 'name': rt['name'], 'sub': rt.get('sub'), 'color': rt['color'], 'side': rt.get('side', 'right'), 'note': None,
                                 'start': round(max(0, rt['start'] - 1.8), 3), 'end': round(rt['start'] + 1.6, 3), 'exit_at': rt['start']})
        elements = [e for e in elements if e['type'] != 'retire']

        self.march_units(elements, beats_t, duration)

        # the story's date at each beat: the last `map: YYYY-MM`, else the last `year:`, else the episode year
        dates, cur = [], None
        for b in beats:
            mm = re.fullmatch(r'(-?\d+)-(\d+)(?:-\d+)?', str(b.get('map') or ''))   # YYYY-MM, or YYYY-MM-DD for two changes in one month
            if mm:
                cur = (int(mm.group(1)), int(mm.group(2)))
            elif b.get('year') and (cur is None or int(b['year']) != cur[0]):
                cur = (int(b['year']), 1)
            dates.append(cur)
        first = next((d for d in dates if d), (self.year, 1))
        dates = [d or first for d in dates]

        # City marks: always-on unless `show: false` or `show: beat N`.
        for k, p in self.places.items():
            if p['show'] is False:
                continue
            start = 0.0
            m = re.fullmatch(r'beat\s*(\d+)', str(p['show']))
            if m:
                n = int(m.group(1)) - 1
                start = beats_t[n]['voice_onset'] if n < len(beats_t) else 0
            nlen = len(p['name'])
            lab = p['label']
            dx, dy = {'right': (18, -20), 'left': (-(nlen * 28 + 22), -20), 'above': (-nlen * 14, -62), 'below': (-nlen * 14, 14)}.get(lab, (18, -20)) if isinstance(lab, str) else lab
            if p['tier'] == 'region':
                dx, dy = -nlen * 25, -26
            detail = p['detail']
            if detail is False:
                detail = ''
            elif not detail and p['approx'] and p['tier'] != 'region' and (s.get('map') or {}).get('show_approx'):
                detail = '近似点'   # off by default: precision lives in review.md and the footer note
            city = {'type': 'city', 'place': k, 'start': start, 'end': duration, 'detail': detail, 'dx': dx, 'dy': dy, 'active': highlights[k]}
            rec = self.place_recs.get(k)
            if rec and p['tier'] != 'region':
                # rank and ruler badge follow the story's date beat by beat (武昌 is a capital only 229-04..09)
                phases = []
                for bt, (y, mo) in zip(beats_t, dates):
                    ph = {'t': round(bt['voice_onset'], 3), 'tier': tier_at(rec, y, mo, p['tier']), 'seat': seat_at(rec, y, mo)}
                    if not phases or (phases[-1]['tier'], phases[-1]['seat']) != (ph['tier'], ph['seat']):
                        phases.append(ph)
                if phases:
                    phases[0]['t'] = 0.0
                    city['phases'] = phases
            elements.insert(0, city)

        m = s.get('map') or {}
        legend = []
        if m.get('rivers', True):
            legend.append('蓝实线：现代河流')
        if 'recorded' in legend_kinds:
            legend.append('红实箭头：史载行动')
        if 'direction' in legend_kinds:
            legend.append('红虚箭头：方向示意')
        if 'flee' in legend_kinds:
            legend.append('蓝细断箭头：败退 / 出奔')
        if 'relation' in legend_kinds or any(e['type'] == 'flag' for e in elements):
            legend.append('蓝虚线：地点—旗牌示意关联')
        footer = s.get('footer') or {}
        basemap_credit = {'relief': '底图：Esri, USGS, NOAA · 河网：Natural Earth', 'dem': '地形：NOAA ETOPO 2022 · 海岸河湖：Natural Earth'}.get(m.get('basemap', 'relief'), '河网：Natural Earth')
        disclosures = ['城池近似 / 示意点' if any(p['approx'] for p in self.places.values()) else '城池点位见报告', '现代地形水系参照，非古河道复原']
        terr = None
        if s.get('territory'):
            from territory import Territory
            terr = Territory(s['territory'], self).compile(beats, beats_t, self.proj)
            if terr:
                terr['look'] = m.get('look', 'light')
                # the map changing colour is heard (24 silent changes in 第19–43集); hatching alone stays quiet
                heard = self.sfx_after_cooldown()
                for a, b in zip(terr['states'], terr['states'][1:]):
                    if a['owners'] != b['owners'] and not any(abs(x['start'] - b['t']) <= 1.5 for x in heard):
                        self.add_sfx('疆域易手', b['t'], min(b['t'] + 3, duration), f"auto 疆域 {b['t']:.1f}s")
                disclosures.append('势力范围按郡示意，郡界为推算')
                if any(st['uncertain'] for st in terr['states']):
                    legend.append('斜纹：归属不明 / 示意')
        # sound etiquette: the same sound not twice within `cooldown` s; warn when a stretch gets busy
        rules = sfx_cues().get('rules', {})
        kept: list[dict] = []
        for x in sorted(self.sfx, key=lambda x: x['start']):
            if any(k['sound'] == x['sound'] and x['start'] - k['start'] < float(rules.get('cooldown', 6)) for k in kept):
                self.warn(f"sfx「{x['name']}」at {x['start']:.1f}s dropped: same sound again within {rules.get('cooldown', 6)} s")
                continue
            busy = [k for k in kept if x['start'] - k['start'] < 10]
            if len(busy) >= int(rules.get('max_per_10s', 4)):
                self.warn(f"sfx「{x['name']}」at {x['start']:.1f}s: {len(busy) + 1} sounds within 10 s — too busy?")
            kept.append(x)
        self.sfx = kept
        return {
            'territory': terr,
            'schema': 'history-studio-episode/1', 'id': s['id'], 'build': build_id, 'title': s['title'], 'series': s.get('series', ''),
            'fps': 30, 'width': W, 'height': H, 'duration': duration, 'theme': {**THEME, **({'river': '#4f9bd3'} if (s.get('map') or {}).get('look', 'light') == 'light' else {}), 'look': m.get('look', 'light'), 'palette': m.get('palette'),
                      'series_title': s.get('series_title') or '三国到隋', 'channel': s.get('channel') or '兰台令史', **(s.get('theme') or {})},
            'map': {'km': round(math.hypot(*(a - b for a, b in zip(self.proj.world(*self.proj_center), self.proj.world(self.proj_center[0], self.proj_center[1] + 0.9)))) / 100, 4),
                    'raster': None, 'rivers': self.atlas_rivers(m.get('extent')) if m.get('look') == 'atlas' else [], 'regions': [], 'watermark': m.get('watermark'), 'minimap': self.minimap_box(),
                    'features': self.atlas_features() if m.get('look') == 'atlas' else []},
            'places': [{k: p[k] for k in ['id', 'name', 'x', 'y', 'lon', 'lat', 'precision', 'tier']} for p in self.places.values()],
            'segments': segments, 'camera': keys, 'phases': phases, 'years': years, 'elements': elements, 'audio': None, 'sfx': self.sfx,
            'legend': footer.get('legend', legend),
            'footer': {'left': footer.get('left', ' · '.join(disclosures)), 'right': footer.get('right', f'史据：{self.source_label()}　{basemap_credit}')},
        }

    def march_units(self, elements: list, beats_t: list, duration: float) -> None:
        """Who is where (2026-10-19, 潼关之战 review). A named unit — an army with `head:`/`unit:`, or the leader
        of a `chase` — is always somewhere on the map until it routs, is merged into another, or the episode ends:
        - a move leaves a faint dashed route only with `trail: true` (default off since 2026-10-28); it fades
          two beats after arrival;
        - where the unit arrives it encamps (tents + name) until it leaves;
        - `merge: [徐晃]` on a move folds those units into the arriving one (one camp, still named 曹操);
          a merged unit that marches out again is a detachment;
        - a rout ends the unit (its route stays, labelled 败走); an approach to a battle (`stop: approach`, as
          `campaign` writes it) pitches no camp;
        - an explicit `camp: {at, unit}` is a garrison that was already there.
        Armies without a name are drawn only while they move; `check` lists them. Problems with the story's
        geography (leaving from a place the unit is not at, two camps of one side at one place) are warnings."""
        def beat_of(t):
            for i, bt in enumerate(beats_t):
                if t < bt['end']:
                    return i + 1
            return len(beats_t)

        def unit_of(e):
            if e.get('chase'):
                return e['chase']['leader']['name']
            tr = e.get('troops') or {}
            return tr.get('unit') or tr.get('head_name')

        moves = [e for e in elements if e['type'] == 'arrow' and (e.get('troops') or e.get('chase'))]
        anon = sorted({beat_of(e['start']) for e in moves if not unit_of(e) and not (e.get('troops') or {}).get('rout')})
        if anon:
            self.warn(f"行军：第 {'、'.join(map(str, anon))} 拍的部队没写 head 或 unit（是谁的兵），只在行军时出现，"
                      f"到达后不会留在地图上；写上 head/unit 才会扎营、留轨迹")
        events = []   # (time, order, kind, element); at one instant: garrison, then leaving, then arriving
        for e in moves:
            if unit_of(e):
                events.append((e['start'], 1, 'depart', e))
                events.append((e['start'] + float(e.get('grow', 2.0)), 2, 'arrive', e))
        for e in elements:
            if e['type'] == 'camp' and e.get('unit'):
                events.append((e['start'], 0, 'garrison', e))
            # a commander who dies takes his camp with him (2026-10-25: 诸葛瞻 died at 绵竹, his camp stayed on);
            # one who surrenders or is taken, or whose banner turns (defect), takes his camp and route with him
            # too (2026-10-27: 于禁 surrendered at 樊城, his camp and the line back to 许 stayed to the end)
            if e['type'] == 'exit' and e.get('verb') in ('卒', '诛', '亡', '降', '囚'):
                events.append((e['start'], 3, 'fall', e))
            if e['type'] == 'flag' and e.get('turn_at') is not None and e.get('name'):   # a `turn` / `defect`, folded into its flag above
                events.append((e['turn_at'], 3, 'fall', {**e, 'who': e['name']}))
        events.sort(key=lambda x: (x[0], x[1]))

        pos, camp, trails, merged, parent, gone, new = {}, {}, {}, {}, {}, set(), []

        def close(u, t):
            c = camp.pop(u, None)
            if c:
                c['end'] = round(max(c['start'] + 0.4, min(c['end'], t)), 3)

        def end_trails(u, t):
            for tr in trails.pop(u, []):
                tr['end'] = round(max(tr['start'] + 0.4, t), 3)

        def text_of(u):   # the camp keeps its commander's name; merged units are not spelled out (user, 2026-10-19)
            return u

        for t, _, kind, e in events:
            ctx = f'第 {beat_of(t)} 拍'
            if kind == 'fall':
                u = e.get('who')
                if u in camp or u in pos or u in trails:
                    close(u, t)
                    end_trails(u, t)
                    pos.pop(u, None)
                    gone.add(u)
                continue
            if kind == 'garrison':
                u = e['unit']
                if pos.get(u) and pos[u] != e['place']:
                    self.warn(f"行军：{ctx} {u} 还在 {pos[u]}，没有行军就出现在 {e['place']}（先写一段 army 把他带过去）")
                close(u, t)
                camp[u], pos[u] = e, e['place']
                gone.discard(u)
                continue
            u = unit_of(e)
            src, dst = e['points'][0], e['points'][-1]
            tr_ = e.get('troops') or {}
            rout = tr_.get('rout')
            color = ((e.get('chase') or {}).get('leader') or {}).get('color') or e.get('color', '#5a4a3a')
            if kind == 'depart':
                if u in parent:   # marching out of the camp it had joined: a detachment again
                    p = parent.pop(u)
                    if u in merged.get(p, []):
                        merged[p].remove(u)
                        if camp.get(p):
                            camp[p]['text'] = text_of(p)
                    pos[u] = pos.get(p)
                if u in gone:
                    self.warn(f'行军：{ctx} {u} 已经溃散，又出现行军（要交代他怎么重新集结的）')
                elif pos.get(u) and pos[u] != src:
                    self.warn(f'行军：{ctx} {u} 此刻在 {pos[u]}，这次却从 {src} 出发（起点改成 {pos[u]}，或先交代他怎么到 {src}）')
                close(u, t)
                end_trails(u, t)
                # the dashed route is drawn only when the script asks for it (`army: {trail: true}`): the moving
                # arrow already shows the way and the camp shows where he is (user, 2026-10-28: 关羽's line
                # from 江陵 to 樊城 hung on for 14 s after he arrived — "这东西有必要吗")
                if tr_.get('trail') or (e.get('chase') or {}).get('trail'):
                    tr = {'type': 'trail', 'points': e['points'], 'color': color, 'start': round(e['start'], 3), 'end': duration,
                          'label': f'{u}败走{dst}' if rout else f'{u}自{src}而来', '_arrive': e['start'] + float(e.get('grow', 2.0))}
                    new.append(tr)
                    if not rout:
                        trails.setdefault(u, []).append(tr)
                if rout:
                    gone.add(u)
                    pos.pop(u, None)
                continue
            # arrive
            if rout or u in gone:
                continue
            pos[u] = dst
            for m in (tr_.get('merge') or (e.get('chase') or {}).get('merge') or []):
                if pos.get(m) != dst:
                    self.warn(f"行军：{ctx} {u} 到 {dst} 与 {m} 合兵，但 {m} 此刻在 {pos.get(m) or '（地图上没有）'}")
                close(m, t)
                trails.setdefault(u, []).extend(trails.pop(m, []))
                merged.setdefault(u, []).append(m)
                parent[m] = u
                pos[m] = dst
            if e.get('stop') == 'approach' or tr_.get('nocamp'):
                continue
            c = {'type': 'camp', 'place': dst, 'text': text_of(u), 'color': color, 'faction': e.get('faction') or color, 'unit': u, 'from': src,
                 'start': round(t, 3), 'end': duration, **({'offset': tr_['camp_offset']} if tr_.get('camp_offset') else {})}
            new.append(c)
            camp[u] = c
        # the dashed route fades two beats after the unit arrives; the camp stays (user, 2026-10-27: 于禁's line
        # back to 许 sat on the map for two minutes)
        for tr in new:
            arr = tr.pop('_arrive', None)
            if tr['type'] == 'trail' and arr is not None:
                k = min(beat_of(arr) + 1, len(beats_t) - 1)
                tr['end'] = round(max(tr['start'] + 0.4, min(tr['end'], beats_t[k]['end'])), 3)
        elements.extend(new)

        # camps that share a place at the same time sit apart, each on the side it came from
        camps = [e for e in elements if e['type'] == 'camp']
        warned = set()
        for k, c in enumerate(camps):
            others = [o for o in camps if o is not c and o['place'] == c['place'] and o['start'] < c['end'] and c['start'] < o['end']]
            if not others:
                continue
            for o in others:
                pair = frozenset([id(c), id(o)])
                if c.get('faction') and o.get('faction') == c['faction'] and o.get('unit') != c.get('unit') and pair not in warned:
                    warned.add(pair)
                    self.warn(f"行军：{c.get('unit') or c['text']} 和 {o.get('unit') or o['text']} 同属一方、同时驻在 {c['place']}，"
                              f"是否应该合兵（在到达的那次行军上写 merge）")
            if c.get('offset'):
                continue
            p = self.places.get(c['place'])
            q = self.places.get(c.get('from')) if c.get('from') else None
            if p and q and (q['x'], q['y']) != (p['x'], p['y']):
                dx, dy = q['x'] - p['x'], q['y'] - p['y']
                n = math.hypot(dx, dy)
                c['offset'] = [round(84 * dx / n), round(40 * dy / n)]
            else:
                c['offset'] = [-84 if k % 2 == 0 else 84, 0]
        for c in camps:
            c.pop('from', None)

    def element(self, kind, spec, ctx, legend_kinds):
        if kind == 'flag':
            at = self.P(spec.get('at'), ctx)
            if not spec.get('name'):
                self.err(f'{ctx}: flag needs `name`')
            factions = self.s.get('factions') or {}
            polities = (self.s.get('territory') or {}).get('polities') or {}
            if spec.get('faction') and spec['faction'] not in factions and spec['faction'] not in polities:
                self.err(f'{ctx}: faction `{spec["faction"]}` not declared in top-level `factions` or `territory.polities`')
            col = spec.get('color') or (self.faction_color(spec['faction'])['flag'] if spec.get('faction') in polities and spec.get('faction') not in factions else factions.get(spec.get('faction'), 'red'))
            return at and {'type': 'flag', 'place': at, 'name': spec.get('name', ''), 'sub': spec.get('sub'), 'color': COLORS.get(col, col), 'side': spec.get('side', 'right'), 'note': spec.get('note')}
        if kind == 'vignette':
            # 情景插画窗 (2026-10-20): a painting from 03_素材/动画素材/第N批/illus_*.png in a feathered oval over the map
            img = str(spec.get('image') or '')
            if not img or not any((ROOT / '03_素材' / '动画素材').glob(f'第*批/{img}.png')):
                self.err(f'{ctx}: vignette needs `image:` — the name of an illus_*.png in 03_素材/动画素材/第N批 (got 「{img}」)')
                return None
            if not img.startswith('illus_'):
                self.warn(f'{ctx}: vignette image 「{img}」 should be named illus_* so it is staged at full size')
            return {'type': 'vignette', 'image': f'anim/{img}.jpg' if img.startswith('illus_') else f'anim/{img}.png', 'text': spec.get('text'),
                    'pos': spec.get('pos', 'center'), 'zoom': float(spec.get('zoom', 1.08))}
        if kind == 'camp':
            # a commander's encampment: tents stay on the map while the army is there (2026-10-19)
            at = self.P(spec.get('at'), ctx)
            col = self.faction_color(spec['faction'])['flag'] if spec.get('faction') else '#5a4a3a'
            unit = spec.get('unit') or spec.get('head')
            return at and {'type': 'camp', 'place': at, 'text': spec.get('text') or unit or '大营', 'color': col, 'faction': spec.get('faction'),
                           **({'unit': unit} if unit else {}), **({'offset': spec['offset']} if spec.get('offset') else {})}
        if kind == 'clash':
            at = self.P(spec.get('at'), ctx)
            sides = []
            for sd in spec.get('sides') or []:
                if not sd.get('faction'):
                    self.err(f'{ctx}: clash side needs `faction`')
                    continue
                sides.append({'faction': sd['faction'], 'color': self.faction_color(sd['faction'])['flag'], 'kind': sd.get('troops', 'infantry'), 'banner': sd.get('banner'),
                              'from': self.P(sd['from'], ctx) if sd.get('from') else None})
            if len(sides) != 2:
                self.err(f'{ctx}: clash needs exactly two `sides`')
                return None
            return at and {'type': 'clash', 'place': at, 'sides': sides, 'title': spec.get('title'), '_trace': spec.get('trace', 14), '_loser': spec.get('loser')}
        if kind == 'rout':
            # the beaten side's survivors stream away from the battlefield
            at, to = spec.get('at') or spec.get('from'), spec.get('to')
            if not at or not to or not spec.get('faction'):
                self.err(f'{ctx}: rout needs `at` (战场), `to` (退往) and `faction` (败方)')
                return None
            a = self.element('arrow', {'from': at, 'to': to, **({'via': spec['via']} if spec.get('via') else {}), 'kind': 'flee', 'faction': spec['faction'], 'label': spec.get('label', '败走'),
                                       'grow': spec.get('grow', 2.2), 'stop': 'near', 'bend': spec.get('bend', 0.15),
                                       '_troops': {'kind': spec.get('troops', 'infantry'), 'banner': spec.get('banner'), 'size': float(spec.get('size', 2.5)), 'rout': True,
                                                   **({'head_name': spec['head']} if spec.get('head') else {}), **({'unit': spec['unit']} if spec.get('unit') else {})}}, ctx, legend_kinds)
            if a:
                a['rout_of'] = self.P(at, ctx)
                a['faction'] = spec['faction']
            return a
        if kind == 'yearflip':
            def face(y):
                txt = self.era_text(int(y), spec.get('era_dynasty') or self.s.get('era_dynasty'))
                era, _, ce = txt.partition('|')
                return {'era': era if ce else None, 'text': ce or era}
            if not spec.get('from') or not spec.get('to'):
                self.err(f'{ctx}: yearflip needs `from` and `to` years')
                return None
            return {'type': 'yearflip', 'from': face(spec['from']), 'to': face(spec['to'])}
        if kind == 'turn':
            at = self.P(spec.get('at'), ctx)
            return at and {'type': 'turn', 'place': at, 'name': spec.get('name', ''), 'color': spec.get('color'), 'from_color': spec.get('from_color'), 'sub': spec.get('sub'), 'from_sub': spec.get('from_sub')}
        if kind == 'retire':
            at = self.P(spec.get('at'), ctx)
            return at and {'type': 'retire', 'place': at, 'name': spec.get('name', ''), 'sub': spec.get('sub'), 'color': spec.get('color', '#5a4a3a'), 'side': spec.get('side', 'right')}
        if kind == 'army':
            # march arrow with a column of soldiers and a commander's banner (or his portrait medallion: head: 马超)
            t = spec.get('troops', 'cavalry')
            if t not in ('cavalry', 'infantry', 'archer', 'crossbow'):
                self.err(f'{ctx}: army troops must be cavalry | infantry | archer | crossbow')
            troops = {'kind': t, 'banner': spec.get('banner'), 'size': float(spec.get('size', 3))}
            if spec.get('head'):
                troops['head_name'] = spec['head']
            if spec.get('unit'):
                troops['unit'] = spec['unit']
            if spec.get('merge'):
                troops['merge'] = list(spec['merge'])
            if spec.get('camp') is False:
                troops['nocamp'] = True
            if spec.get('trail'):
                troops['trail'] = True
            if spec.get('camp_offset'):
                troops['camp_offset'] = spec['camp_offset']
            spec = {**spec, '_troops': troops, '_follow': spec.get('follow')}
            kind = 'arrow'
        if kind == 'chase':
            # a pursuer's portrait follows the leader's portrait along one road (2026-10-19)
            lead, pur = spec.get('leader'), spec.get('pursuer')
            if not lead or not pur:
                self.err(f'{ctx}: chase needs `leader:` and `pursuer:` (people names)')
                return None
            people = self.s.get('people') or {}
            def fcol(name):   # each head rings in its own faction; the leader's faction is the chase's colour
                f = (people.get(name) or {}).get('faction') or spec.get('faction')
                return self.faction_color(f)['flag'] if f else '#7a5a3a'
            spec = {**spec, '_chase': {'lag': float(spec.get('lag', 0.12)), 'leader': {'name': lead, 'color': fcol(lead)}, 'pursuer': {'name': pur, 'color': fcol(pur)}, 'merge': list(spec.get('merge') or [])},
                    '_follow': spec.get('follow')}
            kind = 'arrow'
        if kind == 'march':
            kind = 'arrow'
        if kind == 'flee':
            kind = 'arrow'
            spec = {'kind': 'flee', **spec}
        if kind == 'multi_march':
            routes = spec.get('routes') or []
            if not routes:
                self.err(f'{ctx}: multi_march needs `routes: [{{from, via, to, faction}}…]`')
                return None
            out = []
            for i, r in enumerate(routes):
                a = self.element('arrow', {'to': spec.get('to'), 'kind': spec.get('kind', 'direction'), 'grow': spec.get('grow', 2.0), 'stop': 'approach', **r}, f'{ctx} route{i + 1}', legend_kinds)
                if a:
                    out.append({**a, '_offset': i * float(spec.get('stagger', 0.18))})
            if spec.get('label') and out:
                out[0]['label'] = spec['label']
            return out
        if kind == 'alliance':
            at = self.P(spec.get('at'), ctx)
            parties = [self.P(p, ctx) for p in spec.get('from') or []]
            if not at or not parties or None in parties:
                self.err(f'{ctx}: alliance needs `from: [地点…]` and `at: 会盟地`') if not parties else None
                return None
            legend_kinds.add('relation')
            out = [{'type': 'arrow', 'points': [p, at], 'kind': 'relation', 'grow': 1.4, 'label': None, 'stop': 'near', 'bend': 0.12, '_offset': i * 0.15} for i, p in enumerate(parties)]
            out.append({'type': 'alliance', 'place': at, 'text': spec.get('text', '会盟'), '_offset': 1.2})
            return out
        if kind == 'arrow':
            if spec.get('faction'):
                spec = {'color': self.faction_color(spec['faction'])['flag'], **spec}
            pts = [spec.get('from'), *(spec.get('via') or []), spec.get('to')]
            pts = [self.P(p, ctx) for p in pts]
            if None in pts:
                return None
            k = spec.get('kind', 'direction')
            if k not in ('recorded', 'direction', 'relation', 'flee'):
                self.err(f'{ctx}: arrow kind must be recorded | direction | relation | flee')
                return None
            label = spec.get('label')
            if k == 'recorded':
                ev = spec.get('evidence')
                if not ev or not ev.get('sources'):
                    self.err(f'{ctx}: kind recorded needs `evidence: {{sources: [...], note: 原文所载路线}}`; otherwise use kind direction')
                else:
                    self.check_sources(ev['sources'], ctx)
            if k == 'direction' and label and '示意' not in label:
                label += ' · 示意'
            if k == 'flee':
                label = label or '奔'
            legend_kinds.add(k)
            return {'type': 'arrow', 'points': pts, 'kind': k, 'grow': float(spec.get('grow', 2.0)), 'label': label, 'stop': spec.get('stop', 'near'), 'bend': float(spec.get('bend', 0.18)), **({'color': spec['color']} if spec.get('color') else {}), **({'troops': spec['_troops']} if spec.get('_troops') else {}), **({'chase': spec['_chase']} if spec.get('_chase') else {}), **({'_follow': spec['_follow']} if spec.get('_follow') else {}), **({'faction': spec['faction']} if spec.get('faction') else {})}
        if kind == 'siege':
            at = self.P(spec.get('at'), ctx)
            col = self.faction_color(spec.get('faction'))['flag'] if spec.get('faction') else None
            return at and {'type': 'siege', 'place': at, 'text': spec.get('text', '围'), 'color': col}
        if kind == 'capture':
            at = self.P(spec.get('at'), ctx)
            if not spec.get('faction'):
                self.err(f'{ctx}: capture needs `faction`（新控制者）')
            col = self.faction_color(spec.get('faction'))
            return at and {'type': 'capture', 'place': at, 'text': spec.get('text', '易手'), 'faction': spec.get('faction'), 'color': col['flag'], 'fill': col['fill']}
        if kind == 'replay':
            pts = [self.P(p, ctx) for p in spec.get('path') or []]
            if len(pts) < 2 or None in pts:
                self.err(f'{ctx}: replay needs `path: [地点, 地点, …]`（至少两个）')
                return None
            col = self.faction_color(spec['faction'])['flag'] if spec.get('faction') else spec.get('color')
            return {'type': 'replay', 'points': pts, 'label': spec.get('label'), 'color': col}
        if kind == 'act':
            # map scenes from the painted assets (03_素材/动画素材); see remotion Acts.tsx for each look
            #   at-a-place: coins 卖官 · wind 狂风 · edict 诏书 · prison 下狱 · execute 处斩 · flood 水淹 · thunder 雷 ·
            #               locusts 蝗灾 · fall 城陷 · prop 器物（item: 玉玺/虎符/冕冠/粮仓…）
            #   two places: courier 信使 · catapult 投石（from, to）· refugees 流民（from, to）· arrows 箭雨（[from,] to）
            #   many places: beacon 烽火 · no place: mourn 驾崩 · night 夜色（places → 火把）· inkwash 墨晕转场 · enthrone 登基（who）
            #   farm 屯田（at） · jianlv 剑履上殿（at） · feint 疑兵计（at, n 回合, sub 旗号字）
            #   herd 放牛马（places: [从, 往], n 头数）· pontoon 浮桥（at, angle 桥的走向°, len 桥长像素）
            acts = {'coins', 'wind', 'edict', 'prison', 'courier', 'beacon', 'execute', 'mourn', 'enthrone',
                    'arrows', 'flood', 'night', 'thunder', 'catapult', 'locusts', 'fall', 'refugees', 'prop', 'inkwash', 'farm', 'jianlv', 'feint', 'herd', 'pontoon'}
            a = spec.get('act')
            if a not in acts:
                self.err(f'{ctx}: act must be one of {sorted(acts)}')
                return None
            names = spec.get('places') or ([spec['at']] if spec.get('at') else [])
            pts = [self.P(n, ctx) for n in names]
            if a in ('courier', 'beacon', 'catapult', 'refugees', 'herd') and (len(pts) < 2 or None in pts):
                self.err(f'{ctx}: act {a} needs `places: [地点, 地点, …]` (at least two)')
                return None
            if a == 'enthrone':
                if not (spec.get('who') or spec.get('name')):
                    self.err(f'{ctx}: act enthrone needs `who`')
                    return None
                who = self.person(spec.get('who') or spec.get('name'), ctx)
                return {'type': 'act', 'act': a, 'place': None, 'places': [], 'name': who['name'], 'title': spec.get('title', who['title']),
                        'image': spec.get('image', who['image']), 'text': spec.get('text'), 'sub': spec.get('sub'), 'side': spec.get('side', 'right')}
            if a not in ('mourn', 'night', 'inkwash') and (not pts or None in pts):
                self.err(f'{ctx}: act {a} needs `at` (or `places`)')
                return None
            if a == 'prop' and not spec.get('item'):
                self.err(f'{ctx}: act prop needs `item`（玉玺、虎符、冕冠、粮仓、书信、竹简、城门、楼船…）')
            # the item must be one the engine can draw: an unknown one only fails at render time (旗帜, 第30集 2026-10-25)
            if a == 'prop' and spec.get('item') and spec['item'] not in prop_items():
                self.err(f"{ctx}: act prop 的 item「{spec['item']}」引擎里没有图（可用：{'、'.join(sorted(prop_items())[:40])}…，见 Acts.tsx 的 PROPS）")
            out = {'type': 'act', 'act': a, 'place': pts[0] if pts else None, 'places': pts,
                   'text': spec.get('text'), 'sub': spec.get('sub'), 'side': spec.get('side', 'right'), 'dir': spec.get('dir', 'right'),
                   'color': spec.get('color'), 'step': spec.get('step'), 'grow': spec.get('grow'), 'tone': spec.get('tone', 'ink')}
            for k in ('item', 'n', 'radius', 'size', 'angle', 'len', 'offset'):
                if spec.get(k) is not None:
                    out[k] = spec[k]
            return out
        if kind == 'fire':
            # 火攻: flames + smoke on a camp/city, optional full-screen burst (`flash`, default on)
            at = self.P(spec.get('at'), ctx)
            return at and {'type': 'fire', 'place': at, 'on': spec.get('on'), 'flash': bool(spec.get('flash', False)), 'flash_at': float(spec.get('flash_at', 0.7)),
                           'radius': float(spec.get('radius', 1.0)), 'size': float(spec.get('size', 1.0))}
        if kind == 'spot':
            at = self.P(spec.get('at'), ctx)
            return at and {'type': 'spot', 'place': at, 'text': spec.get('text')}
        if kind == 'breathe':
            if not spec.get('faction'):
                self.err(f'{ctx}: breathe needs `faction`（territory.polities 里的势力）')
            return {'type': 'breathe', 'faction': spec.get('faction')}
        if kind in ('battle', 'stamp'):
            at = self.P(spec.get('at'), ctx)
            if kind == 'stamp':
                return at and {'type': 'stamp', 'place': at, 'text': spec.get('text', '诛')}
            return at and {'type': 'battle', 'place': at, 'title': spec.get('title'), 'text': spec.get('text'), 'side': spec.get('side', 'left')}
        if kind == 'card':
            at = self.P(spec['at'], ctx) if spec.get('at') else None
            if not spec.get('title'):
                self.err(f'{ctx}: card needs `title`')
            return {'type': 'card', 'place': at, 'title': spec.get('title', ''), 'body': spec.get('body'), 'side': spec.get('side', 'right')}
        if kind == 'portrait':
            person = self.reg.persons.get(spec.get('person', ''))
            image = spec.get('image')
            if person and not image:
                image = f"portraits/{person['id']}.png"
            name = spec.get('name') or (f"{person['names']['title']} · {person['names']['formal']}" if person else '')
            if not image and not name:
                self.err(f'{ctx}: portrait needs `person`, `image` or `name`')
                return None
            # No image: the engine draws a typographic name card instead of a face.
            return {'type': 'portrait', 'image': image, 'name': name, 'title': spec.get('title', ''), 'note': spec.get('note', 'AI人物示意像' if image else '')}
        if kind in ('enter', 'person_card', 'exit'):
            who = self.person(spec.get('who') or spec.get('person') or spec.get('name'), ctx)
            if spec.get('who') is None and spec.get('person') is None and spec.get('name') is None:
                self.err(f'{ctx}: {kind} needs `who:` (a people key, maindata person id or name)')
            at = self.P(spec['at'], ctx) if spec.get('at') else None
            col = self.faction_color(spec.get('faction') or who.get('faction'))
            base = {'who': who['key'], 'name': who['name'], 'title': spec.get('title', who['title']), 'role': spec.get('role', who['role']),
                    'faction': spec.get('faction') or who.get('faction'), 'color': col, 'image': spec.get('image', who['image']),
                    'place': at, 'side': spec.get('side', 'left'), 'faces': spec.get('faces', who.get('faces', 'right'))}
            if kind == 'person_card':
                base['base'] = spec.get('base', who.get('base'))
                base['side'] = spec.get('side', 'right')   # left side is reserved for faction bars
                return {'type': 'person_card', **base}
            if kind == 'exit':
                verb = spec.get('verb', '卒')
                return {'type': 'exit', **base, 'verb': EXIT_STAMP.get(verb, verb), 'show_portrait': bool(spec.get('portrait', False))}
            if spec.get('settle') and not at:
                self.err(f'{ctx}: enter settle needs `at` (the city the portrait settles on)')
            return {'type': 'enter', **base, 'note': spec.get('note'), **({'settle': True, '_settle': {'sub': spec.get('settle_sub', base['title']), 'until': spec.get('settle_until')}} if spec.get('settle') and at else {})}
        if kind == 'tactic':
            # 战场示意: a battle close-up drawn over the dimmed map; one element per beat = one phase of the fight
            ph = spec.get('phase', 'deploy')
            layout = spec.get('layout', 'square_wings')
            phases = {'square_wings': ('deploy', 'charge', 'volley', 'rout'),          # 界桥：方阵两翼包抄、伏楯强弩
                      'raid': ('deploy', 'charge', 'climb', 'surround', 'breakout')}  # 突袭：八百冲阵、主将登高、被围、杀回救人
            if layout not in phases:
                self.err(f'{ctx}: tactic layout is {" / ".join(phases)}')
            elif ph not in phases[layout]:
                self.err(f'{ctx}: tactic {layout} phase is {" / ".join(phases[layout])}')
            return {'type': 'tactic', 'layout': layout, 'phase': ph, 'title': spec.get('title'), **({'labels': spec['labels']} if spec.get('labels') else {}),
                    'colors': {'a': self.faction_color(spec.get('attacker'))['flag'], 'd': self.faction_color(spec.get('defender'))['flag']},
                    'banners': {'a': spec.get('banner_a', ''), 'd': spec.get('banner_d', '')}}
        if kind == 'forces':
            # 兵力对比分屏 (after 纸上谈兵): two halves cut by a slanted line; the loser's half shatters like glass
            sides = []
            for k in ('left', 'right'):
                sd = spec.get(k)
                if not isinstance(sd, dict) or not sd.get('name'):
                    self.err(f'{ctx}: forces needs `left:` and `right:` with at least `name` (e.g. 曹军) and `sub` (e.g. 兵不满万)')
                    return None
                w = self.person(sd['who'], ctx) if sd.get('who') else None
                fac = sd.get('faction') or (w or {}).get('faction')
                sides.append({'name': sd['name'], 'sub': sd.get('sub', ''), 'color': self.faction_color(fac),
                              'image': sd.get('image', (w or {}).get('image')), 'faces': (w or {}).get('faces', 'right')})
            loser = spec.get('loser')
            if loser not in (None, 'left', 'right'):
                self.err(f'{ctx}: forces `loser` is left or right')
            return {'type': 'forces', 'left': sides[0], 'right': sides[1], 'loser': loser}
        if kind == 'versus':
            sides = []
            for k in ('left', 'right'):
                if not spec.get(k):
                    self.err(f'{ctx}: versus needs `left:` and `right:`')
                    return None
                w = self.person(spec[k], ctx)
                w_spec = spec[k] if isinstance(spec[k], dict) else {}
                sides.append({'who': w['key'], 'name': w['name'], 'title': w_spec.get('title', w['title']), 'image': w_spec.get('image', w['image']),
                              'color': self.faction_color(w_spec.get('faction') or w.get('faction')), 'faces': w_spec.get('faces', w.get('faces', 'right'))})
            return {'type': 'versus', 'left': sides[0], 'right': sides[1], 'label': spec.get('label', '对'), 'caption': spec.get('text')}
        if kind == 'title_bar':
            if not spec.get('text'):
                self.err(f'{ctx}: title_bar needs `text`')
            return {'type': 'title_bar', 'text': spec.get('text', ''), 'sub': spec.get('sub')}
        if kind == 'quote':
            if not spec.get('text') or not spec.get('source'):
                self.err(f'{ctx}: quote card needs `text` (原文短句) and `source` (如 晋书·帝纪第四)')
            if len(spec.get('text', '')) > 40:
                self.warn(f'{ctx}: quote card text over 40 chars; keep a short line')
            return {'type': 'quote', 'text': spec.get('text', ''), 'source': spec.get('source', ''), 'era': spec.get('era'), 'side': spec.get('side', 'right')}
        if kind == 'faction_bar':
            col = self.faction_color(spec.get('faction'))
            return {'type': 'faction_bar', 'text': spec.get('text', ''), 'faction': spec.get('faction'), 'color': col}
        if kind == 'headline':
            return {'type': 'headline', 'text': spec.get('text', ''), 'sub': spec.get('sub')}
        if kind == 'region':
            ids = {r['id'] for r in self.s.get('regions', []) or []}
            if str(spec.get('id')).split('/')[0] not in ids:
                self.err(f'{ctx}: region `{spec.get("id")}` not declared in top-level `regions`')
                return None
            return {'type': 'region', 'region': spec['id'], 'label': spec.get('label')}
        return None


# ---------------------------------------------------------------- commands

SERIES_VOICES = WORKFLOW / 'series' / '三国到隋' / '人物声音.yaml'
SERIES_SPOKEN = WORKFLOW / 'series' / '三国到隋' / '读音.yaml'
SERIES_MAP = WORKFLOW / 'series' / '三国到隋' / '疆域.yaml'
_CELL_INDEX: dict = {}


def cell_index(cells: str = 'han-140') -> dict:
    """zhou → units and parent (140 郡国志 commandery) → units of a cell set; han-219 splits 建安 commanderies off."""
    if cells not in _CELL_INDEX:
        g = read_json(HERE / 'data' / 'cells' / f'{cells}.geojson')
        zj, kids = {}, {}
        for f in g['features']:
            pr = f['properties']
            if pr.get('kind') == 'jun':
                zj.setdefault(pr['zhou'], []).append(pr['id'])
                if pr.get('parent') and pr['parent'] != pr['id']:
                    kids.setdefault(pr['parent'], []).append(pr['id'])
        _CELL_INDEX[cells] = {'zhou': zj, 'kids': kids, 'all': {j for js in zj.values() for j in js}}
    return _CELL_INDEX[cells]


def zhou_juns(cells: str = 'han-140') -> dict:
    return cell_index(cells)['zhou']


def _timeline(tl: dict, date: str, cells: str):
    """Replay the series timeline up to `date`: (owner per unit, hatched units).
    A 州 name sets all its units. A 140 commandery name sets that unit, and the 建安 commanderies split off it
    follow along only while they were in the same hands (襄阳 stays 魏 when 吴 takes 南郡; 汉中 passing to 蜀汉
    does not drag along 上庸三郡 that went to 魏). New units can be named directly."""
    ix = cell_index(cells)
    key = lambda d: tuple(int(x) for x in str(d).split('-'))
    state, hatched = {}, set()

    def units_for(u, before):
        if u in ix['zhou']:
            return list(ix['zhou'][u])
        if u not in ix['all']:
            return []
        return [u] + [k for k in ix['kids'].get(u, []) if before.get(k) == before.get(u)]

    for ev in sorted(tl.get('events') or [], key=lambda e: key(e['date'])):
        if key(ev['date']) > key(date):
            break
        before = dict(state)
        for pol, units in (ev.get('set') or {}).items():
            for u in units:
                for j in units_for(u, before):
                    state[j] = pol
                    hatched.discard(j)
        for u in ev.get('uncertain') or []:
            hatched |= set(units_for(u, state))    # after this event's own `set`: split-offs hatch along if they moved along
    return state, hatched


def map_owners(tl: dict, date: str, cells: str = 'han-140') -> dict:
    """Owners (polity → commanderies) at `date` (YYYY-MM, or YYYY-MM-DD) from the series timeline."""
    state, _ = _timeline(tl, date, cells)
    out = {}
    for j, pol in state.items():
        out.setdefault(pol, []).append(j)
    return out


def map_uncertain(tl: dict, date: str, cells: str = 'han-140') -> list:
    """Commanderies drawn hatched at `date`: an event's `uncertain:` list marks them contested until a later event sets them."""
    return sorted(_timeline(tl, date, cells)[1])
_SPOKEN: dict | None = None


def spoken_form(text: str) -> str:
    """Text as sent to the voice engine: series pronunciation fixes (麴义→曲义, 长子→掌子…); captions keep the original."""
    global _SPOKEN
    if _SPOKEN is None:
        _SPOKEN = ((yaml.safe_load(SERIES_SPOKEN.read_text(encoding='utf-8')) or {}).get('spoken') or {}) if SERIES_SPOKEN.exists() else {}
    for a, b in _SPOKEN.items():
        text = text.replace(a, b)
    return text


def load_script(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ScriptError('script must be a YAML mapping')
    # Series territory timeline: `map: 196-06` on a beat = owners computed from 疆域.yaml at that month,
    # so every episode draws the same history and episode N ends where N+1 starts.
    if SERIES_MAP.exists() and any(isinstance(b, dict) and b.get('map') for b in data.get('beats') or []):
        tl = yaml.safe_load(SERIES_MAP.read_text(encoding='utf-8')) or {}
        terr = data.setdefault('territory', {})
        cells = terr.get('cells') or 'han-140'
        pols = terr.setdefault('polities', {})
        for b in data['beats']:
            if isinstance(b, dict) and b.get('map'):
                b['owners'] = map_owners(tl, str(b['map']), cells)
                if 'uncertain' not in b:
                    b['uncertain'] = map_uncertain(tl, str(b['map']), cells)
                for pol in b['owners']:
                    if pol not in pols and pol in (tl.get('polities') or {}):
                        pols[pol] = dict(tl['polities'][pol])
        # the map before the first change is the timeline one month earlier = where the previous episode ended
        first = next(b for b in data['beats'] if isinstance(b, dict) and b.get('map'))
        if first.get('owners_cue') or first is not data['beats'][0]:
            y0, m0 = (int(x) for x in str(first['map']).split('-')[:2])
            prev = f'{y0 - 1}-12' if m0 == 1 else f'{y0}-{m0 - 1:02d}'
            terr['start_owners'] = map_owners(tl, prev, cells)
            for pol in terr['start_owners']:
                if pol not in pols and pol in (tl.get('polities') or {}):
                    pols[pol] = dict(tl['polities'][pol])
        for pol, cfg in list(pols.items()):     # series colour wins unless the episode set its own slot
            base = (tl.get('polities') or {}).get(pol)
            if base and isinstance(cfg, dict):
                pols[pol] = {**base, **cfg}
        declared = set(data.get('places') or {})
        for pol, cfg in pols.items():   # a series label city the episode doesn't show: let the engine place the name
            if isinstance(cfg, dict) and cfg.get('label_at') and cfg['label_at'] not in declared:
                cfg.pop('label_at')
    # Series voice registry: a character keeps one voice across every episode. An episode's people entry
    # inherits voice / voice_sample / voice_speed from 人物声音.yaml unless it sets its own.
    if SERIES_VOICES.exists() and isinstance(data.get('people'), dict):
        reg = (yaml.safe_load(SERIES_VOICES.read_text(encoding='utf-8')) or {}).get('voices') or {}
        # the registry wins: one person, one voice across the series (2026-10-13: old per-episode 曹操 voices
        # kept him soft after the registry was made more commanding). An episode may still add a voice for
        # someone the registry doesn't know.
        for name, entry in data['people'].items():
            if isinstance(entry, dict) and name in reg:
                for k in ('voice', 'voice_sample', 'voice_speed'):
                    if k in reg[name]:
                        entry[k] = reg[name][k]
    return data


def report_issues(c: Compiler) -> None:
    for w in c.warnings:
        print('  ⚠', w)
    for e in c.errors:
        print('  ✖', e)


def report_readings(script: dict) -> None:
    """读音预检: names, old words and rare characters nobody has checked yet (2026-10-28, 禅让 read chán)."""
    try:   # pypinyin missing or the table malformed must not stop a build
        import polyphone
        for r in polyphone.risky(script):
            print(f"  ⚠ 读音 第 {r['beat']} 拍「{r['word']}」{r['kind']}（{r['why']}），猜 {r['guess']}：核过后写进 读音.yaml 的 confirmed 或 spoken")
    except Exception as e:
        print(f"  ⚠ 读音预检没跑成：{type(e).__name__}: {e}")


def cmd_check(path: Path, as_json=False) -> int:
    script = load_script(path)
    timing = run_voice(script, path.parent, 'placeholder') if not (script.get('voice') or {}).get('mode') == 'imported' else run_voice(script, path.parent)
    c = Compiler(script, path, Registry())
    try:
        ep = c.compile(timing, 'check')
        c.campaign_lines = campaign.check(c, ep, path)
    except ScriptError as e:
        print(json.dumps({'ok': False, 'errors': str(e).split('\n'), 'warnings': []}, ensure_ascii=False) if as_json else e)
        return 1
    if as_json:
        print(json.dumps({'ok': not c.errors, 'errors': c.errors, 'warnings': c.warnings, 'beats': len(ep['segments']), 'duration_estimate': ep['duration'],
                          'places': {k: {'ref': p['ref'], 'precision': p['precision']} for k, p in c.places.items()}}, ensure_ascii=False, indent=1))
        return 1 if c.errors else 0
    report_issues(c)
    report_readings(script)
    print(f"{'FAIL' if c.errors else 'OK'}  {len(ep['segments'])} beats, {ep['duration']:.2f}s ({timing['mode']} timing), {len(ep['elements'])} elements, {len(c.places)} places")
    for p in c.places.values():
        print(f"  · {p['name']:<6} {p['ref']:<24} {p['precision'][:60]}")
    return 1 if c.errors else 0


def stage(path: Path, build_id: str | None, mode: str | None = None) -> tuple[Path, dict]:
    script = load_script(path)
    proj_dir = path.parent
    timing = run_voice(script, proj_dir, mode)
    reg = Registry()
    c = Compiler(script, path, reg)
    build_id = build_id or dt.datetime.now().strftime('B%Y%m%d-%H%M%S')
    ep = c.compile(timing, build_id)
    c.campaign_lines = campaign.check(c, ep, path)   # 战事.yaml: territory and marches against the ledger (2026-10-25)
    report_issues(c)
    if c.errors:
        raise ScriptError(f'{len(c.errors)} error(s); nothing staged')
    out = OUT_ROOT / script['id'] / build_id
    if out.exists():
        raise ScriptError(f'build {out} already exists; builds are never overwritten')
    try:
        return _stage_into(out, path, script, c, ep, timing)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)  # never leave a half-staged build behind
        raise


def _stage_into(out: Path, path: Path, script: dict, c: 'Compiler', ep: dict, timing: dict) -> tuple[Path, dict]:
    proj_dir = path.parent
    pub = out / 'public'
    (pub / 'fonts').mkdir(parents=True)
    for f in (HERE / 'assets' / 'fonts').iterdir():
        shutil.copy2(f, pub / 'fonts' / f.name)
    # hand-painted animation assets (03_素材/动画素材/第N批): shrunk once to ≤1024 px, then staged as anim/<name>.png
    (pub / 'anim').mkdir(exist_ok=True)
    for f in sorted((ROOT / '03_素材' / '动画素材').glob('第*批/*.png')):
        # scene backdrops (第6批 scene_*) fill the frame: keep 1920 px, as JPEG, already softened and dimmed
        # (blurring a full-frame image in CSS on every frame made renders slow)
        full = f.stem.startswith('scene_')
        illus = f.stem.startswith('illus_')    # 情景插画 (vignette): full size, sharp
        # 第12批 city icons share names with older assets (pass_gate): staged as icon_<name>
        name = 'icon_' + f.name if f.parent.name == '第12批' else f.name
        small = CACHE / 'anim' / (f.stem + '-soft.jpg' if full else f.stem + '.jpg' if illus else name)
        if not small.exists() or small.stat().st_mtime < f.stat().st_mtime:
            small.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(f) as im:
                if illus:
                    im2 = im.convert('RGB')
                    im2.thumbnail((1920, 1080), Image.LANCZOS)
                    im2.save(small, quality=90, optimize=True)
                elif full:
                    from PIL import ImageEnhance, ImageFilter
                    ImageEnhance.Brightness(im.convert('RGB').filter(ImageFilter.GaussianBlur(1.2))).enhance(0.92).save(small, quality=88, optimize=True)
                else:
                    im.thumbnail((1024, 1024), Image.LANCZOS)
                    im.save(small, optimize=True)
        shutil.copy2(small, pub / 'anim' / (f.stem + '.jpg' if full or illus else name))
    # paper fibres for the dialogue stage, made once (an SVG feTurbulence recomputed every frame was the slow part)
    fib = CACHE / 'anim' / 'paper_fibre.png'
    if not fib.exists():
        fib.parent.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(7)
        acc = np.zeros((H, W), np.float32)
        for k, amp in enumerate((1.0, 0.5, 0.25)):
            gx, gy = max(2, int(W * 0.012 * 2 ** k)), max(2, int(H * 0.09 * 2 ** k))
            layer = Image.fromarray((rng.random((gy, gx)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
            acc += amp * (np.asarray(layer, np.float32) / 255.0)
        acc = (acc - acc.min()) / (acc.max() - acc.min())
        rgba = np.zeros((H, W, 4), np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = 115, 84, 46
        rgba[..., 3] = (acc * 0.35 * 255).astype(np.uint8)
        Image.fromarray(rgba, 'RGBA').save(fib, optimize=True)
    shutil.copy2(fib, pub / 'anim' / 'paper_fibre.png')

    m = script.get('map') or {}
    extent = m.get('extent') or [100, 24, 124, 42]
    provenance = {'extent': extent, 'projection': {'center': [c.proj.lon0, c.proj.lat0], 'scale': c.proj.s}}
    if m.get('basemap', 'relief') == 'dem':
        import basemap_dem
        look = m.get('look', 'light')
        img, meta = basemap_dem.build([c.proj.lon0, c.proj.lat0], c.proj.s, extent, float(m.get('raster_res', 1.0)),
                                      {**basemap_dem.LOOKS.get(look, {}), **(basemap_dem.WARM if m.get('palette') == 'warm' else {}),
                                       **(m.get('style') or {})})
        img.save(pub / 'relief.jpg', quality=92)
        ep['map']['raster'] = {'src': 'relief.jpg', 'x': meta['x'], 'y': meta['y'], 'width': meta['width'], 'height': meta['height']}
        provenance['basemap'] = {**meta, 'attribution': 'NOAA ETOPO 2022; Natural Earth', 'rights': 'Public domain inputs; commercial use OK'}
        if meta.get('missing_dem_fraction', 0) > 0.01:
            print(f"  ⚠ basemap: {meta['missing_dem_fraction']:.1%} of DEM area missing (tile not downloaded)")
    if m.get('basemap', 'relief') in ('relief', 'dem'):
        if m.get('basemap', 'relief') == 'relief':
            img, meta = build_raster(c.proj, extent, float(m.get('raster_res', 1.0)), m.get('tone') or {})
            img.save(pub / 'relief.jpg', quality=92)
            ep['map']['raster'] = {'src': 'relief.jpg', 'x': meta['x'], 'y': meta['y'], 'width': meta['width'], 'height': meta['height']}
            provenance['basemap'] = {**meta, 'source': 'Local cached Esri World_Shaded_Relief tiles (.workbuddy)', 'attribution': 'Esri, USGS, NOAA', 'rights': 'Attribution shown. Public/commercial redistribution NOT cleared; internal review only.'}
        rx0, ry0, rx1, ry1 = meta['x'], meta['y'], meta['x'] + meta['width'], meta['y'] + meta['height']
        cams = ep['camera']
        for a, b in zip(cams, cams[1:]):
            for f in (0, .25, .5, .75, 1):
                z = math.exp(math.log(a['z']) + (math.log(b['z']) - math.log(a['z'])) * f)
                cx, cy = a['cx'] + (b['cx'] - a['cx']) * f, a['cy'] + (b['cy'] - a['cy']) * f
                if cx - W / 2 / z < rx0 or cx + W / 2 / z > rx1 or cy - H / 2 / z < ry0 or cy + H / 2 / z > ry1:
                    raise ScriptError(f"camera at {a['t'] + (b['t'] - a['t']) * f:.2f}s (zoom {z:.2f}) sees past the basemap; widen map.extent or zoom in")
        if meta.get('uncovered_fraction', 0) > 0.02:
            print(f"  ⚠ basemap: {meta['uncovered_fraction']:.1%} of raster has no cached tile (filled with paper)")
    if m.get('rivers', True) and m.get('look') != 'atlas':     # atlas draws its own ranked river bands (atlas_rivers)
        rivers_geo = ne10_rivers(int(m.get('river_rank', 6))) if m.get('basemap') == 'dem' else read_json(HERE / 'data' / 'rivers-ne50.geojson')
        ep['map']['rivers'] = project_lines(c.proj, rivers_geo, extent)
        provenance['rivers'] = 'Natural Earth 1:50m rivers (public domain); modern channels, not ancient reconstruction'
    region_groups: dict[str, list[str]] = {}
    for r in script.get('regions', []) or []:
        for need in ['file', 'source', 'precision']:
            if not r.get(need):
                raise ScriptError(f'region {r.get("id")}: needs `{need}` — no unsourced borders')
        geo = read_json((proj_dir / r['file']).resolve())
        ep['footer']['left'] += f" · 疆域「{r.get('name', r['id'])}」：{r['precision']}"
        provenance.setdefault('regions', []).append({k: r.get(k) for k in ['id', 'file', 'source', 'precision', 'license']})
        if r.get('name_field'):
            # Snapshot with several polities: one region each, colours by adjacency.
            import regions as snapshot
            for g in snapshot.load_snapshot(geo, r['name_field'], r.get('rename'), r.get('main'), r.get('slots')):
                rid = f"{r['id']}/{g['name']}"
                svg_path = ' '.join('M ' + ' L '.join('%.1f %.1f' % c.proj.world(x, y) for x, y in ring) + ' Z' for poly in g['polys'] for ring in poly)
                ax, ay = c.proj.world(*g['anchor'])
                ep['map']['regions'].append({'id': rid, 'name': g['name'], 'fill': g['fill'], 'edge': g['edge'], 'path': svg_path, 'source': r['source'],
                                             'precision': r['precision'], 'anchor': [round(ax, 1), round(ay, 1)] if r.get('labels', True) else None, 'main': g['name'] == r.get('main')})
                region_groups.setdefault(r['id'], []).append(rid)
        else:
            ep['map']['regions'].append({'id': r['id'], 'name': r.get('name', ''), 'fill': r.get('fill', '#b5523b'), 'edge': r.get('edge', '#7a2f1f'), 'path': project_polygons(c.proj, geo),
                                         'source': r['source'], 'precision': r['precision'], 'anchor': None, 'main': False})
            region_groups[r['id']] = [r['id']]
        if r.get('show', 'always') == 'always':
            ep['elements'][:0] = [{'type': 'region', 'region': rid, 'start': 0.0, 'end': ep['duration']} for rid in region_groups[r['id']]]
    # `- region: {id: group}` in a beat expands to every polity of that snapshot.
    expanded = []
    for e in ep['elements']:
        if e['type'] == 'region' and e['region'] in region_groups and e['region'] not in [x['id'] for x in ep['map']['regions']]:
            expanded += [{**e, 'region': rid} for rid in region_groups[e['region']]]
        else:
            expanded.append(e)
    ep['elements'] = expanded

    # commander portraits for medallions (army `head:` and chase): taken from the episode's `people`
    people = script.get('people') or {}
    def medal_image(name):
        pe = people.get(name) or {}
        src_rel = pe.get('image')
        if not src_rel:
            return None
        src = next((c for c in (proj_dir / src_rel, REMOTION / 'public' / src_rel, ROOT / src_rel) if c.exists()), None)
        if src is None:
            print(f"  ⚠ medallion portrait not found for {name}: {src_rel}")
            return None
        dst = pub / 'portraits' / src.name
        dst.parent.mkdir(exist_ok=True)
        shutil.copy2(src, dst)
        return f'portraits/{src.name}'
    for e in ep['elements']:
        tr = e.get('troops') or {}
        if tr.get('head_name'):
            img = medal_image(tr['head_name'])
            if img:
                tr['head_image'] = img
            else:
                tr.pop('head_name', None)
        if e.get('type') == 'camp' and e.get('unit'):
            # a unit inside a city it holds shows as its commander's medallion, not tents (第12批)
            img = medal_image(e['unit'])
            if img:
                e['image'] = img
        ch = e.get('chase')
        if ch:
            for role in ('leader', 'pursuer'):
                r = ch[role]
                img = medal_image(r['name'])
                if img:
                    r['src'] = img
                else:
                    print(f"  ⚠ chase: {r['name']} has no portrait; medallion left blank")
                    r['src'] = ''
    atlas = (script.get('map') or {}).get('look') == 'atlas'
    for e in ep['elements']:
        if atlas and e['type'] == 'flag' and not e.get('image'):
            # atlas look: a named person's flag becomes a round portrait badge when he has a portrait
            pe = (script.get('people') or {}).get(e['name'])
            if isinstance(pe, dict) and pe.get('image'):
                e['image'] = pe['image']
        holders = [e] if e['type'] in ('portrait', 'enter', 'person_card', 'exit') or (e['type'] in ('act', 'flag') and e.get('image')) else [e['left'], e['right']] if e['type'] in ('versus', 'forces') else e['actors'] if e['type'] == 'stage' else []
        for h in holders:
            if not h.get('image'):
                continue
            # image paths may be relative to the episode, to the Remotion public dir, or to the project root
            src = next((c for c in (proj_dir / h['image'], REMOTION / 'public' / h['image'], ROOT / h['image']) if c.exists()), proj_dir / h['image'])
            if not src.exists():
                print(f"  ⚠ image not found for {h.get('name')}: {h['image']} (using name card)")
                h['image'] = None
                continue
            dst = pub / 'portraits' / src.name
            dst.parent.mkdir(exist_ok=True)
            shutil.copy2(src, dst)
            h['image'] = f'portraits/{src.name}'
            with Image.open(src) as im:
                # A real cut-out (transparent background) floats freely; otherwise use a feathered frame.
                h['cutout'] = im.mode in ('RGBA', 'LA') and im.getchannel('A').getextrema()[0] < 16

    mcfg = script.get('music') if isinstance(script.get('music'), dict) else {}
    audio = mix_audio(timing, ep['duration'], script.get('voice') or {}, pub / 'mix.wav', ep.get('sfx'), (music_plan(script, timing), mcfg))
    if audio and audio.get('music'):
        ep['music'] = audio['music']
    if audio and ep.get('sfx'):
        audio['sfx'] = len(ep['sfx'])
    if audio:
        ep['audio'] = 'mix.wav'
    if audio and (script.get('voice') or {}).get('caption_timing') == 'word':
        # word-level caption times from the finished mix (voice: caption_timing: word; see wordtime.py)
        import wordtime
        try:
            ep['caption_timing'] = wordtime.retime(ep, pub / 'mix.wav')
            print(f"  caption timing (word): {ep['caption_timing']}", flush=True)
        except Exception as e:   # model missing or broken: keep the character-share timing rather than fail the build
            ep['caption_timing'] = {'mode': 'chars', 'error': f'{type(e).__name__}: {str(e)[:160]}'}
            print(f"  ⚠ caption timing (word) unavailable, kept character timing: {type(e).__name__}", flush=True)
    write_json(pub / 'episode.json', ep)
    write_review(out / 'review.md', script, ep, c, timing, audio)
    shutil.copy2(path, out / 'episode.yaml')
    write_json(out / 'build.json', {
        'build': ep['build'], 'episode': script['id'], 'script': str(path), 'script_sha256': sha256(path), 'created': dt.datetime.now().isoformat(timespec='seconds'),
        'duration': ep['duration'], 'timing': {'mode': timing['mode'], 'measurement': timing.get('measurement')}, 'audio': audio,
        'places': [{k: p[k] for k in ['id', 'ref', 'name', 'lon', 'lat', 'precision', 'source']} for p in c.places.values()],
        'sources': sorted(c.used_sources), 'provenance': provenance, 'warnings': c.warnings,
        'episode_json_sha256': sha256(pub / 'episode.json'),
    })
    print(f"staged {out}\n  {ep['duration']:.2f}s, timing={timing['mode']}, audio={'yes' if audio else 'NONE (silent)'}")
    # 画面审查: does the picture follow what the narration says (deaths, surrenders, cities changing hands, leftover units)
    try:   # a broken review must not fail a finished build
        import audit
        items = audit.audit(script, ep)
        (out / '画面审查.md').write_text(audit.report(script, items), encoding='utf-8')
        for x in items:
            print(f"  ⚠ 画面审查 第 {x['beat']} 拍 {audit.mmss(x['t'])} [{x['rule']}] {x['msg']}")
    except Exception as e:
        print(f"  ⚠ 画面审查没跑成：{type(e).__name__}: {e}")
    report_readings(script)
    return out, ep


def write_review(dst: Path, script: dict, ep: dict, c: 'Compiler', timing: dict, audio: dict | None) -> None:
    """One page for the human reviewer: narration vs. source text, places, caveats."""
    local = {x['id']: x for x in script.get('sources_local', []) or []}

    def cite(i):
        x = local.get(i) or c.reg.citations.get(i) or {}
        return f"《{x.get('work', i)}》{x.get('volume') or ''}"
    L = [f"# 审稿单：{script['title']}（{ep['build']}）", '',
         f"时长 {ep['duration']:.1f} 秒 · 配音 {timing['mode']} · 音频 {'有' if audio else '无（静音排版）'}", '']
    if script.get('notes'):
        L += ['## 史实说明', ''] + [f'- {n}' for n in script['notes']] + ['']
    L += ['## 旁白与出处', '', '| 拍 | 旁白 | 出处 | 原文依据 |', '|---|---|---|---|']
    for i, b in enumerate(script['beats']):
        L.append(f"| {i + 1} | {b.get('say', '')} | {'；'.join(cite(x) for x in b.get('sources', []))} | {b.get('quote', '（未摘原文）')} |")
    L += ['', '## 地点', '', '| 名称 | 库内 ID | 精度 | 坐标来源 | 状态 |', '|---|---|---|---|---|']
    gaz = GAZ_IDS()
    for p in c.places.values():
        state = '待人工复核（agent 入库）' if p['ref'] in gaz else ('本集临时点' if p['ref'].startswith('local:') else 'maindata')
        L.append(f"| {p['name']} | {p['ref']} | {p['precision']} | {p['source'] or '—'} | {state} |")
    arrows = [e for e in ep['elements'] if e['type'] == 'arrow']
    if arrows:
        L += ['', '## 箭头性质', '']
        L += [f"- {' → '.join(e['points'])}：{ {'recorded': '史载行动', 'direction': '方向示意', 'relation': '关系连线', 'flee': '败退 / 出奔（示意）'}[e['kind']]}{'（' + e['label'] + '）' if e.get('label') else ''}" for e in arrows]
    if timing.get('asr'):
        bad = [a for a in timing['asr'] if a['ratio'] < 0.92]
        L += ['', f"## 配音听写校对：{len(timing['asr']) - len(bad)}/{len(timing['asr'])} 句一致", '']
        L += [f"- 第 {a['beat']} 拍 听写「{a['heard']}」：{'；'.join(a['diff'])}" for a in bad] or ['- 全部一致（仍建议真人试听人名读音）']
    if c.warnings:
        L += ['', '## 警告', ''] + [f'- {w}' for w in c.warnings]
    if getattr(c, 'campaign_lines', None):
        L += ['', '## 战事账对照（事件 → 哪一拍讲到 → 画了什么）', ''] + c.campaign_lines
    L += ['', '## 需要你判断', '', '- 旁白是否忠于原文、有无过度演绎', '- 地点精度是否可以接受', '- 人名读音与混音（试听成片）', '']
    dst.write_text('\n'.join(L), encoding='utf-8')


def latest_build(path: Path) -> Path:
    script = load_script(path)
    builds = sorted((OUT_ROOT / script['id']).glob('*/build.json'), key=lambda p: p.stat().st_mtime)
    if not builds:
        raise ScriptError('no staged build; run `studio.py build` first')
    return builds[-1].parent


def report_progress(eid: str, stage: str, done: int | None = None, total: int | None = None, note: str = '', folder: str | None = None) -> None:
    """Write 05_项目/Remotion/studio/<id>/progress.json so the web Studio can show progress
    for builds and renders started anywhere (CLI, background, web)."""
    try:
        d = OUT_ROOT / eid
        d.mkdir(parents=True, exist_ok=True)
        f = d / 'progress.json'
        # several builds/renders may report at once: an empty or half-written file just means "no previous state"
        try:
            prev = read_json(f) if f.exists() else {}
        except ValueError:
            prev = {}
        if not isinstance(prev, dict):
            prev = {}
        started = prev.get('started') if prev.get('stage') == stage and prev.get('status') == 'running' else dt.datetime.now().timestamp()
        data = {'stage': stage, 'done': done, 'total': total, 'note': note, 'status': 'done' if stage == '完成' else 'running',
                'started': started, 'updated': dt.datetime.now().timestamp(), 'pid': os.getpid(),
                'folder': folder or prev.get('folder')}
        # write to a temp file and swap it in, so a reader never sees a truncated file (2026-10-12: empty progress.json broke a render)
        tmp = f.with_name(f'progress.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        for _ in range(5):
            try:
                os.replace(tmp, f)
                break
            except PermissionError:   # Windows: the web UI may be reading it this instant
                time.sleep(0.05)
        else:
            tmp.unlink(missing_ok=True)
    except OSError:
        pass


def npx(*args):
    return subprocess.run(['npx.cmd' if sys.platform == 'win32' else 'npx', 'remotion', *args], cwd=REMOTION, check=True)


def cmd_still(path: Path, times: list[float]) -> None:
    out = latest_build(path)
    ep = read_json(out / 'public' / 'episode.json')
    (out / 'stills').mkdir(exist_ok=True)
    if times == ['beats']:  # one frame in the middle of every beat's narration
        times = [round((s['voice_onset'] + s['voice_offset']) / 2, 2) for s in ep['segments']]
    # Bundle once, then render every frame from the bundle (no re-bundling per frame).
    bundle = out / '.bundle'
    npx('bundle', 'src/studio/index.tsx', f'--out-dir={bundle}', f'--public-dir={out / "public"}')
    try:
        for t in times:
            f = min(int(float(t) * ep['fps']), int(ep['duration'] * ep['fps']) - 1)
            npx('still', str(bundle), 'Episode', str(out / 'stills' / f'f{f:05d}.png'), f'--frame={f}', '--log=error', '--gl=angle')
    finally:
        shutil.rmtree(bundle, ignore_errors=True)
    files = sorted((out / 'stills').glob('f*.png'))
    # PIL, not ffmpeg concat+tile: a still that came out RGBA reset the tile and the sheet lost every frame
    # before it (第21集, 2026-10-25)
    from PIL import Image
    cols = 3
    rows = math.ceil(len(files) / cols)
    sheet = Image.new('RGB', (640 * cols, 360 * rows))
    for k, f in enumerate(files):
        with Image.open(f) as im:
            sheet.paste(im.convert('RGB').resize((640, 360)), ((k % cols) * 640, (k // cols) * 360))
    sheet.save(out / 'stills-sheet.jpg', quality=88)
    print(f'{len(files)} stills -> {out / "stills-sheet.jpg"}')


def cmd_render(path: Path) -> None:
    out = latest_build(path)
    ep = read_json(out / 'public' / 'episode.json')
    mp4 = out / f"{ep['id']}-{ep['build']}.mp4"
    # --gl=angle lets Chrome composite on the GPU (Direct3D); 8 workers measured fastest on a 16-thread CPU
    cmd = ['npx.cmd' if sys.platform == 'win32' else 'npx', 'remotion', 'render', 'src/studio/index.tsx', 'Episode', str(mp4),
           f'--public-dir={out / "public"}', '--gl=angle', f'--concurrency={RENDER_CONCURRENCY}']
    report_progress(ep['id'], '渲染', 0, None, '启动渲染器')
    proc = subprocess.Popen(cmd, cwd=REMOTION, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
    last = 0.0
    for line in proc.stdout:
        print(line, end='', flush=True)
        m = re.search(r'Rendered (\d+)/(\d+)(?:, time remaining: ([^,\r\n]+))?', line)
        now = dt.datetime.now().timestamp()
        if m and now - last > 1.5:
            last = now
            report_progress(ep['id'], '渲染', int(m.group(1)), int(m.group(2)), f'剩余约 {m.group(3)}' if m.group(3) else '')
        elif 'Encoded' in line and now - last > 1.5:
            last = now
            report_progress(ep['id'], '编码', None, None, line.strip()[:80])
    if proc.wait() != 0:
        report_progress(ep['id'], '失败', None, None, 'Remotion 渲染失败，见日志')
        raise ScriptError('remotion render failed')
    # no post-render self-check (2026-10-29, user: "去掉自检，我会自己看"): the full decode, volumedetect and
    # contact sheet read the whole film three times, ~10 min after the render was done. Only a quick probe stays.
    probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name,width,height,r_frame_rate,nb_frames,sample_rate', '-of', 'json', str(mp4)], capture_output=True, text=True, check=True).stdout)
    write_json(out / 'media-check.json', {'mp4': str(mp4), 'probe': probe, 'note': 'No self-check; the user reviews the film.'})
    report_progress(ep['id'], '完成', 1, 1, mp4.name, folder=str(mp4))
    print(json.dumps({'mp4': str(mp4), 'duration': probe.get('format', {}).get('duration')}, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- agent tools

def http_json(url: str, timeout=30):
    import time
    import urllib.request
    from urllib.error import HTTPError
    req = urllib.request.Request(url, headers={'User-Agent': 'HistoryStudio/1.0 (local research tool)'})
    for attempt in range(5):
        time.sleep(0.7)  # stay under Wikidata's anonymous rate limit
        try:
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            time.sleep(int(e.headers.get('Retry-After') or 3 * (attempt + 1)))


def wikidata_candidates(name: str, limit=6) -> list[dict]:
    from urllib.parse import quote
    found = http_json(f'https://www.wikidata.org/w/api.php?action=wbsearchentities&search={quote(name)}&language=zh&uselang=zh&format=json&limit={limit}')
    ids = [x['id'] for x in found.get('search', [])]
    if not ids:
        return []
    ents = http_json(f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={'|'.join(ids)}&props=labels|descriptions|claims&languages=zh|zh-cn|en&format=json")['entities']
    out = []
    for qid in ids:
        e = ents.get(qid, {})
        coord = (e.get('claims', {}).get('P625') or [{}])[0].get('mainsnak', {}).get('datavalue', {}).get('value')
        lab = e.get('labels', {})
        des = e.get('descriptions', {})
        out.append({
            'qid': qid, 'label': (lab.get('zh-cn') or lab.get('zh') or lab.get('en') or {}).get('value'),
            'description': (des.get('zh-cn') or des.get('zh') or des.get('en') or {}).get('value'),
            'lon': coord and round(coord['longitude'], 5), 'lat': coord and round(coord['latitude'], 5),
            'source': f'https://www.wikidata.org/wiki/{qid}',
        })
    return out


def cmd_places(names: list[str], year: int | None, web: bool) -> None:
    reg = Registry()
    result = {}
    for name in names:
        local = []
        for pid, p in reg.places.items():
            labels = [*p.get('aliases', []), *(n.get('text', '') for n in p.get('names', []))]
            if pid == name or any(name == a or (len(name) > 1 and name in a) for a in labels if a):
                local.append({'id': pid, 'name': (year and year_value(p.get('names'), year, 'text')) or next((a for a in labels if a and re.match(r'[一-鿿]', a)), pid),
                              'lon': p['coordinates'][0], 'lat': p['coordinates'][1], 'precision': p.get('coordinatePrecision'),
                              'source': p.get('coordinateSource'), 'from': 'gazetteer' if pid in GAZ_IDS() else 'maindata'})
        entry = {'local': local}
        if web and not local:
            try:
                seen, cands = set(), []
                for q in (name, name + '县', name + '城', name + '縣'):
                    for c in wikidata_candidates(q):
                        if c['lon'] is not None and c['qid'] not in seen:
                            seen.add(c['qid'])
                            cands.append(c)
                entry['wikidata'] = cands
            except Exception as e:  # network is optional
                entry['wikidata_error'] = str(e)
        result[name] = entry
    print(json.dumps(result, ensure_ascii=False, indent=1))


def GAZ_IDS() -> set[str]:
    return {p['id'] for p in read_json(GAZETTEER)['places']} if GAZETTEER.exists() else set()


def cmd_place_add(a) -> None:
    """Record a confirmed place in the shared gazetteer so later episodes reuse it."""
    data = read_json(GAZETTEER) if GAZETTEER.exists() else {'note': 'History Studio shared gazetteer. Added by agents/editors per episode; each entry carries source and precision. reviewStatus=agent means not yet human-reviewed.', 'places': []}
    if not re.fullmatch(r'[a-z0-9_]+', a.id):
        raise ScriptError('id must be lowercase ascii, e.g. suanzao_county')
    if a.id in {p['id'] for p in data['places']} or Registry().place(a.id):
        raise ScriptError(f'{a.id} already exists')
    for need in ['precision', 'source']:
        if not getattr(a, need):
            raise ScriptError(f'--{need} is required')
    lo = hi = None
    if a.years:  # "190-220", "-221-581" (BCE start) or "190.." open-ended
        m = re.fullmatch(r'(-?\d+)?(?:-|\.\.)(-?\d+)?', a.years.strip())
        if not m:
            raise ScriptError('--years like 190-220, -221-581 or 190..')
        lo, hi = (int(x) if x else None for x in m.groups())
    data['places'].append({
        'id': a.id, 'aliases': [a.name, *[x for x in (a.aliases or '').split(',') if x]], 'coordinates': [a.lon, a.lat],
        'coordinatePrecision': a.precision, 'coordinateSource': a.source, 'coordinateStatus': 'approximate',
        'names': [{'text': a.name, 'from': lo, 'to': hi}], 'tiers': [{'from': lo, 'to': hi, 'tier': a.tier}],
        'note': a.note or '', 'reviewStatus': 'agent', 'added': dt.date.today().isoformat(),
    })
    write_json(GAZETTEER, data)
    print(f'added {a.id} ({a.name}) to {GAZETTEER}')


def cmd_sources(terms: list[str], books: list[str] | None, limit: int, width: int) -> None:
    """Search the local Twenty-Four Histories corpus; every hit is citable by paragraph id."""
    files = sorted(CORPUS.glob('*.jsonl'))
    if books:
        files = [f for f in files if f.stem in books]
    hits = []
    for f in files:
        with f.open(encoding='utf-8') as fh:
            for line in fh:
                r = json.loads(line)
                t = r['text']
                if all(x in t for x in terms):
                    i = t.find(terms[0])
                    lo = max(0, i - width // 3)
                    hits.append({'id': r['id'], 'book': r['book'], 'juan': r.get('juanTitle'), 'unit': r.get('unitTitle'),
                                 'damaged': bool(r.get('damaged')) or '□' in t, 'text': ('…' if lo else '') + t[lo:lo + width] + ('…' if lo + width < len(t) else '')})
                    if len(hits) >= limit:
                        break
        if len(hits) >= limit:
            break
    print(json.dumps(hits, ensure_ascii=False, indent=1))


TEMPLATE = (HERE / 'templates' / 'episode.yaml')


def cmd_new(eid: str) -> None:
    d = PROJECTS / eid
    if (d / 'episode.yaml').exists():
        raise ScriptError(f'{d / "episode.yaml"} exists')
    d.mkdir(parents=True, exist_ok=True)
    (d / 'episode.yaml').write_text(TEMPLATE.read_text(encoding='utf-8').replace('__ID__', eid), encoding='utf-8')
    print(f'created {d / "episode.yaml"}')


@functools.lru_cache(None)
def prop_items() -> set:
    """Names `act: prop` can draw, read from the engine's PROPS table so the two never drift apart."""
    src = (REMOTION / 'src' / 'studio' / 'Acts.tsx').read_text(encoding='utf-8')
    block = src[src.index('const PROPS'):]
    block = block[:block.index('};')]
    return set(re.findall(r"([一-鿿]+):\s*'", block))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('new').add_argument('id')
    for name in ['voice', 'preview', 'render']:
        sub.add_parser(name).add_argument('script', type=Path)
    ck = sub.add_parser('check')
    ck.add_argument('script', type=Path)
    ck.add_argument('--json', action='store_true')
    pl = sub.add_parser('places', help='look up place names (local gazetteer, then Wikidata with --web)')
    pl.add_argument('names', nargs='+')
    pl.add_argument('--year', type=int)
    pl.add_argument('--web', action='store_true')
    pa = sub.add_parser('place-add', help='record a confirmed place in the shared gazetteer')
    for f in ['id', 'name', 'precision', 'source']:
        pa.add_argument('--' + f, required=f in ('id', 'name'))
    pa.add_argument('--lon', type=float, required=True)
    pa.add_argument('--lat', type=float, required=True)
    pa.add_argument('--aliases')
    pa.add_argument('--years', help='e.g. --years=190-220 or --years=-221-581')
    pa.add_argument('--tier', default='county', choices=['capital', 'province', 'commandery', 'county', 'stronghold', 'pass', 'ferry', 'region'])
    pa.add_argument('--note')
    so = sub.add_parser('sources', help='search the local Twenty-Four Histories corpus')
    so.add_argument('terms', nargs='+')
    so.add_argument('--books', nargs='+')
    so.add_argument('--limit', type=int, default=12)
    so.add_argument('--width', type=int, default=220)
    b = sub.add_parser('build')
    b.add_argument('script', type=Path)
    b.add_argument('--build')
    b.add_argument('--voice', choices=['placeholder', 'mimo', 'files', 'imported'], help='override voice.mode')
    st = sub.add_parser('still')
    st.add_argument('script', type=Path)
    st.add_argument('-t', nargs='+', default=['beats'], help='seconds, or `beats` for the middle of every beat')
    a = ap.parse_args(argv)
    try:
        if a.cmd == 'new':
            cmd_new(a.id)
        elif a.cmd == 'check':
            return cmd_check(a.script.resolve(), a.json)
        elif a.cmd == 'places':
            cmd_places(a.names, a.year, a.web)
        elif a.cmd == 'place-add':
            cmd_place_add(a)
        elif a.cmd == 'sources':
            cmd_sources(a.terms, a.books, a.limit, a.width)
        elif a.cmd == 'voice':
            t = run_voice(load_script(a.script), a.script.resolve().parent)
            print(json.dumps(t, ensure_ascii=False, indent=1))
        elif a.cmd == 'build':
            stage(a.script.resolve(), a.build, a.voice)
        elif a.cmd == 'preview':
            out = latest_build(a.script.resolve())
            npx('studio', 'src/studio/index.tsx', f'--public-dir={out / "public"}')
        elif a.cmd == 'still':
            cmd_still(a.script.resolve(), a.t)
        elif a.cmd == 'render':
            cmd_render(a.script.resolve())
    except ScriptError as e:
        print('✖', e)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
