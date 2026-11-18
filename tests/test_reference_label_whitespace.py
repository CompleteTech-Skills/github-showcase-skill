"""Reference matching preserves raw label characters; exercise actual lint CLI safety checks."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ctshowcase import readmelint

ROOT = Path(__file__).resolve().parents[1]
MISSING = "R7 local image does not resolve: docs/images/missing.png"
BAD_COLOUR = "R7 off-palette badge colour FF0000"


def cli_fails(tmp_path, source, ending):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github", "files": ["README.md"]}),
                    encoding="utf-8")
    path = tmp_path / "README.md"
    path.write_bytes(source.replace("\n", ending).encode("utf-8"))
    run = subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "--meta", str(meta),
                          "--repo-dir", str(tmp_path), "lint", "readme", str(path)],
                         capture_output=True, encoding="utf-8", check=False)
    assert run.returncode == 1 and not run.stderr, run
    return json.loads(run.stdout)["fails"]


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])
@pytest.mark.parametrize("char", ["\u00a0", "\x85", "\u2003", "\x1c", "\v", "\f"])
@pytest.mark.parametrize("case", ["collision-local", "collision-colour", "nonmatching", "exact", "solo"])
def test_literal_label_whitespace_cli(tmp_path, ending, char, case):
    # VT/FF are significant too: native cmark-gfm does NOT fold them as label whitespace.
    label = f"a{char}b"
    if case.startswith("collision"):
        target = "docs/images/missing.png" if case == "collision-local" else "https://img.shields.io/badge/type-bad-FF0000"
        source = f"![Shot][a b]\n\n[{label}]: https://example.org/good.png\n[a b]: {target}\n"
    elif case == "nonmatching":
        source = f"![Shot][a b]\n\n[{label}]: docs/images/missing.png\n"
    else:
        label = char if case == "solo" else label
        source = f"![Shot][{label}]\n\n[{label}]: docs/images/missing.png\n"
    fails = cli_fails(tmp_path, source, ending)
    assert (MISSING in fails) == (case in ("collision-local", "exact", "solo")), fails
    assert any(BAD_COLOUR in fail for fail in fails) == (case == "collision-colour"), fails


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])
@pytest.mark.parametrize("space", [" ", "\t", "\n", " \t\n "])
@pytest.mark.parametrize("usage", ["![Shot][ A B ]", "![a b][]", "![a b]"])
def test_ascii_label_whitespace_cli(tmp_path, ending, space, usage):
    source = f"{usage}\n\n[ \ta{space}b\t ]: docs/images/missing.png\n"
    assert MISSING in cli_fails(tmp_path, source, ending)


@pytest.mark.parametrize("usage", ["![a\u00a0b][]", "![a\u00a0b]", "![Shot][a\u00a0b]"])
def test_literal_labels_in_all_reference_forms_cli(tmp_path, usage):
    assert MISSING in cli_fails(tmp_path, usage + "\n\n[a\u00a0b]: docs/images/missing.png\n", "\n")


@pytest.mark.parametrize("label,definition,resolves", [
    (r"a\*b", r"a\*b", True),
    (r"a\*b", "a*b", False),
    ("a&amp;b", "a&b", False),
    ("Straße", "STRASSE", True),
    ("a" * 999, "A" * 999, True),
    ("a" * 1000, "A" * 1000, False),
])
def test_matching_keeps_raw_escape_entity_casefold_and_length_contract(label, definition, resolves):
    doc = f"![Shot][{label}]\n\n[{definition}]: docs/images/missing.png\n"
    images = readmelint._images(readmelint._outside_code(doc), doc)
    assert images == ([("Shot", "docs/images/missing.png")] if resolves else [])
