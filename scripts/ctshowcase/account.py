"""Account chart (`account-chart`): one GitHub account's repositories, enterprises and organizations as one tree.

Read-only toward GitHub. `capture` runs GraphQL *queries* through `gh api graphql` (each query file is checked for a
mutation before it runs) and writes a snapshot that names public repositories only: for private and internal
repositories the queries ask GitHub for a count, never a name, so no private name can reach a chart, a fixture or a
log. `render` works offline on that snapshot. It applies the estate gates (excluded owners are left out, T3 orgs wait
for co-owner sign-off, HOLD orgs and exposure-flagged repositories are never named), then writes four files: the
Mermaid source, the dark compositor SVG, its HD PNG, and a Markdown companion that repeats every name as a link and
carries the counts the image leaves out (SVG rules S15 and S16). `capture-query` prints the reads without running them.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from . import STANDARD
from .chips import SEP
from .errors import CHECK_FAILED, OK, NeedsInput, Refused, ShowcaseError

SCHEMA = "account-chart/v1"
ACTIONS = ("capture-query", "capture", "render")
HIDE = ("forks", "archived")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_PAGES = 200
NOT_PUBLIC_KEYS = ("private", "isPrivate", "visibility")
ROLES = ("owner", "member")
CAPTURE_STATES = ("complete", "partial", "uncaptured", "unknown")


# =====================================================================================================
# capture (read-only GraphQL through gh)
# =====================================================================================================
def argv(name: str, **variables) -> list[str]:
    """`gh api graphql -f var=value ... -F query=@FILE`. String variables go raw (-f) so a numeric-looking login or
    cursor is never coerced; the query file is checked for a mutation first."""
    from .resolver import query_path, query_text
    query_text(name)
    out = ["gh", "api", "graphql"]
    for k, v in variables.items():
        if v is not None:
            out += ["-f", f"{k}={v}"]
    return out + ["-F", f"query=@{query_path(name)}"]


def _gh(name: str, **variables) -> dict:
    cmd = argv(name, **variables)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShowcaseError(f"gh api graphql failed: {exc}", log="needs-input:gh")
    try:
        data = json.loads(p.stdout or "{}")
    except ValueError:
        data = {}
    errors = data.get("errors") if isinstance(data, dict) else None
    if errors:
        raise ShowcaseError(f"{name}: {errors[0].get('message')}", log="needs-input:gh")
    if p.returncode != 0:
        raise ShowcaseError(f"{name}: {(p.stderr or p.stdout).strip()[:300]}", log="needs-input:gh")
    return data.get("data") or {}


def _dig(obj, path):
    for k in path:
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def _paged(run, name: str, path: tuple, **variables) -> tuple[dict, list | None, str]:
    """First-page data, captured nodes and completeness; unavailable or interrupted reads never mean empty."""
    first, nodes, after, cursors = None, [], None, set()
    for _ in range(MAX_PAGES):
        try:
            data = run(name, **variables, after=after)
        except ShowcaseError:
            if first is None:
                raise
            return first, nodes, "partial"
        first = data if first is None else first
        conn = _dig(data, path)
        if not isinstance(conn, dict):
            return first or {}, nodes if after is not None else None, "partial" if after is not None else "uncaptured"
        page_nodes = conn.get("nodes")
        if not isinstance(page_nodes, list) or any(not isinstance(n, dict) for n in page_nodes):
            return first or {}, nodes, "partial"
        nodes += page_nodes
        page = conn.get("pageInfo") or {}
        after = page.get("endCursor")
        if page.get("hasNextPage") is False:
            return first or {}, nodes, "complete"
        if page.get("hasNextPage") is not True or not after or after in cursors:
            return first or {}, nodes, "partial"
        cursors.add(after)
    return first or {}, nodes, "partial"


def _repo(node: dict) -> dict | None:
    name = node.get("name")
    if not isinstance(name, str) or not REPO_RE.match(name):
        return None
    lang = (node.get("primaryLanguage") or {}).get("name") if isinstance(node.get("primaryLanguage"), dict) else None
    return {"name": name, "description": " ".join(str(node.get("description") or "").split()),
            "language": lang if isinstance(lang, str) and lang else None,
            "fork": bool(node.get("isFork")), "archived": bool(node.get("isArchived"))}


def _repos(nodes) -> list[dict]:
    seen = {r["name"].lower(): r for r in filter(None, map(_repo, nodes or []))}
    return sorted(seen.values(), key=lambda r: (r["name"].lower(), r["name"]))


def _not_public(node) -> int | None:
    """Owned repositories the viewer can see that are not public (private and internal): a count, never names."""
    a, p = _dig(node, ("all", "totalCount")), _dig(node, ("public", "totalCount"))
    return a - p if type(a) is int and type(p) is int and 0 <= p <= a else None


def _logins(nodes) -> dict[str, str]:
    return {n["login"].lower(): n["login"] for n in nodes or [] if isinstance(n.get("login"), str) and LOGIN_RE.match(n["login"])}


def capture_reads(login: str | None = None) -> dict:
    """`capture-query`: the read commands `capture` runs, printed, never run here."""
    if login is not None and not LOGIN_RE.match(login):
        raise ShowcaseError(f"not a GitHub login: {login!r}", log="usage")
    who = login or "VIEWER"
    reads = [{"name": "viewer", "argv": argv("account_viewer")},
             {"name": "account", "argv": argv("account_user", login=who)},
             {"name": "organizations", "argv": argv("account_orgs", login=who)},
             {"name": "enterprises", "argv": argv("account_enterprises")},
             {"name": "enterprise-organizations", "argv": argv("account_enterprise_orgs", slug="SLUG")},
             {"name": "organization", "argv": argv("account_org", org="ORG")}]
    return {"login": login, "reads": reads,
            "paginate": ["user.repositories", "user.organizations", "viewer.enterprises", "enterprise.organizations",
                         "organization.repositories"],
            "note": "Read-only. Page each connection with -f after=<endCursor> while hasNextPage. Enterprises are read for "
                    "the signed-in viewer only (roles too). Non-public repositories are counted (all minus public), never "
                    "named; `account-chart capture` runs these reads and writes the snapshot."}


def _capture_owner(resolver, login: str, allow_t3: bool) -> None:
    resolver.check_owner(login, allow_t3=allow_t3)
    if resolver.family_hold(login):
        raise Refused(f"{login} is on HOLD", log="hold")


def capture(login: str | None = None, run=_gh, today: str | None = None, *, resolver=None,
            allow_t3: bool = False) -> dict:
    """Run the reads and return an account-chart/v1 snapshot (public repository names, non-public counts)."""
    from .config import load_brand
    from .resolver import Resolver
    resolver = resolver or Resolver.from_paths(load_brand())
    if login is not None:
        login = login.strip()
        if not LOGIN_RE.fullmatch(login):
            raise ShowcaseError(f"not a GitHub login: {login!r}", log="usage")
        _capture_owner(resolver, login, allow_t3)  # explicit refusals precede even the viewer read
    viewer = _dig(run("account_viewer"), ("viewer", "login"))
    if not isinstance(viewer, str) or not viewer:
        raise NeedsInput("gh", "gh is not signed in (gh auth status)")
    login = (login or viewer).strip()
    if not LOGIN_RE.match(login):
        raise ShowcaseError(f"not a GitHub login: {login!r}", log="usage")
    _capture_owner(resolver, login, allow_t3)
    is_viewer = login.lower() == viewer.lower()
    first, nodes, state = _paged(run, "account_user", ("user", "repositories"), login=login)
    user = first.get("user")
    if not isinstance(user, dict) or nodes is None:
        raise NeedsInput("account", f"{login} is not a user account {viewer} can see")
    notes: list[str] = []
    _capture_owner(resolver, user.get("login") or login, allow_t3)

    def permitted_repos(owner, items, state, metadata):
        out = []
        for repo in _repos(items):
            try:
                resolver.check_owner(owner, allow_t3=allow_t3, repo=repo["name"])
            except Refused as exc:
                notes.append(f"{exc.log}:{owner}")
            else:
                out.append(repo)
        total = _dig(metadata, ("public", "totalCount"))
        if len(out) != len(items or []) or (type(total) is int and total != len(items or [])):
            state = "partial"
        return {"repositories": out, "capture_state": state}

    _, org_nodes, org_state = _paged(run, "account_orgs", ("user", "organizations"), login=login)
    member_of = _logins(org_nodes)
    enterprises = []
    ent_state = "uncaptured"
    if is_viewer:
        _, ent_nodes, ent_state = _paged(run, "account_enterprises", ("viewer", "enterprises"))
        for e in ent_nodes or []:
            slug = e.get("slug")
            if not isinstance(slug, str) or not SLUG_RE.match(slug):
                continue
            _, eo, eo_state = _paged(run, "account_enterprise_orgs", ("enterprise", "organizations"), slug=slug)
            if eo is None:
                notes.append(f"enterprise-orgs-unavailable:{slug}")
            enterprises.append({"slug": slug, "name": " ".join(str(e.get("name") or slug).split()),
                                "role": "owner" if e.get("viewerIsAdmin") else "member",
                                "capture_state": eo_state,
                                "organizations": sorted(_logins(eo).values(), key=str.lower)})
    else:
        notes.append("enterprises:viewer-only")  # GitHub reports enterprises and roles for the signed-in account only
    logins = dict(member_of)
    for e in enterprises:
        for o in e["organizations"]:
            logins.setdefault(o.lower(), o)
    orgs = []
    for key in sorted(logins):
        o = logins[key]
        try:
            _capture_owner(resolver, o, allow_t3)
            ofirst, rnodes, ostate = _paged(run, "account_org", ("organization", "repositories"), org=o)
            _capture_owner(resolver, (ofirst.get("organization") or {}).get("login") or o, allow_t3)
        except Refused as exc:
            notes.append(f"{exc.log}:{o}")
            ofirst, rnodes, ostate = {}, None, "uncaptured"
        except ShowcaseError:
            ofirst, rnodes, ostate = {}, None, "uncaptured"
        org = ofirst.get("organization")
        if not isinstance(org, dict) or rnodes is None:
            notes.append(f"org-uncaptured:{o}")
            orgs.append({"login": o, "name": "", "member": key in member_of, "role": None, "captured": False,
                         "capture_state": "uncaptured", "repositories": [], "not_public": None})
            continue
        role = None
        if is_viewer:
            role = "owner" if org.get("viewerCanAdminister") else ("member" if key in member_of else None)
        orgs.append({"login": org.get("login") or o, "name": " ".join(str(org.get("name") or "").split()),
                     "member": key in member_of, "role": role, "captured": True,
                     **permitted_repos(org.get("login") or o, rnodes, ostate, org),
                     "not_public": _not_public(org)})
    acct = {"login": user.get("login") or login}
    for k, src in (("name", "name"), ("company", "company"), ("location", "location"), ("website", "websiteUrl")):
        acct[k] = " ".join(str(user.get(src) or "").split())
    return {"schema": SCHEMA, "std": STANDARD, "captured": today or date.today().isoformat(), "viewer": viewer,
            "account": acct, **permitted_repos(acct["login"], nodes, state, user), "not_public": _not_public(user),
            "organizations_state": org_state, "enterprises_state": ent_state,
            "enterprises": sorted(enterprises, key=lambda e: (e["name"].casefold(), e["slug"])),
            "organizations": orgs, "notes": sorted(set(notes))}


def snapshot_text(snap: dict) -> str:
    return json.dumps(snap, indent=1, ensure_ascii=False) + "\n"


# =====================================================================================================
# snapshot validation
# =====================================================================================================
def _bad(msg: str, log: str = "usage") -> ShowcaseError:
    return ShowcaseError(f"snapshot: {msg}", log=log)


def _clean_repos(items, where: str) -> list[dict]:
    if not isinstance(items, list):
        raise _bad(f"{where}.repositories must be a list")
    out = []
    for r in items:
        if not isinstance(r, dict) or not isinstance(r.get("name"), str) or not REPO_RE.match(r["name"]):
            raise _bad(f"{where}: a repository needs a valid name")
        for k in NOT_PUBLIC_KEYS:  # a capture names public repositories only; a hand-edited one is refused (privacy)
            if k in r and r[k] not in (False, "public", "PUBLIC", None):
                raise ShowcaseError(f"snapshot: {where} names a repository that is not public; refused",
                                    log="privacy:not-public-repository")
        out.append({"name": r["name"], "description": " ".join(str(r.get("description") or "").split()),
                    "language": r.get("language") if isinstance(r.get("language"), str) and r.get("language") else None,
                    "fork": bool(r.get("fork")), "archived": bool(r.get("archived"))})
    return sorted(out, key=lambda r: (r["name"].lower(), r["name"]))


def _count(v, where: str) -> int | None:
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise _bad(f"{where}.not_public must be a non-negative integer")
    return v


def _state(row: dict, key: str = "capture_state", *, default: str = "unknown") -> str:
    value = row.get(key, default)
    if value not in CAPTURE_STATES:
        raise _bad(f"{key} must be one of {', '.join(CAPTURE_STATES)}")
    return value


def _repository_state(row: dict, *, account: bool = False) -> str:
    captured = row.get("captured", True if account else None)
    if captured is not None and type(captured) is not bool and not account:
        raise _bad("organization.captured must be a boolean or null")
    complete = (account or captured is True) and isinstance(row.get("repositories"), list)
    state = _state(row, default="complete" if complete else "unknown")
    return "uncaptured" if captured is False else state


def validate(snap) -> dict:
    """A clean copy of an account-chart/v1 snapshot; refuses one that is malformed or names a non-public repository."""
    if not isinstance(snap, dict) or snap.get("schema") != SCHEMA:
        raise _bad(f"not an {SCHEMA} snapshot (run `account-chart capture`)")
    acct = snap.get("account")
    if not isinstance(acct, dict) or not isinstance(acct.get("login"), str) or not LOGIN_RE.match(acct["login"]):
        raise _bad("account.login is missing or invalid")
    captured = str(snap.get("captured") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", captured):
        raise _bad("captured must be an absolute date (YYYY-MM-DD)")
    ents = []
    for e in snap.get("enterprises") or []:
        if not isinstance(e, dict) or not isinstance(e.get("slug"), str) or not SLUG_RE.match(e["slug"]):
            raise _bad("an enterprise needs a valid slug")
        orgs = e.get("organizations") or []
        if not isinstance(orgs, list) or not all(isinstance(o, str) and LOGIN_RE.match(o) for o in orgs):
            raise _bad(f"enterprise {e['slug']}: organizations must be logins")
        ents.append({"slug": e["slug"], "name": " ".join(str(e.get("name") or e["slug"]).split()),
                     "role": e.get("role") if e.get("role") in ROLES else None, "organizations": list(orgs),
                     "capture_state": _state(e, default="complete" if isinstance(e.get("organizations"), list) else "unknown")})
    orgs = []
    seen = set()
    for o in snap.get("organizations") or []:
        if not isinstance(o, dict) or not isinstance(o.get("login"), str) or not LOGIN_RE.match(o["login"]):
            raise _bad("an organization needs a valid login")
        if o["login"].lower() in seen:
            raise _bad(f"organization {o['login']} is listed twice")
        seen.add(o["login"].lower())
        orgs.append({"login": o["login"], "name": " ".join(str(o.get("name") or "").split()),
                     "member": bool(o.get("member", True)), "role": o.get("role") if o.get("role") in ROLES else None,
                     "captured": o.get("captured"), "capture_state": _repository_state(o),
                     "repositories": _clean_repos(o.get("repositories") or [], o["login"]),
                     "not_public": _count(o.get("not_public"), o["login"])})
    return {"schema": SCHEMA, "std": snap.get("std") or STANDARD, "captured": captured,
            "viewer": snap.get("viewer") if isinstance(snap.get("viewer"), str) else None,
            "account": {"login": acct["login"], **{k: " ".join(str(acct.get(k) or "").split())
                                                   for k in ("name", "company", "location", "website")}},
            "repositories": _clean_repos(snap.get("repositories") or [], "account"),
            "not_public": _count(snap.get("not_public"), "account"),
            "capture_state": _repository_state(snap, account=True),
            **{f"{key}_state": _state(snap, f"{key}_state", default="complete" if isinstance(snap.get(key), list) else "unknown")
               for key in ("organizations", "enterprises")},
            "enterprises": sorted(ents, key=lambda e: (e["name"].casefold(), e["slug"])), "organizations": orgs,
            "notes": [n for n in snap.get("notes") or [] if isinstance(n, str)]}


def load_snapshot(path: str | Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShowcaseError(f"cannot read snapshot {path}: {exc}", log="usage")
    return validate(raw)


# =====================================================================================================
# the model: estate gates, styles and order
# =====================================================================================================
def _tier_rank(row: dict) -> int:
    t = str(row.get("tier") or "")
    return int(t[1]) if t[:1] == "T" and t[1:2].isdigit() else 9


def neutral_style(brand) -> dict:
    """The house fonts and canvas with the chart's neutral tokens: for orgs without a brand row or with a pending
    identity, which never inherit CompleteTech art."""
    from .config import deep_merge
    n = brand.raw["chart"]["neutral"]
    st = brand.family("completetech")
    tokens = deep_merge(st["tokens"], {k: n[k] for k in ("eyebrow", "title", "accent", "accent_mid", "accent_deep",
                                                         "plate_low")})
    tokens["edge"] = dict(n["edge"])
    tokens["bar"] = {**tokens["bar"], "from": n["bar"]["from"], "to": n["bar"]["to"]}
    return {**st, "tokens": tokens, "company_label": brand.raw["chart"]["labels"]["organization"], "eyebrow_case": "upper",
            "name": "neutral"}


def enterprise_style(brand, base: dict) -> dict:
    e = brand.raw["chart"]["enterprise"]
    tokens = {**base["tokens"], "eyebrow": e["eyebrow"], "accent": e["accent"], "plate_low": e["fill"],
              "edge": {"color": e["accent"], "opacity": e["edge_opacity"]},
              "bar": {**base["tokens"]["bar"], "from": e["accent"], "to": e["accent"]}}
    return {**base, "tokens": tokens}


def org_style(brand, login: str) -> tuple[dict, bool, str | None]:
    """(style, neutral, family) for an org: its family's tokens, or the neutral style."""
    from .errors import ConfigError
    row = brand.org(login)
    fam = row.get("family") if row.get("known") else None
    if not fam or ((brand.raw.get("families") or {}).get(fam) or {}).get("identity_pending"):
        return neutral_style(brand), True, None
    try:
        return brand.style(login), False, fam
    except (NeedsInput, ConfigError):
        return neutral_style(brand), True, None


def _eyebrow(style: dict, row: dict, neutral: bool) -> tuple[str, str]:
    """(eyebrow, the company label alone): the org tile's eyebrow rule."""
    label = style["company_label"]
    eb = f"{label}{SEP}{row['eyebrow']}" if (not neutral and row.get("eyebrow")) else label
    if style.get("eyebrow_case") == "upper":
        return eb.upper(), label.upper()
    return eb, label


def _host(url: str) -> str:
    m = re.match(r"^https?://([^/]+)", url or "")
    return m.group(1).lower().removeprefix("www.") if m else ""


def build(snap: dict, brand, *, resolver=None, flags: dict | None = None, allow_t3: bool = False,
          hide: tuple | list = (), private: str = "note") -> tuple[dict, list[str]]:
    """The chart model from a validated snapshot, after the estate gates, and the logs of everything left out."""
    from .org import Estate, _t3_granted, _t3_held
    r = resolver or brand.resolver()
    estate = Estate(brand, r, flags=flags or {})
    cfg = brand.raw["chart"]
    labels = cfg["labels"]
    logs: list[str] = list(snap.get("notes") or [])
    login = snap["account"]["login"]
    _capture_owner(r, login, allow_t3)
    counts = {"public": 0, "named": 0, "withheld": 0, "hidden": 0, "not_public": 0, "organizations": 0,
              "enterprises": 0, "omitted_orgs": 0, "unknown_not_public": 0}
    languages: dict[str, int] = {}

    def gate_repos(owner: str, repos: list[dict], held: bool) -> list[dict]:
        out = []
        for rp in repos:
            full = f"{owner}/{rp['name']}"
            counts["public"] += 1
            if held:
                counts["withheld"] += 1
                continue
            if _t3_held(estate, full, allow_t3):
                logs.append(f"t3-signoff:{full}")  # a repository withdrawn from a wildcard grant stays unnamed
                counts["withheld"] += 1
                continue
            if estate.exposure(full):
                logs.append("exposure-withheld")  # never logged by name (q24)
                counts["withheld"] += 1
                continue
            if ("forks" in hide and rp["fork"]) or ("archived" in hide and rp["archived"]):
                counts["hidden"] += 1
                continue
            counts["named"] += 1
            if rp["language"]:
                languages[rp["language"]] = languages.get(rp["language"], 0) + 1
            out.append({**rp, "full_name": full, "url": f"https://github.com/{full}"})
        return out

    def notes_for(named: list, public: int | None, not_public: int | None, held: bool, state: str) -> list[str]:
        if held:
            return ["held"]
        out = [state] if state != "complete" else []
        if not_public and private == "note":
            out.append("private")
        if not named and public == 0 and not out and not_public is not None:
            out.append("empty")
        if not_public is None:
            out.append("unknown_private")
        return out

    def repository_facts(source: dict, owner: str, held: bool) -> dict:
        state = source["capture_state"]
        repos = source["repositories"] if state in ("complete", "partial") else []
        named = gate_repos(owner, repos, held)
        count = source["not_public"] if state in ("complete", "partial") else None
        counts["not_public"] += count or 0
        counts["unknown_not_public"] += count is None
        public = len(repos) if state == "complete" else None
        return {"repos": named, "public": public, "not_public": count, "held": held,
                "capture_state": state, "captured": None if state == "unknown" else state != "uncaptured",
                "notes": notes_for(named, public, count, held, state)}

    def org_node(o: dict) -> dict | None:
        lg = o["login"]
        st = r.owner_status(lg)
        if st == "excluded":
            logs.append(f"exempt:{lg}")
            counts["omitted_orgs"] += 1
            return None
        if r.is_placeholder(lg):
            logs.append(f"placeholder:{lg}")
            counts["omitted_orgs"] += 1
            return None
        if st == "t3" and not (allow_t3 and _t3_granted(lg)):
            logs.append(f"t3-signoff:{lg}")  # T3 work waits for co-owner sign-off (decision 12)
            counts["omitted_orgs"] += 1
            return None
        held = st == "hold" or r.family_hold(lg)
        if held:
            logs.append(f"hold:{lg}")
        style, neutral, family = org_style(brand, lg)
        row = brand.org(lg)
        if not row.get("known"):
            logs.append(f"needs-input:org-row:{lg}")  # neutral until it has a brand.yaml row (`brand add-org`)
        elif neutral:
            logs.append(f"needs-input:brand-identity:{lg}")  # a pending identity never borrows CompleteTech art
        name = (row.get("display_name") if row.get("known") else None) or o["name"] or lg
        eyebrow, short = _eyebrow(style, row, neutral)
        mark = brand.asset(row.get("mark")) if row.get("known") and row.get("mark") else None
        counts["organizations"] += 1
        return {"kind": "org", "login": lg, "name": name, "eyebrow": eyebrow, "eyebrow_short": short, "sub": f"@{lg}",
                "role": o["role"], "member": o["member"], "style": style, "neutral": neutral, "family": family,
                "mark": mark if mark and mark.is_file() else None, "initials": _initials(name), "url": f"https://github.com/{lg}",
                "flagship": bool(row.get("flagship")), "tier": _tier_rank(row) if row.get("known") else 9,
                **repository_facts(o, lg, held)}

    # -- the account --------------------------------------------------------------------------------
    row = brand.org(login)
    if row.get("known"):
        acct_style, _, acct_family = org_style(brand, login)
    else:
        acct_style, acct_family = brand.family("completetech"), "completetech"
    prof = (row.get("profile") or {}) if row.get("known") else {}
    a = snap["account"]
    name = prof.get("name") or (row.get("display_name") if row.get("known") else None) or a["name"] or login
    eyebrow = f"{acct_style['company_label']}{SEP}{labels['account']}"
    if acct_style.get("eyebrow_case") == "upper":
        eyebrow = eyebrow.upper()
    chips = []
    for c in prof.get("chips") or []:
        kind, _, text = str(c).partition(":")
        if kind in ("key", "attr") and text:
            chips.append((text, kind))
    if not chips:
        for text, kind in ((_host(a["website"]), "key"), (a["company"].lstrip("@"), "attr"), (a["location"], "attr")):
            if text:
                chips.append((text, kind))
    acct_mark = brand.asset(row.get("mark")) if row.get("known") and row.get("mark") else None
    account = {"login": login, "name": name, "eyebrow": eyebrow, "handle": f"github.com/{login}", "chips": chips[:4],
               "style": acct_style, "mark": acct_mark if acct_mark and acct_mark.is_file() else None,
               "initials": _initials(name), "url": f"https://github.com/{login}"}

    # -- personal repositories ----------------------------------------------------------------------
    personal = {"kind": "personal", "login": login, "name": labels["personal_title"], "eyebrow": labels["personal"],
                "eyebrow_short": labels["personal"], "sub": f"@{login}", "role": None, "style": acct_style,
                "neutral": False, "family": acct_family, "mark": account["mark"], "initials": account["initials"],
                "url": account["url"], **repository_facts(snap, login, False)}

    # -- organizations and enterprises ----------------------------------------------------------------
    fam_order = {f: i for i, f in enumerate(brand.raw.get("families") or {})}

    def order(n: dict):
        band = 0 if n["family"] == acct_family else (1 if not n["neutral"] else 2)
        return (band, fam_order.get(n["family"], 99), 0 if n["flagship"] else 1, n["tier"], n["name"].casefold(),
                n["login"].lower())

    by_login = {o["login"].lower(): o for o in snap["organizations"]}
    placed: set[str] = set()
    enterprises = []
    for e in snap["enterprises"]:
        nodes = []
        for lg in e["organizations"]:
            o = by_login.get(lg.lower())
            if lg.lower() in placed:
                continue
            if o is None:
                o = {"login": lg, "name": "", "member": False, "role": None, "repositories": [],
                     "capture_state": "uncaptured", "not_public": None}
                logs.append(f"org-uncaptured:{lg}")
            placed.add(lg.lower())
            n = org_node(o)
            if n:
                nodes.append(n)
        counts["enterprises"] += 1
        est = enterprise_style(brand, acct_style)
        enterprises.append({"kind": "enterprise", "slug": e["slug"], "name": e["name"], "eyebrow": labels["enterprise"],
                            "eyebrow_short": labels["enterprise"], "sub": f"enterprises/{e['slug']}", "role": e["role"],
                            "style": est, "url": f"https://github.com/enterprises/{e['slug']}",
                            "capture_state": e["capture_state"],
                            "orgs": sorted(nodes, key=order)})
    standalone = [n for o in snap["organizations"] if o["login"].lower() not in placed for n in [org_node(o)] if n]
    standalone.sort(key=order)

    roles = sorted({n["role"] for n in standalone + [x for e in enterprises for x in e["orgs"]] if n["role"]} |
                   {e["role"] for e in enterprises if e["role"]})
    legend = [k for k, _ in sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    n_orgs = counts["organizations"]
    title = f"GitHub account map of {name} (@{login})"
    parts = ["personal repositories"]
    if counts["enterprises"]:
        parts.append(f"{counts['enterprises']} enterprise" + ("s" if counts["enterprises"] != 1 else ""))
    parts.append(f"{n_orgs} organization" + ("s" if n_orgs != 1 else ""))
    desc = (f"{', '.join(parts[:-1])} and {parts[-1]}" if len(parts) > 1 else parts[0]) + ", each with its public repositories"
    from .chart import note_text
    coverage = [f"{n['login']}: {note_text(n['capture_state'], labels)}"
                for n in [personal, *standalone, *[o for e in enterprises for o in e["orgs"]]]
                if n["capture_state"] != "complete"]
    coverage += [f"{key}: {note_text(snap[f'{key}_state'], labels)}" for key in ("organizations", "enterprises")
                 if snap[f"{key}_state"] != "complete"]
    coverage += [f"{e['slug']} organizations: {note_text(e['capture_state'], labels)}" for e in enterprises
                 if e["capture_state"] != "complete"]
    if coverage:
        desc += ". " + "; ".join(coverage)
    if counts["unknown_not_public"]:
        desc += ". Some private or internal repository counts are unknown"
    model = {"account": account, "personal": personal, "enterprises": enterprises, "orgs": standalone, "counts": counts,
             "roles": roles, "legend_languages": legend or ["default"], "title": title, "desc": desc,
             "captured": snap["captured"], "viewer": snap.get("viewer"), "coverage": coverage,
             **{f"{key}_state": snap[f"{key}_state"] for key in ("organizations", "enterprises")}}
    return model, sorted(set(logs))


def _initials(name: str) -> str:
    from .chart import _initials as initials
    return initials(name)


# =====================================================================================================
# Markdown companion (S15: every name repeated as a link; S16: the counts live here, not in the image)
# =====================================================================================================
def _md(s: str) -> str:
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", " ".join((s or "").split()))


def _attr(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def alt_text(model: dict) -> str:
    c = model["counts"]
    return (f"{model['title']}: {model['desc']}. {c['named']} public repositories are named; "
            f"the list below repeats each one as a link.")


def markdown(model: dict, files: dict) -> str:
    """The README block for the chart: the image (linking to the full-resolution PNG), the counts, and every repository
    in the map as a link, grouped like the tree."""
    c = model["counts"]
    acct = model["account"]
    labels_role = {"owner": "owner", "member": "member"}
    img = files["svg"]
    big = files.get("png") or files["svg"]
    out = [f"<!-- Generated by github-showcase-skill `showcase.py account-chart render` from the {model['captured']} "
           f"snapshot ({STANDARD}). Regenerate it; do not edit by hand. -->", "",
           '<p align="center">', f'  <a href="{big}"><img src="{img}" alt="{_attr(alt_text(model))}" width="100%"></a>',
           "</p>", ""]
    facts = [f"{c['named']} public repositories across "
             + (f"{c['enterprises']} enterprise{'s' if c['enterprises'] != 1 else ''} and " if c["enterprises"] else "")
             + f"{c['organizations']} organization{'s' if c['organizations'] != 1 else ''}"]
    if c["not_public"]:
        facts.append(f"{c['not_public']} private or internal repositories are counted, never named")
    if c["withheld"]:
        facts.append(f"{c['withheld']} public repositories are withheld (on hold, awaiting co-owner sign-off or under "
                     "exposure review)")
    if c["hidden"]:
        facts.append(f"{c['hidden']} forks or archived repositories are hidden from this render")
    if c["omitted_orgs"]:
        facts.append(f"{c['omitted_orgs']} organizations are outside this map (excluded, awaiting sign-off or merged)")
    facts += model.get("coverage", [])
    if c.get("unknown_not_public"):
        facts.append("some private or internal repository counts are unknown; shown counts include only captured data")
    out += ["<sub>" + ". ".join(facts) + f". Captured {model['captured']}. Mermaid source: "
            f"<a href=\"{files['mmd']}\">{files['mmd']}</a>.</sub>", ""]
    out += ["<details>", "<summary>Every repository in this map</summary>", ""]

    def repo_line(rp: dict) -> str:
        tags = [t for t, on in (("fork", rp["fork"]), ("archived", rp["archived"])) if on]
        line = f"- [`{rp['name']}`]({rp['url']})"
        if tags:
            line += " <sub>" + ", ".join(tags) + "</sub>"
        if rp["description"]:
            line += f": {_md(rp['description'])}"
        return line

    def lane(node: dict, level: str) -> list[str]:
        head = f"{level} [{_md(node['name'])}]({node['url']})"
        if node["kind"] == "org":
            head += f" <sub>@{node['login']}" + (f" · {labels_role[node['role']]}" if node.get("role") else "") + "</sub>"
        lines = [head, ""]
        lines += [repo_line(rp) for rp in node["repos"]]
        extra = []
        if node.get("held"):
            extra.append("on hold: its repositories are not named")
        if node.get("capture_state", "complete") != "complete":
            from .chart import note_text
            extra.append(note_text(node["capture_state"], {}))
        if node["not_public"]:
            extra.append(f"{node['not_public']} private or internal, not named")
        elif node["not_public"] is None:
            extra.append("private or internal repository count unknown")
        if not node["repos"] and not extra:
            extra.append("no public repositories" if not node["public"] else "no repositories shown")
        if extra:
            lines.append(f"- <sub>{'; '.join(extra)}</sub>")
        return lines + [""]

    p = dict(model["personal"], name=f"{acct['name']} (@{acct['login']})")
    out += lane(p, "####")
    for ent in model["enterprises"]:
        role = f" <sub>enterprise · {labels_role[ent['role']]}</sub>" if ent.get("role") else " <sub>enterprise</sub>"
        out += [f"### [{_md(ent['name'])}]({ent['url']}){role}", ""]
        for org in ent["orgs"]:
            out += lane(org, "####")
    if model["orgs"]:
        out += ["### Organizations", ""]
        for org in model["orgs"]:
            out += lane(org, "####")
    out += ["</details>", ""]
    return "\n".join(out)


# =====================================================================================================
# CLI
# =====================================================================================================
def register(sub) -> None:
    s = sub.add_parser("account-chart", help="map one account's repositories, enterprises and organizations: Mermaid "
                                             "source, dark SVG, HD PNG and a Markdown companion (read-only capture)")
    s.add_argument("action", choices=ACTIONS, help="capture-query prints the read-only queries (no network); capture "
                                                   "runs them and writes the snapshot; render works offline on it")
    s.add_argument("login", nargs="?", help="capture, capture-query: the account (default: the signed-in viewer)")
    s.add_argument("--out", help="capture: the snapshot file to write (account-chart/v1 JSON)")
    s.add_argument("--snapshot", help="render: a snapshot written by `account-chart capture`")
    s.add_argument("--out-dir", help="render: directory for NAME.mmd, NAME.svg, NAME.png and NAME.md")
    s.add_argument("--name", default="account-chart", help="render: output file stem (default account-chart)")
    s.add_argument("--width", type=int, default=2400, help="render: canvas width in px, 1600-4800 (default 2400)")
    s.add_argument("--scale", type=int, choices=(1, 2, 3, 4), default=2,
                   help="render: PNG pixels per px (default 2; lowered automatically above 120 megapixels)")
    s.add_argument("--hide", action="append", choices=HIDE, default=[], help="render: leave forks or archived "
                                                                             "repositories out (repeatable)")
    s.add_argument("--private", choices=("note", "omit"), default="note",
                   help="render: note (default) shows a 'private work' pill where an owner has non-public repositories "
                        "(never a name or a count); omit leaves it out")
    s.add_argument("--avatar", help="render: the account's avatar image (default: its brand mark, else a monogram)")
    s.add_argument("--no-png", action="store_true", help="render: skip the HD PNG")
    s.add_argument("--mmdc", nargs="?", const="mmdc", metavar="PATH",
                   help="render: also render NAME.mermaid.png from the Mermaid source with mermaid-cli (optional; "
                        "browser output, not byte-deterministic)")
    s.add_argument("--mmdc-config", metavar="FILE", help="render: puppeteer config JSON passed to mmdc -p")
    s.add_argument("--registry", help="capture/render: registry/estate.yaml for the org resolver and leak check (read only)")
    s.add_argument("--decisions", help="render: decisions/decisions.json (exposure flags keep repositories unnamed)")
    for flag, what in (("--approved", "decisions/approved.tsv"), ("--approved-yaml", "decisions/APPROVED_ACTIONS.yaml"),
                       ("--actions", "decisions/estate-actions.json")):
        s.add_argument(flag, help=f"capture/render: {what} for the org resolver (default: the bundle's)")
    s.add_argument("--allow-t3", action="store_true", default=argparse.SUPPRESS, help="T3 orgs after co-owner sign-off")
    s.set_defaults(func=cmd_account_chart)


def _inputs(args, brand) -> list[Path]:
    """Protect named inputs and the same default policy/config files the shared loaders read."""
    from . import signoff
    from .config import LOCK
    from .resolver import estate_root
    paths = [brand.path, LOCK, signoff.record_file()]
    if getattr(args, "mmdc", None):
        paths.append(shutil.which(args.mmdc) or args.mmdc)
    paths += [getattr(args, key, None) for key in ("snapshot", "avatar", "mmdc_config", "registry", "decisions",
                                                 "approved", "approved_yaml", "actions", "t3_signoff_file")]
    root = estate_root()
    if root:
        paths += [root / name for name in ("registry/estate.yaml", "decisions/decisions.json", "decisions/approved.tsv",
                                           "decisions/APPROVED_ACTIONS.yaml", "decisions/estate-actions.json")]
    return [Path(p) for p in paths if p is not None]


def _preflight(paths, inputs=()) -> dict:
    """Inspect every lexical ancestor before resolving aliases; never follow an output link to write."""
    states, resolved = {}, []
    try:
        sources = [p.resolve() for p in inputs]
    except RuntimeError as exc:
        raise ShowcaseError("account-chart input path cannot be resolved", log="account-chart:path") from exc
    for path in paths:
        absolute = path.absolute()
        for parent in reversed(absolute.parents):
            try:
                info = parent.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(info.st_mode):
                raise ShowcaseError("account-chart output ancestors must be real directories", log="account-chart:path")
        try:
            info = absolute.lstat()
        except FileNotFoundError:
            info = None
        if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            raise ShowcaseError("account-chart outputs must be unlinked regular files", log="account-chart:path")
        target = absolute.resolve()
        for other in [*sources, *resolved]:
            if target == other or (target.exists() and other.exists() and target.samefile(other)):
                raise ShowcaseError("account-chart outputs must be distinct from inputs and each other",
                                    log="account-chart:path")
        resolved.append(target)
        states[path] = (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns,
                        info.st_ctime_ns, info.st_nlink) if info else None
    return states


def _publish(outputs, inputs, states) -> None:
    from .formatting import write_formatted_outputs
    if _preflight(states, inputs) != states:
        raise ShowcaseError("account-chart output changed during generation", log="account-chart:path")
    write_formatted_outputs(outputs)


def cmd_account_chart(args):
    if args.action == "capture-query":
        return {"command": "account-chart", "action": "capture-query", "result": "ok", **capture_reads(args.login),
                "logs": []}, OK
    if args.action == "capture":
        if not args.out:
            raise ShowcaseError("account-chart capture needs --out FILE", log="usage")
        from .config import load_brand, t3_signed_off
        from .resolver import Resolver
        brand = load_brand(getattr(args, "config", None))
        inputs = _inputs(args, brand)
        path = Path(args.out)
        states = _preflight([path], inputs)
        resolver = Resolver.from_paths(brand, args.registry, args.approved, args.approved_yaml, args.actions)
        snap = capture(args.login, resolver=resolver, allow_t3=t3_signed_off())
        _publish([(path, snapshot_text(snap).encode("utf-8"))], inputs, states)
        n = sum(len(o["repositories"]) for o in snap["organizations"]) + len(snap["repositories"])
        return {"command": "account-chart", "action": "capture", "owner": snap["account"]["login"], "result": "ok",
                "out": args.out, "counts": {"organizations": len(snap["organizations"]),
                                            "enterprises": len(snap["enterprises"]), "public_repositories": n},
                "logs": snap["notes"]}, OK
    return render(args)


def render(args):
    from . import chart, svglint
    from .config import load_brand, t3_signed_off
    from .org import _default_decisions, estate_leak_scope, load_flags, public_leaks
    from .resolver import Resolver
    from .scene import png_bytes
    from .typeset import Fonts
    if not args.snapshot or not args.out_dir:
        raise ShowcaseError("account-chart render needs --snapshot FILE and --out-dir DIR", log="usage")
    if not NAME_RE.match(args.name) or re.search(r"-(dark|light)$", args.name):
        raise ShowcaseError("--name must be a lower-case file stem without a -dark/-light suffix (decision 21)", log="usage")
    if not chart.W_MIN <= args.width <= chart.W_MAX:
        raise ShowcaseError(f"--width must be {chart.W_MIN}-{chart.W_MAX} px", log="usage")
    brand = load_brand(getattr(args, "config", None))
    out_dir = Path(args.out_dir)
    files = {"mmd": f"{args.name}.mmd", "svg": f"{args.name}.svg", "md": f"{args.name}.md"}
    if not args.no_png:
        files["png"] = f"{args.name}.png"
    if args.mmdc:
        files["mermaid"] = f"{args.name}.mermaid.png"
    inputs = _inputs(args, brand)
    states = _preflight([out_dir / name for name in files.values()], inputs)
    snap = load_snapshot(args.snapshot)
    resolver = Resolver.from_paths(brand, args.registry, args.approved, args.approved_yaml, args.actions)
    flags = load_flags(args.decisions or _default_decisions())
    model, logs = build(snap, brand, resolver=resolver, flags=flags, allow_t3=t3_signed_off(), hide=tuple(args.hide),
                        private=args.private)
    nodes = [model["account"], model["personal"], *model["orgs"],
             *[o for e in model["enterprises"] for o in e["orgs"]]]
    inputs += [n["mark"] for n in nodes if n.get("mark")]
    inputs += [brand.font_file(key) for key in brand.raw["fonts"]]
    _preflight(states, inputs)
    if args.avatar and not Path(args.avatar).is_file():
        raise ShowcaseError(f"--avatar {args.avatar} is not a file", log="usage")
    fonts = Fonts(brand)
    laid = chart.layout(model, brand, fonts, width=args.width, avatar=args.avatar)
    svg = chart.svg(laid, fonts)
    lint = svglint.lint_bytes("chart", svg.encode("utf-8"), str(out_dir / files["svg"]))
    mmd, minfo = chart.mermaid(model, brand)
    md = markdown(model, files)
    if minfo["bytes"] > 50_000:
        logs.append(f"mermaid-size:{minfo['bytes']}")  # over Mermaid's default maxTextSize: GitHub may refuse to draw it
    if minfo["edges"] + minfo["invisible_links"] > 500:
        logs.append(f"mermaid-edges:{minfo['edges'] + minfo['invisible_links']}")  # over Mermaid's default maxEdges
    res = {"command": "account-chart", "action": "render", "owner": model["account"]["login"], "result": "ok",
           "counts": model["counts"], "size": {"width": laid.w, "height": laid.h}, "lint": lint, "mermaid": minfo,
           "coverage": model["coverage"]}
    if lint["result"] != "PASS":
        return {**res, "result": "fail", "logs": sorted(set(logs))}, CHECK_FAILED
    if resolver.registry:  # defence in depth: the snapshot names public repositories only; check against the estate too
        from .org import Estate
        scope, slog = estate_leak_scope(Estate(brand, resolver, flags=flags))
        named = [rp for n in [model["personal"], *model["orgs"], *[o for e in model["enterprises"] for o in e["orgs"]]]
                 for rp in n["repos"]]
        scope["public_names"] |= {rp["name"].lower() for rp in named}
        scope["public_texts"] = list(scope["public_texts"]) + [rp["description"] for rp in named if rp["description"]]
        hits = sorted(set(public_leaks(mmd, scope) + public_leaks(md, scope) + public_leaks(svg, scope)))
        logs += slog
        if hits:
            return {**res, "result": "fail", "leaks": hits, "logs": sorted(set(logs))}, CHECK_FAILED
    outputs = []
    for key, data in (("mmd", mmd.encode("utf-8")), ("svg", svg.encode("utf-8")), ("md", md.encode("utf-8"))):
        outputs.append((out_dir / files[key], data))
    if not args.no_png:
        scale = chart.png_scale(laid, args.scale)
        if scale != args.scale:
            logs.append(f"png-scale:{scale}")
        img = chart.png_image(laid, fonts, scale)
        outputs.append((out_dir / files["png"], png_bytes(img)))
        res["size"]["png"] = [img.width, img.height]
    if args.mmdc:
        with tempfile.TemporaryDirectory(prefix="account-chart-render-") as directory:
            staging = Path(directory)
            (staging / files["mmd"]).write_text(mmd, encoding="utf-8")
            rendered = _mmdc(args, staging, files["mmd"], files["mermaid"],
                             chart.canvas_colour(model["account"]["style"]), args.scale, logs)
            if rendered:
                staged = staging / files["mermaid"]
                _preflight([staged])
                outputs.append((out_dir / files["mermaid"], staged.read_bytes()))
    _publish(outputs, inputs, states)
    res["outputs"] = [str(path) for path, _ in outputs]
    res["logs"] = sorted(set(logs))
    return res, OK


def _mmdc(args, out_dir: Path, src: str, dest: str, background: str, scale: int, logs: list[str]) -> list[str]:
    """Optional: draw the Mermaid source with mermaid-cli (a headless browser), for an HD picture of the .mmd itself."""
    exe = shutil.which(args.mmdc) or (args.mmdc if Path(args.mmdc).is_file() else None)
    if not exe:
        logs.append("needs-input:mmdc")
        return []
    with tempfile.TemporaryDirectory(prefix="account-chart-mmdc-") as tmp:
        # natural size: without this mmdc fits the diagram to an 800 px page, which is not a high-definition picture
        conf = Path(tmp) / "mermaid.json"
        conf.write_text(json.dumps({"flowchart": {"useMaxWidth": False}}), encoding="utf-8")
        cmd = [exe, "-i", str(out_dir / src), "-o", str(out_dir / dest), "-s", str(scale), "-b", background, "-q",
               "-c", str(conf)]
        if args.mmdc_config:
            cmd += ["-p", args.mmdc_config]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=600)
        except (OSError, subprocess.SubprocessError):
            logs.append("mmdc-failed")
            return []
    if p.returncode != 0 or not (out_dir / dest).is_file():
        logs.append("mmdc-failed")
        return []
    logs.append("mmdc:not-deterministic")
    return [str(out_dir / dest)]
