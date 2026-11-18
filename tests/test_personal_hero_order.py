"""Public CLI regression: an authored badge cannot precede a managed profile hero."""
import json
import re

import pytest

from conftest import run_cli


BUILD_BADGE = b"![Build](https://img.shields.io/badge/build-passing-green)"
LEGACY_HERO = (
    b'<!-- showcase:banner:start -->\n<p align="center">\n'
    b'  <img src="docs/images/banner.png" alt="CompleteDotTech by CompleteTech LLC" width="100%">\n'
    b'</p>\n<!-- showcase:banner:end -->'
)
PROFILE_HEADING = b"# Synthetic profile\n\n"
AUTHORED_BODY = b"Authored  double spaces.  \r\n\n\tIndented note.\n\n"
MODES = [
    pytest.param("upgrade", "G", (), id="upgrade-G"),
    pytest.param("upgrade", "H", (), id="upgrade-H"),
    pytest.param("upgrade", "J", (), id="upgrade-J"),
    pytest.param("header", "J", (), id="header"),
    pytest.param("upgrade", "J", ("--no-regroup",), id="no-regroup"),
]


@pytest.fixture(scope="module")
def applicable_intro(tmp_path_factory):
    """Use the offline public generator, rather than fabricating a valid SVG."""
    output = tmp_path_factory.mktemp("hero-order-intro") / "intro.svg"
    result = run_cli("intro", "--profile", "CompleteDotTech", "--static", "--out", output)
    assert result.returncode == 0, result.stdout + result.stderr
    return output.read_bytes()


def fixture_repo(tmp_path, source, intro=None):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({
        "owner": "CompleteDotTech", "repo": "CompleteDotTech", "visibility": "public",
        "license": "MIT", "description": "Show synthetic public projects.",
        "topics": [], "files": [], "files_complete": True,
    }), encoding="utf-8")
    (tmp_path / "README.md").write_bytes(source)
    # Existing state makes a partial refusal observable, including overwritten files.
    for name, data in {
        "docs/images/.showcase.json": (
            b'{"outputs":{"synthetic-fixture.svg":{"sha256":"'
            + b"0" * 64 + b'"}}}\n'
        ),
        "docs/images/badges/authored.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>\n',
        "records.jsonl": b'{"id":"synthetic-existing-record"}\n',
        "CONTRIBUTING.md": b"Synthetic authored contribution notes.  \r\n",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if intro is not None:
        path = tmp_path / "assets/intro.svg"
        path.parent.mkdir(parents=True)
        path.write_bytes(intro)
    return meta


def snapshot(directory):
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def generate(tmp_path, meta, mode, variant, options):
    return run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path,
                   "readme", "--mode", mode, "--variant", variant, *options,
                   "--badges", "local", "--records", tmp_path / "records.jsonl", "--write")


def assert_refusal_unchanged(result, tmp_path, before):
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:" in result.stdout + result.stderr, result.stdout + result.stderr
    assert snapshot(tmp_path) == before, "Refusal must preserve README, badges, sidecar and records"


def assert_intro_first(tmp_path, meta):
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    # This intentionally covers only our fixture's simple Markdown/HTML grammar.
    visible = re.sub(r"(?ms)^```[^\n]*\n.*?^```[^\n]*(?:\n|$)", "", text)
    first = re.search(r"!\[[^\]]*\]\([^\n]*\)|<img\b[^>]*>", visible)
    assert first is not None and 'src="assets/intro.svg"' in first.group(), text
    lint = run_cli("--meta", meta, "--repo-dir", tmp_path,
                   "lint", "readme", tmp_path / "README.md")
    assert lint.returncode in (0, 1), lint.stdout + lint.stderr
    failures = json.loads(lint.stdout)["fails"]
    assert not [failure for failure in failures if "D13" in failure], failures


@pytest.mark.parametrize("mode,variant,options", MODES)
@pytest.mark.parametrize("has_intro", [False, True], ids=["missing-intro", "applicable-intro"])
def test_authored_badge_before_managed_hero_requires_correct_order_or_atomic_refusal(
        tmp_path, applicable_intro, mode, variant, options, has_intro):
    prefix = BUILD_BADGE + b"\n\n"
    suffix = b"\n\n" + PROFILE_HEADING + AUTHORED_BODY
    source = prefix + LEGACY_HERO + suffix
    meta = fixture_repo(tmp_path, source, applicable_intro if has_intro else None)
    before = snapshot(tmp_path)
    result = generate(tmp_path, meta, mode, variant, options)
    if not has_intro or result.returncode != 0:
        assert_refusal_unchanged(result, tmp_path, before)
        return

    updated = (tmp_path / "README.md").read_bytes()
    assert_intro_first(tmp_path, meta)
    assert updated.count(BUILD_BADGE) == 1
    # Normal upgrade can rebuild the documented H1/header. Authored prose and
    # its significant whitespace must remain byte-identical wherever it moves.
    assert prefix in updated and AUTHORED_BODY in updated, "Authored badge/body bytes must survive"
    assert b"docs/images/banner.png" not in updated
    assert updated.count(b"<!-- showcase:banner:start -->") == 1
    if mode == "header" or "--no-regroup" in options:
        block = re.search(br"<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->",
                          updated, re.DOTALL)
        assert block is not None
        assert updated[:block.start()] == prefix, "In-place refresh cannot move authored text"
        assert updated[block.end():] == suffix


@pytest.mark.parametrize("mode,options", [
    pytest.param("header", (), id="header"),
    pytest.param("upgrade", ("--no-regroup",), id="no-regroup"),
])
def test_literal_fenced_badge_does_not_block_in_place_intro_refresh(
        tmp_path, applicable_intro, mode, options):
    prefix = b"```markdown\n" + BUILD_BADGE + b"\n```\n\n"
    suffix = b"\n\n" + PROFILE_HEADING + AUTHORED_BODY
    meta = fixture_repo(tmp_path, prefix + LEGACY_HERO + suffix, applicable_intro)
    result = generate(tmp_path, meta, mode, "J", options)
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    assert updated.startswith(prefix) and updated.endswith(suffix)
    assert b"docs/images/banner.png" not in updated
    assert_intro_first(tmp_path, meta)


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_authored_hero_is_never_adopted_to_satisfy_profile_order(tmp_path, applicable_intro, mode):
    authored = LEGACY_HERO.replace(b'width="100%"', b'width="840"')
    source = BUILD_BADGE + b"\n\n" + authored + b"\n\n" + PROFILE_HEADING + AUTHORED_BODY
    meta = fixture_repo(tmp_path, source, applicable_intro)
    before = snapshot(tmp_path)
    result = generate(tmp_path, meta, mode, "J", ())
    if result.returncode != 0:
        assert_refusal_unchanged(result, tmp_path, before)
        return
    updated = (tmp_path / "README.md").read_bytes()
    assert authored in updated and AUTHORED_BODY in updated
    assert updated.count(BUILD_BADGE) == 1
    assert b"assets/intro.svg" not in updated, "An applicable asset does not confer ownership of authored art"
