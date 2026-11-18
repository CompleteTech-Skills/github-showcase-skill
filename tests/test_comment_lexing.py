"""Only valid inline comments suppress rendered content; blocks have their own rules."""
import pytest

from ctshowcase import mdcode, readmelint

IMAGE = "![Shot](docs/images/missing.png)"


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


@pytest.mark.parametrize("begin,end", [
    ("> ", ""), ("-> ", ""), ("text -- ", ""), ("text ", "-"),
    ("text --- ", ""), ("text <!--> ", ""),
])
def test_malformed_inline_comments_leave_markdown_images_live(begin, end):
    text = "Text <!--" + begin + IMAGE + end + "-->\n"
    assert images(text) == [("Shot", "docs/images/missing.png")]


@pytest.mark.parametrize("begin,end", [(" ", " "), ("-text ", ""), ("text - ", ""), ("\n", "\n")])
def test_valid_inline_comments_still_hide_comment_contents(begin, end):
    assert images("Text <!--" + begin + IMAGE + end + "-->\n") == []


@pytest.mark.parametrize("boundary", ["## Heading ", "- ", "> ", "1. "])
def test_inline_comments_cannot_cross_a_new_markdown_block(boundary):
    text = "Text <!-- start\n" + boundary + IMAGE + "\n-->\n"
    assert images(text) == [("Shot", "docs/images/missing.png")]


def test_html_block_comment_retains_its_distinct_permissive_extent():
    # At a block start, <!-- starts a raw HTML block even when it would not be
    # a valid inline HTML token. Markdown inside the block remains literal.
    assert images("<!-- -- body\n## Heading " + IMAGE + "\n-->\n") == []


def test_invalid_inline_comments_are_reported_by_real_linter(make_ctx, tmp_path):
    from ctshowcase import readme
    ctx = make_ctx(repo_dir=tmp_path)
    path = tmp_path / "README.md"
    path.write_text(readme.scaffold(ctx, "") + "\nText <!--> " + IMAGE + " -->\n", encoding="utf-8")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, path)["fails"]


def test_invalid_comment_body_indexing_remains_bounded():
    text = "Text <!--> " * 2000 + IMAGE + " -->"
    readmelint._comment_matches.cache_clear()
    mdcode.WORK.clear()
    assert images(text) == [("Shot", "docs/images/missing.png")]
    assert mdcode.WORK["comment_scan_chars"] <= 12 * len(text)
