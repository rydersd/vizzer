from pathlib import Path
from vizzer.adapters import ledgers
from vizzer.config import Config, DEFAULTS, deep_merge

FIX = Path(__file__).parent / "fixtures" / "ledger_proj"

def test_scan_ledger():
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"ledgers": {"enabled": True}}}))
    res = ledgers.scan(cfg, FIX)
    [g] = res.groups
    assert g.id == "ledger:widget-refactor" and g.kind == "ledger"
    assert g.meta["goal"] == "Ship the widget refactor with zero regressions."
    assert g.meta["open_questions"] == 1
    sts = [(i.id, i.status) for i in res.items]
    assert sts == [
        ("phase:widget-refactor/01-phase-1-extract-widget-core", "shipped"),
        ("phase:widget-refactor/02-phase-2-port-call-sites", "building"),
        ("phase:widget-refactor/03-phase-3-delete-legacy-shims", "backlog"),
    ]
    assert all(i.group == "ledger:widget-refactor" for i in res.items)
