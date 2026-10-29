"""Original synthesized sound effects for History Studio (no samples, so no licence questions).

    python tools/synth_sfx.py            # writes 03_素材/音效/原创合成/*.wav and prints their lengths

Instruments are modelled from their physics, not imitated from recordings:
- 编钟 bianzhong: a struck bronze bell — inharmonic partials (bell ratios), each decaying at its own rate,
  plus a short metallic strike transient. Low partials ring long, high ones die fast.
- 大鼓 big drum: a pitched membrane thump (pitch falls 95 → 48 Hz) plus a soft noise skin slap.
- 磬 qing (stone chime): stiffer, brighter partials, shorter ring than bronze.
- 铜钱 copper cash: many tiny metallic clicks (random high partials, 20–70 ms each); clusters thin out
  as a heap settles.
Deterministic (fixed seeds) so every rebuild sounds identical.
"""
import wave
from pathlib import Path

import numpy as np

SR = 48000
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / '03_素材' / '音效' / '原创合成'

# bronze bell partial ratios (approximate, Chinese two-tone bells are close to western bell spectra)
BELL = [(0.5, 0.35, 5.5), (1.0, 1.0, 3.6), (1.19, 0.45, 2.8), (1.5, 0.30, 2.2), (2.0, 0.55, 1.8),
        (2.51, 0.28, 1.2), (2.98, 0.22, 0.9), (4.07, 0.14, 0.55), (5.16, 0.08, 0.35)]
STONE = [(1.0, 1.0, 1.4), (2.76, 0.5, 0.7), (5.4, 0.25, 0.35), (8.9, 0.12, 0.18)]

# 宫商角徵羽 on G3 (196 Hz): low enough to be solemn, high enough to ring like bronze rather than a dull gong
GONG, SHANG, JUE, ZHI, YU = 196.0, 220.0, 246.94, 293.66, 329.63


def env_strike(n, tau):
    t = np.arange(n) / SR
    return np.exp(-t / tau) * (1 - np.exp(-t / 0.002))


def bell(f, dur=4.5, amp=1.0, seed=0, partials=BELL):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for r, a, tau in partials:
        det = 1 + rng.normal(0, 0.002)                    # slight detune → shimmer
        beat = 1 + 0.08 * np.sin(2 * np.pi * (0.7 + rng.random()) * t)   # two-tone beating of real bells
        x += a * beat * np.sin(2 * np.pi * f * r * det * t + rng.random() * 6.28) * env_strike(n, tau)
    hit = rng.normal(0, 1, int(0.03 * SR))                 # mallet on bronze: short bright noise
    hit = np.convolve(hit, np.ones(6) / 6, 'same') * np.exp(-np.arange(len(hit)) / (0.006 * SR))
    x[:len(hit)] += 0.35 * hit
    return amp * x / np.max(np.abs(x))


def drum(dur=2.2, amp=1.0, seed=1, f0=95.0, f1=48.0):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.09)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / 0.55) + 0.35 * np.sin(2 * ph * 1.5) * np.exp(-t / 0.18)
    skin = rng.normal(0, 1, n) * np.exp(-t / 0.035)
    skin = np.convolve(skin, np.ones(30) / 30, 'same')
    x = body + 0.5 * skin
    return amp * x / np.max(np.abs(x))


def coins(dur=1.8, density=60, seed=3, settle=True, amp=1.0):
    """A heap of copper cash poured out: clicks thick at first, thinning as it settles."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = np.zeros(n)
    k = int(density * dur)
    times = rng.beta(1.3, 3.0 if settle else 1.0, k) * (dur - 0.12)
    for i, t0 in enumerate(np.sort(times)):
        m = int(rng.uniform(0.02, 0.07) * SR)
        tt = np.arange(m) / SR
        click = np.zeros(m)
        base = rng.uniform(2600, 5200)                       # small bronze discs ring high
        for r in (1.0, 1.47, 2.09, 2.56):
            click += np.sin(2 * np.pi * base * r * tt + rng.random() * 6.28) * rng.uniform(0.3, 1)
        click *= np.exp(-tt / rng.uniform(0.006, 0.02))
        a = rng.uniform(0.25, 1.0) * (1 - 0.5 * t0 / dur)
        s = int(t0 * SR)
        x[s:s + m] += a * click[: n - s]
    # a low dull bed: the heap itself (cash on a wooden table)
    t = np.arange(n) / SR
    thud = rng.normal(0, 1, n) * np.exp(-t / 0.25)
    thud = np.convolve(thud, np.ones(220) / 220, 'same')
    x += 1.6 * thud
    return amp * x / np.max(np.abs(x))


def place(track, clip, at):
    s = int(at * SR)
    e = min(len(track), s + len(clip))
    track[s:e] += clip[: e - s]


def reverb(x, wet=0.25, seed=7):
    """Cheap hall: a few decaying echoes, so the bells sit in a palace hall rather than a box."""
    rng = np.random.default_rng(seed)
    y = x.copy()
    for d, g in [(0.031, 0.5), (0.047, 0.42), (0.071, 0.35), (0.113, 0.28), (0.167, 0.2), (0.241, 0.14), (0.353, 0.09)]:
        k = int(d * SR * (1 + rng.uniform(-0.05, 0.05)))
        y[k:] += wet * g * x[:-k]
    return y


def fade(x, fin=0.005, fout=0.6):
    a, b = int(fin * SR), int(fout * SR)
    x[:a] *= np.linspace(0, 1, a)
    x[-b:] *= np.linspace(1, 0, b)
    return x


def save(name, x, peak=0.89):
    OUT.mkdir(parents=True, exist_ok=True)
    x = x / (np.max(np.abs(x)) or 1) * peak
    with wave.open(str(OUT / f'{name}.wav'), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype('<i2').tobytes())
    print(f'{name}.wav  {len(x) / SR:.1f}s')


def main():
    # 登基 A: three bells rising 宫 → 徵 → 宫(8va), then the big drum, a long bronze tail
    x = np.zeros(int(6.5 * SR))
    for i, (f, at) in enumerate([(GONG, 0.0), (ZHI, 0.75), (GONG * 2, 1.5)]):
        place(x, bell(f, 5.0, 0.9, seed=10 + i), at)
    place(x, drum(2.5, 1.1), 2.35)
    place(x, bell(GONG, 4.0, 0.5, seed=20), 2.35)
    save('登基-编钟三响大鼓', fade(reverb(x)))

    # 登基 B: drum first (the court assembles), then two deep bells together (宫 + 徵), quieter and grander
    x = np.zeros(int(6.0 * SR))
    place(x, drum(2.2, 1.0, f0=88, f1=44), 0.0)
    place(x, drum(2.2, 0.8, seed=2, f0=88, f1=44), 0.55)
    place(x, bell(GONG, 5.0, 0.9, seed=31), 1.2)
    place(x, bell(ZHI, 5.0, 0.6, seed=32), 1.2)
    save('登基-双鼓合钟', fade(reverb(x, 0.3)))

    # 登基 C: bells + stone chime (钟磬齐鸣), lighter — for 册封 / 受禅 rather than a full enthronement
    x = np.zeros(int(5.5 * SR))
    place(x, bell(ZHI, 4.5, 0.8, seed=41), 0.0)
    place(x, bell(GONG * 2, 4.5, 0.7, seed=42, partials=STONE), 0.45)
    place(x, bell(YU * 2, 4.5, 0.6, seed=43, partials=STONE), 0.9)
    place(x, bell(GONG, 4.5, 0.8, seed=44), 1.35)
    save('册封-钟磬齐鸣', fade(reverb(x)))

    # 卖官 A: a heap of cash poured onto a table
    save('卖官-铜钱倾倒', fade(coins(1.8, 70, seed=3), fout=0.3))
    # 卖官 B: two handfuls counted out (two short pours), drier — 明码标价
    x = np.zeros(int(2.2 * SR))
    place(x, coins(0.8, 55, seed=5), 0.0)
    place(x, coins(0.9, 55, seed=6), 1.0)
    save('卖官-两把铜钱', fade(x, fout=0.25))
    # 卖官 C: one string of cash dropped (a few dense clicks + thud)
    save('卖官-一串铜钱落桌', fade(coins(0.9, 45, seed=8, settle=True), fout=0.2))

    # 单独的编钟、大鼓（以后排列组合用）
    save('编钟-单响-宫', fade(reverb(bell(GONG, 4.0, seed=51))))
    save('大鼓-单击', fade(drum(2.0), fout=0.4))


if __name__ == '__main__':
    main()
