"""Round r7 footer findings for issue 47: same-host images that are not historical logos, and the never-drop-a-line
guard for unmarked footers whose re-emitted lines must not be exempted (source findings at 020f30a).

Only existing APIs are used: conftest.meta_dict, the `brand` fixture, ctshowcase.footer, ctshowcase.readme,
RepoContext and normalize. All fixtures are synthetic and written under tmp_path. Expected state at 020f30a: tests that
depend on the readme.py fix fail until that fix lands; no assertion here is weakened to make them pass.
"""
from collections import Counter

import pytest

from conftest import meta_dict
from ctshowcase import footer, readme
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

CREDIT = ('<sub>Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration'
          "</sub>")
OWN_SITE_LINK = '<a href="https://www.complete.tech">'
CLOSE_LINK = "</a>"


def unmarked(src, alt="CompleteTech LLC"):
    return ('<p align="center"><a href="https://www.complete.tech"><img src="%s" alt="%s" width="160"></a><br>%s</p>'
            % (src, alt, CREDIT))


def image_lines(text, src):
    return sum(1 for ln in text.splitlines() if src in ln)


def stripped_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


@pytest.mark.parametrize("src", [
    "https://www.complete.tech/team-photo.png",
    "https://www.complete.tech/wp-content/uploads/team.png",
    "https://www.complete.tech/assets/logo.png",
])
def test_same_host_non_logo_image_is_kept_through_upgrade(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src))
    assert src in before and footer.block(brand) not in before
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if src in ln], f"{src} was reported as removed"
    assert image_lines(after, src) == image_lines(before, src)
    assert image_lines(after, src) >= 1
    assert readme.preservation(before, after, removed) == []
    assert readme.is_footer_copy(unmarked(src), brand, own_site=True) is False


def test_historical_logo_path_with_query_still_migrates(brand, tmp_path):
    src = "https://www.complete.tech/wp-content/uploads/logo.png?ver=2"
    assert readme.is_footer_copy(unmarked(src), brand, own_site=True) is True
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src))
    assert src in before
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1
    assert src not in after
    assert readme.preservation(before, after, removed) == []


def test_regular_unmarked_footer_does_not_exempt_reemitted_banner_anchors(brand, tmp_path):
    """The legacy footer is multi-line and shares its standalone anchor lines with the footer that is emitted again.
    Anchor lines the new footer carries must not be added to `removed`: the multiset guard then still sees one banner
    anchor pair missing (before: banner + old footer = 2, after: the new footer = 1). Had the whole old footer been
    exempted (`removed += old_footer`), the exemption would hide the lost banner anchors and preservation would pass.
    A one-line legacy footer would not show this, because it has no standalone anchor lines to exempt."""
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    assert ctx.det["variant"] == "C"
    scaffold = readme.scaffold(ctx)
    banner_body = readme.banner_html(ctx)
    assert readme.wrap("banner", banner_body) in scaffold
    # the generated banner wrapped in a standalone company-link anchor, one anchor tag per line
    linked = "\n".join([readme.start("banner"), OWN_SITE_LINK, banner_body, CLOSE_LINK, readme.end("banner")])
    light = brand.raw["footer"]["logo_light_url"]
    old_footer = footer.markup(brand).replace(f'<img src="{light}"', '<img src="docs/images/logo.svg"', 1)
    assert old_footer != footer.markup(brand)
    old_lines, new_lines = Counter(stripped_lines(old_footer)), Counter(stripped_lines(footer.block(brand)))
    for anchor in (OWN_SITE_LINK, CLOSE_LINK):  # both the old and the new footer carry the anchor as its own line
        assert old_lines[anchor] == 1 and new_lines[anchor] == 1
    before = scaffold.replace(readme.wrap("banner", banner_body), linked).replace(footer.block(brand), old_footer)
    assert linked in before and old_footer in before and footer.block(brand) not in before

    after, removed = readme.upgrade(ctx, before)

    assert after.count("Built by") == 1 and "docs/images/logo.svg" not in after
    # the regenerated banner carries no company anchors: the wrapper it lost must be reported, not exempted
    problems = readme.preservation(before, after, removed)
    assert f"lost line: {OWN_SITE_LINK}" in problems
    assert f"lost line: {CLOSE_LINK}" in problems
    # removed holds no anchor line: the new footer carries both again
    removed_counts = Counter(stripped_lines("\n".join(removed)))
    for anchor in (OWN_SITE_LINK, CLOSE_LINK):
        assert removed_counts[anchor] == 0


def test_unmarked_footer_removed_lines_exclude_reemitted_lines(brand, tmp_path):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    light = brand.raw["footer"]["logo_light_url"]
    # a multi-line legacy footer: the marked footer's markup, with only its own logo image pointing at a local file
    old_footer = footer.markup(brand).replace(f'<img src="{light}"', '<img src="docs/images/logo.svg"', 1)
    assert old_footer != footer.markup(brand)
    before = readme.scaffold(ctx).replace(footer.block(brand), old_footer)
    assert footer.block(brand) not in before and old_footer in before

    after, removed = readme.upgrade(ctx, before)

    old_lines = Counter(stripped_lines(old_footer))
    new_lines = Counter(stripped_lines(footer.block(brand)))
    surplus = old_lines - new_lines
    footer_vocabulary = set(old_lines) | set(new_lines)
    removed_footer = Counter(ln.strip() for ln in removed if ln.strip() in footer_vocabulary)
    assert removed_footer <= surplus
    assert readme.preservation(before, after, removed) == []
