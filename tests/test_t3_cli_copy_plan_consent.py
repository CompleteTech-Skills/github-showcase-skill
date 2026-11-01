"""CLI-level and captured-repository T3 sign-off regressions for project copy-plan (issue 23). Synthetic records only.

Binding context: t23-adjudication-full-plan-consent-d874.md (UPDATE: the CLI-emitted README job must omit withdrawn
repositories, keep kept repositories and carry the regrant ids) and t23-adjudication-captured-readme-authorization.md
(captured repositories need their own authorization in the README, the workflows job and the settings job).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

BASE = [{"id": "grant", "repos": ["*"], "approved_on": "2026-01-01"},
        {"id": "withdraw", "repos": ["withdrawn-x"], "approved": False, "approved_on": "2026-10-01"}]
REGRANT = BASE + [{"id": "regrant", "repos": ["withdrawn-x"], "approved_on": "2026-10-02"}]


def _cli_run(tmp_path, records, repos=None, captured=None):
    """Run the real `scripts/showcase.py project copy-plan` (org role) and return (result, jobs)."""
    from test_t3_signoff_require import _bundle, _run, OWNER
    from test_project import cap_of
    root = tmp_path
    bundle = _bundle(root, records)
    cap = cap_of("copy-capture.json", OWNER)
    board = cap["data"]["organization"]["projectV2"]
    board["public"] = False
    for number, name, filter_ in [(6, "My items", "assignee:@me -status:Done"),
                                  (7, "Shipped", "status:Done updated:>=@today-30d")]:
        board["views"]["nodes"].append(dict(board["views"]["nodes"][2], id=f"PVTV_n{number}", number=number,
                                            name=name, filter=filter_))
    if captured:
        board["repositories"] = {"nodes": [{"nameWithOwner": x} for x in captured]}
    capfile = root / "capture.json"
    capfile.write_text(json.dumps(cap), encoding="utf-8")
    jobsfile = root / "jobs.jsonl"
    result = _run(root, bundle, "--allow-t3", "project", "copy-plan", "--target", OWNER, "--copied", str(capfile),
                  "--jobs", str(jobsfile), "--files-dir", str(root / "bodies"),
                  *(["--repos", ",".join(repos)] if repos else []))
    jobs = []
    if jobsfile.exists():
        jobs = [json.loads(line) for line in jobsfile.read_text(encoding="utf-8").splitlines() if line.strip()]
    return result, jobs


def _cli_readme(tmp_path, records, repos=None, captured=None):
    """The single README job the CLI emits, as (job, readme_text, all_jobs)."""
    result, jobs = _cli_run(tmp_path, records, repos=repos, captured=captured)
    assert result.returncode == 0, result.stdout + result.stderr
    readmes = [j for j in jobs if "--readme" in j.get("argv", [])]
    assert len(readmes) == 1, [j.get("id") for j in jobs]
    job = readmes[0]
    text = job["argv"][job["argv"].index("--readme") + 1]
    return job, text, jobs


def _ids(job):
    return set(job.get("signoff_ids") or []) | ({job["signoff_id"]} if job.get("signoff_id") else set())


# B) subprocess CLI, org role, explicit --repos -------------------------------------------------------------------
def test_cli_org_readme_mixed_explicit_omits_withdrawn_keeps_kept(tmp_path):
    from test_t3_signoff_require import OWNER
    job, text, _ = _cli_readme(tmp_path, BASE, repos=[f"{OWNER}/withdrawn-x", f"{OWNER}/kept-y"])
    assert "withdrawn-x" not in text, text
    assert "kept-y" in text, text
    ids = _ids(job)
    assert "grant" in ids, job
    assert "regrant" not in ids, job


def test_cli_org_readme_regrant_keeps_repo_and_carries_both_ids(tmp_path):
    from test_t3_signoff_require import OWNER
    job, text, _ = _cli_readme(tmp_path, REGRANT, repos=[f"{OWNER}/withdrawn-x", f"{OWNER}/kept-y"])
    assert "withdrawn-x" in text and "kept-y" in text, text
    assert {"grant", "regrant"} <= _ids(job), job


def test_cli_org_readme_mixed_captured_omits_withdrawn(tmp_path):
    from test_t3_signoff_require import OWNER
    job, text, jobs = _cli_readme(tmp_path, BASE, repos=None,
                                  captured=[f"{OWNER}/withdrawn-x", f"{OWNER}/kept-y"])
    assert "withdrawn-x" not in text, text
    assert "kept-y" in text, text
    assert "grant" in _ids(job), job
    assert not [j["id"] for j in jobs if "-link-" in j["id"]], [j["id"] for j in jobs]


def test_cli_org_readme_no_grant_refuses_whole_run(tmp_path):
    """No record at all. Observed CLI behaviour (not a per-repository omission): the whole run is refused with
    rc 2, result 'refused', log 't3-signoff:missing', and no jobs file is written, so no README is emitted."""
    from test_t3_signoff_require import OWNER
    repos = [f"{OWNER}/withdrawn-x", f"{OWNER}/kept-y"]
    result, jobs = _cli_run(tmp_path, [], repos=repos)
    combined = result.stdout + result.stderr
    assert result.returncode == 2, combined
    out = json.loads(result.stdout)
    assert out.get("result") == "refused", out
    assert "t3-signoff:missing" in out.get("logs", []), out
    assert jobs == [], [j.get("id") for j in jobs]


# C) in-library same-owner captured-repository regressions (all three jobs) ----------------------------------------
def _same_owner_plan(brand, tmp_path, monkeypatch, records, captured, repositories=None):
    from test_t3_emission_scope import _Strict, _file, _resolver, _private_board, OWNER
    from ctshowcase import project as PJ
    board = _private_board()
    board["data"]["organization"]["projectV2"]["repositories"] = {
        "nodes": [{"nameWithOwner": f"{OWNER}/{x}"} for x in captured]}
    with _Strict(monkeypatch, _file(tmp_path, records)):
        return PJ.copy_plan(OWNER, role="org", copied=board, resolver=_resolver(brand), repositories=repositories,
                            allow_t3=True, reviewed="2026-10-25")


def test_same_owner_captured_withdrawn_omitted_across_all_jobs(brand, tmp_path, monkeypatch):
    from test_t3_emission_scope import _workflows, _settings, _readme_jobs
    from test_t3_signoff_withdrawal import T3_WILD
    # repositories=None: the captured same-owner repositories feed README, workflows auto-add and settings alike
    # (t23-adjudication-captured-workflows-settings-12dd.md); each is authorised on its own owner and name.
    plan = _same_owner_plan(brand, tmp_path, monkeypatch, T3_WILD, ["withdrawn-x", "kept-y"])
    readmes = _readme_jobs(plan)
    assert len(readmes) == 1, [j["id"] for j in plan["jobs"]]
    text = readmes[0]["argv"][readmes[0]["argv"].index("--readme") + 1]
    assert "withdrawn-x" not in text, text
    assert "kept-y" in text, text
    assert "t3s-all" in _ids(readmes[0]), readmes[0]
    for j in plan["jobs"]:
        assert "withdrawn-x" not in json.dumps(j), j["id"]
    workflows = _workflows(plan)
    assert workflows, [j["id"] for j in plan["jobs"]]
    adds = [s for j in workflows for s in j["steps"] if "auto-add" in s.lower()]
    assert adds and all("kept-y" in s for s in adds), adds
    assert "t3s-all" in _ids(workflows[0]), workflows[0]
    settings = _settings(plan)
    assert settings, [j["id"] for j in plan["jobs"]]
    for j in settings:
        assert any("kept-y" in s for s in j["steps"]), j["steps"]
        assert "t3s-all" in _ids(j), j
    assert not [j["id"] for j in plan["jobs"] if "-link-" in j["id"]], [j["id"] for j in plan["jobs"]]


def test_same_owner_captured_regrant_retained_across_jobs(brand, tmp_path, monkeypatch):
    from test_t3_emission_scope import _readme_jobs
    from test_t3_signoff_withdrawal import T3_WILD
    recs = [*T3_WILD, {"id": "t3s-regrant", "repos": ["withdrawn-x"], "approved_on": "2026-10-02"}]
    plan = _same_owner_plan(brand, tmp_path, monkeypatch, recs, ["withdrawn-x", "kept-y"])
    readmes = _readme_jobs(plan)
    assert len(readmes) == 1, [j["id"] for j in plan["jobs"]]
    text = readmes[0]["argv"][readmes[0]["argv"].index("--readme") + 1]
    assert "withdrawn-x" in text and "kept-y" in text, text
    ids = _ids(readmes[0])
    assert "t3s-regrant" in ids and "t3s-all" in ids, readmes[0]
    from test_t3_emission_scope import _workflows, _settings
    adds = [s for j in _workflows(plan) for s in j["steps"] if "auto-add" in s.lower()]
    assert adds and all("withdrawn-x" in s for s in adds), adds
    assert "t3s-regrant" in _ids(_workflows(plan)[0])
    for j in _settings(plan):
        assert any("withdrawn-x" in s for s in j["steps"]), j["steps"]
        assert "t3s-regrant" in _ids(j), j


def test_same_owner_captured_all_withdrawn_names_no_repository(brand, tmp_path, monkeypatch):
    from test_t3_emission_scope import _workflows, _settings
    from test_t3_signoff_withdrawal import T3_WILD
    recs = [{"id": "t3s-all", "repos": ["*"], "approved_on": "2026-01-01"},
            {"id": "t3s-wd", "repos": ["withdrawn-x", "withdrawn-z"], "approved": False, "approved_on": "2026-10-01"}]
    plan = _same_owner_plan(brand, tmp_path, monkeypatch, recs, ["withdrawn-x", "withdrawn-z"])
    for j in plan["jobs"]:
        assert "withdrawn-x" not in json.dumps(j) and "withdrawn-z" not in json.dumps(j), j["id"]
    assert not [s for j in _workflows(plan) for s in j["steps"] if "auto-add" in s.lower()]
    assert not _settings(plan), [j["id"] for j in plan["jobs"]]


# 7) distinct controls -----------------------------------------------------------------------------------------------
def test_control_no_repositories_and_no_capture(brand, tmp_path, monkeypatch):
    from test_t3_emission_scope import _Strict, _file, _resolver, _private_board, _readme_jobs, OWNER
    from ctshowcase import project as PJ
    from test_t3_signoff_withdrawal import T3_WILD
    board = _private_board()
    board["data"]["organization"]["projectV2"]["repositories"] = {"nodes": []}
    with _Strict(monkeypatch, _file(tmp_path, T3_WILD)):
        plan = PJ.copy_plan(OWNER, role="org", copied=board, resolver=_resolver(brand), repositories=None,
                            allow_t3=True, reviewed="2026-10-25")
    readmes = _readme_jobs(plan)
    text = " ".join(j["argv"][j["argv"].index("--readme") + 1] for j in readmes)
    assert "withdrawn-x" not in text and "kept-y" not in text, text
    assert not any(str(x).startswith("t3-signoff:") for x in plan["logs"]), plan["logs"]
    assert readmes, [j["id"] for j in plan["jobs"]]
