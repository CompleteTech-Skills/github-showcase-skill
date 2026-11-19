"""Public-CLI byte-preservation controls for late personal hero relocation (#159)."""
from __future__ import annotations

import hashlib
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
META = {
    "owner": "CompleteDotTech", "repo": "CompleteDotTech", "visibility": "public",
    "license": "MIT", "description": "Show synthetic public projects.",
    "topics": [], "files": [], "files_complete": True,
}
HERO = re.compile(r"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.S)


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
    root = tmp_path_factory.mktemp("relocation-generated")
    intro = root / "assets/intro.svg"
    result = cli("intro", "--profile", "CompleteDotTech", "--static", "--out", intro)
    assert result.returncode == 0, result.stdout + result.stderr
    ordinary = root / "ordinary"
    ordinary.mkdir()
    name = "synthetic-relocation-control"
    meta = capture(root / "ordinary.json", name)
    result = cli("--meta", meta, "--repo-dir", ordinary, "readme", "--mode", "scaffold",
                 "--badges", "local", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    hero = HERO.search((ordinary / "README.md").read_text(encoding="utf-8"))
    assert hero is not None and "docs/images/banner.png" in hero.group()
    legacy = hero.group().replace(name, "CompleteDotTech")
    return intro.read_bytes(), legacy.replace("\n", "\r\n").encode("utf-8")


def prepare(tmp_path, generated, before):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "README.md").write_bytes(before)
    intro = checkout / "assets/intro.svg"
    intro.parent.mkdir()
    intro.write_bytes(generated[0])
    return checkout, capture(tmp_path / "meta.json")


def upgrade(checkout, meta, variant):
    return cli("--meta", meta, "--repo-dir", checkout, "--format", "json", "readme",
               "--mode", "upgrade", "--variant", variant, "--badges", "local", "--write")


CASES = [
    pytest.param(
        b"> [!NOTE]\r\n> Synthetic callout.\n\n# Profile\r\n\n"
        b"Body section\r\n-----\r\n\nAuthored  body.  \n\n",
        b"\r\n\nAuthored  suffix.\t\r",
        id="mixed_suffix_separator",
    ),
    pytest.param(
        b"> [!NOTE]\r\n> Synthetic callout.\n\n# Profile\r\n\n"
        b"Body section\r-----\n\nAuthored  body.\t\r\n\n",
        b"\n\r\nAuthored  suffix.\t\r",
        id="lone_cr_heading_and_reverse_separator",
    ),
]


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("prefix,suffix", CASES)
def test_late_owned_legacy_relocation_preserves_complete_authored_bytes(
    tmp_path, generated, variant, prefix, suffix,
):
    before = BOM + prefix + generated[1] + suffix
    checkout, meta = prepare(tmp_path, generated, before)
    path = checkout / "README.md"
    result = upgrade(checkout, meta, variant)
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_bytes()
    assert after.startswith(BOM)
    assert after.index(b'src="assets/intro.svg"') < after.index(b"Body section")
    # BOM is an encoding marker; every authored byte on either side of the old
    # hero, including adjacent blank-line separators, must survive relocation.
    assert prefix in after, (variant, "complete authored prefix changed", before, after)
    assert prefix + suffix in after, (variant, "complete authored suffix or boundary changed", suffix, after)
    assert b"docs/images/banner.png" not in after
    second = upgrade(checkout, meta, variant)
    assert second.returncode == 0, second.stdout + second.stderr
    assert path.read_bytes() == after


@pytest.mark.parametrize("variant", ["G", "H"])
def test_unmarked_authored_art_with_mixed_newlines_is_unchanged(tmp_path, generated, variant):
    before = (BOM + b"> [!NOTE]\r\n> Synthetic callout.\n\n# Profile\r\n\n"
              b"![Authored art](assets/authored-art.svg)\r\n\nBody section\r\n-----"
              b"\r\n\nAuthored  suffix.\t\r")
    checkout, meta = prepare(tmp_path, generated, before)
    path = checkout / "README.md"
    result = upgrade(checkout, meta, variant)
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == before
    second = upgrade(checkout, meta, variant)
    assert second.returncode == 0, second.stdout + second.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("variant", ["G", "H"])
def test_edited_template_bootstrap_preserves_relocated_authored_bytes(tmp_path, generated, variant):
    # This is an edited template: its pristine digest describes the original
    # synthetic body, while the current body contains an authored replacement.
    digest = hashlib.sha256(b"Original synthetic template.\n").hexdigest()
    pristine = f"<!-- showcase:template-body:pristine sha256={digest} -->\r\n".encode()
    opening = b"<!-- showcase:template-body:start -->\r\n"
    edited = b"Authored  template.\t\r\n<!-- showcase:template-body:end -->\n\n"
    prefix = (b"> [!NOTE]\r\n> Synthetic callout.\n\n# Profile\r\n\n"
              b"Body section\r\n-----\r\n\nAuthored  body.  \n\n")
    suffix = b"\r\n\nAuthored  suffix.\t\r"
    before = BOM + prefix + opening + pristine + edited + generated[1] + suffix
    checkout, meta = prepare(tmp_path, generated, before)
    result = cli("--meta", meta, "--repo-dir", checkout, "--format", "json", "readme",
                 "--bootstrap", "--variant", variant, "--badges", "local", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "bootstrap:edited" in result.stdout
    after = (checkout / "README.md").read_bytes()
    assert after.startswith(BOM) and pristine not in after
    assert after.index(b'src="assets/intro.svg"') < after.index(b"Body section")
    expected_prefix = prefix + opening + edited
    assert expected_prefix in after
    assert expected_prefix + suffix in after, (variant, "bootstrap changed authored boundary", suffix, after)


@pytest.mark.parametrize("variant", ["G", "H"])
def test_cr_lf_fusion_at_removed_hero_requires_atomic_refusal(tmp_path, generated, variant):
    prefix = (b"> [!NOTE]\r\n> Synthetic callout.\n\n# Profile\r\n\n"
              b"Body section\r\n-----\r\n\nAuthored  body.  \r")
    suffix = b"\nAuthored suffix.\t\r"
    checkout, meta = prepare(tmp_path, generated, BOM + prefix + generated[1] + suffix)
    (checkout / "CONTRIBUTING.md").write_bytes(b"Synthetic contribution instructions.\t\r\n")

    def files():
        return {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    before = files()
    result = cli("--meta", meta, "--repo-dir", checkout, "--format", "json", "readme",
                 "--mode", "upgrade", "--variant", variant, "--badges", "local", "--write",
                 "--records", tmp_path / "records.json")
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:intro-order" in result.stdout
    assert files() == before
