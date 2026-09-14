"""Read-only cross-project engine comparison and content-bound change proposals.

Only the radar's own local store is written. Patch applicability is checked in
throwaway directories; no command applies a patch to a registered checkout.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import time

MAX_FILES = 1500
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_PROPOSALS = 300
SUFFIXES = {'.py', '.js', '.css', '.html', '.json', '.md', '.txt', '.svg'}
SKIP = {'__pycache__', '.git', 'node_modules', '.pytest_cache'}


class RadarError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def _run(argv, cwd=None, data=None):
    try:
        return subprocess.run(argv, cwd=cwd, input=data, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RadarError(f'Command unavailable or timed out: {argv[0]}') from exc


def _git(root, *args):
    result = _run(['git', '-C', str(root), *args])
    if result.returncode:
        raise RadarError(result.stderr.decode(errors='replace').strip()[:400])
    return result.stdout


def _relative(path):
    if (not isinstance(path, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', path)
            or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts
            or path in ('', '.')):
        raise RadarError(f'Unsafe engine-relative path: {path!r}')
    return path


def _contained(root, relative):
    path = root / _relative(relative)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise RadarError(f'Symlink not accepted: {relative}')
    if not path.resolve().is_relative_to(root.resolve()):
        raise RadarError('Path leaves its project')
    return path


def _store(root):
    path = _contained(root.resolve(), '.vizzer/radar')
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _locked(root):
    import fcntl
    store = _store(root)
    fd = os.open(store / 'lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield store
    except BlockingIOError as exc:
        raise RadarError('Another radar command is running; retry after it finishes') from exc
    finally:
        os.close(fd)


def _read(path, default):
    if not path.exists():
        return default
    if path.is_symlink() or path.stat().st_size > 96 * 1024 * 1024:
        raise RadarError('Invalid radar state file')
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RadarError('Unreadable radar state; existing state was preserved') from exc
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise RadarError('Unsupported radar state schema')
    return value


def _write(path, value):
    if path.is_symlink():
        raise RadarError('Refusing a symlink state destination')
    payload = json.dumps(value, sort_keys=True, indent=2) + '\n'
    if len(payload.encode()) > 96 * 1024 * 1024:
        raise RadarError('Radar state exceeds 96 MiB budget; prior state retained')
    fd, temporary = tempfile.mkstemp(prefix='.radar-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _accept(files, path, raw):
    _relative(path)
    if len(raw) > MAX_FILE_BYTES:
        raise RadarError(f'File exceeds 4 MiB: {path}')
    try:
        files[path] = raw.decode('utf-8')
    except UnicodeError as exc:
        raise RadarError(f'Non-text engine file requires manual review: {path}') from exc
    if len(files) > MAX_FILES or sum(len(v.encode()) for v in files.values()) > MAX_TOTAL_BYTES:
        raise RadarError('Engine snapshot exceeds 1500 files / 32 MiB')


def snapshot(project, engine_path):
    project = project.resolve()
    engine = _contained(project, engine_path)
    if not engine.is_dir():
        raise RadarError('Registered engine directory is unavailable')
    files = {}
    for directory, dirs, names in os.walk(engine, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise RadarError('Engine contains a symlink directory')
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix not in SUFFIXES:
                continue
            if path.is_symlink():
                raise RadarError('Engine contains a symlink file')
            if path.stat().st_size > MAX_FILE_BYTES:
                raise RadarError('Engine file exceeds snapshot limit')
            _accept(files, path.relative_to(engine).as_posix(), path.read_bytes())
    if not files:
        raise RadarError('Engine snapshot contains no supported source files')
    return files


def baseline(root, ref, engine_path='src/vizzer'):
    _relative(engine_path)
    commit = _git(root, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()
    archive = _git(root, 'archive', '--format=tar', commit, '--', engine_path)
    if len(archive) > MAX_TOTAL_BYTES * 2:
        raise RadarError('Baseline archive exceeds budget')
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            if not member.name.startswith(engine_path + '/'):
                continue
            path = member.name[len(engine_path) + 1:]
            if Path(path).suffix not in SUFFIXES or any(p in SKIP for p in Path(path).parts):
                continue
            if not member.isfile():
                raise RadarError('Baseline source must be a regular file')
            if member.size > MAX_FILE_BYTES:
                raise RadarError('Baseline file exceeds budget')
            _accept(files, path, tar.extractfile(member).read())
    if not files:
        raise RadarError('No engine sources in baseline')
    return {'schema': 1, 'commit': commit, 'enginePath': engine_path,
            'fingerprint': _digest(files), 'files': files}


def register(root, project_id, project_path, engine_path, ref):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', project_id) or project_id == 'upstream':
        raise RadarError('Use a lowercase project slug other than upstream')
    project_path = project_path.resolve()
    snapshot(project_path, engine_path)  # validate scope before storing it
    base = baseline(root, ref)
    with _locked(root) as store:
        registry = _read(store / 'registry.json', {'schema': 1, 'projects': {}})
        if project_id in registry['projects']:
            raise RadarError('Project already registered; baseline cannot change silently')
        if len(registry['projects']) >= 12:
            raise RadarError('First-version limit: 12 registered projects')
        registry['projects'][project_id] = {
            'path': str(project_path), 'enginePath': engine_path,
            'baseline': base['commit'], 'registeredAt': _now(),
            'baselineMeaning': 'explicit comparison reference; not asserted fork ancestry',
        }
        _write(store / ('baseline-' + base['commit'] + '.json'), base)
        _write(store / 'registry.json', registry)
    return registry['projects'][project_id]


def patch_text(path, before, after):
    _relative(path)
    if before is None and after == '':
        return f'diff --git a/{path} b/{path}\nnew file mode 100644\nindex 0000000..e69de29\n'
    if before == '' and after is None:
        return f'diff --git a/{path} b/{path}\ndeleted file mode 100644\nindex e69de29..0000000\n'
    lines = difflib.unified_diff((before or '').splitlines(keepends=True),
                                (after or '').splitlines(keepends=True),
                                fromfile='/dev/null' if before is None else 'a/' + path,
                                tofile='/dev/null' if after is None else 'b/' + path)
    return ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n'
                   for line in lines)


def presence(path, before, after, current):
    if current == after:
        return 'exact'
    if current == before:
        return 'missing'
    # Check the actual diff against an isolated copy, including unrelated edits.
    # A reverse check establishes matching hunks, not semantic equivalence.
    with tempfile.TemporaryDirectory(prefix='vizzer-radar-') as temporary:
        target = Path(temporary) / _relative(path)
        if current is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(current)
        patch = patch_text(path, before, after).encode()
        for flags, result in [(['--reverse'], 'patch_present'), ([], 'applicable')]:
            checked = _run(['git', 'apply', '--check', '--no-index', *flags, '-'],
                           cwd=temporary, data=patch)
            if checked.returncode == 0:
                return result
    return 'needs_reconciliation'


def _identity(project, engine_path, files):
    try:
        head = _git(project, 'rev-parse', 'HEAD').decode().strip()
        dirty = bool(_git(project, 'status', '--porcelain', '--untracked-files=normal', '--', engine_path))
    except RadarError:
        head, dirty = None, None
    return {'head': head, 'dirty': dirty, 'fingerprint': _digest(files)}


def scan(root):
    started = time.monotonic()
    with _locked(root) as store:
        registry = _read(store / 'registry.json', {'schema': 1, 'projects': {}})
        if not registry['projects']:
            raise RadarError('Register at least one local project before scanning')
        old = _read(store / 'report.json', {'schema': 1, 'proposals': []})
        for p in old['proposals']:
            if p['id'] != _digest({'path': p['path'], 'before': p['before'], 'after': p['after']}):
                raise RadarError('Proposal fingerprint mismatch')
        proposals = {p['id']: p for p in old['proposals']}
        upstream = snapshot(root, 'src/vizzer')
        committed = baseline(root, 'HEAD')
        copies = {'upstream': upstream}
        identities = {'upstream': _identity(root, 'src/vizzer', upstream)}
        errors = {}
        for project_id, project in registry['projects'].items():
            if not re.fullmatch(r'[0-9a-f]{40,64}', project['baseline']):
                raise RadarError('Invalid baseline commit')
            try:
                files = snapshot(Path(project['path']), project['enginePath'])
                copies[project_id] = files
                identities[project_id] = _identity(Path(project['path']), project['enginePath'], files)
            except (OSError, RadarError) as exc:
                errors[project_id] = str(exc)
        if len(registry['projects']) > 12:
            raise RadarError('First-version limit: 12 registered projects')
        discovered = set()
        for project_id, project in registry['projects'].items():
            if project_id not in copies:
                continue
            base = _read(store / ('baseline-' + project['baseline'] + '.json'), {})
            if _digest(base['files']) != base['fingerprint']:
                raise RadarError('Baseline fingerprint mismatch')
            for origin in ('upstream', project_id):
                current = copies[origin]
                for path in sorted(set(base['files']) | set(current)):
                    before, after = base['files'].get(path), current.get(path)
                    if before == after:
                        continue
                    change_id = _digest({'path': path, 'before': before, 'after': after})
                    if change_id not in proposals:
                        proposals[change_id] = {
                            'id': change_id, 'path': path, 'before': before, 'after': after,
                            'title': 'Review engine change: ' + path,
                            'summary': 'Difference from a comparison baseline; not proof of a newer downstream improvement. Behavioral intent needs review.',
                            'firstSeen': _now(), 'origins': {}, 'history': [],
                            'evidence': [], 'review': None,
                        }
                    proposal = proposals[change_id]
                    proposal['origins'][origin] = {
                        **identities[origin], 'baseline': base['commit'],
                    }
                    discovered.add(change_id)
        if len(proposals) > MAX_PROPOSALS:
            raise RadarError('Proposal budget exceeded (300); narrow registered engine scope')
        catalog = ['upstream', *sorted(registry['projects'])]
        for proposal in proposals.values():
            if time.monotonic() - started > 45:
                raise RadarError('Scan exceeded 45 seconds; prior report remains authoritative')
            observations = {}
            for project_id in catalog:
                observations[project_id] = ('unavailable' if project_id not in copies else
                    presence(proposal['path'], proposal['before'], proposal['after'],
                             copies[project_id].get(proposal['path'])))
            present = {'exact', 'patch_present'}
            committed_presence = presence(proposal['path'], proposal['before'], proposal['after'],
                                          committed['files'].get(proposal['path']))
            proposal['committedUpstream'] = committed_presence
            if observations['upstream'] in present and committed_presence in present:
                state = 'adopted' if all(v in present for v in observations.values()) else 'integrated'
            else:
                state = 'reviewed' if proposal['review'] else 'discovered'
            if proposal['id'] not in discovered and not any(v in present for v in observations.values()):
                state = 'unavailable' if errors else 'superseded'
            signature = _digest({'state': state, 'observations': observations})
            if not proposal['history'] or proposal['history'][-1]['signature'] != signature:
                proposal['history'].append({'at': _now(), 'state': state,
                                            'observations': observations, 'signature': signature})
            proposal['state'], proposal['observations'] = state, observations
        # Detect unstable observations instead of asserting a coherent scan over changing files.
        for project_id, files in copies.items():
            project = registry['projects'].get(project_id)
            location = Path(project['path']) if project else root
            engine = project['enginePath'] if project else 'src/vizzer'
            if _identity(location, engine, snapshot(location, engine)) != identities[project_id]:
                raise RadarError('Sources changed during scan; retry after the current edit finishes')
        if _git(root, 'rev-parse', 'HEAD').decode().strip() != committed['commit']:
            raise RadarError('Upstream commit changed during scan; retry')
        report = {'schema': 1, 'scannedAt': _now(), 'projects': identities, 'errors': errors,
                  'upstreamCommit': committed['commit'],
                  'proposals': sorted(proposals.values(), key=lambda p: (p['title'], p['id'])),
                  'scope': 'Registered local engine text files. No semantic-equivalence or test-execution claim.'}
        _write(store / 'report.json', report)
        return report


def report(root):
    path = _contained(root.resolve(), '.vizzer/radar/report.json')
    result = _read(path, {'schema': 1, 'proposals': [], 'projects': {}, 'errors': {}})
    for proposal in result['proposals']:
        if proposal['id'] != _digest({'path': proposal['path'], 'before': proposal['before'], 'after': proposal['after']}):
            raise RadarError('Proposal fingerprint mismatch')
        _relative(proposal['path'])
    return result


def annotate(root, change_id, title=None, summary=None, evidence=None, review=None, brief=None):
    with _locked(root) as store:
        result = _read(store / 'report.json', {'schema': 1, 'proposals': []})
        proposal = next((p for p in result['proposals'] if p['id'] == change_id), None)
        if proposal is None:
            raise RadarError('Unknown proposal fingerprint; scan and use its full id')
        if proposal['id'] != _digest({'path': proposal['path'], 'before': proposal['before'], 'after': proposal['after']}):
            raise RadarError('Proposal fingerprint mismatch')
        if title:
            proposal['title'] = title[:180]
        if summary:
            proposal['summary'] = summary[:4000]
        if evidence:
            for path in evidence:
                source = _contained(root.resolve(), path)
                if not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
                    raise RadarError('Evidence must be a bounded local file')
                item = {'path': path, 'sha256': _digest(source.read_bytes()),
                        'claim': 'Linked artifact; not independently executed by radar'}
                if item not in proposal['evidence']:
                    proposal['evidence'].append(item)
        if brief:
            source = _contained(root.resolve(), brief)
            if source.suffix != '.md' or not source.is_file() or source.stat().st_size > 65536:
                raise RadarError('Article brief must be a repository Markdown file at most 64 KiB')
            body = source.read_text(encoding='utf-8')
            headings = set(re.findall(r'^## (.+?)\s*$', body, re.MULTILINE))
            if not {'Intent', 'Rationale', 'Sources'} <= headings:
                raise RadarError('Article brief requires Intent, Rationale and Sources sections; mark unknowns explicitly')
            item = {'path': brief, 'sha256': _digest(body.encode()), 'body': body,
                    'at': _now(), 'fingerprint': change_id}
            history = proposal.setdefault('briefHistory', [])
            if not history or history[-1]['sha256'] != item['sha256'] or history[-1]['path'] != brief:
                history.append(item)
            proposal['brief'] = history[-1]
        if review:
            history = proposal.setdefault('reviewHistory', [])
            if proposal.get('review') and proposal['review'] not in history:
                history.append(proposal['review'])
            proposal['review'] = {'at': _now(), 'note': review[:4000], 'fingerprint': change_id}
            history.append(proposal['review'])
        _write(store / 'report.json', result)
        return proposal


def watch(root, interval):
    import fcntl
    fd = os.open(_store(root) / 'watch.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _watch_loop(root, interval)
    except BlockingIOError as exc:
        raise RadarError('A watcher already owns this radar') from exc
    finally:
        os.close(fd)


def _watch_loop(root, interval):
    if interval < 10 or interval > 3600:
        raise RadarError('Watch interval must be 10..3600 seconds')
    previous = None
    while True:
        try:
            store = _store(root)
            registry = _read(store / 'registry.json', {'schema': 1, 'projects': {}})
            signatures = {'registry': _digest(registry), 'upstream': _digest(snapshot(root, 'src/vizzer')),
                          'head': _git(root, 'rev-parse', 'HEAD').decode().strip()}
            for project_id, project in registry['projects'].items():
                try:
                    location = Path(project['path'])
                    signatures[project_id] = _identity(location, project['enginePath'], snapshot(location, project['enginePath']))
                except (OSError, RadarError):
                    signatures[project_id] = 'unavailable'
            # An annotation/review is also an observable input change.
            signatures['report'] = _digest(report(root))
            if signatures != previous:
                scan(root)
                refreshed = _run([sys.executable, str(root / 'vizzer/engine'), 'refresh'], cwd=root)
                if refreshed.returncode:
                    raise RadarError('Radar scanned, but view refresh failed')
                signatures['report'] = _digest(report(root))
                previous = signatures
                print('radar: changed sources scanned and views refreshed', flush=True)
            _write(store / 'watch.json', {'schema': 1, 'at': _now(), 'state': 'watching', 'interval': interval})
        except (RadarError, OSError, ValueError, KeyError, TypeError) as exc:
            _write(_store(root) / 'watch.json', {'schema': 1, 'at': _now(), 'state': 'error', 'error': str(exc)})
            print(f'radar: {exc}; prior scan retained', flush=True)
        time.sleep(interval)


def status(root):
    result = report(root)
    watch_state = _read(_contained(root.resolve(), '.vizzer/radar/watch.json'), {'schema': 1})
    message = 'Watcher not running; use radar scan to update this snapshot.'
    if watch_state.get('at'):
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(watch_state['at'])).total_seconds()
        if elapsed > max(90, 3 * watch_state.get('interval', 30)):
            message = 'Watcher heartbeat is stale; showing the last successful scan.'
        elif watch_state.get('state') == 'error':
            message = 'Scan failed: ' + watch_state.get('error', 'unknown error') + '. Last successful scan retained.'
        else:
            message = 'Watching registered engines locally. Changes appear after the next completed scan.'
    return {'scannedAt': result.get('scannedAt'), 'watchMessage': message}


def cli(root, args):
    try:
        if args.radar_action == 'register':
            result = register(root, args.id, Path(args.project), args.engine, args.baseline)
        elif args.radar_action == 'scan':
            scanned = scan(root)
            result = {'scannedAt': scanned['scannedAt'], 'projects': list(scanned['projects']),
                      'errors': scanned['errors'], 'proposals': len(scanned['proposals'])}
        elif args.radar_action == 'show':
            result = report(root)
            result = {**result, 'proposals': [{k: v for k, v in p.items() if k not in ('before', 'after')}
                                             for p in result['proposals']]}
        elif args.radar_action == 'annotate':
            result = annotate(root, args.id, args.title, args.summary, args.evidence, args.review, args.brief)
            result = {k: v for k, v in result.items() if k not in ('before', 'after')}
        elif args.radar_action == 'watch':
            watch(root, args.interval)
            return 0
        print(json.dumps(result, indent=2))
        return 0
    except KeyboardInterrupt:
        print('radar: watcher stopped')
        return 0
    except (RadarError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f'radar: {exc}')
        return 2
