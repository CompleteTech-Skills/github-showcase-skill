"""Markdown code spans, so marker searches skip documented examples. Stdlib only and imports nothing from the package:
`readme` (and through it `readmelint` and `footer`) and the stdlib-only `meta` find marker blocks the same way.
CommonMark escaping: the parity of the backslashes directly before a backtick decides escaping (odd = escaped,
even = real), for any number of backslashes."""
from __future__ import annotations

import re

# CommonMark: a backtick fence's info string has no backtick, so "```npm test``` runs" is inline code, not a fence
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,})")
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t\r\n]|$)")


def _run_end(text: str, i: int) -> int:
    """Index just past the backtick run that starts at `i`."""
    j = i
    while j < len(text) and text[j] == "`":
        j += 1
    return j


def _paragraph_end(text: str, pos: int) -> int:
    """Index where the paragraph containing `pos` ends: the start of the first later line that is blank, a fence
    opener or an ATX heading. A heading line containing `pos` ends at its own line end. Otherwise len(text)."""
    line_start = text.rfind("\n", 0, pos) + 1
    if _ATX_HEADING.match(text[line_start:pos]):
        eol = text.find("\n", pos)
        return len(text) if eol < 0 else eol
    nl = text.find("\n", pos)
    while nl >= 0:
        start = nl + 1
        eol = text.find("\n", start)
        line = text[start:] if eol < 0 else text[start:eol]
        if not line.strip(" \t\r") or FENCE_OPEN.match(line) or _ATX_HEADING.match(line):
            return start
        if eol < 0:
            break
        nl = eol
    return len(text)


def _closing_run(text: str, pos: int, k: int) -> tuple[int, int] | None:
    """First maximal backtick run of exactly `k` backticks at or after `pos` and before the paragraph ends."""
    limit = _paragraph_end(text, pos)
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
    content must be non-empty. It may span single newlines within one paragraph, but not a blank line, a fence
    opener line or an ATX heading line, so the closing run must come before any of those."""
    i = start
    while True:
        i = text.find("`", i)
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
    for line in text.splitlines(keepends=True):
        if fence is None:
            m = FENCE_OPEN.match(line)
            if m:
                _scan_chunk(chunk, cstart, spans)
                chunk = ""
                fence, fstart = m.group(1), pos
            elif not line.strip():
                _scan_chunk(chunk, cstart, spans)
                chunk = ""
            elif _ATX_HEADING.match(line):
                _scan_chunk(chunk, cstart, spans)
                _scan_chunk(line, pos, spans)
                chunk = ""
            else:
                if not chunk:
                    cstart = pos
                chunk += line
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
