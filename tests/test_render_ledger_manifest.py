import json
from vizzer.config import Config, DEFAULTS
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all

def _graph():
    return Graph(
        groups=[Group(id="ledger:wr", kind="ledger", title="Wr",
                      meta={"goal": "Ship it.", "open_questions": 2, "path": "t/l.md"})],
        vocab=Config(data=DEFAULTS).vocab,
        items=[Item(id="phase:wr/01-a", title="Extract core", status="shipped",
                    group="ledger:wr", source={"adapter": "ledgers", "path": "t/l.md"},
                    activity={"modified": "2026-02-01T00:00:00+00:00", "last_touched": 100,
                              "created": "2026-01-01T00:00:00+00:00", "commits": 1, "mentions": 0}),
               Item(id="phase:wr/02-b", title="Port sites", status="building",
                    group="ledger:wr", source={"adapter": "ledgers", "path": "t/l.md"},
                    activity={"modified": "2026-02-01T00:00:00+00:00", "last_touched": 100,
                              "created": "2026-01-01T00:00:00+00:00", "commits": 1, "mentions": 0})])

def test_ledger_table(tmp_path):
    md = render_all(_graph(), Config(data=DEFAULTS), tmp_path, only={"ledger_table"})["ledger-table.md"]
    assert "Ship it." in md and "Port sites" in md
    assert "1/2" in md and "| 2 |" in md and "2026-02-01" in md

def test_manifest(tmp_path):
    out = render_all(_graph(), Config(data=DEFAULTS), tmp_path, only={"manifest"})["manifest.json"]
    m = json.loads(out)
    assert m["doc_count"] == 2 and m["docs"][0]["kind"] == "phase"
    assert m["docs"][0]["synopsis"] is None
    assert out.endswith("\n") and out == json.dumps(m, indent=2, ensure_ascii=False) + "\n"

def test_ledger_table_empty(tmp_path):
    g = Graph(vocab=Config(data=DEFAULTS).vocab)
    md = render_all(g, Config(data=DEFAULTS), tmp_path, only={"ledger_table"})["ledger-table.md"]
    assert "No continuity ledgers" in md
