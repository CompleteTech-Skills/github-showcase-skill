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
    window = skill[skill.index(MARKER):][:2400]
    assert "excluded" in window, window
    assert "HOLD" in window, window


def test_skill_states_which_commands_do_not_enforce_owner_eligibility():
    """doctor forces R7=hold only without the flag; local meta and fingerprint never refuse (verified in code/tests)."""
    skill = _read("SKILL.md")
    para = skill[skill.index(MARKER):].split("\n\n", 1)[0]
    assert "only without `--allow-t3`" in para, para
    assert "evaluated normally" in para, para
    assert "`fingerprint`" in para and "--from-gh" in para, para
    assert "with or without the flag, with the R7" not in para


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
    # issue 23 adds --require-t3-signoff (default) and right after --allow-t3 (there is no opt-out flag); the synopsis must keep up with --help
    fragment = "[--quiet] [--allow-t3] [--require-t3-signoff] [--t3-signoff-file PATH] [--version]"
    usage_fragment = "[--allow-t3] [--require-t3-signoff] [--t3-signoff-file PATH] [--version]"
    help_usage = " ".join(result.stdout.split())
    skill = _read("SKILL.md")
    ref = skill[skill.index("## Command Reference"):]
    synopsis = next(line for line in ref.splitlines() if line.startswith("python3 <skill-dir>/scripts/showcase.py"))
    assert usage_fragment in help_usage, help_usage  # argparse prints the pair as separate options
    assert fragment in " ".join(synopsis.split()), synopsis


def test_skill_documents_require_t3_signoff_beside_allow_t3():
    """Epic 22 integration: the sign-off paragraph (issue 31) names the opt-in record check (issue 23) and its codes."""
    skill = _read("SKILL.md")
    para = skill[skill.index(MARKER):].split("\n\n", 1)[0]
    assert "--require-t3-signoff" in para, para
    for code in ("t3-signoff:missing", "t3-signoff:expired", "t3-signoff:scope"):
        assert code in para, code


def test_skill_documents_default_on_enforcement_path_and_no_opt_out():
    """Issue 23: SKILL.md, ONBOARDING.md, CHANGELOG.md and references/t3-signoff.md describe the default-on record check."""
    skill = _read("SKILL.md")
    para = skill[skill.index(MARKER):].split("\n\n", 1)[0]
    assert "on by default" in para and "decisions/t3-signoffs.yaml" in skill, para
    assert "no opt-out" in para and "--no-require-t3-signoff" not in para and "SHOWCASE_REQUIRE_T3_SIGNOFF" not in para, para
    for name in ("SKILL.md", "ONBOARDING.md", "CHANGELOG.md", "references/t3-signoff.md", "references/org.md",
                 "references/constraints.md"):
        text = _read(name)
        assert "--no-require-t3-signoff" not in text and "SHOWCASE_REQUIRE_T3_SIGNOFF" not in text, name
    assert "Earlier, opt-in form" not in _read("CHANGELOG.md")
    helptext = " ".join(subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), "--help"],
                                       capture_output=True, encoding="utf-8",
                                       env=dict(os.environ, COLUMNS="5000")).stdout.split())
    assert "valid sign-off record" in helptext and "decisions/t3-signoffs.yaml" in helptext  # --allow-t3 help names the record
    assert "default off" not in para and "is always named explicitly" not in para, para
    assert "it is never read from a config file or environment." not in para, para
    assert "decisions/t3-signoffs.yaml" in _read("ONBOARDING.md")
    changelog = _read("CHANGELOG.md")
    assert "Default-on T3 sign-off enforcement" in changelog and "decisions/t3-signoffs.yaml" in changelog
    ref = _read("references/t3-signoff.md")
    assert "DEFAULT OFF" not in ref and "decisions/t3-signoffs.yaml" in ref


def test_require_t3_signoff_is_documented_as_accepted_and_ignored():
    """The flag is a no-op, never a released compatibility surface: no doc says it is kept for compatibility."""
    for name in ("SKILL.md", "CHANGELOG.md", "references/t3-signoff.md"):
        text = _read(name)
        for line in text.splitlines():
            if "--require-t3-signoff" in line:
                assert "kept for compatibility" not in line, (name, line[:200])
        assert "accepted and ignored" in text, name
