"""The unchanged final decision 18 footer and a separately owned credit immediately before it."""
from __future__ import annotations

import re
import urllib.error
import urllib.request

START, END = "<!-- showcase:footer:start -->", "<!-- showcase:footer:end -->"
# Additive maintenance credit never overrides decision 18: the footer remains last,
# byte-identical, and the only <picture>.
CREDIT_START, CREDIT_END = "<!-- showcase:credit:start -->", "<!-- showcase:credit:end -->"
GENERATED_BY = re.compile(r"<!-- generated-by: ([a-z0-9-]+) v=([0-9A-Za-z.+-]+) std=([0-9A-Za-z.-]+) -->")


def markup(brand) -> str:
    f = brand.raw["footer"]
    company = brand.strings["company"]
    return "\n".join([
        '<p align="center">',
        f'  <a href="{f["href"]}">',
        "    <picture>",
        f'      <source media="(prefers-color-scheme: dark)" srcset="{f["logo_dark_url"]}">',
        f'      <img src="{f["logo_light_url"]}" alt="{f["alt"]}" width="{f["width"]}">',
        "    </picture>",
        "  </a>",
        "  <br>",
        f'  {f["line_prefix"]} <a href="{f["href"]}">{company}</a> {f["line_suffix"]}',
        "</p>",
    ])


def attribution(brand) -> dict | None:
    """The `attribution` row of brand.yaml (skill name, URL, publisher, credit wording), or None for a config without one."""
    a = brand.raw.get("attribution") if brand is not None else None
    return a if isinstance(a, dict) and a.get("skill") and a.get("skill_url") else None


def generated_by(brand) -> str | None:
    """The hidden provenance marker: `<!-- generated-by: github-showcase-skill v=<version> std=ct-std-v1 -->`."""
    from . import STANDARD, __version__
    a = attribution(brand)
    return f"<!-- generated-by: {a['skill']} v={__version__} std={STANDARD} -->" if a else None


def credit_line(brand) -> str | None:
    """The configured credit and its optional installation link."""
    a = attribution(brand)
    if not a:
        return None
    install = (f' · <a href="{a["install_url"]}">{a["install_label"]}</a>'
               if a.get("install_label") and a.get("install_url") else "")
    return (f'<p align="center"><sub>{a["credit_prefix"]} <a href="{a["skill_url"]}">{a["skill"]}</a> '
            f'{a["credit_suffix"]}{install}</sub></p>')


def credit_markup(brand) -> str | None:
    """The body of the credit block: the hidden marker, then the visible line."""
    return f"{generated_by(brand)}\n{credit_line(brand)}" if attribution(brand) else None


def credit_block(brand) -> str | None:
    body = credit_markup(brand)
    return f"{CREDIT_START}\n{body}\n{CREDIT_END}" if body else None


def footer_block(brand) -> str:
    """The decision 18 footer alone, between its markers (byte-identical to the decision's markup)."""
    return f"{START}\n{markup(brand)}\n{END}"


def block(brand) -> str:
    """Append the credit, then the unchanged final footer; configs without attribution get only the footer."""
    credit = credit_block(brand)
    return (f"{credit}\n\n" if credit else "") + footer_block(brand)


def split_credit(text: str, brand=None) -> tuple[str, str | None]:
    """Inspect only a real credit block immediately before the final footer, outside code.

    This parser is for checking, never ownership or removal from an authored file.
    A credit after the footer cannot make the footer-last check pass.
    """
    from .mdcode import MANAGED_BLOCK_PATTERN, find_blocks

    t = text.replace("\r\n", "\n")
    blocks = find_blocks(MANAGED_BLOCK_PATTERN, t)
    if (brand is not None and blocks and blocks[-1].group(1) == "credit"
            and t[blocks[-1].end():].strip() == markup(brand)):
        credit = blocks[-1]
        return t[:credit.start()] + t[credit.end():], credit.group(2)
    if len(blocks) < 2:
        return text, None
    credit, footer = blocks[-2:]
    if (credit.group(1) != "credit" or footer.group(1) != "footer"
            or t[credit.end():footer.start()].strip() or t[footer.end():].strip()):
        return text, None
    return t[:credit.start()] + t[credit.end():], credit.group(2)


def _norm_credit(text: str) -> tuple | None:
    """Strict whole-body HTML tokens, allowing formatting and an older generator version.

    Every tag, attribute, comment and visible word must match; a marker cannot
    claim ownership of additional authored content or another generator's line.
    """
    from html.parser import HTMLParser

    class CreditParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.events, self.stack, self.valid = [], [], True

        def handle_starttag(self, tag, attrs):
            if len({key for key, _ in attrs}) != len(attrs):
                self.valid = False
            self.events.append(("start", tag, tuple(sorted(attrs, key=lambda item: item[0]))))
            self.stack.append(tag)

        def handle_endtag(self, tag):
            if not self.stack or self.stack.pop() != tag:
                self.valid = False
            self.events.append(("end", tag))

        def handle_data(self, data):
            value = re.sub(r"[ \t\r\n\f]+", " ", data).strip(" ")
            if value:
                self.events.append(("text", value))

        def handle_comment(self, data):
            marker = GENERATED_BY.fullmatch("<!--" + data + "-->")
            self.events.append(("generator", marker.group(1), marker.group(3)) if marker else ("comment", data))

        def handle_decl(self, decl):
            self.valid = False

        def handle_pi(self, data):
            self.valid = False

        def unknown_decl(self, data):
            self.valid = False

    parser = CreditParser()
    try:
        parser.feed(text)
        parser.close()
    except (ValueError, AssertionError):
        return None
    return tuple(parser.events) if parser.valid and not parser.stack else None


def credit_matches(brand, body: str | None) -> bool:
    want = credit_markup(brand)
    if body is None or want is None:
        return False
    from . import STANDARD
    marker = GENERATED_BY.search(body)
    normalized = _norm_credit(body)
    return (marker is not None and marker.group(1) == "github-showcase-skill"
            and marker.group(3) == STANDARD and normalized is not None and normalized == _norm_credit(want))


def _blocks(text: str) -> list[str]:
    return [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def check(brand, readme_text: str) -> tuple[str, list[str]]:
    """pass | fail:missing | fail:not-last | fail:drift (any byte difference) | fail:duplicate (an old footer-like
    block, centred with "Built by" and complete.tech, kept outside code before the decision 18 one) |
    fail:credit-missing | fail:credit-drift. The credit directly precedes the unchanged final footer."""
    rest, credit = split_credit(readme_text, brand)
    st, logs = _check_footer_impl(brand, rest)
    if st != "pass" or attribution(brand) is None:
        return st, logs
    if credit is None:
        return "fail:credit-missing", logs
    if not credit_matches(brand, credit):
        return "fail:credit-drift", logs
    return st, logs


def _check_footer_impl(brand, readme_text: str) -> tuple[str, list[str]]:
    want = markup(brand)
    text = readme_text.replace("\r\n", "\n")
    stripped = text.replace(START + "\n", "").replace("\n" + END, "")
    blocks = _blocks(stripped)
    if not blocks:
        return "fail:missing", []
    last = blocks[-1].strip()
    if last == want:
        logs = []
        lic = [m.start() for m in re.finditer(r"(?m)^## Licens(e|ing)\s*$", stripped)]
        if lic and stripped.rfind(want) < lic[-1]:
            return "fail:not-last", logs
        from .readme import is_footer_like, masked  # lazy: readme imports this module
        if any(is_footer_like(b) for b in _blocks(masked(stripped))[:-1]):
            return "fail:duplicate", logs
        return "pass", logs
    if want in stripped:
        return "fail:not-last", []
    if "complete.tech" in last and "<picture>" in last and "Built by" in last:
        return "fail:drift", []
    if "Built by" in stripped and "complete.tech" in stripped:
        return "fail:drift", []
    return "fail:missing", []


def _head(url: str, timeout: float = 20.0) -> int | None:
    """HTTP status of a read-only HEAD request (None when the host cannot be reached)."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "github-showcase-skill"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # fixed https brand URLs only
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return None


def online(brand, head=_head) -> tuple[str, list[dict]]:
    """Phase 4.0 hard gate: a read-only HEAD of both decision 18 raw logo URLs; pass only when both return 200."""
    f = brand.raw["footer"]
    rows = []
    for key in ("logo_light_url", "logo_dark_url"):
        url = f[key]
        if not url.startswith("https://"):
            rows.append({"url": url, "status": None, "result": "fail"})
            continue
        st = head(url)
        rows.append({"url": url, "status": st, "result": "pass" if st == 200 else "fail"})
    return ("pass" if all(r["result"] == "pass" for r in rows) else "fail:offline"), rows
