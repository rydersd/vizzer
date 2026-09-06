"""Refresh this source checkout before starting its persistent local server."""
import os
from pathlib import Path
import subprocess
import sys


root = Path(__file__).resolve().parents[1]
engine = root / "vizzer" / "engine"
subprocess.run([sys.executable, str(engine), "refresh"], cwd=root, check=True)
os.chdir(root)
os.execv(sys.executable, [sys.executable, "-u", str(engine), "serve"])
