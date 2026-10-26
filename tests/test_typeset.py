import pytest

from ctshowcase.errors import ArtFail
from ctshowcase.typeset import split_last_hyphen


def test_width_stable(fonts):
    a = fonts.width("mono-bold", "php2shell-check", 56)
    assert abs(a - fonts.width("mono-bold", "php2shell-check", 56)) < 0.01
    assert abs(a - 15 * 0.6 * 56) < 1  # JetBrains Mono advance 600/1000


def test_tracking_widens(fonts):
    assert fonts.width("poppins-semibold", "SKILLS", 22, 0.12) > fonts.width("poppins-semibold", "SKILLS", 22)


def test_ladder(fonts):
    assert fonts.fit("mono-bold", "short", (56, 52), 704) == 56
    assert fonts.fit("mono-bold", "x" * 20, (56, 52, 48, 44, 40, 36), 704) == 56
    assert fonts.fit("mono-bold", "x" * 23, (56, 52, 48, 44, 40, 36), 704) == 48
    assert fonts.fit("mono-bold", "x" * 60, (56, 40), 704) is None


def test_hyphen_wrap(fonts):
    lines = split_last_hyphen(fonts, "mono-bold", "completetech-manageengine-servicedesk-mcp-bridge", 40, 704)
    assert lines and "".join(lines) == "completetech-manageengine-servicedesk-mcp-bridge"
    assert lines[0].endswith("-")


def test_wrap_and_artfail(fonts):
    lines = fonts.wrap("poppins-regular", "one two three four five six seven", 12, 80, 5)
    assert lines and " ".join(lines) == "one two three four five six seven"
    with pytest.raises(ArtFail):
        fonts.wrap_ladder("poppins-regular", "word " * 80, (12, 11.5), 100, (2, 3), "x")


def test_outline_defs_dedupe(fonts):
    from ctshowcase.scene import Scene, Text, to_svg
    sc = Scene(400, 160, title="t")
    sc.add(Text("mono-medium", "aaaa", 20, 0, 50, "#FFFFFF"))
    svg = to_svg(sc, fonts)
    assert svg.count('<path id="') == 1 and svg.count("<use ") == 4 and "<text" not in svg and "…" not in svg
