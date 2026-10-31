"""Regressions found in test round 1 (real estate metadata across every family)."""
import json
from pathlib import Path

import pytest

from conftest import FIX, run_cli

from ctshowcase import footer, readme, readmelint, svglint
from ctshowcase.context import RepoContext
from ctshowcase.errors import NeedsInput
from ctshowcase.meta import normalize


def test_svglint_missing_file_is_a_fail_not_a_crash(tmp_path):
    r = svglint.lint_file("card", tmp_path / "nope.svg")
    assert r["result"] == "FAIL" and r["fails"] == ["missing"]
    p = run_cli("lint", "svg", "--kind", "card", tmp_path / "nope.svg")
    assert p.returncode == 1 and "Traceback" not in p.stderr


def test_failed_capture_is_needs_input(tmp_path):
    bad = tmp_path / "m.json"
    bad.write_text(json.dumps({"owner": "LibreEvolve", "repo": "libreevolve", "error": "{\"message\":\"no access\"}"}))
    with pytest.raises(NeedsInput):
        normalize(json.loads(bad.read_text()))
    p = run_cli("--meta", bad, "--no-repo-dir", "readme")
    assert p.returncode == 4 and "needs-input:metadata" in p.stdout


def test_labels_as_python_repr_are_parsed():
    m = normalize({"owner": "o", "repo": "r", "visibility": "public",
                   "labels": "[{'name': 'bug', 'color': 'D73A4A', 'description': \"Something isn't working\"}]"})
    assert m["labels"] == [{"name": "bug", "color": "d73a4a", "description": "Something isn't working"}]


def test_skill_detected_from_readme_link_without_tree(brand):
    meta = normalize(json.loads((FIX / "CompleteTech-Skills__agentic-email-skill.json").read_text()))
    meta.pop("files", None)
    meta.pop("manifests", None)
    meta["readme_head"] = "**CompleteTech LLC Skills** · [Agent instructions](SKILL.md)\n\n# Agentic Email Skill\n"
    ctx = RepoContext(brand, meta, None)
    assert ctx.det["type"] == "agent-skills" and ctx.det["variant"] == "A"
    assert "needs-input:file-tree" in ctx.logs


def test_type_override(brand):
    ctx = RepoContext(brand, normalize({"owner": "CompleteTech-LLC", "repo": "x", "visibility": "public"}), None,
                      type_override="cli")
    assert ctx.det["type"] == "cli" and "type-override:cli" in ctx.logs


@pytest.mark.parametrize("owner", ["Jev-Engineering", "jevplay-games", "LibreEvolve", "TouchedByAnAgent", "AI-Ascension"])
def test_t2_card_never_carries_the_completetech_logo(brand, fonts, owner):
    from ctshowcase import card
    meta = normalize({"owner": owner, "repo": "demo-tool", "description": "Run the demo tool for the family.",
                      "visibility": "public", "language": "Python", "license": "MIT"})
    ctx = RepoContext(brand, meta, None)
    _, _, info = card.render(ctx, fonts)
    assert info["icon"]["source"] == "family-wordmark" and info["icon"]["path"] is None


def test_t1_banner_falls_back_to_the_logo(brand, fonts):
    from ctshowcase import banner
    meta = normalize({"owner": "CompleteTech-LLC", "repo": "demo-tool", "description": "Run the demo tool.",
                      "visibility": "public"})
    _, info = banner.layout(RepoContext(brand, meta, None), fonts, allow_few_chips=True)
    assert info["icon"]["source"] == "brand-logo"  # CompleteTech-LLC keeps the full logo on the white card
    meta["owner"] = "CompleteTech-Infrastructure"
    _, info = banner.layout(RepoContext(brand, meta, None), fonts, allow_few_chips=True)
    assert info["icon"]["source"] == "org-mark"  # every other T1 org shows its Neon Night mark (P1.4)


def test_wordmark_banner_renders(brand, fonts):
    from ctshowcase import banner
    meta = normalize({"owner": "TouchedByAnAgent", "repo": "oura-full-read", "visibility": "public",
                      "description": "Read heart rate from Oura rings and standard BLE monitors."})
    data, info = banner.render(RepoContext(brand, meta, None), fonts, allow_few_chips=True)
    assert info["icon"]["source"] == "family-wordmark" and info["icon_fit"] is None and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_fork_outside_the_watching_org_gets_a_banner_but_no_card(tmp_path):
    # K01 (decisions 12, 13, 18; STANDARD R13/R14): only watching-org forks skip the banner; forks have no card (§5.4)
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"owner": "CompleteTech-Infrastructure", "repo": "cockpit-podman", "fork": True,
                             "visibility": "public", "description": "Cockpit UI for podman containers.",
                             "language": "JavaScript", "license": "LGPL-2.1"}))
    p = run_cli("--format", "json", "--meta", m, "--no-repo-dir", "banner", "--out", tmp_path / "b.png",
                "--chip", "JavaScript", "--chip", "LGPL-2.1")
    assert p.returncode == 0 and json.loads(p.stdout)["result"] in ("ok", "incomplete"), p.stdout + p.stderr
    assert (tmp_path / "b.png").exists()
    p = run_cli("--format", "json", "--meta", m, "--no-repo-dir", "card", "--out", tmp_path / "c.svg")
    assert p.returncode == 0 and json.loads(p.stdout)["logs"] == ["exempt:no-card"] and not (tmp_path / "c.svg").exists()


def test_lint_refuses_t3(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"owner": "Pick-Your-AI", "repo": "site", "visibility": "public", "description": "x."}))
    (tmp_path / "README.md").write_text("# x\n")
    p = run_cli("--meta", m, "--repo-dir", tmp_path, "lint", "readme")
    assert p.returncode == 2 and "t3-signoff" in p.stdout


def test_lint_all_fails_a_missing_banner(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"owner": "CompleteTech-LLC", "repo": "demo", "visibility": "public", "description": "Run it."}))
    p = run_cli("--meta", m, "--repo-dir", tmp_path, "lint", "all")
    lines = [json.loads(x) for x in p.stdout.splitlines()]
    assert p.returncode == 1 and {Path(x["file"]).name for x in lines if x["result"] == "FAIL"} == {"banner.png", "card.svg"}


def test_preserved_readme_lints_like_it_was_upgraded(brand, tmp_path):
    raw = json.loads((FIX / "jevplay-games__jev-minesweeper.json").read_text())
    ctx = RepoContext(brand, normalize(raw), None)
    before = "<p align=\"center\"><img src=\"assets/banner.png\" alt=\"SafeSweep banner\" width=\"100%\"></p>\n\n# SafeSweep\n\n## How it works\n\nRace.\n"
    after, _ = readme.upgrade(ctx, before)
    assert "preserve-banner:kept-below-hero" in ctx.logs  # q57 pres default: the hero goes above the own banner
    assert after.index("docs/images/banner.png") < after.index("assets/banner.png")
    (tmp_path / "docs" / "images").mkdir(parents=True)
    (tmp_path / "docs" / "images" / "banner.png").write_bytes(b"x")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "banner.png").write_bytes(b"x")
    (tmp_path / "README.md").write_text(after)
    r = readmelint.lint(ctx, tmp_path / "README.md")
    assert not [f for f in r["fails"] if f.startswith(("D13", "R2", "R7 unexpected", "R7 2-4"))], r["fails"]


def test_empty_description_never_writes_an_empty_tagline(brand):
    ctx = RepoContext(brand, normalize({"owner": "CompleteTech-LLC", "repo": "demo", "visibility": "public"}), None)
    out = readme.scaffold(ctx, "")
    assert "****" not in out and "needs-input:description" in ctx.logs
    ctx.meta["description"] = "Run the demo."
    assert "**Run the demo.**" in readme.header_only(ctx, out)


def test_touchedbyanagent_scaffold_ends_with_the_footer(brand):
    ctx = RepoContext(brand, normalize({"owner": "TouchedByAnAgent", "repo": "demo", "visibility": "public",
                                        "description": "Read the ring."}), None)
    assert footer.check(brand, readme.scaffold(ctx, ""))[0] == "pass"


def test_unknown_visibility_is_not_written_as_internal(brand):
    ctx = RepoContext(brand, normalize({"owner": "CompleteTech-LLC", "repo": "demo", "description": "Run it."}), None)
    assert ctx.public and "needs-input:visibility" in ctx.logs
    assert "Internal" not in readme.scaffold(ctx, "")
