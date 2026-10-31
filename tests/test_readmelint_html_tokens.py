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


@pytest.mark.parametrize("document,expected", [
    ('<img alt="a`b" src="https://img.shields.io/badge/a-b-005ADD"> see `![F](https://img.shields.io/badge/c-d-005ADD)`',
     [("a`b", "https://img.shields.io/badge/a-b-005ADD")]),
    ("<!-- `x -->`![F](y.png)`", []),
    ("<!-- `x -->`![F](y.png)` ![G](g.png)", [("G", "g.png")]),
])
def test_code_span_after_a_winning_tag_or_comment_is_still_code(document, expected):
    assert images(document) == expected


def test_code_example_after_attribute_backtick_is_not_a_badge_or_local_file(make_ctx, tmp_path):
    usage = '<!-- `x -->`![F](y.png)`'
    result = lint_reference(make_ctx, tmp_path, usage, "")
    assert "R7 local image does not resolve: y.png" not in result["fails"]
    assert "R7 2-4 header badges required (found 1)" in result["fails"]


def test_multiline_reference_title_keeps_the_definition(make_ctx, tmp_path):
    from test_reference_badge_count import URL
    assert images('![A][a]\n\n[a]: x.png "Build\nstatus"\n') == [("A", "x.png")]
    assert images("![A][a]\n\n[a]: x.png (Build\nstatus)\n") == [("A", "x.png")]
    assert images('![A][a]\n\n[a]: x.png "Build\n\nstatus"\n') == []  # a blank line ends the paragraph: not a definition
    ok = lint_reference(make_ctx, tmp_path / "ok", "![CI][ci]", f'[ci]: {URL} "Build\nstatus"')
    assert not any("badge" in failure for failure in ok["fails"]), ok
    missing = lint_reference(make_ctx, tmp_path / "missing", "![CI][ci]", '[ci]: docs/images/missing.svg "Build\nstatus"')
    assert "R7 local image does not resolve: docs/images/missing.svg" in missing["fails"]


def test_reference_labels_keep_literal_backticks(make_ctx, tmp_path):
    from test_reference_badge_count import URL
    document = "![CI][ci`current`]\n\n[ci`old`]: docs/images/missing.svg\n[ci`current`]: https://example.test/b.svg\n"
    assert images(document) == [("CI", "https://example.test/b.svg")]
    shortcut = "![ci`x`]\n\n[ci`y`]: a.png\n[ci`x`]: b.png\n"
    assert images(shortcut) == [("ci`x`", "b.png")]
    result = lint_reference(make_ctx, tmp_path, "![CI][ci`current`]",
                            f"[ci`old`]: docs/images/missing.svg\n[ci`current`]: {URL}")
    assert not any("missing.svg" in failure for failure in result["fails"]), result
    assert not any("badge" in failure for failure in result["fails"]), result
    assert images("`[ci]: a.png`\n\n![C][ci]") == []


def test_apostrophe_in_markdown_badge_url_cannot_hide_an_off_palette_colour(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![Type](https://img.shields.io/badge/type-it's-FF0000)", "")
    assert "R7 off-palette badge colour FF0000" in result["fails"]
    quoted = lint_reference(make_ctx, tmp_path / "q", "![Type](<https://img.shields.io/badge/type-it's-FF0000?style=flat-square>)", "")
    assert "R7 off-palette badge colour FF0000" in quoted["fails"]


def test_escaped_backticks_do_not_hide_angle_image_from_lint(make_ctx, tmp_path):
    usage = r"\`![Screenshot](<docs/images/missing.png>)\`"
    result = lint_reference(make_ctx, tmp_path, usage, "")
    assert "R7 local image does not resolve: docs/images/missing.png" in result["fails"]


def test_real_inline_code_still_hides_angle_image_from_lint(make_ctx, tmp_path):
    usage = "`![Screenshot](<docs/images/missing.png>)`"
    result = lint_reference(make_ctx, tmp_path, usage, "")
    assert "R7 local image does not resolve: docs/images/missing.png" not in result["fails"]


def test_even_backslash_run_before_backtick_is_real_code(make_ctx, tmp_path):
    usage = r"\\`![Screenshot](<docs/images/missing.png>)`"
    result = lint_reference(make_ctx, tmp_path, usage, "")
    assert "R7 local image does not resolve: docs/images/missing.png" not in result["fails"]


MISSING = "![Shot](docs/images/missing.png)"


@pytest.mark.parametrize("count", range(8))
def test_backslash_parity_before_backtick_controls_code_masking(count):
    document = "\\" * count + "`![Shot](<docs/images/missing.png>)`"
    expected = [("Shot", "docs/images/missing.png")] if count % 2 else []
    assert images(document) == expected


def test_escaped_backtick_then_real_span_masks_image():
    assert images("\\``" + MISSING + "` y") == []
    assert images("\\``code` " + MISSING) == [("Shot", "docs/images/missing.png")]


@pytest.mark.parametrize("count", range(8))
def test_backslash_parity_before_html_comment_opener(count):
    document = "\\" * count + "<!-- " + MISSING + " -->"
    expected = [("Shot", "docs/images/missing.png")] if count % 2 else []
    assert images(document) == expected


@pytest.mark.parametrize("count", range(8))
def test_backslash_parity_before_html_img_open_tag(count):
    document = "\\" * count + '<img src="docs/images/missing.png" alt="Shot">'
    found = images(document)
    # An escaped "<" is literal text, so odd runs render no HTML image.
    assert found == ([] if count % 2 else [("Shot", "docs/images/missing.png")])


def test_reference_definition_title_is_not_rendered_markdown():
    document = ('[unused]: https://example.test/page "![Ghost][ghost]"\n'
                "[ghost]: docs/images/missing.png\n")
    assert images(document) == []
    with_real = document + "\n![Real][ghost]\n"
    assert images(with_real) == [("Real", "docs/images/missing.png")]


def test_html_img_inside_reference_definition_title_is_not_an_image():
    document = '[unused]: https://example.test/page "<img src=\'docs/images/missing.png\' alt=\'Ghost\'>"\n'
    assert images(document) == []


def test_http_shields_badges_count_and_pass_r7(make_ctx, tmp_path):
    usage = ("![Type](http://img.shields.io/badge/type-GitHub%20profile-005ADD)\n"
             "![License](http://img.shields.io/badge/license-MIT-64748B)")
    result = lint_reference(make_ctx, tmp_path, usage, "")
    assert not any("badge" in failure for failure in result["fails"]), result
    assert images(usage) == [
        ("Type", "http://img.shields.io/badge/type-GitHub%20profile-005ADD"),
        ("License", "http://img.shields.io/badge/license-MIT-64748B"),
    ]


def test_off_palette_http_badge_still_fails(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![Type](http://img.shields.io/badge/type-x-FF0000)", "")
    assert "R7 off-palette badge colour FF0000" in result["fails"]
