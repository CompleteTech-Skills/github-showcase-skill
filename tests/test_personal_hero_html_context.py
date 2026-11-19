"""Source-blind CLI acceptance for the whole raw HTML context of an owned hero."""
import json
import re
import shutil

import pytest

from conftest import run_cli
from test_personal_hero_badge_urls import generated as generated
from test_personal_hero_guard_paths import CONTENT_FLAGS, atomic_intro_order, checkout, controlled_formatter
from test_personal_hero_order import snapshot
from test_personal_hero_url_authority import offline_cli as offline_cli


HERO = re.compile(br"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.S)
GUIDE = b"[Authored guide](GUIDE.md)"
IMAGE = b"![Authored diagram](art.svg)"
TARGETS = {"GUIDE.md", "art.svg"}
STYLES = ["LF", "CRLF", "CR", "mixed"]


def readme(directory, meta, mode, formatted=False):
    options = ("--format-generated",) if formatted else ()
    return run_cli("--format", "json", "--meta", meta, "--repo-dir", directory,
                   "readme", "--mode", mode, "--variant", "J", "--badges", "local",
                   "--records", directory / "records.jsonl", "--write", *options)


def inventory(directory, meta):
    result = run_cli("--meta", meta, "--repo-dir", directory,
                     "content", "links", "README.md", *CONTENT_FLAGS)
    assert result.returncode == 0, result.stdout + result.stderr
    # Ignore newly generated navigation/badges and physical line-number movement.
    # Preserve authored target, rendering kind, source syntax and resolution status.
    return sorted((row["target"], row["image"], row["syntax"], row["kind"], row["status"])
                  for row in json.loads(result.stdout)["findings"] if row["target"] in TARGETS)


def parts(generated, seam, style):
    ending = {"LF": b"\n", "CRLF": b"\r\n", "CR": b"\r", "mixed": b"\n"}[style]
    hero = generated["legacy_hero"].encode().replace(b"\n", ending)
    breaks = (b"\r\n", b"\r", b"\n", b"\r") if style == "mixed" else (ending,) * 4
    lead = ending if seam == "own-line" else b" "
    # Neither the prose line nor the second/third physical line is separated
    # from the hero's original raw HTML block by a blank line.
    suffix = (lead + b"Authored  raw prose.\t" + breaks[0] + GUIDE + breaks[1]
              + IMAGE + breaks[2] * 2 + b"Authored  tail.\t" + breaks[3])
    return b"", hero, suffix


def success(directory, meta, mode, prefix, suffix, before_inventory, formatted=False):
    updated = (directory / "README.md").read_bytes()
    after_inventory = inventory(directory, meta)
    blocks = list(HERO.finditer(updated))
    before_retry = snapshot(directory)
    retry = readme(directory, meta, mode, formatted)
    problems = []
    if prefix and updated.count(prefix) != 1:
        problems.append("complete authored prefix bytes changed or duplicated")
    if updated.count(suffix) != 1:
        problems.append("complete authored suffix bytes changed or duplicated")
    if len(blocks) != 1 or updated.count(b'src="assets/intro.svg"') != 1:
        problems.append("expected exactly one applicable owned intro")
    if b"docs/images/banner.png" in updated:
        problems.append("legacy banner reference survived")
    if after_inventory != before_inventory:
        problems.append("authored Markdown/link/image interpretation changed")
    if retry.returncode != 0 or snapshot(directory) != before_retry:
        problems.append("successful retry changed the whole checkout snapshot")
    # Keep generated asset bodies and configured human identity out of diagnostics.
    assert not problems, json.dumps({"problems": problems, "inventory_before": before_inventory,
                                    "inventory_after": after_inventory, "retry_exit": retry.returncode})


def exercise(directory, generated, mode, prefix, hero, suffix, *, expected_targets=(),
             require_success=False, formatted=False):
    meta = checkout(directory, prefix + hero + suffix, generated["intro"])
    called = None
    if formatted:
        # Reuse the existing identity/AST stub. This is controlled ordering
        # evidence, not native Prettier parsing or rendering evidence.
        called = controlled_formatter(directory)
        entry = directory / "node_modules/prettier/index.cjs"
        # Make the observation marker idempotent so it cannot manufacture a
        # retry failure when successful semantic preservation is possible.
        entry.write_text(entry.read_text(encoding="utf-8").replace("appendFileSync", "writeFileSync"),
                         encoding="utf-8")
    before_inventory = inventory(directory, meta)
    assert sorted(row[0] for row in before_inventory) == sorted(expected_targets), before_inventory
    before = snapshot(directory)

    result = readme(directory, meta, mode, formatted)

    if result.returncode == 4 and not require_success:
        atomic_intro_order(result, directory, before)
        if called is not None:
            assert not called.exists(), "A refused unsafe move must stop before the controlled formatter loads"
        return
    assert result.returncode == 0, result.stdout + result.stderr
    success(directory, meta, mode, prefix, suffix, before_inventory, formatted)


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("seam", ["inline-prose", "own-line"])
def test_later_literal_markdown_keeps_its_original_raw_html_context(tmp_path, generated, mode, style, seam):
    exercise(tmp_path, generated, mode, *parts(generated, seam, style))


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
def test_authored_prefix_sharing_the_hero_html_block_keeps_its_meaning(tmp_path, generated, mode):
    prefix = b"<div>\r\n" + GUIDE + b"\n" + IMAGE + b"\r\n"
    suffix = b"\nAuthored  raw tail.\t\r\n</div>\r\n\r\nAuthored notes.\n"
    exercise(tmp_path, generated, mode, prefix, generated["legacy_hero"].encode(), suffix)


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("kind", ["plain-paragraph", "blank-separated-Markdown"])
def test_safe_paragraph_and_explicit_blank_line_controls_succeed(tmp_path, generated, mode, kind):
    if kind == "plain-paragraph":
        suffix = (b" Authored  plain prose.\t\nSecond plain line.\r\n\r\n"
                  + GUIDE + b"\r\n\r\nAuthored tail.\n")
        expected = ("GUIDE.md",)
    else:
        suffix = b"\r\n\r\n" + GUIDE + b"\n" + IMAGE + b"\r\n\r\nAuthored tail.\n"
        expected = ("GUIDE.md", "art.svg")
    exercise(tmp_path, generated, mode, b"", generated["legacy_hero"].encode(), suffix,
             expected_targets=expected, require_success=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="controlled formatter ordering needs local Node.js")
@pytest.mark.parametrize("mode,seam,style", [
    ("scaffold", "inline-prose", "LF"), ("upgrade", "own-line", "CRLF"),
])
def test_whole_html_context_is_checked_before_controlled_formatting(tmp_path, generated, mode, seam, style):
    exercise(tmp_path, generated, mode, *parts(generated, seam, style), formatted=True)
