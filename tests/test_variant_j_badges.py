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


def profile_cli(ctx, tmp_path, *args):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(ctx.meta), encoding="utf-8")
    # Isolate these regressions from the separately tracked Windows stdout-encoding defect.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "--meta", str(meta),
                             "--repo-dir", str(tmp_path), *args], capture_output=True, encoding="utf-8", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
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


@pytest.mark.parametrize("html", [False, True])
def test_local_profile_badge_plus_ci_passes_lint(make_ctx, tmp_path, html):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    ctx = profile_context(make_ctx, tmp_path, license=None)
    profile_cli(ctx, tmp_path, "readme", "--mode", "scaffold", "--badges", "local", "--write")
    path = tmp_path / "README.md"
    text = path.read_text(encoding="utf-8")
    assert "docs/images/badges/type-github-profile.svg" in text
    if html:
        text = re.sub(r"!\[([^\]]+)\]\((docs/images/badges/[^)]+)\)",
                      r'<img src="\2" alt="\1">', text)
        path.write_text(text, encoding="utf-8")
    assert not any("badge" in f for f in profile_cli(ctx, tmp_path, "lint", "readme")["fails"])


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
