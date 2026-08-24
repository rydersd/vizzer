import json
import sqlite3
import zlib

import pytest

from vizzer.config import Config
from vizzer.cli import _render_graph
from vizzer.developer_graph import index_from_work_graph
from vizzer.developer_query import DeveloperGraphIndex, DeveloperQueryError
from vizzer.developer_store import (
    STORE_RELPATH,
    DeveloperStoreError,
    StoredDeveloperGraphIndex,
    prepare_developer_store,
)
from vizzer.model import Graph, Group, Item
from vizzer.story_sidebar import object_detail_providers


def _config():
    return Config(data={
        "project": {"name": "Persisted query fixture"},
        "developer_flow": {
            "enabled": True,
            "materialization_cap": 100,
            "direction": "RIGHT",
        },
    })


def _graph():
    return Graph(
        groups=[
            Group(id="capability:alpha", kind="capability", title="Alpha"),
            Group(id="epic:alpha/core", kind="epic", title="Core",
                  parent="capability:alpha"),
            Group(id="epic:alpha/empty", kind="epic", title="Empty",
                  parent="capability:alpha"),
            Group(id="capability:external", kind="capability", title="External"),
        ],
        items=[
            Item(
                id=f"story:alpha-{index}",
                title=f"Alpha {index}",
                status="building" if index % 7 == 0 else "ready",
                group="epic:alpha/core",
                deps=(["service:external"] if index == 0 else
                      [f"story:alpha-{index - 1}"] if index < 4 else []),
                source=(
                    {"adapter": "spec_tree", "path": "stories/alpha-0.md"}
                    if index == 0 else {}
                ),
            )
            for index in range(101)
        ] + [
            Item(id="service:external", title="External service", status="shipped",
                 group="capability:external"),
        ],
    )


def _write_graph(root, graph):
    path = root / "vizzer/vizzer-graph.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph.dumps(), encoding="utf-8")


def _indexes(tmp_path):
    graph, cfg = _graph(), _config()
    story = tmp_path / "stories/alpha-0.md"
    story.parent.mkdir()
    story.write_text(
        "# Story: Alpha 0\n\n## Definition of done\n\n- First proof.\n",
        encoding="utf-8",
    )
    _write_graph(tmp_path, graph)
    detail_provider, identity_provider = object_detail_providers(tmp_path)
    projected, resolver = index_from_work_graph(
        graph, cfg, detail_provider=detail_provider,
        detail_identity_provider=identity_provider,
    )
    oracle = DeveloperGraphIndex(
        projected, assume_validated=True, detail_provider=resolver,
    )
    path = prepare_developer_store(graph, cfg, tmp_path)
    assert path == tmp_path / STORE_RELPATH
    stored = StoredDeveloperGraphIndex.open_current(tmp_path, cfg)
    assert stored is not None
    return graph, cfg, oracle, stored


@pytest.mark.parametrize("query_case", [
    {"schema": 1, "scope": {"kind": "overview"}, "page": {"limit": 1}},
    {"schema": 1, "scope": {"kind": "group", "id": "capability:alpha"},
     "page": {"limit": 5}},
    {"schema": 1, "scope": {"kind": "group", "id": "capability:alpha"},
     "filters": {"statuses": ["building"], "query": "alpha"},
     "page": {"limit": 9}},
    {"schema": 1, "scope": {"kind": "object", "id": "story:alpha-1"}},
    {"schema": 1, "scope": {"kind": "object", "id": "story:alpha-1"},
     "filters": {"statuses": ["ready"], "query": "alpha"},
     "page": {"limit": 5}},
    {"schema": 1, "scope": {"kind": "object", "id": "story:alpha-1"},
     "filters": {"statuses": ["building"]}, "page": {"limit": 5}},
    {"schema": 1, "scope": {"kind": "object", "id": "story:alpha-0"},
     "filters": {"relationKinds": ["depends-on"]}},
])
def test_persisted_queries_match_the_in_memory_oracle(tmp_path, query_case):
    _graph_value, _cfg, oracle, stored = _indexes(tmp_path)
    try:
        assert stored.query(query_case) == oracle.query(query_case)
    finally:
        stored.close()


def test_persisted_cursor_pagination_matches_oracle(tmp_path):
    _graph_value, _cfg, oracle, stored = _indexes(tmp_path)
    request = {
        "schema": 1,
        "scope": {"kind": "group", "id": "capability:alpha"},
        "page": {"limit": 2},
    }
    try:
        expected_first = oracle.query(request)
        actual_first = stored.query(request)
        assert actual_first == expected_first
        request["page"]["cursor"] = actual_first["page"]["nextCursor"]
        assert stored.query(request) == oracle.query(request)
    finally:
        stored.close()


def test_store_is_read_only_and_stale_graph_bytes_are_never_opened(tmp_path):
    _graph_value, cfg, _oracle, stored = _indexes(tmp_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            stored._connection.execute("DELETE FROM objects")
    finally:
        stored.close()

    graph_path = tmp_path / "vizzer/vizzer-graph.json"
    graph_path.write_text(graph_path.read_text() + "\n", encoding="utf-8")
    assert StoredDeveloperGraphIndex.open_current(tmp_path, cfg) is None


def test_authored_detail_rebuild_changes_snapshot_and_rejects_old_cursor(tmp_path):
    graph, cfg, _oracle, before = _indexes(tmp_path)
    request = {
        "schema": 1,
        "scope": {"kind": "group", "id": "capability:alpha"},
        "page": {"limit": 2},
    }
    old_cursor = before.query(request)["page"]["nextCursor"]
    before_snapshot = before.fingerprint

    (tmp_path / "stories/alpha-0.md").write_text(
        "# Story: Alpha 0\n\n## Definition of done\n\n- Revised proof.\n",
        encoding="utf-8",
    )
    prepare_developer_store(graph, cfg, tmp_path)
    after = StoredDeveloperGraphIndex.open_current(tmp_path, cfg)
    assert after is not None
    try:
        assert after.fingerprint != before_snapshot
        request["page"]["cursor"] = old_cursor
        with pytest.raises(DeveloperQueryError, match="stale"):
            after.query(request)
    finally:
        before.close()
        after.close()


def test_corrupt_store_falls_back_instead_of_serving_unvalidated_bytes(tmp_path):
    _graph_value, cfg, _oracle, stored = _indexes(tmp_path)
    path = stored.path
    stored.close()
    path.write_bytes(b"not sqlite")
    assert StoredDeveloperGraphIndex.open_current(tmp_path, cfg) is None


def test_tampered_row_identity_is_rejected_at_the_query_boundary(tmp_path):
    _graph_value, cfg, _oracle, stored = _indexes(tmp_path)
    path = stored.path
    stored.close()
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT data FROM objects WHERE id='story:alpha-0'"
        ).fetchone()
        record = json.loads(zlib.decompress(row[0]))
        record["id"] = "story:cross-wired"
        connection.execute(
            "UPDATE objects SET data=? WHERE id='story:alpha-0'",
            (json.dumps(record, sort_keys=True, separators=(",", ":")),),
        )
        connection.commit()
    finally:
        connection.close()
    tampered = StoredDeveloperGraphIndex.open_current(tmp_path, cfg)
    assert tampered is not None
    try:
        with pytest.raises(DeveloperStoreError, match="object id does not match"):
            tampered.query({
                "schema": 1,
                "scope": {"kind": "object", "id": "story:alpha-0"},
            })
    finally:
        tampered.close()


def test_failed_atomic_replacement_preserves_the_previous_store(tmp_path, monkeypatch):
    graph, cfg, _oracle, stored = _indexes(tmp_path)
    path = stored.path
    stored.close()
    before = path.read_bytes()
    monkeypatch.setattr(
        "vizzer.developer_store.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replacement stopped")),
    )
    with pytest.raises(OSError, match="replacement stopped"):
        prepare_developer_store(graph, cfg, tmp_path)
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".developer-flow-*.sqlite3"))


def test_projection_configuration_change_invalidates_the_store(tmp_path):
    _graph_value, _cfg, _oracle, stored = _indexes(tmp_path)
    stored.close()
    changed = Config(data={
        "project": {"name": "A renamed projection"},
        "developer_flow": {
            "enabled": True, "materialization_cap": 100, "direction": "RIGHT",
        },
    })
    assert StoredDeveloperGraphIndex.open_current(tmp_path, changed) is None


def test_programmatic_group_cycle_fails_instead_of_hanging_the_builder(tmp_path):
    graph, cfg = _graph(), _config()
    graph.groups[0].parent = "epic:alpha/core"
    with pytest.raises(DeveloperStoreError, match="group cycle"):
        prepare_developer_store(graph, cfg, tmp_path)
    assert not list((tmp_path / ".vizzer/cache").glob(".developer-flow-*"))


def test_render_prepares_the_ignored_store_for_large_served_graphs(tmp_path):
    graph, cfg = _graph(), _config()
    _write_graph(tmp_path, graph)
    assert _render_graph(
        cfg, graph, tmp_path, "developer_flow", "render"
    ) == 0
    assert (tmp_path / "vizzer/views/developer-flow.html").is_file()
    stored = StoredDeveloperGraphIndex.open_current(tmp_path, cfg)
    assert stored is not None
    stored.close()


def test_cache_failure_does_not_block_the_authoritative_static_render(
    tmp_path, monkeypatch, capsys,
):
    graph, cfg = _graph(), _config()
    _write_graph(tmp_path, graph)
    monkeypatch.setattr(
        "vizzer.cli.prepare_developer_store",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk busy")),
    )
    assert _render_graph(
        cfg, graph, tmp_path, "developer_flow", "render"
    ) == 0
    assert (
        "warning: developer query cache unavailable: disk busy"
        in capsys.readouterr().out
    )
    assert (tmp_path / "vizzer/views/developer-flow.html").is_file()
