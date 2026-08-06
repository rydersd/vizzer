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
[[status]]
name = "done"
emoji = "✅"
done = true
'''


def test_parse_subset():
    d = parse_toml_subset(SAMPLE)
    assert d["project"]["name"] == "demo"
    assert d["sources"]["spec_tree"]["enabled"] is True
    assert d["sources"]["spec_tree"]["levels"] == ["capability"]
    assert d["reconcile"]["staleness_days"] == 30
    assert d["gates"] == [{"item": "story:x", "reason": "decision D#1 pending"}]
    assert [s["name"] for s in d["status"]] == ["todo", "done"]


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
