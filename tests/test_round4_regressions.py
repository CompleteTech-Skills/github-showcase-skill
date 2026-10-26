"""Round-4 review regressions for the org, project, enterprise and content groups (synthetic data only).

Each test pins one defect an agent hit when it ran the groups with no other context: approval ids the writer could never
match, a profile that called a public org private, plans that read as success with nothing checked, and org lookups
that skipped the shared resolver (CQ-03)."""
import json
import os
import subprocess
import sys

from conftest import EX, ROOT

from ctshowcase import content as C
from ctshowcase import org as O
from ctshowcase import project as P
from ctshowcase.errors import NEEDS_INPUT, OK
from ctshowcase.resolver import Resolver

ESTATE = EX / "estate"
N = "Northwind-Trading-Co"
PFIX = ROOT / "tests" / "fixtures" / "project"
OLD, NEW = "CompleteTech-Pokemon", "CompleteTech-TCG"  # org-005: a real rename, not case-only like org-001


def cli(*args, env=None, cwd=ROOT):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, env=e)


def renamed(brand, registry=None):
    """A resolver that knows the approved org-005 rename (CompleteTech-Pokemon -> CompleteTech-TCG)."""
    rows = {("org-rename", OLD, "*", NEW)}
    return Resolver(brand, registry or {}, {"rows": rows, "ids": set(), "answers": {}, "actions": [], "extra": []})


# ------------------------------------------------------------------------------------------- writer jobs
def test_jobs_file_in_a_new_directory_is_created_not_a_traceback(tmp_path):
    jobs = tmp_path / "state" / "plans" / "jobs.jsonl"
    p = cli("org", "about", N, "--jobs", jobs, env={"SHOWCASE_ESTATE_ROOT": str(ESTATE)})
    assert p.returncode == 0, p.stderr
    assert jobs.is_file() and json.loads(jobs.read_text().splitlines()[0])["kind"] == "org-about"


def test_unwritable_path_is_a_usage_error(tmp_path):
    (tmp_path / "f").write_text("x")
    p = cli("enterprise", "plan", "--snapshot", ROOT / "tests" / "fixtures" / "enterprise" / "snapshot-before.json",
            "--jobs", tmp_path / "f" / "jobs.jsonl")  # a file where a directory must be
    assert p.returncode == 2 and "Traceback" not in p.stderr and json.loads(p.stdout)["result"] == "usage"


def test_create_project_jobs_carry_the_q41_approval_ids(tmp_path):
    p = cli("project", "copy-plan", "--target", N, "--source", f"{N}/7")
    job = json.loads(p.stdout)["jobs"][0]
    assert job["kind"] == "create-project" and job["approval_id"] == "q41.orgs"
    p = cli("project", "estate-plan")
    assert json.loads(p.stdout)["jobs"][0]["approval_id"] == "q41.estate"
    p = cli("project", "copy-plan", "--target", N, "--approval-id", "q41.custom")
    assert json.loads(p.stdout)["jobs"][0]["approval_id"] == "q41.custom"


def test_stage_two_jobs_need_files_dir_and_log_no_copy_approval(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    cap = PFIX / "copy-capture.json"
    p = cli("project", "copy-plan", "--target", N, "--copied", cap, "--jobs", jobs)
    assert p.returncode == 2 and not jobs.exists() and "--files-dir" in json.loads(p.stdout)["error"]
    p = cli("project", "copy-plan", "--target", N, "--copied", cap, "--jobs", jobs, "--files-dir", tmp_path / "bodies")
    res = json.loads(p.stdout)
    assert p.returncode == 0 and jobs.is_file()
    assert not any(x.startswith(("needs-approval:create-project", "fallback:direct-copy")) for x in res["logs"])
    for j in res["jobs"]:
        argv = j.get("argv") or []
        if "--input" in argv:
            assert os.path.isabs(argv[argv.index("--input") + 1]) and os.path.isfile(argv[argv.index("--input") + 1])


def test_workflow_toggle_names_the_workflow_file(brand):
    wfs = {"workflows": [{"id": 22, "name": "Stale", "path": ".github/workflows/stale.yml", "state": "active"}]}
    files = {".github/workflows/stale.yml": "name: Stale\non:\n  schedule:\n    - cron: '0 0 * * *'\njobs:\n  s:\n"
                                           "    runs-on: x\n    steps:\n      - uses: actions/stale@v9\n"}
    meta = {"owner": N, "repo": "tool-fork", "fork": True, "parent": {"full_name": "upstream-org/tool"},
            "visibility": "public", "default_branch": "main"}
    res = C.actions_report(meta, workflows=wfs, workflow_files=files, resolver=Resolver(brand, {}, None),
                           approval_ids={"stale.yml": "q79-1"})
    assert [j["argv"] for j in res["jobs"]] == [["gh", "workflow", "disable", "stale.yml", "-R", f"{N}/tool-fork"]]


# ------------------------------------------------------------------------------------------- org profile and labels
def test_retemplate_approval_as_build_approvals_writes_it(brand):
    reg = {"orgs": {N: {"tier": "T1", "final_repos": [".github"]}}}
    r = Resolver(brand, reg, {"rows": {("profile-retemplate", N, ".github", "")}, "ids": set(), "answers": {},
                              "actions": [], "extra": []})
    assert r.approved("profile-retemplate", N, ".github") and not r.approved("profile-retemplate", N)


def test_no_metadata_is_needs_input_not_a_private_org_or_an_empty_plan(tmp_path):
    env = {"SHOWCASE_ESTATE_ROOT": str(ESTATE)}
    p = cli("org", "profile", N, "--out-dir", tmp_path, env=env)
    res = json.loads(p.stdout)
    assert p.returncode == NEEDS_INPUT and res["result"] == "needs-input" and "needs-input:metadata" in res["logs"]
    assert not (tmp_path / "profile").exists()
    p = cli("org", "labels", N, env=env)
    res = json.loads(p.stdout)
    assert p.returncode == NEEDS_INPUT and res["jobs"] == [] and "needs-input:metadata" in res["logs"]
    p = cli("org", "profile", N, "--meta-dir", ESTATE / "meta", env=env)
    assert p.returncode == 0 and json.loads(p.stdout)["variant"] == "kit"


def test_watching_org_profile_ends_with_the_decision_18_footer(brand, tmp_path):
    w = "romgenie-following-repos"
    reg = {"orgs": {w: {"tier": "T2-R", "final_repos": [".github", "tool"], "profile": {"name": "romgenie following"}}}}
    est = O.Estate(brand, Resolver(brand, reg, None))
    est.add_meta({"owner": w, "repo": "tool", "fork": True, "visibility": "public", "description": "A followed tool.",
                  "parent": {"full_name": "upstream-org/tool"}, "pushed_at": "2026-10-01T00:00:00Z"}, "x.json")
    res, code = O.profile(est, w)
    assert code == OK and res["readme"].rstrip().endswith("<!-- showcase:footer:end -->")
    assert res["readme"].count("<picture>") == 1


# ------------------------------------------------------------------------------------------- CQ-03 resolver
def test_metadata_captured_under_the_old_login_is_found_under_the_new_one(brand):
    est = O.Estate(brand, renamed(brand, {"orgs": {OLD: {"tier": "T1"}}}))
    est.add_meta({"owner": OLD, "repo": "tcg-stock-watch", "visibility": "public"}, "x.json")
    assert est.repos_of(NEW) == ["tcg-stock-watch"]


def test_project_links_accept_a_former_login_and_name_the_current_one(brand):
    cap = json.loads((PFIX / "copy-capture.json").read_text())
    plan = P.copy_plan(NEW, copied=cap, repositories=[f"{OLD}/tcg-stock-watch"], resolver=renamed(brand))
    links = [j["argv"] for j in plan["jobs"] if j.get("argv", [None, None])[:3] == ["gh", "project", "link"]]
    assert links and links[0][-1] == f"{NEW}/tcg-stock-watch"
    assert not any(x.startswith("link-skipped") for x in plan["logs"])


def test_workflow_guard_on_a_former_login_is_still_this_repository(brand):
    wf = ("name: Deploy\non: [push]\njobs:\n  d:\n    if: github.repository_owner == 'CompleteTech-Pokemon'\n"
          "    runs-on: x\n    steps:\n      - run: make\n")
    facts = C.workflow_facts(".github/workflows/d.yml", wf, "main", repo=f"{NEW}/tcg-stock-watch", resolver=renamed(brand))
    assert facts["guarded"] is False


def test_a_repository_still_waiting_on_a_transfer_in_is_not_unknown_visibility(brand):
    """The registry homes a repository here after an unapproved transfer: it is not in the org today, so it neither
    blocks the private-org variant nor counts as missing metadata (logged pending-move instead)."""
    reg = {"orgs": {N: {"tier": "T1", "final_repos": [".github", "tool", "ledger"], "profile": {"name": "Northwind"}}}}
    acts = [{"id": "move-9", "owner": "Northwind-Labs", "repo": "tool", "action": "transfer", "target_owner": N}]
    est = O.Estate(brand, Resolver(brand, reg, {"rows": set(), "ids": set(), "answers": {}, "actions": acts, "extra": []}))
    est.add_meta({"owner": "Northwind-Labs", "repo": "tool", "visibility": "public"}, "a.json")
    est.add_meta({"owner": N, "repo": "ledger", "visibility": "private"}, "b.json")
    res, code = O.profile(est, N)
    assert code == OK and res["variant"] == "private" and "pending-move:tool:move-9" in res["logs"]
    assert not any(x.startswith("needs-input:visibility") for x in res["logs"])
    est.metas.pop(f"{N}/ledger".lower())  # now a repository that is here has no metadata: unknown, so no private claim
    res, code = O.profile(est, N)
    assert code == NEEDS_INPUT and "needs-input:visibility:ledger" in res["logs"]
