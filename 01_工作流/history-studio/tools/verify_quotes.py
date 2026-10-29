"""Check every quoted source passage against the local corpus, word for word (原文自动核对, 2026-10-24).

Codex's 史料包 and 审读 files cite the corpus as {quote: 原文, para: 三国志-p01189}. This finds every such pair
anywhere in a YAML/JSON file and checks that the quote really is in that paragraph. Punctuation, spaces and
traditional/simplified differences are ignored; "……" splits a quote into pieces that must appear in order.
A quote without a para (or with a wrong one) is searched for in the whole corpus, so a misnumbered citation
is reported with the right id instead of being called a fabrication.

    python tools/verify_quotes.py ../projects/s01e19-xx/research/史料包.yaml
    python tools/verify_quotes.py 审读.yaml --json

Exit code 1 when any quote can't be found anywhere: that file goes back to Codex.
"""
import argparse
import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, '..', '..', 'corpus')
PUNCT = re.compile(r'[\s，。、；：？！“”‘’「」『』《》〈〉（）()\[\]【】,.;:?!"\'·—\-…]+')

try:
    import opencc
    _t2s = opencc.OpenCC('t2s').convert
except ImportError:      # the corpus is simplified already; only traditional quotes would be missed
    _t2s = lambda s: s


def norm(s):
    return PUNCT.sub('', _t2s(str(s)))


def pieces(quote):
    return [norm(p) for p in re.split(r'…+|\.{3,}|⋯+', str(quote)) if norm(p)]


def in_order(parts, text):
    i = 0
    for p in parts:
        j = text.find(p, i)
        if j < 0:
            return False
        i = j + len(p)
    return True


def load_corpus():
    paras = {}
    for f in sorted(os.listdir(CORPUS)):
        if f.endswith('.jsonl'):
            with open(os.path.join(CORPUS, f), encoding='utf-8') as fh:
                for line in fh:
                    r = json.loads(line)
                    paras[r['id']] = norm(r['text'])
    return paras


def walk(node, path=''):
    """Yield (path, dict) for every mapping that carries a quote."""
    if isinstance(node, dict):
        if 'quote' in node and isinstance(node['quote'], (str, int)):
            yield path, node
        for k, v in node.items():
            yield from walk(v, f'{path}.{k}' if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f'{path}[{i}]')


def check(item, paras):
    parts = pieces(item['quote'])
    if not parts:
        return 'empty', None
    para = item.get('para')
    if para and para in paras and in_order(parts, paras[para]):
        return 'ok', para
    hits = [pid for pid, t in paras.items() if in_order(parts, t)]
    if hits:
        return ('wrong-para' if para else 'no-para'), hits[:3]
    return ('para-missing' if para and para not in paras else 'not-found'), None


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    text = open(a.file, encoding='utf-8').read()
    data = json.loads(text) if a.file.endswith('.json') else yaml.safe_load(text)
    paras = load_corpus()
    rows = []
    for path, item in walk(data):
        status, ref = check(item, paras)
        rows.append({'at': path, 'quote': str(item['quote'])[:40], 'para': item.get('para'), 'status': status, 'found': ref})
    bad = [r for r in rows if r['status'] in ('not-found', 'para-missing')]
    if a.json:
        print(json.dumps({'total': len(rows), 'bad': len(bad), 'rows': rows}, ensure_ascii=False, indent=1))
    else:
        label = {'ok': '对', 'wrong-para': '段落号错', 'no-para': '没写段落', 'not-found': '查无此文',
                 'para-missing': '段落不存在', 'empty': '空'}
        for r in rows:
            if r['status'] != 'ok':
                print(f"{label[r['status']]:6} {r['at']}  「{r['quote']}」 {r['para'] or ''} → {r['found'] or ''}")
        ok = sum(r['status'] == 'ok' for r in rows)
        print(f'{len(rows)} 条原文：{ok} 条一字不差，{len(rows) - ok - len(bad)} 条出处号要改，{len(bad)} 条在本地语料里查不到')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
