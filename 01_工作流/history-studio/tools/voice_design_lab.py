"""MiMo 音色设计实验：详细描述 → 定妆样音 → 用样音复刻合成连续旁白（保证整集音色一致）。

    python tools/voice_design_lab.py        # 输出到 06_报告/音色设计-<日期>/

音色设计每次调用都会略有不同，所以只用它生成一段"定妆样音"，正式配音一律用这段样音做复刻参考。
密钥从 MIMO_API_KEY 读取，不写入任何文件。
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))
import studio  # noqa: E402
import mimo_tts  # noqa: E402
import voice_lab as V  # noqa: E402

OUT = studio.ROOT / '06_报告' / f"音色设计-{dt.date.today():%Y%m%d}"

# 定妆样音的台词：有交代、有转折、有收束，约 30 秒
REF_TEXT = ('公元二百零八年的冬天，长江上刮起了东南风。曹操的几百艘战船，用铁链连成一片，停在赤壁对岸。'
            '没有人想到，一个老将的一封降书，会让这支天下最强的军队，在一夜之间灰飞烟灭。'
            '从这一天起，天下三分的格局，再也没有人能改变。')

# 描述按官方建议写：性别年龄、音色质感、情绪语气、语速节奏、角色场景；不写混响等后期词，不模仿真人
DESIGNS = [
    ('D1', '纪录片浑厚男声', '四十岁左右的男性纪录片旁白，嗓音低沉浑厚，胸腔共鸣饱满，带一点磁性的颗粒感；语速中等，不拖沓，咬字清晰；讲到历史转折时语气沉下来，像在大银幕前娓娓道来，让人身临其境。'),
    ('D2', '讲史博主', '三十岁左右的男性历史知识博主，嗓音清亮有底气，中音饱满；语速中等偏快且稳定，咬字利落；讲故事有起伏和悬念感，像在跟朋友讲一段精彩的往事，亲切自然，不油腻不夸张。'),
    ('D3', '说书先生', '五十岁左右的男性说书先生，嗓音醇厚、略带沙哑，标准普通话；节奏感强，抑扬顿挫，关键处稍作停顿再接着讲，带一点江湖气和幽默感，但吐字干净利落。'),
    ('D4', '冷静纪实', '三十五岁左右的男性，声音干净、稳重、略低沉；语气冷静克制，像高质量历史纪录片的解说员；语速稳定，几乎没有夸张的情绪，靠重音和停顿来表现张力。'),
    ('D5', '热血解说', '二十五岁左右的男性，声音明亮有力量，语速偏快，富有感染力；讲到战争场面时有紧张感和画面感，像热门短视频里的历史解说，节奏紧凑，句尾干脆。'),
    ('D6', 'MiniMax「history」同款描述', '历史纪录片男声旁白，声音浑厚深沉，富有磁性，娓娓道来历史事件时让人身临其境。'),
    ('D7', '知性女声', '三十岁左右的女性历史解说，声音清亮温润，知性大方；语速中等偏快且稳定，讲述时有画面感和故事感，情绪克制但有感染力。'),
]


def call(model, messages, audio):
    import urllib.request
    req = urllib.request.Request(mimo_tts.API_URL, data=json.dumps({'model': model, 'messages': messages, 'audio': audio}, ensure_ascii=False).encode(),
                                 headers={'Authorization': 'Bearer ' + mimo_tts.get_api_key(), 'Content-Type': 'application/json'})
    res = studio.with_backoff(lambda: json.load(urllib.request.urlopen(req, timeout=180)), 'TTS')
    return base64.b64decode(res['choices'][0]['message']['audio']['data'])


def design(key, desc):
    f = OUT / f'{key}-定妆样音.wav'
    if not f.exists():
        f.write_bytes(call(mimo_tts.VOICE_DESIGN_MODEL, [{'role': 'user', 'content': desc}, {'role': 'assistant', 'content': REF_TEXT}],
                           {'format': 'wav', 'optimize_text_preview': False}))
    return f


def clone_line(key, ref: Path, i, line):
    f = OUT / f'{key}-{i + 1}.wav'
    if not f.exists():
        voice = 'data:audio/wav;base64,' + base64.b64encode(ref.read_bytes()).decode()
        f.write_bytes(call(mimo_tts.VOICE_CLONE_MODEL, [{'role': 'user', 'content': V.DIRECTOR2}, {'role': 'assistant', 'content': line}],
                           {'format': 'wav', 'voice': voice}))
    return f


def load(f):
    pcm = OUT / f'_{f.stem}.pcm.wav'
    studio.ffmpeg_pcm(f, pcm)
    x = studio.read_pcm(pcm)
    pcm.unlink()
    return x / (np.max(np.abs(x)) or 1) * 0.89


def mp3(f: Path) -> str:
    m = f.with_suffix('.mp3')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(f), '-ac', '1', '-ar', '32000', '-b:a', '64k', str(m)], check=True)
    return 'data:audio/mpeg;base64,' + base64.b64encode(m.read_bytes()).decode()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        refs = dict(zip([d[0] for d in DESIGNS], pool.map(lambda d: design(d[0], d[2]), DESIGNS)))
        jobs = [(k, refs[k], i, line) for k in refs for i, line in enumerate(V.LINES[:5])]
        list(pool.map(lambda j: clone_line(*j), jobs))
    rows = []
    gap = np.zeros(int(0.16 * 48000), np.float32)
    text = ''.join(V.LINES[:5])
    for key, name, desc in DESIGNS:
        pieces = []
        for i, line in enumerate(V.LINES[:5]):
            x, _, _ = studio.clean_voice(load(OUT / f'{key}-{i + 1}.wav'), tail=False)
            y, _ = studio.even_out(x, line, 4.8, OUT / '_e')
            pieces.append(y / (np.max(np.abs(y)) or 1) * 0.89)
        seq = OUT / f'{key}-连读.wav'
        studio.write_pcm(seq, np.concatenate([np.concatenate([p, gap]) for p in pieces]))
        asr = studio.asr_check(seq, text)
        rows.append({'key': key, 'name': name, 'desc': desc, 'asr': round(asr['ratio'], 3), 'diff': asr['diff'][:3]})
        print(key, name, 'ASR', rows[-1]['asr'], rows[-1]['diff'], flush=True)
    (OUT / 'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    h = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MiMo 音色设计试听</title>',
         '<style>:root{--bg:#f2f2f7;--card:#fff;--ink:#1c1c1e;--ink2:#6e6e73}@media(prefers-color-scheme:dark){:root{--bg:#000;--card:#1c1c1e;--ink:#f5f5f7;--ink2:#98989d}}'
         'body{font:15px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;max-width:900px;margin:0 auto;padding:24px 16px;background:var(--bg);color:var(--ink)}'
         '.c{background:var(--card);border-radius:16px;padding:14px 18px;margin:12px 0;box-shadow:0 2px 10px #0001}b{font-size:17px}audio{width:100%;margin:6px 0}small{color:var(--ink2)}p.d{margin:4px 0 8px;font-size:13.5px;color:var(--ink2)}</style></head><body>',
         '<h2>MiMo 音色设计试听</h2><p><small>每个音色两段：<b>定妆样音</b>（音色设计模型直接生成，赤壁一段）；<b>正式效果</b>（用定妆样音做复刻参考，按 B2 导演指令合成高平陵 5 句，再逐句校准语速——正式出片就是这个效果）。</small></p>']
    for r in rows:
        k = r['key']
        h.append(f"<div class='c'><b>{k}　{r['name']}</b><p class='d'>描述：{r['desc']}</p>"
                 f"<small>定妆样音</small><audio controls preload='none' src='{mp3(OUT / f'{k}-定妆样音.wav')}'></audio>"
                 f"<small>正式效果（高平陵 5 句）· ASR {r['asr']}</small><audio controls preload='none' src='{mp3(OUT / f'{k}-连读.wav')}'></audio></div>")
    h.append('</body></html>')
    (OUT / '音色设计-试听.html').write_text('\n'.join(h), encoding='utf-8')
    print(OUT / '音色设计-试听.html')


if __name__ == '__main__':
    main()
