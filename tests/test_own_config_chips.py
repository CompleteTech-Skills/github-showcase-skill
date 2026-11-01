"""Configured chips for this repository's own showcase (.github/showcase.yml).

Fixtures are synthetic (tmp_path repositories and in-memory metadata); no network is used and no subprocess is run.
The real .github/showcase.yml is read as plain YAML and checked against the repo-config JSON schema.
"""
import json

import pytest
import yaml

from conftest import ROOT
from ctshowcase import chips

EXPECTED_CHIPS = {"key": ["Claude + Codex"], "attrs": ["Python", "Offline"]}
SKILL_TOPICS = ["claude-skill", "codex-skill", "agent-skills"]


def _skill_repo(tmp_path, override=True):
    (tmp_path / "SKILL.md").write_text("---\nname: x\n---\n")
    if override:
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "showcase.yml").write_text(
            "chips:\n"
            "  key: [\"Claude + Codex\"]\n"
            "  attrs: [\"Python\", \"Offline\"]\n",
            encoding="utf-8",
        )
    return tmp_path


def test_own_config_declares_chips():
    data = yaml.safe_load((ROOT / ".github" / "showcase.yml").read_text(encoding="utf-8"))
    assert data["chips"] == EXPECTED_CHIPS
    assert isinstance(data["subtitle"], str) and data["subtitle"].strip()

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "references" / "repo-config.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)


def test_override_key_and_attrs_no_runtime_duplicate(make_ctx, tmp_path):
    repo = _skill_repo(tmp_path, override=True)
    ctx = make_ctx(repo_dir=repo, owner="CompleteTech-Skills", repo="x-skill", topics=SKILL_TOPICS,
                   language="Python", license="MIT")

    assert chips.key_chips(ctx) == [("Claude + Codex", "override")]
    assert chips.attr_chips(ctx) == [("Python", "override"), ("Offline", "override")]
    assert chips.derive(ctx) == ([("Claude + Codex", "override")], [("Python", "override"), ("Offline", "override")])

    attr_texts = [text for text, _ in chips.attr_chips(ctx)]
    assert not any("Claude" in text or "Codex" in text for text in attr_texts)
    key_texts = [text for text, _ in chips.key_chips(ctx)]
    assert not set(key_texts) & set(attr_texts)


def test_without_override_topic_runtime_chip_is_derived_in_attrs(make_ctx, tmp_path):
    repo = _skill_repo(tmp_path, override=False)
    ctx = make_ctx(repo_dir=repo, owner="CompleteTech-Skills", repo="x-skill", topics=SKILL_TOPICS,
                   language="Python", license="MIT")
    assert ("Claude · Codex", "topics") in chips.attr_chips(ctx)
