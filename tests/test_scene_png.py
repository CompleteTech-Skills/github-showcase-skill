import io

from PIL import Image

from ctshowcase.pnglint import chunk_types
from ctshowcase.scene import Rect, Scene, Text, png_bytes, to_png_image


def _render(fonts, text):
    sc = Scene(200, 100)
    sc.add(Rect(0, 0, 200, 100, "#000000"), Text("mono-bold", text, 80, 10, 80, "#FFFFFF"))
    return to_png_image(sc, fonts, scale=1)


def test_even_odd_holes(fonts):
    for ch, (x, y) in (("o", (34, 52)), ("8", (34, 37))):
        im = _render(fonts, ch)
        assert im.getpixel((x, y)) == (0, 0, 0), ch  # counter stays background
        assert max(im.getpixel((x2, y)) for x2 in range(10, 60))[0] > 200  # glyph ink present


def test_deterministic_no_metadata(fonts):
    a = png_bytes(_render(fonts, "p8o"))
    b = png_bytes(_render(fonts, "p8o"))
    assert a == b
    kinds = chunk_types(a)
    assert "tEXt" not in kinds and "tIME" not in kinds and "iTXt" not in kinds
    assert Image.open(io.BytesIO(a)).mode == "RGB"
