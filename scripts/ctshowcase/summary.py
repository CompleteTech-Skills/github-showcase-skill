"""Account chart summary SVG (`account-chart render`): the profile intro's design closing the chart, with its languages.

One dark 1280x360 SVG of the intro kind (S02, S10, S11 to S21): the account's mark on the family plate, gold circuit
traces that draw out from it and carry signals, the eyebrow, the account's name, and each language's share of the code
the chart shows (forks excluded) as a bar that grows in, segment by segment, over a labelled key. Animated like the
intro by default; `static` gives the settled frame alone, for a page that already shows an animated intro (S11: one
animated asset per page). Text is outlined (S05a), every colour comes from brand.yaml or the capture, and the
percentages are the ones the chart's colour key shows and its Markdown repeats (S15).
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

from .chart import percent
from .chips import eyebrow_track
from .color import best_fg
from .errors import ArtFail
from .scene import Picture, SvgWriter, Text, _esc
from .typeset import Fonts, ntos

W, H = 1280, 360
DY = 20                     # the intro's 320 px geometry, centred in 360
CLOUD_RIGHT = 0.7004        # the cloud-and-bulb's right edge inside the full CompleteTech logo (as the intro)
RIGHT = 1184
BAR_Y, BAR_H, BAR_GAP = 184, 16, 3
KEY_Y, KEY_ROW, KEY_SIZE, KEY_ROWS = 230, 30, 15, 3  # the third row's baseline stays clear of the lower trace
DOT_R = 5


def _mark(brand, account: dict) -> tuple[Image.Image | None, bool]:
    """Prefer the account's configured mark; a verified CompleteTech identity may use its dark master."""
    path = account.get("mark")
    if not path:
        row = brand.org(account["login"])
        if row.get("known") and row.get("family") == "completetech":
            path = brand.mark_dark() or brand.dark_master()
    if not path or not Path(path).is_file():
        return None, False
    im = Image.open(path)
    im.load()
    return im, Path(path).name.startswith("logo")


def _key(fonts: Fonts, font: str, entries: list[dict], avail: float, other: str) -> list[dict]:
    """The key entries that fit KEY_ROWS rows of `avail` px; the smallest languages merge into `other` until they do."""
    entries = [dict(e) for e in entries if e["share"]]

    def width(e):
        return DOT_R * 2 + 8 + fonts.width(font, e["name"], KEY_SIZE) + 8 + fonts.width(font, percent(e["share"]), KEY_SIZE)

    def rows(es):
        n, x = 1, 0.0
        for e in es:
            w = width(e)
            if x and x + w > avail:
                n, x = n + 1, 0.0
            x += w + 28
        return n

    while len(entries) > 1 and rows(entries) > KEY_ROWS:
        rest = [e for e in entries if e["language"] is not None or e["name"] != other]
        tail = min(rest, key=lambda e: (e["share"], e["name"]))
        entries.remove(tail)
        merged = next((e for e in entries if e["language"] is None and e["name"] == other), None)
        if merged is None:
            entries.append({"name": other, "language": None, "share": tail["share"]})
        else:
            merged["share"] += tail["share"]
    return entries


def _segments(entries: list[dict], left: float, right: float) -> list[tuple[float, dict, float]]:
    """Apportion the available bar at SVG's tenth-pixel precision, without enlarging tiny code shares.

    Cumulative boundaries keep the final segment inside the bar even when earlier shares round up. A share
    smaller than one drawable unit may have zero width; its language and exact displayed share stay in the key.
    """
    if not entries:
        return []
    lo, hi = math.ceil(left * 10), math.floor(right * 10)
    gap = min(round(BAR_GAP * 10), max(0, hi - lo) // max(1, len(entries) - 1))
    available = max(0, hi - lo - gap * (len(entries) - 1))
    total = sum(entry["share"] for entry in entries)
    used, cumulative = 0, 0.0
    segments = []
    for i, entry in enumerate(entries):
        cumulative += entry["share"]
        end = available if i == len(entries) - 1 else round(available * cumulative / total)
        end = min(available, max(used, end))
        segments.append(((lo + used + gap * i) / 10, entry, (end - used) / 10))
        used = end
    return segments


def build(brand, fonts: Fonts, model: dict, *, static: bool = False) -> str | None:
    """The summary SVG, or None when the chart has no code shares to show (a snapshot without sizes)."""
    return build_with_key(brand, fonts, model, static=static)[0]


def build_with_key(brand, fonts: Fonts, model: dict, *, static: bool = False) -> tuple[str | None, list[dict]]:
    """Compose the SVG and its actual key together so the Markdown can repeat every displayed percentage."""
    if not model.get("code_share"):
        return None, []
    from .account import chart_labels
    acct = model["account"]
    style = acct["style"]
    tok, fk = style["tokens"], style["fonts"]
    labels = chart_labels(brand)
    langs = {**(model.get("language_colors") or {}), **(brand.raw.get("languages") or {})}
    canvas = style["canvas"] if style["canvas"]["kind"] in ("gradient-grid", "flat", "flat-grid") else \
        {"kind": "flat", "color": tok["plate_low"]}
    gold, sky, navy = tok["gold_trace"], tok["accent"], tok["plate_low"]
    w = SvgWriter(fonts, prefix="s")

    # -- the mark (never cropped), or the account's monogram ----------------------------------------------------
    im, full_logo = _mark(brand, acct)
    MX = 64
    if im is not None:
        k = min(352 / im.width, 176 / im.height)
        MW, MH = im.width * k, im.height * k
        MY = 72 + DY + (176 - MH) / 2
        mark_svg = w.node(Picture(MX, MY, MW, MH, im, "webp", 82, 2))
    else:
        MW = MH = 168
        MY = 72 + DY + 4
        ink = best_fg(tok["accent_deep"], [tok["title"], tok.get("ink") or navy])
        size = MH * 0.4
        tw = fonts.width(fk["display"], acct["initials"], size)
        cap = fonts.face(fk["display"]).cap * size
        mark_svg = (f'<circle cx="{ntos(MX + MW / 2)}" cy="{ntos(MY + MH / 2)}" r="{ntos(MW / 2)}" fill="{tok["accent_deep"]}"/>'
                    + w.node(Text(fk["display"], acct["initials"], size, MX + (MW - tw) / 2, MY + (MH + cap) / 2, ink)))

    # -- traces (the intro's geometry: out of the mark, around the text, to the right edge) -------------------
    sx = MX + MW * (CLOUD_RIGHT if full_logo else 1.0) + 8
    vx = MX + MW + 24
    TX = max(448, vx + 44)
    cy_top, cy_bot = 34 + DY, 288 + DY
    pa, pb = (sx, MY + (0.20 if full_logo else 0.35) * MH), (sx, MY + (0.45 if full_logo else 0.65) * MH)
    traces = [("tA", f"M{ntos(pa[0])} {ntos(pa[1])}H{ntos(vx)}V{ntos(cy_top + 48)}L{ntos(vx + 48)} {ntos(cy_top)}H1184"
                     f"L1216 {ntos(cy_top + 32)}V{ntos(cy_top + 78)}", .20, 1.15, pa, (1216, cy_top + 84)),
              ("tB", f"M{ntos(pb[0])} {ntos(pb[1])}H{ntos(vx)}V{ntos(cy_bot - 48)}L{ntos(vx + 48)} {ntos(cy_bot)}H1184"
                     f"L1216 {ntos(cy_bot - 32)}V{ntos(cy_bot - 78)}", .35, 1.15, pb, (1216, cy_bot - 84))]

    def pad(c):
        return f'<circle cx="{ntos(c[0])}" cy="{ntos(c[1])}" r="6" fill="{navy}" stroke="{gold}" stroke-width="3"/>'

    trace_attr = f'fill="none" stroke="{gold}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"'
    bloom_attr = f'fill="none" stroke="{gold}" stroke-opacity=".14" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"'
    defs_paths = "".join(f'<path id="{i}" d="{d}" pathLength="1"/>' for i, d, *_ in traces)
    still_traces = "".join(f'<use href="#{i}"/>' for i, *_ in traces)
    anim_traces = "".join(f'<use href="#{i}" class="d" style="animation-delay:{dl}s;animation-duration:{du}s"/>'
                          for i, _d, dl, du, *_ in traces)
    pads_still = "".join(pad(c) for *_x, sp, ep in traces for c in (sp, ep))
    pads_anim = "".join(f'<g class="f" style="animation-delay:{dl}s">{pad(sp)}</g>'
                        f'<g class="f" style="animation-delay:{dl + du - .05:.2f}s">{pad(ep)}</g>'
                        for _i, _d, dl, du, sp, ep in traces)
    signals = "".join(
        f'<g opacity="0"><animateMotion dur="{dur}s" begin="2.6s" repeatCount="indefinite" calcMode="linear" '
        f'keyPoints="0;1;1" keyTimes="0;.8;1"><mpath href="#{path}"/></animateMotion>'
        f'<animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;.06;.74;.8;1" dur="{dur}s" begin="2.6s" '
        f'repeatCount="indefinite"/><circle r="14" fill="url(#sg)"/><circle r="3.5" fill="{tok["signal_core"]}"/></g>'
        for path, dur in (("tA", 6.1), ("tB", 7.7)))

    # -- type: eyebrow and name -------------------------------------------------------------------------------
    track = eyebrow_track(style)
    eb_size = fonts.fit(fk["eyebrow"], acct["eyebrow"], (18, 16, 14), RIGHT - TX, track)
    nsz = fonts.fit(fk["display"], acct["name"], (56, 50, 44, 40), RIGHT - TX)
    if eb_size is None or nsz is None:
        raise ArtFail("summary-type", acct["name"])
    type_svg = (w.node(Text(fk["eyebrow"], acct["eyebrow"], eb_size, TX, 74 + DY, tok["eyebrow"], track))
                + w.node(Text(fk["display"], acct["name"], nsz, TX, 146 + DY, tok["title"])))

    # -- the bar and its key ----------------------------------------------------------------------------------
    key_font = fk["chip"]
    entries = _key(fonts, key_font, model["code_share"], RIGHT - TX, labels["other_languages"])
    segs = _segments(entries, TX, RIGHT)
    colour = {id(e): langs.get(e["language"] or "", langs.get("default")) for e in entries}
    track_rect = (f'<rect x="{TX}" y="{BAR_Y}" width="{RIGHT - TX}" height="{BAR_H}" rx="{BAR_H / 2:g}" fill="{tok["title"]}" '
                  'fill-opacity=".08"/>')

    def seg(x, e, sw, cls=""):
        return f'<rect{cls} x="{ntos(x)}" y="{BAR_Y}" width="{ntos(sw)}" height="{BAR_H}" fill="{colour[id(e)]}"/>'

    bar_still = "".join(seg(x, e, sw) for x, e, sw in segs)
    # The last key fades in for .4s after a 1.3s start. Bound the whole stagger to S11c's 2.5s,
    # regardless of how many short language names fit the key; retain the original spacing for small keys.
    stagger = min(.12, .8 / max(1, len(entries) - 1))
    bar_anim = "".join(seg(x, e, sw, f' class="gr" style="animation-delay:{1.0 + stagger * i:.2f}s"')
                       for i, (x, e, sw) in enumerate(segs))
    keys, kx, ky = [], TX, KEY_Y
    for e in entries:
        pct = percent(e["share"])
        name_w = fonts.width(key_font, e["name"], KEY_SIZE)
        iw = DOT_R * 2 + 8 + name_w + 8 + fonts.width(key_font, pct, KEY_SIZE)
        if kx > TX and kx + iw > RIGHT:
            kx, ky = TX, ky + KEY_ROW
        cap = fonts.face(key_font).cap * KEY_SIZE
        keys.append(f'<circle cx="{ntos(kx + DOT_R)}" cy="{ntos(ky - cap / 2)}" r="{DOT_R}" fill="{colour[id(e)]}"/>'
                    + w.node(Text(key_font, e["name"], KEY_SIZE, kx + DOT_R * 2 + 8, ky, tok["title"]))
                    + w.node(Text(key_font, pct, KEY_SIZE, kx + DOT_R * 2 + 16 + name_w, ky, tok["subtitle"])))
        kx += iw + 28
    keys_still = "".join(keys)
    keys_anim = "".join(f'<g class="f" style="animation-delay:{1.3 + stagger * i:.2f}s">{k}</g>' for i, k in enumerate(keys))

    # -- plate ------------------------------------------------------------------------------------------------
    gradient = canvas["kind"] == "gradient-grid"
    c0, c1 = (canvas["from"], canvas["to"]) if gradient else (canvas["color"], canvas["color"])
    bg = (f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c0}"/>'
          f'<stop offset="1" stop-color="{c1}"/></linearGradient>')
    ov = canvas.get("overlay") if gradient else None
    if ov:
        bg += (f'<linearGradient id="lift" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{ov["color"]}" '
               f'stop-opacity="{ov.get("from", 0)}"/><stop offset="1" stop-color="{ov["color"]}" '
               f'stop-opacity="{ov.get("to", .55)}"/></linearGradient>')
    grid = (f'<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" '
            f'stroke="{canvas["grid"]}" stroke-width="1" stroke-opacity="{canvas.get("grid_opacity", .25)}"/></pattern>'
            if canvas["kind"] in ("gradient-grid", "flat-grid") else "")
    bar = tok["bar"]
    bar_h = bar.get("height", 6)
    shares = "; ".join(f"{e['name']} {percent(e['share'])}" for e in entries)
    title = f"{acct['name']}: the languages of the code in this GitHub account map"
    identity = f"{acct['name']} mark" if im is not None else "account monogram"
    desc = (("Animated summary" if not static else "Summary")
            + f": the {identity} on a dark plate with gold circuit traces"
            + (" drawing out from it while signals travel along them, and a bar of languages growing in segment by segment"
               if not static else ", and a bar of languages")
            + f". Text: {acct['eyebrow']}; {acct['name']}; the code across the repositories shown, excluding forks: {shares}.")
    defs = (f'<defs>{bg}<linearGradient id="bar" x1="0" y1="0" x2="{W}" y2="0" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{bar["from"]}"/><stop offset="1" stop-color="{bar.get("to") or bar["from"]}"/>'
            f'</linearGradient><radialGradient id="sg"><stop offset="0" stop-color="{sky}" stop-opacity=".75"/>'
            f'<stop offset=".35" stop-color="{sky}" stop-opacity=".28"/><stop offset="1" stop-color="{sky}" stop-opacity="0"/>'
            f'</radialGradient>{grid}<clipPath id="plate"><rect width="{W}" height="{H}" rx="16"/></clipPath>'
            f'<clipPath id="track"><rect x="{TX}" y="{BAR_Y}" width="{RIGHT - TX}" height="{BAR_H}" rx="{BAR_H / 2:g}"/>'
            f'</clipPath>{defs_paths}{"".join(w.defs)}</defs>')
    plate = (f'<g clip-path="url(#plate)"><rect width="{W}" height="{H}" fill="url(#bg)"/>'
             + (f'<rect width="{W}" height="{H}" fill="url(#lift)"/>' if ov else "")
             + (f'<rect width="{W}" height="{H}" fill="url(#grid)"/>' if grid else ""))
    edge = (f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="15.5" fill="none" stroke="{tok["edge"]["color"]}" '
            'stroke-opacity=".3"/>')
    if static:
        css = ""
        body = (f'<g {bloom_attr}>{still_traces}</g><g {trace_attr}>{still_traces}</g>{pads_still}'
                f'<rect y="{H - bar_h}" width="{W}" height="{bar_h}" fill="url(#bar)"/></g>{edge}{mark_svg}'
                f'{type_svg}{track_rect}<g clip-path="url(#track)">{bar_still}</g>{keys_still}')
    else:
        css = ("<style>.d{stroke-dasharray:1;stroke-dashoffset:0;animation-name:dr;"
               "animation-timing-function:cubic-bezier(.55,0,.35,1);animation-fill-mode:backwards}"
               "@keyframes dr{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
               ".f{animation:fi .4s ease-out backwards}@keyframes fi{from{opacity:0}to{opacity:1}}"
               ".gr{transform-box:fill-box;transform-origin:0 50%;animation:gr .6s cubic-bezier(.2,.8,.2,1) backwards}"
               "@keyframes gr{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
               ".still{display:none}"
               "@media (prefers-reduced-motion:reduce){.anim{display:none}.still{display:inline}}</style>\n")
        body = (f'<g class="still"><g {bloom_attr}>{still_traces}</g><g {trace_attr}>{still_traces}</g>{pads_still}</g>'
                f'<g class="anim"><g {bloom_attr}>{anim_traces}</g><g {trace_attr}>{anim_traces}</g>{pads_anim}</g>'
                f'<rect y="{H - bar_h}" width="{W}" height="{bar_h}" fill="url(#bar)"/></g>{edge}{mark_svg}{type_svg}'
                f'{track_rect}<g class="still"><g clip-path="url(#track)">{bar_still}</g>{keys_still}</g>'
                f'<g class="anim"><g clip-path="url(#track)">{bar_anim}</g>{keys_anim}{signals}</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="{_esc(title)}">\n<title>{_esc(title)}</title>\n<desc>{_esc(desc)}</desc>\n{css}{defs}\n'
            f'{plate}{body}\n</svg>\n'), entries
