"""Offline CLI regressions for an owned personal hero beside authored artwork."""
import pytest

from test_personal_hero_inline_seams import (
    BLOCK,
    assert_atomic_refusal,
    fixture_repo,
    snapshot,
)
from test_personal_hero_order import LEGACY_HERO, applicable_intro as applicable_intro, generate


ENDINGS = [pytest.param(b'\n', id='LF'), pytest.param(b'\r\n', id='CRLF')]
VARIANTS = ['J', 'G', 'H']
AUTHORED_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"/>\n'


def source_parts(ending, *, authored=False):
    hero = LEGACY_HERO.replace(b'\n', ending)
    if authored:
        # One deliberate edit makes this body authored, despite its familiar path.
        hero = hero.replace(b'width="100%"', b'width="840"')
    suffix = (
        b'\n\n> [!NOTE]\n> Synthetic  callout.  \n\n# Synthetic profile\n\n'
        b'<img src="custom.svg" alt="Authored artwork" width="840">  \n\n'
        b'Authored  prose keeps double spaces.  \n\tLiteral note.\n\n'
    ).replace(b'\n', ending)
    return hero, suffix


def prepare(directory, source, intro):
    meta = fixture_repo(directory, source, intro)
    (directory / 'custom.svg').write_bytes(AUTHORED_SVG)
    return meta


def assert_migrated(directory, suffix, result):
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'readme-shrink' not in result.stdout and 'exempt' not in result.stdout
    updated = (directory / 'README.md').read_bytes()
    blocks = list(BLOCK.finditer(updated))
    assert len(blocks) == 1, updated
    hero = blocks[0]
    assert hero.start() == 0, 'The owned opening hero must refresh in place'
    assert b'src="assets/intro.svg"' in hero.group()
    assert b'docs/images/banner.png' not in updated
    assert updated[hero.end():].startswith(suffix), 'Authored suffix bytes must stay attached'
    assert updated.count(suffix) == 1, 'Authored artwork and prose must not be duplicated'


@pytest.mark.parametrize('variant', VARIANTS)
@pytest.mark.parametrize('ending', ENDINGS)
@pytest.mark.parametrize('has_intro', [False, True], ids=['missing-intro', 'applicable-intro'])
def test_upgrade_refreshes_owned_hero_beside_authored_art(
        tmp_path, applicable_intro, variant, ending, has_intro):
    hero, suffix = source_parts(ending)
    meta = prepare(tmp_path, hero + suffix, applicable_intro if has_intro else None)
    before = snapshot(tmp_path)
    result = generate(tmp_path, meta, 'upgrade', variant, ())
    if not has_intro:
        assert_atomic_refusal(result, tmp_path, before, 'needs-input:intro')
        return
    assert_migrated(tmp_path, suffix, result)
    assert (tmp_path / 'custom.svg').read_bytes() == AUTHORED_SVG


@pytest.mark.parametrize('ending', ENDINGS)
def test_header_control_refreshes_the_same_owned_hero(tmp_path, applicable_intro, ending):
    hero, suffix = source_parts(ending)
    meta = prepare(tmp_path, hero + suffix, applicable_intro)
    result = generate(tmp_path, meta, 'header', 'J', ())
    assert_migrated(tmp_path, suffix, result)


@pytest.mark.parametrize('variant', VARIANTS)
@pytest.mark.parametrize('ending', ENDINGS)
@pytest.mark.parametrize('has_intro', [False, True], ids=['missing-intro', 'applicable-intro'])
def test_modified_marked_hero_stays_authored(
        tmp_path, applicable_intro, variant, ending, has_intro):
    hero, suffix = source_parts(ending, authored=True)
    source = hero + suffix
    meta = prepare(tmp_path, source, applicable_intro if has_intro else None)
    result = generate(tmp_path, meta, 'upgrade', variant, ())
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / 'README.md').read_bytes()
    assert updated.startswith(source), 'An edited hero cannot authorize dropping authored bytes'
    assert updated.count(hero) == 1 and updated.count(suffix) == 1
    assert b'assets/intro.svg' not in updated, 'Available intro does not confer ownership'
    assert (tmp_path / 'custom.svg').read_bytes() == AUTHORED_SVG


@pytest.mark.parametrize('ending', ENDINGS)
@pytest.mark.parametrize('has_intro', [False, True], ids=['missing-intro', 'applicable-intro'])
def test_owned_hero_migration_keeps_inline_authored_badge_segment(
        tmp_path, applicable_intro, ending, has_intro):
    suffix = (
        b'\n\n# Profile\n\nAuthored  prefix.  <!-- showcase:badges:start -->\n'
        b'![Build](https://img.shields.io/badge/build-passing-green)\n'
        b'<!-- showcase:badges:end -->  Authored  suffix.  \n\nAuthored  prose.\t\n'
    ).replace(b'\n', ending)
    source = LEGACY_HERO.replace(b'\n', ending) + suffix
    meta = fixture_repo(tmp_path, source, applicable_intro if has_intro else None)
    before = snapshot(tmp_path)
    result = generate(tmp_path, meta, 'upgrade', 'J', ())
    if not has_intro:
        assert_atomic_refusal(result, tmp_path, before, 'needs-input:intro')
        return
    assert_migrated(tmp_path, suffix, result)
