"""Offline CLI acceptance: moving a hero cannot rewrite its source context (#159)."""
import json
import re

import pytest

from conftest import ROOT, run_cli
from test_personal_hero_badge_urls import generated as generated
from test_personal_hero_order import fixture_repo, snapshot
from test_personal_hero_url_authority import offline_cli as offline_cli


BOM = b"\xef\xbb\xbf"
LINK = b'<a href="GUIDE.md">Authored documentation</a>'
BLOCK = re.compile(br"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.S)
NAV_BLOCK = b"<!-- showcase:nav:start -->\nOld navigation\n<!-- showcase:nav:end -->"
NAV = re.compile(br"<!-- showcase:nav:start -->.*?<!-- showcase:nav:end -->", re.S)
CONTENT = ROOT / "tests/fixtures/content"
CONTENT_FLAGS = ("--registry", CONTENT / "registry.min.yaml",
                 "--approved", CONTENT / "approved.empty.txt",
                 "--approved-yaml", CONTENT / "approved.empty.yaml",
                 "--actions", CONTENT / "estate-actions.json")
SEAMS = [
    pytest.param(b"  ", b"  ", id="two-plus-two-spaces"),
    pytest.param(b"   ", b" ", id="three-plus-one-spaces"),
    pytest.param(b"", b"    ", id="zero-plus-four-spaces"),
    pytest.param(BOM, b"    ", id="encoding-BOM-plus-four-spaces"),
    pytest.param(BOM * 2 + b"  ", b"  ", id="authored-extra-BOM-plus-spaces"),
    pytest.param(b"", b"", id="plain-control"),
]


def checkout(directory, source, intro=None):
    meta = fixture_repo(directory, source, intro)
    (directory / "GUIDE.md").write_bytes(b"# Synthetic guide\r\n")
    (directory / "LICENSE").write_bytes(b"Synthetic MIT license fixture.\n")
    capture = json.loads(meta.read_text(encoding="utf-8"))
    capture.update(files=["README.md", "GUIDE.md", "LICENSE", "art.svg"], files_complete=True)
    meta.write_text(json.dumps(capture), encoding="utf-8")
    (directory / "art.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>\n')
    return meta


def readme(directory, meta, mode):
    return run_cli("--format", "json", "--meta", meta, "--repo-dir", directory,
                   "readme", "--mode", mode, "--variant", "J", "--badges", "local",
                   "--records", directory / "records.jsonl", "--write")


def visible_guide(directory, meta):
    result = run_cli("--meta", meta, "--repo-dir", directory,
                     "content", "links", "README.md", *CONTENT_FLAGS)
    assert result.returncode == 0, result.stdout + result.stderr
    return [row for row in json.loads(result.stdout)["findings"] if row["target"] == "GUIDE.md"]


def refusal(result, directory, before, code):
    assert result.returncode == 4, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["result"] == "needs-input" and code in report["logs"], report
    assert snapshot(directory) == before, "Refusal must change or create no checkout files"


def parts(generated, prefix, indentation):
    # The hero itself is generated through the CLI by the imported fixture. Only
    # authored bytes deliberately mix endings; lone CR is significant too.
    hero = generated["legacy_hero"].replace("\n", "\r\n").encode("utf-8")
    suffix = indentation + LINK + b"  \r\n\r\nAuthored  notes.\t\n\nLast authored line.\r"
    return prefix, hero, suffix


def assert_success(directory, meta, mode, prefix, suffix, before_links):
    updated = (directory / "README.md").read_bytes()
    blocks = list(BLOCK.finditer(updated))
    after_links = visible_guide(directory, meta)
    before_retry = snapshot(directory)
    retry = readme(directory, meta, mode)
    problems = []
    if len(blocks) != 1:
        problems.append("expected exactly one managed hero")
    elif updated[:blocks[0].start()] != prefix:
        problems.append("complete authored prefix changed or moved")
    if updated.count(suffix) != 1:
        problems.append("complete authored suffix bytes changed or duplicated")
    if updated.count(BOM) != prefix.count(BOM):
        problems.append("encoding/authored BOM count changed")
    if updated.count(b'src="assets/intro.svg"') != 1 or b"docs/images/banner.png" in updated:
        problems.append("expected exactly one applicable intro and no legacy banner")
    if len(after_links) != 1 or after_links[0]["status"] != "ok":
        problems.append("authored GUIDE.md HTML link lost visibility")
    if retry.returncode != 0 or snapshot(directory) != before_retry:
        problems.append("successful retry changed the complete checkout snapshot")
    assert not problems, json.dumps({"problems": problems, "before_links": before_links,
                                    "after_links": after_links, "retry_exit": retry.returncode,
                                    "expected_prefix_hex": prefix.hex(),
                                    "actual_prefix_hex": updated[:blocks[0].start()].hex() if blocks else None}, indent=2)


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("prefix,indentation", SEAMS)
def test_owned_hero_move_preserves_authored_bytes_and_link_visibility(
        tmp_path, generated, mode, prefix, indentation):
    prefix, hero, suffix = parts(generated, prefix, indentation)
    meta = checkout(tmp_path, prefix + hero + suffix, generated["intro"])
    before_links = visible_guide(tmp_path, meta)
    assert len(before_links) == 1 and before_links[0]["status"] == "ok", before_links
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode)

    if result.returncode == 4 and (prefix or indentation):
        refusal(result, tmp_path, before, "needs-input:intro-order")
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert_success(tmp_path, meta, mode, prefix, suffix, before_links)


@pytest.mark.parametrize("prefix,indentation", SEAMS)
def test_header_only_control_preserves_original_context(tmp_path, generated, prefix, indentation):
    prefix, hero, suffix = parts(generated, prefix, indentation)
    meta = checkout(tmp_path, prefix + hero + suffix, generated["intro"])
    before_links = visible_guide(tmp_path, meta)
    assert len(before_links) == 1 and before_links[0]["status"] == "ok", before_links

    result = readme(tmp_path, meta, "header")

    assert result.returncode == 0, result.stdout + result.stderr
    assert_success(tmp_path, meta, "header", prefix, suffix, before_links)
    block, = BLOCK.finditer((tmp_path / "README.md").read_bytes())
    assert (tmp_path / "README.md").read_bytes()[block.end():] == suffix


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("prefix,indentation", SEAMS)
def test_owned_hero_missing_intro_refuses_atomically(tmp_path, generated, mode, prefix, indentation):
    prefix, hero, suffix = parts(generated, prefix, indentation)
    meta = checkout(tmp_path, prefix + hero + suffix)
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode)

    refusal(result, tmp_path, before, "needs-input:intro")


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("kind", ["raw-HTML-markdown", "comment", "fenced-code", "managed-image"])
def test_art_classification_requires_original_visible_context(tmp_path, generated, mode, kind):
    if kind == "raw-HTML-markdown":
        # Removing a navigation marker must not make raw HTML's literal Markdown
        # into a rendered image that the original source never displayed.
        source = b"<div>\n" + NAV_BLOCK + b"\n![Cover](art.svg)\n</div>\n\n"
    elif kind == "comment":
        source = NAV_BLOCK + b'\n<!--\n<img src="art.svg" alt="Hidden">\n-->\n\n'
    elif kind == "fenced-code":
        source = b'```html\n' + NAV_BLOCK + b'\n<img src="art.svg" alt="Literal">\n```\n\n'
    else:
        source = NAV_BLOCK + b'\n![Language Python](' + generated["badge_path"].encode() + b')\n\n'
    meta = checkout(tmp_path, source)
    if kind == "managed-image":
        badge = tmp_path / generated["badge_path"]
        badge.parent.mkdir(parents=True, exist_ok=True)
        badge.write_bytes(generated["badge"])
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode)

    refusal(result, tmp_path, before, "needs-input:intro")


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("indentation", [b"", b"    "], ids=["plain-control", "four-spaces-after-end-comment"])
def test_visible_html_art_after_nav_stays_authored_without_intro(tmp_path, mode, indentation):
    source = (NAV_BLOCK + indentation + b'<img src="art.svg" alt="Authored artwork">\n'
              b'\nAuthored  notes.  \r\n')
    meta = checkout(tmp_path, source)
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode)

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    updated = (tmp_path / "README.md").read_bytes()
    nav, = NAV.finditer(updated)
    # The documented managed nav may refresh; its adjacent authored bytes may not.
    assert updated[:nav.start()] == b""
    assert updated[nav.end():] == source[len(NAV_BLOCK):]
    assert updated.count(b'<img src="art.svg" alt="Authored artwork">') == 1
    assert b"assets/intro.svg" not in updated and not (tmp_path / "assets/intro.svg").exists()
    changed = updated != before["README.md"]
    assert report["result"] == ("changed" if changed else "unchanged"), report
    assert report["written"] is changed, report


@pytest.mark.parametrize("mode", ["scaffold", "upgrade", "header"])
def test_lf_legacy_keeps_inline_authored_crlf_and_mixed_suffix(tmp_path, generated, mode):
    # Preserve the generator's LF hero beside authored CRLF; choosing one global
    # newline for the moved header must not normalize the inline authored line.
    hero = generated["legacy_hero"].encode("utf-8")
    suffix = LINK + b"  \r\n\r\nAuthored  notes.\t\n\nLast authored line.\r"
    meta = checkout(tmp_path, hero + suffix, generated["intro"])
    before_links = visible_guide(tmp_path, meta)
    assert len(before_links) == 1 and before_links[0]["status"] == "ok", before_links

    result = readme(tmp_path, meta, mode)

    assert result.returncode == 0, result.stdout + result.stderr
    assert_success(tmp_path, meta, mode, b"", suffix, before_links)
