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


# One owner-normalisation policy (strip all surrounding whitespace, then case-fold) for evaluate(), _withdrawn() and
# record_for(): a padded spelling of an owner is that owner, never a different one that escapes its withdrawal.
PADDED = [" Acme", "Acme ", " Acme ", "\tAcme\n", " Acme "]


def _pad(template, name):
    return template.replace("Acme", name)


@pytest.mark.parametrize("padded", PADDED)
@pytest.mark.parametrize("repo", ["site", None])
def test_padded_owner_withdrawal_revokes_the_grant(padded, repo):
    recs = [_rec("g1", ["*"]), _rec("w1", ["*"], approved=False, on="2026-06-01", owner=padded)]
    assert _ev(recs, repo) == (None, "revoked")


def test_plain_owner_withdrawal_control():
    recs = [_rec("g1", ["*"]), _rec("w1", ["*"], approved=False, on="2026-06-01")]
    assert _ev(recs, "site") == (None, "revoked") and _ev(recs, None) == (None, "revoked")


@pytest.mark.parametrize("padded", PADDED)
def test_padded_grant_owner_with_a_clean_withdrawal_is_revoked(padded):
    recs = [_rec("g1", ["*"], owner=padded), _rec("w1", ["*"], approved=False, on="2026-06-01")]
    assert _ev(recs, "site") == (None, "revoked") and _ev(recs, None) == (None, "revoked")


@pytest.mark.parametrize("padded", PADDED)
def test_padded_grant_owner_alone_still_grants(padded):
    assert _ev([_rec("g1", ["*"], owner=padded)], "site") == ("g1", None)


@pytest.mark.parametrize("padded", PADDED)
def test_padded_unrelated_owner_withdrawal_is_isolated(padded):
    recs = [_rec("g1", ["*"]), _rec("w1", ["*"], approved=False, on="2026-06-01", owner=_pad(padded, "Other"))]
    assert _ev(recs, "site") == ("g1", None) and _ev(recs, None) == ("g1", None)


@pytest.mark.parametrize("padded", PADDED)
def test_require_refuses_a_padded_owner_withdrawal(padded, tmp_path, monkeypatch):
    from ctshowcase import signoff
    from ctshowcase.errors import Refused
    p = tmp_path / "s.yaml"
    p.write_text(json.dumps({"signoffs": [_rec("g1", ["*"]),
                                          _rec("w1", ["*"], approved=False, on="2026-06-01", owner=padded)]}),
                 encoding="utf-8")
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(p))
    run = signoff.reset()
    try:
        for repo in ("site", None):
            with pytest.raises(Refused) as ei:
                signoff.require(OWN, repo)
            assert ei.value.log == "t3-signoff:revoked", ei.value.log
    finally:
        signoff.restore(run)


@pytest.mark.parametrize("padded", PADDED)
def test_record_for_never_stamps_a_grant_withdrawn_under_a_padded_owner(padded, tmp_path, monkeypatch):
    from ctshowcase import signoff
    recs = [_rec("g1", ["*"]), _rec("w1", ["a"], approved=False, on="2026-06-01", owner=padded)]
    p = tmp_path / "s.yaml"
    p.write_text(json.dumps({"signoffs": recs}), encoding="utf-8")
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(p))
    run = signoff.reset()
    try:
        signoff._grant(OWN.lower(), recs[0])
        assert signoff.record_for(OWN, "a") is None
        assert signoff.record_for(OWN, "site")["id"] == "g1"
    finally:
        signoff.restore(run)


@pytest.mark.parametrize("padded", PADDED)
def test_cli_refuses_a_padded_owner_withdrawal(padded, tmp_path):
    own = "Pick-Your-AI"
    recs = [_rec("g1", ["*"], owner=own), _rec("w1", ["*"], approved=False, on="2026-06-01", owner=_pad(padded, own))]
    r = _cli(tmp_path, recs, "describe")
    assert r.returncode == 2 and "t3-signoff:revoked" in r.stdout + r.stderr, r.stdout + r.stderr


# ------------------------------------------------------------------ cross-owner README repositories (issue 23, r5)
# A README names repositories of owners other than the board's. Each is authorized on ITS OWN resolved owner and name,
# whatever the board owner's tier: a T3 owner's repository on a non-T3 board is gated like any T3 repository.
T3_OWNER = "Pick-Your-AI"
BOARD_OWNER = "CompleteTech-Skills"
T3_WILD = [{"id": "t3s-all"},
           {"id": "t3s-drop-x", "repos": ["withdrawn-x"], "approved": False, "approved_on": "2026-10-01"}]


def _xo_capture(captured=None, owner=BOARD_OWNER):
    """The private copy capture on `owner`'s board, every view numbered; `captured` fills spec.repositories."""
    from test_t3_emission_scope import _private_board
    c = _private_board()
    p = c["data"]["organization"]["projectV2"]
    p["url"] = f"https://github.com/orgs/{owner}/projects/{p['number']}"
    p["repositories"] = {"nodes": [{"nameWithOwner": n} for n in captured or []]}
    return c


def _xo_plan(brand, tmp_path, monkeypatch, records, repos, captured=None, allow_t3=True, owner=BOARD_OWNER):
    from test_t3_emission_scope import _Strict, _file, _resolver
    from ctshowcase import project as PJ
    with _Strict(monkeypatch, _file(tmp_path, records)):
        return PJ.copy_plan(owner, role="org", copied=_xo_capture(captured, owner), resolver=_resolver(brand),
                            repositories=repos, allow_t3=allow_t3, reviewed="2026-10-25")


def _xo_readme(plan):
    rd = [j for j in plan["jobs"] if "--readme" in (j.get("argv") or [])]
    assert len(rd) == 1, [j["id"] for j in plan["jobs"]]
    return rd[0], rd[0]["argv"][rd[0]["argv"].index("--readme") + 1]


def _xo_ids(job):
    return set(job.get("signoff_ids") or []) | ({job["signoff_id"]} if job.get("signoff_id") else set())


def test_cross_owner_board_is_not_t3(brand):
    """Precondition: the board owner is not T3, the repository owner is (so the board-owner check cannot gate it)."""
    from test_t3_emission_scope import _resolver
    r = _resolver(brand)
    assert r.owner_status(BOARD_OWNER) != "t3" and r.owner_status(T3_OWNER) == "t3"


def test_cross_owner_explicit_no_grant_omits_readme_repo(brand, tmp_path, monkeypatch):
    plan = _xo_plan(brand, tmp_path, monkeypatch, [], [f"{T3_OWNER}/withdrawn-x"])
    _, text = _xo_readme(plan)
    assert "withdrawn-x" not in text, text
    assert any(str(x).startswith(f"t3-signoff:missing:{T3_OWNER}/withdrawn-x") for x in plan["logs"]), plan["logs"]


def test_cross_owner_explicit_withdrawn_omitted_kept_retained_with_grant_id(brand, tmp_path, monkeypatch):
    plan = _xo_plan(brand, tmp_path, monkeypatch, T3_WILD, [f"{T3_OWNER}/withdrawn-x", f"{T3_OWNER}/kept-y"])
    job, text = _xo_readme(plan)
    assert "withdrawn-x" not in text and "kept-y" in text, text
    assert "t3s-all" in _xo_ids(job), job
    assert any(str(x).startswith(f"t3-signoff:revoked:{T3_OWNER}/withdrawn-x") for x in plan["logs"]), plan["logs"]


def test_cross_owner_explicit_valid_grant_retained_and_stamped(brand, tmp_path, monkeypatch):
    plan = _xo_plan(brand, tmp_path, monkeypatch, [{"id": "t3s-all"}], [f"{T3_OWNER}/kept-y"])
    job, text = _xo_readme(plan)
    assert "kept-y" in text, text
    assert "t3s-all" in _xo_ids(job), job
    assert not any(str(x).startswith("t3-signoff:") for x in plan["logs"]), plan["logs"]


def test_cross_owner_explicit_regrant_stamps_repository_record(brand, tmp_path, monkeypatch):
    recs = [*T3_WILD, {"id": "t3s-regrant", "repos": ["withdrawn-x"], "approved_on": "2026-10-02"}]
    plan = _xo_plan(brand, tmp_path, monkeypatch, recs, [f"{T3_OWNER}/withdrawn-x"])
    job, text = _xo_readme(plan)
    assert "withdrawn-x" in text, text
    assert "t3s-regrant" in _xo_ids(job), job


def test_cross_owner_captured_repositories_withdrawn_vs_kept(brand, tmp_path, monkeypatch):
    """repositories=None: the README names the board's captured spec.repositories, each checked on its own owner."""
    plan = _xo_plan(brand, tmp_path, monkeypatch, T3_WILD, None,
                    captured=[f"{T3_OWNER}/withdrawn-x", f"{T3_OWNER}/kept-y"])
    job, text = _xo_readme(plan)
    assert "withdrawn-x" not in text and "kept-y" in text, text
    assert "t3s-all" in _xo_ids(job), job
    assert any(str(x).startswith(f"t3-signoff:revoked:{T3_OWNER}/withdrawn-x") for x in plan["logs"]), plan["logs"]
    assert not [j for j in plan["jobs"] if "-link-" in j["id"]], [j["id"] for j in plan["jobs"]]  # no link job for captured


def test_cross_owner_captured_without_grant_omits_repository(brand, tmp_path, monkeypatch):
    plan = _xo_plan(brand, tmp_path, monkeypatch, [], None, captured=[f"{T3_OWNER}/withdrawn-x"])
    _, text = _xo_readme(plan)
    assert "withdrawn-x" not in text, text
    assert any(str(x).startswith(f"t3-signoff:missing:{T3_OWNER}/withdrawn-x") for x in plan["logs"]), plan["logs"]


def test_control_cross_owner_non_t3_repository_untouched(brand, tmp_path, monkeypatch):
    other = "Northwind-Trading-Co"
    plan = _xo_plan(brand, tmp_path, monkeypatch, [], [f"{other}/some-repo"], captured=[f"{other}/cap-repo"])
    _, text = _xo_readme(plan)
    assert "some-repo" in text, text
    assert not any(str(x).startswith("t3-signoff:") for x in plan["logs"]), plan["logs"]


def test_control_same_owner_behaviour_unchanged(brand, tmp_path, monkeypatch):
    plan = _xo_plan(brand, tmp_path, monkeypatch, T3_WILD, [f"{T3_OWNER}/withdrawn-x", f"{T3_OWNER}/kept-y"],
                    owner=T3_OWNER)
    job, text = _xo_readme(plan)
    assert "withdrawn-x" not in text and "kept-y" in text, text
    assert "t3s-all" in _xo_ids(job), job


def test_control_without_allow_t3_path_unchanged(brand, tmp_path, monkeypatch):
    plan = _xo_plan(brand, tmp_path, monkeypatch, [], [f"{T3_OWNER}/withdrawn-x"], allow_t3=False)
    _, text = _xo_readme(plan)
    assert "withdrawn-x" in text, text
    assert not any(str(x).startswith("t3-signoff:") for x in plan["logs"]), plan["logs"]


def test_control_standalone_project_readme_unchanged(brand):
    """`project readme` is read-only text: it names the repositories it is given, with no sign-off lookup."""
    from ctshowcase import project as PJ
    text, logs = PJ.readme(BOARD_OWNER, "Skills", 3, {v["name"]: i + 1 for i, v in enumerate(PJ.VIEWS)},
                           repositories=[f"{T3_OWNER}/withdrawn-x"], reviewed="2026-10-25")
    assert "withdrawn-x" in text, text
    assert not any(str(x).startswith("t3-signoff:") for x in logs), logs


# ------------------------------------------------------------------ Estate Org options and association ids (issue 23, r6)
# A job that already holds a repository-specific regrant keeps it when the Org/association grant is stamped later; the
# direct `project copy-plan --role estate` path stamps the captured T3 Org option exactly as estate_plan does.
SITE = f"{T3_OWNER}/site"
REGRANT_RECORDS = [{"id": "t3s-g"},
                   {"id": "t3s-w", "repos": ["site"], "approved": False, "approved_on": "2026-10-01"},
                   {"id": "t3s-r", "repos": ["site"], "approved_on": "2026-10-02"}]


def _estate_capture(option_name="Pick Your AI", option_desc=f"T3: {T3_OWNER}", repositories=()):
    """A complete private Estate capture (every view numbered) whose Org field holds one option."""
    from test_t3_signoff_require import _complete_estate_capture
    cap = _complete_estate_capture()
    board = cap["data"]["user"]["projectV2"]
    org = [f for f in board["fields"]["nodes"] if f["name"] == "Org"][0]
    org["options"] = [{"id": "optorg1", "name": option_name, "color": "YELLOW", "description": option_desc}]
    board["repositories"] = {"nodes": [{"nameWithOwner": n} for n in repositories]}
    assert board["public"] is False
    return cap


def _estate_resolver(brand, in_directory=True):
    from test_t3_emission_scope import _registry, _resolver
    reg = _registry(True)
    if in_directory:
        reg["profile"]["org_directory"].append({"group": "T3", "orgs": [T3_OWNER]})
    return _resolver(brand, reg)


def _ids_of(job):
    return list(job.get("signoff_ids") or ([job["signoff_id"]] if job.get("signoff_id") else []))


@pytest.mark.parametrize("in_directory", [True, False], ids=["org-listed", "org-retained-from-capture"])
def test_estate_org_option_keeps_repository_regrant(brand, tmp_path, monkeypatch, in_directory):
    """Grant G covers `*`, a withdrawal revokes site, and a repository-scoped regrant R reauthorizes site. The Estate
    README links site (authorized by R) and names the Pick-Your-AI Org option (authorized by G): it carries both, and the
    Org stamp must not replace R with G."""
    from test_t3_emission_scope import _Strict, _file
    from ctshowcase import project as PJ, signoff
    with _Strict(monkeypatch, _file(tmp_path, REGRANT_RECORDS)):
        assert signoff.evaluate([T3_OWNER], "site")[0]["id"] == "t3s-r"  # precondition: R is what authorizes site
        plan = PJ.estate_plan(_estate_resolver(brand, in_directory), copied=_estate_capture(repositories=[SITE]),
                              user_id=100, allow_t3=True, reviewed="2026-10-25")
    readme = [j for j in plan["jobs"] if "--readme" in (j.get("argv") or [])]
    assert len(readme) == 1, [j["id"] for j in plan["jobs"]]
    text = readme[0]["argv"][readme[0]["argv"].index("--readme") + 1]
    assert "site" in text and "Pick Your AI" in text, text
    ids = _ids_of(readme[0])
    assert "t3s-r" in ids and "t3s-g" in ids and len(ids) == len(set(ids)), readme[0]
    assert not any(str(x).startswith("t3-signoff:") for x in plan["logs"]), plan["logs"]


def test_stamp_associations_keeps_ids_already_on_the_item():
    from ctshowcase import signoff
    item = {"id": "j", "signoff_id": "t3s-r"}
    signoff.stamp_associations(item, ["t3s-g"])
    assert item["signoff_id"] == "t3s-r" and item["signoff_ids"] == ["t3s-r", "t3s-g"], item
    listed = {"id": "j", "signoff_ids": ["t3s-r", "t3s-x"]}  # signoff_ids input, deduplicated with the new ids
    signoff.stamp_associations(listed, ["t3s-x", "t3s-g", "t3s-g"])
    assert listed["signoff_id"] == "t3s-r" and listed["signoff_ids"] == ["t3s-r", "t3s-x", "t3s-g"], listed
    again = {"id": "j", "signoff_id": "t3s-g"}  # the same id is neither duplicated nor turned into a list
    signoff.stamp_associations(again, ["t3s-g"])
    assert again["signoff_id"] == "t3s-g" and "signoff_ids" not in again, again
    bare = {"id": "j"}
    signoff.stamp_associations(bare, [])  # no association ids: untouched
    assert bare == {"id": "j"}, bare


# the direct CLI path (`project copy-plan --target @me --role estate`) ----------------------------------------------
def _direct_estate(tmp_path, capture, records, *flags):
    from test_t3_emission_scope import _file
    cap = tmp_path / "capture.json"
    cap.write_text(json.dumps(capture), encoding="utf-8")
    sf = _file(tmp_path, records)
    e = dict(os.environ)
    e.pop("SHOWCASE_T3_SIGNOFF_FILE", None)
    e.pop("SHOWCASE_ESTATE_ROOT", None)
    r = subprocess.run([*SHOWCASE, "--t3-signoff-file", str(sf), "project", "copy-plan", "--target", "@me",
                        "--role", "estate", "--copied", str(cap), "--files-dir", str(tmp_path / "bodies"),
                        "--user-id", "100", "--reviewed", "2026-10-25", *flags],
                       cwd=ROOT, env=e, capture_output=True, text=True, encoding="utf-8")
    try:
        out = json.loads(r.stdout)
    except ValueError:
        out = {}
    return r, out


def _readme_job(out):
    jobs = [j for j in out.get("jobs", []) if "--readme" in (j.get("argv") or [])]
    return jobs[0] if jobs else None


def test_direct_copy_plan_estate_stamps_captured_t3_org(tmp_path):
    r, out = _direct_estate(tmp_path, _estate_capture(), [{"id": "t3s-g"}], "--allow-t3")
    assert r.returncode == 0, r.stdout + r.stderr
    job = _readme_job(out)
    assert job is not None, [j["id"] for j in out["jobs"]]
    assert "Pick Your AI" in job["argv"][job["argv"].index("--readme") + 1]
    assert _ids_of(job) == ["t3s-g"], job
    assert not any(str(x).startswith("t3-signoff:") for x in out["logs"]), out["logs"]


def test_direct_copy_plan_estate_repository_regrant_survives_org_stamp(tmp_path):
    r, out = _direct_estate(tmp_path, _estate_capture(repositories=[SITE]), REGRANT_RECORDS, "--allow-t3")
    assert r.returncode == 0, r.stdout + r.stderr
    job = _readme_job(out)
    assert job is not None and "site" in job["argv"][job["argv"].index("--readme") + 1], out["jobs"]
    assert set(_ids_of(job)) == {"t3s-g", "t3s-r"}, job


def test_direct_copy_plan_estate_control_without_the_flag_stamps_nothing(tmp_path):
    r, out = _direct_estate(tmp_path, _estate_capture(), [{"id": "t3s-g"}])
    assert "t3s-g" not in r.stdout, r.stdout  # nothing is stamped from a run without --allow-t3
    assert not any(_ids_of(j) for j in out.get("jobs", [])), out.get("jobs")


def test_direct_copy_plan_estate_control_without_a_record_is_held(tmp_path):
    r, out = _direct_estate(tmp_path, _estate_capture(), [], "--allow-t3")
    assert f"t3-signoff:missing:{T3_OWNER}" in r.stdout + r.stderr, r.stdout + r.stderr
    assert "t3s-" not in r.stdout, r.stdout
    assert _readme_job(out) is None, out.get("jobs")
    assert "Pick Your AI" not in json.dumps(out.get("jobs", [])), out.get("jobs")


def test_direct_copy_plan_estate_withdrawn_captured_org_leaves_no_readme_and_no_stamp(tmp_path):
    recs = [{"id": "t3s-g"}, {"id": "t3s-w", "approved": False, "approved_on": "2026-10-01"}]
    r, out = _direct_estate(tmp_path, _estate_capture(), recs, "--allow-t3")
    assert f"t3-signoff:revoked:{T3_OWNER}" in out.get("logs", []), r.stdout + r.stderr
    assert _readme_job(out) is None, out["jobs"]  # the README is held with the withdrawn Org
    assert "Pick Your AI" not in json.dumps(out["jobs"]), out["jobs"]
    assert not any(_ids_of(j) for j in out["jobs"]), [j for j in out["jobs"] if _ids_of(j)]


def test_direct_copy_plan_estate_control_non_t3_org_option_gets_no_stamp(tmp_path):
    cap = _estate_capture(option_name="CompleteTech Skills", option_desc="T1: CompleteTech-Skills")
    r, out = _direct_estate(tmp_path, cap, [{"id": "t3s-g"}], "--allow-t3")
    assert r.returncode == 0, r.stdout + r.stderr
    job = _readme_job(out)
    assert job is not None and "CompleteTech Skills" in job["argv"][job["argv"].index("--readme") + 1], out["jobs"]
    assert not any(_ids_of(j) for j in out["jobs"]), [j for j in out["jobs"] if _ids_of(j)]
