"""Markdown code spans, so marker searches skip documented examples. Stdlib only and imports nothing from the package:
`readme` (and through it `readmelint` and `footer`) and the stdlib-only `meta` find marker blocks the same way.
CommonMark escaping: the parity of the backslashes directly before a backtick decides escaping (odd = escaped,
even = real), for any number of backslashes. Block structure is decided before inline spans (CommonMark appendix A):
an inline code span never pairs across a block boundary. A fence inside a block quote or a list item is container-aware:
it opens and closes on the container's own lines, its quote and item markers are container syntax, and a line of lower
quote depth (or, in an item, a line left of the item's content column) ends it. A raw HTML block (CommonMark 4.6) is
tracked the same way: its lines are literal text, so a backtick inside one never opens a code span; types 1-5 run to
their own end condition, types 6 and 7 to the next blank line, and normal Markdown resumes after it."""
from __future__ import annotations

import bisect
import collections
import functools
import re

# Work counters for the cached scanners (layout builds on a cache miss, inline regions examined); tests read them.
WORK: collections.Counter = collections.Counter()

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


# the seven HTML block kinds (CommonMark 4.6). Types 1-5 end at a marker found on a line (the start line included);
# types 6 and 7 end at the next blank line. Type 7 is one complete open or closing tag alone on its line and cannot
# interrupt a paragraph, so an inline tag in running text (`<span>a` b</span>`) stays Markdown.
_HTML_OPEN_1_5 = (
    (re.compile(r"^ {0,3}<(?:script|pre|style|textarea)(?:[ \t>]|$)", re.I),
     re.compile(r"</(?:script|pre|style|textarea)>", re.I)),
    (re.compile(r"^ {0,3}<!--"), re.compile(r"-->")),
    (re.compile(r"^ {0,3}<\?"), re.compile(r"\?>")),
    (re.compile(r"^ {0,3}<![A-Za-z]"), re.compile(r">")),
    (re.compile(r"^ {0,3}<!\[CDATA\["), re.compile(r"\]\]>")),
)
_HTML_TYPE_6 = re.compile(r"^ {0,3}</?(?:" + "|".join(_TYPE_6) + r")(?:[ \t]|/?>|$)", re.I)
_HTML_TYPE_7 = re.compile(
    r"^ {0,3}(?:<[A-Za-z][A-Za-z0-9-]*(?:[ \t]+[A-Za-z_:][\w:.-]*(?:[ \t]*=[ \t]*(?:[^\s\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*"
    r"[ \t]*/?>|</[A-Za-z][A-Za-z0-9-]*[ \t]*>)[ \t]*$")


def _html_block(line: str):
    """None when `line` (container markers removed) does not start an HTML block; otherwise the end-condition regex of
    a type 1-5 block, or True for a type 6 or 7 block, which ends at the next blank line."""
    for opener, end in _HTML_OPEN_1_5:
        if opener.match(line):
            return end
    return True if _HTML_TYPE_6.match(line) or _HTML_TYPE_7.match(line) else None


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


def _strip_quotes(body: str, depth: int) -> str:
    """`body` with at most `depth` leading block-quote markers removed: deeper `>` characters stay content."""
    for _ in range(depth):
        m = _QUOTE.match(body)
        if not m:
            break
        body = body[m.end():]
    return body


def _containers(body: str) -> tuple[int, int, str]:
    """(block-quote depth, list-item content column, remainder): quote and item markers are peeled in any order, so
    `- ```x`, `1. ```x`, `- > ```x` and `> - ```x` all reach the same remainder. The column is the summed width of the
    item prefixes, measured on the quote-stripped line; it is 0 when the line has no item marker."""
    depth, col, rest = 0, 0, body
    while True:
        if m := _QUOTE.match(rest):
            depth += 1
        elif m := _ITEM_PREFIX.match(rest):
            col += m.end()
        else:
            return depth, col, rest
        rest = rest[m.end():]


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
def _layout(text: str) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...], tuple[int, ...],
                                tuple[tuple[int, int], ...]]:
    """(inline regions, fenced spans, continuation starts, raw HTML block spans). An inline region is a stretch in which
    one inline code span can live: a paragraph, a heading line, an HTML block start line or one table cell. A
    continuation start is the source offset of a line that continues an open paragraph or table (not the first line of
    a block, not a heading, not a line inside a fence). An HTML block span runs from its first line to just past its
    last line, excluding a terminating blank line or the line that ended its container."""
    WORK['layout_builds'] += 1
    regions: list[tuple[int, int]] = []
    fences: list[tuple[int, int]] = []
    html_blocks: list[tuple[int, int]] = []
    hstart = 0
    conts: set[int] = set()
    seg: list[tuple[int, str]] = []
    # an open fence: (fence run, block-quote depth, list-item content column (0 outside an item), item-before-quote flag)
    fence, fstart, table, para_depth, base, pos = None, 0, False, 0, 0, 0
    # content columns of the open depth-0 list items; they persist across blank lines (see the list update below)
    lists: list[int] = []
    # an open raw HTML block: (end regex, or None for a block that ends at a blank line; the same container fields)
    html = None

    def flush(rows):
        if rows:
            regions.append((rows[0][0], rows[-1][0] + len(rows[-1][1])))

    def row_cells(at, raw):
        regions.extend((a, b) for a, b in _cell_bounds(raw.rstrip("\r\n"), at) if a < b)

    for raw in re.findall(r"[^\n]*\n|[^\n]+", text):
        at, pos = pos, pos + len(raw)
        body = raw.rstrip("\r\n")
        depth, rest = _quotes(body)
        if fence is not None:
            run, fdepth, col, outer = fence
            # an item whose marker precedes its quote marker (`- > ```x`) is indented before the quote marker, so its
            # indentation is the raw one; otherwise it is the indentation left after the quote markers (`> - ```x`)
            # only the fence's own quote depth is container syntax: extra `>` characters inside it are code content
            inner = _strip_quotes(body, fdepth)
            lead = len(body) - len(body.lstrip(" ")) if outer else len(inner) - len(inner.lstrip(" "))
            if depth < fdepth or (col and depth >= fdepth and rest.strip(" \t") and lead < col):
                # the quote container of an open fence ended, or a non-blank line at the fence's quote depth OR DEEPER
                # (a new quote opened by the line) that is indented below the item content column ends the fence
                # unclosed; the line is then processed as an ordinary line (a dedented `>` begins a real quote)
                fences.append((fstart, at))
                fence = None
            else:
                # a depth-0 fence is closed by its raw line, as before; a quoted fence by the line inside its quote; an
                # item fence by the line after its content column is removed
                closer = inner if fdepth else body
                if col:
                    closer = closer[min(len(closer) - len(closer.lstrip(" ")), col):]
                close = _FENCE_CLOSE.match(closer)
                if close and close.group(1)[0] == run[0] and len(close.group(1)) >= len(run):
                    fences.append((fstart, pos))
                    fence = None
                continue
        if html is not None:
            end, hdepth, hcol, houter = html
            inner = _strip_quotes(body, hdepth)
            lead = len(body) - len(body.lstrip(" ")) if houter else len(inner) - len(inner.lstrip(" "))
            if depth < hdepth or (hcol and depth >= hdepth and rest.strip(" \t") and lead < hcol):
                # its quote or list item ended (a dedented line may open a new, deeper quote): no lazy continuation
                html = None
                html_blocks.append((hstart, at))
            elif end is None:
                if rest.strip(" \t"):
                    continue
                html = None   # a type 6 or 7 block ends at the blank line, which is then handled as usual
                html_blocks.append((hstart, at))
            else:
                if end.search(rest):
                    html = None
                    html_blocks.append((hstart, pos))
                continue
        if not rest.strip(" \t"):
            flush(seg)
            seg, table, base = [], False, 0
            continue
        if table:
            if not _interrupts(rest, depth, para_depth, 0):
                row_cells(at, raw)
                conts.add(at)
                continue
            table = False
        elif seg:
            lead = len(rest) - len(rest.lstrip(" "))
            if _is_delimiter_row(rest) and _cell_count(_quotes(seg[-1][1].rstrip("\r\n"))[1]) == _cell_count(rest):
                flush(seg[:-1])
                # the header row (the last paragraph line) starts the table, so it is not a continuation
                conts.discard(seg[-1][0])
                row_cells(*seg[-1])
                conts.add(at)
                seg, table = [], True
                continue
            if _SETEXT.match(rest[min(lead, base):]):
                flush(seg)
                seg, base = [], 0
                continue
            if not _interrupts(rest, depth, para_depth, base):
                seg.append((at, raw))
                conts.add(at)
                continue
            flush(seg)
            seg, base = [], 0
        # the opener may sit behind quote and list-item markers in any order, e.g. `- ```x` or `> - ```x`
        # CommonMark list items: a blank line keeps the item open and a dedented non-blank line ends it. A depth-0 line
        # pops the items it is dedented out of and an item marker pushes its content column; quoted lines leave `lists`.
        cdepth, col, crest = _containers(body)
        lead = len(body) - len(body.lstrip(" "))
        if cdepth == 0:
            while lists and lead < lists[-1]:
                lists.pop()
            if col:
                lists.append(col)
        opener = FENCE_OPEN.match(crest)
        # an unmarked line indented into an open item may open a fence at that item's content column
        in_item = cdepth == 0 and col == 0 and bool(lists) and lead >= lists[-1]
        item_opener = FENCE_OPEN.match(body[lists[-1]:]) if in_item else None
        if item_opener:
            fence, fstart = (item_opener.group(1), 0, lists[-1], True), at
        elif opener:
            fence, fstart = (opener.group(1), cdepth, col, bool(col) and not _QUOTE.match(body)), at
        elif _ATX_HEADING.match(rest):
            regions.append((at, pos))
        elif (kind := _html_block(crest)) is not None:
            # raw HTML: no inline region, so a backtick on these lines never pairs and the block's images stay visible
            hstart = at
            if kind is not True and kind.search(crest):
                html_blocks.append((at, pos))   # the block closes on its own opening line
            else:
                html = (None if kind is True else kind, cdepth, col, bool(col) and not _QUOTE.match(body))
        elif not _THEMATIC.match(rest):
            item = _ITEM_PREFIX.match(rest)
            seg, para_depth, base = [(at, raw)], depth, (item.end() if item else 0)
    if fence is not None:
        fences.append((fstart, len(text)))
    else:
        flush(seg)
    if html is not None:
        html_blocks.append((hstart, len(text)))
    return tuple(regions), tuple(fences), tuple(sorted(conts)), tuple(html_blocks)


@functools.lru_cache(maxsize=16)
def continuation_starts(text: str) -> frozenset[int]:
    """Source offsets of the lines that continue an open paragraph or table (every such line after the first line of
    its block, and each table row after the header). Headings, block starts and lines inside fences are not included."""
    return frozenset(_layout(text)[2])


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


@functools.lru_cache(maxsize=16)
def _region_bounds(text: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(starts, ends) of the inline regions that hold a backtick, as parallel tuples in document order. Regions are
    sorted and non-overlapping, so the first region that ends after an offset is found by bisection; a region with no
    backtick has no code span and is left out."""
    kept = [(lo, hi) for lo, hi in _layout(text)[0] if "`" in text[lo:hi]]
    return tuple(lo for lo, _ in kept), tuple(hi for _, hi in kept)


def find_inline_code(text: str, start: int = 0) -> tuple[int, int] | None:
    """(start, end) of the first CommonMark inline code span whose opening run begins at or after `start`. The span
    runs from the opening backtick run to the end of its closing run; escaping backslashes are not part of it. A
    backtick preceded by an odd number of backslashes is escaped, so its run starts one character later. The
    content must be non-empty. It may span single newlines within one paragraph, but the closing run must lie in the
    same inline region: no blank line, fence, heading, list item, new block quote, thematic break, setext underline,
    HTML block start (types 1-6) or table cell boundary in between. Fenced text holds no inline span."""
    los, his = _region_bounds(text)
    for n in range(bisect.bisect_right(his, start), len(los)):
        WORK['regions'] += 1
        lo, hi = los[n], his[n]
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


@functools.lru_cache(maxsize=16)
def fence_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Sorted (start, end) of every fenced block, including fences inside block quotes (the cached `_layout` fences)."""
    return tuple(sorted(_layout(text)[1]))


@functools.lru_cache(maxsize=16)
def html_block_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Sorted, non-overlapping (start, end) of every raw HTML block (the cached `_layout` HTML spans)."""
    return tuple(sorted(_layout(text)[3]))


@functools.lru_cache(maxsize=16)
def inline_code_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Sorted, non-overlapping inline code spans: `find_inline_code` repeated from offset 0, each call resuming at the
    end of the previous span."""
    spans: list[tuple[int, int]] = []
    at = 0
    while (span := find_inline_code(text, at)) is not None:
        spans.append(span)
        at = span[1]
    return tuple(sorted(spans))


def code_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of fenced code (``` and ~~~, an unclosed fence runs to the end) and inline code spans."""
    return sorted(fence_spans(text) + inline_code_spans(text))


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
