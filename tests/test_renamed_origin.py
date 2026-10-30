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
- The content tests pin `content links` / `content images`: accepted and logged with `--meta` naming the override's
  repository, refused without `--meta` (their slug comes from the origin). The fingerprint, meta and stderr tests pin
  the `origin-renamed` audit line for the other commands.
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
    # REGRESSION GUARD, intentionally also green on base 2be04ac: the default (no flag) must keep rejecting a stale
    # origin with exit 2. Every test that exercises --assume-repo or the new message fails on base (18 of 20 do).
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _describe(meta, co)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "example-org/new-name" in r.stdout
    assert "example-org/old-name" in r.stdout
    assert '"result": "usage"' in r.stdout


def test_same_name_other_case_is_accepted(tmp_path):
    # REGRESSION GUARD, intentionally also green on base 2be04ac: case-different origins stay accepted by default.
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


def _readme(co):
    (co / "README.md").write_text("# new-name\n\nSee [docs](https://example.com/x).\n", encoding="utf-8")


def test_content_links_with_meta_and_assume_is_logged(tmp_path):
    """`content links` takes its slug from --meta (content._owner_repo). With --meta naming the override's repository
    the run is accepted, reports that slug, and logs the rename (main() adds it to the content result)."""
    _need_git()
    meta, co = _fixture(tmp_path)
    _readme(co)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "content", "links"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert '"repo": "new-name"' in r.stdout, r.stdout
    assert "origin-renamed:example-org/old-name->example-org/new-name" in r.stdout, r.stdout


def test_content_links_without_meta_refuses_assume(tmp_path):
    """Without --meta the content slug can only come from the origin, which the override cannot change. The flag is
    therefore refused (usage, exit 2) instead of being silently ignored (review A1, B3)."""
    _need_git()
    _meta, co = _fixture(tmp_path)
    _readme(co)
    r = _run(["--repo-dir", str(co), "--assume-repo", "example-org/new-name", "content", "links"])
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert '"result": "usage"' in r.stdout, r.stdout
    assert "without --meta" in r.stdout and "git remote set-url origin" in r.stdout, r.stdout


def test_content_images_with_meta_and_assume_is_logged(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    _readme(co)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "content", "images"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert "origin-renamed:example-org/old-name->example-org/new-name" in r.stdout, r.stdout


def test_fingerprint_logs_origin_renamed(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "fingerprint",
              "--out-dir", "OUT"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert '"logs": ["origin-renamed:example-org/old-name->example-org/new-name"]' in r.stdout, r.stdout


def test_meta_out_logs_origin_renamed(tmp_path):
    _need_git()
    meta, co = _fixture(tmp_path)
    out = tmp_path / "out.json"
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "meta", "--out", str(out)])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert '"logs": ["origin-renamed:example-org/old-name->example-org/new-name"]' in r.stdout, r.stdout


def test_meta_stdout_logs_origin_renamed_on_stderr(tmp_path):
    """Bare metadata JSON on stdout stays clean; the audit line goes to stderr."""
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "meta"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert "origin-renamed:example-org/old-name->example-org/new-name" in r.stderr, r.stderr
    assert "origin-renamed" not in r.stdout, r.stdout


def test_default_run_logs_no_origin_renamed(tmp_path):
    """Without the flag no origin-renamed line is ever written (a matching origin logs nothing either)."""
    _need_git()
    meta, co = _fixture(tmp_path)
    subprocess.run(["git", "-C", str(co), "remote", "set-url", "origin", "https://github.com/example-org/new-name.git"],
                   check=True)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "fingerprint",
              "--out-dir", "OUT"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert '"logs": []' in r.stdout, r.stdout


def test_other_repo_names_the_checkout_diagnostic(tmp_path):
    """An override naming another repository than --meta, with a checkout present, raises the checkout's own mismatch
    diagnostic (the checkout, its origin and the repair), not a bare usage message (review B3)."""
    _need_git()
    meta, co = _fixture(tmp_path)
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/something-else", "describe"])
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "is a checkout of example-org/old-name" in r.stdout, r.stdout
    assert "git remote set-url origin" in r.stdout, r.stdout


def test_partial_metadata_takes_identity_from_override_without_checkout(tmp_path):
    """Metadata that names no owner or repo (load_file fills 'unknown') is not a conflicting repository: the override
    supplies the identity (review B2)."""
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"description": "A synthetic example repository for tests.",
                                   "visibility": "public"}), encoding="utf-8")
    r = _run(["--meta", str(partial), "--no-repo-dir", "--assume-repo", "example-org/new-name", "meta"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert '"owner": "example-org"' in r.stdout and '"repo": "new-name"' in r.stdout, r.stdout
    assert "names another repository" not in r.stdout, r.stdout


def test_partial_metadata_with_checkout_takes_identity_from_override(tmp_path):
    """Review A/B2: partial metadata plus a stale-origin checkout is accepted (no 'unknown/...' mismatch)."""
    _need_git()
    _, co = _fixture(tmp_path)
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"repo": "new-name", "visibility": "public",
                                   "description": "A synthetic example repository for tests."}), encoding="utf-8")
    r = _run(["--meta", str(partial), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "describe"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert "unknown/" not in r.stdout and "/unknown" not in r.stdout, r.stdout
    assert "origin-renamed:example-org/old-name->example-org/new-name" in r.stdout, r.stdout


def test_metadata_only_override_is_logged(tmp_path):
    """Review B1: a run without a checkout still carries the audit line, with 'unknown' as the old slug."""
    r = _run(["--no-repo-dir", "--assume-repo", "example-org/new-name", "--meta", str(tmp_path / "m.json"), "fingerprint"]) \
        if False else None
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"description": "A synthetic example repository for tests.",
                                   "visibility": "public"}), encoding="utf-8")
    r = _run(["--meta", str(partial), "--no-repo-dir", "--assume-repo", "example-org/new-name", "fingerprint"])
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert "origin-renamed:unknown->example-org/new-name" in r.stdout, r.stdout


def test_content_report_file_carries_the_audit_line(tmp_path):
    """Review B3: the --report file has the same logs as stdout, also with --quiet."""
    _need_git()
    meta, co = _fixture(tmp_path)
    _readme(co)
    report = tmp_path / "report.json"
    r = _run(["--meta", str(meta), "--repo-dir", str(co), "--assume-repo", "example-org/new-name", "content", "links",
              "--report", str(report)])
    assert r.returncode != 2, (r.stdout, r.stderr)
    line = "origin-renamed:example-org/old-name->example-org/new-name"
    assert line in json.loads(report.read_text(encoding="utf-8"))["logs"]
