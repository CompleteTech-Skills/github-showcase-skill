"""Round r6 footer findings: unmarked old footers, <picture> local logos, and the never-drop-a-line guard."""
import pytest

from conftest import meta_dict
from ctshowcase import footer, readme
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

CREDIT = ('<sub>Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration'
          "</sub>")


def unmarked(src, alt="CompleteTech LLC"):
    return ('<p align="center"><a href="https://www.complete.tech"><img src="%s" alt="%s" width="160"></a><br>%s</p>'
            % (src, alt, CREDIT))


def picture(light, dark):
    return ('<p align="center">\n  <a href="https://complete.tech"><picture>\n'
            '    <source media="(prefers-color-scheme: dark)" srcset="%s">\n'
            '    <img src="%s" alt="CompleteTech LLC" width="200">\n  </picture></a><br>\n  %s\n</p>\n'
            % (dark, light, CREDIT))


@pytest.mark.parametrize("src", ["https://www.complete.tech/wp-content/uploads/logo.png", "docs/images/logo.svg"])
def test_unmarked_old_footer_with_company_alt_is_replaced_by_upgrade(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src))
    assert src in before and "showcase:footer" not in before
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1 and footer.check(brand, after)[0] == "pass"
    assert readme.preservation(before, after, removed) == []


def test_strict_default_keeps_a_company_alt_partner_image(brand):
    text = "# A\n\n" + unmarked("docs/images/logo.svg")
    assert readme.drop_old_footer(text, brand) == (text, [])
    assert readme.drop_old_footer(text, brand, loose_src=True)[1]


def test_picture_footer_with_old_local_files_is_replaced(brand, tmp_path):
    block = picture("assets/logo.png", "assets/logo-dark.png")
    assert readme.is_footer_copy(block, brand)
    assert not readme.is_footer_copy(picture("assets/partner.png", "assets/logo-dark.png"), brand)
    assert not readme.is_footer_copy(block.replace('alt="CompleteTech LLC"', 'alt="Partner"'), brand)
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), block)
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1 and footer.check(brand, after)[0] == "pass"
    assert readme.preservation(before, after, removed) == []


AUTHORED = '<p align="center">\n<img src="docs/diagram.png" alt="Diagram">\n<br>\n</p>\n\n'


def test_compliant_footer_adds_no_removed_lines_and_a_lost_br_still_fails(brand, tmp_path):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    scaffold = readme.scaffold(ctx)
    before = scaffold.replace(footer.block(brand), AUTHORED + footer.block(brand))
    after, removed = readme.upgrade(ctx, before)
    footer_lines = {ln.strip() for ln in footer.markup(brand).splitlines() if ln.strip()}
    assert not [ln for ln in removed if ln.strip() in footer_lines]  # header lines may be reported, footer lines not
    lost = after.replace("<br>\n</p>\n\n<!-- showcase:footer", "</p>\n\n<!-- showcase:footer", 1)
    assert lost != after
    assert any("<br>" in p for p in readme.preservation(before, lost, removed))
