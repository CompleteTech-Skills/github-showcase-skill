"""Description lint against STANDARD §4.1 and the keep-or-edit proposal (spec A6.7).

The tool never composes a new sentence (§1.5 rule 2): when edits cannot fix it, it returns the §4.2 template.
"""
from __future__ import annotations

import re
import unicodedata

from .detect import standard

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


def _extended_pictographic(s: str) -> bool:
    return bool(_EMOJI.search(s))


def checks(text: str, *, slug: str, type_: str, has_brand_assets: bool | None, product: str | None = None,
           owner: str = "", new: bool = False) -> list[dict]:
    d = standard("descriptions")
    s = unicodedata.normalize("NFC", text or "")
    out = []

    def add(rule, ok, span=""):
        out.append({"rule": rule, "result": "pass" if ok else "fail", **({"span": span} if span and not ok else {})})

    limit = d["max_new"] if new else d["max_existing"]
    add("D1", 0 < len(s) <= limit, f"{len(s)} > {limit}" if s else "empty")
    add("D2", bool(s) and s.endswith(".") and s[:1].isupper(), s[-1:] if s else "")
    m = re.search(r"[.!?]\s", s[:-1]) if s else None
    add("D3", not m, s[m.start(): m.start() + 20] if m else "")
    m0 = re.match(r"[\w'.-]+", s) if s else None
    first = m0.group(0).rstrip(".") if m0 else ""
    add("D4", first not in d["d4_banned_first"], first)
    m = re.search(d["d5_regex"], s, re.I)
    add("D5", not m, m.group(0) if m else "")
    bad6 = ("–" in s or "—" in s or _extended_pictographic(s) or s != s.strip() or "  " in s)
    add("D6", not bad6, "dash/emoji/spacing")
    m = re.search(d["d7_regex"], s)
    add("D7", not m, m.group(0) if m else "")
    words = re.findall(r"[a-z0-9]+", s.lower())
    slug_words = set(re.findall(r"[a-z0-9]+", slug.lower())) | set(d["d8_filler"])
    add("D8", not words or not set(words) <= slug_words, "slug words only")
    # V1 voice by type
    ok_v1 = True
    if type_ in d["verb_types"]:
        ok_v1 = first in d["verbs"]
    elif type_ in d["prefix_types"]:
        ok_v1 = s.startswith(d["prefix_types"][type_])
    elif type_ == "game":
        ok_v1 = bool(re.match(r"^[^:]+: play ", s))
    else:
        ok_v1 = first not in d["verbs"] and first not in d["d4_banned_first"]
    add("V1", ok_v1, first)
    # P1 product prefix only for games and T3 Pick-Your-AI
    m = re.match(r"^([A-Z][^:]{0,40}): ", s)
    add("P1", not m or type_ == "game" or owner == "Pick-Your-AI" or type_ in ("fork", "backup", "website"), m.group(0) if m else "")
    if has_brand_assets is None:
        out.append({"rule": "B1", "result": "unknown"})
    else:
        add("B1", ("CompleteTech LLC" in s) == has_brand_assets and not re.search(d["skill_suffix"], s),
            "brand mention mismatch")
    m = re.search(d["disclaimer_regex"], s, re.I)
    add("X1", not m, m.group(0).strip() if m else "")
    return out


def propose(text: str, **kw) -> dict:
    d = standard("descriptions")
    res = checks(text, **kw)
    failing = [c["rule"] for c in res if c["result"] == "fail"]
    if not failing:
        return {"action": "keep", "checks": res}
    t, edits = (text or ""), []
    if t and not t.endswith("."):
        t += "."
        edits.append("add-final-period")
    t2 = re.sub(r"\s+", " ", t).strip()
    if t2 != t:
        t = t2
        edits.append("fix-whitespace")
    for bad, good in d["brand_fixes"].items():
        if bad in t:
            t = t.replace(bad, good)
            if "fix-brand" not in edits:
                edits.append("fix-brand")
    t2 = re.sub(d["skill_suffix"], "", t)
    if t2 != t:
        t = t2.rstrip(" .") + "."
        edits.append("remove-skill-suffix")
    t2 = re.sub(d["disclaimer_regex"], "", t, flags=re.I)
    if t2 != t:
        t = t2.rstrip(" ,;.") + "."
        edits.append("remove-disclaimer")
    if edits and t:
        res2 = checks(t, **kw)
        if all(c["result"] != "fail" for c in res2):
            return {"action": "edit", "text": t, "edits": edits, "checks": res}
    type_ = kw.get("type_")
    tmpl_key = {"agent-skills": "agent-skills", "website": "website", "fork": "fork", "backup": "backup",
                "github-profile": "github", "game": "game"}.get(type_)
    if type_ in d["verb_types"] and not tmpl_key:
        tmpl_key = "verb-type"
    if type_ == "security-check":
        tmpl_key = "security-check-cve" if re.search(r"-cve-\d{4}-\d+", kw.get("slug", "")) else "security-check-issue"
    if type_ == "game" and kw.get("owner") == "jevplay-games":
        tmpl_key = "game-jevplay"
    template = d["templates"].get(tmpl_key or "noun-type")
    slots = {}
    m = re.search(r"cve-(\d{4})-(\d+)", kw.get("slug", ""))
    if m:
        slots["id"] = f"{m.group(1)}-{m.group(2)}"
    if kw.get("product"):
        slots["Product"] = kw["product"]
    return {"action": "needs-writer", "failing": failing, "template": template, "slots_known": slots, "checks": res}
