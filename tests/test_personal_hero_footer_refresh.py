"""Public CLI contract: personal upgrades migrate owned footers, preserve authored bytes."""
import re

import pytest
import yaml

from conftest import ROOT
from test_personal_hero_order import applicable_intro as applicable_intro
from test_personal_hero_order import (
    LEGACY_HERO, fixture_repo, generate, snapshot,
)


ENDINGS = [pytest.param(b"\n", id="LF"), pytest.param(b"\r\n", id="CRLF")]
FOOTER = re.compile(br"<!-- showcase:footer:start -->.*?<!-- showcase:footer:end -->", re.DOTALL)
HERO = re.compile(br"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.DOTALL)


def footer_block(ending, *, legacy=True, authored=False, partner=False):
    """Decision 18 markup, with URL facts read only from the public brand data."""
    brand = yaml.safe_load((ROOT / "references/brand.yaml").read_text(encoding="utf-8"))["footer"]
    light = brand["logo_light_url"]
    dark = brand["logo_dark_url"]
    if legacy:
        light, dark = brand["legacy_logo_urls"][:2]
    if partner:
        light = "https://example.test/partner-badge.png"
    lines = [
        '<!-- showcase:footer:start -->', '<p align="center">',
        f'  <a href="{brand["href"]}">', '    <picture>',
        f'      <source media="(prefers-color-scheme: dark)" srcset="{dark}">',
        f'      <img src="{light}" alt="{brand["alt"]}" width="200">',
        '    </picture>', '  </a>', '  <br>',
        '  Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration',
        '</p>', '<!-- showcase:footer:end -->',
    ]
    if authored:
        lines.insert(-2, '  <span>Authored  partner credit.  </span>')
    return ending.join(line.encode("utf-8") for line in lines)


def authored_opening(ending):
    return ending.join((
        b'<p align="center">', b'  <img src="assets/authored-art.svg" alt="Synthetic authored artwork">',
        b'</p>', b'', b'# Synthetic profile', b'', b'Authored  double spaces.  ',
        b'\tAn authored indented note.', b'', b'<!-- Authored comment. -->', b'', b'',
    ))


def assert_current_footer(updated):
    brand = yaml.safe_load((ROOT / "references/brand.yaml").read_text(encoding="utf-8"))["footer"]
    block, = FOOTER.finditer(updated)
    assert brand["logo_light_url"].encode() in block.group()
    assert brand["logo_dark_url"].encode() in block.group()
    assert all(url.encode() not in block.group() for url in brand["legacy_logo_urls"][:2])
    assert block.group().count(b'<picture>') == 1
    assert updated.count(b'Built by') == 1


@pytest.mark.parametrize("variant", ["J", "G", "H"])
@pytest.mark.parametrize("ending", ENDINGS)
def test_authored_opening_does_not_prevent_owned_legacy_footer_migration(tmp_path, variant, ending):
    authored = authored_opening(ending)
    source = authored + footer_block(ending) + ending
    meta = fixture_repo(tmp_path, source)
    result = generate(tmp_path, meta, "upgrade", variant, ())

    assert result.returncode == 0, result.stdout + result.stderr
    assert "readme-shrink" not in result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    assert updated.count(authored) == 1, "Every authored opening/body byte must survive together"
    assert b'assets/intro.svg' not in updated, "Authored artwork requires no generated intro"
    assert_current_footer(updated)
    if ending == b"\r\n":
        assert b"\n" not in updated.replace(b"\r\n", b""), "Preserve the source's CRLF convention"


@pytest.mark.parametrize("variant", ["J", "G", "H"])
@pytest.mark.parametrize("case,ending", [("authored-credit", b"\n"), ("partner-source", b"\r\n")])
def test_authored_or_partner_edited_footer_is_never_claimed(tmp_path, variant, case, ending):
    authored = authored_opening(ending)
    custom = footer_block(ending, authored=case == "authored-credit", partner=case == "partner-source")
    source = authored + custom + ending
    meta = fixture_repo(tmp_path, source)
    result = generate(tmp_path, meta, "upgrade", variant, ())

    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    assert updated == source, "An authored opening and edited footer must remain byte-identical"
    assert b'assets/intro.svg' not in updated


@pytest.mark.parametrize("ending", ENDINGS)
@pytest.mark.parametrize("has_intro", [False, True], ids=["missing-intro", "applicable-intro"])
def test_owned_hero_and_footer_refresh_together_without_losing_authored_art(
        tmp_path, applicable_intro, ending, has_intro):
    authored = authored_opening(ending)
    source = LEGACY_HERO.replace(b"\n", ending) + ending * 2 + authored + footer_block(ending) + ending
    meta = fixture_repo(tmp_path, source, applicable_intro if has_intro else None)
    before = snapshot(tmp_path)
    result = generate(tmp_path, meta, "upgrade", "J", ())

    if not has_intro:
        assert result.returncode == 4, result.stdout + result.stderr
        assert "needs-input:intro" in result.stdout
        assert snapshot(tmp_path) == before, "Missing intro must not partially migrate the footer or write outputs"
        return

    assert result.returncode == 0, result.stdout + result.stderr
    assert "readme-shrink" not in result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    assert updated.count(authored) == 1, "Simultaneous owned migrations must preserve authored artwork/body bytes"
    hero, = HERO.finditer(updated)
    assert b'src="assets/intro.svg"' in hero.group()
    assert b'docs/images/banner.png' not in updated
    assert_current_footer(updated)
