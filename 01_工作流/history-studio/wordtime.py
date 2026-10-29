"""Word-level caption timing (2026-10-19 experiment, after auto-subtitles).

Captions used to be timed by each chunk's share of characters inside its beat, so long
sentences drift. Here faster-whisper (cached model, no network) transcribes the finished
mix, each caption's characters are aligned to the recognised characters, and the caption
takes the time of its first and last matched character. Anything that does not align well
keeps its character-share timing, so a bad recognition can only leave a caption as it was.
"""
from __future__ import annotations

import difflib
import re

MARGIN = 0.07          # same padding as the character-share timing
MIN_COVER = 0.8        # share of a caption's characters that must align
MAX_SHIFT = 1.0        # larger moves than this are treated as misalignment


def _strip(t: str) -> str:
    return re.sub(r'[\W_]', '', t)


def retime(ep: dict, mix_path, model_name: str = 'small') -> dict:
    """Rewrite segments[*].captions[*].t0/t1 in place; return a summary for build.json."""
    from faster_whisper import WhisperModel

    caps = []   # (segment, caption) in reading order
    for seg in ep['segments']:
        for c in seg.get('captions', []) or []:
            caps.append((seg, c))
    ref = ''.join(_strip(c['text']) for _, c in caps)
    if not ref:
        return {'mode': 'word', 'changed': 0, 'fallback': 0}

    def transcribe(device, compute):
        m = WhisperModel(model_name, device=device, compute_type=compute, local_files_only=True)
        s, _ = m.transcribe(str(mix_path), language='zh', word_timestamps=True, vad_filter=False, beam_size=1)
        return list(s)   # run here, so a CUDA failure surfaces inside the try below

    # GPU first (RTX 3050 laptop, 4 GB); CPU int8 if CUDA cannot load (e.g. missing cublas64_12.dll)
    try:
        segs = transcribe('cuda', 'float16')
    except (RuntimeError, ValueError, OSError):
        segs = transcribe('cpu', 'int8')
    chars = []  # (char, start, end): word time spread linearly over its characters
    for seg in segs:
        for w in seg.words or []:
            t = _strip(w.word)
            if not t:
                continue
            step = (w.end - w.start) / len(t)
            chars += [(ch, w.start + k * step, w.start + (k + 1) * step) for k, ch in enumerate(t)]
    hyp = ''.join(x[0] for x in chars)

    times = [None] * len(ref)
    for a, b, n in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        for k in range(n):
            times[a + k] = (chars[b + k][1], chars[b + k][2])

    changed = fallback = 0
    pos = 0
    for seg, c in caps:
        n = len(_strip(c['text']))
        if n == 0:
            continue
        mine = times[pos:pos + n]
        pos += n
        hit = [m for m in mine if m is not None]
        if len(hit) / n < MIN_COVER:
            fallback += 1
            continue
        t0 = max(seg['start'], hit[0][0] - MARGIN)
        t1 = min(seg['end'], hit[-1][1] + MARGIN)
        if abs(t0 - c['t0']) > MAX_SHIFT or abs(t1 - c['t1']) > MAX_SHIFT or t1 <= t0:
            fallback += 1
            continue
        c['t0'], c['t1'] = round(t0, 3), round(t1, 3)
        changed += 1
    return {'mode': 'word', 'model': model_name, 'captions': len(caps), 'changed': changed, 'fallback': fallback,
            'char_match': round(sum(x is not None for x in times) / len(ref), 3)}
