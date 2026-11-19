"""Issue 213: CLI observations of independent owner restrictions (synthetic, offline).

Cases were designed from the issue and public CLI/consent contracts, without
reading candidate implementation, and frozen before their unmodified-base runs.
"""
from __future__ import annotations

import copy
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import showcase  # noqa: E402
from ctshowcase import account  # noqa: E402

OWNER = "Northwind-CoOwned"
FORMER = "Northwind-Former"
READER = "northwind-reader"


def record(id="synthetic-grant", **overrides):
    return dict({"id": id, "owner": FORMER, "repos": ["*"], "approved": True,
                 "approver": "synthetic-reviewer", "approved_on": "2000-01-01",
                 "expires": "2099-12-31"}, **overrides)


CASES = {
    "no-opt-in": ([record()], False, False),
    "missing": ([], True, False),
    "expired": ([record(expires="2001-01-01")], True, False),
    "revoked": ([record(), record("synthetic-revocation", approved=False,
                                 approved_on="2000-02-01")], True, False),
    "wrong-repository": ([record(repos=["unrelated-repository"])], True, False),
    "authorized": ([record()], True, True),
}


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Never execute gh/writer or open a network connection, even on a regression."""
    def blocked(*args, **kwargs):
        raise AssertionError("unexpected transport/process execution in offline CLI test")
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path))
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)
    monkeypatch.chdir(ROOT)


def inputs(tmp_path, records, *, t3=True, excluded=False, split_alias=False):
    raw = yaml.safe_load((ROOT / "references/brand.yaml").read_text(encoding="utf-8"))
    raw["orgs"][OWNER] = copy.deepcopy(raw["orgs"]["Northwind-Trading-Co"])
    raw["orgs"][OWNER].update(former_slugs=[FORMER], display_name="Northwind Co-Owned")
    raw["owners"]["hold"].append(OWNER)
    if t3:
        raw["owners"]["t3"].append(FORMER.swapcase() if split_alias else OWNER)
    if excluded:
        raw["owners"]["excluded"].append(FORMER.swapcase())
    config = tmp_path / "brand.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"orgs": {OWNER: {
        "former_slugs": [FORMER], "tier": "T1", "profile": {
            "name": "Northwind Co-Owned", "blog": "https://northwind.example"}}}}), encoding="utf-8")
    signoffs = tmp_path / "signoffs.yaml"
    signoffs.write_text(yaml.safe_dump({"signoffs": records}), encoding="utf-8")
    return ["--config", str(config), "--t3-signoff-file", str(signoffs)], registry


def cli(capsys, prefix, *argv):
    code = showcase.main([*prefix, *map(str, argv)])
    output = capsys.readouterr()
    assert not output.err, output.err
    return code, json.loads(output.out)


def repo(name, *, parent=None):
    return {"name": name, "description": "Synthetic fixture.", "language": "Python",
            "fork": parent is not None, "archived": False,
            **({"parent": parent} if parent is not None else {})}


def snapshot(tmp_path, *, root=READER, org_login=OWNER, root_repos=None, org_repos=None):
    snap = {"schema": "account-chart/v1", "std": "ct-std-v1", "captured": "2026-01-01",
            "viewer": root, "account": {"login": root, "name": "Northwind Reader", "company": "",
                                      "location": "", "website": ""},
            "repositories": root_repos if root_repos is not None else [repo("reader-control")],
            "not_public": 0, "enterprises": [], "organizations": [{
                "login": org_login, "name": "Northwind Co-Owned", "member": True, "role": "owner",
                "captured": True, "not_public": 0,
                "repositories": org_repos if org_repos is not None else [repo("consent-protected")] }],
            "notes": []}
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snap), encoding="utf-8")
    return path


def fake_reads(monkeypatch, *, root=READER, discovered=OWNER, root_repos=None, org_repos=None):
    calls = []
    def connection(nodes):
        return {"nodes": nodes, "pageInfo": {"hasNextPage": False}}
    def nodes(repos):
        return [{"name": r["name"], "description": "Synthetic fixture.", "isFork": r["fork"],
                 "isArchived": False, "primaryLanguage": {"name": "Python"},
                 **({"parent": {"nameWithOwner": r["parent"]}} if r.get("parent") else {})} for r in repos]
    def run(name, **variables):
        calls.append((name, variables))
        if name == "account_viewer":
            return {"viewer": {"login": root}}
        if name == "account_user":
            rs = root_repos if root_repos is not None else [repo("reader-control")]
            return {"user": {"login": root, "name": "Northwind Reader",
                             "all": {"totalCount": len(rs)}, "public": {"totalCount": len(rs)},
                             "repositories": connection(nodes(rs))}}
        if name == "account_orgs":
            return {"user": {"organizations": connection([{"login": discovered}])}}
        if name == "account_enterprises":
            return {"viewer": {"enterprises": connection([])}}
        if name == "account_org":
            rs = org_repos if org_repos is not None else [repo("consent-protected")]
            return {"organization": {"login": variables["org"], "name": "Northwind Co-Owned",
                                     "viewerCanAdminister": True, "all": {"totalCount": len(rs)},
                                     "public": {"totalCount": len(rs)}, "repositories": connection(nodes(rs))}}
        raise AssertionError(f"unexpected GraphQL query {name}")
    monkeypatch.setattr(account, "_gh", run)
    return calls


@pytest.mark.parametrize("split_alias", [False, True], ids=["same-login", "former-case-alias"])
@pytest.mark.parametrize("case", CASES)
def test_capture_hold_does_not_supply_t3_consent(tmp_path, monkeypatch, capsys, case, split_alias):
    records, opt_in, authorized = CASES[case]
    prefix, registry = inputs(tmp_path, records, split_alias=split_alias)
    calls = fake_reads(monkeypatch, discovered=FORMER.lower() if split_alias else OWNER)
    out = tmp_path / "captured.json"
    code, result = cli(capsys, prefix + (["--allow-t3"] if opt_in else []), "account-chart", "capture", READER,
                       "--registry", registry, "--allow-hold", "--out", out)
    assert code == 0, result
    saved = out.read_text(encoding="utf-8")
    assert "reader-control" in saved, "the unrestricted root account must still be captured"
    assert any(name == "account_org" for name, _ in calls) == authorized, "HOLD bypassed independent T3 query consent"
    assert ("consent-protected" in saved) == authorized, "capture persisted a repository without independent T3 consent"


@pytest.mark.parametrize("case", CASES)
def test_render_rechecks_overlapping_alias_consent(tmp_path, capsys, case):
    records, opt_in, authorized = CASES[case]
    prefix, registry = inputs(tmp_path, records, split_alias=True)
    snap = snapshot(tmp_path, org_login=FORMER.lower())
    out = tmp_path / "rendered"
    code, result = cli(capsys, prefix + (["--allow-t3"] if opt_in else []), "account-chart", "render",
                       "--snapshot", snap, "--registry", registry, "--allow-hold", "--no-png", "--out-dir", out)
    assert code == 0, result
    # The SVG outlines text into glyph paths; inspect the two readable outputs.
    for suffix in ("mmd", "md"):
        text = (out / f"account-chart.{suffix}").read_text(encoding="utf-8")
        assert "reader-control" in text
        assert ("consent-protected" in text) == authorized, (suffix, "render bypassed T3 consent")


@pytest.mark.parametrize("case", CASES)
def test_org_about_hold_allowance_keeps_consent_and_job_provenance(tmp_path, capsys, case):
    records, opt_in, authorized = CASES[case]
    prefix, registry = inputs(tmp_path, records, split_alias=True)
    jobs = tmp_path / "jobs.jsonl"
    code, result = cli(capsys, prefix + (["--allow-t3"] if opt_in else []), "org", "about", FORMER.lower(),
                       "--registry", registry, "--jobs", jobs)
    if not authorized:
        assert code == 2, "shared org HOLD allowance bypassed independent T3 consent"
        assert any("t3-signoff" in log for log in result["logs"]), result
        assert not jobs.exists() or not jobs.read_text(encoding="utf-8").strip()
    else:
        assert code == 0 and result["jobs"], result
        emitted = [json.loads(line) for line in jobs.read_text(encoding="utf-8").splitlines()]
        assert emitted and all(job.get("signoff_id") == "synthetic-grant" for job in emitted)
        assert all("approval_id" not in job for job in emitted), "consent is separate from writer approval"


@pytest.mark.parametrize("excluded", [False, True], ids=["root-hold", "excluded-alias"])
@pytest.mark.parametrize("action", ["capture", "render"])
def test_chart_flags_cannot_release_root_hold_or_exclusion(tmp_path, monkeypatch, capsys, excluded, action):
    prefix, registry = inputs(tmp_path, [record()], excluded=excluded, split_alias=True)
    calls = fake_reads(monkeypatch, root=FORMER.lower())
    dest = tmp_path / "result"
    if action == "capture":
        args = ["account-chart", "capture", FORMER.lower(), "--out", dest]
    else:
        args = ["account-chart", "render", "--snapshot", snapshot(tmp_path, root=FORMER.lower()),
                "--no-png", "--out-dir", dest]
    code, result = cli(capsys, prefix + ["--allow-t3"], *args, "--registry", registry, "--allow-hold")
    assert code == 2, result
    assert calls == [], "a refused explicit root must make no network query"
    assert not dest.exists(), "a refused root must write no output"


def test_allow_hold_control_and_excluded_organization(tmp_path, monkeypatch, capsys):
    for excluded in (False, True):
        folder = tmp_path / str(excluded)
        folder.mkdir()
        prefix, registry = inputs(folder, [], t3=False, excluded=excluded)
        calls = fake_reads(monkeypatch, discovered=FORMER.lower())
        dest = folder / "captured.json"
        code, result = cli(capsys, prefix, "account-chart", "capture", READER, "--registry", registry,
                           "--allow-hold", "--out", dest)
        assert code == 0, result
        assert any(n == "account_org" for n, _ in calls) == (not excluded)
        assert ("consent-protected" in dest.read_text(encoding="utf-8")) == (not excluded)


def test_withdrawal_filters_held_repositories_and_nested_fork_parents(tmp_path, monkeypatch, capsys):
    records = [record(), record("synthetic-withdrawal", repos=[f"{FORMER.lower()}/upstream-denied"],
                                approved=False, approved_on="2000-02-01")]
    prefix, registry = inputs(tmp_path, records, split_alias=True)
    roots = [repo("retained-fork", parent=f"{FORMER}/upstream-kept"),
             repo("unknown-upstream-fork", parent=f"{FORMER}/upstream-denied")]
    calls = fake_reads(monkeypatch, root_repos=roots,
                       org_repos=[repo("upstream-kept"), repo("upstream-denied")])
    dest = tmp_path / "captured.json"
    code, result = cli(capsys, prefix + ["--allow-t3"], "account-chart", "capture", READER,
                       "--registry", registry, "--allow-hold", "--out", dest)
    assert code == 0 and any(n == "account_org" for n, _ in calls), result
    saved = json.loads(dest.read_text(encoding="utf-8"))
    assert {r["name"] for o in saved["organizations"] for r in o["repositories"]} == {"upstream-kept"}, \
        "a wildcard owner grant must not revive its withdrawn repository"
    by_name = {r["name"]: r for r in saved["repositories"]}
    assert by_name["retained-fork"]["parent"] == f"{FORMER}/upstream-kept"
    assert "parent" not in by_name["unknown-upstream-fork"], "withdrawn upstream metadata must remain unknown"
    assert "upstream-denied" not in json.dumps(saved), "withheld parent/repository facts must not reach disk"


def test_scoped_parent_consent_does_not_authorize_an_organization_query(tmp_path, monkeypatch, capsys):
    prefix, registry = inputs(tmp_path, [record(repos=["upstream-kept"])], split_alias=True)
    roots = [repo("retained-fork", parent=f"{FORMER}/upstream-kept"),
             repo("unknown-upstream-fork", parent=f"{FORMER}/upstream-denied")]
    calls = fake_reads(monkeypatch, root_repos=roots)
    dest = tmp_path / "captured.json"
    code, result = cli(capsys, prefix + ["--allow-t3"], "account-chart", "capture", READER,
                       "--registry", registry, "--allow-hold", "--out", dest)
    assert code == 0, result
    saved = json.loads(dest.read_text(encoding="utf-8"))
    by_name = {r["name"]: r for r in saved["repositories"]}
    assert by_name["retained-fork"]["parent"] == f"{FORMER}/upstream-kept", "a valid scoped parent grant must work"
    assert "parent" not in by_name["unknown-upstream-fork"], "HOLD must not mask the parent's repository scope"
    assert not any(n == "account_org" for n, _ in calls), "a scoped parent grant cannot authorize owner-wide reads"
