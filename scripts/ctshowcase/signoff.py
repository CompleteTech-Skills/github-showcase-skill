"""Opt-in T3 sign-off verification (`--require-t3-signoff`, env SHOWCASE_REQUIRE_T3_SIGNOFF=1; issue 23).

Off by default: nothing here runs and `--allow-t3` keeps its original meaning (tests/test_allow_t3_global.py).
When on, `--allow-t3` is honoured only while the estate bundle holds a valid, unexpired sign-off record for the
owner (and the repository when the record is scoped). The bundle is read, never copied: `decisions/t3-signoffs.yaml`
under `estate_root()` (env SHOWCASE_ESTATE_ROOT)::

    signoffs:
      - id: t3s-001            # carried onto writer jobs as `signoff_id` (and `approval_id` when none else is set)
        owner: Example-Co-Owned   # any login of the org (renames resolve through the aliases the gate passes in)
        repos: ["*"]           # "*" or repository names / OWNER/NAME; absent or empty matches nothing (fail closed)
        approved: true
        expires: 2099-12-31    # required: a record with no parsable date never validates

Refusals are exit 2 with log `t3-signoff:missing` (no approved record for the owner), `t3-signoff:expired` (every
matching record is past `expires`) or `t3-signoff:scope` (the owner has records but none covers the repository; an
owner-wide command with no repository needs a `*` record). Excluded and HOLD owners are refused before this runs.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from .errors import Refused

SIGNOFF_FILE = "t3-signoffs.yaml"
_REQUIRE = False
_GRANTED: dict[str, list[dict]] = {}  # lowercase login -> the records that granted it, for stamping this run's writer jobs
_ALIASES: dict[str, set[str]] = {}  # lowercase login -> every login of its org, filled by Resolver.aliases under the flag


def env_required() -> bool:
    return os.environ.get("SHOWCASE_REQUIRE_T3_SIGNOFF", "").strip().lower() in ("1", "true", "yes", "on")


def set_required(value: bool) -> None:
    global _REQUIRE
    _REQUIRE = bool(value)


def required() -> bool:
    return _REQUIRE


def reset() -> None:
    _GRANTED.clear()
    _ALIASES.clear()


def register_aliases(logins: list[str]) -> None:
    """Remember that these logins name one org, so a record under a former login still matches wherever the owner is
    re-checked (doctor rows, org and project helpers) without each caller passing the aliases again."""
    group = {x.lower() for x in logins if x}
    for x in list(group):
        group |= _ALIASES.get(x, set())
    for x in group:
        _ALIASES[x] = group


def _expand(owners: list[str]) -> list[str]:
    out = {o.lower() for o in owners if o}
    for o in list(out):
        out |= _ALIASES.get(o, set())
    return sorted(out)


def load_records(root: Path | None = None) -> list[dict]:
    from .config import load_yaml_text
    from .resolver import estate_root
    root = root or estate_root()
    path = root / "decisions" / SIGNOFF_FILE if root else None
    if not path or not path.is_file():
        return []
    data = load_yaml_text(path.read_text(encoding="utf-8"))
    items = data.get("signoffs") if isinstance(data, dict) else data
    return [r for r in items or [] if isinstance(r, dict)]


def _expiry(rec: dict) -> _dt.date | None:
    v = rec.get("expires")
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    # the whole value must parse: `2099-12-31garbage` is not a date, so it never validates (fail closed)
    try:
        return _dt.date.fromisoformat(str(v).strip())
    except ValueError:
        pass
    try:
        return _dt.datetime.fromisoformat(str(v).strip()).date()
    except ValueError:
        return None


def _covers(rec: dict, repo: str | None, logins: list[str] | None = None) -> bool:
    """`*` covers everything; a bare name covers that repository; OWNER/NAME needs the owner to be one of `logins`
    (the requested owner and its org aliases) as well as the name. A malformed `repos` (not a string or a list of
    strings) covers nothing, so it surfaces as t3-signoff:scope instead of an uncaught exception."""
    repos = rec.get("repos")
    if isinstance(repos, str):
        repos = [repos]
    if not isinstance(repos, list) or not all(isinstance(x, str) for x in repos):
        return False
    if "*" in repos:
        return True
    name = (repo or "").split("/")[-1].lower()
    if not name:
        return False
    mine = {x.lower() for x in logins or []}
    for r in repos:
        head, _, tail = r.rpartition("/")
        if tail.lower() != name:
            continue
        if not head or head.lower() in mine or logins is None:
            return True
    return False


def evaluate(owners: list[str], repo: str | None = None, today: _dt.date | None = None,
             records: list[dict] | None = None) -> tuple[dict | None, str | None]:
    """(record, None) when signed off, else (None, 'missing' | 'expired' | 'scope')."""
    today = today or _dt.date.today()
    logins = {o.lower() for o in owners if o}
    recs = load_records() if records is None else records
    logins = set(_expand(list(logins)))
    # a record with no id cannot be carried onto writer jobs, so it never authorizes anything
    mine = [r for r in recs if r.get("approved") is True and str(r.get("id") or "").strip()
            and str(r.get("owner") or "").lower() in logins]
    if not mine:
        return None, "missing"
    scoped = [r for r in mine if _covers(r, repo, sorted(logins))]
    if not scoped:
        return None, "scope"
    live = [r for r in scoped if (_expiry(r) or _dt.date.min) >= today]
    if not live:
        return None, "expired"
    return live[0], None


def granted(owner: str, repo: str | None = None, aliases: list[str] | None = None) -> bool:
    """True when sign-off is not required, or a valid record covers the owner (and repository). Never raises."""
    if not _REQUIRE:
        return True
    rec, _ = evaluate([owner, *(aliases or [])], repo)  # evaluate also expands the aliases Resolver.aliases registered
    return rec is not None


def require(owner: str, repo: str | None = None, aliases: list[str] | None = None) -> dict | None:
    """Gate for a requested `--allow-t3`: the record, or Refused (exit 2) logged t3-signoff:<why>. No-op when off."""
    if not _REQUIRE:
        return None
    logins = [owner, *(aliases or [])]
    rec, why = evaluate(logins, repo)
    if rec is None:
        raise Refused(f"{owner}{'/' + repo if repo else ''} is T3 and --require-t3-signoff is set: "
                      f"no valid sign-off record ({why})", log=f"t3-signoff:{why}")
    for login in _expand(logins):
        _GRANTED.setdefault(login, []).append(rec)
    return rec


def record_for(owner: str, repo: str | None = None) -> dict | None:
    for rec in _GRANTED.get((owner or "").lower(), []):
        if _covers(rec, repo, _expand([owner or ""])):
            return rec
    return None


def stamp(jobs):
    """Under the flag, writer jobs for a signed-off T3 owner carry `signoff_id` (and `approval_id` when none is set)."""
    if not _REQUIRE or not _GRANTED:
        return jobs
    for j in jobs or []:
        if not isinstance(j, dict) or "phase" not in j:
            continue
        full = str(j.get("repo") or "")
        owner = j.get("org") or j.get("owner") or (full.split("/")[0] if "/" in full else "")
        rec = record_for(str(owner), full or None)
        if rec is not None and rec.get("id"):
            j["signoff_id"] = str(rec["id"])
            j.setdefault("approval_id", str(rec["id"]))
    return jobs
