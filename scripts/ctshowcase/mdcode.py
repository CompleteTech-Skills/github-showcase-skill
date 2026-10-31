"""Markdown code spans, so marker searches skip documented examples. Stdlib only and imports nothing from the package:
`readme` (and through it `readmelint` and `footer`) and the stdlib-only `meta` find marker blocks the same way.
CommonMark escaping: the parity of the backslashes directly before a backtick decides escaping (odd = escaped,
even = real), for any number of backslashes. Paragraph boundaries follow CommonMark and GitHub: blank lines, fences,
ATX headings, thematic and setext lines, list items (bullets, and ordered items that start at 1), block quote lines
only when the paragraph is not already in a quote, and HTML blocks of types 1-6 (type 7 cannot interrupt a
paragraph). Link and image destinations are literal: a backtick inside `](...)` is neither an opener nor a closer."""
from __future__ import annotations

import re

# CommonMark: a backtick fence's info string has no backtick, so "```npm test``` runs" is inline code, not a fence
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,})")
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t\r\n]|$)")
_THEMATIC = re.compile(r"^ {0,3}([-*_])[ \t]*(\1[ \t]*){2,}$")
_SETEXT = re.compile(r"^ {0,3}=+[ \t]*$")
_QUOTE_START = re.compile(r"^ {0,3}>")
_QUOTE_MARK = re.compile(r"^ {0,3}>[ \t]?")
_ITEM_START = re.compile(r" {0,3}(?:[-+*]|1[.)])[ \t]+\S")  # interrupts a paragraph at its own indentation
_ITEM_NESTED = re.compile(r"[ \t]*(?:[-+*]|1[.)])[ \t]+\S")  # interrupts a paragraph inside a list: any indentation
_LIST_ITEM = re.compile(r"[ \t]*(?:[-+*]|\d{1,9}[.)])[ \t]+\S")  # a paragraph whose first line is a list item
_HTML_START = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^ {0,3}<(script|pre|style|textarea)([\s>]|$)",  # type 1
        r"^ {0,3}<!--",  # type 2
        r"^ {0,3}<\?",  # type 3
        r"^ {0,3}<![A-Za-z]",  # type 4
        r"^ {0,3}<!\[CDATA\[",  # type 5
        r"^ {0,3}</?(address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details"
        r"|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html"
        r"|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary"
        r"|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(\s|/?>|$)",  # type 6
    )
)


def _run_end(text: str, i: int) -> int:
    """Index just past the backtick run that starts at `i`."""
    j = i
    while j < len(text) and text[j] == "`":
        j += 1
    return j


def _escaped(text: str, j: int) -> bool:
    """True when the character at `j` is preceded by an odd number of backslashes."""
    n = 0
    while j - n > 0 and text[j - n - 1] == "\\":
        n += 1
    return n % 2 == 1


def _line_at(text: str, start: int) -> str:
    """The line that begins at `start`, without its newline."""
    eol = text.find("\n", start)
    return text[start:] if eol < 0 else text[start:eol]


def _block_body(line: str, in_quote: bool) -> str:
    """`line` without its newline and, when `in_quote`, without its '>' quote prefixes."""
    body = line.rstrip("\r\n")
    if in_quote:
        m = _QUOTE_MARK.match(body)
        while m:
            body = body[m.end():]
            m = _QUOTE_MARK.match(body)
    return body


def _is_rule(body: str) -> bool:
    """A thematic break or a setext underline: a line of its own that never contains a backtick."""
    return bool(_THEMATIC.match(body) or _SETEXT.match(body))


def _standalone(body: str) -> bool:
    """A line that is not paragraph text: a fence opener, an ATX heading, or a thematic or setext line."""
    return bool(FENCE_OPEN.match(body) or _ATX_HEADING.match(body) or _is_rule(body))


def _paragraph_in_quote(first_line: str) -> bool:
    """True when a paragraph whose first line is `first_line` is already inside a block quote."""
    return bool(_QUOTE_START.match(first_line))


def _paragraph_in_list(first_line: str) -> bool:
    """True when a paragraph whose first line is `first_line` starts with a list marker (inside a quote, if any)."""
    return bool(_LIST_ITEM.match(_block_body(first_line, _paragraph_in_quote(first_line))))


def _interrupts(line: str, in_quote: bool, in_list: bool) -> bool:
    """True when `line` is a block boundary: blank, a fence opener, an ATX heading, a thematic or setext line, a list
    item start, a block quote start (only when not `in_quote`) or an HTML block start of types 1-6. This is the single
    block-boundary rule: `_paragraph_end` and `code_spans` both call it. `in_quote` and `in_list` describe the
    paragraph the line would interrupt. With `in_quote` the '>' prefixes are stripped first, so a continued quote line
    stays in its paragraph. Only ordered items that start at 1 interrupt a paragraph; nested items (`in_list`) may be
    indented."""
    body = _block_body(line, in_quote)
    if not body.strip() or _standalone(body):
        return True
    if (_ITEM_NESTED if in_list else _ITEM_START).match(body):
        return True
    if not in_quote and _QUOTE_START.match(body):
        return True
    return any(p.match(body) for p in _HTML_START)


def _paragraph_start(text: str, pos: int) -> int:
    """Offset of the first line of the paragraph whose line holds `pos`. Walks back to the start of the run of
    non-blank lines, then replays the block rules forward from there: a standalone line is not paragraph text, and
    any other line that `_interrupts` opens a new paragraph. Returns the line start of `pos` when no paragraph
    text precedes it."""
    target = text.rfind("\n", 0, pos) + 1
    run = target
    while run > 0:
        prev = text.rfind("\n", 0, run - 1) + 1
        if not text[prev:run].strip():
            break
        run = prev
    first, first_line = None, ""  # offset and text of the current paragraph's first line
    start = run
    while True:
        eol = text.find("\n", start)
        line = _line_at(text, start)
        quote = _paragraph_in_quote(first_line)
        body = _block_body(line, quote)
        if not body.strip() or _standalone(body):
            first, first_line = None, ""
        elif first is None or _interrupts(line, quote, _paragraph_in_list(first_line)):
            first, first_line = start, line
        if start >= target or eol < 0:
            break
        start = eol + 1
    return target if first is None else first


def _paragraph_end(text: str, pos: int) -> int:
    """Index where the paragraph containing `pos` ends: the start of the first later line that `_interrupts`, judged
    with the paragraph's own quote and list context. A heading line containing `pos` ends at its own line end.
    Otherwise len(text)."""
    line_start = text.rfind("\n", 0, pos) + 1
    if _ATX_HEADING.match(text[line_start:pos]):
        eol = text.find("\n", pos)
        return len(text) if eol < 0 else eol
    first = _line_at(text, _paragraph_start(text, pos))
    quote, in_list = _paragraph_in_quote(first), _paragraph_in_list(first)
    nl = text.find("\n", pos)
    while nl >= 0:
        start = nl + 1
        if _interrupts(_line_at(text, start), quote, in_list):
            return start
        nl = text.find("\n", start)
    return len(text)


def _skip_space(text: str, m: int, limit: int) -> int:
    while m < limit and text[m] in " \t\r\n":
        m += 1
    return m


def _after_destination(text: str, m: int, limit: int) -> int | None:
    """Index just past the ')' that closes a link destination ending at `m`: optional whitespace, an optional title,
    then ')'. None when the destination is malformed."""
    m = _skip_space(text, m, limit)
    if m < limit and text[m] == ")":
        return m + 1
    if m < limit and text[m] in "\"'(":
        close = ")" if text[m] == "(" else text[m]
        n = m + 1
        while n < limit and text[n] != close:
            n += 2 if text[n] == "\\" else 1
        if n < limit:
            n = _skip_space(text, n + 1, limit)
            if n < limit and text[n] == ")":
                return n + 1
    return None


def _destination_end(text: str, j: int) -> int | None:
    """For the `](` whose ']' is at `j`: the index just past the ')' of a well-formed link or image destination, else
    None. The marker counts only when its ']' is unescaped and an unescaped '[' precedes it in the same paragraph.
    The destination is literal: '<...>' on one line, or a run without whitespace whose parentheses balance, then an
    optional title."""
    if _escaped(text, j):
        return None
    para = _paragraph_start(text, j)
    if not any(text[k] == "[" and not _escaped(text, k) for k in range(para, j)):
        return None
    limit = _paragraph_end(text, j)
    k = j + 2
    while k < limit and text[k] in " \t":
        k += 1
    if k < limit and text[k] == "<":
        m = k + 1
        while m < limit and text[m] not in "<>\n":
            m += 2 if text[m] == "\\" else 1
        if m >= limit or text[m] != ">":
            return None
        return _after_destination(text, m + 1, limit)
    depth, m = 0, k
    while m < limit and text[m] not in " \t\r\n":
        c = text[m]
        if c == "\\":
            m += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                return m + 1
            depth -= 1
        m += 1
    if m >= limit or depth:
        return None
    return _after_destination(text, m, limit)


def _next_backtick(text: str, i: int, stop: int | None = None) -> int:
    """Index of the first backtick at or after `i` (and before `stop`, if given) that is not inside a well-formed link
    or image destination. -1 when there is none."""
    end = len(text) if stop is None else stop
    while True:
        tick = text.find("`", i, end)
        marker = text.find("](", i, end if tick < 0 else tick)
        if marker < 0:
            return tick
        dest = _destination_end(text, marker)
        i = dest if dest is not None else marker + 1


def _closing_run(text: str, pos: int, k: int) -> tuple[int, int] | None:
    """First maximal backtick run of exactly `k` backticks at or after `pos` and before the paragraph ends, outside
    any link destination."""
    limit = _paragraph_end(text, pos)
    while True:
        p = _next_backtick(text, pos, limit)
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
    content must be non-empty. It may span single newlines within one paragraph, but not a block boundary (see
    `_interrupts`), so the closing run must come before the paragraph ends. Backticks inside a link or image
    destination are literal and never open or close a span."""
    i = start
    while True:
        i = _next_backtick(text, i)
        if i < 0:
            return None
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
        closer = _closing_run(text, j, j - run_start)
        if closer is not None:
            return run_start, closer[1]
        i = j


def code_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of fenced code (``` and ~~~, an unclosed fence runs to the end) and inline code spans."""
    spans, pos, fence, fstart = [], 0, None, 0
    chunk, cstart = "", 0  # pending paragraph text outside fences, and its absolute start offset
    in_quote = in_list = False  # the pending paragraph's quote and list context, from its first line
    for line in text.splitlines(keepends=True):
        if fence is None:
            if chunk and not _interrupts(line, in_quote, in_list):
                chunk += line
            else:
                rule = _is_rule(_block_body(line, in_quote))
                _scan_chunk(chunk, cstart, spans)
                chunk, in_quote, in_list = "", False, False
                m = FENCE_OPEN.match(line)
                if m:
                    fence, fstart = m.group(1), pos
                elif not line.strip():
                    pass
                elif _ATX_HEADING.match(line):
                    _scan_chunk(line, pos, spans)
                elif not rule:
                    cstart, chunk = pos, line
                    in_quote, in_list = _paragraph_in_quote(line), _paragraph_in_list(line)
        else:
            close = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", line.rstrip("\n"))
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= len(fence):
                spans.append((fstart, pos + len(line)))
                fence = None
        pos += len(line)
    if fence is not None:
        spans.append((fstart, len(text)))
    else:
        _scan_chunk(chunk, cstart, spans)
    return spans


def _scan_chunk(chunk: str, base: int, spans: list[tuple[int, int]]) -> None:
    """Append the inline code spans of `chunk`, a run of non-fence lines, as absolute offsets (`chunk` starts at
    `base`)."""
    at = 0
    while True:
        span = find_inline_code(chunk, at)
        if span is None:
            return
        spans.append((base + span[0], base + span[1]))
        at = span[1]


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
