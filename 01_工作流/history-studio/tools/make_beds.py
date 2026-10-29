"""Build looping 底声 (ambient bed) tracks from the pad / riser sounds in 03_素材/音效/网盘音效.

usage: python history-studio/tools/make_beds.py
Each mood: chosen pads are trimmed of silence (and of the riser's climax), level-matched, gently low-passed,
chained with long crossfades into ~3 minutes, and the end crossfaded into the start so it loops seamlessly.
Output: 03_素材/音乐/底声/<mood>.wav (48 kHz mono) + entries in 03_素材/音乐/library.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / '03_素材' / '音效' / '网盘音效'
OUT = ROOT / '03_素材' / '音乐' / '底声'
SR = 48000
PAD = '中间铺垫环境音-高级电影感-氛围音/中间铺垫环境音-高级电影感-氛围音 ({}).wav'
DARK = '中间-重金属环境音-底音-衔接音/重金属电影感环境音-开头-衔接音-底音 ({}).wav'
LYR = '抒情旅拍前奏铺垫音-氛围拉满-衔接音/抒情旅拍前奏铺垫音-氛围拉满-衔接音 ({}).wav'

# mood -> [(file, keep_until_sec or None)]; picked by measurement: low rhythm, dark spectrum, steady level
MOODS = {
    '底声·阴沉': {'use': '宫变、杀戮、阴谋、死亡', 'parts': [(DARK.format(3), None), (DARK.format(1), None), (PAD.format(30), None), (DARK.format(43), None)]},
    '底声·紧张': {'use': '权谋、对峙、劝谏、悬念', 'parts': [(PAD.format(18), None), (PAD.format(17), None), (PAD.format(21), None), (PAD.format(10), None), (PAD.format(22), None), (PAD.format(20), None), (PAD.format(19), None)]},
    '底声·舒展': {'use': '开场交代、结尾总结、下集预告', 'parts': [(LYR.format(25), 54.0), (LYR.format(10), 38.0), (LYR.format(18), 30.0)]},
}
TARGET = 180.0
XF = 4.0


def movavg(x: np.ndarray, w: int) -> np.ndarray:
    """Centred moving average in O(n) (np.convolve with a 2 s kernel took minutes)."""
    c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])
    i = np.arange(len(x))
    a, b = np.clip(i - w // 2, 0, len(x)), np.clip(i + w // 2 + 1, 0, len(x))
    return ((c[b] - c[a]) / np.maximum(1, b - a)).astype(np.float32)


def decode(p: Path) -> np.ndarray:
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(p), '-ac', '1', '-ar', str(SR), '-af', 'lowpass=f=7000', '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def trim(x: np.ndarray, until: float | None) -> np.ndarray:
    if until:
        x = x[: int(until * SR)]
    w = SR // 10
    env = np.sqrt(movavg(x ** 2, w))
    on = np.nonzero(env > 10 ** (-45 / 20))[0]
    if not len(on):
        return x[:0]
    x = x[on[0]: on[-1]]
    # level-match on the steady part
    body = np.abs(x) > 1e-4
    return x / (float(np.sqrt(np.mean(x[body] ** 2))) or 1) * 10 ** (-20 / 20)


def chain(parts: list[np.ndarray]) -> np.ndarray:
    xf = int(XF * SR)
    out = parts[0]
    k = 1
    while len(out) < TARGET * SR:
        p = parts[k % len(parts)]
        k += 1
        if len(p) < 2 * xf:
            continue
        r = np.linspace(0, 1, xf)
        out = np.concatenate([out[:-xf], out[-xf:] * np.cos(r * np.pi / 2) + p[:xf] * np.sin(r * np.pi / 2), p[xf:]])
    # loop seam: fade the tail into the head
    r = np.linspace(0, 1, xf)
    head = out[:xf].copy()
    out = out[xf:]
    out[-xf:] = out[-xf:] * np.cos(r * np.pi / 2) + head * np.sin(r * np.pi / 2)
    return out


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    OUT.mkdir(parents=True, exist_ok=True)
    lib_f = ROOT / '03_素材' / '音乐' / 'library.json'
    lib = json.loads(lib_f.read_text(encoding='utf-8'))
    import wave
    for mood, spec in MOODS.items():
        parts = [trim(decode(SRC / f), until) for f, until in spec['parts']]
        parts = [p for p in parts if len(p) > SR * 6]
        bed = chain(parts)
        # gentle leveller: a bed should sit still under the voice, so swell and dips are evened out (2 s window)
        w = 2 * SR
        env = np.sqrt(movavg(bed ** 2, w)) + 1e-6
        gain_db = np.clip((-21 - 20 * np.log10(env)) * 0.6, -6, 8)
        bed = bed * 10 ** (gain_db / 20)
        bed = bed / max(1e-6, float(np.abs(bed).max())) * 0.89 if np.abs(bed).max() > 0.89 else bed
        f = OUT / f'{mood.split("·")[1]}.wav'
        with wave.open(str(f), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(bed, -1, 1) * 32767).astype(np.int16).tobytes())
        lib['moods'][mood] = {'file': f'底声/{f.name}', 'use': spec['use'], 'loop': True,
                              'credit': '', 'source': '网盘音效包（文件夹标注可商用，来源未核实）',
                              'from': [p for p, _ in spec['parts']]}
        print(f'{mood}: {len(bed) / SR:.0f}s → {f.relative_to(ROOT)}')
    lib_f.write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
