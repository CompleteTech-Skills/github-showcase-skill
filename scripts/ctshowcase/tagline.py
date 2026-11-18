"""Stdlib-only tagline receipts shared by rendering, metadata and lint.

Normalize transport line endings only: whitespace inside the payload is evidence.
A receipt detects edits; it is not a signature or proof against intentional forgery.
"""
from __future__ import annotations

import hashlib
import re

RECEIPT = re.compile(r"<!-- showcase:tagline:generated sha256=([0-9a-f]{64}) -->\n(.*)", re.S)
NOTICE = re.compile(r"<!--\s*showcase:tagline:generated\b", re.I)


def normalize(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n")


def digest(payload: str) -> str:
    return hashlib.sha256(normalize(payload).encode("utf-8")).hexdigest()


def marked(body: str) -> bool:
    """Receipt-like text blocks every legacy fallback, even when malformed."""
    return NOTICE.search(body) is not None


def generated(payload: str) -> str:
    return f"<!-- showcase:tagline:generated sha256={digest(payload)} -->\n{payload}"


def payload(body: str) -> str | None:
    """Return the verified payload; None means legacy, edited, or malformed."""
    source = normalize(body)
    match = RECEIPT.fullmatch(source)
    if match is None or marked(match.group(2)) or digest(match.group(2)) != match.group(1):
        return None
    return match.group(2)


def _visible_payload(value: str) -> str:
    lines = value.split("\n")
    start, end = 0, len(lines)
    while start < end and not lines[start].strip(" \t"):
        start += 1
    while start < end and not lines[end - 1].strip(" \t"):
        end -= 1
    return "\n".join(lines[start:end])


def visible(body: str) -> str | None:
    """Read the verified body without outer blank lines added by a formatter."""
    verified = payload(body)
    return _visible_payload(verified) if verified is not None else None


def inherited_payload(body: str) -> str | None:
    """Return exact inheritance evidence, retaining verified separator whitespace."""
    verified = payload(body)
    return verified if verified is not None else None if marked(body) else normalize(body)


def _rendered_unit(value: str) -> tuple[str, str] | None:
    if value.startswith("**") and value.endswith("**"):
        from .mdcode import inline_regions

        inner = value[2:-2]
        if (inner and not (inner[0].isspace() or inner[-1].isspace())
                and inline_regions(value) == ((0, len(value)),)):
            return "markdown", inner
        return None
    # One wrapper newline stays inside the HTML block; a blank line can end it
    # and expose the remaining text to Markdown parsing.
    margin = r"[ \t]*(?:\n[ \t]*)?"
    match = re.fullmatch(rf'<p align="center">{margin}<b>(.*?)</b>{margin}</p>', value, re.S)
    return ("html", match.group(1)) if match is not None else None


def matches_description(body: str, description: str) -> bool:
    """R2 is separate from ownership; only verified payloads may use soft wraps."""
    verified = visible(body)
    if verified is None and marked(body):
        return False
    value = normalize(body) if verified is None else verified
    description = description.strip()
    if verified is None:
        return value in (f"**{description}**", f'<p align="center"><b>{description}</b></p>')
    from .mdcode import tagline_reflow_key

    unit = _rendered_unit(value)
    if unit is None:
        return False
    markdown = unit[0] == "markdown"
    return tagline_reflow_key(unit[1], markdown=markdown) == tagline_reflow_key(description, markdown=markdown)


def reseal(original: str, formatted: str) -> str | None:
    """Reseal only previously verified content after the caller's AST check.

    Authored/invalid bodies cannot be normalized back into ownership. Receipt
    text itself must survive unchanged, including its old digest.
    """
    if payload(original) is None:
        if payload(formatted) is not None or (marked(original) != marked(formatted)):
            return None
        return formatted
    before = RECEIPT.fullmatch(normalize(original))
    after = RECEIPT.fullmatch(normalize(formatted))
    if after is None or after.group(1) != before.group(1) or marked(after.group(2)):
        return None
    if before.group(2) != after.group(2):
        from .mdcode import tagline_reflow_key

        old_unit = _rendered_unit(_visible_payload(before.group(2)))
        new_unit = _rendered_unit(_visible_payload(after.group(2)))
        if old_unit is None or new_unit is None or old_unit[0] != new_unit[0]:
            return None
        markdown = old_unit[0] == "markdown"
        if tagline_reflow_key(old_unit[1], markdown=markdown) != tagline_reflow_key(new_unit[1], markdown=markdown):
            return None
    # Replace only the digest in the original transport representation.
    start = formatted.index("sha256=") + len("sha256=")
    return formatted[:start] + digest(after.group(2)) + formatted[start + 64:]
