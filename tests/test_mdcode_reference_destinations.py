"""Native-adjudicated full-reference precedence and destination escape regressions."""
import base64
import json
import shutil
import subprocess
import sys

import pytest

from conftest import EX, ROOT, run_cli
from ctshowcase import mdcode, readme, readmelint

LABEL = "la`bel"
DEFINITION = f"\n\n[{LABEL}]: outer.png\n"
EXAMPLE = "`<!-- showcase:tagline:start -->**KEEP CODE EXAMPLE**<!-- showcase:tagline:end -->`"
REAL = "<!-- showcase:tagline:start -->**REAL MARKER**<!-- showcase:tagline:end --> lone`"


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(EX / "repos/northwind-support-triage-agent", repo)
    meta = EX / "meta/northwind-support-triage-agent.json"
    args = ("--meta", meta, "--repo-dir", repo)
    result = run_cli(*args, "readme", "--mode", "scaffold", "--variant", "C", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    (repo / "docs/images").mkdir(parents=True, exist_ok=True)
    (repo / "docs/images/banner.png").write_bytes(b"synthetic existence fixture")
    (repo / "outer.png").write_bytes(b"synthetic existence fixture")
    return repo, args


def insert(checkout, source, ending="\n", remove_tagline=False):
    repo, args = checkout
    path = repo / "README.md"
    text = path.read_text(encoding="utf-8")
    if remove_tagline:
        for block in readme.find_blocks(readme.MARK, text):
            if block.group(1) == "tagline":
                text = text[:block.start()] + text[block.end():]
                break
    text = text.replace("## License", source + "\n## License", 1).replace("\n", ending)
    path.write_bytes(text.encode("utf-8"))
    return path, args


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("prefix", ["", "!"])
def test_cli_full_reference_nested_description_keeps_following_code(checkout, ending, prefix):
    # cmark-gfm: outer image/link followed by code, never the Shot image.
    source = f"{prefix}[a [nested] text][{LABEL}] `![Shot](docs/images/missing.png)`" + DEFINITION
    path, args = insert(checkout, source, ending)
    result = run_cli(*args, "lint", "readme", path, "--variant", "C")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["fails"] == []


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_cli_marker_example_survives_refresh(checkout, mode):
    source = f"[a [nested] text][{LABEL}] {EXAMPLE}" + DEFINITION
    path, args = insert(checkout, source, remove_tagline=True)
    result = run_cli(*args, "readme", "--mode", mode, "--variant", "C", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert source.encode() in path.read_bytes()


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_cli_real_marker_after_nested_description_remains_active(checkout, mode):
    source = f"[a [nested] text][{LABEL}] {REAL}" + DEFINITION
    path, args = insert(checkout, source, remove_tagline=True)
    before = path.read_bytes()
    result = run_cli(*args, "readme", "--mode", mode, "--variant", "C", "--write")
    if mode == "upgrade":
        # Refreshing the active marker would lose its authored line prefix; the shrink guard must refuse.
        assert result.returncode == 1, result.stdout + result.stderr
        assert "readme-shrink" in json.loads(result.stdout)["logs"]
        assert path.read_bytes() == before
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert b"**REAL MARKER**" not in path.read_bytes()


@pytest.mark.parametrize("example,expected", [(EXAMPLE, []), (REAL, ["**REAL MARKER**"])])
def test_metadata_cli_uses_same_full_reference_marker_precedence(tmp_path, example, expected):
    source = f"[a [nested] text][{LABEL}] {example}" + DEFINITION
    encoded = {"path": "README.md", "content": base64.b64encode(source.encode()).decode()}
    full = "Northwind-Trading-Co/support-triage-agent"
    responses = {
        "repos/" + full: {"owner": {"login": "Northwind-Trading-Co"}, "name": "support-triage-agent",
                          "visibility": "public", "template_repository": {"full_name": "Northwind-Trading-Co/template"}},
        "repos/" + full + "/readme": encoded,
        "repos/Northwind-Trading-Co/template/readme": encoded,
    }
    fixture = tmp_path / "responses.json"
    fixture.write_text(json.dumps(responses), encoding="utf-8")
    # Replace transport only; execute production CLI parsing, metadata capture and output in a fresh process.
    script = ("import json,runpy,sys; from pathlib import Path; "
              "sys.path.insert(0,sys.argv[1]); from ctshowcase import meta; "
              "responses=json.loads(Path(sys.argv[2]).read_text()); "
              "meta._gh=lambda path,**kwargs: responses.get(path); "
              "sys.argv=[sys.argv[3], 'meta', '--from-gh', sys.argv[4]]; "
              "runpy.run_path(sys.argv[0],run_name='__main__')")
    result = subprocess.run([sys.executable, "-c", script, str(ROOT / "scripts"), str(fixture),
                             str(ROOT / "scripts/showcase.py"), full], cwd=tmp_path,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["template_taglines"] == expected


@pytest.mark.parametrize("form", ["inline", "reference"])
def test_cli_unicode_symbol_escape_cannot_alias_existing_file(checkout, form):
    repo, _ = checkout
    (repo / "x§y").write_bytes(b"synthetic wrong-name control")
    source = r"![Shot](x\§y)" if form == "inline" else "![Shot][ref]\n\n[ref]: x\\§y\n"
    path, args = insert(checkout, source)
    result = run_cli(*args, "lint", "readme", path, "--variant", "C")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "R7 local image does not resolve: x\\§y" in json.loads(result.stdout)["fails"]


@pytest.mark.parametrize("form", ["inline", "reference"])
@pytest.mark.parametrize("written,target", [
    (r"x\&amp;y", "x&y"), ("x&amp;y", "x&y"),
    ("x&copy.png", "x&copy.png"), (r"x&copy\;png", "x&copy;png"),
    (r"x&amp\;y", "x&amp;y"),
])
def test_cli_destination_entities_follow_cmark_gfm(checkout, form, written, target):
    repo, _ = checkout
    (repo / target).write_bytes(b"synthetic existence fixture")
    source = f"![Shot](<{written}>)" if form == "inline" else f"![Shot][ref]\n\n[ref]: <{written}>\n"
    path, args = insert(checkout, source)
    result = run_cli(*args, "lint", "readme", path, "--variant", "C")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["fails"] == []


@pytest.mark.parametrize("form", ["inline", "reference"])
@pytest.mark.parametrize("written,target", [(r"x\!y", "x!y"), ("x!y", "x!y"),
    (r"x\§y", r"x\§y"), ("x§y", "x§y"), (r"x\\§y", r"x\§y"),
    (r"x\ay", r"x\ay"), ("x&amp;y", "x&y"), (r"x\&amp;y", "x&y")])
def test_ascii_punctuation_escape_grammar_shared_by_destinations(form, written, target):
    source = f"![Shot](<{written}>)" if form == "inline" else f"![Shot][ref]\n\n[ref]: <{written}>\n"
    assert readmelint._images(readmelint._outside_code(source), source) == [("Shot", target)]


@pytest.mark.parametrize("source,accepted", [
    ("[a [nested] text][ref]", True),
    ("[a [nested] text][]", False),
    ("[a [nested] text]", False),
    ("[ref][]", True),
    ("[ref]", True),
    ("[a [nested] text][missing]", False),
    ("[a [nested] text][bad[label]", False),
])
def test_full_collapsed_shortcut_and_invalid_labels(source, accepted):
    close = source.index("]", source.index("text")) if "text" in source else source.index("]")
    assert (mdcode._reference_form(source, 0, close, len(source), {"ref"}) is not None) is accepted


def test_real_nested_link_still_deactivates_outer_full_reference():
    source = "[outer [inner][ref]][other`label] `![Shot](missing.png)`\n\n[ref]: x\n[other`label]: y\n"
    images = readmelint._images(readmelint._outside_code(source), source)
    assert ("Shot", "missing.png") in images
    assert source.index("][other") not in mdcode._active_openers(source)


def test_full_reference_offsets_and_work_stay_bounded():
    counts = []
    for count in (100, 200):
        source = (f"[a [nested] text][{LABEL}] `example` " * count) + DEFINITION.replace("\n", "\r\n")
        mdcode._accepted_inline.cache_clear()
        mdcode._OPENER_STEPS = 0
        spans = mdcode.inline_code_spans(source)
        assert len(spans) == count
        assert all(source[start:end] == "`example`" for start, end in spans)
        assert len(mdcode._outside_code(source)) == len(source)
        counts.append(mdcode._OPENER_STEPS)
    assert counts[1] <= counts[0] * 2.1


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
def test_nested_reference_marker_projection_keeps_source_offsets(ending):
    source = (f"[a [nested] text][{LABEL}] {EXAMPLE}" + DEFINITION).replace("\n", ending)
    projection = mdcode._marker_projection(source)
    assert len(projection) == len(source)
    assert all(projection[i] == ch for i, ch in enumerate(source) if ch in "\r\n")
    assert mdcode.find_blocks(readme.MARK, source) == []
    assert source[mdcode.inline_code_spans(source)[0][0]:mdcode.inline_code_spans(source)[0][1]] == EXAMPLE


@pytest.mark.parametrize("source", [
    "100. > ![Shot](\n     > docs/images/missing.png\n     > )",
    "- - > ![Shot](docs/images/missing.png\n    > \"title\")",
    "- > ![Shot](\n\t> docs/images/missing.png\n\t> )",
    "> ![Shot][foo\n> bar]\n\n[foo bar]: docs/images/missing.png",
    "- - > ![Shot][foo\n    > bar]\n\n[foo bar]: docs/images/missing.png",
])
def test_cli_containers_preserve_multiline_images(checkout, source):
    path, args = insert(checkout, source)
    result = run_cli(*args, "lint", "readme", path, "--variant", "C")
    assert "R7 local image does not resolve: docs/images/missing.png" in json.loads(result.stdout)["fails"]


@pytest.mark.parametrize("source", [
    "> \\![Shot][foo\n> bar]\n\n[foo bar]: docs/images/missing.png",
    "- - > `![Shot](\n    > docs/images/missing.png)`",
    "> ![Shot][foo\n> bar]\n\n[foo baz]: docs/images/missing.png",
    "- - > ```\n    > ![Shot](docs/images/missing.png)\n    > ```",
])
def test_cli_containers_keep_literal_images_inert(checkout, source):
    path, args = insert(checkout, source)
    result = run_cli(*args, "lint", "readme", path, "--variant", "C")
    assert not any("local image" in f for f in json.loads(result.stdout)["fails"])


def test_cli_multiline_reference_precedence_keeps_following_code(checkout):
    source = "> [outer [inner][foo\n> bar]](x`y) ![Shot](docs/images/missing.png)\n\n[foo bar]: target"
    path, args = insert(checkout, source)
    result = run_cli(*args, "lint", "readme", path, "--variant", "C")
    assert "R7 local image does not resolve: docs/images/missing.png" in json.loads(result.stdout)["fails"]


def test_deep_list_definition_peeling_memory_is_linear():
    import tracemalloc

    peaks = []
    for depth in (1000, 4000):
        source = "- " * depth + "x\n"
        tracemalloc.start()
        mdcode._peel_definition_containers(source, list(source))
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    assert peaks[1] < peaks[0] * 6, peaks
    assert peaks[1] < 2_000_000, peaks
