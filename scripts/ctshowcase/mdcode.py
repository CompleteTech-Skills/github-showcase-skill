"""Markdown code spans, so marker searches skip documented examples. Stdlib only and imports nothing from the package:
`readme` (and through it `readmelint` and `footer`) and the stdlib-only `meta` find marker blocks the same way.
CommonMark escaping: the parity of the backslashes directly before a backtick decides escaping (odd = escaped,
even = real), for any number of backslashes."""
from __future__ import annotations

import re

# CommonMark: a backtick fence's info string has no backtick, so "```npm test``` runs" is inline code, not a fence
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,})")
# Compatibility name only: readmelint still searches with it until it calls find_inline_code. Its one-backslash
# lookbehind does not implement the parity rule, so new callers must use find_inline_code instead.
INLINE_CODE = re.compile(r"(?<!(?<!\\)\\)(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)")


def _run_end(text: str, i: int) -> int:
    """Index just past the backtick run that starts at `i`."""
    j = i
    while j < len(text) and text[j] == "`":
        j += 1
    return j


def _closing_run(text: str, pos: int, k: int) -> tuple[int, int] | None:
    """First maximal backtick run of exactly `k` backticks at or after `pos`, found before the line ends."""
    while True:
        p = text.find("`", pos)
        if p < 0 or text.find("\n", pos, p) >= 0:
            return None
        q = _run_end(text, p)
        if q - p == k:
            return p, q
        pos = q


def find_inline_code(text: str, start: int = 0) -> tuple[int, int] | None:
    """(start, end) of the first CommonMark inline code span whose opening run begins at or after `start`. The span
    runs from the opening backtick run to the end of its closing run; escaping backslashes are not part of it. A
    backtick preceded by an odd number of backslashes is escaped, so its run starts one character later. The
    content must be non-empty and contain no newline."""
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
    for line in text.splitlines(keepends=True):
        if fence is None:
            m = FENCE_OPEN.match(line)
            if m:
                fence, fstart = m.group(1), pos
            else:
                at = 0
                while True:
                    span = find_inline_code(line, at)
                    if span is None:
                        break
                    spans.append((pos + span[0], pos + span[1]))
                    at = span[1]
        else:
            close = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", line.rstrip("\n"))
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= len(fence):
                spans.append((fstart, pos + len(line)))
                fence = None
        pos += len(line)
    if fence is not None:
        spans.append((fstart, len(text)))
    return spans


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
