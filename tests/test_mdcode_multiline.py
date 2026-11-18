"""Inline code spans may cross soft line breaks inside one paragraph, never a blank line, fence or ATX heading."""
import pytest

from ctshowcase import mdcode

SAMPLE = "Example ```sample\nTODO``` end."


def test_multiline_span_covers_both_lines_and_masks_content():
    spans = mdcode.code_spans(SAMPLE)
    assert [SAMPLE[a:b] for a, b in spans] == ["```sample\nTODO```"]
    assert "TODO" not in mdcode.masked(SAMPLE)
    assert "end." in mdcode.masked(SAMPLE)


@pytest.mark.parametrize("between", ["\n\n", "\n# Heading\n", "\n  ## Heading\n"])
def test_blocks_between_opener_and_closer_end_the_search(between):
    text = "Example ```sample" + between + "TODO``` end."
    assert mdcode.find_inline_code(text) is None


@pytest.mark.parametrize("between", ["\n\n", "\n# Heading\n"])
def test_no_span_and_content_stays_visible(between):
    text = "Example ```sample" + between + "TODO``` end."
    assert mdcode.code_spans(text) == []
    assert "TODO" in mdcode.masked(text)


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_fence_line_between_yields_no_inline_span(fence):
    text = "Example ```sample\n" + fence + "\nTODO``` end."
    assert mdcode.find_inline_code("Example ```sample\n") is None
    assert all(a != 8 for a, _ in mdcode.code_spans(text))
    assert mdcode.code_spans(text) == [(18, len(text))]


def test_offsets_absolute_around_fenced_block():
    before = "Lead ```a\nb``` mid.\n"
    fence = "\n```\nraw ```x\n```\n\n"
    after = "Tail ```c\nd``` end."
    text = before + fence + after
    spans = mdcode.code_spans(text)
    assert [text[a:b] for a, b in spans] == ["```a\nb```", "```\nraw ```x\n```\n", "```c\nd```"] or len(spans) == 3
    assert text[spans[0][0]:spans[0][1]] == "```a\nb```"
    assert text[spans[-1][0]:spans[-1][1]] == "```c\nd```"
    fenced = [text[a:b] for a, b in spans[1:-1]]
    assert fenced == ["```\nraw ```x\n```\n"]
    masked = mdcode.masked(text)
    assert "raw" not in masked and "a\nb" not in masked.replace("\x00", "") and "end." in masked


@pytest.mark.parametrize("count", range(6))
def test_parity_still_holds_in_multiline_text(count):
    text = "x\n" + "\\" * count + "`code`"
    assert (mdcode.code_spans(text) == []) == bool(count % 2)
