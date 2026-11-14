"""A tab after a list marker reaches the next four-column stop."""
import pytest

from ctshowcase import mdcode, readme, readmelint


@pytest.mark.parametrize("prefix,column", [("-\t", 4), ("1.\t", 4), ("- \t", 4), ("> -\t", 2), ("> 1.\t", 6)])
@pytest.mark.parametrize("indent", [2, 3, 4, 5, 6])
def test_tabbed_item_fence_uses_visual_content_column(prefix, column, indent):
    quote = "> " if prefix.startswith(">") else ""
    text = prefix + "```\n" + quote + " " * indent + "![Shot](docs/images/missing.png)\n"
    # Leaving the item ends its fence. Four remaining columns still form a
    # separate indented code block in the quote, rather than a rendered image.
    expected = [("Shot", "docs/images/missing.png")] if indent < min(column, 4) else []
    assert readmelint._images(readmelint._outside_code(text), text) == expected
    if 4 <= indent < column:
        assert mdcode.fence_spans(text) == ((0, len(prefix + "```\n")),)
        assert len(mdcode.code_block_spans(text)) == 2
    _, measured, rest = mdcode._containers(prefix + "```")
    assert (measured, rest) == (column, "```")


def test_tabbed_item_fence_cannot_hide_a_missing_image_from_lint(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    text = readme.scaffold(ctx, "") + "\n-\t```\n  ![Shot](docs/images/missing.png)\n"
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, path)["fails"]
