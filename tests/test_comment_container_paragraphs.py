"""Inline markup follows paragraph ancestors, including lazy continuations."""
import pytest

from ctshowcase import mdcode, readmelint

IMAGE = "![Shot](docs/images/missing.png)"


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


@pytest.mark.parametrize("first,second", [
    ("> Text <!--", "2. "),
    ("> Text <!--", "0. "),
    ("> Text <!--", "1. "),
    ("- Text <!--", "2. "),
    ("- > Text <!--", "  2. "),
    ("> - Text <!--", "> 2. "),
])
def test_ordered_list_after_leaving_ancestor_ends_inline_comment(first, second):
    text = first + "\n" + second + IMAGE + " -->\n"
    assert images(text) == [("Shot", "docs/images/missing.png")]


@pytest.mark.parametrize("first,second", [
    ("- > Text <!--", "  > "),
    ("- > Text <!--", "  >\t"),
    ("> - Text <!--", ">   "),
    ("> - > Text <!--", ">   > "),
    ("- - Text <!--", "    "),
    ("1. > Text <!--", "   > "),
])
def test_matched_ancestors_keep_valid_multiline_comment(first, second):
    assert images(first + "\n" + second + IMAGE + " -->\n") == []


@pytest.mark.parametrize("first,second", [
    ("> Text <!--", ""),
    ("- > Text <!--", "  "),
    ("> - Text <!--", ""),
    ("- Text <!--", ""),
])
def test_plain_lazy_continuation_keeps_valid_inline_comment(first, second):
    assert images(first + "\n" + second + IMAGE + " -->\n") == []


def test_same_paragraph_keeps_inline_code_but_new_list_cannot_close_it():
    live = "> Text `\n2. " + IMAGE + "`\n"
    code = "- > Text `\n  > " + IMAGE + "`\n"
    assert images(live) == [("Shot", "docs/images/missing.png")]
    assert images(code) == []
    assert mdcode.inline_code_spans(live) == ()
    assert len(mdcode.inline_code_spans(code)) == 1


@pytest.mark.parametrize("first,second", [
    ("- ## Heading <!--", "  "),
    ("- > ## Heading <!--", "  > "),
    ("> - ## Heading <!--", ">   "),
    ("- - ## Heading <!--", "    "),
])
def test_heading_inside_containers_does_not_open_multiline_inline_region(first, second):
    assert images(first + "\n" + second + IMAGE + " -->\n") == [("Shot", "docs/images/missing.png")]


def test_comment_leaving_quote_reports_missing_image_in_real_linter(make_ctx, tmp_path):
    from ctshowcase import readme
    ctx = make_ctx(repo_dir=tmp_path)
    path = tmp_path / "README.md"
    prefix = readme.scaffold(ctx, "") + "\n"
    path.write_text(prefix + "> Text <!--\n2. " + IMAGE + " -->\n", encoding="utf-8")
    missing = "R7 local image does not resolve: docs/images/missing.png"
    assert missing in readmelint.lint(ctx, path)["fails"]
    path.write_text(prefix + "- > Text <!--\n  > " + IMAGE + " -->\n", encoding="utf-8")
    assert missing not in readmelint.lint(ctx, path)["fails"]
