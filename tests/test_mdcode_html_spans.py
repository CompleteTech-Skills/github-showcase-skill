"""Extents of raw HTML blocks (CommonMark 4.6), as exposed by mdcode.html_block_spans."""
from ctshowcase import mdcode


def pieces(text):
    return [text[a:b] for a, b in mdcode.html_block_spans(text)]


def test_type6_block_ends_before_the_blank_line():
    assert pieces("<div>\nraw\n\nafter\n") == ["<div>\nraw\n"]


def test_comment_block_ends_on_its_end_line():
    assert pieces("<!-- a\nb -->\ntext after\n\npara\n") == ["<!-- a\nb -->\n"]


def test_unterminated_block_runs_to_end_of_file():
    text = "intro\n\n<div>\nraw\nmore"
    assert pieces(text) == ["<div>\nraw\nmore"]


def test_block_inside_a_blockquote_ends_with_the_quote():
    text = "> <div>\n> raw\n\nplain\n"
    spans = pieces(text)
    assert len(spans) == 1 and spans[0].startswith("> <div>") and "plain" not in spans[0]


def test_no_block_inside_a_fence():
    assert pieces("```html\n<div>\nraw\n</div>\n```\n") == []


def test_no_block_for_plain_markdown():
    assert mdcode.html_block_spans("just text\n\n- item\n") == ()
