"""Colour parsing and WCAG contrast (S33, A3.3). Colours are always supplied by brand.yaml."""
from __future__ import annotations


def rgb(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgba(value: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    r, g, b = rgb(value)
    return r, g, b, max(0, min(255, round(opacity * 255)))


def luminance(value: str) -> float:
    def ch(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb(value)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def best_fg(bg: str, candidates: list[str]) -> str:
    """Highest-contrast candidate; ties keep the earlier candidate."""
    best, score = candidates[0], -1.0
    for c in candidates:
        s = contrast(c, bg)
        if s > score + 1e-9:
            best, score = c, s
    return best


def mix(a: str, b: str, t: float) -> tuple[int, int, int]:
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t)


def hexstr(c: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*c)


def lab(value) -> tuple[float, float, float]:
    """CIE L*a*b* (D65) of a hex colour or an (r, g, b) tuple."""
    r, g, b = rgb(value) if isinstance(value, str) else value[:3]

    def lin(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    rl, gl, bl = lin(r), lin(g), lin(b)
    x = (0.4124 * rl + 0.3576 * gl + 0.1805 * bl) / 0.95047
    y = 0.2126 * rl + 0.7152 * gl + 0.0722 * bl
    z = (0.0193 * rl + 0.1192 * gl + 0.9505 * bl) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a, b) -> float:
    """CIE76 colour difference."""
    la, lb = lab(a), lab(b)
    return sum((p - q) ** 2 for p, q in zip(la, lb)) ** 0.5
