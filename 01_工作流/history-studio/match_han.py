"""Match 郡国志 commanderies/counties to Wikidata candidate items.

Input: data/han-commanderies.json, data/han-wikidata-candidates.json.
Output: data/han-county-coords.json (consumed by cells.py) with per-county
coordinates, the chosen QID, a precision class and the reasons.

Precision classes:
  ancient   – item described as an ancient/former county, city site or Han unit
  modern    – a modern place with the same name used as an approximation
Same-name places elsewhere are resolved by distance to the commandery's other
members and to the commandery item itself.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from regions import T2S

HERE = Path(__file__).resolve().parent
EXTRA = str.maketrans('陽陰鄉縣國關門東開長馬臨溫潁鉅陳魯濟齊樂萊荊揚廬會呉陸隴漢涼張遼雲鄭衛趙鄴蘭鳳陝黽盧黃', '阳阴乡县国关门东开长马临温颍巨陈鲁济齐乐莱荆扬庐会吴陆陇汉凉张辽云郑卫赵邺兰凤陕黾卢黄')
BBOX = (92, 8, 132, 46)
ANCIENT = ('古县', '古縣', '旧县', '舊縣', '故城', '遗址', '遺址', '古城', '古代', '汉朝', '漢朝', '东汉', '東漢', '西汉', '西漢', '秦朝', '历史', '歷史', '郡', '侯国', '侯國', '已废', '已廢', '中国古代')
NOISE = ('人物', '演员', '演員', '植物', '动物', '电影', '電影', '小说', '小說', '车站', '車站', '公司', '学校', '學校', '姓', '山峰', '河流', '湖泊', '寺', '游戏', '遊戲', '歌曲', '星')


def norm(s: str) -> str:
    return s.translate(T2S).translate(EXTRA)


def score(item, base: str) -> tuple[float, str, list[str]]:
    why, s = [], 0.0
    names = {norm(n) for n in item['names']}
    b = norm(base)
    if names & {b + '县', b + '侯国', b + '国', b + '道', b + '邑'}:
        s += 2
        why.append('county-label')
    elif b in names:
        s += 1
        why.append('bare-label')
    d = item['desc']
    ancient = any(k in d for k in ANCIENT)
    if ancient:
        s += 3
        why.append('ancient-desc')
    if any(k in d for k in NOISE):
        s -= 4
        why.append('noise')
    f, t = item['from'], item['to']
    if f is not None and f <= 160 and (t is None or t >= 120):
        s += 3
        why.append('alive-140')
    elif f is not None and f > 600:
        s -= 1
        why.append('later')
    return s, ('ancient' if ancient or 'alive-140' in why else 'modern'), why


def coord(item):
    return item['coord'] or item['capcoord']


def main():
    comm = json.loads((HERE / 'data' / 'han-commanderies.json').read_text(encoding='utf-8'))['commanderies']
    items = json.loads((HERE / 'data' / 'han-wikidata-candidates.json').read_text(encoding='utf-8'))['items']
    by_name: dict[str, list] = {}
    for it in items:
        c = coord(it)
        if not c or not (BBOX[0] <= c[0] <= BBOX[2] and BBOX[1] <= c[1] <= BBOX[3]):
            continue
        for n in it['names']:
            by_name.setdefault(norm(n), []).append(it)

    def candidates(base, suffixes):
        seen, out = set(), []
        for s in suffixes:
            for it in by_name.get(norm(base) + s, []):
                if it['qid'] not in seen:
                    seen.add(it['qid'])
                    out.append(it)
        return out

    results, jun_anchor = [], {}
    seats_file = HERE / 'data' / 'han-seats-geocoded.json'
    seats = json.loads(seats_file.read_text(encoding='utf-8'))['seats'] if seats_file.exists() else {}
    for j in comm:
        stem = j['jun'][:-1] if j['jun'][-1] in '郡國国尹' else j['jun']
        jc = [it for it in candidates(stem, ['郡', '国', '']) + candidates(j['jun'], ['']) if any(k in it['desc'] for k in ('郡', '国', '國', '汉', '漢', '古'))]
        if jc:
            jun_anchor[j['jun']] = coord(max(jc, key=lambda it: (it['from'] is not None and it['from'] <= 200, len(it['desc']))))
    for j in comm:
        scored = {}
        for n in j['counties']:
            cs = []
            for it in candidates(n, ['县', '侯国', '国', '道', '']):
                s, prec, why = score(it, n)
                if s >= 1:
                    cs.append((s, prec, why, it))
            scored[n] = sorted(cs, key=lambda x: -x[0])
        seat = seats.get(j['jun'])
        frontier = (j['zhou'] or '') in ('涼州', '并州', '幽州', '益州', '交州')
        radius = 4.0 if frontier else 2.2
        if seat:
            mx, my = seat['lon'], seat['lat']
        else:
            confident = [cs[0][3] for cs in scored.values() if cs and cs[0][1] == 'ancient']
            mx = statistics.median(coord(c)[0] for c in confident) if confident else None
            my = statistics.median(coord(c)[1] for c in confident) if confident else None
        for n in j['counties']:
            cs = scored[n]
            row = {'zhou': j['zhou'], 'jun': j['jun'], 'county': n, 'seat': n == j['seat'], 'qid': None}
            if cs and mx is not None:
                best = max(cs, key=lambda x: x[0] - 1.5 * math.hypot(coord(x[3])[0] - mx, coord(x[3])[1] - my))
                far = math.hypot(coord(best[3])[0] - mx, coord(best[3])[1] - my)
                s_, prec, why, it = best
                if far > radius:
                    why = why + ['far-from-jun']
                lon, lat = coord(it)
                row.update({'qid': it['qid'], 'label': it['names'][0], 'desc': it['desc'][:40], 'lon': lon, 'lat': lat, 'precision': prec, 'score': s_, 'why': why})
            results.append(row)
    out = HERE / 'data' / 'han-county-coords.json'
    out.write_text(json.dumps({'source': 'Wikidata (CC0) exact-label candidates; 《后汉书·郡国志》 structure', 'counties': results, 'jun_anchor': jun_anchor},
                              ensure_ascii=False, indent=1), encoding='utf-8')
    ok = [r for r in results if r['qid'] and 'far-from-jun' not in r['why']]
    anc = [r for r in ok if r['precision'] == 'ancient']
    seats = [r for r in results if r['seat']]
    jun_cov = sum(1 for j in comm if any(r['jun'] == j['jun'] and r['qid'] and 'far-from-jun' not in r['why'] for r in results))
    print(f'counties located {len(ok)}/{len(results)} (ancient {len(anc)}, modern-approx {len(ok) - len(anc)}); seats {sum(1 for r in seats if r["qid"])}/{len(seats)}; '
          f'commanderies with ≥1 point {jun_cov}/{len(comm)}; commandery anchors {len(jun_anchor)}')
    print('commanderies with no point:', [j['jun'] for j in comm if not any(r['jun'] == j['jun'] and r['qid'] and 'far-from-jun' not in r['why'] for r in results)])


if __name__ == '__main__':
    main()
