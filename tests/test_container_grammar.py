"""CommonMark 4.1/4.6/5.2 precedence and empty-item content columns."""
import pytest

from ctshowcase import mdcode, readmelint

IMAGE = "![Probe](missing.png)"


def images(text):
    masked = readmelint._outside_code(text)
    assert len(masked) == len(text)
    assert [i for i, c in enumerate(masked) if c == "\n"] == [i for i, c in enumerate(text) if c == "\n"]
    return readmelint._images(masked, text)


@pytest.mark.parametrize("marker", ["-", "+", "*", "1.", "2)", "123456789."])
@pytest.mark.parametrize("indent", range(4))
@pytest.mark.parametrize("trailing", ["", " ", "   ", "     ", "\t", " \t"])
@pytest.mark.parametrize("continuation", range(12))
def test_empty_item_has_one_virtual_padding_column(marker, indent, trailing, continuation):
    width = indent + len(marker) + 1
    text = " " * indent + marker + trailing + "\n" + " " * continuation + IMAGE + "\n"
    # A continuation reaching the content column belongs to the empty item;
    # otherwise it starts outside it. Four residual columns mean code.
    residual = continuation - width if continuation >= width else continuation
    assert images(text) == ([("Probe", "missing.png")] if residual < 4 else [])
    path, content = mdcode._container_path(mdcode.block_line(text.splitlines()[0]))
    assert path == (("item", width),)
    assert content == ""


@pytest.mark.parametrize("marker", ["-", "1.", "2)"])
@pytest.mark.parametrize("padding", range(1, 9))
def test_nonempty_item_uses_one_to_four_padding_columns(marker, padding):
    path, content = mdcode._container_path(marker + " " * padding + IMAGE)
    actual = padding if padding <= 4 else 1
    assert path == (("item", len(marker) + actual),)
    assert content == " " * (padding - actual) + IMAGE


@pytest.mark.parametrize("digit", ["١", "１", "𝟚"])
def test_ordered_markers_are_ascii_only(digit):
    text = digit + ".\n    " + IMAGE + "\n"
    assert mdcode._container_path(text.splitlines()[0]) == ((), digit + ".")
    # The digit line is an ordinary paragraph, so indentation cannot start code.
    assert images(text) == [("Probe", "missing.png")]


@pytest.mark.parametrize("rule", ["---", "- ---", "- - -", "***", "* **", "* * *", "___", "_ _ _", "-\t--"])
@pytest.mark.parametrize("prefix,continuation,path", [
    ("", "    ", ()),
    ("> ", ">     ", (("quote", 0),)),
    ("1. ", "       ", (("item", 3),)),
    ("> 1. ", ">        ", (("quote", 0), ("item", 3))),
])
def test_thematic_break_precedes_new_list_marker(rule, prefix, continuation, path):
    text = prefix + rule + "\n" + continuation + IMAGE + "\n"
    assert mdcode._container_path(mdcode.block_line(text.splitlines()[0]))[0] == path
    assert images(text) == []
    assert mdcode.code_block_spans(text) == ((text.index("\n") + 1, len(text)),)


@pytest.mark.parametrize("opener,continuation", [("> <!--", ""), ("- <!--", ""), ("- > <!--", ""), ("> - <!--", "> ")])
@pytest.mark.parametrize("closer", ["-->\n", "", "\n<!-- another -->\n"])
def test_raw_comment_stops_when_its_container_ends(opener, continuation, closer):
    text = opener + "\n" + continuation + IMAGE + "\n" + closer
    assert images(text) == [("Probe", "missing.png")]
    assert mdcode.html_block_spans(text)[0] == (0, len(opener) + 1)


@pytest.mark.parametrize("prefix", ["", "> ", "- ", "> - ", "- > "])
def test_raw_comment_still_hides_images_within_same_container(prefix):
    path, _ = mdcode._container_path(prefix + "<!--")
    continuation = "".join("> " if kind == "quote" else " " * width for kind, width in path)
    text = prefix + "<!--\n" + continuation + IMAGE + "\n" + continuation + "-->\n"
    assert images(text) == []


@pytest.mark.parametrize("indent,live", [(6, True), (7, False)])
def test_empty_ordered_item_separates_preceding_quote_code_opener(indent, live):
    text = "> Text `\n2.\n" + " " * indent + IMAGE + "`\n"
    assert images(text) == ([("Probe", "missing.png")] if live else [])


@pytest.mark.parametrize("prefix", ["", "> "])
@pytest.mark.parametrize("marker", ["-", "2."])
@pytest.mark.parametrize("tabs", ["\t", "\t ", "\t\t"])
def test_empty_item_tab_continuations_keep_original_column_stops(prefix, marker, tabs):
    text = prefix + marker + "\t\n" + prefix + tabs + IMAGE + "\n"
    width = len(marker) + 1
    indent = len((prefix + tabs).expandtabs(4)) - len(prefix)
    residual = indent - width if indent >= width else indent
    assert images(text) == ([("Probe", "missing.png")] if residual < 4 else [])


@pytest.mark.parametrize("opener", ["<!-->", "<!--->", "<!-- closed -->"])
def test_raw_comment_closer_on_opening_line_does_not_hide_next_block(opener):
    text = opener + "\n## Heading " + IMAGE + "\n-->\n"
    assert images(text) == [("Probe", "missing.png")]
    assert mdcode.html_block_spans(text) == ((0, len(opener) + 1),)
