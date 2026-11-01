"""Footer image attributes are matched as whole attribute names (issue 47, source finding P2 at 4823d10).

`is_footer_copy` used to read `data-alt="<company>"` as an `alt` attribute, so a partner image with a real
`alt="Partner"` could be taken for a footer copy and removed by the G/H callout path or `upgrade()`. Only exact
`alt`, `src` and `srcset` attribute names count, and the first occurrence of a name is the one a browser reads.

Synthetic data only: the brand is the shared `brand` fixture (conftest), the partner alt is "Partner" and the local
partner-style source is `assets/logo.png`. The tests mirror the scaffold, upgrade and preservation pattern of
tests/test_footer_upgrade_preservation.py.
"""
import pytest

from conftest import meta_dict
from ctshowcase import footer, readme
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

PARTNER = "Partner"
LOCAL = "assets/logo.png"
UPSTREAM = "# Upstream project\n\nAuthored upstream text, kept as written.\n\n## Usage\n\nRun it.\n"


def credit(brand):
    f = brand.raw["footer"]
    return f"<sub>{f['line_prefix']} {brand.strings['company']} {f['line_suffix']}</sub>"


def block_with(brand, attrs):
    return '<p align="center">\n<img %s>\n<br>\n%s\n</p>' % (attrs, credit(brand))


def ctx_for(brand, tmp_path, **kw):
    return RepoContext(brand, normalize(meta_dict(**kw)), tmp_path)


def image_lines(text, src):
    return sum(1 for ln in text.splitlines() if src in ln)


# (a) attribute names other than alt, src and srcset never authorize a footer image


@pytest.mark.parametrize("attrs", [
    'src="assets/logo.png" alt="Partner" data-alt="CompleteTech LLC"',
    'src="assets/logo.png" alt="Partner" xalt="CompleteTech LLC"',
    'src="assets/logo.png" alt="Partner" title="alt=CompleteTech LLC"',
    'src="assets/logo.png" data-alt="CompleteTech LLC"',
    'data-src="{logo}" src="assets/partner.png" alt="CompleteTech LLC"',
], ids=["data-alt", "xalt", "title-alt", "data-alt-no-alt", "data-src-partner-file"])
def test_non_alt_attribute_names_do_not_authorize(brand, attrs):
    attrs = attrs.replace("{logo}", brand.raw["footer"]["logo_light_url"])
    assert readme.is_footer_copy(block_with(brand, attrs), brand) is False


# (b) first-attribute semantics: the first alt is the one that counts


def test_first_alt_partner_wins_over_later_company_alt(brand):
    block = block_with(brand, f'src="{LOCAL}" alt="{PARTNER}" alt="{brand.strings["company"]}"')
    assert readme.is_footer_copy(block, brand) is False


def test_first_alt_company_wins_over_later_partner_alt(brand):
    block = block_with(brand, f'src="{LOCAL}" alt="{brand.strings["company"]}" alt="{PARTNER}"')
    assert readme.is_footer_copy(block, brand) is True


# (c) positive controls, the company alt and the footer's own logo keep working


def test_company_alt_on_former_local_logo_is_footer_copy(brand):
    block = block_with(brand, f'src="{LOCAL}" alt="{brand.strings["company"]}"')
    assert readme.is_footer_copy(block, brand) is True


def test_footer_logo_src_with_partner_alt_is_still_footer_copy(brand):
    # existing behaviour: a src that is the brand footer logo URL is accepted whatever the alt says
    block = block_with(brand, f'src="{brand.raw["footer"]["logo_light_url"]}" alt="{PARTNER}"')
    assert readme.is_footer_copy(block, brand) is True


# (d) _footer_attrs: exact names only, first occurrence, quotes stripped, never raises


def test_footer_attrs_keeps_exact_names_first_occurrence_quotes_stripped():
    attrs = ('data-alt="CompleteTech LLC" xalt="CompleteTech LLC" title="alt=CompleteTech LLC" data-src="x.png" '
             "src='assets/logo.png' alt=\"Partner\" alt=\"CompleteTech LLC\" srcset=assets/logo-2x.png 2x")
    got = readme._footer_attrs(attrs)
    assert isinstance(got, dict)
    assert set(got) <= {"alt", "src", "srcset"}
    assert got["alt"] == PARTNER  # first occurrence, quotes stripped
    assert got["src"] == LOCAL
    assert got["srcset"] == "assets/logo-2x.png"


@pytest.mark.parametrize("attrs", ['alt="CompleteTech LLC src="assets/logo.png', "src='unterminated", "", "   ", "alt="])
def test_footer_attrs_tolerates_unterminated_and_empty_input(attrs):
    got = readme._footer_attrs(attrs)
    assert isinstance(got, dict)
    assert set(got) <= {"alt", "src", "srcset"}


def test_footer_attrs_empty_input_has_no_attributes():
    assert readme._footer_attrs("") == {}


def test_footer_attrs_valueless_first_alt_wins(brand):
    # a valueless attribute is still the first occurrence: a later duplicate never overrides it
    company = brand.strings["company"]
    got = readme._footer_attrs(f'src="{LOCAL}" alt alt="{company}"')
    assert got["alt"] == ""
    assert got["src"] == LOCAL
    # `alt= alt=...`: an unquoted value runs to the next whitespace, as a browser reads it, so the value is
    # `alt="<company>` and not the company name; the first alt never vouches for the image
    got = readme._footer_attrs(f'src="{LOCAL}" alt= alt="{company}"')
    assert got.get("alt") != company
    assert got["src"] == LOCAL
    # a valueless src followed by a duplicate src
    got = readme._footer_attrs(f'src alt="{PARTNER}" src="{LOCAL}"')
    assert got["src"] == ""
    assert got["alt"] == PARTNER


# (e) marked footer regression through the scaffold, G/H callout and upgrade paths


def marked_partner_footer(brand):
    """A marked footer whose only image is a partner file with a real alt "Partner"; data-alt carries the company."""
    body = block_with(brand, f'src="{LOCAL}" alt="{PARTNER}" data-alt="{brand.strings["company"]}"')
    return f"{footer.START}\n{body}\n{footer.END}"


def test_marked_data_alt_partner_footer_is_not_exempt_from_preservation_in_upgrade(brand, tmp_path):
    # upgrade() regenerates the marked footer block; a partner image in it is not a footer copy, so it is not reported
    # as removed and the never-drop-a-line guard (preservation, i.e. readme-shrink) refuses the replacement.
    ctx = ctx_for(brand, tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), marked_partner_footer(brand))
    assert LOCAL in before and footer.block(brand) not in before
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if LOCAL in ln], "the partner image was exempted from preservation"
    problems = readme.preservation(before, after, removed)
    assert any(LOCAL in p for p in problems), problems


@pytest.mark.parametrize("variant", ["G", "H"])
def test_marked_data_alt_partner_footer_is_kept_through_callout_upgrade(brand, tmp_path, variant):
    kw = dict(fork=True, parent={"full_name": "someone/upstream", "default_branch": "main"}) if variant == "G" \
        else dict(repo="host-backup-20260914")
    ctx = ctx_for(brand, tmp_path, **kw)
    assert ctx.det["variant"] == variant
    before = UPSTREAM + "\n" + marked_partner_footer(brand) + "\n"
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if LOCAL in ln], "the partner image was reported as removed"
    assert image_lines(after, LOCAL) == image_lines(before, LOCAL)
    assert image_lines(after, LOCAL) >= 1
    assert readme.preservation(before, after, removed) == []


# (f) a valueless alt before a company alt never vouches for an image: the first alt is the one a browser reads


@pytest.mark.parametrize("src", [LOCAL, "assets/custom-mark.png"], ids=["former-local-logo", "custom-local-image"])
def test_is_footer_copy_valueless_alt_local_image_not_footer(brand, src):
    company = brand.strings["company"]
    block = block_with(brand, f'src="{src}" alt alt="{company}"')
    assert readme.is_footer_copy(block, brand) is False


def test_company_alt_on_former_local_logo_is_footer_copy_control(brand):
    # control for the valueless-alt case: the same former local logo with a real company alt is footer copy
    block = block_with(brand, f'src="{LOCAL}" alt="{brand.strings["company"]}"')
    assert readme.is_footer_copy(block, brand) is True


def test_company_alt_on_custom_local_image_is_not_footer_copy_control(brand):
    # control: a custom local image is never footer copy on the alt alone, so the valueless-alt case cannot change it
    block = block_with(brand, f'src="assets/custom-mark.png" alt="{brand.strings["company"]}"')
    assert readme.is_footer_copy(block, brand) is False


@pytest.mark.parametrize("src", [LOCAL, "assets/custom-mark.png"], ids=["former-local-logo", "custom-local-image"])
def test_marked_valueless_alt_local_image_footer_is_not_removed_in_upgrade(brand, tmp_path, src):
    # the authored image in a marked footer is not reported as removed; the replacement is refused by the
    # preservation guard or the image line survives in the output
    ctx = ctx_for(brand, tmp_path)
    body = block_with(brand, f'src="{src}" alt alt="{brand.strings["company"]}"')
    before = readme.scaffold(ctx).replace(footer.block(brand), f"{footer.START}\n{body}\n{footer.END}")
    assert src in before and footer.block(brand) not in before
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if src in ln], "the authored image was reported as removed"
    problems = readme.preservation(before, after, removed)
    assert problems or image_lines(after, src) >= 1, problems
