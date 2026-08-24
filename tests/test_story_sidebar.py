from pathlib import Path

from vizzer.model import Item
from vizzer.story_sidebar import (
    canonical_story_sections, extract_story_sidebar_sections, object_detail_provider,
    object_detail_providers,
)


def test_authored_sections_have_legacy_and_canonical_shapes():
    markdown = """# Story

## Review steps
1. Open the page.

## Acceptance criteria
- It reports ready.

## Definition of done
- The owner repeated the check.
"""
    legacy = extract_story_sidebar_sections(markdown)
    assert legacy["review_steps"] == "1. Open the page."
    assert canonical_story_sections(markdown) == {
        "reviewSteps": "1. Open the page.",
        "acceptance": "- It reports ready.",
        "definitionOfDone": "- The owner repeated the check.",
    }


def test_provider_enriches_detail_without_trusting_absolute_or_escaping_paths(tmp_path):
    story = tmp_path / "stories/check.md"
    story.parent.mkdir()
    story.write_text("## Owner test list\n- Repeat the check.\n", encoding="utf-8")
    item = Item(
        id="story:check", title="Check", source={"adapter": "docs", "path": "stories/check.md"}
    )
    detail = object_detail_provider(tmp_path)(item)
    assert detail["sections"]["reviewSteps"] == "- Repeat the check."

    absolute = Item(
        id="story:absolute", title="Absolute",
        source={"adapter": "docs", "path": story.as_posix()},
    )
    assert object_detail_provider(tmp_path)(absolute)["sections"] == {}

    escaping = Item(
        id="story:escape", title="Escape",
        source={"adapter": "docs", "path": "../outside.md"},
    )
    assert object_detail_provider(tmp_path)(escaping)["sections"] == {}


def test_gherkin_is_acceptance_fallback():
    assert canonical_story_sections("```gherkin\nGiven a ready service\n```") == {
        "acceptance": "Given a ready service"
    }


def test_detail_identity_changes_with_authored_sections(tmp_path):
    story = tmp_path / "stories/check.md"
    story.parent.mkdir()
    story.write_text("## Definition of done\n- First check.\n", encoding="utf-8")
    item = Item(
        id="story:check", title="Check",
        source={"adapter": "docs", "path": "stories/check.md"},
    )
    _provide, identify = object_detail_providers(tmp_path)
    before = identify(item)

    story.write_text("## Definition of done\n- Revised check.\n", encoding="utf-8")
    _provide, identify = object_detail_providers(tmp_path)
    assert identify(item) != before
