"""Write the readable narration script (series/三国到隋/第NN集-标题.md) from an episode.yaml.

usage: python history-studio/script_md.py projects/<id>/episode.yaml [more.yaml …]

Chapters come from `phase:`, character lines are marked 【人物】「…」 with their style. An older hand-written
file of the same episode number is kept once as …-v1.md before being replaced.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding='utf-8')
WF = Path(__file__).resolve().parents[1]
SERIES = WF / 'series' / '三国到隋'
CN = '一二三四五六七八九十'


def main(paths: list[str]) -> None:
    for p in paths:
        y = yaml.safe_load(Path(p).read_text(encoding='utf-8'))
        m = re.search(r'第\s*(\d+)\s*集', str(y.get('series', '')))
        num = int(m.group(1)) if m else 0
        title = y.get('title', y['id'])
        out = SERIES / f'第{num:02d}集-{title}.md'
        for old in SERIES.glob(f'第{num:02d}集-*.md'):
            if old != out and not old.stem.endswith('-v1'):
                v1 = old.with_name(old.stem + '-v1.md')
                if not v1.exists():
                    shutil.move(old, v1)
        if out.exists() and not out.with_name(out.stem + '-v1.md').exists() and '慢慢讲故事' not in out.read_text(encoding='utf-8'):
            shutil.copy2(out, out.with_name(out.stem + '-v1.md'))
        chars = sum(len(re.sub(r'[\W_]', '', b['say'])) for b in y['beats'])
        pub = y.get('publish') or {}
        lines = [f'# 第{num}集｜{title}', '',
                 f'- 合集：{y.get("series", "")}', f'- 年份：{y.get("year", "")}',
                 f'- 字数：约 {chars} 字（含人物台词），预计约 {chars / 4.3 / 60:.1f} 分钟',
                 *(f'- 主问题：{pub["hook"]}' for _ in [0] if pub.get('hook')),
                 *(f'- 说明：{n}' for n in y.get('notes') or []), '',
                 '> 由 episode.yaml 自动生成（script_md.py）。慢慢讲故事，关键原话由人物"亲口说"（`speaker`）。改台词请改 episode.yaml。', '']
        n = ch = 0
        for b in y['beats']:
            if b.get('phase'):
                lines += ['', f'## 第{CN[ch] if ch < len(CN) else ch + 1}章　{b["phase"]}', '']
                ch += 1
            n += 1
            if b.get('speaker'):
                lines.append(f'{n}. **【{b["speaker"]}】「{b["say"]}」**（{b.get("style", "")}）')
            else:
                lines.append(f'{n}. {b["say"]}')
        out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(out.name, n, 'lines', chars, '字')


if __name__ == '__main__':
    main(sys.argv[1:])
