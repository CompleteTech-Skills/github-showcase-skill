"""Inline-code detection uses arbitrary-length backslash parity before every opening backtick."""
import pytest

from ctshowcase import mdcode


@pytest.mark.parametrize("count", range(8))
def test_find_inline_code_backslash_parity(count):
    text = "\\" * count + "`code`"
    found = mdcode.find_inline_code(text)
    if count % 2:
        assert found is None
    else:
        assert found is not None and text[found[0]:found[1]].endswith("`code`")
    assert (mdcode.code_spans(text) == []) == bool(count % 2)


def test_escaped_backtick_does_not_stop_next_backtick_opening_a_span():
    text = "\\``code` tail"
    spans = mdcode.code_spans(text)
    assert [text[a:b] for a, b in spans] == ["`code`"]


@pytest.mark.parametrize("count", range(8))
def test_masked_hides_only_even_runs(count):
    text = "\\" * count + "`secret`"
    assert ("secret" in mdcode.masked(text)) == bool(count % 2)


def test_fenced_blocks_unchanged_by_parity():
    text = "```\n\\`![x](y.png)`\n```\nafter"
    assert "y.png" not in mdcode.masked(text)
    assert "after" in mdcode.masked(text)
