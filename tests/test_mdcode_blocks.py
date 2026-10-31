"""Block structure is decided before inline code: a span never pairs across a block boundary. Expected renders follow
the GitHub Markdown API (gfm mode) and CommonMark 0.31.2 HTML blocks 1-6 (type 7 cannot interrupt a paragraph)."""
import re

import pytest

from ctshowcase import mdcode, readme, readmelint

IMAGE = "![x](docs/images/missing.png)"
MARKER = "<!-- showcase:tagline:start -->\n**Use `npx` now**\n<!-- showcase:tagline:end -->"


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


def covers(text, needle):
    at = text.index(needle)
    return any(a <= at < b for a, b in mdcode.code_spans(text))


def test_stray_backtick_above_marker_keeps_the_block():
    t = "Price is 5` per unit\n" + MARKER + "\n"
    assert [m.group(1) for m in mdcode.find_blocks(readme.MARK, t)] == ["tagline"]
    assert not covers(t, "<!-- showcase:tagline:start")
    assert [t[a:b] for a, b in mdcode.code_spans(t)] == ["`npx`"]


def test_footer_marker_after_unmatched_backtick_in_list_item():
    t = "- Run `make\n<!-- showcase:footer:start -->\nfooter\n<!-- showcase:footer:end -->\n- then `done`\n"
    assert [m.group(1) for m in mdcode.find_blocks(readme.MARK, t)] == ["footer"]


@pytest.mark.parametrize("first,second", [
    ("- Install `foo", "- See " + IMAGE + " and `bar`"),
    ("* Install `foo", "* See " + IMAGE + " and `bar`"),
    ("1. Install `foo", "2. See " + IMAGE + " and `bar`"),
    ("1. Install `foo", "1. See " + IMAGE + " and `bar`"),
    ("10. Install `foo", "11. See " + IMAGE + " and `bar`"),
    ("- Install `foo", "  - See " + IMAGE + " and `bar`"),
])
def test_list_items_do_not_share_a_code_span(first, second):
    assert images(first + "\n" + second + "\n") == [("x", "docs/images/missing.png")]


def test_continued_quote_lines_stay_one_paragraph_as_on_github():
    t = "> quote with ` tick\n> and ![x](y.png) then `z`\n"
    assert images(t) == []
    assert [t[a:b] for a, b in mdcode.code_spans(t)] == ["` tick\n> and ![x](y.png) then `"]


def test_lazy_quote_continuation_stays_one_paragraph():
    t = "> quote with ` tick\nand ![x](y.png) then `z`\n"
    assert images(t) == []


@pytest.mark.parametrize("first,second", [
    ("plain ` tick", "> and ![x](y.png) then `z`"),
    ("> outer ` tick", "> > and ![x](y.png) then `z`"),
])
def test_new_quote_breaks_a_paragraph(first, second):
    assert images(first + "\n" + second + "\n") == [("x", "y.png")]


@pytest.mark.parametrize("boundary", ["***", "---", "___", "- - -", "<div>", "</div>", "<p align=\"center\">", "<!-- note -->",
                                      "<pre>", "<?php", "<![CDATA[", "<details>", "## Heading", "===", "-"])
def test_boundary_lines_stop_the_span(boundary):
    t = "a ` b\n" + boundary + "\nc " + IMAGE + " `z`\n"
    assert images(t) == [("x", "docs/images/missing.png")]
    assert not covers(t, "![x]")


@pytest.mark.parametrize("line", ["<span>b` here", "<a href=\"u\">b` here", "<custom-tag>b` here", "<div"])
def test_type_7_and_inline_tags_are_not_boundaries(line):
    t = "Use `a\n" + line + "\n"
    if line == "<div":
        assert mdcode.code_spans(t) == []
    else:
        assert [t[a:b] for a, b in mdcode.code_spans(t)] == ["`a\n" + line[:line.index("`") + 1]]


def test_ordinary_multiline_code_stays_code():
    t = "Use `a\nb` here " + IMAGE + "\n"
    assert [t[a:b] for a, b in mdcode.code_spans(t)] == ["`a\nb`"]
    assert images(t) == [("x", "docs/images/missing.png")]


def test_recognised_table_rows_and_cells_do_not_pair_with_each_other():
    t = "| A | B |\n| --- | --- |\n| ` | ![table](table.png) |\n| `x | y` |\n"
    assert images(t) == [("table", "table.png")]
    assert mdcode.code_spans(t) == []


def test_plain_paragraph_with_a_pipe_is_not_a_table():
    t = "plain ` | text\nnext ![plain](plain.png) `\n"
    assert images(t) == []
    assert len(mdcode.code_spans(t)) == 1


def test_table_header_split_from_the_paragraph_above():
    t = "intro `\n| A | B |\n| - | - |\n| ![t](t.png) | ` |\n"
    assert images(t) == [("t", "t.png")]


def _stack(kind, a, payload):
    """`a` (text above), a boundary of `kind`, then `payload`; list and quote kinds prefix the payload's first line."""
    prefix = {"list": "- ", "ordered": "1. ", "quote": "> "}.get(kind)
    if prefix:
        return a + "\n" + prefix + payload + "\n"
    middle = {"blank": ["", ""], "thematic": ["***"], "setext": ["==="], "html6": ["<div>"], "comment": ["<!-- c -->"],
              "heading": ["## H"], "fence": ["```", "code", "```"]}[kind]
    return "\n".join([a, *middle, payload]) + "\n"


KINDS = ["blank", "list", "ordered", "quote", "thematic", "setext", "html6", "comment", "heading", "fence"]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("above", ["Price is 5` per unit", "Run `make"])
def test_matrix_marker_block_survives(kind, above):
    t = _stack(kind, above, MARKER)
    assert [m.group(1) for m in mdcode.find_blocks(readme.MARK, t)] == ["tagline"], kind
    assert not covers(t, "<!-- showcase:tagline:start")


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("above,tail", [("Price is 5` per unit", " `z`"), ("Run `make", " done`")])
def test_matrix_image_stays_rendered(kind, above, tail):
    t = _stack(kind, above, IMAGE + tail)
    assert images(t) == [("x", "docs/images/missing.png")], kind


@pytest.mark.parametrize("above,tail", [("Price is 5` per unit", " `z`"), ("Run `make", " done`")])
def test_matrix_soft_break_control_still_pairs(above, tail):
    t = above + "\n" + IMAGE + tail + "\n"
    assert images(t) == []


# --- fences inside block quotes (container-aware) ---------------------------------------------------------------
def placeholder(text):
    from ctshowcase.detect import standard
    return re.search(standard("readme-variants")["placeholder_regex"], readmelint._outside_code(text))


# (document, exact fenced span expected from fence_spans)
QUOTED_FENCES = [
    pytest.param("> ```text\n> TODO\n> ```", "> ```text\n> TODO\n> ```", id="probe"),
    pytest.param("> > ```\n> > TODO\n> > ```", "> > ```\n> > TODO\n> > ```", id="nested-quote"),
    pytest.param("> ~~~\n> TODO\n> ~~~", "> ~~~\n> TODO\n> ~~~", id="tilde"),
    pytest.param("   > ```\n   > TODO\n   > ```", "   > ```\n   > TODO\n   > ```", id="indented-quote"),
    pytest.param("> ```\n> TODO\nplain after", "> ```\n> TODO\n", id="lower-depth-line-ends-it-unclosed"),
    pytest.param("> ```\n> TODO\n", "> ```\n> TODO\n", id="unclosed-at-end"),
    pytest.param("> > ```\n> > TODO\n> outer\n", "> > ```\n> > TODO\n", id="inner-quote-ends-at-outer-depth"),
]


@pytest.mark.parametrize("doc,fenced", QUOTED_FENCES)
def test_quoted_fence_is_code(doc, fenced):
    assert [doc[a:b] for a, b in mdcode.fence_spans(doc)] == [fenced]
    assert covers(doc, "TODO")
    assert (0, len(fenced)) in mdcode.code_spans(doc)
    assert "TODO" not in mdcode.masked(doc)
    assert placeholder(doc) is None


@pytest.mark.parametrize("opener,closer", [("> ```text", "> ```"), ("> > ```", "> > ```"), ("> ~~~", "> ~~~"),
                                           ("   > ```", "   > ```")])
def test_closed_quoted_fence_leaves_later_text_visible(opener, closer):
    doc = f"{opener}\n{closer.split('>')[0]}> x\n{closer}\n\nTODO later\n"
    assert not covers(doc, "TODO later")
    assert placeholder(doc).group(0) == "TODO"


def test_genuine_placeholder_outside_code_still_fails():
    assert placeholder("# X\n\nTODO write this\n") is not None
    assert placeholder("> note\n> TODO inside a plain quote\n") is not None


def test_quoted_fence_does_not_swallow_a_following_paragraph():
    doc = "> ```\n> code\nTODO paragraph\n"
    assert covers(doc, "code")
    assert not covers(doc, "TODO paragraph")
    assert placeholder(doc) is not None


def test_top_level_fence_behaviour_is_unchanged():
    doc = "```\nTODO\n```\n\n> TODO quoted prose\n"
    assert [doc[a:b] for a, b in mdcode.fence_spans(doc)] == ["```\nTODO\n```\n"]
    assert not covers(doc, "TODO quoted prose")


# --- list-item fences and paragraph continuation starts -----------------------------------------------------------
def spans_of(text):
    return [text[a:b] for a, b in mdcode.fence_spans(text)]


def test_item_fence_opens_and_closes_on_the_items_own_lines():
    t = "1. ```bash\n   npm test\n   ```\n\nafter\n"
    (a, b), = mdcode.fence_spans(t)
    assert t[a:b].endswith("   ```\n") and "npm test" in t[a:b]
    assert "after" not in t[a:b] and t[b:].startswith("\nafter")


def test_item_fence_closing_line_is_not_a_new_opener():
    t = "- ```text\n  TODO\n  ```\n\n![x](docs/images/missing.png)\n"
    assert len(mdcode.fence_spans(t)) == 1
    assert images(t) == [("x", "docs/images/missing.png")]


def test_unclosed_item_fence_runs_to_the_end_of_the_document():
    t = "- ```text\n  open\n  still\n"
    assert mdcode.fence_spans(t)[-1][1] == len(t)


def test_dedent_below_the_content_column_ends_an_item_fence():
    t = "- ```text\n  open\nplain ![x](docs/images/missing.png)\n"
    (a, b), = mdcode.fence_spans(t)
    assert b == t.index("plain")
    assert images(t) == [("x", "docs/images/missing.png")]


@pytest.mark.parametrize("t", ["- > ```text\n  > a\n  > ```\n", "> - ```text\n>   a\n>   ```\n"],
                         ids=["item-quote", "quote-item"])
def test_composed_item_and_quote_fences_are_one_span(t):
    assert len(mdcode.fence_spans(t)) == 1 and mdcode.fence_spans(t)[0][1] == len(t)


def test_continuation_starts_hold_paragraph_continuation_lines_only():
    t = "# Head\n\nfirst line\nsecond line\n[a]: x\n\n- item\n\n```\nfenced\n```\n\n## Next\n"
    starts = mdcode.continuation_starts(t)
    assert {t.index("second line"), t.index("[a]: x")} <= starts
    for block_start in ("# Head", "first line", "- item", "fenced", "## Next"):
        assert t.index(block_start) not in starts


QUOTED_EXTRA = "> ```text\n> > ```\n> code\n> ```\n> ![Shot](<docs/images/missing.png>)"


def test_extra_quote_markers_inside_a_quoted_fence_are_code_content():
    spans = mdcode.fence_spans(QUOTED_EXTRA)
    closer = QUOTED_EXTRA.index("> code\n> ```\n") + len("> code\n> ```\n")
    assert spans == ((0, closer),)
    assert not covers(QUOTED_EXTRA, "![Shot]")


def test_extra_quote_markers_do_not_hide_the_image_after_the_real_closer():
    assert [src for _, src in images(QUOTED_EXTRA)] == ["docs/images/missing.png"]


def test_a_real_quoted_closer_still_closes():
    t = "> ```text\n> code\n> ```\n> ![Shot](docs/images/missing.png)"
    assert mdcode.fence_spans(t) == ((0, t.index("> ![Shot]")),)


def test_a_depth_two_fence_still_opens_and_closes_on_its_own_depth():
    t = "> > ```text\n> > code\n> > ```\n> > ![Shot](docs/images/missing.png)"
    assert mdcode.fence_spans(t) == ((0, t.index("> > ![Shot]")),)
    assert [src for _, src in images(t)] == ["docs/images/missing.png"]
