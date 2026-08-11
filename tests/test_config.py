from pathlib import Path

import pytest

from vizzer.config import (Config, ConfigError, DEFAULT_STATUSES, DEFAULTS,
                           deep_merge, parse_toml_subset)

SAMPLE = '''
# comment
[project]
name = "demo"          # trailing comment
[sources.spec_tree]
enabled = true
glob = "spec/*/stories/*.md"
levels = ["capability"]
[reconcile]
staleness_days = 30
[[gates]]
item = "story:x"
reason = "decision D#1 pending"
[[status]]
name = "todo"
emoji = "🔲"
done = false
role = "ready"
description = "Ready to be completed."
next = ["done"]
[[status]]
name = "done"
emoji = "✅"
done = true
role = "done"
description = "Completed and verified."
'''


def test_parse_subset():
    d = parse_toml_subset(SAMPLE)
    assert d["project"]["name"] == "demo"
    assert d["sources"]["spec_tree"]["enabled"] is True
    assert d["sources"]["spec_tree"]["levels"] == ["capability"]
    assert d["reconcile"]["staleness_days"] == 30
    assert d["gates"] == [{"item": "story:x", "reason": "decision D#1 pending"}]
    assert [s["name"] for s in d["status"]] == ["todo", "done"]
    assert [s["role"] for s in d["status"]] == ["ready", "done"]
    assert d["status"][0]["next"] == ["done"]


def test_parse_errors_carry_line_numbers():
    with pytest.raises(ConfigError, match="line 1"):
        parse_toml_subset('key = {inline = "no"}')


def test_hash_inside_string_is_not_comment():
    assert parse_toml_subset('k = "a#b"')["k"] == "a#b"


def test_deep_merge():
    out = deep_merge({"a": {"x": 1, "y": 1}, "l": [1]}, {"a": {"y": 2}, "l": [2]})
    assert out == {"a": {"x": 1, "y": 2}, "l": [2]}


def test_config_load_defaults_when_missing(tmp_path):
    cfg = Config.load(tmp_path)
    assert cfg.get("render.output_dir") == "vizzer/views"
    assert cfg.get("nope.nope", 7) == 7
    assert {s["name"] for s in cfg.vocab["statuses"]} == {s["name"] for s in DEFAULT_STATUSES}
    assert cfg.done_statuses() == {"shipped", "verified"}
    assert cfg.status_meta("nonexistent") == {"name": "nonexistent", "emoji": "❔", "done": False}


def test_config_load_merges_and_overrides_vocab(tmp_path):
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(SAMPLE)
    cfg = Config.load(tmp_path)
    assert cfg.get("project.name") == "demo"
    assert cfg.get("reconcile.precedence") == DEFAULTS["reconcile"]["precedence"]
    assert cfg.done_statuses() == {"done"}
    assert cfg.gates() == {"story:x": "decision D#1 pending"}
    assert cfg.status_role("todo") == "ready"
    assert cfg.status_role("done") == "done"
    assert cfg.transition_allowed("todo", "done")
    assert not cfg.transition_allowed("todo", "todo")
    assert not cfg.transition_allowed("done", "todo")


def test_status_roles_default_to_backwards_compatible_lifecycle_buckets():
    """codex-sequence-2026-08-08: role data may refine, not erase, old behavior."""
    cfg = Config(data=DEFAULTS)
    assert cfg.status_role("specced") == "ready"
    assert cfg.status_role("building") == "active"
    assert cfg.status_role("bug-gap") == "active"
    assert cfg.status_role("shipped") == "done"
    assert cfg.status_role("parked") == "hold"
    assert cfg.status_role("not-in-vocab") == "unknown"
    assert cfg.get("reconcile.dependency_authority") == ""


def test_explicitly_empty_status_vocabulary_is_not_replaced_by_defaults(tmp_path):
    """codex-sequence-2026-08-08: an empty configured vocabulary fails loudly."""
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text("status = []\n")
    with pytest.raises(ConfigError, match="non-empty table array"):
        Config.load(tmp_path)


@pytest.mark.parametrize("status_config, message", [
    ('''
[[status]]
name = "building"
emoji = "🔧"
done = false
next = ["missing"]
''', "undefined next status"),
    ('''
[[status]]
name = "shipped"
emoji = "✅"
done = true
next = ["building"]
[[status]]
name = "building"
emoji = "🔧"
done = false
''', "cannot transition to unfinished"),
    ('''
[[status]]
name = "building"
emoji = "🔧"
done = false
next = "shipped"
''', "next must be an array"),
])
def test_invalid_status_transition_metadata_is_rejected(tmp_path, status_config, message):
    """codex-sequence-2026-08-08: lifecycle declarations fail before a refresh."""
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(status_config)
    with pytest.raises(ConfigError, match=message):
        Config.load(tmp_path)


@pytest.mark.parametrize("activity_config, message", [
    ('path = true\nstale_after_minutes = 30\n', "activity.path"),
    ('path = "vizzer/active-work.json"\nstale_after_minutes = 0\n', "positive integer"),
    ('path = "vizzer/active-work.json"\ntrail_rounds = 1\n', "2 through 8"),
    ('path = "vizzer/active-work.json"\ntrail_rounds = 9\n', "2 through 8"),
])
def test_invalid_activity_configuration_is_rejected(tmp_path, activity_config, message):
    """codex-sequence-2026-08-08: broken instrumentation config fails early."""
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(
        "[activity]\n" + activity_config
    )
    with pytest.raises(ConfigError, match=message):
        Config.load(tmp_path)


@pytest.mark.parametrize(("assessment_config", "message"), [
    ('enabled = "yes"\n', "assessment.enabled"),
    ('enabled = true\nsignals_path = ""\n', "signals_path"),
    ("enabled = true\nsmall_limit = -1\n", "small_limit"),
    ('enabled = true\nverification_globs = [""]\n', "verification_globs"),
])
def test_invalid_assessment_configuration_is_rejected(
    tmp_path, assessment_config, message,
):
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(
        "[assessment]\n" + assessment_config
    )
    with pytest.raises(ConfigError, match=message):
        Config.load(tmp_path)


def test_loose_document_role_is_typed_at_the_config_boundary(tmp_path):
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(
        '[sources.loose_docs]\nitem_role = "miscellaneous"\n'
    )

    with pytest.raises(ConfigError, match="item_role must be one of"):
        Config.load(tmp_path)


def test_named_area_groups_are_validated_and_exposed(tmp_path):
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(
        '[[area]]\nid = "products"\ntitle = "Products"\n'
        'facet = "product"\nvalues = ["time", "notes"]\n'
    )

    config = Config.load(tmp_path)

    assert config.areas() == [{
        "id": "products", "title": "Products", "facet": "product",
        "values": ["time", "notes"],
    }]


def test_named_area_group_rejects_empty_values(tmp_path):
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(
        '[[area]]\nid = "products"\ntitle = "Products"\n'
        'facet = "product"\nvalues = []\n'
    )

    with pytest.raises(ConfigError, match="values must be non-empty strings"):
        Config.load(tmp_path)
