"""Owner-authored story revisions queued for review, without replacing source."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import os
import tempfile


class StoryEditConflict(ValueError):
    pass


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def edit_path(root, story_id):
    folder = root / 'vizzer/story-edits'
    if folder.is_symlink() or not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError('Story edits directory must stay inside the project')
    path = folder / (digest(story_id) + '.json')
    if path.is_symlink():
        raise ValueError('Story edit ledger must not be a symlink')
    return path


def read_edit(root, story_id, source):
    if not story_id.startswith('story:') or source.suffix != '.md':
        raise ValueError('Only Markdown stories can be edited')
    if not source.resolve().is_relative_to(root.resolve()):
        raise ValueError('Story source must stay inside the project')
    path = edit_path(root, story_id)
    ledger = json.loads(path.read_text()) if path.exists() else {'schema': 1, 'storyId': story_id, 'revision': 0, 'revisions': []}
    if ledger.get('storyId') != story_id:
        raise ValueError('Story edit ledger identity mismatch')
    current = source.read_text(encoding='utf-8')
    latest = ledger['revisions'][-1] if ledger['revisions'] else None
    return dict(storyId=story_id, sourcePath=str(source.resolve().relative_to(root.resolve())), source=current,
                sourceHash=digest(current), revision=ledger['revision'], latest=latest)


def save_edit(root, story_id, source, body):
    if set(body) != {'storyId', 'expectedSourceHash', 'expectedRevision', 'text'}:
        raise ValueError('Expected storyId, expectedSourceHash, expectedRevision and text')
    state = read_edit(root, story_id, source)
    if isinstance(body['expectedRevision'], bool) or not isinstance(body['expectedRevision'], int):
        raise ValueError('expectedRevision must be an integer')
    if body['expectedSourceHash'] != state['sourceHash'] or body['expectedRevision'] != state['revision']:
        raise StoryEditConflict('The story or pending revision changed. Keep your draft and reopen to compare before saving.')
    text = body['text']
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 200000:
        raise ValueError('Story must contain 1–200000 UTF-8 bytes')
    previous = state['latest']['edited'] if state['latest'] else state['source']
    if text == previous:
        raise ValueError('No changes to save')
    path = edit_path(root, story_id)
    ledger = json.loads(path.read_text()) if path.exists() else {'schema': 1, 'storyId': story_id, 'revision': 0, 'revisions': []}
    entry = dict(revision=state['revision'] + 1, status='pending-review',
                 submittedAt=datetime.now(timezone.utc).isoformat(), submittedBy='owner',
                 sourcePath=state['sourcePath'], baseHash=state['sourceHash'], editedHash=digest(text),
                 original=state['source'], edited=text,
                 diff=''.join(difflib.unified_diff(state['source'].splitlines(True), text.splitlines(True),
                                                fromfile=state['sourcePath'], tofile=state['sourcePath']+' (owner revision)')))
    ledger['revision'] = entry['revision']; ledger['revisions'].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.story-edit-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(ledger, stream, ensure_ascii=False, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return dict(revision=entry['revision'], status='pending-review', path=str(path.relative_to(root)))
