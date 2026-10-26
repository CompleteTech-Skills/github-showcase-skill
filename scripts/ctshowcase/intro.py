"""Profile intro SVG (prototype build.py intro(), dark only, decision 21; spec A6.4).

One file. Animated only for the personal profile and flagship orgs; otherwise --static is forced.
Motion follows SVG_RULES S11a-S13a and S20/S21 (reduced-motion .still frame, .anim groups).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .chips import eyebrow_track
from .errors import ConfigError
from .scene import Picture, SvgWriter, Text, _esc
from .typeset import Fonts, ntos

W = 1280
CLOUD_RIGHT = 0.7004  # right edge of the cloud-and-bulb inside the full CompleteTech logo (fraction of its width)


def _mark_box(img: Image.Image, max_w: float, max_h: float) -> tuple[float, float]:
    k = min(max_w / img.width, max_h / img.height)
    return img.width * k, img.height * k


def build(brand, fonts: Fonts, *, owner: str, name: str, eyebrow: str, tagline: str, chips: list[tuple[str, str]],
          mark_path, height: int = 320, static: bool = False) -> str:
    if height not in (320, 360):
        raise ConfigError("--height must be 320 or 360")
    H = height
    style = brand.style(owner)
    tok, fk = style["tokens"], style["fonts"]
    canvas = style["canvas"]
    gold, sky, azure, royal = tok["gold_trace"], tok["accent"], tok["accent_mid"], tok["accent_deep"]
    navy = tok["plate_low"]
    dy = (H - 320) / 2  # vertical centring offset for the 360 option

    w = SvgWriter(fonts, prefix="i")
    # -- mark (never cropped: the whole committed file is scaled to fit its box) -----------------------
    im = Image.open(mark_path)
    im.load()
    MX, MY, MHmax = 64, 72 + dy, 176
    MW, MH = _mark_box(im, 352, MHmax)
    MY = 72 + dy + (MHmax - MH) / 2
    mark = w.node(Picture(MX, MY, MW, MH, im, "webp", 82, 2))
    # traces leave from pads just right of the cloud (the mark's top 56%, above the wordmark band), run right inside
    # the cloud band, and turn at x = mark right + 24, so they never cross the wordmark (review P2.13)
    full_logo = Path(mark_path).name.startswith("logo")  # the full logo carries the wordmark below the cloud
    sx = MX + MW * (CLOUD_RIGHT if full_logo else 1.0) + 8
    vx = MX + MW + 24
    TX = max(448, vx + 44)  # the diagonal turn passes about 24 px above the eyebrow
    cy_top, cy_bot = 34 + dy, 288 + dy
    pa, pb = (sx, MY + (0.20 if full_logo else 0.35) * MH), (sx, MY + (0.45 if full_logo else 0.65) * MH)
    traces = [
        ("tA", f"M{ntos(pa[0])} {ntos(pa[1])}H{ntos(vx)}V{ntos(cy_top + 48)}L{ntos(vx + 48)} {ntos(cy_top)}H1184L1216 {ntos(cy_top + 32)}V{ntos(cy_top + 78)}",
         .20, 1.15, pa, (1216, cy_top + 84)),
        ("tB", f"M{ntos(pb[0])} {ntos(pb[1])}H{ntos(vx)}V{ntos(cy_bot - 48)}L{ntos(vx + 48)} {ntos(cy_bot)}H1184L1216 {ntos(cy_bot - 32)}V{ntos(cy_bot - 78)}",
         .35, 1.15, pb, (1216, cy_bot - 84)),
        ("tL", f"M{ntos(MX + MW * 0.32)} {ntos(MY - 18)}V{ntos(cy_top + 12)}L{ntos(MX + MW * 0.32 - 12)} {ntos(cy_top)}H0", .20, .45,
         (MX + MW * 0.32, MY - 18), None),
        ("tM", f"M{ntos(MX + MW * 0.14)} {ntos(MY + MH + 14)}V{ntos(cy_bot - 12)}L{ntos(MX + MW * 0.14 - 12)} {ntos(cy_bot)}H0", .30, .45,
         (MX + MW * 0.14, MY + MH + 14), None),
        ("tS", f"M752 {ntos(cy_top)}V0", 1.00, .25, None, None),
        ("tT", f"M1000 {ntos(cy_bot)}V{H}", 1.05, .25, None, None),
    ]
    junctions = [(752, cy_top), (1000, cy_bot)]
    motion_only = [("mC", f"M{ntos(pa[0])} {ntos(pa[1])}H{ntos(vx)}V{ntos(cy_top + 48)}L{ntos(vx + 48)} {ntos(cy_top)}H752V0")]

    def pad(c):
        return f'<circle cx="{ntos(c[0])}" cy="{ntos(c[1])}" r="6" fill="{navy}" stroke="{gold}" stroke-width="3"/>'

    defs_paths = "".join(f'<path id="{i}" d="{d}" pathLength="1"/>' for i, d, *_ in traces)
    defs_paths += "".join(f'<path id="{i}" d="{d}"/>' for i, d in motion_only)
    trace_attr = f'fill="none" stroke="{gold}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"'
    bloom_attr = f'fill="none" stroke="{gold}" stroke-opacity=".14" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"'
    still_traces = "".join(f'<use href="#{i}"/>' for i, *_ in traces)
    anim_traces = "".join(f'<use href="#{i}" class="d" style="animation-delay:{dl}s;animation-duration:{du}s"/>'
                          for i, d, dl, du, *_ in traces)
    pads_still, pads_anim = [], []
    for i, d, dl, du, sp, ep in traces:
        if sp:
            pads_still.append(pad(sp))
            pads_anim.append(f'<g class="f" style="animation-delay:{dl}s">{pad(sp)}</g>')
        if ep:
            pads_still.append(pad(ep))
            pads_anim.append(f'<g class="f" style="animation-delay:{dl + du - .05:.2f}s">{pad(ep)}</g>')
    for jx, jy in junctions:
        v = f'<circle cx="{jx}" cy="{ntos(jy)}" r="4.5" fill="{gold}"/>'
        pads_still.append(v)
        pads_anim.append(f'<g class="f" style="animation-delay:.9s">{v}</g>')

    signals = []
    for path, dur, end in (("tA", 6.1, (1216, cy_top + 84)), ("tB", 7.7, (1216, cy_bot - 84)), ("mC", 9.3, None)):
        b = "2.4s"
        signals.append(
            f'<g opacity="0"><animateMotion dur="{dur}s" begin="{b}" repeatCount="indefinite" calcMode="linear" '
            f'keyPoints="0;1;1" keyTimes="0;.8;1"><mpath href="#{path}"/></animateMotion>'
            f'<animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;.06;.74;.8;1" dur="{dur}s" begin="{b}" repeatCount="indefinite"/>'
            f'<circle r="14" fill="url(#sg)"/><circle r="3.5" fill="{tok["signal_core"]}"/></g>')
        if end:
            signals.append(
                f'<circle cx="{end[0]}" cy="{ntos(end[1])}" r="6" fill="none" stroke="{sky}" stroke-width="2" opacity="0">'
                f'<animate attributeName="r" values="6;6;26;26" keyTimes="0;.8;.97;1" dur="{dur}s" begin="{b}" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0;0;.9;0;0" keyTimes="0;.79;.81;.97;1" dur="{dur}s" begin="{b}" repeatCount="indefinite"/></circle>')

    # -- type ---------------------------------------------------------------------------------------------
    eb_font, name_font, tag_font = fk["eyebrow"], fk["display"], fk["tagline"]
    track = eyebrow_track(style)
    eb_size = fonts.fit(eb_font, eyebrow, (18, 16, 14), 1184 - TX, track) or 14
    eb_svg = w.node(Text(eb_font, eyebrow, eb_size, TX, 74 + dy, tok["eyebrow"], track))
    nsz = fonts.fit(name_font, name, (62, 56, 50, 44), 1184 - TX)
    if nsz is None:
        from .errors import ArtFail
        raise ArtFail("intro-name", name)
    name_svg = w.node(Text(name_font, name, nsz, TX, 146 + dy, tok["title"]))
    TS, TY, TGX = 32, 206 + dy, TX + 34
    tsz = fonts.fit(tag_font, tagline, (32, 28, 24), 1184 - TGX) or 24
    TS = tsz
    glyphs, tag_w = fonts.shape(tag_font, tagline, TS)
    adv = fonts.width(tag_font, "x", TS)
    n = len(tagline)
    t0, t1 = .6, 2.2
    step = (t1 - t0) / n
    tag_still = w.node(Text(tag_font, tagline, TS, TGX, TY, tok["body"]))
    uses = []
    for i, (gid, gx, gy) in enumerate(glyphs):
        ident = w.glyph(tag_font, gid)
        if ident is None:
            continue
        uses.append(f'<use href="#{ident}" x="{ntos(gx * 100 / TS)}" class="g" style="animation-delay:{t0 + (i + 1) * step:.3f}s"/>')
    tag_anim = (f'<g fill="{tok["body"]}" transform="translate({ntos(TGX)} {ntos(TY)}) scale({TS / 100:.4g})">' + "".join(uses) + "</g>")
    chevron = (f'<path d="M{ntos(TX + 2)} {ntos(TY - 20)}l10 9-10 9" fill="none" stroke="{gold}" stroke-width="3.5" '
               'stroke-linecap="round" stroke-linejoin="round"/>')
    caret_rect = f'<rect x="{ntos(TGX + 2)}" y="{ntos(TY - 24)}" width="{ntos(adv - 4)}" height="30" rx="2" fill="{sky}"/>'
    caret_anim = (f'<g class="cm" transform="translate({ntos(tag_w)} 0)" style="animation-duration:{t1 - t0:.2f}s;animation-delay:{t0}s;animation-timing-function:steps({n},end)">'
                  f'<g class="bl">{caret_rect}</g></g>')
    caret_still = f'<g transform="translate({ntos(tag_w)} 0)">{caret_rect}</g>'

    chip_svg, cx, cyc, ch = [], TX, 230 + dy, 36
    fc = fonts.face(fk["chip"])
    for label, kind in chips:
        c = tok["chip_key"] if kind == "key" else tok["chip_attr"]
        cw = fonts.width(fk["chip"], label, 18) + 36
        chip_svg.append(f'<rect x="{ntos(cx)}" y="{ntos(cyc)}" width="{ntos(cw)}" height="{ch}" rx="{ch / 2:g}" fill="{c["bg"]}"/>')
        chip_svg.append(w.node(Text(fk["chip"], label, 18, cx + 18, cyc + ch / 2 + fc.cap * 9, c["fg"])))
        cx += cw + 12
    if cx > 1184 + 12:
        from .errors import ArtFail
        raise ArtFail("intro-chips", " ".join(lb for lb, _ in chips))

    gradient = canvas["kind"] == "gradient-grid"
    c0 = canvas["from"] if gradient else canvas["color"]
    c1 = canvas["to"] if gradient else canvas["color"]
    bg_def = (f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c0}"/>'
              f'<stop offset="1" stop-color="{c1}"/></linearGradient>')
    ov = canvas.get("overlay") if gradient else None
    if ov:  # the golden's horizontal lift, shared with the banner and card
        bg_def += (f'<linearGradient id="lift" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{ov["color"]}" '
                   f'stop-opacity="{ov.get("from", 0)}"/><stop offset="1" stop-color="{ov["color"]}" stop-opacity="{ov.get("to", .55)}"/>'
                   '</linearGradient>')
    bg_fill = "url(#bg)"
    grid = ""
    if canvas["kind"] in ("gradient-grid", "flat-grid"):
        grid = (f'<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" '
                f'stroke="{canvas["grid"]}" stroke-width="1" stroke-opacity="{canvas.get("grid_opacity", .25)}"/></pattern>')
    elif canvas["kind"] == "halftone":
        p = canvas.get("pitch", 12)
        grid = (f'<pattern id="grid" width="{p}" height="{p}" patternUnits="userSpaceOnUse"><circle cx="{p / 2:g}" cy="{p / 2:g}" '
                f'r="{canvas.get("radius", 2)}" fill="{canvas["dot"]}" fill-opacity="{canvas.get("dot_opacity", .2)}"/></pattern>')
    grid_rect = f'<rect width="{W}" height="{H}" fill="url(#grid)"/>' if grid else ""
    lift_rect = f'<rect width="{W}" height="{H}" fill="url(#lift)"/>' if ov else ""
    bar = tok["bar"]
    bar_h = bar.get("height", 6)
    edge = (f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="15.5" fill="none" stroke="{tok["edge"]["color"]}" '
            f'stroke-opacity=".3"/>')
    title = f"{name} · {brand.strings['company']} — {tagline}" if owner == "CompleteDotTech" else f"{name} — {tagline}"
    chip_text = ", ".join(lb for lb, _ in chips)
    desc = (f"{'Animated header' if not static else 'Header'}: the {brand.strings['short']} mark on a dark plate"
            + (", gold circuit traces drawing out from the mark around the text while signals travel along them" if not static else
               " with gold circuit traces around the text")
            + f". Text: {eyebrow}; {name}; {'typed ' if not static else ''}tagline {tagline}; chips {chip_text}.")
    defs = f'''<defs>
{bg_def}
<linearGradient id="bar" x1="0" y1="0" x2="{W}" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{bar["from"]}"/><stop offset="1" stop-color="{bar.get("to") or bar["from"]}"/></linearGradient>
<radialGradient id="glow" cx="{ntos(MX + MW / 2)}" cy="{ntos(MY + MH / 2)}" r="190" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{sky}" stop-opacity=".30"/><stop offset=".5" stop-color="{azure}" stop-opacity=".10"/><stop offset="1" stop-color="{royal}" stop-opacity="0"/></radialGradient>
<radialGradient id="sg"><stop offset="0" stop-color="{sky}" stop-opacity=".75"/><stop offset=".35" stop-color="{sky}" stop-opacity=".28"/><stop offset="1" stop-color="{sky}" stop-opacity="0"/></radialGradient>
{grid}
<clipPath id="plate"><rect width="{W}" height="{H}" rx="16"/></clipPath>
{defs_paths}
{"".join(w.defs)}
</defs>'''
    if static:
        style_css = ""
        traces_svg = f'<g {bloom_attr}>{still_traces}</g><g {trace_attr}>{still_traces}</g>{"".join(pads_still)}'
        tag_block = f"{tag_still}{caret_still}"
    else:
        style_css = f'''<style>
.d{{stroke-dasharray:1;stroke-dashoffset:0;animation-name:dr;animation-timing-function:cubic-bezier(.55,0,.35,1);animation-fill-mode:backwards}}
@keyframes dr{{from{{stroke-dashoffset:1}}to{{stroke-dashoffset:0}}}}
.f{{animation:fi .3s ease-out backwards}}
.g{{animation:fi .01s linear backwards}}
@keyframes fi{{from{{opacity:0}}to{{opacity:1}}}}
.cm{{animation-name:cm;animation-fill-mode:backwards}}
@keyframes cm{{from{{transform:translateX(0)}}to{{transform:translateX({ntos(tag_w)}px)}}}}
.bl{{animation:bl 1s step-end 2.3s 3}}
@keyframes bl{{50%{{opacity:0}}}}
.still{{display:none}}
@media (prefers-reduced-motion:reduce){{.anim{{display:none}}.still{{display:inline}}}}
</style>
'''
        traces_svg = (f'<g class="still"><g {bloom_attr}>{still_traces}</g><g {trace_attr}>{still_traces}</g>{"".join(pads_still)}</g>\n'
                      f'<g class="anim"><g {bloom_attr}>{anim_traces}</g><g {trace_attr}>{anim_traces}</g>{"".join(pads_anim)}</g>')
        tag_block = (f'<g class="still">{tag_still}{caret_still}</g>\n'
                     f'<g class="anim">{tag_anim}{caret_anim}{"".join(signals)}</g>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{_esc(title)}">
<title>{_esc(title)}</title>
<desc>{_esc(desc)}</desc>
{style_css}{defs}
<g clip-path="url(#plate)">
<rect width="{W}" height="{H}" fill="{bg_fill}"/>
{lift_rect}{grid_rect}
<rect width="{W}" height="{H}" fill="url(#glow)"/>
{traces_svg}
<rect y="{H - bar_h}" width="{W}" height="{bar_h}" fill="url(#bar)"/>
</g>
{edge}
{mark}
{eb_svg}
{name_svg}
{chevron}
{tag_block}
{"".join(chip_svg)}
</svg>
'''
