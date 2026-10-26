"""Review: the family's shared validator stays generic; the CHANGELOG gate lives in validate_quality.py.

AGENTS.md: scripts/validate_package.py and tests/test_package_contract.py are byte-identical to the siblings',
package-specific checks belong in scripts/validate_quality.py. Synthetic fixtures only.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(f"review_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    spec.loader.exec_module(module)
    return module


def test_shared_validator_has_no_package_specific_checks():
    text = (ROOT / "scripts" / "validate_package.py").read_text(encoding="utf-8")
    package = load("validate_package")
    assert "CHANGELOG.md" not in package.FILES
    for local_only in ("CHANGELOG", "REPO_OWNERS"):
        assert local_only not in text, f"{local_only} belongs in validate_quality.py, not the shared validator"
    # the family validator already accepts the CompleteTech-Skills home of this package
    assert "CompleteTech-Skills/github-showcase-skill" in package.allowed_repositories("github-showcase-skill")


def write_package(root, version="1.0.0", changelog="# Changelog\n\n## 1.0.0 — 2026-01-01\n"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(f"---\nname: northwind-demo\ndescription: demo\nversion: {version}\n---\n# Demo\n",
                                   encoding="utf-8")
    if changelog is not None:
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return root


def test_quality_changelog_gate_accepts_matching_entry(tmp_path):
    quality = load("validate_quality")
    quality.gate_changelog(write_package(tmp_path / "ok"))
    quality.gate_changelog(write_package(tmp_path / "bracketed", changelog="# Changelog\n\n## [1.0.0]\n"))


@pytest.mark.parametrize("changelog", [None, "# Changelog\n\n## 0.9.0\n", "# Changelog\n\n## 1.0.0-rc1\n",
                                       "# Changelog\n\n### 1.0.0\n", "# Changelog\n\n## 1.0.01\n"])
def test_quality_changelog_gate_rejects_missing_file_or_entry(tmp_path, changelog):
    quality = load("validate_quality")
    with pytest.raises(RuntimeError, match="CHANGELOG.md"):
        quality.gate_changelog(write_package(tmp_path / "pkg", changelog=changelog))


def test_quality_main_runs_the_changelog_gate():
    text = (ROOT / "scripts" / "validate_quality.py").read_text(encoding="utf-8")
    main = text[text.index("def main("):]
    assert "gate_changelog()" in main


def test_this_checkout_has_its_changelog_entry():
    load("validate_quality").gate_changelog(ROOT)
