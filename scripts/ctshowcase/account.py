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
from .errors import CHECK_FAILED, OK, NeedsInput, ShowcaseError

SCHEMA = "account-chart/v1"
ACTIONS = ("capture-query", "capture", "render")
HIDE = ("forks", "archived")
# left out by default; `render --show VALUE` brings each back
SHOW = ("all-orgs", "private-work", ".github")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_PAGES = 200
NOT_PUBLIC_KEYS = ("private", "isPrivate", "visibility")
ROLES = ("owner", "member")
CAPTURE_STATES = ("complete", "uncaptured", "failed", "partial", "unknown")
NOTES = ("held", "uncaptured", "failed", "partial", "unknown", "private", "empty")


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
    """First page, observed nodes and coverage; a missing/failed continuation never proves an empty connection."""
    from .errors import Refused
    first, nodes, after = None, [], None
    cursors = set()
    for _ in range(MAX_PAGES):
        try:
            data = run(name, **variables, after=after)
        except Refused:
            raise  # consent and response identity are gates, not partial network failures
        except ShowcaseError:
            return first or {}, nodes if first is not None else None, "partial" if first is not None else "failed"
        first = data if first is None else first
        conn = _dig(data, path)
        if not isinstance(conn, dict):
            return first or {}, nodes if after is not None else None, "partial" if after is not None else "uncaptured"
        page_nodes = conn.get("nodes")
        if not isinstance(page_nodes, list) or any(not isinstance(n, dict) for n in page_nodes):
            return first or {}, nodes, "partial"
        nodes += page_nodes
        page = conn.get("pageInfo") or {}
        if not isinstance(page, dict):
            return first or {}, nodes, "partial"
        if page.get("hasNextPage") is False:
            return first or {}, nodes, "complete"
        after = page.get("endCursor")
        if page.get("hasNextPage") is not True or not isinstance(after, str) or not after or after in cursors:
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


def _not_public(node) -> int:
    """Owned repositories the viewer can see that are not public (private and internal): a count, never names."""
    a, p = _dig(node, ("all", "totalCount")), _dig(node, ("public", "totalCount"))
    return max(0, a - p) if isinstance(a, int) and isinstance(p, int) else 0


def _repository_status(status: str, node: dict, nodes: list) -> str:
    """A complete connection must also account for every public repository the same response counted."""
    public = _dig(node, ("public", "totalCount"))
    kept = _repos(nodes)
    if status == "complete" and (len(kept) != len(nodes)
                                or (isinstance(public, int) and public != len(kept))):
        return "partial"
    return status


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


def _check_capture_owner(resolver, login: str, allow_t3: bool) -> None:
    """Use the shared owner and sign-off gates before a query can return repository data."""
    from .errors import Refused
    resolver.check_owner(login, allow_t3=allow_t3)
    if resolver.family_hold(login):
        raise Refused(f"{login} is on HOLD", log="hold")
    if resolver.is_placeholder(login):
        raise Refused(f"{login} is a merged placeholder", log="exempt")


def capture(login: str | None = None, run=None, today: str | None = None, *, brand=None, resolver=None,
            allow_t3: bool = False, flags: dict | None = None) -> dict:
    """Run the reads and return an account-chart/v1 snapshot (public repository names, non-public counts)."""
    from .config import load_brand, t3_signed_off
    from .errors import Refused
    from .org import Estate, _t3_held
    from .resolver import Resolver
    brand = brand or load_brand()
    resolver = resolver or Resolver.from_paths(brand)
    estate = Estate(brand, resolver, flags=flags or {})
    allow_t3 = allow_t3 or t3_signed_off()
    run = run or _gh
    if login is not None:
        login = login.strip()
        if not LOGIN_RE.fullmatch(login):
            raise ShowcaseError(f"not a GitHub login: {login!r}", log="usage")
        _check_capture_owner(resolver, login, allow_t3)
    viewer = _dig(run("account_viewer"), ("viewer", "login"))
    if not isinstance(viewer, str) or not LOGIN_RE.fullmatch(viewer):
        raise NeedsInput("gh", "gh is not signed in (gh auth status)")
    login = (login or viewer).strip()
    _check_capture_owner(resolver, login, allow_t3)
    is_viewer = resolver.same(login, viewer)
    # Recheck before every page as well: a changed/withdrawn consent record does not authorize another read.
    def guarded(name, **variables):
        owner = variables.get("org") or variables.get("login") or login
        _check_capture_owner(resolver, owner, allow_t3)
        data = run(name, **variables)
        # Repository queries request login on every page. Discovery queries currently omit source identity;
        # preserve that protocol, but validate an identity whenever supplied before accumulating any nodes.
        entity, field, expected, required = {
            "account_user": ("user", "login", variables.get("login"), True),
            "account_org": ("organization", "login", variables.get("org"), True),
            "account_orgs": ("user", "login", variables.get("login"), False),
            "account_enterprises": ("viewer", "login", viewer, False),
            "account_enterprise_orgs": ("enterprise", "slug", variables.get("slug"), False),
        }[name]
        source = _dig(data, (entity,))
        if isinstance(source, dict) and (required or field in source):
            actual = source.get(field)
            pattern = SLUG_RE if field == "slug" else LOGIN_RE
            if (not isinstance(actual, str) or not pattern.fullmatch(actual)
                    or not (actual.casefold() == expected.casefold() if field == "slug"
                            else resolver.same(expected, actual))):
                # Never echo an untrusted returned identity or payload; refuse the whole capture before publishing.
                raise Refused("capture response identity does not match the requested source",
                              log="usage:capture-identity")
            if field == "login":
                _check_capture_owner(resolver, actual, allow_t3)
        return data

    first, nodes, repo_status = _paged(guarded, "account_user", ("user", "repositories"), login=login)
    user = first.get("user")
    if not isinstance(user, dict) or nodes is None:
        raise NeedsInput("account", f"{login} is not a user account {viewer} can see")
    actual = user.get("login") or login
    if not isinstance(actual, str) or not resolver.same(login, actual):
        raise NeedsInput("account", "captured account identity differs from the requested account")
    _check_capture_owner(resolver, actual, allow_t3)
    repo_status = _repository_status(repo_status, user, nodes)
    notes: list[str] = []
    def safe_repos(owner, raw):
        kept = []
        for repo in _repos(raw):
            full = f"{owner}/{repo['name']}"
            if _t3_held(estate, full, allow_t3):
                notes.append("t3-signoff:repository-withheld")
            elif estate.exposure(full):
                notes.append("exposure-withheld")
            else:
                kept.append(repo)
        return kept

    _, org_nodes, org_status = _paged(guarded, "account_orgs", ("user", "organizations"), login=login)
    member_of = _logins(org_nodes)
    enterprises = []
    if is_viewer:
        _, ent_nodes, ent_status = _paged(guarded, "account_enterprises", ("viewer", "enterprises"))
        for e in ent_nodes or []:
            slug = e.get("slug")
            if not isinstance(slug, str) or not SLUG_RE.match(slug):
                continue
            _, eo, eo_status = _paged(guarded, "account_enterprise_orgs", ("enterprise", "organizations"), slug=slug)
            if eo_status != "complete":
                notes.append(f"enterprise-orgs-unavailable:{slug}")
            enterprises.append({"slug": slug, "name": " ".join(str(e.get("name") or slug).split()),
                                "role": "owner" if e.get("viewerIsAdmin") else "member",
                                "organizations": sorted(_logins(eo).values(), key=str.lower), "capture_status": eo_status})
    else:
        ent_status = "uncaptured"
        notes.append("enterprises:viewer-only")  # GitHub reports enterprises and roles for the signed-in account only
    logins = dict(member_of)
    for e in enterprises:
        for o in e["organizations"]:
            logins.setdefault(o.lower(), o)
    orgs = []
    for key in sorted(logins):
        o = logins[key]
        try:
            _check_capture_owner(resolver, o, allow_t3)
        except Refused as exc:
            notes.append(f"{exc.log}:{o}")
            orgs.append({"login": o, "name": "", "member": key in member_of, "role": None, "captured": False,
                         "capture_status": "uncaptured", "repositories": [], "not_public": 0})
            continue
        ofirst, rnodes, status = _paged(guarded, "account_org", ("organization", "repositories"), org=o)
        org = ofirst.get("organization")
        if not isinstance(org, dict) or rnodes is None:
            notes.append(f"org-uncaptured:{o}")
            notes.append(f"org-{status}:{o}")
            orgs.append({"login": o, "name": "", "member": key in member_of, "role": None, "captured": False,
                         "capture_status": status, "repositories": [], "not_public": 0})
            continue
        role = None
        if is_viewer:
            role = "owner" if org.get("viewerCanAdminister") else ("member" if key in member_of else None)
        captured_repos = safe_repos(o, rnodes)
        status = _repository_status(status, org, rnodes)
        if len(captured_repos) != len(_repos(rnodes)):
            status = "partial"
        if status != "complete":
            notes.append(f"org-{status}:{o}")
        orgs.append({"login": o, "name": " ".join(str(org.get("name") or "").split()),
                     "member": key in member_of, "role": role, "captured": status == "complete",
                     "capture_status": status, "repositories": captured_repos, "not_public": _not_public(org)})
    acct = {"login": user.get("login") or login}
    for k, src in (("name", "name"), ("company", "company"), ("location", "location"), ("website", "websiteUrl")):
        acct[k] = " ".join(str(user.get(src) or "").split())
    captured_repos = safe_repos(login, nodes)
    if len(captured_repos) != len(_repos(nodes)):
        repo_status = "partial"
    coverage = {"repositories": repo_status, "organizations": org_status, "enterprises": ent_status}
    notes += [f"{scope}-{status}" for scope, status in coverage.items() if status != "complete"]
    return {"schema": SCHEMA, "std": STANDARD, "captured": today or date.today().isoformat(), "viewer": viewer,
            "account": acct, "repositories": captured_repos, "not_public": _not_public(user), "coverage": coverage,
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


def _count(v, where: str) -> int:
    if v is None:
        return 0
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise _bad(f"{where}.not_public must be a non-negative integer")
    return v


def _capture_state(node: dict, where: str) -> str:
    captured = node.get("captured", True)
    if not isinstance(captured, bool):
        raise _bad(f"{where}.captured must be a boolean")
    status = node.get("capture_status", "complete" if captured else "uncaptured")
    if status not in CAPTURE_STATES or (not captured and status == "complete"):
        raise _bad(f"{where}.capture_status is invalid or contradicts captured")
    if node.get("captured") is True:
        return "complete"  # the v1 completeness flag remains authoritative; status explains a false flag
    return status


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
        status = _capture_state(e, f"enterprise {e['slug']}")
        if "capture_status" not in e and f"enterprise-orgs-unavailable:{e['slug']}" in (snap.get("notes") or []):
            status = "uncaptured"
        ents.append({"slug": e["slug"], "name": " ".join(str(e.get("name") or e["slug"]).split()),
                     "role": e.get("role") if e.get("role") in ROLES else None, "organizations": list(orgs),
                     "capture_status": status})
    orgs = []
    seen = set()
    for o in snap.get("organizations") or []:
        if not isinstance(o, dict) or not isinstance(o.get("login"), str) or not LOGIN_RE.match(o["login"]):
            raise _bad("an organization needs a valid login")
        if o["login"].lower() in seen:
            raise _bad(f"organization {o['login']} is listed twice")
        seen.add(o["login"].lower())
        status = _capture_state(o, o["login"])
        repos = _clean_repos(o.get("repositories") or [], o["login"])
        not_public = _count(o.get("not_public"), o["login"])
        observed = status in ("complete", "partial")
        orgs.append({"login": o["login"], "name": " ".join(str(o.get("name") or "").split()),
                     "member": bool(o.get("member", True)), "role": o.get("role") if o.get("role") in ROLES else None,
                     "captured": status == "complete", "capture_status": status,
                     "repositories": repos if observed else [], "not_public": not_public if observed else None})
    coverage = snap.get("coverage") or {}
    if not isinstance(coverage, dict) or any(v not in CAPTURE_STATES for v in coverage.values()):
        raise _bad("coverage must map connections to capture states")
    coverage = {key: coverage.get(key, "complete") for key in ("repositories", "organizations", "enterprises")}
    if "enterprises:viewer-only" in (snap.get("notes") or []):
        coverage["enterprises"] = "uncaptured"
    repos = _clean_repos(snap.get("repositories") or [], "account")
    not_public = _count(snap.get("not_public"), "account")
    observed = coverage["repositories"] in ("complete", "partial")
    return {"schema": SCHEMA, "std": snap.get("std") or STANDARD, "captured": captured, "coverage": coverage,
            "viewer": snap.get("viewer") if isinstance(snap.get("viewer"), str) else None,
            "account": {"login": acct["login"], **{k: " ".join(str(acct.get(k) or "").split())
                                                   for k in ("name", "company", "location", "website")}},
            "repositories": repos if observed else [], "not_public": not_public if observed else None,
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
          hide: tuple | list = (), show: tuple | list = ()) -> tuple[dict, list[str]]:
    """The chart model from a validated snapshot, after the estate gates, and the logs of everything left out.

    By default the chart leaves out organizations with no public repository to show, the 'private work' pill and
    repositories named `.github`; `show` brings each back (`all-orgs`, `private-work`, `.github`). `hide` drops forks
    or archived repositories. An organization whose inventory is not completely observed is always shown, so a
    missing capture is never mistaken for an organization without public repositories."""
    from .org import Estate, _t3_granted, _t3_held
    r = resolver or brand.resolver()
    estate = Estate(brand, r, flags=flags or {})
    cfg = brand.raw["chart"]
    labels = cfg["labels"]
    logs: list[str] = list(snap.get("notes") or [])
    login = snap["account"]["login"]
    r.check_owner(login, allow_t3=allow_t3)  # an excluded or HOLD account refuses (exit 2)
    counts = {"public": 0, "named": 0, "withheld": 0, "hidden": 0, "not_public": 0, "organizations": 0,
              "enterprises": 0, "omitted_orgs": 0, "incomplete_orgs": 0, "orgs_without_public": 0, "hidden_by": {}}
    hidden_categories: set[str] = set()  # categories survive omission; omitted orgs never add repository counts
    languages: dict[str, int] = {}

    def hidden_reason(rp: dict) -> str | None:
        """Why a render option leaves this repository out, if one does (the estate gates are separate)."""
        if ".github" not in show and rp["name"].lower() == ".github":
            return ".github"
        if "forks" in hide and rp["fork"]:
            return "forks"
        if "archived" in hide and rp["archived"]:
            return "archived"
        return None

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
            reason = hidden_reason(rp)
            if reason:
                hidden_categories.add(reason)
                counts["hidden"] += 1
                counts["hidden_by"][reason] = counts["hidden_by"].get(reason, 0) + 1
                continue
            counts["named"] += 1
            if rp["language"]:
                languages[rp["language"]] = languages.get(rp["language"], 0) + 1
            out.append({**rp, "full_name": full, "url": f"https://github.com/{full}"})
        return out

    def notes_for(named: list, public: int, not_public: int, held: bool, status: str) -> list[str]:
        if held:
            return ["held"]
        if status != "complete":
            return [status]
        out = ["private"] if not_public and "private-work" in show else []
        if not named and not public and not out:
            out.append("empty")
        return out

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
        status = _capture_state(o, lg)
        observed = status in ("complete", "partial")
        repos = o["repositories"] if observed else []
        held = st == "hold" or r.family_hold(lg)
        reasons = [hidden_reason(rp) for rp in repos]
        if status == "complete" and "all-orgs" not in show and not (held and repos) and all(reasons):
            # completely observed and nothing public to show (none at all, only private work, or only repositories a
            # render option hides): left off unless --show all-orgs. HOLD public work stays withheld, not hidden.
            hidden_categories.update(reason for reason in reasons if reason)
            logs.append(f"no-public:{lg}")
            counts["orgs_without_public"] += 1
            return None
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
        not_public = o["not_public"] if observed else None
        named = gate_repos(lg, repos, held)
        counts["not_public"] += not_public or 0
        counts["organizations"] += 1
        if status != "complete":
            counts["incomplete_orgs"] += 1
        return {"kind": "org", "login": lg, "name": name, "eyebrow": eyebrow, "eyebrow_short": short, "sub": f"@{lg}",
                "role": o["role"], "member": o["member"], "style": style, "neutral": neutral, "family": family,
                "mark": mark if mark and mark.is_file() else None, "initials": _initials(name), "url": f"https://github.com/{lg}",
                "flagship": bool(row.get("flagship")), "tier": _tier_rank(row) if row.get("known") else 9,
                "repos": named, "public": len(repos) if observed else None, "not_public": not_public, "held": held,
                "capture_status": status,
                "notes": notes_for(named, len(repos), not_public, held, status)}

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
    coverage = snap.get("coverage") or {}
    personal_status = coverage.get("repositories", "complete")
    observed = personal_status in ("complete", "partial")
    repos = snap["repositories"] if observed else []
    not_public = snap["not_public"] if observed else None
    p_named = gate_repos(login, repos, False)
    counts["not_public"] += not_public or 0
    personal = {"kind": "personal", "login": login, "name": labels["personal_title"], "eyebrow": labels["personal"],
                "eyebrow_short": labels["personal"], "sub": f"@{login}", "role": None, "style": acct_style,
                "neutral": False, "family": acct_family, "mark": account["mark"], "initials": account["initials"],
                "url": account["url"], "repos": p_named, "public": len(repos) if observed else None,
                "not_public": not_public, "held": False, "capture_status": personal_status,
                "notes": notes_for(p_named, len(repos), not_public, False, personal_status)}

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
                o = {"login": lg, "name": "", "member": False, "role": None, "captured": False,
                     "capture_status": "uncaptured", "repositories": [], "not_public": 0}
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
                            "capture_status": e.get("capture_status", "complete"), "orgs": sorted(nodes, key=order)})
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
    evidence = []
    for key, label in (("repositories", "Personal repository inventory"), ("organizations", "Organization membership"),
                       ("enterprises", "Enterprise membership")):
        if coverage.get(key, "complete") != "complete":
            evidence.append(f"{label}: {_coverage_text(coverage[key])}")
    for ent in enterprises:
        if ent["capture_status"] != "complete":
            evidence.append(f"Organizations of enterprise {ent['slug']}: {_coverage_text(ent['capture_status'])}")
    for node in standalone + [o for e in enterprises for o in e["orgs"]]:
        if node["capture_status"] != "complete":
            evidence.append(f"Repository inventory for @{node['login']}: {_coverage_text(node['capture_status'])}")
    if evidence:
        desc += ". " + ". ".join(evidence) + ". Counts cover observed data only; this map is incomplete"
    model = {"account": account, "personal": personal, "enterprises": enterprises, "orgs": standalone, "counts": counts,
             "roles": roles, "legend_languages": legend or ["default"], "title": title, "desc": desc,
             "captured": snap["captured"], "viewer": snap.get("viewer"), "coverage": coverage, "evidence": evidence,
             "show": sorted(show), "hide": sorted(hide), "hidden_categories": sorted(hidden_categories)}
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


def _coverage_text(status: str) -> str:
    return {"uncaptured": "not captured; inventory is unknown", "failed": "not captured (capture failed); inventory is unknown",
            "partial": "partially captured; remaining inventory was not captured",
            "unknown": "capture status unknown"}[status]


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
    private_work = "private-work" in model.get("show", ())
    if c["not_public"] and private_work:
        facts.append(f"{c['not_public']} private or internal repositories are counted, never named")
    if c["withheld"]:
        facts.append(f"{c['withheld']} public repositories are withheld (on hold, awaiting co-owner sign-off or under "
                     "exposure review)")
    hidden_categories = model.get("hidden_categories", c.get("hidden_by") or {})
    left_out = [text for on, text in ((c.get("orgs_without_public"), "organizations with no public repositories shown"),
                                      (".github" in hidden_categories, "`.github` repositories"),
                                      ("forks" in hidden_categories, "forks"),
                                      ("archived" in hidden_categories, "archived repositories")) if on]
    if left_out:  # what the render options leave out, without counts
        facts.append("Not shown: " + (", ".join(left_out[:-1]) + " and " + left_out[-1] if len(left_out) > 1
                                      else left_out[0]))
    if c["omitted_orgs"]:
        facts.append(f"{c['omitted_orgs']} organizations are outside this map (excluded, awaiting sign-off or merged)")
    if model.get("evidence"):
        facts.append("Counts cover observed data only; this map is incomplete")
    out += ["<sub>" + ". ".join(facts) + f". Captured {model['captured']}. Mermaid source: "
            f"<a href=\"{files['mmd']}\">{files['mmd']}</a>.</sub>", ""]
    if model.get("evidence"):
        out += [f"- {_md(item)}." for item in model["evidence"]] + [""]
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
        if node.get("capture_status", "complete") != "complete":
            extra.append(_coverage_text(node["capture_status"]))
        if node["not_public"] and private_work:
            extra.append(f"{node['not_public']} private or internal, not named")
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
    s.add_argument("--show", action="append", choices=SHOW, default=[],
                   help="render: also show what is left out by default (repeatable): all-orgs (organizations with no "
                        "public repository to show), private-work (a 'private work' pill where an owner has non-public "
                        "repositories, never a name, and the private counts in the Markdown), .github (repositories "
                        "named .github)")
    s.add_argument("--avatar", help="render: the account's avatar image (default: its brand mark, else a monogram)")
    s.add_argument("--no-png", action="store_true", help="render: skip the HD PNG")
    s.add_argument("--mmdc", nargs="?", const="mmdc", metavar="PATH",
                   help="render: also render NAME.mermaid.png from the Mermaid source with mermaid-cli (optional; "
                        "browser output, not byte-deterministic)")
    s.add_argument("--mmdc-config", metavar="FILE", help="render: puppeteer config JSON passed to mmdc -p")
    s.add_argument("--registry", help="capture, render: registry/estate.yaml for the org resolver and leak check (read only)")
    s.add_argument("--decisions", help="capture, render: decisions/decisions.json (exposure flags keep repositories unnamed)")
    for flag, what in (("--approved", "decisions/approved.tsv"), ("--approved-yaml", "decisions/APPROVED_ACTIONS.yaml"),
                       ("--actions", "decisions/estate-actions.json")):
        s.add_argument(flag, help=f"capture, render: {what} for the org resolver (default: the bundle's)")
    s.add_argument("--allow-t3", action="store_true", default=argparse.SUPPRESS, help="T3 orgs after co-owner sign-off")
    s.set_defaults(func=cmd_account_chart)


def _sources(args, brand, model: dict | None = None) -> list[Path]:
    """Every file input, including implicit estate/consent files and render assets, participates in alias checks."""
    from . import signoff
    from .config import LOCK
    from .resolver import QUERIES, estate_root
    paths = [brand.path, LOCK, signoff.record_file(), *QUERIES.glob("account_*.graphql")]
    for name in ("snapshot", "avatar", "config", "registry", "decisions", "approved", "approved_yaml", "actions",
                 "mmdc_config", "t3_signoff_file"):
        value = getattr(args, name, None)
        if value:
            paths.append(Path(value))
    root = estate_root()
    if root:
        paths += [root / "registry/estate.yaml", *[root / "decisions" / name for name in
                  ("approved.tsv", "APPROVED_ACTIONS.yaml", "estate-actions.json", "decisions.json")]]
    # Configuration declares source ownership even when a lane or asset is not rendered. Protect those paths in
    # the first preflight, before visibility or consent gates can remove nodes from the chart model.
    paths += [brand.asset(row.get("mark")) for row in (brand.raw.get("orgs") or {}).values() if row.get("mark")]
    assets = brand.raw.get("brand_assets") or {}
    paths += [brand.asset(assets.get(key)) for key in
              ("logo_light", "logo_dark", "logo_dark_candidate", "mark_dark", "mark_light", "bulb_dark") if assets.get(key)]
    paths += [brand.font_file(key) for key in brand.raw.get("fonts") or {}]
    if model is not None:
        nodes = [model["account"], model["personal"], *model["orgs"], *[o for e in model["enterprises"] for o in e["orgs"]]]
        paths += [n["mark"] for n in nodes if n.get("mark")]
    if getattr(args, "mmdc", None):
        paths.append(Path(shutil.which(args.mmdc) or args.mmdc))
    return [Path(path) for path in paths if path is not None]


def _check_outputs(paths: list[Path], sources: list[Path] = ()) -> dict:
    """Preflight the entire graph without creating directories or truncating any file.

    Check lexical ancestors before resolving aliases: resolving first would conceal a symlink or junction.
    Hard-linked destinations are refused too, including a link to an authored file outside the output directory.
    """
    def fail(path, reason):
        raise ShowcaseError(f"unsafe account-chart output {path}: {reason}", log="usage:account-chart-path")

    resolved, states = [], {}
    for path in paths:
        absolute = path.absolute()
        for index, component in enumerate([absolute, *absolute.parents]):
            try:
                info = component.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                fail(path, str(exc))
            if stat.S_ISLNK(info.st_mode) or getattr(component, "is_junction", lambda: False)():
                fail(path, "symlink or junction in destination")
            if index:
                if not stat.S_ISDIR(info.st_mode):
                    fail(path, "destination ancestor is not a directory")
            elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                fail(path, "destination is not an unlinked regular file")
            if not index:
                states[path] = (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns,
                                info.st_ctime_ns, info.st_nlink)
        try:
            real = absolute.resolve()
            for other in [*resolved, *sources]:
                if real == other.resolve() or (real.exists() and other.exists() and real.samefile(other)):
                    fail(path, "destination aliases another output or an input")
        except (OSError, RuntimeError) as exc:
            fail(path, str(exc))
        resolved.append(real)
        states.setdefault(path, None)
    return states


def _write_outputs(outputs: dict[Path, bytes], sources: list[Path], states: dict) -> None:
    """Recheck pre-generation destinations, then use the shared publisher's staging and rollback."""
    from .formatting import write_formatted_outputs
    if _check_outputs(list(states), sources) != states:
        raise ShowcaseError("account-chart output changed during generation", log="usage:account-chart-path")
    write_formatted_outputs(list(outputs.items()))


def cmd_account_chart(args):
    if args.action == "capture-query":
        return {"command": "account-chart", "action": "capture-query", "result": "ok", **capture_reads(args.login),
                "logs": []}, OK
    if args.action == "capture":
        if not args.out:
            raise ShowcaseError("account-chart capture needs --out FILE", log="usage")
        from .config import load_brand, t3_signed_off
        from .org import _default_decisions, load_flags
        from .resolver import Resolver
        brand = load_brand(getattr(args, "config", None))
        sources = _sources(args, brand)
        states = _check_outputs([Path(args.out)], sources)  # a refused destination causes no network reads
        resolver = Resolver.from_paths(brand, args.registry, args.approved, args.approved_yaml, args.actions)
        snap = capture(args.login, brand=brand, resolver=resolver, allow_t3=t3_signed_off(),
                       flags=load_flags(args.decisions or _default_decisions()))
        _write_outputs({Path(args.out): snapshot_text(snap).encode("utf-8")}, sources, states)
        n = sum(len(o["repositories"]) for o in snap["organizations"]) + len(snap["repositories"])
        return {"command": "account-chart", "action": "capture", "owner": snap["account"]["login"], "result": "ok",
                "out": args.out, "counts": {"organizations": len(snap["organizations"]),
                                            "enterprises": len(snap["enterprises"]), "public_repositories": n},
                "coverage": snap["coverage"], "logs": snap["notes"]}, OK
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
    out_dir = Path(args.out_dir)
    files = {"mmd": f"{args.name}.mmd", "svg": f"{args.name}.svg", "md": f"{args.name}.md"}
    if not args.no_png:
        files["png"] = f"{args.name}.png"
    planned = [out_dir / name for name in files.values()]
    if args.mmdc:
        planned.append(out_dir / f"{args.name}.mermaid.png")
    brand = load_brand(getattr(args, "config", None))
    sources = _sources(args, brand)
    states = _check_outputs(planned, sources)
    snap = load_snapshot(args.snapshot)
    resolver = Resolver.from_paths(brand, args.registry, args.approved, args.approved_yaml, args.actions)
    flags = load_flags(args.decisions or _default_decisions())
    model, logs = build(snap, brand, resolver=resolver, flags=flags, allow_t3=t3_signed_off(), hide=tuple(args.hide),
                        show=tuple(args.show))
    sources = _sources(args, brand, model)
    _check_outputs(planned, sources)
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
           "coverage": model["coverage"], "evidence": model["evidence"]}
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
    outputs = {out_dir / files[key]: data.encode("utf-8") for key, data in (("mmd", mmd), ("svg", svg), ("md", md))}
    if not args.no_png:
        scale = chart.png_scale(laid, args.scale)
        if scale != args.scale:
            logs.append(f"png-scale:{scale}")
        img = chart.png_image(laid, fonts, scale)
        outputs[out_dir / files["png"]] = png_bytes(img)
        res["size"]["png"] = [img.width, img.height]
    if args.mmdc:
        # The optional browser writes into an isolated directory, never into an authored destination.
        with tempfile.TemporaryDirectory(prefix="account-chart-mmdc-stage-") as tmp:
            staging = Path(tmp).resolve()  # internal scratch only: TMPDIR may be a platform-managed symlink
            (staging / files["mmd"]).write_text(mmd, encoding="utf-8")
            dest = f"{args.name}.mermaid.png"
            made = _mmdc(args, staging, files["mmd"], dest, chart.canvas_colour(model["account"]["style"]),
                         args.scale, logs)
            if made:
                _check_outputs([staging / dest], [staging / files["mmd"]])
                outputs[out_dir / dest] = (staging / dest).read_bytes()
    _write_outputs(outputs, sources, states)
    res["outputs"] = [str(path) for path in outputs]
    res["logs"] = sorted(set(logs))
    return res, OK


def _mmdc(args, out_dir: Path, src: str, dest: str, background: str, scale: int, logs: list[str]) -> list[str]:
    """Optional: draw the Mermaid source with mermaid-cli (a headless browser), for an HD picture of the .mmd itself."""
    exe = shutil.which(args.mmdc) or (args.mmdc if Path(args.mmdc).is_file() else None)
    if not exe:
        logs.append("needs-input:mmdc")
        return []
    import tempfile
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
