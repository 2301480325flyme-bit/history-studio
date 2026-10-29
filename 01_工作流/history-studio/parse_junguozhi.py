"""Parse 《后汉书·郡国志》 (志第十九–二十三) into provinces → commanderies → counties.

Source: zh.wikisource 後漢書/卷109–113 raw wikitext (public domain text),
cached in data/wikisource/. Structure: `==州==`, `===郡===`, counties in
`〖名…〗`. The treatise records the layout around 永和五年 (140 CE); per its
preface "凡县名先书者，郡所治也" the first county is the seat.

    python parse_junguozhi.py      # writes data/han-commanderies.json
"""

import json
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
CACHE = HERE / 'data' / 'wikisource'
OUT = HERE / 'data' / 'han-commanderies.json'
VOLUMES = range(109, 114)


def fetch(n: int) -> str:
    f = CACHE / f'hhs-{n}.wiki'
    if not f.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        u = 'https://zh.wikisource.org/w/index.php?title=' + quote(f'後漢書/卷{n}') + '&action=raw'
        f.write_text(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'HistoryStudio/1.0'}), timeout=60).read().decode('utf-8'), encoding='utf-8')
        time.sleep(1)
    return f.read_text(encoding='utf-8')


def strip_templates(s: str) -> str:
    """Drop commentary {{*|…}} (nested), keep the first argument of other templates."""
    out, i = [], 0
    while i < len(s):
        if s.startswith('{{', i):
            depth, j = 0, i
            while j < len(s):
                if s.startswith('{{', j):
                    depth += 1
                    j += 2
                elif s.startswith('}}', j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            body = s[i + 2:j - 2]
            if not body.startswith('*|') and '|' in body:
                out.append(strip_templates(body.split('|')[1]))
            i = j
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def main():
    result = []
    zhou = None
    for n in VOLUMES:
        text = strip_templates(fetch(n))
        text = re.sub(r'-\{([^}]*)\}-', r'\1', text)  # MediaWiki language-conversion markup
        jun = None
        for line in text.splitlines():
            m3 = re.match(r'^===\s*(.+?)\s*===\s*$', line)
            m2 = re.match(r'^==\s*(.+?)\s*==\s*$', line)
            # 卷113 style: "◎　汉中郡秦置。…"
            m4 = re.match(r'^[\s　]*◎[\s　]*(.+?)(?=秦|高帝|武帝|昭帝|宣帝|明帝|章帝|和帝|安帝|顺帝|順帝|灵帝|靈帝|光武|故|本|。|，|雒阳|雒陽)', line)
            if m3 or m4:
                name = (m3 or m4).group(1).strip()
                jun = {'jun': name, 'zhou': zhou, 'seat': None, 'counties': [], 'volume': f'後漢書/卷{n}'}
                result.append(jun)
                if m3:
                    continue
            elif m2:
                zhou = m2.group(1).strip()
                jun = None
                continue
            if jun is None:
                continue
            if 'cities_stated' not in jun:
                c = re.search(r'([一二三四五六七八九十百]+)城', line)
                if c:
                    jun['cities_stated'] = c.group(1)
            names = re.findall(r'〖([^〗]+)〗', line)
            if not names and not m4:
                # 卷110–112 style: one county per indented line, "平輿，有沈亭…" / "汝陽，"
                body = line.strip(' 　')
                head = re.match(r'^([一-鿿\[\]A-Z0-9]{1,6})[，,。]', body)
                if head and not body.startswith(jun['jun'][:2]) and not re.search(r'[置改屬属]', head.group(1)):
                    names = [head.group(1)]
            for name in names:
                name = re.sub(r'[（(].*?[)）]|[〔〕\s]|\[[A-Z0-9]+\]', '', name)
                if name and name not in jun['counties']:
                    jun['counties'].append(name)
    result = [j for j in result if j['jun'] != '校勘記' and j['zhou'] != '史論']
    for j in result:
        if j['jun'] == '巴陵':  # 卷113 typo for 巴郡 (the text describes 巴郡: 江州 seat, 十四城)
            j['jun'], j['note'] = '巴郡', '原文作「巴陵」，据所领江州等十四城当为巴郡'
        j['seat'] = j['counties'][0] if j['counties'] else None
    OUT.write_text(json.dumps({'source': '《後漢書》志第十九至二十三 郡國志（zh.wikisource 卷109–113，公有领域）', 'epoch': '约永和五年（140）', 'commanderies': result},
                              ensure_ascii=False, indent=1), encoding='utf-8')
    zs = {}
    for j in result:
        zs.setdefault(j['zhou'], []).append(j['jun'])
    print(f'{len(result)} commanderies, {sum(len(j["counties"]) for j in result)} counties')
    for z, js in zs.items():
        print(f'  {z}: {len(js)} — {"、".join(js)}')
    print([j['jun'] for j in result if not j['counties']])


if __name__ == '__main__':
    main()
