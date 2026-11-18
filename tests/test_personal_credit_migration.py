"""Offline CLI regression: owned credit migration retains exact personal source spans."""
import json
import os
import re
import subprocess
import sys

import pytest
import yaml

from conftest import ROOT


HERO = re.compile(br"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.S)
CREDIT = re.compile(br"<!-- showcase:credit:start -->.*?<!-- showcase:credit:end -->", re.S)
FOOTER = re.compile(br"<!-- showcase:footer:start -->.*?<!-- showcase:footer:end -->", re.S)
LEGACY_HERO = (
    b'<!-- showcase:banner:start -->\n<p align="center">\n'
    b'  <img src="docs/images/banner.png" alt="CompleteDotTech by CompleteTech LLC" width="100%">\n'
    b'</p>\n<!-- showcase:banner:end -->'
)


@pytest.fixture(scope="module")
def offline_cli(tmp_path_factory):
    root = tmp_path_factory.mktemp("personal-credit-cli")
    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import sys\n"
        "def block_network(event, args):\n"
        "    if event in ('socket.connect', 'socket.getaddrinfo'):\n"
        "        raise RuntimeError('personal credit test forbids network')\n"
        "sys.addaudithook(block_network)\n", encoding="utf-8",
    )
    env = dict(os.environ, PYTHONPATH=str(guard), PYTHONDONTWRITEBYTECODE="1",
               SHOWCASE_ESTATE_ROOT=str(root / "absent-estate"), SHOWCASE_STATE_DIR=str(root / "state"),
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def run(*args):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/showcase.py"), "--format", "json", *map(str, args)],
            cwd=root, env=env, capture_output=True, encoding="utf-8", timeout=60,
        )

    return run


@pytest.fixture(scope="module")
def generated(tmp_path_factory, offline_cli):
    intro = tmp_path_factory.mktemp("personal-credit-art") / "intro.svg"
    result = offline_cli("intro", "--profile", "CompleteDotTech", "--static", "--out", intro)
    assert result.returncode == 0, result.stdout + result.stderr
    result = offline_cli("footer")
    assert result.returncode == 0, result.stdout + result.stderr
    markup = json.loads(result.stdout)["markup"].encode("utf-8")
    credit, = CREDIT.finditer(markup)
    footer, = FOOTER.finditer(markup)
    brand = yaml.safe_load((ROOT / "references/brand.yaml").read_text(encoding="utf-8"))["footer"]
    legacy = footer.group()
    for key, previous in zip(("logo_light_url", "logo_dark_url"), brand["legacy_logo_urls"][:2]):
        legacy = legacy.replace(brand[key].encode("utf-8"), previous.encode("utf-8"))
    assert legacy != footer.group(), "The migration fixture must use documented historical logo URLs"
    return intro.read_bytes(), credit.group(), footer.group(), legacy


def target(tmp_path, intro, before):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, data in {
        "README.md": before,
        "assets/intro.svg": intro,
        "CONTRIBUTING.md": b"Synthetic authored contribution notes.  \r\n",
        "docs/images/.showcase.json": b'{"outputs": {}, "synthetic_sentinel": "keep exact bytes"}\n',
        "docs/images/badges/authored.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>\n',
        "records.jsonl": b'{"id":"synthetic-existing-record"}\n',
    }.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({
        "owner": "CompleteDotTech", "repo": "CompleteDotTech", "visibility": "public",
        "license": "MIT", "description": "Show synthetic public projects.",
        "topics": [], "files": [], "files_complete": True,
    }), encoding="utf-8")
    return repo, meta


def upgrade(offline_cli, repo, meta, variant):
    return offline_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "upgrade",
                       "--variant", variant, "--badges", "local", "--records", repo / "records.jsonl", "--write")


def snapshot(repo):
    return {path.relative_to(repo).as_posix(): path.read_bytes()
            for path in repo.rglob("*") if path.is_file()}


def authored_parts(style):
    if style == "mixed":
        return (
            b"\r\n", b"\r\n\n\r\n",
            b"> [!NOTE]\r\n> Synthetic callout.  \n\n# Synthetic profile\r\n\n"
            b"Body section\r-----\n\nAuthored  body.\t\r\n\n\tLiteral indented note.  \r\n\n",
            b"\r\n\n\n", b"\n\r\n\n",
        )
    ending = b"\r\n" if style == "CRLF" else b"\n"
    body = (
        b"> [!NOTE]\n> Synthetic callout.  \n\n# Synthetic profile\n\n"
        b"Body section\n-----\n\nAuthored  body.\t\n\n\tLiteral indented note.  \n\n"
    ).replace(b"\n", ending)
    return ending, ending * 3, body, ending * 3, ending * 3


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("style", ["LF", "CRLF", "mixed"])
@pytest.mark.parametrize("old_credit", [False, True], ids=["current-credit", "old-credit"])
@pytest.mark.parametrize("legacy_footer,trailing_credit", [
    pytest.param(True, False, id="credit-before-legacy-footer"),
    pytest.param(True, True, id="credit-after-legacy-footer"),
    pytest.param(False, True, id="credit-after-current-footer"),
])
def test_owned_credit_and_footer_migrate_without_changing_authored_bytes(
        tmp_path, generated, offline_cli, variant, style, old_credit, legacy_footer, trailing_credit):
    intro, current_credit, current_footer, previous_footer = generated
    credit = re.sub(br" v=[0-9A-Za-z.+-]+ ", b" v=0.8.2 ", current_credit) if old_credit else current_credit
    ending, header_gap, body, middle_gap, tail_gap = authored_parts(style)
    hero = LEGACY_HERO.replace(b"\n", ending)
    credit = credit.replace(b"\n", ending)
    footer = (previous_footer if legacy_footer else current_footer).replace(b"\n", ending)
    first, last = (footer, credit) if trailing_credit else (credit, footer)
    before = hero + header_gap + body + first + middle_gap + last + tail_gap
    repo, meta = target(tmp_path, intro, before)

    result = upgrade(offline_cli, repo, meta, variant)
    assert result.returncode == 0, result.stdout + result.stderr
    after = (repo / "README.md").read_bytes()
    new_hero, = HERO.finditer(after)
    new_credit, = CREDIT.finditer(after)
    new_footer, = FOOTER.finditer(after)
    assert new_hero.start() == 0 and b'src="assets/intro.svg"' in new_hero.group()
    assert b"docs/images/banner.png" not in after
    # Compare the entire retained source, including every separator exposed by
    # removing the owned blocks. A line-by-line presence check would miss drift.
    assert after[new_hero.end():new_credit.start()] == header_gap + body + middle_gap + tail_gap
    assert new_credit.group().replace(b"\r\n", b"\n") == current_credit
    assert new_footer.group().replace(b"\r\n", b"\n") == current_footer
    assert after[new_credit.end():new_footer.start()].strip() == b""
    assert after[new_footer.end():].strip() == b""
    assert after.count(b"<picture>") == 1
    if style == "CRLF":
        assert b"\n" not in after.replace(b"\r\n", b""), "Keep the source's CRLF convention"
    checked = offline_cli("--meta", meta, "--repo-dir", repo, "footer", "--check", repo / "README.md")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert json.loads(checked.stdout)["result"] == "pass"

    second = upgrade(offline_cli, repo, meta, variant)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (repo / "README.md").read_bytes() == after, "A repeated migration must be byte-idempotent"


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("case", ["foreign-generator", "foreign-link", "authored-child", "inline-prefix", "inline-suffix"])
def test_ambiguous_credit_refuses_before_any_personal_migration(tmp_path, generated, offline_cli, variant, case):
    intro, credit, _, legacy_footer = generated
    edits = {
        "foreign-generator": credit.replace(b"generated-by: github-showcase-skill", b"generated-by: northwind-docs"),
        "foreign-link": credit.replace(b"https://github.com/CompleteTech-Skills/github-showcase-skill",
                                       b"https://example.test/authored-tool"),
        "authored-child": credit.replace(b"</sub>", b"<span>Authored attribution.</span></sub>"),
        "inline-prefix": b"Authored neighbor." + credit,
        "inline-suffix": credit + b"Authored neighbor.",
    }
    _, gap, body, middle_gap, tail_gap = authored_parts("LF")
    before = LEGACY_HERO + gap + body + edits[case] + middle_gap + legacy_footer + tail_gap
    repo, meta = target(tmp_path, intro, before)
    original = snapshot(repo)

    result = upgrade(offline_cli, repo, meta, variant)
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:credit-ownership" in json.loads(result.stdout)["logs"]
    assert snapshot(repo) == original, "Credit refusal must preserve README, badges, sidecar and records"


@pytest.mark.parametrize("variant", ["G", "H"])
def test_credit_removal_cannot_fuse_authored_line_endings(tmp_path, generated, offline_cli, variant):
    intro, credit, _, legacy_footer = generated
    before = (LEGACY_HERO + b"\n\n> [!NOTE]\n> Synthetic callout.\n\n# Synthetic profile\n\n"
              b"Authored  body.\t\r" + credit + b"\n\n" + legacy_footer + b"\n")
    repo, meta = target(tmp_path, intro, before)
    original = snapshot(repo)

    result = upgrade(offline_cli, repo, meta, variant)
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:intro-order" in json.loads(result.stdout)["logs"]
    assert snapshot(repo) == original, "A lossy CR/LF join must refuse before any output is written"
