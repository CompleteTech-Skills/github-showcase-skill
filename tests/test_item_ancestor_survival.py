"""A deeper quote/item ending must not discard a still-open outer list item."""
import pytest

from ctshowcase import mdcode, readme, readmelint

IMAGE = "![Shot](docs/images/missing.png)"


@pytest.mark.parametrize("nested", ["- > - ", "- > 1. ", "1. > - ", "> - > - "])
@pytest.mark.parametrize("surface", ["```text", "<pre>", "<div>"])
def test_later_opened_surface_keeps_surviving_outer_item(nested, surface):
    outer = "> " if nested.startswith(">") else ""
    width = 3 if nested.startswith("1.") else 2
    text = nested + "Example\n\n" + outer + " " * width + surface + "\n" + IMAGE + "\n"
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "docs/images/missing.png")]


def test_later_fence_still_protects_documented_markers_inside_outer_item():
    text = "- > - Example\n\n  ```text\n  <!-- showcase:tagline:start -->\n  Example\n"
    text += "  <!-- showcase:tagline:end -->\n  ```\n\n" + IMAGE
    assert not mdcode.find_blocks(readme.MARK, text)
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "docs/images/missing.png")]
