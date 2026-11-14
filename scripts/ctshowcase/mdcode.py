"""Shared stdlib Markdown grammar, so marker and image scans agree on literals. Stdlib only and imports nothing from the package:
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
import html
import re
import string
import unicodedata

# Work counters for the cached scanners (layout builds on a cache miss, inline regions examined); tests read them.
WORK: collections.Counter = collections.Counter()

_SOURCE_NUL = re.compile("\x00")


@functools.lru_cache(maxsize=16)
def _source_view(text: str) -> str:
    """GFM input preprocessing, preserving one source character per position.

    Only raw authored documents enter here. Peeled definition candidates keep
    their internal NUL prefix masks; callers never treat those as raw input.
    This view is not returned to a README writer as replacement authored text.
    """
    WORK['source_view_chars'] += len(text)
    return text.replace("\x00", "\ufffd")


@functools.lru_cache(maxsize=16)
def _parse_views(text: str, document: str) -> tuple[str, str]:
    """Preprocess raw source NUL, without reinterpreting masked projection NUL.

    `text` may be a source-aligned masked copy. Only positions whose original
    document actually held NUL are replacement characters; other NULs remain
    synthetic masks. Short/no-document callers supply raw `text` instead.
    """
    source = _source_view(document)
    if len(document) < len(text):
        return _source_view(text), source
    if source == document:
        return text, source
    out = None
    for match in _SOURCE_NUL.finditer(document, 0, len(text)):
        at = match.start()
        if text[at] == "\x00":
            if out is None:
                out = list(text)
            out[at] = "\ufffd"
    return ("".join(out) if out is not None else text), source


# Markdown line endings are LF, CRLF or lone CR, never Python's other
# Unicode splitlines separators. Keep source characters and offsets intact.
LINE_END = r"(?:\r\n|\r(?!\n)|(?<!\r)\n)"
_LINE_END = re.compile(r"\r\n|[\r\n]")
_LINES = re.compile(r"[^\r\n]*(?:\r\n|[\r\n])|[^\r\n]+")
BLANK_LINE = re.compile(LINE_END + r"[ \t\x00]*" + LINE_END)


def source_lines(text: str):
    """Yield original lines including their original terminators, without copying offsets."""
    return (match.group() for match in _LINES.finditer(text))


def after_line_end(text: str, index: int) -> int:
    """Position after a line ending at index, or index if none starts there."""
    match = _LINE_END.match(text, index)
    return match.end() if match else index


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
_ITEM_AT = re.compile(_ITEM_PREFIX.pattern.removeprefix("^"))
_MARKER_AT = re.compile(r" {0,3}(?:[-+*]|[0-9]{1,9}[.)])")
_THEMATIC_AT = re.compile(_THEMATIC.pattern.removeprefix("^"))
_DELIMITER_CELLS = re.compile(r"\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*")
_TYPE_6 = ("address article aside base basefont blockquote body caption center col colgroup dd details dialog dir div dl "
           "dt fieldset figcaption figure footer form frame frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend "
           "li link main menu menuitem nav noframes ol optgroup option p param search section summary table tbody td "
           "tfoot th thead title tr track ul").split()
# GFM raw HTML uses ASCII whitespace and names, unlike Python's Unicode \s/\w.
# Share these lexical classes with the inline scanner so a complete type-7 tag
# has the same grammar as an inline tag (its block extent remains independent).
HTML_SPACE = r"[ \t\n\v\f\r]"
HTML_ATTRIBUTE_NAME = r"[A-Za-z_:][A-Za-z0-9_.:-]*"
HTML_ATTRIBUTE_VALUE = r"""(?:[^ \t\n\v\f\r"'=<>`]+|'[^']*'|"[^"]*")"""
HTML_ATTRIBUTE = rf"{HTML_SPACE}+{HTML_ATTRIBUTE_NAME}(?:{HTML_SPACE}*={HTML_SPACE}*{HTML_ATTRIBUTE_VALUE})?"
HTML_OPEN_TAG_PATTERN = rf"<([A-Za-z][A-Za-z0-9-]*)((?:{HTML_ATTRIBUTE})*){HTML_SPACE}*/?>"
HTML_CLOSE_TAG_PATTERN = rf"</[A-Za-z][A-Za-z0-9-]*{HTML_SPACE}*>"
# CommonMark HTML blocks 1-6 interrupt a paragraph; type 7 (any other complete tag, like <span> or <a>) cannot
_HTML_BLOCK = re.compile(
    r"^ {0,3}(?:<(?ai:script|pre|style|textarea)(?:[ \t>]|$)|<!--|<\?|<![A-Z]|<!\[CDATA\[|</?(?ai:"
    + "|".join(_TYPE_6) + r")(?:[ \t]|/?>|$))")


# the seven HTML block kinds (CommonMark 4.6). Types 1-5 end at a marker found on a line (the start line included);
# types 6 and 7 end at the next blank line. Type 7 is one complete open or closing tag alone on its line and cannot
# interrupt a paragraph, so an inline tag in running text (`<span>a` b</span>`) stays Markdown.
_HTML_OPEN_1_5 = (
    (re.compile(r"^ {0,3}<(?:script|pre|style|textarea)(?:[ \t>]|$)", re.I | re.A),
     re.compile(r"</(?:script|pre|style|textarea)>", re.I | re.A)),
    (re.compile(r"^ {0,3}<!--"), re.compile(r"-->")),
    (re.compile(r"^ {0,3}<\?"), re.compile(r"\?>")),
    (re.compile(r"^ {0,3}<![A-Z]"), re.compile(r">")),
    (re.compile(r"^ {0,3}<!\[CDATA\["), re.compile(r"\]\]>")),
)
_HTML_TYPE_6 = re.compile(r"^ {0,3}</?(?:" + "|".join(_TYPE_6) + r")(?:[ \t]|/?>|$)", re.I | re.A)
_HTML_TYPE_7 = re.compile(
    rf"^ {{0,3}}(?:{HTML_OPEN_TAG_PATTERN}|{HTML_CLOSE_TAG_PATTERN}){HTML_SPACE}*$")


def _html_block(line: str):
    """None when `line` (container markers removed) does not start an HTML block; otherwise the end-condition regex of
    a type 1-5 block, or True for a type 6 or 7 block, which ends at the next blank line."""
    for opener, end in _HTML_OPEN_1_5:
        if opener.match(line):
            return end
    return True if _HTML_TYPE_6.match(line) or _HTML_TYPE_7.match(line) else None


@functools.lru_cache(maxsize=16)
def _backtick_index(text: str):
    """Maximal raw runs, indexed once; escaped closers remain eligible raw runs."""
    starts, ends, lengths = [], [], collections.defaultdict(list)
    WORK['backtick_index_chars'] += len(text)
    for match in re.finditer(r"`+", text):
        start, end = match.span()
        starts.append(start)
        ends.append(end)
        lengths[end - start].append(start)
        WORK['backtick_index_runs'] += 1
    return tuple(starts), tuple(ends), {length: tuple(positions) for length, positions in lengths.items()}


def _run_end(text: str, i: int) -> int:
    """Index just past the raw run at `i`, including a resumed position inside it."""
    starts, ends, _ = _backtick_index(text)
    at = bisect.bisect_right(starts, i) - 1
    WORK['backtick_end_lookups'] += 1
    return ends[at] if at >= 0 and i < ends[at] else i


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
    # A thematic break must end in its marker; avoid rescanning each nested
    # suffix when a long item chain ends in ordinary content.
    trimmed = body.rstrip(" \t")
    marker = trimmed[-1:] if trimmed[-1:] in ("-", "*", "_") else ""
    thematic_start = len(trimmed.rstrip(marker + " \t")) if marker else len(body)
    cursor = 0
    while True:
        if match := _QUOTE.match(body, cursor):
            path.append(("quote", 0))
            cursor = match.end()
        elif not (marker and cursor >= thematic_start
                  and _THEMATIC_AT.match(body, cursor)) and (match := _ITEM_AT.match(body, cursor)):
            item_marker = _MARKER_AT.match(body, cursor)
            end = item_marker.end()
            while end < len(body) and body[end] == " ":
                end += 1
            # A blank item has one virtual padding column. Nonempty items
            # use up to four spaces, leaving any excess as content.
            empty = end == len(body)
            width = end - cursor if not empty and 0 < end - item_marker.end() <= 4 else item_marker.end() - cursor + 1
            path.append(("item", width))
            cursor = len(body) if empty else cursor + width
        else:
            return tuple(path), body[cursor:]


def _continue_containers(body: str, path: tuple[tuple[str, int], ...]) -> str | None:
    """Strip ancestors in their original order, or None when this line leaves one."""
    cursor = 0
    residual = 0
    nonblank_end = len(body.rstrip(" "))
    for kind, width in path:
        if kind == "quote":
            # A partially consumed tab is represented by virtual spaces.
            if residual:
                if residual > 3:
                    return None
                prefix = " " * residual + body[cursor:cursor + 4]
                match = _QUOTE.match(prefix)
                if match is None:
                    return None
                cursor += match.end() - residual
                residual = 0
            else:
                match = _QUOTE.match(body, cursor)
                if match is None:
                    return None
                cursor = match.end()
        else:
            column = 0
            used = min(residual, width)
            column += used
            residual -= used
            while column < width and cursor < len(body) and body[cursor] in " \t":
                column = (column // 4 + 1) * 4 if body[cursor] == "\t" else column + 1
                cursor += 1
                WORK['container_indent_chars'] += 1
            if column < width and (residual or cursor < nonblank_end):
                return None
            residual += max(0, column - width)
    return " " * residual + body[cursor:]



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


class _DefinitionProgress:
    """Track a paragraph's initial definition without rescanning title prefixes."""

    def __init__(self, line: str):
        self.parts = []
        self.state = "pending"
        self.closer = ""
        self.has_title = False
        self.feed(line)

    def feed(self, line: str) -> None:
        if self.state == "invalid":
            return
        self.parts.append(line)
        WORK['definition_progress_chars'] += len(line)
        if self.state == "title":
            # Escapes do not cross a line ending. Parenthesized titles cannot
            # contain an unescaped opening parenthesis.
            escaped = False
            for char in line:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == self.closer:
                    self.state = "pending"
                    break
            else:
                return
        candidate = "\n".join(self.parts)
        match = REF_DEFINITION.match(candidate)
        if match and match.end() == len(candidate) and _definition_key(match, candidate) and (
                match.group(3) is None or _balanced_destination(match.group(3))):
            destination_end = match.end(2) + 1 if match.group(2) is not None else match.end(3)
            self.has_title = bool(candidate[destination_end:match.end()].strip())
            self.state = "complete"
            return
        # A title may continue for arbitrarily many lines. Identify its opener
        # once, then scan each subsequent line only once until the closer.
        for opener, closer in ((chr(34), chr(34)), ("'", "'"), ("(", ")")):
            trial = candidate + closer
            match = REF_DEFINITION.match(trial)
            if (match and match.end() == len(trial) and _definition_key(match, trial)
                    and (match.group(3) is None or _balanced_destination(match.group(3)))
                    and match.end(2 if match.group(2) is not None else 3) < len(candidate)
                    and candidate[match.end(2) + 1 if match.group(2) is not None else match.end(3):]
                    .lstrip(" \t\r\n\x00").startswith(opener)):
                self.state, self.closer = "title", closer
                return
        # Labels may span lines but are limited to 999 characters. A colon
        # with no destination can also take its destination on the next line.
        stripped = candidate.lstrip(" ")
        if ((stripped.startswith("[") and "]:" not in stripped and len(stripped) <= 1001)
                or (stripped.endswith(":") and "]:" in stripped and len(self.parts) == 1)):
            self.state = "pending"
        else:
            self.state = "invalid"


@functools.lru_cache(maxsize=16)
def _layout(text: str) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...], tuple[int, ...],
                                tuple[tuple[int, int], ...], tuple[tuple[int, int], ...], dict[int, int]]:
    """(inline regions, fenced spans, continuation starts, raw HTML spans, indented spans). An inline region is a stretch in which
    one inline code span can live: a paragraph, a heading line, an HTML block start line or one table cell. A
    continuation start is the source offset of a line that continues an open paragraph or table (not the first line of
    a block, not a heading, not a line inside a fence). An HTML block span runs from its first line to just past its
    last line, excluding a terminating blank line or the line that ended its container. The final tuple records
    indented code blocks, which cannot interrupt a paragraph and are never inline regions."""
    text = _source_view(text)
    WORK['layout_builds'] += 1
    regions: list[tuple[int, int]] = []
    fences: list[tuple[int, int]] = []
    html_blocks: list[tuple[int, int]] = []
    indented_blocks: list[tuple[int, int]] = []
    indented = None  # (source start, ordered container ancestors)
    hstart = 0
    conts: set[int] = set()
    prefixes: dict[int, int] = {}
    seg: list[tuple[int, str]] = []
    # An open fence: (fence run, ordered container ancestors).
    fence, fstart, table, para_depth, pos = None, 0, False, 0, 0
    para_path: tuple[tuple[str, int], ...] = ()
    definition = None
    # Paths through open list items, outermost first. They persist across blank
    # lines; a nonblank line that cannot continue an ancestor leaves that item.
    lists: tuple[tuple[str, int], ...] = ()

    def surviving_list(body, path):
        rest, last = body, 0
        for index, ancestor in enumerate(path):
            rest = _continue_containers(rest, (ancestor,))
            if rest is None:
                break
            if ancestor[0] == "item":
                last = index + 1
        return path[:last]
    # an open raw HTML block: (end regex, or None for a block that ends at a blank line; the same container fields)
    html = None

    def flush(rows):
        if rows:
            regions.append((rows[0][0], rows[-1][0] + len(rows[-1][1])))

    def row_cells(at, raw):
        regions.extend((a, b) for a, b in _cell_bounds(raw.rstrip("\r\n"), at) if a < b)

    for raw in source_lines(text):
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
                lists = surviving_list(body, lists)
            continue
        if table:
            if not _interrupts(rest, depth, para_depth, 0, quote_column):
                row_cells(at, raw)
                conts.add(at)
                continue
            table = False
        elif seg:
            para_content, matched = _paragraph_line(body, para_path)
            if definition and definition.state == "complete":
                # A following title is part of the definition only inside the
                # same containers. Otherwise the definition has no paragraph
                # that could lazily continue into this line.
                possible_title = matched and not definition.has_title and para_content.lstrip(" ").startswith(('"', "'", "("))
                if not possible_title:
                    flush(seg)
                    seg = []
            if seg and definition:
                definition.feed(para_content)
            if not seg:
                pass  # process this line as a new block below
            elif not para_content.strip(" "):
                # A blank line can carry item/quote prefixes. It is still a
                # paragraph boundary after those ancestors have been peeled.
                flush(seg)
                seg, table = [], False
                continue
            elif matched and _is_delimiter_row(para_content) and _cell_count(_quotes(seg[-1][1].rstrip("\r\n"))[1]) == _cell_count(para_content):
                flush(seg[:-1])
                # the header row (the last paragraph line) starts the table, so it is not a continuation
                conts.discard(seg[-1][0])
                row_cells(*seg[-1])
                conts.add(at)
                seg, table = [], True
                continue
            elif matched and _SETEXT.match(para_content):
                flush(seg)
                seg = []
                continue
            elif not _paragraph_interrupts(para_content, matched):
                seg.append((at, raw))
                conts.add(at)
                if matched:
                    prefixes[at] = source_prefix_chars(raw, len(body) - len(para_content))
                continue
            flush(seg)
            seg = []
        # Continue the deepest surviving list before looking for more
        # containers. This retains the ancestor order even when a quoted fence
        # starts on a later line of an item, rather than on the marker line.
        lists = surviving_list(body, lists)
        inherited = lists
        content = _continue_containers(body, inherited) if inherited else body
        added, crest = _container_path(content)
        path = inherited + added
        item_indices = [i for i, (kind, _) in enumerate(added) if kind == "item"]
        if item_indices:
            lists = path[:len(inherited) + item_indices[-1] + 1]
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
            definition = _DefinitionProgress(crest) if crest.lstrip(" ").startswith("[") else None
    if fence is not None:
        fences.append((fstart, len(text)))
    else:
        flush(seg)
    if html is not None:
        html_blocks.append((hstart, len(text)))
    if indented is not None:
        indented_blocks.append((indented[0], len(text)))
    return tuple(regions), tuple(fences), tuple(sorted(conts)), tuple(html_blocks), tuple(indented_blocks), prefixes


def inline_regions(text: str) -> tuple[tuple[int, int], ...]:
    """Canonical, source-aligned blocks in which one inline construct may live."""
    return _layout(text)[0]


@functools.lru_cache(maxsize=16)
def continuation_starts(text: str) -> frozenset[int]:
    """Source offsets of the lines that continue an open paragraph or table (every such line after the first line of
    its block, and each table row after the header). Headings, block starts and lines inside fences are not included."""
    return frozenset(_layout(text)[2])


def _closing_run(text: str, pos: int, k: int, limit: int) -> tuple[int, int] | None:
    """First maximal raw run of length `k` in [pos, limit), without suffix rescans."""
    positions = _backtick_index(text)[2].get(k, ())
    at = bisect.bisect_left(positions, pos)
    WORK['backtick_close_lookups'] += 1
    if at < len(positions) and positions[at] + k <= limit:
        return positions[at], positions[at] + k
    return None


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


_BARE_START = re.compile(r"(?ai:https?://|ftp://)|www\.")
_ASCII_SPACE = " \t\r\n"


def _host_character(char: str) -> bool:
    # cmark-gfm permits Unicode host characters, but neither Unicode spaces
    # nor punctuation (ASCII punctuation includes symbols such as `$`).
    return (char not in _ASCII_SPACE + "\f" and unicodedata.category(char) != "Zs"
            and char not in string.punctuation and not unicodedata.category(char).startswith("P"))


def _bare_autolinks(text: str, lo: int, hi: int):
    """Lexical GFM URL candidates; bracket/HTML/code precedence belongs to callers.

    Index host runs and token ends once. Nested URL starts in a long token
    share their suffix work, including rejected underscore domains. Native
    cmark-gfm also accepts short hosts, ftp and scheme starts after punctuation;
    `www.` has the published stricter preceding-delimiter rule.
    """
    if _BARE_START.search(text, lo, hi) is None:
        return
    size = hi - lo
    host_ends = [hi] * (size + 1)
    token_ends = [hi] * (size + 1)
    opens, closes, dots, underscores = [], [], [], []
    for i in range(hi - 1, lo - 1, -1):
        char = text[i]
        token_ends[i - lo] = i if char in _ASCII_SPACE + "<" else token_ends[i - lo + 1]
        if char in "._-" or _host_character(char):
            host_ends[i - lo] = host_ends[i - lo + 1]
        elif char == "\\" and i + 1 < hi:
            next_char = text[i + 1]
            host_ends[i - lo] = (host_ends[i - lo + 2] if i + 2 <= hi and
                                   (next_char in "._-" or _host_character(next_char)) else i + 1)
        else:
            host_ends[i - lo] = i
    for i in range(lo, hi):
        char = text[i]
        if char == "(":
            opens.append(i)
        elif char == ")":
            closes.append(i)
        elif char == ".":
            dots.append(i)
        elif char == "_":
            underscores.append(i)
    # The punctuation-only tail is shared by every start in its token.
    trimmed = {}
    content_starts = set()
    line_at = lo
    for raw in source_lines(text[lo:hi]):
        expanded = block_line(raw.rstrip("\r\n"))
        _, rest = _container_path(expanded)
        content_starts.add(line_at + source_prefix_chars(raw, len(expanded) - len(rest)))
        line_at += len(raw)
    for match in _BARE_START.finditer(text, lo, hi):
        WORK['bare_starts'] += 1
        start = match.start()
        www = match.group() == "www."
        before = text[start - 1] if start > lo else ""
        if www:
            if before and before not in _ASCII_SPACE + "*_~(" and start not in content_starts:
                continue
            host = start
        else:
            # cmark rewinds the entire ASCII-letter run before `://`.
            if before and before in string.ascii_letters:
                continue
            host = match.end()
            if host >= hi or not _host_character(text[host]):
                continue
        domain_end = host_ends[host - lo]
        first_dot = bisect.bisect_left(dots, host)
        last_dot = bisect.bisect_left(dots, domain_end)
        if www and last_dot == first_dot:
            continue
        # Underscores in either of the last two segments invalidate a host.
        # Match native's >10-segment safeguard without rescanning the suffix.
        tail = dots[last_dot - 2] + 1 if last_dot - first_dot >= 2 else host
        under = bisect.bisect_left(underscores, tail)
        if (last_dot - first_dot <= 10 and under < len(underscores)
                and underscores[under] < domain_end):
            continue
        end = token_ends[start - lo]
        if end not in trimmed:
            cursor = end
            while cursor > lo:
                WORK['bare_trim_steps'] += 1
                char = text[cursor - 1]
                if char in ")?!.,:*_~'\"":
                    cursor -= 1
                elif char == ";":
                    previous = cursor - 2
                    while previous >= lo and text[previous] in string.ascii_letters:
                        previous -= 1
                        WORK['bare_trim_steps'] += 1
                    cursor = previous if previous >= lo and text[previous] == "&" else cursor - 1
                else:
                    break
            trimmed[end] = cursor
        tail = trimmed[end]
        opening = bisect.bisect_left(opens, end) - bisect.bisect_left(opens, start)
        last_close = bisect.bisect_left(closes, end)
        closing = last_close - bisect.bisect_left(closes, start)
        excess = max(0, closing - opening)
        trailing_closes = last_close - bisect.bisect_left(closes, tail)
        end = tail if excess >= trailing_closes else closes[last_close - excess - 1] + 1
        if end > host:
            yield start, end
    WORK['bare_index_chars'] += 2 * size


@functools.lru_cache(maxsize=16)
def autolink_candidates(text: str, bare: bool = True) -> tuple[tuple[int, int], ...]:
    """Source-aligned URI/email autolinks, before inline precedence is applied.

    Bare candidates can overlap each other or an angle candidate. They require
    bracket context from the shared inline precedence scan before acceptance.
    These are candidates, not a global mask: a code opener before `<` still
    consumes raw backticks inside the URI. An earlier tag, title or comment
    likewise wins. A backslash can escape the opener, never the raw closer.
    """
    text = _source_view(text)
    spans = []
    for lo, hi in inline_regions(text):
        for match in _AUTOLINK.finditer(text, lo, hi):
            start = match.start()
            before = start
            while before > lo and text[before - 1] == "\\":
                before -= 1
            if (start - before) % 2 == 0:
                spans.append(match.span())
        if bare:
            spans.extend(_bare_autolinks(text, lo, hi))
    return tuple(sorted(spans))


def find_autolink(text: str, start: int = 0) -> tuple[int, int] | None:
    """First candidate whose opener is at or after `start` (cached index lookup)."""
    spans = autolink_candidates(text)
    index = bisect.bisect_left(spans, (start, -1))
    return spans[index] if index < len(spans) else None


def _find_raw_inline_code(text: str, start: int = 0) -> tuple[int, int] | None:
    """(start, end) of the first CommonMark inline code span whose opening run begins at or after `start`. The span
    runs from the opening backtick run to the end of its closing run; escaping backslashes are not part of it. A
    backtick preceded by an odd number of backslashes is escaped, so its run starts one character later. The
    content must be non-empty. It may span single newlines within one paragraph, but the closing run must lie in the
    same inline region: no blank line, fence, heading, list item, new block quote, thematic break, setext underline,
    HTML block start (types 1-6) or table cell boundary in between. Fenced text holds no inline span."""
    text = _source_view(text)
    los, his = _region_bounds(text)
    # Bare URLs need bracket context from the shared accepted-inline pass.
    # Leave their raw ticks available here: that scanner compares the earlier
    # URL opener against this possible code span and resumes after the winner.
    links = autolink_candidates(text, bare=False)
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
def _raw_inline_code_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Sorted, non-overlapping inline code spans: `_find_raw_inline_code` repeated from offset 0, each call resuming at the
    end of the previous span."""
    spans: list[tuple[int, int]] = []
    at = 0
    while (span := _find_raw_inline_code(text, at)) is not None:
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
            if out[i] not in "\r\n":
                out[i] = "\x00"
    return "".join(out)


def find_blocks(pattern: re.Pattern, text: str) -> list[re.Match]:
    """Matches outside accepted code/literal data, with original source groups byte-identical."""
    found = (pattern.fullmatch(text, m.start(), m.end()) for m in pattern.finditer(_marker_projection(text)))
    return [m for m in found if m]


# Shared stdlib-only inline/reference grammar. Readme, meta and image lint
# project this same accepted precedence result; no package-level imports.
# Explicit source-aligned line boundaries also handle CRLF as one ending.
_NL = LINE_END
_SOFT_NL = _NL + rf"(?![ \t\x00]*{_NL})"
REF_DEFINITION = re.compile(
    rf"(?:\A|(?<=\n)|(?<=\r)(?!\n))\x00* {{0,3}}\[((?:\\.|[^\[\]\\\r\n]|{_SOFT_NL})+)\]:"
    rf"[ \t\x00]*(?:{_NL}[ \t\x00]*)?(?:<((?:\\[^\r\n]|[^<>\\\r\n])*)>|((?!<)[^\x00-\x20\x7f]+?))"
    rf"(?:(?:[ \t]+|[ \t\x00]*{_NL}[ \t\x00]*)(?:\"(?:\\.|\\(?={_NL})|[^\"\\\r\n]|{_SOFT_NL})*\"|"
    rf"'(?:\\.|\\(?={_NL})|[^'\\\r\n]|{_SOFT_NL})*'|\((?:\\.|\\(?={_NL})|[^()\\\r\n]|{_SOFT_NL})*\)))?"
    r"[ \t]*(?=\r|\n|\Z)")
# a title may span lines but never a blank one; NUL stands in for a blanked quote or list-item prefix (see below)
# CommonMark raw HTML: an open tag needs a valid tag name, valid attributes and a closing `>`; anything else is text
HTML_OPEN_TAG = re.compile(HTML_OPEN_TAG_PATTERN)
HTML_ATTR = re.compile(rf"({HTML_ATTRIBUTE_NAME})(?:{HTML_SPACE}*={HTML_SPACE}*"
                       rf"({HTML_ATTRIBUTE_VALUE}))?")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_RAW_HTML_OPEN = re.compile(r"<\?|<![A-Za-z]|<!\[CDATA\[")
_INLINE_DECLARATION = re.compile(rf"<![A-Z]+{HTML_SPACE}")
_HTML_CLOSE_TAG = re.compile(HTML_CLOSE_TAG_PATTERN)
_LINK_SPACE = " \t\r\n"
_ESCAPABLE = frozenset(string.punctuation)
_ESCAPE_SEQUENCE = re.compile(r"\\([" + re.escape("".join(sorted(_ESCAPABLE))) + r"])")


def _destination_value(value: str) -> str:
    """Decode destination entities and CommonMark's ASCII punctuation escapes only."""
    token = re.compile(r"\\?&(?:#[xX][0-9a-fA-F]{1,6}|#[0-9]{1,7}|[A-Za-z][A-Za-z0-9]{1,31});|\\[" + re.escape("".join(sorted(_ESCAPABLE))) + r"]")
    def decode(match):
        part = match.group()
        if part.startswith("\\&"):
            part = part[1:]
        elif part.startswith("\\"):
            return part[1:]
        if part.startswith("&#") or part[1:] in html.entities.html5:
            return html.unescape(part)
        return part

    return token.sub(decode, value)


def _escaped(text: str, i: int) -> bool:
    """True when an odd number of consecutive backslashes immediately precedes index `i` (CommonMark escape)."""
    count, before = 0, i - 1
    while before >= 0 and text[before] == "\\":
        count += 1
        before -= 1
    return count % 2 == 1


def _search_unescaped(pattern, text: str, pos: int, html_spans=None, document: str | None = None):
    """First match at or after `pos` whose opening character is not backslash-escaped. A match starting inside one of
    `html_spans` (raw HTML block spans) is never escaped: backslashes are literal there."""
    def escaped(start):
        return _escaped(text, start) and not (html_spans is not None and _span_at(html_spans, start) is not None)

    source = document if document is not None else text
    match = pattern.search(text, pos)
    while match:
        invalid = escaped(match.start())
        if not invalid and pattern is HTML_OPEN_TAG:
            block = _span_at(html_spans or (), match.start()) or _span_at(inline_regions(source), match.start())
            invalid = block is None or match.end() > block[1]
        if not invalid:
            return match
        # A rejected tag is text, so a later real tag/image inside the rejected
        # match must still be considered instead of consuming the whole match.
        match = pattern.search(text, match.start() + 1)
    return None


@functools.lru_cache(maxsize=16)
def _comment_matches(text: str, html_spans):
    """Index comment candidates without rescanning rejected opener suffixes.

    Each delimiter/paragraph pass visits the document once. Closer and paragraph
    cursors advance monotonically across openers. Keep nested candidates too:
    an outer opener can belong to a literal tag attribute or reference label,
    leaving an inner opener live when a caller resumes beyond that literal.
    Inline comments may not cross paragraphs; raw HTML-block comments may.
    """
    WORK['comment_builds'] += 1
    WORK['comment_scan_chars'] += 4 * len(text)
    closers = [m.start() for m in re.finditer(r"-->", text)]
    doubles = [m.start() for m in re.finditer(r"(?=--)", text)]
    paragraphs = [m.start() for m in BLANK_LINE.finditer(text)]
    regions = _layout(text)[0]
    matches, starts = [], []
    closer = paragraph = double = 0
    for opener in re.finditer(r"<!--", text):
        start = opener.start()
        block = _span_at(html_spans, start)
        in_block = block is not None
        if not in_block and _escaped(text, start):
            continue
        while closer < len(closers) and closers[closer] < opener.end():
            closer += 1
        if in_block:
            # Raw comments can be unterminated when their container ends.
            # Their literal extent stops there, even if an unrelated later
            # block contains a closer. Inline comment rules do not apply.
            end = min(closers[closer] + 3, block[1]) if closer < len(closers) else block[1]
            matches.append((start, end))
            starts.append(start)
            continue
        if closer == len(closers):
            break
        while paragraph < len(paragraphs) and paragraphs[paragraph] < start:
            paragraph += 1
        end = closers[closer] + 3
        if not in_block and paragraph < len(paragraphs) and paragraphs[paragraph] < end:
            continue
        if not in_block:
            # CommonMark inline comments have stricter lexical rules than
            # HTML block comments. A delimiter-looking body is ordinary text
            # if it begins > or ->, contains --, or ends in a hyphen.
            begin = opener.end()
            while double < len(doubles) and doubles[double] < begin:
                double += 1
            if begin != closers[closer] and (
                    text[begin:begin + 1] == ">" or text[begin:begin + 2] == "->"
                    or double < len(doubles) and doubles[double] != closers[closer]):
                continue
            # Inline markup cannot join separate blocks (including headings,
            # list items and table cells), even without a blank line.
            region = _span_at(regions, start)
            if region is None or end > region[1]:
                continue
        matches.append((start, end))
        starts.append(start)
    return tuple(starts), tuple(matches)


class _CommentMatch:
    """The span-only match interface the HTML scans consume, with no body rescan."""
    __slots__ = ("_start", "_end")

    def __init__(self, start: int, end: int):
        self._start, self._end = start, end

    def start(self):
        return self._start

    def end(self):
        return self._end

    def span(self):
        return self._start, self._end


def _search_comment(text: str, pos: int, html_spans):
    """First indexed, unescaped valid HTML comment at or after `pos`."""
    starts, matches = _comment_matches(text, tuple(html_spans))
    index = bisect.bisect_left(starts, pos)
    return _CommentMatch(*matches[index]) if index < len(matches) else None


@functools.lru_cache(maxsize=16)
def _raw_html_matches(text: str, document: str):
    """Index PI, declaration, CDATA and closing-tag candidates once.

    Delimiter cursors only advance, including for rejected unterminated or
    cross-block openers. Keep nested candidates: an earlier apparent opener
    may be literal text inside code, a tag attribute or a reference label.
    Comments retain their separate, stricter GitHub lexical rules.
    """
    WORK['raw_html_scan_chars'] += 6 * len(text)
    html_blocks = html_block_spans(document)
    regions = inline_regions(document)
    ends = {end: [m.start() for m in re.finditer(re.escape(end), text)] for end in ('?>', '>', ']]>')}
    cursors = dict.fromkeys(ends, 0)
    matches = []
    for opener in _RAW_HTML_OPEN.finditer(text):
        start = opener.start()
        end_marker = '?>' if opener.group() == '<?' else ']]>' if opener.group() == '<![CDATA[' else '>'
        cursor, positions = cursors[end_marker], ends[end_marker]
        while cursor < len(positions) and positions[cursor] < opener.end():
            cursor += 1
        cursors[end_marker] = cursor
        block = _span_at(html_blocks, start)
        if (block is None and end_marker == '>' and _INLINE_DECLARATION.match(text, start) is None):
            # Retain the published GFM inline declaration grammar, like the
            # existing strict inline-comment rules. HTML blocks independently
            # require an uppercase ASCII-letter opener without inline name/space rules.
            continue
        if block is not None:
            # A raw HTML block can end with its container before a closer.
            end = min(positions[cursor] + len(end_marker), block[1]) if cursor < len(positions) else block[1]
        elif cursor < len(positions):
            end = positions[cursor] + len(end_marker)
        else:
            continue
        region = block or _span_at(regions, start)
        if region is not None and end <= region[1] and (block is not None or not _escaped(text, start)):
            matches.append((start, end))
    for match in _HTML_CLOSE_TAG.finditer(text):
        start, end = match.span()
        block = _span_at(html_blocks, start)
        region = block or _span_at(regions, start)
        if region is not None and end <= region[1] and (block is not None or not _escaped(text, start)):
            matches.append((start, end))
    matches.sort()
    return tuple(start for start, _ in matches), tuple(matches)


def _search_raw_html(text: str, pos: int, document: str | None = None):
    starts, matches = _raw_html_matches(text, document if document is not None else text)
    index = bisect.bisect_left(starts, pos)
    return _CommentMatch(*matches[index]) if index < len(matches) else None


def _span_at(spans, index: int, strict: bool = False):
    """The (a, b) span of a sorted, non-overlapping sequence that holds `index` (a <= index < b; strict: a < index < b),
    found by bisection so membership is a lookup, not a walk from offset 0."""
    WORK['span_checks'] += 1
    n = bisect.bisect_left(spans, (index, -1) if strict else (index + 1, -1)) - 1
    if n >= 0 and (spans[n][0] < index < spans[n][1] if strict else spans[n][0] <= index < spans[n][1]):
        return spans[n]
    return None


def _in_inline_code(text: str, index: int) -> bool:
    """True when `index` lies strictly inside a non-fenced inline code span (a < index < b for a span (a, b))."""
    return _span_at(_raw_inline_code_spans(text), index, strict=True) is not None


def _in_html_block(text: str, index: int) -> bool:
    """True when `index` lies inside a raw HTML block (CommonMark HTML block extent): there a backslash is literal text,
    and the block's lines are not Markdown reference definitions. The spans are cached per document by `mdcode`."""
    return _span_at(html_block_spans(text), index) is not None


def _raw_definition_matches(candidate: str, document: str):
    """Read definitions within source blocks, leaving an invalid next-block title visible.

    Bounding the regex itself, instead of rejecting an overlong match afterward,
    retains a valid destination when only its apparent optional title belongs to
    another block.
    """
    for lo, hi in inline_regions(document):
        yield from REF_DEFINITION.finditer(candidate, lo, hi)


def _definition_candidates(document: str) -> str:
    """The document with code blocks and HTML comments blanked (same length), the text in which a definition is read."""
    document = _source_view(document)
    out = list(document)
    for a, b in code_block_spans(document):
        for i in range(a, b):
            if out[i] not in "\r\n":
                out[i] = " "
    # raw HTML block text is literal HTML, not Markdown: a `[label]: dest` line inside it defines nothing. The block's
    # extent ends at its end condition, so a definition after the block still counts.
    for a, b in html_block_spans(document):
        for i in range(a, b):
            if out[i] not in "\r\n":
                out[i] = " "
    fences = code_block_spans(document)
    html_spans = html_block_spans(document)
    links = _inline_link_spans(document, fences)  # resolved link destinations and titles: literal text, computed once
    # Reference labels are parsed before inline HTML. A comment-looking string
    # inside a syntactically valid definition label is literal label text, even
    # though the same string in a paragraph would be an actual HTML comment.
    candidate = _peel_definition_containers(document, out.copy())
    continuation = continuation_starts(document)
    label_spans = []
    previous_end = None
    for match in _raw_definition_matches(candidate, document):
        if not _definition_key(match, document):
            continue
        if match.group(3) is not None and not _balanced_destination(match.group(3)):
            continue
        if match.start() in continuation and previous_end != match.start():
            continue
        label_spans.append(match.span(1))
        previous_end = after_line_end(document, match.end())
    # Left-to-right scan over the next HTML open tag and the next comment, as in `_outside_code`: a comment opener that
    # sits inside a complete open tag (for example an attribute value) is attribute text, so the tag is consumed whole.
    pos = 0
    tag = comment = raw_html = None
    while True:
        if tag is not False and (tag is None or tag.start() < pos):
            tag = _search_unescaped(HTML_OPEN_TAG, document, pos, html_spans) or False
        if comment is not False and (comment is None or comment.start() < pos):
            comment = _search_comment(document, pos, html_spans) or False
        if raw_html is not False and (raw_html is None or raw_html.start() < pos):
            raw_html = _search_raw_html(document, pos) or False
        found = [m for m in (tag, comment, raw_html) if m]
        if not found:
            break
        nxt = min(found, key=lambda m: m.start())
        start = nxt.start()
        literal_label = _span_at(label_spans, start)
        if literal_label is not None:
            pos = literal_label[1]
            continue
        inside = _span_at(links, start)
        if inside is not None:  # an opener inside a link destination or title is text: resume after that span
            pos = inside[1]
            continue
        if nxt is tag or nxt is raw_html:
            # a tag inside inline code or a fence is text: the search resumes one character on. A real tag is consumed
            # without blanking, so a `<!--` inside its attributes never opens a comment.
            if _in_inline_code(document, start) or _span_at(fences, start) is not None:
                pos = start + 1
            else:
                pos = nxt.end()
            continue
        # an opener that is escaped, inside inline code or inside a fence is text: the search resumes one character on,
        # so a code-span `<!--` never consumes text up to a later real `-->`
        if _escaped(document, start) or _in_inline_code(document, start) or _span_at(fences, start) is not None:
            pos = start + 1
            continue
        for i in range(*nxt.span()):
            if out[i] not in "\r\n":
                out[i] = " "
        pos = nxt.end()
    return _peel_definition_containers(document, out)


def _peel_definition_containers(document: str, out: list[str]) -> str:
    # Quote and list-item markers are container syntax: a definition inside `> ` or `- ` is still a definition and is
    # global to the document. Each peeled prefix becomes NUL (same length), so offsets are unchanged and the pattern
    # sees an ordinary line start. Fenced lines are already blanked; blanked comment text has no prefix to peel.
    # A list item's content continues on the lines after its marker: a non-blank line indented at least to the content
    # column of the deepest open item (within the same block quote) is inside that item, so that many columns are peeled.
    # A blank line keeps the items open; a line indented less closes the items it does not reach.
    pos = 0
    path: list[tuple[str, int]] = []
    item_ends: list[int] = []
    for raw in source_lines(document):
        body = raw.rstrip("\r\n")
        end = pos + len(body)
        source = block_line(body)
        line = block_line("".join(out[pos:end]))
        # Walk the open path once, retaining only fully continued items.
        remainder, last = source, 0
        for index, ancestor in enumerate(path):
            remainder = _continue_containers(remainder, (ancestor,))
            if remainder is None:
                break
            if ancestor[0] == "item":
                last = index + 1
        del path[last:]
        while item_ends and item_ends[-1] > last:
            item_ends.pop()
        inner = _continue_containers(line, path) if path else line
        # Blanking code/comments can remove a structural prefix, in which case
        # the line itself contains no live definition to peel.
        if inner is not None:
            added, rest = _container_path(inner)
            base = len(path)
            path.extend(added)
            item_ends.extend(base + index + 1 for index, (kind, _) in enumerate(added) if kind == "item")
            del path[item_ends[-1] if item_ends else 0:]
            # Four residual columns mean indented code, not a definition. For
            # 0..3 columns, a partially consumed tab can be blanked whole:
            # both spellings remain legal, and source offsets stay unchanged.
            indent = _indent_columns(rest)
            if indent < 4:
                columns = len(line) - len(rest) + indent
                prefix = source_prefix_chars(body, columns)
                out[pos:pos + prefix] = ["\x00"] * prefix
        pos += len(raw)
    return "".join(out)


def _whitespace_columns(text: str, target: int | None = None) -> tuple[int, int]:
    """(characters, columns) of the leading spaces and tabs of `text`, a tab advancing to the next multiple of four. The
    scan stops once `target` columns are covered (None: all leading whitespace); a tab that crosses the target is
    counted whole, so the characters can be peeled as one unit."""
    col = i = 0
    while i < len(text) and text[i] in " \t" and (target is None or col < target):
        col = col + 1 if text[i] == " " else (col // 4 + 1) * 4
        i += 1
    return i, col


def _inline_link_spans(document: str, fences: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    """Spans of resolved inline link destinations and titles, from `(` through the closing `)`, for the definition scan:
    an HTML comment or tag opener inside one is link text, not markup. Link-text openers are kept on a stack, and each
    `](` consumes one of them, whether or not its destination resolves, so a completed link's opener is never reused by
    a later `](`: an orphan destination opens no span. A blank line clears the stack (a paragraph boundary). Escaped and
    inline-code brackets are text and neither open nor consume. Computed in one pass; the spans are sorted and disjoint."""
    document = _source_view(document)
    spans: list[tuple[int, int]] = []
    html_spans = html_block_spans(document)  # raw HTML and fenced code are not link syntax
    openers: list[int] = []  # unconsumed unescaped `[` of the current paragraph, innermost last
    skip_until = 0  # text inside an accepted span is destination or title text: its brackets open nothing
    regions = inline_regions(document)
    autolinks = autolink_candidates(document)
    angles = autolink_candidates(document, bare=False)
    previous_region = None
    for token in re.finditer(r"\[|\]\(|\]|" + BLANK_LINE.pattern, document):
        at = token.start()
        if at < skip_until:
            continue
        region = _span_at(regions, at)
        if region != previous_region:
            openers.clear()
            previous_region = region
        if token.group().startswith(("\r", "\n")):
            openers.clear()  # a blank line ends the paragraph
            continue
        if region is None or _span_at(fences, at) is not None or _span_at(html_spans, at) is not None:
            continue
        if _escaped(document, at) or _in_inline_code(document, at):
            continue  # an escaped or code-span bracket is literal text
        autolink = _span_at(angles, at) or _span_at(autolinks, at)
        if (autolink is not None and not _in_inline_code(document, autolink[0])
                and (document[autolink[0]] == "<" or not openers)):
            continue  # URI/email contents cannot create a link opener or destination
        if token.group() == "[":
            openers.append(at)
        elif token.group() == "]":
            if openers:
                openers.pop()
        elif openers:  # `](` with an active opener: consume it, then read the destination
            openers.pop()
            target = _inline_image_target(document, at + 1)
            if target is not None:
                spans.append((at + 1, target[1]))
                skip_until = target[1]
    return tuple(spans)


def _balanced_destination(dest: str) -> bool:
    """CommonMark bare link destination: a backslash escapes the character after it (an escaped parenthesis does not
    count), and every unescaped `(` is closed by an unescaped `)` without the depth going below zero."""
    depth, i = 0, 0
    while i < len(dest):
        char = dest[i]
        if char == "\\":
            i += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


@functools.lru_cache(maxsize=16)
def _definitions(document: str) -> tuple:
    """Live reference definitions, as regex matches over the document-length candidate text. A definition cannot
    interrupt a paragraph (CommonMark), so a definition-like line that continues a paragraph is text; only a line that
    starts a block counts, plus a definition directly after another live definition. Definitions are decided before
    inline code, so a backtick in a definition destination pairs with nothing. A bare destination must have balanced
    unescaped parentheses (CommonMark); otherwise the line is ordinary Markdown. Computed once per document."""
    document = _source_view(document)
    continuation = continuation_starts(document)
    live: list = []
    for match in _raw_definition_matches(_definition_candidates(document), document):
        if not _definition_key(match, document):
            continue
        if match.group(3) is not None and not _balanced_destination(match.group(3)):
            continue  # a malformed bare destination is not a definition: the line stays ordinary Markdown
        if match.start() in continuation and not (live and after_line_end(document, live[-1].end()) == match.start()):
            continue
        live.append(match)
    return tuple(live)


@functools.lru_cache(maxsize=16)
def _definition_spans(document: str) -> tuple[tuple[int, int], ...]:
    """Spans of complete reference definitions (label, destination and title): their text is not Markdown. Computed
    once per document; the spans are sorted and never overlap."""
    return tuple((m.start(), m.end()) for m in _definitions(document))


class _HTMLTokens:
    """Raw HTML token spans and real img tags, sharing the inline precedence scan."""
    def __init__(self, text, document: str | None = None):
        text, document = _parse_views(text, document if document is not None else text)
        self.text = text
        self.tags = []
        self.images = []
        source = document if document is not None else text
        html_spans = html_block_spans(source)
        pos = 0
        tag = raw_html = None
        while True:
            if tag is not False and (tag is None or tag.start() < pos):
                tag = _search_unescaped(HTML_OPEN_TAG, text, pos, html_spans, source) or False
            if raw_html is not False and (raw_html is None or raw_html.start() < pos):
                raw_html = _search_raw_html(text, pos, source) or False
            matches = [match for match in (tag, raw_html) if match]
            if not matches:
                break
            match = min(matches, key=lambda match: match.start())
            start, end = match.span()
            pos = end
            self.tags.append((start, end))
            if match is tag and match.group(1).lower() == "img":
                first = {}
                for name, value in HTML_ATTR.findall(match.group(2)):
                    value = value[1:-1] if value[:1] in ("'", '"') and value else value
                    first.setdefault(name.lower(), html.unescape(value))
                self.images.append((first.get("alt") or "", first.get("src") or "", start, end))


def _fence_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Inert fenced and indented code blocks, with original source offsets."""
    return code_block_spans(text)


@functools.lru_cache(maxsize=16)
def _outside_code(text: str, mask_inline: bool = True) -> str:
    """Mask Markdown code, comments and autolinks without reading literal attribute backticks as code.
    Constructs are taken left to right, and inline code is looked for again after every HTML tag or comment, so a
    backtick inside an attribute or comment is literal and the next real code span still opens (CommonMark).
    `mask_inline=False` still lets inline code win precedence but leaves its characters readable (reference labels).
    Autolink contents stay masked; label validity and matching always read the original source.
    The result has the same length (and newline positions) as `text`."""
    text = _source_view(text)
    fences = _fence_spans(text)
    definitions = _definition_spans(text)  # decided before inline code: a definition destination's backtick is literal
    labels = _reference_label_spans(text)  # resolved full-reference labels: their backticks are literal too
    html_spans = html_block_spans(text)  # raw HTML blocks: tags there are never escaped by a backslash
    out, pos = list(text), 0
    tag = comment = raw_html = inline = dest = autolink = None

    def blank(a, b):
        for i in range(a, b):
            if out[i] not in "\r\n":
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
            comment = _search_comment(text, pos, html_spans) or False
        if raw_html is not False and (raw_html is None or raw_html.start() < pos):
            raw_html = _search_raw_html(text, pos) or False
        if autolink is not False and (autolink is None or autolink[0] < pos):
            autolink = _find_live_autolink(text, pos) or False
        n = bisect.bisect_left(fences, (pos, -1))
        fence = fences[n] if n < len(fences) else None
        d = bisect.bisect_left(definitions, (pos, -1))
        definition = definitions[d] if d < len(definitions) else None
        lb = bisect.bisect_left(labels, (pos, -1))
        label_span = labels[lb] if lb < len(labels) else None
        code = min([c for c in ((inline if inline else None), fence, autolink) if c], default=None)
        found = [m for m in (tag, comment, raw_html) if m]
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
            if mask_inline or code is fence or code is autolink:
                blank(*code)
            pos = code[1]
        elif nxt is not None:
            if nxt is comment:
                blank(*nxt.span())
            pos = nxt.end()
        else:
            break
    return "".join(out)


_BLANK_LINE_AT = re.compile(_NL + rf"[ \t\x00]*(?:{_NL}|\Z)")  # a newline that starts a blank line (or ends the text)


# Count inspected characters in bracket pairing so malformed-input regressions can
# assert bounded work without relying on machine-dependent timing.
_BRACKET_STEPS = 0


@functools.lru_cache(maxsize=16)
def _bracket_pairs(text: str, document: str | None = None) -> dict[int, int]:
    """Pair brackets in one bounded pass per canonical inline block.

    The masked copy keeps original offsets but cannot classify blocks itself:
    code masks may erase the syntax that caused a boundary in the source.
    Complete raw HTML tokens bind more tightly than description brackets; their
    literal text cannot open or close a description. Accepted nested link
    destinations and titles are likewise literal. Full reference labels use a
    separate raw lexical scan.
    """
    text, document = _parse_views(text, document if document is not None else text)
    global _BRACKET_STEPS
    pairs: dict[int, int] = {}
    source = document if document is not None else text
    autolinks = _live_autolinks(source)
    code = _raw_inline_code_spans(source)
    tags = _HTMLTokens(text, source).tags
    destinations = tuple(span for span in _accepted_inline(source)[3]
                         if source[span[0]:span[0] + 1] == "("
                         and source[span[0] - 1:span[0]] == "]")
    for lo, hi in inline_regions(source):
        stack: list[int] = []
        pos, limit = lo, min(hi, len(text))
        while pos < limit:
            _BRACKET_STEPS += 1
            destination = _span_at(destinations, pos)
            if destination is not None:
                pos = destination[1]
                continue
            link = _span_at(autolinks, pos)
            if link is not None and _span_at(code, link[0]) is None:
                pos = link[1]
                continue
            tag = _span_at(tags, pos)
            if tag is not None:
                pos = tag[1]
                continue
            char = text[pos]
            if char == "\\":
                pos += 2
                continue
            if char == "[":
                stack.append(pos)
            elif char == "]" and stack:
                pairs[stack.pop()] = pos
            pos += 1
    return pairs


def _closing_bracket(text: str, start: int, document: str | None = None) -> int | None:
    """Find a balanced closer in the same source inline block, without rescanning."""
    return _bracket_pairs(text, document).get(start)


# work counter of the opener pass: one per position advanced (an inert-region skip counts one) and one per call of
# `_has_link_opener`; the regression test reads and resets it
_OPENER_STEPS = 0
# work counter of destination parsing (`_inline_image_target`): one per raw or angle destination character read, per
# whitespace character skipped and per title lookup; the regression test reads and resets it
_DEST_STEPS = 0

def _block_boundary(text: str, newline: int, fences: tuple[tuple[int, int], ...], base: int = 0) -> bool:
    """Whether adjacent source lines belong to distinct canonical inline blocks.

    ``fences`` and ``base`` remain accepted for internal-call compatibility;
    mdcode's shared classifier already includes fences and ordered containers.
    """
    regions = inline_regions(text)
    before = _span_at(regions, newline)
    after = _span_at(regions, after_line_end(text, newline))
    # A bare blank line is handled as a paragraph break by callers; this
    # compatibility helper describes the end of actual inline content only.
    return before is not None and before != after


def _crosses_block(text: str, start: int, end: int, fences: tuple[tuple[int, int], ...],
                   document: str | None = None) -> bool:
    """Whether an inline construct would cross its canonical source block."""
    source = document if document is not None else text
    region = _span_at(inline_regions(source), start)
    return region is None or end >= region[1]


_BRACKET = re.compile(r"[][]")


def _next_unescaped_bracket(text: str, start: int, end: int) -> int:
    """Index of the first unescaped `[` or `]` in text[start:end], or -1. The scan stops at that bracket, so a label
    scan costs the length of the text it reads, and the scans of distinct closers do not overlap."""
    for match in _BRACKET.finditer(text, start, end):
        if not _escaped(text, match.start()):
            return match.start()
    return -1


@functools.lru_cache(maxsize=16)
def _label_prefix_index(text: str):
    """Source-aligned structural prefix positions for semantic label lengths."""
    positions = []
    prefixes = _layout(text)[5]
    for start in continuation_starts(text):
        length = prefixes.get(start, 0)
        if not length and (match := _QUOTE.match(text, start)):
            end = match.end()
            while next_match := _QUOTE.match(text, end):
                end = next_match.end()
            length = end - start
        positions.extend(range(start, start + length))
    return tuple(positions)


def _label_range(text: str, start: int, end: int) -> str | None:
    """Materialize a bounded semantic label while retaining source offsets elsewhere."""
    positions = _label_prefix_index(text)
    first = bisect.bisect_left(positions, start)
    last = bisect.bisect_left(positions, end)
    if end - start - (last - first) > 999:
        return None
    WORK['label_materialized_chars'] += end - start
    if first == last:
        return text[start:end]
    excluded = set(positions[first:last])
    return "".join(text[i] for i in range(start, end) if i not in excluded)


def _range_label_key(text: str, start: int, end: int) -> str:
    value = _label_range(text, start, end)
    return _label_key(value) if value is not None else ""


def _reference_form(text: str, open_idx: int, close: int, limit: int, keys: set) -> tuple[int | None, int | None] | None:
    """Reference-style link after the `]` at `close` whose `[` is at `open_idx`, or None. Returns (jump, label_close):
    `jump` is the index past the label's closing bracket (None for a shortcut, which does not jump) and `label_close`
    is that bracket's index (None for a shortcut). The label must be plain text before
    `limit`, the next inert region, so a jump never skips into one. A full reference's description may contain nested
    brackets; only collapsed/shortcut descriptions supply a label and need its lexical restrictions via `_label_key`.
    An inline `(dest)` is decided by the caller first, so a `(` here means the closer is not a shortcut."""
    if text[close + 1:close + 2] == "[":
        label_end = _next_unescaped_bracket(text, close + 2, limit)
        if label_end == -1:
            return None
        if label_end == close + 2 and text[label_end] == "]":  # collapsed `[text][]`
            if _range_label_key(text, open_idx + 1, close) in keys:
                return label_end + 1, label_end
            return None
        if text[label_end] == "]" and _range_label_key(text, close + 2, label_end) in keys:  # full `[text][label]`
            return label_end + 1, label_end
        return None
    if text[close + 1:close + 2] == "(":  # not a shortcut when a destination follows
        return None
    if _range_label_key(text, open_idx + 1, close) in keys:  # shortcut `[text]`
        return None, None
    return None


@functools.lru_cache(maxsize=16)
def _accepted_inline(text: str):
    """Active closing brackets and accepted autolinks from one precedence pass.

    A closing bracket has a matching ACTIVE `[` before it in the same paragraph.
    One left-to-right pass keeps a stack of active `[` indices. Fenced code, inline code, autolinks, HTML comments and HTML open
    tags (attribute values included) are inert, so a bracket inside them is text: it neither opens nor closes a link.
    An unescaped `]` that pops an opener and is directly followed by a destination `(...)` skips that destination,
    which is literal (a backtick in it opens no code span). A blank line clears the stack, and so does a block
    boundary from the shared source-aligned inline regions. This includes headings, ordered containers, list items,
    fences, raw HTML and table cells; plain soft lines in the same paragraph still pair. Raw HTML blocks (`html_block_spans`) are inert and are block boundaries: no `[` inside one opens
    a link, and the stack is cleared entering and leaving it. Completing an inline link deactivates every earlier LINK
    opener in the stack (CommonMark: links may not contain links), while earlier IMAGE openers stay active; a `barrier`
    marks the stack depth below which link openers are inactive, so that deactivation is O(1). Reference-style links
    `[x][ref]`, `[x][]` and `[x]` deactivate earlier link openers too when the label resolves to a live definition
    (`_reference_form`); an inline `(dest)` is tried first. The label of a full reference is read up to the next
    non-inline inert region, so a backtick in a resolved label is literal and an unresolved label is not consumed. Inert regions are found
    by cached lookups as in `_outside_code`, so the pass is linear. Offsets are the source offsets. It never calls
    `_outside_code`. Live reference definitions (`_definition_spans`) are inert block regions like raw HTML blocks: their brackets and backticks are literal, and the opener stack is cleared entering and leaving one."""
    text = _source_view(text)
    global _OPENER_STEPS
    WORK['inline_precedence_builds'] += 1
    fences = _fence_spans(text)
    html_spans = html_block_spans(text)
    defs = _definition_spans(text)  # live reference definitions: inert block regions, cached per document
    keys = {_definition_key(m, text) for m in _definitions(text)}  # live definition labels, computed once per call
    opened: set[int] = set()
    accepted_autolinks = []
    accepted_codes = []
    accepted_literals = []
    stack: list[tuple[int, bool]] = []  # (index of `[`, whether it opens an image `![`)
    barrier = 0  # stack positions below this hold inactive link openers (a link was completed after them)
    inline = tag = comment = raw_html = autolink = None  # cached next starts: None = not searched yet, False = none left
    n, pos = len(text), 0
    blocks = inline_regions(text)
    previous_block = None

    def next_inline(start):
        while True:
            found = _find_raw_inline_code(text, start)  # (start, end) or None
            if not found:
                return False
            inside = _span_at(fences, found[0])
            if inside is not None:
                start = inside[1]
                continue
            inside = _span_at(defs, found[0])  # a backtick inside a live definition is literal, not code
            if inside is not None:
                start = inside[1]
                continue
            return found

    while pos < n:
        block = _span_at(blocks, pos)
        if block != previous_block:
            stack.clear()
            barrier = 0
            previous_block = block
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
        definition = _span_at(defs, pos)
        if definition is not None:  # a live definition is not paragraph text: a block boundary, like raw HTML
            _OPENER_STEPS += 1
            accepted_literals.append(definition)
            pos = definition[1]
            stack.clear()
            barrier = 0
            continue
        if inline is not False and (inline is None or inline[0] < pos):
            inline = next_inline(pos)
        if tag is not False and (tag is None or tag.start() < pos):
            tag = _search_unescaped(HTML_OPEN_TAG, text, pos, html_spans) or False
        if comment is not False and (comment is None or comment.start() < pos):
            comment = _search_comment(text, pos, html_spans) or False
        if raw_html is not False and (raw_html is None or raw_html.start() < pos):
            raw_html = _search_raw_html(text, pos) or False
        if autolink is not False and (autolink is None or autolink[0] < pos):
            autolink = find_autolink(text, pos) or False
        k = bisect.bisect_left(fences, (pos, -1))
        regions = []
        if inline:
            regions.append(inline)
        if tag:
            regions.append(tag.span())
        if comment:
            regions.append(comment.span())
        if raw_html:
            regions.append(raw_html.span())
        if autolink:
            regions.append(autolink)
        if k < len(fences):
            regions.append(fences[k])
        h = bisect.bisect_left(html_spans, (pos, -1))
        if h < len(html_spans):
            regions.append(html_spans[h])
        d = bisect.bisect_left(defs, (pos, -1))  # the next live definition at or after `pos` (`pos` is outside all of them)
        if d < len(defs):
            regions.append(defs[d])
        region = min(regions) if regions else None  # the next inert region at or after `pos`
        following = bisect.bisect_left(blocks, (pos, -1))
        block_limit = block[1] if block else blocks[following][0] if following < len(blocks) else n
        limit = min(region[0] if region else n, block_limit)
        # the next inert region other than inline code: a backtick inside a reference label is literal, so the start of
        # an inline code span must not truncate the label scan of `_reference_form`
        ref_limit = block[1] if block else n
        if k < len(fences):
            ref_limit = min(ref_limit, fences[k][0])
        if h < len(html_spans):
            ref_limit = min(ref_limit, html_spans[h][0])
        if d < len(defs):
            ref_limit = min(ref_limit, defs[d][0])
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
                        accepted_literals.append((i + 1, target[1]))
                        jump = target[1]  # the destination of a completed link is literal text
                        if not is_image:  # completing a link deactivates every earlier link opener
                            barrier = len(stack)
                        break
                    # a backtick inside a reference label is literal, so the inline-code start must not truncate the label scan
                    form = _reference_form(text, open_idx, i, ref_limit, keys)
                    if form is not None:  # a reference-style link completes like an inline one
                        jump_to, label_close = form
                        if label_close is not None:  # the label's `]` is marked as the scan marks any active `]`
                            opened.add(label_close)
                        if not is_image:
                            barrier = len(stack)
                        if jump_to is not None:  # skip the label so its `[` never opens a link
                            accepted_literals.append((i + 1, jump_to))
                            jump = jump_to
                            break
            i += 1
        if jump is not None:
            pos = jump
        elif limit == block_limit and (region is None or limit < region[0]):
            pos = limit
        elif region is None:
            break
        else:
            if region == autolink:
                if text[region[0]] != "<" and stack:
                    # GFM's extension refuses URL autolinks while a bracket
                    # opener is pending, even if it never resolves to a link.
                    autolink = find_autolink(text, region[0] + 1) or False
                    pos = limit
                    continue
                accepted_autolinks.append(region)
            if region == inline:
                accepted_codes.append(region)
            elif (tag and region == tag.span()) or (raw_html and region == raw_html.span()):
                accepted_literals.append(region)
            _OPENER_STEPS += 1
            if k < len(fences) and region == fences[k]:  # a fence skipped as a region is a block boundary too
                stack.clear()
                barrier = 0
            elif h < len(html_spans) and region == html_spans[h]:  # so is a raw HTML block skipped as a region
                stack.clear()
                barrier = 0
            elif d < len(defs) and region == defs[d]:  # and so is a live definition (its own block boundary)
                accepted_literals.append(region)
                stack.clear()
                barrier = 0
            pos = region[1]
    return (frozenset(opened), tuple(accepted_autolinks),
            tuple(accepted_codes), tuple(accepted_literals))


def _inline_openers_and_autolinks(text: str):
    """Compatibility view of the canonical result's brackets and autolinks."""
    return _accepted_inline(_source_view(text))[:2]


_inline_openers_and_autolinks.cache_clear = _accepted_inline.cache_clear
_inline_openers_and_autolinks.cache_info = _accepted_inline.cache_info
_inline_openers_and_autolinks.cache_parameters = _accepted_inline.cache_parameters


def _active_openers(text: str) -> frozenset[int]:
    return _inline_openers_and_autolinks(text)[0]


# Preserve the existing cache-control interface while both views share one
# canonical precedence result (including work-counter resets in regressions).
_active_openers.cache_clear = _inline_openers_and_autolinks.cache_clear
_active_openers.cache_info = _inline_openers_and_autolinks.cache_info


def _live_autolinks(text: str) -> tuple[tuple[int, int], ...]:
    return _inline_openers_and_autolinks(text)[1]


def _find_live_autolink(text: str, start: int):
    spans = _live_autolinks(text)
    index = bisect.bisect_left(spans, (start, -1))
    return spans[index] if index < len(spans) else None


def _has_link_opener(text: str, close: int) -> bool:
    """True when the `]` at index `close` closes a link text: it is in the set of active closing brackets of `text`
    (see `_active_openers`). After the cached pass each call is one set lookup."""
    global _OPENER_STEPS
    _OPENER_STEPS += 1
    return close in _active_openers(text)


def _label_syntax(value: str) -> bool:
    """Full-label lexical validity, distinct from whether it names a definition."""
    return len(value) <= 999 and not any(char in "[]" and not _escaped(value, index)
                                         for index, char in enumerate(value))


def _label_key(value: str) -> str:
    """CommonMark reference matching folds case and whitespace, keeping escapes and entities literal."""
    value = value.replace("\x00", "\ufffd")
    if not _label_syntax(value):
        return ""  # CommonMark labels are at most 999 source characters.
    # cmark-gfm label matching collapses only SP, HT and line endings.
    # VT/FF and Unicode whitespace remain significant raw label characters.
    return re.sub(r"[ \t\r\n]+", " ", value.strip(" \t\r\n")).casefold()


def _definition_key(match: re.Match, document: str) -> str:
    """Peeled container/indent prefixes are separators, never literal label NULs."""
    start = match.start(1)
    label = "".join("" if char == "\x00" and document[start + i] != "\x00" else char
                    for i, char in enumerate(match.group(1)))
    return _label_key(label)


@functools.lru_cache(maxsize=16)
def _reference_label_spans(document: str) -> tuple[tuple[int, int], ...]:
    """Label text of each resolved full reference (`[text][label]`): the characters between the brackets of the second
    pair. Only a label that names a live definition is a reference, so its backticks are literal; an unresolved label
    stays readable for inline code. Junctions inside fences or definitions are text. Computed once per document;
    the spans are sorted and never overlap."""
    document = _source_view(document)
    keys = {_definition_key(m, document) for m in _definitions(document)}
    fences = code_block_spans(document)
    definitions = _definition_spans(document)
    spans = []
    for junction in re.finditer(r"\]\[", document):
        at = junction.start()
        if _escaped(document, at) or _span_at(fences, at) is not None or _span_at(definitions, at) is not None:
            continue
        if at not in _active_openers(document):
            continue  # the first `]` closes no link text (an orphan junction): `[label]` is a shortcut, not a full reference
        open_ = at + 1
        # Full reference labels are raw lexical text: HTML-looking brackets
        # close or invalidate them even though HTML is inert in descriptions.
        region = _span_at(inline_regions(document), open_)
        close = _next_unescaped_bracket(document, open_ + 1, region[1]) if region else -1
        if close < 0 or document[close] != "]":
            continue
        label = _label_range(document, open_ + 1, close)
        if label is None or not _label_key(label) or BLANK_LINE.search(label):
            continue  # an empty label or one spanning a blank line is not a reference label
        first_fence = bisect.bisect_left(fences, (open_ + 1, -1))
        if first_fence < len(fences) and fences[first_fence][0] < close:
            continue  # a fenced block cannot sit inside a link label
        if _label_key(label) in keys:
            spans.append((open_ + 1, close))
    return tuple(spans)


@functools.lru_cache(maxsize=16)
def _blank_line_starts(text: str) -> tuple[int, ...]:
    """Sorted start offsets of every paragraph boundary (a newline that starts a blank line), from one regex pass."""
    return tuple(match.start() for match in BLANK_LINE.finditer(text))


def _blank_between(text: str, a: int, b: int) -> bool:
    """True when a paragraph boundary starts at an offset in [a, b): a bisection over the cached boundary list."""
    starts = _blank_line_starts(text)
    at = bisect.bisect_left(starts, a)
    return at < len(starts) and starts[at] < b


@functools.lru_cache(maxsize=16)
def _title_ends(text: str) -> dict[str, tuple[int, ...]]:
    """Sorted positions of the unescaped `"`, `'`, `)` and `(` in `text`, from one linear pass. An occurrence is escaped when
    an odd number of backslashes directly precedes it: the parity the destination scanner's skip-two loop produces."""
    found: dict[str, list[int]] = {'"': [], "'": [], ")": [], "(": []}
    backslashes = 0  # length of the run of backslashes directly before the current position
    for index, char in enumerate(text):
        if char == "\\":
            backslashes += 1
            continue
        if char in found and backslashes % 2 == 0:
            found[char].append(index)
        backslashes = 0
    return {char: tuple(positions) for char, positions in found.items()}


@functools.lru_cache(maxsize=16)
def _quote_continuation_view(text: str) -> str:
    """Mask quote prefixes on paragraph continuation lines without shifting offsets."""
    chars = None
    prefixes = _layout(text)[5]
    for line_start in continuation_starts(text):
        length = prefixes.get(line_start, 0)
        # Tables retain their existing simple quote-prefix handling.
        if not length and (match := _QUOTE.match(text, line_start)):
            end = match.end()
            while next_match := _QUOTE.match(text, end):
                end = next_match.end()
            length = end - line_start
        if length:
            if chars is None:
                chars = list(text)
            chars[line_start:line_start + length] = " " * length
    return "".join(chars) if chars is not None else text


def _inline_image_target(text: str, start: int) -> tuple[str, int] | None:
    """Read a Markdown destination and optional title after its opening parenthesis. Destination nesting deeper than
    32 parentheses is no link (CommonMark's limit), which bounds each call and keeps the opener pass linear."""
    text = _source_view(text)
    global _DEST_STEPS
    original = text
    region = _span_at(_layout(text)[0], start)
    text = _quote_continuation_view(text)
    pos = start + 1
    while pos < len(text) and text[pos] in _LINK_SPACE:
        _DEST_STEPS += 1
        pos += 1
    if _blank_between(text, start + 1, pos):  # (a) a paragraph boundary before the destination
        return None
    begin = pos
    if pos < len(text) and text[pos] == "<":
        begin = pos = pos + 1
        while pos < len(text) and text[pos] != ">":
            _DEST_STEPS += 1
            if text[pos] in "\r\n<":
                return None
            pos += 2 if text[pos] == "\\" and text[pos + 1:pos + 2] in _ESCAPABLE else 1
        if pos >= len(text):
            return None
        target = text[begin:pos]
        pos += 1
    else:
        depth = 0
        while pos < len(text):
            _DEST_STEPS += 1
            char = text[pos]
            if char == "\\" and text[pos + 1:pos + 2] in _ESCAPABLE:
                pos += 2
                continue
            if ord(char) <= 32 or ord(char) == 127 or char == ")" and depth == 0:
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
    dest_end = pos
    while pos < len(text) and text[pos] in _LINK_SPACE:
        _DEST_STEPS += 1
        pos += 1
    if _blank_between(text, dest_end, pos):  # (b) a boundary before the title, or before `)` when there is no title
        return None
    if pos < len(text) and text[pos] in "\"'(":
        # A title is separated from its destination by whitespace. Without
        # that separator an angle destination followed by quotes is no link,
        # so any Markdown inside those quotes remains rendered content.
        if pos == dest_end:
            return None
        end = ")" if text[pos] == "(" else text[pos]
        pos += 1
        _DEST_STEPS += 1  # one title lookup, not one step per character it passes over
        ends = _title_ends(text)[end]
        at = bisect.bisect_left(ends, pos)  # the first unescaped end character at or after the title start
        if at == len(ends):
            return None
        if end == ")":  # a parenthesized title may not hold an unescaped `(`: the link is then no link (CommonMark 6.3)
            opens = _title_ends(text)["("]
            first_open = bisect.bisect_left(opens, pos)
            if first_open < len(opens) and opens[first_open] < ends[at]:
                return None
        if _blank_between(text, pos, ends[at]) or _crosses_block(original, pos, ends[at], _fence_spans(original)):
            return None  # (c) a title may span soft line breaks, never a paragraph or block boundary (heading, list, fence)
        title_close = pos = ends[at] + 1
        while pos < len(text) and text[pos] in _LINK_SPACE:
            _DEST_STEPS += 1
            pos += 1
        if _blank_between(text, title_close, pos):  # (d) the whitespace after the title, up to `)`
            return None
    if pos >= len(text) or text[pos] != ")":
        return None
    if region is None or pos >= region[1]:
        return None  # destination whitespace cannot join separate Markdown blocks either
    return _destination_value(target), pos + 1


@functools.lru_cache(maxsize=16)
def _link_literal_spans(document: str) -> tuple[tuple[int, int], ...]:
    """Spans of resolved inline link destinations and titles, from `(` through the closing `)`. This text is literal: a
    `![...](...)` inside a link title renders no image, while a linked image in the link text is not covered. The spans
    are sorted and never overlap, because `_active_openers` skips a completed destination."""
    document = _source_view(document)
    spans = []
    for i in sorted(_active_openers(document)):
        if document[i + 1:i + 2] != "(":
            continue
        target = _inline_image_target(document, i + 1)
        if target is not None:
            spans.append((i + 1, target[1]))
    return tuple(sorted(spans))


def _markdown_images(text: str, document: str) -> list[tuple[str, str, int, int]]:
    """Read inline and reference images with balanced alt text; definitions use first-wins labels."""
    text, document = _parse_views(text, document)
    definitions = {}
    for match in _definitions(document):
        destination = match.group(2) if match.group(2) is not None else match.group(3)
        target = _destination_value(destination)
        definitions.setdefault(_definition_key(match, document), target)
    spans = _definition_spans(document)  # definition titles are never rendered as images
    html_spans = html_block_spans(document)  # raw HTML blocks are literal: Markdown image syntax there is text
    link_spans = _link_literal_spans(document)  # a link destination or title is literal text, never a rendered image
    # once per call: block boundaries inside alt text and labels. Fences come from the written document (the masked copy
    # blanks fenced lines, and `_layout` is then built once per document, not once per copy)
    fences = _fence_spans(document if len(document) >= len(text) else text)
    sources = []
    consumed = 0
    for match in re.finditer(r"!\[", text):
        if match.start() < consumed:
            continue
        if _span_at(spans, match.start()) or _span_at(html_spans, match.start()):
            continue
        if _span_at(link_spans, match.start()) is not None:
            continue
        pos = match.start() - 1
        while pos >= 0 and text[pos] == "\\":
            pos -= 1
        if (match.start() - pos - 1) % 2:
            continue  # an escaped exclamation mark is text, not an image
        close = _closing_bracket(text, match.start() + 1, document)
        if close is None:
            continue
        if _crosses_block(text, match.end(), close, fences, document):
            continue  # alt text cannot hold a heading, list item, fence or quote start: no image forms there
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
        key = _range_label_key(document, match.end(), close) if len(document) >= len(text) else _label_key(alt)
        if after < len(text) and text[after] == "[":
            # A reference label is raw lexical text, not rendered inline text.
            # In particular a `]` inside a URI closes the label even though it
            # is inert while reading an image's alt text. A nested `[` makes
            # the full label invalid and leaves the shortcut available.
            source = document if len(document) >= len(text) else text
            region = _span_at(inline_regions(source), after)
            ref_close = _next_unescaped_bracket(source, after + 1, region[1]) if region else -1
            if ref_close < 0 or source[ref_close] != "]":
                ref_close = None
            # a label holding a block boundary is no label: the shortcut form below still applies, as CommonMark has it
            if ref_close is not None and not _crosses_block(text, after + 1, ref_close, fences, document):
                label = _label_range(source, after + 1, ref_close)
                if label is not None and _label_syntax(label):  # invalid labels leave the shortcut and following text visible
                    key = _label_key(label) if label else key
                    after = ref_close + 1
        if key in definitions:
            sources.append((alt, definitions[key], match.start(), after))
            consumed = after
    return sources


def _images(text: str, document: str) -> list[tuple[str, str]]:
    """Read HTML and Markdown images, excluding Markdown-looking text in HTML attributes."""
    text, document = _parse_views(text, document)
    parser = _HTMLTokens(text, document)
    markdown = _markdown_images(text, document)
    # Angle-delimited destinations (and HTML in alt text) belong to their Markdown image,
    # while a Markdown-looking string wholly inside a real HTML tag is attribute text.
    # Both comparisons are interval lookups over sorted, non-overlapping spans (bisection), never a cross product.
    image_spans = [(mstart, mend) for _, _, mstart, mend in markdown]

    def inside(spans, start, end):
        span = _span_at(spans, start)
        return span is not None and end <= span[1]

    link_spans = _link_literal_spans(document)  # tags and images inside a link destination or title are literal text
    label_spans = _reference_label_spans(document)  # a resolved full reference's second label is not rendered
    tags = [(start, end) for start, end in parser.tags if not inside(image_spans, start, end)
            and _span_at(link_spans, start) is None and _span_at(label_spans, start) is None]
    def written_alt(alt, start):
        # `text` has Markdown code masked to spaces (same length): read code-formatted alt text from the document
        begin = start + 2
        return document[begin:begin + len(alt)] if len(document) >= begin + len(alt) else alt

    spans = _definition_spans(document)
    def in_definition(start):
        return _span_at(spans, start) is not None
    def in_link_literal(start):
        return _span_at(link_spans, start) is not None
    result = [(written_alt(alt, start), source) for alt, source, start, end in markdown
              if not in_definition(start) and not inside(tags, start, end) and not in_link_literal(start)]
    kept = set(tags)
    result += [(alt, source) for alt, source, start, end in parser.images
               if (start, end) in kept and not in_definition(start) and not in_link_literal(start)]
    return result



def find_inline_code(text: str, start: int = 0) -> tuple[int, int] | None:
    """First accepted code span at/after `start`, after canonical inline precedence."""
    spans = inline_code_spans(text)
    at = bisect.bisect_left(spans, (start, -1))
    return spans[at] if at < len(spans) else None


def inline_code_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Accepted code spans shared by marker projection and image checking."""
    return _accepted_inline(_source_view(text))[2]


def _clear_inline_code_cache():
    # The public view's reset covers the raw bootstrap and accepted decisions,
    # preserving existing cold-cache work measurements after core factoring.
    _raw_inline_code_spans.cache_clear()
    _accepted_inline.cache_clear()
    _marker_projection.cache_clear()


inline_code_spans.cache_clear = _clear_inline_code_cache
inline_code_spans.cache_info = _accepted_inline.cache_info
inline_code_spans.cache_parameters = _accepted_inline.cache_parameters


@functools.lru_cache(maxsize=16)
def _marker_projection(text: str) -> str:
    """Hide code and accepted literal data, retaining real HTML marker comments.

    This is only a source-aligned projection of the canonical parser result.
    General `masked` keeps HTML structure visible to README/footer callers.
    """
    source = _source_view(text)
    parsed = _accepted_inline(source)
    spans = list(code_block_spans(source)) + list(parsed[1]) + list(parsed[2]) + list(parsed[3])
    # The main inline pass skips raw HTML blocks. Their tag attributes still
    # contain literal data, whereas real marker comments must remain visible.
    blocks = html_block_spans(source)
    for span in _HTMLTokens(source).tags:
        block = _span_at(blocks, span[0])
        if block is not None and span[1] <= block[1]:
            spans.append(span)
    out = list(text)
    # Merge overlapping projections before blanking: nested tags/literals must
    # not make work grow with their overlap depth.
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in merged:
        WORK['marker_projection_chars'] += end - start
        for at in range(start, end):
            if out[at] not in "\r\n":
                out[at] = "\x00"
    return "".join(out)
