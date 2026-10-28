"""Regenerate the README GIFs from the fictional Sample Notes demo project.

    python3 scripts/readme_media/record.py [scene ...]

Builds the demo project in a temporary directory, installs Vizzer into it from
this checkout, enables workstreams and reviews, serves it on loopback, records
each scene in headless Chrome (scripts/readme_media/record.mjs), and encodes
docs/media/<scene>.gif with ffmpeg. Requires python3, Node 22+, Chrome, ffmpeg.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MEDIA = REPO / "docs" / "media"
SCENES = ["constellation", "questions", "views", "workstreams", "reviews", "developer_flow"]
GIF_WIDTH = 960

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
import demo_project  # noqa: E402
from vizzer.review_contract import plan_fingerprint  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Demo", "GIT_AUTHOR_EMAIL": "demo@example.com",
           "GIT_COMMITTER_NAME": "Demo", "GIT_COMMITTER_EMAIL": "demo@example.com"}


def run(*args: str, cwd: Path | None = None, env: dict | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, env={**os.environ, **(env or {})},
                            capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"{' '.join(args)} failed:\n{result.stdout}{result.stderr}")
    return result.stdout


def engine(root: Path, *args: str) -> str:
    return run(sys.executable, "vizzer/engine", *args, "--root", str(root), cwd=root)


def build(root: Path) -> None:
    demo_project.write(root)
    run("git", "init", "-q", cwd=root)
    run("git", "add", "-A", cwd=root)
    run("git", "commit", "-qm", "Sample Notes", cwd=root, env=GIT_ENV)
    run(sys.executable, "-m", "vizzer", "install", str(root),
        env={"PYTHONPATH": str(REPO / "src")})
    demo_project.configure(root)

    state = root / ".demo-workstreams.json"
    state.write_text(json.dumps(demo_project.WORKSTREAMS), encoding="utf-8")
    engine(root, "workstreams", "apply", "--file", str(state), "--expected-revision", "0",
           "--actor", "Product owner", "--rationale", "Split the release into parallel lanes")
    for revision, (sid, actor, model, role, stream, branch) in enumerate(demo_project.SESSIONS):
        engine(root, "sessions", "start", "--id", sid, "--actor", actor, "--model", model,
               "--role", role, "--workstream", stream, "--branch", branch,
               "--worktree", f"/work/{sid}", "--expected-revision", str(revision),
               "--lease-minutes", "240")

    reviews = root / "vizzer" / "reviews"
    (reviews / "plans").mkdir(parents=True, exist_ok=True)
    (reviews / "evidence").mkdir(parents=True, exist_ok=True)
    plan = demo_project.review_plan(root)
    (reviews / "plans" / "search-filters.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    (reviews / "adapters.json").write_text(json.dumps(demo_project.ADAPTERS), encoding="utf-8")
    evidence = reviews / "evidence" / "filtered.png"
    run("node", str(HERE / "record.mjs"), "evidence", str(evidence))
    png = evidence.read_bytes()
    event = {
        "eventId": "agent-run-1", "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "actor": {"kind": "agent", "id": "claude-review"}, "planId": plan["id"],
        "rowId": "filter-by-tag", "planFingerprint": plan_fingerprint(plan),
        "stepResults": [{"stepId": "apply-tag", "outcome": "pass"}],
        "evidence": [{
            "requirementId": "filtered", "path": "vizzer/reviews/evidence/filtered.png",
            "sha256": hashlib.sha256(png).hexdigest(), "bytes": len(png), "mediaType": "image/png",
            "width": 640, "height": 400,
            "caption": "Search for 'roadmap' narrowed to the #planning tag.",
            "capture": {"adapter": "browser", "observedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "redaction": "not-needed"},
        }],
        "verdict": "pass",
    }
    event_file = root / ".demo-review-run.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")
    engine(root, "review", "record", "--plan", plan["id"], "--file", str(event_file),
           "--expected-revision", "0")
    engine(root, "refresh")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def encode(frames: Path, gif: Path) -> None:
    graph = (f"fps=12,scale={GIF_WIDTH}:-1:flags=lanczos,split[a][b];"
             "[a]palettegen=max_colors=128:stats_mode=diff[p];"
             "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    run("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
        "-i", str(frames / "frames.ffconcat"), "-vf", graph, str(gif))


def main(scenes: list[str]) -> None:
    for tool in ("node", "ffmpeg"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is required")
    MEDIA.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vizzer-readme-") as tmp:
        root, frames = Path(tmp) / "sample-notes", Path(tmp) / "frames"
        root.mkdir()
        build(root)
        port = free_port()
        server = subprocess.Popen([sys.executable, "vizzer/engine", "serve", "--port", str(port)],
                                  cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(2)
            run("node", str(HERE / "record.mjs"), f"http://127.0.0.1:{port}", str(frames), *scenes)
        finally:
            server.terminate()
            server.wait(timeout=10)
        for scene in scenes:
            gif = MEDIA / f"{scene.replace('_', '-')}.gif"
            encode(frames / scene, gif)
            print(f"{gif.relative_to(REPO)}: {gif.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1:] or SCENES)
