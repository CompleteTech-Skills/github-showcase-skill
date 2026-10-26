"""Org tile SVG, dark only (PROFILE_README_KIT org variant; spec A6.3). No numbers (S16)."""
from __future__ import annotations

import re

from PIL import Image, ImageDraw

from .card import canvas_nodes_card
from .chips import SEP, eyebrow_track
from .iconbox import corner_ground
from .errors import ArtFail, ConfigError
from .scene import Clip, Linear, Picture, Rect, Scene, Shadow, Text, to_png_image, to_svg
from .typeset import Fonts

W, H = 400, 160
PAD, TILE = 16, 88


def rounded(img: Image.Image, px: int, r: int) -> Image.Image:
    """Avatar drawn at px with rounded-square corners (the avatar file itself is not altered)."""
    im = img.convert("RGBA").resize((px, px), Image.LANCZOS)
    m = Image.new("L", (px * 4, px * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, px * 4 - 1, px * 4 - 1], radius=r * 4, fill=255)
    im.putalpha(Image.composite(im.getchannel("A"), Image.new("L", im.size, 0), m.reduce(4)))
    return im


def layout(brand, fonts: Fonts, owner: str, avatar: str | None, illustration: str | None = None):
    org = brand.org(owner)
    if not org.get("known"):
        raise ConfigError(f"no brand.yaml org row for {owner}", log="needs-input:org-row")
    st = brand.style(owner)
    tok, fk = st["tokens"], st["fonts"]
    name = org.get("display_name") or owner
    desc = org.get("description")
    if not desc:
        raise ConfigError(f"{owner} has no §2.3 description", log="needs-input:org-description")
    first = re.split(r"(?<=[.!?])\s+", desc.strip())[0]
    TX = PAD + TILE + 16
    tw = (W - TX - PAD) if not illustration else 136
    label = st["company_label"]
    eb = (f"{label}{SEP}{org['eyebrow']}" if org.get("eyebrow") else label)
    eb = eb.upper() if st.get("eyebrow_case") == "upper" else eb
    track = eyebrow_track(st)
    nsz = fonts.fit(fk["display"], name, (21, 19, 18, 17, 16), tw)
    if nsz is None:
        raise ArtFail("tile-name", name)
    dsz, dl = fonts.wrap_ladder(fk["card_body"], first, (12, 11.5), tw, (2, 3), "tile-description", hyphens=False)
    clip = Clip(W, H, 12, canvas_nodes_card(st))
    bar = tok["bar"]
    clip.children.append(Rect(0, H - 4, W, 4, Linear(((0, bar["from"], 1), (1, bar.get("to") or bar["from"], 1)), "h")))
    sc = Scene(W, H, title=f"{name}: {first}")
    sc.add(clip, Rect(0.5, 0.5, W - 1, H - 1, None, rx=11.5, stroke=tok["edge"]["color"], stroke_opacity=tok["edge"]["opacity"]))
    ty = (H - TILE) / 2 - 2
    sh = tok["card_shadow"]
    sc.add(Shadow(PAD + sh["dx"] / 2, ty + sh["dy"] / 2, TILE, TILE, 16, sh["color"], sh["opacity"], sh.get("blur", 0) / 2))
    im = None
    if avatar:
        im = Image.open(avatar)
        im.load()
    ground = corner_ground(im) if im is not None else None
    if ground:  # the avatar brings its own tile: draw it full-bleed, never a plate inside a plate (review P1.2)
        sc.add(Rect(PAD, ty, TILE, TILE, ground, rx=16),
               Clip(TILE, TILE, 16, [Picture(PAD, ty, TILE, TILE, im, "webp", 86, 2)], PAD, ty))
    else:
        sc.add(Rect(PAD, ty, TILE, TILE, tok["plate_low"], rx=16))
        if im is not None:
            sc.add(Picture(PAD + 8, ty + 8, 72, 72, rounded(im, 144, 28), "webp", 86, 1))
    sc.add(Rect(PAD + 1, ty + 1, TILE - 2, TILE - 2, None, rx=15, stroke=tok["accent"], stroke_width=2, stroke_opacity=0.6))
    y = 46 if len(dl) < 3 else 32
    sc.add(Text(fk["eyebrow"], eb, 10.5 if fonts.width(fk["eyebrow"], eb, 10.5, track) <= tw else 9.5, TX, y, tok["eyebrow"], track))
    y += 8 + nsz * 1.08
    sc.add(Text(fk["display"], name, nsz, TX, y, tok["title"]))
    y += 4
    for ln in dl:
        y += dsz * 1.33
        sc.add(Text(fk["card_body"], ln, dsz, TX, y, tok["body"]))
    if illustration:
        im = Image.open(illustration)
        im.load()
        k = min(128 / im.width, 128 / im.height)
        sc.add(Picture(256 + (128 - im.width * k) / 2, 16 + (128 - im.height * k) / 2, im.width * k, im.height * k, im))
    return sc


def render(brand, fonts: Fonts, owner: str, avatar=None, illustration=None):
    sc = layout(brand, fonts, owner, avatar, illustration)
    return to_svg(sc, fonts, prefix="t"), sc


def preview_png(scene, fonts, scale=2):
    return to_png_image(scene, fonts, scale=scale, alpha_rx=12)
