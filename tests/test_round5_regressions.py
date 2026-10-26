"""Round 5 (final coherence pass, decision-log rows K01-K16): user decisions 12/13/18 n/a rules, review q27/q57/q92
defaults, the command-name contract and the read-only commands the orchestrator calls by name. Synthetic Northwind
data and public org logins only."""
import copy
import json
from pathlib import Path

import pytest
import yaml

from conftest import ROOT, run_cli


# ---------------------------------------------------------------------------------------------------------------------
# K10: brand.yaml former_slugs
# ---------------------------------------------------------------------------------------------------------------------
def test_every_brand_org_row_carries_former_slugs(brand):
    for login, row in brand.raw["orgs"].items():
        assert isinstance(row.get("former_slugs"), list), login


def test_resolver_reads_a_filled_brand_former_slug(brand, tmp_path):
    from ctshowcase.config import load_brand
    from ctshowcase.resolver import Resolver
    raw = copy.deepcopy(brand.raw)
    raw["orgs"]["Northwind-Trading-Co"]["former_slugs"] = ["Northwind-Trading-Old"]
    cfg = tmp_path / "brand.yaml"
    cfg.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    b = load_brand(cfg)
    r = Resolver(b, {}, None)
    assert r.canonical("Northwind-Trading-Old") == "Northwind-Trading-Co"
    assert r.canonical("northwind-trading-old") == "Northwind-Trading-Co"
    assert b.org("Northwind-Trading-Old")["display_name"] == "Northwind Trading Co."
    assert "northwind-trading-old" in [a.lower() for a in r.aliases("Northwind-Trading-Co")]


# ---------------------------------------------------------------------------------------------------------------------
# K09: §5.3a org membership topics, no completetech-llc alias, topics --also-in / --registry
# ---------------------------------------------------------------------------------------------------------------------
def test_org_topics_map_and_alias(brand):
    from ctshowcase.detect import standard
    t = standard("topics")
    assert "completetech-llc" not in t["aliases"]
    assert t["org_topics"]["CompleteTech-LLC"] == "completetech-llc"
    assert t["org_topics"]["romgenie-following-repos"] is None and t["org_topics"]["romgenie-archive-repostiory"] is None
    assert t["org_topics"]["CompleteTech-Pokemon"] == "completetech-tcg"


def test_also_in_adds_membership_topics_after_family(make_ctx):
    from ctshowcase import topics
    ctx = make_ctx(topics=["completetech-llc"], description="Run the Northwind triage agent for support tickets.")
    r = topics.merge(ctx, ["CompleteTech-Skills", "Northwind-Trading-Co", "romgenie-following-repos", "Pick-Your-AI",
                           "No-Such-Org-Here"])
    p = r["proposed"]
    assert p[0] == "completetech" and p[1] == "completetech-skills" and p[2] == ctx.det["type"]
    assert "completetech-llc" not in p  # no alias: an LLC membership topic is never collapsed into the brand
    assert {"org-topic-home:Northwind-Trading-Co", "org-topic-none:romgenie-following-repos",
            "t3-signoff:also-in:Pick-Your-AI", "needs-input:org-topic:No-Such-Org-Here"} <= set(r["logs"])


def test_also_in_from_metadata_and_cap(make_ctx):
    from ctshowcase import topics
    ctx = make_ctx(also_in=["CompleteTech-LLC"])
    assert "completetech-llc" in topics.merge(ctx)["proposed"]
    many = ["CompleteTech-LLC", "CompleteTech-Skills", "CompleteTech-Data", "CompleteTech-Games", "CompleteTech-Creative",
            "CompleteTech-Commerce", "CompleteTech-Hardware", "CompleteTech-Directories", "CompleteTech-DiscordApps"]
    r = topics.merge(make_ctx(), many)
    assert len(r["proposed"]) <= 10 and any(x.startswith("topics-over:") for x in r["logs"])
    assert r["proposed"].index(make_ctx().det["type"]) == len([x for x in r["proposed"] if x.startswith("completetech")])


def test_fork_also_in_carries_membership_topic(make_ctx):
    from ctshowcase import topics
    ctx = make_ctx(fork=True, parent={"full_name": "upstream/tool", "topics": ["python", "llm"]})
    r = topics.merge(ctx, ["CompleteTech-LLC"])
    assert r["proposed"][:2] == ["fork", "completetech-llc"]


def test_topics_cli_also_in_and_registry(tmp_path):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "support-triage-agent", "visibility": "public",
                                "description": "Run the Northwind triage agent.", "topics": []}), encoding="utf-8")
    p = run_cli("--meta", meta, "--no-repo-dir", "topics", "--also-in", "CompleteTech-Skills")
    assert "completetech-skills" in json.loads(p.stdout)["proposed"]
    reg = tmp_path / "estate.yaml"
    reg.write_text(yaml.safe_dump({"orgs": {"Northwind-Trading-Co": {"also_in_outgoing": [
        {"repo": "support-triage-agent", "also_in": ["CompleteTech-Data"]}]}}}), encoding="utf-8")
    p = run_cli("--meta", meta, "--no-repo-dir", "topics", "--registry", reg)
    assert "completetech-data" in json.loads(p.stdout)["proposed"]


# ---------------------------------------------------------------------------------------------------------------------
# K15 / K16: project copy-plan display name and the project-visibility key forms
# ---------------------------------------------------------------------------------------------------------------------
def _resolver(brand, rows=()):
    from ctshowcase.resolver import Resolver
    return Resolver(brand, {}, {"rows": set(rows), "ids": set(), "answers": {}, "actions": [], "extra": []})


def test_copy_plan_never_titles_a_board_with_the_raw_login(brand):
    from ctshowcase import project as PJ
    from ctshowcase.errors import NeedsInput
    with pytest.raises(NeedsInput) as e:  # CompleteTech-TCG before its rename is approved: no brand row
        PJ.copy_plan("CompleteTech-TCG", resolver=_resolver(brand))
    assert e.value.log == "needs-input:display-name" and e.value.code == 4
    ok = PJ.copy_plan("CompleteTech-TCG", resolver=_resolver(brand), display_name="CompleteTech TCG")
    assert ok["title"] == "CompleteTech TCG — Workstreams"
    assert PJ.copy_plan("Northwind-Trading-Co", resolver=_resolver(brand))["title"] == "Northwind Trading Co. — Workstreams"


def test_copy_plan_cli_appends_nothing_without_display_name(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    p = run_cli("project", "copy-plan", "--target", "Northwind-Renamed-Org", "--jobs", jobs)  # no brand row
    assert p.returncode == 4 and "needs-input:display-name" in p.stdout and not jobs.exists()


def test_project_visibility_accepts_the_guard_key_form(brand):
    from ctshowcase import project as PJ
    raw = json.loads((ROOT / "tests" / "fixtures" / "project" / "copy-capture.json").read_text(encoding="utf-8"))
    raw["data"]["organization"]["projectV2"]["public"] = True
    N = "Northwind-Trading-Co"
    assert PJ.lint(raw, owner=N, resolver=_resolver(brand))["cells"]["visibility"] == "fail"
    guard_form = _resolver(brand, rows=[("graphql", "project-visibility", "*", "")])
    assert guard_form.project_visibility_approved(N) and not guard_form.project_visibility_approved("@me")
    assert PJ.lint(raw, owner=N, resolver=guard_form)["cells"]["visibility"] == "pass"
    assert _resolver(brand, rows=[("project-visibility", N, "*", "")]).project_visibility_approved(N)
    assert PJ.lint(raw, role="estate", resolver=guard_form)["cells"]["visibility"] == "fail"  # the Estate stays private


# ---------------------------------------------------------------------------------------------------------------------
# K08: footer --check --online (Phase 4.0 hard gate)
# ---------------------------------------------------------------------------------------------------------------------
def test_footer_online_needs_both_urls_200(brand):
    from ctshowcase import footer
    seen = []

    def ok(url):
        seen.append(url)
        return 200
    st, rows = footer.online(brand, head=ok)
    assert st == "pass" and len(rows) == 2 and set(seen) == {brand.raw["footer"]["logo_light_url"],
                                                             brand.raw["footer"]["logo_dark_url"]}
    st, rows = footer.online(brand, head=lambda u: 404 if u.endswith("logo-dark.png") else 200)
    assert st == "fail:offline" and [r["result"] for r in rows] == ["pass", "fail"]
    assert footer.online(brand, head=lambda u: None)[0] == "fail:offline"


def test_footer_check_online_cli(tmp_path, monkeypatch, brand):
    import importlib.util
    spec = importlib.util.spec_from_file_location("showcase_cli_k08", ROOT / "scripts" / "showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    from ctshowcase import footer
    readme = tmp_path / "README.md"
    readme.write_text("# X\n\n## License\n\nMIT.\n\n" + footer.block(brand) + "\n", encoding="utf-8")
    monkeypatch.setattr(footer, "_head", lambda url, timeout=20.0: 404)
    monkeypatch.setattr(footer.online, "__defaults__", (footer._head,))
    args = cli.parser().parse_args(["footer", "--check", str(readme), "--online"])
    args.format = "json"
    out, code = cli.cmd_footer(args)
    assert code == 1 and out["result"] == "fail:offline" and "footer-urls-offline" in out["logs"]
    monkeypatch.setattr(footer.online, "__defaults__", (lambda url: 200,))
    out, code = cli.cmd_footer(args)
    assert code == 0 and out["result"] == "pass" and len(out["online"]) == 2
    assert run_cli("footer", "--online").returncode == 2  # --online goes with --check


# ---------------------------------------------------------------------------------------------------------------------
# K05: lint public-leak FILE... and lint prose
# ---------------------------------------------------------------------------------------------------------------------
ESTATE = ROOT / "examples" / "estate"


def _estate_cli(*args):
    import os
    import subprocess
    import sys
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(ESTATE))
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True, env=env)


def test_lint_public_leak_any_file(tmp_path):
    clean, leak = tmp_path / "clean.md", tmp_path / "leak.md"
    clean.write_text("See [support-triage-agent](https://github.com/Northwind-Trading-Co/support-triage-agent).\n")
    leak.write_text("Our private-pricing-engine powers quotes.\n")
    p = _estate_cli("lint", "public-leak", clean, leak, "--meta-dir", ESTATE / "meta")
    rows = [json.loads(x) for x in p.stdout.splitlines()]
    assert p.returncode == 1 and rows[0]["result"] == "pass"
    assert rows[1]["result"] == "fail" and any("private-pricing-engine" in h for h in rows[1]["hits"])
    p = _estate_cli("lint", "public-leak", clean)  # no metadata: every repository counts as private (fails closed)
    assert p.returncode == 1 and "needs-input:meta-dir" in p.stdout


def test_lint_prose_brand_emoji_placeholder_and_description(tmp_path):
    from ctshowcase import prose
    r = prose.lint_text("Built by Complete Tech LLC with Pokemon cards. TODO: more \U0001F680")
    assert r["result"] == "fail" and {"brand:Complete Tech", "brand:Pokemon", "emoji", "placeholder"} <= set(r["logs"])
    ok = prose.lint_text("Built by CompleteTech LLC. See [repo](https://github.com/CompleTetech-Security/x) and "
                         "`complete-tech` in code; the CompleteTech-Pokemon org sells Pokémon cards.")
    assert ok["result"] == "pass", ok
    kept = prose.lint_text("Made by Completetech folks.", preserved=True)
    assert kept["result"] == "pass" and kept["warns"] and "brand:Completetech" in kept["logs"]
    t = prose.lint_text("Teh tool.", dictionary={"teh": "the"})
    assert t["result"] == "fail" and "typo:Teh" in t["logs"]
    assert prose.lint_text("Teh tool.", dictionary={"teh": "the"}, preserved=True)["result"] == "pass"
    p = run_cli("lint", "prose", "--prose-kind", "description", "--text", "Generate invoices for Northwind Trading Co.",
                "--text", "generate invoices")
    rows = [json.loads(x) for x in p.stdout.splitlines()]
    assert p.returncode == 1 and rows[0]["result"] == "pass" and rows[1]["result"] == "fail"


# ---------------------------------------------------------------------------------------------------------------------
# K07: contact-sheet --org ORG --cross-surface (G4)
# ---------------------------------------------------------------------------------------------------------------------
def test_contact_sheet_cross_surface(tmp_path):
    from PIL import Image
    ex = ROOT / "assets" / "examples"
    out = tmp_path / "skills-g4.png"
    p = run_cli("--format", "json", "contact-sheet", "--org", "CompleteTech-Skills", "--cross-surface", "--out", out,
                "--avatar", ROOT / "examples" / "orgs" / "CompleteTech-Skills" / "avatar-500.png",
                "--banner", ROOT / "docs" / "images" / "banner.png", "--card", ex / "card-example.png",
                "--social", ex / "social-preview-example.png")
    r = json.loads(p.stdout)
    assert p.returncode == 0 and r["result"] == "incomplete" and r["logs"] == ["needs-input:cross-surface:org_banner"]
    dark, light = (Path(x) for x in r["outputs"])
    assert dark.name == "skills-g4.on-github-dark.png" and light.name == "skills-g4.on-github-light.png"
    assert Image.open(dark).convert("RGB").getpixel((2, 2)) == (13, 17, 23)
    assert Image.open(light).convert("RGB").getpixel((2, 2)) == (255, 255, 255)
    assert run_cli("contact-sheet", "--cross-surface", "--out", out).returncode == 2  # needs --org
    assert run_cli("contact-sheet", "--org", "BunsDev", "--cross-surface", "--out", out,
                   "--banner", ROOT / "docs" / "images" / "banner.png").returncode == 2  # excluded owner


# ---------------------------------------------------------------------------------------------------------------------
# K04: command-name contract (content social primary; social-preview hidden and deprecated; org-banner/org-tile top level)
# ---------------------------------------------------------------------------------------------------------------------
def test_social_preview_is_a_hidden_deprecated_alias(tmp_path):
    top = run_cli("--help").stdout
    assert "org-banner" in top and "org-tile" in top and "content" in top
    assert not any(ln.strip().startswith("social-preview") for ln in top.splitlines())
    assert run_cli("social-preview", "--help").returncode == 0
    meta = ROOT / "examples" / "meta" / "northwind-support-triage-agent.json"
    repo = ROOT / "examples" / "repos" / "northwind-support-triage-agent"
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    p = run_cli("--meta", meta, "--repo-dir", repo, "--format", "json", "social-preview", "--out", a)
    assert p.returncode == 0 and "deprecated:social-preview (use content social)" in json.loads(p.stdout)["logs"]
    q = run_cli("--meta", meta, "--repo-dir", repo, "content", "social", "--out", b)
    assert q.returncode == 0 and "deprecated:social-preview (use content social)" not in q.stdout
    assert a.read_bytes() == b.read_bytes()
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    ref = skill[skill.index("## Command Reference"):]
    assert "\nsocial-preview " not in ref and "content social" in ref and "\norg-banner " in ref and "\norg-tile " in ref


# ---------------------------------------------------------------------------------------------------------------------
# K11: org profile --user CompleteDotTech
# ---------------------------------------------------------------------------------------------------------------------
def _user_estate(tmp_path, who_what):
    reg = yaml.safe_load((ESTATE / "registry" / "estate.yaml").read_text(encoding="utf-8"))
    reg["profile"].update({
        "name": "Example Steward", "blog": "https://www.complete.tech", "location": "Cincinnati, OH",
        "intro": {"tagline": "Innovation at Every Integration"}, "who_what": who_what,
        "socials": [{"label": "X", "url": "https://x.com/CompleteTechLLC"}],
        "pins": [{"repo": "Northwind-Trading-Co/support-triage-agent", "why": "Internal reason that never ships publicly."},
                 {"repo": "Northwind-Trading-Co/private-pricing-engine", "why": "Private; must be dropped."}],
        "more_projects": ["Northwind-Trading-Co/order-ledger"]})
    root = tmp_path / "bundle"
    (root / "registry").mkdir(parents=True)
    (root / "registry" / "estate.yaml").write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")
    return root


def _user_cli(root, *args):
    import os
    import subprocess
    import sys
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(root))
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), "org", "profile", "--user",
                           "CompleteDotTech", "--meta-dir", str(ESTATE / "meta"), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True, env=env)


def test_user_profile_kit_order_and_public_slice(tmp_path):
    root = _user_estate(tmp_path, "I run CompleteTech LLC from Cincinnati, OH. My work lives in the organizations below.")
    out = tmp_path / "profile-repo"
    p = _user_cli(root, "--out-dir", out, "--render")
    r = json.loads(p.stdout)
    assert p.returncode == 0 and r["variant"] == "personal" and not r["leaks"], r
    text = (out / "README.md").read_text(encoding="utf-8")
    order = ["assets/intro.svg", "assets/badges/", "I run CompleteTech LLC", "## Flagship projects", "## Organizations",
             "<summary>More projects", "<summary>Latest activity", "## Contact", "<!-- showcase:footer:start -->"]
    pos = [text.index(x) for x in order]
    assert pos == sorted(pos)
    assert "private-pricing-engine" not in text and "Internal reason" not in text
    assert "featured-dropped:Northwind-Trading-Co/private-pricing-engine" in r["logs"]
    assert (out / "data.json").is_file() and (out / "assets" / "badges" / "x.svg").is_file()
    assert (out / "assets" / "cards" / "Northwind-Trading-Co__support-triage-agent.svg").is_file()
    assert text.rstrip().endswith("<!-- showcase:footer:end -->")


def test_user_profile_leak_writes_nothing(tmp_path):
    root = _user_estate(tmp_path, "My private-pricing-engine sets the prices.")
    out = tmp_path / "profile-repo"
    p = _user_cli(root, "--out-dir", out)
    r = json.loads(p.stdout)
    assert p.returncode == 1 and r["result"] == "fail" and any("private-pricing-engine" in h for h in r["leaks"])
    assert not out.exists()
    import os
    import subprocess
    import sys
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(root))
    q = subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), "org", "profile", "--user", "romgenie"],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert q.returncode == 2  # decision 3: the romgenie account is never changed


# ---------------------------------------------------------------------------------------------------------------------
# K06: new, adopt and doctor --estate (read only)
# ---------------------------------------------------------------------------------------------------------------------
def test_new_prints_create_job_then_adopt(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    p = run_cli("new", "Northwind-Trading-Co/invoice-parser-cli", "--type", "cli", "--description",
                "Parse Northwind invoices into JSON.", "--jobs", jobs)
    r = json.loads(p.stdout)
    assert p.returncode == 0 and r["command"] == "new"
    create = r["jobs"][0]
    assert create["argv"][:6] == ["gh", "repo", "create", "Northwind-Trading-Co/invoice-parser-cli", "--template",
                                  "CompleteTech-LLC/completetech-repo-template"] and "--private" in create["argv"]
    kinds = [j["kind"] for j in r["jobs"]]
    assert kinds[:3] == ["create-repo", "repo-settings", "topics"]
    assert "security" not in kinds  # a new repository is private: PVR and alerts apply once it is public
    assert "delete_branch_on_merge=true" in r["jobs"][1]["argv"]
    assert len(jobs.read_text().splitlines()) == len(r["jobs"])
    assert run_cli("new", "Northwind-Trading-Co/Bad_Name", "--type", "cli").returncode == 2
    assert run_cli("new", "Northwind-Trading-Co/tool-new", "--type", "cli").returncode == 2  # N4 filler suffix
    assert run_cli("new", "Northwind-Trading-Co/good-tool", "--type", "not-a-type").returncode == 2
    assert run_cli("new", "BunsDev/thing", "--type", "cli").returncode == 2
    assert run_cli("new", "romgenie-following-repos/thing", "--type", "cli").returncode == 2


def test_adopt_public_repo_settings_topics_labels_security(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "support-triage-agent", "visibility": "public",
                             "description": "Run the Northwind triage agent.", "topics": ["wip"], "language": "Python",
                             "license": "MIT", "has_issues": False, "delete_branch_on_merge": False,
                             "labels": [{"name": "bug", "color": "d73a4a", "description": ""}]}), encoding="utf-8")
    p = run_cli("--meta", m, "--no-repo-dir", "adopt", "Northwind-Trading-Co/support-triage-agent")
    r = json.loads(p.stdout)
    assert p.returncode == 0, p.stdout + p.stderr
    kinds = [j["kind"] for j in r["jobs"]]
    assert {"repo-settings", "topics", "labels", "security", "browser"} <= set(kinds)
    settings = next(j for j in r["jobs"] if j["kind"] == "repo-settings")["argv"]
    assert "has_issues=true" in settings and "delete_branch_on_merge=true" in settings and "has_wiki=false" not in settings
    sec = [j["argv"][-1] for j in r["jobs"] if j["kind"] == "security"]
    assert sec == ["repos/Northwind-Trading-Co/support-triage-agent/private-vulnerability-reporting",
                   "repos/Northwind-Trading-Co/support-triage-agent/vulnerability-alerts"]
    assert any(j.get("ui_action") == "social-preview" for j in r["jobs"])
    assert any("About sidebar" in c for c in r["checklist"]) and r["pending"]
    for j in r["jobs"]:
        assert j["kind"] == "browser" or j["argv"][0] == "gh"
    assert run_cli("--meta", m, "--no-repo-dir", "adopt", "Northwind-Trading-Co/other").returncode == 2  # wrong meta


def test_doctor_estate_classifies_unregistered_and_diffs_template(tmp_path):
    import shutil
    md = tmp_path / "meta"
    shutil.copytree(ESTATE / "meta", md)
    base = {"owner": "Northwind-Trading-Co", "visibility": "public", "description": "x", "files": ["README.md"]}
    for name, extra in (("upstream-copy-fork", {"fork": True, "ahead_by": 0, "parent": {"full_name": "pallets/flask"}}),
                        ("ledger-backup-20240101", {}), ("Shiny_Tool", {"default_branch": "master"}),
                        ("empty-one", {"files": []})):
        (md / f"{name}.json").write_text(json.dumps(dict(base, repo=name, **extra)), encoding="utf-8")
    tpl, co = tmp_path / "template", tmp_path / "checkouts"
    (tpl / ".github" / "workflows").mkdir(parents=True)
    (tpl / ".github" / "workflows" / "showcase.yml").write_text("name: Showcase\n")
    (tpl / ".editorconfig").write_text("root = true\n")
    born = co / "Northwind-Trading-Co__order-ledger"
    (born / ".github" / "workflows").mkdir(parents=True)
    (born / ".github" / "workflows" / "showcase.yml").write_text("name: Showcase (old)\n")
    out = tmp_path / "NEW_PROPOSALS.yaml"
    out.write_text(yaml.safe_dump({"proposals": [{"id": "manual-1", "kind": "keep", "repo": "x"}]}))
    p = _estate_cli("doctor", "--estate", "--meta-dir", md, "--template-dir", tpl, "--checkouts", co, "--out", out)
    r = json.loads(p.stdout)
    assert p.returncode == 0 and r["result"] == "proposals", p.stdout + p.stderr
    kinds = {(x["repo"], x["kind"]) for x in r["proposals"]}
    assert ("upstream-copy-fork", "move") in kinds and ("ledger-backup-20240101", "archive") in kinds
    assert ("Shiny_Tool", "rename") in kinds and ("Shiny_Tool", "rename-default-branch") in kinds
    assert ("empty-one", "delete") in kinds
    assert not any(x["repo"] == "support-triage-agent" for x in r["proposals"])  # registered repos are not intake
    assert {(d["file"], d["status"]) for d in r["drift"]} == {(".github/workflows/showcase.yml", "differs"),
                                                               (".editorconfig", "missing")}
    saved = yaml.safe_load(out.read_text())["proposals"]
    assert saved[0]["id"] == "manual-1" and len(saved) == 1 + len(r["proposals"])
    again = _estate_cli("doctor", "--estate", "--meta-dir", md, "--out", out)  # re-run replaces only its own entries
    assert len(yaml.safe_load(out.read_text())["proposals"]) == len(saved) and json.loads(again.stdout)["drift"] == []


# ---------------------------------------------------------------------------------------------------------------------
# K01: doctor n/a rules mirror STANDARD R13, R14 and R16 (decisions 12, 13, 18)
# ---------------------------------------------------------------------------------------------------------------------
def _doctor(brand, tmp_path, **meta):
    from ctshowcase import doctor
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    repo = tmp_path / meta.get("repo", "r")
    repo.mkdir(exist_ok=True)
    (repo / "README.md").write_text("# Upstream\n\nKept.\n", encoding="utf-8")
    base = {"owner": "CompleteTech-Infrastructure", "visibility": "public", "description": "Run it."}
    return doctor.row(RepoContext(brand, normalize(dict(base, **meta)), repo))["cells"]


def test_doctor_forks_backups_and_dot_github_need_banner_icon_footer(brand, tmp_path):
    for meta in ({"repo": "cockpit-podman", "fork": True}, {"repo": "old-tool-backup-20240101"},
                 {"repo": ".github"}):
        c = _doctor(brand, tmp_path, **meta)
        assert c["banner"] == "fail" and c["icon"] == "fail" and c["footer"] == "fail", (meta, c)
    assert _doctor(brand, tmp_path, repo="cockpit-podman", fork=True)["card"] == "n/a"
    watching = _doctor(brand, tmp_path, owner="romgenie-following-repos", repo="up-fork", fork=True)
    assert {watching[k] for k in ("banner", "icon", "card", "footer")} == {"n/a"}
    profile = _doctor(brand, tmp_path, owner="CompleteDotTech", repo="CompleteDotTech")
    assert profile["banner"] == "n/a" and profile["icon"] == "fail"


def test_doctor_preserve_list_banner_na_only_when_unchanged(brand, brand_with, tmp_path):
    from ctshowcase import doctor
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    repo = tmp_path / "creative-studio"
    repo.mkdir()
    (repo / "README.md").write_text('<p align="center"><img src="assets/hero.jpg" alt="Creative Studio"></p>\n\n# Creative Studio\n')
    meta = normalize({"owner": "CompleteTech-Skills", "repo": "creative-studio", "visibility": "public",
                      "description": "Build sprites."})
    assert doctor.row(RepoContext(brand, meta, repo))["cells"]["banner"] == "fail"
    assert doctor.row(RepoContext(brand_with(preserve_banner="unchanged"), meta, repo))["cells"]["banner"] == "n/a"


# ---------------------------------------------------------------------------------------------------------------------
# K02: q57 defaults: banner then nav; nav_first option; preserve-list hero above; header refresh reorders
# ---------------------------------------------------------------------------------------------------------------------
def test_header_order_default_and_nav_first(brand, brand_with):
    from ctshowcase import readme
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    meta = normalize({"owner": "CompleteTech-LLC", "repo": "demo-tool", "visibility": "public", "description": "Run it."})
    out = readme.scaffold(RepoContext(brand, meta, None), "")
    assert out.index("<!-- showcase:banner:start -->") < out.index("<!-- showcase:nav:start -->") < out.index("# Demo Tool")
    nf = readme.scaffold(RepoContext(brand_with(nav_first=True), meta, None), "")
    assert nf.index("<!-- showcase:nav:start -->") < nf.index("<!-- showcase:banner:start -->")
    # a README written in the old order is reordered by the header refresh (what the Action runs)
    ctx = RepoContext(brand, meta, None)
    assert readme.header_only(ctx, nf).index("<!-- showcase:banner:start -->") < \
        readme.header_only(ctx, nf).index("<!-- showcase:nav:start -->")
    assert readme.header_only(RepoContext(brand_with(nav_first=True), meta, None), nf) == \
        readme.header_only(RepoContext(brand_with(nav_first=True), meta, None), readme.header_only(ctx, nf))


def test_lint_follows_the_configured_order(brand, brand_with, tmp_path):
    from ctshowcase import readme, readmelint
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    meta = normalize({"owner": "CompleteTech-LLC", "repo": "demo-tool", "visibility": "public", "description": "Run it.",
                      "language": "Python", "license": "MIT"})
    (tmp_path / "docs" / "images").mkdir(parents=True)
    (tmp_path / "docs" / "images" / "banner.png").write_bytes(b"x")
    ctx = RepoContext(brand, meta, tmp_path)
    (tmp_path / "README.md").write_text(readme.scaffold(ctx, ""), encoding="utf-8")
    fails = readmelint.lint(ctx, tmp_path / "README.md")["fails"]
    assert not [f for f in fails if "nav line" in f or "hero banner" in f or f.startswith("D13")], fails
    nf = RepoContext(brand_with(nav_first=True), meta, tmp_path)
    assert any("nav line must be the first line" in f for f in readmelint.lint(nf, tmp_path / "README.md")["fails"])


# ---------------------------------------------------------------------------------------------------------------------
# K03: §7.4 G short form for 0-ahead forks outside the watching org
# ---------------------------------------------------------------------------------------------------------------------
def test_fork_note_short_form_when_zero_ahead(make_ctx):
    from ctshowcase import readme
    parent = {"full_name": "upstream/tool", "default_branch": "main"}
    zero = make_ctx(fork=True, repo="tool", parent=parent, ahead_by=0)
    out = readme.upgrade(zero, "# Tool\n")[0]
    assert "> **Fork of [upstream/tool](https://github.com/upstream/tool)**, kept by" in out
    assert "changes" not in out.split("# Tool")[0].split("[!NOTE]")[1]  # claims no changes
    unknown = make_ctx(fork=True, repo="tool", parent=parent)
    out_u = readme.upgrade(unknown, "# Tool\n")[0]
    assert "kept by" in out_u and "needs-input:ahead-by" in unknown.logs
    ahead = make_ctx(fork=True, repo="tool", parent=parent, ahead_by=4)
    assert "compare with upstream" in readme.upgrade(ahead, "# Tool\n")[0]
    for o in (out, out_u):
        assert o.index("docs/images/banner.png") < o.index("[!NOTE]") < o.index("# Tool") < o.index("showcase:footer:start")


def test_fork_full_treatment_needs_the_variant(make_ctx, brand_with):
    from ctshowcase import readme
    from ctshowcase.context import RepoContext
    ctx = make_ctx(fork=True, repo="tool", parent={"full_name": "upstream/tool"}, ahead_by=2)
    full = RepoContext(brand_with(fork_readme="full"), ctx.meta, None)
    readme.upgrade(full, "# Tool\n")
    assert any(x.startswith("needs-input:fork-variant") for x in full.logs)


def test_user_profile_lists_a_pinned_slug_fork_without_a_card(tmp_path):
    """A `-fork` copy (type rule 1) has no card in `card` or doctor: the personal profile lists it as a line and stays
    complete (GitHub forks are left out of the pins altogether)."""
    import os
    import shutil
    import subprocess
    import sys
    root = _user_estate(tmp_path, "I run CompleteTech LLC from Cincinnati, OH. My work lives in the organizations below.")
    reg_path = root / "registry" / "estate.yaml"
    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    reg["profile"]["pins"].insert(0, {"repo": "Northwind-Trading-Co/upstream-fork"})
    reg_path.write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")
    metas = tmp_path / "meta"
    shutil.copytree(ESTATE / "meta", metas)
    copy = metas / "Northwind-Trading-Co__upstream-fork.json"
    copy.write_text(json.dumps(dict(json.loads(copy.read_text(encoding="utf-8")), fork=False)), encoding="utf-8")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), "org", "profile", "--user",
                        "CompleteDotTech", "--meta-dir", str(metas)], cwd=ROOT, capture_output=True, text=True,
                       env=dict(os.environ, SHOWCASE_ESTATE_ROOT=str(root)))
    r = json.loads(p.stdout)
    assert "card-fallback:Northwind-Trading-Co/upstream-fork:exempt:no-card" in r["logs"], r["logs"]
    assert "cards/Northwind-Trading-Co__upstream-fork.svg" not in r["readme"] and "upstream-fork" in r["readme"]
    assert "Northwind-Trading-Co/upstream-fork" not in [a.get("repo") for a in r["assets"] if a["kind"] == "card"]
    assert r["result"] == "ok", r["logs"]
