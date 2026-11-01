"""View-filter repository authorization (issue 23): a proposed view filter that names a repository by a positive `repo:`
qualifier is authorized like a README repository before its updateProjectV2View mutation is emitted. A denied or
withdrawn repository holds the job (`view-filter-held` plus a `t3-signoff:<code>` log); a permitted one carries the
covering sign-off id. A non-T3 owner's filter is unchanged and unstamped. Synthetic records and names only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_t3_emission_scope import FIX, OWNER, _file, _resolver, _Strict  # noqa: E402

WS = [{"name": "Pricing research", "kind": "Research", "description": "Price experiments"}]
WILD = [{"id": "t3s-all"}, {"id": "t3s-drop-x", "repos": ["withdrawn-x"], "approved": False, "approved_on": "2026-10-01"}]
T1 = "CompleteTech-Skills"
BASE_FILTER = "status:Backlog,Ready workstream:Research"


def _capture(owner, flt):
    c = json.loads((FIX / "copy-capture.json").read_text(encoding="utf-8"))
    p = c["data"]["organization"]["projectV2"]
    p["url"] = f"https://github.com/orgs/{owner}/projects/{p['number']}"
    for v in p["views"]["nodes"]:
        if v["name"] == "Backlog":
            v["filter"] = flt
    return c


def _plan(brand, flt, *, owner=T1, allow_t3=True):
    from ctshowcase import project as PJ
    return PJ.copy_plan(owner, role="org", copied=_capture(owner, flt), resolver=_resolver(brand), workstreams=WS,
                        allow_t3=allow_t3, reviewed="2026-10-25")


def _backlog(plan_or_jobs):
    jobs = plan_or_jobs["jobs"] if isinstance(plan_or_jobs, dict) else plan_or_jobs
    return [j for j in jobs if j["id"].endswith("-filter") and "Pricing research" in " ".join(j.get("argv") or [])]


def _held(plan):
    return [x for x in plan["logs"] if str(x).startswith("view-filter-held:")]


def _t3_codes(plan):
    return [x for x in plan["logs"] if str(x).startswith("t3-signoff:")]


def test_rename_filter_job_is_emitted_for_a_plain_filter(brand):
    """Control: the mutation exists when no repository is named, so the absence below is the authorization."""
    plan = _plan(brand, BASE_FILTER)
    assert len(_backlog(plan)) == 1, [j["id"] for j in plan["jobs"]]


def test_withdrawn_repo_in_filter_holds_the_job(tmp_path, monkeypatch, brand):
    flt = f"repo:{OWNER}/withdrawn-x workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt)
    assert not _backlog(plan), [j["id"] for j in plan["jobs"]]
    assert not any("withdrawn-x" in " ".join(j.get("argv") or []) for j in plan["jobs"] if j["id"].endswith("-filter"))
    assert _held(plan), plan["logs"]
    assert _t3_codes(plan), plan["logs"]
    assert any("view filter held" in str(p.get("why", "")) for p in plan["pending"]), plan["pending"]


def test_kept_repo_in_filter_keeps_the_job_and_carries_the_signoff_id(tmp_path, monkeypatch, brand):
    flt = f"repo:{OWNER}/kept-y workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt)
    jobs = _backlog(plan)
    assert len(jobs) == 1, [j["id"] for j in plan["jobs"]]
    assert jobs[0].get("signoff_id") == "t3s-all", jobs[0]
    assert "kept-y" in " ".join(jobs[0]["argv"])
    assert not _held(plan) and not _t3_codes(plan), plan["logs"]


def test_mixed_filter_holds_the_whole_job(tmp_path, monkeypatch, brand):
    flt = f"repo:{OWNER}/kept-y,{OWNER}/withdrawn-x workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt)
    assert not _backlog(plan) and _held(plan), plan["logs"]


def test_regrant_stamps_both_records_on_the_filter_job(tmp_path, monkeypatch, brand):
    recs = [*WILD, {"id": "t3s-regrant", "repos": ["withdrawn-x"], "approved_on": "2026-10-02"}]
    flt = f"repo:{OWNER}/withdrawn-x,{OWNER}/kept-y workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, recs)):
        plan = _plan(brand, flt)
    jobs = _backlog(plan)
    assert len(jobs) == 1, plan["logs"]
    ids = set(jobs[0].get("signoff_ids") or []) | {jobs[0].get("signoff_id")}
    assert {"t3s-all", "t3s-regrant"} <= ids, jobs[0]


def test_without_allow_t3_the_filter_is_held(tmp_path, monkeypatch, brand):
    flt = f"repo:{OWNER}/kept-y workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt, allow_t3=False)
    assert not _backlog(plan), [j["id"] for j in plan["jobs"]]
    assert _held(plan), plan["logs"]
    assert f"t3-signoff:readme:{OWNER}/kept-y" in plan["logs"], plan["logs"]


def test_non_t3_owner_filter_is_unchanged_and_unstamped(tmp_path, monkeypatch, brand):
    flt = "repo:Other-Org/some-repo workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt, owner="Northwind-Trading-Co")
    jobs = _backlog(plan)
    assert len(jobs) == 1, [j["id"] for j in plan["jobs"]]
    assert "some-repo" in " ".join(jobs[0]["argv"]) and "signoff_id" not in jobs[0], jobs[0]
    assert not _held(plan)


@pytest.mark.parametrize("flt", [
    f"-repo:{OWNER}/withdrawn-x workstream:Research",  # negative qualifier names no association
    "repo:* workstream:Research",                      # wildcard names no single repository
    "repo: workstream:Research",                       # empty value
])
def test_negative_and_wildcard_repo_tokens_are_ignored(tmp_path, monkeypatch, brand, flt):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt)
    assert not _held(plan), plan["logs"]
    assert len(_backlog(plan)) == 1, [j["id"] for j in plan["jobs"]]


def test_filter_repo_refs_parsing():
    from ctshowcase.project import _filter_repo_refs as refs
    assert refs('repo:A/x,B/y -repo:C/z repo:"A/X" repo:* repo:') == ["A/x", "B/y"]
    assert refs("") == [] and refs(None) == []


@pytest.mark.parametrize("bad", ["false", 0, None])
def test_invalid_boolean_on_covering_record_holds_the_filter(tmp_path, monkeypatch, brand, bad):
    recs = [{"id": "t3s-bad", "approved": bad, "expires": "2099-12-31"}]
    flt = f"repo:{OWNER}/kept-y workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, recs)):
        plan = _plan(brand, flt)
    assert not _backlog(plan), [j["id"] for j in plan["jobs"]]
    assert _held(plan) and _t3_codes(plan), plan["logs"]


def test_invalid_boolean_withdrawal_does_not_let_an_older_grant_cover_the_filter(tmp_path, monkeypatch, brand):
    recs = [{"id": "t3s-all"}, {"id": "t3s-bad-w", "repos": ["withdrawn-x"], "approved": "false",
                                "approved_on": "2026-10-01", "expires": "2099-12-31"}]
    flt = f"repo:{OWNER}/withdrawn-x workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, recs)):
        plan = _plan(brand, flt)
    assert not _backlog(plan), [j["id"] for j in plan["jobs"]]


def test_estate_role_never_carries_a_repo_qualifier_into_a_filter_job(tmp_path, monkeypatch, brand):
    from ctshowcase import project as PJ
    c = json.loads((FIX / "estate-copy-capture.json").read_text(encoding="utf-8"))
    board = next(v for v in _walk(c) if isinstance(v, dict) and "views" in v and "fields" in v)
    for v in board["views"]["nodes"][1:]:
        v["filter"] = f"repo:{OWNER}/withdrawn-x"
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = PJ.estate_plan(_resolver(brand), copied=c, user_id=100, allow_t3=True)
    for j in plan["jobs"]:
        if j["id"].endswith("-filter"):
            assert "withdrawn-x" not in " ".join(j.get("argv") or []), j


def _walk(o):
    yield o
    if isinstance(o, dict):
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


# CLI path -------------------------------------------------------------------------------------------------------
def _cli(tmp_path, records, flt):
    from test_t3_signoff_require import _bundle, _run
    bundle = _bundle(tmp_path, records)
    capfile = tmp_path / "capture.json"
    capfile.write_text(json.dumps(_capture(OWNER, flt)), encoding="utf-8")
    wsfile = tmp_path / "ws.json"
    wsfile.write_text(json.dumps(WS), encoding="utf-8")
    jobsfile = tmp_path / "jobs.jsonl"
    r = _run(tmp_path, bundle, "--allow-t3", "project", "copy-plan", "--target", OWNER, "--copied", str(capfile),
             "--workstreams", str(wsfile), "--jobs", str(jobsfile), "--files-dir", str(tmp_path / "bodies"))
    jobs = ([json.loads(x) for x in jobsfile.read_text(encoding="utf-8").splitlines() if x.strip()]
            if jobsfile.exists() else [])
    return r, jobs


CLI_RECORDS = [{"id": "grant", "repos": ["*"], "approved_on": "2026-01-01"},
               {"id": "withdraw", "repos": ["withdrawn-x"], "approved": False, "approved_on": "2026-10-01"}]


def test_cli_copy_plan_holds_the_withdrawn_filter(tmp_path):
    r, jobs = _cli(tmp_path, CLI_RECORDS, f"repo:{OWNER}/withdrawn-x workstream:Research")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not _backlog(jobs), [j["id"] for j in jobs]
    assert "view-filter-held" in r.stdout + r.stderr and "t3-signoff:" in r.stdout + r.stderr, r.stdout + r.stderr


def test_cli_copy_plan_permitted_filter_carries_the_signoff_id(tmp_path):
    r, jobs = _cli(tmp_path, CLI_RECORDS, f"repo:{OWNER}/kept-y workstream:Research")
    assert r.returncode == 0, r.stdout + r.stderr
    got = _backlog(jobs)
    assert len(got) == 1 and got[0].get("signoff_id") == "grant", [j["id"] for j in jobs]


# Grouping parentheses (issue 23, P1): a parenthesized positive qualifier authorizes and stamps like a bare one.
def test_filter_repo_refs_ignores_grouping_parentheses():
    from ctshowcase.project import _filter_repo_refs as refs
    assert refs("(repo:A/x) workstream:Research") == ["A/x"]
    assert refs("(repo:A/x OR repo:B/y)") == ["A/x", "B/y"]
    assert refs("((repo:A/x))") == ["A/x"]
    assert refs("(-repo:C/z)") == []
    assert refs("-(repo:A/x)") == ["A/x"]  # fail closed: a negated group still names the repository
    assert refs('repo:"A/(x)"') == ["A/(x)"]  # parentheses inside a quoted value are part of the name


GROUPED_WITHDRAWN = [
    f"(repo:{OWNER}/withdrawn-x) workstream:Research",
    f"(repo:{OWNER}/kept-y repo:{OWNER}/withdrawn-x) workstream:Research",
    f"workstream:Research (repo:{OWNER}/withdrawn-x)",
]


@pytest.mark.parametrize("flt", GROUPED_WITHDRAWN)
def test_grouped_withdrawn_repo_holds_the_job_with_parity(tmp_path, monkeypatch, brand, flt):
    bare = flt.replace("(", "").replace(")", "")
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt)
        ungrouped = _plan(brand, bare)
    assert not _backlog(plan), [j["id"] for j in plan["jobs"]]
    assert _held(plan), plan["logs"]
    assert _t3_codes(plan), plan["logs"]
    assert not _backlog(ungrouped) and _held(ungrouped) and _t3_codes(ungrouped), ungrouped["logs"]


@pytest.mark.parametrize("flt", GROUPED_WITHDRAWN)
def test_grouped_withdrawn_repo_without_a_record_holds_the_job(tmp_path, monkeypatch, brand, flt):
    with _Strict(monkeypatch, _file(tmp_path, [])):
        plan = _plan(brand, flt)
    assert not _backlog(plan), [j["id"] for j in plan["jobs"]]
    assert _held(plan), plan["logs"]
    assert _t3_codes(plan), plan["logs"]


def test_grouped_permitted_repo_keeps_the_job_and_carries_the_signoff_id(tmp_path, monkeypatch, brand):
    flt = f"(repo:{OWNER}/kept-y) workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt)
    jobs = _backlog(plan)
    assert len(jobs) == 1, [j["id"] for j in plan["jobs"]]
    assert jobs[0].get("signoff_id") == "t3s-all", jobs[0]
    assert not _held(plan) and not _t3_codes(plan), plan["logs"]


def test_grouped_t1_only_repo_emits_one_unstamped_job(tmp_path, monkeypatch, brand):
    flt = f"(repo:{T1}/some-repo) workstream:Research"
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _plan(brand, flt)
    jobs = _backlog(plan)
    assert len(jobs) == 1, [j["id"] for j in plan["jobs"]]
    assert "signoff_id" not in jobs[0], jobs[0]
    assert not _held(plan), plan["logs"]
