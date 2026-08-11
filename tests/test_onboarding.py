import json

import pytest

from vizzer.config import Config, ConfigError
from vizzer.cli import main
from vizzer.onboarding import ConfigurationError, configure_from_answers, grill


def _story(root, relative="experience-spec/domains/editor/journeys/first-use/stories/open.md"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Story: Open a document\n\n> Status: specced\n")
    return path


def test_grill_configures_custom_experience_spec_and_handbook_without_magic_names(tmp_path):
    _story(tmp_path)
    (tmp_path / "handbook").mkdir()
    (tmp_path / "handbook" / "principles.md").write_text("# Principles\n")
    answers = iter([
        "Canvas Lab",                       # project
        "experience-spec",                  # structured folder
        "Experience specification",         # structured label
        "experience-spec/domains/*/journeys/*/stories/*.md",
        "domain, journey",                  # hierarchy
        "handbook",                         # knowledge folders
        "Team handbook",                    # knowledge label
        "y",                                # include reference nodes
        "",                                 # DAG
        "y",                                # confirm
    ])
    output = []

    result = grill(
        tmp_path,
        input_fn=lambda prompt: next(answers),
        output_fn=output.append,
    )

    assert result["project_name"] == "Canvas Lab"
    assert result["spec_tree"]["glob"].startswith("experience-spec/")
    assert result["spec_tree"]["levels"] == ["domain", "journey"]
    assert result["source_areas"] == [
        {"id": "experience-specification", "title": "Experience specification",
         "role": "delivery", "path": "experience-spec", "adapter": "spec_tree"},
        {"id": "team-handbook", "title": "Team handbook",
         "role": "knowledge", "path": "handbook", "adapter": "loose_docs"},
    ]
    assert any("1 structured work item" in line for line in output)


def test_answer_file_configuration_writes_source_areas_that_drive_adapters(tmp_path):
    _story(tmp_path, "product-thinking/areas/editor/streams/onboarding/stories/open.md")
    (tmp_path / "field-notes").mkdir()
    (tmp_path / "field-notes" / "research.md").write_text("# Research\n")
    answers = {
        "projectName": "Oddly Named Project",
        "structuredSpec": {
            "folder": "product-thinking",
            "title": "Experience intent",
            "storyGlob": "product-thinking/areas/*/streams/*/stories/*.md",
            "levels": ["area", "stream"],
            "itemKind": "story",
            "dagImport": "",
        },
        "knowledge": [
            {"folder": "field-notes", "title": "Research notebook", "includeItems": True},
        ],
    }

    text, summary = configure_from_answers(tmp_path, answers)
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(text)
    config = Config.load(tmp_path)

    assert summary["storyCount"] == 1
    assert config.get("sources.spec_tree.glob") == answers["structuredSpec"]["storyGlob"]
    assert config.get("sources.loose_docs.globs") == ["field-notes/**/*.md"]
    assert config.get("sources.loose_docs.enabled") is True
    assert config.source_areas()[0]["title"] == "Experience intent"
    assert config.source_areas()[1]["role"] == "knowledge"


@pytest.mark.parametrize("folder", ["../outside", "/tmp/outside"])
def test_configuration_rejects_source_folders_outside_project(tmp_path, folder):
    with pytest.raises(ConfigurationError, match="stay inside the project"):
        configure_from_answers(tmp_path, {
            "projectName": "Bad",
            "structuredSpec": None,
            "knowledge": [{"folder": folder, "title": "Escape"}],
        })


def test_configuration_refuses_unmatched_structured_glob_instead_of_fake_success(tmp_path):
    (tmp_path / "experience-spec").mkdir()
    with pytest.raises(ConfigurationError, match="matches no files"):
        configure_from_answers(tmp_path, {
            "projectName": "Empty",
            "structuredSpec": {
                "folder": "experience-spec",
                "title": "Experience spec",
                "storyGlob": "experience-spec/**/stories/*.md",
                "levels": ["area"],
                "itemKind": "story",
                "dagImport": "",
            },
            "knowledge": [],
        })


def test_config_rejects_unknown_source_area_role(tmp_path):
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(
        '[[source_area]]\nid = "magic"\ntitle = "Magic"\n'
        'role = "vibes"\npath = "docs"\nadapter = "loose_docs"\n'
    )
    with pytest.raises(ConfigError, match="source area.*role"):
        Config.load(tmp_path)


def test_configure_cli_accepts_reviewable_answers_file(tmp_path, capsys):
    _story(tmp_path)
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({
        "projectName": "Canvas Lab",
        "structuredSpec": {
            "folder": "experience-spec", "title": "Experience Spec",
            "storyGlob": "experience-spec/domains/*/journeys/*/stories/*.md",
            "levels": ["domain", "journey"], "itemKind": "story", "dagImport": "",
        },
        "knowledge": [],
    }))

    assert main(["configure", str(tmp_path), "--answers", str(answers), "--yes"]) == 0
    assert Config.load(tmp_path).get("project.name") == "Canvas Lab"
    assert "Experience Spec" in capsys.readouterr().out
