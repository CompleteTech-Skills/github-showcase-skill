"""Quote-prefix tabs supply optional quote space before item indentation."""
import pytest

from ctshowcase import mdcode, readme, readmelint

IMAGE = "![Shot](docs/images/missing.png)"
MARKER = "<!-- showcase:tagline:start -->\n**Example**\n<!-- showcase:tagline:end -->"


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


@pytest.mark.parametrize("opener,continuation", [
    ("> 1. ```text\n", ">\t"),
    ("> 1. ```text\n", "> \t"),
    ("> > 1. ```text\n", "> >\t"),
    ("> > 1. ```text\n", ">\t>\t"),
])
def test_quote_optional_space_leaves_item_before_real_image(opener, continuation):
    # These continue the quote but leave its three-column ordered item. The
    # unclosed item fence ends before the real Markdown image (CommonMark).
    text = opener + continuation + IMAGE + "\n"
    assert images(text) == [("Shot", "docs/images/missing.png")]
    assert mdcode.fence_spans(text) == ((0, len(opener)),)
    assert images(text.expandtabs(4)) == images(text)


@pytest.mark.parametrize("quote", [">\t", "> \t", ">\t>\t", "> >\t"])
def test_tabs_can_supply_quote_space_and_open_close_fence(quote):
    text = quote + "```text\n" + "\n".join(quote + row for row in MARKER.splitlines())
    text += "\n" + quote + "```\n\n" + IMAGE
    assert not mdcode.find_blocks(readme.MARK, text)
    assert images(text) == [("Shot", "docs/images/missing.png")]
    (start, end), = mdcode.fence_spans(text)
    assert start == 0 and end == text.rindex(IMAGE) - 1


@pytest.mark.parametrize("quote", [">\t ", "> \t ", ">\t>\t ", "> >\t   "])
def test_residual_tab_columns_can_keep_ordered_item_fence(quote):
    # The residual tab columns plus spaces reach the item content column; the
    # image and marker examples remain literal, and a later image stays live.
    prefix = "> > " if quote.count(">") == 2 else "> "
    text = prefix + "1. ```text\n" + quote + IMAGE + "\n" + quote + "```\n\n" + IMAGE
    assert images(text) == [("Shot", "docs/images/missing.png")]
    assert images(text.expandtabs(4)) == images(text)


def test_quote_tabs_end_raw_html_at_the_actual_item_boundary():
    text = "> 1. <pre>\n>\t" + IMAGE + "\n"
    assert mdcode.html_block_spans(text) == ((0, len("> 1. <pre>\n")),)
    assert images(text) == [("Shot", "docs/images/missing.png")]


def test_dedented_quote_tab_image_is_reported_by_real_linter(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    text = readme.scaffold(ctx, "") + "\n> 1. ```text\n>\t" + IMAGE + "\n"
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, path)["fails"]


@pytest.mark.parametrize("opening,leaves,stays", [
    ("> - > ```text\n", "> >   ", ">   >   "),
    ("> - > ```text\n", "> >\t  ", ">   >\t  "),
    ("> 1. > ```text\n", "> >    ", ">    >   "),
    ("> 1. > ```text\n", ">\t>\t ", ">    >\t "),
])
def test_item_indentation_precedes_its_nested_quote(opening, leaves, stays):
    # Content indentation after a second quote cannot substitute for missing
    # list-item indentation before it. The same rule applies with tab padding.
    live = opening + leaves + IMAGE + "\n"
    code = opening + stays + IMAGE + "\n"
    assert images(live) == [("Shot", "docs/images/missing.png")]
    assert images(code) == []
    assert mdcode.fence_spans(live) == ((0, len(opening)),)
    assert images(live.expandtabs(4)) == images(live)
    assert images(code.expandtabs(4)) == images(code)


def test_later_fence_retains_inherited_item_before_nested_quote():
    opening = "> - Example\n>\n>   > ```text\n"
    live = opening + "> >   " + IMAGE + "\n"
    code = opening + ">   > " + IMAGE + "\n>   > ```\n\n" + IMAGE
    assert images(live) == [("Shot", "docs/images/missing.png")]
    assert images(code) == [("Shot", "docs/images/missing.png")]
    assert len(mdcode.fence_spans(live)) == len(mdcode.fence_spans(code)) == 1


def test_item_before_nested_quote_also_bounds_raw_html():
    opening = "> - > <pre>\n"
    text = opening + "> >   " + IMAGE + "\n"
    assert mdcode.html_block_spans(text) == ((0, len(opening)),)
    assert images(text) == [("Shot", "docs/images/missing.png")]
