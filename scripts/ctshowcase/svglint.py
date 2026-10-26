"""Static GitHub-safe SVG linter (SVG_RULES S-rules + decision 21), ported from scripts/ct_svg_lint.py and extended."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://www.w3.org/2000/svg}"
KB = 1000
KIND = {  # viewBoxes, hard budget, animation allowed, target budget
    "intro": (("0 0 1280 320", "0 0 1280 360"), 300 * KB, True, 120 * KB),
    "card": (("0 0 400 160",), 40 * KB, False, 30 * KB),
    "tile": (("0 0 400 160",), 40 * KB, False, 30 * KB),
    "plate": (("0 0 1280 320",), 150 * KB, False, 80 * KB),
    "divider": (("0 0 1200 20",), 4 * KB, False, 4 * KB),
}
BANNED_EL = {"script", "foreignObject", "iframe", "video", "audio", "canvas", "a", "font", "font-face"}
TEXT_EL = {"text", "tspan", "textPath"}
FILTER_EL = {"feTurbulence", "feDisplacementMap"}
SMIL = {"animate", "animateMotion", "animateTransform", "set"}
# S08: symbol glyphs that must be drawn as paths (arrows, stars, ticks, geometric shapes, dingbats)
SYMBOL = re.compile("[←-⇿☀-➿■-◿⬀-⯿✀-➿\U0001F300-\U0001FAFF]")


def lint_bytes(kind: str, raw: bytes, name: str = "<svg>") -> dict:
    if kind not in KIND:
        raise ValueError(f"unknown kind {kind}")
    vbs, hard, anim_ok, target = KIND[kind]
    fails: list[str] = []
    warns: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        fails.append("S01 BOM present")
    if len(raw) > hard:
        fails.append(f"S10 size {len(raw)} > {hard}")
    elif len(raw) > target:
        warns.append(f"S10 size {len(raw)} > target {target}")
    try:
        src = raw.decode("utf-8")
    except UnicodeDecodeError:
        return dict(file=name, result="FAIL", fails=["S01 not UTF-8"], warns=[], bytes=len(raw), animated=False)
    for c in re.findall(r"<!--(.*?)-->", src, re.S):
        if "--" in c:
            fails.append("S03 '--' inside comment")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return dict(file=name, result="FAIL", fails=sorted(set(fails + [f"S01 not well-formed: {e}"])), warns=warns,
                    bytes=len(raw), animated=False)
    if root.get("viewBox") not in vbs:
        fails.append(f"S02 viewBox {root.get('viewBox')} not in {list(vbs)}")
    else:
        w, h = root.get("viewBox").split()[2:]
        if (root.get("width"), root.get("height")) != (w, h):
            fails.append("S02 width/height must equal viewBox size")
    label = root.get("aria-label")
    if root.get("role") != "img" or not label:
        fails.append("S30 root needs role=img + aria-label")
    t = root.find(NS + "title")
    if t is None or (t.text or "").strip() != (label or ""):
        fails.append("S30 <title> must equal aria-label")
    d = root.find(NS + "desc")
    for txt in (label or "", (d.text or "") if d is not None else ""):
        if SYMBOL.search(txt):
            fails.append("S08 symbol glyph in aria-label/desc")
    animated = False
    parent = {c: p for p in root.iter() for c in p}
    for el in root.iter():
        tag = el.tag.replace(NS, "")
        if tag in BANNED_EL:
            fails.append(f"S05 banned element <{tag}>")
        if tag in TEXT_EL:
            fails.append(f"S05a text element <{tag}> (outline text to paths)")
        if tag in FILTER_EL:
            fails.append(f"S12 banned filter <{tag}>")
        for k, v in el.attrib.items():
            kk = k.split("}")[-1]
            if kk.startswith("on"):
                fails.append(f"S05 event handler {kk}")
            if "xlink" in k:
                fails.append("S05 use href, not xlink:href")
            if kk == "href":
                if not (v.startswith("#") or re.match(r"data:image/(png|webp|jpeg);base64,", v)):
                    fails.append(f"S05d external or non-raster href {v[:40]}")
        if tag in SMIL:
            animated = True
        if tag == "line" and (el.get("stroke") or "").startswith("url("):
            fails.append("S06 gradient-stroked <line>")
        if el.get("filter"):
            if any(c.tag.replace(NS, "") in SMIL for c in el.iter()) or "animation" in (el.get("style") or ""):
                fails.append("S14 animation under a filter")
    css = "".join(s.text or "" for s in root.iter(NS + "style"))
    if re.search(r"@import|@font-face", css):
        fails.append("S05c @import/@font-face in <style>")
    for u in re.findall(r"url\(([^)]*)\)", src):
        if not u.strip("'\"").startswith("#"):
            fails.append(f"S05d url() to non-fragment {u[:30]}")
    if "@keyframes" in css or re.search(r"animation\s*:", css) or "animation-name" in css:
        animated = True
    if animated:
        if not anim_ok:
            fails.append("S11 animation not allowed for this asset kind")
        flat = css.replace(" ", "")
        if not re.search(r"@media\(prefers-reduced-motion:reduce\)\{[^}]*\.anim\{display:none\}[^}]*\.still\{display:inline\}", flat):
            fails.append("S20 missing reduced-motion swap (.anim hidden, .still shown)")
        if ".still{display:none}" not in flat:
            fails.append("S20 .still must be hidden by default")
        anim_classes = set(re.findall(r"\.([\w-]+)\{[^}]*animation", css))

        def inside_anim(e):
            while e is not None:
                if "anim" in (e.get("class") or "").split():
                    return True
                e = parent.get(e)
            return False
        for el in root.iter():
            tag = el.tag.replace(NS, "")
            cls = set((el.get("class") or "").split())
            if (tag in SMIL or cls & anim_classes) and not inside_anim(el):
                fails.append(f"S21 animated <{tag} class={sorted(cls)}> outside .anim")
                break
        if not any("still" in (e.get("class") or "").split() for e in root.iter()):
            fails.append("S20 no .still group")
        if d is None:
            warns.append("S31 animated asset should carry <desc>")
        for m in re.finditer(r'dur="([\d.]+)s"[^>]*repeatCount="indefinite"', src):
            if float(m.group(1)) < 4:
                fails.append(f"S13 perpetual loop {m.group(1)}s < 4s")
        # S13a: every SMIL signal fades in/out with keyTimes
        for el in root.iter(NS + "animateMotion"):
            if not el.get("keyTimes"):
                fails.append("S13a signal motion without keyTimes")
    return dict(file=name, result="FAIL" if fails else "PASS", fails=sorted(set(fails)), warns=warns, bytes=len(raw),
                animated=animated)


def lint_file(kind: str, path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        return dict(file=str(p), result="FAIL", fails=["missing"], warns=[])
    r = lint_bytes(kind, p.read_bytes(), str(p))
    # D21 single dark asset: a *-dark.svg / *-light.svg beside a sibling fails
    m = re.match(r"(.+)-(dark|light)\.svg$", p.name)
    if m:
        sib = [p.with_name(f"{m.group(1)}.svg"), p.with_name(f"{m.group(1)}-{'light' if m.group(2) == 'dark' else 'dark'}.svg")]
        if any(s.exists() for s in sib):
            r["fails"] = sorted(set(r["fails"] + ["D21 single dark asset: light/dark sibling pair"]))
            r["result"] = "FAIL"
    return r
