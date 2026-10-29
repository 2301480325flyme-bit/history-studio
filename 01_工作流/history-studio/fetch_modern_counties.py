"""Locate Han counties by their modern county-level successor (Wikidata, CC0).

Reads data/han-counties-modern.json (郡 → 县 → 今县级驻地, compiled from
standard historical-geography knowledge), geocodes the modern names by exact
Wikidata label, keeps the candidate nearest the commandery's known points, and
fills only the counties that data/han-county-coords.json has not located yet
(existing Wikidata matches are kept as they are). Points more than 2.5° (3.5° in the large southern
commanderies, 4° on the frontier) from the commandery are rejected.

    python fetch_modern_counties.py && python cells.py han-140
"""

import json
import math
import statistics
from pathlib import Path

from fetch_han_wikidata import sparql

HERE = Path(__file__).resolve().parent
TAGS = ['zh', 'zh-hans', 'zh-cn']
Q = '''SELECT ?name ?i ?coord ?desc WHERE {
 VALUES ?l { %s } ?i rdfs:label ?l ; wdt:P625 ?coord . BIND(STR(?l) AS ?name)
 OPTIONAL { ?i schema:description ?desc FILTER(lang(?desc) IN ("zh","zh-hans","zh-cn")) } }'''
ADMIN = ('市', '县', '縣', '区', '區', '旗', '自治')
FRONTIER = ('涼州', '凉州', '并州', '幽州', '益州', '交州')
WIDE = ('揚州', '扬州', '荊州', '荆州')   # 豫章、武陵、长沙等大郡，南部县离郡治本来就远


def main():
    table = json.loads((HERE / 'data' / 'han-counties-modern.json').read_text(encoding='utf-8'))['counties']
    path = HERE / 'data' / 'han-county-coords.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    rows_all = data['counties']
    seats = json.loads((HERE / 'data' / 'han-seats-geocoded.json').read_text(encoding='utf-8'))['seats']
    names = sorted({m for js in table.values() for m in js.values()})
    cands: dict[str, list] = {}
    for k in range(0, len(names), 150):
        for r in sparql(Q % ' '.join(f'"{n}"@{t}' for n in names[k:k + 150] for t in TAGS)):
            lon, lat = (float(x) for x in r['coord']['value'][6:-1].split())
            if 90 <= lon <= 135 and 8 <= lat <= 50:
                cands.setdefault(r['name']['value'], []).append({'qid': r['i']['value'].rsplit('/', 1)[1], 'lon': lon, 'lat': lat,
                                                                 'desc': r.get('desc', {}).get('value', '')})
    located = lambda r: r.get('qid') and 'far-from-jun' not in r.get('why', [])

    def ref(jun):
        if jun in seats:
            return seats[jun]['lon'], seats[jun]['lat']
        pts = [(r['lon'], r['lat']) for r in rows_all if r['jun'] == jun and located(r)]
        return (statistics.median(p[0] for p in pts), statistics.median(p[1] for p in pts)) if pts else None

    added, rejected, missing = 0, [], []
    for r in rows_all:
        if located(r):
            continue
        modern = (table.get(r['jun']) or {}).get(r['county'])
        if not modern:
            continue
        cs = cands.get(modern)
        if not cs:
            missing.append(modern)
            continue
        cs = [c for c in cs if any(k in c['desc'] for k in ADMIN)] or cs
        rp = ref(r['jun'])
        pick = min(cs, key=lambda c: math.hypot(c['lon'] - rp[0], c['lat'] - rp[1])) if rp else cs[0]
        far = math.hypot(pick['lon'] - rp[0], pick['lat'] - rp[1]) if rp else 0
        if far > (4.0 if r['zhou'] in FRONTIER else 3.5 if r['zhou'] in WIDE else 2.5):
            rejected.append((r['jun'], r['county'], modern, round(far, 1)))
            continue
        r.update({'qid': pick['qid'], 'label': modern, 'desc': pick['desc'][:40], 'lon': pick['lon'], 'lat': pick['lat'],
                  'precision': 'modern-successor', 'score': 2, 'why': ['modern-successor-table']})
        added += 1
    data['source'] += '; + modern successor table data/han-counties-modern.json (Wikidata CC0 coordinates)'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    ok = sum(1 for r in rows_all if located(r))
    print(f'added {added}; counties located now {ok}/{len(rows_all)}')
    print('no wikidata label:', sorted(set(missing)))
    print('rejected (too far):', rejected)


if __name__ == '__main__':
    main()
