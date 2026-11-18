"""Reference definitions share the code scanner's visual container columns."""
import pytest

from ctshowcase import readmelint


@pytest.mark.parametrize("prefix", [
    ">\t", "> \t", ">  \t", ">\t ", "-\t", "> -\t", ">\t1. ",
    "> 1.\t", "- >\t", ">\t>\t", ">\t 1. ", ">\t1.\t",
])
def test_tabbed_container_definition_resolves_at_original_source_offsets(prefix):
    text = "![Shot][x]\n\n" + prefix + "[x]: docs/images/missing.png\n"
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "docs/images/missing.png")]
    assert readmelint._images(readmelint._outside_code(text.expandtabs(4)), text.expandtabs(4)) == [
        ("Shot", "docs/images/missing.png")]
    match, = readmelint._definitions(text)
    assert text[slice(*match.span(1))] == "x"
    assert text[slice(*match.span(3))] == "docs/images/missing.png"


@pytest.mark.parametrize("prefix", ["\t", ">\t  ", "> \t  ", ">\t1.     "])
def test_four_residual_columns_are_indented_code_not_definitions(prefix):
    text = "![Shot][x]\n\n" + prefix + "[x]: docs/images/missing.png\n"
    assert readmelint._images(readmelint._outside_code(text), text) == []


def test_tab_inside_literal_label_and_destination_is_not_rewritten():
    text = "![Shot][a b]\n\n>\t[a\tb]: <docs/images/missing.png>\n"
    match, = readmelint._definitions(text)
    assert match.group(1) == "a\tb"
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "docs/images/missing.png")]


@pytest.mark.parametrize("size,expected", [(999, True), (1000, False)])
def test_reference_label_source_length_boundary(size, expected):
    label = "x" * size
    text = f"![Shot][{label}]\n\n>\t[{label}]: docs/images/missing.png\n"
    images = readmelint._images(readmelint._outside_code(text), text)
    assert images == ([("Shot", "docs/images/missing.png")] if expected else [])


def test_whitespace_only_definition_is_not_a_reference_label():
    text = "![  ]\n\n>\t[  ]: docs/images/missing.png\n"
    assert not readmelint._definitions(text)
    assert readmelint._images(readmelint._outside_code(text), text) == []
