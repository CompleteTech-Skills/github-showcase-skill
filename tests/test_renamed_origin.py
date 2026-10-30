"""A checkout whose `origin` still names the old repository name is refused by default (usage, exit 2); a case-only
difference in the same name is accepted. Synthetic names only: example-org, old-name, new-name.

These are regression guards, not a reproduction of a defect. The refusal is the existing check in
`scripts/showcase.py::repo_dir` (review A4, via `_same_slug`), and both tests already pass on the base commit 2be04ac
(verified by exporting that commit to a scratch directory and running this file there: 2 passed). No source change is
needed, and none should be made to satisfy this file. Do not mark them xfail: the behaviour they pin is correct.

Mutation evidence (scratch copy of 2be04ac, not committed): disabling the origin check or making `_same_slug` always
true fails `test_stale_origin_is_rejected_by_default`; making `_same_slug` case-sensitive fails
`test_same_name_other_case_is_accepted`. Each test therefore detects its own defect class, even though neither fails
on the current base."""
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
