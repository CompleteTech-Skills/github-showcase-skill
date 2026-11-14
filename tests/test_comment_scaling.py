"""Rejected inline comment openers must not repeatedly rescan a distant closer."""
import pytest

from ctshowcase import mdcode, readmelint

IMAGE = "![Shot](docs/images/missing.png)"


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


def measure(n):
    text = ("text <!--\n\n" * n) + "-->\n\n" + IMAGE
    readmelint._comment_matches.cache_clear()
    readmelint._outside_code.cache_clear()
    readmelint._definitions.cache_clear()
    readmelint._definition_spans.cache_clear()
    mdcode.WORK.clear()
    assert images(text) == [("Shot", "docs/images/missing.png")]
    return len(text), dict(mdcode.WORK)


def test_invalid_comment_index_work_is_bounded_by_document_size():
    small_size, small = measure(200)
    large_size, large = measure(800)
    # Each version of the text used by the image pipeline gets at most one
    # cached index. Three full delimiter passes replace unbounded suffix scans.
    assert 0 < small["comment_builds"] <= 3
    assert 0 < large["comment_builds"] <= 3
    assert small["comment_scan_chars"] <= 9 * small_size
    assert large["comment_scan_chars"] <= 9 * large_size
    assert large["comment_scan_chars"] <= 4.1 * small["comment_scan_chars"]


def test_invalid_comment_search_does_not_call_unbounded_regex_search(monkeypatch):
    class NoSuffixSearch:
        def search(self, *args):
            raise AssertionError("comments must use indexed delimiters, not suffix regex searches")

        def match(self, *args):
            raise AssertionError("indexed spans must not rescan overlapping comment bodies")

    monkeypatch.setattr(readmelint, "HTML_COMMENT", NoSuffixSearch())
    measure(300)


@pytest.mark.parametrize("prefix,suffix,expected", [
    ("<!-- block\n\n", "-->\n", []),
    ("text <!-- inline\n\n", "-->\n", [("Shot", "docs/images/missing.png")]),
    ("text <!-- inline\n", "-->\n", []),
    ("\\<!-- escaped\n", "-->\n", [("Shot", "docs/images/missing.png")]),
])
def test_comment_paragraph_and_block_rules_remain_distinct(prefix, suffix, expected):
    assert images(prefix + IMAGE + "\n" + suffix) == expected


def test_literal_attribute_opener_does_not_hide_later_real_comment():
    # The first indexed opener belongs to an attribute; the later nested opener
    # is a real comment after that tag. Candidate indexing must retain both.
    text = '<span data-x="<!--">outside</span> <!-- ' + IMAGE + ' -->\n\n' + IMAGE
    assert images(text) == [("Shot", "docs/images/missing.png")]


def test_literal_reference_label_opener_does_not_hide_later_real_comment():
    text = '[Docs][<!--]\n\n[<!--]: /docs\n\n<!-- ' + IMAGE + ' -->\n\n' + IMAGE
    assert images(text) == [("Shot", "docs/images/missing.png")]
