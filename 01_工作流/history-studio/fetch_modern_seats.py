"""Geocode modern seat locations of Han commanderies via Wikidata (CC0).

Reads data/han-seats-modern.json, queries exact labels, picks the
administrative unit nearest the commandery's other located points (or its
province's), and writes data/han-seats-geocoded.json.
"""

import json
import math
import statistics
from pathlib import Path

from fetch_han_wikidata import sparql

HERE = Path(__file__).resolve().parent
TAGS = ['zh', 'zh-hans', 'zh-cn', 'zh-hant']
Q = '''SELECT ?name ?i ?coord ?desc WHERE {
 VALUES ?l { %s } ?i rdfs:label ?l ; wdt:P625 ?coord . BIND(STR(?l) AS ?name)
 OPTIONAL { ?i schema:description ?desc FILTER(lang(?desc) IN ("zh","zh-hans","zh-cn")) } }'''
ADMIN = ('市', '县', '縣', '区', '區', '旗', '省', '首都', '城市', '自治')


def main():
    table = json.loads((HERE / 'data' / 'han-seats-modern.json').read_text(encoding='utf-8'))['seats']
    names = sorted({v[1] for v in table.values()})
    rows = sparql(Q % ' '.join(f'"{n}"@{t}' for n in names for t in TAGS))
    cands: dict[str, list] = {}
    for r in rows:
        lon, lat = (float(x) for x in r['coord']['value'][6:-1].split())
        if not (90 <= lon <= 135 and 8 <= lat <= 46):
            continue
        desc = r.get('desc', {}).get('value', '')
        cands.setdefault(r['name']['value'], []).append({'qid': r['i']['value'].rsplit('/', 1)[1], 'lon': lon, 'lat': lat, 'desc': desc})
    coords = json.loads((HERE / 'data' / 'han-county-coords.json').read_text(encoding='utf-8'))['counties']
    comm = json.loads((HERE / 'data' / 'han-commanderies.json').read_text(encoding='utf-8'))['commanderies']
    zhou_of = {j['jun']: j['zhou'] for j in comm}

    def ref_for(jun):
        pts = [(c['lon'], c['lat']) for c in coords if c['jun'] == jun and c.get('qid') and 'far-from-jun' not in c.get('why', [])]
        if not pts:
            pts = [(c['lon'], c['lat']) for c in coords if zhou_of.get(c['jun']) == zhou_of.get(jun) and c.get('qid') and 'far-from-jun' not in c.get('why', [])]
        return (statistics.median(p[0] for p in pts), statistics.median(p[1] for p in pts)) if pts else None

    out, missing = {}, []
    for jun, (ancient, modern) in table.items():
        cs = cands.get(modern, [])
        if not cs:
            missing.append((jun, modern))
            continue
        ref = ref_for(jun)
        admin = [c for c in cs if any(k in c['desc'] for k in ADMIN)] or cs
        pick = min(admin, key=lambda c: math.hypot(c['lon'] - ref[0], c['lat'] - ref[1])) if ref else admin[0]
        far = round(math.hypot(pick['lon'] - ref[0], pick['lat'] - ref[1]), 2) if ref else None
        out[jun] = {'seat': ancient, 'modern': modern, **pick, 'dist_to_ref_deg': far,
                    'precision': '郡治今址近似（现代驻地坐标）'}
    (HERE / 'data' / 'han-seats-geocoded.json').write_text(json.dumps({'source': 'Wikidata (CC0) modern place coordinates; seat table data/han-seats-modern.json', 'seats': out},
                                                                      ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'geocoded {len(out)}/{len(table)}; missing {missing}')
    print('far from reference (>3°):', [(j, v['modern'], v['dist_to_ref_deg']) for j, v in out.items() if (v['dist_to_ref_deg'] or 0) > 3])


if __name__ == '__main__':
    main()
