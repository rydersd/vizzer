from pathlib import Path
from vizzer.adapters import todos
from vizzer.config import Config, DEFAULTS, deep_merge

FIX = Path(__file__).parent / "fixtures" / "todo_proj"

def test_scan_todos():
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"todos": {"enabled": True}}}))
    res = todos.scan(cfg, FIX)
    assert [g.id for g in res.groups] == ["todo-file:TODO.md"]
    sts = [(i.id, i.status) for i in res.items]
    assert sts == [("todo:todo/01-set-up-ci", "shipped"),
                   ("todo:todo/02-write-install-docs", "backlog")]
