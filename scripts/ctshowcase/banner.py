"""README hero banner PNG (decision 13, golden layout; spec A6.1). One dark file, no light variant (decision 21)."""
from __future__ import annotations

import re

from PIL import Image

from . import chips as chipmod
from . import iconbox
from .context import RepoContext
from .errors import ArtFail, NeedsInput
from .scene import Grid, Halftone, Linear, Rect, Scene, Text, png_bytes, to_png_image
from .typeset import Fonts, split_last_hyphen

W, H = 1280, 360
CARD = (56, 70, 476, 290)
CARD_R = 24
ICON_INSET = 28
TX, TW = 520, 704
EYEBROW_SIZES = (20, 19, 18)
TITLE_SIZES = (56, 52, 48, 44, 40, 36)
TITLE_2LINE = 40
SUB_SIZES = (26, 24, 22)
SUB2_SIZES = (24, 22, 20)  # last resort, logged needs-input:subtitle; three lines at 20 px only after that
SUB_LH = 1.3
CHIP_H, CHIP_PAD, CHIP_GAP, CHIP_SIZE = 38, 16, 12, 18
MIN_CHIPS = 2  # decision 13: two to four fact chips
# vertical rhythm measured on the golden (box tops): eyebrow 82, title 124, subtitle 199, chips 243-281
GOLD_EYEBROW_TOP, GOLD_TITLE_TOP, GOLD_SUB_TOP, GOLD_CHIP_TOP = 82, 124, 199, 243
STACK_CENTRE = (82 + 281) / 2
# a description head never ends on a dangling word ("... heatmaps built")
HEAD_STOP = {"built", "made", "using", "based", "powered", "and", "or", "of", "to", "the", "a", "an", "with", "for",
             "in", "on", "by", "from", "via"}


def canvas_nodes(style: dict, w: float, h: float, grid_pitch: float | None = None) -> list:
    """The family canvas: gradient-grid (vertical base, the golden's horizontal lift, grid), flat, flat-grid or
    halftone. Shared by the banner, card and org tile."""
    c = style["canvas"]
    kind = c["kind"]
    pitch = grid_pitch or c.get("grid_pitch", 32)
    if kind == "gradient-grid":
        out = [Rect(0, 0, w, h, Linear(((0, c["from"], 1), (1, c["to"], 1)), "v"))]
        ov = c.get("overlay")
        if ov:
            out.append(Rect(0, 0, w, h, Linear(((0, ov["color"], ov.get("from", 0.0)), (1, ov["color"], ov.get("to", 0.55))), "h")))
        out.append(Grid(0, 0, w, h, pitch, c["grid"], c.get("grid_opacity", 0.25)))
        return out
    if kind == "halftone":
        return [Rect(0, 0, w, h, c["color"]),
                Halftone(0, 0, w, h, c.get("pitch", 12), c.get("radius", 2), c["dot"], c.get("dot_opacity", 0.2))]
    if kind == "flat-grid":
        return [Rect(0, 0, w, h, c["color"]), Grid(0, 0, w, h, pitch, c["grid"], c.get("grid_opacity", 0.07))]
    return [Rect(0, 0, w, h, c["color"])]


def eyebrow_text(ctx: RepoContext, category: str | None = None) -> str:
    return chipmod.eyebrow_text(ctx, category)


def description_heads(first: str) -> list[str]:
    """One-line heads of the first sentence, in order: before ':' ';' ' — ', then before ', ', then before
    ' with ' / ' for '. A head needs three words and never ends on a dangling word."""
    out: list[str] = []
    for pattern in (r"\s*(?::|;|\s—)\s", r",\s", r"\s(?:with|for|that|which)\s"):
        for m in reversed(list(re.finditer(pattern, first))):  # the longest head first: the most informative that fits
            head = first[:m.start()].strip()
            words = head.split()
            if len(words) >= 3 and words[-1].lower() not in HEAD_STOP and head not in out and head.count("(") == head.count(")"):
                out.append(head)
    return out


def subtitle_candidates(ctx: RepoContext, cli: str | None) -> list[tuple[str, str]]:
    """One-line candidates in order: cli, override, security short title, description, first sentence, heads."""
    out: list[tuple[str, str]] = []
    if cli:
        out.append((cli, "cli"))
    if ctx.override.get("subtitle"):
        out.append((ctx.override["subtitle"], "override"))
    desc = (ctx.meta.get("description") or "").strip()
    if ctx.det["type"] == "security-check":
        for m in re.finditer(r"\(([^()]+)\)", desc):
            inner = m.group(1).strip()
            if not re.fullmatch(r"(CVE-\d{4}-\d{4,}[,;\s]*(and\s+)?)+", inner, re.I):
                out.append((inner, "description-short-title"))
                break
    # the description, final period removed; CVE-only parentheticals dropped (the CVE ids are chips)
    clean = re.sub(r"\s*\((?:CVE-\d{4}-\d{4,}[,;\s]*(?:and\s+)?)+\)", "", desc).strip()
    if clean:
        out.append((clean.rstrip("."), "description"))
        first = re.split(r"(?<=[.!?])\s+", clean)[0].rstrip(".")
        if first != clean.rstrip("."):
            out.append((first, "description-first-sentence"))
        bare = re.sub(r"\s*\([^()]*\)", "", first).strip()  # the first sentence without its parenthetical asides
        if bare and bare != first:
            out.append((bare, "description-no-asides"))
        out += [(h, "description-head") for h in description_heads(first)]
        if bare and bare != first:
            out += [(h, "description-head") for h in description_heads(bare) if (h, "description-head") not in out]
    return out


def layout(ctx: RepoContext, fonts: Fonts, *, subtitle: str | None = None, keys=None, attrs=None,
           category: str | None = None, icon: str | None = None, allow_few_chips: bool = False) -> tuple[Scene, dict]:
    style = ctx.style
    tok, fk = style["tokens"], style["fonts"]
    info: dict = {"chips": [], "logs": ctx.logs}

    # -- eyebrow ---------------------------------------------------------------------------------------
    eb = eyebrow_text(ctx, category)
    track = chipmod.eyebrow_track(style)
    eb_size = fonts.fit(fk["eyebrow"], eb, EYEBROW_SIZES, TW, track)
    if eb_size is None:
        raise ArtFail("eyebrow", eb)
    # -- title (repo slug) ------------------------------------------------------------------------------
    slug = ctx.repo
    t_size = fonts.fit(fk["title"], slug, TITLE_SIZES, TW)
    t_lines = [slug] if t_size else None
    if not t_lines:
        t_size = TITLE_2LINE
        t_lines = split_last_hyphen(fonts, fk["title"], slug, t_size, TW)
        if not t_lines:
            raise ArtFail("title", slug)
    # -- subtitle: every one-line candidate first (26 -> 22); two lines only as the last resort (needs-input:subtitle)
    sub_lines = sub_size = sub_src = None
    desc = (ctx.meta.get("description") or "").strip().rstrip(".")
    for text, src in subtitle_candidates(ctx, subtitle):
        s_ = fonts.fit(fk["subtitle"], text, SUB_SIZES, TW)
        if s_:
            sub_lines, sub_size, sub_src = [text], s_, src
            break
    if sub_lines is None and desc:
        for maxl, sizes in ((2, SUB2_SIZES), (3, SUB2_SIZES[-1:])):
            for s_ in sizes:
                lines = fonts.wrap(fk["subtitle"], desc, s_, TW, maxl, hyphens=False)
                if lines:
                    sub_lines, sub_size, sub_src = lines, s_, f"description-{maxl}-lines"
                    ctx.log("needs-input:subtitle")
                    break
            if sub_lines:
                break
    if sub_lines is None:
        raise ArtFail("subtitle", ctx.meta.get("description") or "")
    # -- chips ------------------------------------------------------------------------------------------
    k, a = chipmod.derive(ctx, keys, attrs, category)

    def chip_w(label):
        return fonts.width(fk["chip"], label, CHIP_SIZE) + 2 * CHIP_PAD

    while True:
        row = [(t, s, "key") for t, s in k] + [(t, s, "attr") for t, s in a]
        total = sum(chip_w(t) for t, _, _ in row) + CHIP_GAP * max(0, len(row) - 1)
        if total <= TW or not a:
            break
        a = a[:-1]
    if total > TW:
        raise ArtFail("chips", " ".join(t for t, _, _ in row))
    info["incomplete"] = len(row) < MIN_CHIPS
    if info["incomplete"]:
        ctx.log("needs-input:banner-chips")
        if not allow_few_chips:
            raise NeedsInput("banner-chips", f"{len(row)} fact chip(s); decision 13 needs 2-4. Add `chips:` to "
                                             ".github/showcase.yml or pass --key-chip/--chip (or --allow-few-chips)")

    # -- vertical stack (golden rhythm, re-centred on the golden centre) -------------------------------------
    fe, ft, fs = fonts.face(fk["eyebrow"]), fonts.face(fk["title"]), fonts.face(fk["subtitle"])
    g1 = GOLD_TITLE_TOP - (GOLD_EYEBROW_TOP + fe.cap * EYEBROW_SIZES[0])
    g2 = GOLD_SUB_TOP - (GOLD_TITLE_TOP + ft.cap * 56)
    g3 = GOLD_CHIP_TOP - (GOLD_SUB_TOP + fs.cap * 26)
    y = 0.0
    eb_base = y + fe.cap * eb_size
    y = eb_base + g1
    t_bases = []
    for i, _ in enumerate(t_lines):
        t_bases.append(y + ft.cap * t_size + i * t_size * 1.1)
    y = t_bases[-1] + g2
    sub_bases = [y + fs.cap * sub_size + i * sub_size * SUB_LH for i in range(len(sub_lines))]
    chip_top = sub_bases[-1] + g3
    stack_h = chip_top + CHIP_H
    off = STACK_CENTRE - stack_h / 2
    if len(t_lines) == 1 and t_size == TITLE_SIZES[0] and eb_size == EYEBROW_SIZES[0] and len(sub_lines) == 1:
        off = GOLD_EYEBROW_TOP  # exact golden positions

    scene = Scene(W, H, title=f"{slug} by {ctx.company}")
    scene.add(*canvas_nodes(style, W, H))

    # -- left card with the icon (the icon's own ground fills the card when it has one) -------------------------
    x0, y0, x1, y1 = CARD
    icon_nodes, info["icon"], k_fit = iconbox.plate(ctx, fonts, (x0, y0, x1 - x0, y1 - y0), CARD_R, ICON_INSET, icon)
    scene.add(*icon_nodes)
    info["icon_fit"] = k_fit

    # -- text column -------------------------------------------------------------------------------------------
    scene.add(Text(fk["eyebrow"], eb, eb_size, TX, off + eb_base, tok["eyebrow"], track))
    for line, base in zip(t_lines, t_bases):
        scene.add(Text(fk["title"], line, t_size, TX, off + base, tok["title"]))
    for line, base in zip(sub_lines, sub_bases):
        scene.add(Text(fk["subtitle"], line, sub_size, TX, off + base, tok["subtitle"]))
    cx, cy = TX, off + chip_top
    fc = fonts.face(fk["chip"])
    for label, src, kind in row:
        c = tok["chip_key"] if kind == "key" else tok["chip_attr"]
        w = chip_w(label)
        scene.add(Rect(cx, cy, w, CHIP_H, c["bg"], rx=CHIP_H / 2))
        scene.add(Text(fk["chip"], label, CHIP_SIZE, cx + CHIP_PAD, cy + CHIP_H / 2 + fc.cap * CHIP_SIZE / 2, c["fg"]))
        info["chips"].append({"text": label, "kind": kind, "source": src, "box": [round(cx, 1), round(cy, 1), round(w, 1), CHIP_H]})
        cx += w + CHIP_GAP

    # -- bottom accent bar ------------------------------------------------------------------------------------
    bar = tok["bar"]
    bh_ = bar.get("height", 6)
    scene.add(Rect(0, H - bh_, W, bh_, Linear(((0, bar["from"], 1), (1, bar.get("to") or bar["from"], 1)), "h")))
    info.update(eyebrow=eb, eyebrow_size=eb_size, title_lines=t_lines, title_size=t_size, subtitle=" ".join(sub_lines), subtitle_lines=sub_lines,
                subtitle_size=sub_size, subtitle_source=sub_src, stack_offset=round(off, 2))
    return scene, info


def render(ctx: RepoContext, fonts: Fonts, *, scale: int = 2, budget: int = 300_000, **kw) -> tuple[bytes, dict]:
    """Return (png bytes, info) following the save ladder; ArtFail(png-budget) when nothing fits."""
    scene, info = layout(ctx, fonts, **kw)
    # icon resolution check (never upscale beyond 2x its pixels)
    if info["icon_fit"] is not None and info["icon_fit"] * scale > 2.0:
        ctx.log("needs-input:icon-resolution")
    big = to_png_image(scene, fonts, scale=scale)
    ladder = [("lossless", big, False), ("quantized", big, True)]
    if scale != 1:
        small = big.resize((W, H), Image.LANCZOS)
        ladder += [("lossless-1x", small, False), ("quantized-1x", small, True)]
    for name, img, q in ladder:
        data = png_bytes(img, quantize=q)
        if len(data) <= budget:
            info.update(save=name, px=list(img.size), bytes=len(data), scale=img.size[0] // W)
            return data, info
    raise ArtFail("png-budget", f"{len(data)} bytes")

