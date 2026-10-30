"""A checkout whose origin is a stale (renamed) slug: refused by default with the fix named; accepted, logged, with
the explicit global `--assume-repo OWNER/REPO`. The skill never edits the remote and makes no network call."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]
META = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))
OLD = "https://github.com/northwind-synthetic/old-name.git"


def _checkout(tmp_path):
    rd = tmp_path / "co"
    rd.mkdir()
    subprocess.run(["git", "init", "-q", str(rd)], check=True)
    subprocess.run(["git", "-C", str(rd), "remote", "add", "origin", OLD], check=True)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner="northwind-synthetic", repo="new-name")), encoding="utf-8")
    return rd, meta


def _run(rd, meta, *flags):
    return subprocess.run([*SHOWCASE, "--meta", str(meta), "--repo-dir", str(rd), *flags, "describe"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")


def _origin(rd):
    return subprocess.run(["git", "-C", str(rd), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()


def test_stale_origin_is_refused_by_default_and_names_the_fix(tmp_path):
    rd, meta = _checkout(tmp_path)
    r = _run(rd, meta)
    out = r.stdout + r.stderr
    assert r.returncode == 2, out
    assert "git remote set-url origin https://github.com/northwind-synthetic/new-name.git" in out
    assert "--assume-repo northwind-synthetic/new-name" in out


def test_assume_repo_accepts_with_a_logged_note_and_leaves_the_remote_alone(tmp_path):
    rd, meta = _checkout(tmp_path)
    r = _run(rd, meta, "--assume-repo", "northwind-synthetic/new-name")
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert "assume-repo:northwind-synthetic/new-name" in r.stdout + r.stderr
    assert _origin(rd) == OLD


def test_assume_repo_naming_another_repository_is_still_refused(tmp_path):
    rd, meta = _checkout(tmp_path)
    r = _run(rd, meta, "--assume-repo", "northwind-synthetic/other")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "does not match" in r.stdout + r.stderr


def test_assume_repo_must_be_owner_slash_repo(tmp_path):
    rd, meta = _checkout(tmp_path)
    # Exit 2 alone is vacuous: an unknown flag also exits 2 on the base. Assert the flag exists (usage text) and that the
    # failure is this flag's own OWNER/REPO validation message, not argparse's "unrecognized arguments".
    assert "--assume-repo" in subprocess.run([*SHOWCASE, "--help"], cwd=ROOT, capture_output=True, text=True,
                                             encoding="utf-8").stdout
    for bad in ("nonsense", "a/b/c", "/repo", "owner/"):
        r = _run(rd, meta, "--assume-repo", bad)
        out = r.stdout + r.stderr
        assert r.returncode == 2, (bad, out)
        assert "--assume-repo expects OWNER/REPO" in out, (bad, out)
        assert "unrecognized arguments" not in out, (bad, out)
