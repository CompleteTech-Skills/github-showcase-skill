"""README image tokenizing never raises and follows CommonMark for raw HTML, comments, code and titles."""
import pytest

from ctshowcase import readmelint
from test_reference_badge_count import lint_reference


def images(document):
    return readmelint._images(readmelint._outside_code(document), document)


@pytest.mark.parametrize("document", [
    "Wrap <![CI](https://x/badge.svg)> here",
    "Inline `<![x]` example\n\n![A](a.png)",
    "<![if x]> ![A](a.png)",
])
def test_marked_section_lookalikes_do_not_raise(document):
    images(document)


def test_marked_section_lookalike_keeps_image():
    assert images("Wrap <![CI](https://x/badge.svg)> here") == [("CI", "https://x/badge.svg")]


@pytest.mark.parametrize("document", [
    "Retry while attempts <limit.\n\n![Diagram](docs/missing.png)\n\n> Note: callout\n",
    "Use `List<String` then ![Diagram](docs/missing.png) and `a>b` ok",
    "Compare a <b and c.\n\n![Diagram](docs/missing.png)\n\n> quote\n",
])
def test_stray_angle_bracket_is_not_a_tag(document):
    assert images(document) == [("Diagram", "docs/missing.png")]


def test_comment_opener_inside_code_does_not_hide_images():
    document = "Use `<!--` to start a comment.\n\n![Screenshot](docs/missing.png)\n\n<!-- note -->\n"
    assert images(document) == [("Screenshot", "docs/missing.png")]
    fenced = "```\n<!--\n```\n\n![Screenshot](docs/missing.png)\n\n<!-- note -->\n"
    assert images(fenced) == [("Screenshot", "docs/missing.png")]
    assert images("<!-- ![Hidden](h.png) -->\n![Shown](s.png)") == [("Shown", "s.png")]


def test_reference_title_with_escaped_quote_still_defines_image():
    document = '![Screenshot][shot]\n\n[shot]: <docs/missing.png> "The \\"before\\" screenshot"\n'
    assert images(document) == [("Screenshot", "docs/missing.png")]
    assert images("![S][s]\n\n[s]: a.png 'it\\'s'\n") == [("S", "a.png")]


def test_inline_code_angle_bracket_does_not_hide_html_images_from_lint(make_ctx, tmp_path):
    usage = 'Loop while `i<n` holds.\n\n<img src="docs/missing.png" alt="">'
    result = lint_reference(make_ctx, tmp_path, usage, "")
    assert any("without alt" in f for f in result["fails"])
    assert "R7 local image does not resolve: docs/missing.png" in result["fails"]
    prose = lint_reference(make_ctx, tmp_path / "second", 'Compare a <b and c.\n\n<img src="docs/missing.png" alt="">', "")
    assert "R7 local image does not resolve: docs/missing.png" in prose["fails"]
