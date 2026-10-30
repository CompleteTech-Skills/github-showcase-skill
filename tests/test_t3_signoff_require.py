"""`--require-t3-signoff` (issue 23): `--allow-t3` needs a valid, unexpired sign-off record in the estate bundle.

Synthetic records only (owner Pick-Your-AI is the brand.yaml T3 owner; the ids and dates are made up). The existing
tests/test_allow_t3_global.py is the proof that behaviour without the new flag is unchanged and stays untouched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]
META = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))
OWNER = "Pick-Your-AI"


def _bundle(tmp_path, records):
    d = tmp_path / "bundle" / "decisions"
    d.mkdir(parents=True)
    lines = ["signoffs:"]
    for r in records:
        lines.append(f"  - id: {r['id']}")
        lines.append(f"    owner: {r.get('owner', OWNER)}")
        lines.append(f"    repos: {json.dumps(r.get('repos', ['*']))}")
        lines.append(f"    approved: {str(r.get('approved', True)).lower()}")
        lines.append(f"    expires: {r.get('expires', '2099-12-31')}")
    (d / "t3-signoffs.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path / "bundle"


def _run(tmp_path, bundle, *argv, owner=OWNER, env=None):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner=owner, repo="northwind-synthetic")), encoding="utf-8")
    e = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(bundle))
    e.pop("SHOWCASE_REQUIRE_T3_SIGNOFF", None)
    e.update(env or {})
    return subprocess.run([*SHOWCASE, "--meta", str(meta), "--no-repo-dir", *argv], cwd=ROOT, env=e,
                          capture_output=True, text=True, encoding="utf-8")


def _out(r):
    return r.stdout + r.stderr


def test_missing_record_refuses(tmp_path):
    r = _run(tmp_path, _bundle(tmp_path, []), "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:missing" in _out(r), _out(r)


def test_unapproved_record_counts_as_missing(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-9", "approved": False}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:missing" in _out(r), _out(r)


def test_expired_record_refuses(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-1", "expires": "2020-01-01"}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:expired" in _out(r), _out(r)


def test_record_scoped_to_other_repo_refuses(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-2", "repos": ["some-other-repo"]}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:scope" in _out(r), _out(r)


def test_valid_wildcard_and_repo_scoped_records_are_honoured(tmp_path):
    for repos in (["*"], ["northwind-synthetic"], [f"{OWNER}/northwind-synthetic"]):
        b = _bundle(tmp_path / "_".join(repos).replace("/", "_").replace("*", "star"), [{"id": "t3s-3", "repos": repos}])
        r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe")
        assert r.returncode != 2 and "t3-signoff" not in _out(r), (repos, _out(r))


def test_env_var_is_equivalent_to_the_flag(tmp_path):
    b = _bundle(tmp_path, [])
    r = _run(tmp_path, b, "--allow-t3", "describe", env={"SHOWCASE_REQUIRE_T3_SIGNOFF": "1"})
    assert r.returncode == 2 and "t3-signoff:missing" in _out(r), _out(r)


# Guard test: passes on base 2be04ac by design (verified: 28 of 30 tests in this file fail on base, only the two guards pass). It pins the unchanged default.
def test_flag_without_allow_t3_still_refuses_as_before(tmp_path):
    r = _run(tmp_path, _bundle(tmp_path, [{"id": "t3s-4"}]), "--require-t3-signoff", "describe")
    assert r.returncode == 2 and "t3-signoff" in _out(r)


# Guard test: passes on base 2be04ac by design (verified: 28 of 30 tests in this file fail on base, only the two guards pass). It pins the unchanged default.
def test_default_is_unchanged_without_the_new_flag(tmp_path):
    """No flag and no records at all: `--allow-t3` alone still lifts the refusal (byte-for-byte old behaviour)."""
    r = _run(tmp_path, _bundle(tmp_path, []), "--allow-t3", "describe")
    assert r.returncode != 2 and "t3-signoff" not in _out(r), _out(r)


def test_excluded_owner_is_refused_even_with_a_record(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-5", "owner": "BunsDev"}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe", owner="BunsDev")
    assert r.returncode == 2, _out(r)
    assert "t3-signoff" not in _out(r) or "exempt" in _out(r)


def test_doctor_shows_the_signoff_id(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-7", "expires": "2099-01-02"}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "doctor", "--format", "json")
    row = json.loads(r.stdout)
    assert row["signoff_id"] == "t3s-7" and row["signoff_expires"] == "2099-01-02", r.stdout
    plain = _run(tmp_path, b, "--allow-t3", "doctor", "--format", "json")
    assert "signoff_id" not in json.loads(plain.stdout)  # off by default: the row is unchanged


def test_writer_jobs_carry_the_signoff_id(tmp_path):
    from ctshowcase import signoff
    from ctshowcase.records import append
    rec = {"id": "t3s-8", "owner": OWNER, "repos": ["*"], "approved": True, "expires": "2099-12-31"}
    signoff.set_required(True)
    try:
        signoff._GRANTED[OWNER.lower()] = [rec]
        out = tmp_path / "jobs.jsonl"
        append(out, [{"id": "a", "phase": "p", "kind": "repo-settings", "repo": f"{OWNER}/x", "argv": []},
                     {"id": "b", "phase": "p", "kind": "repo-settings", "repo": f"{OWNER}/y", "argv": [],
                      "approval_id": "ent-009"},
                     {"id": "c", "phase": "p", "kind": "repo-settings", "repo": "Other-Org/z", "argv": []}])
        a, b, c = (json.loads(x) for x in out.read_text(encoding="utf-8").splitlines())
        assert a["signoff_id"] == "t3s-8" and a["approval_id"] == "t3s-8"
        assert b["signoff_id"] == "t3s-8" and b["approval_id"] == "ent-009"  # an existing approval is kept
        assert "signoff_id" not in c
    finally:
        signoff.set_required(False)
        signoff.reset()


def test_jobs_are_untouched_without_the_flag(tmp_path):
    from ctshowcase import signoff
    from ctshowcase.records import append
    signoff._GRANTED[OWNER.lower()] = {"id": "t3s-8", "repos": ["*"]}
    try:
        out = tmp_path / "jobs.jsonl"
        append(out, [{"id": "a", "phase": "p", "kind": "k", "repo": f"{OWNER}/x"}])
        assert "signoff_id" not in json.loads(out.read_text(encoding="utf-8"))
    finally:
        signoff.reset()


def test_state_does_not_outlive_the_invocation(tmp_path, capsys):
    from ctshowcase import signoff
    import showcase
    showcase.main(["--require-t3-signoff", "config"])
    capsys.readouterr()
    assert signoff.required() is False and not signoff._GRANTED


@pytest.mark.parametrize("repo,expect", [(None, "scope"), ("a", None), ("B", None), ("c", "scope")])
def test_evaluate_scope_rules(repo, expect):
    from ctshowcase import signoff
    recs = [{"id": "s", "owner": OWNER, "repos": ["a", f"{OWNER}/b"], "approved": True, "expires": "2099-01-01"}]
    rec, why = signoff.evaluate([OWNER], repo, records=recs)
    assert why == expect and (rec is None) == (expect is not None)


# --- review round: repository scope threading, ids, aliases, project gate, doctor renderers ---------------------

@pytest.mark.parametrize("argv", [("labels", "--plan"), ("content", "linguist"), ("content", "actions")])
def test_repo_scoped_record_is_honoured_by_repository_commands(tmp_path, argv):
    """Regression: only gate_owner/doctor passed the repo, so a repo-scoped record hit t3-signoff:scope elsewhere."""
    b = _bundle(tmp_path, [{"id": "t3s-9", "repos": ["northwind-synthetic"]}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", *argv)
    assert "t3-signoff" not in _out(r), _out(r)
    other = _bundle(tmp_path / "o", [{"id": "t3s-9", "repos": ["some-other-repo"]}])
    r = _run(tmp_path, other, "--require-t3-signoff", "--allow-t3", *argv)
    assert r.returncode == 2 and "t3-signoff:scope" in _out(r), _out(r)


def test_record_without_an_id_never_authorizes(tmp_path):
    from ctshowcase import signoff
    rec = {"owner": OWNER, "repos": ["*"], "approved": True, "expires": "2099-12-31"}
    assert signoff.evaluate([OWNER], None, records=[rec]) == (None, "missing")
    assert signoff.evaluate([OWNER], None, records=[dict(rec, id="  ")]) == (None, "missing")
    assert signoff.evaluate([OWNER], None, records=[dict(rec, id="t3s-1")])[1] is None


def test_alias_record_matches_every_later_check(tmp_path, monkeypatch):
    """A record under a former login must satisfy the secondary helpers (config/org/project/doctor), not just the gate."""
    from ctshowcase import signoff
    from ctshowcase.config import set_t3_signed_off, t3_signed_off
    from ctshowcase.org import _t3_granted as org_granted
    from ctshowcase.project import _t3_granted as project_granted
    b = _bundle(tmp_path, [{"id": "t3s-10", "owner": "Old-Login"}])
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(b))
    signoff.set_required(True)
    set_t3_signed_off(True)
    try:
        assert not t3_signed_off("New-Login")  # nothing links the logins yet
        signoff.register_aliases(["New-Login", "Old-Login"])  # what Resolver.aliases does under the flag
        assert t3_signed_off("New-Login") and org_granted("New-Login") and project_granted("New-Login")
    finally:
        set_t3_signed_off(False)
        signoff.set_required(False)
        signoff.reset()


def test_project_gate_registers_the_grant_and_reports_the_reason(tmp_path, monkeypatch):
    from ctshowcase import signoff
    from ctshowcase.errors import Refused
    from ctshowcase.project import _gate_target
    from ctshowcase.resolver import Resolver
    from ctshowcase.config import Brand
    brand = Brand({"owners": {"t3": [OWNER]}}, ROOT / "references" / "brand.yaml")
    resolver = Resolver(brand, {}, None)
    signoff.set_required(True)
    try:
        monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(_bundle(tmp_path / "ok", [{"id": "t3s-11"}])))
        assert _gate_target(resolver, OWNER, allow_t3=True) == OWNER
        assert signoff.record_for(OWNER, None)["id"] == "t3s-11"  # so stamp() can put it on the writer job
        signoff.reset()
        monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(_bundle(tmp_path / "old", [{"id": "t3s-12", "expires": "2000-01-01"}])))
        with pytest.raises(Refused) as exc:
            _gate_target(resolver, OWNER, allow_t3=True)
        assert exc.value.log == "t3-signoff:expired"
    finally:
        signoff.set_required(False)
        signoff.reset()


def test_default_doctor_renderers_show_the_signoff_id(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-13"}])
    for fmt in ("tsv", "md"):
        r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "doctor", "--format", fmt)
        assert "t3s-13" in r.stdout, _out(r)
        plain = _run(tmp_path, b, "--allow-t3", "doctor", "--format", fmt)
        assert "t3s-13" not in plain.stdout and "signoff_id" not in plain.stdout  # off: output unchanged


# --- review round 2: evidence for each fixed finding (synthetic records only) ---

def _raw_bundle(tmp_path, body):
    d = tmp_path / "bundle" / "decisions"
    d.mkdir(parents=True)
    (d / "t3-signoffs.yaml").write_text("signoffs:\n" + body, encoding="utf-8")
    return tmp_path / "bundle"


def test_doctor_without_allow_t3_still_reports_hold_under_the_flag(tmp_path):
    r = _run(tmp_path, _bundle(tmp_path, []), "--require-t3-signoff", "doctor", "--format", "json")
    assert r.returncode in (0, 1) and "t3-signoff:missing" not in _out(r), _out(r)
    assert "hold" in _out(r)


def test_qualified_scope_for_another_owner_refuses(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-4", "repos": ["Other-Org/northwind-synthetic"]}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:scope" in _out(r), _out(r)


def test_garbage_expiry_never_validates(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-5", "expires": "2099-12-31garbage"}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:expired" in _out(r), _out(r)


def test_malformed_repos_refuses_instead_of_raising(tmp_path):
    b = _raw_bundle(tmp_path, f"  - id: t3s-6\n    owner: {OWNER}\n    repos: 7\n    approved: true\n    expires: 2099-12-31\n")
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:scope" in _out(r) and "Traceback" not in _out(r), _out(r)


def test_adopt_and_content_links_honour_repo_scoped_record(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-7", "repos": ["northwind-synthetic"]}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "adopt", f"{OWNER}/northwind-synthetic")
    assert "t3-signoff" not in _out(r), _out(r)


def test_report_jobs_carry_signoff_id(tmp_path):
    from ctshowcase import signoff
    signoff.reset()
    signoff.set_required(True)
    try:
        rec = {"id": "t3s-8", "owner": OWNER, "repos": ["*"], "approved": True, "expires": "2099-12-31"}
        signoff._GRANTED[OWNER.lower()] = [rec]
        from ctshowcase.content import _finish
        import argparse
        rp = tmp_path / "report.json"
        _finish(argparse.Namespace(jobs=None, report=str(rp)),
                {"job": {"phase": 3, "org": OWNER, "repo": f"{OWNER}/northwind-synthetic"}}, 0)
        saved = json.loads(rp.read_text(encoding="utf-8"))["job"]
        assert saved["signoff_id"] == "t3s-8" and saved["approval_id"] == "t3s-8"
    finally:
        signoff.set_required(False)
        signoff.reset()
