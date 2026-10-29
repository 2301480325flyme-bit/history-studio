"""Dispatch a task to Codex and keep a record of it (Claude 主控 · Codex 辅助, 2026-10-24).

Claude writes a goal-based brief, this script hands it to the Codex CLI, and everything about the run lands
in one task folder so it can be reviewed, resumed and audited later:

    00_管理/codex任务/<YYYYMMDD>-<name>/
        brief.md      the brief as sent
        meta.json     model, effort, write scope, session id, start/end, tokens, exit code
        events.jsonl  Codex's event stream
        report.md     Codex's final message (its 汇报)
        changes.txt   files changed during the run; anything outside the write scope is flagged

    python tools/codex_task.py start ep19-史料包 --brief brief.md --write 01_工作流/projects/s01e19-xx/research
    python tools/codex_task.py resume ep19-史料包 "第 3 条出处段落 ID 对不上，请用 studio.py sources 重查"
    python tools/codex_task.py status

Run `start` / `resume` in the background (they block until Codex finishes; long tasks take tens of minutes).
Only one task may write to a given directory at a time; `start` refuses when a running task overlaps.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
TASKS = os.path.join(ROOT, '00_管理', 'codex任务')
CODEX_JS = r'D:\Install room\codex-cli\node_modules\@openai\codex\bin\codex.js'
MODEL = 'gpt-6.1-terra'   # the user's choice for helper work since 2026-10-29 (fast); was gpt-6-luna

# Codex's Windows sandbox runs commands under a restricted account that may not execute the per-user Python
# (CreateProcessAsUserW: access denied, 2026-10-24), and research needs studio.py. So Codex runs unsandboxed;
# the write scope is enforced by the rules in the prompt and checked afterwards (changes.txt, git).
SANDBOX = ['--dangerously-bypass-approvals-and-sandbox']
PYTHON = sys.executable   # the sandboxed shell has no python on PATH; hand Codex the interpreter

RULES = """

---
（以下由派活脚本附加，所有 Claude 派给你的任务都适用）
- 你是 Claude 的助手：研究、整理、生图这些耗时的活由你做，大纲、旁白、分镜、引擎代码和验收归 Claude。
- 只在这些目录里新建或修改文件：{scope}。别处需要改，写进汇报里的「建议」，不要自己动手。
- 不改 01_工作流/history-studio/*.py、remotion-shuihong/src/、episode.yaml 的 beats；不渲染、不 git commit、不删除文件。
- Python 用 & '{python}'（沙箱里 PATH 没有 python）。读写文件、处理中文路径一律用 Python（open(..., encoding='utf-8')）；不要用 PowerShell 的 Get-Content / Set-Content / Out-File，
  Windows PowerShell 5.1 会把中文读成乱码（2026-10-24 试跑时因此统计出错）。读到乱码就停下重读，不要在乱码上继续推理。
- 密钥只从环境变量读取，不打印、不写入文件。
- 引用史料必须能在本地语料（python studio.py sources …）或维基文库原文里查到；查不到的写「未核」，不要凭记忆补原文。
- 最后一条消息就是汇报，按任务单「交付与验收」逐条写：做了什么、文件路径、依据、没做完的和原因、对规范的建议。
"""


def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def git_changes():
    out = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8').stdout
    files = {}
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if ' -> ' in path:
            path = path.split(' -> ')[1]
        full = os.path.join(ROOT, path)
        files[path] = os.path.getmtime(full) if os.path.exists(full) else None
    return files


def task_dir(name):
    hits = sorted(d for d in os.listdir(TASKS) if d.endswith('-' + name)) if os.path.isdir(TASKS) else []
    if not hits:
        raise SystemExit(f'no task named {name}')
    return os.path.join(TASKS, hits[-1])


def load(d):
    return json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))


def save(d, meta):
    json.dump(meta, open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def inside(path, scope):
    p = path.replace('\\', '/')
    return any(p == s or p.startswith(s.rstrip('/') + '/') for s in scope)


def run(d, meta, args, prompt):
    """Run Codex, stream its events to events.jsonl, then record session, tokens and changed files."""
    before = git_changes()
    cmd = ['node', CODEX_JS, 'exec', *args, '--json', '-o', os.path.join(d, 'report.md')]
    meta.update(status='running', updated=now())
    save(d, meta)
    with open(os.path.join(d, 'events.jsonl'), 'a', encoding='utf-8') as log:
        env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        p = subprocess.run(cmd, cwd=ROOT, input=prompt, stdout=log, stderr=subprocess.DEVNULL,
                           text=True, encoding='utf-8', env=env)
    tokens = 0
    for line in open(os.path.join(d, 'events.jsonl'), encoding='utf-8'):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        sid = ev.get('thread_id') or ev.get('session_id')
        if sid and not meta.get('session'):
            meta['session'] = sid
        usage = ev.get('usage') or {}
        # cached input is billed far cheaper; count what actually costs quota
        tokens += usage.get('input_tokens', 0) - usage.get('cached_input_tokens', 0) + usage.get('output_tokens', 0)
    after = git_changes()
    own = os.path.relpath(TASKS, ROOT).replace(os.sep, '/')
    changed = sorted(k for k, m in after.items() if (k not in before or before[k] != m) and not inside(k, [own]))
    # files outside the scope may also come from another agent working at the same time: review, don't assume
    outside = [c for c in changed if not inside(c, meta['write'])]
    with open(os.path.join(d, 'changes.txt'), 'w', encoding='utf-8') as f:
        for c in changed:
            f.write(('范围外 ' if c in outside else '       ') + c + '\n')
    meta.update(status='done' if p.returncode == 0 else 'failed', exit=p.returncode, updated=now(),
                tokens=meta.get('tokens', 0) + tokens, changed=len(changed), outside=outside)
    save(d, meta)
    print(f"{meta['status']}: {d}\n  report  {os.path.join(d, 'report.md')}\n  changed {len(changed)} files, "
          f"outside scope {len(outside)} (yours or another agent's: check), tokens {tokens} (uncached)")
    for c in outside:
        print('  范围外', c)


def start(a):
    scope = [w.replace('\\', '/').rstrip('/') for w in a.write]
    if os.path.isdir(TASKS):
        for t in os.listdir(TASKS):
            mp = os.path.join(TASKS, t, 'meta.json')
            if os.path.exists(mp):
                m = json.load(open(mp, encoding='utf-8'))
                if m.get('status') == 'running' and any(inside(s, m['write']) or inside(w, [s]) for s in scope for w in m['write']):
                    raise SystemExit(f'task {t} is still running in an overlapping directory; wait for it')
    d = os.path.join(TASKS, f'{datetime.date.today():%Y%m%d}-{a.name}')
    os.makedirs(d, exist_ok=True)
    brief = open(a.brief, encoding='utf-8').read()
    open(os.path.join(d, 'brief.md'), 'w', encoding='utf-8').write(brief)
    meta = {'name': a.name, 'model': a.model, 'effort': a.effort, 'write': scope,
            'started': now(), 'session': None}
    args = ['-m', a.model, '-c', f'model_reasoning_effort="{a.effort}"', *SANDBOX]
    run(d, meta, args, brief + RULES.format(scope='、'.join(scope), python=PYTHON))


def resume(a):
    d = task_dir(a.name)
    meta = load(d)
    if not meta.get('session'):
        raise SystemExit('no session id recorded for this task; start a new one')
    args = ['-m', meta['model'], '-c', f'model_reasoning_effort="{meta["effort"]}"', *SANDBOX]
    meta['rounds'] = meta.get('rounds', 1) + 1
    with open(os.path.join(d, 'brief.md'), 'a', encoding='utf-8') as f:
        f.write(f"\n\n## 第 {meta['rounds']} 轮（{now()}）\n{a.message}\n")
    run(d, meta, ['resume', meta['session'], *args], a.message)


def status(a):
    if not os.path.isdir(TASKS):
        return print('no tasks yet')
    for t in sorted(os.listdir(TASKS))[-a.n:]:
        mp = os.path.join(TASKS, t, 'meta.json')
        if os.path.exists(mp):
            m = json.load(open(mp, encoding='utf-8'))
            print(f"{t:40} {m.get('status', '?'):8} {m.get('updated', '')}  rounds {m.get('rounds', 1)}  "
                  f"tokens {m.get('tokens', 0)}  outside {len(m.get('outside', []))}")


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('start')
    s.add_argument('name')
    s.add_argument('--brief', required=True)
    s.add_argument('--write', nargs='+', required=True, help='directories (repo-relative) Codex may write to')
    s.add_argument('--effort', default='medium', choices=['low', 'medium', 'high'])
    s.add_argument('--model', default=MODEL)
    r = sub.add_parser('resume')
    r.add_argument('name')
    r.add_argument('message')
    st = sub.add_parser('status')
    st.add_argument('-n', type=int, default=15)
    a = ap.parse_args()
    {'start': start, 'resume': resume, 'status': status}[a.cmd](a)


if __name__ == '__main__':
    main()
