"""Public CLI checks for authored prefix bytes and the suffix's rendered context."""
import json
import re

import pytest

from conftest import ROOT, run_cli
from test_personal_hero_order import LEGACY_HERO, applicable_intro as applicable_intro, fixture_repo, snapshot
from test_personal_hero_url_authority import offline_cli as offline_cli


BOM = b"\xef\xbb\xbf"
LINK = b'<a href="GUIDE.md">Authored documentation</a>'
HERO = re.compile(br"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.DOTALL)
CONTENT_FIX = ROOT / "tests/fixtures/content"
CONTENT_FLAGS = ("--registry", CONTENT_FIX / "registry.min.yaml",
                 "--approved", CONTENT_FIX / "approved.empty.txt",
                 "--approved-yaml", CONTENT_FIX / "approved.empty.yaml",
                 "--actions", CONTENT_FIX / "estate-actions.json")
CASES = [
    pytest.param(1, b"", "J", id="encoding-only-J"),
    pytest.param(2, b"", "J", id="two-BOM-zero-spaces-J"),
    pytest.param(2, b"   ", "J", id="two-BOM-three-spaces-J"),
    pytest.param(2, b"    ", "J", id="two-BOM-four-spaces-J"),
    pytest.param(3, b"    ", "J", id="three-BOM-four-spaces-J"),
    pytest.param(2, b"\t", "J", id="two-BOM-tab-J"),
    pytest.param(2, b"    ", "G", id="two-BOM-four-spaces-G"),
    pytest.param(3, b"\t", "H", id="three-BOM-tab-H"),
    pytest.param(1, b"", "G", id="encoding-only-G"),
    pytest.param(1, b"", "H", id="encoding-only-H"),
]


def source_parts(bom_count, whitespace, variant):
    prefix = BOM * bom_count + whitespace
    if variant == "J":
        suffix = LINK + b"  \r\n\r\nAuthored  suffix paragraph.\t\r\n"
    else:
        # Existing callout supplies the documented G/H context. The visible link
        # follows the callout and H1, so these controls have no missing context.
        callout = (
            b"> [!NOTE]\r\n> **Fork of [Example-Org/synthetic-upstream]"
            b"(https://github.com/Example-Org/synthetic-upstream)**, kept by CompleteTech LLC. "
            b"The upstream README follows unchanged; the upstream license applies.\r\n" if variant == "G" else
            b"> [!WARNING]\r\n> **Archived on 2026-01-01.** Retired. There is no replacement. "
            b"This repository is read-only.\r\n"
        )
        suffix = (b"\r\n\r\n" + callout + b"\r\n# Synthetic profile\r\n\r\n"
                  + LINK + b"  \r\n\r\nAuthored notes.\t\r\n")
    return prefix, LEGACY_HERO.replace(b"\n", b"\r\n"), suffix


def checkout(directory, source, intro, variant="J"):
    meta = fixture_repo(directory, source, intro)
    (directory / "GUIDE.md").write_bytes(b"# Synthetic guide\r\n\r\nLocal documentation.\r\n")
    (directory / "LICENSE").write_bytes(b"Synthetic MIT license fixture.\r\n")
    capture = json.loads(meta.read_text(encoding="utf-8"))
    capture.update(files=["README.md", "GUIDE.md", "LICENSE"], files_complete=True)
    if variant == "G":
        capture.update(parent={"full_name": "Example-Org/synthetic-upstream", "default_branch": "main"},
                       ahead_by=0, default_branch="main")
    meta.write_text(json.dumps(capture), encoding="utf-8")
    return meta


def scaffold(directory, meta, variant):
    return run_cli("--format", "json", "--meta", meta, "--repo-dir", directory,
                   "readme", "--mode", "scaffold", "--variant", variant, "--badges", "local",
                   "--records", directory / "records.jsonl", "--write")


def guide_links(directory, meta):
    result = run_cli("--meta", meta, "--repo-dir", directory, "content", "links", "README.md", *CONTENT_FLAGS)
    assert result.returncode == 0, result.stdout + result.stderr
    return [row for row in json.loads(result.stdout)["findings"] if row["target"] == "GUIDE.md"]


def lint(directory, meta, variant="J"):
    result = run_cli("--meta", meta, "--repo-dir", directory, "lint", "readme", directory / "README.md",
                     "--variant", variant)
    return result, json.loads(result.stdout)


@pytest.mark.parametrize("bom_count,whitespace,variant", CASES)
def test_owned_hero_scaffold_keeps_prefix_and_visible_suffix_context(
        tmp_path, applicable_intro, bom_count, whitespace, variant):
    prefix, hero, suffix = source_parts(bom_count, whitespace, variant)
    meta = checkout(tmp_path, prefix + hero + suffix, applicable_intro, variant)
    before_links = guide_links(tmp_path, meta)
    assert len(before_links) == 1 and before_links[0]["status"] == "ok", before_links

    result = scaffold(tmp_path, meta, variant)

    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    blocks = list(HERO.finditer(updated))
    after_links = guide_links(tmp_path, meta)
    lint_result, lint_report = lint(tmp_path, meta, variant)
    before_retry = snapshot(tmp_path)
    retry = scaffold(tmp_path, meta, variant)
    after_retry = snapshot(tmp_path)
    problems = []
    if len(blocks) != 1:
        problems.append("Expected exactly one managed hero")
    elif updated[:blocks[0].start()] != prefix:
        problems.append("Complete authored prefix bytes changed or moved")
    if updated.count(BOM) != bom_count or updated.count(suffix) != 1:
        problems.append("Authored BOM or complete suffix bytes changed")
    if updated.count(b'src="assets/intro.svg"') != 1 or b"docs/images/banner.png" in updated:
        problems.append("Expected one applicable intro and no legacy banner")
    if len(after_links) != 1 or after_links[0]["status"] != "ok":
        problems.append("The authored GUIDE.md link lost its visible context")
    if lint_result.returncode != 0 or any("R7" in failure for failure in lint_report["fails"]):
        problems.append("Actual README lint must pass, including R7 ordering")
    if retry.returncode != 0 or after_retry != before_retry:
        problems.append("Scaffold retry must preserve the complete checkout snapshot")
    if b"\r" in updated.replace(b"\r\n", b"") or b"\n" in updated.replace(b"\r\n", b""):
        problems.append("Uniform authored CRLF must survive")
    assert not problems, json.dumps({
        "problems": problems, "expected_prefix_hex": prefix.hex(),
        "actual_prefix_hex": updated[:blocks[0].start()].hex() if blocks else None,
        "guide_before": before_links, "guide_after": after_links,
        "lint_exit": lint_result.returncode, "lint": lint_report,
        "retry_exit": retry.returncode, "retry_stdout": retry.stdout,
    }, indent=2)


@pytest.mark.parametrize("variant,whitespace", [("J", b"    "), ("J", b"\t"),
                                                ("G", b"    "), ("H", b"\t")])
def test_owned_prefix_missing_intro_refuses_atomically(tmp_path, variant, whitespace):
    prefix, hero, suffix = source_parts(2, whitespace, variant)
    meta = checkout(tmp_path, prefix + hero + suffix, None, variant)
    before = snapshot(tmp_path)

    result = scaffold(tmp_path, meta, variant)

    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:intro" in json.loads(result.stdout)["logs"]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("marked", [True, False], ids=["edited-marker-body", "unmarked-art"])
def test_authored_art_prefix_does_not_acquire_generator_ownership(tmp_path, marked):
    prefix, hero, suffix = source_parts(2, b"    ", "J")
    authored = (hero.replace(b'width="100%"', b'width="840"') if marked else
                b'<img src="docs/images/custom-art.svg" alt="Authored art" width="840">')
    source = prefix + authored + suffix
    meta = checkout(tmp_path, source, None)
    (tmp_path / "docs/images/custom-art.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>\n')
    before = snapshot(tmp_path)
    assert len(guide_links(tmp_path, meta)) == 1

    result = scaffold(tmp_path, meta, "J")

    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(tmp_path) == before
    assert len(guide_links(tmp_path, meta)) == 1
    assert b"assets/intro.svg" not in (tmp_path / "README.md").read_bytes()


@pytest.mark.parametrize("style", ["fenced", "indented"])
def test_literal_hero_and_link_do_not_supply_visible_artwork(tmp_path, style):
    example = LEGACY_HERO.replace(b"\n", b"\r\n") + b"\r\n" + LINK
    if style == "fenced":
        source = BOM + b"\r\n\r\n```html\r\n" + example + b"\r\n```\r\n"
    else:
        source = BOM + b"\r\n\r\n" + b"\r\n".join(b"    " + line for line in example.split(b"\r\n")) + b"\r\n"
    meta = checkout(tmp_path, source, None)
    before = snapshot(tmp_path)
    assert guide_links(tmp_path, meta) == []

    result = scaffold(tmp_path, meta, "J")

    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:intro" in json.loads(result.stdout)["logs"]
    assert snapshot(tmp_path) == before


def test_visible_authored_preamble_still_fails_personal_header_order(tmp_path, applicable_intro):
    meta = checkout(tmp_path, b"", applicable_intro)
    generated = scaffold(tmp_path, meta, "J")
    assert generated.returncode == 0, generated.stdout + generated.stderr
    nominal, report = lint(tmp_path, meta)
    assert nominal.returncode == 0, report
    readme = tmp_path / "README.md"
    readme.write_bytes(BOM * 2 + b"Visible authored preamble.\r\n\r\n" + readme.read_bytes())
    before = snapshot(tmp_path)

    result, report = lint(tmp_path, meta)

    assert result.returncode == 1, report
    assert any(failure.startswith("R7 ") and "hero banner must open the README" in failure
               for failure in report["fails"]), report
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("seam", ["adjacent", "separated"])
def test_g_fork_callout_cannot_split_owned_hero_prefix_or_precede_intro(
        tmp_path, applicable_intro, seam):
    prefix = BOM * 2 + b"    "
    hero = LEGACY_HERO.replace(b"\n", b"\r\n")
    separator = b"" if seam == "adjacent" else b"\r\n\r\n"
    suffix = (separator + LINK + b"  \r\n\r\n# Synthetic profile\r\n\r\n"
              b"Authored  fork paragraph.\t\r\n")
    meta = checkout(tmp_path, prefix + hero + suffix, applicable_intro, "G")
    assert len(guide_links(tmp_path, meta)) == 1
    before = snapshot(tmp_path)

    result = scaffold(tmp_path, meta, "G")

    if result.returncode == 4:
        assert seam == "adjacent", "The separated control must support the documented fork layout"
        report = json.loads(result.stdout)
        assert report["result"] == "needs-input" and "needs-input:intro-order" in report["logs"], report
        assert snapshot(tmp_path) == before, "An unsafe inline move must refuse before every output write"
        return
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    block, = HERO.finditer(updated)
    after_links = guide_links(tmp_path, meta)
    lint_result, lint_report = lint(tmp_path, meta, "G")
    note = updated.find(b"> [!NOTE]")
    before_retry = snapshot(tmp_path)
    retry = scaffold(tmp_path, meta, "G")
    problems = []
    if updated[:block.start()] != prefix or updated.count(BOM) != 2:
        problems.append("The complete encoding/authored prefix must remain attached to the hero")
    if updated.count(b"> [!NOTE]") != 1 or not block.end() <= note < updated.find(LINK):
        problems.append("Exactly one fork callout must follow the intro and precede the authored upstream body")
    if updated.count(suffix) != 1 or len(after_links) != 1 or after_links[0]["status"] != "ok":
        problems.append("The complete authored suffix and its visible link context must survive")
    if updated.count(b'src="assets/intro.svg"') != 1 or b"docs/images/banner.png" in updated:
        problems.append("Expected one applicable owned intro and no legacy banner")
    if lint_result.returncode != 0:
        problems.append("Actual G README lint must pass")
    if retry.returncode != 0 or snapshot(tmp_path) != before_retry:
        problems.append("Successful retry must preserve the complete fixture snapshot")
    assert not problems, json.dumps({
        "problems": problems, "seam": seam, "actual_prefix_hex": updated[:block.start()].hex(),
        "hero_end": block.end(), "callout_start": note, "guide_after": after_links,
        "lint_exit": lint_result.returncode, "lint": lint_report, "retry_exit": retry.returncode,
    }, indent=2)
