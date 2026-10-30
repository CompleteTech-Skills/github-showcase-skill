"""Docs: the global --allow-t3 is documented in SKILL.md, the CHANGELOG and --help.

Synthetic checks only: no network, no registry. Documentation text, not behaviour.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
SIGNOFF_MARKER = "**Co-owner sign-off (`--allow-t3`).**"


def test_skill_synopsis_lists_global_flag():
    lines = SKILL.splitlines()
    start = lines.index("## Command Reference")
    synopsis = next(line for line in lines[start:] if line.startswith("python3 <skill-dir>/scripts/showcase.py"))
    assert "[--allow-t3]" in synopsis
    assert synopsis.index("[--allow-t3]") < synopsis.index("<command>")


def test_skill_documents_refusals():
    assert SIGNOFF_MARKER in SKILL
    assert "t3-signoff" in SKILL
    window = SKILL[SKILL.index(SIGNOFF_MARKER):][:1200]
    assert "excluded" in window
    assert "HOLD" in window


def test_changelog_unreleased_lists_flag():
    start = CHANGELOG.index("## Unreleased")
    end = CHANGELOG.index("\n## ", start + 1)
    assert "--allow-t3" in CHANGELOG[start:end]


def test_help_text_matches_docs():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "showcase.py"), "--help"],
        capture_output=True, encoding="utf-8",
    )
    assert result.returncode == 0
    assert "--allow-t3" in result.stdout
