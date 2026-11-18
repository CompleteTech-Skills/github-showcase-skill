"""Image scans share the README parser's backtick escape and paragraph behavior."""
import json

import pytest
from conftest import run_cli

from ctshowcase.content import extract_links


@pytest.mark.parametrize("slashes,rendered", [(0, False), (1, True), (2, False), (3, True), (4, False)])
def test_code_backslash_parity(slashes, rendered):
    prefix = "\\" * slashes
    text = prefix + "`![Missing](docs/images/missing.png)" + prefix + "`"
    links = extract_links(text)
    assert any(x["target"] == "docs/images/missing.png" for x in links) is rendered


@pytest.mark.parametrize("text,missing", [
    (r"\`![Missing](docs/images/missing.png)\`", True),
    ("`![Missing](docs/images/missing.png)`", False),
    ("`\n![Missing](docs/images/missing.png)\n`", False),
    ("```markdown\n![Missing](docs/images/missing.png)\n```", False),
    ("<!-- ![Missing](docs/images/missing.png) -->", False),
    ("> ```markdown\n> ![Missing](docs/images/missing.png)\n> ```", False),
])
def test_cli_images_literal_and_real_code(tmp_path, text, missing):
    readme = tmp_path / "README.md"
    readme.write_text(text + "\n", encoding="utf-8")
    result = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    report = json.loads(result.stdout)
    assert result.returncode == (1 if missing else 0), report
    assert bool(report["images"]) is missing
    if missing:
        assert report["images"][0]["status"] == "missing"


def test_inline_code_cannot_cross_paragraph_boundary():
    text = "`example\n\n![Missing](docs/images/missing.png)\n\n`"
    assert any(x["target"] == "docs/images/missing.png" for x in extract_links(text))


def test_code_comment_opener_cannot_hide_later_image():
    text = "`<!--`\n\n![Missing](docs/images/missing.png)"
    assert any(x["target"] == "docs/images/missing.png" for x in extract_links(text))


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_cli_images_line_endings_and_reference_locations(tmp_path, ending):
    readme = tmp_path / "README.md"
    lines = [
        b"<!--", b"> ```", b"![Hidden](docs/images/comment.png)", b"-->",
        b"", b"> ```md", b"> ![Hidden](docs/images/fence.png)", b"> ```",
        b"", b"text ![Shot </span", b">](docs/images/quote.png)",
        b"", b"![Missing](docs/images/missing.png)", b"",
        b'![Again](docs/images/missing.png)', b"",
    ]
    authored = ending.join(lines)
    readme.write_bytes(authored)
    result = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["images"] == [{
        "path": "docs/images/missing.png",
        "referenced_from": ["README.md:13", "README.md:15"],
        "status": "missing",
    }]
    assert readme.read_bytes() == authored


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_cli_links_and_images_preserve_semantic_comment_spacing(tmp_path, ending):
    readme = tmp_path / "README.md"
    readme.write_bytes(ending.join([
        b"# Hello <!-- abc --> world",
        b"[Heading](#hello---world)",
        b"",
        b"<!-- inline -->[shot]: docs/images/reference.png",
        b"",
        b"```md",
        b"![Fenced](docs/images/fenced.png)",
        b"```",
        b"",
    ]))
    result = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)["findings"]
    assert [(row["target"], row["status"]) for row in findings] == [
        ("#hello---world", "ok"),
        ("docs/images/reference.png", "broken"),
    ]
    result = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["images"] == [{
        "path": "docs/images/reference.png",
        "referenced_from": ["README.md:4"],
        "status": "missing",
    }]


def test_cli_images_distinguishes_html_tokens_from_markdown(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        '<pre>\n'
        '`![Literal](docs/images/raw.png)`\n'
        '`![Remote](https://example.org/raw.png)`\n'
        '<img alt="Real HTML image" src="docs/images/html.png">\n'
        '</pre>\n'
        '\n'
        'Intro <span title="`![Literal](docs/images/attribute.png)`">'
        '![Real Markdown image](docs/images/markdown.png)</span>\n',
        encoding="utf-8",
    )
    result = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert [(row["path"], row["referenced_from"]) for row in report["images"]] == [
        ("docs/images/html.png", ["README.md:4"]),
        ("docs/images/markdown.png", ["README.md:7"]),
    ]
    assert report["remote"] == []


def test_cli_links_and_images_ignore_literal_html_reference_and_destination(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        '<pre>\n'
        '[Literal]: docs/images/raw-reference.png\n'
        '<img alt="HTML image" src="docs/images/html.png">\n'
        '</pre>\n'
        '\n'
        '[Visible]: docs/images/visible-reference.png\n'
        '\n'
        '![Alt](<span></span> docs/images/pretend.png)\n'
        '![Visible](<docs/images/visible-image.png> "Title")\n',
        encoding="utf-8",
    )
    result = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert result.returncode == 0, result.stderr
    assert [row["target"] for row in json.loads(result.stdout)["findings"]] == [
        "docs/images/html.png",
        "docs/images/visible-reference.png",
        "docs/images/visible-image.png",
    ]
    result = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    assert result.returncode == 1, result.stderr
    assert [(row["path"], row["referenced_from"]) for row in json.loads(result.stdout)["images"]] == [
        ("docs/images/html.png", ["README.md:3"]),
        ("docs/images/visible-image.png", ["README.md:9"]),
        ("docs/images/visible-reference.png", ["README.md:6"]),
    ]
