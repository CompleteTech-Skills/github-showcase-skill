"""Per-repository T3 sign-off withdrawals (issue 23): an `approved: false` record vetoes the grant for every repository
it covers (`*` covers all), dated on or after the grant, so a co-owner can withdraw one repository from a `*` or
multi-repo grant. A malformed withdrawal that could cover the request fails closed (`t3-signoff:invalid`).
Synthetic records only."""
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
OWN = "Acme"


def _rec(id_, repos, approved=True, on="2026-01-01", owner=OWN, **extra):
    r = {"id": id_, "owner": owner, "repos": repos, "approved": approved, "approver": "synthetic-co-owner",
         "approved_on": on}
    if approved:
        r["expires"] = "2099-12-31"
    r.update(extra)
    return r


def _ev(records, repo, owners=(OWN,)):
    from ctshowcase import signoff
    rec, err = signoff.evaluate(list(owners), repo, records=records)
    return (rec["id"] if rec else None), err


def test_withdrawal_of_one_repo_from_a_multi_repo_grant():
    recs = [_rec("g1", ["a", "b"]), _rec("w1", ["a"], approved=False, on="2026-06-01")]
    assert _ev(recs, "a") == (None, "revoked")
    assert _ev(recs, "b") == ("g1", None)


def test_withdrawal_of_one_repo_from_a_star_grant():
    recs = [_rec("g1", ["*"]), _rec("w1", ["a"], approved=False, on="2026-06-01")]
    assert _ev(recs, "a") == (None, "revoked")
    assert _ev(recs, "site") == ("g1", None)


def test_star_withdrawal_vetoes_every_repository():
    recs = [_rec("g1", ["a", "b"]), _rec("w1", ["*"], approved=False, on="2026-06-01")]
    assert _ev(recs, "a") == (None, "revoked") and _ev(recs, "b") == (None, "revoked")


def test_same_day_withdrawal_vetoes_and_earlier_does_not():
    same = [_rec("g1", ["*"], on="2026-06-01"), _rec("w1", ["a"], approved=False, on="2026-06-01")]
    assert _ev(same, "a") == (None, "revoked")
    earlier = [_rec("g1", ["*"], on="2026-06-01"), _rec("w1", ["a"], approved=False, on="2026-05-31")]
    assert _ev(earlier, "a") == ("g1", None)


def test_owner_name_and_bare_name_forms_and_aliases_revoke_each_other():
    bare_grant = [_rec("g1", ["a"]), _rec("w1", [f"{OWN}/a"], approved=False, on="2026-06-01")]
    assert _ev(bare_grant, "a") == (None, "revoked")
    full_grant = [_rec("g1", [f"{OWN}/a", "b"]), _rec("w1", ["a"], approved=False, on="2026-06-01")]
    assert _ev(full_grant, "a") == (None, "revoked") and _ev(full_grant, "b") == ("g1", None)
    # another account's OWNER/NAME stays distinct
    other = [_rec("g1", ["a"]), _rec("w1", ["Other/a"], approved=False, on="2026-06-01")]
    assert _ev(other, "a") == ("g1", None)


def test_regrant_after_withdrawal_is_not_vetoed():
    recs = [_rec("g1", ["*"]), _rec("w1", ["a"], approved=False, on="2026-06-01"),
            _rec("g2", ["a"], on="2026-07-01")]
    assert _ev(recs, "a") == ("g2", None)
    assert _ev(recs, "site") == ("g1", None)


@pytest.mark.parametrize("extra,problem", [
    ({"reason": "co-owner withdrew"}, "reason"),
    ({"approved_on": "2026-10-01T12:00:00Z"}, "approved_on"),
    ({"note": 7}, "note"),
    ({"repos": [1]}, "repos"),
    ({"repos": []}, "repos"),
])
def test_malformed_withdrawal_fails_closed(extra, problem):
    w = dict(_rec("w1", ["*"], approved=False, on="2026-10-01"), **extra)
    recs = [_rec("g1", ["*"]), w]
    got, err = _ev(recs, "site")
    assert got is None and err and err.startswith("invalid:w1:"), (got, err)


def test_malformed_withdrawal_for_an_unrelated_repo_does_not_block_another_repo():
    recs = [_rec("g1", ["*"]), _rec("w1", ["a"], approved=False, on="2026-10-01", reason="x")]
    assert _ev(recs, "b") == ("g1", None)
    got, err = _ev(recs, "a")
    assert got is None and err.startswith("invalid:w1:")


def test_malformed_record_for_another_owner_has_no_effect():
    recs = [_rec("g1", ["*"]), _rec("w9", ["*"], approved=False, on="2026-10-01", owner="Other", reason="x")]
    assert _ev(recs, "site") == ("g1", None)


def test_record_for_honours_the_per_repository_veto(tmp_path, monkeypatch):
    from ctshowcase import signoff
    p = tmp_path / "s.yaml"
    p.write_text(json.dumps({"signoffs": [_rec("g1", ["*"]), _rec("w1", ["a"], approved=False, on="2026-06-01")]}),
                 encoding="utf-8")
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(p))
    run = signoff.reset()
    try:
        signoff._grant(OWN.lower(), _rec("g1", ["*"]))
        assert signoff.record_for(OWN, "a") is None
        assert signoff.record_for(OWN, "site")["id"] == "g1"
    finally:
        signoff.restore(run)


def _cli(tmp_path, records, *argv, repo="northwind-synthetic"):
    f = tmp_path / "t3-signoffs.yaml"
    f.write_text(json.dumps({"signoffs": records}), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner="Pick-Your-AI", repo=repo)), encoding="utf-8")
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(tmp_path))
    env.pop("SHOWCASE_T3_SIGNOFF_FILE", None)
    return subprocess.run([*SHOWCASE, "--meta", str(meta), "--no-repo-dir", "--t3-signoff-file", str(f), "--allow-t3",
                           *argv], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")


def test_cli_refuses_a_withdrawn_repository_and_a_malformed_withdrawal(tmp_path):
    own = "Pick-Your-AI"
    withdrawn = [_rec("g1", ["*"], owner=own), _rec("w1", ["northwind-synthetic"], approved=False, on="2026-06-01", owner=own)]
    (tmp_path / "a").mkdir()
    r = _cli(tmp_path / "a", withdrawn, "describe")
    assert r.returncode == 2 and "t3-signoff:revoked" in r.stdout + r.stderr, r.stdout + r.stderr
    bad = [_rec("g1", ["*"], owner=own), _rec("w1", ["*"], approved=False, on="2026-06-01", owner=own, reason="x")]
    (tmp_path / "b").mkdir()
    r = _cli(tmp_path / "b", bad, "describe")
    assert r.returncode == 2 and "t3-signoff:invalid" in r.stdout + r.stderr, r.stdout + r.stderr
    (tmp_path / "c").mkdir()
    ok = [_rec("g1", ["*"], owner=own), _rec("w1", ["some-other-repo"], approved=False, on="2026-06-01", owner=own)]
    r = _cli(tmp_path / "c", ok, "describe")
    assert r.returncode == 0, r.stdout + r.stderr


# Non-boolean `approved` values on a record beside a valid grant (synthetic). Only a literal False is a withdrawal, so
# a string "false", 0, null, or any other non-boolean must refuse as invalid, never be ignored in favour of g1.
NON_BOOLEAN_APPROVED = ["false", "true", 0, 1, None]


@pytest.mark.parametrize("bad", NON_BOOLEAN_APPROVED)
@pytest.mark.parametrize("repos,repo", [(["*"], "site"), (["site"], "site"), (["*"], None), (["site"], None)])
def test_non_boolean_approved_beside_valid_grant_fails_closed(bad, repos, repo):
    records = [_rec("g1", ["*"]), {**_rec("w1", repos, approved=False, on="2026-06-01"), "approved": bad}]
    got, err = _ev(records, repo)
    assert got is None and err and err.startswith("invalid:w1:") and "approved" in err, (got, err)


@pytest.mark.parametrize("bad", NON_BOOLEAN_APPROVED)
def test_non_boolean_approved_dated_before_the_grant_still_fails_closed(bad):
    records = [_rec("g1", ["*"]), {**_rec("w1", ["*"], approved=False, on="2020-01-01"), "approved": bad}]
    got, err = _ev(records, "site")
    assert got is None and err and err.startswith("invalid:w1:") and "approved" in err, (got, err)


@pytest.mark.parametrize("bad", NON_BOOLEAN_APPROVED)
def test_non_boolean_approved_for_an_unrelated_owner_does_not_block(bad):
    records = [_rec("g1", ["*"]),
               {**_rec("w1", ["*"], approved=False, on="2026-06-01", owner="Other"), "approved": bad}]
    assert _ev(records, "site") == ("g1", None)


@pytest.mark.parametrize("bad", NON_BOOLEAN_APPROVED)
def test_non_boolean_approved_for_another_repository_does_not_block(bad):
    records = [_rec("g1", ["*"]), {**_rec("w1", ["other"], approved=False, on="2026-06-01"), "approved": bad}]
    assert _ev(records, "site") == ("g1", None)


def test_literal_false_withdrawal_and_valid_grant_controls():
    withdrawn = [_rec("g1", ["*"]), _rec("w1", ["*"], approved=False, on="2026-06-01")]
    assert _ev(withdrawn, "site") == (None, "revoked")
    assert _ev([_rec("g1", ["*"])], "site") == ("g1", None)


@pytest.mark.parametrize("bad", NON_BOOLEAN_APPROVED)
def test_non_boolean_approved_is_never_a_valid_approval(bad):
    records = [{**_rec("g1", ["*"]), "approved": bad}]
    got, err = _ev(records, "site")
    assert got is None and err and err.startswith("invalid:"), (got, err)



# Owner-wide wildcard grant with a narrow per-repository withdrawal (synthetic records only).
PYA = "Pick-Your-AI"


def _wildcard_pair():
    g1 = _rec("g1", ["*"], owner=PYA, approver="coowner", on="2026-01-01")
    w1 = _rec("w1", ["northwind-member"], approved=False, owner=PYA, approver="coowner", on="2026-06-01")
    return [g1, w1]


def test_wildcard_grant_with_narrow_withdrawal_refuses_only_that_repo():
    recs = _wildcard_pair()
    assert _ev(recs, "northwind-member", owners=(PYA,)) == (None, "revoked")
    assert _ev(recs, "kept-y", owners=(PYA,)) == ("g1", None)
    # owner-wide authorization is kept; the per-repo check lives in the emitters
    assert _ev(recs, None, owners=(PYA,)) == ("g1", None)


def test_record_for_never_stamps_withdrawn_repo(tmp_path, monkeypatch):
    from ctshowcase import signoff
    p = tmp_path / "s.yaml"
    p.write_text(json.dumps({"signoffs": _wildcard_pair()}), encoding="utf-8")
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(p))
    run = signoff.reset()
    try:
        signoff._grant(PYA.lower(), _wildcard_pair()[0])
        assert signoff.record_for(PYA, "northwind-member") is None
        assert signoff.record_for(PYA, "kept-y")["id"] == "g1"
    finally:
        signoff.restore(run)


@pytest.mark.parametrize("bad", ["false", 0, None])
def test_malformed_withdrawal_beside_wildcard_grant_stays_invalid(bad):
    g1 = _rec("g1", ["*"], owner=PYA, approver="coowner", on="2026-01-01")
    w1 = {**_rec("w1", ["*"], approved=False, owner=PYA, approver="coowner", on="2026-06-01"), "approved": bad}
    got, err = _ev([g1, w1], "northwind-member", owners=(PYA,))
    assert got is None and err and err.startswith("invalid"), (got, err)


def test_unrelated_owner_withdrawal_is_isolated():
    recs = [_wildcard_pair()[0],
            _rec("w2", ["northwind-member"], approved=False, owner="Other-Org", approver="coowner", on="2026-06-01")]
    assert _ev(recs, "northwind-member", owners=(PYA,)) == ("g1", None)


@pytest.mark.parametrize("repos", [" * ", ["* "], [" site"], " site ", ["Acme/site "]])
def test_whitespace_padded_withdrawal_scope_still_vetoes_a_single_repository(repos):
    """A schema-valid but padded `repos` entry must scope the same way for a single repository as for the owner."""
    recs = [_rec("g1", ["*"]), _rec("w1", repos, approved=False, on="2026-06-01")]
    assert _ev(recs, "site") == (None, "revoked")
