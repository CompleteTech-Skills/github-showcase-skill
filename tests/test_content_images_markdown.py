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


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_cli_images_excludes_reference_definitions_in_raw_html(tmp_path, ending):
    readme = tmp_path / "README.md"
    authored = ending.join([
        b"<pre>",
        b"[Literal]: docs/images/pre-example.png",
        b"</pre>",
        b"",
        b"<div>",
        b"[Literal]: docs/images/div-example.png",
        b"</div>",
        b"",
        b"[shot]: <docs/images/reference.png>",
        b"",
        b"![Shot][shot]",
        b"![Real](docs/images/real.png)",
        b'<img src="docs/images/html.png" alt="HTML image">',
        b"",
        b"<pre<!-- comment -->>",
        b"",
        b"[visible]: docs/images/visible.png",
        b"",
        b"![Visible][visible]",
        b"",
        b'Intro <span title="example',
        b"[Literal]: docs/images/attribute-example.png",
        b'">Text</span>',
        b"",
    ])
    readme.write_bytes(authored)

    result = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["images"] == [
        {"path": "docs/images/html.png", "referenced_from": ["README.md:13"], "status": "missing"},
        {"path": "docs/images/real.png", "referenced_from": ["README.md:12"], "status": "missing"},
        {"path": "docs/images/reference.png", "referenced_from": ["README.md:9"], "status": "missing"},
        {"path": "docs/images/visible.png", "referenced_from": ["README.md:17"], "status": "missing"},
    ]
    assert report["remote"] == []
    assert readme.read_bytes() == authored

    links = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert links.returncode == 0, links.stderr
    assert {row["target"] for row in json.loads(links.stdout)["findings"]} == {
        "docs/images/html.png", "docs/images/real.png", "docs/images/reference.png",
        "docs/images/visible.png",
    }


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_image_and_link_reports_use_live_html_attributes_and_no_masked_destinations(tmp_path, ending):
    text = (
        '# Synthetic documentation\n\n'
        'Intro <span title="example <img src=\'docs/images/inline-example.png\'>">Text</span>.\n\n'
        '<span title="example on the next line\n<img src=\'docs/images/multiline-example.png\'>">Text</span>\n\n'
        '<img title="example src=\'docs/images/title-example.png\'" src="docs/images/real.png">\n\n'
        '<source\n srcset="docs/images/source.png 1x, docs/images/retina.png 2x">\n\n'
        '[Malformed]: <span>.png\n\n'
        '[Also malformed]: <span></span> docs/images/pretend.png\n\n'
        '[Valid]: <docs/images/reference.png>\n\n'
        'Example: `<img src="docs/images/code-example.png">`.\n\n'
        '[Guide](guide.md "Example: <img src=\'docs/images/title-code.png\'>")\n\n'
        '<script>\nconst example = "<img src=\'docs/images/raw-text.png\'>";\n</script>\n'
    )
    source = text.replace("\n", ending).encode()
    readme = tmp_path / "README.md"
    readme.write_bytes(source)
    targets = {"docs/images/real.png": 8, "docs/images/source.png": 10, "docs/images/reference.png": 17}

    links = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert links.returncode == 0, links.stdout + links.stderr
    assert {row["target"]: row["line"] for row in json.loads(links.stdout)["findings"]} == {
        **targets, "guide.md": 21,
    }

    images = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    assert images.returncode == 1, images.stdout + images.stderr
    assert {row["path"]: row["referenced_from"] for row in json.loads(images.stdout)["images"]} == {
        target: [f"README.md:{line}"] for target, line in targets.items()
    }
    assert readme.read_bytes() == source


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_cli_reference_targets_never_include_or_truncate_html_masks(tmp_path, ending):
    readme = tmp_path / "README.md"
    authored = ending.join([
        b"[prefix]: <span>docs/images/prefix.png",
        b"",
        b"[interior]: docs/images/interior.png<span>.png invalid title",
        b"",
        b"[angle]: <docs/images/angle<span>.png>",
        b"",
        b"[<span>label]: docs/images/label.png invalid title",
        b"",
        b"[<span>valid]: docs/images/accepted-label.png",
        b"",
        b"[real]: <docs/images/reference.png>",
        b"",
        b"![Real](docs/images/real.png)",
        b'<img src="docs/images/html.png" alt="Real HTML">',
        b"",
        b"[<span>masked]: docs/images/masked-label.png invalid title",
        b"",
    ])
    readme.write_bytes(authored)
    links = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert links.returncode == 0, links.stderr
    findings = json.loads(links.stdout)["findings"]
    assert [(row["target"], row["line"]) for row in findings] == [
        ("docs/images/accepted-label.png", 9), ("docs/images/reference.png", 11),
        ("docs/images/real.png", 13), ("docs/images/html.png", 14),
    ]
    assert "\\u0000" not in links.stdout
    images = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    assert images.returncode == 1, images.stderr
    assert json.loads(images.stdout)["images"] == [
        {"path": "docs/images/accepted-label.png", "referenced_from": ["README.md:9"], "status": "missing"},
        {"path": "docs/images/html.png", "referenced_from": ["README.md:14"], "status": "missing"},
        {"path": "docs/images/real.png", "referenced_from": ["README.md:13"], "status": "missing"},
        {"path": "docs/images/reference.png", "referenced_from": ["README.md:11"], "status": "missing"},
    ]
    assert "\\u0000" not in images.stdout
    assert readme.read_bytes() == authored


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_cli_references_after_comments_use_the_complete_definition_grammar(tmp_path, ending):
    readme = tmp_path / "README.md"
    source = ending.join([
        b"<!-- marker -->[Malformed]: <span>.png",
        b"<!-- marker -->[Prefix]: <span>docs/images/pretend.png",
        b"<!-- marker -->[<span>invalid]: docs/images/also-pretend.png invalid title",
        b"<!-- marker -->[<span>valid]: <docs/images/accepted.png> 'Optional title'",
        b"<!-- marker -->[Valid]: docs/images/plain.png",
        b"",
    ])
    readme.write_bytes(source)
    refs = {"docs/images/accepted.png": 4, "docs/images/plain.png": 5}

    links = run_cli("--repo-dir", tmp_path, "content", "links", "README.md")
    assert links.returncode == 0, links.stdout + links.stderr
    assert {row["target"]: row["line"] for row in json.loads(links.stdout)["findings"]} == refs

    images = run_cli("--repo-dir", tmp_path, "content", "images", "README.md")
    assert images.returncode == 1, images.stdout + images.stderr
    assert {row["path"]: row["referenced_from"] for row in json.loads(images.stdout)["images"]} == {
        path: [f"README.md:{line}"] for path, line in refs.items()
    }
    assert readme.read_bytes() == source
