"""Repo social preview (1280x640, R10) and org banner (1600x400): STANDARD §9.2/§9.5 sizes, dark design (decision 21).

Both reuse the banner's family canvas, icon card and accent bar, so a repository's preview, banner and card read as
one set. Text is typeset and outlined like every other surface; nothing here is drawn by an image model.
"""
from __future__ import annotations

import io

from PIL import Image

from . import chips as chipmod
from . import iconbox
from .banner import canvas_nodes
from .context import RepoContext
from .errors import ArtFail
from .readme import product_name
from .scene import Circle, Linear, Picture, Rect, Scene, Text, png_bytes, to_png_image
from .typeset import Fonts

SW, SH = 1280, 640
S_X, S_TW = 64, 600
S_CARD = (720, 136, 496, 344)
S_TITLE = (64, 60, 56, 52, 48)
S_CAPTION = (24, 22, 20)
SOCIAL_BUDGET = 900_000

OW, OH = 1600, 400
ORG_BUDGET = 400_000


def _bar(tok: dict, w: float, h: float) -> Rect:
    bar = tok["bar"]
    bh = bar.get("height", 6)
    return Rect(0, h - bh, w, bh, Linear(((0, bar["from"], 1), (1, bar.get("to") or bar["from"], 1)), "h"))


def social_layout(ctx: RepoContext, fonts: Fonts, title: str | None = None, icon: str | None = None) -> tuple[Scene, dict]:
    st = ctx.style
    tok, fk = st["tokens"], st["fonts"]
    desc = ctx.require_description()
    sc = Scene(SW, SH, title=f"{ctx.repo} by {ctx.company}: {desc}")
    sc.add(*canvas_nodes(st, SW, SH))
    track = chipmod.eyebrow_track(st)
    eb = chipmod.eyebrow_text(ctx)
    eb_size = fonts.fit(fk["eyebrow"], eb, (22, 20, 18), S_TW, track)
    if eb_size is None:
        eb = st["company_label"].upper() if st.get("eyebrow_case") == "upper" else st["company_label"]
        eb_size = 18
    sc.add(Text(fk["eyebrow"], eb, eb_size, S_X, 84, tok["eyebrow"], track))
    name = title or product_name(ctx)
    t_font = fk.get("display") or fk["title"]
    t_size = t_lines = None
    for size in S_TITLE:
        lines = fonts.wrap(t_font, name, size, S_TW, 2)
        if lines:
            t_size, t_lines = size, lines
            break
    if not t_lines:
        raise ArtFail("social-title", name)
    face = fonts.face(t_font)
    y = 150 + face.cap * t_size
    for ln in t_lines:
        sc.add(Text(t_font, ln, t_size, S_X, y, tok["title"]))
        y += t_size * 1.19
    rule_y = max(340, y - t_size * 1.19 + 40)
    sc.add(Rect(S_X, rule_y, 120, 4, tok["accent_deep"], rx=2),
           Circle(S_X + 120 + 6, rule_y + 2, 6, tok["plate_low"], tok["gold_trace"], 3))
    cat = None if chipmod.fallback_category(ctx) else ctx.det.get("category")
    cy = rule_y + 32
    if cat:
        sc.add(Text(fk["card_chip_attr"], cat, 28, S_X, cy + 22, tok["accent"]))
        cy += 48
    cap = None
    for size in S_CAPTION:
        lines = fonts.wrap(fk["subtitle"], desc, size, S_TW, 3, hyphens=False)
        if lines and cy + len(lines) * 32 <= 548:
            cap = (size, lines)
            break
    if cap is None:
        raise ArtFail("social-caption", desc)
    yy = cy + 24
    for ln in cap[1]:
        sc.add(Text(fk["subtitle"], ln, cap[0], S_X, yy, tok["subtitle"]))
        yy += 32
    foot = f"github.com/{ctx.owner}/{ctx.repo}"
    fsize = 20 if fonts.width("mono-regular", foot, 20) <= SW - 128 else 16
    sc.add(Text("mono-regular", foot, fsize, S_X, 588, tok["muted"]))
    x, y0, w, h = S_CARD
    nodes, icon_info, _ = iconbox.plate(ctx, fonts, (x, y0, w, h), 32, 44, icon)
    sc.add(*nodes)
    sc.add(_bar(tok, SW, SH))
    return sc, {"title_lines": t_lines, "title_size": t_size, "caption_lines": cap[1], "icon": icon_info, "eyebrow": eb}


def social_render(ctx: RepoContext, fonts: Fonts, title: str | None = None, icon: str | None = None) -> tuple[bytes, str, dict]:
    """(bytes, format, info): PNG within 900 KB, else JPG q85 (STANDARD §9.2)."""
    sc, info = social_layout(ctx, fonts, title, icon)
    img = to_png_image(sc, fonts, scale=1)
    data = png_bytes(img)
    if len(data) <= SOCIAL_BUDGET:
        return data, "png", info
    data = png_bytes(img, quantize=True)
    if len(data) <= SOCIAL_BUDGET:
        return data, "png", info
    b = io.BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=85, optimize=True)
    return b.getvalue(), "jpg", info


def org_banner_layout(brand, fonts: Fonts, owner: str, illustration: str | None = None) -> Scene:
    org = brand.org(owner)
    st = brand.style(owner)
    tok, fk = st["tokens"], st["fonts"]
    name = org.get("display_name") or owner
    sc = Scene(OW, OH, title=f"{name}")
    sc.add(*canvas_nodes(st, OW, OH))
    if st["name"] == "completetech":
        im = Image.open(brand.dark_master())
        im.load()
        k = min(480 / im.width, 240 / im.height)
        sc.add(Picture(96, 80 + (240 - im.height * k) / 2, im.width * k, im.height * k, im))
    else:
        font = fk.get("display") or fk["title"]
        size = fonts.fit(font, name, (64, 56, 48, 40), 860)
        if size is None:
            raise ArtFail("org-banner-name", name)
        face = fonts.face(font)
        sc.add(Text(font, name, size, 96, OH / 2 + face.cap * size / 2, tok["title"]))
    if illustration:
        im = Image.open(illustration)
        im.load()
        k = min(464 / im.width, 320 / im.height)
        sc.add(Picture(1040 + (464 - im.width * k) / 2, 40 + (320 - im.height * k) / 2, im.width * k, im.height * k, im))
    sc.add(_bar(tok, OW, OH))
    return sc


def org_banner_render(brand, fonts: Fonts, owner: str, illustration: str | None = None) -> bytes:
    """JPG q85 within 400 KB (STANDARD §9.2 org banner)."""
    img = to_png_image(org_banner_layout(brand, fonts, owner, illustration), fonts, scale=1).convert("RGB")
    for q in (85, 80, 75):
        b = io.BytesIO()
        img.save(b, "JPEG", quality=q, optimize=True)
        if b.tell() <= ORG_BUDGET:
            return b.getvalue()
    raise ArtFail("org-banner-budget", f"{b.tell()} bytes")
