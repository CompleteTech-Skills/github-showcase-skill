"""STANDARD §5.6 topic merge algorithm (spec A6.8). Proposes; never writes."""
from __future__ import annotations

import re

from .config import t3_signed_off
from .context import RepoContext
from .detect import standard


def _singular(w: str) -> str:
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _norm_phrase(s: str) -> str:
    return "-".join(_singular(t) for t in re.findall(r"[a-z0-9]+", s.lower()))


def domain_candidates(text: str, vocab: list[str]) -> list[str]:
    """§5.9 entries found as whole words (spaces -> hyphens, singular matching), in order of first occurrence."""
    tokens = re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", text.lower())  # domains such as jevplay.games stay one word
    norm = [_singular(t) for t in tokens]
    hits = []
    used: set[int] = set()
    # longer entries claim their words first, so "board game" yields board-game, not also games
    for entry in sorted(vocab, key=lambda e: -len(e.split("-"))):
        parts = [_singular(p) for p in entry.split("-")]
        n = len(parts)
        for i in range(len(norm) - n + 1):
            if norm[i:i + n] == parts and not used & set(range(i, i + n)):
                hits.append((i, entry))
                used.update(range(i, i + n))
                break
    return [e for _, e in sorted(hits)]


def org_topic(brand, login: str) -> tuple[bool, str | None]:
    """(known, topic) for an org's §5.3a membership topic, under any of its logins (CQ-03). The romgenie utility orgs
    are known with topic None (they take no incoming also_in)."""
    table = standard("topics").get("org_topics") or {}
    low = {k.lower(): v for k, v in table.items()}
    for a in brand.aliases(login) if brand is not None else [login]:
        if a and a.lower() in low:
            return True, low[a.lower()]
    return False, None


def membership_topics(ctx: RepoContext, also_in: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(orgs, topics, logs) in also_in order: one topic per also_in org (§5.3a), never the home org's own, none for the
    utility orgs, T3 only after co-owner sign-off."""
    orgs, topics_, logs = [], [], []
    res = ctx.brand.resolver()
    for org in also_in:
        org = (org or "").strip()
        if not org:
            continue
        if res.same(org, ctx.owner):
            logs.append(f"org-topic-home:{org}")
            continue
        status = ctx.brand.owner_status(org)
        if status in ("excluded", "hold"):
            logs.append(f"exempt:also-in:{org}")
            continue
        if status == "t3" and not t3_signed_off():
            logs.append(f"t3-signoff:also-in:{org}")
            continue
        known, topic = org_topic(ctx.brand, org)
        if not known:
            logs.append(f"needs-input:org-topic:{org}")
            continue
        if not topic:
            logs.append(f"org-topic-none:{org}")
            continue
        if topic not in topics_:
            orgs.append(org)
            topics_.append(topic)
    return orgs, topics_, logs


def merge(ctx: RepoContext, also_in: list[str] | None = None) -> dict:
    """§5.6 merge. `also_in` (org logins, from the registry or `--also-in`) adds the §5.3a org membership topics; when
    it is None, the metadata's own `also_in` list is used (empty when absent)."""
    t = standard("topics")
    meta = ctx.meta
    owner, slug = ctx.owner, ctx.repo
    org = ctx.org
    typ = ctx.det["type"]
    logs: list[str] = []
    current = list(meta.get("topics") or [])
    vocab = set(t["brand_topics"]) | set(t["family_topics"]) | set(t["type_topics"]) | set(t["featured"]) | \
        set(t["allowed"]) | set(t["domain"])
    private = meta.get("visibility") == "private"
    # owner identity through the shared resolver (CQ-03): an approved org rename (CompleTetech-Security ->
    # CompleteTech-Security) or a re-cased login must not change the repository's required topics
    res = ctx.brand.resolver()
    cve_vendor = slug.split("-")[0] if res.same(owner, standard("types")["security_owner"]) and \
        re.search(r"-cve-\d{4}-\d+-check$", slug) else None

    def alias(x):
        x = x.lower()
        return t["aliases"].get(x, x)

    # step 1-2: alias then drop
    surviving = []
    for x in current:
        a = alias(x)
        low_owner = owner.lower()
        if not re.match(t["drop_valid"], a) or re.match(t["drop_noise"], a):
            continue
        if (a == low_owner or a.startswith(low_owner + "-")) and a not in t["brand_topics"]:
            continue
        if a in t["type_topics"] and a != typ:
            continue
        if a not in vocab and a != cve_vendor:
            continue
        if private and a in t["private_banned"]:
            continue
        if a not in surviving:
            surviving.append(a)

    if also_in is None:
        also_in = list(meta.get("also_in") or [])
    m_orgs, m_topics, m_logs = membership_topics(ctx, also_in) if typ != "github-profile" else ([], [], [])
    logs += m_logs
    limit = t["max_private"] if private else t["max_public"]

    if typ == "fork":
        parent = (meta.get("parent") or {}).get("topics") or []
        tech = [alias(x) for x in parent if alias(x) in set(t["featured"]) | set(t["allowed"])]
        # a fork listed in also_in also carries that org membership topic (§5.1), counted toward the maximum
        proposed = list(dict.fromkeys(["fork"] + m_topics + list(dict.fromkeys(tech))[:4]))[:limit]
        return _result(current, proposed, logs)
    if typ == "github-profile":
        proposed = [org.get("brand_topic") or "completetech", "github-profile"]
        return _result(current, proposed, logs)

    brand = org.get("brand_topic")
    proposed: list[str] = [brand] if brand else []
    # family topics (§5.3 scope)
    fam = list(org.get("family_topics") or [])
    scope = org.get("family_topics_scope")
    if scope and scope.startswith("type:") and scope[5:] != typ:
        fam = []
    fam = [f for f in fam if f not in (org.get("family_topics_omit") or {}).get(slug, [])]
    if slug in (org.get("family_topics_except") or []):
        fam = []
    proposed += fam
    # §5.3a: org membership topics after the family topics, before the type; they count toward the maximum but are
    # never a brand topic. If brand + family + org + type alone exceed it, org topics drop from the end of also_in.
    while m_topics and len(proposed) + len(m_topics) + 1 > limit:
        logs.append(f"topics-over:{m_orgs.pop()}")
        m_topics.pop()
    proposed += [x for x in m_topics if x not in proposed]
    proposed.append(typ)
    # domain (§5.9)
    text = f"{meta.get('description') or ''} {ctx.facts.h1() or ''}"
    vocab_dom = t["touchedbyanagent_domain"] if res.same(owner, "TouchedByAnAgent") else t["domain"]
    found = domain_candidates(text, vocab_dom)
    existing_dom = [x for x in surviving if x in vocab_dom]
    ranked = [x for x in found if x in existing_dom] + sorted(x for x in existing_dom if x not in found) + \
        [x for x in found if x not in existing_dom]
    if cve_vendor:
        ranked = [cve_vendor] + ranked
    domain = [x for x in dict.fromkeys(ranked) if x not in proposed][:3]
    if not domain:
        logs.append("needs-input:domain-topic")
    proposed += domain
    # tech: language, framework, surviving existing tech
    tech: list[str] = []
    lang = t["languages"].get(meta.get("language") or "")
    if lang:
        tech.append(lang)
    for dep in ctx.facts.dependencies() if ctx.facts.known else []:
        fw = t["frameworks"].get(dep)
        if fw:
            tech.append(fw)
            break
    tech_vocab = set(t["featured"]) | set(t["allowed"])
    tech += [x for x in surviving if x in tech_vocab]
    tech = [x for x in dict.fromkeys(tech) if x not in proposed][:3]
    proposed += tech
    proposed = list(dict.fromkeys(proposed))
    proposed = proposed[:limit]
    minimum = t["min_private"] if private else t["min_public"]
    if len(proposed) < minimum:
        logs.append("topics-short")
    return _result(current, proposed, logs)


def _result(current, proposed, logs):
    return {"current": current, "proposed": proposed, "equal_as_set": set(current) == set(proposed),
            "add": [x for x in proposed if x not in current], "remove": [x for x in current if x not in proposed],
            "logs": logs}


def registry_also_in(resolver, owner: str, repo: str) -> list[str]:
    """The repo's `also_in` orgs from the registry's `also_in_outgoing` rows of its home org (read only)."""
    try:
        reg = resolver.registry_org(owner)
    except Exception:  # an org without a registry row has no cross-listing
        return []
    for row in reg.get("also_in_outgoing") or []:
        if isinstance(row, dict) and str(row.get("repo") or "").lower() == repo.lower():
            return [str(x) for x in row.get("also_in") or []]
    return []


def gh_command(owner: str, repo: str, proposed: list[str]) -> str:
    return f"gh api -X PUT repos/{owner}/{repo}/topics " + " ".join(f"-f names[]={x}" for x in proposed)
