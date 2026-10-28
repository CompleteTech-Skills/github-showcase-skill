"""Follow-ups to the doctor applicability change: every surface that doctor scores, adopt plans and content renders
agrees on one rule (R5 for forks, the user's default-branch keep decision, R10 for the profile capstone and backups)."""
import json

import pytest

from conftest import ROOT, meta_dict, run_cli
from ctshowcase import doctor
from ctshowcase.intake import adopt, classify


CLI_CONFIG = {".github/showcase.yml": "type: cli\n"}
FORKS = {"github": {"fork": True}, "slug": {"repo": "widget-fork", "fork": False},
         "override": {"fork": True, "manifests": CLI_CONFIG},
         "slug-override": {"repo": "widget-fork", "fork": False, "manifests": CLI_CONFIG}}


def fork_ctx(make_ctx, how, **kw):
    """A fork four ways: GitHub's flag, the `-fork` slug rule, and each of them under a `type: cli` repo config."""
    ctx = make_ctx(**FORKS[how], **kw)
    assert (ctx.det["type"] == "cli") == how.endswith("override")
    return ctx


@pytest.mark.parametrize("how", FORKS)
@pytest.mark.parametrize("tier,issues,expected", [
    ("T2-R", True, "fail"), ("T2-R", False, "pass"), ("T2-R", None, "unknown"),
    ("T1", True, "pass"), ("T1", None, "pass"),
])
def test_r5_forks_in_utility_orgs_need_issues_off(make_ctx, how, tier, issues, expected):
    ctx = fork_ctx(make_ctx, how, default_branch="develop", has_issues=issues, delete_branch_on_merge=False)
    ctx.org = dict(ctx.org, tier=tier)
    assert ctx.is_fork
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


@pytest.mark.parametrize("how", FORKS)
def test_doctor_and_adopt_share_the_fork_rule_for_labels(make_ctx, how):
    ctx = fork_ctx(make_ctx, how, has_issues=True, labels=[{"name": "bug", "color": "d73a4a", "description": ""}])
    assert doctor.row(ctx)["cells"]["R6"] == "n/a"
    r = adopt(ctx, ctx.brand.resolver())
    assert "labels:n/a" in r["logs"] and not any(j["kind"] in ("labels", "security") for j in r["jobs"])


@pytest.mark.parametrize("how", FORKS)
def test_forks_get_no_card_under_any_type(make_ctx, how):
    assert fork_ctx(make_ctx, how).art_status()["card"] == "exempt:no-card"  # card, lint all and doctor's card cell


@pytest.mark.parametrize("how", FORKS)
def test_slug_forks_keep_the_fork_rule_under_a_type_override(make_ctx, how):
    ctx = fork_ctx(make_ctx, how, default_branch="develop", has_issues=True, delete_branch_on_merge=True)
    r = adopt(ctx, ctx.brand.resolver())
    assert not any("rename-default-branch" in c for c in r["checklist"])
    assert "rename-default-branch" not in [p["kind"] for p in classify(dict(ctx.meta), ctx.brand, None)]


@pytest.mark.parametrize("fork,repo,r1_na,rename", [
    (True, "Northwind_Widget", True, False),       # GitHub forks keep the upstream name (§3.1)
    (False, "Northwind_Widget-fork", False, True),  # a non-network copy follows `UPSTREAM-fork` naming
])
def test_r1_and_estate_renames_exempt_github_forks_only(make_ctx, brand, fork, repo, r1_na, rename):
    ctx = make_ctx(repo=repo, fork=fork, files=["a.py"])
    assert (doctor.r1(ctx) == "n/a") == r1_na
    assert ("rename" in [p["kind"] for p in classify(dict(ctx.meta), brand, None)]) == rename


@pytest.mark.parametrize("meta,proposed", [
    ({"default_branch": "master"}, True),
    ({"default_branch": "master", "default_branch_policy": "keep"}, False),
    ({"default_branch": "develop", "repo": "widget-fork"}, False),
    ({"default_branch": "develop", "fork": True, "ahead_by": 0}, False),
])
def test_estate_proposals_honour_forks_and_the_keep_decision(brand, meta, proposed):
    kinds = [p["kind"] for p in classify(meta_dict(**meta), brand, None)]
    assert ("rename-default-branch" in kinds) == proposed


@pytest.mark.parametrize("tier,archived", [("T2-R", False), ("T1", True)])
def test_content_social_exempts_a_backup_r10_leaves_out(tmp_path, tier, archived):
    """A backup in the archive org, or an archived one, has no R10 preview: content social exempts it, as before."""
    import yaml
    raw = yaml.safe_load((ROOT / "references" / "brand.yaml").read_text(encoding="utf-8"))
    raw["orgs"]["Northwind-Trading-Co"]["tier"] = tier
    cfg = tmp_path / "brand.yaml"
    cfg.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps(meta_dict(repo="ledger-backup-20240101", archived=archived)), encoding="utf-8")
    out = tmp_path / "sp.png"
    p = run_cli("--config", cfg, "--meta", meta, "--no-repo-dir", "--format", "json", "content", "social", "--out", out,
                "--job")
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "exempt" and not out.exists(), p.stdout + p.stderr
    d = json.loads(run_cli("--config", cfg, "--meta", meta, "--no-repo-dir", "doctor", "--format", "json").stdout)
    assert d["cells"]["R10"] == "n/a"


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


@pytest.mark.parametrize("owners,allow", [("watching", ["--allow-hold"]), ("t3", [])])
@pytest.mark.parametrize("repo,fork", [("ledger-backup-20240101", False), ("widget-fork", False)])
def test_card_exemption_survives_owner_codes(tmp_path, owners, allow, repo, fork):
    """A backup or fork has no card in every owner state: `card` writes none (or the owner gate refuses first) and the
    art_status card slot that lint all, doctor and the profile pages read says exempt:no-card."""
    import yaml

    from ctshowcase.config import Brand
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    raw = yaml.safe_load((ROOT / "references" / "brand.yaml").read_text(encoding="utf-8"))
    raw["owners"][owners] = list(raw["owners"].get(owners) or []) + ["Northwind-Trading-Co"]
    cfg = tmp_path / "brand.yaml"
    cfg.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    m = meta_dict(repo=repo, fork=fork)
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps(m), encoding="utf-8")
    out = tmp_path / "card.svg"
    p = run_cli("--config", cfg, "--meta", meta, "--no-repo-dir", "--format", "json", "card", "--out", out, *allow)
    assert not out.exists(), p.stdout + p.stderr
    if p.returncode == 0:
        assert json.loads(p.stdout)["result"] == "exempt"
    rd = tmp_path / "checkout"
    rd.mkdir()
    (rd / "README.md").write_text("# x\n", encoding="utf-8")
    ctx = RepoContext(Brand(raw, cfg), normalize(m), rd)
    assert ctx.card_exempt() and ctx.art_status()["card"].startswith("exempt")  # a watching fork: bare `exempt`
    assert doctor.row(ctx)["cells"]["card"] == "n/a"
