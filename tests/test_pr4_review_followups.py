"""Follow-ups to the doctor applicability change: every surface that doctor scores, adopt plans and content renders
agrees on one rule (R5 for forks, the user's default-branch keep decision, R10 for the profile capstone and backups)."""
import json

import pytest

from conftest import ROOT, meta_dict, run_cli
from ctshowcase import doctor
from ctshowcase.intake import adopt


@pytest.mark.parametrize("tier,issues,expected", [
    ("T2-R", True, "fail"), ("T2-R", False, "pass"), ("T2-R", None, "unknown"),
    ("T1", True, "pass"), ("T1", None, "pass"),
])
def test_r5_forks_in_utility_orgs_need_issues_off(make_ctx, tier, issues, expected):
    ctx = make_ctx(fork=True, default_branch="develop", has_issues=issues, delete_branch_on_merge=False)
    ctx.org = dict(ctx.org, tier=tier)
    assert doctor.row(ctx)["cells"]["R5"] == expected
    planned = any(j["kind"] == "repo-settings" for j in adopt(ctx, ctx.brand.resolver())["jobs"])
    assert planned == (expected != "pass")  # doctor passes only what adopt has nothing left to change


@pytest.mark.parametrize("policy", ["keep", None])
def test_adopt_honours_the_keep_decision(make_ctx, policy):
    ctx = make_ctx(default_branch="master", default_branch_policy=policy, has_issues=True, delete_branch_on_merge=True)
    r = adopt(ctx, ctx.brand.resolver())
    asks_rename = any("rename-default-branch" in c for c in r["checklist"])
    assert asks_rename == (policy is None)
    assert ("default-branch kept (user)" in r["logs"]) == (policy == "keep")


@pytest.mark.parametrize("owner,repo", [("CompleteDotTech", "CompleteDotTech"),
                                        ("Northwind-Trading-Co", "support-triage-agent-backup-20260101")])
def test_content_social_renders_what_adopt_uploads(tmp_path, owner, repo):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps(meta_dict(owner=owner, repo=repo, uses_custom_og_image=False, has_issues=True,
                                         delete_branch_on_merge=True)), encoding="utf-8")
    out = tmp_path / "sp.png"
    p = run_cli("--meta", meta, "--no-repo-dir", "--format", "json", "content", "social", "--out", out, "--job")
    res = json.loads(p.stdout)
    assert p.returncode == 0, p.stdout + p.stderr
    assert res["result"] == "ok" and out.is_file() and res.get("job"), res
    a = json.loads(run_cli("--meta", meta, "--no-repo-dir", "adopt", f"{owner}/{repo}").stdout)
    assert any(j.get("ui_action") == "social-preview" for j in a["jobs"])
    d = json.loads(run_cli("--meta", meta, "--no-repo-dir", "doctor", "--format", "json").stdout)
    assert d["cells"]["R10"] == "fail"


def test_contract_docs_name_the_group_key_and_archived_adopt():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "group?" in skill and "labels:OWNER/REPO" in skill
    row = next(ln for ln in skill.splitlines() if ln.startswith("| `adopt`"))
    assert "archived" in row and "pending" in row
    log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 1.0.0")[0]
    assert "R11" in log and "T1/T2" in log
