"""三国数据包：关键地点批量入库（Wikidata CC0 坐标）。

Each place lists Wikidata labels to try (ancient site / landmark first, then the
modern seat) and a rough expected position used only to reject same-name places
elsewhere. Coordinates written to data/gazetteer.json always come from the
chosen Wikidata item; precision text says what the point stands for.

    python build_sanguo_places.py          # adds new places, reports unresolved ones
"""

import json
import math
from datetime import date
from pathlib import Path

from fetch_han_wikidata import sparql
from studio import GAZETTEER, Registry, read_json, write_json

# id, 名, 别名, tier, 年代, [查询标签…], 预期位置(lon, lat), 精度说明, 用途
P = [
    ('guangzong', '广宗', [], 'city', '-200-600', ['广宗县'], (115.14, 37.07), '今广宗县驻地近似', '黄巾张角据点'),
    ('changshe', '长社', ['长葛'], 'city', '-200-600', ['长社', '长葛市'], (113.77, 34.22), '今长葛市一带近似', '皇甫嵩破黄巾'),
    ('xiapi', '下邳', [], 'city', '-200-600', ['下邳故城', '下邳', '邳州市'], (117.95, 34.0), '下邳故城或今邳州近似', '吕布败亡'),
    ('xiaopei', '小沛', ['沛', '沛县'], 'city', '-200-600', ['沛县'], (116.93, 34.73), '今沛县驻地近似', '刘备屯驻'),
    ('shouchun', '寿春', ['寿县'], 'city', '-200-600', ['寿县', '寿春'], (116.78, 32.58), '今寿县驻地近似', '袁术称帝、淮南三叛'),
    ('xiangyang', '襄阳', [], 'city', '-200-1911', ['襄阳古城', '襄阳市'], (112.14, 32.04), '襄阳古城或今襄阳近似', '刘表治所、樊城之战'),
    ('fancheng', '樊城', [], 'city', '-200-1911', ['樊城区'], (112.14, 32.06), '今樊城区近似', '关羽围樊'),
    ('jiangling', '江陵', [], 'city', '-200-1911', ['荆州古城', '江陵', '荆州市'], (112.19, 30.35), '荆州古城（江陵）近似', '荆州重镇'),
    ('chengdu_city', '成都', ['益州'], 'capital', '-300-1911', ['成都市'], (104.07, 30.66), '今成都市驻地近似', '蜀汉都城'),
    ('nanzheng', '南郑', ['汉中'], 'city', '-300-1911', ['汉中市', '南郑区'], (107.03, 33.07), '今汉中市近似', '张鲁据点、汉中之战'),
    ('wu_city', '吴', ['吴县', '苏州'], 'city', '-500-1911', ['苏州市'], (120.62, 31.3), '今苏州市近似', '孙氏江东根基'),
    ('chaisang', '柴桑', ['九江'], 'city', '-200-600', ['柴桑区', '九江市'], (115.99, 29.7), '今九江柴桑一带近似', '孙权驻军、赤壁前夕'),
    ('wuchang_e', '武昌', ['鄂', '鄂城'], 'capital', '221-600', ['鄂州市'], (114.89, 30.39), '今鄂州市近似（孙吴武昌）', '孙权一度定都'),
    ('xiakou', '夏口', ['沙羡'], 'city', '200-600', ['武汉市', '武昌区'], (114.3, 30.55), '今武汉一带近似', '江夏、赤壁前后'),
    ('chibi_site', '赤壁', [], 'pass', '208-208', ['赤壁古战场', '赤壁市'], (113.9, 29.72), '赤壁之战战场示意（今赤壁市一带，具体地点有争议）', '赤壁之战'),
    ('changban', '长坂', ['当阳'], 'pass', '208-208', ['长坂坡', '当阳市'], (111.79, 30.82), '今当阳一带示意', '长坂之战'),
    ('maicheng', '麦城', [], 'city', '219-219', ['麦城', '当阳市'], (111.85, 30.7), '今当阳东南一带示意', '关羽败走'),
    ('yiling', '夷陵', [], 'city', '-200-600', ['夷陵区', '宜昌市'], (111.29, 30.7), '今宜昌夷陵一带近似', '夷陵之战'),
    ('xiaoting', '猇亭', [], 'pass', '222-222', ['猇亭区'], (111.43, 30.53), '今宜昌猇亭区近似', '陆逊火烧连营'),
    ('baidicheng', '白帝城', ['永安', '鱼复'], 'stronghold', '-200-1911', ['白帝城', '奉节县'], (109.57, 31.04), '白帝城遗址或今奉节近似', '刘备托孤'),
    ('hefei', '合肥', [], 'stronghold', '-200-1911', ['合肥市'], (117.28, 31.86), '今合肥市近似（汉魏合肥城在其北）', '合肥之战'),
    ('ruxu', '濡须', ['濡须口'], 'pass', '212-253', ['濡须口', '无为市'], (117.9, 31.35), '濡须口一带示意', '濡须之战'),
    ('baima', '白马', [], 'city', '-200-600', ['滑县'], (114.52, 35.58), '今滑县一带近似', '白马之围、斩颜良'),
    ('yanjin', '延津', [], 'pass', '200-200', ['延津县'], (114.2, 35.14), '今延津县近似（延津渡在其北）', '诛文丑'),
    ('guandu_site', '官渡', [], 'pass', '200-200', ['官渡古战场', '中牟县'], (114.05, 34.8), '官渡古战场示意（今中牟东北）', '官渡之战'),
    ('liucheng', '柳城', ['白狼山'], 'city', '-200-600', ['朝阳市'], (120.45, 41.57), '今朝阳市一带近似', '曹操征乌桓'),
    ('tongguan', '潼关', [], 'pass', '200-1911', ['潼关县', '潼关'], (110.25, 34.55), '今潼关县近似', '潼关之战'),
    ('dingjunshan', '定军山', [], 'pass', '219-219', ['定军山', '勉县'], (106.67, 33.13), '定军山（今勉县南）', '黄忠斩夏侯渊'),
    ('yangpingguan', '阳平关', [], 'pass', '200-600', ['阳平关', '勉县'], (106.45, 33.17), '阳平关一带示意（今勉县西）', '汉中门户'),
    ('jieting', '街亭', [], 'pass', '228-228', ['街亭', '秦安县'], (105.85, 34.95), '街亭示意（今秦安东北，有争议）', '马谡失街亭'),
    ('qishan', '祁山', [], 'stronghold', '228-234', ['祁山', '礼县'], (105.3, 34.1), '祁山堡一带（今礼县东）示意', '诸葛亮北伐'),
    ('chencang', '陈仓', [], 'stronghold', '-200-600', ['陈仓区', '宝鸡市'], (107.2, 34.37), '今宝鸡陈仓一带近似', '郝昭守陈仓'),
    ('wuzhangyuan', '五丈原', [], 'pass', '234-234', ['五丈原', '岐山县'], (107.63, 34.26), '五丈原（今岐山南）', '诸葛亮病逝'),
    ('jiange', '剑阁', ['剑门关'], 'pass', '200-1911', ['剑门关', '剑阁县'], (105.53, 32.2), '剑门关一带', '姜维拒钟会'),
    ('mianzhu_old', '绵竹', [], 'city', '-200-600', ['绵竹市'], (104.2, 31.34), '今绵竹一带近似（汉绵竹在其南）', '诸葛瞻战死'),
    ('yinping', '阴平', [], 'pass', '-200-600', ['文县'], (104.68, 32.94), '今文县一带近似', '邓艾偷渡阴平'),
    ('xiangping_c', '襄平', ['辽东'], 'city', '-200-600', ['辽阳市'], (123.17, 41.27), '今辽阳市近似', '公孙氏据辽东、司马懿平辽'),
    ('wanxian', '宛', ['南阳'], 'city', '-300-1911', ['宛城区', '南阳市'], (112.53, 33.0), '今南阳宛城区近似', '张绣、曹操'),
    ('pengcheng', '彭城', ['徐州'], 'city', '-300-1911', ['徐州市'], (117.18, 34.26), '今徐州市近似', '徐州治所'),
    ('changsha_c', '长沙', ['临湘'], 'city', '-300-1911', ['长沙市'], (112.94, 28.23), '今长沙市近似', '孙坚、荆南'),
    ('weixian_nz', '味县', ['南中'], 'city', '-100-600', ['曲靖市', '麒麟区'], (103.8, 25.5), '今曲靖一带近似', '诸葛亮南征'),
    ('dingtao', '定陶', [], 'city', '-300-1911', ['定陶区'], (115.57, 35.07), '今定陶区近似', '兖州之战'),
    ('puyang_c', '濮阳', [], 'city', '-300-1911', ['濮阳县'], (115.03, 35.7), '今濮阳县近似', '曹操吕布濮阳之战'),
    ('nanpi', '南皮', [], 'city', '-200-1911', ['南皮县'], (116.7, 38.04), '今南皮县近似', '袁谭败亡'),
    ('gaoping', '高平陵', [], 'pass', '249-249', ['洛阳市'], (112.45, 34.62), '洛阳南郊示意（高平陵之变）', '司马懿政变'),
]


def main():
    reg = Registry()
    labels = sorted({l for p in P for l in p[5]})
    vals = ' '.join(f'"{l}"@{t}' for l in labels for t in ('zh', 'zh-hans', 'zh-cn', 'zh-hant'))
    q = '''SELECT ?l ?i ?coord ?desc WHERE { VALUES ?lab { %s } ?i rdfs:label ?lab ; wdt:P625 ?coord . BIND(STR(?lab) AS ?l)
      OPTIONAL { ?i schema:description ?desc FILTER(lang(?desc) IN ("zh","zh-hans","zh-cn")) } }''' % vals
    rows = sparql(q)
    cands: dict[str, list] = {}
    for r in rows:
        lon, lat = (float(x) for x in r['coord']['value'][6:-1].split())
        cands.setdefault(r['l']['value'], []).append({'qid': r['i']['value'].rsplit('/', 1)[1], 'lon': lon, 'lat': lat, 'desc': r.get('desc', {}).get('value', '')})
    data = read_json(GAZETTEER) if GAZETTEER.exists() else {'places': []}
    have = {p['id'] for p in data['places']}
    added, skipped, unresolved = [], [], []
    for pid, name, aliases, tier, years, labs, (hx, hy), prec, use in P:
        if pid in have or reg.place(pid):
            skipped.append(name)
            continue
        pick = None
        for lab in labs:   # earlier labels (ancient site / landmark) win if close enough
            near = [c for c in cands.get(lab, []) if math.hypot(c['lon'] - hx, c['lat'] - hy) <= 1.0]
            if near:
                pick = min(near, key=lambda c: math.hypot(c['lon'] - hx, c['lat'] - hy))
                pick['label'] = lab
                break
        if not pick:
            unresolved.append(name)
            continue
        lo, hi = (int(x) if x else None for x in years.rsplit('-', 1)) if years.count('-') == 1 or not years.startswith('-') else (int('-' + years[1:].split('-', 1)[0]), int(years[1:].split('-', 1)[1]))
        data['places'].append({
            'id': pid, 'aliases': [name, *aliases], 'coordinates': [round(pick['lon'], 5), round(pick['lat'], 5)],
            'coordinatePrecision': f"{prec}（坐标取 Wikidata「{pick['label']}」）", 'coordinateSource': f"https://www.wikidata.org/wiki/{pick['qid']}",
            'coordinateStatus': 'approximate', 'names': [{'text': name, 'from': lo, 'to': hi}], 'tiers': [{'from': lo, 'to': hi, 'tier': tier}],
            'note': f'三国数据包：{use}', 'reviewStatus': 'agent', 'added': date.today().isoformat(), 'pack': 'sanguo'})
        added.append(f"{name}←{pick['label']}")
    write_json(GAZETTEER, data)
    print(f'added {len(added)}: {"、".join(added)}')
    print(f'already present {len(skipped)}: {"、".join(skipped)}')
    print(f'unresolved {len(unresolved)}: {"、".join(unresolved)}')


if __name__ == '__main__':
    main()
