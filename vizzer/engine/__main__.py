"""Run this repository's Vizzer directly from its authoritative source tree."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "src"))
os.chdir(root)

from vizzer import render_id, write_marker
from vizzer.cli import main

result = main()
if result == 0 and sys.argv[1:2] == ["refresh"]:
    write_marker(root, render_id(root))
raise SystemExit(result)
