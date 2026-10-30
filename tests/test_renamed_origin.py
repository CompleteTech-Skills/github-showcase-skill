"""A checkout whose `origin` still names the old repository name is refused by default (usage, exit 2); a case-only
difference in the same name is accepted. Synthetic names only: example-org, old-name, new-name.

Two groups of tests live here:

- The first two tests (`test_stale_origin_is_rejected_by_default`, `test_same_name_other_case_is_accepted`) are
  regression guards for the #117 default behaviour. They pass on the base commit 2be04ac (verified by exporting that
  commit to a scratch directory and running this file there: 2 passed), so they need no source change. Do not mark
  them xfail: the behaviour they pin is correct. Mutation evidence (scratch copy of 2be04ac, not committed): disabling
  the origin check or making `_same_slug` always true fails the first; making `_same_slug` case-sensitive fails the
  second.
- The `--assume-repo` tests (E6.3.2) cover the explicit override in `scripts/showcase.py` (`_parse_slug`,
  `_check_assume`, `_apply_assume`, `repo_dir`). They depend on that change and fail on the base commit 2be04ac, as
  intended. The override is off by default; without the flag the guards above still apply.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]


def _fixture(tmp_path):
    co = tmp_path / "co"
    co.mkdir()
    subprocess.run(["git", "init", "-q", str(co)], check=True)
    subprocess.run(["git", "-C", str(co), "remote", "add", "origin", "https://github.com/example-org/old-name.git"],
                   check=True)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({
        "owner": "example-org",
        "repo": "new-name",
        "visibility": "public",
        "description": "A synthetic example repository for tests.",
        "default_branch": "main",
    }), encoding="utf-8")
    return meta, co


def _describe(meta, co):
    return subprocess.run([*SHOWCASE, "--meta", str(meta), "--repo-dir", str(co), "describe"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")


def _need_git():
    if shutil.which("git") is None:
        pytest.skip("git is not on PATH")


def test_stale_origin_is_rejected_by_default(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _describe(meta, co)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "example-org/new-name" in r.stdout
    assert "example-org/old-name" in r.stdout
    assert '"result": "usage"' in r.stdout


def test_same_name_other_case_is_accepted(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    subprocess.run(["git", "-C", str(co), "remote", "set-url", "origin",
                    "https://github.com/Example-Org/NEW-NAME.git"], check=True)
    r = _describe(meta, co)
    assert r.returncode != 2, (r.stdout, r.stderr)


# --- E6.3.2: explicit override --assume-repo (off by default; logged; never edits the remote) ----------------------

OLD_URL = "https://github.com/example-org/old-name.git"


def _run(args, cwd=ROOT):
    return subprocess.run([*SHOWCASE, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def test_assume_repo_accepts_stale_origin(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "describe"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert "origin-renamed:example-org/old-name->example-org/new-name" in r.stdout, r.stdout


def test_assume_repo_without_meta_uses_new_slug(tmp_path):
    _need_git()
    _meta, co = _fixture(tmp_path)
    r = _run(["--repo-dir", str(co), "--assume-repo", "example-org/new-name", "describe"])
    assert '"repo": "new-name"' in r.stdout, (r.stdout, r.stderr)


def test_assume_repo_for_other_repo_is_rejected(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/something-else", "describe"])
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert '"result": "usage"' in r.stdout, r.stdout


def test_assume_repo_bad_format_is_usage_error(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "nonsense", "describe"])
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "must be OWNER/REPO" in r.stdout, (r.stdout, r.stderr)


def test_rejection_message_names_the_fix(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _describe(meta, co)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "git remote set-url origin" in r.stdout, r.stdout
    assert "--assume-repo example-org/new-name" in r.stdout, r.stdout


def test_remote_never_modified(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "describe"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    got = subprocess.run(["git", "-C", str(co), "remote", "get-url", "origin"], capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout.strip()
    assert got == OLD_URL


def test_assume_repo_other_repo_is_refused_without_checkout(tmp_path):
    """--no-repo-dir skips the checkout check, so the --meta comparison must still run (review B1): an override naming
    another repository than the metadata is refused before the metadata is relabelled."""
    meta, _co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--no-repo-dir", "--assume-repo", "example-org/something-else", "describe"])
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert '"result": "usage"' in r.stdout, r.stdout
    assert "something-else" in r.stdout, r.stdout


def test_assume_repo_format_is_checked_for_every_command(tmp_path):
    """Validation runs before any command, so a command that never reaches repo_dir() (fonts) still refuses a malformed
    value (review B2). An empty value is malformed too, not 'no override'."""
    r = _run(["--assume-repo", "nonsense", "fonts", "--check"])
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "must be OWNER/REPO" in r.stdout, (r.stdout, r.stderr)
    r = _run(["--assume-repo", "", "fonts", "--check"])
    assert r.returncode == 2, (r.stdout, r.stderr)


def test_assume_repo_is_not_silently_ignored_for_meta_only_commands(tmp_path):
    """A malformed override is refused for local metadata commands too, not only for checkout commands (review B2)."""
    meta, _co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--no-repo-dir", "--assume-repo", "nonsense", "meta"])
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "must be OWNER/REPO" in r.stdout, (r.stdout, r.stderr)


def test_content_links_ignore_assume_repo_documented_limitation(tmp_path):
    """`content links` takes its slug from --meta or the checkout's origin (content._owner_repo), not from the
    override. This pins the limitation that SKILL.md states (review A1): the run reports the origin slug and logs no
    origin-renamed entry. Operators who need the new slug pass --meta with it."""
    _need_git()
    _meta, co = _fixture(tmp_path)
    (co / "README.md").write_text("# new-name\n\nSee [docs](https://example.com/x).\n", encoding="utf-8")
    r = _run(["--repo-dir", str(co), "--assume-repo", "example-org/new-name", "content", "links"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert '"repo": "old-name"' in r.stdout, r.stdout
    assert "origin-renamed" not in r.stdout, r.stdout
