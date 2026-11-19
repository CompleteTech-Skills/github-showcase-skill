"""Heading boundaries share the Markdown block parser and preserve source offsets."""
import pytest

from ctshowcase import mdcode, readme


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])
@pytest.mark.parametrize("title,section,level", [
    ("# Profile\n", "## Notes\n", 2),
    ("Profile\n=======\n", "Notes\n-----\n", 2),
    ("# Profile\n", "Multiline\nsection title\n---\n", 2),
    ("  # Profile\n", "   ### Notes ###\n", 3),
    ("# Profile\n", "# Another title\n", 1),
    ("Profile\n=======\n", "Another title\n=====\n", 1),
])
def test_heading_source_ranges_and_personal_opening(ending, title, section, level):
    preamble = "> [!NOTE]\n> Synthetic callout.\n\n"
    between = "\nOpening prose.\n\n"
    source = (preamble + title + between + section + "\nAuthored body.\n").replace("\n", ending)
    first = len(preamble.replace("\n", ending))
    boundary = len((preamble + title + between).replace("\n", ending))
    assert mdcode.top_level_heading_spans(source) == (
        (first, first + len(title.replace("\n", ending)), 1),
        (boundary, boundary + len(section.replace("\n", ending)), level),
    )
    assert readme.personal_header_end(source) == boundary


@pytest.mark.parametrize("literal", [
    "```markdown\nNotes\n-----\n## Hidden\n```\n",
    "~~~\nNotes\n-----\n~~~\n",
    "    Notes\n    -----\n    ## Hidden\n",
    "<div>\nNotes\n-----\n## Hidden\n</div>\n",
    "<pre>\nNotes\n-----\n</pre>\n",
    "<!--\nNotes\n-----\n## Hidden\n-->\n",
    "> Notes\n> -----\n> ## Quoted\n",
    "- Notes\n  -----\n  ## Item heading\n",
    "| Notes | Value |\n| ----- | ----- |\n| row | data |\n",
    "[ref]: /synthetic \"Synthetic title\"\n\n-----\n",
    "-----\n",
    "= = =\n",
    "##Not-a-heading\n",
])
@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])
def test_literal_and_container_headings_do_not_end_personal_opening(literal, ending):
    prefix = ("# Profile\n\n" + literal + "\n").replace("\n", ending)
    section = "## Real body\n".replace("\n", ending)
    source = prefix + section
    assert mdcode.top_level_heading_spans(source) == (
        (0, len("# Profile" + ending), 1),
        (len(prefix), len(source), 2),
    )
    assert readme.personal_header_end(source) == len(prefix)


@pytest.mark.parametrize("source", ["Opening prose.\n", "# Profile\n\nOpening prose.\n",
                                    "Profile\n=======\n\nOpening prose.\n"])
def test_without_body_heading_the_opening_extends_to_end(source):
    assert readme.personal_header_end(source) == len(source)


@pytest.mark.parametrize("source", ["## Notes\n", "Notes\n-----\n"])
def test_first_h2_already_starts_authored_body(source):
    assert readme.personal_header_end(source) == 0


def test_heading_consumers_reuse_one_layout_build():
    source = "# Synthetic profile\n\nNotes\n-----\n\nLiteral `code`.\n"
    mdcode._layout.cache_clear()
    mdcode.WORK.clear()
    assert mdcode.inline_regions(source)
    assert len(mdcode.top_level_heading_spans(source)) == 2
    assert readme.personal_header_end(source) == source.index("Notes")
    assert mdcode.WORK["layout_builds"] == 1
