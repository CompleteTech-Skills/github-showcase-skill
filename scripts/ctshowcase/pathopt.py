"""Rewrite absolute SVG path data (fontTools SVGPathPen output) as relative commands at a chosen precision.

Ported from the prototype (showcase/prototypes/build/card/pathopt.py).
"""
from __future__ import annotations

import re

TOK = re.compile(r"[MLHVQCZmlhvqcz]|-?\d*\.?\d+(?:e-?\d+)?")
ARGS = dict(M=2, L=2, H=1, V=1, Q=4, C=6, Z=0)


def fmt(v: float, nd: int) -> str:
    s = f"{v:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s


def rel(d: str, nd: int = 0, scale: float = 1.0) -> str:
    toks = TOK.findall(d)
    i = 0
    out: list[str] = []
    cx = cy = sx = sy = 0.0
    last = None

    def q(v):
        return round(v * scale, nd)

    while i < len(toks):
        c = toks[i]
        i += 1
        n = ARGS[c]
        if n == 0:
            out.append("z")
            cx, cy = sx, sy
            last = "z"
            continue
        while True:
            a = [float(t) for t in toks[i:i + n]]
            i += n
            if c == "H":
                a = [a[0], cy / scale]
                cc = "L"
            elif c == "V":
                a = [cx / scale, a[0]]
                cc = "L"
            else:
                cc = c
            pts = [q(v) for v in a]
            r = [pts[k] - (cx if k % 2 == 0 else cy) for k in range(len(pts))]
            cmd = cc.lower()
            if cmd == "l" and r[1] == 0:
                cmd, r = "h", [r[0]]
            elif cmd == "l" and r[0] == 0:
                cmd, r = "v", [r[1]]
            s = ""
            for v in r:
                t = fmt(v, nd)
                if s and not t.startswith("-"):
                    s += " "
                s += t
            out.append((cmd if cmd != last or cmd == "m" else " ") + s)
            last = cmd if cmd != "m" else "l"
            cx, cy = pts[-2], pts[-1]
            if cc == "M":
                sx, sy = cx, cy
                c, n = "L", 2
            if i >= len(toks) or toks[i].isalpha():
                break
    return "".join(out).replace("  ", " ")
