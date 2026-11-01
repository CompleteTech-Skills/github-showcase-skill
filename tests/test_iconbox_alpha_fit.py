"""Issue #130: custom transparent icon art is fitted by its alpha bounds inside the icon plate (compositor only).

Every image is synthetic and generated under tmp_path; no committed raster is read or edited. Geometry is derived
from the card (56, 70, 420, 220), radius 24 and inset 28 used by the banner, so the inner box is 364 x 164.
"""
import pytest
from PIL import Image, ImageDraw

from conftest import EX

CARD = (56, 70, 420, 220)
RADIUS = 24
INSET = 28
INNER_W, INNER_H = 364, 164
BBOX = (168, 236, 856, 787)  # PIL-style (left, top, right exclusive, bottom exclusive): 688 x 551
BBOX_SIZE = (688, 551)


def pics(nodes):
    return [c for n in nodes for c in getattr(n, "children", [n]) if type(c).__name__ == "Picture"]


def save_and_reopen(im, path):
    im.save(path, format="PNG")
    reopened = Image.open(path)
    reopened.load()
    return reopened


def palette_art(size=1024):
    """Mode P with palette transparency: index 0 is the transparent background, index 1 the coloured artwork."""
    im = Image.new("P", (size, size), 0)
    palette = [255, 255, 255, 200, 30, 30] + [0, 0, 0] * 254
    im.putpalette(palette)
    im.paste(1, BBOX)
    im.info["transparency"] = 0
    return im


def rgba_art(size=1024):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    im.paste((200, 30, 30, 255), BBOX)
    return im


def render(ctx, fonts, path):
    from ctshowcase import iconbox
    return iconbox.plate(ctx, fonts, CARD, RADIUS, INSET, cli_icon=str(path))


def assert_fits_inner_box(pic):
    assert abs(pic.w / pic.h - BBOX_SIZE[0] / BBOX_SIZE[1]) < 0.01
    assert pic.w >= INNER_W - 1 or pic.h >= INNER_H - 1
    # The old whole-canvas behaviour drew the 1024 px square at 164 px, so the 688 px content was 110.2 px wide.
    assert pic.w > 164 * 688 / 1024 + 1


def test_alpha_fit_palette_transparency(tmp_path, make_ctx, fonts):
    from ctshowcase import iconbox
    path = tmp_path / "palette-icon.png"
    im = save_and_reopen(palette_art(), path)
    assert im.mode == "P"
    assert im.info.get("transparency") == 0

    fitted = iconbox.alpha_fit(im)
    assert fitted is not None
    assert fitted.mode == "RGBA"
    assert fitted.size == BBOX_SIZE

    nodes, info, _ = render(make_ctx(), fonts, path)
    assert info["full_bleed"] is False
    found = pics(nodes)
    assert len(found) == 1
    assert_fits_inner_box(found[0])


def test_alpha_fit_rgba(tmp_path, make_ctx, fonts):
    from ctshowcase import iconbox
    path = tmp_path / "rgba-icon.png"
    im = save_and_reopen(rgba_art(), path)
    assert im.mode == "RGBA"

    fitted = iconbox.alpha_fit(im)
    assert fitted is not None
    assert fitted.mode == "RGBA"
    assert fitted.size == BBOX_SIZE

    nodes, info, _ = render(make_ctx(), fonts, path)
    assert info["full_bleed"] is False
    found = pics(nodes)
    assert len(found) == 1
    assert_fits_inner_box(found[0])


def test_blank_transparency_unchanged(tmp_path, make_ctx, fonts):
    from ctshowcase import iconbox
    path = tmp_path / "blank-icon.png"
    im = save_and_reopen(Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)), path)

    assert iconbox.alpha_fit(im) is None

    nodes, _, _ = render(make_ctx(), fonts, path)
    found = pics(nodes)
    assert len(found) == 1
    assert found[0].w == pytest.approx(164, abs=0.01)
    assert found[0].h == pytest.approx(164, abs=0.01)


def test_opaque_and_full_bleed_unchanged(tmp_path, make_ctx, fonts):
    from ctshowcase import iconbox

    # An opaque solid-colour image has no transparent pixels, so there is nothing to fit.
    solid_path = tmp_path / "solid-icon.png"
    solid = save_and_reopen(Image.new("RGB", (1024, 1024), (30, 120, 200)), solid_path)
    assert iconbox.alpha_fit(solid) is None

    # An opaque striped image (no transparency at all) is also left alone.
    striped = Image.new("RGB", (1024, 1024), (240, 240, 240))
    draw = ImageDraw.Draw(striped)
    for x in range(0, 1024, 64):
        draw.rectangle((x, 0, x + 31, 1023), fill=(20, 60, 140))
    striped_path = tmp_path / "striped-icon.png"
    striped = save_and_reopen(striped, striped_path)
    assert iconbox.alpha_fit(striped) is None

    # Alpha 255 everywhere with a distinctive ground: drawn full-bleed over the whole card, never cropped.
    ground_path = tmp_path / "ground-icon.png"
    ground = Image.new("RGBA", (1024, 1024), (230, 60, 140, 255))
    ground = save_and_reopen(ground, ground_path)
    assert iconbox.alpha_fit(ground) is None

    nodes, info, _ = render(make_ctx(), fonts, ground_path)
    assert info["full_bleed"] is True
    found = pics(nodes)
    assert len(found) == 1
    pic = found[0]
    # Whole-canvas geometry: the 1024 px square is scaled to the card height (220) and centred horizontally.
    scale = min(CARD[2] / 1024, CARD[3] / 1024)
    assert pic.w == pytest.approx(1024 * scale, abs=0.01)
    assert pic.h == pytest.approx(1024 * scale, abs=0.01)
    assert pic.x == pytest.approx(CARD[0] + (CARD[2] - 1024 * scale) / 2, abs=0.01)
    assert pic.y == pytest.approx(CARD[1], abs=0.01)
    assert pic.image.size == (1024, 1024)


def test_fully_covered_alpha_bbox_returns_none(tmp_path):
    from ctshowcase import iconbox
    # Transparent corners, but a cross of opaque pixels touches all four edges: the alpha bbox is the whole canvas.
    im = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    im.paste((30, 120, 200, 255), (0, 462, 1024, 562))
    im.paste((30, 120, 200, 255), (462, 0, 562, 1024))
    path = tmp_path / "cross-icon.png"
    im = save_and_reopen(im, path)
    assert im.getpixel((0, 0))[3] == 0
    assert iconbox.alpha_fit(im) is None


def test_pixel_art_sizing_unchanged(tmp_path, make_ctx, fonts):
    from ctshowcase import iconbox
    ctx = make_ctx(repo_dir=EX / "repos" / "jev-minesweeper", owner="jevplay-games", repo="jev-minesweeper",
                   description="Two-board Minesweeper race against Jev.")
    nodes, info, _ = iconbox.plate(ctx, fonts, (56, 70, 420, 220), 24, 28)
    found = pics(nodes)
    assert info["plate"] == "#F386A1"
    assert found[0].resample == "nearest"
    assert (found[0].w * 2) % found[0].image.width == 0

    # A 16 x 16 sprite upscaled x16 to 256 px with a transparent margin of three cells on each side.
    sprite = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    draw.rectangle((3, 3, 12, 12), fill=(250, 200, 40, 255))
    draw.rectangle((6, 6, 9, 9), fill=(20, 20, 20, 255))
    big = sprite.resize((256, 256), Image.NEAREST)
    path = tmp_path / "sprite-icon.png"
    big = save_and_reopen(big, path)

    assert ctx.style.get("icon_pixel_art")
    nodes, _, fit = render(ctx, fonts, path)
    found = pics(nodes)
    assert len(found) == 1
    pic = found[0]
    assert pic.resample == "nearest"
    assert (pic.w * 2) % pic.image.width == 0
    # Native 16-cell grid kept: not cropped to the alpha bbox (which would be 10 cells wide).
    assert pic.image.width == 16
    assert fit is None


def test_bundled_brand_marks_and_logos_untouched(make_ctx, fonts):
    from ctshowcase import iconbox
    assert iconbox.CUSTOM_ICON_SOURCES == {"cli", "override", "repo"}

    # No icon argument and no repo: the bundled CompleteTech light logo is drawn at its own size.
    ctx = make_ctx()
    nodes, info, _ = iconbox.plate(ctx, fonts, CARD, RADIUS, INSET)
    assert info["source"] == "brand-logo"
    assert info["source"] not in iconbox.CUSTOM_ICON_SOURCES
    bundled = ctx.brand.logo_light()
    assert pics(nodes)[0].image.size == Image.open(bundled).size

    # Small icon boxes use the bundled light mark, which must also stay uncropped.
    small = (56, 70, 120, 120)
    nodes, info, _ = iconbox.plate(ctx, fonts, small, RADIUS, INSET)
    assert info["source"] == "brand-mark"
    assert info["source"] not in iconbox.CUSTOM_ICON_SOURCES
    assert pics(nodes)[0].image.size == Image.open(ctx.brand.mark_light()).size


def test_org_mark_untouched(tmp_path, make_ctx, fonts):
    from ctshowcase import iconbox
    # A synthetic org mark with transparent margins: the org-mark source is a bundled-brand path, never fitted.
    mark = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(mark).rectangle((128, 128, 383, 383), fill=(20, 60, 140, 255))
    mark_path = tmp_path / "org-mark.png"
    mark.save(mark_path, format="PNG")
    ctx = make_ctx()
    ctx.org = dict(ctx.org, mark=str(mark_path))
    nodes, info, _ = iconbox.plate(ctx, fonts, CARD, RADIUS, INSET)
    assert info["source"] == "org-mark"
    assert info["source"] not in iconbox.CUSTOM_ICON_SOURCES
    assert pics(nodes)[0].image.size == (512, 512)


def test_source_png_not_modified(tmp_path, make_ctx, fonts):
    path = tmp_path / "palette-source.png"
    save_and_reopen(palette_art(), path)
    before = path.read_bytes()

    render(make_ctx(), fonts, path)

    assert path.read_bytes() == before
    assert Image.open(path).mode == "P"
