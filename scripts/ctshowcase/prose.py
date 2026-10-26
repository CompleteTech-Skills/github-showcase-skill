"""`lint prose` (COVERAGE CQ-17): checks on text the run writes (descriptions, taglines, org and profile text, README
prose). STANDARD §1.2 brand strings, no emoji, no placeholder text, the §4.1 description formula for descriptions,
and, when the optional `codespell` package is installed, its dictionary for typos (project allowlist below).

Run-written text fails on any finding; `--preserved` text (kept verbatim from a repository) only warns and logs
`typo:<word>` / `brand:<string>`, because the run never rewrites preserved prose beyond the §7.1 brand-string fixes.
"""
from __future__ import annotations

import re
from pathlib import Path

from .detect import standard
from .readme import EMOJI

# STANDARD §1.2: (pattern, what it should be). Matched outside URLs, code, HTML comments and org/repo slugs.
BRAND_RULES = [
    (re.compile(r"\bComplete Tech\b"), "CompleteTech"),
    (re.compile(r"\bCompletetech\b"), "CompleteTech"),
    (re.compile(r"\bCompleTetech\b"), "CompleteTech"),
    (re.compile(r"\bCOMPLETETECH(?: LLC)?\b"), "CompleteTech LLC (all caps only in compositor eyebrows)"),
    (re.compile(r"\bcomplete-tech\b"), "completetech (brand topic)"),
    (re.compile(r"\bAI systems, integrations, and field proof\b", re.I), "Innovation at Every Integration"),
    (re.compile(r"\bPokemon\b"), "Pokémon"),
]
# words codespell flags that are correct here (slugs, CVE ids, product names): CQ-17 project allowlist
ALLOW = {"gage", "tcg", "jev", "jevplay", "romgenie", "netscaler", "kicad", "sts2", "claw", "clawhub", "openclaw",
         "complete", "completetech", "libreevolve", "touchedbyanagent", "northwind"}


def _codespell_dictionary() -> dict[str, str] | None:
    """The pinned codespell dictionary when the optional package is installed, else None (typo check skipped)."""
    try:
        import codespell_lib  # type: ignore[import-not-found]
    except ImportError:
        return None
    path = Path(codespell_lib.__file__).resolve().parent / "data" / "dictionary.txt"
    if not path.is_file():
        return None
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        wrong, _, right = line.partition("->")
        if wrong and right:
            out[wrong.strip().lower()] = right.split(",")[0].strip()
    return out


def _prose_only(text: str) -> str:
    """Text with code, HTML comments, tags, URLs and owner/repo slugs removed (those are never prose)."""
    t = re.sub(r"```.*?```|~~~.*?~~~", " ", text, flags=re.S)
    t = re.sub(r"`[^`\n]*`", " ", t)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"\]\([^)]*\)", "]", t)  # Markdown link targets
    t = re.sub(r"<[^>]+>", " ", t)  # HTML tags and their attributes
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"\b[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+\b", " ", t)  # OWNER/REPO
    return re.sub(r"\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b", " ", t)  # slugs and logins (CompleTetech-Security, ...)


def typos(text: str, dictionary: dict[str, str] | None, allow: set[str] = frozenset()) -> list[str]:
    if not dictionary:
        return []
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z][A-Za-z']+", text):
        low = w.lower()
        if low in seen or low in ALLOW or low in allow:
            continue
        seen.add(low)
        if low in dictionary:
            out.append(f"{w}->{dictionary[low]}")
    return out


def lint_text(text: str, *, kind: str = "text", preserved: bool = False, describe_checks: list[dict] | None = None,
              dictionary: dict[str, str] | None = None, allow: set[str] = frozenset(), name: str = "-") -> dict:
    """One result {file, kind, result, fails, warns, logs}. kind: text | description | tagline."""
    fails, warns, logs = [], [], []
    prose = _prose_only(text)
    findings = []
    for pat, want in BRAND_RULES:
        for m in pat.finditer(prose):
            findings.append(("brand", f"'{m.group(0)}' (use {want})", f"brand:{m.group(0)}"))
    if EMOJI.search(text):
        findings.append(("emoji", "emoji present", "emoji"))
    ph = re.search(standard("readme-variants")["placeholder_regex"], prose)
    if ph or re.search(r"<…>|<\.\.\.>|\[(?:TODO|TBD|placeholder)\]", text, re.I):
        findings.append(("placeholder", f"placeholder text: {ph.group(0) if ph else '<…>'}", "placeholder"))
    for t in typos(prose, dictionary, allow):
        findings.append(("typo", f"typo {t}", f"typo:{t.split('->')[0]}"))
    for cat, msg, log in findings:
        if preserved and cat in ("brand", "typo", "emoji"):
            warns.append(msg)  # preserved text: logged, never a failure (§7.1 rule 5 keeps it verbatim)
        else:
            fails.append(msg)
        logs.append(log)
    if kind in ("description", "tagline"):
        for c in describe_checks or []:
            if c["result"] == "fail":
                fails.append(f"§4.1 {c['rule']}" + (f": {c['span']}" if c.get("span") else ""))
    if dictionary is None:
        logs.append("typo-check:skipped (pip install codespell to enable)")
    res = "fail" if fails else "pass"
    return {"file": name, "kind": kind, "result": res, "fails": sorted(set(fails)), "warns": sorted(set(warns)),
            "logs": sorted(set(logs))}
