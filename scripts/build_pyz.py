#!/usr/bin/env python3
"""Build the single-file distributable: python3 scripts/build_pyz.py <out.pyz>"""
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_pyz.py <output.pyz>", file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "app"
        shutil.copytree(ROOT / "src" / "vizzer", staging / "vizzer",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (staging / "__main__.py").write_text(
            "from vizzer.cli import main\nraise SystemExit(main())\n")
        zipapp.create_archive(staging, target=out, interpreter="/usr/bin/env python3")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
