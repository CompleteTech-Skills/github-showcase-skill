"""Contact sheets for set reviews (decision 10; spec A6.12): each input on GitHub dark and light page colours."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .errors import ShowcaseError
from .scene import Scene, Text, png_bytes, to_png_image
from .typeset import Fonts


def render_svg(path: Path) -> Image.Image | None:
    """Static frame of an SVG at 2x through the optional resvg_py package (no CSS animation, like GitHub's image
    proxy fallbacks and many renderers): the intro's resting state is judged here. None when resvg_py is absent."""
    try:
        import resvg_py
    except ImportError:
        return None
    import io
    try:
        data = bytes(resvg_py.svg_to_bytes(svg_path=str(path), zoom=2))
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as exc:  # noqa: BLE001 - any renderer failure is a usage error for this input
        raise ShowcaseError(f"{path.name}: cannot render the SVG ({exc})", log="usage")
    return im


def load_input(path: Path) -> Image.Image:
    if path.suffix.lower() == ".svg":
        png = path.with_suffix(".png")
        if not png.is_file():
            im = render_svg(path)
            if im is None:
                raise ShowcaseError(f"{path.name}: SVG inputs need a PNG preview sibling ({png.name}; `card --png`, "
                                    "`org-tile --png`) or the optional resvg_py package (pip install resvg_py)", log="usage")
            return im.convert("RGBA")
        path = png
    im = Image.open(path)
    im.load()
    return im.convert("RGBA")


def build(inputs: list[Path], out: Path, brand, fonts: Fonts, mode: str = "grid", tile: int = 400, cols: int | None = None,
          gap: int = 24, widths=(1012, 390), mask: str = "none", labels: bool = False, title: str | None = None) -> list[Path]:
    rev = brand.raw["review"]
    images = [(p, load_input(p)) for p in inputs]
    written = []
    for theme, bg, lab in (("dark", rev["bg_dark"], rev["label_dark"]), ("light", rev["bg_light"], rev["label_light"])):
        tiles = []
        if mode == "stack":
            for p, im in images:
                for w in widths:
                    h = round(im.height * w / im.width)
                    tiles.append((p, im.resize((w, h), Image.LANCZOS), f"{p.name} @ {w}px"))
            cols_ = 1
        elif mode == "avatar":
            big = []
            for p, im in images:
                for size in (32, 128):
                    t = im.resize((size, size), Image.LANCZOS)
                    if mask in ("circle", "rounded"):
                        m = Image.new("L", (size * 4, size * 4), 0)
                        d = ImageDraw.Draw(m)
                        if mask == "circle":
                            d.ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
                        else:
                            d.rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=size * 4 // 6, fill=255)
                        a = t.getchannel("A")
                        from PIL import ImageChops
                        t.putalpha(ImageChops.multiply(a, m.reduce(4)))
                    big.append((p, t, p.stem if size == 128 else ""))
            tiles = big
            cols_ = cols or 8
        else:
            for p, im in images:
                h = round(im.height * tile / im.width)
                tiles.append((p, im.resize((tile, h), Image.LANCZOS), p.name))
            cols_ = cols or max(1, min(3, len(tiles)))
        rows = [tiles[i:i + cols_] for i in range(0, len(tiles), cols_)]
        lab_h = 22 if labels else 0
        title_h = 36 if title else 0
        col_w = [max((r[c][1].width for r in rows if c < len(r)), default=0) for c in range(cols_)]
        row_h = [max(t[1].height for t in r) + lab_h for r in rows]
        W = gap + sum(w + gap for w in col_w)
        H = gap + title_h + sum(h + gap for h in row_h)
        sheet = Image.new("RGBA", (max(W, 200), H), bg)
        if title:
            sc = Scene(max(W, 200), title_h)
            sc.add(Text("poppins-semibold", title, 16, gap, 24, lab))
            _paste_text(sheet, sc, fonts, bg, (0, gap // 2))
        y = gap + title_h
        for r, rh in zip(rows, row_h):
            x = gap
            for c, (p, im, name) in enumerate(r):
                sheet.alpha_composite(im, (x, y))
                if labels and name:
                    sc = Scene(col_w[c], lab_h)
                    sc.add(Text("poppins-regular", name, 12, 0, 16, lab))
                    _paste_text(sheet, sc, fonts, bg, (x, y + im.height + 2))
                x += col_w[c] + gap
            y += rh + gap
        stem = out.name[:-len(out.suffix)] if out.suffix else out.name
        target = out.with_name(f"{stem}.on-github-{theme}.png")  # proofing surfaces, not -dark/-light asset variants
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png_bytes(sheet.convert("RGB"), quantize=True))
        written.append(target)
    return written


# STANDARD §9.0 G4 cross-surface gate: (key, label, width in px on the sheet; the avatar is square)
CROSS_SURFACES = (("avatar", "Org avatar at 32 px", 32), ("banner", "README hero banner", 1012),
                  ("card", "Repo card", 400), ("social", "Social preview", 640), ("org_banner", "Org profile banner", 1012))


def _rounded(im: Image.Image, size: int) -> Image.Image:
    """The avatar as GitHub shows an org avatar: a rounded square at `size` px."""
    t = im.resize((size, size), Image.LANCZOS)
    m = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=size * 4 // 6, fill=255)
    from PIL import ImageChops
    t.putalpha(ImageChops.multiply(t.getchannel("A"), m.reduce(4)))
    return t


def build_cross_surface(org: str, surfaces: dict[str, Path | None], out: Path, brand, fonts: Fonts,
                        gap: int = 24) -> tuple[list[Path], list[str]]:
    """`contact-sheet --org ORG --cross-surface` (G4): the org avatar at 32 px, a hero banner, a repo card, the social
    preview and the org banner on one sheet, labelled, on the GitHub dark and light page colours (brand.yaml
    `review`). Missing surfaces are logged `needs-input:cross-surface:<key>`; the sheet shows the rest."""
    rev = brand.raw["review"]
    have = [(k, lab, w, load_input(Path(surfaces[k]))) for k, lab, w in CROSS_SURFACES if surfaces.get(k)]
    logs = [f"needs-input:cross-surface:{k}" for k, _, _ in CROSS_SURFACES if not surfaces.get(k)]
    if not have:
        raise ShowcaseError("contact-sheet --cross-surface needs at least one of --avatar, --banner, --card, --social, "
                            "--org-banner", log="usage")
    title, lab_h, title_h = f"{org}: cross-surface review (G4)", 22, 36
    written = []
    for theme, bg, lab in (("dark", rev["bg_dark"], rev["label_dark"]), ("light", rev["bg_light"], rev["label_light"])):
        tiles = []
        for k, label, w, im in have:
            img = _rounded(im, w) if k == "avatar" else im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
            tiles.append((label, img))
        W = gap * 2 + max(max(im.width for _, im in tiles), 480)
        H = gap + title_h + sum(lab_h + im.height + gap for _, im in tiles)
        sheet = Image.new("RGBA", (W, H), bg)
        sc = Scene(W, title_h)
        sc.add(Text("poppins-semibold", title, 16, gap, 24, lab))
        _paste_text(sheet, sc, fonts, bg, (0, gap // 2))
        y = gap + title_h
        for label, im in tiles:
            sc = Scene(W - gap, lab_h)
            sc.add(Text("poppins-regular", label, 12, 0, 16, lab))
            _paste_text(sheet, sc, fonts, bg, (gap, y))
            sheet.alpha_composite(im, (gap, y + lab_h))
            y += lab_h + im.height + gap
        stem = out.name[:-len(out.suffix)] if out.suffix else out.name
        target = out.with_name(f"{stem}.on-github-{theme}.png")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png_bytes(sheet.convert("RGB"), quantize=True))
        written.append(target)
    return written, logs


def _paste_text(sheet, scene, fonts, bg, pos):
    img = to_png_image(scene, fonts, scale=1, background=bg)
    sheet.alpha_composite(img.convert("RGBA"), pos)
