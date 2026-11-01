"""Default-on T3 sign-off verification (`--allow-t3` needs a record; issue 23, tasks 24-27).

On by default: `--allow-t3` is honoured only while the sign-off record file holds a valid, unexpired record for the
owner (and the repository when the record is scoped). The record file is the private estate file
`<estate_root>/decisions/t3-signoffs.yaml` (default_record_path(); estate_root is resolver.estate_root()). An explicit
`--t3-signoff-file PATH` (env SHOWCASE_T3_SIGNOFF_FILE) overrides it. The order is: the explicit flag, then the env,
then the default. The tool never creates the file and never falls back to trusting the flag when it is absent.
There is no opt-out: no flag or environment variable turns enforcement off. The file is read, never copied.
A writer job carries the granting record as `signoff_id` (and `signoff_ids` when several records authorized it).
`approval_id` is never set from a sign-off: it names the decisions/APPROVED_ACTIONS.yaml row.
Format (the contract is references/t3-signoff.schema.json, described in references/t3-signoff.md)::

    signoffs:
      - id: t3s-001                 # carried onto writer jobs and change records as `signoff_id`
        owner: Example-Co-Owned     # any login of the org (renames resolve through the aliases the gate passes in)
        repos: ["*"]                # "*" or repository names / OWNER/NAME; an absent or empty value makes the record invalid (t3-signoff:invalid)
        approved: true
        approver: example-co-owner  # who signed off (audit)
        approved_on: 2026-01-15     # when they signed off (audit); a future date grants nothing yet
        expires: 2099-12-31         # optional; absent means no expiry. A date (valid through that day) or a timestamp with a UTC offset; not before approved_on
        note: "optional free text"

Refusals are exit 2 with log `t3-signoff:no-file` (no record file at the resolved path, or no estate root to resolve one; the log names the path), `t3-signoff:missing` (no approved record
for the owner), `t3-signoff:invalid` (the owner's records all break the schema, or a malformed record or withdrawal could cover the
repository; the error names the first problem),
`t3-signoff:expired` (every matching record is past `expires`) or `t3-signoff:scope` (the owner has records but none
covers the repository; an owner-wide command with no repository needs a `*` record), or `t3-signoff:revoked` (a
later or same-day `approved: false` record withdraws every grant covering the repository). Excluded and HOLD owners are
refused before this runs.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from contextvars import ContextVar, Token
from pathlib import Path

from .errors import Refused

FILE_ENV = "SHOWCASE_T3_SIGNOFF_FILE"
DEFAULT_RELATIVE = Path("decisions") / "t3-signoffs.yaml"

# All sign-off state is context-local, like `--allow-t3` itself (config._T3_SIGNED_OFF, issue 28): one thread's or
# asyncio task's record file, grants and aliases never leak into another's owner gate
# (tests/test_t3_signoff_require.py::test_signoff_state_is_context_local). showcase.main() opens a fresh run state
# and restores the enclosing one on every exit.
_FILE: ContextVar[str | None] = ContextVar("ctshowcase_t3_signoff_file", default=None)
# (granted, aliases): lowercase login -> the records that granted it, for stamping this run's writer jobs; and
# lowercase login -> every login of its org, filled by Resolver.aliases by default. None until first use.
# Copy-on-write: every update builds new dicts and sets them, so a context that inherited this value (an asyncio task,
# contextvars.copy_context().run) never mutates its parent's grants
# (tests/test_t3_signoff_require.py::test_child_context_grant_does_not_leak_into_parent).
_RUN: ContextVar[tuple[dict[str, tuple[dict, ...]], dict[str, frozenset[str]]] | None] = ContextVar(
    "ctshowcase_t3_signoff_run", default=None)


def set_file(path: str | Path | None) -> Token:
    """Set this context's `--t3-signoff-file` (None: fall back to env SHOWCASE_T3_SIGNOFF_FILE, else no file)."""
    return _FILE.set(str(path) if path else None)


def reset_file(token: Token) -> None:
    _FILE.reset(token)


def explicit_file() -> Path | None:
    """The file named by `--t3-signoff-file` or env SHOWCASE_T3_SIGNOFF_FILE, else None (in that order)."""
    v = _FILE.get() or os.environ.get(FILE_ENV, "").strip()
    return Path(v) if v else None


def default_record_path() -> Path | None:
    """`<estate_root>/decisions/t3-signoffs.yaml` in the private estate bundle, or None when no estate root resolves.
    Only a path: the file is never created."""
    from . import resolver
    root = resolver.estate_root()
    return root / DEFAULT_RELATIVE if root else None


def record_file() -> Path | None:
    """The record file this context reads: the explicit flag, then the env, then default_record_path()."""
    return explicit_file() or default_record_path()


def _run_state() -> tuple[dict[str, tuple[dict, ...]], dict[str, frozenset[str]]]:
    state = _RUN.get()
    return state if state is not None else ({}, {})


def _granted() -> dict[str, tuple[dict, ...]]:
    """Read-only view of this context's grants (a fresh dict; writes go through _grant)."""
    return dict(_run_state()[0])


def _aliases() -> dict[str, frozenset[str]]:
    return _run_state()[1]


def _grant(login: str, rec: dict) -> None:
    granted, aliases = _run_state()
    new = dict(granted)
    new[login] = (*new.get(login, ()), rec)
    _RUN.set((new, aliases))


def reset() -> Token:
    """Start empty grants and aliases in this context. New dicts, so an enclosing run's state is untouched;
    the token restores it (restore)."""
    return _RUN.set(({}, {}))


def restore(token: Token) -> None:
    _RUN.reset(token)


def register_aliases(logins: list[str]) -> None:
    """Remember that these logins name one org, so a record under a former login still matches wherever the owner is
    re-checked (doctor rows, org and project helpers) without each caller passing the aliases again."""
    granted, aliases = _run_state()
    group = {_owner_key(x) for x in logins if x}
    for x in list(group):
        group |= aliases.get(x, frozenset())
    new = dict(aliases)
    for x in group:
        new[x] = frozenset(group)
    _RUN.set((granted, new))


def _owner_key(owner) -> str:
    """The ONE owner identity used to match grants, withdrawals and the cached run grants: all surrounding whitespace
    (tab, newline, NBSP included) stripped, then case-folded as before. A padded spelling of an owner is that owner, so
    it can neither escape its own withdrawal nor be read as a different owner."""
    return owner.strip().lower() if isinstance(owner, str) else ""


def _expand(owners: list[str]) -> list[str]:
    aliases = _aliases()
    out = {_owner_key(o) for o in owners if o} - {""}
    for o in list(out):
        out |= aliases.get(o, frozenset())
    return sorted(out)


def load_records(path: str | Path | None = None) -> list[dict]:
    """Records from PATH, else from this run's record_file() (flag, env, then the estate default). No file: []."""
    from .config import load_yaml_text
    path = Path(path) if path else record_file()
    if not path or not path.is_file():
        return []
    try:
        data = load_yaml_text(path.read_text(encoding="utf-8"))
    except Exception:  # invalid YAML or unreadable file: no usable records, so the gate refuses (t3-signoff:missing)
        return []
    # the envelope is checked before any record is read (a top-level list or an extra key never authorizes)
    return list(_envelope(data))


def _envelope(data) -> tuple[dict, ...]:
    """The records of a file whose envelope conforms to references/t3-signoff.schema.json, else none at all.

    The schema's root is an object with exactly one property, `signoffs`, an array of record objects
    (additionalProperties false). Anything else (a top-level list, an extra top-level key, `signoffs: 7`, a scalar
    or a list entry in `signoffs`) is a file an external validator of the estate bundle refuses, so the whole file
    authorizes nothing and the gate refuses t3-signoff:missing, as for unparsable YAML. Records that break the schema
    one by one are still judged per record (problems(), t3-signoff:invalid).
    (tests/test_t3_signoff_require.py::test_file_envelope_follows_the_schema)"""
    if not isinstance(data, dict) or set(data) != {"signoffs"}:
        return ()
    items = data["signoffs"]
    if not isinstance(items, list) or not all(isinstance(r, dict) for r in items):
        return ()
    return tuple(items)


# The string forms references/t3-signoff.schema.json permits ($defs.date and $defs.awareTimestamp), checked before
# parsing. Python 3.11+ fromisoformat also accepts compact (`20991231`), week (`2099-W52-1`) and hour-only offset
# (`+00`) forms that the schema rejects, so without these the tool would grant a record an external validator of the
# estate bundle refuses (tests/test_t3_signoff_require.py::test_problems_follow_the_schema_string_patterns, which runs
# without jsonschema). ASCII digits only, like the schema's ECMA-262 `\d`. The one deliberate difference: a
# calendar-impossible date that matches the pattern (`2099-02-30`) still fails to parse here, so the tool is stricter
# than the schema there and fails closed.
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_AWARE_TS_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:?[0-9]{2})",
                          re.ASCII)


def _parse_when(v) -> _dt.date | _dt.datetime | None:
    """A date, or a timezone-aware timestamp. A naive timestamp is ambiguous, so it never parses (fail closed).
    A string must match the schema's date or awareTimestamp pattern in full (no surrounding whitespace) first."""
    if isinstance(v, _dt.datetime):
        return v if v.tzinfo is not None else None
    if isinstance(v, _dt.date):
        return v
    if not isinstance(v, str):
        return None
    # the whole value must match and parse: `2099-12-31garbage` is not a date, so it never validates (fail closed)
    if _DATE_RE.fullmatch(v):
        try:
            return _dt.date.fromisoformat(v)
        except ValueError:
            return None
    if not _AWARE_TS_RE.fullmatch(v):
        return None
    try:
        ts = _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))  # `Z` for Python < 3.11
    except ValueError:
        return None
    return ts if ts.tzinfo is not None else None


def _expiry(rec: dict) -> _dt.date | _dt.datetime | None:
    return _parse_when(rec.get("expires"))


def problems(rec: dict, today: _dt.date | None = None) -> list[str]:
    """What makes one record unusable ([] when it is sound): the breaks of references/t3-signoff.schema.json, plus two
    rules a schema cannot state, an `approved_on` later than TODAY (default: today, local calendar; the sign-off has
    not happened yet) and an `expires` earlier than `approved_on` (a grant that ended before it began). Kept in step
    with the schema by tests/test_t3_signoff_require.py::test_schema_and_problems_agree_on_the_fixtures."""
    out = []
    for key in ("id", "owner", "approver"):
        if not isinstance(rec.get(key), str) or not rec[key].strip():
            out.append(f"{key}: needs a non-empty string")
    repos = rec.get("repos")
    if not (isinstance(repos, str) and repos.strip()) and not (
            isinstance(repos, list) and repos and all(isinstance(x, str) and x.strip() for x in repos)):
        out.append("repos: needs '*', a repository name or a non-empty list of them")
    if not isinstance(rec.get("approved"), bool):
        out.append("approved: needs true or false (a boolean, not a string)")
    approved_on = _parse_when(rec.get("approved_on"))
    if approved_on is None or isinstance(approved_on, _dt.datetime):
        out.append("approved_on: needs a date (YYYY-MM-DD)")
    if "expires" in rec and _parse_when(rec["expires"]) is None:
        out.append("expires: needs a date (YYYY-MM-DD) or a timestamp with a UTC offset")
    if "note" in rec and rec["note"] is not None and not isinstance(rec["note"], str):
        out.append("note: needs a string")
    if isinstance(approved_on, _dt.date) and not isinstance(approved_on, _dt.datetime):
        if approved_on > (today or _dt.datetime.now().astimezone().date()):
            out.append(f"approved_on: {approved_on.isoformat()} is in the future (the sign-off has not happened yet)")
        exp = _expiry(rec)
        if exp is not None:
            exp_day = exp.astimezone(_dt.timezone.utc).date() if isinstance(exp, _dt.datetime) else exp
            if exp_day < approved_on:
                out.append(f"expires: is earlier than approved_on {approved_on.isoformat()}")
    # key=str: YAML keys need not be strings (`7: x` beside `unexpected: true`), and sorting mixed types raised
    # TypeError out of showcase.main() instead of refusing t3-signoff:invalid
    # (tests/test_t3_signoff_require.py::test_mixed_type_unknown_keys_refuse_invalid)
    extra = sorted(set(rec) - {"id", "owner", "repos", "approved", "approver", "approved_on", "expires", "note"},
                   key=lambda k: (type(k).__name__, str(k)))
    if extra:
        out.append("unknown field(s): " + ", ".join(map(str, extra)))
    return out


def _live(rec: dict, now: _dt.datetime) -> bool:
    """A date expiry is valid through the end of that day (inclusive, local calendar day, as before); a timestamp
    expiry is valid only strictly before that instant, compared timezone-aware (a record expiring at
    2026-10-30T00:00:00+00:00 is dead at 2026-10-30T12:44Z). An absent `expires` means no expiry, so it is always live."""
    if "expires" not in rec:
        return True
    exp = _expiry(rec)
    if isinstance(exp, _dt.datetime):
        return exp > now
    if isinstance(exp, _dt.date):
        return exp >= now.astimezone().date()
    return False


def _repo_list(repos) -> list[str] | None:
    """`repos` as a list of strings (a bare string is one entry), or None when it is malformed."""
    if isinstance(repos, str):
        return [repos]
    if isinstance(repos, list) and all(isinstance(x, str) for x in repos):
        return repos
    return None


def _repos_malformed(rec: dict) -> bool:
    """True when problems() reports the `repos:` break: `repos` is neither a non-empty string nor a non-empty list of
    non-empty strings."""
    repos = rec.get("repos")
    if isinstance(repos, str) and repos.strip():
        return False
    if isinstance(repos, list) and repos and all(isinstance(x, str) and x.strip() for x in repos):
        return False
    return True


def _scope_key(entry: str, logins: list[str] | None) -> str:
    """A canonical key for one `repos` entry, so equivalent scopes compare equal. `*` stays `*`. A bare NAME is its
    lowercased name. OWNER/NAME for one of LOGINS (the owner's own logins, aliases included) is the bare name, the same
    repository. OWNER/NAME for another account keeps its full lowercased form. With logins None, the lowercased entry."""
    e = entry.strip().lower()
    if e == "*":
        return "*"
    head, sep, tail = e.rpartition("/")
    if not sep:
        return e
    if logins is not None and head in {x.lower() for x in logins}:
        return tail
    return e


def _withdrawn(grant: dict, withdrawals: list[dict], logins: list[str] | None = None,
               repo: str | None = None) -> bool:
    """True when an approved:false record (a withdrawal) vetoes GRANT: its approved_on is on or after the grant's
    approved_on (same day counts), and its owner is one of LOGINS (when given). A malformed `repos` never withdraws.
    With REPO (non-empty) the veto is per repository: a withdrawal vetoes the grant when the grant covers REPO and the
    withdrawal covers REPO (_covers), whether or not it covers the grant's whole scope. So a grant of [a, b] or `*`
    withdrawn for [a] is refused for a and still grants b. Without REPO the whole-grant rule applies: the withdrawal
    has `*`, or every scope of the grant appears among its own. Scopes are compared owner- and alias-aware: a bare
    name equals OWNER/NAME when OWNER is one of the owner's own LOGINS, so the two forms revoke each other, and another
    account's OWNER/NAME stays distinct."""
    g_on = _parse_when(grant.get("approved_on"))
    g_repos = _repo_list(grant.get("repos"))
    if g_on is None or g_repos is None or isinstance(g_on, _dt.datetime):
        return False
    owners = {_owner_key(x) for x in logins} if logins is not None else None
    g_keys = {_scope_key(x, logins) for x in g_repos}
    for f in withdrawals:
        if owners is not None and _owner_key(f.get("owner")) not in owners:
            continue
        f_on = _parse_when(f.get("approved_on"))
        f_repos = _repo_list(f.get("repos"))
        if f_on is None or f_repos is None or isinstance(f_on, _dt.datetime) or f_on < g_on:
            continue
        if repo:
            if _covers(grant, repo, logins) and _covers(f, repo, logins):
                return True
            continue
        f_keys = {_scope_key(x, logins) for x in f_repos}
        if "*" in f_keys:
            return True
        if g_keys <= f_keys:
            return True
    return False


def _malformed_withdrawal(ours: list[dict], repo: str | None, logins: list[str], today: _dt.date) -> str | None:
    """The refusal for a malformed withdrawal that could withdraw a grant for REPO, else None. A record is a possible
    withdrawal unless its `approved` is the boolean true: a literal false, or any non-boolean value ("false", "true",
    0, 1, null, missing), is treated as a withdrawal and fails closed. Only a true grant is skipped here. It is never
    coerced to a grant or a withdrawal. Possibly relevant: its `repos` is malformed, its approved_on is not a date (none,
    or a timestamp), REPO is empty, or it covers REPO. A malformed record clearly for another named repository does not
    block."""
    for r in ours:
        if r.get("approved") is True:
            continue
        probs = problems(r, today)
        if not probs:
            continue
        on = _parse_when(r.get("approved_on"))
        if _repos_malformed(r) or on is None or isinstance(on, _dt.datetime) or not repo or _covers(r, repo, logins):
            return f"invalid:{str(r.get('id') or '?')}: {probs[0]}"
    return None


def evaluate(owners: list[str], repo: str | None = None, today: _dt.date | None = None,
             records: list[dict] | None = None, now: _dt.datetime | None = None) -> tuple[dict | None, str | None]:
    """(record, None) when signed off, else (None, 'no-file' | 'missing' | 'invalid:<id>: <problem>' | 'expired' | 'scope' |
    'revoked'). The veto is per requested REPO: 'revoked' means every otherwise-grantable record was vetoed for that
    repository by a withdrawal (see _withdrawn). Fail closed: when a malformed withdrawal (a literal approved: false failing
    problems(), or a record whose `approved` is not a boolean, which is treated as a possible withdrawal and never
    coerced to a grant or a withdrawal) could cover REPO, no record is returned and the result is
    'invalid:<id>: <problem>'. A malformed withdrawal clearly for another repository does not block. Only owners in
    the logins are considered.
    `today` (a date) is kept for callers that only care about date expiries; `now` is an aware instant."""
    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc)
        if today is not None:  # start of that local day, so date expiries compare exactly as before
            now = _dt.datetime.combine(today, _dt.time.min).astimezone()
    if records is None:
        path = record_file()
        if path is None:
            return None, "no-file:no estate root resolves, so there is no default record path"
        if not path.is_file():
            return None, f"no-file:{path}"
        records = load_records()
    logins = set(_expand([o for o in owners if o]))
    seen: set[str] = set()
    for r in records:  # signoff_id is the audit key carried onto jobs, so an id must name exactly one record
        rid = str(r.get("id") or "")
        if rid and rid in seen:
            return None, f"invalid:{rid}: duplicate id (record ids must be unique within the file)"
        seen.add(rid)
    ours = [r for r in records if _owner_key(r.get("owner")) in logins]
    today = now.astimezone().date()
    valid = [r for r in ours if not problems(r, today)]
    withdrawals = [r for r in valid if r.get("approved") is False]
    mine = [r for r in valid if r.get("approved") is True]
    had_grants = bool(mine)
    revoked = [g for g in mine if _withdrawn(g, withdrawals, sorted(logins), repo)]
    mine = [g for g in mine if g not in revoked]
    if had_grants and not mine:
        return None, "revoked"
    if not mine:
        bad = [r for r in ours if problems(r, today)]
        if bad:  # a malformed record never authorizes, and the refusal says why instead of a silent 'missing'
            return None, f"invalid:{str(bad[0].get('id') or '?')}: {problems(bad[0], today)[0]}"
        return None, "missing"
    scoped = [r for r in mine if _covers(r, repo, sorted(logins))]
    if not scoped:
        # a malformed record that would have covered the repository is the cause, not a missing scope
        # a malformed `repos` is reported whether or not it would have covered the repository
        bad = [r for r in ours if problems(r, today) and (_repos_malformed(r) or _covers(r, repo, sorted(logins)))]
        if bad:
            malformed = [r for r in bad if _repos_malformed(r)]
            pick = (malformed or bad)[0]
            probs = problems(pick, today)
            line = next((p for p in probs if p.startswith("repos:")), probs[0]) if malformed else probs[0]
            return None, f"invalid:{str(pick.get('id') or '?')}: {line}"
        if any(_covers(g, repo, sorted(logins)) for g in revoked):  # the grant that covered it was withdrawn
            return None, "revoked"
        return None, "scope"
    live = [r for r in scoped if _live(r, now)]
    if not live:
        return None, "expired"
    unsafe = _malformed_withdrawal(ours, repo, sorted(logins), today)
    if unsafe:  # a malformed withdrawal that could cover the repository never lets the grant through
        return None, unsafe
    return live[0], None


def _covers(rec: dict, repo: str | None, logins: list[str] | None = None) -> bool:
    """`*` covers everything; a bare name covers that repository; OWNER/NAME needs the owner to be one of `logins`
    (the requested owner and its org aliases) as well as the name. A repository given as OWNER/NAME is covered only
    when that owner is one of `logins` too (only `*` covers another account's repository). A malformed `repos` (not a string or a list of
    strings) covers nothing; evaluate() reports such a record as t3-signoff:invalid through problems(), not as
    t3-signoff:scope."""
    repos = rec.get("repos")
    if isinstance(repos, str):
        repos = [repos]
    if not isinstance(repos, list) or not all(isinstance(x, str) for x in repos):
        return False
    repos = [x.strip() for x in repos]  # same normalisation as _scope_key: padding never hides a scope
    if "*" in repos:
        return True
    name = (repo or "").split("/")[-1].lower()
    if not name:
        return False
    mine = {x.lower() for x in logins or []}
    holder = (repo or "").rpartition("/")[0].lower()
    if holder and logins is not None and holder not in mine:
        return False  # OWNER/NAME names another account's repository: a bare name or this owner's pair never covers it
    for r in repos:
        head, _, tail = r.rpartition("/")
        if tail.lower() != name:
            continue
        if not head or head.lower() in mine or logins is None:
            return True
    return False


def granted(owner: str, repo: str | None = None, aliases: list[str] | None = None) -> bool:
    """True when a valid record covers the owner (and repository). Never raises."""
    rec, _ = evaluate([owner, *(aliases or [])], repo)  # evaluate also expands the aliases Resolver.aliases registered
    return rec is not None


def require(owner: str, repo: str | None = None, aliases: list[str] | None = None) -> dict | None:
    """Gate for a requested `--allow-t3`: the record, or Refused (exit 2) logged t3-signoff:<why>."""
    logins = [owner, *(aliases or [])]
    rec, why = evaluate(logins, repo)
    if rec is None:
        code, _, detail = (why or "missing").partition(":")
        hint = (" (create the record in the private estate bundle, or pass --t3-signoff-file PATH / set "
                "SHOWCASE_T3_SIGNOFF_FILE)") if code == "no-file" else ""
        raise Refused(f"{owner}{'/' + repo if repo else ''} is T3 and a sign-off record is required: "
                      f"no valid sign-off record ({code}{': ' + detail.strip() if detail else ''}){hint}",
                      log=f"t3-signoff:{code}")
    for login in _expand(logins):
        _grant(login, rec)
    return rec


def record_for(owner: str, repo: str | None = None) -> dict | None:
    """The granted record covering OWNER (and REPO) that no withdrawal in the record file vetoes for REPO, else None.
    The same per-repository veto as evaluate() applies (a withdrawal that names REPO after the grant still refuses the
    stamp), so the file's withdrawals are read here, only when this run holds a grant."""
    logins = _expand([owner or ""])  # a grant cached under a former login still applies once the alias is registered
    granted = _granted()
    withdrawals = [r for r in load_records() if r.get("approved") is False] if granted else []
    for login in dict.fromkeys([_owner_key(owner), *logins]):
        for rec in granted.get(login, ()):
            if _covers(rec, repo, logins) and not _withdrawn(rec, withdrawals, logins, repo):
                return rec
    return None


def stamp(items, owner: str | None = None):
    """Carry the granting sign-off onto this run's output:

    - writer jobs (dicts with `phase`) for a signed-off T3 owner get `signoff_id`;
    - change records (records.record(): dicts with `std`, `owner` and `repo`, no `phase`) get `signoff_id` too.

    Jobs carry `signoff_id` (and `signoff_ids` via stamp_associations). `approval_id` is left untouched on every item,
    because it names the decisions/APPROVED_ACTIONS.yaml row, not a sign-off.

    `owner` names the gated owner explicitly when a job's target is another account (the star-List jobs of a T3 org's
    `org pins` run as the personal account, org.star_list_plan); without it the owner is read from the item. An item
    that already carries a `signoff_id` is left as it is."""
    if not _granted():
        return items
    for j in items or []:
        if not isinstance(j, dict) or "signoff_id" in j:
            continue
        is_job = "phase" in j
        if not is_job and not ("std" in j and "owner" in j and "repo" in j):
            continue
        full = str(j.get("repo") or "")
        who = owner or j.get("org") or j.get("owner") or (full.split("/")[0] if "/" in full else "")
        _put(j, record_for(str(who), full or None))
    return items


def _put(j: dict, rec: dict | None) -> None:
    """Set `signoff_id` (only) on J from REC. approval_id is never set here (it names an APPROVED_ACTIONS.yaml row)."""
    if rec is not None and rec.get("id"):
        j["signoff_id"] = str(rec["id"])


def stamp_associations(item: dict, association_ids, owner: str | None = None, repo: str | None = None) -> dict:
    """Name on ITEM (a writer job or a change record) every record that authorized it: OWNER's own
    grant first (when OWNER/REPO is a signed-off T3 target), then each id in ASSOCIATION_IDS (a T3 org that ITEM
    brings in without targeting it: topics.merge `signoff_ids` for an `also_in` membership topic, project.estate_plan
    for a T3 org in the personal Estate's Org field). `signoff_id` is the first id and `signoff_ids` lists all of them
    only when there is more than one. Jobs carry only these sign-off ids: approval_id is never read or set here, since
    it names the decisions/APPROVED_ACTIONS.yaml row. Ids already on ITEM (`signoff_id`/`signoff_ids`) are kept and
    merged, never replaced, so a repository-specific regrant stamped earlier survives a later Org/association stamp
    (tests/test_t3_signoff_withdrawal.py::test_estate_org_option_keeps_repository_regrant).
    No-op when there are no association ids.
    Shared by showcase.cmd_topics, intake.adopt and project.estate_plan
    (tests/test_t3_signoff_require.py::test_adopt_topics_job_carries_the_also_in_signoff,
    ::test_estate_plan_jobs_carry_the_t3_orgs_signoff)."""
    if not association_ids or not isinstance(item, dict):
        return item
    existing: list[str] = []
    if item.get("signoff_id"):
        existing.append(str(item["signoff_id"]))
    listed = item.get("signoff_ids")
    if isinstance(listed, list) and listed:
        existing += [str(x) for x in listed if x]
    own = record_for(owner, repo) if owner else None
    own_ids = [str(own["id"])] if own and own.get("id") else []
    ids = list(dict.fromkeys(existing + own_ids + [str(x) for x in association_ids]))
    item["signoff_id"] = ids[0]
    if len(ids) > 1:
        item["signoff_ids"] = ids
    return item


def record(owner: str, repo: str | None = None, aliases: list[str] | None = None) -> dict | None:
    """The valid record covering OWNER (and REPO), else None; registers no grant."""
    rec, _ = evaluate([owner, *(aliases or [])], repo)
    return rec


def stamp_source(job: dict, full: str, aliases: list[str] | None = None) -> dict:
    """Stamp a writer job that names another owner's T3 repository FULL (OWNER/NAME) with the record
    covering that repository. A star-List item job (org.star_list_plan) targets the personal account for some org's
    List, so neither the target nor the org's grant names the record that let the favorite through
    (org._t3_held checks it with granted(), which does not register a grant). It is evaluated here instead. The
    repository's record wins over the List org's: the item job is what puts the T3 repository in public; the org's own
    grant was enforced at the command gate and stays on its List create/describe jobs. No-op when the job
    already carries a signoff_id or when no valid record covers FULL (the favorite is then held and has no job)."""
    if not isinstance(job, dict) or "signoff_id" in job or "/" not in (full or ""):
        return job
    owner, name = full.split("/", 1)
    rec, _ = evaluate([owner, *(aliases or [])], name)
    _put(job, rec)
    return job
