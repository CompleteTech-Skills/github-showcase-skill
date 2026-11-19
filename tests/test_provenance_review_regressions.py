"""PR206 review regressions: synthetic receipt/CLI evidence, never rendering or live writer evidence."""
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

OWNER = "Northwind-Trading-Co"
FORMER = "Northwind-Trading-Old"
SLUG = f"{OWNER}/review-demo"


@pytest.fixture
def cli(tmp_path):
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import socket\ndef blocked(*a, **kw):\n raise AssertionError('live transport prohibited')\n"
        "socket.socket.connect = blocked\nsocket.create_connection = blocked\nsocket.getaddrinfo = blocked\n",
        encoding="utf-8")
    shim = guard / "gh"
    shim.write_text("#!/bin/sh\necho 'live gh prohibited by regression test' >&2\nexit 97\n", encoding="utf-8")
    shim.chmod(0o755)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(guard),
               PATH=str(guard) + os.pathsep + os.environ["PATH"],
               SHOWCASE_STATE_DIR=str(tmp_path / "state"), SHOWCASE_ESTATE_ROOT=str(tmp_path / "estate"))
    for key in ("CI", "GITHUB_ACTIONS", "SHOWCASE_STAR_PROMPT"):
        env.pop(key, None)

    def call(*args):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "--format", "json", *map(str, args)],
                                cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert result.stdout.strip(), (result.returncode, result.stderr)
        return result, json.loads(result.stdout)

    return call


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"orgs": {OWNER: {"former_slugs": [FORMER]}}}), encoding="utf-8")
    return path


@pytest.fixture
def receipt(tmp_path, brand, registry, cli):
    root = tmp_path / "export"
    (root / "docs/images").mkdir(parents=True)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": OWNER, "repo": "review-demo", "description": "Review synthetic receipts.",
                               "topics": [], "visibility": "public", "language": "Python", "license": "MIT"}),
                    encoding="utf-8")
    # These intentionally synthetic bytes exercise the published receipt contract, not image validity or rendering.
    (root / "README.md").write_text("# Synthetic review\n<!-- showcase:banner:start -->\n"
                                    "![Synthetic](docs/images/banner.png)\n", encoding="utf-8")
    resolver = Resolver.from_paths(brand, registry)
    inputs = fp.inputs(load_file(meta), root, same_owner=resolver.same, metadata_path=meta)
    document = {}
    for name in ("banner.png", "card.svg"):
        path = root / "docs/images" / name
        path.write_bytes(b"synthetic receipt data: " + name.encode())
        document = fp.update_sidecar(document, inputs, brand.sha256, name, fp.file_record(path))
    (root / P.REPO_STAMP).write_text(fp.sidecar_text(document), encoding="utf-8")
    result, report = cli("--meta", meta, "--repo-dir", root, "provenance", "stamp", SLUG,
                         "--registry", registry, "--offline", "--changed", "no")
    assert result.returncode == 0 and report["completed"] and report["missing"] == []
    result, report = cli("--meta", meta, "--repo-dir", root, "provenance", "check", SLUG,
                         "--registry", registry, "--offline")
    assert result.returncode == 0 and report["status"] == "fresh"
    return root, meta


def write_queue(path, **target):
    path.write_text(json.dumps({"id": "synthetic-pending", "phase": "1", "kind": "readme",
                                "argv": ["synthetic-writer", "never-executed"], **target}) + "\n", encoding="utf-8")
    return path.read_bytes()


@pytest.mark.parametrize("queued", [f"{FORMER}/review-demo", f"{FORMER.lower()}/REVIEW-DEMO", SLUG.upper()])
@pytest.mark.parametrize("changed", ["auto", "no"])
def test_former_org_repository_queue_stays_pending_and_does_not_count(cli, receipt, registry, tmp_path, queued, changed):
    root, meta = receipt
    jobs = tmp_path / "pending.jsonl"
    before_jobs = write_queue(jobs, repo=queued)
    before_state = (tmp_path / "state/state.json").read_bytes()
    result, report = cli("--meta", meta, "--repo-dir", root, "provenance", "stamp", SLUG,
                         "--registry", registry, "--jobs", jobs, "--changed", changed, "--offline")
    assert result.returncode == 0, report
    assert report["completed"] is False and "writer:pending" in report["missing"], report
    assert (tmp_path / "state/state.json").read_bytes() == before_state
    assert jobs.read_bytes() == before_jobs
    checked, current = cli("--meta", meta, "--repo-dir", root, "provenance", "check", SLUG,
                           "--registry", registry, "--offline")
    assert checked.returncode == 1 and current["status"] == "incomplete"
    assert "writer:pending" in current["missing"]


@pytest.mark.parametrize("target", ["org:" + OWNER, "org:" + FORMER.lower()])
@pytest.mark.parametrize("queued", [{"org": FORMER}, {"org": FORMER.lower()},
                                    {"repo": f"{FORMER}/.GITHUB"}, {"org": OWNER.upper()},
                                    {"repo": "Northwind-Labs/unrelated", "org": FORMER}])
def test_org_queue_aliases_and_both_target_fields_are_resolved(cli, registry, tmp_path, target, queued):
    root = tmp_path / "profile-export"
    root.mkdir()
    jobs = tmp_path / "pending.jsonl"
    before = write_queue(jobs, **queued)
    result, report = cli("--repo-dir", root, "provenance", "stamp", target,
                         "--registry", registry, "--jobs", jobs, "--offline", "--changed", "no")
    assert result.returncode == 0 and not report["completed"], report
    assert "writer:pending" in report["missing"], report
    assert jobs.read_bytes() == before and not (tmp_path / "state/state.json").exists()
    # This deliberately incomplete profile is not a successful art/About capture; only the pending diagnosis is tested.


@pytest.mark.parametrize("action", ["rename", "transfer"])
@pytest.mark.parametrize("approved", [True, False])
def test_repository_queue_identity_uses_existing_approval_semantics(cli, receipt, registry, tmp_path, action, approved):
    root, meta = receipt
    old_owner = OWNER if action == "rename" else "Northwind-Labs"
    old_repo = "review-before" if action == "rename" else "review-demo"
    record = {"id": "synthetic-identity", "action": action, "owner": old_owner, "repo": old_repo,
              **({"new_name": "review-demo"} if action == "rename" else {"target_owner": OWNER})}
    actions, approvals = tmp_path / "actions.json", tmp_path / "approved.json"
    actions.write_text(json.dumps([record]), encoding="utf-8")
    approvals.write_text(json.dumps({"actions": [{"id": record["id"], "approved": approved}]}), encoding="utf-8")
    jobs = tmp_path / "pending.jsonl"
    before_jobs = write_queue(jobs, repo=f"{old_owner}/{old_repo}".upper())
    before = ledger.load(tmp_path / "state")["completed_runs"]
    result, report = cli("--meta", meta, "--repo-dir", root, "provenance", "stamp", SLUG, "--registry", registry,
                         "--actions", actions, "--approved-yaml", approvals, "--jobs", jobs, "--changed", "no", "--offline")
    assert result.returncode == 0 and report["completed"] is (not approved), report
    assert ("writer:pending" in report["missing"]) is approved
    assert ledger.load(tmp_path / "state")["completed_runs"] == before + (not approved)
    assert jobs.read_bytes() == before_jobs


@pytest.mark.parametrize("queued", [f"{FORMER}/another-repo", "Northwind-Labs/review-demo"])
def test_unrelated_queue_does_not_hold_verified_local_capture(cli, receipt, registry, tmp_path, queued):
    root, meta = receipt
    jobs = tmp_path / "unrelated.jsonl"
    before = write_queue(jobs, repo=queued)
    result, report = cli("--meta", meta, "--repo-dir", root, "provenance", "stamp", SLUG,
                         "--registry", registry, "--jobs", jobs, "--changed", "no", "--offline")
    assert result.returncode == 0 and report["completed"] and report["result"] == "fresh", report
    assert "writer:pending" not in report["missing"]
    assert ledger.load(tmp_path / "state")["completed_runs"] == 2 and jobs.read_bytes() == before


@pytest.fixture
def enterprise(tmp_path):
    registry = tmp_path / "estate/registry"
    registry.mkdir(parents=True)
    (registry / "estate.yaml").write_text("orgs: {}\n", encoding="utf-8")
    snapshot = {"slug": "northwind-review", "sections": {"profile": {"name": "Synthetic review"},
                "organizations": [], "members": [], "outside_collaborators": []}}
    raw = (json.dumps(snapshot) + "\n").encode()
    (registry / "enterprise.snapshot.json").write_bytes(raw)
    state = ledger.empty()
    state["completed_runs"] = 4
    ledger.save(state, tmp_path / "state")
    return registry, raw


@pytest.mark.parametrize("alias", ["exact", "parent", "input-symlink", "input-hardlink", "output-symlink"])
@pytest.mark.parametrize("with_jobs", [False, True])
def test_enterprise_snapshot_cannot_alias_local_stamp(cli, enterprise, tmp_path, alias, with_jobs):
    registry, raw = enterprise
    stamp_path = registry / P.ENTERPRISE_STAMP
    capture = registry / "supplied.json"
    if alias == "output-symlink":
        capture.write_bytes(raw)
        stamp_path.symlink_to(capture)
    else:
        stamp_path.write_bytes(raw)
        if alias == "exact":
            capture = stamp_path
        elif alias == "parent":
            (registry / "nested").mkdir()
            capture = registry / "nested" / ".." / P.ENTERPRISE_STAMP
        elif alias == "input-symlink":
            capture.symlink_to(stamp_path)
        else:
            os.link(stamp_path, capture)
    jobs = tmp_path / "jobs.jsonl"
    before_jobs = write_queue(jobs, repo="Northwind-Trading-Co/unrelated") if with_jobs else None
    before_state = (tmp_path / "state/state.json").read_bytes()
    extra = ("--jobs", jobs) if with_jobs else ()
    result, report = cli("--no-repo-dir", "provenance", "stamp", "enterprise:northwind-review", "--out-dir", registry,
                         "--snapshot", capture, "--offline", *extra)
    assert result.returncode == 2 and not report.get("completed"), report
    assert capture.read_bytes() == raw and stamp_path.read_bytes() == raw
    assert capture.samefile(stamp_path)
    assert (registry / "enterprise.snapshot.json").read_bytes() == raw
    assert (tmp_path / "state/state.json").read_bytes() == before_state
    assert (jobs.read_bytes() if jobs.exists() else None) == before_jobs


@pytest.mark.parametrize("capture_kind", ["separate", "symlink-to-snapshot", "hardlink-to-snapshot"])
def test_distinct_enterprise_capture_keeps_its_bytes_and_can_complete(cli, enterprise, tmp_path, capture_kind):
    registry, raw = enterprise
    capture = tmp_path / "supplied.json"
    if capture_kind == "separate":
        capture.write_bytes(raw)
    elif capture_kind == "symlink-to-snapshot":
        capture.symlink_to(registry / "enterprise.snapshot.json")
    else:
        os.link(registry / "enterprise.snapshot.json", capture)
    result, report = cli("--no-repo-dir", "provenance", "stamp", "enterprise:northwind-review", "--out-dir", registry,
                         "--snapshot", capture, "--offline")
    assert result.returncode == 0 and report["completed"] and report["missing"] == [], report
    assert capture.read_bytes() == raw and (registry / "enterprise.snapshot.json").read_bytes() == raw
    assert not capture.samefile(registry / P.ENTERPRISE_STAMP)
    assert ledger.load(tmp_path / "state")["completed_runs"] == 5


def test_repository_metadata_cannot_be_the_local_stamp_destination(cli, tmp_path):
    root = tmp_path / "export"
    capture = root / P.REPO_STAMP
    capture.parent.mkdir(parents=True)
    before = json.dumps({"owner": OWNER, "repo": "review-demo", "description": "Synthetic captured metadata.",
                         "topics": [], "visibility": "public", "language": "Python", "license": "MIT"}).encode()
    capture.write_bytes(before)
    result, report = cli("--meta", capture, "--repo-dir", root, "provenance", "stamp", SLUG, "--offline")
    assert result.returncode == 2 and not report.get("completed"), report
    assert capture.read_bytes() == before and not (tmp_path / "state/state.json").exists()
