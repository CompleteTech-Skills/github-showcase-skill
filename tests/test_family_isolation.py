"""Audit that no non-CompleteTech org row resolves to the completetech family (E2.2.1, task 41).

Synthetic and public metadata only. Org keys are matched case-sensitively against brand.raw
directly; brand.org() is deliberately not used because it resolves aliases.
"""
from __future__ import annotations

# NOTE for reviewers: issue 40's proposed fix is "give each non-CompleteTech org its own family (or fail
# loudly)". TicketStub (Jevelopers-neatHack-2026) has no owner-supplied palette or mark, so inventing a family
# for it would fabricate brand data; it takes the "fail loudly" branch instead: Brand.identity_gap reports
# `org-family` for any known row filed under `completetech` whose display name is not a CompleteTech brand, and
# Brand.check_owner / Resolver.check_owner (every brand-rendering generator and planner gate, project boards
# included) refuse it with needs-input:org-family. content sidebar renders no brand text and passes identity=False. No test here is an expected failure: a mismatched row must REFUSE, and every other
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

# 1E3A8A is CompleteTech's badge accent and grid navy (art-direction.md, brand.yaml badges.accent and the completetech
# canvas): epic 35 review 4 found every non-CompleteTech language badge still painted it, uncaught by this pattern.
FORBIDDEN = re.compile(r'completetech|CompleteDotTech|005ADD|1E3A8A', re.I)
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
# 005ADD brand blue. Render the card (SVG and scene text), the banner (scene text) and its style tokens, the README
# scaffold and the README lint
# for EVERY org row and scan the text. This is an audit of existing data: it passes on the base because
# the base is already correct for every row except TicketStub (strict xfail below); it would fail on any
# regression, which test_render_audit_catches_a_family_regression demonstrates by mutation.
LEGIT_OWNED_NAMES = re.compile(r'completetech', re.I)


def _owned(raw: dict, owner: str) -> bool:
    """CompleteTech-owned rows may legitimately mention the family: display name, user account, demo owner."""
    return (owner not in family_mismatches(raw) and raw['orgs'][owner].get('family') == 'completetech')         or owner in LEGIT_COMPLETETECH_ROWS or owner == raw['brand_strings']['demo_owner']


def scene_text(scene, info: dict) -> str:
    """Every string a scene draws (Text nodes, Clip children included), its title and description, and the layout's
    text metadata (eyebrow, title, subtitle, chips): what the renderer outlines into paths."""
    from ctshowcase.scene import Clip, Text
    out = [scene.title, scene.desc]

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Text):
                out.append(n.text)
            elif isinstance(n, Clip):
                walk(n.children)
    walk(scene.nodes)
    out += [str(info.get(k) or '') for k in ('eyebrow', 'title_lines', 'subtitle', 'name_lines', 'desc_lines')]
    out += [c.get('text', '') for c in info.get('chips') or [] if isinstance(c, dict)]
    return ' | '.join(out)


def rendered_leaks(brand, owner: str, tmp_path: Path) -> dict[str, list[str]]:
    from conftest import EX, meta_dict
    from ctshowcase import banner, card, footer, readme, readmelint
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    from ctshowcase.typeset import Fonts
    shutil.copytree(EX / 'repos' / 'northwind-support-triage-agent', tmp_path, dirs_exist_ok=True)
    (tmp_path / 'docs/images').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'docs/images/banner.png').write_bytes(b'x')
    ctx = RepoContext(brand, normalize(meta_dict(owner=owner, description='Run the Northwind customer support email triage agent from the command line.')), tmp_path)
    fonts = Fonts(brand)
    svg, card_scene, card_info = card.render(ctx, fonts)
    # the card and banner draw their text as outlined SVG paths / PNG pixels, so the strings are scanned from the
    # scene before outlining (epic 35 review 3: a hardcoded CompleteTech eyebrow passed the path-only scan)
    banner_scene, banner_info = banner.layout(ctx, fonts)
    text = readme.scaffold(ctx, '')
    (tmp_path / 'README.md').write_text(text, encoding='utf-8')
    surfaces = {
        'card': svg.decode() if isinstance(svg, bytes) else svg,
        'card text': scene_text(card_scene, card_info),
        'banner text': scene_text(banner_scene, banner_info),
        'banner style tokens': json.dumps(painted_style(ctx.style), sort_keys=True),
        'family canvas': repr(banner.canvas_nodes(ctx.style, 1280, 640)),
        # decision 18: the footer is the one place the CompleteTech name is correct; strip only it (Type badges are
        # scanned: each non-CompleteTech family sets badge_brand, so no 005ADD badge is exempt)
        'readme scaffold': text.replace(footer.block(brand), ''),
        'readme lint': json.dumps(readmelint.lint(ctx, tmp_path / 'README.md')),
    }
    return {k: sorted({m.lower() for m in FORBIDDEN.findall(v)}) for k, v in surfaces.items() if FORBIDDEN.search(v)}


def painted_style(style: dict) -> dict:
    """ctx.style minus canvas keys no renderer reads for this family's canvas kind. Brand.family deep-merges each
    family over the completetech base, so a flat, flat-grid or halftone canvas inherits the gradient-grid keys
    (`overlay` #1E3A8A, and `grid` #1E3A8A where the family sets none). Only a gradient-grid canvas paints the
    overlay (banner.canvas_nodes, intro.py `if gradient`), and flat or halftone never draw a grid; the scan of the
    real canvas nodes ('family canvas' above) proves neither reaches a non-CompleteTech output."""
    reads = {'gradient-grid': None, 'flat': {'kind', 'color'},
             'flat-grid': {'kind', 'color', 'grid', 'grid_opacity', 'grid_pitch'},
             'halftone': {'kind', 'color', 'pitch', 'radius', 'dot', 'dot_opacity'}}
    style = copy.deepcopy(style)
    keep = reads.get(style.get('canvas', {}).get('kind'))
    if keep is not None:
        style['canvas'] = {k: v for k, v in style['canvas'].items() if k in keep}
    return style


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


def test_every_non_completetech_family_sets_its_own_badge_accent(brand):
    # epic 35 review 4: without badge_accent the language/runtime badge fell back to the global badges.accent 1E3A8A
    ct = {str(brand.raw['badges'][k]).upper() for k in ('accent', 'brand')}
    fams = {name: fam or {} for name, fam in brand.raw['families'].items() if name != 'completetech'}
    assert {n for n, f in fams.items() if not f.get('badge_accent')} == set()
    assert {n for n, f in fams.items() if str(f['badge_accent']).upper() in ct} == set()


def _white_text_contrast(hex6: str) -> float:
    def lin(x):
        x /= 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(hex6[i:i + 2], 16)) for i in (0, 2, 4))
    return 1.05 / (0.2126 * r + 0.7152 * g + 0.0722 * b + 0.05)


def test_family_badge_accents_are_contrast_checked(brand):
    # shields.io draws white text on the message side; every family accent clears 4.5:1
    low = {n: f['badge_accent'] for n, f in brand.raw['families'].items()
           if (f or {}).get('badge_accent') and _white_text_contrast(str(f['badge_accent'])) < 4.5}
    assert low == {}


@pytest.mark.parametrize('owner', ['LibreEvolve', 'AI-Ascension', 'TouchedByAnAgent', 'Jev-Engineering'])
def test_language_badge_uses_the_family_accent(brand, owner):
    # reviewer scenario (epic 35 review 4): a public Python MIT repo emitted language-Python-1E3A8A for each T2 family
    from conftest import meta_dict
    from ctshowcase import readme
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    ctx = RepoContext(brand, normalize(meta_dict(owner=owner, repo='thing', language='Python')), None, type_override='cli')
    urls = [u for _, u, _ in readme.badges(ctx)]
    lang = [u for u in urls if '/badge/language-' in u]
    assert lang and not any(FORBIDDEN.search(u) for u in urls), urls
    assert lang[0].endswith('-' + str(ctx.style['badge_accent']))


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


def test_render_audit_catches_a_hardcoded_completetech_label(brand, tmp_path, monkeypatch):
    # epic 35 review 3 (reviewer B, P2): with the shared eyebrow function returning `CompleteTech`, a LibreEvolve card
    # and banner carried that label but the audit returned {} (the card text is outlined paths, the banner was only
    # scanned as style tokens). The scene text surfaces catch it on both renderers.
    from ctshowcase import chips
    monkeypatch.setattr(chips, 'eyebrow_text', lambda ctx, category=None: 'CompleteTech')
    leaks = rendered_leaks(brand, 'LibreEvolve', tmp_path)
    assert {'card text', 'banner text'} <= set(leaks), leaks


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


# --- epic 35 review round 2: which planners take the identity gate ---------------------------------------------------
# content sidebar plans the Releases / Packages / Deployments checkboxes and renders no brand text, so it does not take
# the gate; a batch must still never abort on one owner (on the pre-fix HEAD a TicketStub row in a mixed batch turned
# the whole result into needs-input:org-family and the Northwind job was lost). Project boards (copy-plan, readme) DO
# take it: on the pre-fix HEAD `--allow-t3 project copy-plan --target Jevelopers-neatHack-2026` exited 0 with a
# create-project job.
CFIX = ROOT / 'tests' / 'fixtures' / 'content'
NO_ESTATE = ('--registry', CFIX / 'registry.min.yaml', '--approved', CFIX / 'approved.empty.txt', '--approved-yaml',
             CFIX / 'approved.empty.yaml', '--actions', CFIX / 'estate-actions.json')


def _strict_config(tmp_path):
    import yaml
    raw = yaml.safe_load((ROOT / 'references' / 'brand.yaml').read_text(encoding='utf-8'))
    raw['isolation'] = {'unknown_org': 'refuse'}
    cfg = tmp_path / 'brand.yaml'
    cfg.write_text(yaml.safe_dump(raw), encoding='utf-8')
    return cfg


def test_sidebar_mixed_batch_keeps_every_repo(tmp_path):
    from conftest import run_cli
    facts = tmp_path / 'facts.json'
    facts.write_text(json.dumps({
        'Northwind-Trading-Co/support-triage-agent': {'releases': [{'id': 1}], 'deployments': [], 'packages': 0,
                                                      'visibility': 'public'},
        'Jevelopers-neatHack-2026/tickets': {'releases': [{'id': 1}], 'deployments': [], 'packages': 0,
                                             'visibility': 'public'}}), encoding='utf-8')
    r = run_cli('--no-repo-dir', '--allow-t3', '--format', 'json', 'content', 'sidebar', '--facts', facts, *NO_ESTATE)
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out['result'] == 'proposal', (r.stdout, r.stderr)
    assert out['repos'] == 2 and not out['skipped'], out
    assert {j['repo'] for j in out['jobs']} >= {'Northwind-Trading-Co/support-triage-agent'}


def test_sidebar_batch_with_unknown_owner_under_refuse_config_skips_nothing_else(tmp_path):
    from conftest import run_cli
    facts = tmp_path / 'facts.json'
    facts.write_text(json.dumps({
        'Northwind-Trading-Co/support-triage-agent': {'releases': [{'id': 1}], 'deployments': [], 'packages': 0,
                                                      'visibility': 'public'},
        'Some-New-Org/thing': {'releases': [{'id': 1}], 'deployments': [], 'packages': 0,
                               'visibility': 'public'}}), encoding='utf-8')
    r = run_cli('--config', _strict_config(tmp_path), '--no-repo-dir', '--format', 'json', 'content', 'sidebar',
                '--facts', facts, *NO_ESTATE)
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out['result'] == 'proposal', (r.stdout, r.stderr)
    assert 'Northwind-Trading-Co/support-triage-agent' in {j['repo'] for j in out['jobs']}


def test_sidebar_batch_skips_a_gated_owner_instead_of_aborting(tmp_path, monkeypatch, capsys):
    """Defence in depth: if any owner gate raises NeedsInput inside the batch, only that repository is skipped."""
    from ctshowcase import content as C
    from ctshowcase.errors import NeedsInput
    from ctshowcase.resolver import Resolver
    real = Resolver.check_owner

    def gate(self, login, **kw):
        if login == 'Jevelopers-neatHack-2026':
            raise NeedsInput('org-family')
        return real(self, login, **kw)
    monkeypatch.setattr(Resolver, 'check_owner', gate)
    facts = tmp_path / 'facts.json'
    facts.write_text(json.dumps({
        'Northwind-Trading-Co/support-triage-agent': {'releases': [{'id': 1}], 'deployments': [], 'packages': 0,
                                                      'visibility': 'public'},
        'Jevelopers-neatHack-2026/tickets': {'releases': [], 'deployments': [], 'packages': 0}}), encoding='utf-8')
    code = C.main(list(map(str, ('--no-repo-dir', 'content', 'sidebar', '--facts', facts, *NO_ESTATE))))
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out['result'] == 'proposal', out
    assert out['skipped'] == [{'repo': 'Jevelopers-neatHack-2026/tickets', 'why': 'needs-input:org-family'}]


def test_project_copy_plan_refuses_ticketstub(tmp_path):
    from conftest import run_cli
    r = run_cli('--allow-t3', '--format', 'json', 'project', 'copy-plan', '--target', 'Jevelopers-neatHack-2026',
                *NO_ESTATE)
    assert r.returncode == 4 and 'needs-input:org-family' in r.stdout + r.stderr, (r.stdout, r.stderr)
    assert '"create-project"' not in r.stdout


def test_project_copy_plan_refuses_unknown_owner_under_refuse_config(tmp_path):
    from conftest import run_cli
    r = run_cli('--config', _strict_config(tmp_path), '--format', 'json', 'project', 'copy-plan', '--target',
                'Some-New-Org', '--display-name', 'Some New Org', *NO_ESTATE)
    assert r.returncode == 4 and 'needs-input:org-row' in r.stdout + r.stderr, (r.stdout, r.stderr)
    # the default config keeps the historical behaviour (behaviour-changing defaults stay off)
    ok = run_cli('--format', 'json', 'project', 'copy-plan', '--target', 'Some-New-Org', '--display-name',
                 'Some New Org', *NO_ESTATE)
    assert ok.returncode == 0, (ok.stdout, ok.stderr)


def test_project_copy_plan_gate_order(brand):
    """The T3 approval gate still answers first (Refused); with --allow-t3 the identity gate answers (NeedsInput)."""
    from ctshowcase import project as PJ
    from ctshowcase.errors import NeedsInput, Refused
    from ctshowcase.resolver import Resolver
    with pytest.raises(Refused):
        PJ.copy_plan('Jevelopers-neatHack-2026', resolver=Resolver(brand))
    with pytest.raises(NeedsInput) as e:
        PJ.copy_plan('Jevelopers-neatHack-2026', resolver=Resolver(brand), allow_t3=True)
    assert e.value.detail == 'org-family'
    assert PJ.copy_plan('Northwind-Trading-Co', resolver=Resolver(brand))['jobs']  # an owned identity still plans


def test_project_readme_refuses_ticketstub(tmp_path):
    from conftest import run_cli
    cap = ROOT / 'tests' / 'fixtures' / 'project' / 'copy-capture.json'
    r = run_cli('--allow-t3', '--format', 'json', 'project', 'readme', '--capture', cap, '--owner',
                'Jevelopers-neatHack-2026', '--display-name', 'TicketStub', *NO_ESTATE)
    assert r.returncode == 4 and 'needs-input:org-family' in r.stdout + r.stderr, (r.stdout, r.stderr)


def test_org_reports_answer_for_a_gated_owner_and_generators_still_refuse(tmp_path):
    # epic 35 review 3 (reviewer A, P2): `org health` and `org doctor` are read-only reports and `org labels` renders
    # no brand text, so org._gate passes identity=False for them (as per-repo doctor does); they returned
    # needs-input:org-family for TicketStub before this change. profile, about and pins render brand text and keep it.
    from conftest import run_cli
    empty = tmp_path / 'dot-github'
    empty.mkdir()
    r = run_cli('--format', 'json', 'org', 'health', 'Jevelopers-neatHack-2026', '--allow-t3', '--dot-github', empty)
    out = json.loads(r.stdout)
    assert 'needs-input:org-family' not in out.get('logs', []) and out.get('cells'), out
    snap = tmp_path / 'snap.json'
    snap.write_text('{}', encoding='utf-8')
    r = run_cli('--format', 'json', 'org', 'doctor', 'Jevelopers-neatHack-2026', '--allow-t3', '--snapshot', snap)
    out = json.loads(r.stdout)
    assert out.get('action') == 'doctor' and out.get('cells'), out
    for action in ('profile', 'about', 'pins'):
        r = run_cli('--format', 'json', 'org', action, 'Jevelopers-neatHack-2026', '--allow-t3', *NO_ESTATE)
        assert r.returncode == 4 and 'needs-input:org-family' in r.stdout, (action, r.stdout, r.stderr)

