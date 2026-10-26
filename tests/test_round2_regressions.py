"""Regression tests for the round-2 review (functional defects 1-16 and the visual review P1-P3)."""
import importlib.util
import json
import shutil
import subprocess
import sys

import pytest
from PIL import Image

from conftest import EX, FIX, ROOT, run_cli
from ctshowcase import readme as R
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

TEMPLATE = ROOT.parent / "template"
needs_template = pytest.mark.skipif(not (TEMPLATE / "README.md").is_file(), reason="template checkout not beside the skill")


def _meta(tmp_path, **kw):
    base = {"owner": "CompleteTech-LLC", "repo": "invoice-parser-cli", "visibility": "public",
            "description": "Parse supplier invoices into structured JSON from the command line.", "created_at": "2026-10-25T00:00:00Z"}
    base.update(kw)
    p = tmp_path / "meta.json"
    p.write_text(json.dumps(base))
    return p


def _child(tmp_path):
    d = tmp_path / "repo"
    shutil.copytree(TEMPLATE, d)
    return d


# -- 1, 2, 6, 7, 12: bootstrap -----------------------------------------------------------------------------------
@needs_template
def test_security_bootstrap_variant_f_licensing_and_lint(tmp_path):
    d = _child(tmp_path)
    m = _meta(tmp_path, owner="CompleTetech-Security", repo="acme-cve-2026-12345-check",
              description="Detect CVE-2026-12345 in Acme Gateway deployments without exploitation.")
    p = run_cli("--meta", m, "--repo-dir", d, "readme", "--bootstrap", "--write")
    assert p.returncode == 0, p.stdout + p.stderr
    text = (d / "README.md").read_text()
    assert "## Licensing" in text and "## License\n" not in text and "AGPL-3.0" in text
    assert not [ln for ln in text.splitlines() if ln.startswith("# ")]  # variant F: no H1
    lint = run_cli("--meta", m, "--repo-dir", d, "lint", "readme")
    assert "R7 unexpected H2" not in lint.stdout


def test_slug_title_keeps_cve_ids():
    assert R.slug_title("acme-cve-2026-12345-check") == "Acme CVE-2026-12345 Check"


@needs_template
def test_pristine_hash_protects_human_text(tmp_path):
    d = _child(tmp_path)
    m = _meta(tmp_path)
    assert R.bootstrap_state((d / "README.md").read_text()) == "pristine"
    assert run_cli("--meta", m, "--repo-dir", d, "readme", "--bootstrap", "--write").returncode == 0
    text = (d / "README.md").read_text()
    assert R.bootstrap_state(text) == "pristine"  # the generated body carries its own hash: re-bootstrappable
    text = text.replace("## Install\n\n", "## Install\n\nRun `pipx install invoice-parser-cli` (a person wrote this).\n\n", 1)
    (d / "README.md").write_text(text)
    assert R.bootstrap_state(text) == "edited"
    p = run_cli("--meta", m, "--repo-dir", d, "readme", "--bootstrap", "--write")
    assert p.returncode == 0 and "bootstrap:edited" in p.stdout
    after = (d / "README.md").read_text()
    assert "(a person wrote this)" in after and "template-body:pristine" not in after


def test_old_marker_without_hash_is_not_trusted():
    text = "<!-- showcase:template-body:start -->\n<!-- showcase:template-body:pristine -->\n## About\n\nMine.\n<!-- showcase:template-body:end -->\n"
    assert R.bootstrap_state(text) == "edited"


@needs_template
def test_type_key_rebootstraps_and_for_scopes_overrides(tmp_path):
    d = _child(tmp_path)
    m = _meta(tmp_path)
    p = run_cli("--meta", m, "--repo-dir", d, "--format", "json", "readme", "--bootstrap")
    assert "override-for:CompleteTech-LLC/completetech-repo-template" in p.stdout  # the template's chips stay home
    (d / ".github" / "showcase.yml").write_text("type: research\n")
    run_cli("--meta", m, "--repo-dir", d, "readme", "--bootstrap", "--write")
    text = (d / "README.md").read_text()
    assert "## Findings" in text or "## Data and Sources" in text  # variant D from the configured type


def test_empty_description_empties_tagline(brand, tmp_path):
    ctx = RepoContext(brand, normalize({"owner": "CompleteTech-LLC", "repo": "x", "description": "", "visibility": "public"}),
                      tmp_path)
    text = "<!-- showcase:tagline:start -->\n**Create new CompleteTech repositories.**\n<!-- showcase:tagline:end -->\n"
    out = R.header_only(ctx, text)
    assert "Create new CompleteTech" not in out and "needs-input:description" in ctx.logs


def test_private_license_text_without_license_file(brand, tmp_path):
    for owner in ("CompleteTech-LLC", "CompleTetech-Security"):
        ctx = RepoContext(brand, normalize({"owner": owner, "repo": "internal-scanner", "visibility": "private",
                                            "description": "Scan hosts.", "created_at": "2024-03-01T00:00:00Z"}), tmp_path)
        text = "## License\n\n<!-- showcase:license -->\nNo license is granted.\n\nfooter\n"
        out = R.header_only(ctx, text)
        assert "Proprietary. Copyright (c) 2024 CompleteTech LLC. All rights reserved." in out and "## License\n" in out


# -- 3: keep-existing ---------------------------------------------------------------------------------------------
def test_keep_existing_only_with_an_own_banner(brand, brand_with, tmp_path):
    meta = normalize({"owner": "AI-Ascension", "repo": "new-agent", "visibility": "public", "description": "Run an agent."})
    (tmp_path / "README.md").write_text("# New Agent\n")
    assert RepoContext(brand, meta, tmp_path).art_status()["banner"] is None
    (tmp_path / "README.md").write_text('<p align="center"><img src="assets/hero.png" alt="hero"></p>\n\n# New Agent\n')
    # K02 (q57 aia/pres defaults): the hero goes above the existing banner, so the banner still applies
    assert RepoContext(brand, meta, tmp_path).art_status()["banner"] is None
    unchanged = brand_with(preserve_banner="unchanged")
    assert RepoContext(unchanged, meta, tmp_path).art_status()["banner"] == "exempt:keep-existing"


# -- 4: repo-dir --------------------------------------------------------------------------------------------------
def test_repo_dir_guards(tmp_path):
    m = _meta(tmp_path)
    assert run_cli("--meta", m, "--repo-dir", tmp_path / "missing", "doctor").returncode == 2
    p = run_cli("--meta", m, "banner", cwd=tmp_path)  # cwd is not the checkout the metadata describes
    assert p.returncode == 2 and "--repo-dir" in p.stderr
    repo = tmp_path / "other"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/CompleteTech-Skills/github-showcase-skill"],
                   check=True)
    p = run_cli("--meta", m, "--repo-dir", repo, "describe")
    assert p.returncode == 2 and "checkout of CompleteTech-Skills/github-showcase-skill" in p.stdout


def test_default_out_lands_in_the_target_checkout(tmp_path):
    m = _meta(tmp_path, language="Python", license="MIT")
    repo = tmp_path / "repo"
    repo.mkdir()
    p = run_cli("--meta", m, "--repo-dir", repo, "banner", "--chip", "Python", "--chip", "MIT")
    assert p.returncode == 0, p.stdout + p.stderr
    assert (repo / "docs" / "images" / "banner.png").is_file() and not (ROOT / "docs" / "images" / ".showcase.json").read_text().count(
        "invoice-parser-cli")


# -- 5: labels --plan (K14: --apply is gone; the plan leaves as gh argv and writer jobs) ------------------------------
def test_labels_plan_reads_live_labels_and_emits_jobs(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("showcase_cli", ROOT / "scripts" / "showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    from ctshowcase import meta as M
    live = [{"name": "bug", "color": "d73a4a", "description": ""}, {"name": "enhancement", "color": "a2eeef", "description": ""}]
    monkeypatch.setattr(M, "_gh", lambda path, paginate=False, raw=False: live)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    # a captured tree with no file §6.4 rule 0 reads proves the renames need no checkout
    m = _meta(tmp_path, labels=[], files=["README.md", "src/invoice_parser/cli.py"], files_complete=True)
    gh = tmp_path / "dot-github.json"  # the owner's .github, captured whole, has no default issue form
    gh.write_text(json.dumps({"owner": "CompleteTech-LLC", "repo": ".github", "files": ["README.md"], "files_complete": True}))
    with pytest.raises(SystemExit):  # the write flags no longer exist
        cli.parser().parse_args(["--meta", str(m), "--no-repo-dir", "labels", "--apply", "--yes"])
    jobs = tmp_path / "jobs.jsonl"
    args = cli.parser().parse_args(["--meta", str(m), "--no-repo-dir", "labels", "--plan", "--jobs", str(jobs),
                                    "--org-defaults", str(gh)])
    args.format = "json"
    out, code = cli.cmd_labels(args)
    renames = [o for o in out["ops"] if o["op"] == "rename"]
    assert {o["name"] for o in renames} >= {"bug", "enhancement"}  # renames planned from the live labels
    assert not calls and code == 1 and out["result"] == "fail"  # nothing ran
    assert out["argv"][0][:3] == ["gh", "label", "edit"] and all(a[-2] == "-R" for a in out["argv"])
    lines = [json.loads(x) for x in jobs.read_text().splitlines()]
    assert len(lines) == len(out["argv"]) and lines[0]["kind"] == "labels" and lines[0]["argv"] == out["argv"][0]


# -- 11: fewer than two chips --------------------------------------------------------------------------------------
def test_doctor_banner_incomplete_is_not_done(tmp_path):
    m = _meta(tmp_path)
    repo = tmp_path / "repo"
    (repo / "assets").mkdir(parents=True)
    assert run_cli("--meta", m, "--repo-dir", repo, "banner", "--allow-few-chips").returncode == 0
    run_cli("--meta", m, "--repo-dir", repo, "readme", "--mode", "scaffold", "--write")
    row = json.loads(run_cli("--meta", m, "--repo-dir", repo, "doctor", "--format", "json").stdout)
    assert row["cells"]["banner"] == "incomplete" and row["done"] == "no"


# -- 14: commit script; Action helpers ---------------------------------------------------------------------------------
def test_commit_script_force_and_pr_error():
    s = (ROOT / "scripts" / "action_commit.sh").read_text()
    assert "push --force-with-lease" not in s and "git push --force origin" in s and "gh pr list --head" in s and "::error" in s


def test_action_prepare_foreign_and_drop(tmp_path):
    img = tmp_path / "docs" / "images"
    img.mkdir(parents=True)
    (tmp_path / "assets").mkdir()
    icon = tmp_path / "assets" / "icon.png"
    Image.new("RGBA", (8, 8)).save(icon)
    import hashlib
    sha = hashlib.sha256(icon.read_bytes()).hexdigest()
    (img / ".showcase.json").write_text(json.dumps({"inputs": {"owner": "CompleteTech-LLC", "repo": "completetech-repo-template",
                                                              "icon_sha256": sha}, "outputs": {"banner.png": {}, "card.svg": {}}}))
    (img / "banner.png").write_bytes(b"x")
    h = [sys.executable, str(ROOT / "scripts" / "action_prepare.py")]
    p = subprocess.run([*h, "foreign", "AI-Ascension/new-agent"], cwd=tmp_path, capture_output=True, text=True)
    assert p.stdout.strip() == "true" and not icon.exists()  # the template's icon never stands for the new repository
    subprocess.run([*h, "drop", "banner.png"], cwd=tmp_path, check=True)
    side = json.loads((img / ".showcase.json").read_text())
    assert not (img / "banner.png").exists() and list(side["outputs"]) == ["card.svg"]


def test_action_treats_exempt_like_a_skip():
    s = (ROOT / "action.yml").read_text()
    assert '"$result" = "exempt"' in s and "--allow-few-chips" in s and "allow-unmeasured" in s
    assert "GITHUB_STEP_SUMMARY" in (ROOT / "scripts" / "action_prepare.py").read_text()


# -- 16 and visual -------------------------------------------------------------------------------------------------
def test_metatron_and_prompdev_are_excluded(brand):
    assert brand.owner_status("MetatronAngelAgent") == "excluded" and brand.owner_status("PrompDev") == "excluded"


def test_archived_repo_gets_r6(tmp_path):
    m = _meta(tmp_path, archived=True, labels=[{"name": "bug", "color": "d73a4a", "description": ""}])
    row = json.loads(run_cli("--meta", m, "--no-repo-dir", "doctor", "--format", "json").stdout)
    assert row["cells"]["R6"] != "n/a"


def test_intro_resting_state_is_revealed(tmp_path):
    out = tmp_path / "i.svg"
    assert run_cli("intro", "--profile", "CompleteDotTech", "--out", out).returncode == 0
    svg = out.read_text()
    assert ".g{opacity:0" not in svg and ".f{opacity:0" not in svg and "stroke-dashoffset:0;" in svg
    assert 'class="cm" transform="translate(' in svg and "backwards" in svg


def test_social_preview_and_org_banner(tmp_path):
    m = EX / "meta" / "northwind-support-triage-agent.json"
    p = run_cli("--meta", m, "--repo-dir", EX / "repos" / "northwind-support-triage-agent", "--format", "json", "social-preview",
                "--out", tmp_path / "s.png")
    assert p.returncode == 0 and Image.open(tmp_path / "s.png").size == (1280, 640)
    p = run_cli("org-banner", "--org", "romgenie-archive-repostiory", "--out", tmp_path / "o.jpg")
    assert p.returncode == 0 and Image.open(tmp_path / "o.jpg").size == (1600, 400)


def test_jev_pixel_art_nearest(make_ctx, fonts):
    from ctshowcase import iconbox
    ctx = make_ctx(repo_dir=EX / "repos" / "jev-minesweeper", owner="jevplay-games", repo="jev-minesweeper",
                   description="Two-board Minesweeper race against Jev.")
    nodes, info, fit = iconbox.plate(ctx, fonts, (56, 70, 420, 220), 24, 28)
    pics = [c for n in nodes for c in getattr(n, "children", [n]) if type(c).__name__ == "Picture"]
    assert info["plate"] == "#F386A1" and pics[0].resample == "nearest" and (pics[0].w * 2) % pics[0].image.width == 0


def test_skill_card_uses_mark_light_in_small_boxes(make_ctx, fonts):
    from ctshowcase import card
    info = card.render(make_ctx(owner="CompleteTech-LLC"), fonts)[2]
    assert info["icon"]["source"] == "brand-mark"


def test_fixture_meta_unchanged():
    assert (FIX / "CompleTetech-Security__php2shell-check.json").is_file()
