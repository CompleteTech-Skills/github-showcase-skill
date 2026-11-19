"""Offline CLI guards for formatting, authored nav prose and literal inline Markdown."""
import json
import re
import shutil

import pytest

from conftest import ROOT, run_cli
from test_formatting import local_prettier
from test_personal_hero_badge_urls import generated as generated
from test_personal_hero_order import fixture_repo, snapshot
from test_personal_hero_url_authority import offline_cli as offline_cli


HERO = re.compile(br"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.S)
LINK = b'<a href="GUIDE.md">Authored documentation</a>'
ART = b'<img src="art.svg" alt="Authored artwork">'
CONTENT = ROOT / "tests/fixtures/content"
CONTENT_FLAGS = ("--registry", CONTENT / "registry.min.yaml",
                 "--approved", CONTENT / "approved.empty.txt",
                 "--approved-yaml", CONTENT / "approved.empty.yaml",
                 "--actions", CONTENT / "estate-actions.json")


def checkout(directory, source, intro=None):
    meta = fixture_repo(directory, source, intro)
    for name, data in {"GUIDE.md": b"# Synthetic guide\r\n",
                       "LICENSE": b"Synthetic MIT license fixture.\n",
                       "art.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>\n'}.items():
        (directory / name).write_bytes(data)
    capture = json.loads(meta.read_text(encoding="utf-8"))
    capture.update(files=["README.md", "GUIDE.md", "LICENSE", "art.svg"], files_complete=True)
    meta.write_text(json.dumps(capture), encoding="utf-8")
    return meta


def readme(directory, meta, mode, *options):
    return run_cli("--format", "json", "--meta", meta, "--repo-dir", directory,
                   "readme", "--mode", mode, "--variant", "J", "--badges", "local",
                   "--records", directory / "records.jsonl", "--write", *options)


def matching_links(directory, meta, target):
    result = run_cli("--meta", meta, "--repo-dir", directory,
                     "content", "links", "README.md", *CONTENT_FLAGS)
    assert result.returncode == 0, result.stdout + result.stderr
    return [row for row in json.loads(result.stdout)["findings"] if row["target"] == target]


def atomic_intro_order(result, directory, before):
    assert result.returncode == 4, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["result"] == "needs-input" and "needs-input:intro-order" in report["logs"], report
    assert snapshot(directory) == before, "Refusal must change or create no checkout files"


def controlled_formatter(directory):
    """Identity/AST stub: controlled ordering evidence, never native Prettier proof."""
    local_prettier(directory)
    (directory / ".prettierrc.json").write_text("{}\n", encoding="utf-8")
    called = directory / "controlled-formatter-called.txt"
    (directory / "node_modules/prettier/index.cjs").write_text(
        "require('fs').appendFileSync(" + json.dumps(str(called)) + ", 'loaded\\n');\n"
        "exports.resolveConfig = async () => ({});\n"
        "exports.format = async (input) => input;\n"
        "exports.__debug = {parse: async () => ({ast: {children: []}})};\n",
        encoding="utf-8",
    )
    return called


@pytest.mark.skipif(shutil.which("node") is None, reason="controlled formatter ordering needs local Node.js")
@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
def test_unsafe_intro_move_refuses_before_controlled_formatter_executes(tmp_path, generated, mode):
    source = b"  " + generated["legacy_hero"].encode() + b"  " + LINK + b"  \r\n\r\nAuthored notes.\n"
    meta = checkout(tmp_path, source, generated["intro"])
    called = controlled_formatter(tmp_path)
    before_links = matching_links(tmp_path, meta, "GUIDE.md")
    assert len(before_links) == 1 and before_links[0]["status"] == "ok", before_links
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode, "--format-generated")

    # Capture all ordering evidence even when the CLI wrongly reports success.
    report = json.loads(result.stdout)
    assert (result.returncode == 4 and report["result"] == "needs-input"
            and "needs-input:intro-order" in report["logs"]
            and not called.exists() and snapshot(tmp_path) == before), {
                "exit": result.returncode, "report": report, "formatter_called": called.exists(),
                "checkout_unchanged": snapshot(tmp_path) == before,
            }


@pytest.mark.skipif(shutil.which("node") is None, reason="controlled formatter ordering needs local Node.js")
def test_controlled_formatter_is_reachable_for_safe_owned_refresh(tmp_path, generated):
    source = generated["legacy_hero"].encode() + b"\n\n" + LINK + b"\n"
    meta = checkout(tmp_path, source, generated["intro"])
    called = controlled_formatter(tmp_path)

    result = readme(tmp_path, meta, "scaffold", "--format-generated")

    assert result.returncode == 0, result.stdout + result.stderr
    assert called.is_file(), "The controlled formatter must be reachable for this safe CLI control"
    after_links = matching_links(tmp_path, meta, "GUIDE.md")
    assert len(after_links) == 1 and after_links[0]["status"] == "ok", after_links


@pytest.mark.parametrize("mode", ["scaffold", "header", "upgrade"])
@pytest.mark.parametrize("body", [
    "**Authored safety note** · Keep this authored sentence exactly.",
    "Authored safety note. Keep this authored sentence exactly.",
], ids=["formatted-prose", "plain-prose"])
def test_authored_nav_prose_beside_visible_art_never_acquires_ownership(tmp_path, mode, body):
    nav = ("<!-- showcase:nav:start -->\r\n" + body + "\r\n<!-- showcase:nav:end -->").encode()
    suffix = b"    " + ART + b"\n\nAuthored  notes.\t\r\n"
    source = nav + suffix
    meta = checkout(tmp_path, source)
    before = snapshot(tmp_path)
    before_art = matching_links(tmp_path, meta, "art.svg")
    assert len(before_art) == 1 and before_art[0]["image"] is True, before_art

    result = readme(tmp_path, meta, mode)

    if result.returncode == 4:
        atomic_intro_order(result, tmp_path, before)
        return
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    assert updated.count(source) == 1, "All authored nav prose, markup, art and adjacent bytes must survive"
    assert b"assets/intro.svg" not in updated and not (tmp_path / "assets/intro.svg").exists()
    after_art = matching_links(tmp_path, meta, "art.svg")
    assert len(after_art) == 1 and after_art[0]["image"] is True, after_art
    before_retry = snapshot(tmp_path)
    retry = readme(tmp_path, meta, mode)
    assert retry.returncode == 0 and snapshot(tmp_path) == before_retry, retry.stdout + retry.stderr


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("literal,target", [
    pytest.param(b"[Literal guide](GUIDE.md)", "GUIDE.md", id="literal-link"),
    pytest.param(b"![Literal diagram](art.svg)", "art.svg", id="literal-image"),
    pytest.param(b"## [Literal heading](GUIDE.md)", "GUIDE.md", id="literal-heading-link"),
])
def test_owned_hero_move_cannot_activate_same_line_literal_markdown(tmp_path, generated, mode, literal, target):
    suffix = literal + b"  \r\n\r\nAuthored  notes.\t\n"
    source = generated["legacy_hero"].encode() + suffix
    meta = checkout(tmp_path, source, generated["intro"])
    assert matching_links(tmp_path, meta, target) == [], "The original HTML block keeps this Markdown literal"
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode)

    if result.returncode == 4:
        atomic_intro_order(result, tmp_path, before)
        return
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    assert updated.count(suffix) == 1, "Preserve every authored suffix byte"
    assert matching_links(tmp_path, meta, target) == [], "Moving the hero must not activate literal Markdown"
    block, = HERO.finditer(updated)
    assert block.start() == 0 and b'src="assets/intro.svg"' in block.group()
    assert updated.count(b'src="assets/intro.svg"') == 1 and b"docs/images/banner.png" not in updated
    before_retry = snapshot(tmp_path)
    retry = readme(tmp_path, meta, mode)
    assert retry.returncode == 0 and snapshot(tmp_path) == before_retry, retry.stdout + retry.stderr
