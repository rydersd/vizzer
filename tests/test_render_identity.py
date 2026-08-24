import sys

import pytest

import vizzer


def _package(root, installed=False):
    package = (
        root / "vizzer/engine/vizzer" if installed else root / "src/vizzer"
    )
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "view.js").write_text("const value = 1;\n", encoding="utf-8")
    return package


def test_render_identity_survives_source_to_vendored_layout_and_line_endings(tmp_path):
    source_root = tmp_path / "source"
    installed_root = tmp_path / "installed"
    _package(source_root)
    installed = _package(installed_root, installed=True)
    (installed / "view.js").write_bytes(b"const value = 1;\r\n")

    assert vizzer.render_id(source_root) == vizzer.render_id(installed_root)


def test_render_identity_moves_with_content_but_not_ignored_debris(tmp_path):
    package = _package(tmp_path)
    before = vizzer.render_id(tmp_path)
    (package / ".DS_Store").write_bytes(b"noise")
    assert vizzer.render_id(tmp_path) == before
    (package / "view.js").write_text("const value = 2;\n", encoding="utf-8")
    assert vizzer.render_id(tmp_path) != before


def test_render_identity_fails_closed_on_unclassified_or_symlinked_content(tmp_path):
    package = _package(tmp_path)
    (package / "runtime.wasm").write_bytes(b"runtime")
    with pytest.raises(vizzer.RenderIdError, match="unclassified"):
        vizzer.render_id(tmp_path)
    (package / "runtime.wasm").unlink()
    (package / "linked.py").symlink_to(package / "__init__.py")
    with pytest.raises(vizzer.RenderIdError, match="symlink"):
        vizzer.render_id(tmp_path)


def test_marker_roundtrips_and_rejects_malformed_identity(tmp_path):
    identity = "0123456789abcdef"
    vizzer.write_marker(tmp_path, identity)
    assert vizzer.read_marker(tmp_path).render_id == identity
    (tmp_path / vizzer.MARKER_RELPATH).write_text("not-an-id\n", encoding="utf-8")
    assert vizzer.read_marker(tmp_path) is None
    with pytest.raises(vizzer.RenderIdError, match="malformed"):
        vizzer.write_marker(tmp_path, "nope")


def test_process_identity_refuses_to_adopt_replacement_package(tmp_path, monkeypatch):
    package = _package(tmp_path)
    previous_id = getattr(sys, vizzer._PROCESS_ID_ATTR, None)
    previous_reason = getattr(sys, vizzer._PROCESS_ID_REASON_ATTR, None)
    monkeypatch.setattr(vizzer, "package_root", lambda: tmp_path)
    monkeypatch.delattr(sys, vizzer._PROCESS_ID_ATTR, raising=False)
    monkeypatch.delattr(sys, vizzer._PROCESS_ID_REASON_ATTR, raising=False)
    try:
        captured = vizzer.process_render_id()
        assert captured == vizzer.render_id(tmp_path)
        (package / "view.js").write_text("const value = 2;\n", encoding="utf-8")
        assert vizzer.process_render_id() is None
        assert "changed after process start" in vizzer.process_render_id_reason()
    finally:
        if previous_id is not None:
            setattr(sys, vizzer._PROCESS_ID_ATTR, previous_id)
        if previous_reason is not None:
            setattr(sys, vizzer._PROCESS_ID_REASON_ATTR, previous_reason)
