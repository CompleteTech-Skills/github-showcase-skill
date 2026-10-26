"""Decision 18 footer: the exact markup, wrapped in marker comments (spec A6.5)."""
from __future__ import annotations

import re
import urllib.error
import urllib.request

START, END = "<!-- showcase:footer:start -->", "<!-- showcase:footer:end -->"


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


def block(brand) -> str:
    return f"{START}\n{markup(brand)}\n{END}"


def _blocks(text: str) -> list[str]:
    return [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def check(brand, readme_text: str) -> tuple[str, list[str]]:
    """pass | fail:missing | fail:not-last | fail:drift (any byte difference)."""
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
