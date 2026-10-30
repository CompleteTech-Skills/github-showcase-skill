"""README lint: R7 + decision 13 (banner first, plain <img>) + decision 18 (footer last, exact) (spec A6.11)."""
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import unquote

from . import footer as footermod
from .context import RepoContext
from .detect import standard
from .readme import BANNER_BLOCK, EMOJI, MARK, is_footer_like, masked, normalize_text, nav_first, preserved, split_sections

IMG_MD = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)")
IMG_HTML = re.compile(r"<img\b([^>]*)>", re.I)
PALETTE = {"1E3A8A", "005ADD", "067647", "64748B", "E551BA", "F386A1", "1E1E1E"}
REF_DEFINITION = re.compile(
    r"^ {0,3}\[((?:\\.|[^\]\\\n])+)\]:[ \t]*(?:\n[ \t]*)?(?:<([^<>\n]+)>|(\S+?))"
    r"(?:[ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^\)\n]*\)))?[ \t]*$", re.M)
REF_IMAGE = re.compile(r"!\[((?:\\.|[^\]\\])*)\](?:\[((?:\\.|[^\]\\])*)\])?(?!\()")


def _outside_code(text: str) -> str:
    """The text without fenced code (``` and ~~~), inline code and HTML comments."""
    text = re.sub(r"(?ms)^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,}).*?^ {0,3}\1", "", text)  # no backtick in a ``` info string
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _reference_images(text: str, document: str) -> list[tuple[str, str]]:
    """Resolve full, collapsed and shortcut image references used in the header.

    Definitions may occur anywhere outside code; the first definition wins, and labels are
    case-insensitive with collapsed whitespace. Unused definitions are not images.
    """
    def label(value):
        value = html.unescape(re.sub(r"\\([^\w\s])", r"\1", value))
        return " ".join(value.split()).casefold()

    definitions = {}
    for match in REF_DEFINITION.finditer(_outside_code(document)):
        definitions.setdefault(label(match.group(1)), html.unescape(match.group(2) or match.group(3)))
    sources = []
    for match in REF_IMAGE.finditer(text):
        pos = match.start() - 1
        while pos >= 0 and text[pos] == "\\":
            pos -= 1
        if (match.start() - pos - 1) % 2:
            continue  # an escaped exclamation mark is text, not an image
        key = label(match.group(2) or match.group(1))
        if key in definitions:
            sources.append((match.group(1), definitions[key]))
    return sources


def lint(ctx: RepoContext, path: Path, variant: str | None = None) -> dict:
    fails, warns = [], []
    incomplete: list[str] = []
    if not path.is_file():
        return {"file": str(path), "result": "fail", "fails": ["missing README"], "warns": []}
    raw = path.read_bytes()
    text = normalize_text(raw.decode("utf-8", errors="replace"))  # a leading BOM never hides the H1
    variant = variant if variant and variant != "auto" else ctx.det["variant"]
    rv = standard("readme-variants")
    if len(raw) >= 512_000:
        fails.append("R7 size >= 500 KiB")
    if variant in ("G", "H"):
        # §7.4 G/H: the hero banner block, then the callout, then the body unchanged, then the footer
        rest = text.lstrip()
        m = BANNER_BLOCK.match(rest)
        if m:
            rest = rest[m.end():].lstrip()
        elif ctx.art_status()["banner"] is None:
            fails.append(f"D13 variant {variant} must open with the hero banner block")
        first = rest.splitlines()[0] if rest.strip() else ""
        if not first.startswith(">"):
            fails.append(f"R7 variant {variant} callout must follow the banner")
        if ctx.footer_status() is None:
            st, _ = footermod.check(ctx.brand, text)
            if st != "pass":
                fails.append(f"D18 footer {st}")
        return _result(path, fails, warns, incomplete)
    plain = MARK.sub(lambda m: m.group(2), text)
    lines = [ln for ln in plain.splitlines() if ln.strip()]
    preserve = preserved(ctx, text)
    unchanged = preserve and ctx.preserve_unchanged()
    # §7.1 order (q57 `nav`): hero banner, then the nav line; "Nav line first" (readme.nav_first) puts the nav on top
    navs = lines
    if not nav_first(ctx) and not unchanged:
        n = _lead_banner_lines(lines)
        if n is None:
            fails.append("R7 the hero banner must open the README, then the nav line")
            navs = []
        else:
            navs = lines[n:]
    if not navs or not re.match(r"^\*\*[^*]+\*\* · ", navs[0]):
        fails.append("R7 nav line must follow the hero banner" if not nav_first(ctx) and not unchanged
                     else "R7 nav line must be the first line")
    # banner: first image, plain <img>, docs/images/banner.png
    imgs = [(m.start(), m.group(0)) for m in IMG_HTML.finditer(plain)] + [(m.start(), m.group(0)) for m in IMG_MD.finditer(plain)]
    imgs.sort()
    if preserve:
        if unchanged:
            note = "exempt:preserve-banner" if _first_is_foreign(imgs) else "exempt:preserve"
            warns.append(f"{note}: §7.0 additive-only README (q57 pres: unchanged); R2 tagline, R7 H2 order and D13 are n/a")
        else:
            warns.append("preserve: §7.0 additive-only README under the hero banner (q57 pres); R2 tagline and R7 H2 "
                         "order are n/a")
    if imgs:
        _, first = imgs[0]
        if "docs/images/banner.png" not in first and not unchanged:
            fails.append("D13 the banner must be the first image (docs/images/banner.png)")
        pic = re.search(r"<picture>.*?</picture>", plain, re.S)
        if pic and "docs/images/banner.png" in pic.group(0):
            fails.append("D13 banner must be a plain <img>, not <picture>")
    elif not unchanged:
        fails.append("D13 no banner image")
    # H1 (not F)
    h1s = [ln for ln in _outside_code(plain).splitlines() if re.match(r"^# \S", ln)]
    if variant == "F":
        if h1s:
            warns.append("variant F has no H1 (golden layout)")
    elif len(h1s) != 1:
        fails.append(f"R7 exactly one H1 required (found {len(h1s)})")
    # badges 2-4, palette tokens only
    shields = re.findall(r"img\.shields\.io/badge/([^)\"\s]+)", plain)
    header_part = plain.split("\n---\n", 1)[0]
    badge_header = _outside_code(header_part)
    image_sources = [m.group(2) for m in IMG_MD.finditer(badge_header)]
    image_sources += [source for _, source in _reference_images(badge_header, plain)]
    for image in IMG_HTML.finditer(badge_header):
        source = re.search(r"\bsrc\s*=\s*(['\"])(.*?)\1", image.group(1))
        if source:
            image_sources.append(source.group(2))
    nbadges = sum(bool(src.startswith("https://img.shields.io/badge/")
                       or re.fullmatch(r"(?:\./)?docs/images/badges/[^/?#]+\.svg(?:[?#].*)?", unquote(src))
                       or re.search(r"(?:^|/)badge\.svg(?:[?#].*)?$", src)) for src in image_sources)
    if not preserve:
        from .readme import badges as derivable
        floor = min(2, len(derivable(ctx)))  # a public repo with no licence and no language derives fewer than two
        if not max(1, floor) <= nbadges <= 4:
            fails.append(f"R7 2-4 header badges required (found {nbadges})")
        elif nbadges < 2:
            warns.append(f"badges-short: {nbadges} badge (no licence or language to show yet)")
    for s in shields:
        col = re.split(r"[?)]", s.rsplit("-", 1)[-1])[0].upper()
        if re.fullmatch(r"[0-9A-F]{6}", col) and col not in PALETTE:
            fails.append(f"R7 off-palette badge colour {col}")
    # tagline == description
    desc = (ctx.meta.get("description") or "").strip()
    if desc and not preserve:
        if f"**{desc}**" not in plain and f"<b>{desc}</b>" not in plain:
            fails.append("R2 bold tagline must equal the GitHub description")
    elif not desc:
        warns.append("tagline not checked (no description in meta)")
    # H2 order, License last
    pre, sections = split_sections(plain)
    order = [h for h, _ in rv["variants"].get(variant, [])]
    # "License" and "Licensing" are one slot: a private repository reads "## License" (proprietary) even in variant F
    lic_slot = next((h for h in order if h in ("License", "Licensing")), "License")
    names = [EMOJI.sub("", h).strip() for h, _ in sections]
    names = [lic_slot if n in ("License", "Licensing") else n for n in names]
    req = [h for h, r in rv["variants"].get(variant, []) if r == "R"]
    pos = [order.index(n) for n in names if n in order]
    if pos != sorted(pos) and not preserve:
        fails.append("R7 H2 order does not follow the variant")
    for n in names:
        if n not in order and n != "Notes" and not preserve:
            fails.append(f"R7 unexpected H2 '{n}' (move under ## Notes)")
    if names and names[-1] not in ("License", "Licensing"):
        lic_needed = any(r in ("License", "Licensing") for r in req)
        if any(n in ("License", "Licensing") for n in names) or lic_needed and ctx.meta.get("license"):
            fails.append("R7 License must be the last H2")
    if "Notes" in names and names.index("Notes") < len(names) - 2:
        fails.append("R7 ## Notes must sit immediately before License")
    for r in req:
        if r in ("License", "Licensing"):
            if r not in names and not (ctx.public and not ctx.meta.get("license")):
                incomplete.append(f"needs-input:{variant}:{r}")
            continue
        alt_ok = variant == "D" and r == "Findings" and "Status" in names
        if r not in names and not alt_ok and not preserve:
            incomplete.append(f"needs-input:{variant}:{r}")
    for h, b in sections:
        if not re.sub(r"<!--.*?-->", "", b, flags=re.S).strip() and h not in ("Notes",):
            incomplete.append(f"needs-input:{variant}:{h}")
    # footer last and exact
    if ctx.footer_status() is None:  # the watching org's `footer: false` exempts only its forks
        st, _ = footermod.check(ctx.brand, text)
        if st != "pass":
            fails.append(f"D18 footer {st}")
        elif _extra_footer(text):
            fails.append("D18 footer fail:duplicate")
    # alt text, local images
    for m in IMG_MD.finditer(plain):
        if not m.group(1).strip():
            fails.append(f"R7 image without alt text: {m.group(2)[:40]}")
        _local(path, m.group(2), fails)
    for m in IMG_HTML.finditer(plain):
        a = re.search(r'alt="([^"]*)"', m.group(1))
        if not a or not a.group(1).strip():
            fails.append("R7 <img> without alt text")
        src = re.search(r'src="([^"]+)"', m.group(1))
        if src:
            _local(path, src.group(1), fails, example="examples" in src.group(1))
    for alt, source in _reference_images(_outside_code(plain), plain):
        if not alt.strip():
            fails.append(f"R7 image without alt text: {source[:40]}")
        _local(path, source, fails)
    body = _outside_code(plain)
    ph = re.search(rv["placeholder_regex"], body)
    if ph or re.search(r"<…>|<\.\.\.>", body):
        fails.append(f"R7 placeholder text: {ph.group(0) if ph else '<…>'}")
    if EMOJI.search(plain):
        fails.append("R7 emoji present")
    fences = re.findall(r"(?m)^(```+)(.*)$", plain)
    for i in range(0, len(fences), 2):
        if not fences[i][1].strip():
            fails.append("R7 code fence without info string")
            break
    prose = re.sub(r"https?://\S+", "", body)
    for bad in ("Complete Tech LLC", "Completetech LLC", "CompleTetech LLC"):
        if bad in prose:
            fails.append(f"§1.2 brand string '{bad}'")
    return _result(path, fails, warns, incomplete)


def _lead_banner_lines(lines: list[str]) -> int | None:
    """How many leading non-blank lines the hero banner takes (`<p align="center">`, the banner `<img>`, `</p>`, or one
    line holding it), or None when the README does not open with it."""
    if len(lines) >= 3 and lines[0].strip() == '<p align="center">' and "docs/images/banner.png" in lines[1] \
            and lines[2].strip() == "</p>":
        return 3
    if lines and "docs/images/banner.png" in lines[0]:
        return 1
    return None


def _first_is_foreign(imgs) -> bool:
    return bool(imgs) and "docs/images/banner.png" not in imgs[0][1]


def _extra_footer(text: str) -> bool:
    """True when a footer-like block (centred, "Built by", complete.tech) sits anywhere but last: an old footer kept
    beside the decision 18 one."""
    t = masked(text.replace(footermod.START + "\n", "").replace("\n" + footermod.END, ""))
    blocks = [b for b in re.split(r"\n\s*\n", t.strip()) if b.strip()]
    return any(is_footer_like(b) for b in blocks[:-1])


def _local(readme: Path, src: str, fails: list, example: bool = False):
    if re.match(r"^(https?:|data:|#)", src):
        return
    p = (readme.parent / unquote(src.split("#")[0].split("?")[0])).resolve()  # docs/My%20Shot.png names "My Shot.png"
    if not p.is_file():
        fails.append(f"R7 local image does not resolve: {src}")
        return
    limit = 600_000 if example else 300_000
    if p.stat().st_size > limit:
        fails.append(f"R7 image over {limit} B: {src}")


def _result(path, fails, warns, incomplete):
    res = "fail" if fails else ("incomplete" if incomplete else "pass")
    return {"file": str(path), "result": res, "fails": sorted(set(fails)), "warns": warns,
            "logs": sorted(set(incomplete))}
