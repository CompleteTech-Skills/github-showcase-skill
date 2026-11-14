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
