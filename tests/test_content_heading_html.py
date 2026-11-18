"""Raw HTML boundaries must survive the heading inventory's comment projection."""
import json

import pytest

from conftest import run_cli
from ctshowcase.content import headings


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_cli_heading_inventory_excludes_raw_html_candidates(tmp_path, ending):
    lines = [
        b"<div>",
        b"<!-- marker --># Inline Fake",
        b"# Raw<!-- marker -->Fake",
        b"Raw Setext",
        b"===",
        b'<h2 id="explicit-html">HTML Heading</h2>',
        b'<a name="named-anchor"></a>',
        b"</div>",
        b"",
        b"# Real<!-- marker -->Heading",
        b"",
        b"Real<!-- marker -->Setext",
        b"---",
        b"",
        b"# `Code` Heading",
        b"",
        b"[Inline](#inline-fake)",
        b"[Raw](#raw-fake)",
        b"[Setext](#raw-setext)",
        b"[Real](#real-heading)",
        b"[Real setext](#real-setext)",
        b"[HTML](#html-heading)",
        b"[ID](#explicit-html)",
        b"[Name](#named-anchor)",
        b"[Code](#code-heading)",
        b"",
    ]
    path = tmp_path / "README.md"
    original = ending.join(lines)
    path.write_bytes(original)
    result = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert headings(original.decode("utf-8")) == [
        {"line": 6, "text": "HTML Heading", "slug": "html-heading"},
        {"line": 10, "text": "Real Heading", "slug": "real-heading"},
        {"line": 12, "text": "Real Setext", "slug": "real-setext"},
        {"line": 15, "text": "Code Heading", "slug": "code-heading"},
    ]
    assert [(row["line"], row["target"], row["status"]) for row in report["findings"]] == [
        (17, "#inline-fake", "broken"),
        (18, "#raw-fake", "broken"),
        (19, "#raw-setext", "broken"),
        (20, "#real-heading", "ok"),
        (21, "#real-setext", "ok"),
        (22, "#html-heading", "ok"),
        (23, "#explicit-html", "ok"),
        (24, "#named-anchor", "ok"),
        (25, "#code-heading", "ok"),
    ]
    assert path.read_bytes() == original


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_cli_setext_requires_markdown_title_and_underline(tmp_path, ending):
    lines = [
        b"<!-- marker -->False Title",
        b"===",
        b"",
        b"False Underline",
        b"<!-- marker -->---",
        b"",
        b"True<!-- inline -->Title",
        b"===",
        b"",
        b"[First](#false-title)",
        b"[Second](#false-underline)",
        b"[Control](#true-title)",
        b"",
    ]
    path = tmp_path / "README.md"
    original = ending.join(lines)
    path.write_bytes(original)
    result = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert headings(original.decode("utf-8")) == [
        {"line": 7, "text": "True Title", "slug": "true-title"},
    ]
    assert [(row["line"], row["target"], row["status"]) for row in report["findings"]] == [
        (10, "#false-title", "broken"),
        (11, "#false-underline", "broken"),
        (12, "#true-title", "ok"),
    ]
    assert path.read_bytes() == original


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
@pytest.mark.parametrize("opener,closer", [
    (b"<pre>", b"</pre>"),
    (b"<?instruction", b"?>"),
    (b"<!DECLARATION", b">"),
    (b"<![CDATA[", b"]]>"),
    (b"<custom-element>", b"</custom-element>"),
])
def test_cli_other_raw_html_blocks_do_not_add_heading_duplicates(tmp_path, ending, opener, closer):
    # A literal '>' would terminate a declaration block before its closer.
    lines = [opener, b"# Same Heading", b"Same Setext", b"---", closer,
             b"", b"# Same<!-- marker -->Heading", b"", b"Same Setext", b"---", b"",
             b"[ATX](#same-heading)", b"[Setext](#same-setext)", b""]
    path = tmp_path / "README.md"
    original = ending.join(lines)
    path.write_bytes(original)
    result = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert headings(original.decode("utf-8")) == [
        {"line": 7, "text": "Same Heading", "slug": "same-heading"},
        {"line": 9, "text": "Same Setext", "slug": "same-setext"},
    ]
    assert [(row["line"], row["target"], row["status"]) for row in report["findings"]] == [
        (12, "#same-heading", "ok"), (13, "#same-setext", "ok"),
    ]
    assert path.read_bytes() == original


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
@pytest.mark.parametrize("opener,closer", [
    (b"<textarea>", (b"</textarea>",)),
    (b"<script>", (b"</script>",)),
    (b'<div title="', (b'">', b"</div>")),
])
def test_literal_html_heading_spellings_do_not_consume_real_heading_slugs(tmp_path, ending, opener, closer):
    lines = [opener, b"# Literal <h2>Same</h2>", *closer, b"", b"# Same", b"",
             b"[Real](#same)", b"[Duplicate](#same-1)", b"[Literal](#literal-same)", b""]
    readme = tmp_path / "README.md"
    original = ending.join(lines)
    readme.write_bytes(original)

    result = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")

    assert result.returncode == 0, result.stdout + result.stderr
    findings = json.loads(result.stdout)["findings"]
    assert [(row["line"], row["target"], row["status"]) for row in findings] == [
        (lines.index(b"[Real](#same)") + 1, "#same", "ok"),
        (lines.index(b"[Duplicate](#same-1)") + 1, "#same-1", "broken"),
        (lines.index(b"[Literal](#literal-same)") + 1, "#literal-same", "broken"),
    ]
    assert readme.read_bytes() == original


def test_cli_html_heading_uses_the_live_closer_outside_quoted_attributes(tmp_path):
    source = ('<h2 title="Literal </h2> > text">Real<!-- marker -->HTML'
              '<span title="Ignore </h2> here"></span></h2>\n\n'
              '[Real](#real-html)\n')
    readme = tmp_path / "README.md"
    readme.write_text(source, encoding="utf-8")
    result = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert result.returncode == 0, result.stdout + result.stderr
    assert headings(source) == [{"line": 1, "text": "Real HTML", "slug": "real-html"}]
    finding, = json.loads(result.stdout)["findings"]
    assert finding["target"] == "#real-html" and finding["status"] == "ok"
