"""Account chart renderers (`account-chart render`): the dark compositor tree as GitHub-safe SVG and an HD PNG, and the
same tree as Mermaid source.

The tree reads top to bottom. The account heads it; a trunk drops from its avatar, and each child (the personal
repositories, every enterprise, every organization outside one) branches off on a rounded elbow. An enterprise is a
gold-edged frame with its own trunk to its organizations. Every organization is a lane: its card (family palette,
mark or monogram, role chip) and its public repositories as pills that flow to the right edge and wrap.

Deterministic (S07): the same snapshot renders byte-identical SVG, PNG and Mermaid files. Text is outlined (S05a),
icons are paths (S08), and nothing in the image is a count (S16): the counts go to the Markdown companion. Every
colour comes from references/brand.yaml (`chart:` and the family tokens).
"""
from __future__ import annotations

import json
import math
import re

from PIL import Image, ImageDraw

from .banner import canvas_nodes
from .chips import eyebrow_track
from .color import best_fg, contrast, hexstr, mix, rgb
from .errors import ArtFail
from .iconbox import corner_ground
from .scene import SS, Circle, Clip, Grid, Linear, Picture, PngRenderer, Rect, Scene, Shadow, Stroke, Text, to_svg
from .tile import rounded
from .typeset import Fonts, ntos

W_DEFAULT, W_MIN, W_MAX = 2400, 1600, 4800
M = 64                         # outer margin
AV = 112                       # account avatar
HEAD_GAP = 52                  # header to the first lane
BRANCH = 44                    # trunk to a child card
ELBOW = 14                     # elbow radius
CARD_W, CARD_H, CARD_H2, CARD_R = 392, 84, 102, 14
CAV = 52                       # card avatar
LANE_GAP = 16
PILL_H, PILL_GAP, PILL_ROWGAP, PILL_SIZE = 30, 8, 8, 12.5
PILLS_DX = 28                  # card to the first pill
ENT_PAD = 20
ENT_GAP = 18                   # enterprise card to its first lane
FOOT_H = 52
PILL_FONT = "mono-medium"
MAX_PNG_PIXELS = 120_000_000
BIG = 4_000_000                # device pixels above which a rounded rect is painted without a full supersampled mask


class Chart:
    """A laid-out chart: background and foreground nodes for one canvas, plus the facts the CLI reports."""

    def __init__(self, w: int, h: int, bg: list, fg: list, title: str, desc: str, style: dict):
        self.w, self.h, self.bg, self.fg, self.title, self.desc, self.style = w, h, bg, fg, title, desc, style

    def scene(self) -> Scene:
        return Scene(self.w, self.h, self.bg + self.fg, title=self.title, desc=self.desc)


# =====================================================================================================
# geometry helpers
# =====================================================================================================
def _d(points) -> str:
    """Absolute M/L path data (the Stroke backend's grammar), fixed precision."""
    head, *rest = points
    return f"M{ntos(head[0])} {ntos(head[1])}" + "".join(f"L{ntos(x)} {ntos(y)}" for x, y in rest)


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, n: int = 8) -> list:
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def _elbow(tx: float, cy: float, x_end: float) -> list:
    """From the trunk at (tx, cy - ELBOW), a quarter turn into the horizontal branch to x_end."""
    return _arc(tx + ELBOW, cy - ELBOW, ELBOW, math.pi, math.pi / 2) + [(x_end, cy)]


def _initials(name: str) -> str:
    words = [w for w in re.split(r"[\s._-]+", name or "") if w and w[0].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def _canvas(style: dict) -> dict:
    """The account family's canvas for the chart: a halftone is painted flat (its dots would dominate a long canvas)."""
    c = dict(style["canvas"])
    if c["kind"] not in ("gradient-grid", "flat", "flat-grid"):
        c = {"kind": "flat", "color": c.get("color") or style["tokens"]["ink"]}
    return c


def canvas_colour(style: dict) -> str:
    c = _canvas(style)
    return c.get("from") or c["color"]


def _solid(colour: str, opacity: float, ground: str) -> str:
    """The opaque colour of `colour` at `opacity` over `ground` (overlapping connectors must not darken)."""
    return hexstr(mix(ground, colour, opacity))


# =====================================================================================================
# drawing primitives
# =====================================================================================================
class _Draw:
    def __init__(self, brand, fonts: Fonts, model: dict):
        self.brand, self.fonts, self.model = brand, fonts, model
        self.cfg = brand.raw["chart"]
        self.labels = self.cfg["labels"]
        self.langs = brand.raw.get("languages") or {}
        self.fg: list = []
        acct = model["account"]["style"]
        self.ground = canvas_colour(acct)
        con = self.cfg["connector"]
        self.wire = _solid(con["color"], con["opacity"], self.ground)
        self.wire_w = con["width"]
        pill = self.cfg["pill"]
        self.pill_ground = _solid(pill["color"], pill["opacity"], self.ground)

    def dot(self, cx: float, cy: float, language: str | None, op: float = 1.0) -> None:
        """A language dot; a linguist colour too dark to read on the pill (Lua, PowerShell) gets a muted ring."""
        colour = self.langs.get(language or "", self.langs.get("default"))
        if contrast(colour, self.pill_ground) < 2.0:
            self.fg.append(Circle(cx, cy, 4.5, fill=colour, stroke=self.cfg["muted"], stroke_width=1.2, opacity=op))
        else:
            self.fg.append(Circle(cx, cy, 4.5, fill=colour, opacity=op))

    # -- text -------------------------------------------------------------------------------------
    def fit(self, key: str, text: str, sizes, maxw: float, element: str, track: float = 0.0) -> float:
        s = self.fonts.fit(key, text, sizes, maxw, track)
        if s is None:
            raise ArtFail(element, text)
        return s

    def text(self, key, text, size, x, baseline, fill, track=0.0, opacity=1.0):
        self.fg.append(Text(key, text, size, x, baseline, fill, track, opacity))
        return self.fonts.width(key, text, size, track)

    # -- icons (paths, S08) -----------------------------------------------------------------------
    def fork_icon(self, x: float, cy: float, colour: str, op: float) -> float:
        for px, py in ((x + 2, cy - 4.2), (x + 10, cy - 4.2), (x + 6, cy + 4.6)):
            self.fg.append(Circle(px, py, 1.9, fill=colour, opacity=op))
        self.fg.append(Stroke(_d([(x + 2, cy - 4.2), (x + 2, cy - 1.6), (x + 6, cy + 1.4), (x + 6, cy + 4.6)]), colour, 1.4, op))
        self.fg.append(Stroke(_d([(x + 10, cy - 4.2), (x + 10, cy - 1.6), (x + 6, cy + 1.4)]), colour, 1.4, op))
        return 12

    def archive_icon(self, x: float, cy: float, colour: str, op: float) -> float:
        self.fg.append(Rect(x, cy - 5.2, 12, 3.2, colour, rx=0.8, opacity=op))
        self.fg.append(Rect(x + 1.2, cy - 1.4, 9.6, 6.6, None, rx=1.2, stroke=colour, stroke_width=1.3, stroke_opacity=op))
        self.fg.append(Stroke(_d([(x + 4.4, cy + 1.2), (x + 7.6, cy + 1.2)]), colour, 1.3, op))
        return 12

    def lock_icon(self, x: float, cy: float, colour: str, op: float) -> float:
        self.fg.append(Stroke(_d([(x + 3.2, cy - 0.6)] + _arc(x + 6, cy - 3.2, 2.8, math.pi, 2 * math.pi, 8)
                                 + [(x + 8.8, cy - 0.6)]), colour, 1.4, op))
        self.fg.append(Rect(x + 1.4, cy - 1.2, 9.2, 6.8, colour, rx=1.6, opacity=op))
        return 12

    def building_icon(self, x: float, y: float, size: float, colour: str) -> None:
        u = size / 24
        self.fg.append(Rect(x + 5 * u, y + 4 * u, 14 * u, 17 * u, None, rx=1.5 * u, stroke=colour, stroke_width=1.6 * u))
        for row in range(3):
            for col in range(2):
                self.fg.append(Rect(x + (8.2 + col * 5) * u, y + (7.5 + row * 4) * u, 2.6 * u, 2.2 * u, colour, rx=0.4 * u))
        self.fg.append(Rect(x + 10.6 * u, y + 18 * u, 2.8 * u, 3 * u, colour, rx=0.4 * u))

    # -- avatars, chips, cards --------------------------------------------------------------------
    def avatar(self, x: float, y: float, size: float, style: dict, mark, initials: str, rx: float) -> None:
        tok, fk = style["tokens"], style["fonts"]
        im = None
        if mark:
            try:
                im = Image.open(mark)
                im.load()
            except OSError:
                im = None
        if im is not None:
            ground = corner_ground(im)
            if ground:  # the mark brings its own tile: full bleed, never a plate inside a plate
                self.fg.append(Rect(x, y, size, size, ground, rx=rx))
                self.fg.append(Clip(size, size, rx, [Picture(x, y, size, size, im, "webp", 86, 2)], x, y))
            else:
                inset = round(size * 0.12)
                inner = size - 2 * inset
                self.fg.append(Rect(x, y, size, size, tok["plate_low"], rx=rx))
                self.fg.append(Picture(x + inset, y + inset, inner, inner,
                                       rounded(im, round(inner * 2), round(max(2.0, rx - inset) * 2)), "webp", 86, 1))
        else:
            self.fg.append(Rect(x, y, size, size, Linear(((0, tok["accent_mid"], 1), (1, tok["accent_deep"], 1)), "v"), rx=rx))
            ink = best_fg(tok["accent_deep"], [tok["title"], tok.get("ink") or tok["plate_low"]])
            tsz = size * 0.4
            tw = self.fonts.width(fk["display"], initials, tsz)
            cap = self.fonts.face(fk["display"]).cap * tsz
            self.text(fk["display"], initials, tsz, x + (size - tw) / 2, y + (size + cap) / 2, ink)
        self.fg.append(Rect(x + 1, y + 1, size - 2, size - 2, None, rx=max(0.0, rx - 1), stroke=tok["accent"], stroke_width=2,
                            stroke_opacity=0.6))

    def chip_width(self, style: dict, text: str, size: float = 10.5, pad: float = 9) -> float:
        return self.fonts.width(style["fonts"]["chip"], text, size) + 2 * pad

    def chip(self, x: float, y: float, style: dict, text: str, kind: str, size: float = 10.5, h: float = 20,
             pad: float = 9) -> float:
        c = style["tokens"]["chip_key" if kind == "key" else "chip_attr"]
        w = self.chip_width(style, text, size, pad)
        self.fg.append(Rect(x, y, w, h, c["bg"], rx=h / 2))
        cap = self.fonts.face(style["fonts"]["chip"]).cap * size
        self.text(style["fonts"]["chip"], text, size, x + pad, y + (h + cap) / 2, c["fg"])
        return w

    def eyebrow_colour(self, style: dict, ground: str) -> str:
        """The family eyebrow when it keeps 4.5:1 on the card (S33), else the title colour."""
        tok = style["tokens"]
        return tok["eyebrow"] if contrast(tok["eyebrow"], ground) >= 4.5 else tok["title"]

    def card_metrics(self, node: dict) -> dict:
        """Sizes and lines for a card before it is placed: the lane needs its height first."""
        st = node["style"]
        fk = st["fonts"]
        tw = CARD_W - 16 - CAV - 14 - 16
        role = self.role_text(node)
        chip_w = self.chip_width(st, role) + 8 if role else 0
        track = eyebrow_track(st)
        eb = node["eyebrow"]
        eb_size = self.fonts.fit(fk["eyebrow"], eb, (10.5, 10, 9.5), tw - chip_w, track)
        if eb_size is None and node.get("eyebrow_short"):
            eb = node["eyebrow_short"]
            eb_size = self.fonts.fit(fk["eyebrow"], eb, (10.5, 10, 9.5), tw - chip_w, track)
        if eb_size is None:
            raise ArtFail("chart-eyebrow", eb)
        nsz = self.fonts.fit(fk["display"], node["name"], (17, 16, 15, 14), tw)
        lines = [node["name"]]
        if nsz is None:
            nsz, lines = self.fonts.wrap_ladder(fk["display"], node["name"], (14, 13), tw, (2,), "chart-org-name", hyphens=False)
        sub_size = self.fit(PILL_FONT, node["sub"], (11, 10.5, 10, 9.5), tw, "chart-login")
        return {"eyebrow": eb, "eb_size": eb_size, "track": track, "name_size": nsz, "lines": lines, "sub_size": sub_size,
                "role": role, "h": CARD_H if len(lines) == 1 else CARD_H2}

    def role_text(self, node: dict) -> str | None:
        return {"owner": self.labels["owner"], "member": self.labels["member"]}.get(node.get("role") or "")

    def card(self, x: float, y: float, node: dict, met: dict, avatar=None) -> None:
        st = node["style"]
        tok, fk = st["tokens"], st["fonts"]
        h = met["h"]
        sh = tok["card_shadow"]
        surface = self.cfg["surface"]
        plate = tok["plate_low"]
        self.fg.append(Shadow(x + sh["dx"] / 2, y + sh["dy"] / 2, CARD_W, h, CARD_R, sh["color"], sh["opacity"],
                              sh.get("blur", 0) / 2))
        self.fg.append(Rect(x, y, CARD_W, h, plate, rx=CARD_R, opacity=surface["opacity"], stroke=tok["edge"]["color"],
                            stroke_opacity=tok["edge"]["opacity"]))
        bar = tok["bar"]
        self.fg.append(Clip(CARD_W, h, CARD_R, [Rect(x, y, 4, h, Linear(((0, bar["from"], 1), (1, bar.get("to") or bar["from"], 1)),
                                                                         "v"))], x, y))
        ay = y + (h - CAV) / 2
        if avatar is not None:
            avatar(x + 16, ay)
        else:
            self.avatar(x + 16, ay, CAV, st, node.get("mark"), node["initials"], 12)
        tx = x + 16 + CAV + 14
        ground = _solid(plate, surface["opacity"], self.ground)
        top = y + (h - (met["eb_size"] + 8 + met["name_size"] * 1.15 * len(met["lines"]) + 6 + met["sub_size"])) / 2
        base = top + met["eb_size"] * 0.9
        self.text(fk["eyebrow"], met["eyebrow"], met["eb_size"], tx, base, self.eyebrow_colour(st, ground), met["track"])
        if met["role"]:
            cw = self.chip_width(st, met["role"])
            self.chip(x + CARD_W - 14 - cw, base - 14, st, met["role"], "key" if node.get("role") == "owner" else "attr")
        base += 8
        for ln in met["lines"]:
            base += met["name_size"] * 1.15
            self.text(fk["display"], ln, met["name_size"], tx, base, tok["title"])
        base += 6 + met["sub_size"]
        self.text(PILL_FONT, node["sub"], met["sub_size"], tx, base, self.cfg["muted"])

    # -- pills ------------------------------------------------------------------------------------
    def pill_width(self, item: dict) -> float:
        if item["kind"] == "note":
            w = self.fonts.width(self.model["account"]["style"]["fonts"]["card_body"], item["text"], 12)
            return 14 + (12 + 7 if item["icon"] else 0) + w + 14
        w = 14 + 9 + 9 + self.fonts.width(PILL_FONT, item["name"], PILL_SIZE) + 14
        return w + 20 * (item["fork"] + item["archived"])

    def pill(self, x: float, y: float, item: dict, style: dict) -> None:
        tok = style["tokens"]
        cy = y + PILL_H / 2
        w = item["w"]
        muted = self.cfg["muted"]
        if item["kind"] == "note":
            self.fg.append(Rect(x, y, w, PILL_H, None, rx=PILL_H / 2, stroke=muted, stroke_width=1, stroke_opacity=0.45))
            tx = x + 14
            if item["icon"]:
                tx += self.lock_icon(tx, cy, muted, 0.9) + 7
            key = self.model["account"]["style"]["fonts"]["card_body"]
            cap = self.fonts.face(key).cap * 12
            self.text(key, item["text"], 12, tx, cy + cap / 2, muted)
            return
        op = self.cfg["archived_opacity"] if item["archived"] else 1.0
        pill = self.cfg["pill"]
        self.fg.append(Rect(x, y, w, PILL_H, pill["color"], rx=PILL_H / 2, opacity=pill["opacity"], stroke=tok["edge"]["color"],
                            stroke_opacity=min(1.0, tok["edge"]["opacity"] * 1.25) * op))
        self.dot(x + 16, cy, item["language"], op)
        cap = self.fonts.face(PILL_FONT).cap * PILL_SIZE
        tx = x + 30
        tx += self.text(PILL_FONT, item["name"], PILL_SIZE, tx, cy + cap / 2, tok["title"], opacity=op) + 8
        if item["fork"]:
            tx += self.fork_icon(tx, cy, muted, op) + 8
        if item["archived"]:
            self.archive_icon(tx, cy, muted, 1.0)

    def flow(self, items: list[dict], avail: float) -> list[list[dict]]:
        rows: list[list[dict]] = []
        cur, used = [], 0.0
        for it in items:
            it["w"] = self.pill_width(it)
            need = it["w"] + (PILL_GAP if cur else 0)
            if cur and used + need > avail:
                rows.append(cur)
                cur, used = [], 0.0
                need = it["w"]
            if it["w"] > avail:
                raise ArtFail("chart-pill", it.get("name") or it.get("text") or "")
            cur.append(it)
            used += need
        if cur:
            rows.append(cur)
        return rows


# =====================================================================================================
# layout
# =====================================================================================================
def _items(node: dict, labels: dict) -> list[dict]:
    items = [{"kind": "repo", **r} for r in node["repos"]]
    for note in node["notes"]:
        items.append({"kind": "note", "note": note, "text": labels.get(note, labels["uncaptured"]),
                      "icon": note == "private"})
    return items


def markers(model: dict) -> set[str]:
    """The pill markers the chart draws: `fork`, `archived` and `private` (a 'private work' note)."""
    lanes = [model["personal"], *model["orgs"], *[o for e in model["enterprises"] for o in e["orgs"]]]
    out = {k for n in lanes if n for rp in n["repos"] for k in ("fork", "archived") if rp[k]}
    return out | ({"private"} if any("private" in n["notes"] for n in lanes if n) else set())


def layout(model: dict, brand, fonts: Fonts, *, width: int = W_DEFAULT, avatar: str | None = None) -> Chart:
    if not W_MIN <= width <= W_MAX:
        raise ArtFail("chart-width", str(width))
    dr = _Draw(brand, fonts, model)
    cfg, labels = dr.cfg, dr.labels
    acct = model["account"]
    st = acct["style"]
    tok, fk = st["tokens"], st["fonts"]
    W = width
    right = W - M

    # -- header: the account ----------------------------------------------------------------------
    mark = avatar or acct.get("mark")
    dr.avatar(M, M, AV, st, mark, acct["initials"], AV / 2)
    tx = M + AV + 32
    maxw = right - tx
    track = eyebrow_track(st)
    eb_size = dr.fit(fk["eyebrow"], acct["eyebrow"], (15, 14, 13, 12), maxw, "chart-eyebrow", track)
    dr.text(fk["eyebrow"], acct["eyebrow"], eb_size, tx, M + 26, tok["eyebrow"], track)
    nsz = dr.fit(fk["display"], acct["name"], (54, 50, 46, 42, 38, 34), maxw, "chart-name")
    name_base = M + 26 + 14 + nsz * 0.76
    dr.text(fk["display"], acct["name"], nsz, tx, name_base, tok["title"])
    handle_base = name_base + 36
    hw = dr.text(PILL_FONT, acct["handle"], 17, tx, handle_base, tok["subtitle"])
    cx = tx + hw + 22
    for text, kind in acct["chips"]:
        w = dr.chip_width(st, text, 12.5, 12)
        if cx + w > right:
            break  # an optional chip that does not fit is left out (the Markdown companion lists the facts)
        cx += dr.chip(cx, handle_base - 19, st, text, kind, 12.5, 26, 12) + 10
    y = max(M + AV, handle_base + 10) + HEAD_GAP
    if model.get("evidence"):
        item = _items({"repos": [], "notes": ["partial"]}, labels)[0]
        item["w"] = dr.pill_width(item)
        dr.pill(tx, y, item, st)
        y += PILL_H + PILL_ROWGAP

    # -- the tree -----------------------------------------------------------------------------------
    trunk_x = M + AV / 2
    trunk_top = M + AV + 6
    branch_ys: list[float] = []
    x1 = trunk_x + BRANCH

    def lane(node: dict, x: float, y: float) -> tuple[float, float]:
        met = dr.card_metrics(node)
        avail = right - (x + CARD_W + PILLS_DX) - (ENT_PAD if node.get("_in_enterprise") else 0)
        rows = dr.flow(_items(node, labels), avail)
        rows_h = len(rows) * PILL_H + (len(rows) - 1) * PILL_ROWGAP if rows else 0
        h = max(met["h"], rows_h)
        dr.card(x, y, node, met, None if node["kind"] != "personal" else
                (lambda ax, ay: dr.avatar(ax, ay, CAV, st, mark, acct["initials"], CAV / 2)))
        py = y + (met["h"] - rows_h) / 2 if rows_h <= met["h"] else y
        for row in rows:
            px = x + CARD_W + PILLS_DX
            for it in row:
                dr.pill(px, py, it, node["style"])
                px += it["w"] + PILL_GAP
            py += PILL_H + PILL_ROWGAP
        return h, y + met["h"] / 2

    if model.get("personal"):
        h, cy = lane(model["personal"], x1, y)
        branch_ys.append((cy, True))
        y += h + LANE_GAP

    ent_cfg = cfg["enterprise"]
    for ent in model["enterprises"]:
        y += 6
        frame_at = len(dr.fg)
        inner = x1 + ENT_PAD
        est = ent["style"]
        met = dr.card_metrics(ent)

        def ent_avatar(ax, ay, est=est):
            dr.fg.append(Rect(ax, ay, CAV, CAV, est["tokens"]["plate_low"], rx=12))
            dr.building_icon(ax + 10, ay + 10, CAV - 20, ent_cfg["accent"])
            dr.fg.append(Rect(ax + 1, ay + 1, CAV - 2, CAV - 2, None, rx=11, stroke=ent_cfg["accent"], stroke_width=2,
                              stroke_opacity=0.6))
        top = y
        dr.card(inner, y + ENT_PAD, ent, met, ent_avatar)
        if ent.get("capture_status", "complete") != "complete":
            item = _items({"repos": [], "notes": [ent["capture_status"]]}, labels)[0]
            item["w"] = dr.pill_width(item)
            dr.pill(inner + CARD_W + PILLS_DX, y + ENT_PAD + (met["h"] - PILL_H) / 2, item, est)
        ent_cy = y + ENT_PAD + met["h"] / 2
        branch_ys.append((ent_cy, False))  # the junction sits on the enterprise card, past the frame edge
        sub_x = inner + 16 + CAV / 2
        sub_top = y + ENT_PAD + met["h"]
        ly = y + ENT_PAD + met["h"] + ENT_GAP
        sub_ys = []
        wires_at = len(dr.fg)
        for org in ent["orgs"]:
            org["_in_enterprise"] = True
            h, cy = lane(org, sub_x + BRANCH, ly)
            sub_ys.append(cy)
            ly += h + LANE_GAP
        bottom = (ly - LANE_GAP if ent["orgs"] else sub_top) + ENT_PAD
        ewire = _solid(ent_cfg["accent"], cfg["connector"]["opacity"], _solid(ent_cfg["fill"], ent_cfg["fill_opacity"], dr.ground))
        wires = []
        if sub_ys:
            wires.append(Stroke(_d([(sub_x, sub_top), (sub_x, sub_ys[-1] - ELBOW)]), ewire, dr.wire_w))
            for cy in sub_ys:
                wires.append(Stroke(_d(_elbow(sub_x, cy, sub_x + BRANCH)), ewire, dr.wire_w))
                wires.append(Circle(sub_x + BRANCH, cy, 3.5, fill=cfg["junction"]))
        dr.fg[wires_at:wires_at] = wires
        frame = Rect(x1, top, right - x1, bottom - top, ent_cfg["fill"], rx=20, opacity=ent_cfg["fill_opacity"],
                     stroke=ent_cfg["accent"], stroke_width=1.5, stroke_opacity=ent_cfg["edge_opacity"])
        # the account's branch continues over the frame to the enterprise card, where its junction sits
        dr.fg[frame_at:frame_at] = [frame, Stroke(_d([(x1, ent_cy), (inner, ent_cy)]), dr.wire, dr.wire_w),
                                    Circle(inner, ent_cy, 3.5, fill=cfg["junction"])]
        y = bottom + LANE_GAP + 6

    for org in model["orgs"]:
        h, cy = lane(org, x1, y)
        branch_ys.append((cy, True))
        y += h + LANE_GAP

    wires = []
    if branch_ys:
        wires.append(Stroke(_d([(trunk_x, trunk_top), (trunk_x, branch_ys[-1][0] - ELBOW)]), dr.wire, dr.wire_w))
        for cy, dot in branch_ys:
            wires.append(Stroke(_d(_elbow(trunk_x, cy, x1)), dr.wire, dr.wire_w))
            if dot:
                wires.append(Circle(x1, cy, 3.5, fill=cfg["junction"]))
    dr.fg[0:0] = wires  # under every card and frame

    # -- legend and brand line ------------------------------------------------------------------------
    y += 20
    base = y + 16
    lx = M
    key = fk["card_body"]
    muted = cfg["muted"]
    for lang in model["legend_languages"]:
        dr.dot(lx + 5, base - 4, lang)
        lx += 14
    lx += 4
    lx += dr.text(key, labels["language"], 12, lx, base, muted) + 26
    marks = markers(model)  # explain only the markers this chart draws
    if "fork" in marks:
        lx += dr.fork_icon(lx, base - 4, muted, 1.0) + 8
        lx += dr.text(key, labels["fork"], 12, lx, base, muted) + 26
    if "archived" in marks:
        lx += dr.archive_icon(lx, base - 4, muted, 1.0) + 8
        lx += dr.text(key, labels["archived"], 12, lx, base, muted) + 26
    if "private" in marks:
        lx += dr.lock_icon(lx, base - 4, muted, 1.0) + 8
        lx += dr.text(key, labels["legend_private"], 12, lx, base, muted) + 26
    if model["roles"]:
        for role in ("owner", "member"):
            if role in model["roles"]:
                lx += dr.chip(lx, base - 14.5, st, labels[role], "key" if role == "owner" else "attr") + 8
    s = brand.strings
    line = f"{s['company']} · {s['tagline']}"
    lw = fonts.width(key, line, 12)
    if lx + 40 + lw <= right:
        dr.text(key, line, 12, right - lw, base, muted)
    H = max(480, math.ceil(base + FOOT_H))
    bg = canvas_nodes(dict(st, canvas=_canvas(st)), W, H)
    return Chart(W, H, bg, dr.fg, model["title"], model["desc"], st)


# =====================================================================================================
# SVG and PNG
# =====================================================================================================
def svg(chart: Chart, fonts: Fonts) -> str:
    return to_svg(chart.scene(), fonts, prefix="a")


def _round_mask(w: int, h: int, r: float, width: int | None = None) -> Image.Image:
    """L mask (device px) of a rounded rect, filled or as a ring of `width`, supersampled only in its four corners."""
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    if width is None:
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    else:
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, outline=255, width=width)
    t = min(int(math.ceil(r)) + 2, w // 2, h // 2)
    for cx, cy in ((0, 0), (w - t, 0), (0, h - t), (w - t, h - t)):
        tile = Image.new("L", (t * SS, t * SS), 0)
        td = ImageDraw.Draw(tile)
        box = [-cx * SS, -cy * SS, (w - cx) * SS - 1, (h - cy) * SS - 1]
        if width is None:
            td.rounded_rectangle(box, radius=r * SS, fill=255)
        else:
            td.rounded_rectangle(box, radius=r * SS, outline=255, width=width * SS)
        m.paste(tile.reduce(SS), (cx, cy))
    return m


class _ChartPng(PngRenderer):
    """The shared rasterizer, plus large rounded rects (the enterprise frame) without a full supersampled mask."""

    def draw(self, canvas, n, clip=None):
        s = self.s
        if isinstance(n, Rect) and clip is None and n.w * n.h * s * s > BIG and not isinstance(n.fill, Linear):
            bx, by, bw, bh = round(n.x * s), round(n.y * s), round(n.w * s), round(n.h * s)
            if n.fill is not None:
                m = _round_mask(bw, bh, n.rx * s)
                if n.opacity != 1:
                    m = m.point(lambda v, o=n.opacity: round(v * o))
                canvas.paste(Image.new("RGB", (bw, bh), rgb(n.fill)), (bx, by), m)
            if n.stroke:
                m = _round_mask(bw, bh, n.rx * s, max(1, round(n.stroke_width * s)))
                if n.stroke_opacity != 1:
                    m = m.point(lambda v, o=n.stroke_opacity: round(v * o))
                canvas.paste(Image.new("RGB", (bw, bh), rgb(n.stroke)), (bx, by), m)
            return
        return super().draw(canvas, n, clip)


def png_scale(chart: Chart, scale: int) -> int:
    """The requested scale, lowered until the PNG stays within MAX_PNG_PIXELS."""
    while scale > 1 and chart.w * chart.h * scale * scale > MAX_PNG_PIXELS:
        scale -= 1
    return scale


def png_image(chart: Chart, fonts: Fonts, scale: int) -> Image.Image:
    size = (chart.w * scale, chart.h * scale)
    img = Image.new("RGB", size)
    r = _ChartPng(fonts, scale)
    for n in chart.bg:  # the canvas: full-bleed gradients painted from 1-pixel strips, the grid without supersampling
        if isinstance(n, Rect) and not n.rx and n.x == 0 and n.y == 0:
            if isinstance(n.fill, Linear):
                layer = r._paint_image(n.fill, size)
                if any(a != 1 for _, _, a in n.fill.stops):
                    img.paste(layer, (0, 0), r._alpha_image(n.fill, size))
                else:
                    img.paste(layer, (0, 0))
            else:
                img.paste(Image.new("RGB", size, rgb(n.fill)), (0, 0))
        elif isinstance(n, Grid):
            r.draw(img, n)
        else:
            r.draw(img, n)
    for n in chart.fg:
        r.draw(img, n)
    return img


# =====================================================================================================
# Mermaid
# =====================================================================================================
def _mq(text: str) -> str:
    """A quoted Mermaid label: entity codes for the characters the grammar or HTML would read."""
    out = str(text).replace("#", "#35;").replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")
    return " ".join(out.split())


def _cls(prefix: str, name: str | None) -> str:
    slug = (name or "").lower().replace("++", "pp").replace("+", "p").replace("#", "sharp")
    return prefix + (re.sub(r"[^a-z0-9]+", "_", slug).strip("_") or "x")


def mermaid(model: dict, brand) -> tuple[str, dict]:
    """The same tree as a `flowchart LR`: account, enterprises, organizations, and each lane's repositories as a
    cluster of pills in rows (invisible `~~~` links keep the rows). Colours are the brand tokens, opaque (Mermaid styles
    take no alpha) and blended on the chart canvas."""
    cfg = brand.raw["chart"]
    labels, mm = cfg["labels"], cfg["mermaid"]
    cols = int(mm["columns"])
    acct = model["account"]
    st = acct["style"]
    tok = st["tokens"]
    ground = canvas_colour(st)
    con = cfg["connector"]
    wire = _solid(con["color"], con["opacity"], ground)
    cluster_bg = _solid(cfg["surface"]["color"], 0.45, ground)
    # fontFamily is a top-level key (Mermaid ignores it under themeVariables); wrappingWidth keeps labels on one line
    init = {"theme": "base", "fontFamily": mm["font_family"],
            "themeVariables": {"darkMode": True, "background": ground, "fontSize": "15px",
                               "primaryColor": tok["plate_low"], "primaryTextColor": tok["title"],
                               "primaryBorderColor": tok["accent"], "secondaryColor": tok["plate_low"],
                               "tertiaryColor": tok["plate_low"], "mainBkg": tok["plate_low"], "nodeBorder": tok["accent"],
                               "lineColor": wire, "textColor": tok["body"], "titleColor": tok["title"],
                               "clusterBkg": cluster_bg, "clusterBorder": _solid(tok["edge"]["color"], tok["edge"]["opacity"], ground),
                               "edgeLabelBackground": ground},
            "flowchart": {"curve": "basis", "htmlLabels": True, "wrappingWidth": 600, "nodeSpacing": 18, "rankSpacing": 56,
                          "padding": 14, "diagramPadding": 24}}
    out = ["%%{init: " + json.dumps(init) + "}%%", "flowchart LR"]
    out += [f"    accTitle: {_mq(model['title'])}", f"    accDescr: {_mq(model['desc'])}", ""]
    capture_note = f'<br/>{_mq(labels.get("partial", labels["uncaptured"]))}' if model.get("evidence") else ""
    out.append(f'    acct(["{_mq(acct["name"])}<br/>@{acct["login"]}{capture_note}"])')
    classes: dict[str, list[str]] = {"account": ["acct"]}
    styles: list[str] = []
    fam_defs: dict[str, dict] = {}
    langs: dict[str, str] = {}
    edges = 0
    links = 0

    def add(cls: str, ident: str) -> None:
        classes.setdefault(cls, []).append(ident)

    def family_class(node: dict) -> str:
        name = _cls("f_", "neutral" if node["neutral"] else node["family"])
        fam_defs.setdefault(name, node["style"])
        return name

    def lane(node: dict, ident: str, label: str, parent: str, long: bool) -> None:
        nonlocal edges, links
        out.append(f'    {ident}("{label}")')
        add(family_class(node), ident)
        out.append(f"    {parent} {'--->' if long else '-->'} {ident}")
        edges += 1
        items = _items(node, labels)
        if not items:
            return
        cid = f"{ident}_r"
        out.append(f'    subgraph {cid} [" "]')
        out.append("        direction LR")
        ids = []
        for i, it in enumerate(items, 1):
            rid = f"{cid}{i}"
            if it["kind"] == "note":
                ids.append(f'{rid}(["{_mq(it["text"])}"])')
                add("note", rid)
                continue
            suffix = "".join(f" · {labels[k].lower()}" for k in ("fork", "archived") if it[k])
            ids.append(f'{rid}(["{_mq(it["name"] + suffix)}"])')
            add("repo", rid)
            lc = _cls("l_", it["language"] or "default")
            langs.setdefault(lc, it["language"] or "default")
            add(lc, rid)
            for k in ("fork", "archived"):
                if it[k]:
                    add(k, rid)
        heads = []
        for i in range(0, len(ids), cols):
            row = ids[i:i + cols]
            out.append("        " + " ~~~ ".join(row))
            heads.append(f"{cid}{i + 1}")
            links += len(row) - 1
        out.append("    end")
        out.append(f"    {ident} --> {cid}")
        edges += 1
        # rows that hang off one node keep their order: without these Dagre may stack the rows in any order
        for h in heads:
            out.append(f"    {ident} ~~~ {h}")
        links += len(heads)
        styles.append(f"    style {cid} fill:{cluster_bg},stroke:{_solid(node['style']['tokens']['edge']['color'], node['style']['tokens']['edge']['opacity'], ground)},stroke-width:1px")

    long = bool(model["enterprises"])
    if model.get("personal"):
        p = model["personal"]
        lane(p, "me", f"{_mq(labels['personal_title'])}<br/>@{acct['login']}", "acct", long)
    for i, ent in enumerate(model["enterprises"], 1):
        eid = f"e{i}"
        role = {"owner": labels["owner"], "member": labels["member"]}.get(ent.get("role") or "")
        tail = f"{labels['enterprise'].title()} · {role}" if role else labels["enterprise"].title()
        if ent.get("capture_status", "complete") != "complete":
            tail += " · " + labels.get(ent["capture_status"], labels["uncaptured"])
        out.append(f'    {eid}{{{{"{_mq(ent["name"])}<br/>{_mq(tail)}"}}}}')
        out.append(f"    acct --> {eid}")
        edges += 1
        add("enterprise", eid)
        for j, org in enumerate(ent["orgs"], 1):
            lane(org, f"{eid}o{j}", _org_label(org, labels), eid, False)
    parent = "acct"
    if long and model["orgs"]:
        # beside an enterprise, the other orgs hang off one hub: they line up with the enterprise's orgs, and the
        # account sits between its three branches instead of beside its median child
        out.append(f'    hub(["{_mq(labels["organizations"])}"])')
        out.append("    acct --> hub")
        edges += 1
        add("hub", "hub")
        parent = "hub"
    for j, org in enumerate(model["orgs"], 1):
        lane(org, f"o{j}", _org_label(org, labels), parent, long and parent == "acct")

    ent = cfg["enterprise"]
    muted = cfg["muted"]
    repo_fill = _solid(cfg["pill"]["color"], cfg["pill"]["opacity"] * 2, ground)
    defs = [f"    classDef account fill:{tok['accent_deep']},stroke:{tok['accent']},stroke-width:2px,color:{tok['title']},font-weight:600",
            f"    classDef hub fill:{tok['plate_low']},stroke:{tok['accent']},stroke-width:1.5px,color:{tok['title']}",
            f"    classDef enterprise fill:{_solid(ent['fill'], 0.9, ground)},stroke:{ent['accent']},stroke-width:2px,"
            f"color:{tok['title']},font-weight:600"]
    for name in sorted(fam_defs):
        ft = fam_defs[name]["tokens"]
        defs.append(f"    classDef {name} fill:{ft['plate_low']},stroke:{ft['accent']},stroke-width:1.5px,color:{ft['title']}")
    defs.append(f"    classDef repo fill:{repo_fill},stroke:{_solid(tok['edge']['color'], 0.6, ground)},stroke-width:1px,"
                f"color:{tok['title']},font-family:monospace")
    lang_colours = brand.raw.get("languages") or {}
    for name in sorted(langs):
        defs.append(f"    classDef {name} stroke:{lang_colours.get(langs[name], lang_colours.get('default'))}")
    defs.append("    classDef fork stroke-dasharray:5 3")
    defs.append(f"    classDef archived color:{muted},stroke:{_solid(muted, 0.5, ground)}")
    defs.append(f"    classDef note fill:{ground},stroke:{_solid(muted, 0.6, ground)},stroke-dasharray:3 3,color:{muted}")
    order = ["account", "hub", "enterprise", *sorted(fam_defs), "repo", *sorted(langs), "fork", "archived", "note"]
    cls_lines = [f"    class {','.join(classes[c])} {c}" for c in order if classes.get(c)]
    text = "\n".join(out + [""] + defs + cls_lines + styles) + "\n"
    info = {"bytes": len(text.encode()), "edges": edges, "invisible_links": links,
            "nodes": sum(len(v) for k, v in classes.items() if not k.startswith("l_") and k not in ("fork", "archived"))}
    return text, info


def _org_label(org: dict, labels: dict) -> str:
    role = {"owner": labels["owner"], "member": labels["member"]}.get(org.get("role") or "")
    tail = f"@{org['login']}" + (f" · {role}" if role else "")
    return f"{_mq(org['name'])}<br/>{_mq(tail)}"
