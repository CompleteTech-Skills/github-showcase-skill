"""HarfBuzz shaping + fontTools outlines, size ladders and wrapping (spec A5, S09).

Text never truncates: when nothing on a ladder fits, callers raise ArtFail and write nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.basePen import BasePen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

from . import pathopt
from .errors import ArtFail


def ntos(v: float) -> str:
    """Fixed one-decimal formatting with no trailing zeros (deterministic SVG numbers)."""
    s = f"{v:.1f}"
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return "0" if s in ("-0", "") else s


class _FlattenPen(BasePen):
    """Collect contours as polygons in font units (fixed subdivision; cached per glyph)."""

    QSEG, CSEG = 16, 24

    def __init__(self, glyphset):
        super().__init__(glyphset)
        self.contours: list[list[tuple[float, float]]] = []
        self.cur: list[tuple[float, float]] = []

    def _moveTo(self, p):
        if len(self.cur) > 2:
            self.contours.append(self.cur)
        self.cur = [p]

    def _lineTo(self, p):
        self.cur.append(p)

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        for i in range(1, self.QSEG + 1):
            t = i / self.QSEG
            a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
            self.cur.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        for i in range(1, self.CSEG + 1):
            t = i / self.CSEG
            a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
            self.cur.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))

    def _closePath(self):
        if len(self.cur) > 2:
            self.contours.append(self.cur)
        self.cur = []

    _endPath = _closePath


@dataclass
class Face:
    key: str
    path: Path
    tt: TTFont
    hbfont: object
    upem: int
    cap: float          # cap height, em fraction
    ascent: float       # em fraction (hhea)
    descent: float      # em fraction, positive below baseline
    mono: bool
    _svg: dict = field(default_factory=dict)
    _poly: dict = field(default_factory=dict)

    def glyph_svg(self, gid: int) -> str:
        """Glyph outline at 100 units/em, y down, relative integer path data (S05a)."""
        if gid not in self._svg:
            gs = self.tt.getGlyphSet()
            name = self.tt.getGlyphName(gid)
            base = 100.0 / self.upem
            pen = SVGPathPen(gs, ntos=ntos)
            gs[name].draw(TransformPen(pen, (base, 0, 0, -base, 0, 0)))
            d = pen.getCommands()
            self._svg[gid] = pathopt.rel(d, 0) if d else ""
        return self._svg[gid]

    def glyph_polys(self, gid: int) -> list[list[tuple[float, float]]]:
        """Glyph contours in em units (x right, y down)."""
        if gid not in self._poly:
            gs = self.tt.getGlyphSet()
            pen = _FlattenPen(gs)
            gs[self.tt.getGlyphName(gid)].draw(pen)
            pen._closePath()
            u = float(self.upem)
            self._poly[gid] = [[(x / u, -y / u) for x, y in c] for c in pen.contours]
        return self._poly[gid]


class Fonts:
    """Font registry keyed by brand.yaml font keys."""

    def __init__(self, brand):
        self.brand = brand
        self._faces: dict[str, Face] = {}

    def face(self, key: str) -> Face:
        if key not in self._faces:
            path = self.brand.font_file(key)
            tt = TTFont(str(path))
            blob = hb.Blob.from_file_path(str(path))
            hbfont = hb.Font(hb.Face(blob))
            upem = tt["head"].unitsPerEm
            os2 = tt["OS/2"]
            cap = (getattr(os2, "sCapHeight", 0) or int(upem * 0.7)) / upem
            hhea = tt["hhea"]
            mono = key.startswith("mono") or bool(tt["post"].isFixedPitch)
            self._faces[key] = Face(key, path, tt, hbfont, upem, cap, hhea.ascent / upem, -hhea.descent / upem, mono)
        return self._faces[key]

    # -- shaping ----------------------------------------------------------------------------------
    def shape(self, key: str, text: str, size: float, track: float = 0.0):
        """Return ([(gid, x, y)], advance width) in px. Tracking is an em fraction (S: +12% = 0.12)."""
        f = self.face(key)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(f.hbfont, buf, {"liga": False, "calt": False} if f.mono else {})
        s = size / f.upem
        out, x = [], 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((info.codepoint, x + pos.x_offset * s, -pos.y_offset * s))
            x += pos.x_advance * s + track * size
        if out and track:
            x -= track * size
        return out, x

    def width(self, key: str, text: str, size: float, track: float = 0.0) -> float:
        return self.shape(key, text, size, track)[1]

    # -- ladders ----------------------------------------------------------------------------------
    def fit(self, key: str, text: str, sizes, maxw: float, track: float = 0.0):
        """First ladder size at which one line fits, else None."""
        for s in sizes:
            if self.width(key, text, s, track) <= maxw + 1e-6:
                return s
        return None

    def wrap(self, key: str, text: str, size: float, maxw: float, maxlines: int, track: float = 0.0,
             hyphens: bool = True):
        """Greedy wrap at spaces (dropped) and after hyphens (kept). None when it needs > maxlines."""
        tokens: list[tuple[str, str]] = []  # (text, joiner-before-next) joiner '' after hyphen, ' ' after space
        word = ""
        for ch in text:
            if ch == " ":
                if word:
                    tokens.append((word, " "))
                word = ""
            elif ch == "-" and hyphens:
                word += ch
                tokens.append((word, ""))
                word = ""
            else:
                word += ch
        if word:
            tokens.append((word, " "))
        lines: list[str] = []
        cur, joiner = "", ""
        for tok, j in tokens:
            cand = cur + joiner + tok if cur else tok
            if self.width(key, cand, size, track) <= maxw + 1e-6:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = tok
            joiner = j
        if cur:
            lines.append(cur)
        if len(lines) > maxlines or any(self.width(key, ln, size, track) > maxw + 1e-6 for ln in lines):
            return None
        return lines

    def wrap_ladder(self, key: str, text: str, sizes, maxw: float, maxlines_options, element: str,
                    track: float = 0.0, hyphens: bool = True):
        """First (size, lines) on the ladder; raises ArtFail (never an ellipsis)."""
        for s in sizes:
            for ml in maxlines_options:
                lines = self.wrap(key, text, s, maxw, ml, track, hyphens)
                if lines:
                    return s, lines
        raise ArtFail(element, text)


def split_last_hyphen(fonts: Fonts, key: str, text: str, size: float, maxw: float):
    """Two lines, broken at the last hyphen (or domain dot) whose head fits (banner/card slug rule)."""
    idx = [i for i, c in enumerate(text) if c in "-."]
    for i in reversed(idx):
        a, b = text[: i + 1], text[i + 1:]
        if fonts.width(key, a, size) <= maxw and fonts.width(key, b, size) <= maxw:
            return [a, b]
    return None
