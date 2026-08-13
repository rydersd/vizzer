#!/usr/bin/env python3
"""Build the single-file distributable: python3 scripts/build_pyz.py <out.pyz>"""
import os
import shutil
import sys
import tempfile
import time
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DATE_EPOCH = 315532800


def _stage_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    shutil.copystat(source, destination)
    paths = sorted(source.rglob("*"),
                   key=lambda path: path.relative_to(source).as_posix())
    for source_path in paths:
        relative = source_path.relative_to(source)
        if (any(part == "__pycache__" or part.endswith(".egg-info")
                for part in relative.parts)
                or source_path.name == ".DS_Store"
                or source_path.suffix in {".pyc", ".pyo"}):
            continue
        destination_path = destination / relative
        if source_path.is_dir():
            destination_path.mkdir(parents=True, exist_ok=True)
            shutil.copystat(source_path, destination_path)
        elif source_path.is_file():
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)


def _create_archive_in_utc(staging: Path, out: Path) -> None:
    previous_timezone = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        zipapp.create_archive(staging, target=out,
                              interpreter="/usr/bin/env python3")
    finally:
        if previous_timezone is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous_timezone
        if hasattr(time, "tzset"):
            time.tzset()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_pyz.py <output.pyz>", file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "app"
        _stage_tree(ROOT / "src" / "vizzer", staging / "vizzer")
        _stage_tree(ROOT / "docs" / "context", staging / "vizzer" / "context")
        (staging / "__main__.py").write_text(
            "from vizzer.cli import main\nraise SystemExit(main())\n")
        epoch = int(os.environ.get("SOURCE_DATE_EPOCH",
                                   DEFAULT_SOURCE_DATE_EPOCH))
        for path in sorted(staging.rglob("*")):
            os.utime(path, (epoch, epoch))
        _create_archive_in_utc(staging, out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
