"""Repository supply-chain guards: pinned workflow actions and code owners."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)", re.M)
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def test_every_workflow_action_is_pinned_to_a_full_sha():
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows, "no workflows found"
    for wf in workflows:
        for ref in USES.findall(wf.read_text()):
            assert PINNED.match(ref), f"{wf.name}: unpinned action {ref}"


def test_codeowners_has_catch_all_rule():
    text = (ROOT / ".github" / "CODEOWNERS").read_text()
    rules = [line.split() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    assert any(parts[0] == "*" and len(parts) > 1 for parts in rules)


def test_release_rebuilds_vendored_bundle_before_publishing():
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    test_job = text.split("\n  release:")[0]
    assert "npm run build --prefix tools/markdown-editor" in test_job
    assert "git diff --exit-code -- src/vizzer/render/constellation/third-party" in test_job
