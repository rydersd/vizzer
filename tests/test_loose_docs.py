# tests/test_loose_docs.py
from pathlib import Path
from vizzer.adapters import loose_docs
from vizzer.config import Config, DEFAULTS, deep_merge

FIX = Path(__file__).parent / "fixtures" / "docs_proj"

def test_scan_docs():
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"loose_docs": {
        "enabled": True, "globs": ["docs/**/*.md"]}}}))
    res = loose_docs.scan(cfg, FIX)
    items = {i.id: i for i in res.items}
    tok = items["doc:docs/design/tokens"]
    assert tok.status == "shipped" and tok.one_liner == "Color tokens."
    assert tok.role == "reference" and "reference" in tok.tags
    assert tok.group == "folder:docs/design"
    notes = items["doc:docs/roadmap-notes"]
    assert notes.status == "unknown" and notes.one_liner == "Where we're heading."
    assert "doc:docs/_Index_of_docs" not in items
    assert res.warnings == []
