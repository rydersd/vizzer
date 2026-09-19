"""The HTTP reader may serve a last-good graph during an in-place rewrite."""
from __future__ import annotations

import json
import os

import pytest

from vizzer import cli
from vizzer.model import Graph


def _graph_text(*ids: str) -> str:
    return Graph.from_dict({
        "schema": 1,
        "groups": [],
        "items": [{"id": item_id, "title": item_id, "status": "ready"}
                  for item_id in ids],
    }).dumps()


def _write(path, text: str, mtime_ns: int) -> None:
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_stale_graph_is_opt_in_and_rebuilt_for_each_read(tmp_path) -> None:
    path = tmp_path / cli.GRAPH_RELPATH
    path.parent.mkdir(parents=True)
    cli._reset_graph_read_cache()
    try:
        _write(path, _graph_text("story:old"), 1_000)
        initial = cli._read_graph(tmp_path)
        assert [item.id for item in initial.items] == ["story:old"]

        complete = _graph_text("story:old", "story:new")
        _write(path, complete[:len(complete) // 2], 2_000)
        with pytest.raises(json.JSONDecodeError):
            json.loads(path.read_text(encoding="utf-8"))

        # Non-serving callers stay strict: stale state is never silently used
        # for refresh, check, or mutation work.
        assert cli._read_graph(tmp_path) is None

        stale_one = cli._read_graph(tmp_path, allow_stale=True)
        stale_one.workstreams = {"request-local": True}
        stale_two = cli._read_graph(tmp_path, allow_stale=True)
        assert [item.id for item in stale_two.items] == ["story:old"]
        assert stale_one is not stale_two
        assert not stale_two.workstreams

        path.unlink()
        assert [item.id for item in cli._read_graph(tmp_path, allow_stale=True).items] == ["story:old"]

        _write(path, complete, 3_000)
        assert {item.id for item in cli._read_graph(tmp_path).items} == {
            "story:old", "story:new",
        }
    finally:
        cli._reset_graph_read_cache()


def test_first_read_never_invents_a_stale_graph(tmp_path) -> None:
    path = tmp_path / cli.GRAPH_RELPATH
    path.parent.mkdir(parents=True)
    cli._reset_graph_read_cache()
    try:
        _write(path, _graph_text("story:only")[:12], 1_000)
        assert cli._read_graph(tmp_path) is None
        assert cli._read_graph(tmp_path, allow_stale=True) is None
    finally:
        cli._reset_graph_read_cache()


def test_semantically_invalid_rewrite_uses_stale_only_for_read_only_callers(tmp_path) -> None:
    path = tmp_path / cli.GRAPH_RELPATH
    path.parent.mkdir(parents=True)
    cli._reset_graph_read_cache()
    try:
        _write(path, _graph_text("story:good"), 1_000)
        assert cli._read_graph(tmp_path) is not None
        _write(path, json.dumps({"schema": 1, "groups": "not a list", "items": []}), 2_000)

        assert cli._read_graph(tmp_path) is None
        recovered = cli._read_graph(tmp_path, allow_stale=True)
        assert recovered is not None
        assert [item.id for item in recovered.items] == ["story:good"]
    finally:
        cli._reset_graph_read_cache()


def test_graph_cache_is_scoped_to_its_exact_project_root(tmp_path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_path = first_root / cli.GRAPH_RELPATH
    second_path = second_root / cli.GRAPH_RELPATH
    first_path.parent.mkdir(parents=True)
    second_path.parent.mkdir(parents=True)
    cli._reset_graph_read_cache()
    try:
        _write(first_path, _graph_text("story:first"), 1_000)
        _write(second_path, _graph_text("story:second"), 1_000)
        assert [item.id for item in cli._read_graph(first_root).items] == ["story:first"]
        assert [item.id for item in cli._read_graph(second_root).items] == ["story:second"]

        first_path.unlink()
        second_path.unlink()
        assert [item.id for item in cli._read_graph(first_root, allow_stale=True).items] == ["story:first"]
        assert [item.id for item in cli._read_graph(second_root, allow_stale=True).items] == ["story:second"]
    finally:
        cli._reset_graph_read_cache()


def test_changed_during_read_never_becomes_cached_authority(tmp_path, monkeypatch) -> None:
    path = tmp_path / cli.GRAPH_RELPATH
    path.parent.mkdir(parents=True)
    cli._reset_graph_read_cache()
    try:
        _write(path, _graph_text("story:race"), 1_000)
        original = cli._graph_file_identity
        calls = 0

        def changing_identity(candidate):
            nonlocal calls
            identity = original(candidate)
            calls += 1
            if identity is None:
                return None
            return (identity[0], identity[1], identity[2] + calls, identity[3])

        monkeypatch.setattr(cli, "_graph_file_identity", changing_identity)
        assert cli._read_graph(tmp_path) is None
        assert cli._read_graph(tmp_path, allow_stale=True) is None
    finally:
        cli._reset_graph_read_cache()


def test_good_recovery_replaces_last_good_snapshot_after_a_torn_write(tmp_path) -> None:
    path = tmp_path / cli.GRAPH_RELPATH
    path.parent.mkdir(parents=True)
    cli._reset_graph_read_cache()
    try:
        _write(path, _graph_text("story:old"), 1_000)
        assert cli._read_graph(tmp_path) is not None
        _write(path, "{", 2_000)
        assert [item.id for item in cli._read_graph(tmp_path, allow_stale=True).items] == ["story:old"]
        _write(path, _graph_text("story:new"), 3_000)
        assert [item.id for item in cli._read_graph(tmp_path).items] == ["story:new"]
        path.unlink()
        assert [item.id for item in cli._read_graph(tmp_path, allow_stale=True).items] == ["story:new"]
    finally:
        cli._reset_graph_read_cache()
