"""Public CLI regressions for owned personal heroes sharing authored marker lines."""
import json
import re

import pytest

from conftest import run_cli
from test_personal_hero_order import BUILD_BADGE, LEGACY_HERO


ENDINGS = [pytest.param(b"\n", id="LF"), pytest.param(b"\r\n", id="CRLF"), pytest.param(b"\r", id="CR")]
SEAMS = ["prefix", "suffix", "both", "whitespace-only-prefix"]
BLOCK = re.compile(br"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->", re.DOTALL)


@pytest.fixture(scope="module")
def applicable_intro(tmp_path_factory):
    """Generate one applicable asset offline through the public CLI."""
    path = tmp_path_factory.mktemp("inline-seam-intro") / "intro.svg"
    result = run_cli("intro", "--profile", "CompleteDotTech", "--static", "--out", path)
    assert result.returncode == 0, result.stdout + result.stderr
    return path.read_bytes()


def source_parts(ending, seam, *, authored=False, badge=False):
    prefix = (BUILD_BADGE + ending * 2 if badge else b"") + b"# Synthetic profile" + ending * 2
    if seam == "whitespace-only-prefix":
        prefix = (BUILD_BADGE + ending * 2 if badge else b"") + b"  "
    elif seam in ("prefix", "both"):
        prefix += b"Authored  prefix.  "
    suffix = b"  Authored  suffix." if seam in ("suffix", "both") else b""
    suffix += ending * 2 + b"Authored  body.\t" + ending
    hero = LEGACY_HERO.replace(b"\n", ending)
    if authored:
        hero = hero.replace(b'width="100%"', b'width="840"')
    return prefix, hero, suffix


def fixture_repo(directory, source, intro):
    meta = directory / "meta.json"
    meta.write_text(json.dumps({
        "owner": "CompleteDotTech", "repo": "CompleteDotTech", "visibility": "public",
        "license": "MIT", "description": "Show synthetic public projects.",
        "topics": [], "files": [], "files_complete": True,
    }), encoding="utf-8")
    # Sparse provenance is valid; existing files expose partial writes and overwrites.
    files = {
        "README.md": source,
        "docs/images/.showcase.json": b'{"outputs":{}}\n',
        "docs/images/badges/authored.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>\n',
        "records.jsonl": b'{"id":"synthetic-existing-record"}\n',
        "CONTRIBUTING.md": b"Synthetic authored contribution notes.  \r\n",
    }
    if intro is not None:
        files["assets/intro.svg"] = intro
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return meta


def snapshot(directory):
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def upgrade(directory, meta, variant):
    return run_cli("--format", "json", "--meta", meta, "--repo-dir", directory,
                   "readme", "--mode", "upgrade", "--variant", variant, "--badges", "local",
                   "--records", directory / "records.jsonl", "--write")


def assert_atomic_refusal(result, directory, before, code):
    assert result.returncode == 4, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["result"] == "needs-input", report
    assert code in result.stdout, report
    assert snapshot(directory) == before, "Refusal must preserve every file and create no outputs"


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("ending", ENDINGS)
@pytest.mark.parametrize("seam", SEAMS)
@pytest.mark.parametrize("has_intro", [False, True], ids=["missing-intro", "applicable-intro"])
def test_owned_inline_hero_requires_intro_and_preserves_authored_seams(
        tmp_path, applicable_intro, variant, ending, seam, has_intro):
    prefix, hero, suffix = source_parts(ending, seam)
    meta = fixture_repo(tmp_path, prefix + hero + suffix, applicable_intro if has_intro else None)
    before = snapshot(tmp_path)
    result = upgrade(tmp_path, meta, variant)
    if not has_intro:
        assert_atomic_refusal(result, tmp_path, before, "needs-input:intro")
        return

    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    blocks = list(BLOCK.finditer(updated))
    assert len(blocks) == 1, updated
    block = blocks[0]
    assert b'src="assets/intro.svg"' in block.group(), updated
    assert b"docs/images/banner.png" not in updated
    assert "exempt" not in result.stdout, result.stdout
    assert updated[:block.start()].endswith(prefix), "Authored prefix must stay attached byte for byte"
    assert updated[block.end():].startswith(suffix), "Authored suffix must stay attached byte for byte"


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("ending", ENDINGS)
@pytest.mark.parametrize("seam", SEAMS)
def test_preceding_badge_and_inline_seam_refuse_atomically(
        tmp_path, applicable_intro, variant, ending, seam):
    prefix, hero, suffix = source_parts(ending, seam, badge=True)
    meta = fixture_repo(tmp_path, prefix + hero + suffix, applicable_intro)
    before = snapshot(tmp_path)
    result = upgrade(tmp_path, meta, variant)
    assert_atomic_refusal(result, tmp_path, before, "needs-input:intro-order")


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("ending", ENDINGS)
@pytest.mark.parametrize("section", [b"## Notes", b"# Notes"], ids=["H2-section", "second-H1"])
def test_body_section_inline_hero_refuses_atomically(tmp_path, applicable_intro, variant, ending, section):
    prefix, hero, suffix = source_parts(ending, "both")
    title = b"# Synthetic profile" + ending * 2
    prefix = prefix.replace(title, title + section + ending * 2, 1)
    meta = fixture_repo(tmp_path, prefix + hero + suffix, applicable_intro)
    before = snapshot(tmp_path)
    result = upgrade(tmp_path, meta, variant)
    assert_atomic_refusal(result, tmp_path, before, "needs-input:intro-order")


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("has_intro", [False, True], ids=["missing-intro", "applicable-intro"])
def test_modified_authored_hero_with_inline_seams_is_not_adopted(
        tmp_path, applicable_intro, variant, has_intro):
    prefix, hero, suffix = source_parts(b"\r\n", "both", authored=True)
    meta = fixture_repo(tmp_path, prefix + hero + suffix, applicable_intro if has_intro else None)
    before = snapshot(tmp_path)
    result = upgrade(tmp_path, meta, variant)
    if result.returncode != 0:
        assert_atomic_refusal(result, tmp_path, before, "needs-input:")
        return
    updated = (tmp_path / "README.md").read_bytes()
    assert prefix + hero + suffix in updated, "Modified authored hero and its seams must remain intact"
    assert b"assets/intro.svg" not in updated, "An available asset does not confer ownership"
