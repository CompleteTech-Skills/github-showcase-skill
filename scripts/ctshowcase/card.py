"""Repo card SVG, dark only (decision 21; spec A6.2). 400x160, text outlined, icon on the light card surface."""
from __future__ import annotations

import math
import re

from PIL import Image

from . import chips as chipmod
from . import iconbox
from .banner import canvas_nodes
from .context import RepoContext
from .errors import ArtFail
from .scene import Circle, Clip, Linear, Poly, Rect, Scene, Stroke, Text, to_png_image, to_svg
from .typeset import Fonts

W, H = 400, 160
PAD, TILE, TILE_Y, TILE_R = 16, 88, 22, 16
TX = PAD + TILE + 16
TW = W - TX - PAD
NAME_SIZES = (21, 19, 17, 16, 15, 14)
NAME_2LINE = (17, 16, 15, 14)
DESC_STEPS = ((12.5, 3), (12, 3), (11.5, 3), (11, 3), (11.5, 4), (11, 4), (10.5, 4))
EYEBROW_SIZES = (10.5, 10, 9.5)
EYEBROW_BASE = 26          # fixed for every card (review P2.10): overflow shrinks the description, never the eyebrow
CHIP_H, CHIP_SIZE = 20, 10.5
CHIP_Y = H - 36
TEXT_LIMIT = CHIP_Y - 5
BAR_H = 4
CVE_SLUG = re.compile(r"cve-\d{4}-\d+", re.I)


def eyebrow(ctx: RepoContext) -> str:
    """The banner's eyebrow (one shared function), or the company label alone when the category cannot fit."""
    return chipmod.eyebrow_text(ctx)


def star_path(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def split_slug(fonts: Fonts, key: str, slug: str, size: float, maxw: float) -> list[str] | None:
    """Two lines at the hyphen (or dot) giving the most even lines; never inside a CVE id."""
    protected = [range(m.start() + 1, m.end()) for m in CVE_SLUG.finditer(slug)]
    best = None
    for i, c in enumerate(slug):
        if c not in "-." or any(i in r for r in protected):
            continue
        a, b = slug[: i + 1], slug[i + 1:]
        wa, wb = fonts.width(key, a, size), fonts.width(key, b, size)
        if wa <= maxw and wb <= maxw and b:
            score = abs(wa - wb)
            if best is None or score < best[0]:
                best = (score, [a, b])
    return best[1] if best else None


def layout(ctx: RepoContext, fonts: Fonts, icon: str | None = None) -> tuple[Scene, dict]:
    st = ctx.style
    tok, fk = st["tokens"], st["fonts"]
    desc = ctx.require_description()
    name = ctx.repo
    info: dict = {"logs": ctx.logs}
    track = chipmod.eyebrow_track(st)

    eb = eyebrow(ctx)
    eb_size = fonts.fit(fk["eyebrow"], eb, EYEBROW_SIZES, TW, track)
    if eb_size is None:
        eb = st["company_label"].upper() if st.get("eyebrow_case") == "upper" else st["company_label"]
        eb_size = fonts.fit(fk["eyebrow"], eb, EYEBROW_SIZES, TW, track) or EYEBROW_SIZES[-1]

    nsz = fonts.fit(fk["card_name"], name, NAME_SIZES, TW)
    lines = [name] if nsz else None
    if not lines:
        for nsz in NAME_2LINE:
            lines = split_slug(fonts, fk["card_name"], name, nsz, TW)
            if lines:
                break
        if not lines:
            raise ArtFail("card-name", name)
    # description ladder: 12.5 -> 11 on three lines, then four lines at 11.5 / 11; the eyebrow never moves
    dsz = dlines = None
    head = EYEBROW_BASE + 6 + len(lines) * nsz * 1.08 + 3
    for size, maxl in DESC_STEPS:
        cand = fonts.wrap(fk["card_body"], desc, size, TW, maxl, hyphens=False)
        if cand and head + len(cand) * size * 1.33 <= TEXT_LIMIT:
            dsz, dlines = size, cand
            break
    if not dlines:
        raise ArtFail("card-description", desc)

    clip = Clip(W, H, 12, canvas_nodes_card(st))
    bar = tok["bar"]
    clip.children.append(Rect(0, H - BAR_H, W, BAR_H, Linear(((0, bar["from"], 1), (1, bar.get("to") or bar["from"], 1)), "h")))
    scene = Scene(W, H, title=f"{name}: {desc}")
    scene.add(clip)
    edge = tok["edge"]
    scene.add(Rect(0.5, 0.5, W - 1, H - 1, None, rx=11.5, stroke=edge["color"], stroke_opacity=edge["opacity"]))

    # text column
    y = EYEBROW_BASE
    scene.add(Text(fk["eyebrow"], eb, eb_size, TX, y, tok["eyebrow"], track))
    y += 6
    for ln in lines:
        y += nsz * 1.08
        scene.add(Text(fk["card_name"], ln, nsz, TX, y, tok["title"]))
    y += 3
    for ln in dlines:
        y += dsz * 1.33
        scene.add(Text(fk["card_body"], ln, dsz, TX, y, tok["body"]))

    # chip row, in the banner's order: key chips (both CVE ids when they fit), then the attributes, where a bare
    # language is drawn as the language dot in its place; stars last. Overflow drops stars, then attributes from the
    # end, then folds the second key into "+1".
    keys, attrs = chipmod.derive(ctx)
    lang = ctx.meta.get("language")
    stars = ctx.meta.get("stargazers_count") or 0
    stars = stars if stars >= 10 else 0
    fck, fca = fk["card_chip_key"], fk["card_chip_attr"]
    pad_x = 9

    def place(keys, attrs, stars):
        items, x = [], TX
        for label, _ in keys:
            w = fonts.width(fck, label, CHIP_SIZE) + 2 * pad_x
            items.append(("key", x, w, label))
            x += w + 6
        for label, src in attrs:
            if src == "meta" and label == lang:
                w = 13 + fonts.width(fca, label, CHIP_SIZE)
                items.append(("lang", x + 2, w, label))
                x += w + 10
                continue
            w = fonts.width(fca, label, CHIP_SIZE) + 2 * pad_x
            items.append(("attr", x, w, label))
            x += w + 6
        if stars:
            label = f"{stars:,}"
            w = 13 + fonts.width(fca, label, CHIP_SIZE)
            items.append(("stars", x, w, label))
            x += w + 6
        return items, x - 6

    items, end = place(keys, attrs, stars)
    while end > W - PAD:
        if stars:
            stars = 0
        elif attrs:
            attrs = attrs[:-1]
        elif len(keys) > 1:
            keys = [(f"{keys[0][0]} +{len(keys) - 1}", keys[0][1])]
        else:
            raise ArtFail("card-chips", " ".join(k for k, _ in keys))
        items, end = place(keys, attrs, stars)
    fc = fonts.face(fck)
    base = CHIP_Y + CHIP_H / 2 + fc.cap * CHIP_SIZE / 2
    mid = CHIP_Y + CHIP_H / 2
    langs = ctx.brand.raw.get("languages", {})
    for kind, x, w, label in items:
        if kind in ("key", "attr"):
            c = tok["chip_key"] if kind == "key" else tok["chip_attr"]
            scene.add(Rect(x, CHIP_Y, w, CHIP_H, c["bg"], rx=CHIP_H / 2))
            scene.add(Text(fck if kind == "key" else fca, label, CHIP_SIZE, x + pad_x, base, c["fg"]))
        elif kind == "lang":
            scene.add(Circle(x + 5, mid, 4.5, langs.get(label, langs.get("default"))))
            scene.add(Text(fca, label, CHIP_SIZE, x + 14, base, tok["body"]))
        else:
            scene.add(Poly(star_path(x + 5, mid, 5.5), tok["gold_trace"]))
            scene.add(Text(fca, label, CHIP_SIZE, x + 13, base, tok["body"]))
    info["items"] = [{"kind": k, "x": round(x, 1), "w": round(w, 1), "label": lb} for k, x, w, lb in items]

    # gold trace from the tile to a pad beside the first chip, then the icon tile on top
    tx0 = PAD + TILE / 2
    pad_fill = tok["plate_low"]
    scene.add(Stroke(f"M{tx0} {TILE_Y + TILE}V{mid - 7}L{tx0 + 7} {mid}H{TX - 9}", tok["gold_trace"], 1.5))
    scene.add(Circle(TX - 6, mid, 3, pad_fill, tok["gold_trace"], 1.5))
    scene.add(Circle(tx0, TILE_Y + TILE, 2.5, tok["gold_trace"]))
    icon_nodes, icon_info, _ = iconbox.plate(ctx, fonts, (PAD, TILE_Y, TILE, TILE), TILE_R, 10, icon, shadow_scale=0.5)
    scene.add(*icon_nodes)
    info.update(icon=icon_info, name_lines=lines, name_size=nsz, desc_lines=dlines, desc_size=dsz, eyebrow=eb)
    return scene, info


def canvas_nodes_card(style: dict) -> list:
    """The banner canvas at card size (grid pitch 20)."""
    return canvas_nodes(style, W, H, grid_pitch=20)


def render(ctx: RepoContext, fonts: Fonts, icon: str | None = None) -> tuple[str, Scene, dict]:
    scene, info = layout(ctx, fonts, icon)
    svg = to_svg(scene, fonts, prefix="c")
    return svg, scene, info


def preview_png(scene: Scene, fonts: Fonts, scale: int = 2) -> Image.Image:
    return to_png_image(scene, fonts, scale=scale, alpha_rx=12)
