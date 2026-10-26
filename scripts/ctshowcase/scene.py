"""A tiny scene graph with two backends (spec A5): GitHub-safe SVG and a deterministic PNG rasterizer.

Text is never emitted as <text>: glyph outlines are defined once in <defs> and placed with <use>
(S05a). The PNG backend fills the same outlines with a nonzero-winding scanline rasterizer at 4x
supersampling, so the SVG card and the PNG banner share identical metrics without FreeType.
"""
from __future__ import annotations

import base64
import io
import math
import re
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .color import rgb
from .typeset import Fonts, ntos

SS = 4  # supersampling factor for every anti-aliased mask


# ---------------------------------------------------------------------------------------------
# Paints
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Linear:
    """Linear gradient across the shape's box: direction 'v' (top->bottom) or 'h' (left->right)."""

    stops: tuple  # ((offset, color, opacity), ...)
    direction: str = "v"


def paint_key(p) -> str:
    return repr(p)


# ---------------------------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------------------------
@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: object = None
    rx: float = 0
    opacity: float = 1.0
    stroke: str | None = None
    stroke_width: float = 1.0
    stroke_opacity: float = 1.0


@dataclass
class Circle:
    cx: float
    cy: float
    r: float
    fill: str | None = None
    stroke: str | None = None
    stroke_width: float = 1.0
    opacity: float = 1.0


@dataclass
class Stroke:
    """Open polyline path (absolute M/L/H/V only), round caps and joins."""

    d: str
    color: str
    width: float
    opacity: float = 1.0


@dataclass
class Poly:
    """Filled closed polygon (icons such as the star are drawn as paths, S08)."""

    points: list
    fill: str
    opacity: float = 1.0


@dataclass
class Shadow:
    x: float
    y: float
    w: float
    h: float
    rx: float
    color: str
    opacity: float
    blur: float = 0.0


@dataclass
class Picture:
    x: float
    y: float
    w: float
    h: float
    image: Image.Image
    fmt: str = "webp"
    quality: int = 84
    embed_scale: int = 2
    resample: str = "lanczos"  # "nearest" for pixel art (§9.5 avatar rule)


@dataclass
class Grid:
    x: float
    y: float
    w: float
    h: float
    pitch: float
    color: str
    opacity: float


@dataclass
class Halftone:
    x: float
    y: float
    w: float
    h: float
    pitch: float
    radius: float
    color: str
    opacity: float


@dataclass
class Text:
    font: str
    text: str
    size: float
    x: float
    baseline: float
    fill: str
    track: float = 0.0
    opacity: float = 1.0


@dataclass
class Clip:
    """Clip children to a rounded rect (SVG clipPath; PNG alpha mask)."""

    w: float
    h: float
    rx: float
    children: list = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0


@dataclass
class Scene:
    w: int
    h: int
    nodes: list = field(default_factory=list)
    title: str = ""
    desc: str = ""

    def add(self, *nodes):
        self.nodes.extend(nodes)
        return self


# ---------------------------------------------------------------------------------------------
# SVG backend
# ---------------------------------------------------------------------------------------------
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


RESAMPLE = {"lanczos": Image.LANCZOS, "nearest": Image.NEAREST}


def picture_uri(img: Image.Image, w: float, h: float, fmt: str, quality: int, scale: int, resample: str = "lanczos") -> str:
    im = img.convert("RGBA")
    tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    if (tw, th) != im.size:
        im = im.resize((tw, th), RESAMPLE[resample])
    b = io.BytesIO()
    if fmt == "webp":
        im.save(b, "WEBP", quality=quality, method=6, lossless=resample == "nearest")
        mt = "image/webp"
    else:
        im.save(b, "PNG", optimize=True)
        mt = "image/png"
    return f"data:{mt};base64," + base64.b64encode(b.getvalue()).decode()


class SvgWriter:
    def __init__(self, fonts: Fonts, prefix: str = "g"):
        self.fonts, self.prefix = fonts, prefix
        self.defs: list[str] = []
        self.glyph_ids: dict[tuple[str, int], str | None] = {}
        self.paints: dict[str, str] = {}
        self.n = 0

    def _id(self, kind: str) -> str:
        self.n += 1
        return f"{kind}{self.n}"

    def paint(self, p, box=None) -> str:
        if p is None:
            return "none"
        if isinstance(p, str):
            return p
        k = paint_key(p)
        if k not in self.paints:
            gid = self._id("lg")
            x2, y2 = ("0", "1") if p.direction == "v" else ("1", "0")
            stops = "".join(
                f'<stop offset="{ntos(o) if o not in (0, 1) else int(o)}" stop-color="{c}"'
                + (f' stop-opacity="{ntos(a)}"' if a != 1 else "") + "/>"
                for o, c, a in p.stops)
            self.defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">{stops}</linearGradient>')
            self.paints[k] = gid
        return f"url(#{self.paints[k]})"

    def glyph(self, font: str, gid: int) -> str | None:
        key = (font, gid)
        if key not in self.glyph_ids:
            d = self.fonts.face(font).glyph_svg(gid)
            if not d:
                self.glyph_ids[key] = None
            else:
                ident = f"{self.prefix}{len([v for v in self.glyph_ids.values() if v]) + 1}"
                self.glyph_ids[key] = ident
                self.defs.append(f'<path id="{ident}" d="{d}"/>')
        return self.glyph_ids[key]

    def node(self, n) -> str:
        if isinstance(n, Rect):
            a = [f'x="{ntos(n.x)}"', f'y="{ntos(n.y)}"', f'width="{ntos(n.w)}"', f'height="{ntos(n.h)}"']
            if n.rx:
                a.append(f'rx="{ntos(n.rx)}"')
            a.append(f'fill="{self.paint(n.fill)}"')
            if n.opacity != 1:
                a.append(f'fill-opacity="{n.opacity:.3g}"')
            if n.stroke:
                a += [f'stroke="{n.stroke}"', f'stroke-width="{ntos(n.stroke_width)}"']
                if n.stroke_opacity != 1:
                    a.append(f'stroke-opacity="{n.stroke_opacity:.3g}"')
            return "<rect " + " ".join(a) + "/>"
        if isinstance(n, Circle):
            a = [f'cx="{ntos(n.cx)}"', f'cy="{ntos(n.cy)}"', f'r="{ntos(n.r)}"', f'fill="{n.fill or "none"}"']
            if n.stroke:
                a += [f'stroke="{n.stroke}"', f'stroke-width="{ntos(n.stroke_width)}"']
            if n.opacity != 1:
                a.append(f'opacity="{n.opacity:.3g}"')
            return "<circle " + " ".join(a) + "/>"
        if isinstance(n, Stroke):
            op = f' stroke-opacity="{n.opacity:.3g}"' if n.opacity != 1 else ""
            return (f'<path d="{n.d}" fill="none" stroke="{n.color}" stroke-width="{ntos(n.width)}"{op} '
                    'stroke-linecap="round" stroke-linejoin="round"/>')
        if isinstance(n, Poly):
            d = "M" + "L".join(f"{ntos(x)} {ntos(y)}" for x, y in n.points) + "Z"
            op = f' fill-opacity="{n.opacity:.3g}"' if n.opacity != 1 else ""
            return f'<path d="{d}" fill="{n.fill}"{op}/>'
        if isinstance(n, Shadow):
            return (f'<rect x="{ntos(n.x)}" y="{ntos(n.y)}" width="{ntos(n.w)}" height="{ntos(n.h)}" rx="{ntos(n.rx)}" '
                    f'fill="{n.color}" fill-opacity="{n.opacity:.3g}"/>')
        if isinstance(n, Picture):
            uri = picture_uri(n.image, n.w, n.h, n.fmt, n.quality, n.embed_scale, n.resample)
            return f'<image x="{ntos(n.x)}" y="{ntos(n.y)}" width="{ntos(n.w)}" height="{ntos(n.h)}" href="{uri}"/>'
        if isinstance(n, Grid):
            pid = self._id("gp")
            p = ntos(n.pitch)
            self.defs.append(f'<pattern id="{pid}" width="{p}" height="{p}" patternUnits="userSpaceOnUse">'
                             f'<path d="M{p} 0H0V{p}" fill="none" stroke="{n.color}" stroke-opacity="{n.opacity:.3g}"/></pattern>')
            return f'<rect x="{ntos(n.x)}" y="{ntos(n.y)}" width="{ntos(n.w)}" height="{ntos(n.h)}" fill="url(#{pid})"/>'
        if isinstance(n, Halftone):
            pid = self._id("hp")
            p, c = ntos(n.pitch), ntos(n.pitch / 2)
            self.defs.append(f'<pattern id="{pid}" width="{p}" height="{p}" patternUnits="userSpaceOnUse">'
                             f'<circle cx="{c}" cy="{c}" r="{ntos(n.radius)}" fill="{n.color}" fill-opacity="{n.opacity:.3g}"/></pattern>')
            return f'<rect x="{ntos(n.x)}" y="{ntos(n.y)}" width="{ntos(n.w)}" height="{ntos(n.h)}" fill="url(#{pid})"/>'
        if isinstance(n, Text):
            glyphs, _ = self.fonts.shape(n.font, n.text, n.size, n.track)
            uses = []
            for gid, gx, gy in glyphs:
                ident = self.glyph(n.font, gid)
                if ident is None:
                    continue
                ys = f' y="{ntos(gy * 100 / n.size)}"' if gy else ""
                uses.append(f'<use href="#{ident}" x="{ntos(gx * 100 / n.size)}"{ys}/>')
            op = f' fill-opacity="{n.opacity:.3g}"' if n.opacity != 1 else ""
            return (f'<g fill="{n.fill}"{op} transform="translate({ntos(n.x)} {ntos(n.baseline)}) scale({n.size / 100:.4g})">'
                    + "".join(uses) + "</g>")
        if isinstance(n, Clip):
            cid = self._id("cp")
            xy = f'x="{ntos(n.x)}" y="{ntos(n.y)}" ' if (n.x or n.y) else ""
            self.defs.append(f'<clipPath id="{cid}"><rect {xy}width="{ntos(n.w)}" height="{ntos(n.h)}" rx="{ntos(n.rx)}"/></clipPath>')
            return f'<g clip-path="url(#{cid})">' + "".join(self.node(c) for c in n.children) + "</g>"
        raise TypeError(f"unknown node {type(n).__name__}")


def to_svg(scene: Scene, fonts: Fonts, prefix: str = "g", extra_style: str = "") -> str:
    w = SvgWriter(fonts, prefix)
    body = "\n".join(w.node(n) for n in scene.nodes)
    label = _esc(scene.title)
    desc = f"<desc>{_esc(scene.desc)}</desc>\n" if scene.desc else ""
    style = f"<style>{extra_style}</style>\n" if extra_style else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {scene.w} {scene.h}" width="{scene.w}" '
            f'height="{scene.h}" role="img" aria-label="{label}">\n<title>{label}</title>\n{desc}{style}'
            f'<defs>\n' + "\n".join(w.defs) + f'\n</defs>\n{body}\n</svg>\n')


# ---------------------------------------------------------------------------------------------
# PNG backend
# ---------------------------------------------------------------------------------------------
def fill_nonzero(polys, w: int, h: int) -> bytes:
    """Rasterize polygons (pixel coords) into a w*h 0/255 mask, nonzero winding at pixel centres."""
    edges = []
    for poly in polys:
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if y0 == y1:
                continue
            d = 1
            if y0 > y1:
                x0, y0, x1, y1, d = x1, y1, x0, y0, -1
            edges.append((y0, y1, x0, (x1 - x0) / (y1 - y0), d))
    edges.sort()
    buf = bytearray(w * h)
    active: list = []
    ei, ne = 0, len(edges)
    full = b"\xff" * w
    for row in range(h):
        yc = row + 0.5
        while ei < ne and edges[ei][0] <= yc:
            active.append(edges[ei])
            ei += 1
        if not active:
            if ei >= ne:
                break
            continue
        active = [e for e in active if e[1] > yc]
        xs = []
        for y0, y1, x0, slope, d in active:
            if y0 <= yc:
                xs.append((x0 + (yc - y0) * slope, d))
        if not xs:
            continue
        xs.sort()
        wind = 0
        base = row * w
        for i in range(len(xs) - 1):
            wind += xs[i][1]
            if wind != 0:
                a = max(0, math.ceil(xs[i][0] - 0.5))
                b = min(w, math.ceil(xs[i + 1][0] - 0.5))
                if b > a:
                    buf[base + a: base + b] = full[: b - a]
    return bytes(buf)


class PngRenderer:
    def __init__(self, fonts: Fonts, scale: float):
        self.fonts, self.s = fonts, scale

    # helpers -------------------------------------------------------------------------------------
    def _box(self, x, y, w, h):
        s = self.s
        x0, y0 = math.floor(x * s), math.floor(y * s)
        x1, y1 = math.ceil((x + w) * s), math.ceil((y + h) * s)
        return x0, y0, max(1, x1 - x0), max(1, y1 - y0)

    def _shape_mask(self, x, y, w, h, draw):
        """Anti-aliased mask for a shape drawn in local supersampled coords."""
        bx, by, bw, bh = self._box(x - 1, y - 1, w + 2, h + 2)
        m = Image.new("L", (bw * SS, bh * SS), 0)
        draw(ImageDraw.Draw(m), (bx, by))
        return (bx, by), m.reduce(SS)

    def _ss(self, v, origin):
        return (v * self.s - origin) * SS

    def _paint_image(self, paint, size):
        w, h = size
        if isinstance(paint, str):
            return Image.new("RGB", size, rgb(paint))
        stops = paint.stops
        n = h if paint.direction == "v" else w
        strip = Image.new("RGB", (1, n) if paint.direction == "v" else (n, 1))
        px = strip.load()
        for i in range(n):
            t = (i + 0.5) / n
            for k in range(len(stops) - 1):
                o0, c0, _ = stops[k]
                o1, c1, _ = stops[k + 1]
                if t <= o1 or k == len(stops) - 2:
                    u = 0 if o1 == o0 else min(1, max(0, (t - o0) / (o1 - o0)))
                    a, b = rgb(c0), rgb(c1)
                    col = tuple(round(a[j] + (b[j] - a[j]) * u) for j in range(3))
                    break
            if paint.direction == "v":
                px[0, i] = col
            else:
                px[i, 0] = col
        return strip.resize(size, Image.NEAREST)

    def _alpha_image(self, paint, size):
        """Opacity ramp of a Linear paint's stops as an L image of `size`."""
        w, h = size
        n = h if paint.direction == "v" else w
        vals = []
        for i in range(n):
            t = (i + 0.5) / n
            stops = paint.stops
            a = stops[-1][2]
            for k in range(len(stops) - 1):
                o0, _, a0 = stops[k]
                o1, _, a1 = stops[k + 1]
                if t <= o1:
                    u = 0 if o1 == o0 else min(1, max(0, (t - o0) / (o1 - o0)))
                    a = a0 + (a1 - a0) * u
                    break
            vals.append(max(0, min(255, round(a * 255))))
        strip = Image.new("L", (1, n) if paint.direction == "v" else (n, 1))
        strip.putdata(vals)
        return strip.resize(size, Image.NEAREST)

    def _composite(self, canvas, origin, mask, paint, opacity=1.0, box_size=None):
        if opacity != 1:
            mask = mask.point(lambda v: round(v * opacity))
        layer = self._paint_image(paint, box_size or mask.size)
        if layer.size != mask.size:
            layer = layer.crop((0, 0) + mask.size) if layer.size[0] >= mask.size[0] and layer.size[1] >= mask.size[1] \
                else layer.resize(mask.size)
        canvas.paste(layer, origin, mask)

    # nodes ---------------------------------------------------------------------------------------
    def draw(self, canvas: Image.Image, n, clip=None):
        s = self.s
        if isinstance(n, Rect):
            if n.fill is not None:
                def d(dr, o, n=n):
                    box = [self._ss(n.x, o[0]), self._ss(n.y, o[1]), self._ss(n.x + n.w, o[0]) - 1,
                           self._ss(n.y + n.h, o[1]) - 1]
                    if n.rx:
                        dr.rounded_rectangle(box, radius=n.rx * s * SS, fill=255)
                    else:
                        dr.rectangle(box, fill=255)
                o, m = self._shape_mask(n.x, n.y, n.w, n.h, d)
                if isinstance(n.fill, Linear):
                    # gradient spans the rect box, not the padded mask
                    bx, by, bw, bh = self._box(n.x, n.y, n.w, n.h)
                    grad = self._paint_image(n.fill, (bw, bh))
                    layer = Image.new("RGB", m.size)
                    layer.paste(grad, (bx - o[0], by - o[1]))
                    mm = m if n.opacity == 1 else m.point(lambda v: round(v * n.opacity))
                    if any(a != 1 for _, _, a in n.fill.stops):  # per-stop opacity (the canvas overlay)
                        alpha = Image.new("L", m.size, 0)
                        alpha.paste(self._alpha_image(n.fill, (bw, bh)), (bx - o[0], by - o[1]))
                        mm = ImageChops.multiply(mm, alpha)
                    canvas.paste(layer, o, self._clipm(mm, o, clip))
                else:
                    self._composite(canvas, o, self._clipm(m, o, clip), n.fill, n.opacity)
            if n.stroke:
                sw = n.stroke_width

                def d2(dr, o, n=n, sw=sw):
                    box = [self._ss(n.x, o[0]), self._ss(n.y, o[1]), self._ss(n.x + n.w, o[0]) - 1,
                           self._ss(n.y + n.h, o[1]) - 1]
                    dr.rounded_rectangle(box, radius=max(0, n.rx) * s * SS, outline=255, width=max(1, round(sw * s * SS)))
                o, m = self._shape_mask(n.x - sw, n.y - sw, n.w + 2 * sw, n.h + 2 * sw, d2)
                self._composite(canvas, o, self._clipm(m, o, clip), n.stroke, n.stroke_opacity)
            return
        if isinstance(n, Poly):
            xs, ys = [p[0] for p in n.points], [p[1] for p in n.points]
            bx, by, bw, bh = self._box(min(xs) - 1, min(ys) - 1, max(xs) - min(xs) + 2, max(ys) - min(ys) + 2)
            poly = [((x * s - bx) * SS, (y * s - by) * SS) for x, y in n.points]
            m = Image.frombytes("L", (bw * SS, bh * SS), fill_nonzero([poly], bw * SS, bh * SS)).reduce(SS)
            self._composite(canvas, (bx, by), self._clipm(m, (bx, by), clip), n.fill, n.opacity)
            return
        if isinstance(n, Shadow):
            pad = n.blur * 3 + 2

            def d(dr, o, n=n):
                box = [self._ss(n.x, o[0]), self._ss(n.y, o[1]), self._ss(n.x + n.w, o[0]) - 1, self._ss(n.y + n.h, o[1]) - 1]
                dr.rounded_rectangle(box, radius=n.rx * s * SS, fill=255)
            o, m = self._shape_mask(n.x - pad, n.y - pad, n.w + 2 * pad, n.h + 2 * pad, d)
            if n.blur:
                m = m.filter(ImageFilter.GaussianBlur(n.blur * s / 2))
            self._composite(canvas, o, self._clipm(m, o, clip), n.color, n.opacity)
            return
        if isinstance(n, Circle):
            def d(dr, o, n=n, fill=True):
                box = [self._ss(n.cx - n.r, o[0]), self._ss(n.cy - n.r, o[1]), self._ss(n.cx + n.r, o[0]), self._ss(n.cy + n.r, o[1])]
                dr.ellipse(box, fill=255)
            sw = n.stroke_width if n.stroke else 0
            r_out = n.r + sw / 2
            if n.stroke:
                outer = Circle(n.cx, n.cy, r_out)
                o, m = self._shape_mask(n.cx - r_out, n.cy - r_out, 2 * r_out, 2 * r_out, lambda dr, o: d(dr, o, outer))
                self._composite(canvas, o, self._clipm(m, o, clip), n.stroke, n.opacity)
            if n.fill:
                inner = Circle(n.cx, n.cy, n.r - sw / 2)
                o, m = self._shape_mask(n.cx - n.r, n.cy - n.r, 2 * n.r, 2 * n.r, lambda dr, o: d(dr, o, inner))
                self._composite(canvas, o, self._clipm(m, o, clip), n.fill, n.opacity)
            return
        if isinstance(n, Stroke):
            pts = _polyline(n.d)
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            pad = n.width

            def d(dr, o, n=n, pts=pts):
                q = [(self._ss(x, o[0]), self._ss(y, o[1])) for x, y in pts]
                wpx = max(1, round(n.width * s * SS))
                dr.line(q, fill=255, width=wpx, joint="curve")
                for x, y in (q[0], q[-1]):
                    dr.ellipse([x - wpx / 2, y - wpx / 2, x + wpx / 2, y + wpx / 2], fill=255)
            o, m = self._shape_mask(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad, d)
            self._composite(canvas, o, self._clipm(m, o, clip), n.color, n.opacity)
            return
        if isinstance(n, Picture):
            bx, by, bw, bh = self._box(n.x, n.y, n.w, n.h)
            tw, th = max(1, round(n.w * s)), max(1, round(n.h * s))
            im = n.image.convert("RGBA").resize((tw, th), RESAMPLE[n.resample])
            ox, oy = round(n.x * s), round(n.y * s)
            if clip is not None:
                cm = self._clipm(Image.new("L", im.size, 255), (ox, oy), clip)
                im.putalpha(ImageChops.multiply(im.getchannel("A"), cm))
            if canvas.mode == "RGBA":
                canvas.alpha_composite(im, (ox, oy))
            else:
                canvas.paste(im.convert("RGB"), (ox, oy), im.getchannel("A"))
            return
        if isinstance(n, Grid):
            bx, by, bw, bh = self._box(n.x, n.y, n.w, n.h)
            m = Image.new("L", (bw, bh), 0)
            dr = ImageDraw.Draw(m)
            lw = max(1, round(s))
            k = 0
            while k * n.pitch <= n.w:
                x = round((n.x + k * n.pitch) * s) - bx
                dr.rectangle([x, 0, x + lw - 1, bh], fill=255)
                k += 1
            k = 0
            while k * n.pitch <= n.h:
                y = round((n.y + k * n.pitch) * s) - by
                dr.rectangle([0, y, bw, y + lw - 1], fill=255)
                k += 1
            self._composite(canvas, (bx, by), self._clipm(m, (bx, by), clip), n.color, n.opacity)
            return
        if isinstance(n, Halftone):
            bx, by, bw, bh = self._box(n.x, n.y, n.w, n.h)
            m = Image.new("L", (bw * SS, bh * SS), 0)
            dr = ImageDraw.Draw(m)
            r = n.radius * s * SS
            j = 0
            while j * n.pitch < n.h:
                i = 0
                while i * n.pitch < n.w:
                    cx = ((n.x + i * n.pitch + n.pitch / 2) * s - bx) * SS
                    cy = ((n.y + j * n.pitch + n.pitch / 2) * s - by) * SS
                    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
                    i += 1
                j += 1
            m = m.reduce(SS)
            self._composite(canvas, (bx, by), self._clipm(m, (bx, by), clip), n.color, n.opacity)
            return
        if isinstance(n, Text):
            self._text(canvas, n, clip)
            return
        if isinstance(n, Clip):
            for c in n.children:
                self.draw(canvas, c, clip=n)
            return
        raise TypeError(f"unknown node {type(n).__name__}")

    def _clipm(self, mask, origin, clip):
        if clip is None:
            return mask
        s = self.s
        full = Image.new("L", (mask.size[0] * SS, mask.size[1] * SS), 0)
        dr = ImageDraw.Draw(full)
        x0, y0 = clip.x * s, clip.y * s
        dr.rounded_rectangle([(x0 - origin[0]) * SS, (y0 - origin[1]) * SS, (x0 + clip.w * s - origin[0]) * SS - 1,
                              (y0 + clip.h * s - origin[1]) * SS - 1], radius=clip.rx * s * SS, fill=255)
        return ImageChops.multiply(mask, full.reduce(SS))

    def _text(self, canvas, n: Text, clip):
        f = self.fonts.face(n.font)
        glyphs, adv = self.fonts.shape(n.font, n.text, n.size, n.track)
        s = self.s
        top = n.baseline - f.ascent * n.size - 2
        bot = n.baseline + f.descent * n.size + 2
        bx, by, bw, bh = self._box(n.x - 2, top, adv + 4, bot - top)
        polys = []
        for gid, gx, gy in glyphs:
            for c in f.glyph_polys(gid):
                polys.append([(((n.x + gx + px * n.size) * s - bx) * SS, ((n.baseline + gy + py * n.size) * s - by) * SS)
                              for px, py in c])
        W, H = bw * SS, bh * SS
        m = Image.frombytes("L", (W, H), fill_nonzero(polys, W, H)).reduce(SS)
        self._composite(canvas, (bx, by), self._clipm(m, (bx, by), clip), n.fill, n.opacity)


_CMD = re.compile(r"([MLHV])\s*([-\d.]+)(?:[\s,]+([-\d.]+))?")


def _polyline(d: str):
    pts, x, y = [], 0.0, 0.0
    for c, a, b in _CMD.findall(d):
        if c in "ML":
            x, y = float(a), float(b)
        elif c == "H":
            x = float(a)
        elif c == "V":
            y = float(a)
        pts.append((x, y))
    return pts


def to_png_image(scene: Scene, fonts: Fonts, scale: float = 2, background: str | None = None,
                 alpha_rx: float | None = None) -> Image.Image:
    """Render to RGB; with alpha_rx, the plate's rounded corners become transparent (RGBA preview)."""
    size = (round(scene.w * scale), round(scene.h * scale))
    canvas = Image.new("RGB", size, rgb(background) if background else (0, 0, 0))
    r = PngRenderer(fonts, scale)
    for n in scene.nodes:
        r.draw(canvas, n)
    if alpha_rx is None:
        return canvas
    m = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] * SS - 1, size[1] * SS - 1], radius=alpha_rx * scale * SS, fill=255)
    out = canvas.convert("RGBA")
    out.putalpha(m.reduce(SS))
    return out


def png_bytes(img: Image.Image, quantize: bool = False) -> bytes:
    """Deterministic PNG: no metadata chunks, compress level 9."""
    if quantize:
        img = img.convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    b = io.BytesIO()
    img.save(b, "PNG", compress_level=9, optimize=True)
    return b.getvalue()
