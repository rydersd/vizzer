"""Local, incremental public-session history. Never import reasoning or tool output.

The background index is independent of the graph writer and answer ledger. A
request only reads SQLite; scanning transcripts never blocks the constellation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote

WINDOW = 72 * 3600
PUBLIC_EVENT_SCHEMA = '2'
PUBLIC_ARCHIVE_SCHEMA = '3'
_instances = {}
_instances_lock = threading.Lock()
_cache_coordinators = {}
_cache_coordinators_lock = threading.Lock()
COMMON_CONTEXT_TAGS = (
    'system|developer|environment_context|app-context|in-app-browser-context'
)
CLAUDE_CONTEXT_TAGS = (
    'system-reminder|local-command-caveat|local-command-stdout|'
    'command-name|command-message|command-args'
)


def strip_injected_context(text, provider=''):
    """Remove app-supplied context blocks while retaining authored text around them."""
    text = str(text or '')
    tags = COMMON_CONTEXT_TAGS
    if provider == 'Claude':
        tags += '|' + CLAUDE_CONTEXT_TAGS
    pattern = (
        r'<(?P<tag>' + tags + r')\b[^>]*>'
        r'.*?</(?P=tag)>'
    )
    previous = None
    while text != previous:
        previous = text
        text = re.sub(pattern, '', text, flags=re.I | re.S)
    return text.strip()


def clean(text, limit=6000):
    text = strip_injected_context(text)
    # Team handoffs are public conversation, not model reasoning. Keep the
    # authored message and sender, but never treat its contents as instructions.
    text = re.sub(r'<codex_delegation>\s*<source_thread_id>([^<]+)</source_thread_id>\s*<input>(.*?)</input>\s*</codex_delegation>',
                  lambda m: '[Team message from session '+m[1]+']\n'+m[2], text, flags=re.S)
    text = re.sub(r'<(?:codex_delegation)[^>]*>.*?</(?:codex_delegation)>', '[attached context omitted]', text, flags=re.S)
    text = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', text)
    text = re.sub(r'\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}', '[redacted]', text)
    text = text.strip()
    return text[:limit] + ('\n[Excerpt truncated; original source record retained.]' if len(text)>limit else '')


def archive_markdown_text(text):
    """Render local file URLs as portable, inert references in Markdown exports.

    Agent reports legitimately mention files from several worktrees. A literal
    ``file://`` URL is neither portable nor a valid authored wiki link, though,
    and makes the repository link-policy gate treat a recoverable activity log
    as broken documentation. Keep the useful repo-relative suffix when one is
    present, but never emit a clickable machine-local URL.
    """
    def portable(raw):
        path = unquote(raw.removeprefix('file://').removeprefix('localhost'))
        parts = Path(path).parts
        content_index = next(
            (index for index, part in enumerate(parts)
             if part in {'wiki', 'docs', 'src', 'tests', 'vizzer'}),
            None,
        )
        if content_index is not None:
            label = '/'.join(parts[content_index:])
        else:
            label = Path(path).name or 'local file'
        return '`local file: ' + label.replace('`', '') + '`'

    def replace_link(match):
        return match.group(1) + ' (' + portable(match.group(2)) + ')'

    def replace_bare(match):
        raw = match.group(0)
        trailing = ''
        while raw and raw[-1] in '.,;:!?':
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        return portable(raw) + trailing

    text = str(text or '')
    text = re.sub(r'\[([^\]\n]+)\]\((file://[^\s)]+)\)', replace_link, text)
    text = re.sub(r'<(file://[^\s>]+)>', lambda match: portable(match.group(1)), text)
    text = re.sub(r'`(file://[^`\n]+)`', lambda match: portable(match.group(1)), text)
    text = re.sub(
        r'([\"\'])(file://[^\s\"\'<>\])`]+)(\1)',
        lambda match: match.group(1) + portable(match.group(2)) + match.group(3),
        text,
    )
    return re.sub(r'file://[^\s<>\])`\"\']+', replace_bare, text)


def session_label(text, cwd='', sid=''):
    """A recorded title, or an explicitly identified excerpt/branch fallback."""
    text = str(text or '')
    delegated = re.search(r'<input>(.*?)</input>', text, re.S)
    summary = re.search(r'<teammate-message\b[^>]*\bsummary="([^"]+)"', text)
    if delegated:
        text = delegated[1]
    elif summary:
        text = summary[1]
    text = clean(text).split('\n[Excerpt truncated;', 1)[0].strip()
    text = next((line.strip().lstrip('# ') for line in text.splitlines()
                 if line.strip() and not line.startswith('[Team message')), '')
    if not text or text == '[attached context omitted]':
        text = Path(cwd).name + ' · ' + sid[-12:]
    if text.startswith('/'):
        text = Path(text).name + ' · ' + Path(text).parent.name
    return text[:110] + ('…' if len(text)>110 else '')


def story_refs(text):
    """Return explicit Story IDs without inventing links from prose."""
    ids = re.findall(r'\bstory:([a-z0-9][a-z0-9-]+)', str(text or ''))
    ids += re.findall(
        r'wiki/product-spec/[^\s`<>]*?/stories/([a-z0-9-]+)\.md',
        str(text or ''),
    )
    return ['story:' + slug for slug in dict.fromkeys(ids)]


def stamp(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError):
        return 0


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def public_events(record, provider):
    """Yield only public messages and tool names, never reasoning/arguments/results."""
    if provider == 'Codex':
        p = record.get('payload', {})
        if not isinstance(p, dict):
            return
        if record.get('type') == 'event_msg':
            if p.get('type') in ('agent_message', 'user_message'):
                text = strip_injected_context(p.get('message', ''), provider)
                if text:
                    yield ('guidance' if p['type'] == 'user_message' else 'progress', text, '')
        elif record.get('type') == 'response_item' and p.get('type') in ('function_call', 'custom_tool_call'):
            yield ('action', 'Invoked ' + str(p.get('name', 'tool')), str(p.get('name', '')))
    elif record.get('type') == 'assistant':
        for part in record.get('message', {}).get('content', []):
            if not isinstance(part, dict):
                continue
            if part.get('type') == 'text':
                text = strip_injected_context(part.get('text', ''), provider)
                if text:
                    yield ('progress', text, '')
            elif part.get('type') == 'tool_use':
                yield ('action', 'Invoked ' + str(part.get('name', 'tool')), str(part.get('name', '')))
    elif record.get('type') == 'user':
        content = record.get('message', {}).get('content', '')
        if isinstance(content, str):
            text = strip_injected_context(content, provider)
            if text:
                yield ('guidance', text, '')
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get('type') == 'text':
                    text = strip_injected_context(part.get('text', ''), provider)
                    if text:
                        yield ('guidance', text, '')


class History:
    def __init__(self, root, home=None, cache=None, checkout_roots=None):
        self.root = Path(root)
        self.home = Path(home or Path.home())
        self.project_name = self._project_name()
        self.checkout_roots = tuple(
            Path(value).expanduser().resolve(strict=False)
            for value in (checkout_roots or [])
        )
        self.project_common_dir = self._git_common_dir(self.root)
        key = hashlib.sha256(str(self.root).encode()).hexdigest()[:16]
        self.cache = Path(cache or self.home / '.cache' / 'vizzer' / ('history-' + key))
        self.cache.mkdir(parents=True, exist_ok=True)
        self.db = self.cache / 'history-v3.sqlite3'
        cache_identity = str(self.cache.resolve(strict=True))
        with _cache_coordinators_lock:
            self._coordinator = _cache_coordinators.setdefault(
                cache_identity, {'lock': threading.RLock(), 'scope': None}
            )
        self.lock = self._coordinator['lock']
        self.state_lock = threading.Lock()
        self.refreshing = False
        self.last_scan = 0
        self.error = ''
        self.coverage = {}
        self.started = False
        privacy_migrated = False
        scope_changed = False
        archive_needs_rewrite = False
        with self.connect() as c:
            c.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, offset INTEGER, inode INTEGER, metadata TEXT);
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, provider TEXT, title TEXT, cwd TEXT, branch TEXT, model TEXT, source TEXT);
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, session TEXT, timestamp REAL, kind TEXT, text TEXT, tool TEXT, line INTEGER);
                CREATE TABLE IF NOT EXISTS event_story_refs(event TEXT, story TEXT, PRIMARY KEY(event,story));
                CREATE TABLE IF NOT EXISTS history_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_time ON events(timestamp);
                CREATE INDEX IF NOT EXISTS event_session ON events(session,timestamp);
                CREATE INDEX IF NOT EXISTS story_ref_event ON event_story_refs(event);
            ''')
            scope_fingerprint = hashlib.sha256(json.dumps({
                'root': str(self.root.resolve(strict=False)),
                'commonDir': str(self.project_common_dir or ''),
                'checkoutRoots': sorted(str(path) for path in self.checkout_roots),
            }, sort_keys=True).encode()).hexdigest()
            self.scope_fingerprint = scope_fingerprint
            with self.lock:
                previous_scope = c.execute(
                    "SELECT value FROM history_meta WHERE key='admission_scope'"
                ).fetchone()
                if not previous_scope or previous_scope['value'] != scope_fingerprint:
                    # Scope is a privacy boundary. A removed allowlist entry must
                    # revoke its cached rows, references, offsets, and exports.
                    c.executescript('''
                        DELETE FROM event_story_refs;
                        DELETE FROM events;
                        DELETE FROM sessions;
                        DELETE FROM files;
                    ''')
                    c.execute(
                        "INSERT OR REPLACE INTO history_meta VALUES('admission_scope',?)",
                        (scope_fingerprint,),
                    )
                    # Archive cleanup is a separately fallible filesystem step.
                    # Invalidate its marker in the same transaction so a crash or
                    # write failure is retried on the next initialization.
                    c.execute(
                        "DELETE FROM history_meta WHERE key='public_archive_schema'"
                    )
                    scope_changed = True
                self._coordinator['scope'] = scope_fingerprint
            # Existing v3 indexes predate materialized Story references. Run
            # the text scan once as a schema migration, not at every launch;
            # subsequent ingestion maintains this table incrementally.
            migration = c.execute(
                "SELECT value FROM history_meta WHERE key='story_refs_schema'"
            ).fetchone()
            if not migration or migration['value'] != '1':
                for row in c.execute(
                    "SELECT id,text FROM events WHERE kind!='action'"
                ).fetchall():
                    for story in story_refs(row['text']):
                        c.execute(
                            'INSERT OR IGNORE INTO event_story_refs VALUES(?,?)',
                            (row['id'], story),
                        )
                c.execute(
                    "INSERT OR REPLACE INTO history_meta VALUES('story_refs_schema','1')"
                )
            privacy = c.execute(
                "SELECT value FROM history_meta WHERE key='public_event_schema'"
            ).fetchone()
            if not privacy or privacy['value'] != PUBLIC_EVENT_SCHEMA:
                rows = c.execute(
                    '''SELECT e.*,s.provider FROM events e
                       JOIN sessions s ON s.id=e.session'''
                ).fetchall()
                for row in rows:
                    sanitized = strip_injected_context(row['text'], row['provider'])
                    if sanitized == row['text']:
                        continue
                    c.execute('DELETE FROM event_story_refs WHERE event=?', (row['id'],))
                    c.execute('DELETE FROM events WHERE id=?', (row['id'],))
                    if not sanitized:
                        continue
                    event_id = hashlib.sha256(json.dumps([
                        row['session'], row['timestamp'], row['kind'], sanitized,
                        row['tool'], '',
                    ], ensure_ascii=False).encode()).hexdigest()[:24]
                    c.execute(
                        'INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)',
                        (event_id, row['session'], row['timestamp'], row['kind'],
                         sanitized, row['tool'], row['line']),
                    )
                    if row['kind'] != 'action':
                        for story in story_refs(sanitized):
                            c.execute(
                                'INSERT OR IGNORE INTO event_story_refs VALUES(?,?)',
                                (event_id, story),
                            )
                c.execute(
                    "INSERT OR REPLACE INTO history_meta VALUES"
                    "('public_event_schema',?)",
                    (PUBLIC_EVENT_SCHEMA,),
                )
                for row in c.execute(
                    'SELECT id,provider,title,cwd FROM sessions'
                ).fetchall():
                    sanitized = strip_injected_context(
                        row['title'], row['provider']
                    )
                    if sanitized != row['title']:
                        c.execute(
                            'UPDATE sessions SET title=? WHERE id=?',
                            (session_label(sanitized, row['cwd'], row['id']),
                             row['id']),
                        )
                privacy_migrated = True
            archive = c.execute(
                "SELECT value FROM history_meta WHERE key='public_archive_schema'"
            ).fetchone()
            archive_needs_rewrite = (
                scope_changed or privacy_migrated or not archive
                or archive['value'] != PUBLIC_ARCHIVE_SCHEMA
            )
        if archive_needs_rewrite:
            with self.lock:
                if self._scope_current():
                    self._rewrite_all_exports()
                    with self.connect() as c:
                        c.execute(
                            "INSERT OR REPLACE INTO history_meta VALUES"
                            "('public_archive_schema',?)",
                            (PUBLIC_ARCHIVE_SCHEMA,),
                        )

    def connect(self):
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _scope_current(self):
        return self._coordinator['scope'] == self.scope_fingerprint

    def request_refresh(self):
        with self.state_lock:
            if self.refreshing or time.time() - self.last_scan < 30:
                return
            self.refreshing = True
        threading.Thread(target=self._scan, daemon=True, name='vizzer-session-history').start()

    def start(self):
        with self.state_lock:
            if self.started:
                return
            self.started = True
        def loop():
            while True:
                self.request_refresh()
                time.sleep(30)
        threading.Thread(target=loop, daemon=True, name='vizzer-history-clock').start()

    def _project_name(self):
        """Return the shared checkout family name without requiring a live cwd.

        Linked worktrees all point at the same common Git directory.  Its
        parent is a considerably stronger project identity than guessing from
        a checkout suffix, and it keeps transcript discovery portable across
        projects that install Vizzer.
        """
        try:
            import subprocess
            common = subprocess.check_output(
                ['git', '-C', str(self.root), 'rev-parse', '--git-common-dir'],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
            common_path = Path(common)
            if not common_path.is_absolute():
                common_path = self.root / common_path
            common_path = common_path.resolve()
            return common_path.parent.name if common_path.name == '.git' else self.root.name
        except (OSError, subprocess.SubprocessError):
            return self.root.name

    @staticmethod
    def _git_common_dir(checkout):
        checkout = Path(checkout)
        if not checkout.is_dir():
            return None
        try:
            import subprocess
            common = subprocess.check_output(
                ['git', '-C', str(checkout), 'rev-parse', '--git-common-dir'],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
            common_path = Path(common)
            if not common_path.is_absolute():
                common_path = checkout / common_path
            return common_path.resolve(strict=True)
        except (OSError, subprocess.SubprocessError):
            return None

    def _same_project_checkout(self, cwd):
        candidate = Path(str(cwd or '')).expanduser().resolve(strict=False)
        candidate_common_dir = self._git_common_dir(candidate)
        if candidate_common_dir is not None:
            return bool(
                self.project_common_dir is not None
                and candidate_common_dir == self.project_common_dir
            )
        if candidate == self.root.resolve(strict=False) or candidate in self.checkout_roots:
            return True
        return False

    def paths(self):
        for folder in (self.home / '.codex/sessions', self.home / '.codex/archived_sessions'):
            if folder.is_dir():
                for p in folder.rglob('*.jsonl'):
                    if self._confined_regular_file(p, folder):
                        yield 'Codex', p
        folder = self.home / '.claude/projects'
        if folder.is_dir():
            for project in folder.iterdir():
                if project.is_dir() and self.project_name in project.name:
                    for p in project.rglob('*.jsonl'):
                        if self._confined_regular_file(p, project):
                            yield 'Claude', p

    @staticmethod
    def _confined_regular_file(path, root):
        """Reject transcript symlinks and paths escaping an approved root."""
        path, root = Path(path), Path(root)
        try:
            relative = path.relative_to(root)
            root_resolved = root.resolve(strict=True)
            resolved = path.resolve(strict=True)
            resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            return False
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return False
        return resolved.is_file()

    def _generated_folder(self):
        """Create machine-local archives below the cache, never the checkout."""
        folder = self.cache / 'work-history'
        cache_resolved = self.cache.resolve(strict=True)
        current = self.cache
        for part in folder.relative_to(self.cache).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('Generated event-log path must not contain symlinks')
        folder.mkdir(parents=True, exist_ok=True)
        try:
            folder.resolve(strict=True).relative_to(cache_resolved)
        except (OSError, ValueError) as exc:
            raise ValueError('Generated event-log path escapes the cache') from exc
        return folder

    @staticmethod
    def _replace_text(folder, name, body):
        descriptor, raw = tempfile.mkstemp(prefix='.' + name + '.', dir=str(folder))
        temp = Path(raw)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(body)
            os.replace(temp, folder / name)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def in_project(self, metadata):
        cwd = str(metadata.get('cwd', ''))
        # Worktree families are explicit. Do not include unrelated chats that
        # merely mention the project somewhere in their message body.
        if metadata.get('_scope_cwd') != cwd:
            metadata['_scope_cwd'] = cwd
            metadata['_scope_ok'] = self._same_project_checkout(cwd)
        return bool(metadata.get('_scope_ok'))

    def ingest(self, path, provider, now):
        with self.lock:
            if not self._scope_current():
                return set()
            return self._ingest_locked(path, provider, now)

    def _ingest_locked(self, path, provider, now):
        stat = path.stat()
        changed = set()
        with self.connect() as c:
            row = c.execute('SELECT * FROM files WHERE path=?', (str(path),)).fetchone()
            meta = json.loads(row['metadata']) if row else {}
            meta.pop('_scope_cwd', None)
            meta.pop('_scope_ok', None)
            offset = row['offset'] if row and row['inode'] == stat.st_ino and row['offset'] <= stat.st_size else 0
            if offset == stat.st_size:
                return changed
            if not offset:
                meta = {'line': 0}
            with path.open('rb') as f:
                f.seek(offset)
                while True:
                    start = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    if not line.endswith(b'\n'):
                        f.seek(start)  # Retry a writer's incomplete last record.
                        break
                    meta['line'] = meta.get('line', 0) + 1
                    # Tool output and encrypted reasoning can be enormous.
                    if len(line) > 4 * 1024 * 1024:
                        continue
                    try:
                        r = json.loads(line)
                    except (ValueError, UnicodeError):
                        continue
                    if not isinstance(r, dict):
                        continue
                    p = r.get('payload', {})
                    if provider == 'Codex' and r.get('type') in ('session_meta', 'turn_context') and isinstance(p, dict):
                        for key in ('cwd', 'model'):
                            if p.get(key): meta[key] = p[key]
                        if r['type'] == 'session_meta':
                            meta['id'] = p.get('id') or p.get('session_id') or path.stem
                            meta['branch'] = p.get('git', {}).get('branch', '')
                    elif provider == 'Claude':
                        for source, key in (('cwd', 'cwd'), ('sessionId', 'id'), ('gitBranch', 'branch'), ('aiTitle', 'title')):
                            if r.get(source): meta[key] = r[source]
                        if r.get('type') == 'assistant':
                            meta['model'] = r.get('message', {}).get('model', '')
                        if r.get('isSidechain'):
                            meta['sidechain'] = True
                    ts = stamp(r.get('timestamp'))
                    if ts < now - WINDOW or ts > now + 300 or not self.in_project(meta):
                        continue
                    sid = provider.lower() + ':' + str(meta.get('id', path.stem))
                    if provider=='Claude' and 'subagents' in path.parts:
                        sid += ':agent:' + path.stem
                    for i, (kind, raw, tool) in enumerate(public_events(r, provider)):
                        text = clean(raw)
                        if not text or text == '[attached context omitted]':
                            continue
                        if not meta.get('title') and kind in ('guidance', 'progress'):
                            meta['title'] = text.splitlines()[0][:140]
                        call_id = p.get('call_id','') if isinstance(p,dict) and kind=='action' else ''
                        event_id = hashlib.sha256(json.dumps([sid,ts,kind,text,tool,call_id],ensure_ascii=False).encode()).hexdigest()[:24]
                        inserted = c.execute(
                            'INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)',
                            (event_id,sid,ts,kind,text,clean(tool,120),meta['line']),
                        ).rowcount
                        if inserted and kind != 'action':
                            for story in story_refs(text):
                                c.execute(
                                    'INSERT OR IGNORE INTO event_story_refs VALUES(?,?)',
                                    (event_id, story),
                                )
                        c.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?,?,?,?)', (sid,provider,session_label(meta.get('title'),meta.get('cwd',''),sid),meta.get('cwd',''),meta.get('branch',''),meta.get('model',''),str(path)))
                        changed.add(sid)
                offset = f.tell()
            persisted_meta = {
                key: value for key, value in meta.items()
                if not key.startswith('_scope_')
            }
            c.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?)',
                      (str(path),offset,stat.st_ino,json.dumps(persisted_meta)))
        return changed

    def _scan(self):
        with self.lock:
            if not self._scope_current():
                with self.state_lock:
                    self.refreshing = False
                return
            self._scan_locked()

    def _scan_locked(self):
        now = time.time()
        counts = {'Codex': 0, 'Claude': 0, 'unreadable': 0}
        try:
            changed = set()
            for provider, path in self.paths():
                try:
                    if path.stat().st_mtime < now - WINDOW:
                        continue
                    counts[provider] += 1
                    changed.update(self.ingest(path, provider, now))
                except (OSError, ValueError):
                    counts['unreadable'] += 1
            self.coverage = counts
            self.error = ''
            self.update_codex_labels()
            for sid in changed:
                self.export(sid)
            self.export_index(now)
        except Exception as exc:
            self.error = type(exc).__name__ + ': ' + clean(str(exc), 200)
        finally:
            with self.state_lock:
                self.last_scan = time.time()
                self.refreshing = False

    def update_codex_labels(self):
        """Use the app's current recorded title, only for already scoped sessions."""
        path=self.home/'.codex/state_5.sqlite'
        if not path.is_file():
            return
        try:
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2) as app, self.connect() as c:
                for row in c.execute("SELECT id FROM sessions WHERE provider='Codex'").fetchall():
                    source=app.execute('SELECT title,cwd,git_branch,model FROM threads WHERE id=?',(row['id'].split(':',1)[1],)).fetchone()
                    if source:
                        c.execute('UPDATE sessions SET title=?,cwd=?,branch=?,model=? WHERE id=?',(session_label(source[0],source[1],row['id']),source[1],source[2] or '',source[3] or '',row['id']))
        except sqlite3.Error:
            pass  # Versioned app storage may change; transcript labels survive.

    def session(self, sid):
        with self.connect() as c:
            row = c.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
            return dict(row) if row else None

    def export(self, sid):
        """Recoverable local exports; no raw transcript or hidden content copied."""
        with self.lock:
            if not self._scope_current():
                return
            self._export_locked(sid)

    def _export_locked(self, sid):
        session = self.session(sid)
        if not session:
            return
        with self.connect() as c:
            events = [dict(row) for row in c.execute('SELECT * FROM events WHERE session=? ORDER BY timestamp,id', (sid,))]
        slug = hashlib.sha256(sid.encode()).hexdigest()[:20]
        folder = self._generated_folder()
        for extension, body in [('jsonl',''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events)), ('md',self.markdown(session,events))]:
            self._replace_text(folder, slug + '.' + extension, body)

    def export_index(self, now):
        folder = self._generated_folder()
        with self.connect() as c:
            rows = c.execute('SELECT s.id,s.provider,s.title,MAX(e.timestamp) last,COUNT(*) total FROM sessions s JOIN events e ON e.session=s.id WHERE e.timestamp>=? GROUP BY s.id ORDER BY last DESC',(now-WINDOW,)).fetchall()
        lines=['# Session event-log index', '', 'Updated '+iso(now)+'. Rolling 72-hour index; per-session archives retain previously imported records.', '']
        for s in rows:
            slug=hashlib.sha256(s['id'].encode()).hexdigest()[:20]
            label=re.sub(r'[\[\]\n]', ' ',s['title'])
            lines.append('- ['+s['provider']+' · '+label+']('+slug+'.md) · '+str(s['total'])+' events · '+iso(s['last'])+' · session `'+s['id']+'` · [JSONL]('+slug+'.jsonl)')
        self._replace_text(folder, 'INDEX.md', '\n'.join(lines)+'\n')

    def _rewrite_all_exports(self):
        """Replace generated archives after a privacy-schema migration."""
        with self.connect() as c:
            sessions = [row['id'] for row in c.execute(
                'SELECT id FROM sessions ORDER BY id'
            )]
        expected = set()
        for sid in sessions:
            slug = hashlib.sha256(sid.encode()).hexdigest()[:20]
            expected.update({slug + '.md', slug + '.jsonl'})
            self.export(sid)
        folder = self._generated_folder()
        archive_name = re.compile(r'^[0-9a-f]{20}\.(?:md|jsonl)$')
        for path in folder.iterdir():
            if archive_name.fullmatch(path.name) and path.name not in expected:
                path.unlink()
        self.export_index(time.time())

    def markdown(self, session, events):
        lines = ['# '+archive_markdown_text(session['title']), '', 'Session: '+session['id'], 'Provider: '+session['provider'], 'Worktree: '+session['cwd'], 'Branch (recorded): '+(session['branch'] or 'not recorded'), '', 'Public activity excerpts. Explanations and results are agent reports, not independent verification. Gaps are not proof of idle time. Raw reasoning and tool output are excluded.', '']
        for e in events:
            lines += ['## '+iso(e['timestamp'])+' · '+e['kind'], '', 'Event: '+e['id'], '', archive_markdown_text(e['text']), '']
        return '\n'.join(lines)

    def payload(self, query=''):
        self.request_refresh()
        params = parse_qs(query)
        summary = params.get('summary', [''])[0] == '1'
        sid = params.get('session',[''])[0]
        provider = params.get('provider',[''])[0]
        kind = params.get('kind',[''])[0]
        try:
            hour = int(params.get('hour',['-1'])[0])
        except ValueError:
            hour = -1
        try:
            offset = max(0,min(int(params.get('offset',['0'])[0]),1000000))
        except ValueError:
            offset = 0
        now = time.time()
        with self.connect() as c:
            sessions = [dict(row) for row in c.execute('''SELECT s.*,MIN(e.timestamp) first,MAX(e.timestamp) last,COUNT(*) events,
                SUM(e.kind='progress') updates,SUM(e.kind='action') actions FROM sessions s JOIN events e ON e.session=s.id
                WHERE e.timestamp>=? GROUP BY s.id ORDER BY last DESC''',(now-WINDOW,))]
            if summary:
                total, events, bins = 0, [], []
            else:
                args = [now-WINDOW]
                where = 'timestamp>=?'
                if 0 <= hour < 72:
                    where += ' AND timestamp>=? AND timestamp<?'
                    args += [now-WINDOW+hour*3600,now-WINDOW+(hour+1)*3600]
                for column, value in [('session',sid),('kind',kind)]:
                    if value:
                        where += ' AND '+column+'=?'; args.append(value)
                if provider:
                    where += ' AND session IN (SELECT id FROM sessions WHERE provider=?)';args.append(provider)
                total = c.execute('SELECT COUNT(*) FROM events WHERE '+where,args).fetchone()[0]
                events = [dict(row) for row in c.execute('SELECT * FROM events WHERE '+where+' ORDER BY timestamp DESC,id LIMIT 100 OFFSET ?',args+[offset])]
                bins = [dict(row) for row in c.execute('SELECT session,CAST((timestamp-?)/3600 AS INT) hour,COUNT(*) count FROM events WHERE timestamp>=? GROUP BY session,hour',(now-WINDOW,now-WINDOW))]
            references = [dict(row) for row in c.execute(
                '''SELECT e.id event,e.session,e.timestamp,r.story storyId,
                          (SELECT COUNT(*) FROM event_story_refs all_refs
                           WHERE all_refs.event=e.id) eventStoryCount
                   FROM event_story_refs r JOIN events e ON e.id=r.event
                   WHERE e.timestamp>=? ORDER BY e.timestamp,e.id,r.story''',
                (now-WINDOW,),
            )]
            # Keep the newest explicit references per session. The full log is
            # independently retained; no undocumented node association invented.
            buckets={}
            for ref in references:
                buckets[(ref['session'],ref['storyId'],int(ref['timestamp']//3600))]=ref
            trails={}
            for ref in sorted(buckets.values(),key=lambda r:(r['timestamp'],r['event'])):
                trails.setdefault(ref['session'],[]).append(ref)
            references=[ref for lane in trails.values() for ref in lane[-96:]]
        # Server-only provenance paths never become arbitrary filesystem routes.
        for s in sessions:
            s['sourceName'] = Path(s.pop('source')).name
            s['observedSpanSeconds'] = s['last'] - s['first']
        return {'schema':1,'windowStart':iso(now-WINDOW),'windowEnd':iso(now),'hours':72,'sessions':sessions,'events':events,'bins':bins,'references':references,'total':total,'offset':offset,'nextOffset':offset+len(events) if offset+len(events)<total else None,'refreshing':self.refreshing,'lastScan':iso(self.last_scan) if self.last_scan else None,'coverage':self.coverage,'error':self.error}

    def event(self, event_id):
        with self.connect() as c:
            row=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        return dict(row) if row else None

    def log(self, sid, query=''):
        s = self.session(sid)
        if not s:
            return None
        params=parse_qs(query);kind=params.get('kind',[''])[0];tool=params.get('tool',[''])[0];search=params.get('q',[''])[0][:200]
        try: offset=max(0,min(1000000,int(params.get('offset',['0'])[0])))
        except ValueError: offset=0
        where='session=? AND timestamp>=?';args=[sid,time.time()-WINDOW]
        with self.connect() as c:
            total=c.execute('SELECT COUNT(*) FROM events WHERE '+where,args).fetchone()[0]
            tool_names=[r[0] for r in c.execute("SELECT DISTINCT tool FROM events WHERE "+where+" AND tool!='' ORDER BY tool",args)]
            if kind: where+=' AND kind=?';args.append(kind)
            if tool=='@exec':
                # Exact invocation family, not text that merely mentions exec.
                where+=" AND kind='action' AND (lower(tool) IN ('exec','exec_command','functions.exec','functions.exec_command') OR lower(tool) LIKE '%.exec' OR lower(tool) LIKE '%.exec_command')"
            elif tool: where+=' AND tool=?';args.append(tool)
            if search: where+=' AND instr(lower(text),lower(?))>0';args.append(search)
            matching=c.execute('SELECT COUNT(*) FROM events WHERE '+where,args).fetchone()[0]
            events=[dict(row) for row in c.execute('SELECT * FROM events WHERE '+where+' ORDER BY timestamp DESC,id LIMIT 300 OFFSET ?',args+[offset])][::-1]
        return {'session':sid,'markdown':self.markdown(s,events),'eventCount':len(events),'totalEvents':total,'matchingEvents':matching,'tools':tool_names,'offset':offset,'nextOffset':offset+len(events) if offset+len(events)<matching else None,'path':'machine-local work-history/'+hashlib.sha256(sid.encode()).hexdigest()[:20]+'.md'}


def instance(root, checkout_roots=None):
    with _instances_lock:
        key = (str(root), tuple(sorted(str(value) for value in (checkout_roots or []))))
        if key not in _instances:
            _instances[key] = History(root, checkout_roots=checkout_roots)
        return _instances[key]


def loopback_host(handler):
    host = handler.headers.get('Host', '')
    hostname = host.rsplit(':', 1)[0].strip('[]').lower()
    return hostname in {'127.0.0.1', 'localhost', '::1'}


def handle(handler, root, parsed):
    if parsed.path in {
        '/api/work-history', '/api/work-history/log',
        '/api/work-history/event', '/work-history.html',
    } and not loopback_host(handler):
        handler._send_json(403, {'error': 'loopback Host required'})
        return True
    if parsed.path == '/api/work-history/event':
        event_id=parse_qs(parsed.query).get('id',[''])[0]
        body=instance(root).event(event_id)
        handler._send_json(200 if body else 404,body or {'error':'Unknown recorded event'})
        return True
    if parsed.path == '/api/work-history':
        handler._send_json(200, instance(root).payload(parsed.query))
        return True
    if parsed.path == '/api/work-history/log':
        sid = parse_qs(parsed.query).get('session',[''])[0]
        body = instance(root).log(sid, parsed.query)
        handler._send_json(200 if body else 404, body or {'error':'Unknown recorded session'})
        return True
    if parsed.path == '/work-history.html':
        handler.send_response(302)
        handler.send_header('Location','/constellation.html')
        handler.send_header('Content-Length','0')
        handler.end_headers()
        return True
    return False
