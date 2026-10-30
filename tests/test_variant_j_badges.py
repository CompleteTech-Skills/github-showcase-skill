"""Variant J must derive badges and retain authored badges through refreshes."""
import re

import pytest

from ctshowcase import readme, readmelint


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
