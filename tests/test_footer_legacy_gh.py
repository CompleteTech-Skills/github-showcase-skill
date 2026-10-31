"""Fork (G) and backup (H) READMEs migrate the former footer logo URLs (issue 47).

`readme.upgrade` returns early through `callout_only` for variants G and H. These tests pin that the legacy footer
(marked or unmarked) is replaced there too, that the replaced lines are accepted by the preservation check, and that
the guard which exempts replaced lines never vouches for a custom image just because its alt text matches.
"""
import copy

import pytest

from conftest import meta_dict
from ctshowcase import footer, readme
from ctshowcase.config import Brand
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

LEGACY = "https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/"
PARENT = {"full_name": "someone/upstream", "default_branch": "main"}
UPSTREAM = "# Upstream project\n\nAuthored upstream text, kept as written.\n\n## Usage\n\nRun it.\n"
VARIANTS = {
    "G": dict(fork=True, parent=PARENT),
    "H": dict(repo="host-backup-20260914"),
}


def legacy_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["footer"].update(logo_light_url=LEGACY + "logo.png", logo_dark_url=LEGACY + "logo-dark.png")
    return Brand(raw, brand.path)


def ctx_for(brand, variant, tmp_path):
    ctx = RepoContext(brand, normalize(meta_dict(**VARIANTS[variant])), tmp_path)
    assert ctx.det["variant"] == variant
    return ctx


def legacy_readme(brand, marked):
    old = legacy_brand(brand)
    return UPSTREAM + "\n" + (footer.block(old) if marked else footer.markup(old)) + "\n"


@pytest.mark.parametrize("marked", [True, False], ids=["marked", "unmarked"])
@pytest.mark.parametrize("variant", ["G", "H"])
def test_legacy_footer_is_migrated_on_fork_and_backup_readmes(brand, tmp_path, variant, marked):
    ctx = ctx_for(brand, variant, tmp_path)
    before = legacy_readme(brand, marked)
    assert LEGACY in before and footer.check(brand, before)[0] != "pass"
    after, removed = readme.upgrade(ctx, before)
    assert LEGACY not in after
    assert footer.check(brand, after)[0] == "pass"  # exactly one footer: no fail:duplicate
    assert after.count("complete.tech") == footer.markup(brand).count("complete.tech")
    assert removed, "the replaced footer lines are reported"
    assert readme.preservation(before, after, removed) == []
    assert UPSTREAM.strip() in after  # authored content above the footer is byte-preserved
    again, _ = readme.upgrade(ctx_for(brand, variant, tmp_path), after)
    assert again == after


def custom_footer(brand):
    f = brand.raw["footer"]
    block = footer.block(brand).replace(f["logo_light_url"], "https://example.test/partner-badge.png")
    block = block.replace(f["logo_dark_url"], "https://example.test/partner-badge-dark.png")
    return block.replace(f'alt="{f["alt"]}"', 'alt="Partner"')


def partner_alt_kept(brand):
    """A marked footer whose light image is a partner badge while the alt text stays the company name."""
    return footer.block(brand).replace(brand.raw["footer"]["logo_light_url"], "https://example.test/partner-badge.png")


def test_fork_readme_with_custom_marked_footer_is_left_untouched(brand, tmp_path):
    ctx = ctx_for(brand, "G", tmp_path)
    custom = custom_footer(brand)
    before = UPSTREAM + "\n" + custom + "\n"
    after, removed = readme.upgrade(ctx, before)
    assert removed == []
    assert custom in after
    assert readme.preservation(before, after, removed) == []


def test_matching_alt_does_not_vouch_for_a_custom_image_src(brand, tmp_path):
    block = partner_alt_kept(brand)
    assert 'alt="CompleteTech LLC"' in block
    assert not readme.is_footer_copy(block, brand)
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), block)
    assert "partner-badge.png" in before
    after, removed = readme.upgrade(ctx, before)
    # same outcome as origin/main: the custom image is not exempted, so the preservation check raises readme-shrink
    assert readme.preservation(before, after, removed)


def test_fork_with_alt_matching_custom_src_is_not_replaced(brand, tmp_path):
    ctx = ctx_for(brand, "G", tmp_path)
    before = UPSTREAM + "\n" + partner_alt_kept(brand) + "\n"
    after, removed = readme.upgrade(ctx, before)
    assert "partner-badge.png" in after and removed == []


def test_footer_copy_guard_accepts_alt_only_current_and_legacy_images(brand):
    markup = footer.markup(brand)
    assert readme.is_footer_copy(markup, brand)
    legacy = footer.markup(legacy_brand(brand))
    assert LEGACY in legacy and readme.is_footer_copy(legacy, brand)  # legacy src with matching alt
    light = brand.raw["footer"]["logo_light_url"]
    alt_only = markup.replace(f'<img src="{light}" alt=', "<img alt=")
    assert alt_only != markup and "<img alt=" in alt_only
    assert readme.is_footer_copy(alt_only, brand)  # alt-only img, no src
    other = markup.replace(light, "https://example.test/x.png").replace('alt="CompleteTech LLC"', 'alt="Partner"')
    assert not readme.is_footer_copy(other, brand)
