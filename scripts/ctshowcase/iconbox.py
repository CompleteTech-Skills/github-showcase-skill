"""The icon card shared by `banner` (420x220 card) and `card` (88 px tile): plate, shadow, edge and icon.

Icon precedence (first match wins): --icon, `.github/showcase.yml` icon, `assets/icon.png`, the org mark, then a family
fallback. CompleteTech (T1) families fall back to the light CompleteTech logo (or, in an icon box under 200 px, its
cloud-and-bulb mark, `brand_assets.mark_light`). Every other family (T2, T2-R, T3) falls back to a typeset wordmark of
its own display name on the family plate: a T2 surface never carries the CompleteTech logo.

Plate rule (review P1.2): an icon that brings its own opaque ground (four corners opaque and within ΔE 3 of each other)
fills the card with that ground and is drawn full-bleed, clipped to the card radius, so there is never a plate inside a
plate. Dark plates get a 2 px family-accent edge at 60% so they read on the navy canvas and on GitHub dark.

Custom transparent icons (--icon, showcase.yml icon, assets/icon.png) are fitted by their alpha bounds so transparent
margins do not shrink the art. Any file under assets/brand is treated as bundled artwork and is never fitted, even when
it is selected through --icon or showcase.yml icon; opaque or full-bleed icons, pixel art and blank images are unchanged.
"""
from __future__ import annotations

import math
import re
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageChops

from .color import delta_e, hexstr, luminance
from .context import RepoContext
from .scene import Clip, Picture, Rect, Shadow, Text
from .typeset import Fonts

WORDMARK_SIZES = (64, 56, 48, 44, 40, 36, 32, 28, 24, 22, 20, 18, 16, 14, 13, 12, 11, 10, 9, 8, 7.5, 7, 6.5, 6)
SMALL_BOX = 200      # icon boxes narrower than this use the light mark instead of the full logo
GROUND_DE = 3.0      # corner colours within this ΔE are one ground
DARK_PLATE = 0.2     # relative luminance under which a plate gets the accent edge
PIXEL_GRIDS = (16, 24, 32, 48, 64, 96, 128)
CUSTOM_ICON_SOURCES = frozenset({"cli", "override", "repo"})  # ctx.light_icon sources that are user art, not bundled


def corner_spread(im: Image.Image) -> float | None:
    """Largest pairwise ΔE between the four corners, or None when a corner is not opaque."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    px = [rgba.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if any(p[3] < 255 for p in px):
        return None
    return max(delta_e(a[:3], b[:3]) for a, b in combinations(px, 2))


def corner_ground(im: Image.Image, tolerance: float = GROUND_DE) -> str | None:
    """Hex of the icon's own ground when its four corners are opaque and closer than `tolerance` ΔE to each other
    (`--ground-tolerance`, default GROUND_DE), else None.

    Identical corners (spread 0) always count as one ground, so `--ground-tolerance 0` accepts a perfectly flat
    ground and rejects anything with a measurable difference. A positive tolerance keeps the strict boundary:
    a spread equal to the tolerance is not one ground."""
    spread = corner_spread(im)
    if spread is None or (spread > 0 and spread >= tolerance):
        return None
    rgba = im.convert("RGBA")
    w, h = rgba.size
    px = [rgba.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    return hexstr(tuple(round(sum(p[i] for p in px) / 4) for i in range(3)))


def native_pixels(im: Image.Image) -> Image.Image | None:
    """The pixel-art source at its native grid (an upscaled sprite sampled at cell centres), or None."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    if w != h:
        return None
    src = rgba.load()
    for n in PIXEL_GRIDS:
        if w % n:
            continue
        c = w // n
        small = Image.new("RGBA", (n, n))
        sp = small.load()
        for y in range(n):
            for x in range(n):
                sp[x, y] = src[x * c + c // 2, y * c + c // 2]
        up = small.resize((w, h), Image.NEAREST)
        diff = ImageChops.difference(up, rgba).split()
        same = ImageChops.lighter(ImageChops.lighter(diff[0], diff[1]), ImageChops.lighter(diff[2], diff[3])).histogram()[0]
        if same >= 0.99 * w * h:
            return small
    return None


def alpha_fit(im: Image.Image) -> Image.Image | None:
    """Crop custom transparent art to its alpha bounds, or None when no crop applies.

    Fits custom transparent art by its alpha bounds so transparent margins do not shrink it. Compositor only: the
    source file is never modified, and the input image is neither mutated nor reassigned. Returns None when the image
    is fully transparent (blank) or when the alpha bounds are the whole image (opaque or full-bleed art)."""
    rgba = im.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None or bbox == (0, 0, rgba.width, rgba.height):
        return None
    return rgba.crop(bbox)


def is_bundled_brand_asset(path, root) -> bool:
    """True when `path` resolves under <skill root>/assets/brand, whatever the selection route (cli, override or repo).

    Bundled artwork under assets/brand is never alpha-cropped. Returns False when either path cannot be resolved."""
    try:
        Path(path).resolve().relative_to((Path(root) / "assets" / "brand").resolve())
        return True
    except (ValueError, OSError):
        return False


def feather(im: Image.Image, sides: bool, ends: bool, frac: float = 0.14) -> Image.Image:
    """Blend a full-bleed icon's own ground into the card where the icon does not reach the card edge: an alpha ramp
    over the outer 14% of the ground only (glyphs sit inside the avatar live area, so the mark itself is untouched).
    Avatars with a lifted centre otherwise show their square as a lighter plate inside the card."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    ramp_x = [min(1.0, (min(x, w - 1 - x) + 0.5) / (w * frac)) if sides else 1.0 for x in range(w)]
    ramp_y = [min(1.0, (min(y, h - 1 - y) + 0.5) / (h * frac)) if ends else 1.0 for y in range(h)]
    col = Image.new("L", (w, 1))
    col.putdata([round(255 * v * v * (3 - 2 * v)) for v in ramp_x])
    row = Image.new("L", (1, h))
    row.putdata([round(255 * v * v * (3 - 2 * v)) for v in ramp_y])
    mask = ImageChops.multiply(col.resize((w, h)), row.resize((w, h)))
    rgba.putalpha(ImageChops.multiply(rgba.getchannel("A"), mask))
    return rgba


def _icon_nodes(ctx: RepoContext, im: Image.Image, box, clip=None, fit_alpha: bool = False) -> tuple[list, float | None]:
    x, y, w, h = box
    resample = "lanczos"
    if ctx.style.get("icon_pixel_art"):
        native = native_pixels(im)
        if native is not None:  # integer factor in output pixels (scale 2), nearest-neighbour (§9.5 avatar rule)
            k = math.floor(min(w, h) * 2 / native.width) / 2
            if k >= 0.5:
                im, resample = native, "nearest"
                iw = ih = native.width * k
                pic = Picture(x + (w - iw) / 2, y + (h - ih) / 2, iw, ih, im, "webp", 84, 2, resample)
                # pixel art is meant to be enlarged: no icon-resolution warning (fit None)
                return ([Clip(clip[2], clip[3], clip[4], [pic], clip[0], clip[1])] if clip else [pic]), None
    # icon_pixel_art keeps the retained image size even when the native grid is not recognized (no alpha crop)
    if fit_alpha and not ctx.style.get("icon_pixel_art"):
        trimmed = alpha_fit(im)
        im = trimmed if trimmed is not None else im
    k = min(w / im.width, h / im.height)
    iw, ih = im.width * k, im.height * k
    if clip and (iw < w - 1 or ih < h - 1):
        im = feather(im, iw < w - 1, ih < h - 1)
    pic = Picture(x + (w - iw) / 2, y + (h - ih) / 2, iw, ih, im, "webp", 84, 2, resample)
    return ([Clip(clip[2], clip[3], clip[4], [pic], clip[0], clip[1])] if clip else [pic]), k


def plate(ctx: RepoContext, fonts: Fonts, card: tuple[float, float, float, float], radius: float, inset: float,
          cli_icon: str | None = None, shadow_scale: float = 1.0) -> tuple[list, dict, float | None]:
    """Return (scene nodes, icon info, fit factor or None) for the whole icon card at card = (x, y, w, h)."""
    x, y, w, h = card
    tok = ctx.style["tokens"]
    path, src = ctx.light_icon(cli_icon)
    inner = (x + inset, y + inset, w - 2 * inset, h - 2 * inset)
    im = None
    if path is not None:
        if src == "brand-logo" and inner[2] < SMALL_BOX and ctx.brand.mark_light():
            path, src = ctx.brand.mark_light(), "brand-mark"
        im = Image.open(path)
        im.load()
    fill = tok["card_fill"]
    ground = corner_ground(im) if im is not None else None
    full_bleed = ground is not None and delta_e(ground, fill) >= GROUND_DE
    if ground is not None:
        fill = ground
    sh = tok["card_shadow"]
    nodes: list = [Shadow(x + sh["dx"] * shadow_scale, y + sh["dy"] * shadow_scale, w, h, radius, sh["color"], sh["opacity"],
                          sh.get("blur", 0) * shadow_scale),
                   Rect(x, y, w, h, fill, rx=radius)]
    fit = None
    if im is not None:
        shown = str(path)
        try:  # report bundled files relative to the skill root: no local absolute paths in committed results
            shown = path.resolve().relative_to(ctx.brand.root.resolve()).as_posix()
        except ValueError:
            pass
        box = (x, y, w, h) if full_bleed else inner
        icon_nodes, fit = _icon_nodes(ctx, im, box, (x, y, w, h, radius) if full_bleed else None,
                                      fit_alpha=src in CUSTOM_ICON_SOURCES and not full_bleed
                                      and not is_bundled_brand_asset(path, ctx.brand.root))
        nodes += icon_nodes
        info = {"path": shown, "source": src, "plate": fill, "full_bleed": full_bleed}
    else:
        nodes += wordmark(ctx, fonts, inner)
        info = {"path": None, "source": src, "plate": fill, "full_bleed": False}
    if luminance(fill) < DARK_PLATE:
        nodes.append(Rect(x + 1, y + 1, w - 2, h - 2, None, rx=max(0, radius - 1), stroke=tok["accent"], stroke_width=2,
                          stroke_opacity=0.6))
    return nodes, info, fit


def wordmark(ctx: RepoContext, fonts: Fonts, box: tuple[float, float, float, float]) -> list:
    """The family display name, centred, in the family display font and card ink, over a short accent rule.

    The block is kept to a quiet size (at most 78% of the box width and 52% of its height) so it reads as a mark,
    not a headline, and the rule sits below the font's descenders."""
    x, y, w, h = box
    tok, fk = ctx.style["tokens"], ctx.style["fonts"]
    font = fk.get("display") or fk["title"]
    name = ctx.style.get("company_label") or ctx.org.get("display_name") or ctx.owner
    face = fonts.face(font)
    maxw, maxh = w * 0.78, h * 0.52
    ink = tok.get("card_ink") or tok["ink"]

    def block_h(size: float, n: int) -> float:
        return face.cap * size + (n - 1) * size * 1.15 + face.descent * size + size * 0.18 + max(2.0, size * 0.08)

    def balanced(size: float) -> list[list[str]]:
        """One line, then the 2- and 3-line word splits with the narrowest widest line. A one-word name breaks before
        a dot or after a hyphen (`jevplay` / `.games`), so a domain-style name is not shrunk to an illegible size."""
        words, sep = name.split(), " "
        if len(words) == 1:
            parts = [p for p in re.split(r"(?=\.)|(?<=-)", name) if p]
            if len(parts) > 1:
                words, sep = parts, ""
        opts = [[name]]
        for n in (2, 3):
            if len(words) < n:
                break
            cands = []
            for cut in combinations(range(1, len(words)), n - 1):
                bounds = (0, *cut, len(words))
                cands.append([sep.join(words[a:b]) for a, b in zip(bounds, bounds[1:])])
            opts.append(min(cands, key=lambda ls: max(fonts.width(font, ln, size) for ln in ls)))
        return opts

    best = None
    for size in WORDMARK_SIZES:
        for lines in balanced(size):
            if any(fonts.width(font, ln, size) > maxw for ln in lines):
                continue
            if block_h(size, len(lines)) <= maxh:
                best = (size, lines)
                break
        if best:
            break
    if best is None:  # pragma: no cover - a name too long even at 6 px on three lines
        size = WORDMARK_SIZES[-1]
        best = (size, min(balanced(size), key=lambda ls: max(fonts.width(font, ln, size) for ln in ls)))
    size, lines = best
    lh = size * 1.15
    rule_h = max(2.0, size * 0.08)
    top = y + (h - block_h(size, len(lines))) / 2
    out = []
    widest = 0.0
    last_base = top
    for i, line in enumerate(lines):
        lw = fonts.width(font, line, size)
        widest = max(widest, lw)
        last_base = top + face.cap * size + i * lh
        out.append(Text(font, line, size, x + (w - lw) / 2, last_base, ink))
    rw = min(widest, max(size * 1.6, widest * 0.35))
    rule_y = last_base + face.descent * size + size * 0.18
    rule = tok["accent"] if luminance(ink) > 0.5 else tok["accent_deep"]  # light ink means a dark plate
    out.append(Rect(x + (w - rw) / 2, rule_y, rw, rule_h, rule, rx=rule_h / 2))
    return out
