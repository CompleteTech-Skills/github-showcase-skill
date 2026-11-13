"""Variant J must derive badges and retain authored badges through refreshes."""
import json
import os
import re
import subprocess
import sys

import pytest

from ctshowcase import readme, readmelint
from conftest import ROOT


def profile_context(make_ctx, tmp_path, **kwargs):
    (tmp_path / "docs/images").mkdir(parents=True)
    (tmp_path / "docs/images/banner.png").write_bytes(b"banner")
    return make_ctx(repo_dir=tmp_path, repo=".github", language=None,
                    description="Community health files for Northwind Trading Co.", **kwargs)


def badge_block(text):
    return next(m.group(2) for m in readme.MARK.finditer(text) if m.group(1) == "badges")


def test_variant_j_generates_type_and_license_badges(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    assert ctx.det["variant"] == "J"
    text = readme.scaffold(ctx)
    badges = badge_block(text)
    assert "type-GitHub%20profile-" + ctx.brand.raw["badges"]["brand"] in badges
    assert "license-MIT-" + ctx.brand.raw["badges"]["neutral"] in badges
    assert badges.count("img.shields.io/badge/") == 2
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    assert not any("badge" in failure for failure in readmelint.lint(ctx, path)["fails"])


@pytest.mark.parametrize("mode", ["upgrade", "header"])
def test_variant_j_keeps_authored_badges_on_refresh(make_ctx, tmp_path, mode):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.scaffold(ctx)
    colors = ctx.brand.raw["badges"]
    authored = (f'<img src="https://img.shields.io/badge/type-community-{colors["brand"]}" alt="Community">\n'
                f'<img src="https://img.shields.io/badge/license-MIT-{colors["neutral"]}" alt="MIT">')
    text = re.sub(re.escape(readme.wrap("badges", badge_block(text))),
                  lambda _: readme.wrap("badges", authored), text)
    if mode == "upgrade":
        after, removed = readme.upgrade(ctx, text)
        assert readme.preservation(text, after, removed) == []
        again, _ = readme.upgrade(ctx, after)
    else:
        after = readme.header_only(ctx, text)
        assert readme.preservation(text, after, []) == []
        again = readme.header_only(ctx, after)
    assert badge_block(after) == authored
    assert again == after


def test_variant_j_without_license_does_not_invent_one(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path, license=None)
    text = readme.scaffold(ctx)
    badges = badge_block(text)
    assert badges.count("img.shields.io/badge/") == 1
    assert "license-" not in badges
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    result = readmelint.lint(ctx, path)
    assert not any("badge" in failure for failure in result["fails"])
    assert any("badges-short" in warning for warning in result["warns"])


def test_variant_j_preserved_badges_still_obey_lint(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.scaffold(ctx)
    bad = '<img src="https://img.shields.io/badge/type-custom-ABCDEF" alt="Custom">'
    text = text.replace(badge_block(text), bad)
    after, _ = readme.upgrade(ctx, text)
    assert badge_block(after) == bad
    path = tmp_path / "README.md"
    path.write_text(after, encoding="utf-8")
    result = readmelint.lint(ctx, path)
    assert "R7 off-palette badge colour ABCDEF" in result["fails"]
    assert "R7 2-4 header badges required (found 1)" in result["fails"]


@pytest.mark.parametrize("mode", ["upgrade", "header"])
@pytest.mark.parametrize("transition", ["add-license", "change-license", "public", "owner", "local"])
def test_generated_variant_j_badges_refresh(make_ctx, tmp_path, mode, transition):
    values = {"license": None} if transition == "add-license" else {}
    if transition == "public":
        values.update(visibility="private", created_at="2025-01-01T00:00:00Z")
    if transition == "owner":
        (tmp_path / ".github/workflows").mkdir(parents=True)
        (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    before_ctx = profile_context(make_ctx, tmp_path, **values)
    before = readme.scaffold(before_ctx)
    if transition in ("public", "owner"):
        # Isolate badge ownership from the separate nav/license refresh rules.
        before = readme.wrap("badges", badge_block(before)) + "\n\nAuthored paragraph to retain.\n"
    changes = {
        "add-license": {"license": "MIT"},
        "change-license": {"license": "Apache-2.0"},
        "public": {"visibility": "public"},
        "owner": {"owner": "CompleteTech-Skills"},
        "local": {},
    }[transition]
    after_ctx = make_ctx(repo_dir=tmp_path, **(before_ctx.meta | changes))
    if transition == "local":
        after_ctx.local_badges = True
    if mode == "upgrade":
        after, removed = readme.upgrade(after_ctx, before)
    else:
        after, removed = readme.header_only(after_ctx, before), []
    assert readme.preservation(before, after, removed) == []
    if transition in ("public", "owner"):
        assert "Authored paragraph to retain." in after
    body = badge_block(after)
    if transition in ("add-license", "public"):
        assert "license-MIT-" in body
        assert "proprietary" not in body
    elif transition == "change-license":
        assert "license-Apache--2.0-" in body
        assert "license-MIT-" not in body
    elif transition == "owner":
        assert "https://github.com/CompleteTech-Skills/.github/actions/workflows/ci.yml" in body
        assert "https://github.com/Northwind-Trading-Co/.github/actions/workflows/ci.yml" not in body
    else:
        assert "docs/images/badges/" in body
        assert "img.shields.io" not in body
        assert after_ctx.badge_files


def test_editing_a_generated_badge_makes_the_block_authored(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    before = readme.scaffold(ctx)
    edited = before.replace("type-GitHub%20profile-", "type-community-")
    after_ctx = make_ctx(repo_dir=tmp_path, **(ctx.meta | {"license": "Apache-2.0"}))
    after, removed = readme.upgrade(after_ctx, edited)
    assert badge_block(after) == badge_block(edited)
    assert readme.preservation(edited, after, removed) == []


def test_generated_badges_do_not_exempt_authored_content_from_shrink_guard(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    before = readme.scaffold(ctx) + "\nNever discard this authored sentence.\n"
    after = before.replace("Never discard this authored sentence.", "")
    assert any("Never discard" in p for p in readme.preservation(before, after, []))


@pytest.mark.parametrize("mode", ["upgrade", "header"])
def test_legacy_generated_profile_badges_gain_the_type_badge(make_ctx, tmp_path, mode):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.scaffold(ctx)
    legacy = f'![License MIT](https://img.shields.io/badge/license-MIT-{ctx.brand.raw["badges"]["neutral"]})'
    text = text.replace(badge_block(text), legacy)
    if mode == "upgrade":
        after, removed = readme.upgrade(ctx, text)
    else:
        after, removed = readme.header_only(ctx, text), []
    assert "type-GitHub%20profile-" in badge_block(after)
    assert legacy in badge_block(after)
    assert readme.preservation(text, after, removed) == []


def test_large_profile_without_tagline_keeps_authored_badges(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.scaffold(ctx)
    authored = ('<img src="https://img.shields.io/badge/type-community-005ADD" alt="Community">\n'
                '<img src="https://img.shields.io/badge/license-MIT-64748B" alt="MIT">')
    text = text.replace(badge_block(text), authored)
    text = readme._sub_blocks(text, lambda m: "" if m.group(1) == "tagline" else m.group(0))
    text = text.replace("\n---\n", "\n---\n\n" + "Community resources. " * 1000 + "\n")
    assert len(text.encode()) > 15000
    after, removed = readme.upgrade(ctx, text)
    assert badge_block(after) == authored
    assert readme.preservation(text, after, removed) == []


def test_bootstrap_keeps_authored_badges_outside_pristine_body(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.header(ctx, title=readme.TEMPLATE_H1) + "\n\n" + readme.pristine_block("## About\n\nTemplate.")
    authored = ('<img src="https://img.shields.io/badge/type-community-005ADD" alt="Community">\n'
                '<img src="https://img.shields.io/badge/license-MIT-64748B" alt="MIT">')
    text = text.replace(badge_block(text), authored)
    assert readme.bootstrap_state(text) == "pristine"
    after = readme.bootstrap(ctx, text)
    assert badge_block(after) == authored


def profile_cli(ctx, tmp_path, *args, expected_code=0):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(ctx.meta), encoding="utf-8")
    # Isolate these regressions from the separately tracked Windows stdout-encoding defect.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "--meta", str(meta),
                             "--repo-dir", str(tmp_path), *args], capture_output=True, encoding="utf-8", env=env)
    assert result.returncode == expected_code, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_real_template_bootstrap_replaces_inherited_badge(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    text = (ROOT / "tests/fixtures/template-README.md").read_text(encoding="utf-8")
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    profile_cli(ctx, tmp_path, "readme", "--bootstrap", "--write")
    actual = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "type-Template-" not in badge_block(actual)
    assert "type-GitHub%20profile-" in badge_block(actual)
    assert "license-MIT-" in badge_block(actual)
    assert not any("badge" in f for f in profile_cli(ctx, tmp_path, "lint", "readme")["fails"])


# GFM evidence (GitHub Markdown API, mode gfm):
# - gfm-d11-mixed_blank_boundary.html: a blank line between the HTML <img> and the Markdown CI badge
#   renders TWO <img> elements, so a valid mixed fixture must keep that boundary.
# - gfm-d11-mixed_adjacent.html: with no blank line, the HTML block absorbs the Markdown CI badge, which
#   stays literal text and renders exactly ONE <img>.
# The scaffold only emits Markdown badges for variant J (badges_md) with --badges local, so neither
# HTML fixture below is generated output; the adjacent mix cannot be produced by the generator.
@pytest.mark.parametrize("mode", ["markdown", "html_both", "html_blank_boundary"])
def test_local_profile_badge_plus_ci_passes_lint(make_ctx, tmp_path, mode):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    ctx = profile_context(make_ctx, tmp_path, license=None)
    profile_cli(ctx, tmp_path, "readme", "--mode", "scaffold", "--badges", "local", "--write")
    path = tmp_path / "README.md"
    text = path.read_text(encoding="utf-8")
    assert "docs/images/badges/type-github-profile.svg" in text
    if mode == "html_both":
        text = re.sub(r"!\[([^\]]+)\]\((docs/images/badges/[^)]+)\)",
                      r'<img src="\2" alt="\1">', text)
        text = re.sub(r"\[!\[([^\]]+)\]\(([^)]+)\)\]\(([^)]+)\)",
                      r'<a href="\3"><img src="\2" alt="\1"></a>', text)
        path.write_text(text, encoding="utf-8")
    elif mode == "html_blank_boundary":
        text = re.sub(r"!\[([^\]]+)\]\((docs/images/badges/[^)]+)\)",
                      r'<img src="\2" alt="\1">', text)
        text = text.replace(">\n[![CI]", ">\n\n[![CI]")
        assert ">\n\n[![CI]" in text
        path.write_text(text, encoding="utf-8")
    assert not any("badge" in f for f in profile_cli(ctx, tmp_path, "lint", "readme")["fails"])


def test_local_profile_adjacent_html_markdown_badge_mix_counts_one(make_ctx, tmp_path):
    # Negative control for the GFM evidence in test_local_profile_badge_plus_ci_passes_lint:
    # no blank line after the HTML <img>, so the Markdown CI badge is absorbed as literal text.
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    ctx = profile_context(make_ctx, tmp_path, license=None)
    profile_cli(ctx, tmp_path, "readme", "--mode", "scaffold", "--badges", "local", "--write")
    path = tmp_path / "README.md"
    text = path.read_text(encoding="utf-8")
    assert "docs/images/badges/type-github-profile.svg" in text
    text = re.sub(r"!\[([^\]]+)\]\((docs/images/badges/[^)]+)\)",
                  r'<img src="\2" alt="\1">', text)
    assert ">\n[![CI]" in text
    path.write_text(text, encoding="utf-8")
    result = profile_cli(ctx, tmp_path, "lint", "readme", expected_code=1)
    assert "R7 2-4 header badges required (found 1)" in result["fails"]


@pytest.mark.parametrize("mention", ["docs/images/badges/type-github-profile.svg",
                                    "```markdown\n![Example](docs/images/badges/type-github-profile.svg)\n```"])
def test_local_badge_prose_and_code_examples_do_not_count(make_ctx, tmp_path, mention):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    ctx = profile_context(make_ctx, tmp_path, license=None)
    text = readme.scaffold(ctx)
    body = "\n".join(line for line in badge_block(text).splitlines() if "actions/workflows" in line)
    text = text.replace(badge_block(text), body + "\n" + mention)
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    assert "R7 2-4 header badges required (found 1)" in readmelint.lint(ctx, path)["fails"]


@pytest.mark.parametrize("mode", ["upgrade", "header"])
@pytest.mark.parametrize("scenario", ["local", "local-to-remote", "license", "local-license", "owner", "language"])
def test_legacy_badges_migrate_independently_of_current_metadata(make_ctx, tmp_path, mode, scenario):
    ctx = profile_context(make_ctx, tmp_path, license="Apache-2.0" if "license" in scenario else "MIT")
    if scenario in ("local", "local-to-remote"):
        legacy = "![License MIT](docs/images/badges/license-mit.svg)"
    elif scenario == "local-license":
        legacy = "![License MIT](docs/images/badges/license-mit.svg)"
    elif scenario == "owner":
        (tmp_path / ".github/workflows").mkdir(parents=True)
        (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
        legacy = ("![License MIT](https://img.shields.io/badge/license-MIT-64748B)\n"
                  "[![CI](https://github.com/Old-Northwind/.github/actions/workflows/ci.yml/badge.svg)]"
                  "(https://github.com/Old-Northwind/.github/actions/workflows/ci.yml)")
    elif scenario == "language":
        legacy = ("![Language JavaScript](https://img.shields.io/badge/language-JavaScript-1E3A8A)\n"
                  "![License MIT](https://img.shields.io/badge/license-MIT-64748B)")
    else:
        legacy = "![License MIT](https://img.shields.io/badge/license-MIT-64748B)"
    ctx.local_badges = scenario.startswith("local") and scenario != "local-to-remote"
    before = readme.wrap("badges", legacy) + "\n\nAuthored paragraph to retain.\n"
    if mode == "upgrade":
        after, removed = readme.upgrade(ctx, before)
    else:
        after, removed = readme.header_only(ctx, before), []
    body = badge_block(after)
    assert "type-github-profile.svg" in body if ctx.local_badges else "type-GitHub%20profile-" in body
    if "license" in scenario:
        assert "apache" in body.lower()
        assert "license-MIT-" not in body and "license-mit.svg" not in body
    assert "Old-Northwind" not in body and "JavaScript" not in body
    assert "Authored paragraph to retain." in after
    assert readme.preservation(before, after, removed) == []
    again = readme.upgrade(ctx, after)[0] if mode == "upgrade" else readme.header_only(ctx, after)
    assert again == after


def test_legacy_like_authored_custom_badge_block_stays_owned_by_author(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    authored = ("![Type Community](https://img.shields.io/badge/type-Community-005ADD)\n"
                "![License MIT](https://img.shields.io/badge/license-MIT-64748B)")
    before = readme.wrap("badges", authored)
    after, removed = readme.upgrade(ctx, before)
    assert badge_block(after) == authored
    assert readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("mode", ["upgrade", "header"])
def test_cli_legacy_remote_license_migrates_to_local_without_shrink(make_ctx, tmp_path, mode):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.scaffold(ctx)
    legacy = "![License MIT](https://img.shields.io/badge/license-MIT-64748B)"
    (tmp_path / "README.md").write_text(text.replace(badge_block(text), legacy), encoding="utf-8")
    result = profile_cli(ctx, tmp_path, "readme", "--mode", mode, "--badges", "local", "--write")
    assert "readme-shrink" not in result.get("logs", [])
    actual = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "docs/images/badges/type-github-profile.svg" in actual
    assert "docs/images/badges/license-mit.svg" in actual
    assert not any("badge" in f for f in profile_cli(ctx, tmp_path, "lint", "readme")["fails"])


@pytest.mark.parametrize("license", [None, "NOASSERTION", "other"])
@pytest.mark.parametrize("mode", ["upgrade", "header"])
def test_unknown_license_keeps_authored_legacy_shaped_badge(make_ctx, tmp_path, license, mode):
    ctx = profile_context(make_ctx, tmp_path, license=license)
    authored = "![License MIT](https://img.shields.io/badge/license-MIT-64748B)"
    text = readme.scaffold(ctx)
    text = text.replace(badge_block(text), authored)
    if mode == "upgrade":
        after, removed = readme.upgrade(ctx, text)
    else:
        after, removed = readme.header_only(ctx, text), []
    assert badge_block(after) == authored
    assert readme.preservation(text, after, removed) == []


@pytest.mark.parametrize("license", [None, "NOASSERTION", "other"])
def test_cli_unknown_license_does_not_erase_authored_badge(make_ctx, tmp_path, license):
    ctx = profile_context(make_ctx, tmp_path, license=license)
    authored = "![License MIT](https://img.shields.io/badge/license-MIT-64748B)"
    text = readme.scaffold(ctx)
    (tmp_path / "README.md").write_text(text.replace(badge_block(text), authored), encoding="utf-8")
    profile_cli(ctx, tmp_path, "readme", "--write")
    assert badge_block((tmp_path / "README.md").read_text(encoding="utf-8")) == authored


@pytest.mark.parametrize("state", ["pristine", "edited", "unmarked"])
@pytest.mark.parametrize("mode", ["bootstrap", "upgrade", "header"])
@pytest.mark.parametrize("custom", [False, True])
def test_template_badges_across_body_states_and_cli_modes(make_ctx, tmp_path, state, mode, custom):
    ctx = profile_context(make_ctx, tmp_path)
    text = (ROOT / "tests/fixtures/template-README.md").read_text(encoding="utf-8")
    authored = ('<img src="https://img.shields.io/badge/type-community-005ADD" alt="Community">\n'
                '<img src="https://img.shields.io/badge/license-MIT-64748B" alt="MIT">')
    if custom:
        text = text.replace(badge_block(text), authored)
    if state != "pristine":
        text = text.replace("<!-- showcase:template-body:end -->",
                            "A user-written body note.\n<!-- showcase:template-body:end -->")
    if state == "unmarked":
        text = readme.drop_pristine(text).replace("<!-- showcase:template-body:start -->", "")
        text = text.replace("<!-- showcase:template-body:end -->", "")
    if mode == "upgrade":
        # The base also rejects unrelated template identity changes through its shrink guard.
        # Align those generated fields to isolate the badge migration in a real CLI upgrade.
        identity = {"banner": readme.banner_html(ctx), "nav": readme.nav_line(ctx),
                    "tagline": readme.tagline_body(ctx)}
        text = readme._sub_blocks(text, lambda m: readme.wrap(m.group(1), identity[m.group(1)])
                                  if m.group(1) in identity else m.group(0))
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    options = ["--bootstrap"] if mode == "bootstrap" else ["--mode", mode]
    profile_cli(ctx, tmp_path, "readme", *options, "--write")
    actual = path.read_text(encoding="utf-8")
    if custom:
        assert badge_block(actual) == authored
    else:
        assert "type-Template-" not in badge_block(actual)
        assert "type-GitHub%20profile-" in badge_block(actual)
        assert "license-MIT-" in badge_block(actual)
        assert not any("badge" in f for f in readmelint.lint(ctx, path)["fails"])
    if state != "pristine":
        assert "A user-written body note." in actual


@pytest.mark.parametrize("exists", [False, True])
def test_cli_angle_image_destinations_check_file_existence(make_ctx, tmp_path, exists):
    ctx = profile_context(make_ctx, tmp_path)
    if exists:
        (tmp_path / "docs/images/screenshot.png").write_bytes(b"image")
    text = readme.scaffold(ctx).replace("\n---\n", "\n---\n\n![Screenshot](<docs/images/screenshot.png>)\n")
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    result = profile_cli(ctx, tmp_path, "lint", "readme", expected_code=0 if exists else 1)
    assert any("local image does not resolve" in failure for failure in result["fails"]) is not exists


def test_cli_html_alt_backticks_remain_literal(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.scaffold(ctx)
    body = ('<img src="https://img.shields.io/badge/type-GitHub%20profile-005ADD" alt="`showcase.py --help`">\n'
            '<img src="https://img.shields.io/badge/license-MIT-64748B" alt="License">')
    (tmp_path / "README.md").write_text(text.replace(badge_block(text), body), encoding="utf-8")
    result = profile_cli(ctx, tmp_path, "lint", "readme")
    assert not any("without alt" in failure for failure in result["fails"])


@pytest.mark.parametrize("repo, migrates", [("Old-Northwind", True), (".github", True), ("Elsewhere", False)])
def test_legacy_ci_badge_recognizes_personal_profile_repository(make_ctx, tmp_path, repo, migrates):
    ctx = profile_context(make_ctx, tmp_path)
    url = f"https://github.com/Old-Northwind/{repo}/actions/workflows/ci.yml"
    authored = f"![License MIT](https://img.shields.io/badge/license-MIT-64748B)\n[![CI]({url}/badge.svg)]({url})"
    before = readme.wrap("badges", authored) + "\n\nAuthored paragraph to retain.\n"
    after, removed = readme.upgrade(ctx, before)
    assert (authored not in badge_block(after)) is migrates
    assert "Authored paragraph to retain." in after
    assert readme.preservation(before, after, removed) == []


def test_cli_markdown_alt_backticks_remain_literal(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.scaffold(ctx)
    body = ("![`showcase.py --help`](https://img.shields.io/badge/type-GitHub%20profile-005ADD)\n"
            "![License](https://img.shields.io/badge/license-MIT-64748B)")
    (tmp_path / "README.md").write_text(text.replace(badge_block(text), body), encoding="utf-8")
    result = profile_cli(ctx, tmp_path, "lint", "readme")
    assert not any("without alt" in failure for failure in result["fails"])


def test_cli_angle_bracketed_shield_destinations_use_palette_tokens(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    text = readme.scaffold(ctx)
    body = ("![Type](<https://img.shields.io/badge/type-GitHub%20profile-005ADD>)\n"
            "![License](<https://img.shields.io/badge/license-MIT-64748B>)")
    (tmp_path / "README.md").write_text(text.replace(badge_block(text), body), encoding="utf-8")
    result = profile_cli(ctx, tmp_path, "lint", "readme")
    assert not any("palette" in failure.lower() or "badge" in failure.lower() for failure in result["fails"])
    bad = body.replace("64748B>", "FF0000>")
    (tmp_path / "README.md").write_text(text.replace(badge_block(text), bad), encoding="utf-8")
    result = profile_cli(ctx, tmp_path, "lint", "readme", expected_code=1)
    assert any("palette" in failure.lower() for failure in result["fails"])


def test_legacy_ci_badge_profile_repository_matches_owner_case_insensitively(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    url = "https://github.com/Old-Northwind/old-northwind/actions/workflows/ci.yml"
    authored = f"![License MIT](https://img.shields.io/badge/license-MIT-64748B)\n[![CI]({url}/badge.svg)]({url})"
    before = readme.wrap("badges", authored) + "\n\nAuthored paragraph to retain.\n"
    after, removed = readme.upgrade(ctx, before)
    assert authored not in badge_block(after)
    assert readme.preservation(before, after, removed) == []


def test_legacy_language_badge_with_family_palette_migrates(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    ctx.style = dict(ctx.style, badge_accent="115E59")
    authored = ("![Language Python](https://img.shields.io/badge/language-Python-115E59)\n"
                "![License MIT](https://img.shields.io/badge/license-MIT-64748B)")
    assert readme.legacy_profile_badges(ctx.brand, authored, ctx.style)
    assert not readme.legacy_profile_badges(ctx.brand, authored)
    body = readme.badge_body(ctx, authored)
    assert body != authored and "type-GitHub%20profile-" in body


def test_local_inherited_template_badge_migrates_like_remote(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    remote, local = readme.template_badge_bodies(ctx.brand)
    assert local == "![Type Template](docs/images/badges/type-template.svg)"
    for existing in (remote, local):
        body = readme.badge_body(ctx, existing)
        assert body != existing and readme.generated_badges(body)
        assert "type-GitHub%20profile-" in body and "license-MIT-" in body


# --- The generated-badge digest preserves Markdown-significant whitespace ---------------------------------------
def _indented_first_row(text):
    body = badge_block(text)
    comment, rows = body.strip("\n").split("\n", 1)
    indented = f"{comment}\n    {rows}"
    return text.replace(body, indented), indented


def test_indenting_a_generated_badge_row_makes_the_block_authored(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    before = readme.scaffold(ctx)
    assert readme.generated_badges(badge_block(before))
    edited, indented = _indented_first_row(before)
    assert badge_block(edited) == indented
    assert not readme.generated_badges(badge_block(edited))
    after_ctx = make_ctx(repo_dir=tmp_path, **(ctx.meta | {"license": "Apache-2.0"}))
    header = readme.header_only(after_ctx, edited)
    assert badge_block(header) == indented
    upgraded, removed = readme.upgrade(after_ctx, edited)
    assert badge_block(upgraded) == indented
    assert readme.preservation(edited, upgraded, removed) == []


def test_crlf_converted_untouched_block_still_counts_as_generated(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    block = badge_block(readme.scaffold(ctx))
    assert readme.generated_badges(block.replace("\n", "\r\n"))


def _tab_indented_first_row(text):
    body = badge_block(text)
    comment, rows = body.strip("\n").split("\n", 1)
    indented = f"{comment}\n\t{rows}"
    return text.replace(body, indented), indented


def test_tab_indenting_a_generated_badge_row_makes_the_block_authored(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    before = readme.scaffold(ctx)
    assert readme.generated_badges(badge_block(before))
    edited, indented = _tab_indented_first_row(before)
    assert badge_block(edited) == indented
    assert not readme.generated_badges(badge_block(edited))
    after_ctx = make_ctx(repo_dir=tmp_path, **(ctx.meta | {"license": "Apache-2.0"}))
    header = readme.header_only(after_ctx, edited)
    assert badge_block(header) == indented
    upgraded, removed = readme.upgrade(after_ctx, edited)
    assert badge_block(upgraded) == indented
    assert readme.preservation(edited, upgraded, removed) == []


def test_untouched_generated_badge_row_refreshes_on_license_change(make_ctx, tmp_path):
    ctx = profile_context(make_ctx, tmp_path)
    before = readme.scaffold(ctx)
    assert readme.generated_badges(badge_block(before))
    after_ctx = make_ctx(repo_dir=tmp_path, **(ctx.meta | {"license": "Apache-2.0"}))
    header = readme.header_only(after_ctx, before)
    assert badge_block(header) != badge_block(before)
    assert readme.generated_badges(badge_block(header))
    assert "license-MIT-" not in badge_block(header)
    assert "Apache" in badge_block(header)


@pytest.mark.parametrize("variant", ["no-lead", "extra-lead", "extra-trail", "no-trail"])
def test_marker_separator_newline_variations_still_validate(make_ctx, tmp_path, variant):
    ctx = profile_context(make_ctx, tmp_path)
    block = badge_block(readme.scaffold(ctx))
    comment, body = block.strip("\n").split("\n", 1)
    shaped = {"no-lead": f"{comment}\n{body}", "extra-lead": f"{comment}\n\n{body}",
              "extra-trail": f"{comment}\n{body}\n\n", "no-trail": f"{comment}\n{body}"}[variant]
    assert readme.generated_badges(shaped)


def test_badge_digest_is_not_the_template_body_digest(make_ctx, tmp_path):
    body = badge_block(readme.scaffold(profile_context(make_ctx, tmp_path))).split("\n", 1)[1]
    assert readme.badge_sha(body) != readme.badge_sha("    " + body)
    assert readme.badge_sha(body) != readme.badge_sha("\t" + body)
    assert readme.badge_sha(body) == readme.badge_sha(body.replace("\n", "\r\n"))


# --- Round 6: only line endings and separator newlines are normalized when recognizing the inherited template -----
def _template_text(ctx, row):
    text = readme.scaffold(ctx)
    return text.replace(badge_block(text), row)


def _refresh(ctx, text, mode):
    if mode == "header":
        return readme.header_only(ctx, text), []
    return readme.upgrade(ctx, text)


@pytest.mark.parametrize("which", [0, 1], ids=["remote", "local-svg"])
@pytest.mark.parametrize("edit", ["indent4", "tab", "trailing-space", "indent1"])
@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_edited_template_row_without_digest_survives_refresh_byte_for_byte(make_ctx, tmp_path, mode, edit, which):
    ctx = profile_context(make_ctx, tmp_path)
    template = readme.template_badge_bodies(ctx.brand)[which]
    row = {"indent4": "    " + template, "tab": "\t" + template, "trailing-space": template + "  ",
           "indent1": " " + template}[edit]
    text = _template_text(ctx, row)
    assert badge_block(text) == row
    after, removed = _refresh(ctx, text, mode)
    assert badge_block(after) == row
    assert "replaces=" not in after
    assert readme.preservation(text, after, removed) == []
    again, _ = _refresh(ctx, after, mode)
    assert badge_block(again) == row


@pytest.mark.parametrize("which", [0, 1], ids=["remote", "local-svg"])
@pytest.mark.parametrize("shape", ["exact", "crlf", "padded", "crlf-padded"])
@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_exact_template_row_is_still_recognized_and_refreshed(make_ctx, tmp_path, mode, shape, which):
    ctx = profile_context(make_ctx, tmp_path)
    template = readme.template_badge_bodies(ctx.brand)[which]
    row = {"exact": template, "crlf": template + "\r\n", "padded": "\n\n" + template + "\n\n",
           "crlf-padded": "\r\n" + template + "\r\n"}[shape]
    text = _template_text(ctx, row)
    body = readme.badge_body(ctx, row)
    assert body != row and readme.generated_badges(body)
    after, _ = _refresh(ctx, text, mode)
    assert "type-Template" not in badge_block(after) and "type-template" not in badge_block(after)
    assert readme.generated_badges(badge_block(after))


INDENTED_MIT = "    ![License MIT](https://img.shields.io/badge/license-MIT-64748B)"
PLAIN_MIT = INDENTED_MIT.strip()


def two_block_changed_license(make_ctx, tmp_path):
    """Variant J with current license Apache-2.0: an authored indented MIT row, then the same row unindented."""
    ctx = profile_context(make_ctx, tmp_path, license="Apache-2.0")
    text = readme.scaffold(ctx)
    marked = readme.wrap("badges", INDENTED_MIT) + "\n\n" + readme.wrap("badges", PLAIN_MIT)
    return ctx, text.replace(readme.wrap("badges", badge_block(text)), marked)


def test_indented_authored_badge_block_is_not_silently_removed(make_ctx, tmp_path):
    ctx, before = two_block_changed_license(make_ctx, tmp_path)
    after, removed = readme.upgrade(ctx, before)
    problems = readme.preservation(before, after, removed)
    # The authored indented MIT row is kept, or the shrink guard rejects its removal; never a silent drop.
    assert INDENTED_MIT in after or any("License MIT" in problem for problem in problems), (problems, after)
    # The unindented duplicate is a legacy generated row and migrates to the current license.
    assert "license-Apache--2.0-64748B" in after
    assert not re.search(r"^" + re.escape(PLAIN_MIT) + r"$", after, re.M)
    assert after.count("<!-- showcase:badges:generated") == 1


def test_cli_write_never_silently_removes_the_indented_authored_badge(make_ctx, tmp_path):
    ctx, before = two_block_changed_license(make_ctx, tmp_path)
    path = tmp_path / "README.md"
    path.write_text(before, encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(ctx.meta), encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "--meta", str(meta),
                             "--repo-dir", str(tmp_path), "readme", "--mode", "upgrade", "--write"],
                            capture_output=True, encoding="utf-8", env=env)
    written = path.read_text(encoding="utf-8")
    if result.returncode == 0:
        assert INDENTED_MIT in written, written
    else:
        assert "readme-shrink" in result.stdout + result.stderr
        assert written == before


@pytest.mark.parametrize("mode", ["upgrade", "header"])
def test_single_block_legacy_migration_still_passes_without_shrink_and_is_stable(make_ctx, tmp_path, mode):
    ctx = profile_context(make_ctx, tmp_path, license="Apache-2.0")
    before = readme.wrap("badges", PLAIN_MIT) + "\n\nAuthored paragraph to retain.\n"
    run = (lambda text: readme.upgrade(ctx, text)) if mode == "upgrade" else (lambda text: (readme.header_only(ctx, text), []))
    after, removed = run(before)
    assert "license-Apache--2.0-64748B" in badge_block(after) and "license-MIT-" not in badge_block(after)
    assert readme.preservation(before, after, removed) == []
    again, removed_again = run(after)
    assert again == after and readme.preservation(after, again, removed_again) == []
