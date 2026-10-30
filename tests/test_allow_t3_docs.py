"""Docs for the global `--allow-t3` flag: SKILL.md, CHANGELOG.md and `--help` must describe the same behaviour.

Synthetic checks only: no network, no registry, and no shared package files are touched.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "**Co-owner sign-off (`--allow-t3`).**"


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_skill_synopsis_lists_global_flag():
    skill = _read("SKILL.md")
    ref = skill[skill.index("## Command Reference"):]
    synopsis = next(line for line in ref.splitlines() if line.startswith("python3 <skill-dir>/scripts/showcase.py"))
    assert "[--allow-t3]" in synopsis, synopsis
    assert synopsis.index("[--allow-t3]") < synopsis.index("<command>"), synopsis


def test_skill_documents_refusals():
    skill = _read("SKILL.md")
    assert MARKER in skill
    assert "t3-signoff" in skill
    window = skill[skill.index(MARKER):][:1200]
    assert "excluded" in window, window
    assert "HOLD" in window, window


def test_changelog_unreleased_lists_flag():
    changelog = _read("CHANGELOG.md")
    start = changelog.index("## Unreleased")
    end = changelog.index("\n## ", start + 1)
    unreleased = changelog[start:end]
    # the entry belongs in the Added list of Unreleased, not in Fixed or a dated section
    added = unreleased[unreleased.index("### Added"):unreleased.index("### Fixed")]
    assert "--allow-t3" in added


# Regression guard for the CLI help. The help text already names the flag on the base commit, so the
# assertions below pass there too; the cross-check against SKILL.md's synopsis is the part that fails
# on a base that lacks the doc change.
def test_help_text_matches_docs():
    env = dict(os.environ, COLUMNS="200")  # keep argparse from wrapping the usage line
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "showcase.py"), "--help"],
        capture_output=True, encoding="utf-8", env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "--allow-t3" in result.stdout
    fragment = "[--quiet] [--allow-t3] [--version]"
    help_usage = " ".join(result.stdout.split())
    skill = _read("SKILL.md")
    ref = skill[skill.index("## Command Reference"):]
    synopsis = next(line for line in ref.splitlines() if line.startswith("python3 <skill-dir>/scripts/showcase.py"))
    assert fragment in help_usage, help_usage
    assert fragment in " ".join(synopsis.split()), synopsis
