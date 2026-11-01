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


def test_pixel_art_unrecognized_grid_keeps_size_no_alpha_fit(tmp_path, make_ctx, fonts):
    """Unrecognized pixel grid with icon_pixel_art keeps the retained image and placement of main (#130 adjudication);
    flag off still fits by alpha bounds."""
    from ctshowcase import iconbox
    ctx = make_ctx(repo_dir=EX / "repos" / "jev-minesweeper", owner="jevplay-games", repo="jev-minesweeper",
                   description="Two-board Minesweeper race against Jev.")
    assert ctx.style.get("icon_pixel_art")

    # Opaque art with transparent margins: alpha_fit would crop it, but no pixel grid matches a 257 px canvas.
    im = Image.new("RGBA", (257, 257), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((60, 90, 200, 200), fill=(250, 200, 40, 255))
    path = tmp_path / "odd-grid-icon.png"
    im = save_and_reopen(im, path)
    assert iconbox.native_pixels(im) is None

    nodes, _, fit = render(ctx, fonts, path)
    found = pics(nodes)
    assert len(found) == 1
    pic = found[0]
    assert pic.image.size == (257, 257)
    assert pic.resample == "lanczos"
    k = min(INNER_W / 257, INNER_H / 257)
    assert pic.w == pytest.approx(257 * k, abs=0.01)
    assert pic.h == pytest.approx(257 * k, abs=0.01)
    assert pic.w == pytest.approx(pic.h, abs=0.01)
    assert fit == pytest.approx(k)

    # Flag-off contrast: the same file is cropped to its alpha bounds, proving the flag prevents the crop.
    ctx.style["icon_pixel_art"] = False
    nodes, _, _ = render(ctx, fonts, path)
    found = pics(nodes)
    assert len(found) == 1
    assert found[0].image.width < 257


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


def _assert_bundled_both_routes(tmp_path, monkeypatch, make_ctx, fonts, name, im):
    """A synthetic transparent-padded file under <root>/assets/brand/ is drawn uncropped via cli_icon and via override."""
    from ctshowcase import iconbox
    skill = tmp_path / "skill"
    path = skill / "assets" / "brand" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    save_and_reopen(im, path)
    ctx = make_ctx()
    monkeypatch.setattr(ctx.brand, "root", skill)
    assert iconbox.is_bundled_brand_asset(path, ctx.brand.root)

    # CLI route: the bundled file handed in directly as the icon argument.
    nodes, info, _ = iconbox.plate(ctx, fonts, CARD, RADIUS, INSET, cli_icon=str(path))
    assert info["source"] == "cli"
    found = pics(nodes)
    assert len(found) == 1
    assert found[0].image.size == (1024, 1024)
    assert found[0].h <= INNER_H + 1

    # Override route: repo dir is skill/assets and the override icon names brand/<name> inside it.
    ov = make_ctx(repo_dir=skill / "assets")
    ov.override = {"icon": f"brand/{name}"}
    nodes, info, _ = iconbox.plate(ov, fonts, CARD, RADIUS, INSET)
    assert info["source"] == "override"
    found = pics(nodes)
    assert len(found) == 1
    assert found[0].image.size == (1024, 1024)
    assert found[0].h <= INNER_H + 1


def test_synthetic_bundled_brand_png_not_fitted_via_cli_and_override(tmp_path, make_ctx, fonts, monkeypatch):
    _assert_bundled_both_routes(tmp_path, monkeypatch, make_ctx, fonts, "synthetic-logo.png", rgba_art())
    _assert_bundled_both_routes(tmp_path, monkeypatch, make_ctx, fonts, "synthetic-palette-logo.png", palette_art())


def test_same_art_outside_bundled_dir_is_still_fitted(tmp_path, make_ctx, fonts):
    from ctshowcase import iconbox
    path = tmp_path / "custom" / "icon.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    save_and_reopen(rgba_art(), path)
    ctx = make_ctx()
    # The guard is path-based: identical art outside <root>/assets/brand/ is still alpha-fitted.
    assert not iconbox.is_bundled_brand_asset(path, ctx.brand.root)

    nodes, info, _ = iconbox.plate(ctx, fonts, CARD, RADIUS, INSET, cli_icon=str(path))
    assert info["source"] == "cli"
    found = pics(nodes)
    assert len(found) == 1
    assert found[0].image.size == BBOX_SIZE
    assert_fits_inner_box(found[0])


def test_every_real_bundled_brand_png_untouched_both_routes(make_ctx, fonts):
    from ctshowcase import iconbox
    ctx = make_ctx()
    # Read-only: the real assets/brand PNGs are only opened, never written.
    pngs = sorted((ctx.brand.root / "assets" / "brand").glob("*.png"))
    assert len(pngs) == 4
    names = {p.name for p in pngs}
    assert {"logo.png", "mark-light.png", "logo-dark.png", "logo-dark-full.png"} <= names

    for p in pngs:
        with Image.open(p) as src:
            expected = src.size
        assert iconbox.is_bundled_brand_asset(p, ctx.brand.root)

        # CLI route. Pixel-art or full-bleed cases would be Clip-wrapped; pics() flattens Clip children.
        nodes, info, _ = iconbox.plate(ctx, fonts, CARD, RADIUS, INSET, cli_icon=str(p))
        assert info["source"] == "cli"
        found = pics(nodes)
        assert len(found) == 1, p.name
        assert found[0].image.size == expected, p.name

        # Override route: the repo dir is the real assets/ folder and the override icon is brand/<name>.
        ov = make_ctx(repo_dir=p.parent.parent)
        ov.override = {"icon": f"brand/{p.name}"}
        nodes, info, _ = iconbox.plate(ov, fonts, CARD, RADIUS, INSET)
        assert info["source"] == "override"
        found = pics(nodes)
        assert len(found) == 1, p.name
        assert found[0].image.size == expected, p.name


def test_is_bundled_brand_asset_paths(tmp_path):
    from ctshowcase import iconbox
    root = tmp_path / "root"
    assert iconbox.is_bundled_brand_asset(root / "assets" / "brand" / "a.png", root) is True
    assert iconbox.is_bundled_brand_asset(root / "assets" / "icon.png", root) is False
    assert iconbox.is_bundled_brand_asset(root / "assets" / "brand-x" / "a.png", root) is False
    assert iconbox.is_bundled_brand_asset(tmp_path / "outside" / "assets" / "brand" / "a.png", root) is False
    # A traversal that leaves the brand folder resolves to assets/icon.png and is not bundled.
    assert iconbox.is_bundled_brand_asset(root / "assets" / "brand" / ".." / "icon.png", root) is False
