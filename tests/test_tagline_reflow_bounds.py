"""Bounded offline CLI checks of synthetic captures, with independent receipts.

The large local metadata value exercises the accepted file input; it makes no
claim about the length of About text accepted by GitHub. No formatter or network
is involved, and every receipt is constructed without implementation helpers.
"""
import hashlib
import json
import subprocess
import sys

import pytest

from conftest import ROOT, meta_dict

R2 = "R2 bold tagline must equal the GitHub description"
CLI_TIMEOUT = 20


def write_case(tmp_path, payload, description, ending="\n"):
    repo = tmp_path / "repo"
    repo.mkdir()
    meta = tmp_path / "capture.json"
    meta.write_text(json.dumps(meta_dict(description=description)), encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    source = (
        "# Synthetic Northwind Tool\n\n"
        "<!-- showcase:tagline:start -->\n"
        f"<!-- showcase:tagline:generated sha256={digest} -->\n"
        f"{payload}\n"
        "<!-- showcase:tagline:end -->\n\n"
        "## Usage\n\nKeep  two spaces, a tab\there, and café.  \n"
    )
    path = repo / "README.md"
    path.write_bytes(source.replace("\n", ending).encode("utf-8"))
    return path, meta


def lint(path, meta):
    original_readme = path.read_bytes()
    original_meta = meta.read_bytes()
    try:
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/showcase.py"), "--meta", str(meta),
                 "--repo-dir", str(path.parent), "lint", "readme", str(path), "--variant", "A"],
                cwd=path.parent, capture_output=True, text=True, encoding="utf-8", timeout=CLI_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(f"offline tagline lint exceeded the generous {CLI_TIMEOUT}s execution bound")
    finally:
        assert path.read_bytes() == original_readme
        assert meta.read_bytes() == original_meta
    assert result.returncode in (0, 1), result.stdout + result.stderr
    assert not result.stderr, result.stderr
    report = json.loads(result.stdout)
    assert isinstance(report["fails"], list), report
    return report["fails"]


def test_cli_large_captured_whitespace_completes_within_bound(tmp_path):
    path, meta = write_case(tmp_path, "**word end**", "word end")
    assert R2 not in lint(path, meta)
    # A small README and a large whitespace run in the independently supplied
    # capture isolate metadata reflow from Markdown document size. The generous
    # timeout catches unbounded work without depending on timing ratios.
    meta.write_text(json.dumps(meta_dict(description="word" + " " * 131_072 + "end")), encoding="utf-8")
    assert R2 not in lint(path, meta)


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])
@pytest.mark.parametrize("separator,matches", [
    (" ", True),
    ("\n", True),
    ("\n\n", False),
    ("\n \t\n", False),
    ("  \n", False),
    ("\\\n", False),
], ids=["space", "soft-wrap", "paragraph", "blank-paragraph", "two-space-break", "backslash-break"])
def test_cli_reflow_preserves_paragraphs_and_hard_breaks(tmp_path, ending, separator, matches):
    path, meta = write_case(tmp_path, "**word" + separator + "end**", "word end", ending)
    # A valid ownership receipt does not erase Markdown paragraph or hard-break
    # semantics. Only an ordinary space or soft line wrap preserves R2.
    assert (R2 not in lint(path, meta)) is matches
