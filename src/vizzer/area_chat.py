"""Repository-owned planning conversations; no model client or delivery mutations."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path('product-spec/planning/areas')
KEY = re.compile(r'[a-z0-9][a-z0-9-]{0,79}\Z')


def safe(root: Path, relative: Path) -> Path:
    root = root.resolve()
    path = root / relative
    cursor = root
    for part in relative.parts:
        if part in {'..', '.'}:
            raise ValueError('invalid planning path')
        cursor /= part
        if cursor.is_symlink():
            raise ValueError('planning paths cannot be symlinks')
    if not path.resolve().is_relative_to(root):
        raise ValueError('planning path escapes project')
    return path


def catalog(root: Path) -> list[dict]:
    path = safe(root, BASE / 'index.json')
    return json.loads(path.read_text()) if path.exists() else []


def area_dir(root: Path, area: str) -> Path:
    if not isinstance(area, str) or not KEY.fullmatch(area):
        raise ValueError('invalid area')
    if not any(row['id'] == area for row in catalog(root)):
        raise ValueError('unknown planning area')
    return safe(root, BASE / area)


def read_area(root: Path, area: str) -> dict:
    directory = area_dir(root, area)
    meta = next(row for row in catalog(root) if row['id'] == area)
    def read(name):
        path = safe(root, BASE / area / name)
        return path.read_text() if path.exists() else ''
    messages = json.loads(read('messages.json') or '[]')
    answered = {m.get('replyTo') for m in messages if m['author'] != 'Owner'}
    return {**meta, 'purpose': read('purpose.md'), 'plans': read('plans.md'),
            'messages': messages, 'pending': sum(m['author'] == 'Owner' and m['id'] not in answered for m in messages)}


def append_message(root: Path, area: str, message_id: str, text: str,
                   *, author: str = 'Owner', reply_to: str | None = None) -> dict:
    directory = area_dir(root, area)
    if not isinstance(message_id, str) or not KEY.fullmatch(message_id):
        raise ValueError('invalid message ID')
    if not isinstance(text, str) or not text.strip() or len(text.encode()) > 16000:
        raise ValueError('message must be 1..16000 bytes')
    if author not in {'Owner', 'Codex', 'Claude'}:
        raise ValueError('unknown author')
    directory.mkdir(parents=True, exist_ok=True)
    lock = safe(root, BASE / area / '.messages.lock')
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        state = read_area(root, area)
        messages = state['messages']
        digest = hashlib.sha256(text.encode()).hexdigest()
        existing = next((m for m in messages if m['id'] == message_id), None)
        if existing:
            if (existing['sha256'], existing['author'], existing.get('replyTo')) != (digest, author, reply_to):
                raise ValueError('message ID already used for different content')
            return existing
        if author != 'Owner':
            parent = next((m for m in messages if m['id'] == reply_to and m['author'] == 'Owner'), None)
            if not parent:
                raise ValueError('reply must reference an owner message in this area')
            if any(m.get('replyTo') == reply_to for m in messages):
                raise ValueError('owner message already answered')
        elif reply_to:
            raise ValueError('owner message cannot mark another question answered')
        row = {'id': message_id, 'author': author, 'text': text, 'sha256': digest,
               'createdAt': datetime.now(timezone.utc).isoformat(), 'replyTo': reply_to}
        if author != 'Owner':
            row['replyToHash'] = parent['sha256']
        messages.append(row)
        target = safe(root, BASE / area / 'messages.json')
        fd, temporary = tempfile.mkstemp(dir=directory, prefix='.messages-')
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump(messages, output, ensure_ascii=False, indent=2)
                output.write('\n'); output.flush(); os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return row
