"""Enterprise module (decision 24; audit/research/enterprise.md §4). Read-only toward GitHub.

`discover` and `snapshot` run GraphQL *queries* through `gh api graphql` (never a mutation: the query files are
checked before each call). `doctor`, `seat-check`, `diff` and `plan` work offline on snapshot files. `plan` prints
change records with the mutation file and variables for the orchestrator's writer queue; it never runs them.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone

from . import REFERENCES, STANDARD
from .config import load_yaml_text
from .errors import ShowcaseError

QUERIES = REFERENCES / "enterprise" / "queries"
MUTATIONS = REFERENCES / "enterprise" / "mutations"
DESIRED = REFERENCES / "enterprise.yaml"
PAGED = {"organizations": ("q_orgs", ("enterprise", "organizations")),
         "members": ("q_members", ("enterprise", "members")),
         "outside_collaborators": ("q_outside", ("enterprise", "ownerInfo", "outsideCollaborators"))}


def desired() -> dict:
    return load_yaml_text(DESIRED.read_text(encoding="utf-8")) or {}


def query_text(name: str) -> str:
    text = (QUERIES / f"{name}.graphql").read_text(encoding="utf-8")
    if re.search(r"\bmutation\b", text, re.I):  # defence in depth: this module only reads
        raise ShowcaseError(f"{name}.graphql contains a mutation; refused", log="usage")
    return text


def _gh_graphql(name: str, **variables) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={query_text(name)}"]
    for k, v in variables.items():
        if v is not None:
            cmd += ["-F", f"{k}={v}"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShowcaseError(f"gh api graphql failed: {exc}", log="needs-input:gh")
    if p.returncode != 0:
        msg = (p.stderr or p.stdout).strip()[:300]
        hint = " (needs the read:enterprise scope: gh auth refresh -s read:enterprise)" if "scope" in msg.lower() else ""
        raise ShowcaseError(f"{name}: {msg}{hint}", log="needs-input:gh")
    data = json.loads(p.stdout or "{}")
    if data.get("errors"):
        raise ShowcaseError(f"{name}: {data['errors'][0].get('message')}", log="needs-input:gh")
    return data.get("data") or {}


def _dig(obj, path):
    for k in path:
        obj = (obj or {}).get(k)
    return obj


def discover(run=_gh_graphql) -> dict:
    data = run("q_discover")
    nodes = _dig(data, ("viewer", "enterprises", "nodes")) or []
    if not nodes:
        raise ShowcaseError("the viewer administers no enterprise (or lacks read:enterprise)", log="needs-input:enterprise")
    return {"viewer": _dig(data, ("viewer", "login")), "enterprises": nodes}


def snapshot(slug: str, run=_gh_graphql) -> dict:
    """Profile, settings, domains, admins and invitations, plus every page of orgs, members and outside collaborators."""
    prof = _dig(run("q_profile", slug=slug), ("enterprise",))
    if not prof:
        raise ShowcaseError(f"enterprise {slug!r} not found or not visible", log="needs-input:enterprise")
    out: dict = {"profile": prof}
    for key, (qname, path) in PAGED.items():
        items, after = [], None
        while True:
            conn = _dig(run(qname, slug=slug, after=after), path) or {}
            items += conn.get("nodes") or conn.get("edges") or []
            page = conn.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            after = page.get("endCursor")
        out[key] = items
    snap = {"schema": 1, "standard": STANDARD, "taken_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "slug": prof.get("slug"), "id": prof.get("id"), "sections": out}
    snap["sha256"] = {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest() for k, v in out.items()}
    return snap


# -- offline checks ------------------------------------------------------------------------------------
def _orgs(snap):
    return {o["login"]: o for o in snap["sections"].get("organizations", [])}


def _member_roles(snap, login):
    for m in snap["sections"].get("members", []):
        if (m.get("login") or "").lower() == login.lower():
            return {e["node"]["login"]: e["role"] for e in _dig(m, ("organizations", "edges")) or []}
    return {}


def seat_check(snap: dict, user: str) -> dict:
    """E6: the user holds no org role, collaborator grant on a private repository, or pending invitation inside."""
    roles = _member_roles(snap, user)
    grants = []
    for e in snap["sections"].get("outside_collaborators", []):
        if (_dig(e, ("node", "login")) or "").lower() == user.lower():
            grants = [r["nameWithOwner"] for r in _dig(e, ("repositories", "nodes")) or [] if r.get("isPrivate")]
    inv = [i for i in _dig(snap["sections"]["profile"], ("ownerInfo", "pendingMemberInvitations", "nodes")) or []
           if (_dig(i, ("invitee", "login")) or "").lower() == user.lower()]
    blockers = [f"org-role:{o}:{r}" for o, r in sorted(roles.items())] + [f"collaborator:{g}" for g in grants] + \
        [f"invitation:{_dig(i, ('organization', 'login'))}" for i in inv]
    return {"user": user, "result": "pass" if not blockers else "fail", "blockers": blockers}


def doctor(snap: dict, want: dict, brand, baseline: dict | None = None, resolver=None) -> dict:
    """E1-E14 on a snapshot. Org logins go through the shared resolver (CQ-03): after an approved rename the snapshot
    shows the new login while brand.yaml may still key the row by the old one, and both must count as the same org."""
    r = resolver or brand.resolver()
    prof = snap["sections"]["profile"]
    owner_info = prof.get("ownerInfo") or {}
    orgs = _orgs(snap)
    cells: dict[str, str] = {}
    notes: list[str] = []
    wp = want.get("profile") or {}
    diff = [k for k, v in wp.items() if (prof.get(k) or "") != v]
    cells["E1"] = "pass" if not diff else "fail"
    notes += [f"E1 {k}: {prof.get(k)!r} != {wp[k]!r}" for k in diff]
    cells["E2"] = "manual"  # avatar colour test needs the image
    cells["E3"] = "pass" if prof.get("readme") else "warn"
    admins = {_dig(e, ("node", "login")): e.get("role") for e in _dig(owner_info, ("admins", "edges")) or []}
    owners = [a for a, r in admins.items() if r == "OWNER"]
    missing = [o for o in want.get("owners", []) if o.lower() not in {x.lower() for x in owners if x}]
    cells["E4"] = "fail" if missing else ("pass" if len(owners) >= 2 else "warn")
    notes += [f"E4 not an enterprise owner: {o}" for o in missing]
    if len(owners) < 2 and not missing:
        notes.append("E4 a single enterprise owner: record the user's break-glass choice (§3.3)")
    rows = brand.raw.get("orgs", {})
    in_scope = {o for o in orgs if (rows.get(r.brand_key(o) or "") or {}).get("tier") in ("T1", "T2", "T2-R")}
    e5 = []
    for owner in want.get("owners", []):
        roles = _member_roles(snap, owner)
        e5 += [f"E5 {owner} is {roles.get(o, 'not a member')} of {o}" for o in sorted(orgs) if o in in_scope and roles.get(o) != "OWNER"]
    cells["E5"] = "fail" if e5 else "pass"
    notes += e5
    user = want.get("seat_free_user")
    if user:
        sc = seat_check(snap, user)
        cells["E6"] = sc["result"]
        notes += [f"E6 {b}" for b in sc["blockers"]]
    doms = {d["domain"]: d for d in _dig(owner_info, ("domains", "nodes")) or []}
    unverified = [d for d in want.get("domains", []) if not (doms.get(d) or {}).get("isVerified")]
    cells["E7"] = "fail" if unverified else "pass"
    notes += [f"E7 not verified: {d}" for d in unverified]
    noverify = [o for o in sorted(orgs) if o in in_scope and not orgs[o].get("isVerified")]
    cells["E8"] = "warn" if noverify else "pass"  # each needs a §2.3.6 reason code
    notes += [f"E8 no verified badge: {o}" for o in noverify]
    bi = prof.get("billingInfo") or {}
    cells["E9"] = "info"
    notes.append(f"E9 licenses: {bi.get('allLicensableUsersCount')} used of {bi.get('totalLicenses')}")
    if baseline:
        bprof = baseline["sections"]["profile"].get("ownerInfo") or {}
        drift = [k for k in want.get("danger_settings", []) if bprof.get(k) != owner_info.get(k)]
        cells["E10"] = "fail" if drift else "pass"
        notes += [f"E10 danger setting changed: {k}" for k in drift]
        cells["E12"] = "pass" if (baseline.get("slug"), baseline.get("id")) == (snap.get("slug"), snap.get("id")) else "fail"
    else:
        cells["E10"] = cells["E12"] = "unknown"
    cells["E11"] = "manual"
    status = {o: r.owner_status(o) for o in orgs}
    flagged = [o for o in sorted(orgs) if any(r.same(o, x) for x in want.get("never_inside", []))
               or status[o] in ("t3", "hold", "excluded")]
    cells["E13"] = "warn" if flagged else "pass"
    notes += [f"E13 inside the enterprise but out of scope or T3: {o} (blocks member-privilege policies)" for o in flagged]
    cells["E14"] = "manual"
    return {"slug": snap.get("slug"), "cells": cells, "notes": notes,
            "result": "fail" if any(v == "fail" for v in cells.values()) else "pass"}


def diff(old: dict, new: dict) -> dict:
    """Changes between two snapshots: identity, seats, orgs, owners, domains, invitations, settings."""
    def admins(s):
        return {_dig(e, ("node", "login")): e.get("role") for e in _dig(s["sections"]["profile"], ("ownerInfo", "admins", "edges")) or []}

    def doms(s):
        return {d["domain"]: d.get("isVerified") for d in _dig(s["sections"]["profile"], ("ownerInfo", "domains", "nodes")) or []}

    def settings(s):
        oi = s["sections"]["profile"].get("ownerInfo") or {}
        return {k: v for k, v in oi.items() if k.endswith("Setting")}

    out = {"identity_changed": (old.get("slug"), old.get("id")) != (new.get("slug"), new.get("id")),
           "seats": [(_dig(x["sections"]["profile"], ("billingInfo", "allLicensableUsersCount"))) for x in (old, new)],
           "orgs_added": sorted(set(_orgs(new)) - set(_orgs(old))), "orgs_removed": sorted(set(_orgs(old)) - set(_orgs(new))),
           "admins": {k: [admins(old).get(k), admins(new).get(k)] for k in set(admins(old)) | set(admins(new))
                      if admins(old).get(k) != admins(new).get(k)},
           "domains": {k: [doms(old).get(k), doms(new).get(k)] for k in set(doms(old)) | set(doms(new))
                       if doms(old).get(k) != doms(new).get(k)},
           "settings": {k: [settings(old).get(k), settings(new).get(k)] for k in set(settings(old)) | set(settings(new))
                        if settings(old).get(k) != settings(new).get(k)}}
    out["changed"] = any([out["identity_changed"], out["seats"][0] != out["seats"][1], out["orgs_added"],
                          out["orgs_removed"], out["admins"], out["domains"], out["settings"]])
    return out


def plan(snap: dict, want: dict) -> list[dict]:
    """Change records for the gap between the snapshot and enterprise.yaml. Printed, never run."""
    prof = snap["sections"]["profile"]
    eid = snap.get("id")
    recs = []
    ids = {"profile": "ent-001", "domains": "ent-002", **(want.get("approvals") or {})}  # APPROVED_ACTIONS.yaml row ids
    wp = want.get("profile") or {}
    fields = {"name": "name", "description": "description", "websiteUrl": "website", "location": "location"}
    changes = {fields[k]: v for k, v in wp.items() if k in fields and (prof.get(k) or "") != v}
    if changes:
        recs.append({"std": STANDARD, "kind": "enterprise-profile", "approval": "enterprise/profile",
                     "approval_id": ids["profile"], "mutation": "references/enterprise/mutations/m_profile.graphql",
                     "variables": {"id": eid, **changes}, "before": {k: prof.get(k) for k in wp},
                     "read_back": "references/enterprise/queries/q_profile.graphql"})
    doms = {d["domain"]: d for d in _dig(prof, ("ownerInfo", "domains", "nodes")) or []}
    for d in want.get("domains", []):
        if d not in doms:
            recs.append({"std": STANDARD, "kind": "enterprise-domain-add", "approval": f"enterprise/domain-add/{d}",
                         "approval_id": ids["domains"], "mutation": "references/enterprise/mutations/m_domain_add.graphql",
                         "variables": {"owner": eid, "domain": f"https://{d}"},
                         "then": "the user adds the returned TXT record (dnsHostName, verificationToken) at the DNS host"})
        elif not doms[d].get("isVerified"):
            recs.append({"std": STANDARD, "kind": "enterprise-domain-verify", "approval": f"enterprise/domain-verify/{d}",
                         "approval_id": ids["domains"], "mutation": "references/enterprise/mutations/m_domain_verify.graphql",
                         "variables": {"id": doms[d]["id"]}})
    return recs


def _inline(path: str) -> str:
    """A mutation file's text, comments dropped: writer jobs carry every mutation inline (`-f query='mutation …'`)."""
    text = (REFERENCES.parent / path).read_text(encoding="utf-8")
    return "\n".join(ln for ln in (x.split("#", 1)[0].rstrip() for x in text.splitlines()) if ln.strip())


def plan_jobs(snap: dict, recs: list[dict]) -> list[dict]:
    """scripts/writer.py jobs for `plan` records: {id, phase, kind, org, approval_id, argv, note}. The mutation is inline
    and each variable a `-f` string; `read` is the read-only profile query for the before and after capture. Phase 1 is
    the research's write phase (§3.2); every job's approval_id is its review-page row (`ent-001` profile, `ent-002`
    domains; `approvals:` in enterprise.yaml), which scripts/writer.py checks in APPROVED_ACTIONS.yaml. Never run here."""
    slug = snap.get("slug") or "enterprise"
    read = ["gh", "api", "graphql", "-f", f"query={query_text('q_profile').strip()}", "-f", f"slug={slug}"]
    jobs = []
    for r in recs:
        argv = ["gh", "api", "graphql", "-f", f"query={_inline(r['mutation'])}"]
        for k, v in (r.get("variables") or {}).items():
            argv += ["-f", f"{k}={v}"]
        tail = r["approval"].split("/", 1)[1] if "/" in r["approval"] else r["kind"]
        note = {"enterprise-profile": "Enterprise profile fields to enterprise.yaml (E1; research §2.1).",
                "enterprise-domain-add": "Add the domain at enterprise level (E7); then the user adds the TXT record "
                                         "(dnsHostName, verificationToken) at the DNS host.",
                "enterprise-domain-verify": "Verify the domain once its TXT record resolves (E7)."}.get(r["kind"], r["kind"])
        jobs.append({"id": re.sub(r"[^A-Za-z0-9._:@/+-]+", "-", f"p1:enterprise:{slug}:{tail}")[:200], "phase": "1",
                     "kind": "enterprise", "org": slug, "approval_id": r.get("approval_id") or r["approval"], "argv": argv,
                     "note": note,
                     "read": read, "idempotent": r["kind"] != "enterprise-domain-add"})
    return jobs
