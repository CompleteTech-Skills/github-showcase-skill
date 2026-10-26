"""Bundled OFL fonts: verify against FONTS.json (sha256) or fetch the pinned upstream files."""
from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.request

from . import ASSETS

FONT_DIR = ASSETS / "fonts"
MANIFEST = FONT_DIR / "FONTS.json"


def manifest() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["fonts"]


def check() -> list[dict]:
    out = []
    for e in manifest():
        p = FONT_DIR / e["file"]
        ok = p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == e["sha256"]
        lic = (FONT_DIR / e["license"]).is_file()
        out.append({"file": e["file"], "result": "pass" if ok and lic else "fail",
                    **({} if ok else {"problem": "missing or sha256 mismatch"}), **({} if lic else {"license": "missing"})})
    return out


def fetch() -> list[dict]:
    out = []
    for e in manifest():
        p = FONT_DIR / e["file"]
        if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == e["sha256"]:
            out.append({"file": e["file"], "result": "present"})
            continue
        with urllib.request.urlopen(e["source_url"], timeout=60) as r:  # pinned HTTPS GET only
            data = r.read()
        if e.get("derived"):
            from fontTools.ttLib import TTFont
            from fontTools.varLib import instancer
            with tempfile.NamedTemporaryFile(suffix=".ttf") as tmp:
                tmp.write(data)
                tmp.flush()
                inst = instancer.instantiateVariableFont(TTFont(tmp.name), {"wght": 600, "opsz": 72, "SOFT": 0, "WONK": 0},
                                                         updateFontNames=True)
                inst.save(str(p))
            data = p.read_bytes()
        ok = hashlib.sha256(data).hexdigest() == e["sha256"]
        if ok:
            p.write_bytes(data)
        out.append({"file": e["file"], "result": "fetched" if ok else "fail", **({} if ok else {"problem": "sha256 mismatch"})})
    return out
