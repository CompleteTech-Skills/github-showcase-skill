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


RAW_BLOCK_OPENERS = {"<div>", "</div>", '<p align="center">', "<pre>", "<?php", "<![CDATA[", "<details>"}


@pytest.mark.parametrize("boundary", ["***", "---", "___", "- - -", "<div>", "</div>", "<p align=\"center\">", "<!-- note -->",
                                      "<pre>", "<?php", "<![CDATA[", "<details>", "## Heading", "===", "-"])
def test_boundary_lines_stop_the_span(boundary):
    t = "a ` b\n" + boundary + "\nc " + IMAGE + " `z`\n"
    # An opener of a raw HTML block (CommonMark 4.6 types 1-6) keeps the next line inside that block, where Markdown
    # image syntax is literal text; every other boundary leaves the line to the paragraph, so the image renders.
    in_raw_block = any(a <= t.index("![x]") < b for a, b in mdcode.html_block_spans(t))
    assert in_raw_block == (boundary in RAW_BLOCK_OPENERS)
    assert images(t) == ([] if in_raw_block else [("x", "docs/images/missing.png")])
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
    # after a type 6 opener (`html6`) the payload line is inside the raw HTML block and its image syntax is literal text
    assert images(t) == ([] if kind == "html6" else [("x", "docs/images/missing.png")]), kind


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


ITEM_MARKERS = [("- ", 2), ("* ", 2), ("+ ", 2), ("1. ", 3)]


@pytest.mark.parametrize("marker,indent", ITEM_MARKERS, ids=["dash", "star", "plus", "ordered"])
def test_dedented_quote_after_item_fence_ends_the_fence(marker, indent):
    pad = " " * indent
    t = f"{marker}```text\n{pad}example\n> ![Shot](<docs/images/missing.png>)\n\nOrdinary paragraph.\n"
    assert len(mdcode.fence_spans(t)) == 1
    (a, b), = mdcode.fence_spans(t)
    assert b == t.index("> ![Shot]")
    assert images(t) == [("Shot", "docs/images/missing.png")]


@pytest.mark.parametrize("marker,indent", ITEM_MARKERS, ids=["dash", "star", "plus", "ordered"])
def test_indented_quote_inside_item_fence_is_control_content(marker, indent):
    pad = " " * indent
    t = f"{marker}```text\n{pad}example\n{pad}> ![Shot](<docs/images/missing.png>)\n{pad}```\n"
    (a, b), = mdcode.fence_spans(t)
    assert b == len(t)
    assert images(t) == []


def test_blank_line_does_not_end_item_fence_but_dedented_quote_does():
    t = "- ```text\n  example\n\n> ![Shot](<docs/images/missing.png>)\n"
    (a, b), = mdcode.fence_spans(t)
    assert b == t.index("> ![Shot]")
    assert images(t) == [("Shot", "docs/images/missing.png")]


def test_two_angle_delimited_badges_after_item_fence_are_both_counted():
    t = "- ```text\n  example\n> ![A](<https://img.shields.io/badge/a-b-005ADD>) ![B](<https://img.shields.io/badge/c-d-64748B>)\n"
    assert len(images(t)) == 2


def test_deeper_quote_inside_quoted_item_fence_stays_content():
    t = "> - ```text\n>   a\n>   > ![x](docs/images/missing.png)\n>   ```\n"
    (a, b), = mdcode.fence_spans(t)
    assert b == len(t)
    assert images(t) == []


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


# --- raw HTML blocks: literal backticks inside a raw HTML block never open a code span (CommonMark 4.6) -------------
RAW_IMG = '<img src="docs/images/missing.png" alt="Shot">'


def test_literal_backticks_inside_html_block_do_not_hide_the_image():
    t = '<div>\nUse a literal ` character.\n' + RAW_IMG + '\nAnother ` character.\n</div>\n'
    assert mdcode.inline_code_spans(t) == ()
    assert not covers(t, '<img src="docs/images/missing.png"')


def test_lint_reads_the_raw_html_image_that_the_backticks_would_hide():
    t = '<div>\nUse a literal ` character.\n' + RAW_IMG + '\nAnother ` character.\n</div>\n'
    assert images(t) == [("Shot", "docs/images/missing.png")]


def test_nested_raw_html_blocks_keep_the_image_visible():
    t = "<div>\n<details>\nUse a literal ` character.\n" + RAW_IMG + "\nAnother ` character.\n</details>\n</div>\n"
    assert mdcode.inline_code_spans(t) == ()
    assert not covers(t, RAW_IMG)


# Types 1-5 (pre, script, style, comment, PI, CDATA) end only at their end condition, so they get a blank line right
# after the opener: were the block to end at that blank line, the two backtick lines would pair and hide the image.
RAW_HTML_PAIRS = [
    pytest.param("<div>", "</div>", False, id="div"),
    pytest.param("<details>", "</details>", False, id="details"),
    pytest.param("<table>", "</table>", False, id="table"),
    pytest.param("<pre>", "</pre>", True, id="pre"),
    pytest.param("<script>", "</script>", True, id="script"),
    pytest.param("<style>", "</style>", True, id="style"),
    pytest.param("<!-- c", "-->", True, id="comment"),
    pytest.param("<?php", "?>", True, id="pi"),
    pytest.param("<![CDATA[", "]]>", True, id="cdata"),
]


@pytest.mark.parametrize("opener,closer,blank", RAW_HTML_PAIRS)
def test_raw_html_block_keeps_the_image_out_of_code(opener, closer, blank):
    lead = "\n" if blank else ""
    t = opener + "\n" + lead + "Use a literal ` character.\n" + RAW_IMG + "\nAnother ` character.\n" + closer + "\n"
    assert not covers(t, RAW_IMG)


# --- controls that must keep working ------------------------------------------------------------------------------
def test_paragraph_after_a_type_6_block_ends_at_a_blank_line_keeps_its_code():
    t = "<div>\nhtml\n</div>\n\nRun `npx` now\n"
    assert [t[a:b] for a, b in mdcode.inline_code_spans(t)] == ["`npx`"]


def test_type_7_paragraph_still_pairs_its_backticks():
    t = "<span>a` b</span> and `c` d\n"
    assert [t[a:b] for a, b in mdcode.inline_code_spans(t)] == ["` b</span> and `"]


def test_type_1_block_closed_on_its_own_line_leaves_the_next_line_as_markdown():
    t = "<pre>x</pre>\nRun `npx` now\n"
    assert [t[a:b] for a, b in mdcode.inline_code_spans(t)] == ["`npx`"]


# --- container-aware and boundary behaviour of the raw HTML block --------------------------------------------------
def test_quoted_html_block_keeps_the_image_visible_and_ends_with_the_quote():
    t = "> <div>\n> Use a literal ` character.\n> " + RAW_IMG + "\n> Another ` character.\n> </div>\n"
    assert mdcode.inline_code_spans(t) == ()
    lazy = "> <div>\nlazy ` x\n" + IMAGE + "\ny `\n"   # an HTML block has no lazy continuation: this is a paragraph
    assert covers(lazy, IMAGE)


def test_list_item_html_block_keeps_the_image_visible_and_ends_left_of_the_item():
    t = "- <div>\n  Use a literal ` character.\n  " + RAW_IMG + "\n  Another ` character.\n  </div>\n"
    assert mdcode.inline_code_spans(t) == ()
    left = "- <div>\n  x\nUse ` here " + IMAGE + " there `\n"
    assert covers(left, IMAGE)


def test_blank_line_ends_a_type_6_block_and_markdown_resumes_after_it():
    t = "<div>\nraw\n</div>\n\nUse ` here " + IMAGE + " there `\n"
    assert covers(t, IMAGE)


def test_type_7_tag_alone_on_a_line_is_raw_but_cannot_interrupt_a_paragraph():
    raw = "<custom-tag>\nUse ` here\n" + IMAGE + "\nthere `\n"
    assert mdcode.inline_code_spans(raw) == ()
    para = "Run `a\n<custom-tag>\nb` c\n"
    assert [para[a:b] for a, b in mdcode.inline_code_spans(para)] == ["`a\n<custom-tag>\nb`"]


def test_unclosed_type_2_block_runs_to_the_end_and_masks_nothing():
    t = "<!--\n`a\n" + IMAGE + "\nb`\n"
    assert mdcode.inline_code_spans(t) == ()


@pytest.mark.parametrize("opener", ["<div>", "<!--", "<pre>"], ids=["type6", "comment", "pre"])
@pytest.mark.parametrize("marker,indent", ITEM_MARKERS, ids=["dash", "star", "plus", "ordered"])
def test_dedented_quote_after_item_html_block_ends_the_block(marker, indent, opener):
    pad = " " * indent
    t = f"{marker}{opener}\n{pad}raw\n> ![Shot](<docs/images/missing.png>)\n\nOrdinary paragraph.\n"
    (a, b), = mdcode.html_block_spans(t)
    assert b == t.index("> ![Shot]")
    assert images(t) == [("Shot", "docs/images/missing.png")]


def test_dedented_deeper_quote_after_quoted_item_html_block_ends_the_block():
    t = "> - <div>\n>   raw\n> > ![Shot](<docs/images/missing.png>)\n\nOrdinary paragraph.\n"
    (a, b), = mdcode.html_block_spans(t)
    assert b == t.index("> > ![Shot]")


@pytest.mark.parametrize("t", [
    "- <div>\n  raw\n  > ![Shot](<docs/images/missing.png>)\n\nOrdinary paragraph.\n",
    "> - <div>\n>   raw\n>   > ![Shot](<docs/images/missing.png>)\n\nOrdinary paragraph.\n",
], ids=["item", "quoted-item"])
def test_indented_quote_inside_item_html_block_stays_block_content(t):
    (a, b), = mdcode.html_block_spans(t)
    assert b == t.index("\n\n") + 1


# --- fences opened on a list continuation line keep their list item (#7 r4) -----------------------------------------
# GFM oracle: gfm-77004-list_continuation_fence.html (1 image rendered) and gfm-77004-list_fence_inert_control.html
# (0 images). The unclosed fence ends with its list item at the dedented paragraph, so the image is outside code.
SHOT = "![Shot](<docs/images/missing.png>)"


@pytest.mark.parametrize("text", [
    "- Example\n\n  ```text\n  code\n\n" + SHOT,
    "1. x\n\n   ```text\n   code\n\n" + SHOT,
    "- a\n  - b\n\n    ```text\n    code\n\n" + SHOT,
], ids=["bullet", "ordered", "nested"])
def test_list_continuation_fence_ends_before_the_dedented_image(text):
    (start, end), = mdcode.fence_spans(text)
    assert end <= text.index(SHOT)
    assert [found[1] for found in images(text)] == ["docs/images/missing.png"]


def test_fence_at_column_zero_after_a_list_still_runs_to_the_end():
    text = "- Example\n\n```text\ncode\n\n" + SHOT
    (start, end), = mdcode.fence_spans(text)
    assert end == len(text)
    assert not images(text)


def test_blank_line_inside_a_list_fence_stays_code():
    text = "- Example\n\n  ```text\n  code\n\n  " + SHOT + "\n  ```\n"
    (start, end), = mdcode.fence_spans(text)
    assert start < text.index(SHOT) < end
    assert not images(text)


def test_four_spaces_beyond_the_item_column_is_indented_code_not_a_fence():
    text = "- Example\n\n      ```text\n      code\n\n" + SHOT
    assert mdcode.fence_spans(text) == ()


# --- nested containers (#7 r3, 8783e0e): layout offsets for the three Sol cases and their controls ---------------------
HTML_IMG = '<img alt="Shot" src="docs/images/missing.png">'


@pytest.mark.parametrize("gap", ["", ">"], ids=["blank", "quote-blank"])
def test_quoted_list_fence_ends_at_the_line_that_leaves_the_quote_item(gap):
    text = "> - Example\n>\n>   ```text\n>   code\n" + gap + "\n> " + SHOT
    (start, end), = mdcode.fence_spans(text)
    assert start <= text.index("```")
    assert end <= text.index(SHOT)
    assert [found[1] for found in images(text)] == ["docs/images/missing.png"]


def test_quoted_list_fence_closed_on_its_own_line_hides_the_image():
    text = "> - Example\n>\n>   ```text\n>   " + SHOT + "\n>   ```\n"
    (start, end), = mdcode.fence_spans(text)
    assert start < text.index(SHOT) < end
    assert not images(text)


def test_item_html_block_after_four_space_indent_leaves_the_image_visible():
    text = "- Example\n\n    <div>\n    One ` character.\n    " + HTML_IMG + "\n    Another ` character.\n    </div>\n"
    (start, end), = mdcode.html_block_spans(text)
    assert start <= text.index("<div>") and start < text.index(HTML_IMG) < end
    assert [found[1] for found in images(text)] == ["docs/images/missing.png"]
    assert mdcode.code_spans(text) == []


def test_item_html_block_terminator_is_found_after_the_item_indent():
    text = "- Example\n\n    <pre>\n    ` one\n    </pre>\n  " + HTML_IMG + " `\n"
    (start, end), = mdcode.html_block_spans(text)
    assert end <= text.index(HTML_IMG)
