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

# Families without badge_brand ship the type badge in the brand colour 005ADD (badges(), brand.yaml `badges.brand`).
# Probed on the base: these rows' README headers carry exactly that badge and nothing else CompleteTech-coloured.
# The header check excuses only this badge for these rows, the entry must still match a real badge (a stale entry
# fails), and the xfail is reported only after every other check has run. Fixing it needs a design decision.
KNOWN_TYPE_BADGE_GAP: dict[str, str] = {
    owner: 'type badge ships in 005ADD: family has no badge_brand (KNOWN_TYPE_BADGE_GAP, needs a design decision)'
    for owner in ('AI-Ascension', 'Jev-Engineering', 'LibreEvolve', 'TouchedByAnAgent', 'jevplay-games',
                  'romgenie-archive-repostiory', 'romgenie-following-repos')
}

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
    """Remove only the decision 18 footer (its <picture> block and any 'Built by' line).

    Type badges are deliberately kept: a 005ADD type badge is a real leak in a non-owned header, and stripping it
    hid one (review of task 42). Known badge rows are handled explicitly in the leak test, see KNOWN_TYPE_BADGE_GAP.
    """
    out = FOOTER_PICTURE.sub('', md)
    return FOOTER_BUILT_BY.sub('', out)


@pytest.mark.parametrize('owner', ORG_OWNERS, ids=ORG_OWNERS)
def test_org_row_renders_without_completetech_leak(owner, brand, fonts, tmp_path):
    from ctshowcase import card, readme, readmelint

    row = brand.raw['orgs'][owner]
    if completetech_owned(owner, row, brand):
        pytest.skip('CompleteTech-owned row')
    if owner in KNOWN_MISMATCHES:
        pytest.xfail('family needs owner-supplied palette and mark (issue 40 task 43)')

    ctx = synthetic_ctx(brand, owner)
    gaps: list[str] = []  # documented gaps: every other check still runs, then one xfail reports them

    # CARD
    svg, _scene, _info = card.render(ctx, fonts)
    assert not FORBIDDEN.search(svg), 'card leaks CompleteTech branding'

    # README HEADER. The footer is stripped (the one CompleteTech surface allowed in a non-owned README); the type
    # badge is not. Only the documented 005ADD badge is excused, and only for its own rows.
    md = readme.scaffold(ctx)
    header = strip_footer(md)
    if owner in KNOWN_TYPE_BADGE_GAP:
        assert TYPE_BADGE_005ADD.search(header), (
            f'stale KNOWN_TYPE_BADGE_GAP entry for {owner}: no 005ADD type badge in the header; delete the entry')
        gaps.append(KNOWN_TYPE_BADGE_GAP[owner])
        header = TYPE_BADGE_005ADD.sub('', header)
    leaked = [m.group(0) for m in FORBIDDEN.finditer(header)]
    assert not leaked, f'README header leaks CompleteTech branding: {leaked}'

    # LINT: does not choke on the scaffold. A FAIL is legitimate here (no local banner file in tmp_path), so
    # only the lint output text is checked for leaks, without the tmp path that the result carries.
    readme_path = tmp_path / 'README.md'
    readme_path.write_text(md, encoding='utf-8')
    res = readmelint.lint(ctx, readme_path)
    assert isinstance(res, dict), res
    lint_text = json.dumps({k: v for k, v in res.items() if k != 'file'}, default=str)
    assert not FORBIDDEN.search(lint_text), f'lint output leaks CompleteTech branding: {lint_text}'

    # BANNER STYLE: the banner is a PNG, so its inputs are scanned instead of pixels.
    if owner in KNOWN_DEFAULTS_INHERITANCE:
        gaps.append(KNOWN_DEFAULTS_INHERITANCE[owner])
    else:
        style_blob = json.dumps({'style': ctx.style}, default=str)
        assert not FORBIDDEN.search(style_blob), 'banner style inputs leak CompleteTech branding'

    # ORG ROW TEXT (banner inputs include ctx.org): a documented gap applies only when exactly the documented keys leak.
    leaking = sorted(k for k, v in ctx.org.items() if FORBIDDEN.search(json.dumps(v, default=str)))
    known = KNOWN_ORG_ROW_TEXT.get(owner)
    if known is not None and leaking == sorted(known[0]):
        gaps.append(f'org row text names CompleteTech in {leaking}: {known[1]}')
    else:
        assert not leaking, f'org row keys leak CompleteTech branding: {leaking}'

    if gaps:
        pytest.xfail('; '.join(gaps))


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
    picture, built_by = FOOTER_PICTURE.search(md), FOOTER_BUILT_BY.search(md)
    assert picture and built_by  # the footer is really there before stripping
    # A markdown string holding a title, body text and only the footer block copied from the scaffold.
    start = md.rfind('<p align="center">', 0, picture.start())
    planted = f'# synthetic-repo\n\nSynthetic body text.\n\n{md[start:built_by.end()]}\n'
    assert FORBIDDEN.search(planted)  # the footer leaks before stripping
    stripped = strip_footer(planted)
    assert '<picture>' not in stripped and 'Built by' not in stripped
    assert not FORBIDDEN.search(stripped)
    assert '# synthetic-repo' in stripped and 'Synthetic body text.' in stripped
    # On the full scaffold the footer goes and every other line stays, including the type badge and language badge.
    full = strip_footer(md)
    assert '<picture>' not in full and 'Built by' not in full
    assert 'img.shields.io/badge/language-Python' in full
    assert TYPE_BADGE_005ADD.search(full)


def test_strip_footer_keeps_a_type_badge(brand):
    # Regression for the review finding: a 005ADD type badge in a header must survive the footer strip and be seen.
    badge = '![Type Workspace](https://img.shields.io/badge/type-Workspace-005ADD)'
    planted = f'# synthetic-repo\n\n{badge}\n'
    assert strip_footer(planted) == planted
    assert FORBIDDEN.search(strip_footer(planted))


def test_planted_005add_type_badge_fails_the_header_check(brand):
    # Pick-Your-AI has its own teal type badge (badge_brand). Recolouring that badge to 005ADD must be caught by the
    # same README header check the leak test runs, not hidden by it.
    from ctshowcase import readme

    ctx = synthetic_ctx(brand, 'Pick-Your-AI')
    assert not FORBIDDEN.search(strip_footer(readme.scaffold(ctx)))  # baseline: the teal badge is clean
    ctx.style = {**ctx.style, 'badge_brand': '005ADD'}
    header = strip_footer(readme.scaffold(ctx))
    assert TYPE_BADGE_005ADD.search(header), 'the planted recolour did not reach the README header'
    assert FORBIDDEN.search(header)
