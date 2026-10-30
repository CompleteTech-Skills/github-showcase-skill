"""Audit that no non-CompleteTech org row resolves to the completetech family (E2.2.1, task 41).

Synthetic and public metadata only. Org keys are matched case-sensitively against brand.raw
directly; brand.org() is deliberately not used because it resolves aliases.
"""
from __future__ import annotations

# NOTE for reviewers: this module is a regression AUDIT of existing behaviour (task 40 acceptance
# criteria 1 and 2 describe the current state of brand.yaml, not a code change). It is therefore
# expected to pass unchanged on the base commit; verified by running this file against base
# 2be04ac (13 passed, 19 skipped, 2 xfailed, identical to HEAD). A "fails on base" check does not
# apply: no default behaviour or brand.yaml edit is made, by design (see the acceptance criteria).

import copy
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

FORBIDDEN = re.compile(r'completetech|CompleteDotTech|005ADD', re.I)
LEGIT_COMPLETETECH_ROWS = {'CompleteDotTech': 'the CompleteTech owner user account (display name is a person)'}  # the synthetic demo owner is added at runtime from brand.raw['brand_strings']['demo_owner'] (currently Northwind-Trading-Co)
KNOWN_MISMATCHES = {'Jevelopers-neatHack-2026'}  # TicketStub; removed when task 43 lands


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


# -- Rendered-output audit (acceptance criterion 2) -------------------------------------------------
# The data audit above can pass while a render path still falls back to the CompleteTech family or the
# 005ADD brand blue. Render the card, the banner style tokens, the README scaffold and the README lint
# for EVERY org row and scan the text. This is an audit of existing data: it passes on the base because
# the base is already correct for every row except TicketStub (strict xfail below); it would fail on any
# regression, which test_render_audit_catches_a_family_regression demonstrates by mutation.
LEGIT_OWNED_NAMES = re.compile(r'completetech', re.I)
_TYPE_BADGE = re.compile(r'!\[Type [^\]]*\]\([^)]*\)')  # known gap: the 'Type' badge uses the global brand colour 005ADD


def _owned(raw: dict, owner: str) -> bool:
    """CompleteTech-owned rows may legitimately mention the family: display name, user account, demo owner."""
    return (owner not in family_mismatches(raw) and raw['orgs'][owner].get('family') == 'completetech')         or owner in LEGIT_COMPLETETECH_ROWS or owner == raw['brand_strings']['demo_owner']


def rendered_leaks(brand, owner: str, tmp_path: Path) -> dict[str, list[str]]:
    from conftest import EX, meta_dict
    from ctshowcase import card, footer, readme, readmelint
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    from ctshowcase.typeset import Fonts
    shutil.copytree(EX / 'repos' / 'northwind-support-triage-agent', tmp_path, dirs_exist_ok=True)
    (tmp_path / 'docs/images').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'docs/images/banner.png').write_bytes(b'x')
    ctx = RepoContext(brand, normalize(meta_dict(owner=owner, description='Run the Northwind customer support email triage agent from the command line.')), tmp_path)
    svg = card.render(ctx, Fonts(brand))[0]
    text = readme.scaffold(ctx, '')
    (tmp_path / 'README.md').write_text(text, encoding='utf-8')
    surfaces = {
        'card': svg.decode() if isinstance(svg, bytes) else svg,
        'banner style tokens': json.dumps(ctx.style, sort_keys=True),
        # decision 18: the footer is the one place the CompleteTech name is correct; strip it, then the Type badge gap
        'readme scaffold': _TYPE_BADGE.sub('', text.replace(footer.block(brand), '')),
        'readme lint': json.dumps(readmelint.lint(ctx, tmp_path / 'README.md')),
    }
    return {k: sorted({m.lower() for m in FORBIDDEN.findall(v)}) for k, v in surfaces.items() if FORBIDDEN.search(v)}


def _org_params():
    from ctshowcase.config import load_brand
    for owner in load_brand().raw['orgs']:
        marks = [pytest.mark.xfail(strict=True, reason='TicketStub still family: completetech; needs an owner-supplied palette and mark, see issue 40 task 43')]             if owner in KNOWN_MISMATCHES else []
        yield pytest.param(owner, id=owner, marks=marks)


@pytest.mark.parametrize('owner', list(_org_params()))
def test_rendered_output_has_no_completetech_outside_owned_rows(brand, tmp_path, owner):
    if _owned(brand.raw, owner):
        pytest.skip('CompleteTech-owned row: the family name and brand blue are correct here')
    assert rendered_leaks(brand, owner, tmp_path) == {}


def test_render_audit_catches_a_family_regression(brand, tmp_path):
    # Evidence the audit is not vacuous: point a non-CompleteTech row at the completetech family in an
    # in-memory copy (brand.yaml is untouched) and the same scan must report leaks on the card and tokens.
    from ctshowcase.config import Brand
    raw = copy.deepcopy(brand.raw)
    raw['orgs']['Pick-Your-AI']['family'] = 'completetech'
    leaks = rendered_leaks(Brand(raw, brand.path), 'Pick-Your-AI', tmp_path)
    assert {'card', 'banner style tokens'} <= set(leaks), leaks
