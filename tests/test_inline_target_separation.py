"""Rendered images and literal titles differ when target separators are invalid."""
import pytest

from ctshowcase import readmelint

IMAGE = "![Shot](docs/images/missing.png)"


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


@pytest.mark.parametrize("destination", ["<>", "<https://example.test>", "<a b>"])
@pytest.mark.parametrize("quote", ['"', "'", "("])
def test_unseparated_angle_title_cannot_hide_rendered_image(destination, quote):
    # Parenthesized titles cannot nest the image's raw parentheses, so that
    # control uses a complete HTML image rather than an invalid title body.
    inner = IMAGE if quote != "(" else '<img alt="Shot" src="docs/images/missing.png">'
    closing = ")" if quote == "(" else quote
    text = f"[Docs]({destination}{quote}{inner}{closing})"
    assert images(text) == [("Shot", "docs/images/missing.png")]


@pytest.mark.parametrize("title", ['"title"', "'title'", "(title)", r"(escaped\(title\))"])
@pytest.mark.parametrize("destination", ["<>", "<docs/images/missing.png>"])
def test_unseparated_titles_cannot_count_as_rendered_badges(destination, title):
    assert images(f"![Type]({destination}{title})") == []


@pytest.mark.parametrize("separator", [" ", "\t", "\n", "\r\n", " \t\n "])
@pytest.mark.parametrize("quote", ['"', "'"])
def test_separated_titles_remain_literal(separator, quote):
    text = f"[Docs](<https://example.test>{separator}{quote}{IMAGE}{quote})"
    assert images(text) == []


@pytest.mark.parametrize("separator", ["\u00a0", "\u2003", "\v", "\f"])
def test_non_link_whitespace_cannot_separate_a_title(separator):
    assert images(f'![Type](<docs/images/missing.png>{separator}"title")') == []


def test_bare_destination_quotes_are_url_text_without_separator():
    assert images('![Type](docs/images/missing.png"title")') == [("Type", 'docs/images/missing.png"title"')]
    assert images('![Type](docs/images/missing.png "title")') == [("Type", "docs/images/missing.png")]


def test_non_ascii_space_is_valid_destination_text():
    assert images("![Type](docs/images/own\u00a0icon.png)") == [("Type", "docs/images/own\u00a0icon.png")]


@pytest.mark.parametrize("destination", ["docs/images/own\\ icon.png", "<docs/images/own\\\nicon.png>"])
def test_backslash_does_not_escape_non_punctuation_destination_whitespace(destination):
    assert images(f"![Type]({destination})") == []


@pytest.mark.parametrize("prefix", ["- ", "1. ", "> ", "## Heading "])
def test_destination_cannot_start_in_a_different_block(prefix):
    text = '[Docs](\n' + prefix + '"' + IMAGE + '")'
    assert images(text) == [("Shot", "docs/images/missing.png")]


def test_invalid_multiblock_destination_cannot_count_as_image():
    assert images("![Type](\n- )") == []


def test_invalid_outer_target_is_reported_by_real_linter(make_ctx, tmp_path):
    from ctshowcase import readme
    ctx = make_ctx(repo_dir=tmp_path)
    path = tmp_path / "README.md"
    path.write_text(readme.scaffold(ctx, "") + f'\n[Docs](<https://example.test>"{IMAGE}")\n', encoding="utf-8")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, path)["fails"]
