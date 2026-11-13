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
_ORDERED_ITEM = re.compile(r"^ {0,3}([0-9]{1,9})[.)][ \t]+\S")
_ITEM_PREFIX = re.compile(r"^ {0,3}(?:[-+*]|[0-9]{1,9}[.)])(?: {1,4}(?=\S)|[ \t]|$)")
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


def block_line(body: str) -> str:
    """Block syntax in four-column tab stops, before any container is peeled.

    Callers retain the original text for offsets and literal inline content.
    """
    return body.expandtabs(4)


def source_prefix_chars(body: str, columns: int) -> int:
    """Source characters covering a visual prefix (including a partially used tab)."""
    column = 0
    for index, char in enumerate(body):
        if column >= columns:
            return index
        column = (column // 4 + 1) * 4 if char == "\t" else column + 1
    return len(body)


def _strip_quotes(body: str, depth: int) -> str:
    """`body` with at most `depth` leading block-quote markers removed: deeper `>` characters stay content."""
    for _ in range(depth):
        m = _QUOTE.match(body)
        if not m:
            break
        body = body[m.end():]
    return body


def _indent_columns(body: str, start: int = 0) -> int:
    """Leading indentation width; tabs use four-column stops on the original line.

    `start` includes stripped quote markers, so a tab after `> ` supplies two
    columns inside the quote, rather than incorrectly restarting at column zero.
    """
    column = start
    for char in body:
        if char == " ":
            column += 1
        elif char == "\t":
            column = (column // 4 + 1) * 4
        else:
            break
    return column - start


def _dedent_columns(body: str, width: int, start: int = 0) -> str:
    """Remove at most `width` indentation columns, preserving a partially consumed tab.

    Used only for block recognition, never source offsets: a tab crossing the
    container boundary leaves its remaining columns as spaces in the content.
    """
    column, end = start, 0
    limit = start + width
    while end < len(body) and column < limit and body[end] in " \t":
        column = (column // 4 + 1) * 4 if body[end] == "\t" else column + 1
        end += 1
    return " " * max(0, column - limit) + body[end:]


def _containers(body: str) -> tuple[int, int, str]:
    """(block-quote depth, list-item content column, remainder): quote and item markers are peeled in any order, so
    `- ```x`, `1. ```x`, `- > ```x` and `> - ```x` all reach the same remainder. The column is the summed width of the
    item prefixes, measured on the quote-stripped line; it is 0 when the line has no item marker."""
    depth, col, cursor, rest = 0, 0, 0, body
    while True:
        if m := _QUOTE.match(rest):
            depth += 1
            cursor += len(rest[:m.end()])
        elif m := _ITEM_PREFIX.match(rest):
            # Tabs are expanded at four-column stops, not counted as one byte.
            # Consume the complete 1..4-column padding, including mixed spaces
            # and tabs; otherwise a fence is assigned to the wrong container.
            marker = re.match(r"^ {0,3}(?:[-+*]|[0-9]{1,9}[.)])", rest)
            marker_end = marker.end()
            marker_col = cursor + marker_end
            end, padded_col = marker_end, marker_col
            while end < len(rest) and rest[end] in " \t":
                padded_col = ((padded_col // 4 + 1) * 4 if rest[end] == "\t" else padded_col + 1)
                end += 1
            if 0 < padded_col - marker_col <= 4 and end < len(rest):
                col += padded_col - cursor
                cursor = padded_col
                rest = rest[end:]
                continue
            previous = cursor
            for char in rest[:m.end()]:
                cursor = (cursor // 4 + 1) * 4 if char == "\t" else cursor + 1
            col += cursor - previous
        else:
            return depth, col, rest
        rest = rest[m.end():]


def _container_path(body: str) -> tuple[tuple[tuple[str, int], ...], str]:
    """Ordered quote/item ancestors and content, on a tab-expanded block line.

    An item width belongs where its marker occurs: in ``> - >`` its
    indentation is after the first quote and before the second quote.
    """
    path = []
    while True:
        if match := _QUOTE.match(body):
            path.append(("quote", 0))
            body = body[match.end():]
        elif not _THEMATIC.match(body) and (match := _ITEM_PREFIX.match(body)):
            marker = re.match(r"^ {0,3}(?:[-+*]|[0-9]{1,9}[.)])", body)
            end = marker.end()
            while end < len(body) and body[end] == " ":
                end += 1
            # CommonMark 5.2: a marker with blank content has one virtual
            # padding column, regardless of its trailing whitespace. For a
            # nonempty item, 1..4 spaces are padding; greater indentation
            # uses one padding column and retains the excess as content.
            empty = end == len(body)
            width = end if not empty and 0 < end - marker.end() <= 4 else marker.end() + 1
            path.append(("item", width))
            body = "" if empty else body[width:]
        else:
            return tuple(path), body


def _continue_containers(body: str, path: tuple[tuple[str, int], ...]) -> str | None:
    """Strip ancestors in their original order, or None when this line leaves one."""
    for kind, width in path:
        if kind == "quote":
            match = _QUOTE.match(body)
            if match is None:
                return None
            body = body[match.end():]
        else:
            # A blank line needs no item indentation, but any later quote in
            # the path still requires its own marker (quotes have no lazy
            # continuation inside fenced code or raw HTML blocks).
            if body.strip(" ") and _indent_columns(body) < width:
                return None
            body = _dedent_columns(body, width)
    return body


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


def _interrupts(rest: str, depth: int, para_depth: int, base: int, start: int = 0) -> bool:
    """True when a line (block-quote markers removed) starts a block that ends the open paragraph. A continued quote
    line (same depth) and a lazy continuation (lower depth) stay in the paragraph, as GitHub renders them; a deeper
    quote, a fence, an ATX heading, a thematic break, a list item and an HTML block of type 1-6 end it. `base` is the
    content column of the list item holding the paragraph, so an item nested under it is still seen."""
    if depth > para_depth:
        return True
    lead = _indent_columns(rest, start)
    line = _dedent_columns(rest, base, start)
    if FENCE_OPEN.match(line) or _ATX_HEADING.match(line) or _THEMATIC.match(line) or _HTML_BLOCK.match(line):
        return True
    if _BULLET_ITEM.match(line):
        return True
    ordered = _ORDERED_ITEM.match(line)
    # only "1." may interrupt a paragraph, but a sibling item of the enclosing list always ends the item
    return bool(ordered and (ordered.group(1) == "1" or (base and lead < base)))


def _paragraph_line(body: str, path: tuple[tuple[str, int], ...]) -> tuple[str, bool]:
    """Paragraph content and whether all its ancestors occur on this line.

    Paragraphs permit lazy container continuations, unlike fences and raw
    HTML. Keep the ordered path so indentation before a nested quote is not
    confused with quote depth at the beginning of the source line.
    """
    for ancestor in path:
        inner = _continue_containers(body, (ancestor,))
        if inner is None:
            return body, False
        body = inner
    return body, True


def _paragraph_interrupts(content: str, matched: bool) -> bool:
    """Whether a new line ends the paragraph after matching its ancestors.

    A lazy line cannot start a new block container. In particular any ordered
    item starts a list after leaving a quote/item, whereas only an item numbered
    one may interrupt an ordinary paragraph inside matching containers.
    """
    if _QUOTE.match(content):
        return True
    if not matched and re.fullmatch(r" {0,3}(?:[-+*]|[0-9]{1,9}[.)]) *", content):
        return True  # an empty sibling item ends the old item; it is not lazy paragraph text
    if not matched and _ORDERED_ITEM.match(content):
        return True
    if not matched and _HTML_TYPE_7.match(content):
        # Type 7 cannot interrupt the paragraph in its own containers. Once a
        # required ancestor is absent it starts a new HTML block outside them.
        return True
    return _interrupts(content, 0, 0, 0)


@functools.lru_cache(maxsize=16)
def _layout(text: str) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...], tuple[int, ...],
                                tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    """(inline regions, fenced spans, continuation starts, raw HTML spans, indented spans). An inline region is a stretch in which
    one inline code span can live: a paragraph, a heading line, an HTML block start line or one table cell. A
    continuation start is the source offset of a line that continues an open paragraph or table (not the first line of
    a block, not a heading, not a line inside a fence). An HTML block span runs from its first line to just past its
    last line, excluding a terminating blank line or the line that ended its container. The final tuple records
    indented code blocks, which cannot interrupt a paragraph and are never inline regions."""
    WORK['layout_builds'] += 1
    regions: list[tuple[int, int]] = []
    fences: list[tuple[int, int]] = []
    html_blocks: list[tuple[int, int]] = []
    indented_blocks: list[tuple[int, int]] = []
    indented = None  # (source start, ordered container ancestors)
    hstart = 0
    conts: set[int] = set()
    seg: list[tuple[int, str]] = []
    # An open fence: (fence run, ordered container ancestors).
    fence, fstart, table, para_depth, pos = None, 0, False, 0, 0
    para_path: tuple[tuple[str, int], ...] = ()
    # Paths through open list items, outermost first. They persist across blank
    # lines; a nonblank line that cannot continue an ancestor leaves that item.
    lists: list[tuple[tuple[str, int], ...]] = []
    # an open raw HTML block: (end regex, or None for a block that ends at a blank line; the same container fields)
    html = None

    def flush(rows):
        if rows:
            regions.append((rows[0][0], rows[-1][0] + len(rows[-1][1])))

    def row_cells(at, raw):
        regions.extend((a, b) for a, b in _cell_bounds(raw.rstrip("\r\n"), at) if a < b)

    for raw in re.findall(r"[^\n]*\n|[^\n]+", text):
        at, pos = pos, pos + len(raw)
        # Block syntax uses visual columns. Expanding once before peeling any
        # container lets a tab supply the optional quote space AND residual
        # indentation, including nested quotes/list prefixes. Source rows and
        # offsets below remain untouched for inline spans and marker matches.
        body = block_line(raw.rstrip("\r\n"))
        depth, rest = _quotes(body)
        quote_column = len(body[:len(body) - len(rest)].expandtabs(4))
        if fence is not None:
            run, path = fence
            inner = _continue_containers(body, path)
            if inner is None:
                fences.append((fstart, at))
                fence = None
            else:
                close = _FENCE_CLOSE.match(inner)
                if close and close.group(1)[0] == run[0] and len(close.group(1)) >= len(run):
                    fences.append((fstart, pos))
                    fence = None
                continue
        if html is not None:
            end, path = html
            inner = _continue_containers(body, path)
            if inner is None:
                html = None
                html_blocks.append((hstart, at))
            elif end is None:
                if inner.strip(" "):
                    continue
                html = None
                html_blocks.append((hstart, at))
            else:
                if end.search(inner):
                    html = None
                    html_blocks.append((hstart, pos))
                continue
        if indented is not None:
            start, path = indented
            inner = _continue_containers(body, path)
            if inner is not None and (not inner.strip(" ") or _indent_columns(inner) >= 4):
                continue
            indented_blocks.append((start, at))
            indented = None
        if not rest.strip(" \t"):
            flush(seg)
            seg, table = [], False
            if body.strip(" "):
                # An explicitly empty quote can leave an existing list even
                # though it has no paragraph content. A truly blank line
                # instead keeps the item open for an indented continuation.
                while lists and _continue_containers(body, lists[-1]) is None:
                    lists.pop()
            continue
        if table:
            if not _interrupts(rest, depth, para_depth, 0, quote_column):
                row_cells(at, raw)
                conts.add(at)
                continue
            table = False
        elif seg:
            para_content, matched = _paragraph_line(body, para_path)
            if not para_content.strip(" "):
                # A blank line can carry item/quote prefixes. It is still a
                # paragraph boundary after those ancestors have been peeled.
                flush(seg)
                seg, table = [], False
                continue
            if matched and _is_delimiter_row(para_content) and _cell_count(_quotes(seg[-1][1].rstrip("\r\n"))[1]) == _cell_count(para_content):
                flush(seg[:-1])
                # the header row (the last paragraph line) starts the table, so it is not a continuation
                conts.discard(seg[-1][0])
                row_cells(*seg[-1])
                conts.add(at)
                seg, table = [], True
                continue
            if matched and _SETEXT.match(para_content):
                flush(seg)
                seg = []
                continue
            if not _paragraph_interrupts(para_content, matched):
                seg.append((at, raw))
                conts.add(at)
                continue
            flush(seg)
            seg = []
        # Continue the deepest surviving list before looking for more
        # containers. This retains the ancestor order even when a quoted fence
        # starts on a later line of an item, rather than on the marker line.
        while lists and _continue_containers(body, lists[-1]) is None:
            lists.pop()
        inherited = lists[-1] if lists else ()
        content = _continue_containers(body, inherited) if inherited else body
        added, crest = _container_path(content)
        path = inherited + added
        item_indices = [i for i, (kind, _) in enumerate(added) if kind == "item"]
        for item_index in item_indices:
            # Each item can survive when a deeper quote/item ends. Retaining
            # only the deepest path would also discard a still-live ancestor.
            lists.append(inherited + added[:item_index + 1])
        if not crest.strip(" "):
            continue  # empty items/quotes open containers, never a paragraph
        if _indent_columns(crest) >= 4:
            # Indented code cannot interrupt an open paragraph (handled
            # above), but starts here when there is no paragraph to continue.
            indented = (at, path)
            continue
        opener = FENCE_OPEN.match(crest)
        if opener:
            fence, fstart = (opener.group(1), path), at
        elif _ATX_HEADING.match(crest):
            regions.append((at, pos))
        elif (kind := _html_block(crest)) is not None:
            # raw HTML: no inline region, so a backtick on these lines never pairs and the block's images stay visible
            hstart = at
            if kind is not True and kind.search(crest):
                html_blocks.append((at, pos))   # the block closes on its own opening line
            else:
                html = (None if kind is True else kind, path)
        elif not _THEMATIC.match(rest) and not _THEMATIC.match(crest):
            seg, para_depth = [(at, raw)], depth
            para_path = path
    if fence is not None:
        fences.append((fstart, len(text)))
    else:
        flush(seg)
    if html is not None:
        html_blocks.append((hstart, len(text)))
    if indented is not None:
        indented_blocks.append((indented[0], len(text)))
    return tuple(regions), tuple(fences), tuple(sorted(conts)), tuple(html_blocks), tuple(indented_blocks)


def inline_regions(text: str) -> tuple[tuple[int, int], ...]:
    """Canonical, source-aligned blocks in which one inline construct may live."""
    return _layout(text)[0]


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


_AUTOLINK = re.compile(
    # CommonMark replaces source NUL with U+FFFD before parsing. Keeping its
    # source position here gives the same recognition without rewriting bytes.
    r"<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\x01-\x20\x7f<>]*|"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)>")


@functools.lru_cache(maxsize=16)
def autolink_candidates(text: str) -> tuple[tuple[int, int], ...]:
    """Source-aligned URI/email autolinks, before inline precedence is applied.

    These are candidates, not a global mask: a code opener before `<` still
    consumes raw backticks inside the URI. An earlier tag, title or comment
    likewise wins. A backslash can escape the opener, never the raw closer.
    """
    spans = []
    for lo, hi in inline_regions(text):
        for match in _AUTOLINK.finditer(text, lo, hi):
            start = match.start()
            before = start
            while before > lo and text[before - 1] == "\\":
                before -= 1
            if (start - before) % 2 == 0:
                spans.append(match.span())
    return tuple(spans)


def find_autolink(text: str, start: int = 0) -> tuple[int, int] | None:
    """First candidate whose opener is at or after `start` (cached index lookup)."""
    spans = autolink_candidates(text)
    index = bisect.bisect_left(spans, (start, -1))
    return spans[index] if index < len(spans) else None


def find_inline_code(text: str, start: int = 0) -> tuple[int, int] | None:
    """(start, end) of the first CommonMark inline code span whose opening run begins at or after `start`. The span
    runs from the opening backtick run to the end of its closing run; escaping backslashes are not part of it. A
    backtick preceded by an odd number of backslashes is escaped, so its run starts one character later. The
    content must be non-empty. It may span single newlines within one paragraph, but the closing run must lie in the
    same inline region: no blank line, fence, heading, list item, new block quote, thematic break, setext underline,
    HTML block start (types 1-6) or table cell boundary in between. Fenced text holds no inline span."""
    los, his = _region_bounds(text)
    links = autolink_candidates(text)
    for n in range(bisect.bisect_right(his, start), len(los)):
        WORK['regions'] += 1
        lo, hi = los[n], his[n]
        i = max(start, lo)
        while (i := text.find("`", i, hi)) >= 0:
            link = bisect.bisect_right(links, (i, len(text))) - 1
            if link >= 0 and start <= links[link][0] <= i < links[link][1]:
                # Only an opener encountered on this pass creates a literal.
                # A prior code span may have consumed `<` and ended inside the
                # apparent URI; resuming there must read later backticks raw.
                i = links[link][1]
                continue
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
def code_block_spans(text: str) -> tuple[tuple[int, int], ...]:
    """All inert Markdown code blocks; the fenced-only API remains unchanged."""
    layout = _layout(text)
    return tuple(sorted(layout[1] + layout[4]))


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
    """Source offsets of fenced/indented code blocks and inline code spans."""
    return sorted(code_block_spans(text) + inline_code_spans(text))


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
