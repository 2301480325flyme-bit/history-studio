"""建安郡格子（han-219）：在《后汉书·郡国志》140 年郡国上，按史载把建安年间新设的郡拆出来。

每个新郡写明从哪些原郡拿走哪些县（原郡里其余的县留在原郡）、治所和出处。新郡的州按 219 年实际归属写（上庸三郡此时仍属益州汉中，魏文帝合为新城郡才划入荆州）；新郡记下 `parent`（县数最多的那个
原郡），疆域.yaml 里写原郡名时自动包含它拆出来的新郡；写新郡名则只动这一郡。
只收 219 年前后已经设立、史有明文的郡；赤壁以后各家自设而年代有争议的（义阳、临川、临贺等）不收。

    python derive_219.py && python cells.py han-219

输出：data/han-219-commanderies.json（结构同 han-commanderies.json，多 parent/year/source）、
      data/han-219-county-coords.json（县治坐标按新郡重新归属）。
"""

from __future__ import annotations

import json
from pathlib import Path

from regions import norm

HERE = Path(__file__).resolve().parent

# name, zhou, seat, year, source, take: {原郡: [县…]}, extra: [[县名, 今县级驻地]] 原郡国志里没有、按今址补点的县
SPLITS = [
    ('新兴郡', '并州', '九原', 215, '三国志·武帝纪（建安二十年省云中定襄五原朔方郡，郡置一县领其民，合以为新兴郡）', {}, [['九原', '忻州市'], ['定襄', '定襄县']]),
    ('乐平郡', '并州', '沾', 210, '晋书·地理志上（乐平郡，汉末置）', {'上党郡': ['沾'], '常山國': ['上艾']}, [['轑阳', '左权县']]),
    ('章武郡', '冀州', '东平舒', 210, '晋书·地理志上（章武国，泰始元年置；三国志·魏志多见章武郡）', {'勃海郡': ['章武'], '河間國': ['束州', '東平舒']}, []),
    ('博陵郡', '冀州', '博陵', 200, '晋书·地理志上（博陵国，汉末置）', {'中山國': ['蠡吾', '安國'], '安平國': ['南深']}, [['博陵', '蠡县']]),
    ('乐陵郡', '青州', '厌次', 210, '晋书·地理志上（乐陵国，汉末置）', {'平原郡': ['樂陵', '厭次', '般', '濕陰']}, []),
    ('谯郡', '豫州', '谯', 213, '三国志·魏志（谯郡，建安末分沛置）', {'沛國': ['譙', '酇', '蘄', '銍', '龍亢', '鄲'], '汝南郡': ['城父', '山桑']}, []),
    ('东莞郡', '徐州', '东莞', 200, '三国志·臧霸传（汉末东莞郡）', {'琅邪國': ['東莞', '東安'], '泰山郡': ['蓋']}, []),
    ('城阳郡', '徐州', '东武', 198, '三国志·臧霸传（建安三年分琅邪、东海、北海为城阳、利城、昌虑郡）', {'琅邪國': ['東武', '諸', '姑幕'], '北海國': ['高密', '夷安', '淳於', '安丘']}, []),
    ('利城郡', '徐州', '利城', 198, '三国志·臧霸传（同上）', {'東海郡': ['利城', '祝其', '贛楡']}, []),
    ('南乡郡', '荆州', '南乡', 208, '晋书·地理志下（顺阳郡，汉建安中曹操分南阳立南乡郡）', {'南陽郡': ['南鄉', '順陽', '丹水', '析', '武當', '築陽', '陰', '酇']}, []),
    ('章陵郡', '荆州', '章陵', 208, '三国志·魏志（章陵郡，汉末分南阳置）', {'南陽郡': ['章陵', '蔡陽', '襄鄉', '湖陽']}, []),
    ('襄阳郡', '荆州', '襄阳', 208, '晋书·地理志下（襄阳郡，魏武帝平荆州，分南郡编以北及南阳之山都立）', {'南郡': ['襄陽', '中盧', '邔', '宜城', '臨沮'], '南陽郡': ['鄧']}, []),
    ('宜都郡', '荆州', '夷道', 210, '三国志·先主传注、晋书·地理志下（宜都郡，汉临江郡，建安十五年刘备改）', {'南郡': ['夷道', '夷陵', '很山']}, []),
    ('蕲春郡', '扬州', '蕲春', 208, '三国志·吴主传（蕲春郡）', {'江夏郡': ['蘄春', '邾']}, []),
    ('西城郡', '益州', '西城', 215, '三国志·刘封传（申仪西城、申耽上庸、房陵三郡）', {'汉中郡': ['西城', '锡', '安阳']}, []),
    ('上庸郡', '益州', '上庸', 215, '三国志·刘封传', {'汉中郡': ['上庸']}, []),
    ('房陵郡', '益州', '房陵', 215, '三国志·刘封传', {'汉中郡': ['房陵']}, []),
    ('新都郡', '扬州', '始新', 208, '三国志·贺齐传（建安十三年分歙为新都郡）', {'丹陽郡': ['歙', '黝']}, []),
    ('鄱阳郡', '扬州', '鄱阳', 210, '三国志·吴主传（建安十五年分豫章为鄱阳郡）', {'豫章郡': ['鄱陽', '餘汗', '歷陵', '鄡陽']}, []),
    ('庐陵郡', '扬州', '庐陵', 194, '三国志·孙策传注、晋书·地理志下（兴平元年分豫章立庐陵郡）', {'豫章郡': ['廬陵', '贛', '雩都', '南野', '石陽', '新淦']}, []),
    ('巴西郡', '益州', '阆中', 201, '华阳国志·巴志（建安六年刘璋改巴为巴西）', {'巴郡': ['阆中', '安汉', '充国']}, []),
    ('巴东郡', '益州', '鱼复', 201, '华阳国志·巴志（固陵郡，后改巴东）', {'巴郡': ['鱼复', '朐忍']}, []),
    ('宕渠郡', '益州', '宕渠', 215, '三国志·先主传（建安二十年后分巴西置宕渠郡）', {'巴郡': ['宕渠', '汉昌']}, []),
    ('梓潼郡', '益州', '梓潼', 217, '华阳国志·汉中志（建安二十二年分广汉立梓潼郡）', {'广汉郡': ['梓潼', '涪', '白水', '葭萌']}, []),
    ('江阳郡', '益州', '江阳', 213, '华阳国志·蜀志（建安十八年刘璋分犍为立江阳郡）', {'犍为郡': ['江阳', '符节', '汉安']}, []),
    ('汶山郡', '益州', '汶江', 220, '三国志·先主传、华阳国志（刘备置汶山郡）', {'蜀郡': ['汶江道', '绵虒道', '广柔', '湔氐道']}, []),
    ('西平郡', '凉州', '西都', 210, '晋书·地理志上（西平郡，汉献帝建安中置）', {'金城郡': ['临羌', '破羌', '安夷']}, [['西都', '西宁市']]),
    ('南安郡', '凉州', '豲道', 188, '晋书·地理志上（南安郡，汉中平五年置）', {'汉阳郡': ['豲道']}, []),
    ('西郡', '凉州', '日勒', 210, '晋书·地理志上（西郡，汉献帝分张掖置）', {'张掖郡': ['日勒', '删丹']}, []),
]


def main():
    comm = json.loads((HERE / 'data' / 'han-commanderies.json').read_text(encoding='utf-8'))['commanderies']
    coords = json.loads((HERE / 'data' / 'han-county-coords.json').read_text(encoding='utf-8'))['counties']
    modern = json.loads((HERE / 'data' / 'han-seats-geocoded.json').read_text(encoding='utf-8'))
    by_norm = {norm(j['jun']): j for j in comm}
    units = [{**j, 'counties': list(j['counties']), 'parent': norm(j['jun']), 'year': 140, 'source': '后汉书·郡国志'} for j in comm]
    unit_of = {norm(j['jun']): u for j, u in zip(comm, units)}
    moved = {}                       # (原郡 norm, 县 norm) → 新郡名
    problems = []
    extra_seeds = []
    for name, zhou, seat, year, src, take, extra in SPLITS:
        counties, weight = [], {}
        for jn, cs in take.items():
            j = by_norm.get(norm(jn))
            if not j:
                problems.append(f'{name}: 原郡 {jn} 不存在')
                continue
            have = {norm(c): c for c in j['counties']}
            for c in cs:
                if norm(c) not in have:
                    problems.append(f'{name}: {jn} 里没有县 {c}')
                    continue
                unit_of[norm(jn)]['counties'].remove(have[norm(c)])
                counties.append(have[norm(c)])
                moved[(norm(jn), norm(c))] = name
                weight[norm(jn)] = weight.get(norm(jn), 0) + 1
        for cname, place in extra:
            counties.append(cname)
            extra_seeds.append({'jun': name, 'county': cname, 'modern': place})
        parent = max(weight, key=weight.get) if weight else norm(next(iter(take), '') or '')
        if not parent:   # 新兴郡：全是侨置县，挂在太原郡下
            parent = '太原郡'
        units.append({'zhou': zhou, 'jun': name, 'seat': seat, 'counties': counties, 'parent': parent, 'year': year, 'source': src})
    if extra_seeds:      # 侨置/新置县：按今县级驻地取 Wikidata 坐标（CC0），离新郡里其他点太远的不要
        from fetch_han_wikidata import sparql
        q = 'SELECT ?name ?coord ?desc WHERE { VALUES ?l { %s } ?i rdfs:label ?l ; wdt:P625 ?coord . BIND(STR(?l) AS ?name) OPTIONAL { ?i schema:description ?desc FILTER(lang(?desc)="zh") } }'
        rows = sparql(q % ' '.join(f'"{e["modern"]}"@zh' for e in extra_seeds))
        for e in extra_seeds:
            hits = [r for r in rows if r['name']['value'] == e['modern']]
            hits = [r for r in hits if any(k in r.get('desc', {}).get('value', '') for k in ('市', '县', '區', '区'))] or hits
            pts = [tuple(float(x) for x in r['coord']['value'][6:-1].split()) for r in hits]
            pts = [p for p in pts if 95 < p[0] < 125 and 30 < p[1] < 45]
            if pts:
                e['lon'], e['lat'] = pts[0]
            else:
                problems.append(f'{e["jun"]}: 今址 {e["modern"]} 查不到坐标')
    out_c = []
    for r in coords:
        k = (norm(r['jun']), norm(r['county']))
        out_c.append({**r, 'jun': moved[k]} if k in moved else r)
    (HERE / 'data' / 'han-219-commanderies.json').write_text(json.dumps({
        'source': '《后汉书·郡国志》140 年郡国 + 建安年间新设郡（逐郡注出处，见 derive_219.py）', 'epoch': '建安二十四年（219）前后',
        'commanderies': units}, ensure_ascii=False, indent=1), encoding='utf-8')
    (HERE / 'data' / 'han-219-county-coords.json').write_text(json.dumps({
        'source': 'han-county-coords.json 按建安郡重新归属', 'counties': out_c, 'extra_seeds': extra_seeds}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{len(units)} commanderies ({len(SPLITS)} new); {len(moved)} counties moved; {len(extra_seeds)} extra seeds')
    for p in problems:
        print('  !', p)


if __name__ == '__main__':
    main()
