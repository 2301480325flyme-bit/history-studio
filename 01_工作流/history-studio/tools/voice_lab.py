"""MiMo 配音实验：同一段连续旁白用多种方案合成，量语速、做 ASR，拼成可直接试听的对比音频。

    python tools/voice_lab.py            # 输出到 06_报告/配音实验-<日期>/

密钥从 MIMO_API_KEY 读取，不写入任何文件。
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIO = HERE.parent
sys.path.insert(0, str(STUDIO))
sys.path.insert(0, str(STUDIO.parent))   # 01_工作流/mimo_tts.py
import studio  # noqa: E402
import mimo_tts  # noqa: E402

ROOT = studio.ROOT
REF = ROOT / '03_素材' / '配音参考' / 'studio-voice' / 'studio-voice-v2.wav'
OUT = ROOT / '06_报告' / f"配音实验-{dt.date.today():%Y%m%d}"

# 一段连续旁白（高平陵之变）+ 一句长列举 + 一句短收束：最容易暴露语速忽快忽慢
LINES = [
    '新皇帝才八岁，大权落到了宗室曹爽手里。七十岁的司马懿，干脆称病在家。',
    '公元二百四十九年，曹爽陪着小皇帝，出城去高平陵扫墓。',
    '病了好几年的司马懿突然起身，关闭洛阳城门，夺了兵权。',
    '曹爽交出兵权，还以为能做个富家翁，结果被灭了三族。',
    '从这一天起，魏国还姓曹，权力却姓了司马。',
    '南边是淮南袁术，江东孙策，荆州刘表，益州刘璋，各占一方。',
    '蜀汉，亡了。',
]

STYLE_C = '讲故事的语气，交代处平稳，转折处语气上扬、加快，结果处下沉留白，整体语速偏快。'
DIRECTOR = ('角色：一位讲历史的短视频解说员，三十岁上下的男性，声音清亮有底气，像在给朋友讲一段精彩的往事。\n'
            '场景：抖音历史地图视频的旁白，整集几十句话要像一口气讲下来，前后语速必须一致。\n'
            '指导：语速稳定、偏快，大约每秒四到五个字，不要忽快忽慢；句子之间不拖沓，不叹气、不明显换气；'
            '转折处用重音和语调变化来表现，而不是突然加速；结局处语气下沉，但语速不要明显放慢。')
DIRECTOR2 = ('角色：一位讲历史的短视频解说员，三十岁上下的男性，声音清亮有底气，像在给朋友讲一段精彩的往事。\n'
             '场景：抖音历史地图视频的旁白，整集几十句话要像一口气讲下来。\n'
             '指导：每个分句都用同样的中等偏快语速读，不要某一段突然抢快或拖慢；逗号处自然停顿约四分之一秒，句号处略长；'
             '情绪靠语调高低和重音表现，不靠改变语速；不叹气，不明显换气。')
STEADY = '用稳定均匀的语速讲述，每秒约四到五个字，整段保持同一节奏和音量，不叹气，不明显换气，句尾干净收住。'

# 方案：(编号, 名称, 模型, user 指令生成函数, assistant 文本生成函数, voice)
def plain(i, line):
    return line


def tagged(i, line):
    # 音频标签：开头整体风格，转折句加细粒度标签
    t = '(沉稳 干练)' + line
    if '突然' in line:
        t = t.replace('突然起身', '[语气一紧]突然起身')
    if '结果' in line:
        t = t.replace('结果', '[停顿]结果')
    return t


def with_context(make):
    def f(i, line):
        prev = LINES[i - 1] if i and i < 5 else ''
        base = make(i, line)
        return (f'上一句（已读完）：「{prev}」\n请紧接上一句，用完全相同的语速、音量和音色读下一句。\n' + base) if prev else base
    return f


VARIANTS = [
    ('A', '现状：复刻音色 + C 风格', 'clone', lambda i, l: STYLE_C, plain),
    ('B', '复刻音色 + 导演模式（角色/场景/指导）', 'clone', lambda i, l: DIRECTOR, plain),
    ('B2', '复刻音色 + 导演模式（改：分句匀速、逗号停顿）', 'clone', lambda i, l: DIRECTOR2, plain),
    ('C', '复刻音色 + 稳定语速指令', 'clone', lambda i, l: STEADY, plain),
    ('D', '复刻音色 + 导演模式 + 上一句上下文', 'clone', with_context(lambda i, l: DIRECTOR), plain),
    ('E', '复刻音色 + 音频标签（沉稳 干练）', 'clone', lambda i, l: '', tagged),
    ('F', '预置男声「苏打」+ 导演模式', '苏打', lambda i, l: DIRECTOR, plain),
    ('G', '预置男声「白桦」+ 导演模式', '白桦', lambda i, l: DIRECTOR, plain),
    ('H', '音色设计：纪录片解说男声', 'design', lambda i, l: '三十岁左右的男性历史解说员，声音清亮、干净、有磁性，咬字清楚，像高质量纪录片和知识类短视频的旁白，语速偏快且稳定，讲故事时有起伏但不夸张。', plain),
]


def call(model: str, messages: list, audio: dict) -> bytes:
    req = urllib.request.Request(mimo_tts.API_URL, data=json.dumps({'model': model, 'messages': messages, 'audio': audio}, ensure_ascii=False).encode(),
                                 headers={'Authorization': 'Bearer ' + mimo_tts.get_api_key(), 'Content-Type': 'application/json'})
    res = studio.with_backoff(lambda: json.load(urllib.request.urlopen(req, timeout=180)), 'TTS')
    return base64.b64decode(res['choices'][0]['message']['audio']['data'])


def synth(variant, i, line, out: Path):
    key, _, kind, instr, text = variant
    if out.exists():
        return
    msgs = []
    u = instr(i, line)
    if u:
        msgs.append({'role': 'user', 'content': u})
    msgs.append({'role': 'assistant', 'content': text(i, line)})
    if kind == 'clone':
        ref = 'data:audio/wav;base64,' + base64.b64encode(REF.read_bytes()).decode()
        data = call(mimo_tts.VOICE_CLONE_MODEL, msgs, {'format': 'wav', 'voice': ref})
    elif kind == 'design':
        data = call(mimo_tts.VOICE_DESIGN_MODEL, msgs, {'format': 'wav', 'optimize_text_preview': False})
    else:
        data = call(mimo_tts.PRESET_MODEL, msgs, {'format': 'wav', 'voice': kind})
    out.write_bytes(data)


def chars(s: str) -> int:
    return len(re.sub(r'[^一-鿿0-9A-Za-z]', '', s))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(v, i, line, OUT / f'{v[0]}-{i + 1}.wav') for v in VARIANTS for i, line in enumerate(LINES)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda j: synth(*j), jobs))
    rows = []
    for v in VARIANTS:
        rates, asr, pieces = [], [], []
        for i, line in enumerate(LINES):
            f = OUT / f'{v[0]}-{i + 1}.wav'
            pcm = OUT / f'{v[0]}-{i + 1}.pcm.wav'
            studio.ffmpeg_pcm(f, pcm)
            x = studio.read_pcm(pcm)
            pcm.unlink()
            x = x / (np.max(np.abs(x)) or 1) * 0.89
            x, _, _ = studio.clean_voice(x)
            on, off = studio.voice_bounds(x)
            rates.append(chars(line) / max(0.3, off - on))
            asr.append(studio.asr_check(f, line)['ratio'])
            pieces.append(x)
        # 前五句连读（模拟成片里的衔接），句间 0.16 秒
        gap = np.zeros(int(0.16 * 48000), np.float32)
        seq = np.concatenate([np.concatenate([p, gap]) for p in pieces[:5]])
        studio.write_pcm(OUT / f'{v[0]}-连读.wav', seq)
        r = np.array(rates[:5])
        rows.append({'key': v[0], 'name': v[1], 'rate_mean': round(float(r.mean()), 2), 'rate_sd': round(float(r.std()), 2),
                     'rate_min': round(float(r.min()), 2), 'rate_max': round(float(r.max()), 2),
                     'list_rate': round(rates[5], 2), 'short_rate': round(rates[6], 2), 'asr_min': round(min(asr), 2)})
    (OUT / 'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    lines = ['# MiMo 配音实验', '', f'连读样本：高平陵之变 5 句。语速为原始合成（未变速）的 字/秒；波动 = 标准差，越小越稳。', '',
             '| 方案 | 说明 | 平均语速 | 波动 | 最慢–最快 | 长列举句 | 短收束句 | ASR 最低 |', '|---|---|---|---|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['key']} | {r['name']} | {r['rate_mean']} | {r['rate_sd']} | {r['rate_min']}–{r['rate_max']} | {r['list_rate']} | {r['short_rate']} | {r['asr_min']} |")
    lines += ['', '试听：`<方案>-连读.wav` 是前五句连起来的效果；`<方案>-6.wav`、`-7.wav` 是长列举句和短收束句。']
    (OUT / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
