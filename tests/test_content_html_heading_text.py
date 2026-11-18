"""HTML heading text keeps its source context when local anchors are checked."""
import json

import pytest

from conftest import run_cli
from ctshowcase.content import headings


ENDINGS = [b"\n", b"\r\n", b"\r"]


def check_links(tmp_path, lines, ending, strict):
    """Exercise the public CLI and its saved report without normalizing the input."""
    root = tmp_path / "repo"
    root.mkdir()
    readme = root / "README.md"
    original = ending.join(line.encode("utf-8") for line in lines)
    readme.write_bytes(original)
    report_path = tmp_path / "links.json"
    flags = ["--strict"] if strict else []
    result = run_cli("--repo-dir", root, "content", "links", "README.md",
                     "--report", report_path, *flags)
    assert readme.read_bytes() == original
    assert report_path.is_file(), result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert report["action"] == "links"
    return result, report, original.decode("utf-8")


@pytest.mark.parametrize("ending", ENDINGS, ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("strict", [False, True], ids=["default", "strict"])
@pytest.mark.parametrize("body,slug", [
    ("    Indented Title", "indented-title"),
    ("\tTabbed Title", "tabbed-title"),
    ("```Literal Title", "literal-title"),
], ids=["four-spaces", "tab", "literal-backticks"])
def test_cli_html_heading_inner_text_is_not_a_new_markdown_block(tmp_path, ending, strict, body, slug):
    # These characters occur inside an already-open HTML heading. They cannot
    # open an indented Markdown code block or a fenced Markdown code block.
    lines = ["# Synthetic Guide", "", f"<h2>{body}</h2>", "",
             f"[Heading](#{slug})", ""]
    result, report, source = check_links(tmp_path, lines, ending, strict)

    assert [(row["line"], row["target"], row["status"]) for row in report["findings"]] == [
        (5, f"#{slug}", "ok"),
    ]
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["result"] == "pass"
    assert report["broken"] == 0
    assert report["proposals"] == []
    # Check the inventory's location separately from the target's status. Its
    # exact punctuation display is not needed to establish anchor resolution.
    assert [(row["line"], row["slug"]) for row in headings(source)] == [
        (1, "synthetic-guide"), (3, slug),
    ]


@pytest.mark.parametrize("ending", ENDINGS, ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("strict", [False, True], ids=["default", "strict"])
@pytest.mark.parametrize("separator", ["\f", "\v"], ids=["formfeed", "vertical-tab"])
def test_cli_html_heading_accepts_shared_html_tag_separators(tmp_path, ending, strict, separator):
    # Formfeed and vertical tab separate the tag name from an attribute under
    # the existing HTML grammar. Neither is a physical document line ending.
    lines = ["# Synthetic Guide", "", f'<h2{separator}class="synthetic">Visible Title</h2>', "",
             "[Visible](#visible-title)", "", "## Following Heading", "",
             "[Following](#following-heading)", ""]
    result, report, source = check_links(tmp_path, lines, ending, strict)

    assert [(row["line"], row["target"], row["status"]) for row in report["findings"]] == [
        (5, "#visible-title", "ok"), (9, "#following-heading", "ok"),
    ]
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["result"] == "pass"
    assert report["broken"] == 0
    assert report["proposals"] == []
    assert headings(source) == [
        {"line": 1, "text": "Synthetic Guide", "slug": "synthetic-guide"},
        {"line": 3, "text": "Visible Title", "slug": "visible-title"},
        {"line": 7, "text": "Following Heading", "slug": "following-heading"},
    ]


@pytest.mark.parametrize("ending", ENDINGS, ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("strict", [False, True], ids=["default", "strict"])
def test_cli_heading_text_controls_keep_live_html_and_literal_contexts_distinct(tmp_path, ending, strict):
    lines = [
        "<h2>Alpha<!-- real comment -->Beta</h2>",
        "",
        "<h2><em>Nested <strong>HTML</strong></em></h2>",
        "",
        '<h2 title="Literal </h2> > text">Real<!-- marker -->HTML'
        '<span title="Ignore </h2> here"></span></h2>',
        "",
        "`<h2>Hidden Inline</h2>`",
        "",
        "<script>",
        "# Literal <h2>Hidden Script</h2>",
        "</script>",
        "",
        '<div title="',
        "# Literal <h2>Hidden Attribute</h2>",
        '">',
        "</div>",
        "",
        "# Visible Markdown",
        "",
        "[Comment](#alpha-beta)",
        "[Nested](#nested-html)",
        "[Quoted closer](#real-html)",
        "[Inline literal](#hidden-inline)",
        "[Script literal](#hidden-script)",
        "[Attribute literal](#hidden-attribute)",
        "[Markdown](#visible-markdown)",
        "",
    ]
    result, report, source = check_links(tmp_path, lines, ending, strict)

    assert [(row["line"], row["target"], row["status"]) for row in report["findings"]] == [
        (20, "#alpha-beta", "ok"),
        (21, "#nested-html", "ok"),
        (22, "#real-html", "ok"),
        (23, "#hidden-inline", "broken"),
        (24, "#hidden-script", "broken"),
        (25, "#hidden-attribute", "broken"),
        (26, "#visible-markdown", "ok"),
    ]
    assert result.returncode == (1 if strict else 0), result.stdout + result.stderr
    assert report["result"] == ("fail" if strict else "warn")
    assert report["broken"] == 3
    assert headings(source) == [
        {"line": 1, "text": "Alpha Beta", "slug": "alpha-beta"},
        {"line": 3, "text": "Nested HTML", "slug": "nested-html"},
        {"line": 5, "text": "Real HTML", "slug": "real-html"},
        {"line": 18, "text": "Visible Markdown", "slug": "visible-markdown"},
    ]
