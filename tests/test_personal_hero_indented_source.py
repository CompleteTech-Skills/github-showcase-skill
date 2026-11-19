"""Public-CLI controls for indented managed heroes after authored U+FEFF."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts/showcase.py")]
BOM = b"\xef\xbb\xbf"
SUFFIX = b"QAdjacent authored suffix.  \r\n"
META = {
    "owner": "CompleteDotTech", "repo": "CompleteDotTech", "visibility": "public",
    "description": "Inspect synthetic profile records.", "license": "MIT", "language": "Python",
    "files": ["README.md", "LICENSE"], "default_branch": "main",
}


def cli(*args):
    env = dict(os.environ)
    env.pop("SHOWCASE_ESTATE_ROOT", None)
    return subprocess.run([*CLI, *map(str, args)], cwd=ROOT, env=env,
                          capture_output=True, encoding="utf-8")


def capture(path, repo="CompleteDotTech"):
    path.write_text(json.dumps(dict(META, repo=repo)), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    base = tmp_path_factory.mktemp("indented-source-generated")
    intro = base / "assets/intro.svg"
    result = cli("intro", "--profile", "CompleteDotTech", "--static", "--out", intro)
    assert result.returncode == 0, result.stdout + result.stderr
    ordinary = base / "ordinary"
    ordinary.mkdir()
    name = "synthetic-source-control"
    result = cli("--meta", capture(base / "ordinary.json", name), "--repo-dir", ordinary,
                 "readme", "--mode", "scaffold", "--badges", "local", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = (ordinary / "README.md").read_text(encoding="utf-8")
    hero = re.search(r"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", text, re.S)
    assert hero is not None and "docs/images/banner.png" in hero.group()
    legacy = hero.group().replace(name, "CompleteDotTech").replace("\n", "\r\n").encode()
    return intro.read_bytes(), legacy


def prepare(tmp_path, generated, count, indent, available, *, authored=False):
    target = tmp_path / "checkout"
    target.mkdir()
    hero = b'![Authored art](assets/authored-art.svg)' if authored else generated[1]
    before = BOM * count + b" " * indent + hero + SUFFIX
    (target / "README.md").write_bytes(before)
    if available or authored:
        (target / "assets").mkdir()
        name = "intro.svg" if available else "authored-art.svg"
        (target / "assets" / name).write_bytes(generated[0])
    (target / "CONTRIBUTING.md").write_bytes(b"Synthetic contribution text.\t\r\n")
    return target, capture(tmp_path / "meta.json"), before


def scaffold(target, meta):
    return cli("--meta", meta, "--repo-dir", target, "--format", "json", "readme",
               "--mode", "scaffold", "--variant", "J", "--badges", "local", "--write",
               "--records", target.parent / "records.json")


@pytest.mark.parametrize("count,indent", [
    pytest.param(1, 0, id="canonical_encoding_bom"),
    pytest.param(2, 4, id="authored_feff_four_spaces"),
    pytest.param(3, 4, id="two_authored_feff_four_spaces"),
])
def test_source_view_refresh_has_one_owned_intro(tmp_path, generated, count, indent):
    target, meta, _ = prepare(tmp_path, generated, count, indent, True)
    result = scaffold(target, meta)
    assert result.returncode == 0, result.stdout + result.stderr
    after = (target / "README.md").read_bytes()
    assert after.startswith(BOM) and after.count(BOM) == count
    assert SUFFIX in after
    assert after.count(b'<!-- showcase:banner:start -->') == 1, after
    assert after.count(b'<!-- showcase:banner:end -->') == 1, after
    assert after.count(b'src="assets/intro.svg"') == 1, after
    assert b"docs/images/banner.png" not in after, after
    again = scaffold(target, meta)
    assert again.returncode == 0, again.stdout + again.stderr
    assert (target / "README.md").read_bytes() == after


@pytest.mark.parametrize("count", [2, 3])
def test_indented_source_missing_intro_refuses_atomically(tmp_path, generated, count):
    target, meta, _ = prepare(tmp_path, generated, count, 4, False)

    def files():
        return {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    before = files()
    result = scaffold(target, meta)
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:intro" in result.stdout
    assert files() == before


def test_authored_art_source_keeps_complete_bytes(tmp_path, generated):
    target, meta, before = prepare(tmp_path, generated, 2, 0, False, authored=True)
    result = scaffold(target, meta)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / "README.md").read_bytes() == before
    again = scaffold(target, meta)
    assert again.returncode == 0, again.stdout + again.stderr
    assert (target / "README.md").read_bytes() == before
