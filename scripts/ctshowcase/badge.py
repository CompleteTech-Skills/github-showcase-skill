"""Offline flat badges (`readme --badges local`, kit conflict 1): outlined text, no badge server at view time."""
from __future__ import annotations

from .color import contrast
from .errors import NeedsInput
from .scene import Clip, Rect, Scene, Text, to_svg
from .typeset import Fonts

H, PAD, SIZE, FONT = 20, 6, 11, "poppins-medium"


def _foreground(brand, background: str, style: dict | None) -> str:
    # Keep passing historical text bytes; otherwise prefer approved family foregrounds.
    candidates = [brand.raw["badges"]["local_text"]]
    tokens = (style or {}).get("tokens", {})
    candidates += [tokens.get(chip, {}).get("fg") for chip in ("chip_key", "chip_attr")]
    canvas = (style or {}).get("canvas", {})
    candidates += [canvas.get("color"), canvas.get("from")]
    candidates += list(brand.raw.get("contrast_candidates", []))
    for candidate in candidates:
        if candidate and contrast(candidate, background) >= 4.5:
            return candidate
    raise NeedsInput("badge-contrast", "local badge text needs a configured foreground with contrast >= 4.5:1")


def svg(brand, fonts: Fonts, label: str, message: str, colour: str, *, style: dict | None = None) -> str:
    b = brand.raw["badges"]
    label_fg = _foreground(brand, b["local_label_bg"], style)
    value_fg = _foreground(brand, colour, style)
    lw = fonts.width(FONT, label, SIZE) + 2 * PAD
    mw = fonts.width(FONT, message, SIZE) + 2 * PAD
    w = round(lw + mw)
    base = H / 2 + fonts.face(FONT).cap * SIZE / 2
    sc = Scene(w, H, title=f"{label}: {message}")
    sc.add(Clip(w, H, 3, [Rect(0, 0, lw, H, b["local_label_bg"]), Rect(lw, 0, w - lw, H, colour)]),
           Text(FONT, label, SIZE, PAD, base, label_fg), Text(FONT, message, SIZE, lw + PAD, base, value_fg))
    return to_svg(sc, fonts, prefix="b")
