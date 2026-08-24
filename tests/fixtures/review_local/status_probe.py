"""Trusted host fixture for a project-local command adapter."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(source: str, destination: str) -> int:
    state = json.loads(Path(source).read_text(encoding="utf-8"))
    ready = state.get("state") == "ready" and bool(state.get("checks"))
    report = {
        "schema": 1,
        "probe": "local-service-status",
        "outcome": "pass" if ready else "fail",
        "observedState": state.get("state"),
        "checkCount": len(state.get("checks", [])),
    }
    Path(destination).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
