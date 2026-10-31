"""One resolver for every org lookup (COVERAGE CQ-03): old and new logins, placeholders, approvals and GraphQL files.

After an approved org rename (`org-001` CompleTetech-Security -> CompleteTech-Security, `org-005` CompleteTech-Pokemon ->
CompleteTech-TCG, ...) the brand rows, the registry keys and the watching-org exemption must still resolve, so the
org and project modules never look an org up by a bare string. Renames come from, in order:

1. `former_slugs: [old, ...]` on an org row in `references/brand.yaml` or in `registry/estate.yaml`;
2. the registry's top-level `placeholders:` list (`login`, `successor`);
3. approved `org-rename` / `org-merge` items: `decisions/approved.tsv` rows (`action owner name [detail]`, detail =
   the new login or merge target) and `decisions/APPROVED_ACTIONS.yaml` entries with `approved: true`, joined with
   `decisions/estate-actions.json` for the old and new names.

A rename moves the org itself, so `canonical()` follows it. A merge keeps the old org as a placeholder that points at
its successor, so `canonical()` keeps the login and `successor()` names the target. Repository slugs are mapped the same
way: the registry writes each repository under its final slug (after `rename`/`transfer` actions), so `repo_before()`
returns the slug it has today, which is where its metadata and its links still are. The skill only reads these files.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import STANDARD, estate_candidates
from .config import load_yaml_text
from .errors import NeedsInput, ShowcaseError

QUERIES = Path(__file__).resolve().parent / "queries"
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
RENAME_KINDS = ("org-rename",)
MERGE_KINDS = ("org-merge",)
# repository actions that change a slug: the registry names the repository by its final slug before they run
REPO_SLUG_KINDS = ("rename", "transfer", "transfer+rename", "transfer+archive")


def estate_root() -> Path | None:
    """The hand-off bundle that holds `registry/` and `decisions/` (env SHOWCASE_ESTATE_ROOT, else the skill's parent,
    else the bundle root when the skill is the installed copy under `<bundle>/.claude/skills/`)."""
    env = os.environ.get("SHOWCASE_ESTATE_ROOT")
    for cand in ([Path(env)] if env else []) + estate_candidates():
        if (cand / "registry" / "estate.yaml").is_file() or (cand / "decisions").is_dir():
            return cand
    return None


def _read_yaml(path: Path | None):
    if not path or not Path(path).is_file():
        return None
    return load_yaml_text(Path(path).read_text(encoding="utf-8"))


def load_registry(path: str | Path | None = None) -> dict:
    """registry/estate.yaml (private data: read it, never copy it into a repository)."""
    if path is None:
        root = estate_root()
        path = root / "registry" / "estate.yaml" if root else None
    if not path or not Path(path).is_file():
        raise NeedsInput("registry", f"registry not found: {path or 'registry/estate.yaml'} (pass --registry)")
    data = _read_yaml(Path(path))
    if not isinstance(data, dict) or not isinstance(data.get("orgs"), dict):
        raise ShowcaseError(f"{path}: not an estate registry (no orgs mapping)", log="usage")
    return data


def load_approvals(tsv: str | Path | None = None, yaml_path: str | Path | None = None,
                   actions_json: str | Path | None = None) -> dict:
    """Approved rows and approved action ids, plus the action table they refer to. Missing files mean 'none approved'."""
    root = estate_root()
    dec = root / "decisions" if root else None
    tsv = Path(tsv) if tsv else (dec / "approved.tsv" if dec else None)
    yaml_path = Path(yaml_path) if yaml_path else (dec / "APPROVED_ACTIONS.yaml" if dec else None)
    actions_json = Path(actions_json) if actions_json else (dec / "estate-actions.json" if dec else None)
    rows: set[tuple[str, str, str, str]] = set()
    if tsv and tsv.is_file():
        for line in tsv.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            p = [x.strip() for x in line.split("\t")] + ["", "", ""]
            if p[0]:
                rows.add((p[0].lower(), p[1], p[2], p[3]))
    ids: set[str] = set()
    answers: dict = {}
    data = _read_yaml(yaml_path) if yaml_path else None
    items = []
    if isinstance(data, dict):
        answers = data.get("answers") or data.get("questions") or {}
        for key in ("actions", "approved", "items", "question_approvals"):  # row ids and q-ids (q41.orgs, q61.r, ...)
            if isinstance(data.get(key), list):
                items += data[key]
        items += [dict(v, id=k) for k, v in data.items() if isinstance(v, dict) and "approved" in v]
    elif isinstance(data, list):
        items = data
    extra: list[dict] = []
    for it in items:
        if isinstance(it, dict) and it.get("approved") is True:
            if it.get("id"):
                ids.add(str(it["id"]))
            if it.get("action"):
                extra.append(it)
    actions = []
    if actions_json and actions_json.is_file():
        try:
            actions = json.loads(actions_json.read_text(encoding="utf-8"))
        except ValueError:
            actions = []
    return {"rows": rows, "ids": ids, "answers": answers, "actions": actions if isinstance(actions, list) else [],
            "extra": extra}


class Resolver:
    """Maps any known login (old, new, any case) to the org's current login and to its brand and registry rows."""

    def __init__(self, brand=None, registry: dict | None = None, approvals: dict | None = None):
        self.brand, self.registry = brand, registry or {}
        self.approvals = approvals or {"rows": set(), "ids": set(), "answers": {}, "actions": [], "extra": []}
        self._renames: dict[str, str] = {}     # lower(old) -> new (as written)
        self._merges: dict[str, str] = {}      # lower(old) -> successor
        self._spelling: dict[str, str] = {}    # lower(login) -> preferred spelling
        self.sources: list[str] = []
        self._build()

    # -- construction -----------------------------------------------------------------------------------
    @classmethod
    def from_paths(cls, brand=None, registry: str | Path | dict | None = None, approved_tsv=None,
                   approved_yaml=None, actions_json=None, *, require_registry: bool = False) -> "Resolver":
        if isinstance(registry, dict):
            reg = registry
        else:
            try:
                reg = load_registry(registry)
            except NeedsInput:
                if require_registry or registry:
                    raise
                reg = {}
        return cls(brand, reg, load_approvals(approved_tsv, approved_yaml, actions_json))

    def _spell(self, login: str) -> None:
        if login:
            self._spelling.setdefault(login.lower(), login)

    def _add(self, table: dict, old: str, new: str, source: str) -> None:
        if not old or not new or old.lower() == new.lower() and old == new:
            return
        for x in (old, new):
            if not LOGIN_RE.match(x):
                raise ShowcaseError(f"{source}: {x!r} is not a GitHub login", log="usage")
        table[old.lower()] = new
        self.sources.append(f"{source}:{old}->{new}")

    def _build(self) -> None:
        for key, row in ((self.brand.raw.get("orgs") if self.brand else None) or {}).items():
            self._spell(key)
            for old in (row or {}).get("former_slugs") or []:
                self._add(self._renames, str(old), key, "brand.yaml former_slugs")
        for key, row in (self.registry.get("orgs") or {}).items():
            self._spell(key)
            for old in (row or {}).get("former_slugs") or []:
                self._add(self._renames, str(old), key, "registry former_slugs")
        for ph in self.registry.get("placeholders") or []:
            if isinstance(ph, dict) and ph.get("login") and ph.get("successor"):
                self._add(self._merges, ph["login"], ph["successor"], "registry placeholders")
        by_id = {a.get("id"): a for a in self.approvals.get("actions") or [] if isinstance(a, dict)}
        approved = [by_id[i] for i in self.approvals.get("ids") or () if i in by_id] + list(self.approvals.get("extra") or [])
        for a in approved:
            kind = (a.get("action") or "").lower()
            if kind in RENAME_KINDS and a.get("new_name"):
                self._add(self._renames, a["owner"], a["new_name"], f"approved {a.get('id') or kind}")
            elif kind in MERGE_KINDS and a.get("target_owner"):
                self._add(self._merges, a["owner"], a["target_owner"], f"approved {a.get('id') or kind}")
        for action, owner, name, detail in self.approvals.get("rows") or ():
            new = detail or (name if name not in ("", "*") and name.lower() != owner.lower() else "")
            if action in RENAME_KINDS and new:
                self._add(self._renames, owner, new, "approved.tsv")
            elif action in MERGE_KINDS and new:
                self._add(self._merges, owner, new, "approved.tsv")
        # repository slugs: final slug (as the registry writes it) -> (slug today, the action that changes it)
        self._repo_before: dict[str, tuple[str, dict]] = {}
        for a in self.approvals.get("actions") or []:
            if not isinstance(a, dict) or (a.get("action") or "").lower() not in REPO_SLUG_KINDS:
                continue
            if not a.get("owner") or not a.get("repo") or not (a.get("new_name") or a.get("target_owner")):
                continue
            final = f"{self.canonical(a.get('target_owner') or a['owner'])}/{a.get('new_name') or a['repo']}"
            if final.lower() != f"{self.canonical(a['owner'])}/{a['repo']}".lower():
                self._repo_before.setdefault(final.lower(), (f"{a['owner']}/{a['repo']}", a))

    # -- lookups ----------------------------------------------------------------------------------------
    def canonical(self, login: str) -> str:
        """The org's current login: follows approved renames (chains too), keeps merges, fixes the case."""
        if not login:
            return login
        cur, seen = login, set()
        while cur.lower() in self._renames and cur.lower() not in seen:
            seen.add(cur.lower())
            cur = self._renames[cur.lower()]
        return cur if seen else self._spelling.get(cur.lower(), cur)

    def successor(self, login: str) -> str:
        """Where an org's work lives now: the rename target, or the merge target of a placeholder org."""
        cur, seen = self.canonical(login), set()
        while cur.lower() in self._merges and cur.lower() not in seen:
            seen.add(cur.lower())
            cur = self.canonical(self._merges[cur.lower()])
        return cur

    def is_placeholder(self, login: str) -> bool:
        return self.canonical(login).lower() in self._merges

    def aliases(self, login: str) -> list[str]:
        """Every login that names the same org: the current one first, then former ones."""
        cur = self.canonical(login)
        out = [cur]
        for old, new in self._renames.items():
            if self.canonical(new).lower() == cur.lower():
                out.append(self._spelling.get(old, old))
        if login and login.lower() not in {x.lower() for x in out}:
            out.append(login)
        seen, uniq = set(), []
        for x in out:
            if x.lower() not in seen:
                seen.add(x.lower())
                uniq.append(x)
        from . import signoff
        signoff.register_aliases(uniq)  # a record under any login of the org matches wherever it is re-checked
        return uniq

    def same(self, a: str, b: str) -> bool:
        return bool(a and b) and self.canonical(a).lower() == self.canonical(b).lower()

    def slug(self, full_name: str) -> str:
        """OWNER/REPO with the owner resolved (repository names are left alone)."""
        if "/" not in (full_name or ""):
            return full_name
        o, r = full_name.split("/", 1)
        return f"{self.canonical(o)}/{r}"

    def repo_before(self, full_name: str) -> tuple[str, dict] | None:
        """(slug today, action) for a registry slug that a rename or transfer in `estate-actions.json` produces."""
        return getattr(self, "_repo_before", {}).get(self.slug(full_name or "").lower())

    def repo_action_approved(self, action: dict) -> bool:
        """An estate action is approved by its id (APPROVED_ACTIONS.yaml) or by an approved.tsv row."""
        if action.get("id") and self.action_approved(str(action["id"])):
            return True
        return self.approved(str(action.get("action") or ""), str(action.get("owner") or ""), str(action.get("repo") or "*"))

    def _find(self, table: dict, login: str) -> str | None:
        keys = {k.lower(): k for k in table}
        for a in self.aliases(login):
            if a.lower() in keys:
                return keys[a.lower()]
        return None

    def brand_key(self, login: str) -> str | None:
        """The `orgs:` key in brand.yaml for this org (it may still be the old login)."""
        return self._find((self.brand.raw.get("orgs") if self.brand else None) or {}, login)

    def registry_key(self, login: str) -> str | None:
        return self._find(self.registry.get("orgs") or {}, login)

    def registry_org(self, login: str) -> dict:
        key = self.registry_key(login)
        if key is None:
            raise NeedsInput("org", f"{login} has no row in registry/estate.yaml")
        return self.registry["orgs"][key]

    def brand_org(self, login: str, *, strict: bool = True) -> dict:
        """brand.yaml row under the current login. An org with no row is `needs-input:org` (CQ-03), never defaults."""
        key = self.brand_key(login)
        if key is None:
            if strict:
                raise NeedsInput("org", f"{login} has no row in references/brand.yaml (add it, or its former_slugs)")
            return self.brand.org(login) if self.brand else {"owner": login, "known": False}
        row = self.brand.org(key)
        row["owner"], row["brand_key"] = self.canonical(login), key
        return row

    def owner_status(self, login: str) -> str | None:
        """excluded / hold / t3 / watching for any of the org's logins (the watching exemption survives a rename)."""
        if not self.brand:
            return None
        for a in self.aliases(login):
            st = self.brand.owner_status(a)
            if st:
                return st
        return None

    def check_owner(self, login: str, *, allow_t3: bool = False, allow_hold: bool = False,
                    repo: str | None = None, verify_signoff: bool = True) -> str | None:
        """Refuse excluded, hold and (unless signed off) T3 orgs under any of their logins; return the status."""
        from .config import t3_signed_off
        from .errors import Refused
        st = self.owner_status(login)
        if st == "excluded":
            raise Refused(f"{login} is an excluded owner; every command refuses", log="exempt")
        if st == "hold" and not allow_hold:
            raise Refused(f"{login} is on HOLD", log="hold")
        if st == "t3" and not (allow_t3 or t3_signed_off()):
            raise Refused(f"{login} is T3; needs co-owner sign-off", log="t3-signoff")
        if st == "t3" and verify_signoff:  # doctor passes False: it reports the hold instead of refusing
            from . import signoff
            signoff.require(login, repo, self.aliases(login))
        return st

    def family_hold(self, login: str) -> bool:
        if not self.brand:
            return False
        key = self.brand_key(login) or login
        try:
            return bool(self.brand.style(key).get("hold"))
        except Exception:  # an unknown family is not a hold
            return False

    # -- approvals --------------------------------------------------------------------------------------
    def approved(self, action: str, owner: str, name: str = "*") -> bool:
        """approved.tsv semantics (case-insensitive, `*` name wildcard), checked under every alias of the owner."""
        action = action.lower()
        names = {name.lower(), "*"}
        owners = {a.lower() for a in self.aliases(owner)} if owner not in ("@me", "*") else {owner.lower()}
        return any(r[0] == action and r[1].lower() in owners and r[2].lower() in names
                   for r in self.approvals.get("rows") or ())

    def project_visibility_approved(self, owner: str) -> bool:
        """A board may go public only with an approved visibility item: the skill's per-org row `project-visibility
        OWNER *`, or the key form scripts/guard.py and build_approvals.py use, `graphql project-visibility *`. No review
        question grants either today, so boards stay private (fails safe)."""
        if not owner or owner == "@me":
            return False
        return self.approved("project-visibility", owner) or self.approved("graphql", "project-visibility", "*")

    def action(self, action_id: str) -> dict | None:
        for a in self.approvals.get("actions") or []:
            if isinstance(a, dict) and a.get("id") == action_id:
                return a
        return None

    def action_approved(self, action_id: str) -> bool:
        return action_id in (self.approvals.get("ids") or set())

    def summary(self) -> dict:
        return {"std": STANDARD, "renames": dict(sorted(self._renames.items())), "merges": dict(sorted(self._merges.items())),
                "sources": self.sources}


# -- GraphQL query files (read queries only; mutations are printed inline by the plans) ----------------------
def query_path(name: str) -> Path:
    p = QUERIES / f"{name}.graphql"
    if not p.is_file():
        raise ShowcaseError(f"no query file {name}.graphql", log="usage")
    return p


def query_text(name: str) -> str:
    text = query_path(name).read_text(encoding="utf-8")
    body = re.sub(r"(?m)#.*$", "", text)
    if re.search(r"\bmutation\b", body, re.I):  # defence in depth: read files never carry a mutation
        raise ShowcaseError(f"{name}.graphql contains a mutation; refused", log="usage")
    return text


def read_command(query_name: str, /, *, rel_to: Path | None = None, **variables) -> list[str]:
    """`gh api graphql -F var=value ... -F query=@FILE` (reads may load the query from a file; research §0.3(4))."""
    path = query_path(query_name)
    query_text(query_name)
    shown = os.path.relpath(path, rel_to) if rel_to else str(path)
    argv = ["gh", "api", "graphql"]
    for k, v in variables.items():
        if v is not None:
            argv += ["-F", f"{k}={v}"]
    return argv + ["-F", f"query=@{shown}"]


def enterprise_snapshot_query(slug: str, *, rel_to: Path | None = None) -> dict:
    """`enterprise snapshot-query`: the validated Appendix A reads for a slug, printed, never run here."""
    if not slug or not re.match(r"^[a-z0-9][a-z0-9-]*$", slug):
        raise ShowcaseError("enterprise snapshot-query needs --slug (lower-case enterprise slug)", log="usage")
    reads = [{"name": n, "argv": read_command(q, rel_to=rel_to, **({} if q == "enterprise_discover" else {"slug": slug}))}
             for n, q in (("discover", "enterprise_discover"), ("snapshot", "enterprise_snapshot"),
                          ("drift", "enterprise_drift"), ("romgenie", "enterprise_romgenie"))]
    return {"slug": slug, "reads": reads, "paginate": ["organizations", "members", "ownerInfo.outsideCollaborators"],
            "note": "Read-only (read:enterprise). Page organizations, members and outsideCollaborators with after: while "
                    "hasNextPage; `enterprise snapshot` runs the same reads and writes the snapshot file."}
