"""Markdown code spans, so marker searches skip documented examples. Stdlib only and imports nothing from the package:
`readme` (and through it `readmelint` and `footer`) and the stdlib-only `meta` find marker blocks the same way.
CommonMark escaping: the parity of the backslashes directly before a backtick decides escaping (odd = escaped,
even = real), for any number of backslashes. Block structure is decided before inline spans (CommonMark appendix A):
an inline code span never pairs across a block boundary."""
from __future__ import annotations

import functools
import re

# CommonMark: a backtick fence's info string has no backtick, so "```npm test``` runs" is inline code, not a fence
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,})")
_FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t\r\n]|$)")
_THEMATIC = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_BULLET_ITEM = re.compile(r"^ {0,3}[-+*][ \t]+\S")
_ORDERED_ITEM = re.compile(r"^ {0,3}(\d{1,9})[.)][ \t]+\S")
_ITEM_PREFIX = re.compile(r"^ {0,3}(?:[-+*]|\d{1,9}[.)])(?: {1,4}(?=\S)|[ \t]|$)")
_QUOTE = re.compile(r" {0,3}> ?")
_DELIMITER_CELLS = re.compile(r"\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*")
_TYPE_6 = ("address article aside base basefont blockquote body caption center col colgroup dd details dialog dir div dl "
           "dt fieldset figcaption figure footer form frame frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend "
           "li link main menu menuitem nav noframes ol optgroup option p param search section summary table tbody td "
           "tfoot th thead title tr track ul").split()
# CommonMark HTML blocks 1-6 interrupt a paragraph; type 7 (any other complete tag, like <span> or <a>) cannot
_HTML_BLOCK = re.compile(
    r"^ {0,3}(?:<(?:script|pre|style|textarea)(?:[ \t>]|$)|<!--|<\?|<![A-Za-z]|<!\[CDATA\[|</?(?:"
    + "|".join(_TYPE_6) + r")(?:[ \t]|/?>|$))", re.I)


def _run_end(text: str, i: int) -> int:
    """Index just past the backtick run that starts at `i`."""
    j = i
    while j < len(text) and text[j] == "`":
        j += 1
    return j


def _quotes(body: str) -> tuple[int, str]:
    """(block-quote depth, remainder) of a line: the `>` markers are container syntax, not paragraph content."""
    depth = 0
    while m := _QUOTE.match(body):
        depth += 1
        body = body[m.end():]
    return depth, body


def _unescaped_pipe(row: str, i: int) -> bool:
    slashes = 0
    while i - slashes > 0 and row[i - slashes - 1] == "\\":
        slashes += 1
    return not slashes % 2


def _cell_bounds(row: str, base: int = 0) -> list[tuple[int, int]]:
    """(start, end) of each table cell of `row`, split at pipes that are not backslash-escaped."""
    out, last = [], 0
    for i, ch in enumerate(row):
        if ch == "|" and _unescaped_pipe(row, i):
            out.append((base + last, base + i))
            last = i + 1
    out.append((base + last, base + len(row)))
    return out


def _cell_count(rest: str) -> int:
    row = rest.strip()
    row = row[1:] if row.startswith("|") else row
    if row.endswith("|") and _unescaped_pipe(row, len(row) - 1):
        row = row[:-1]
    return len(_cell_bounds(row))


def _is_delimiter_row(rest: str) -> bool:
    row = rest.strip()
    if "|" not in row:
        return False
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") else row
    return bool(_DELIMITER_CELLS.fullmatch(row))


def _interrupts(rest: str, depth: int, para_depth: int, base: int) -> bool:
    """True when a line (block-quote markers removed) starts a block that ends the open paragraph. A continued quote
    line (same depth) and a lazy continuation (lower depth) stay in the paragraph, as GitHub renders them; a deeper
    quote, a fence, an ATX heading, a thematic break, a list item and an HTML block of type 1-6 end it. `base` is the
    content column of the list item holding the paragraph, so an item nested under it is still seen."""
    if depth > para_depth:
        return True
    lead = len(rest) - len(rest.lstrip(" "))
    line = rest[min(lead, base):]
    if FENCE_OPEN.match(line) or _ATX_HEADING.match(line) or _THEMATIC.match(line) or _HTML_BLOCK.match(line):
        return True
    if _BULLET_ITEM.match(line):
        return True
    ordered = _ORDERED_ITEM.match(line)
    # only "1." may interrupt a paragraph, but a sibling item of the enclosing list always ends the item
    return bool(ordered and (ordered.group(1) == "1" or (base and lead < base)))


@functools.lru_cache(maxsize=16)
def _layout(text: str) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    """(inline regions, fenced spans). An inline region is a stretch in which one inline code span can live: a
    paragraph, a heading line, an HTML block start line or one table cell."""
    regions: list[tuple[int, int]] = []
    fences: list[tuple[int, int]] = []
    seg: list[tuple[int, str]] = []
    fence, fstart, table, para_depth, base, pos = None, 0, False, 0, 0, 0

    def flush(rows):
        if rows:
            regions.append((rows[0][0], rows[-1][0] + len(rows[-1][1])))

    def row_cells(at, raw):
        regions.extend((a, b) for a, b in _cell_bounds(raw.rstrip("\r\n"), at) if a < b)

    for raw in re.findall(r"[^\n]*\n|[^\n]+", text):
        at, pos = pos, pos + len(raw)
        body = raw.rstrip("\r\n")
        if fence is not None:
            close = _FENCE_CLOSE.match(body)
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= len(fence):
                fences.append((fstart, pos))
                fence = None
            continue
        depth, rest = _quotes(body)
        if not rest.strip(" \t"):
            flush(seg)
            seg, table, base = [], False, 0
            continue
        if table:
            if not _interrupts(rest, depth, para_depth, 0):
                row_cells(at, raw)
                continue
            table = False
        elif seg:
            lead = len(rest) - len(rest.lstrip(" "))
            if _is_delimiter_row(rest) and _cell_count(_quotes(seg[-1][1].rstrip("\r\n"))[1]) == _cell_count(rest):
                flush(seg[:-1])
                row_cells(*seg[-1])
                seg, table = [], True
                continue
            if _SETEXT.match(rest[min(lead, base):]):
                flush(seg)
                seg, base = [], 0
                continue
            if not _interrupts(rest, depth, para_depth, base):
                seg.append((at, raw))
                continue
            flush(seg)
            seg, base = [], 0
        opener = FENCE_OPEN.match(body)
        if opener:
            fence, fstart = opener.group(1), at
        elif _ATX_HEADING.match(rest) or _HTML_BLOCK.match(rest):
            regions.append((at, pos))
        elif not _THEMATIC.match(rest):
            item = _ITEM_PREFIX.match(rest)
            seg, para_depth, base = [(at, raw)], depth, (item.end() if item else 0)
    if fence is not None:
        fences.append((fstart, len(text)))
    else:
        flush(seg)
    return tuple(regions), tuple(fences)


def _closing_run(text: str, pos: int, k: int, limit: int) -> tuple[int, int] | None:
    """First maximal backtick run of exactly `k` backticks at or after `pos` and before `limit`."""
    while True:
        p = text.find("`", pos, limit)
        if p < 0:
            return None
        q = _run_end(text, p)
        if q - p == k:
            return p, q
        pos = q


def find_inline_code(text: str, start: int = 0) -> tuple[int, int] | None:
    """(start, end) of the first CommonMark inline code span whose opening run begins at or after `start`. The span
    runs from the opening backtick run to the end of its closing run; escaping backslashes are not part of it. A
    backtick preceded by an odd number of backslashes is escaped, so its run starts one character later. The
    content must be non-empty. It may span single newlines within one paragraph, but the closing run must lie in the
    same inline region: no blank line, fence, heading, list item, new block quote, thematic break, setext underline,
    HTML block start (types 1-6) or table cell boundary in between. Fenced text holds no inline span."""
    for lo, hi in _layout(text)[0]:
        if hi <= start:
            continue
        i = max(start, lo)
        while (i := text.find("`", i, hi)) >= 0:
            if i == start and i > 0 and text[i - 1] == "`":
                # `start` landed inside a run that began earlier, so that run is not an opener at or after `start`
                i = _run_end(text, i)
                continue
            j = _run_end(text, i)
            backslashes = 0
            while i - backslashes > 0 and text[i - backslashes - 1] == "\\":
                backslashes += 1
            if backslashes % 2:
                if i + 1 == j:
                    i = j
                    continue
                run_start = i + 1
            else:
                run_start = i
            closer = _closing_run(text, j, j - run_start, hi)
            if closer is not None:
                return run_start, closer[1]
            i = j
    return None


def code_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of fenced code (``` and ~~~, an unclosed fence runs to the end) and inline code spans."""
    spans = list(_layout(text)[1])
    at = 0
    while (span := find_inline_code(text, at)) is not None:
        spans.append(span)
        at = span[1]
    return sorted(spans)


def masked(text: str) -> str:
    """`text` with every code span blanked (same length, newlines kept), so marker searches skip documented examples
    and their offsets still index the original."""
    out = list(text)
    for a, b in code_spans(text):
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = "\x00"
    return "".join(out)


def find_blocks(pattern: re.Pattern, text: str) -> list[re.Match]:
    """Matches of `pattern` outside code, taken on the original text (group contents byte-identical)."""
    found = (pattern.fullmatch(text, m.start(), m.end()) for m in pattern.finditer(masked(text)))
    return [m for m in found if m]
