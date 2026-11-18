"""Black-box personal hero regressions for equivalent local badge URLs (#159)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

import pytest


ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts/showcase.py")]
PROFILE = "CompleteDotTech"
META = {
    "owner": PROFILE, "repo": PROFILE, "visibility": "public", "license": "MIT",
    "description": "Inspect synthetic profile records.", "language": "Python",
    "default_branch": "main", "files": ["README.md", "LICENSE"],
}
HERO = re.compile(r"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.S)


def cli(*args):
    env = dict(os.environ)
    env.pop("SHOWCASE_ESTATE_ROOT", None)
    return subprocess.run([*CLI, *map(str, args)], cwd=ROOT, env=env,
                          capture_output=True, encoding="utf-8")


def metadata(path, repo=PROFILE):
    path.write_text(json.dumps(dict(META, repo=repo)), encoding="utf-8")
    return path


def readme(checkout, capture, mode):
    return cli("--meta", capture, "--repo-dir", checkout, "--format", "json",
               "readme", "--mode", mode, "--badges", "local", "--write",
               "--records", checkout.parent / "records.json")


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """Produce actual local badge and hero fixtures through the public CLI."""
    base = tmp_path_factory.mktemp("badge-url-generated")
    profile = base / "profile"
    profile.mkdir()
    capture = metadata(base / "profile.json")
    intro = profile / "assets/intro.svg"
    result = cli("intro", "--profile", PROFILE, "--static", "--out", intro)
    assert result.returncode == 0, result.stdout + result.stderr
    result = readme(profile, capture, "scaffold")
    assert result.returncode == 0, result.stdout + result.stderr
    text = (profile / "README.md").read_text(encoding="utf-8")
    intro_hero = HERO.search(text)
    assert intro_hero is not None
    badge = re.search(r"docs/images/badges/[a-z0-9-]+\.svg", text)
    assert badge is not None

    # Obtain the legacy banner layout from the repository scaffold, then supply
    # the personal repository's factual slug in the synthetic legacy capture.
    ordinary = base / "ordinary"
    ordinary.mkdir()
    ordinary_name = "synthetic-profile-control"
    result = readme(ordinary, metadata(base / "ordinary.json", ordinary_name), "scaffold")
    assert result.returncode == 0, result.stdout + result.stderr
    legacy = HERO.search((ordinary / "README.md").read_text(encoding="utf-8"))
    assert legacy is not None and "docs/images/banner.png" in legacy.group()
    legacy_hero = legacy.group().replace(ordinary_name, PROFILE)
    return {
        "intro": intro.read_bytes(), "badge_path": badge.group(),
        "badge": (profile / badge.group()).read_bytes(),
        "intro_hero": intro_hero.group(), "legacy_hero": legacy_hero,
    }


def badge_url(path, spelling):
    if spelling == "canonical":
        return path
    if spelling == "unreserved_directory":
        return "%64" + path[1:]
    if spelling == "encoded_separators":
        return quote(path, safe="")
    if spelling == "dot_segments":
        return path.replace("docs/images/", "docs/./images/", 1)
    if spelling == "parent_segments":
        return path.replace("docs/images/", "docs/images/../images/", 1)
    if spelling == "repeated_relative_prefix":
        return "././" + path
    if spelling == "percent_dot_segment":
        return path.replace("docs/images/", "docs/%2E/images/", 1)
    if spelling == "dot_segment_encoded_separators":
        return quote(path.replace("docs/images/", "docs/./images/", 1), safe="")
    assert spelling == "unreserved_filename"
    return path.replace("-", "%2D", 1)


URL_SPELLINGS = [
    "canonical", "unreserved_directory", "encoded_separators", "unreserved_filename",
    "dot_segments", "parent_segments", "repeated_relative_prefix", "percent_dot_segment",
    "dot_segment_encoded_separators",
]


def checkout(tmp_path, generated, *, intro):
    target = tmp_path / "checkout"
    target.mkdir()
    badge = target / generated["badge_path"]
    badge.parent.mkdir(parents=True)
    badge.write_bytes(generated["badge"])
    if intro:
        asset = target / "assets/intro.svg"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(generated["intro"])
    return target, metadata(tmp_path / "metadata.json")


@pytest.mark.parametrize("spelling", URL_SPELLINGS)
def test_first_scaffold_badge_url_still_requires_intro(tmp_path, generated, spelling):
    target, capture = checkout(tmp_path, generated, intro=False)
    url = badge_url(generated["badge_path"], spelling)
    before = f"# Synthetic profile\r\n\r\n![Language Python]({url})\r\n\r\nKeep  this text.  \r\n".encode()
    readme_path = target / "README.md"
    readme_path.write_bytes(before)
    result = readme(target, capture, "scaffold")
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:intro" in result.stdout
    assert readme_path.read_bytes() == before
    assert not (tmp_path / "records.json").exists()


@pytest.mark.parametrize("spelling", URL_SPELLINGS)
@pytest.mark.parametrize("hero", ["legacy_hero", "intro_hero"])
def test_header_with_badge_before_owned_hero_refuses_without_changing_urls(
    tmp_path, generated, spelling, hero,
):
    target, capture = checkout(tmp_path, generated, intro=True)
    url = badge_url(generated["badge_path"], spelling)
    before = (f"![Language Python]({url})\r\n\r\n" + generated[hero].replace("\n", "\r\n")
              + "\r\n\r\n# Synthetic profile\r\n\r\nKeep  this text.  \r\n").encode()
    path = target / "README.md"
    path.write_bytes(before)
    result = readme(target, capture, "header")
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:intro-order" in result.stdout
    assert path.read_bytes() == before
    assert not (tmp_path / "records.json").exists()


@pytest.mark.parametrize("spelling", URL_SPELLINGS)
def test_full_upgrade_places_owned_intro_before_equivalent_badge_url(tmp_path, generated, spelling):
    target, capture = checkout(tmp_path, generated, intro=True)
    url = badge_url(generated["badge_path"], spelling)
    authored_badge = f"![Language Python]({url})"
    before = authored_badge + "\n\n" + generated["intro_hero"] + "\n\n# Synthetic profile\n\nKeep text.\n"
    path = target / "README.md"
    path.write_text(before, encoding="utf-8")
    result = readme(target, capture, "upgrade")
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_text(encoding="utf-8")
    assert after.index('src="assets/intro.svg"') < after.index(authored_badge)
    assert authored_badge in after
    assert "Keep text.\n" in after


@pytest.mark.parametrize("url", [
    "docs/images/custom%2Dbadge%2Dhero.svg", "assets%2Fauthored-badge-art.svg",
    "docs/images/badges/../custom-art.svg", "docs/images/badges/%2E%2E/custom-art.svg",
])
def test_encoded_authored_art_is_not_mistaken_for_generated_badge(tmp_path, generated, url):
    target, capture = checkout(tmp_path, generated, intro=False)
    before = f"# Synthetic profile\r\n\r\n![Authored art]({url})\r\n\r\nKeep  this text.  \r\n".encode()
    path = target / "README.md"
    path.write_bytes(before)
    result = readme(target, capture, "scaffold")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("url", [
    pytest.param("https://example.test/docs/images/badges/profile-art.svg", id="https_canonical"),
    pytest.param("https://example.test/../../docs/images/badges/profile-art.svg", id="https_dot_segments"),
    pytest.param("//example.test/docs/images/badges/profile-art.svg", id="network_relative_canonical"),
    pytest.param("//example.test/../../docs/images/badges/profile-art.svg", id="network_relative_dot_segments"),
])
@pytest.mark.parametrize("available", [False, True], ids=["missing_intro", "applicable_intro"])
def test_remote_authored_art_never_becomes_a_local_badge(tmp_path, generated, url, available):
    target, capture = checkout(tmp_path, generated, intro=available)
    before = (f"# Synthetic profile\r\n\r\n![Authored remote art]({url})\r\n\r\n"
              "Keep  authored text.\t\r\n").encode()
    path = target / "README.md"
    path.write_bytes(before)

    def files():
        return {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    initial_files = files()
    result = readme(target, capture, "scaffold")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == before
    assert files() == initial_files
    assert not (tmp_path / "records.json").exists()
