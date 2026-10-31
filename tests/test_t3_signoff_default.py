"""Default-on T3 sign-off (issue 23, tasks 24-27): a bare `--allow-t3` needs a record at the private estate path.

Synthetic records only (owner Pick-Your-AI is the brand.yaml T3 owner; ids and dates are made up). Each test fails on
b71a063, where enforcement was opt-in and there was no default location.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]
META = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))
OWNER = "Pick-Your-AI"
RECORD = """signoffs:
  - id: {id}
    owner: {owner}
    repos: {repos}
    approved: true
    approver: synthetic-co-owner
    approved_on: 2026-01-15
    expires: 2099-12-31
"""


def _bundle(tmp_path, *, id="t3s-default", owner=OWNER, repos='["*"]', write=True):
    root = tmp_path / "bundle"
    (root / "decisions").mkdir(parents=True)
    if write:
        (root / "decisions" / "t3-signoffs.yaml").write_text(RECORD.format(id=id, owner=owner, repos=repos),
                                                             encoding="utf-8")
    return root


def _run(tmp_path, root, *argv, env=None, owner=OWNER):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner=owner, repo="northwind-synthetic")), encoding="utf-8")
    e = dict(os.environ)
    for k in ("SHOWCASE_T3_SIGNOFF_FILE", "SHOWCASE_ESTATE_ROOT"):
        e.pop(k, None)
    if root is not None:
        e["SHOWCASE_ESTATE_ROOT"] = str(root)
    e.update(env or {})
    return subprocess.run([*SHOWCASE, "--meta", str(meta), "--no-repo-dir", *argv], cwd=ROOT, env=e,
                          capture_output=True, text=True, encoding="utf-8")


def _out(r):
    return r.stdout + r.stderr


def test_bare_allow_t3_without_a_record_is_refused_and_names_the_path(tmp_path):
    root = _bundle(tmp_path, write=False)
    r = _run(tmp_path, root, "--allow-t3", "describe")
    want = root / "decisions" / "t3-signoffs.yaml"
    assert r.returncode == 2 and "t3-signoff:no-file" in _out(r), _out(r)
    assert str(want) in json.loads(r.stdout)["error"], r.stdout
    assert not want.exists(), "the tool must never create the record file"


def test_bare_allow_t3_reads_the_default_estate_record(tmp_path):
    r = _run(tmp_path, _bundle(tmp_path), "--allow-t3", "describe")
    assert r.returncode != 2 and "t3-signoff" not in _out(r), _out(r)


def test_default_record_for_another_owner_does_not_authorize(tmp_path):
    r = _run(tmp_path, _bundle(tmp_path, owner="Some-Other-Org"), "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:missing" in _out(r), _out(r)


def test_unavailable_estate_root_fails_closed(monkeypatch):
    """No estate root resolves: there is no default path, and the gate reports no-file instead of trusting the flag."""
    from ctshowcase import resolver, signoff
    monkeypatch.delenv("SHOWCASE_ESTATE_ROOT", raising=False)
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)
    monkeypatch.setattr(resolver, "estate_root", lambda: None)
    assert signoff.default_record_path() is None and signoff.record_file() is None
    rec, why = signoff.evaluate([OWNER], "northwind-synthetic")
    assert rec is None and why.startswith("no-file:"), why


def test_record_file_resolution_order_flag_then_env_then_default(tmp_path, monkeypatch):
    from ctshowcase import signoff
    root = _bundle(tmp_path)
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(root))
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)
    default = root / "decisions" / "t3-signoffs.yaml"
    assert signoff.default_record_path() == default and signoff.record_file() == default
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(tmp_path / "env.yaml"))
    assert signoff.record_file() == tmp_path / "env.yaml"
    token = signoff.set_file(tmp_path / "flag.yaml")
    try:
        assert signoff.record_file() == tmp_path / "flag.yaml"
    finally:
        signoff.reset_file(token)


def test_there_is_no_opt_out(tmp_path):
    """Adjudication t3-no-bypass: neither a flag nor an environment variable turns enforcement off."""
    root = _bundle(tmp_path, write=False)
    r = _run(tmp_path, root, "--no-require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "unrecognized arguments" in _out(r), _out(r)
    for value in ("0", "false", "no", "off"):
        r = _run(tmp_path, root, "--allow-t3", "describe", env={"SHOWCASE_REQUIRE_T3_SIGNOFF": value})
        assert r.returncode == 2 and "t3-signoff:no-file" in _out(r), (value, _out(r))
    r = _run(tmp_path, root, "--require-t3-signoff", "--allow-t3", "describe")  # the compatible no-op flag
    assert r.returncode == 2 and "t3-signoff:no-file" in _out(r), _out(r)


def test_writer_jobs_carry_the_default_records_id(tmp_path):
    r = _run(tmp_path, _bundle(tmp_path, id="t3s-def-job"), "--allow-t3", "adopt", f"{OWNER}/northwind-synthetic")
    jobs = json.loads(r.stdout)["jobs"]
    topics = [j for j in jobs if j["kind"] == "topics"]
    assert topics and all(j.get("signoff_id") == "t3s-def-job" for j in topics), r.stdout[:400]


# --- exact owner/repo identity for project job provenance ---

def test_record_for_another_owners_repo_does_not_cover_a_same_named_repo_elsewhere(tmp_path, monkeypatch):
    """A record for Pick-Your-AI/website must not stamp (or authorize) Other-Org/website: the repository's owner has
    to be the record's org, the name alone is not an identity."""
    from ctshowcase import signoff
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(_bundle(tmp_path, repos='["Pick-Your-AI/website", "plain-name"]')))
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)
    token = signoff.reset()
    try:
        assert signoff.evaluate([OWNER], "Pick-Your-AI/website")[0] is not None
        assert signoff.evaluate([OWNER], "Other-Org/website")[1] == "scope"
        assert signoff.evaluate([OWNER], "Other-Org/plain-name")[1] == "scope"
        assert signoff.evaluate([OWNER], "Pick-Your-AI/plain-name")[0] is not None
        signoff.require(OWNER, "Pick-Your-AI/website")
        job = {"phase": 1, "repo": "Other-Org/website", "org": OWNER}
        assert "signoff_id" not in signoff.stamp([job])[0]
    finally:
        signoff.restore(token)


def test_stamp_source_matches_the_exact_owner_and_name(tmp_path, monkeypatch):
    from ctshowcase import signoff
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(_bundle(tmp_path, repos='["Pick-Your-AI/website"]')))
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)
    token = signoff.reset()
    try:
        ok = signoff.stamp_source({"phase": 1}, "Pick-Your-AI/website")
        other = signoff.stamp_source({"phase": 1}, "Other-Org/website")
        assert ok.get("signoff_id") == "t3s-default" and "signoff_id" not in other
    finally:
        signoff.restore(token)


def test_estate_plan_stamping_ignores_a_display_name_shared_with_another_org(tmp_path, monkeypatch):
    """A T3 org whose display name equals a T1 org's login or name is ambiguous: only its login (or `T3: login`) credits a job."""
    from ctshowcase import project as PJ, signoff
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(_bundle(tmp_path, owner="Acme-T3")))
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)
    orgs = [{"login": "Acme-T3", "name": "Acme", "tier": "T3", "signoff_id": "t3s-acme"},
            {"login": "Acme", "name": "Acme", "tier": "T1"}]
    jobs = [{"id": "t1", "phase": 1, "argv": ["gh", "x", "name=Acme"]},
            {"id": "t3", "phase": 1, "argv": ["gh", "x", "name=Acme-T3"]}]
    token = signoff.reset()
    try:
        PJ._stamp_estate_orgs(jobs, orgs)
    finally:
        signoff.restore(token)
    assert {j["id"]: j.get("signoff_id") for j in jobs} == {"t1": None, "t3": "t3s-acme"}
