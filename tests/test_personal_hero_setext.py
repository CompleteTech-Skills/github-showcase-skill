"""Offline CLI regressions for Setext headings at personal hero boundaries."""
import json

import pytest

from conftest import run_cli
from test_personal_hero_inline_seams import (
    BLOCK,
    ENDINGS,
    assert_atomic_refusal,
    fixture_repo,
    snapshot,
)
from test_personal_hero_order import LEGACY_HERO, applicable_intro as applicable_intro, generate


CALLOUT = b"> [!NOTE]\n> Synthetic callout.\n\n"
AUTHORED_BODY = b"Authored  body.  \n\n\tLiteral note.\n\n"


def authored_prefix(ending, section=b"Notes\n-----"):
    return (CALLOUT + b"# Profile\n\n" + section + b"\n\n" + AUTHORED_BODY).replace(b"\n", ending)


def lint_failures(directory, meta, variant):
    result = run_cli("--meta", meta, "--repo-dir", directory,
                     "lint", "readme", directory / "README.md", "--variant", variant)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    return json.loads(result.stdout)["fails"]


def assert_intro_opening(directory, prefix):
    updated = (directory / "README.md").read_bytes()
    blocks = list(BLOCK.finditer(updated))
    assert len(blocks) == 1, updated
    hero = blocks[0]
    assert hero.start() == 0, "The managed intro must move before the authored body"
    assert b'src="assets/intro.svg"' in hero.group(), updated
    assert b"docs/images/banner.png" not in updated
    assert prefix in updated[hero.end():], "Every authored byte must survive the move"
    assert updated.count(prefix) == 1, "Moving the hero must not duplicate the authored body"
    return updated, hero


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("ending", ENDINGS)
def test_setext_body_heading_refuses_header_refresh_atomically(tmp_path, applicable_intro, variant, ending):
    prefix = authored_prefix(ending)
    source = prefix + LEGACY_HERO.replace(b"\n", ending)
    meta = fixture_repo(tmp_path, source, applicable_intro)
    before = snapshot(tmp_path)

    result = generate(tmp_path, meta, "header", variant, ())

    assert_atomic_refusal(result, tmp_path, before, "needs-input:intro-order")


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("ending", ENDINGS)
def test_setext_body_heading_moves_intro_before_authored_body(tmp_path, applicable_intro, variant, ending):
    prefix = authored_prefix(ending)
    source = prefix + LEGACY_HERO.replace(b"\n", ending)
    meta = fixture_repo(tmp_path, source, applicable_intro)

    result = generate(tmp_path, meta, "upgrade", variant, ())

    assert result.returncode == 0, result.stdout + result.stderr
    assert_intro_opening(tmp_path, prefix)
    assert not [failure for failure in lint_failures(tmp_path, meta, variant) if failure.startswith("D13 ")]


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("ending", ENDINGS)
def test_setext_body_heading_makes_late_intro_fail_d13(tmp_path, applicable_intro, variant, ending):
    prefix = authored_prefix(ending)
    # Start from an opening hero, so this lint regression does not rely on the
    # separate full-upgrade relocation bug being fixed first.
    source = LEGACY_HERO.replace(b"\n", ending) + ending * 2 + prefix
    meta = fixture_repo(tmp_path, source, applicable_intro)
    result = generate(tmp_path, meta, "upgrade", variant, ())
    assert result.returncode == 0, result.stdout + result.stderr
    updated, hero = assert_intro_opening(tmp_path, prefix)
    assert not [failure for failure in lint_failures(tmp_path, meta, variant) if failure.startswith("D13 ")]

    footer = updated.index(b"<!-- showcase:footer:start -->", hero.end())
    body = updated[hero.end():footer].lstrip(b"\r\n")
    late = body + hero.group() + ending * 2 + updated[footer:]
    (tmp_path / "README.md").write_bytes(late)

    failures = lint_failures(tmp_path, meta, variant)
    assert any(failure.startswith("D13 ") for failure in failures), failures


@pytest.mark.parametrize("variant", ["G", "H"])
def test_atx_body_heading_control_refuses_moves_and_lints(tmp_path, applicable_intro, variant):
    prefix = authored_prefix(b"\r\n", b"## Notes")
    meta = fixture_repo(tmp_path, prefix + LEGACY_HERO, applicable_intro)
    before = snapshot(tmp_path)
    header = generate(tmp_path, meta, "header", variant, ())
    assert_atomic_refusal(header, tmp_path, before, "needs-input:intro-order")

    upgrade = generate(tmp_path, meta, "upgrade", variant, ())
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    updated, hero = assert_intro_opening(tmp_path, prefix)
    assert not [failure for failure in lint_failures(tmp_path, meta, variant) if failure.startswith("D13 ")]
    footer = updated.index(b"<!-- showcase:footer:start -->", hero.end())
    late = updated[hero.end():footer].lstrip(b"\r\n") + hero.group() + b"\r\n\r\n" + updated[footer:]
    (tmp_path / "README.md").write_bytes(late)
    assert any(failure.startswith("D13 ") for failure in lint_failures(tmp_path, meta, variant))


@pytest.mark.parametrize("variant,ending", [("G", b"\n"), ("H", b"\r\n")], ids=["G-LF", "H-CRLF"])
def test_initial_setext_h1_allows_in_place_header_refresh(tmp_path, applicable_intro, variant, ending):
    prefix = (CALLOUT + b"Profile\n=====\n\n").replace(b"\n", ending)
    suffix = (b"\n\n" + AUTHORED_BODY).replace(b"\n", ending)
    meta = fixture_repo(tmp_path, prefix + LEGACY_HERO.replace(b"\n", ending) + suffix, applicable_intro)

    result = generate(tmp_path, meta, "header", variant, ())

    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    blocks = list(BLOCK.finditer(updated))
    assert len(blocks) == 1, updated
    hero = blocks[0]
    assert b'src="assets/intro.svg"' in hero.group(), updated
    assert updated[:hero.start()] == prefix
    assert updated[hero.end():] == suffix
    assert not [failure for failure in lint_failures(tmp_path, meta, variant) if failure.startswith("D13 ")]


@pytest.mark.parametrize("section", [
    pytest.param(b"```markdown\nNotes\n-----\n```", id="fenced-code"),
    pytest.param(b"<pre>\nNotes\n-----\n</pre>", id="raw-HTML"),
    pytest.param(b"-----", id="thematic-break"),
])
def test_literal_setext_and_thematic_break_allow_in_place_refresh(tmp_path, applicable_intro, section):
    prefix = authored_prefix(b"\n", section)
    suffix = b"\n\nAuthored  suffix.  \r\n"
    meta = fixture_repo(tmp_path, prefix + LEGACY_HERO + suffix, applicable_intro)

    result = generate(tmp_path, meta, "header", "G", ())

    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    blocks = list(BLOCK.finditer(updated))
    assert len(blocks) == 1, updated
    hero = blocks[0]
    assert b'src="assets/intro.svg"' in hero.group(), updated
    assert updated[:hero.start()] == prefix and updated[hero.end():] == suffix
    assert not [failure for failure in lint_failures(tmp_path, meta, "G") if failure.startswith("D13 ")]
