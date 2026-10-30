"""Audit that no non-CompleteTech org row resolves to the completetech family (E2.2.1, task 41).

Synthetic and public metadata only. Org keys are matched case-sensitively against brand.raw
directly; brand.org() is deliberately not used because it resolves aliases.
"""
from __future__ import annotations

# NOTE for reviewers: issue 40's proposed fix is "give each non-CompleteTech org its own family (or fail
# loudly)". TicketStub (Jevelopers-neatHack-2026) has no owner-supplied palette or mark, so inventing a family
# for it would fabricate brand data; it takes the "fail loudly" branch instead: Brand.identity_gap reports
# `org-family` for any known row filed under `completetech` whose display name is not a CompleteTech brand, and
# Brand.check_owner / Resolver.check_owner (every generator and planner gate) refuse it with
# needs-input:org-family. No test here is an expected failure: a mismatched row must REFUSE, and every other
# row must render without CompleteTech text, Type badges included (each family now carries badge_brand).
# On the epic base the refusal tests below fail (the card renders with exit 0 and 005ADD) and the Type badge
# scan fails for LibreEvolve (type-...-005ADD); both pass with this change.

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
KNOWN_MISMATCHES = {'Jevelopers-neatHack-2026'}  # TicketStub: refused (needs-input:org-family) until it has its own family (task 43)


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


def test_code_and_audit_agree_on_rows_without_an_identity(brand):
    # Brand.identity_gap (the gate) and family_mismatches (this audit) must name exactly the same rows
    gaps = {o for o in brand.raw['orgs'] if brand.identity_gap(o) == 'org-family'}
    assert gaps == family_mismatches(brand.raw)


@pytest.fixture
def t3_signed_off():
    from ctshowcase.config import set_t3_signed_off
    set_t3_signed_off(True)
    yield
    set_t3_signed_off(False)


def test_every_non_completetech_row_under_completetech_refuses(brand, t3_signed_off):
    # issue 40 criterion 1, "fail loudly" branch: even with T3 sign-off, no gate lets such a row reach a renderer
    from ctshowcase.errors import NeedsInput
    assert family_mismatches(brand.raw)  # not vacuous while TicketStub has no family
    for owner in family_mismatches(brand.raw):
        with pytest.raises(NeedsInput) as e:
            brand.check_owner(owner)
        assert e.value.detail == 'org-family'
        with pytest.raises(NeedsInput):
            brand.resolver().check_owner(owner)
        # read-only verdicts (doctor, footer, meta capture) render nothing and stay available
        assert brand.check_owner(owner, identity=False) == 't3'


def test_identity_rule_by_mutation(brand):
    # a synthetic row (in-memory copy of the demo owner's row) shows which data lifts the refusal
    from ctshowcase.config import Brand
    raw = copy.deepcopy(brand.raw)
    demo = raw['brand_strings']['demo_owner']
    raw['orgs']['Synthetic-Other'] = dict(raw['orgs'][demo], display_name='Synthetic Other')
    raw['orgs']['Synthetic-Bare'] = {k: v for k, v in raw['orgs']['Synthetic-Other'].items() if k != 'license_wording'}
    raw['orgs']['Synthetic-Own'] = dict(raw['orgs']['Synthetic-Bare'], family='libreevolve')
    b = Brand(raw, brand.path)
    assert b.identity_gap('Synthetic-Other') is None       # CompleteTech LLC is its approved rights holder
    assert b.identity_gap('Synthetic-Bare') == 'org-family'  # TicketStub's shape: refused
    assert b.identity_gap('Synthetic-Own') is None           # its own family lifts the refusal


def test_ticketstub_card_cli_refuses_with_needs_input(tmp_path):
    # the reviewer's failing scenario: `--allow-t3 --type cli card` for synthetic TicketStub metadata exited 0 with
    # the completetech family, COMPLETETECH LLC label, mark-light.png and 005ADD. It must refuse and write nothing.
    from conftest import meta_dict, run_cli
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps(meta_dict(owner='Jevelopers-neatHack-2026', repo='synthetic-tickets')), encoding='utf-8')
    out = tmp_path / 'card.svg'
    r = run_cli('--meta', meta, '--no-repo-dir', '--allow-t3', '--type', 'cli', '--format', 'json', 'card',
                '--out', out, '--allow-unmeasured')
    assert r.returncode == 4, (r.stdout, r.stderr)
    assert 'needs-input:org-family' in r.stdout + r.stderr
    assert not out.exists()


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
        # decision 18: the footer is the one place the CompleteTech name is correct; strip only it (Type badges are
        # scanned: each non-CompleteTech family sets badge_brand, so no 005ADD badge is exempt)
        'readme scaffold': text.replace(footer.block(brand), ''),
        'readme lint': json.dumps(readmelint.lint(ctx, tmp_path / 'README.md')),
    }
    return {k: sorted({m.lower() for m in FORBIDDEN.findall(v)}) for k, v in surfaces.items() if FORBIDDEN.search(v)}


def _org_params():
    from ctshowcase.config import load_brand
    for owner in load_brand().raw['orgs']:
        yield pytest.param(owner, id=owner)


@pytest.mark.parametrize('owner', list(_org_params()))
def test_rendered_output_has_no_completetech_outside_owned_rows(brand, tmp_path, owner):
    if _owned(brand.raw, owner):
        pytest.skip('CompleteTech-owned row: the family name and brand blue are correct here')
    if owner in family_mismatches(brand.raw):
        # no family of its own: the gate refuses before any renderer runs (asserted, not skipped)
        from ctshowcase.errors import NeedsInput
        with pytest.raises(NeedsInput):
            brand.check_owner(owner, allow_t3=True)
        return
    assert rendered_leaks(brand, owner, tmp_path) == {}


def test_type_badge_is_scanned_and_uses_the_family_colour(brand):
    # reviewer scenario: a public LibreEvolve CLI README emitted type-CLI%20tool-005ADD and the audit stripped it
    from conftest import meta_dict
    from ctshowcase import readme
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    ctx = RepoContext(brand, normalize(meta_dict(owner='LibreEvolve', repo='thing')), None, type_override='cli')
    urls = [u for _, u, _ in readme.badges(ctx)]
    type_badge = [u for u in urls if '/badge/type-' in u]
    assert type_badge and not any('005ADD' in u.upper() for u in urls), urls
    assert type_badge[0].endswith('-' + brand.raw['families']['libreevolve']['badge_brand'])


def test_every_non_completetech_family_sets_its_own_badge_colour(brand):
    missing = {name for name, fam in brand.raw['families'].items()
               if name != 'completetech' and not (fam or {}).get('badge_brand')}
    assert missing == set()


# -- Unknown owners (no brand.yaml row) ---------------------------------------------------------------
# Brand.org() falls back to the completetech family for an owner with no row. Refusing that by default would change
# behaviour issue 40 did not ask for (an unlisted owner is most often a new CompleteTech org), so the default stays
# and is LOUD (needs-input:org-row on every context); brand.yaml `isolation.unknown_org: refuse` closes the path.

def test_unknown_owner_default_is_flagged_not_silent(brand):
    from conftest import meta_dict
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    assert (brand.raw.get('isolation') or {}).get('unknown_org', 'completetech') == 'completetech'
    ctx = RepoContext(brand, normalize(meta_dict(owner='Some-New-Org', repo='thing')), None)
    assert 'needs-input:org-row' in ctx.logs
    assert brand.identity_gap('Some-New-Org') is None  # default: the historical fallback still renders


def test_unknown_owner_refuses_when_isolation_is_refuse(brand):
    from ctshowcase.config import Brand
    from ctshowcase.errors import NeedsInput
    raw = copy.deepcopy(brand.raw)
    raw['isolation'] = {'unknown_org': 'refuse'}
    strict = Brand(raw, brand.path)
    with pytest.raises(NeedsInput) as e:
        strict.check_owner('Some-New-Org')
    assert e.value.detail == 'org-row'
    for owner in raw['orgs']:  # known rows are unaffected by the key
        assert strict.identity_gap(owner) == brand.identity_gap(owner)


def test_unknown_owner_cli_refuses_under_refuse_config(tmp_path):
    import yaml
    from conftest import meta_dict, run_cli
    raw = yaml.safe_load((ROOT / 'references' / 'brand.yaml').read_text(encoding='utf-8'))
    raw['isolation'] = {'unknown_org': 'refuse'}
    cfg = tmp_path / 'brand.yaml'
    cfg.write_text(yaml.safe_dump(raw), encoding='utf-8')
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps(meta_dict(owner='Some-New-Org', repo='thing')), encoding='utf-8')
    out = tmp_path / 'card.svg'
    r = run_cli('--config', cfg, '--meta', meta, '--no-repo-dir', '--format', 'json', 'card', '--out', out)
    assert r.returncode == 4 and 'needs-input:org-row' in r.stdout + r.stderr, (r.stdout, r.stderr)
    assert not out.exists()


def test_render_audit_catches_a_family_regression(brand, tmp_path):
    # Evidence the audit is not vacuous: point a non-CompleteTech row at the completetech family in an
    # in-memory copy (brand.yaml is untouched) and the same scan must report leaks on the card and tokens.
    from ctshowcase.config import Brand
    raw = copy.deepcopy(brand.raw)
    raw['orgs']['Pick-Your-AI']['family'] = 'completetech'
    leaks = rendered_leaks(Brand(raw, brand.path), 'Pick-Your-AI', tmp_path)
    assert {'card', 'banner style tokens'} <= set(leaks), leaks


def test_data_audit_catches_a_family_regression(brand):
    # Mutation evidence for the data audit: a non-CompleteTech row moved to the completetech family in
    # an in-memory copy must be reported, so the audit is not vacuous even though it passes on base.
    raw = copy.deepcopy(brand.raw)
    raw['orgs']['Pick-Your-AI']['family'] = 'completetech'
    assert 'Pick-Your-AI' in family_mismatches(raw)


# -- Epic #35 integration: issue 36's license_wording under issue 40's audit -----------------------------
# Issue 36 added a per-org brand string (license_wording) that is written into README License rows. It is a
# new place CompleteTech text could reach another org, so the issue 40 audit must cover it in data and render.

def test_license_wording_mentions_completetech_only_on_owned_rows(brand):
    leaks = {owner for owner, row in brand.raw['orgs'].items()
             if FORBIDDEN.search(str(row.get('license_wording') or '')) and not _owned(brand.raw, owner)}
    assert leaks == set()


def test_render_audit_catches_a_completetech_license_wording(brand, tmp_path):
    # Mutation evidence (in-memory copy; brand.yaml untouched): give a non-CompleteTech row the CompleteTech
    # holder and the README scaffold scan must report it. On base 2be04ac (before issue 36) no rights
    # sentence reads license_wording, so this assertion fails there and passes once issue 36 is merged.
    from ctshowcase.config import Brand
    raw = copy.deepcopy(brand.raw)
    raw['orgs']['Pick-Your-AI']['license_wording'] = 'CompleteTech LLC'
    leaks = rendered_leaks(Brand(raw, brand.path), 'Pick-Your-AI', tmp_path)
    assert 'readme scaffold' in leaks, leaks
