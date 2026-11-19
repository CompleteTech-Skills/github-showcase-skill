"""Fixed-clock, synthetic Git/receipt retries; no renderer, live API or writer execution evidence."""
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT
from ctshowcase import fingerprint as fp
from ctshowcase import ledger, provenance as P
from ctshowcase.meta import load_file
from ctshowcase.resolver import Resolver

SLUG = "Northwind-Trading-Co/retry-demo"
T0, T1, T2 = "2026-11-01T10:00:00Z", "2026-11-02T10:00:00Z", "2026-11-03T10:00:00Z"


def git(root, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="Synthetic Test", GIT_AUTHOR_EMAIL="test@example.invalid",
               GIT_COMMITTER_NAME="Synthetic Test", GIT_COMMITTER_EMAIL="test@example.invalid")
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8", env=env)


def commit(root):
    git(root, "add", "--all")
    git(root, "commit", "-qm", "Synthetic local baseline")


@pytest.fixture
def receipt(tmp_path, brand):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# Synthetic baseline\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    commit(root)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "retry-demo",
                               "description": "Synthetic retry receipt.", "topics": [], "visibility": "public",
                               "language": "Python", "license": "MIT"}), encoding="utf-8")
    (root / "README.md").write_text("# Synthetic retry\n<!-- showcase:banner:start -->\n"
                                    "![Synthetic](docs/images/banner.png)\n", encoding="utf-8")
    (root / "docs/images").mkdir(parents=True)
    inputs = fp.inputs(load_file(meta), root, same_owner=Resolver(brand).same, metadata_path=meta)
    document = {}
    for name in ("banner.png", "card.svg"):
        path = root / "docs/images" / name
        path.write_bytes(b"synthetic receipt bytes: " + name.encode())
        document = fp.update_sidecar(document, inputs, brand.sha256, name, fp.file_record(path))
    (root / P.REPO_STAMP).write_text(fp.sidecar_text(document), encoding="utf-8")
    return root, meta


def stamp(brand, receipt, now, **kwargs):
    root, meta = receipt
    return P.stamp_one(SLUG, brand, Resolver(brand), root=root, meta_path=str(meta), now=now, **kwargs)


def document(receipt):
    return json.loads((receipt[0] / P.REPO_STAMP).read_text(encoding="utf-8"))


def tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(root).parts}


@pytest.mark.parametrize("dirty", ["untracked", "index", "worktree", "evidence-only"])
@pytest.mark.parametrize("changed", ["auto", "no"])
def test_same_dirty_capture_retry_preserves_every_byte_and_stamp_counter(brand, receipt, dirty, changed):
    root, _ = receipt
    if dirty == "index":
        git(root, "add", "--all")
    elif dirty in ("worktree", "evidence-only"):
        commit(root)
        if dirty == "worktree":
            with (root / "README.md").open("a", encoding="utf-8") as stream:
                stream.write("\nSynthetic uncommitted edit.\n")
    first, code = stamp(brand, receipt, T0)
    assert code == 0 and first["completed"] and first["provenance"]["run_count"] == 1
    before = tree_bytes(root)
    assert git(root, "status", "--porcelain").stdout.strip()
    if dirty == "evidence-only":
        assert git(root, "diff", "--name-only").stdout.splitlines() == [P.REPO_STAMP]
    retry, code = stamp(brand, receipt, T1, changed=changed)
    assert code == 0 and retry["completed"] and retry["result"] == "fresh", retry
    assert retry["written"] is None and "provenance:fresh-no-write" in retry["logs"]
    assert tree_bytes(root) == before
    assert document(receipt)["provenance"] == first["provenance"]


@pytest.mark.parametrize("output", ["README.md", "docs/images/card.svg"])
def test_genuine_output_change_advances_once_then_retry_is_idempotent(brand, receipt, output):
    root, _ = receipt
    first, _ = stamp(brand, receipt, T0)
    path = root / output
    path.write_bytes(path.read_bytes() + b"\nSynthetic changed bytes.\n")
    if output.endswith("card.svg"):
        doc = document(receipt)
        doc = fp.update_sidecar(doc, doc["inputs"], doc["config_sha256"], "card.svg", fp.file_record(path))
        (root / P.REPO_STAMP).write_text(fp.sidecar_text(doc), encoding="utf-8")
    changed, code = stamp(brand, receipt, T1)
    assert code == 0 and changed["completed"] and changed["written"]
    prov = changed["provenance"]
    assert (prov["first_run_at"], prov["last_run_at"], prov["last_changed_at"], prov["run_count"]) == (T0, T1, T1, 2)
    assert prov["fingerprint"] == first["provenance"]["fingerprint"]
    before = tree_bytes(root)
    retry, code = stamp(brand, receipt, T2)
    assert code == 0 and retry["result"] == "fresh" and retry["written"] is None
    assert tree_bytes(root) == before


def pending_queue(tmp_path):
    jobs = tmp_path / "pending.jsonl"
    jobs.write_text(json.dumps({"id": "synthetic-pending", "phase": "1", "kind": "readme", "repo": SLUG,
                                "argv": ["synthetic-writer", "not-executed"]}) + "\n", encoding="utf-8")
    return jobs


@pytest.mark.parametrize("state", ["incomplete", "pending"])
@pytest.mark.parametrize("changed", ["auto", "no"])
def test_incomplete_or_pending_dirty_retry_never_completes_or_rewrites(brand, receipt, tmp_path, state, changed):
    root, _ = receipt
    jobs = pending_queue(tmp_path) if state == "pending" else None
    if state == "incomplete":
        (root / "docs/images/card.svg").unlink()
    first, code = stamp(brand, receipt, T0, jobs=jobs)
    assert code == 0 and not first["completed"] and first["missing"]
    before, queue_bytes = tree_bytes(root), jobs.read_bytes() if jobs else None
    retry, code = stamp(brand, receipt, T1, jobs=jobs, changed=changed)
    assert code == 0 and not retry["completed"] and retry["result"] == "incomplete", retry
    assert retry["written"] is None and "provenance:incomplete-no-write" in retry["logs"]
    assert tree_bytes(root) == before and (jobs.read_bytes() if jobs else None) == queue_bytes
    assert document(receipt)["provenance"] == first["provenance"]


@pytest.mark.parametrize("explicit", [{"force": True}, {"changed": "yes"}])
@pytest.mark.parametrize("incomplete", [False, True])
def test_explicit_force_or_changed_retains_existing_timestamp_semantics(brand, receipt, explicit, incomplete):
    root, _ = receipt
    if incomplete:
        (root / "docs/images/card.svg").unlink()
    first, _ = stamp(brand, receipt, T0)
    before = document(receipt)
    second, code = stamp(brand, receipt, T1, **explicit)
    assert code == 0 and second["written"] and second["completed"] is (not incomplete)
    prov = second["provenance"]
    assert (prov["first_run_at"], prov["last_run_at"], prov["last_changed_at"], prov["run_count"]) == (T0, T1, T0, 2)
    assert prov["fingerprint"] == first["provenance"]["fingerprint"]
    after = document(receipt)
    assert {k: v for k, v in after.items() if k != "provenance"} == {k: v for k, v in before.items() if k != "provenance"}


CLI_DRIVER = """
import runpy, socket, sys
from pathlib import Path
_, clock, script, *arguments = sys.argv
sys.path.insert(0, str(Path(script).parent))
from ctshowcase import ledger, provenance
def blocked(*args, **kwargs):
    raise AssertionError("live transport prohibited by retry regression")
socket.socket.connect = socket.create_connection = socket.getaddrinfo = blocked
provenance.GH._call = ledger.gh_starred = blocked
provenance.utc_now = lambda: clock
sys.argv = [script, *arguments]
runpy.run_path(script, run_name="__main__")
"""


@pytest.mark.parametrize("state", ["complete", "incomplete", "pending"])
def test_fixed_clock_cli_final_route_records_dirty_retry_without_stamp_churn(receipt, tmp_path, state):
    root, meta = receipt
    jobs = pending_queue(tmp_path) if state == "pending" else None
    if state == "incomplete":
        (root / "docs/images/card.svg").unlink()
    env = dict(os.environ, SHOWCASE_STATE_DIR=str(tmp_path / "state"), SHOWCASE_ESTATE_ROOT=str(tmp_path / "estate"),
               PYTHONDONTWRITEBYTECODE="1")
    for key in ("CI", "GITHUB_ACTIONS", "SHOWCASE_STAR_PROMPT"):
        env.pop(key, None)

    def call(now):
        command = [sys.executable, "-c", CLI_DRIVER, now, str(ROOT / "scripts/showcase.py"), "--format", "json",
                   "--meta", str(meta), "--repo-dir", str(root), "provenance", "stamp", SLUG, "--offline"]
        if jobs:
            command += ["--jobs", str(jobs)]
        process = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
        assert process.returncode == 0, process.stdout + process.stderr
        return json.loads(process.stdout)

    first = call(T0)
    assert first["completed"] is (state == "complete") and first["written"]
    before = tree_bytes(root)
    retry = call(T1)
    assert retry["completed"] is (state == "complete") and retry["written"] is None, retry
    assert retry["result"] == ("fresh" if state == "complete" else "incomplete")
    assert tree_bytes(root) == before and document(receipt)["provenance"] == first["provenance"]
    counts = ledger.load(tmp_path / "state")
    assert (counts["completed_runs"], counts["fresh_runs"]) == ((2, 1) if state == "complete" else (0, 0))
    if state == "complete":
        with (root / "README.md").open("a", encoding="utf-8") as stream:
            stream.write("\nGenuine synthetic output edit.\n")
        advanced = call(T2)
        assert advanced["completed"] and advanced["provenance"]["run_count"] == 2
        assert advanced["provenance"]["last_changed_at"] == T2
        assert ledger.load(tmp_path / "state")["completed_runs"] == 3
