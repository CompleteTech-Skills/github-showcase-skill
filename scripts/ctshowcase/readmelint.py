"""README lint: R7 + decision 13 (banner first, plain <img>) + decision 18 (footer last, exact) (spec A6.11)."""
from __future__ import annotations

import bisect
import functools
import html
import re
from pathlib import Path
from urllib.parse import unquote

from . import footer as footermod
from . import mdcode
from .mdcode import find_inline_code
from .context import RepoContext
from .detect import standard
from .readme import BANNER_BLOCK, EMOJI, MARK, is_footer_like, masked, normalize_text, nav_first, preserved, split_sections

IMG_MD = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)")
IMG_HTML = re.compile(r"<img\b([^>]*)>", re.I)
PALETTE = {"1E3A8A", "005ADD", "067647", "64748B", "E551BA", "F386A1", "1E1E1E"}
REF_DEFINITION = re.compile(
    r"^\x00* {0,3}\[((?:\\.|[^\]\\\n])+)\]:[ \t\x00]*(?:\n[ \t\x00]*)?(?:<([^<>\n]+)>|([^\s\x00]+?))"
    r"(?:(?:[ \t]+|[ \t\x00]*\n[ \t\x00]*)(?:\"(?:\\.|[^\"\\\n]|\n(?![ \t\x00]*\n))*\"|'(?:\\.|[^'\\\n]|\n(?![ \t\x00]*\n))*'"
    r"|\((?:\\.|[^()\\\n]|\n(?![ \t\x00]*\n))*\)))?[ \t]*$", re.M)
# a title may span lines but never a blank one; NUL stands in for a blanked quote or list-item prefix (see below)
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


def _search_unescaped(pattern, text: str, pos: int, html_spans=None):
    """First match at or after `pos` whose opening character is not backslash-escaped. A match starting inside one of
    `html_spans` (raw HTML block spans) is never escaped: backslashes are literal there."""
    def escaped(start):
        return _escaped(text, start) and not (html_spans is not None and _span_at(html_spans, start) is not None)

    match = pattern.search(text, pos)
    while match and escaped(match.start()):
        match = pattern.search(text, match.start() + 1)
    return match


def _span_at(spans, index: int, strict: bool = False):
    """The (a, b) span of a sorted, non-overlapping sequence that holds `index` (a <= index < b; strict: a < index < b),
    found by bisection so membership is a lookup, not a walk from offset 0."""
    mdcode.WORK['span_checks'] += 1
    n = bisect.bisect_left(spans, (index, -1) if strict else (index + 1, -1)) - 1
    if n >= 0 and (spans[n][0] < index < spans[n][1] if strict else spans[n][0] <= index < spans[n][1]):
        return spans[n]
    return None


def _in_inline_code(text: str, index: int) -> bool:
    """True when `index` lies strictly inside a non-fenced inline code span (a < index < b for a span (a, b))."""
    return _span_at(mdcode.inline_code_spans(text), index, strict=True) is not None


def _in_html_block(text: str, index: int) -> bool:
    """True when `index` lies inside a raw HTML block (CommonMark HTML block extent): there a backslash is literal text,
    and the block's lines are not Markdown reference definitions. The spans are cached per document by `mdcode`."""
    return _span_at(mdcode.html_block_spans(text), index) is not None


def _badge_colour(path: str) -> str:
    """Upper-cased colour of a Shields badge path (the text after `/badge/`): its last segment, with the query and
    fragment removed. Shields escapes a literal dash as a pair `--`; a lone `-` is the structural separator. The scan
    runs left to right, so `type-example---FF0000` reads as `type`, `example-`, `FF0000`. Labels and messages may hold
    apostrophes or hex-looking text; only the final segment is the colour."""
    path = path.split("#", 1)[0].split("?", 1)[0]  # literal delimiters only: an encoded %23 or %3F belongs to a label
    text = unquote(path)
    segments, current, i = [], [], 0
    while i < len(text):
        if text[i] == "-" and text[i + 1:i + 2] == "-":  # an escaped literal dash
            current.append("-")
            i += 2
        elif text[i] == "-":  # the structural separator
            segments.append("".join(current))
            current = []
            i += 1
        else:
            current.append(text[i])
            i += 1
    segments.append("".join(current))
    return segments[-1].upper()


def _definition_candidates(document: str) -> str:
    """The document with fenced blocks and HTML comments blanked (same length), the text in which a definition is read."""
    out = list(document)
    for a, b in mdcode.fence_spans(document):
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = " "
    # raw HTML block text is literal HTML, not Markdown: a `[label]: dest` line inside it defines nothing. The block's
    # extent ends at its end condition, so a definition after the block still counts.
    for a, b in mdcode.html_block_spans(document):
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = " "
    fences = mdcode.fence_spans(document)
    pos = 0
    while (m := HTML_COMMENT.search(document, pos)):
        start = m.start()
        # an opener that is escaped, inside inline code or inside a fence is text: the search resumes one character on,
        # so a code-span `<!--` never consumes text up to a later real `-->`
        if _escaped(document, start) or _in_inline_code(document, start) or _span_at(fences, start) is not None:
            pos = start + 1
            continue
        for i in range(*m.span()):
            if out[i] != "\n":
                out[i] = " "
        pos = m.end()
    # Quote and list-item markers are container syntax: a definition inside `> ` or `- ` is still a definition and is
    # global to the document. Each peeled prefix becomes NUL (same length), so offsets are unchanged and the pattern
    # sees an ordinary line start. Fenced lines are already blanked; blanked comment text has no prefix to peel.
    pos = 0
    for raw in re.findall(r"[^\n]*\n|[^\n]+", document):
        body = raw.rstrip("\r\n")
        line = "".join(out[pos:pos + len(body)])
        prefix = len(line) - len(mdcode._containers(line)[2])
        out[pos:pos + prefix] = ["\x00"] * prefix
        pos += len(raw)
    return "".join(out)


@functools.lru_cache(maxsize=16)
def _definitions(document: str) -> tuple:
    """Live reference definitions, as regex matches over the document-length candidate text. A definition cannot
    interrupt a paragraph (CommonMark), so a definition-like line that continues a paragraph is text; only a line that
    starts a block counts, plus a definition directly after another live definition. Definitions are decided before
    inline code, so a backtick in a definition destination pairs with nothing. Computed once per document."""
    continuation = mdcode.continuation_starts(document)
    live: list = []
    for match in REF_DEFINITION.finditer(_definition_candidates(document)):
        if match.start() in continuation and not (live and live[-1].end() + 1 == match.start()):
            continue
        live.append(match)
    return tuple(live)


@functools.lru_cache(maxsize=16)
def _definition_spans(document: str) -> tuple[tuple[int, int], ...]:
    """Spans of complete reference definitions (label, destination and title): their text is not Markdown. Computed
    once per document; the spans are sorted and never overlap."""
    return tuple((m.start(), m.end()) for m in _definitions(document))


class _HTMLTokens:
    """Strict CommonMark open tags (never raises): spans let Markdown parsing respect attribute boundaries."""
    def __init__(self, text):
        self.text = text
        self.tags = []
        self.images = []
        for match in HTML_OPEN_TAG.finditer(text):
            start, end = match.span()
            if _escaped(text, start) and not _in_html_block(text, start):  # raw HTML: a backslash is literal
                continue
            self.tags.append((start, end))
            if match.group(1).lower() == "img":
                first = {}
                for name, value in HTML_ATTR.findall(match.group(2)):
                    value = value[1:-1] if value[:1] in ("'", '"') and value else value
                    first.setdefault(name.lower(), html.unescape(value))
                self.images.append((first.get("alt") or "", first.get("src") or "", start, end))


def _fence_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Fenced code blocks, including fences inside block quotes (cached per document by `mdcode`)."""
    return mdcode.fence_spans(text)


@functools.lru_cache(maxsize=16)
def _outside_code(text: str, mask_inline: bool = True) -> str:
    """Mask Markdown code and comments without reading literal backticks in HTML attributes as code.
    Constructs are taken left to right, and inline code is looked for again after every HTML tag or comment, so a
    backtick inside an attribute or comment is literal and the next real code span still opens (CommonMark).
    `mask_inline=False` still lets inline code win precedence but leaves its characters readable (reference labels).
    The result has the same length (and newline positions) as `text`."""
    fences = _fence_spans(text)
    definitions = _definition_spans(text)  # decided before inline code: a definition destination's backtick is literal
    labels = _reference_label_spans(text)  # resolved full-reference labels: their backticks are literal too
    html_spans = mdcode.html_block_spans(text)  # raw HTML blocks: tags there are never escaped by a backslash
    out, pos = list(text), 0
    tag = comment = inline = dest = None

    def blank(a, b):
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = " "

    def next_inline(start):
        while True:
            found = find_inline_code(text, start)  # (start, end) or None
            if not found:
                return False
            inside = _span_at(fences, found[0])
            if inside is None:
                return found
            start = inside[1]

    def next_destination(start):
        """(start, end) of the first inline link or image destination `](...)` from `start`: its text is literal, so a
        backtick inside it opens no code span (CommonMark parses the destination before looking for later code)."""
        while match := _search_unescaped(re.compile(r"\]\("), text, start):
            if not _has_link_opener(text, match.start()):
                start = match.start() + 1
                continue
            target = _inline_image_target(text, match.end() - 1)
            if target:
                return match.start(), target[1]
            start = match.start() + 1
        return False

    while pos < len(text):
        if inline is not False and (inline is None or inline[0] < pos):
            inline = next_inline(pos)
        if dest is not False and (dest is None or dest[0] < pos):
            dest = next_destination(pos)
        if tag is not False and (tag is None or tag.start() < pos):
            tag = _search_unescaped(HTML_OPEN_TAG, text, pos, html_spans) or False
        if comment is not False and (comment is None or comment.start() < pos):
            comment = _search_unescaped(HTML_COMMENT, text, pos, html_spans) or False
        n = bisect.bisect_left(fences, (pos, -1))
        fence = fences[n] if n < len(fences) else None
        d = bisect.bisect_left(definitions, (pos, -1))
        definition = definitions[d] if d < len(definitions) else None
        lb = bisect.bisect_left(labels, (pos, -1))
        label_span = labels[lb] if lb < len(labels) else None
        code = min([c for c in ((inline if inline else None), fence) if c], default=None)
        found = [m for m in (tag, comment) if m]
        nxt = min(found, key=lambda m: m.start()) if found else None
        if definition and all(definition[0] <= other for other in [c[0] for c in (code, dest) if c]
                              + [m.start() for m in found]):
            pos = definition[1]
        elif label_span and all(label_span[0] <= other for other in [c[0] for c in (code, dest) if c]
                                + [m.start() for m in found]):
            pos = label_span[1]  # a resolved reference label is literal text: its backticks open no code span
        elif dest and all(dest[0] < other for other in [c[0] for c in (code,) if c] + [m.start() for m in found]):
            pos = dest[1]
        elif code and (nxt is None or code[0] <= nxt.start()):
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


# work counter of the opener pass: one per position advanced (an inert-region skip counts one) and one per call of
# `_has_link_opener`; the regression test reads and resets it
_OPENER_STEPS = 0
# work counter of destination parsing (`_inline_image_target`): one per raw or angle destination character read, per
# whitespace character skipped and per title lookup; the regression test reads and resets it
_DEST_STEPS = 0

# block starts at a line start after up to three spaces of indent (CommonMark 4.1 ATX headings, 4.2 thematic breaks,
# 5.2 list items, which may interrupt a paragraph); blockquotes are tested apart because a quote line continues a quote
_BLOCK_START_LINE = re.compile(
    r" {0,3}(?:#{1,6}(?:[ \t]|$)|(?:[-+*]|\d{1,9}[.)])(?:[ \t]|$)"
    r"|(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$)", re.M)
# single-line blocks (headings and thematic breaks): the line itself is the whole block
_ATX_OR_THEMATIC_LINE = re.compile(
    r" {0,3}(?:#{1,6}(?:[ \t]|$)|(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$)", re.M)
_BLOCKQUOTE_LINE = re.compile(r" {0,3}>")
# the underline of a setext heading: `===` or `---` after paragraph text (a bare `---` line is a thematic break above)
_SETEXT_UNDERLINE = re.compile(r" {0,3}(?:=+|-+)[ \t]*$", re.M)


def _block_boundary(text: str, newline: int, fences: tuple[tuple[int, int], ...]) -> bool:
    """True when the newline at `newline` (plain text, outside every inert region) ends a link-opener span even though
    no blank line follows: the line that just ended is a heading, a thematic break or the underline of a setext heading,
    or the next line starts a heading, list item, thematic break, fence, or a blockquote that does not continue a
    blockquote line. Each check reads at most the two adjacent lines (the previous line is found backwards only as far
    as its own start), so the cost is linear in the length of the lines involved."""
    ended = text.rfind("\n", 0, newline) + 1  # start of the line that just ended
    if _ATX_OR_THEMATIC_LINE.match(text, ended):
        return True
    if ended > 0 and _SETEXT_UNDERLINE.match(text, ended):  # an underline makes a heading only after paragraph text
        previous = text.rfind("\n", 0, ended - 1) + 1
        if text[previous:ended - 1].strip():
            return True
    nxt = newline + 1
    if _BLOCK_START_LINE.match(text, nxt):
        return True
    k = nxt  # a fence opener is found at its line start after up to three spaces of indent
    while k < len(text) and k - nxt < 3 and text[k] == " ":
        k += 1
    at = bisect.bisect_left(fences, (k, -1))
    if at < len(fences) and fences[at][0] == k:
        return True
    return bool(_BLOCKQUOTE_LINE.match(text, nxt)) and not _BLOCKQUOTE_LINE.match(text, ended)


_BRACKET = re.compile(r"[][]")


def _next_unescaped_bracket(text: str, start: int, end: int) -> int:
    """Index of the first unescaped `[` or `]` in text[start:end], or -1. The scan stops at that bracket, so a label
    scan costs the length of the text it reads, and the scans of distinct closers do not overlap."""
    for match in _BRACKET.finditer(text, start, end):
        if not _escaped(text, match.start()):
            return match.start()
    return -1


def _reference_form(text: str, open_idx: int, close: int, limit: int, keys: set) -> tuple[int | None, int | None] | None:
    """Reference-style link after the `]` at `close` whose `[` is at `open_idx`, or None. Returns (jump, label_close):
    `jump` is the index past the label's closing bracket (None for a shortcut, which does not jump) and `label_close`
    is that bracket's index (None for a shortcut). The label must be plain text before
    `limit`, the next inert region, so a jump never skips into one. Link text holding an unescaped bracket is no label.
    An inline `(dest)` is decided by the caller first, so a `(` here means the closer is not a shortcut."""
    if _next_unescaped_bracket(text, open_idx + 1, close) != -1:
        return None
    if text[close + 1:close + 2] == "[":
        label_end = _next_unescaped_bracket(text, close + 2, limit)
        if label_end == -1:
            return None
        if label_end == close + 2 and text[label_end] == "]":  # collapsed `[text][]`
            if _label_key(text[open_idx + 1:close]) in keys:
                return label_end + 1, label_end
            return None
        if text[label_end] == "]" and _label_key(text[close + 2:label_end]) in keys:  # full `[text][label]`
            return label_end + 1, label_end
        return None
    if text[close + 1:close + 2] == "(":  # not a shortcut when a destination follows
        return None
    if _label_key(text[open_idx + 1:close]) in keys:  # shortcut `[text]`
        return None, None
    return None


@functools.lru_cache(maxsize=16)
def _active_openers(text: str) -> frozenset[int]:
    """Indices of every `]` that closes a link text, i.e. has a matching ACTIVE `[` before it in the same paragraph.
    One left-to-right pass keeps a stack of active `[` indices. Fenced code, inline code, HTML comments and HTML open
    tags (attribute values included) are inert, so a bracket inside them is text: it neither opens nor closes a link.
    An unescaped `]` that pops an opener and is directly followed by a destination `(...)` skips that destination,
    which is literal (a backtick in it opens no code span). A blank line clears the stack, and so does a block
    boundary: a heading, list item, thematic break, fence or blockquote start (see `_block_boundary`), and the line
    after a heading or thematic break, and the underline of a setext heading. A quote line continues an open quote,
    so a `[` and its `](` in one blockquote still pair. Raw HTML blocks (`mdcode.html_block_spans`) are inert and are block boundaries: no `[` inside one opens
    a link, and the stack is cleared entering and leaving it. Completing an inline link deactivates every earlier LINK
    opener in the stack (CommonMark: links may not contain links), while earlier IMAGE openers stay active; a `barrier`
    marks the stack depth below which link openers are inactive, so that deactivation is O(1). Reference-style links
    `[x][ref]`, `[x][]` and `[x]` deactivate earlier link openers too when the label resolves to a live definition
    (`_reference_form`); an inline `(dest)` is tried first. Inert regions are found
    by cached lookups as in `_outside_code`, so the pass is linear. Offsets are the source offsets. It never calls
    `_outside_code`."""
    global _OPENER_STEPS
    fences = _fence_spans(text)
    html_spans = mdcode.html_block_spans(text)
    keys = {_label_key(m.group(1)) for m in _definitions(text)}  # live definition labels, computed once per call
    opened: set[int] = set()
    stack: list[tuple[int, bool]] = []  # (index of `[`, whether it opens an image `![`)
    barrier = 0  # stack positions below this hold inactive link openers (a link was completed after them)
    inline = tag = comment = None  # cached next starts: None = not searched yet, False = none left
    n, pos = len(text), 0

    def next_inline(start):
        while True:
            found = find_inline_code(text, start)  # (start, end) or None
            if not found:
                return False
            inside = _span_at(fences, found[0])
            if inside is None:
                return found
            start = inside[1]

    while pos < n:
        fence = _span_at(fences, pos)
        if fence is not None:  # fenced code is inert and a block boundary: no opener before it can match a closer after it
            _OPENER_STEPS += 1
            pos = fence[1]
            stack.clear()
            barrier = 0
            continue
        html_block = _span_at(html_spans, pos)
        if html_block is not None:  # a raw HTML block is inert text and a block boundary, like fenced code
            _OPENER_STEPS += 1
            pos = html_block[1]
            stack.clear()
            barrier = 0
            continue
        if inline is not False and (inline is None or inline[0] < pos):
            inline = next_inline(pos)
        if tag is not False and (tag is None or tag.start() < pos):
            tag = _search_unescaped(HTML_OPEN_TAG, text, pos, html_spans) or False
        if comment is not False and (comment is None or comment.start() < pos):
            comment = _search_unescaped(HTML_COMMENT, text, pos, html_spans) or False
        k = bisect.bisect_left(fences, (pos, -1))
        regions = []
        if inline:
            regions.append(inline)
        if tag:
            regions.append(tag.span())
        if comment:
            regions.append(comment.span())
        if k < len(fences):
            regions.append(fences[k])
        h = bisect.bisect_left(html_spans, (pos, -1))
        if h < len(html_spans):
            regions.append(html_spans[h])
        region = min(regions) if regions else None  # the next inert region at or after `pos`
        limit = region[0] if region else n
        jump = None
        i = pos
        while i < limit:  # plain text between inert regions: brackets are read one position at a time
            _OPENER_STEPS += 1
            char = text[i]
            if char == "[" and not _escaped(text, i):
                stack.append((i, i > 0 and text[i - 1] == "!" and not _escaped(text, i - 1)))
            elif char == "]" and stack and not _escaped(text, i):
                # the top opener is active unless a link was completed after it (images stay active)
                active = stack[-1][1] or len(stack) - 1 >= barrier
                open_idx, is_image = stack.pop()
                if len(stack) < barrier:
                    barrier = len(stack)
                if active:
                    opened.add(i)
                    if text[i + 1:i + 2] == "(" and (target := _inline_image_target(text, i + 1)):
                        jump = target[1]  # the destination of a completed link is literal text
                        if not is_image:  # completing a link deactivates every earlier link opener
                            barrier = len(stack)
                        break
                    form = _reference_form(text, open_idx, i, limit, keys)
                    if form is not None:  # a reference-style link completes like an inline one
                        jump_to, label_close = form
                        if label_close is not None:  # the label's `]` is marked as the scan marks any active `]`
                            opened.add(label_close)
                        if not is_image:
                            barrier = len(stack)
                        if jump_to is not None:  # skip the label so its `[` never opens a link
                            jump = jump_to
                            break
            elif char == "\n":
                j = i + 1
                while j < n and text[j] in " \t\r":
                    j += 1
                if j < n and text[j] == "\n":  # a blank line is a paragraph boundary
                    stack.clear()
                    barrier = 0
                elif _block_boundary(text, i, fences):  # so is the start of a block without a blank line
                    stack.clear()
                    barrier = 0
            i += 1
        if jump is not None:
            pos = jump
        elif region is None:
            break
        else:
            _OPENER_STEPS += 1
            if k < len(fences) and region == fences[k]:  # a fence skipped as a region is a block boundary too
                stack.clear()
                barrier = 0
            elif h < len(html_spans) and region == html_spans[h]:  # so is a raw HTML block skipped as a region
                stack.clear()
                barrier = 0
            pos = region[1]
    return frozenset(opened)


def _has_link_opener(text: str, close: int) -> bool:
    """True when the `]` at index `close` closes a link text: it is in the set of active closing brackets of `text`
    (see `_active_openers`). After the cached pass each call is one set lookup."""
    global _OPENER_STEPS
    _OPENER_STEPS += 1
    return close in _active_openers(text)


def _label_key(value: str) -> str:
    """Normalised reference label: backslash escapes and entities resolved, whitespace collapsed, case folded."""
    value = html.unescape(re.sub(r"\\([^\w\s])", r"\1", value))
    return " ".join(value.split()).casefold()


@functools.lru_cache(maxsize=16)
def _reference_label_spans(document: str) -> tuple[tuple[int, int], ...]:
    """Label text of each resolved full reference (`[text][label]`): the characters between the brackets of the second
    pair. Only a label that names a live definition is a reference, so its backticks are literal; an unresolved label
    stays readable for inline code. Junctions inside fences or definitions are text. Computed once per document;
    the spans are sorted and never overlap."""
    keys = {_label_key(m.group(1)) for m in _definitions(document)}
    fences = mdcode.fence_spans(document)
    definitions = _definition_spans(document)
    spans = []
    for junction in re.finditer(r"\]\[", document):
        at = junction.start()
        if _escaped(document, at) or _span_at(fences, at) is not None or _span_at(definitions, at) is not None:
            continue
        if at not in _active_openers(document):
            continue  # the first `]` closes no link text (an orphan junction): `[label]` is a shortcut, not a full reference
        open_ = at + 1
        close = _closing_bracket(document, open_)
        if close is None:
            continue
        label = document[open_ + 1:close]
        if not label.strip() or re.search(r"\n[ \t]*\n", label):
            continue  # an empty label or one spanning a blank line is not a reference label
        first_fence = bisect.bisect_left(fences, (open_ + 1, -1))
        if first_fence < len(fences) and fences[first_fence][0] < close:
            continue  # a fenced block cannot sit inside a link label
        if _label_key(label) in keys:
            spans.append((open_ + 1, close))
    return tuple(spans)


@functools.lru_cache(maxsize=16)
def _title_ends(text: str) -> dict[str, tuple[int, ...]]:
    """Sorted positions of the unescaped `"`, `'` and `)` in `text`, from one linear pass. An occurrence is escaped when
    an odd number of backslashes directly precedes it: the parity the destination scanner's skip-two loop produces."""
    found: dict[str, list[int]] = {'"': [], "'": [], ")": []}
    backslashes = 0  # length of the run of backslashes directly before the current position
    for index, char in enumerate(text):
        if char == "\\":
            backslashes += 1
            continue
        if char in found and backslashes % 2 == 0:
            found[char].append(index)
        backslashes = 0
    return {char: tuple(positions) for char, positions in found.items()}


def _inline_image_target(text: str, start: int) -> tuple[str, int] | None:
    """Read a Markdown destination and optional title after its opening parenthesis. Destination nesting deeper than
    32 parentheses is no link (CommonMark's limit), which bounds each call and keeps the opener pass linear."""
    global _DEST_STEPS
    pos = start + 1
    while pos < len(text) and text[pos].isspace():
        _DEST_STEPS += 1
        pos += 1
    begin = pos
    if pos < len(text) and text[pos] == "<":
        begin = pos = pos + 1
        while pos < len(text) and text[pos] != ">":
            _DEST_STEPS += 1
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
            _DEST_STEPS += 1
            char = text[pos]
            if char == "\\":
                pos += 2
                continue
            if char.isspace() or char == ")" and depth == 0:
                break
            if char == "(":
                depth += 1
                if depth > 32:  # CommonMark's nesting limit: a deeper destination is no link
                    return None
            elif char == ")":
                depth -= 1
            pos += 1
        if depth:
            return None
        target = text[begin:pos]
    while pos < len(text) and text[pos].isspace():
        _DEST_STEPS += 1
        pos += 1
    if pos < len(text) and text[pos] in "\"'(":
        end = ")" if text[pos] == "(" else text[pos]
        pos += 1
        _DEST_STEPS += 1  # one title lookup, not one step per character it passes over
        ends = _title_ends(text)[end]
        at = bisect.bisect_left(ends, pos)  # the first unescaped end character at or after the title start
        if at == len(ends):
            return None
        pos = ends[at] + 1
        while pos < len(text) and text[pos].isspace():
            _DEST_STEPS += 1
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
    for match in _definitions(document):
        target = html.unescape(re.sub(r"\\([^\w\s])", r"\1", match.group(2) or match.group(3)))
        definitions.setdefault(label(match.group(1)), target)
    spans = _definition_spans(document)  # definition titles are never rendered as images
    html_spans = mdcode.html_block_spans(document)  # raw HTML blocks are literal: Markdown image syntax there is text
    sources = []
    consumed = 0
    for match in re.finditer(r"!\[", text):
        if match.start() < consumed:
            continue
        if _span_at(spans, match.start()) or _span_at(html_spans, match.start()):
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
        after = close + 1  # tentative: `consumed` moves only once the image resolves, so a failed outer keeps its nested images
        if after < len(text) and text[after] == "(":
            # Destinations are read from the written document: the masked copy blanks literal backticks in filenames.
            target = _inline_image_target(document if len(document) >= len(text) else text, after)
            if target:
                source, end = target
                sources.append((alt, source, match.start(), end))
                consumed = end
                continue
            # not an inline destination (for example, a space-containing label): try a shortcut reference
        # `text` masks inline code to spaces (a prefix-aligned copy): labels are matched on the written source, literal backticks included
        key = label(document[match.end():close] if len(document) >= len(text) else alt)
        if after < len(text) and text[after] == "[":
            ref_close = _closing_bracket(text, after)
            if ref_close is not None:
                key = label((document if len(document) >= len(text) else text)[after + 1:ref_close]) or key
                after = ref_close + 1
        if key in definitions:
            sources.append((alt, definitions[key], match.start(), after))
            consumed = after
    return sources


def _images(text: str, document: str) -> list[tuple[str, str]]:
    """Read HTML and Markdown images, excluding Markdown-looking text in HTML attributes."""
    parser = _HTMLTokens(text)
    markdown = _markdown_images(text, document)
    # Angle-delimited destinations (and HTML in alt text) belong to their Markdown image,
    # while a Markdown-looking string wholly inside a real HTML tag is attribute text.
    # Both comparisons are interval lookups over sorted, non-overlapping spans (bisection), never a cross product.
    image_spans = [(mstart, mend) for _, _, mstart, mend in markdown]

    def inside(spans, start, end):
        span = _span_at(spans, start)
        return span is not None and end <= span[1]

    tags = [(start, end) for start, end in parser.tags if not inside(image_spans, start, end)]
    def written_alt(alt, start):
        # `text` has Markdown code masked to spaces (same length): read code-formatted alt text from the document
        begin = start + 2
        return document[begin:begin + len(alt)] if len(document) >= begin + len(alt) else alt

    spans = _definition_spans(document)
    def in_definition(start):
        return _span_at(spans, start) is not None
    result = [(written_alt(alt, start), source) for alt, source, start, end in markdown
              if not in_definition(start) and not inside(tags, start, end)]
    kept = set(tags)
    result += [(alt, source) for alt, source, start, end in parser.images
               if (start, end) in kept and not in_definition(start)]
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
    shields: list[str] = []
    header_part = plain.split("\n---\n", 1)[0]
    # masked over the whole document, then cut to the header: a reference label is resolved by a definition below it
    badge_header = _outside_code(plain)[:len(header_part)]
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
    # colours come only from complete parsed image destinations, so an apostrophe or other HTML delimiter inside a Markdown URL hides nothing
    shields += [m.group(1) for _, src in _images(_outside_code(plain), plain)
                if (m := SHIELDS_BADGE.match(src))]
    shields = list(dict.fromkeys(shields))
    for s in shields:
        col = _badge_colour(s)
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
