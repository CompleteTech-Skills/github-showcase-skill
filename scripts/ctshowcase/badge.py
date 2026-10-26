"""Offline flat badges (`readme --badges local`, kit conflict 1): outlined text, no badge server at view time."""
from __future__ import annotations

from .scene import Clip, Rect, Scene, Text, to_svg
from .typeset import Fonts

H, PAD, SIZE, FONT = 20, 6, 11, "poppins-medium"


def svg(brand, fonts: Fonts, label: str, message: str, colour: str) -> str:
    b = brand.raw["badges"]
    lw = fonts.width(FONT, label, SIZE) + 2 * PAD
    mw = fonts.width(FONT, message, SIZE) + 2 * PAD
    w = round(lw + mw)
    base = H / 2 + fonts.face(FONT).cap * SIZE / 2
    sc = Scene(w, H, title=f"{label}: {message}")
    sc.add(Clip(w, H, 3, [Rect(0, 0, lw, H, b["local_label_bg"]), Rect(lw, 0, w - lw, H, colour)]),
           Text(FONT, label, SIZE, PAD, base, b["local_text"]), Text(FONT, message, SIZE, lw + PAD, base, b["local_text"]))
    return to_svg(sc, fonts, prefix="b")
