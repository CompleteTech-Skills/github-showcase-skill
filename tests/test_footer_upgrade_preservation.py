"""Footer upgrade preservation for partner and foreign images through `readme.upgrade` (issue 47, adjudication
t47-upgrade-preservation-adjudication.md and t47-source-trust-adjudication.md).

An unmarked footer whose <img> alt is exactly the company does not vouch for an arbitrary src. Partner images
(`assets/partner.png`), foreign hosts and look-alike hosts must survive `upgrade()`, and only the demonstrated own-site
legacy logos (the company website host derived from brand data, and the conventional local `docs/images/logo.svg`)
may migrate. These tests exercise the real path `RepoContext(brand, ...)` -> `readme.upgrade` -> `readme.preservation`.

Scope notes:
- The helper `unmarked` and the constants are copied locally from tests/test_footer_r6_regressions.py. No test module
  is imported from another test module.
- The write-flow test is intentionally absent. The only caller of `readme.preservation` on the write path is the
  gate in scripts/showcase.py (upgrade, then preservation) inside the full README command, which needs watching
  status, gate and ctx plumbing. No cheap public entry point exists, so no entry point was invented.
- At the owner head e58465e the partner, foreign and look-alike cases fail (`upgrade()` deletes them) and the
  `own_site=True` helper tests fail with TypeError until the readme.py fix lands. This file is a reproduction of that
  state and does not weaken any existing test.
"""
import copy

import pytest

from conftest import meta_dict
from ctshowcase import footer, readme
from ctshowcase.config import Brand
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

CREDIT = ('<sub>Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration'
          "</sub>")
OWN_SITE_HOST = "https://www.complete.tech"
DERIVED_HOST = "https://www.example-co.test"

NEGATIVE_SRCS = [
    "assets/partner.png",
    "https://example.test/assets/logo.png",
    "https://www.complete.tech.evil.test/wp-content/uploads/logo.png",
    "https://notcomplete.tech/logo.png",
]
POSITIVE_SRCS = [
    "https://www.complete.tech/wp-content/uploads/logo.png",
    "docs/images/logo.svg",
]


def unmarked(src, alt="CompleteTech LLC", href=OWN_SITE_HOST):
    return ('<p align="center"><a href="%s"><img src="%s" alt="%s" width="160"></a><br>%s</p>'
            % (href, src, alt, CREDIT.replace(OWN_SITE_HOST, href)))


def image_lines(text, src):
    return sum(1 for ln in text.splitlines() if src in ln)


@pytest.mark.parametrize("src", NEGATIVE_SRCS)
def test_company_alt_partner_or_foreign_image_is_kept_through_upgrade(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src))
    assert src in before and footer.block(brand) not in before
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if src in ln], f"{src} was reported as removed"
    assert image_lines(after, src) == image_lines(before, src)
    assert image_lines(after, src) >= 1
    assert readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("src", ["https://www.complete.tech/wp-content/uploads/logo.png"])
def test_wrong_alt_image_is_kept_through_upgrade(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src, alt="Partner"))
    assert src in before
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if src in ln], f"{src} was reported as removed"
    assert image_lines(after, src) == image_lines(before, src)
    assert image_lines(after, src) >= 1
    assert readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("src", POSITIVE_SRCS)
def test_own_site_legacy_logo_still_migrates_through_upgrade(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src))
    assert src in before
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1
    assert src not in after
    assert readme.preservation(before, after, removed) == []


def test_own_site_host_is_derived_from_brand_data(brand, tmp_path):
    raw = copy.deepcopy(brand.raw)
    raw["brand_strings"]["website"] = DERIVED_HOST
    raw["footer"]["href"] = DERIVED_HOST
    derived = Brand(raw, brand.path)
    ctx = RepoContext(derived, normalize(meta_dict()), tmp_path)
    own = DERIVED_HOST + "/wp-content/uploads/logo.png"
    before = readme.scaffold(ctx).replace(footer.block(derived), unmarked(own, href=DERIVED_HOST))
    assert own in before
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1 and own not in after
    assert readme.preservation(before, after, removed) == []
    # the previous public host is no longer this brand's own site, so its logo is kept as foreign
    foreign = OWN_SITE_HOST + "/wp-content/uploads/logo.png"
    before2 = readme.scaffold(ctx).replace(footer.block(derived), unmarked(foreign))
    after2, removed2 = readme.upgrade(ctx, before2)
    assert image_lines(after2, foreign) == image_lines(before2, foreign)
    assert image_lines(after2, foreign) >= 1
    assert not [ln for ln in removed2 if foreign in ln]


@pytest.mark.parametrize("src", NEGATIVE_SRCS)
def test_helper_rejects_non_own_site_images_with_own_site_flag(brand, src):
    block = unmarked(src)
    assert readme.is_footer_copy(block, brand, own_site=True) is False
    text = "# A\n\n" + block
    assert readme.drop_old_footer(text, brand, own_site=True) == (text, [])


def test_helper_wrong_alt_partner_is_rejected_with_own_site_flag(brand):
    block = unmarked(POSITIVE_SRCS[0], alt="Partner")
    assert readme.is_footer_copy(block, brand, own_site=True) is False
    text = "# A\n\n" + block
    assert readme.drop_old_footer(text, brand, own_site=True) == (text, [])


@pytest.mark.parametrize("src", POSITIVE_SRCS)
def test_helper_accepts_own_site_legacy_logos_with_own_site_flag(brand, src):
    assert readme.is_footer_copy(unmarked(src), brand, own_site=True) is True


def test_strict_default_drop_old_footer_keeps_company_alt_svg(brand):
    text = "# A\n\n" + unmarked("docs/images/logo.svg")
    assert readme.drop_old_footer(text, brand) == (text, [])
