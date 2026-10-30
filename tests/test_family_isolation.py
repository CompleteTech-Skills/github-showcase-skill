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

# Org rows are NOT exempted here. The org blob (ctx.org) is part of the banner inputs, so a CompleteTech string in the
# row itself fails the banner-style check: AI-Ascension, Jev-Engineering, LibreEvolve and jevplay-games carry
# "Steward: CompleteTech LLC." in description; romgenie-archive-repostiory and romgenie-following-repos also carry
# brand_topic: completetech. Those are findings for an owner decision (see the PR body), not documented gaps; there is
# deliberately no per-row text allowlist, so any new leak still fails.

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


def strip_footer_only(md):
    """Remove only the decision 18 footer (its <picture> block and any 'Built by' line). Type badges stay."""
    out = FOOTER_PICTURE.sub('', md)
    return FOOTER_BUILT_BY.sub('', out)


def strip_footer(md):
    """The decision 18 footer and every 005ADD type badge image (the KNOWN_TYPE_BADGE_GAP shape)."""
    return TYPE_BADGE_005ADD.sub('', strip_footer_only(md))


def scene_text(scene):
    """Every text string the scene draws, including text nested in clip children, plus the SVG title and desc.

    Outlined text in the SVG is paths, so the SVG check alone cannot see a leaked eyebrow; this walks the scene.
    """
    from ctshowcase.scene import Text
    out = [scene.title, scene.desc]

    def walk(nodes):
        for node in nodes:
            if isinstance(node, Text):
                out.append(node.text)
            walk(getattr(node, 'children', None) or [])

    walk(scene.nodes)
    return out


def card_leaks(ctx, fonts):
    from ctshowcase import card
    svg, scene, _info = card.render(ctx, fonts)
    hits = [m.group(0) for m in FORBIDDEN.finditer(svg)]
    hits += [m.group(0) for text in scene_text(scene) for m in FORBIDDEN.finditer(text)]
    return hits


@pytest.mark.parametrize('owner', ORG_OWNERS, ids=ORG_OWNERS)
def test_org_row_renders_without_completetech_leak(owner, brand, fonts, tmp_path):
    from ctshowcase import readme, readmelint

    row = brand.raw['orgs'][owner]
    if completetech_owned(owner, row, brand):
        pytest.skip('CompleteTech-owned row')
    if owner in KNOWN_MISMATCHES:
        pytest.xfail('family needs owner-supplied palette and mark (issue 40 task 43)')

    ctx = synthetic_ctx(brand, owner)
    gaps: list[str] = []  # documented gaps: every other check still runs, then one xfail reports them

    # CARD: the SVG and every text string in the scene (outlined text is invisible to the SVG check alone).
    leaked = card_leaks(ctx, fonts)
    assert not leaked, f'card leaks CompleteTech branding: {leaked}'

    # README HEADER. The footer is the one CompleteTech surface allowed in a non-owned README, so it is removed first.
    # A 005ADD type badge is not allowed: it is only excused for KNOWN_TYPE_BADGE_GAP rows, and only when it is there.
    md = readme.scaffold(ctx)
    badges = TYPE_BADGE_005ADD.findall(strip_footer_only(md))
    if owner in KNOWN_TYPE_BADGE_GAP:
        assert badges, (
            f'stale KNOWN_TYPE_BADGE_GAP entry for {owner}: no 005ADD type badge in the header; delete the entry')
        gaps.append(KNOWN_TYPE_BADGE_GAP[owner])
    else:
        assert not badges, f'README header carries a 005ADD type badge: {badges}'
    header = strip_footer(md)
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

    # BANNER STYLE: the banner is a PNG, so its inputs (style tokens and the whole org row) are scanned instead.
    blob = json.dumps({'style': ctx.style, 'org': {k: v for k, v in ctx.org.items()}}, default=str)
    if FORBIDDEN.search(blob) and owner in KNOWN_DEFAULTS_INHERITANCE:
        gaps.append(KNOWN_DEFAULTS_INHERITANCE[owner])
    else:
        assert not FORBIDDEN.search(blob), (
            f'banner style inputs leak CompleteTech branding: {sorted({m.group(0) for m in FORBIDDEN.finditer(blob)})}')

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
    # On the full scaffold the footer goes, and so does the 005ADD type badge (strip_footer's rule); other badges stay.
    full = strip_footer(md)
    assert '<picture>' not in full and 'Built by' not in full
    assert 'img.shields.io/badge/language-Python' in full
    assert not TYPE_BADGE_005ADD.search(full)
    assert TYPE_BADGE_005ADD.search(strip_footer_only(md))


def test_strip_footer_removes_a_005add_type_badge_image():
    # strip_footer's documented rule: a 005ADD type badge image goes (KNOWN_TYPE_BADGE_GAP), and a teal one stays.
    badge = '![Type Workspace](https://img.shields.io/badge/type-Workspace-005ADD)'
    teal = '![Type Workspace](https://img.shields.io/badge/type-Workspace-0F766E)'
    planted = f'# synthetic-repo\n\n{badge} {teal}\n\n<img src="https://img.shields.io/badge/type-Tool-005ADD" alt="t">\n'
    stripped = strip_footer(planted)
    assert 'type-Workspace-005ADD' not in stripped and 'type-Tool-005ADD' not in stripped
    assert teal in stripped and '# synthetic-repo' in stripped


def test_footer_only_strip_keeps_a_type_badge():
    # Regression for the review finding: the header check must see a 005ADD type badge, so it uses the footer-only strip.
    badge = '![Type Workspace](https://img.shields.io/badge/type-Workspace-005ADD)'
    planted = f'# synthetic-repo\n\n{badge}\n'
    assert strip_footer_only(planted) == planted
    assert TYPE_BADGE_005ADD.search(strip_footer_only(planted))
    assert FORBIDDEN.search(strip_footer_only(planted))


def test_planted_005add_type_badge_fails_the_header_check(brand):
    # Pick-Your-AI has its own teal type badge (badge_brand). Recolouring that badge to 005ADD must be caught by the
    # same README header check the leak test runs (the footer-only strip, not the badge-stripping one).
    from ctshowcase import readme

    ctx = synthetic_ctx(brand, 'Pick-Your-AI')
    assert not FORBIDDEN.search(strip_footer(readme.scaffold(ctx)))  # baseline: the teal badge is clean
    ctx.style = {**ctx.style, 'badge_brand': '005ADD'}
    header = strip_footer_only(readme.scaffold(ctx))
    assert TYPE_BADGE_005ADD.search(header), 'the planted recolour did not reach the README header'
    assert FORBIDDEN.search(header)


def test_card_text_scan_catches_a_planted_eyebrow(brand, fonts, monkeypatch):
    # Regression for the review finding: outlined eyebrow text is invisible to the SVG check. A planted CompleteTech
    # eyebrow must be caught through the scene text, and the SVG on its own must miss it (the reason the scan exists).
    from ctshowcase import card

    ctx = synthetic_ctx(brand, 'Pick-Your-AI')
    assert not card_leaks(ctx, fonts)  # baseline: clean card
    monkeypatch.setattr(card, 'eyebrow', lambda _ctx: 'CompleteTech LLC')
    svg, scene, _info = card.render(ctx, fonts)
    assert not FORBIDDEN.search(svg), 'the SVG check was expected to miss outlined text'
    assert any(FORBIDDEN.search(text) for text in scene_text(scene)), 'the scene text scan missed the planted eyebrow'
    assert card_leaks(ctx, fonts)
