"""README lint: R7 + decision 13 (banner first, plain <img>) + decision 18 (footer last, exact) (spec A6.11)."""
from __future__ import annotations

import bisect
import functools
import html
import re
import string
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
# Explicit source-aligned line boundaries also handle CRLF as one ending.
_NL = mdcode.LINE_END
_SOFT_NL = _NL + rf"(?![ \t\x00]*{_NL})"
REF_DEFINITION = re.compile(
    rf"(?:\A|(?<=\n)|(?<=\r)(?!\n))\x00* {{0,3}}\[((?:\\.|[^\[\]\\\r\n]|{_SOFT_NL})+)\]:"
    rf"[ \t\x00]*(?:{_NL}[ \t\x00]*)?(?:<((?:\\[^\r\n]|[^<>\\\r\n])*)>|((?!<)[^\x00-\x20\x7f]+?))"
    rf"(?:(?:[ \t]+|[ \t\x00]*{_NL}[ \t\x00]*)(?:\"(?:\\.|[^\"\\\r\n]|{_SOFT_NL})*\"|"
    rf"'(?:\\.|[^'\\\r\n]|{_SOFT_NL})*'|\((?:\\.|[^()\\\r\n]|{_SOFT_NL})*\)))?"
    r"[ \t]*(?=\r|\n|\Z)")
# a title may span lines but never a blank one; NUL stands in for a blanked quote or list-item prefix (see below)
# CommonMark raw HTML: an open tag needs a valid tag name, valid attributes and a closing `>`; anything else is text
HTML_OPEN_TAG = re.compile(mdcode.HTML_OPEN_TAG_PATTERN)
HTML_ATTR = re.compile(rf"({mdcode.HTML_ATTRIBUTE_NAME})(?:{mdcode.HTML_SPACE}*={mdcode.HTML_SPACE}*"
                       rf"({mdcode.HTML_ATTRIBUTE_VALUE}))?")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_RAW_HTML_OPEN = re.compile(r"<\?|<![A-Za-z]|<!\[CDATA\[")
_INLINE_DECLARATION = re.compile(rf"<![A-Z]+{mdcode.HTML_SPACE}")
_HTML_CLOSE_TAG = re.compile(mdcode.HTML_CLOSE_TAG_PATTERN)
_LINK_SPACE = " \t\r\n"
_ESCAPABLE = frozenset(string.punctuation)
SHIELDS_SRC = re.compile(r"https?://img\.shields\.io/badge/", re.I)
SHIELDS_BADGE = re.compile(r"https?://img\.shields\.io/badge/(.+)", re.I)


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
            block = _span_at(html_spans or (), match.start()) or _span_at(mdcode.inline_regions(source), match.start())
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
    mdcode.WORK['comment_builds'] += 1
    mdcode.WORK['comment_scan_chars'] += 4 * len(text)
    closers = [m.start() for m in re.finditer(r"-->", text)]
    doubles = [m.start() for m in re.finditer(r"(?=--)", text)]
    paragraphs = [m.start() for m in mdcode.BLANK_LINE.finditer(text)]
    regions = mdcode._layout(text)[0]
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
    mdcode.WORK['raw_html_scan_chars'] += 6 * len(text)
    html_blocks = mdcode.html_block_spans(document)
    regions = mdcode.inline_regions(document)
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


def _raw_definition_matches(candidate: str, document: str):
    """Read definitions within source blocks, leaving an invalid next-block title visible.

    Bounding the regex itself, instead of rejecting an overlong match afterward,
    retains a valid destination when only its apparent optional title belongs to
    another block.
    """
    for lo, hi in mdcode.inline_regions(document):
        yield from REF_DEFINITION.finditer(candidate, lo, hi)


def _definition_candidates(document: str) -> str:
    """The document with code blocks and HTML comments blanked (same length), the text in which a definition is read."""
    out = list(document)
    for a, b in mdcode.code_block_spans(document):
        for i in range(a, b):
            if out[i] not in "\r\n":
                out[i] = " "
    # raw HTML block text is literal HTML, not Markdown: a `[label]: dest` line inside it defines nothing. The block's
    # extent ends at its end condition, so a definition after the block still counts.
    for a, b in mdcode.html_block_spans(document):
        for i in range(a, b):
            if out[i] not in "\r\n":
                out[i] = " "
    fences = mdcode.code_block_spans(document)
    html_spans = mdcode.html_block_spans(document)
    links = _inline_link_spans(document, fences)  # resolved link destinations and titles: literal text, computed once
    # Reference labels are parsed before inline HTML. A comment-looking string
    # inside a syntactically valid definition label is literal label text, even
    # though the same string in a paragraph would be an actual HTML comment.
    candidate = _peel_definition_containers(document, out.copy())
    continuation = mdcode.continuation_starts(document)
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
        previous_end = mdcode.after_line_end(document, match.end())
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
    items: list[tuple[tuple[str, int], ...]] = []
    for raw in mdcode.source_lines(document):
        body = raw.rstrip("\r\n")
        end = pos + len(body)
        source = mdcode.block_line(body)
        line = mdcode.block_line("".join(out[pos:end]))
        while items and mdcode._continue_containers(source, items[-1]) is None:
            items.pop()
        inherited = items[-1] if items else ()
        inner = mdcode._continue_containers(line, inherited) if inherited else line
        # Blanking code/comments can remove a structural prefix, in which case
        # the line itself contains no live definition to peel.
        if inner is not None:
            added, rest = mdcode._container_path(inner)
            for index, (kind, _) in enumerate(added):
                if kind == "item":
                    items.append(inherited + added[:index + 1])
            # Four residual columns mean indented code, not a definition. For
            # 0..3 columns, a partially consumed tab can be blanked whole:
            # both spellings remain legal, and source offsets stay unchanged.
            indent = mdcode._indent_columns(rest)
            if indent < 4:
                columns = len(line) - len(rest) + indent
                prefix = mdcode.source_prefix_chars(body, columns)
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
    spans: list[tuple[int, int]] = []
    html_spans = mdcode.html_block_spans(document)  # raw HTML and fenced code are not link syntax
    openers: list[int] = []  # unconsumed unescaped `[` of the current paragraph, innermost last
    skip_until = 0  # text inside an accepted span is destination or title text: its brackets open nothing
    regions = mdcode.inline_regions(document)
    autolinks = mdcode.autolink_candidates(document)
    angles = mdcode.autolink_candidates(document, bare=False)
    previous_region = None
    for token in re.finditer(r"\[|\]\(|\]|" + mdcode.BLANK_LINE.pattern, document):
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
    continuation = mdcode.continuation_starts(document)
    live: list = []
    for match in _raw_definition_matches(_definition_candidates(document), document):
        if not _definition_key(match, document):
            continue
        if match.group(3) is not None and not _balanced_destination(match.group(3)):
            continue  # a malformed bare destination is not a definition: the line stays ordinary Markdown
        if match.start() in continuation and not (live and mdcode.after_line_end(document, live[-1].end()) == match.start()):
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
        self.text = text
        self.tags = []
        self.images = []
        source = document if document is not None else text
        html_spans = mdcode.html_block_spans(source)
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
    return mdcode.code_block_spans(text)


@functools.lru_cache(maxsize=16)
def _outside_code(text: str, mask_inline: bool = True) -> str:
    """Mask Markdown code, comments and autolinks without reading literal attribute backticks as code.
    Constructs are taken left to right, and inline code is looked for again after every HTML tag or comment, so a
    backtick inside an attribute or comment is literal and the next real code span still opens (CommonMark).
    `mask_inline=False` still lets inline code win precedence but leaves its characters readable (reference labels).
    Autolink contents stay masked; label validity and matching always read the original source.
    The result has the same length (and newline positions) as `text`."""
    fences = _fence_spans(text)
    definitions = _definition_spans(text)  # decided before inline code: a definition destination's backtick is literal
    labels = _reference_label_spans(text)  # resolved full-reference labels: their backticks are literal too
    html_spans = mdcode.html_block_spans(text)  # raw HTML blocks: tags there are never escaped by a backslash
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
    literal text cannot open or close a description. Full reference labels
    use a separate raw lexical scan.
    """
    global _BRACKET_STEPS
    pairs: dict[int, int] = {}
    source = document if document is not None else text
    autolinks = _live_autolinks(source)
    code = mdcode.inline_code_spans(source)
    tags = _HTMLTokens(text, source).tags
    for lo, hi in mdcode.inline_regions(source):
        stack: list[int] = []
        pos, limit = lo, min(hi, len(text))
        while pos < limit:
            _BRACKET_STEPS += 1
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
    regions = mdcode.inline_regions(text)
    before = _span_at(regions, newline)
    after = _span_at(regions, mdcode.after_line_end(text, newline))
    # A bare blank line is handled as a paragraph break by callers; this
    # compatibility helper describes the end of actual inline content only.
    return before is not None and before != after


def _crosses_block(text: str, start: int, end: int, fences: tuple[tuple[int, int], ...],
                   document: str | None = None) -> bool:
    """Whether an inline construct would cross its canonical source block."""
    source = document if document is not None else text
    region = _span_at(mdcode.inline_regions(source), start)
    return region is None or end >= region[1]


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
def _inline_openers_and_autolinks(text: str):
    """Active closing brackets and accepted autolinks from one precedence pass.

    A closing bracket has a matching ACTIVE `[` before it in the same paragraph.
    One left-to-right pass keeps a stack of active `[` indices. Fenced code, inline code, autolinks, HTML comments and HTML open
    tags (attribute values included) are inert, so a bracket inside them is text: it neither opens nor closes a link.
    An unescaped `]` that pops an opener and is directly followed by a destination `(...)` skips that destination,
    which is literal (a backtick in it opens no code span). A blank line clears the stack, and so does a block
    boundary from the shared source-aligned inline regions. This includes headings, ordered containers, list items,
    fences, raw HTML and table cells; plain soft lines in the same paragraph still pair. Raw HTML blocks (`mdcode.html_block_spans`) are inert and are block boundaries: no `[` inside one opens
    a link, and the stack is cleared entering and leaving it. Completing an inline link deactivates every earlier LINK
    opener in the stack (CommonMark: links may not contain links), while earlier IMAGE openers stay active; a `barrier`
    marks the stack depth below which link openers are inactive, so that deactivation is O(1). Reference-style links
    `[x][ref]`, `[x][]` and `[x]` deactivate earlier link openers too when the label resolves to a live definition
    (`_reference_form`); an inline `(dest)` is tried first. The label of a full reference is read up to the next
    non-inline inert region, so a backtick in a resolved label is literal and an unresolved label is not consumed. Inert regions are found
    by cached lookups as in `_outside_code`, so the pass is linear. Offsets are the source offsets. It never calls
    `_outside_code`. Live reference definitions (`_definition_spans`) are inert block regions like raw HTML blocks: their brackets and backticks are literal, and the opener stack is cleared entering and leaving one."""
    global _OPENER_STEPS
    fences = _fence_spans(text)
    html_spans = mdcode.html_block_spans(text)
    defs = _definition_spans(text)  # live reference definitions: inert block regions, cached per document
    keys = {_definition_key(m, text) for m in _definitions(text)}  # live definition labels, computed once per call
    opened: set[int] = set()
    accepted_autolinks = []
    stack: list[tuple[int, bool]] = []  # (index of `[`, whether it opens an image `![`)
    barrier = 0  # stack positions below this hold inactive link openers (a link was completed after them)
    inline = tag = comment = raw_html = autolink = None  # cached next starts: None = not searched yet, False = none left
    n, pos = len(text), 0
    blocks = mdcode.inline_regions(text)
    previous_block = None

    def next_inline(start):
        while True:
            found = find_inline_code(text, start)  # (start, end) or None
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
            autolink = mdcode.find_autolink(text, pos) or False
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
        if tag:
            ref_limit = min(ref_limit, tag.start())
        if comment:
            ref_limit = min(ref_limit, comment.start())
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
                    autolink = mdcode.find_autolink(text, region[0] + 1) or False
                    pos = limit
                    continue
                accepted_autolinks.append(region)
            _OPENER_STEPS += 1
            if k < len(fences) and region == fences[k]:  # a fence skipped as a region is a block boundary too
                stack.clear()
                barrier = 0
            elif h < len(html_spans) and region == html_spans[h]:  # so is a raw HTML block skipped as a region
                stack.clear()
                barrier = 0
            elif d < len(defs) and region == defs[d]:  # and so is a live definition (its own block boundary)
                stack.clear()
                barrier = 0
            pos = region[1]
    return frozenset(opened), tuple(accepted_autolinks)


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
    if not _label_syntax(value):
        return ""  # CommonMark labels are at most 999 source characters.
    # cmark-gfm label matching collapses only SP, HT and line endings.
    # VT/FF and Unicode whitespace remain significant raw label characters.
    return re.sub(r"[ \t\r\n]+", " ", value.strip(" \t\r\n")).casefold()


def _definition_key(match: re.Match, document: str) -> str:
    """Peeled container/indent prefixes are separators, never literal label NULs."""
    start = match.start(1)
    label = "".join(" " if char == "\x00" and document[start + i] != "\x00" else char
                    for i, char in enumerate(match.group(1)))
    return _label_key(label)


@functools.lru_cache(maxsize=16)
def _reference_label_spans(document: str) -> tuple[tuple[int, int], ...]:
    """Label text of each resolved full reference (`[text][label]`): the characters between the brackets of the second
    pair. Only a label that names a live definition is a reference, so its backticks are literal; an unresolved label
    stays readable for inline code. Junctions inside fences or definitions are text. Computed once per document;
    the spans are sorted and never overlap."""
    keys = {_definition_key(m, document) for m in _definitions(document)}
    fences = mdcode.code_block_spans(document)
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
        region = _span_at(mdcode.inline_regions(document), open_)
        close = _next_unescaped_bracket(document, open_ + 1, min(region[1], open_ + 1001)) if region else -1
        if close < 0 or document[close] != "]":
            continue
        label = document[open_ + 1:close]
        if not _label_key(label) or mdcode.BLANK_LINE.search(label):
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
    return tuple(match.start() for match in mdcode.BLANK_LINE.finditer(text))


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


def _inline_image_target(text: str, start: int) -> tuple[str, int] | None:
    """Read a Markdown destination and optional title after its opening parenthesis. Destination nesting deeper than
    32 parentheses is no link (CommonMark's limit), which bounds each call and keeps the opener pass linear."""
    global _DEST_STEPS
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
        if _blank_between(text, pos, ends[at]) or _crosses_block(text, pos, ends[at], _fence_spans(text)):
            return None  # (c) a title may span soft line breaks, never a paragraph or block boundary (heading, list, fence)
        title_close = pos = ends[at] + 1
        while pos < len(text) and text[pos] in _LINK_SPACE:
            _DEST_STEPS += 1
            pos += 1
        if _blank_between(text, title_close, pos):  # (d) the whitespace after the title, up to `)`
            return None
    if pos >= len(text) or text[pos] != ")":
        return None
    region = _span_at(mdcode._layout(text)[0], start)
    if region is None or pos >= region[1]:
        return None  # destination whitespace cannot join separate Markdown blocks either
    return html.unescape(re.sub(r"\\([^\w\s])", r"\1", target)), pos + 1


@functools.lru_cache(maxsize=16)
def _link_literal_spans(document: str) -> tuple[tuple[int, int], ...]:
    """Spans of resolved inline link destinations and titles, from `(` through the closing `)`. This text is literal: a
    `![...](...)` inside a link title renders no image, while a linked image in the link text is not covered. The spans
    are sorted and never overlap, because `_active_openers` skips a completed destination."""
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
    definitions = {}
    for match in _definitions(document):
        destination = match.group(2) if match.group(2) is not None else match.group(3)
        target = html.unescape(re.sub(r"\\([^\w\s])", r"\1", destination))
        definitions.setdefault(_definition_key(match, document), target)
    spans = _definition_spans(document)  # definition titles are never rendered as images
    html_spans = mdcode.html_block_spans(document)  # raw HTML blocks are literal: Markdown image syntax there is text
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
        key = _label_key(document[match.end():close] if len(document) >= len(text) else alt)
        if after < len(text) and text[after] == "[":
            # A reference label is raw lexical text, not rendered inline text.
            # In particular a `]` inside a URI closes the label even though it
            # is inert while reading an image's alt text. A nested `[` makes
            # the full label invalid and leaves the shortcut available.
            source = document if len(document) >= len(text) else text
            region = _span_at(mdcode.inline_regions(source), after)
            ref_close = _next_unescaped_bracket(source, after + 1, min(region[1], after + 1001)) if region else -1
            if ref_close < 0 or source[ref_close] != "]":
                ref_close = None
            # a label holding a block boundary is no label: the shortcut form below still applies, as CommonMark has it
            if ref_close is not None and not _crosses_block(text, after + 1, ref_close, fences, document):
                label = (document if len(document) >= len(text) else text)[after + 1:ref_close]
                if _label_syntax(label):  # invalid labels leave the shortcut and following text visible
                    key = _label_key(label) if label else key
                    after = ref_close + 1
        if key in definitions:
            sources.append((alt, definitions[key], match.start(), after))
            consumed = after
    return sources


def _images(text: str, document: str) -> list[tuple[str, str]]:
    """Read HTML and Markdown images, excluding Markdown-looking text in HTML attributes."""
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


def lint(ctx: RepoContext, path: Path, variant: str | None = None) -> dict:
    fails, warns = [], []
    incomplete: list[str] = []
    if not path.is_file():
        return {"file": str(path), "result": "fail", "fails": ["missing README"], "warns": []}
    raw = path.read_bytes()
    # Lint uses an LF-only read view for its presentation checks. Shared scans
    # also accept unnormalized source; this view never reaches a README writer.
    text = normalize_text(raw.decode("utf-8", errors="replace")).replace("\r", "\n")
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
