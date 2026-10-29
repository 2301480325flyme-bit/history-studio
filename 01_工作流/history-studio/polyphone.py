"""读音预检 (2026-10-28, user: "有没有问题能一劳永逸解决掉").

MiMo reads everyday words right; what it gets wrong is names, titles and old words (乐进, 刘禅, 毌丘俭,
仆射, 单于, 禅让) and rare characters (叡, 頠, 遹). Swapping every polyphone automatically does more harm
than good (it would touch 长安, 将领, 投降…), so this lists only the risky words that nobody has checked yet:

- a polyphonic or rare character inside a name the narration speaks (portraits, speakers, armies, flags,
  places on the map);
- a rare character (outside the 3,755 common GB2312 characters) anywhere in the narration;
- a word from the old-words list below.

Each one is settled once in `series/三国到隋/读音.yaml`: `spoken:` (a same-sound substitute, as before) or
`confirmed:` (the plain text reads right). Then it never comes up again, in any episode.
`studio.py check` and `build` print what is still open.

    python history-studio/polyphone.py --all s01e18 s01e43 [--out report.md]
"""
from __future__ import annotations

import argparse
import re
import sys
from functools import lru_cache
from pathlib import Path

import yaml
from pypinyin import Style, pinyin
from pypinyin.pinyin_dict import pinyin_dict

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SERIES_TABLE = ROOT / 'series' / '三国到隋' / '读音.yaml'

# old words whose reading is not the everyday one (checked against 汉语大词典 usage)
OLD_WORDS = ['禅让', '禅位', '受禅', '单于', '可汗', '仆射', '长史', '长子', '阏氏', '冒顿', '月氏', '龟兹', '吐谷浑',
             '万俟', '尉迟', '会稽', '番禺', '犍为', '大宛', '身毒', '令狐', '皋陶', '骠骑', '车骑', '都尉', '校尉',
             '中常侍', '尚书令', '太傅', '少帝', '还军', '还师', '降将', '乐府', '乐浪', '燕王', '燕国', '前燕', '后燕',
             '南燕', '北燕', '西燕', '燕然', '朝歌', '单父', '句注', '句丽', '高句丽', '谷蠡', '撑犁', '亡命', '遗诏']
# characters whose reading in names and places is often not the everyday one (乐进 yuè, 单于 chán, 会稽 kuài,
# 番禺 pān, 荥阳 xíng, 六安 lù…); pypinyin lists a second reading for far more (司, 王, 石), which MiMo reads fine
POLY = set('乐单长仆解曾区查盖朴尉万召种繁员华冼相车宿隗贾缪覃秘那句令会阏番龟吐冒氏沓阆降校骑朝重藏屏谷蔚浚燕莎洗叶'
           '任柏沈纪应般济泌郫犍荥渑六莘费亳厦栎蕃秭邳郯鄄郏莒繇射禅率还行传将数说参')
NAME_FIELDS = ('who', 'name', 'head', 'unit', 'left', 'right', 'leader', 'speaker')
PLACE_FIELDS = ('at', 'from', 'to', 'via', 'places')


def readings(c: str) -> list[str]:
    raw = pinyin_dict.get(ord(c))
    return raw.split(',') if raw else []


def common(c: str, level: int = 1) -> bool:
    """In GB2312: level 1 = the 3,755 everyday characters, level 2 = all 6,763."""
    try:
        b = c.encode('gb2312')
    except UnicodeEncodeError:
        return False
    return len(b) == 2 and 0xB0 <= b[0] <= (0xD7 if level == 1 else 0xF7)


@lru_cache(maxsize=None)
def table() -> dict:
    return (yaml.safe_load(SERIES_TABLE.read_text(encoding='utf-8')) or {}) if SERIES_TABLE.exists() else {}


def settled() -> list[str]:
    t = table()
    return [*(t.get('spoken') or {}), *(t.get('confirmed') or [])]


def guess(word: str) -> str:
    return ' '.join(x[0] for x in pinyin(word, style=Style.TONE))


def names_of(script: dict) -> tuple[set, set]:
    people, places = set(script.get('portraits') or {}), set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in NAME_FIELDS and isinstance(v, str):
                    people.add(v)
                elif k in PLACE_FIELDS:
                    for p in (v if isinstance(v, list) else [v]):
                        if isinstance(p, str):
                            places.add(p)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(script.get('beats') or [])
    return {n for n in people if re.fullmatch(r'[一-鿿]{2,5}', n)}, {p for p in places if re.fullmatch(r'[一-鿿]{1,6}', p)}


def risky(script: dict) -> list[dict]:
    """Open items: [{word, kind, why, beat, guess}], one per word (first beat it is spoken in)."""
    beats = [(k, b.get('voice_text', b['say'])) for k, b in enumerate(script.get('beats') or [], 1) if isinstance(b, dict) and b.get('say')]
    done = settled()

    def covered(word, line, at):
        # a settled entry covers the word when it overlaps this occurrence
        for s in done:
            j = line.find(s, max(0, at - len(s) + 1))
            while j != -1 and j < at + len(word):
                if j + len(s) > at:
                    return True
                j = line.find(s, j + 1)
        return False

    found = {}

    def first(word, kind, why):
        for k, line in beats:
            i = line.find(word)
            while i != -1:
                if not covered(word, line, i):
                    found.setdefault(word, {'word': word, 'kind': kind, 'why': why, 'beat': k, 'guess': guess(word)})
                    return
                i = line.find(word, i + 1)

    people, places = names_of(script)
    for kind, group in (('人名', people), ('地名', places)):
        for n in group:
            poly = [c for c in n if c in POLY and len(readings(c)) > 1]
            rare = [c for c in n if not common(c)]
            if poly or rare:
                first(n, kind, '多音字 ' + '、'.join(poly) if poly else '生僻字 ' + '、'.join(rare))
    for w in OLD_WORDS:
        first(w, '古称', '古读')
    for k, line in beats:
        for i, c in enumerate(line):
            if '一' <= c <= '鿿' and not common(c, 2) and not covered(c, line, i):
                w = line[max(0, i - 1):i + 2]
                found.setdefault(c, {'word': c, 'kind': '生僻字', 'why': f'「{w}」', 'beat': k, 'guess': guess(c)})
    return sorted(found.values(), key=lambda r: r['beat'])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--all', nargs=2, metavar=('FROM', 'TO'), required=True, help='episode range, e.g. s01e18 s01e43')
    ap.add_argument('--out', help='write a Markdown report here')
    a = ap.parse_args(argv)
    lo, hi = (int(re.sub(r'\D', '', x)) for x in a.all)
    words = {}
    for d in sorted((ROOT / 'projects').glob('s01e*')):
        if lo <= int(re.sub(r'\D', '', d.name.split('-')[0])) <= hi and (d / 'episode.yaml').exists():
            for r in risky(yaml.safe_load((d / 'episode.yaml').read_text(encoding='utf-8'))):
                words.setdefault(r['word'], {**r, 'eps': []})['eps'].append(d.name.split('-')[0][4:])
    md = ['# 读音预检', '', f"范围 {a.all[0]}–{a.all[1]}：{len(words)} 个词还没核过读音。",
          '核过的写进 `series/三国到隋/读音.yaml`：读得对的放 `confirmed:`，读不对的在 `spoken:` 里写同音替换。', '',
          '| 词 | 类别 | 原因 | pypinyin 猜测 | 出现集数 |', '|---|---|---|---|---|']
    for r in sorted(words.values(), key=lambda r: (r['kind'], r['eps'][0])):
        md.append(f"| {r['word']} | {r['kind']} | {r['why']} | {r['guess']} | {'、'.join(r['eps'])} |")
    text = '\n'.join(md) + '\n'
    if a.out:
        Path(a.out).write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
