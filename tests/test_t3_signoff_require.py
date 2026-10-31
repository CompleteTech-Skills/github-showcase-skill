"""`--require-t3-signoff` (issue 23): `--allow-t3` needs a valid, unexpired sign-off record in the file named by
`--t3-signoff-file` (env SHOWCASE_T3_SIGNOFF_FILE) or, by default, in the private estate bundle
(`<estate root>/decisions/t3-signoffs.yaml`; tests/test_t3_signoff_default.py). The enforcement is default-on; the tests
there is no opt-out (tests/test_t3_signoff_default.py::test_there_is_no_opt_out).

Synthetic records only (owner Pick-Your-AI is the brand.yaml T3 owner; the ids and dates are made up). The existing
tests/test_allow_t3_global.py pins the refusals without `--allow-t3`; it only gained the record-file environment that
`--allow-t3` now needs.
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
        lines.append(f"    approver: {r.get('approver', 'synthetic-co-owner')}")
        lines.append(f"    approved_on: {r.get('approved_on', '1990-01-01')}")
        lines.append(f"    expires: {r.get('expires', '2099-12-31')}")
    (d / "t3-signoffs.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path / "bundle"


def _run(tmp_path, bundle, *argv, owner=OWNER, env=None, meta_extra=None):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner=owner, repo="northwind-synthetic", **(meta_extra or {}))),
                    encoding="utf-8")
    e = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(bundle))
    e.pop("SHOWCASE_T3_SIGNOFF_FILE", None)
    e.update(env or {})
    rec = ["--t3-signoff-file", str(_file(bundle))] if bundle is not None else []
    return subprocess.run([*SHOWCASE, "--meta", str(meta), "--no-repo-dir", *rec, *argv], cwd=ROOT, env=e,
                          capture_output=True, text=True, encoding="utf-8")


def _file(bundle):
    return Path(bundle) / "decisions" / "t3-signoffs.yaml"


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
    plain = _run(tmp_path, b, "doctor", "--format", "json")
    assert "signoff_id" not in json.loads(plain.stdout)  # without --allow-t3 the row is unchanged


def test_writer_jobs_carry_the_signoff_id(tmp_path):
    from ctshowcase import signoff
    from ctshowcase.records import append
    rec = {"id": "t3s-8", "owner": OWNER, "repos": ["*"], "approved": True, "expires": "2099-12-31"}
    try:
        signoff._grant(OWNER.lower(), rec)
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
        signoff.reset()


def test_state_does_not_outlive_the_invocation(tmp_path, capsys):
    from ctshowcase import signoff
    import showcase
    before = signoff.record_file()
    showcase.main(["--t3-signoff-file", "elsewhere.yaml", "config"])
    capsys.readouterr()
    assert signoff.record_file() == before and not signoff._granted()  # the file held for that call only


@pytest.mark.parametrize("repo,expect", [(None, "scope"), ("a", None), ("B", None), ("c", "scope")])
def test_evaluate_scope_rules(repo, expect):
    from ctshowcase import signoff
    recs = [{"id": "s", "owner": OWNER, "repos": ["a", f"{OWNER}/b"], "approved": True, "approver": "x",
             "approved_on": "2026-01-01", "expires": "2099-01-01"}]
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
    rec = {"owner": OWNER, "repos": ["*"], "approved": True, "approver": "x", "approved_on": "2026-01-01",
           "expires": "2099-12-31"}
    # a record with no usable id breaks the schema: refused as invalid (it never authorizes), not silently missing
    assert signoff.evaluate([OWNER], None, records=[rec])[0] is None
    assert signoff.evaluate([OWNER], None, records=[rec])[1].startswith("invalid:")
    assert signoff.evaluate([OWNER], None, records=[dict(rec, id="  ")])[1].startswith("invalid:")
    assert signoff.evaluate([OWNER], None, records=[dict(rec, id="t3s-1")])[1] is None


def test_alias_record_matches_every_later_check(tmp_path, monkeypatch):
    """A record under a former login must satisfy the secondary helpers (config/org/project/doctor), not just the gate."""
    from ctshowcase import signoff
    from ctshowcase.config import set_t3_signed_off, t3_signed_off
    from ctshowcase.org import _t3_granted as org_granted
    b = _bundle(tmp_path, [{"id": "t3s-10", "owner": "Old-Login"}])
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(_file(b)))
    set_t3_signed_off(True)
    try:
        assert not t3_signed_off("New-Login")  # nothing links the logins yet
        signoff.register_aliases(["New-Login", "Old-Login"])  # what Resolver.aliases does under the flag
        assert t3_signed_off("New-Login") and org_granted("New-Login")
        assert signoff.record("New-Login")["id"] == "t3s-10"  # what project.estate_orgs asks
    finally:
        set_t3_signed_off(False)
        signoff.reset()


def test_project_gate_registers_the_grant_and_reports_the_reason(tmp_path, monkeypatch):
    from ctshowcase import signoff
    from ctshowcase.errors import Refused
    from ctshowcase.project import _gate_target
    from ctshowcase.resolver import Resolver
    from ctshowcase.config import Brand
    brand = Brand({"owners": {"t3": [OWNER]}}, ROOT / "references" / "brand.yaml")
    resolver = Resolver(brand, {}, None)
    try:
        monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(_file(_bundle(tmp_path / "ok", [{"id": "t3s-11"}]))))
        assert _gate_target(resolver, OWNER, allow_t3=True) == OWNER
        assert signoff.record_for(OWNER, None)["id"] == "t3s-11"  # so stamp() can put it on the writer job
        signoff.reset()
        monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(_file(_bundle(tmp_path / "old", [{"id": "t3s-12", "expires": "2000-01-01"}]))))
        with pytest.raises(Refused) as exc:
            _gate_target(resolver, OWNER, allow_t3=True)
        assert exc.value.log == "t3-signoff:expired"
    finally:
        signoff.reset()


def test_default_doctor_renderers_show_the_signoff_id(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-13"}])
    for fmt in ("tsv", "md"):
        r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "doctor", "--format", fmt)
        assert "t3s-13" in r.stdout, _out(r)
        plain = _run(tmp_path, b, "doctor", "--format", fmt)
        assert "t3s-13" not in plain.stdout and "signoff_id" not in plain.stdout  # no --allow-t3: output unchanged


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
    assert r.returncode == 2 and "t3-signoff:invalid" in _out(r) and "expires" in _out(r), _out(r)


def test_malformed_repos_refuses_instead_of_raising(tmp_path):
    b = _raw_bundle(tmp_path, f"  - id: t3s-6\n    owner: {OWNER}\n    repos: 7\n    approved: true\n"
                              "    approver: x\n    approved_on: 2026-01-01\n    expires: 2099-12-31\n")
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:invalid" in _out(r) and "repos" in _out(r), _out(r)
    assert "Traceback" not in _out(r), _out(r)


def test_adopt_and_content_links_honour_repo_scoped_record(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-7", "repos": ["northwind-synthetic"]}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "adopt", f"{OWNER}/northwind-synthetic")
    assert "t3-signoff" not in _out(r), _out(r)


def test_report_jobs_carry_signoff_id(tmp_path):
    from ctshowcase import signoff
    signoff.reset()
    try:
        rec = {"id": "t3s-8", "owner": OWNER, "repos": ["*"], "approved": True, "expires": "2099-12-31"}
        signoff._grant(OWNER.lower(), rec)
        from ctshowcase.content import _finish
        import argparse
        rp = tmp_path / "report.json"
        _finish(argparse.Namespace(jobs=None, report=str(rp)),
                {"job": {"phase": 3, "org": OWNER, "repo": f"{OWNER}/northwind-synthetic"}}, 0)
        saved = json.loads(rp.read_text(encoding="utf-8"))["job"]
        assert saved["signoff_id"] == "t3s-8" and saved["approval_id"] == "t3s-8"
    finally:
        signoff.reset()


# --- review round 3 ---

def test_hold_owner_is_refused_even_with_a_record(tmp_path, monkeypatch):
    """No shipped owner is on HOLD, so build one in-process: a valid `*` record must not lift hold (Brand and Resolver)."""
    from ctshowcase import signoff
    from ctshowcase.config import Brand
    from ctshowcase.errors import Refused
    from ctshowcase.resolver import Resolver
    brand = Brand({"owners": {"hold": ["Held-Co"]}}, ROOT / "references" / "brand.yaml")
    resolver = Resolver(brand, {}, None)
    b = _bundle(tmp_path, [{"id": "t3s-h", "owner": "Held-Co", "repos": ["*"]}])
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(_file(b)))
    try:
        for check in (brand.check_owner, resolver.check_owner):
            with pytest.raises(Refused) as exc:
                check("Held-Co", allow_t3=True)
            assert exc.value.log == "hold"
    finally:
        signoff.reset()


@pytest.mark.parametrize("body", ["signoffs: 7\n", "signoffs: [unclosed\n", "- not: [valid\n"])
def test_malformed_signoff_file_refuses_instead_of_raising(tmp_path, body):
    d = tmp_path / "bundle" / "decisions"
    d.mkdir(parents=True)
    (d / "t3-signoffs.yaml").write_text(body, encoding="utf-8")
    r = _run(tmp_path, tmp_path / "bundle", "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:missing" in _out(r) and "Traceback" not in _out(r), _out(r)


@pytest.mark.parametrize("records,why", [([], "missing"), ([{"id": "t3s-x", "expires": "2000-01-01"}], "expired")])
def test_keyed_sidebar_batch_does_not_swallow_signoff_refusals(tmp_path, records, why):
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({f"{OWNER}/northwind-synthetic": {}}), encoding="utf-8")
    r = _run(tmp_path, _bundle(tmp_path, records), "--require-t3-signoff", "--allow-t3",
             "content", "sidebar", "--facts", str(facts))
    assert r.returncode == 2 and f"t3-signoff:{why}" in _out(r), _out(r)


# --- epic 22 integration: sign-off state is context-local, like --allow-t3 (issue 28) ---

def test_signoff_state_is_context_local(tmp_path, monkeypatch):
    """Issue 28 made `--allow-t3` a ContextVar; issue 23's grants and aliases must follow, or one thread's grant
    stamps (or authorizes) another thread's run. Both threads hold `--allow-t3` and the bundle has no record; only
    `holder` registers a grant. With module globals `plain` would see `holder`'s grant."""
    import threading
    from ctshowcase import signoff
    from ctshowcase.config import Brand, reset_t3_signed_off, set_t3_signed_off
    from ctshowcase.errors import Refused
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(_file(_bundle(tmp_path, []))))
    brand = Brand({"owners": {"t3": [OWNER]}}, ROOT / "references" / "brand.yaml")
    barrier = threading.Barrier(2, timeout=10)
    out: dict[str, tuple] = {}

    def worker(name, holder):
        t3 = set_t3_signed_off(True)
        run = signoff.reset()
        try:
            if holder:
                signoff._grant("someone-else", {"id": "t3s-lax"})
            barrier.wait()  # both states are live at once
            try:
                result = ("passed", brand.check_owner(OWNER, allow_t3=True))
            except Refused as exc:
                result = ("refused", exc.log)
            barrier.wait()  # neither resets until both have checked
            out[name] = (*result, sorted(signoff._granted()))
        finally:
            signoff.restore(run)
            reset_t3_signed_off(t3)

    threads = [threading.Thread(target=worker, args=("plain", False)),
               threading.Thread(target=worker, args=("holder", True))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert out["plain"] == ("refused", "t3-signoff:missing", []), out
    assert out["holder"] == ("refused", "t3-signoff:missing", ["someone-else"]), out


def test_main_restores_an_enclosing_runs_signoff_state(tmp_path, capsys):
    """A nested showcase.main() (an in-process caller) must not clear the caller's grants or record file."""
    from ctshowcase import signoff
    import showcase
    run = signoff.reset()
    file = signoff.set_file("outer-file.yaml")
    try:
        signoff._grant("outer", {"id": "t3s-outer"})
        showcase.main(["config"])
        capsys.readouterr()
        assert signoff.explicit_file() == Path("outer-file.yaml")
        assert signoff._granted() == {"outer": ({"id": "t3s-outer"},)}
    finally:
        signoff.reset_file(file)
        signoff.restore(run)


# --- review round 4: explicit record file, record schema, timestamp expiry, copy-on-write state, change records ---

def test_no_record_file_refuses_and_names_the_resolved_path(tmp_path):
    """Nothing at the default path and no explicit file: the gate refuses t3-signoff:no-file and names the path it
    resolved (the estate default). It never creates the file and never falls back to trusting --allow-t3."""
    root = tmp_path / "bundle"
    (root / "decisions").mkdir(parents=True)
    r = _run(tmp_path, None, "--allow-t3", "describe", env={"SHOWCASE_ESTATE_ROOT": str(root)})
    want = root / "decisions" / "t3-signoffs.yaml"
    assert r.returncode == 2 and "t3-signoff:no-file" in _out(r), _out(r)
    assert str(want) in json.loads(r.stdout)["error"], r.stdout
    assert not want.exists()


def test_record_file_may_have_any_name_and_come_from_env(tmp_path):
    src = _file(_bundle(tmp_path, [{"id": "t3s-env"}]))
    chosen = tmp_path / "elsewhere" / "my-approved-actions.yaml"
    chosen.parent.mkdir()
    chosen.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    r = _run(tmp_path, None, "--require-t3-signoff", "--allow-t3", "describe",
             env={"SHOWCASE_ESTATE_ROOT": str(tmp_path / "nowhere"), "SHOWCASE_T3_SIGNOFF_FILE": str(chosen)})
    assert r.returncode != 2 and "t3-signoff" not in _out(r), _out(r)


@pytest.mark.parametrize("expires,why", [
    ("2026-10-30T00:00:00+00:00", "expired"),   # same calendar day, but the instant has passed
    ("2026-10-30T12:43:59Z", "expired"),
    ("2026-10-30T12:45:00+00:00", None),
    ("2026-10-30T14:00:00+02:00", "expired"),   # 12:00Z
    ("2026-10-30", None),                       # a date is valid through that whole day (inclusive)
    ("2026-10-29", "expired"),
])
def test_timestamp_expiry_is_compared_as_an_instant(expires, why):
    import datetime as dt
    from ctshowcase import signoff
    now = dt.datetime(2026, 10, 30, 12, 44, tzinfo=dt.timezone.utc)
    rec = {"id": "t", "owner": OWNER, "repos": ["*"], "approved": True, "approver": "x", "approved_on": "2026-01-01",
           "expires": expires}
    assert signoff.evaluate([OWNER], None, records=[rec], now=now)[1] == why
    aware = dt.datetime(2026, 10, 30, 0, 0, tzinfo=dt.timezone.utc)  # what YAML yields for an unquoted timestamp
    assert signoff.evaluate([OWNER], None, records=[dict(rec, expires=aware)], now=now)[1] == "expired"


def test_naive_timestamp_expiry_is_invalid():
    import datetime as dt
    from ctshowcase import signoff
    rec = {"id": "t", "owner": OWNER, "repos": ["*"], "approved": True, "approver": "x", "approved_on": "2026-01-01"}
    for naive in ("2099-12-31T00:00:00", dt.datetime(2099, 12, 31)):
        assert signoff.evaluate([OWNER], None, records=[dict(rec, expires=naive)])[1].startswith("invalid:")


@pytest.mark.parametrize("drop", ["approver", "approved_on"])
def test_audit_fields_are_required(tmp_path, drop):
    body = (f"  - id: t3s-a\n    owner: {OWNER}\n    repos: ['*']\n    approved: true\n"
            "    approver: x\n    approved_on: 2026-01-01\n    expires: 2099-12-31\n")
    body = "\n".join(line for line in body.split("\n") if not line.strip().startswith(drop + ":"))
    r = _run(tmp_path, _raw_bundle(tmp_path, body), "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:invalid" in _out(r) and drop in _out(r), _out(r)


def test_approved_as_a_string_is_reported_invalid_not_missing(tmp_path):
    body = (f"  - id: t3s-s\n    owner: {OWNER}\n    repos: ['*']\n    approved: 'true'\n"
            "    approver: x\n    approved_on: 2026-01-01\n    expires: 2099-12-31\n")
    r = _run(tmp_path, _raw_bundle(tmp_path, body), "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:invalid" in _out(r) and "t3s-s" in _out(r), _out(r)


def _iso(v):
    import datetime as dt
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _iso(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_iso(x) for x in v]
    return v


def test_schema_and_problems_agree_on_the_fixtures():
    """references/t3-signoff.schema.json is the contract; signoff.problems() must accept and reject the same records.
    jsonschema is not a runtime dependency, so the schema half runs only where it is installed."""
    import yaml
    from ctshowcase import signoff
    fix = ROOT / "tests" / "fixtures" / "t3-signoff"
    valid = yaml.safe_load((fix / "valid.yaml").read_text(encoding="utf-8"))
    invalid = yaml.safe_load((fix / "invalid.yaml").read_text(encoding="utf-8"))
    assert all(signoff.problems(r) == [] for r in valid["signoffs"]), [signoff.problems(r) for r in valid["signoffs"]]
    assert all(len(signoff.problems(r)) == 1 for r in invalid["signoffs"]), [signoff.problems(r) for r in invalid["signoffs"]]
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "references" / "t3-signoff.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_iso(valid), schema)
    for rec in invalid["signoffs"]:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"signoffs": [_iso(rec)]}, schema)


def test_topics_change_records_carry_the_signoff_id(tmp_path):
    """#26: change records (records.record(), no `phase`) carry signoff_id, and no approval_id (not a writer job)."""
    b = _bundle(tmp_path, [{"id": "t3s-cr"}])
    out = tmp_path / "rec.jsonl"
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "topics", "--records", str(out))
    assert "t3-signoff" not in _out(r) and out.is_file(), _out(r)
    recs = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert recs and all(x["signoff_id"] == "t3s-cr" and "approval_id" not in x for x in recs), recs


def test_adopt_json_output_stamps_change_records_and_jobs(tmp_path):
    b = _bundle(tmp_path, [{"id": "t3s-ad"}])
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "adopt", f"{OWNER}/northwind-synthetic")
    obj = json.loads(r.stdout)
    assert obj.get("records") and all(x.get("signoff_id") == "t3s-ad" for x in obj["records"]), obj.get("records")
    assert all(x.get("signoff_id") == "t3s-ad" for x in obj.get("jobs") or []), obj.get("jobs")


def test_child_context_grant_does_not_leak_into_parent(tmp_path, monkeypatch):
    """An asyncio task inherits the parent's context. Before copy-on-write the inherited (granted, aliases) dicts were
    shared, so a signed child's grant stayed in the unsigned parent and stamp() put the child's id on its jobs."""
    import asyncio
    from ctshowcase import signoff
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(_file(_bundle(tmp_path, [{"id": "t3s-child"}]))))

    async def child():
        signoff.require(OWNER)
        signoff.register_aliases([OWNER, "Old-Login"])
        return signoff.record_for(OWNER)["id"]

    async def parent():
        signoff.reset()  # the parent's state exists before the child starts, so the child inherits it
        got = await asyncio.create_task(child())
        job = {"id": "j", "phase": "p", "kind": "k", "repo": f"{OWNER}/x", "argv": []}
        signoff.stamp([job])
        return got, signoff._granted(), signoff._aliases(), job

    got, grants, aliases, job = asyncio.run(parent())
    assert got == "t3s-child"
    assert grants == {} and aliases == {} and "signoff_id" not in job and "approval_id" not in job


def test_star_list_jobs_for_a_t3_org_carry_its_signoff(tmp_path, monkeypatch, brand):
    """`org pins` for a T3 org plans its star-List jobs on the personal account (org=CompleteDotTech); the grant is the
    org's, so target-based stamping missed them. star_list_plan now passes the gated owner explicitly."""
    from ctshowcase import org as O, signoff
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off
    from ctshowcase.resolver import Resolver
    fix = ROOT / "tests" / "fixtures" / "org"
    reg = {"orgs": {OWNER: {"star_list": {"name": "Pick Your AI: built on", "description": "x"}, "favorites": []}}}
    est = O.Estate(brand, Resolver(brand, reg, {"rows": set(), "ids": set(), "answers": {}, "actions": [], "extra": []}))
    lists = json.loads((fix / "star-lists.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(_file(_bundle(tmp_path, [{"id": "t3s-sl"}]))))
    t3 = set_t3_signed_off(True)
    run = signoff.reset()
    try:
        signoff.require(OWNER)
        res = O.star_list_plan(est, OWNER, lists_capture=lists, allow_t3=True)
        assert res["jobs"] and all(j["org"] == O.USER_LOGIN for j in res["jobs"]), res
        assert all(j["signoff_id"] == "t3s-sl" and j["approval_id"] == "t3s-sl" for j in res["jobs"]), res["jobs"]
    finally:
        signoff.restore(run)
        reset_t3_signed_off(t3)


# --- review round 3: evidence for each fixed finding (synthetic records only) ---

def _schema_def(name):
    return json.loads((ROOT / "references" / "t3-signoff.schema.json").read_text(encoding="utf-8"))["$defs"][name]


def _schema_accepts(value, *defs):
    """The schema's own string patterns (ECMA-262: `^...$` anchored, ASCII digits), applied with `re` so this runs
    where jsonschema is not installed (test_schema_and_problems_agree_on_the_fixtures skips there)."""
    import re
    return any(re.search(_schema_def(d)["pattern"], value, re.ASCII) and not value.endswith("\n") for d in defs)


_WHEN = ["2099-12-31", "20991231", "2099-W52-1", "2099-W52", "2099-365", " 2099-12-31", "2099-12-31 ",
         "2099-12-31T00:00:00Z", "2099-12-31T00:00:00+00:00", "2099-12-31T00:00:00+0000", "2099-12-31 00:00Z",
         "2099-12-31T00:00:00.5-05:00", "2099-12-31T00:00+00", "2099-12-31T00Z", "20991231T000000Z",
         "2099-12-31T00:00:00", "2099-12-31garbage", "\u0662\u0660\u0669\u0669-12-31"]


@pytest.mark.parametrize("value", _WHEN)
def test_problems_follow_the_schema_string_patterns(value):
    """Python 3.11+ fromisoformat accepts compact, week-date and `+00` forms the schema rejects; problems() used to
    accept them, so --require-t3-signoff granted a record the published schema refuses. Both now agree."""
    from ctshowcase import signoff
    base = {"id": "t3s-p", "owner": OWNER, "repos": "*", "approved": True, "approver": "x",
            "approved_on": "2026-01-15", "expires": "2099-12-31"}
    exp_ok = not any(p.startswith("expires:") for p in signoff.problems(dict(base, expires=value)))
    assert exp_ok == _schema_accepts(value, "date", "awareTimestamp"), value
    on_ok = not any(p.startswith("approved_on:") and "in the future" not in p  # the future rule is not a schema rule
                    for p in signoff.problems(dict(base, approved_on=value)))
    assert on_ok == _schema_accepts(value, "date"), value


def test_calendar_impossible_dates_fail_closed_although_the_pattern_matches():
    """The one deliberate difference from the schema: a pattern-shaped but impossible date never validates."""
    from ctshowcase import signoff
    assert _schema_accepts("2099-02-30", "date")
    rec = {"id": "t3s-c", "owner": OWNER, "repos": "*", "approved": True, "approver": "x",
           "approved_on": "2026-01-15", "expires": "2099-02-30"}
    assert signoff.problems(rec) == ["expires: needs a date (YYYY-MM-DD) or a timestamp with a UTC offset"]


@pytest.mark.parametrize("field,value", [("expires", "20991231"), ("expires", "2099-W52-1"),
                                         ("approved_on", "20260115")])
def test_compact_and_week_dates_refuse_invalid(tmp_path, field, value):
    vals = {"approved_on": "2026-01-15", "expires": "2099-12-31", field: value}
    body = (f"  - id: t3s-cmp\n    owner: {OWNER}\n    repos: ['*']\n    approved: true\n    approver: x\n"
            f"    approved_on: '{vals['approved_on']}'\n    expires: '{vals['expires']}'\n")
    r = _run(tmp_path, _raw_bundle(tmp_path, body), "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:invalid" in _out(r) and field in _out(r), _out(r)


def test_mixed_type_unknown_keys_refuse_invalid(tmp_path):
    """`unexpected: true` beside `7: unexpected`: sorting str and int keys raised TypeError out of showcase.main()."""
    body = (f"  - id: t3s-mix\n    owner: {OWNER}\n    repos: ['*']\n    approved: true\n    approver: x\n"
            "    approved_on: 2026-01-15\n    expires: 2099-12-31\n    unexpected: true\n    7: unexpected\n")
    r = _run(tmp_path, _raw_bundle(tmp_path, body), "--require-t3-signoff", "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:invalid" in _out(r) and "unknown field" in _out(r), _out(r)
    assert "Traceback" not in _out(r), _out(r)


def test_t1_star_list_item_for_a_t3_favorite_carries_the_favorites_signoff(tmp_path, monkeypatch, brand):
    """A T1 org's List featuring a T3 org's repository: the favorite passed _t3_held via granted(), which registers no
    grant, and star_list_plan stamped only the T1 org, so the updateUserListsForItem job had no signoff_id."""
    from ctshowcase import org as O, signoff
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off
    from ctshowcase.resolver import Resolver
    t1, fav = "Northwind-Trading-Co", f"{OWNER}/northwind-synthetic"
    reg = {"orgs": {t1: {"star_list": {"name": "Misc", "description": ""}, "favorites": [{"full_name": fav}]}}}
    est = O.Estate(brand, Resolver(brand, reg, {"rows": set(), "ids": set(), "answers": {}, "actions": [], "extra": []}),
                   metas={"m": {"owner": OWNER, "repo": "northwind-synthetic", "visibility": "public"}})
    lists = json.loads((ROOT / "tests" / "fixtures" / "org" / "star-lists.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE",
                       str(_file(_bundle(tmp_path, [{"id": "t3s-fav", "repos": ["northwind-synthetic"]}]))))
    t3 = set_t3_signed_off(True)
    run = signoff.reset()
    try:
        assert est.resolver.owner_status(t1) != "t3"
        res = O.star_list_plan(est, t1, lists_capture=lists, allow_t3=True, repo_ids={fav: "R_synthetic"})
        items = [j for j in res["jobs"] if "list-item" in j["id"]]
        assert len(items) == 1 and items[0]["org"] == O.USER_LOGIN, res
        assert items[0]["signoff_id"] == "t3s-fav" and items[0]["approval_id"] == "t3s-fav", items
    finally:
        signoff.restore(run)
        reset_t3_signed_off(t3)


# --- review round 4: evidence for each fixed finding (synthetic records and slugs only) ---

T1 = "CompleteTech-Skills"  # a brand.yaml T1 org; the transfer below is synthetic


def _transfer_estate(brand, favorites=()):
    """A synthetic approved pending transfer: the registry homes northwind-member in T1, but the repository is still
    held by the T3 org (Pick-Your-AI) and its metadata was captured there, so estate.current() resolves to the T3 org."""
    from ctshowcase import labels as L, org as O
    from ctshowcase.resolver import Resolver
    approvals = {"rows": set(), "ids": {"mv-synthetic"}, "answers": {}, "extra": [], "actions": [
        {"id": "mv-synthetic", "action": "transfer", "owner": OWNER, "repo": "northwind-member", "target_owner": T1}]}
    labels = [dict(lb) for lb in L.standard_labels()][:-2]  # two standard labels missing: create jobs are planned
    reg = {"orgs": {T1: {"final_repos": ["northwind-member"], "favorites": [{"full_name": f} for f in favorites],
                         "star_list": {"name": "Misc", "description": ""}}}}
    est = O.Estate(brand, Resolver(brand, reg, approvals), {"m": {
        "owner": OWNER, "repo": "northwind-member", "visibility": "public", "labels": labels, "has_issues": True,
        "files": [], "files_complete": True}})
    assert est.current(f"{T1}/northwind-member") == f"{OWNER}/northwind-member"
    return est, reg


class _Strict:
    """`--allow-t3` (unless allow_t3=False) plus `--require-t3-signoff` in this context, reading the given file."""

    def __init__(self, monkeypatch, path, allow_t3=True):
        self.monkeypatch, self.path, self.allow_t3 = monkeypatch, path, allow_t3

    def __enter__(self):
        from ctshowcase import signoff
        from ctshowcase.config import set_t3_signed_off
        self.monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(self.path))
        self.tokens = (set_t3_signed_off(self.allow_t3), signoff.reset())
        return self

    def __exit__(self, *exc):
        from ctshowcase import signoff
        from ctshowcase.config import reset_t3_signed_off
        t3, run = self.tokens
        signoff.restore(run)
        reset_t3_signed_off(t3)


def test_org_labels_gate_the_t3_owner_a_transfer_resolves_to(tmp_path, monkeypatch, brand):
    """`org labels CompleteTech-Skills` with a member whose approved pending transfer resolves to Pick-Your-AI: the
    label jobs target the T3 org, so they need its record. Before, the org gate only saw the T1 org, and an empty
    record file still produced `gh label create ... -R Pick-Your-AI/northwind-member` jobs with no signoff_id."""
    from ctshowcase import org as O, signoff
    est, _ = _transfer_estate(brand)
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "none", []))):
        res, _ = O.labels_plan(est, T1, allow_t3=True)
        assert not [j for j in res["jobs"] if f"{OWNER}/northwind-member" in j.get("argv", [])], res["jobs"]
        assert res["repos"] == [{"repo": f"{OWNER}/northwind-member", "result": "held", "log": "t3-signoff:missing"}]
        assert res["result"] == "incomplete", res
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "ok", [{"id": "t3s-lbl", "repos": ["northwind-member"]}]))):
        res, _ = O.labels_plan(est, T1, allow_t3=True)
        jobs = [j for j in res["jobs"] if f"{OWNER}/northwind-member" in j.get("argv", [])]
        assert jobs, res
        signoff.stamp(jobs)  # showcase.main stamps every emitted job list the same way
        assert all(j["signoff_id"] == "t3s-lbl" for j in jobs), jobs
    # no --allow-t3: the base behaviour is kept (the transfer-target hold is opt-in via the T3 flag, not via the
    # default-on enforcement), so T1/T2 org output does not change
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "noflag", [{"id": "t3s-x"}])), allow_t3=False):
        res, _ = O.labels_plan(est, T1, allow_t3=False)
        assert res["result"] == "plan" and not [x for x in res["repos"] if x.get("result") == "held"], res


def test_favorite_transferred_to_a_t3_org_is_held_without_its_record(tmp_path, monkeypatch, brand):
    """A favorite named CompleteTech-Skills/northwind-member resolves to Pick-Your-AI/northwind-member. _t3_held
    checked only the named (T1) owner, so with an empty record file the favorite went public and `org pins` planned
    updateUserListsForItem for it, unstamped."""
    from ctshowcase import org as O
    fav = f"{T1}/northwind-member"
    est, reg = _transfer_estate(brand, favorites=[fav])
    lists = json.loads((ROOT / "tests" / "fixtures" / "org" / "star-lists.json").read_text(encoding="utf-8"))
    ids = {f"{OWNER}/northwind-member": "R_synthetic"}
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "none", []))):
        favs, logs = O.public_favorites(est, reg["orgs"][T1], allow_t3=True)
        assert favs == [] and logs == [f"t3-signoff:{fav}"], (favs, logs)
        plan = O.star_list_plan(est, T1, lists_capture=lists, allow_t3=True, repo_ids=ids)
        assert not [j for j in plan["jobs"] if "list-item" in j["id"]], plan["jobs"]
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "ok", [{"id": "t3s-fv", "repos": ["northwind-member"]}]))):
        favs, _ = O.public_favorites(est, reg["orgs"][T1], allow_t3=True)
        assert favs == [f"{OWNER}/northwind-member"], favs
        plan = O.star_list_plan(est, T1, lists_capture=lists, allow_t3=True, repo_ids=ids)
        items = [j for j in plan["jobs"] if "list-item" in j["id"]]
        assert len(items) == 1 and items[0]["signoff_id"] == "t3s-fv", plan["jobs"]


def test_t3_also_in_association_carries_its_signoff_id(tmp_path):
    """`topics --also-in Pick-Your-AI --records` on a T1 repository: the record that let the T3 membership topic in
    is named on the change record. Before, granted() verified it without keeping it and stamp() looked only at the T1
    target owner, so the change record that adds the T3 topic had no signoff_id."""
    from ctshowcase.config import load_brand
    from ctshowcase.topics import org_topic
    topic = org_topic(load_brand(), OWNER)[1]
    assert topic
    b = _bundle(tmp_path, [{"id": "t3s-assoc"}])
    out = tmp_path / "rec.jsonl"
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "topics", "--also-in", OWNER, "--records", str(out),
             owner=T1)
    obj = json.loads(r.stdout)
    assert topic in obj["proposed"] and obj.get("signoff_ids") == ["t3s-assoc"], _out(r)
    recs = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert len(recs) == 1 and recs[0]["owner"] == T1 and topic in recs[0]["after"], recs
    assert recs[0]["signoff_id"] == "t3s-assoc" and "approval_id" not in recs[0], recs


_GOOD = {"id": "t3s-env", "owner": OWNER, "repos": ["*"], "approved": True, "approver": "synthetic-co-owner",
         "approved_on": "2026-01-15", "expires": "2099-12-31"}


@pytest.mark.parametrize("doc,ok", [
    ({"signoffs": [_GOOD]}, True),
    ([_GOOD], False),                                # top-level list (schema: type object)
    ({"signoffs": [_GOOD], "extra": True}, False),    # unsupported top-level key (additionalProperties false)
    ({"signoffs": [_GOOD, "t3s-scalar"]}, False),     # a non-object entry (items: record)
    ({"signoffs": _GOOD}, False),                     # signoffs not an array
    ({}, False),                                      # signoffs missing (required)
])
def test_file_envelope_follows_the_schema(tmp_path, doc, ok):
    """The record file's envelope is checked before any record is read: a structure the published schema refuses
    authorizes nothing (t3-signoff:missing, like unparsable YAML). Before, a top-level list or an extra top-level key
    still granted --allow-t3 (exit 0)."""
    d = tmp_path / "bundle" / "decisions"
    d.mkdir(parents=True)
    (d / "t3-signoffs.yaml").write_text(json.dumps(doc), encoding="utf-8")  # JSON is YAML
    r = _run(tmp_path, tmp_path / "bundle", "--require-t3-signoff", "--allow-t3", "describe")
    if ok:
        assert r.returncode != 2 and "t3-signoff" not in _out(r), _out(r)
    else:
        assert r.returncode == 2 and "t3-signoff:missing" in _out(r) and "Traceback" not in _out(r), _out(r)
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "references" / "t3-signoff.schema.json").read_text(encoding="utf-8"))
    assert jsonschema.Draft202012Validator(schema).is_valid(doc) is ok


# --- review round 4: evidence for each fixed finding (synthetic records only) ---

def test_transfer_to_a_t3_org_is_unchanged_without_the_flag(monkeypatch, brand):
    """Enforcement is always on; with no --allow-t3: a T1 member whose approved pending transfer resolves to the T3 org keeps
    the base (2be04ac) behaviour. `org labels` plans its label jobs and the favorite and home entry stay public,
    exactly as before this epic. The transfer-target T3 checks (org._t3_moved_held, the labels_plan gate) belong to
    --allow-t3 only (enforcement defaulting on changes nothing here): no issue of epic #22 (#31, #28, #23-#27) asks for a default-on tightening."""
    from ctshowcase import org as O
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)
    fav = f"{T1}/northwind-member"
    est, reg = _transfer_estate(brand, favorites=[fav])
    t3 = set_t3_signed_off(False)
    try:
        res, _ = O.labels_plan(est, T1, allow_t3=False)
        assert res["result"] == "plan" and not [x for x in res["repos"] if x.get("result") == "held"], res
        assert [j for j in res["jobs"] if f"{OWNER}/northwind-member" in j.get("argv", [])], res["jobs"]
        favs, logs = O.public_favorites(est, reg["orgs"][T1], allow_t3=False)
        assert favs == [f"{OWNER}/northwind-member"] and not logs, (favs, logs)
        data, logs = O.public_slice(est, T1, allow_t3=False)
        assert f"{OWNER}/northwind-member" in json.dumps(data), data
        assert not any(x.startswith("t3-signoff") for x in logs), logs
    finally:
        reset_t3_signed_off(t3)


def test_home_repository_held_by_a_t3_org_is_omitted_without_its_record(tmp_path, monkeypatch, brand):
    """`org profile CompleteTech-Skills` under --require-t3-signoff: northwind-member is homed in the T1 org but the
    T3 org holds it today. public_slice built its home list through estate.is_public only, so with no record the
    profile README and data still named Pick-Your-AI/northwind-member (featured and sections)."""
    from ctshowcase import org as O
    est, reg = _transfer_estate(brand)
    reg["orgs"][T1].update(pins_public=["northwind-member"], sections=[{"title": "Tools", "repos": ["northwind-member"]}])
    full = f"{OWNER}/northwind-member"
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "none", []))):
        data, logs = O.public_slice(est, T1, allow_t3=True)
        assert full not in json.dumps(data) and f"t3-signoff:{full}" in logs, (data, logs)
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "ok", [{"id": "t3s-home", "repos": ["northwind-member"]}]))):
        data, logs = O.public_slice(est, T1, allow_t3=True)
        assert [e["full_name"] for e in data["featured"]] == [full], data
        assert f"t3-signoff:{full}" not in logs, logs
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "noflag", [{"id": "t3s-x"}])), allow_t3=False):
        data, logs = O.public_slice(est, T1, allow_t3=False)  # no --allow-t3: base behaviour, no transfer-target hold
        assert full in json.dumps(data) and f"t3-signoff:{full}" not in logs, (data, logs)


def test_adopt_topics_job_carries_the_also_in_signoff(tmp_path):
    """`adopt` of a T1 repository whose metadata has also_in: [Pick-Your-AI]: the topics PUT job and change record
    that add the T3 membership topic carry the T3 org's record. intake.adopt ignored topics.merge `signoff_ids`, and
    target-owner stamping only sees the T1 owner."""
    from ctshowcase.config import load_brand
    from ctshowcase.topics import org_topic
    topic = org_topic(load_brand(), OWNER)[1]
    b = _bundle(tmp_path, [{"id": "t3s-adopt"}])
    extra = {"also_in": [OWNER]}
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "adopt", f"{T1}/northwind-synthetic", owner=T1,
             meta_extra=extra)
    obj = json.loads(r.stdout)
    jobs = [j for j in obj["jobs"] if j["kind"] == "topics"]
    recs = [x for x in obj["records"] if x.get("kind") == "topics"]
    assert len(jobs) == 1 and any(topic in a for a in jobs[0]["argv"]), obj["jobs"]
    assert jobs[0]["signoff_id"] == "t3s-adopt" and jobs[0]["approval_id"] == "t3s-adopt", jobs
    assert recs and all(x["signoff_id"] == "t3s-adopt" and "approval_id" not in x for x in recs), obj["records"]
    # an existing approval_id on the job is kept
    r = _run(tmp_path, b, "--require-t3-signoff", "--allow-t3", "adopt", f"{T1}/northwind-synthetic",
             "--approval-id", "q-synthetic", owner=T1, meta_extra=extra)
    jobs = [j for j in json.loads(r.stdout)["jobs"] if j["kind"] == "topics"]
    assert jobs[0]["signoff_id"] == "t3s-adopt" and jobs[0]["approval_id"] == "q-synthetic", jobs


def test_estate_plan_jobs_carry_the_t3_orgs_signoff(tmp_path, monkeypatch, brand):
    """`project estate-plan --copied ...` with a signed-off T3 org in the registry: the Org-field job that brings
    Pick Your AI into the personal board carries its record. _t3_granted only checked the record and stamping by
    target owner looks at @me, so the job had neither signoff_id nor approval_id. Several T3 orgs on one job give
    signoff_ids (signoff.stamp_associations)."""
    from ctshowcase import project as PJ
    from ctshowcase.config import load_yaml_text
    from ctshowcase.resolver import Resolver
    reg = load_yaml_text((ROOT / "tests" / "fixtures" / "org" / "registry.yaml").read_text(encoding="utf-8"))
    reg["profile"]["org_directory"].append({"group": "T3", "orgs": [OWNER]})
    reg["orgs"][OWNER] = {}
    res = Resolver(brand, reg, {"rows": {("create-project", "@me", "*", "")}, "ids": set(), "answers": {},
                                "actions": [], "extra": []})
    cap = json.loads((ROOT / "tests" / "fixtures" / "project" / "estate-copy-capture.json").read_text(encoding="utf-8"))
    name = brand.raw["orgs"][OWNER]["display_name"]
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "ok", [{"id": "t3s-board"}]))):
        plan = PJ.estate_plan(res, copied=cap, user_id=100, allow_t3=True)
        t3 = [o for o in plan["orgs"] if o["login"] == OWNER]
        assert t3 and t3[0]["signoff_id"] == "t3s-board", plan["orgs"]
        named = [j for j in plan["jobs"] if OWNER in json.dumps(j) or name in json.dumps(j, ensure_ascii=False)]
        assert any(j["id"].endswith("-field-org") for j in named), plan["jobs"]
        assert all(j["signoff_id"] == "t3s-board" for j in named), named
        assert all("signoff_id" not in j for j in plan["jobs"] if j not in named), plan["jobs"]
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "none", []))):
        plan = PJ.estate_plan(res, copied=cap, user_id=100, allow_t3=True)
        assert OWNER not in [o["login"] for o in plan["orgs"]] and OWNER not in json.dumps(plan["jobs"])


# --- review round 5: evidence for each fixed finding (synthetic records and slugs only) ---

def test_estate_plan_stamping_matches_whole_names_not_substrings(tmp_path, monkeypatch):
    """A job that names `Acme Tools` / `Acme-Tools` must not be credited to a T3 org named `Acme`."""
    from ctshowcase import project as PJ
    orgs = [{"login": "Acme", "name": "Acme", "tier": "T3", "signoff_id": "t3s-acme"},
            {"login": "Acme-Tools", "name": "Acme Tools", "tier": "T1"}]
    jobs = [{"id": "other", "phase": 1, "argv": ["gh", "x", "name=Acme Tools"], "note": "Acme-Tools and Acme Tools"},
            {"id": "own", "phase": 1, "argv": ["gh", "api", "graphql", "-f", 'query=m { o: [{name: "Acme", description: "T3: Acme"}] }']},
            {"id": "plain", "phase": 1, "argv": ["gh", "x", "name=Acme"]}]
    with _Strict(monkeypatch, _file(_bundle(tmp_path, [{"id": "t3s-acme", "owner": "Acme"}]))):
        PJ._stamp_estate_orgs(jobs, orgs)
    got = {j["id"]: j.get("signoff_id") for j in jobs}
    assert got == {"other": None, "own": "t3s-acme", "plain": "t3s-acme"}, got
    assert "approval_id" not in jobs[0], jobs[0]


def test_pending_rename_is_gated_on_the_emitted_name(tmp_path, monkeypatch, brand):
    """A favorite named under its new name, while metadata and the emitted slug are the old name: a record scoped to
    the new name alone must not let the old name into public (same owner, so the transfer check skipped it)."""
    from ctshowcase import org as O
    from ctshowcase.resolver import Resolver
    fav = f"{OWNER}/new-name"
    approvals = {"rows": set(), "ids": {"rn-synthetic"}, "answers": {}, "extra": [], "actions": [
        {"id": "rn-synthetic", "action": "rename", "owner": OWNER, "repo": "old-name", "new_name": "new-name"}]}
    reg = {"orgs": {"Northwind-Trading-Co": {"favorites": [{"full_name": fav}],
                                             "star_list": {"name": "Misc", "description": ""}}}}
    est = O.Estate(brand, Resolver(brand, reg, approvals),
                   {"m": {"owner": OWNER, "repo": "old-name", "visibility": "public"}})
    assert est.current(fav) == f"{OWNER}/old-name"
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "new", [{"id": "t3s-new", "repos": ["new-name"]}]))):
        favs, logs = O.public_favorites(est, reg["orgs"]["Northwind-Trading-Co"], allow_t3=True)
        assert favs == [] and logs == [f"t3-signoff:{fav}"], (favs, logs)
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "both", [{"id": "t3s-both", "repos": ["new-name", "old-name"]}]))):
        favs, _ = O.public_favorites(est, reg["orgs"]["Northwind-Trading-Co"], allow_t3=True)
        assert favs == [f"{OWNER}/old-name"], favs
    favs, _ = O.public_favorites(est, reg["orgs"]["Northwind-Trading-Co"], allow_t3=True)  # flag off: unchanged
    assert favs == [f"{OWNER}/old-name"], favs


def test_record_for_follows_an_alias_registered_after_the_grant(tmp_path, monkeypatch):
    from ctshowcase import signoff
    with _Strict(monkeypatch, _file(_bundle(tmp_path, [{"id": "t3s-al"}]))):
        signoff.require(OWNER)
        assert signoff.record_for("Renamed-Org") is None
        signoff.register_aliases([OWNER, "Renamed-Org"])
        assert signoff.record_for("Renamed-Org")["id"] == "t3s-al"
        job = {"phase": 1, "org": "Renamed-Org"}
        assert signoff.stamp([job])[0]["signoff_id"] == "t3s-al"


def test_list_union_job_carries_the_signoff_of_a_t3_destination_list(tmp_path, monkeypatch, brand):
    """Two orgs share a public T1 favorite; `org pins` for the T1 org adds it to the T3 org's existing List as well.
    That membership needs the T3 org's record on the job."""
    from ctshowcase import org as O
    from ctshowcase.resolver import Resolver
    t1, fav = "Northwind-Trading-Co", "Northwind-Trading-Co/shared-synthetic"
    reg = {"orgs": {t1: {"favorites": [{"full_name": fav}], "star_list": {"name": "Misc", "description": ""}},
                    OWNER: {"favorites": [{"full_name": fav}], "star_list": {"name": "Built on", "description": ""}}}}
    est = O.Estate(brand, Resolver(brand, reg, {"rows": set(), "ids": set(), "answers": {}, "actions": [], "extra": []}),
                   {"m": {"owner": t1, "repo": "shared-synthetic", "visibility": "public"}})
    def lst(i, n):
        return {"id": i, "name": n, "slug": n.lower(), "description": "", "isPrivate": False,
                "items": {"totalCount": 0, "nodes": []}}
    lists = {"data": {"viewer": {"login": "x", "lists": {"totalCount": 2, "nodes": [lst("UL_t1", "Misc"), lst("UL_t3", "Built on")]}}}}
    ids = {fav: "R_shared"}
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "ok", [{"id": "t3s-dest"}]))):
        plan = O.star_list_plan(est, t1, lists_capture=lists, allow_t3=True, repo_ids=ids)
        items = [j for j in plan["jobs"] if "list-item" in j["id"]]
        assert len(items) == 1 and "UL_t3" in items[0]["argv"][-1], plan["jobs"]
        assert items[0]["signoff_id"] == "t3s-dest", items
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "none", [])), allow_t3=False):
        plan = O.star_list_plan(est, t1, lists_capture=lists, allow_t3=False, repo_ids=ids)
        items = [j for j in plan["jobs"] if "list-item" in j["id"]]
        assert items and "UL_t3" not in items[0]["argv"][-1] and "signoff_id" not in items[0], items


def test_t3_favorite_and_t3_list_org_keep_both_grants(tmp_path, monkeypatch, brand):
    """A T3 org's unchanged List gains a public repository of the other T3 org: the item job needs the favorite's record
    and the List org's record. The favorite's record used to suppress the destination's (stamp skipped a stamped job)."""
    from ctshowcase import org as O
    from ctshowcase.resolver import Resolver
    other = "Jevelopers-neatHack-2026"
    fav = f"{other}/northwind-synthetic"
    reg = {"orgs": {OWNER: {"favorites": [{"full_name": fav}], "star_list": {"name": "Built on", "description": ""}}}}
    est = O.Estate(brand, Resolver(brand, reg, {"rows": set(), "ids": set(), "answers": {}, "actions": [], "extra": []}),
                   {"m": {"owner": other, "repo": "northwind-synthetic", "visibility": "public"}})
    lists = {"data": {"viewer": {"login": "x", "lists": {"totalCount": 1, "nodes": [
        {"id": "UL_t3", "name": "Built on", "slug": "built-on", "description": "", "isPrivate": False,
         "items": {"totalCount": 0, "nodes": []}}]}}}}
    recs = [{"id": "t3s-fav", "owner": other}, {"id": "t3s-dest", "owner": OWNER}]
    with _Strict(monkeypatch, _file(_bundle(tmp_path / "both", recs))):
        plan = O.star_list_plan(est, OWNER, lists_capture=lists, allow_t3=True, repo_ids={fav: "R_x"})
        items = [j for j in plan["jobs"] if "list-item" in j["id"]]
        assert len(items) == 1, plan["jobs"]
        assert items[0]["signoff_id"] == "t3s-fav" and items[0]["signoff_ids"] == ["t3s-fav", "t3s-dest"], items
        assert items[0]["approval_id"] == "t3s-fav", items  # the first id; an existing approval_id is never replaced


# --- review round 6: dates that make a record unusable, malformed-vs-scope, no opt-out ---

@pytest.mark.parametrize("approved_on,expires,needle", [
    ("2099-06-01", "2099-12-31", "in the future"),
    ("2099-06-01", "2099-01-01", "in the future"),            # also expires before it was approved
    ("2026-01-15", "2026-01-14", "earlier than approved_on"),
    ("2026-01-15", "2026-01-14T23:59:59+00:00", "earlier than approved_on"),
])
def test_future_or_inverted_dates_never_authorize(approved_on, expires, needle):
    from ctshowcase import signoff
    rec = {"id": "t3s-dates", "owner": OWNER, "repos": ["*"], "approved": True, "approver": "x",
           "approved_on": approved_on, "expires": expires}
    assert any(needle in x for x in signoff.problems(rec)), signoff.problems(rec)
    got, why = signoff.evaluate([OWNER], None, records=[rec])
    assert got is None and why.startswith("invalid:t3s-dates") and needle in why, (got, why)


def test_equal_approved_on_and_expires_and_today_are_valid():
    import datetime as dt
    from ctshowcase import signoff
    today = dt.datetime.now().astimezone().date()
    rec = {"id": "t3s-today", "owner": OWNER, "repos": ["*"], "approved": True, "approver": "x",
           "approved_on": today, "expires": today}
    assert signoff.problems(rec) == []
    assert signoff.evaluate([OWNER], None, records=[rec])[0] is rec


def test_future_dated_record_refuses_on_the_cli(tmp_path):
    """Native probe from the review: a record dated 2099 that expires before it was given lifted the T3 gate."""
    b = _bundle(tmp_path, [{"id": "a1", "approved_on": "2099-06-01", "expires": "2099-01-01"}])
    r = _run(tmp_path, b, "--allow-t3", "describe")
    assert r.returncode == 2 and "t3-signoff:invalid" in _out(r) and "in the future" in _out(r), _out(r)


def test_malformed_record_for_the_repository_is_invalid_not_scope():
    from ctshowcase import signoff
    good = {"id": "t3s-1", "owner": OWNER, "repos": ["other-repo"], "approved": True, "approver": "x",
            "approved_on": "2026-01-15", "expires": "2099-12-31"}
    bad = dict(good, id="t3s-2", repos=["northwind-synthetic"], approved="true")
    got, why = signoff.evaluate([OWNER], "northwind-synthetic", records=[good, bad])
    assert got is None and why.startswith("invalid:t3s-2") and "approved" in why, (got, why)
    # a malformed record for some other repository is not the cause: the refusal stays 'scope'
    unrelated = dict(bad, repos=["unrelated"])
    assert signoff.evaluate([OWNER], "northwind-synthetic", records=[good, unrelated]) == (None, "scope")
    assert signoff.evaluate([OWNER], "other-repo", records=[good, bad])[0] is good


# --- review round 5: duplicate ids, doctor shape ---

def test_duplicate_record_ids_refuse_invalid(tmp_path):
    """signoff_id is the audit key on jobs, so two records sharing an id make a file that authorizes nothing."""
    from ctshowcase import signoff
    base = {"id": "t3s-001", "owner": OWNER, "repos": ["*"], "approved": True, "approver": "a",
            "approved_on": "2026-01-15", "expires": "2099-12-31"}
    other = dict(base, owner="Jevelopers-neatHack-2026", repos=["x"], approver="b")
    rec, why = signoff.evaluate([OWNER], None, records=[base, other])
    assert rec is None and why.startswith("invalid:t3s-001") and "duplicate id" in why, (rec, why)
    rec, why = signoff.evaluate([OWNER], None, records=[base, dict(other, id="t3s-002")])
    assert why is None and rec["id"] == "t3s-001"


def test_doctor_row_shape_is_unchanged_without_allow_t3(tmp_path):
    """The documented row (R1-R11, banner, icon, card, footer, done) gains signoff_id only when --allow-t3 is passed."""
    bundle = _bundle(tmp_path, [])
    r = _run(tmp_path, bundle, "doctor", "--header", owner="CompleteTech-Skills")
    head = r.stdout.splitlines()[0].split("\t")
    assert head[-1] == "done" and "signoff_id" not in head, r.stdout
