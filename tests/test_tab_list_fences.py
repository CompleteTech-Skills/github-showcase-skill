"""A tab after a list marker reaches the next four-column stop."""
import pytest

from ctshowcase import mdcode, readme, readmelint


@pytest.mark.parametrize("prefix", ["-\t", "1.\t", "- \t", "> -\t", "> 1.\t"])
@pytest.mark.parametrize("indent,rendered", [(2, True), (3, True), (4, False), (5, False)])
def test_tabbed_item_fence_uses_visual_content_column(prefix, indent, rendered):
    quote = "> " if prefix.startswith(">") else ""
    text = prefix + "```\n" + quote + " " * indent + "![Shot](docs/images/missing.png)\n"
    expected = [("Shot", "docs/images/missing.png")] if rendered else []
    assert readmelint._images(readmelint._outside_code(text), text) == expected
    _, column, rest = mdcode._containers(prefix + "```")
    assert (column, rest) == (4, "```")


def test_tabbed_item_fence_cannot_hide_a_missing_image_from_lint(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    text = readme.scaffold(ctx, "") + "\n-\t```\n  ![Shot](docs/images/missing.png)\n"
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, path)["fails"]
