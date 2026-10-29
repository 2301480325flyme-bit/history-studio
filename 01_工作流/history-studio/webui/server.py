"""History Studio web UI — local server (127.0.0.1 only).

    python webui/server.py            # then open http://127.0.0.1:8770

Wraps studio.py: list/import/edit episode scripts, form-based config edits
(comment-preserving YAML round trip), check, build, stills, render and a live
Remotion Studio preview. Long actions run as background jobs whose logs and
progress the page polls. Files are served only from the project folders and
the studio build output.
"""

from __future__ import annotations

import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ruamel.yaml import YAML

HERE = Path(__file__).resolve().parent
STUDIO = HERE.parent
sys.path.insert(0, str(STUDIO))
import studio  # noqa: E402

ROOT = studio.ROOT
PROJECTS = studio.PROJECTS
OUT_ROOT = studio.OUT_ROOT
STATIC = HERE / 'static'
PORT = int(os.environ.get('HISTORY_STUDIO_PORT') or os.environ.get('PORT') or 8770)   # PORT: assigned by the preview pane
PREVIEW_PORT = 3100

ryaml = YAML()
ryaml.preserve_quotes = True
ryaml.width = 4096
ryaml.indent(mapping=2, sequence=4, offset=2)

JOBS: dict[str, dict] = {}
RENDER_LOCK = threading.Lock()
PREVIEW = {'proc': None, 'episode': None}


# ---------------------------------------------------------------- helpers

def episode_dirs() -> list[Path]:
    """Series episodes first in episode order (s01e01, s01e02 …), then other projects newest first, engine demos (zz-*) last."""
    def key(p: Path):
        m = re.match(r's(\d+)e(\d+)', p.name)
        if m:
            return (0, int(m.group(1)), int(m.group(2)), 0.0)
        return (2 if p.name.startswith('zz-') else 1, 0, 0, -p.stat().st_mtime)
    return sorted((p.parent for p in PROJECTS.glob('*/episode.yaml')), key=key)


def ep_dir(key: str) -> Path:
    d = (PROJECTS / key).resolve()
    if d.parent != PROJECTS.resolve() or not (d / 'episode.yaml').exists():
        raise FileNotFoundError(key)
    return d


def load_plain(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}


def builds_of(script_id: str) -> list[dict]:
    out = []
    for b in sorted((OUT_ROOT / script_id).glob('*/build.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        d = b.parent
        info = json.loads(b.read_text(encoding='utf-8'))
        mp4 = next(iter(d.glob('*.mp4')), None)
        mc = d / 'media-check.json'
        out.append({
            'build': d.name, 'created': info.get('created'), 'duration': info.get('duration'), 'timing': (info.get('timing') or {}).get('mode'),
            'audio': bool(info.get('audio')), 'warnings': info.get('warnings', []),
            'files': {k: rel(d / f) for k, f in [('review', 'review.md'), ('contact', 'contact-sheet.jpg'), ('stills', 'stills-sheet.jpg'), ('publish', '发布/发布信息.json')] if (d / f).exists()},
            'mp4': rel(mp4) if mp4 else None,
            'media': json.loads(mc.read_text(encoding='utf-8')) if mc.exists() else None,
            'stills': [rel(p) for p in sorted((d / 'stills').glob('f*.png'))],
        })
    return out


def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def safe_file(relpath: str) -> Path:
    p = (ROOT / unquote(relpath)).resolve()
    allowed = [OUT_ROOT.resolve(), PROJECTS.resolve(), (ROOT / '03_素材' / '音效').resolve(), (STUDIO / 'data').resolve(), (STUDIO / 'assets').resolve(), (STUDIO / 'gallery').resolve()]
    if not any(str(p).startswith(str(a)) for a in allowed) or not p.is_file():
        raise PermissionError(relpath)
    return p


def styled(value, like=None):
    """Plain JSON value → ruamel node, keeping the old node's flow/block style.

    New small mappings/lists of scalars default to one-line flow style, which is
    how hand-written scripts write places and polities."""
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    if isinstance(value, dict):
        node = CommentedMap((k, styled(v, like.get(k) if hasattr(like, 'get') else None)) for k, v in value.items())
    elif isinstance(value, list):
        node = CommentedSeq(styled(v) for v in value)
    else:
        return value
    flow = None
    if like is not None and hasattr(like, 'fa'):
        flow = like.fa.flow_style()
    if flow is None:
        flow = len(value) <= 8 and all(not isinstance(v, (dict, list)) for v in (value.values() if isinstance(value, dict) else value))
    if flow:
        node.fa.set_flow_style()
    else:
        node.fa.set_block_style()
    return node


def set_path(doc, path: list, value):
    """Set doc[path] creating maps as needed; value None deletes the key."""
    from ruamel.yaml.comments import CommentedMap
    cur = doc
    for k in path[:-1]:
        if isinstance(cur, list):
            cur = cur[int(k)]
            continue
        if k not in cur or cur[k] is None:
            cur[k] = CommentedMap()
        cur = cur[k]
    last = path[-1]
    if isinstance(cur, list):
        cur[int(last)] = styled(value, cur[int(last)])
    elif value is None:
        cur.pop(last, None)
    else:
        cur[last] = styled(value, cur.get(last))


def backup(path: Path):
    hist = path.parent / '.history'
    hist.mkdir(exist_ok=True)
    shutil.copy2(path, hist / f"episode-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml")


# ---------------------------------------------------------------- jobs

def start_job(key: str, kind: str, args: list[str], exclusive=False) -> str:
    jid = uuid.uuid4().hex[:10]
    job = {'id': jid, 'episode': key, 'kind': kind, 'status': 'queued', 'log': [], 'progress': None, 'started': time.time(), 'ended': None, 'cmd': args}
    JOBS[jid] = job

    def run():
        lock = RENDER_LOCK if exclusive else None
        if lock:
            job['log'].append('等待其他渲染任务结束…')
            lock.acquire()
        try:
            if job.get('cancel'):
                job['status'] = 'cancelled'
                return
            job['status'] = 'running'
            env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1', 'FORCE_COLOR': '0'}
            # args are studio.py sub-commands, or another studio script (publish.py …) as the first item
            cmd = [sys.executable, *args] if args and str(args[0]).endswith('.py') else [sys.executable, str(STUDIO / 'studio.py'), *args]
            proc = subprocess.Popen(cmd, cwd=STUDIO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    env=env, text=True, encoding='utf-8', errors='replace', bufsize=1)
            job['pid'] = proc.pid
            if job.get('cancel'):
                kill_tree(proc.pid)
            for line in proc.stdout:
                line = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
                m = re.search(r'Rendered (\d+)/(\d+)(?:, time remaining: ([^,]+))?', line)
                if m:
                    job['done'], job['total'] = int(m.group(1)), int(m.group(2))
                    job['note'] = f'剩余约 {m.group(3).strip()}' if m.group(3) else ''
                elif line.startswith('Encoded'):
                    job['note'] = '编码中 ' + line.split()[-1]
                elif (m2 := re.search(r'TTS beat (\d+)', line)):
                    job['note'] = f'配音第 {int(m2.group(1)) + 1} 句'
                if m:
                    job['progress'] = int(m.group(1)) / max(1, int(m.group(2)))
                    if job['log'] and job['log'][-1].startswith('Rendered'):
                        job['log'][-1] = line
                        continue
                if re.match(r'(Bundling|Copying public dir|Encoded|Stitched)', line):
                    continue
                if line:
                    job['log'].append(line)
                    job['log'] = job['log'][-400:]
            code = proc.wait()
            job['status'] = 'cancelled' if job.get('cancel') else 'done' if code == 0 else 'failed'
            job['code'] = code
            if job['status'] == 'done' and args[:1] == ['render']:
                job['folder'] = latest_mp4(key)
        except Exception as e:  # report, never crash the server
            job['status'] = 'failed'
            job['log'].append(f'✖ {e}')
        finally:
            job['ended'] = time.time()
            if lock:
                lock.release()

    threading.Thread(target=run, daemon=True).start()
    return jid


def kill_tree(pid: int) -> bool:
    if sys.platform == 'win32':
        r = subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, text=True, encoding='gbk', errors='replace')
        return r.returncode == 0
    try:
        os.kill(pid, 15)
        return True
    except OSError:
        return False


def cancel_job(jid: str) -> dict:
    j = JOBS.get(jid)
    if j:
        if j['status'] not in ('queued', 'running'):
            return {'ok': True, 'note': '任务已结束'}
        j['cancel'] = True
        j['log'].append('✖ 已手动停止')
        if j['status'] == 'queued':
            j['status'] = 'cancelled'
        elif j.get('pid'):
            kill_tree(j['pid'])
        return {'ok': True}
    if jid.startswith('ext-'):
        f = OUT_ROOT / jid[4:] / 'progress.json'
        try:
            pr = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
        except (OSError, ValueError):
            pr = {}
        if not pr.get('pid'):
            return {'error': '这个后台任务没有记录进程号（旧版本启动的），请在任务管理器里结束 python.exe'}
        if not kill_tree(int(pr['pid'])):
            return {'error': '停止失败：可能是以管理员身份启动的任务，请在任务管理器里结束'}
        pr.update(status='cancelled', stage='已停止', updated=time.time())
        f.write_text(json.dumps(pr, ensure_ascii=False, indent=1), encoding='utf-8')
        return {'ok': True}
    return {'error': '找不到任务'}


def latest_mp4(key: str) -> str | None:
    try:
        sid = load_plain(ep_dir(key) / 'episode.yaml').get('id', key)
    except Exception:
        sid = key
    mp4s = sorted((OUT_ROOT / str(sid)).glob('*/*.mp4'), key=lambda x: x.stat().st_mtime, reverse=True)
    return str(mp4s[0]) if mp4s else None


def open_in_explorer(target: str) -> dict:
    p = Path(target) if Path(target).is_absolute() else ROOT / unquote(target)
    p = p.resolve()
    if not any(str(p).startswith(str(a.resolve())) for a in (OUT_ROOT, PROJECTS)) or not p.exists():
        raise PermissionError(target)
    if sys.platform == 'win32':
        if p.is_file():
            subprocess.Popen(f'explorer /select,"{p}"')
        else:
            os.startfile(str(p))
    else:
        subprocess.Popen(['open', '-R', str(p)] if p.is_file() else ['open', str(p)])
    return {'ok': True}


def archive_episode(key: str) -> dict:
    """“删除”项目 = 移到 projects/_archive/（手动移回即可恢复）；构建和成片都不动。"""
    d = ep_dir(key)
    if any(j['episode'] == key and j['status'] in ('queued', 'running') for j in JOBS.values()):
        return {'error': '这个项目还有任务在运行，先停止任务再删除'}
    if PREVIEW.get('episode') == key:
        stop_preview()
    arch = PROJECTS / '_archive'
    arch.mkdir(exist_ok=True)
    dst = arch / f"{key}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.move(str(d), str(dst))
    return {'ok': True, 'archived': rel(dst)}


def job_summary(j: dict) -> dict:
    return {k: v for k, v in j.items() if k not in ('log', 'cmd')}


def start_preview(key: str) -> dict:
    stop_preview()
    d = ep_dir(key)
    try:
        out = studio.latest_build(d / 'episode.yaml')
    except studio.ScriptError as e:
        return {'error': str(e)}
    npx = 'npx.cmd' if sys.platform == 'win32' else 'npx'
    proc = subprocess.Popen([npx, 'remotion', 'studio', 'src/studio/index.tsx', f'--public-dir={out / "public"}', f'--port={PREVIEW_PORT}', '--no-open'],
                            cwd=studio.REMOTION, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PREVIEW.update(proc=proc, episode=key, build=out.name)
    return {'url': f'http://localhost:{PREVIEW_PORT}', 'build': out.name}


def port_listeners(port: int) -> set[int]:
    """PIDs listening on a local TCP port."""
    if sys.platform == 'win32':
        out = subprocess.run(['netstat', '-ano', '-p', 'TCP'], capture_output=True, text=True, errors='replace').stdout
        return {int(f[4]) for f in (line.split() for line in out.splitlines())
                if len(f) == 5 and f[3] == 'LISTENING' and f[1].rsplit(':', 1)[-1] == str(port)}
    out = subprocess.run(['lsof', '-ti', f'tcp:{port}', '-sTCP:LISTEN'], capture_output=True, text=True).stdout
    return {int(x) for x in out.split()}


def kill_tree(pid: int):
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def stop_preview():
    p = PREVIEW.get('proc')
    if p and p.poll() is None:
        kill_tree(p.pid)
    # npx → cmd → node: the Remotion node process can outlive its launcher (or a
    # restarted server), keep the port, and every new preview then silently fails
    # to bind and the page keeps showing the old episode. PREVIEW_PORT is ours alone.
    for _ in range(20):
        pids = port_listeners(PREVIEW_PORT)
        if not pids:
            break
        for pid in pids:
            kill_tree(pid)
        time.sleep(0.25)
    PREVIEW.update(proc=None, episode=None)


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = 'HistoryStudio/1.0'

    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> dict:
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n).decode('utf-8')) if n else {}

    def send_file(self, p: Path):
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
        if p.suffix == '.md':
            ctype = 'text/markdown; charset=utf-8'
        rng = self.headers.get('Range')
        start, end = 0, size - 1
        if rng and (m := re.match(r'bytes=(\d*)-(\d*)', rng)):
            start = int(m.group(1) or 0)
            end = int(m.group(2)) if m.group(2) else size - 1
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        else:
            self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        with p.open('rb') as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionResetError, BrokenPipeError):
                    return
                left -= len(chunk)

    def route(self, method: str):
        u = urlparse(self.path)
        parts = [unquote(x) for x in u.path.strip('/').split('/') if x]
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if method == 'GET' and (not parts or parts[0] in ('index.html',)):
                return self.send_file(STATIC / 'index.html')
            if method == 'GET' and parts[0] == 'static':
                p = (STATIC / '/'.join(parts[1:])).resolve()
                if not str(p).startswith(str(STATIC.resolve())) or not p.is_file():
                    return self.send_json({'error': 'not found'}, 404)
                return self.send_file(p)
            if method == 'GET' and parts[0] == 'files':
                return self.send_file(safe_file('/'.join(parts[1:])))
            if parts[0] != 'api':
                return self.send_json({'error': 'not found'}, 404)
            return self.api(method, parts[1:], q)
        except FileNotFoundError as e:
            return self.send_json({'error': f'找不到：{e}'}, 404)
        except PermissionError as e:
            return self.send_json({'error': f'不允许访问：{e}'}, 403)
        except Exception as e:
            return self.send_json({'error': f'{type(e).__name__}: {e}'}, 500)

    def api(self, method, p, q):
        if p == ['episodes'] and method == 'GET':
            out = []
            for d in episode_dirs():
                try:
                    s = load_plain(d / 'episode.yaml')
                except Exception as e:
                    s = {'title': f'（脚本解析失败：{e}）'}
                sid = s.get('id', d.name)
                group = 'episode' if re.match(r's\d+e\d+', d.name) else 'demo' if d.name.startswith('zz-') else 'archive'
                out.append({'key': d.name, 'id': sid, 'group': group, 'title': s.get('title', ''), 'series': s.get('series', ''), 'year': s.get('year'),
                            'beats': len(s.get('beats') or []), 'territory': bool(s.get('territory')),
                            'updated': datetime.fromtimestamp((d / 'episode.yaml').stat().st_mtime).strftime('%m-%d %H:%M'),
                            'builds': len(list((OUT_ROOT / str(sid)).glob('*/build.json')))})
            return self.send_json(out)
        if p == ['episodes'] and method == 'POST':
            b = self.body()
            text = b.get('yaml')
            if text:
                import yaml
                data = yaml.safe_load(text)
                if not isinstance(data, dict) or not data.get('id'):
                    return self.send_json({'error': '导入的脚本必须是 YAML，且包含 id'}, 400)
                key = re.sub(r'[^\w\-]', '-', str(b.get('key') or data['id']))
            else:
                key = re.sub(r'[^\w\-]', '-', b.get('key', '').strip())
                if not key:
                    return self.send_json({'error': '请填写剧集 ID（英文/数字/短横线）'}, 400)
                text = studio.TEMPLATE.read_text(encoding='utf-8').replace('__ID__', key)
            d = PROJECTS / key
            if (d / 'episode.yaml').exists():
                return self.send_json({'error': f'{key} 已存在'}, 409)
            d.mkdir(parents=True, exist_ok=True)
            (d / 'episode.yaml').write_text(text, encoding='utf-8')
            return self.send_json({'key': key})
        if len(p) >= 2 and p[0] == 'episodes':
            key = p[1]
            d = ep_dir(key)
            path = d / 'episode.yaml'
            sub = p[2:]
            if sub == ['script'] and method == 'GET':
                text = path.read_text(encoding='utf-8')
                try:
                    data = load_plain(path)
                except Exception as e:
                    data, err = None, str(e)
                else:
                    err = None
                return self.send_json({'text': text, 'data': data, 'parse_error': err, 'builds': builds_of((data or {}).get('id', key))})
            if sub == ['script'] and method == 'PUT':
                text = self.body().get('text', '')
                import yaml
                try:
                    yaml.safe_load(text)
                except Exception as e:
                    return self.send_json({'error': f'YAML 格式错误：{e}'}, 400)
                backup(path)
                path.write_text(text, encoding='utf-8')
                return self.send_json({'ok': True})
            if sub == ['config'] and method == 'PATCH':
                ops = self.body().get('set', [])
                doc = ryaml.load(path.read_text(encoding='utf-8'))
                for op in ops:
                    set_path(doc, op['path'], op.get('value'))
                buf = io.StringIO()
                ryaml.dump(doc, buf)
                backup(path)
                path.write_text(buf.getvalue(), encoding='utf-8')
                return self.send_json({'ok': True})
            if sub == ['check'] and method == 'POST':
                r = subprocess.run([sys.executable, str(STUDIO / 'studio.py'), 'check', str(path), '--json'], cwd=STUDIO, capture_output=True, text=True,
                                   encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                m = re.search(r'\{.*\}\s*$', r.stdout, re.S)
                return self.send_json(json.loads(m.group(0)) if m else {'ok': False, 'errors': [r.stdout[-2000:] + r.stderr[-2000:]], 'warnings': []})
            if sub == ['jobs'] and method == 'POST':
                b = self.body()
                act = b.get('action')
                silent = b.get('voice') == 'placeholder' or act == 'quick'
                build_id = b.get('build') or datetime.now().strftime(('P' if silent else 'S') + '%m%d-%H%M%S')
                if act == 'build':
                    args = ['build', str(path), '--build', build_id] + (['--voice', b['voice']] if b.get('voice') else [])
                    return self.send_json({'job': start_job(key, '构建 ' + build_id, args)})
                if act == 'quick':  # silent layout build + stills for every beat
                    jid = start_job(key, '排版预览 ' + build_id, ['build', str(path), '--build', build_id, '--voice', 'placeholder'])
                    return self.send_json({'job': jid, 'then': 'still'})
                if act == 'still':
                    return self.send_json({'job': start_job(key, '逐拍抽帧', ['still', str(path)], exclusive=True)})
                if act == 'render':
                    return self.send_json({'job': start_job(key, '渲染成片', ['render', str(path)], exclusive=True)})
                if act == 'publish':  # 发布包：标题、简介、话题、章节、封面（按指定构建，默认最新）
                    return self.send_json({'job': start_job(key, '生成发布包', [str(STUDIO / 'publish.py'), str(path)] + (['--build', b['build']] if b.get('build') else []))})
                return self.send_json({'error': f'未知操作 {act}'}, 400)
            if sub == ['preview'] and method == 'POST':
                return self.send_json(start_preview(key))
            if sub == ['history'] and method == 'GET':
                return self.send_json(sorted((x.name for x in (d / '.history').glob('*.yaml')), reverse=True) if (d / '.history').exists() else [])
        if len(p) == 2 and p[0] == 'episodes' and method == 'DELETE':
            r = archive_episode(p[1])
            return self.send_json(r, 400 if r.get('error') else 200)
        if p == ['open-folder'] and method == 'POST':
            return self.send_json(open_in_explorer(self.body().get('path', '')))
        if len(p) == 2 and p[0] == 'jobs' and method == 'DELETE':
            r = cancel_job(p[1])
            return self.send_json(r, 400 if r.get('error') else 200)
        if p == ['preview'] and method == 'DELETE':
            stop_preview()
            return self.send_json({'ok': True})
        if p[:1] == ['jobs'] and method == 'GET':
            ext = external_jobs()
            if len(p) == 1:
                own = [job_summary(j) for j in JOBS.values()]
                return self.send_json(sorted(own + [job_summary(j) for j in ext.values()], key=lambda j: -j['started'])[:30])
            j = JOBS.get(p[1]) or ext.get(p[1])
            return self.send_json(j or {'error': 'no job'}, 200 if j else 404)
        if p == ['components']:
            data = json.loads((STUDIO / 'components.json').read_text(encoding='utf-8'))
            for b in data['batches']:
                g = STUDIO / b.get('gallery', data.get('gallery', 'gallery'))
                b['images'] = [rel(x) for x in sorted(g.glob('*.jpg'), key=lambda x: int(x.stem) if x.stem.isdigit() else 0)] if g.exists() else []
            return self.send_json(data)
        if p == ['sfx']:
            f = ROOT / '03_素材' / '音效' / 'catalog.json'
            return self.send_json(json.loads(f.read_text(encoding='utf-8')) if f.exists() else {'items': []})
        if p == ['palette']:
            return self.send_json(json.loads((STUDIO / 'data' / 'palette.json').read_text(encoding='utf-8')))
        if p == ['meta']:
            cells = [{'id': f.stem, **json.loads(f.read_text(encoding='utf-8'))['meta']} for f in sorted((STUDIO / 'data' / 'cells').glob('*.geojson'))]
            refs = [x.relative_to(ROOT).as_posix() for x in sorted((ROOT / '03_素材' / '配音参考').rglob('*.wav'))]
            return self.send_json({'cells': cells, 'voice_refs': refs, 'preview': {'episode': PREVIEW.get('episode'), 'url': f'http://localhost:{PREVIEW_PORT}' if PREVIEW.get('episode') else None}})
        if p == ['tools', 'sources']:
            terms = [t for t in re.split(r'\s+', q.get('q', '').strip()) if t]
            books = [b for b in q.get('books', '').split(',') if b]
            if not terms:
                return self.send_json([])
            buf = io.StringIO()
            import contextlib
            with contextlib.redirect_stdout(buf):
                studio.cmd_sources(terms, books or None, int(q.get('limit', 20)), 260)
            return self.send_json(json.loads(buf.getvalue()))
        if p == ['tools', 'places']:
            names = [t for t in re.split(r'[\s,，]+', q.get('q', '').strip()) if t]
            buf = io.StringIO()
            import contextlib
            with contextlib.redirect_stdout(buf):
                studio.cmd_places(names, int(q['year']) if q.get('year') else None, q.get('web') == '1')
            return self.send_json(json.loads(buf.getvalue()))
        return self.send_json({'error': 'unknown api'}, 404)

    def do_GET(self):
        self.route('GET')

    def do_POST(self):
        self.route('POST')

    def do_PUT(self):
        self.route('PUT')

    def do_PATCH(self):
        self.route('PATCH')

    def do_DELETE(self):
        self.route('DELETE')


def external_jobs() -> dict:
    """Builds/renders started outside the web UI (CLI, background) report to
    05_项目/Remotion/studio/<id>/progress.json; show recent ones as jobs."""
    out = {}
    now = time.time()
    for f in OUT_ROOT.glob('*/progress.json'):
        try:
            pr = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        fresh = now - pr.get('updated', 0)
        if pr.get('pid') and any(j.get('pid') == pr['pid'] for j in JOBS.values()):
            continue                      # started from this page: already listed as its own job
        if pr.get('status') == 'cancelled' and fresh > 600:
            continue
        if pr.get('status') == 'running' and fresh > 180:
            continue                      # stale: the process probably died
        if pr.get('status') == 'done' and fresh > 1800:
            continue
        key = f.parent.name
        total, done = pr.get('total'), pr.get('done')
        prog = (done / total) if total and done is not None else None
        line = f"{pr.get('stage')}" + (f' {done}/{total}' if total else '') + (f" · {pr['note']}" if pr.get('note') else '')
        jid = 'ext-' + key
        st = pr.get('status') if pr.get('status') in ('done', 'cancelled') else 'running'
        out[jid] = {'id': jid, 'episode': key, 'kind': f"后台任务 · {pr.get('stage')}", 'status': st, 'external': True,
                    'log': [line, '（从命令行或后台启动，进度来自 progress.json）'], 'progress': 1.0 if st == 'done' else prog,
                    'done': done, 'total': total, 'note': pr.get('note', ''), 'folder': pr.get('folder') if st == 'done' else None,
                    'started': pr.get('started', now), 'ended': pr.get('updated') if st != 'running' else None, 'cmd': []}
    return out


def main():
    import threading
    import urllib.request
    import webbrowser
    url = f'http://127.0.0.1:{PORT}'
    open_browser = '--open' in sys.argv
    # Already running (e.g. a second double-click): just open the page instead of failing on the port.
    try:
        urllib.request.urlopen(url, timeout=1.5)
        print(f'History Studio 已在运行：{url}', flush=True)
        if open_browser:
            webbrowser.open(url)
        return
    except OSError:
        pass
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    except OSError as e:
        print(f'端口 {PORT} 被其他程序占用，无法启动：{e}', flush=True)
        print('可以设置环境变量 HISTORY_STUDIO_PORT 换一个端口。', flush=True)
        return
    print(f'History Studio UI: {url}', flush=True)
    if open_browser:   # open only once the server is listening
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    finally:
        stop_preview()


if __name__ == '__main__':
    main()
