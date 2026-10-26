"""Eyebrow and fact chips shared by the banner and the card (spec A6.1 'Chip derivation').

Facts only; every chip records its source. One eyebrow function and one chip order serve both surfaces, so a
repository's banner and card never disagree.
"""
from __future__ import annotations

import re

from .context import RepoContext

CVE = re.compile(r"CVE-\d{4}-\d{4,}", re.I)
HTTP_CLIENTS = {"requests", "httpx", "aiohttp", "urllib3", "axios", "node-fetch", "got", "undici"}
SEP = " · "  # en spaces around the middle dot, so COMPANY and CATEGORY read apart (golden)
TRACK_UPPER, TRACK_ASIS = 0.06, 0.01


# ------------------------------------------------------------------------------------------------
# Eyebrow
# ------------------------------------------------------------------------------------------------
def fallback_category(ctx: RepoContext) -> bool:
    """True when the type is the rule-25 Workspace fallback: a category that says nothing."""
    return ctx.det.get("type") == "workspace"


def eyebrow_category(ctx: RepoContext, category: str | None = None) -> str | None:
    org = ctx.org
    cat = category or ctx.override.get("category") or org.get("banner_category") or org.get("eyebrow")
    if not cat and not fallback_category(ctx):
        cat = ctx.det.get("category")
    return cat or None


def eyebrow_text(ctx: RepoContext, category: str | None = None) -> str:
    """`COMPANY · CATEGORY` (decision 13), upper-cased for families whose eyebrow case is upper."""
    label = ctx.style["company_label"]
    cat = eyebrow_category(ctx, category)
    text = f"{label}{SEP}{cat}" if cat else label
    return text.upper() if ctx.style.get("eyebrow_case") == "upper" else text


def eyebrow_track(style: dict) -> float:
    """Letter-spacing: +6% for upper-case eyebrows (golden 409 px), +1% for lower- or mixed-case families."""
    return TRACK_UPPER if style.get("eyebrow_case") == "upper" else TRACK_ASIS


def _stems(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        for suf in ("ies", "es", "s"):
            if len(w) > len(suf) + 2 and w.endswith(suf):
                w = w[: -len(suf)] + ("y" if suf == "ies" else "")
                break
        out.add(w)
    return out


# ------------------------------------------------------------------------------------------------
# Chips
# ------------------------------------------------------------------------------------------------
def cve_ids(ctx: RepoContext) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    readme = ctx.facts.readme() or ""
    header = readme.split("\n## ", 1)[0]
    for source, text in (("slug", ctx.repo), ("description", ctx.meta.get("description") or ""), ("readme", header)):
        for m in CVE.findall(text):
            v = m.upper()
            if v not in [f[0] for f in found]:
                found.append((v, source))
    return found[:2]


def key_chips(ctx: RepoContext, category: str | None = None) -> list[tuple[str, str]]:
    """Gold chips: the key identifier. Override, then CVE ids, then the type category; a type category that repeats an
    eyebrow word (AI RESEARCH / Research) or is the Workspace fallback is dropped (logged needs-input:key-chip)."""
    over = (ctx.override.get("chips") or {}).get("key")
    if over:
        return [(k, "override") for k in over[:2]]
    cves = cve_ids(ctx)
    if cves:
        return cves
    cat = ctx.det.get("category")
    if not cat or fallback_category(ctx) or _stems(cat) & _stems(eyebrow_text(ctx, category)):
        ctx.log("needs-input:key-chip")
        return []
    return [(cat, "type")]


def attr_chips(ctx: RepoContext) -> list[tuple[str, str]]:
    """Blue chips, in the one order both surfaces use: runtime, language, dependencies, offline, license.
    Live-host chips are not used: a long host name pulls focus from the key chip (review P3)."""
    over = (ctx.override.get("chips") or {}).get("attrs")
    if over:
        return [(a, "override") for a in over[:3]]
    out: list[tuple[str, str]] = []
    topics = set(ctx.meta.get("topics") or [])
    # 3. skills runtime
    rt = [n for t, n in (("claude-skill", "Claude"), ("codex-skill", "Codex")) if t in topics]
    if rt and ctx.det["type"] == "agent-skills":
        out.append((" · ".join(rt), "topics"))
    # 4. language + floor version
    f = ctx.facts
    py, node = f.requires_python(), f.engines_node()
    lang = ctx.meta.get("language")
    if lang == "Python" and py:
        out.append((f"Python {py}+", "manifest"))
    elif lang in ("JavaScript", "TypeScript") and node:
        out.append((f"Node {node}+", "manifest"))
    elif py:
        out.append((f"Python {py}+", "manifest"))
    elif node:
        out.append((f"Node {node}+", "manifest"))
    elif lang:
        out.append((lang, "meta"))
    # 5. no dependencies / offline (known facts only)
    deps = f.runtime_dependencies()
    if deps is not None and f.known:
        has_manifest = any(m in f.root_files() for m in ("pyproject.toml", "package.json", "requirements.txt", "setup.py"))
        if has_manifest and not deps and not f.has_lockfile():
            out.append(("No dependencies", "manifest"))
        readme = f.readme() or ""
        if re.search(r"\boffline\b", readme, re.I) and not (set(d.lower() for d in deps) & HTTP_CLIENTS) and has_manifest:
            out.append(("Offline", "readme"))
    # 6. license
    lic = ctx.meta.get("license")
    if ctx.public and lic and lic not in ("NOASSERTION", "other"):
        special = ctx.org.get("license_chip")
        out.append((special if special and lic.upper().startswith("AGPL") else lic, "license"))
    return out[:3]


def derive(ctx: RepoContext, cli_keys=None, cli_attrs=None, category: str | None = None):
    keys = [(k, "cli") for k in cli_keys] if cli_keys else key_chips(ctx, category)
    attrs = [(a, "cli") for a in cli_attrs] if cli_attrs else attr_chips(ctx)
    return keys[:2], attrs[:3]
