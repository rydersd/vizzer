"""Vizzer package and deterministic render identity."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import NamedTuple


__version__ = "0.8.36"
RENDER_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
MARKER_RELPATH = Path("vizzer/RENDER_ID")
RENDER_SOURCE_SUFFIXES = frozenset({".py", ".js", ".css", ".html", ".md", ".txt"})
DERIVED_DIRECTORY_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
})
IGNORED_NAMES = frozenset({".DS_Store", "RENDER_ID"})
IGNORED_SUFFIXES = frozenset({".orig", ".rej", ".bak", ".swp", ".swo", ".log"})
_PROCESS_ID_ATTR = "_vizzer_process_render_id"
_PROCESS_ID_REASON_ATTR = "_vizzer_process_render_id_reason"


class RenderIdError(RuntimeError):
    """The running or installed package could not be identified honestly."""


class Marker(NamedTuple):
    render_id: str


def running_from_archive() -> str | None:
    return getattr(globals().get("__loader__", None), "archive", None)


def package_root() -> Path:
    """Return the source checkout or installed-project root for this process."""
    if running_from_archive():
        raise RenderIdError("an archive has no package directory to inspect")
    package = Path(__file__).resolve().parent
    if package.parent.name == "src":
        return package.parent.parent
    if package.parent.name == "engine" and package.parent.parent.name == "vizzer":
        return package.parents[2]
    raise RenderIdError(f"cannot locate a Vizzer root from {package}")


def _package_dir(root: Path) -> Path:
    root = Path(root)
    candidates = (root / "vizzer/engine/vizzer", root / "src/vizzer")
    present = [candidate for candidate in candidates if candidate.is_dir()]
    if len(present) != 1:
        raise RenderIdError(
            f"expected exactly one Vizzer package below {root}; found {len(present)}"
        )
    return present[0]


def _source_files(package: Path) -> list[Path]:
    result = []
    for path in sorted(package.rglob("*")):
        relative = path.relative_to(package)
        if path.is_symlink():
            raise RenderIdError(
                f"{relative.as_posix()} is a symlink; package identity requires real files"
            )
        if any(part in DERIVED_DIRECTORY_NAMES for part in relative.parts[:-1]):
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            raise RenderIdError(f"{relative.as_posix()} is not a regular file")
        if path.name in IGNORED_NAMES or path.suffix in IGNORED_SUFFIXES:
            continue
        if path.suffix not in RENDER_SOURCE_SUFFIXES:
            raise RenderIdError(
                f"{relative.as_posix()} is unclassified package content; classify its suffix"
            )
        result.append(path)
    if not result:
        raise RenderIdError(f"no Vizzer package source found under {package}")
    return result


def _hash_package(package: Path) -> str:
    digest = hashlib.sha256()
    for path in _source_files(package):
        relative = (Path("vizzer") / path.relative_to(package)).as_posix().encode()
        blob = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(str(len(blob)).encode("ascii"))
        digest.update(b"\0")
        digest.update(blob)
    return digest.hexdigest()[:16]


def _archive_render_id() -> str:
    try:
        value = (files(__package__) / "RENDER_ID").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError, FileNotFoundError) as exc:
        raise RenderIdError("archive has no usable bundled render identity") from exc
    if not RENDER_ID_PATTERN.fullmatch(value):
        raise RenderIdError("archive render identity is malformed")
    return value


def render_id(root: Path | None = None) -> str:
    """Hash package bytes using logical paths that survive vendoring and zipapps."""
    if root is None and running_from_archive():
        return _archive_render_id()
    base = Path(root) if root is not None else package_root()
    return _hash_package(_package_dir(base))


def process_render_id() -> str | None:
    """Fixed identity of this process; later source replacement is a refusal."""
    cached = getattr(sys, _PROCESS_ID_ATTR, None)
    if cached is None:
        try:
            cached = render_id()
        except RenderIdError as exc:
            setattr(sys, _PROCESS_ID_REASON_ATTR, str(exc))
            return None
        setattr(sys, _PROCESS_ID_ATTR, cached)
    if running_from_archive():
        return cached
    try:
        current = render_id()
    except RenderIdError as exc:
        setattr(sys, _PROCESS_ID_REASON_ATTR, str(exc))
        return None
    if current != cached:
        setattr(sys, _PROCESS_ID_REASON_ATTR, "package bytes changed after process start")
        return None
    return cached


def process_render_id_reason() -> str:
    process_render_id()
    return getattr(sys, _PROCESS_ID_REASON_ATTR, "") or "reason unrecorded"


def read_marker(root: Path) -> Marker | None:
    try:
        value = (Path(root) / MARKER_RELPATH).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return Marker(value) if RENDER_ID_PATTERN.fullmatch(value) else None


def write_marker(root: Path, value: str) -> None:
    """Atomically publish the installed identity; never expose a half-write."""
    if not RENDER_ID_PATTERN.fullmatch(value):
        raise RenderIdError("refusing to write a malformed render identity")
    destination = Path(root) / MARKER_RELPATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=str(destination.parent), prefix=f".{destination.name}.", suffix=".tmp"
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"{value}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
