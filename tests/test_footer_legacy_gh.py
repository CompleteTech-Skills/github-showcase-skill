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


# ------------------------------------------------------------------ former local-logo footer and remote legacy URL footer
def old_local_footer(src, alt="CompleteTech LLC"):
    return ('<p align="center">\n  <a href="https://complete.tech"><img src="%s" alt="%s" width="160"></a><br>\n'
            '  <sub>Built by <a href="https://complete.tech">CompleteTech LLC</a> · Innovation at Every Integration</sub>\n'
            "</p>\n" % (src, alt))


@pytest.mark.parametrize("src", ["assets/logo.png", "./logo.png"])
def test_footer_copy_accepts_old_local_logo_and_remote_legacy_url_at_once(brand, src):
    assert readme.is_footer_copy(old_local_footer(src), brand)
    legacy = footer.markup(legacy_brand(brand))
    assert LEGACY in legacy and readme.is_footer_copy(legacy, brand)


@pytest.mark.parametrize("src", ["assets/logo.png", "./logo.png"])
def test_upgrade_on_old_local_logo_footer_yields_one_built_by(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), old_local_footer(src))
    assert "Built by" in before and src in before and footer.block(brand) not in before
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1
    assert removed and readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("block", [
    old_local_footer("assets/partner.png"),
    old_local_footer("assets/logo.png", alt="Partner"),
    old_local_footer("https://example.test/assets/logo.png"),
], ids=["partner-file", "wrong-alt", "foreign-host"])
def test_non_footer_images_are_not_footer_copies_and_are_left(brand, block):
    assert not readme.is_footer_copy(block, brand)
    text = "# A\n\n" + block
    assert readme.drop_old_footer(text, brand) == (text, [])


@pytest.mark.parametrize("marked", [True, False], ids=["marked", "unmarked"])
@pytest.mark.parametrize("variant", ["G", "H"])
def test_reemitted_footer_lines_are_not_reported_as_removed(brand, tmp_path, variant, marked):
    from collections import Counter

    ctx = ctx_for(brand, variant, tmp_path)
    before = legacy_readme(brand, marked)
    after, removed = readme.upgrade(ctx, before)
    assert removed, "the replaced footer lines are reported"
    kept = Counter(ln.strip() for ln in footer.block(brand).splitlines() if ln.strip())
    for ln in removed:
        # a line the replacement footer carries again is not a removal, so it must not be exempted from the guard
        assert kept[ln.strip()] == 0, f"re-emitted footer line reported as removed: {ln.strip()}"
    assert '<p align="center">' not in [ln.strip() for ln in removed]
    assert "</p>" not in [ln.strip() for ln in removed]
    assert readme.preservation(before, after, removed) == []


BANNER_BODY = '<a href="https://www.complete.tech">\n<img src="banner.png" alt="banner">\n</a>'


def banner_wrapped_legacy_readme(brand):
    banner = f"{readme.start('banner')}\n{BANNER_BODY}\n{readme.end('banner')}"
    filler = "Authored paragraph that stays exactly as written in the upstream project.\n\n" * 40
    return banner + "\n\n" + UPSTREAM + "\n" + filler + footer.block(legacy_brand(brand)) + "\n"


@pytest.mark.parametrize("variant", ["G", "H"])
def test_banner_wrapper_loss_beside_legacy_footer_is_refused(brand, tmp_path, variant):
    ctx = ctx_for(brand, variant, tmp_path)
    before = banner_wrapped_legacy_readme(brand)
    after, removed = readme.upgrade(ctx, before)
    problems = readme.preservation(before, after, removed)
    assert problems, "the banner loss must not be accepted"
    # the footer also carries a standalone </a>, so the banner's own wrapper line must still be counted as lost
    assert "lost line: </a>" in problems, problems


@pytest.mark.parametrize("variant", ["G", "H"])
def test_cli_refuses_banner_wrapper_loss_on_fork_footer_migration(brand, tmp_path, variant):
    import json

    from conftest import run_cli

    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(**VARIANTS[variant])), encoding="utf-8")
    readme_path = tmp_path / "README.md"
    before = banner_wrapped_legacy_readme(brand)
    readme_path.write_text(before, encoding="utf-8", newline="")
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--write")
    assert p.returncode != 0 and "readme-shrink" in p.stdout + p.stderr, p.stdout + p.stderr
    assert readme_path.read_bytes() == before.encode("utf-8"), "a refused write must leave README.md unchanged"
