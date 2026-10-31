"""README lint: R7 + decision 13 (banner first, plain <img>) + decision 18 (footer last, exact) (spec A6.11)."""
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import unquote

from . import footer as footermod
from .mdcode import FENCE_OPEN, code_spans, find_inline_code
from .context import RepoContext
from .detect import standard
from .readme import BANNER_BLOCK, EMOJI, MARK, is_footer_like, masked, normalize_text, nav_first, preserved, split_sections

IMG_MD = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)")
IMG_HTML = re.compile(r"<img\b([^>]*)>", re.I)
PALETTE = {"1E3A8A", "005ADD", "067647", "64748B", "E551BA", "F386A1", "1E1E1E"}
REF_DEFINITION = re.compile(
    r"^ {0,3}\[((?:\\.|[^\]\\\n])+)\]:[ \t]*(?:\n[ \t]*)?(?:<([^<>\n]+)>|(\S+?))"
    r"(?:(?:[ \t]+|[ \t]*\n[ \t]*)(?:\"(?:\\.|[^\"\\\n]|\n(?![ \t]*\n))*\"|'(?:\\.|[^'\\\n]|\n(?![ \t]*\n))*'"
    r"|\((?:\\.|[^()\\\n]|\n(?![ \t]*\n))*\)))?[ \t]*$", re.M)  # a title may span lines but never a blank one
# CommonMark raw HTML: an open tag needs a valid tag name, valid attributes and a closing `>`; anything else is text
_ATTR = r"""\s+[A-Za-z_:][A-Za-z0-9_.:-]*(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?"""
HTML_OPEN_TAG = re.compile(rf"<([A-Za-z][A-Za-z0-9-]*)((?:{_ATTR})*)\s*/?>")
HTML_ATTR = re.compile(r"""([A-Za-z_:][A-Za-z0-9_.:-]*)(?:\s*=\s*([^\s"'=<>`]+|'[^']*'|"[^"]*"))?""")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
SHIELDS_SRC = re.compile(r"https?://img\.shields\.io/badge/", re.I)
SHIELDS_BADGE = re.compile(r"https?://img\.shields\.io/badge/(.+)", re.I)


def _escaped(text: str, i: int) -> bool:
    """True when an odd number of consecutive backslashes immediately precedes index `i` (CommonMark escape)."""
    count, before = 0, i - 1
    while before >= 0 and text[before] == "\\":
        count += 1
        before -= 1
    return count % 2 == 1


def _search_unescaped(pattern, text: str, pos: int):
    """First match at or after `pos` whose opening character is not backslash-escaped."""
    match = pattern.search(text, pos)
    while match and _escaped(text, match.start()):
        match = pattern.search(text, match.start() + 1)
    return match


def _definition_spans(document: str) -> list[tuple[int, int]]:
    """Spans of complete reference definitions (label, destination and title): their text is not Markdown."""
    return [(m.start(), m.end()) for m in REF_DEFINITION.finditer(_outside_code(document, mask_inline=False))]


class _HTMLTokens:
    """Strict CommonMark open tags (never raises): spans let Markdown parsing respect attribute boundaries."""
    def __init__(self, text):
        self.text = text
        self.tags = []
        self.images = []
        for match in HTML_OPEN_TAG.finditer(text):
            start, end = match.span()
            if _escaped(text, start):
                continue
            self.tags.append((start, end))
            if match.group(1).lower() == "img":
                first = {}
                for name, value in HTML_ATTR.findall(match.group(2)):
                    value = value[1:-1] if value[:1] in ("'", '"') and value else value
                    first.setdefault(name.lower(), html.unescape(value))
                self.images.append((first.get("alt") or "", first.get("src") or "", start, end))


def _fence_spans(text: str) -> list[tuple[int, int]]:
    """Fenced code blocks only (the spans `code_spans` opens at a fence line)."""
    fences = []
    for a, b in code_spans(text):
        begin = text.rfind("\n", 0, a) + 1
        end = text.find("\n", begin)
        if FENCE_OPEN.match(text[begin:end if end >= 0 else len(text)]) and not text[begin:a].strip():
            fences.append((a, b))
    return sorted(fences)


def _outside_code(text: str, mask_inline: bool = True) -> str:
    """Mask Markdown code and comments without reading literal backticks in HTML attributes as code.
    Constructs are taken left to right, and inline code is looked for again after every HTML tag or comment, so a
    backtick inside an attribute or comment is literal and the next real code span still opens (CommonMark).
    `mask_inline=False` still lets inline code win precedence but leaves its characters readable (reference labels).
    The result has the same length (and newline positions) as `text`."""
    fences = _fence_spans(text)
    out, pos = list(text), 0
    tag = comment = inline = None

    def blank(a, b):
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = " "

    def next_inline(start):
        while True:
            found = find_inline_code(text, start)  # (start, end) or None
            if not found:
                return False
            inside = next((f for f in fences if f[0] <= found[0] < f[1]), None)
            if inside is None:
                return found
            start = inside[1]

    while pos < len(text):
        if inline is not False and (inline is None or inline[0] < pos):
            inline = next_inline(pos)
        if tag is not False and (tag is None or tag.start() < pos):
            tag = _search_unescaped(HTML_OPEN_TAG, text, pos) or False
        if comment is not False and (comment is None or comment.start() < pos):
            comment = _search_unescaped(HTML_COMMENT, text, pos) or False
        fence = next((f for f in fences if f[0] >= pos), None)
        code = min([c for c in ((inline if inline else None), fence) if c], default=None)
        found = [m for m in (tag, comment) if m]
        nxt = min(found, key=lambda m: m.start()) if found else None
        if code and (nxt is None or code[0] <= nxt.start()):
            if mask_inline or code is fence:
                blank(*code)
            pos = code[1]
        elif nxt is not None:
            if nxt is comment:
                blank(*nxt.span())
            pos = nxt.end()
        else:
            break
    return "".join(out)


def _closing_bracket(text: str, start: int) -> int | None:
    """Find a balanced closing bracket, respecting escaped and nested brackets."""
    depth, pos = 1, start + 1
    while pos < len(text):
        char = text[pos]
        if char == "\\":
            pos += 2
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if not depth:
                return pos
        pos += 1
    return None


def _inline_image_target(text: str, start: int) -> tuple[str, int] | None:
    """Read a Markdown destination and optional title after its opening parenthesis."""
    pos = start + 1
    while pos < len(text) and text[pos].isspace():
        pos += 1
    begin = pos
    if pos < len(text) and text[pos] == "<":
        begin = pos = pos + 1
        while pos < len(text) and text[pos] != ">":
            if text[pos] in "\n<":
                return None
            pos += 2 if text[pos] == "\\" else 1
        if pos >= len(text):
            return None
        target = text[begin:pos]
        pos += 1
    else:
        depth = 0
        while pos < len(text):
            char = text[pos]
            if char == "\\":
                pos += 2
                continue
            if char.isspace() or char == ")" and depth == 0:
                break
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            pos += 1
        if depth:
            return None
        target = text[begin:pos]
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos < len(text) and text[pos] in "\"'(":
        end = ")" if text[pos] == "(" else text[pos]
        pos += 1
        while pos < len(text) and text[pos] != end:
            pos += 2 if text[pos] == "\\" else 1
        if pos >= len(text):
            return None
        pos += 1
        while pos < len(text) and text[pos].isspace():
            pos += 1
    if pos >= len(text) or text[pos] != ")":
        return None
    return html.unescape(re.sub(r"\\([^\w\s])", r"\1", target)), pos + 1


def _markdown_images(text: str, document: str) -> list[tuple[str, str, int, int]]:
    """Read inline and reference images with balanced alt text; definitions use first-wins labels."""
    def label(value):
        value = html.unescape(re.sub(r"\\([^\w\s])", r"\1", value))
        return " ".join(value.split()).casefold()

    definitions = {}
    for match in REF_DEFINITION.finditer(_outside_code(document, mask_inline=False)):
        target = html.unescape(re.sub(r"\\([^\w\s])", r"\1", match.group(2) or match.group(3)))
        definitions.setdefault(label(match.group(1)), target)
    spans = _definition_spans(document)  # definition titles are never rendered as images
    sources = []
    consumed = 0
    for match in re.finditer(r"!\[", text):
        if match.start() < consumed:
            continue
        if any(a <= match.start() < b for a, b in spans):
            continue
        pos = match.start() - 1
        while pos >= 0 and text[pos] == "\\":
            pos -= 1
        if (match.start() - pos - 1) % 2:
            continue  # an escaped exclamation mark is text, not an image
        close = _closing_bracket(text, match.start() + 1)
        if close is None:
            continue
        alt = text[match.end():close]
        consumed = close + 1
        if consumed < len(text) and text[consumed] == "(":
            target = _inline_image_target(text, consumed)
            if target:
                source, consumed = target
                sources.append((alt, source, match.start(), consumed))
            continue
        # `text` masks inline code to spaces (a prefix-aligned copy): labels are matched on the written source, literal backticks included
        key = label(document[match.end():close] if len(document) >= len(text) else alt)
        if consumed < len(text) and text[consumed] == "[":
            ref_close = _closing_bracket(text, consumed)
            if ref_close is not None:
                key = label((document if len(document) >= len(text) else text)[consumed + 1:ref_close]) or key
                consumed = ref_close + 1
        if key in definitions:
            sources.append((alt, definitions[key], match.start(), consumed))
    return sources


def _images(text: str, document: str) -> list[tuple[str, str]]:
    """Read HTML and Markdown images, excluding Markdown-looking text in HTML attributes."""
    parser = _HTMLTokens(text)
    markdown = _markdown_images(text, document)
    # Angle-delimited destinations (and HTML in alt text) belong to their Markdown image,
    # while a Markdown-looking string wholly inside a real HTML tag is attribute text.
    tags = [(start, end) for start, end in parser.tags
            if not any(mstart <= start and end <= mend for _, _, mstart, mend in markdown)]
    def written_alt(alt, start):
        # `text` has Markdown code masked to spaces (same length): read code-formatted alt text from the document
        begin = start + 2
        return document[begin:begin + len(alt)] if len(document) >= begin + len(alt) else alt

    spans = _definition_spans(document)
    def in_definition(start):
        return any(a <= start < b for a, b in spans)
    result = [(written_alt(alt, start), source) for alt, source, start, end in markdown
              if not in_definition(start) and not any(tstart <= start and end <= tend for tstart, tend in tags)]
    result += [(alt, source) for alt, source, start, end in parser.images
               if (start, end) in tags and not in_definition(start)]
    return result


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
    shields = re.findall(r"img\.shields\.io/badge/([^)\"'<>\s]+)", plain)
    header_part = plain.split("\n---\n", 1)[0]
    badge_header = _outside_code(header_part)
    image_sources = [source for _, source in _images(badge_header, plain)]
    nbadges = sum(bool(SHIELDS_SRC.match(src)
                       or re.fullmatch(r"(?:\./)?docs/images/badges/[^/?#]+\.svg(?:[?#].*)?", unquote(src))
                       or re.search(r"(?:^|/)badge\.svg(?:[?#].*)?$", src)) for src in image_sources)
    if not preserve:
        from .readme import badges as derivable
        floor = min(2, len(derivable(ctx)))  # a public repo with no licence and no language derives fewer than two
        if not max(1, floor) <= nbadges <= 4:
            fails.append(f"R7 2-4 header badges required (found {nbadges})")
        elif nbadges < 2:
            warns.append(f"badges-short: {nbadges} badge (no licence or language to show yet)")
    # colours are read from parsed image destinations too, so an apostrophe or other HTML delimiter inside a Markdown URL hides nothing
    shields += [m.group(1).split("?")[0].split("#")[0] for _, src in _images(_outside_code(plain), plain)
                if (m := SHIELDS_BADGE.match(src))]
    for s in shields:
        col = re.split(r"[?)]", s.rsplit("-", 1)[-1])[0].upper()
        family_cols = {str(ctx.style.get(k) or "").upper() for k in ("badge_brand", "badge_accent")}
        if re.fullmatch(r"[0-9A-F]{6}", col) and col not in PALETTE and col not in family_cols:
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
    visible = _outside_code(plain)
    for alt, source in _images(visible, plain):
        if not alt.strip():
            fails.append(f"R7 image without alt text: {source[:40]}")
        if source:
            _local(path, source, fails, example="examples" in source)
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
