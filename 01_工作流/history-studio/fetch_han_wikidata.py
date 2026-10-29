"""Find Wikidata items (CC0) for every Han commandery and county by exact label.

Batched SPARQL with VALUES of label literals (simplified + as-written forms,
with and without 郡/县 suffix, across zh language tags). Returns coordinates,
capital (P36) coordinates, inception/dissolution and descriptions so the
matcher can choose the Han-era unit. Polite pacing; honours Retry-After.

    python fetch_han_wikidata.py     # data/han-wikidata-candidates.json
"""

import json
import time
import urllib.request
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode

from regions import T2S

HERE = Path(__file__).resolve().parent
COMM = HERE / 'data' / 'han-commanderies.json'
OUT = HERE / 'data' / 'han-wikidata-candidates.json'
UA = {'User-Agent': 'HistoryStudio/1.0 (historical map research)', 'Accept': 'application/sparql-results+json'}
TAGS = ['zh', 'zh-hans', 'zh-hant', 'zh-cn', 'zh-tw', 'zh-hk']
EXTRA_T2S = str.maketrans('陽陰鄉縣國關門東開長馬臨溫潁鉅陳魯濟齊樂萊荊揚廬會呉陸隴漢涼張遼雲鄭衛趙鄴蘭鳳陝黽盧黃城', '阳阴乡县国关门东开长马临温颍巨陈鲁济齐乐莱荆扬庐会吴陆陇汉凉张辽云郑卫赵邺兰凤陕黾卢黄城')

Q = '''SELECT ?name ?i ?desc ?coord ?capcoord ?inc ?dis ?cls WHERE {
 VALUES ?l { %s }
 ?i rdfs:label ?l . BIND(STR(?l) AS ?name)
 OPTIONAL { ?i wdt:P625 ?coord }
 OPTIONAL { ?i wdt:P36 ?cap . ?cap wdt:P625 ?capcoord }
 OPTIONAL { ?i wdt:P571 ?inc } OPTIONAL { ?i wdt:P576 ?dis } OPTIONAL { ?i wdt:P31 ?cls }
 OPTIONAL { ?i schema:description ?desc FILTER(lang(?desc) IN ("zh","zh-hans","zh-cn","zh-hant")) }
 FILTER(BOUND(?coord) || BOUND(?capcoord)) }'''


def sparql(q: str):
    req = urllib.request.Request('https://query.wikidata.org/sparql', data=urlencode({'query': q}).encode(), headers={**UA, 'Content-Type': 'application/x-www-form-urlencoded'})
    for attempt in range(15):
        try:
            return json.load(urllib.request.urlopen(req, timeout=300))['results']['bindings']
        except HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 14:
                raise
            wait = int(e.headers.get('Retry-After') or 70)
            print(f'  WDQS {e.code}; retry in {wait}s', flush=True)
            time.sleep(wait)


def variants(name: str, suffixes) -> set[str]:
    base = {name, name.translate(T2S).translate(EXTRA_T2S)}
    return {b + s for b in base for s in suffixes}


def main():
    comm = json.loads(COMM.read_text(encoding='utf-8'))['commanderies']
    want = set()
    for j in comm:
        jn = j['jun']
        want |= variants(jn, [''])
        stem = jn[:-1] if jn[-1] in '郡國国尹' else jn
        want |= variants(stem, ['郡', '國', '国'])
        for c in j['counties']:
            want |= variants(c, ['', '县', '縣', '侯国', '侯國'])
    names = sorted(want)
    print(len(names), 'label strings', flush=True)
    rows = []
    batch = 220
    for k in range(0, len(names), batch):
        vals = ' '.join(f'"{n}"@{t}' for n in names[k:k + batch] for t in TAGS)
        got = sparql(Q % vals)
        rows += got
        print(f'  {min(k + batch, len(names))}/{len(names)} → {len(got)} rows', flush=True)
        time.sleep(3)

    def year(b):
        if not b:
            return None
        s = b['value']
        return (-1 if s.startswith('-') else 1) * int(s.lstrip('+-').split('-')[0])

    items = {}
    for r in rows:
        qid = r['i']['value'].rsplit('/', 1)[1]
        it = items.setdefault(qid, {'qid': qid, 'names': set(), 'desc': '', 'coord': None, 'capcoord': None, 'from': None, 'to': None, 'classes': set()})
        it['names'].add(r['name']['value'])
        if 'desc' in r and len(r['desc']['value']) > len(it['desc']):
            it['desc'] = r['desc']['value']
        for key in ('coord', 'capcoord'):
            if key in r and not it[key]:
                lon, lat = (float(x) for x in r[key]['value'][6:-1].split())
                it[key] = [round(lon, 5), round(lat, 5)]
        if 'inc' in r:
            y = year(r['inc'])
            it['from'] = y if it['from'] is None else min(it['from'], y)
        if 'dis' in r:
            y = year(r['dis'])
            it['to'] = y if it['to'] is None else max(it['to'], y)
        if 'cls' in r:
            it['classes'].add(r['cls']['value'].rsplit('/', 1)[1])
    out = [{**v, 'names': sorted(v['names']), 'classes': sorted(v['classes'])} for v in items.values()]
    OUT.write_text(json.dumps({'source': 'Wikidata SPARQL exact-label match (CC0)', 'fetched': time.strftime('%Y-%m-%d'), 'items': out}, ensure_ascii=False), encoding='utf-8')
    print(f'{len(out)} candidate items -> {OUT}')


if __name__ == '__main__':
    main()
