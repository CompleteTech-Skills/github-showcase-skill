"""Unmarked old footers are recognised, and a compliant footer keeps authored lines protected (issue 47).

Synthetic Northwind fixtures only. Helpers come from conftest, the `brand` fixture and `tmp_path`.
"""
import pytest

from conftest import meta_dict
from ctshowcase import footer, readme
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize
from conftest import ROOT

LEGACY = "https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/"
AUTHORED = '<p align="center">\n  <img src="docs/diagram.png" alt="Diagram">\n<br>\n</p>\n'


def unmarked_img_footer(img_tag):
    """A centred footer with the img wrapped in a complete.tech link, followed by the credit line."""
    return (
        '<p align="center">\n'
        f'  <a href="https://www.complete.tech">{img_tag}</a><br>\n'
        '  <sub>Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration</sub>\n'
        "</p>"
    )


def replace_marked_footer(brand, text, unmarked):
    return text.replace(footer.block(brand), unmarked)


def ctx_for(brand, tmp_path):
    return RepoContext(brand, normalize(meta_dict()), tmp_path)


@pytest.mark.parametrize("src", [
    "https://www.complete.tech/wp-content/uploads/logo.png",
    "docs/images/logo.svg",
], ids=["legacy-wp-url", "unlisted-local-svg"])
def test_unmarked_old_footer_with_company_alt_is_replaced(brand, tmp_path, src):
    """An unmarked old footer whose img alt is the company name is replaced by the marked footer."""
    ctx = ctx_for(brand, tmp_path)
    img = f'<img src="{src}" alt="CompleteTech LLC" width="160">'
    before = replace_marked_footer(brand, readme.scaffold(ctx), unmarked_img_footer(img))
    assert "Built by" in before and footer.block(brand) not in before
    after, removed = readme.upgrade(ctx, before)
    assert footer.check(brand, after)[0] == "pass"
    assert after.count("Built by") == 1


def test_unmarked_local_picture_footer_is_replaced(brand, tmp_path):
    """An unmarked picture footer with local dark and light logos and the company alt is replaced."""
    ctx = ctx_for(brand, tmp_path)
    picture = (
        "<picture>\n"
        '    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.png">\n'
        '    <img src="assets/logo.png" alt="CompleteTech LLC" width="200">\n'
        "  </picture>"
    )
    unmarked = (
        '<p align="center">\n'
        f'  <a href="https://www.complete.tech">{picture}</a><br>\n'
        '  <sub>Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration</sub>\n'
        "</p>"
    )
    before = replace_marked_footer(brand, readme.scaffold(ctx), unmarked)
    assert "assets/logo-dark.png" in before and footer.block(brand) not in before
    after, removed = readme.upgrade(ctx, before)
    assert footer.check(brand, after)[0] == "pass"
    assert after.count("Built by") == 1


def test_partner_images_are_not_footer_copies(brand):
    """A partner image in a picture source, or a local logo with a non-company alt, is not a footer copy."""
    partner_source = (
        '<p align="center">\n'
        '  <a href="https://www.complete.tech">\n'
        "    <picture>\n"
        '      <source media="(prefers-color-scheme: dark)" srcset="assets/partner.png">\n'
        '      <img src="assets/logo.png" alt="CompleteTech LLC" width="200">\n'
        "    </picture>\n"
        "  </a><br>\n"
        '  <sub>Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration</sub>\n'
        "</p>"
    )
    wrong_alt = unmarked_img_footer('<img src="assets/logo.png" alt="Partner" width="160">')
    assert not readme.is_footer_copy(partner_source, brand)
    assert not readme.is_footer_copy(wrong_alt, brand)


def test_footer_shaped_svg_src_is_strict_by_default_and_loose_with_flag(brand):
    """An unlisted svg src is rejected by default and accepted only when loose_src is set."""
    block = unmarked_img_footer('<img src="docs/images/logo.svg" alt="CompleteTech LLC" width="160">')
    assert not readme.is_footer_copy(block, brand)
    assert readme.is_footer_copy(block, brand, loose_src=True)


def test_compliant_footer_keeps_authored_lines_protected(brand, tmp_path):
    """Upgrading a compliant README does not report footer lines as removed, so a lost authored <br> is caught."""
    ctx = ctx_for(brand, tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), AUTHORED + footer.block(brand))
    assert AUTHORED in before
    after, removed = readme.upgrade(ctx, before)
    assert not any("Built by" in line for line in removed)
    assert readme.preservation(before, after, removed) == []
    assert AUTHORED in after
    lost = after.replace(AUTHORED, AUTHORED.replace("<br>\n", "", 1), 1)
    assert lost != after
    problems = readme.preservation(before, lost, removed)
    assert problems and any("<br>" in p for p in problems)


def test_template_fixture_footer_migrates_legacy_urls_and_is_preserved(brand, tmp_path):
    """Legacy footer lines are reported as removed and the preservation check accepts the replacement."""
    before = (ROOT / "tests" / "fixtures" / "template-README.md").read_text(encoding="utf-8")
    assert LEGACY + "logo.png" in before
    ctx = ctx_for(brand, tmp_path)
    after, removed = readme.upgrade(ctx, before)
    assert any(LEGACY in line for line in removed)
    assert readme.preservation(before, after, removed) == []
