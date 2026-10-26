"""Markdown code spans, so marker searches skip documented examples. Stdlib only and imports nothing from the package:
`readme` (and through it `readmelint` and `footer`) and the stdlib-only `meta` find marker blocks the same way."""
from __future__ import annotations

import re

# CommonMark: a backtick fence's info string has no backtick, so "```npm test``` runs" is inline code, not a fence
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,})")
INLINE_CODE = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)")


def code_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of fenced code (``` and ~~~, an unclosed fence runs to the end) and inline code spans."""
    spans, pos, fence, fstart = [], 0, None, 0
    for line in text.splitlines(keepends=True):
        if fence is None:
            m = FENCE_OPEN.match(line)
            if m:
                fence, fstart = m.group(1), pos
            else:
                spans += [(pos + c.start(), pos + c.end()) for c in INLINE_CODE.finditer(line)]
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
