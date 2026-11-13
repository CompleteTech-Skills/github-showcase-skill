"""Tabs use visual columns when continuing/closing an item-contained fence."""
import pytest

from ctshowcase import mdcode, readme, readmelint

IMAGE = "![Shot](docs/images/missing.png)"
MARKER = "<!-- showcase:tagline:start -->\n**Authored example**\n<!-- showcase:tagline:end -->"


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


@pytest.mark.parametrize("marker", ["- ", "1. ", "-\t", "1.\t"])
@pytest.mark.parametrize("indent", ["\t", " \t", "\t "])
@pytest.mark.parametrize("quote", ["", "> > "])
def test_tab_continuation_and_closer_stay_inside_item_fence(marker, indent, quote):
    text = quote + marker + "```\n" + quote + indent + IMAGE + "\n" + quote + indent + "```\n\n" + IMAGE
    # The first image is code. The tab-indented closer must close that fence,
    # so the second image is real Markdown and is still audited.
    assert images(text) == [("Shot", "docs/images/missing.png")]
    (start, end), = mdcode.fence_spans(text)
    assert start == 0
    assert text.index(IMAGE) < end < text.rindex(IMAGE)


@pytest.mark.parametrize("quote", ["", "> "])
def test_tab_continuation_in_later_fence_cannot_activate_example_markers(quote):
    lines = (quote + "- Example\n" + quote.rstrip() + "\n" + quote + "  ```markdown\n"
             + "\n".join(quote + "\t" + row for row in MARKER.splitlines())
             + "\n" + quote + "  ```\n")
    assert not mdcode.find_blocks(readme.MARK, lines)
    (start, end), = mdcode.fence_spans(lines)
    assert start == lines.index(quote + "  ```")
    assert end == len(lines)


def test_tab_continuation_example_does_not_fail_readme_lint(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    text = readme.scaffold(ctx, "") + "\n- Example\n\n  ```markdown\n\t" + IMAGE + "\n  ```\n"
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    assert "R7 local image does not resolve: docs/images/missing.png" not in readmelint.lint(ctx, path)["fails"]


@pytest.mark.parametrize("indent,closed", [("\t", True), ("\t ", True), ("\t  ", False)])
def test_partial_tab_retains_content_indentation_for_closer(indent, closed):
    # The item content begins at column 2. A tab reaches column 4 and leaves
    # two content spaces; two more spaces exceed the closer's three-space limit.
    text = "- ```\n  code\n" + indent + "```\n  " + IMAGE
    assert images(text) == ([("Shot", "docs/images/missing.png")] if closed else [])


def test_tabbed_item_continuation_can_open_fence():
    text = "- Example\n\n\t```markdown\n\t" + IMAGE + "\n\t```\n\n" + IMAGE
    assert images(text) == [("Shot", "docs/images/missing.png")]
    assert len(mdcode.fence_spans(text)) == 1


@pytest.mark.parametrize("quote", ["", "> "])
def test_tabbed_html_continuation_stays_literal_until_its_terminator(quote):
    text = (quote + "- <pre>\n" + quote + "\t`\n" + quote + "\t" + IMAGE
            + "\n" + quote + "\t</pre>\n\n" + IMAGE)
    (start, end), = mdcode.html_block_spans(text)
    assert text.index(IMAGE) < end < text.rindex(IMAGE)
    assert images(text) == [("Shot", "docs/images/missing.png")]


@pytest.mark.parametrize("marker,indent", [("- ", "\t"), ("-\t", "\t"), ("1. ", "\t ")])
def test_quoted_item_tabs_reach_the_content_column(marker, indent):
    text = "> " + marker + "```\n> " + indent + IMAGE + "\n> " + indent + "```\n\n" + IMAGE
    assert images(text) == [("Shot", "docs/images/missing.png")]


@pytest.mark.parametrize("marker,indent", [("1. ", "\t"), ("1. ", " \t"), ("1.\t", "\t ")])
def test_tabs_are_aligned_from_start_of_quoted_line(marker, indent):
    # '> ' consumes two columns: its following tab reaches absolute column 4,
    # only two columns inside the quote, leaving the ordered item's code fence.
    text = "> " + marker + "```\n> " + indent + IMAGE + "\n"
    assert images(text) == [("Shot", "docs/images/missing.png")]
