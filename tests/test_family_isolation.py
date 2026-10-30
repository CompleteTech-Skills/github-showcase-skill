"""Audit that no non-CompleteTech org row resolves to the completetech family (E2.2.1, task 41), and that
no non-CompleteTech org row renders CompleteTech branding on any generated surface (E2.2.2, task 42).

Synthetic and public metadata only. Org keys are matched case-sensitively against brand.raw
directly; brand.org() is deliberately not used because it resolves aliases.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from ctshowcase.config import load_brand  # noqa: E402

FORBIDDEN = re.compile(r'completetech|CompleteDotTech|005ADD', re.I)
LEGIT_COMPLETETECH_ROWS = {'CompleteDotTech': 'the CompleteTech owner user account (display name is a person)'}  # the synthetic demo owner is added at runtime from brand.raw['brand_strings']['demo_owner'] (currently Northwind-Trading-Co)
KNOWN_MISMATCHES = {'Jevelopers-neatHack-2026'}  # TicketStub; removed when task 43 lands

# Org rows whose own text (the whole org row, not the banner or card) names CompleteTech. Each entry lists the
# exact row keys that match FORBIDDEN and why. The leak test xfails only when exactly those keys match, so any
# new leak in another key, or in the card, README header, lint output or banner style, still fails.
KNOWN_ORG_ROW_TEXT = {
    'AI-Ascension': (('description',), 'description ends "Steward: CompleteTech LLC." (brand.yaml); the org profile text only'),
    'Jev-Engineering': (('description',), 'description ends "Steward: CompleteTech LLC." (brand.yaml); the org profile text only'),
    'LibreEvolve': (('description',), 'description ends "Steward: CompleteTech LLC." (brand.yaml); the org profile text only'),
    'jevplay-games': (('description',), 'description ends "Steward: CompleteTech LLC." (brand.yaml); the org profile text only'),
    'romgenie-archive-repostiory': (('brand_topic', 'description'), 'brand_topic: completetech (a family topic, see topics.py) and a description naming CompleteTech LLC'),
    'romgenie-following-repos': (('brand_topic', 'description'), 'brand_topic: completetech (a family topic, see topics.py) and a description naming CompleteTech LLC'),
}

# Rows whose card, README, lint or banner style inherit 005ADD from `defaults` would go here. The probe found none:
# every family that is not CompleteTech overrides each token that defaults sets to 005ADD.
KNOWN_DEFAULTS_INHERITANCE: dict[str, str] = {}

# Module-level, not a fixture: parametrize ids need the owner names at collection time.
ALL_BRAND = load_brand(ROOT / 'references' / 'brand.yaml')
ORG_OWNERS = sorted(ALL_BRAND.raw['orgs'])

# Decision 18 footer: its <picture> block and every line containing "Built by".
FOOTER_PICTURE = re.compile(r'<picture>.*?</picture>', re.S)
FOOTER_BUILT_BY = re.compile(r'^[^\n]*Built by[^\n]*\n?', re.M)
# Family-without-badge_brand type badge in 005ADD (KNOWN_TYPE_BADGE_GAP, recorded in the audit; fix needs a design decision).
TYPE_BADGE_005ADD = re.compile(
    r'!\[[^\]]*\]\([^)"]*img\.shields\.io/badge/type-[^)"]*-005ADD[^)"]*\)'
    r'|<img\b[^>]*?img\.shields\.io/badge/type-[^>"]*-005ADD[^>]*>',
    re.S,
)


def family_mismatches(raw: dict) -> set[str]:
    demo_owner = raw['brand_strings']['demo_owner']
    return {
        owner
        for owner, row in raw['orgs'].items()
        if row.get('family') == 'completetech'
        and 'completetech' not in str(row.get('display_name', '')).lower()
        and owner not in LEGIT_COMPLETETECH_ROWS
        and owner != demo_owner
    }


def test_known_family_mismatches_are_exactly_the_documented_list(brand):
    assert family_mismatches(brand.raw) == KNOWN_MISMATCHES


@pytest.mark.xfail(strict=True, reason='Jevelopers-neatHack-2026 (TicketStub) still family: completetech; needs an owner-supplied palette and mark, see issue 40 task 43')
def test_no_non_completetech_row_uses_the_completetech_family(brand):
    assert family_mismatches(brand.raw) == set()


def undefined_families(raw: dict) -> set[str]:
    families = raw['families']
    return {owner for owner, row in raw['orgs'].items() if row['family'] not in families}


def test_every_org_family_exists(brand):
    # 'completetech' is an ordinary key of families (brand.yaml); no special case, so a removed
    # families.completetech fails here instead of being silently accepted by the org rows.
    assert undefined_families(brand.raw) == set()


def test_family_existence_check_catches_removed_completetech_family(brand):
    # Evidence that the membership check above is not vacuous: drop families.completetech from an
    # in-memory copy and every completetech org row must be reported as undefined.
    import copy
    raw = copy.deepcopy(brand.raw)
    del raw['families']['completetech']
    reported = undefined_families(raw)
    assert 'CompleteDotTech' in reported
    assert reported == {owner for owner, row in raw['orgs'].items() if row['family'] == 'completetech'}


def test_legit_exceptions_still_exist(brand):
    demo_owner = brand.raw['brand_strings']['demo_owner']
    for owner in [*LEGIT_COMPLETETECH_ROWS, demo_owner]:
        assert owner in brand.raw['orgs'], owner


# -- E2.2.2 generic cross-brand leak test (task 42) ------------------------------------------------

@pytest.fixture(scope='module', autouse=True)
def t3_signed_off():
    # Owner gates (check_owner, art_status, footer_status) refuse T3 rows unless the run is signed off.
    # The leak test renders every row, so it records the sign-off for the module and restores it after.
    from ctshowcase.config import set_t3_signed_off
    set_t3_signed_off(True)
    try:
        yield
    finally:
        set_t3_signed_off(False)


def completetech_owned(owner, row, brand):
    return ('completetech' in str(row.get('display_name', '')).lower()
            or owner in LEGIT_COMPLETETECH_ROWS
            or owner == brand.raw['brand_strings']['demo_owner'])


def synthetic_ctx(brand, owner):
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    return RepoContext(brand, normalize({'owner': owner, 'repo': 'synthetic-repo', 'description': 'Synthetic repository for the leak test.', 'topics': [], 'visibility': 'public', 'language': 'Python', 'license': 'MIT', 'labels': []}), None)


def strip_footer(md):
    """Remove the decision 18 footer (its <picture> block and any 'Built by' line) and the family type badge in 005ADD."""
    out = FOOTER_PICTURE.sub('', md)
    out = FOOTER_BUILT_BY.sub('', out)
    return TYPE_BADGE_005ADD.sub('', out)


@pytest.mark.parametrize('owner', ORG_OWNERS, ids=ORG_OWNERS)
def test_org_row_renders_without_completetech_leak(owner, brand, fonts, tmp_path):
    from ctshowcase import card, readme, readmelint

    row = brand.raw['orgs'][owner]
    if completetech_owned(owner, row, brand):
        pytest.skip('CompleteTech-owned row')
    if owner in KNOWN_MISMATCHES:
        pytest.xfail('family needs owner-supplied palette and mark (issue 40 task 43)')

    ctx = synthetic_ctx(brand, owner)

    # CARD
    svg, _scene, _info = card.render(ctx, fonts)
    assert not FORBIDDEN.search(svg), 'card leaks CompleteTech branding'

    # README HEADER (footer stripped; the footer is the one CompleteTech surface allowed in a non-owned README)
    header = strip_footer(readme.scaffold(ctx))
    assert not FORBIDDEN.search(header), 'README header leaks CompleteTech branding'

    # LINT: does not choke on the scaffold. A FAIL is legitimate here (no local banner file in tmp_path), so
    # only the lint output text is checked for leaks, without the tmp path that the result carries.
    readme_path = tmp_path / 'README.md'
    readme_path.write_text(readme.scaffold(ctx), encoding='utf-8')
    res = readmelint.lint(ctx, readme_path)
    assert isinstance(res, dict), res
    lint_text = json.dumps({k: v for k, v in res.items() if k != 'file'}, default=str)
    assert not FORBIDDEN.search(lint_text), f'lint output leaks CompleteTech branding: {lint_text}'

    # BANNER STYLE: the banner is a PNG, so its inputs are scanned instead of pixels.
    if owner in KNOWN_DEFAULTS_INHERITANCE:
        pytest.xfail(KNOWN_DEFAULTS_INHERITANCE[owner])
    style_blob = json.dumps({'style': ctx.style}, default=str)
    assert not FORBIDDEN.search(style_blob), 'banner style inputs leak CompleteTech branding'

    # ORG ROW TEXT (banner inputs include ctx.org): the xfail is reached only when exactly the documented keys leak.
    leaking = sorted(k for k, v in ctx.org.items() if FORBIDDEN.search(json.dumps(v, default=str)))
    known = KNOWN_ORG_ROW_TEXT.get(owner)
    if known is not None and leaking == sorted(known[0]):
        pytest.xfail(f'org row text names CompleteTech in {leaking}: {known[1]}')
    assert not leaking, f'org row keys leak CompleteTech branding: {leaking}'


def test_leak_regex_catches_a_planted_leak():
    # Guards against FORBIDDEN being edited into a pattern that matches nothing.
    assert FORBIDDEN.search('x 005add y')
    assert FORBIDDEN.search('Built by CompleteTech LLC')
    assert FORBIDDEN.search('CompleteDotTech')
    assert not FORBIDDEN.search('Pick Your AI teal 0F766E')


def test_strip_footer_removes_only_the_footer(brand):
    from ctshowcase import readme

    ctx = synthetic_ctx(brand, 'AI-Ascension')  # footer True row
    md = readme.scaffold(ctx)
    assert '<picture>' in md and 'Built by' in md  # the footer is really there before stripping
    stripped = strip_footer(md)
    assert '<picture>' not in stripped and 'Built by' not in stripped
    assert not FORBIDDEN.search(stripped)
    assert readme.product_name(ctx) in stripped
    assert 'img.shields.io/badge/language-Python' in stripped  # non-type badges survive
