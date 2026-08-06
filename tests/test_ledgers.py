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


def test_indented_checkboxes_are_captured(tmp_path):
    """Real ledgers nest phase checkboxes under a `- Done:` bullet; indentation must not hide them."""
    from vizzer.adapters import ledgers as led
    from vizzer.config import Config, DEFAULTS, deep_merge

    d = tmp_path / "thoughts" / "ledgers"
    d.mkdir(parents=True)
    (d / "CONTINUITY_CLAUDE-nested.md").write_text(
        "# Continuity — nested\n\n## Goal\nShip it.\n\n## State\n"
        "- Done:\n  - [x] Phase one\n- Now: \n  - [→] Phase two\n"
        "- Remaining:\n    - [ ] Phase three\n"
    )
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"ledgers": {"enabled": True}}}))
    res = led.scan(cfg, tmp_path)
    assert [i.status for i in res.items] == ["shipped", "building", "backlog"]
    assert [i.title for i in res.items] == ["Phase one", "Phase two", "Phase three"]


HEADING_STYLE = """# Continuity — heading style

## Goal
Ship the pathfinder lane.

## Done

- Read the story and audit.
- Extracted the Boolean kernel.

## Now

The fourth blocker is resolved under the aligned control ruling. Evidence is being
committed before the required draft PR.

## Next

1. Commit and push the control evidence.
2. Open the required draft PR.

## Open Questions
- UNCONFIRMED: warm-gate amendment wording
"""


def test_heading_style_ledger_is_parsed(tmp_path):
    """Many real ledgers use `## Done` / `## Now` / `## Next` headings instead of checkboxes."""
    from vizzer.adapters import ledgers as led
    from vizzer.config import Config, DEFAULTS, deep_merge

    d = tmp_path / "thoughts" / "ledgers"
    d.mkdir(parents=True)
    (d / "CONTINUITY_CODEX-headings.md").write_text(HEADING_STYLE)
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"ledgers": {"enabled": True}}}))
    res = led.scan(cfg, tmp_path)

    [group] = res.groups
    assert group.meta["goal"] == "Ship the pathfinder lane."
    assert group.meta["open_questions"] == 1

    statuses = [i.status for i in res.items]
    assert statuses.count("shipped") == 2      # two Done bullets
    assert statuses.count("backlog") == 2      # two numbered Next entries
    assert statuses.count("building") == 1     # prose Now becomes one active phase
    now = next(i for i in res.items if i.status == "building")
    assert now.title.startswith("The fourth blocker is resolved")


def test_checkbox_style_still_wins_when_both_present(tmp_path):
    """A ledger with real checkboxes must not also emit duplicate heading-derived items."""
    from vizzer.adapters import ledgers as led
    from vizzer.config import Config, DEFAULTS, deep_merge

    d = tmp_path / "thoughts" / "ledgers"
    d.mkdir(parents=True)
    (d / "CONTINUITY_CLAUDE-both.md").write_text(
        "# Continuity — both\n\n## Goal\nG.\n\n## Done\n\n- [x] Phase one\n\n## Next\n\n- [ ] Phase two\n"
    )
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"ledgers": {"enabled": True}}}))
    res = led.scan(cfg, tmp_path)
    assert [i.title for i in res.items] == ["Phase one", "Phase two"]
