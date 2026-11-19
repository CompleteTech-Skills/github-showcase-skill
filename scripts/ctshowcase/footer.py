"""Decision 18 footer: the exact markup, wrapped in marker comments (spec A6.5), and the decision 25 credit block
that follows it, or ends a README on its own when the footer is exempt (`exempt:footer`)."""
from __future__ import annotations

import re
import urllib.error
import urllib.request

START, END = "<!-- showcase:footer:start -->", "<!-- showcase:footer:end -->"
# Decision 25 (PROPOSAL pending user confirmation): the public credit follows the decision 18 footer in its own marker
# block, never inside it, so the footer markup stays byte-identical and stays the only <picture>.
CREDIT_START, CREDIT_END = "<!-- showcase:credit:start -->", "<!-- showcase:credit:end -->"
GENERATED_BY = re.compile(r"<!-- generated-by: ([a-z0-9-]+) v=([0-9A-Za-z.+-]+) std=([0-9A-Za-z.-]+) -->")
_TRAILING_CREDIT = re.compile(re.escape(CREDIT_START) + r"\n(.*?)\n" + re.escape(CREDIT_END) + r"\s*\Z", re.S)


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
    """The visible credit, rendered from brand.yaml: README styled with github-showcase-skill by CompleteTech LLC,
    then the install prompt (` · Get the skill`, linking to the skill's quick start) when `install_label` is set."""
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
    """What every README and profile generator appends: the decision 18 footer, then (decision 25) the credit block
    after it. A config without an `attribution` row gets the footer alone."""
    credit = credit_block(brand)
    return footer_block(brand) + (f"\n\n{credit}" if credit else "")


def split_credit(text: str) -> tuple[str, str | None]:
    """(text without a trailing credit block, that block's body or None). Only a credit block that ends the file is
    taken off; anything after it means the footer is not last, which `check` reports."""
    t = text.replace("\r\n", "\n")
    m = _TRAILING_CREDIT.search(t)
    if not m:
        return text, None
    return t[:m.start()].rstrip("\n") + "\n", m.group(1)


def _norm_credit(text: str) -> str:
    # The marker may name an older skill version: the next regeneration bumps it, so a release never fails every README.
    return GENERATED_BY.sub(lambda m: f"<!-- generated-by: {m.group(1)} v=* std={m.group(3)} -->",
                            text.replace("\r\n", "\n").strip())


def credit_matches(brand, body: str | None) -> bool:
    want = credit_markup(brand)
    return body is not None and want is not None and _norm_credit(body) == _norm_credit(want)


def _blocks(text: str) -> list[str]:
    return [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def check(brand, readme_text: str) -> tuple[str, list[str]]:
    """pass | fail:missing | fail:not-last | fail:drift (any byte difference) | fail:duplicate (an old footer-like
    block, centred with "Built by" and complete.tech, kept outside code before the decision 18 one) |
    fail:credit-missing | fail:credit-drift (decision 25: the credit block must directly follow the footer and end the
    README). The footer itself is checked exactly as before, on the text without its trailing credit block."""
    rest, credit = split_credit(readme_text)
    st, logs = _check_footer_impl(brand, rest)
    if st != "pass" or attribution(brand) is None:
        return st, logs
    if credit is None:
        return "fail:credit-missing", logs
    if not credit_matches(brand, credit):
        return "fail:credit-drift", logs
    return st, logs


def credit_check(brand, readme_text: str) -> tuple[str, list[str]]:
    """The credit alone, for a README whose decision 18 footer is exempt (`exempt:footer`: the org row says
    `footer: false`, or the owner has no row): pass | fail:credit-missing | fail:credit-drift. The credit block must
    end the README. A config without an `attribution` row has no credit to check and passes."""
    if attribution(brand) is None:
        return "pass", []
    _, credit = split_credit(readme_text)
    if credit is None:
        return "fail:credit-missing", []
    if not credit_matches(brand, credit):
        return "fail:credit-drift", []
    return "pass", []


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
