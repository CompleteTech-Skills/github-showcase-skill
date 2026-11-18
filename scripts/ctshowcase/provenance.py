"""Provenance stamp and the run-once check (decision 25, PROPOSAL pending user confirmation).

One schema-validated stamp per target (references/provenance.schema.json) records that this skill showcased it and
when it last ran, so a run can be skipped before it starts when nothing changed:

| Target | Stamp |
|---|---|
| repository `OWNER/REPO` | the `provenance` block of `docs/images/.showcase.json` (the existing sidecar, extended) |
| organization `ORG` (or `org:ORG`) | `.github/showcase.json` in the `ORG/.github` repository |
| personal profile `user:LOGIN` | `.github/showcase.json` in the `LOGIN/LOGIN` repository |
| Enterprise `enterprise:SLUG` | `<estate root>/registry/enterprise.showcase.json`, beside the snapshot; never a public repository |

Timestamps and `run_count` are never part of `fingerprint`, so they never make a target look changed and never loop
the Action. `last_run_at` is written only together with the run's other changes (the same Action commit, the same
checkout commit, or a writer job in the same jobs file); a run that changes nothing writes nothing and is reported
`fresh`. The skill stays read-only toward GitHub: `check` makes read-only `gh api` GETs (or reads a local checkout),
and `stamp` writes only into `--repo-dir`/`--out-dir` or emits a `scripts/writer.py` job.
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import REFERENCES, STANDARD, __version__
from . import fingerprint as fp
from .errors import CHECK_FAILED, NEEDS_INPUT, OK, USAGE, NeedsInput, ShowcaseError

SCHEMA = REFERENCES / "provenance.schema.json"
REPO_STAMP = "docs/images/.showcase.json"
DOT_STAMP = ".github/showcase.json"
ENTERPRISE_STAMP = "enterprise.showcase.json"   # in <estate root>/registry/
STATUSES = ("never", "fresh", "stale", "untracked", "foreign")
# Exit codes (errors.py): fresh 0 (skip the target); never, stale, untracked 1 (work to do); foreign 2 (refused owner,
# like every other command); 4 needs-input (no metadata, gh unavailable). A batch exits 4 if any target needs input,
# else 1 if any target has work to do, else 0; a foreign target in a batch is reported, not escalated.
EXIT = {"fresh": OK, "never": CHECK_FAILED, "stale": CHECK_FAILED, "untracked": CHECK_FAILED, "foreign": USAGE}
JOB_PHASE = "9"   # after every other phase of the run: the stamp records the run that the earlier jobs made
COMMIT_MESSAGE = "docs: record showcase provenance (ct-std-v1) [skip ci]"
MANAGED = ("docs/images", "README.md", "CONTRIBUTING.md", ".github/showcase.json", "profile")
UNKNOWN = object()  # an input that could not be read this time: skipped, never reported as a change


def utc_now() -> str:
    from .ledger import now_iso
    return now_iso()


def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def validate(stamp: dict) -> list[str]:
    from .schema import validate as _validate
    return _validate(stamp, schema())


# -----------------------------------------------------------------------------------------------------------------
# Read-only GitHub access (GET only) and local sources
# -----------------------------------------------------------------------------------------------------------------
class GH:
    """`gh api -X GET` only. A 404 is an absent file (None); any other failure is needs-input:gh. Requests are spaced by
    `delay` seconds so a batch stays inside GitHub's rate limits."""

    def __init__(self, run=subprocess.run, delay: float = 0.0, sleep=time.sleep):
        self.run, self.delay, self.sleep, self.calls, self.cache = run, delay, sleep, [], {}

    def _call(self, path: str) -> str | None:
        if self.calls and self.delay:
            self.sleep(self.delay)
        argv = ["gh", "api", "-X", "GET", path]
        self.calls.append(argv)
        try:
            p = self.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            raise NeedsInput("gh", f"gh api failed: {exc}") from None
        if p.returncode != 0:
            err = p.stderr or ""
            if "HTTP 404" in err:
                return None
            if "rate limit" in err.lower() or "HTTP 403" in err or "HTTP 429" in err:
                raise NeedsInput("gh-rate-limit", f"GitHub rate limit while reading {path}; retry later")
            raise NeedsInput("gh", f"gh api GET {path} failed: {err.strip()[:200]}")
        return p.stdout

    def json(self, path: str):
        """One GET per path per run: a check and the stamp that follows it read each file once."""
        if path in self.cache:
            return self.cache[path]
        out = self._call(path)
        try:
            data = json.loads(out) if out and out.strip() else None
        except ValueError:
            raise NeedsInput("gh", f"unreadable response for {path}") from None
        self.cache[path] = data
        return data

    def file(self, repo: str, path: str) -> tuple[bytes | None, str | None]:
        """(bytes, blob sha) of one file through the contents API, or (None, None) when it does not exist."""
        data = self.json(f"repos/{repo}/contents/{path}")
        if not isinstance(data, dict) or data.get("type") != "file":
            return None, None
        try:
            return base64.b64decode(data.get("content") or ""), data.get("sha")
        except (ValueError, TypeError):
            raise NeedsInput("gh", f"unreadable content for {repo}/{path}") from None


class Source:
    """Where a target's files are read: a local checkout (`--repo-dir`/`--out-dir`) or a repository through GH."""

    def __init__(self, *, root: Path | None = None, gh: GH | None = None, repo: str | None = None):
        self.root, self.gh, self.repo, self.shas = root, gh, repo, {}

    @property
    def local(self) -> bool:
        return self.root is not None

    def read(self, rel: str) -> bytes | None:
        if self.root is not None:
            p = self.root / rel
            return p.read_bytes() if p.is_file() and not p.is_symlink() else None
        if self.gh is None or not self.repo:
            return None
        data, blob = self.gh.file(self.repo, rel)
        if blob:
            self.shas[rel] = blob
        return data

    def read_json(self, rel: str) -> dict:
        data = self.read(rel)
        if data is None:
            return {}
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return {}
        return obj if isinstance(obj, dict) else {}


# -----------------------------------------------------------------------------------------------------------------
# Targets
# -----------------------------------------------------------------------------------------------------------------
@dataclass
class Target:
    kind: str                 # repo | org | profile | enterprise
    id: str                   # canonical id: OWNER/REPO with the owner resolved, ORG, LOGIN, or the enterprise slug
    owner: str = ""
    repo: str = ""
    raw: str = ""
    logs: list = field(default_factory=list)

    @property
    def stamp_repo(self) -> str | None:
        """The repository that holds the stamp (None for the Enterprise, whose stamp is private and local)."""
        return {"repo": self.id, "org": f"{self.id}/.github", "profile": f"{self.id}/{self.id}"}.get(self.kind)

    @property
    def stamp_path(self) -> str:
        return {"repo": REPO_STAMP, "enterprise": ENTERPRISE_STAMP}.get(self.kind, DOT_STAMP)


def parse_target(text: str, resolver, gh: GH | None = None) -> Target:
    """OWNER/REPO, ORG or org:ORG, user:LOGIN, enterprise:SLUG. A bare login is an org when brand.yaml or the registry
    knows it as one; otherwise one read-only `users/LOGIN` GET decides (type User is a personal profile). Every org
    login goes through the resolver, so a renamed org still finds its stamp (CQ-03)."""
    raw = (text or "").strip()
    if not raw:
        raise ShowcaseError("provenance needs a TARGET (OWNER/REPO, ORG, user:LOGIN or enterprise:SLUG)", log="usage")
    low = raw.lower()
    if low.startswith("enterprise:"):
        slug = raw.split(":", 1)[1].strip()
        if not slug:
            raise ShowcaseError("enterprise:SLUG needs a slug", log="usage")
        return Target("enterprise", slug, raw=raw)
    if "/" in raw:
        owner, repo = raw.split("/", 1)
        if not owner or not repo or "/" in repo:
            raise ShowcaseError(f"not a repository: {raw!r} (OWNER/REPO)", log="usage")
        owner = resolver.canonical(owner)
        t = Target("repo", f"{owner}/{repo}", owner, repo, raw)
        if owner.lower() != raw.split("/", 1)[0].lower():
            t.logs.append(f"resolved:{raw.split('/', 1)[0]}->{owner}")
        return t
    for prefix, kind in (("org:", "org"), ("user:", "profile")):
        if low.startswith(prefix):
            login = raw.split(":", 1)[1].strip()
            canon = resolver.canonical(login) if kind == "org" else login
            t = Target(kind, canon, canon, raw=raw)
            if canon.lower() != login.lower():
                t.logs.append(f"resolved:{login}->{canon}")
            return t
    canon = resolver.canonical(raw)
    if resolver.brand_key(raw) or resolver.registry_key(raw):
        t = Target("org", canon, canon, raw=raw)
        if canon.lower() != raw.lower():
            t.logs.append(f"resolved:{raw}->{canon}")
        return t
    if gh is not None:
        info = gh.json(f"users/{raw}")
        if isinstance(info, dict) and info.get("type") == "User":
            return Target("profile", info.get("login") or raw, info.get("login") or raw, raw=raw)
        if isinstance(info, dict) and info.get("type") == "Organization":
            return Target("org", canon, canon, raw=raw)
    raise NeedsInput("target-kind", f"{raw}: unknown login; write org:{raw} or user:{raw}")


# -----------------------------------------------------------------------------------------------------------------
# Current inputs per kind
# -----------------------------------------------------------------------------------------------------------------
def _repo_meta(target: Target, meta_path: str | None, gh: GH | None, same=None) -> dict:
    from .meta import load_file, normalize
    if meta_path:
        m = load_file(meta_path)
        named = f"{m.get('owner')}/{m.get('repo')}"
        owner_ok = bool(m.get("owner")) and (same(m["owner"], target.owner) if same else
                                             str(m["owner"]).lower() == target.owner.lower())
        if (m.get("repo") or "").lower() != target.repo.lower() or not owner_ok:  # any login of a renamed org
            raise ShowcaseError(f"--meta describes {named}, not {target.id}", log="usage")
        return m
    if gh is None:
        raise NeedsInput("metadata", f"{target.id}: pass --meta FILE, or allow read-only gh api GETs")
    raw = gh.json(f"repos/{target.id}")
    if not isinstance(raw, dict):
        raise NeedsInput("metadata", f"{target.id}: repository not found or not readable")
    return normalize(raw)


def _remote_repo_inputs(meta: dict, src: Source, same_owner=None) -> dict:
    """fingerprint.inputs() for a repository read through the contents API. The detected type needs the file tree, so
    it is UNKNOWN remotely (never reported as a change)."""
    inp = fp.inputs(meta, None, same_owner=same_owner)
    override = None
    for n in (".github/showcase.yml", ".github/showcase.yaml"):
        override = src.read(n)
        if override is not None:
            break
    icon_rel = "assets/icon.png"
    if override is not None:
        v = fp.override_icon(override.decode("utf-8", errors="replace"))
        if v:
            icon_rel = v
    inp["override_sha256"] = sha(override)
    inp["icon_sha256"] = sha(src.read(icon_rel))
    inp["type"] = UNKNOWN
    return inp


def _about(gh: GH | None, path: str, keys: tuple[str, ...]):
    if gh is None:
        return UNKNOWN
    data = gh.json(path)
    return {k: (data or {}).get(k) for k in keys} if isinstance(data, dict) else UNKNOWN


def current_inputs(target: Target, brand, src: Source, *, meta_path: str | None = None, gh: GH | None = None,
                   snapshot: dict | None = None, same_owner=None) -> tuple[dict, dict]:
    """(inputs, context): the inputs whose change makes the target stale. `context` carries what was read on the way
    (the repository metadata, the sidecar) for the status and the stamp."""
    if target.kind == "repo":
        meta = _repo_meta(target, meta_path, gh, same_owner)
        if src.local:
            inp = fp.inputs(meta, src.root, same_owner=same_owner, metadata_path=meta_path)
        else:
            inp = _remote_repo_inputs(meta, src, same_owner)
        return inp, {"meta": meta}
    if target.kind == "org":
        inp = {"login": target.id,
               "profile_readme_sha256": sha(src.read("profile/README.md")),
               "profile_data_sha256": sha(src.read("profile/data.json")),
               "about": _about(gh, f"orgs/{target.id}", ("name", "description", "blog", "location", "email"))}
        return inp, {}
    if target.kind == "profile":
        inp = {"login": target.id, "readme_sha256": sha(src.read("README.md")),
               "about": _about(gh, f"users/{target.id}", ("name", "bio", "blog", "location"))}
        return inp, {}
    snap_sha = None
    if isinstance(snapshot, dict):
        # the snapshot's own per-section digests, else a digest of its canonical sections (never its taken_at time)
        from .config import canonical
        snap_sha = snapshot.get("sha256") or (hashlib.sha256(canonical(snapshot.get("sections") or {}).encode())
                                              .hexdigest() if snapshot.get("sections") else None)
    if snapshot is not None and isinstance(snapshot, dict) and snapshot.get("slug") and \
            str(snapshot["slug"]).lower() != target.id.lower():
        raise ShowcaseError(f"--snapshot is for {snapshot['slug']}, not {target.id}", log="usage")
    return {"slug": target.id, "snapshot_sha256": snap_sha if snap_sha else UNKNOWN}, {}


def _known(inp: dict) -> dict:
    return {k: v for k, v in inp.items() if v is not UNKNOWN}


def fingerprint_of(inp: dict, cfg_sha: str) -> str:
    """The stamp's fingerprint: the inputs, the skill version and the brand config. Never a timestamp or a count."""
    return fp.fingerprint(_known(inp), cfg_sha)


# -----------------------------------------------------------------------------------------------------------------
# Status
# -----------------------------------------------------------------------------------------------------------------
def read_stamp(target: Target, src: Source) -> dict:
    return src.read_json(target.stamp_path if target.kind != "enterprise" else ENTERPRISE_STAMP)


def _managed_markers(text: str) -> bool:
    return "<!-- showcase:" in text or "github-showcase-skill" in text or (
        "Built by" in text and "complete.tech" in text and "<picture>" in text)


def _surfaces(target: Target, src: Source, stamp_file: dict) -> list[str]:
    if target.kind == "repo":
        names = sorted(k for k in fp.output_records(stamp_file) if isinstance(k, str))
        readme = src.read("README.md")
        if readme is not None and _managed_markers(readme.decode("utf-8", errors="replace")):
            names.append("README.md")
        return names
    if target.kind == "org":
        return [p for p in ("profile/README.md", "profile/data.json") if src.read(p) is not None]
    if target.kind == "profile":
        return ["README.md"] if src.read("README.md") is not None else []
    return ["enterprise.snapshot.json"]


def _untracked(target: Target, src: Source, stamp_file: dict) -> bool:
    if target.kind == "repo":
        if stamp_file.get("outputs") or stamp_file.get("fingerprint"):
            return True
        readme = src.read("README.md")
        return readme is not None and _managed_markers(readme.decode("utf-8", errors="replace"))
    if target.kind == "org":
        readme = src.read("profile/README.md")
        return readme is not None and _managed_markers(readme.decode("utf-8", errors="replace"))
    if target.kind == "profile":
        readme = src.read("README.md")
        return readme is not None and _managed_markers(readme.decode("utf-8", errors="replace"))
    return src.read("enterprise.snapshot.json") is not None


def owner_refusal(target: Target, resolver) -> tuple[str | None, str | None]:
    """(refusal log, owner status): an excluded, held or (without a valid sign-off) T3 owner is refused before anything
    about the target is read."""
    if target.kind == "enterprise":
        return None, None
    from .config import t3_signed_off
    try:
        return None, resolver.check_owner(target.owner or target.id, allow_t3=t3_signed_off(),
                                          repo=target.repo or None)
    except ShowcaseError as exc:  # Refused, or a sign-off record that does not cover this target
        return exc.log, None


def watching_reason(target: Target, owner_status: str | None, meta: dict | None) -> str | None:
    """A watching-org fork keeps its upstream README; its other non-`.github` repositories are held until decided."""
    if owner_status == "watching" and target.kind == "repo" and (target.repo or "").lower() != ".github":
        return "exempt:watching-fork" if (meta or {}).get("fork") else "hold:watching-non-fork"
    return None


def _changes(stored_inputs: dict, current: dict) -> list[str]:
    out = []
    for k in sorted(set(stored_inputs) | set(current)):
        cur = current.get(k)
        if cur is UNKNOWN or k not in stored_inputs:  # unread now, or not read when stamped (an offline stamp)
            continue
        if stored_inputs.get(k) != cur:
            out.append(k)
    return out


def status(target: Target, brand, resolver, src: Source, *, meta_path: str | None = None, gh: GH | None = None,
           snapshot: dict | None = None) -> dict:
    """{status, target, kind, changed[], surfaces[], last_run_at, fingerprint, logs[]} for one target."""
    logs = list(target.logs)
    out = {"status": None, "target": target.id, "kind": target.kind, "changed": [], "surfaces": [],
           "last_run_at": None, "fingerprint": None,
           "stamp": {"repo": target.stamp_repo, "path": target.stamp_path}, "logs": logs}
    refusal, owner_st = owner_refusal(target, resolver)
    if refusal:  # never suggest running, and read nothing of the target
        out.update(status="foreign")
        logs.append(refusal)
        return out
    stamp_file = read_stamp(target, src)
    prov = stamp_file.get("provenance") if isinstance(stamp_file.get("provenance"), dict) else None
    cfg = fp.config_sha256(brand)
    inp, ctx = current_inputs(target, brand, src, meta_path=meta_path, gh=gh, snapshot=snapshot,
                              same_owner=resolver.same)
    out.update(last_run_at=prov.get("last_run_at") if prov else None, fingerprint=fingerprint_of(inp, cfg))
    reason = watching_reason(target, owner_st, ctx.get("meta"))
    if reason:
        out.update(status="foreign")
        logs.append(reason)
        return out
    if any(v is UNKNOWN for v in inp.values()):
        logs += [f"provenance:unverified:{k}" for k, v in sorted(inp.items()) if v is UNKNOWN]
    if prov is None:
        out["status"] = "untracked" if _untracked(target, src, stamp_file) else "never"
        out["surfaces"] = _surfaces(target, src, stamp_file) if out["status"] == "untracked" else []
        if out["status"] == "untracked":
            logs.append("provenance:backfill-available")
        return out
    if target.kind == "enterprise" and inp.get("snapshot_sha256") is UNKNOWN:
        raise NeedsInput("snapshot", "enterprise freshness needs the current snapshot: pass --snapshot FILE "
                         "(from `enterprise snapshot`)")
    errs = validate({"provenance": prov})
    if errs:
        logs += [f"provenance:invalid:{e[:120]}" for e in errs[:5]]
    changed = []
    if prov.get("skill_version") != __version__:
        changed.append("skill_version")
    if prov.get("standard") != STANDARD:
        changed.append("standard")
    stored_cfg = stamp_file.get("config_sha256")
    # A repository sidecar's config digest belongs to the generators; a stamp-only sidecar has none and its
    # fingerprint (which includes the config) decides instead.
    if (stored_cfg or target.kind != "repo") and stored_cfg != cfg:
        changed.append("config")
    stored_inputs = stamp_file.get("inputs") if isinstance(stamp_file.get("inputs"), dict) else {}
    changed += [f"inputs:{k}" for k in _changes(stored_inputs, inp)]
    unknown = any(v is UNKNOWN for v in inp.values())
    if target.kind == "repo":
        side_fp = stamp_file.get("fingerprint")
        if side_fp and side_fp != prov.get("fingerprint"):
            changed.append("unstamped-generation")  # art regenerated after the last stamp
        elif not side_fp and not errs and not unknown and prov.get("fingerprint") != fingerprint_of(inp, cfg):
            changed.append("fingerprint")  # stamped before any art: compare the inputs themselves
        if src.local and fp.output_records(stamp_file) and \
                fp.outputs_changed(stamp_file, fingerprint_of(inp, cfg), out_dir=src.root / "docs/images"):
            changed.append("outputs")
        readme = src.read("README.md")
        if readme is not None:
            from .footer import END, attribution, split_credit
            text = readme.decode("utf-8", errors="replace")
            if attribution(brand) and END in text and split_credit(text)[1] is None:
                changed.append("readme:credit")  # decision 25 migration: an old footer without the credit
    elif not errs and not unknown and prov.get("fingerprint") != fingerprint_of(inp, cfg):
        changed.append("fingerprint")
    if errs:
        changed.append("stamp:invalid")
    out["changed"] = sorted(set(changed), key=changed.index)
    out["surfaces"] = list(prov.get("surfaces") or [])
    out["status"] = "stale" if out["changed"] else "fresh"
    return out


# -----------------------------------------------------------------------------------------------------------------
# Stamp
# -----------------------------------------------------------------------------------------------------------------
def build_provenance(brand, target: Target, inp: dict, surfaces: list[str], previous: dict | None, *,
                     inputs_changed: bool, now: str) -> dict:
    from .footer import attribution
    a = attribution(brand) or {}
    prev = previous if isinstance(previous, dict) else {}
    count = prev.get("run_count") if isinstance(prev.get("run_count"), int) and prev.get("run_count", 0) > 0 else 0
    return {"skill": a.get("skill", "github-showcase-skill"), "skill_url": a.get("skill_url", ""),
            "publisher": a.get("publisher", brand.strings.get("company", "")), "skill_version": __version__,
            "standard": STANDARD, "target": {"kind": target.kind, "id": target.id},
            "first_run_at": prev.get("first_run_at") or now, "last_run_at": now,
            "last_changed_at": now if inputs_changed or not prev.get("last_changed_at") else prev["last_changed_at"],
            "run_count": count + 1, "fingerprint": fingerprint_of(inp, fp.config_sha256(brand)),
            "surfaces": sorted(dict.fromkeys(surfaces))}


def stamp_document(brand, target: Target, stamp_file: dict, inp: dict, prov: dict) -> dict:
    """The whole stamp file after this run. For a repository it is the existing sidecar with only the `provenance`
    block replaced (the generators own every other key); a new sidecar carries an empty `outputs` map, which the
    Action's staged-output guard reads as nothing staged."""
    if target.kind == "repo":
        doc = dict(stamp_file) if stamp_file else {"schema": 1, "skill_version": __version__, "standard": STANDARD,
                                                   "outputs": {}}
        doc.setdefault("outputs", {})
        doc["provenance"] = prov
        return doc
    return {"schema": 1, "config_sha256": fp.config_sha256(brand), "inputs": _known(inp), "provenance": prov}


def stamp_text(doc: dict) -> str:
    return fp.sidecar_text(doc)  # sorted keys, the sidecar's own deterministic format


def local_changes(root: Path, exclude: str) -> bool | None:
    """True when the checkout has uncommitted changes under the managed paths other than the stamp file (the run's
    other changes); None when `root` is not a git checkout."""
    try:
        p = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--",
                            *MANAGED], capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    paths = [ln[3:].strip().strip('"') for ln in p.stdout.splitlines() if ln.strip()]
    if any(x != exclude for x in paths):
        return True
    if exclude in paths:  # the sidecar changed: art regenerated, unless only our own block differs
        try:
            head = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{exclude}"], capture_output=True,
                                  text=True, encoding="utf-8", timeout=30)
            old = json.loads(head.stdout) if head.returncode == 0 and head.stdout.strip() else {}
            new = json.loads((root / exclude).read_text(encoding="utf-8"))
        except (OSError, ValueError, subprocess.SubprocessError):
            return True
        old.pop("provenance", None)
        new.pop("provenance", None)
        return old != new
    return False


def jobs_for(path: str | None, target: Target) -> bool:
    """True when the run's jobs file already holds writer jobs for this target (its other changes)."""
    if not path or not Path(path).is_file():
        return False
    names = {x.lower() for x in (target.id, target.stamp_repo or "") if x}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if isinstance(j, dict) and str(j.get("repo") or j.get("org") or "").lower() in names and \
                not str(j.get("id", "")).startswith("provenance:"):
            return True
    return False


def writer_job(target: Target, text: str, blob_sha: str | None) -> dict:
    from .content import job_id
    from .org import job
    repo = target.stamp_repo
    argv = ["gh", "api", "-X", "PUT", f"repos/{repo}/contents/{target.stamp_path}",
            "-f", f"message={COMMIT_MESSAGE}", "-f", "content=" + base64.b64encode(text.encode("utf-8")).decode("ascii")]
    if blob_sha:
        argv += ["-f", f"sha={blob_sha}"]
    note = (f"Record the showcase provenance stamp of {target.kind} {target.id} in {repo}:{target.stamp_path}, in the "
            "same writer batch as this run's other changes. Re-read the file first; if its blob sha changed, re-run "
            "`showcase.py provenance stamp` instead of applying this job.")
    return job(job_id("provenance", target.kind, target.id), JOB_PHASE, "provenance", argv, repo=repo, note=note,
               path=target.stamp_path, idempotent=True)


def topic_job(brand, target: Target, meta: dict, approval_id: str) -> tuple[dict | None, list[str]]:
    """Optional (off by default): add the `attribution.topic` to a public repository's topics, as a writer job that
    needs approval. Authored topics are kept in order; the estate's public topic limit is never exceeded."""
    from .detect import standard
    from .footer import attribution
    from .content import job_id
    from .org import job
    a = attribution(brand) or {}
    topic = a.get("topic")
    if not topic or target.kind != "repo":
        return None, []
    if (meta.get("visibility") or "").lower() != "public":
        return None, ["n/a:attribution-topic:private"]
    current = [t for t in (meta.get("topics") or []) if isinstance(t, str)]
    if topic in current:
        return None, ["attribution-topic:present"]
    limit = standard("topics")["max_public"]
    if len(current) >= limit:
        return None, ["needs-input:topics-capacity"]
    names = current + [topic]
    argv = ["gh", "api", "-X", "PUT", f"repos/{target.id}/topics", "-H", "Accept: application/vnd.github+json"]
    for n in names:
        argv += ["-f", f"names[]={n}"]
    return job(job_id("provenance", "topic", target.id), JOB_PHASE, "topics", argv, repo=target.id,
               approval_id=approval_id, note=f"Optional attribution topic `{topic}` (decision 25): adds it after the "
               "authored topics; the writer re-reads the live topics first.", idempotent=True), []


# -----------------------------------------------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------------------------------------------
def _estate_registry_dir() -> Path | None:
    from .resolver import estate_root
    root = estate_root()
    return root / "registry" if root else None


def enterprise_stamp_dir() -> Path | None:
    """<estate root>/registry: the private home of the Enterprise stamp, beside enterprise.snapshot.json."""
    return _estate_registry_dir()


def source_for(target: Target, *, root: str | Path | None, gh: GH | None) -> Source:
    if target.kind == "enterprise":
        d = Path(root) if root else _estate_registry_dir()
        if d is None:
            raise NeedsInput("estate-root", "the Enterprise stamp lives in the private estate bundle "
                             "(<estate root>/registry/); set SHOWCASE_ESTATE_ROOT or pass --out-dir DIR")
        return Source(root=d)
    if root:
        return Source(root=Path(root))
    return Source(gh=gh, repo=target.stamp_repo)


def _snapshot(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShowcaseError(f"cannot read --snapshot {path}: {exc}", log="usage") from None
    return data if isinstance(data, dict) else None


def _meta_gh(target: Target, meta_path: str | None, gh: GH | None) -> GH | None:
    """With --meta, a repository's metadata comes from the file; org and profile About fields still use gh."""
    return None if (meta_path and target.kind == "repo") else gh


def check_one(text: str, brand, resolver, *, root=None, meta_path=None, gh=None, snapshot=None) -> dict:
    target = parse_target(text, resolver, gh)
    src = source_for(target, root=root, gh=gh)
    return status(target, brand, resolver, src, meta_path=meta_path, gh=_meta_gh(target, meta_path, gh),
                  snapshot=snapshot)


def stamp_one(text: str, brand, resolver, *, root=None, meta_path=None, gh=None, snapshot=None, jobs=None,
              changed: str = "auto", force: bool = False, now: str | None = None) -> tuple[dict, int]:
    """Write (with a local root) or emit as a writer job the stamp of one target. Returns (result, exit code)."""
    target = parse_target(text, resolver, gh)
    src = source_for(target, root=root, gh=gh)
    mgh = _meta_gh(target, meta_path, gh)
    st = status(target, brand, resolver, src, meta_path=meta_path, gh=mgh, snapshot=snapshot)
    res = {"command": "provenance", "action": "stamp", "target": target.id, "kind": target.kind,
           "status": st["status"], "changed": st["changed"], "stamp": st["stamp"], "written": None, "jobs": [],
           "logs": st["logs"]}
    if st["status"] == "foreign":
        res["result"] = "refused"
        return res, USAGE
    other = {"yes": True, "no": False}.get(changed)
    if other is None and src.local and target.kind != "enterprise":
        other = local_changes(src.root, target.stamp_path)
    if other is None:
        other = jobs_for(jobs, target)
    if not (force or st["status"] in ("never", "untracked", "stale") or other):
        res["result"] = "fresh"
        res["logs"].append("provenance:fresh-no-write")  # no commit just to bump the time
        return res, OK
    stamp_file = read_stamp(target, src)
    previous = stamp_file.get("provenance") if isinstance(stamp_file.get("provenance"), dict) else None
    inp, _ = current_inputs(target, brand, src, meta_path=meta_path, gh=mgh, snapshot=snapshot,
                            same_owner=resolver.same)
    now = now or utc_now()
    # Any recorded difference is a change (art regenerated since the last stamp shows as `unstamped-generation`,
    # because the generators already refreshed the sidecar's inputs); other changes alone only bump last_run_at.
    inputs_changed = previous is None or bool(st["changed"])
    prov = build_provenance(brand, target, inp, _surfaces(target, src, stamp_file), previous, now=now,
                            inputs_changed=inputs_changed)
    if target.kind == "repo" and isinstance(stamp_file.get("fingerprint"), str) and len(stamp_file["fingerprint"]) == 64:
        prov["fingerprint"] = stamp_file["fingerprint"]  # the generated art's fingerprint (the sidecar's own inputs)
    errs = validate({"provenance": prov})
    if errs:
        raise ShowcaseError("provenance stamp does not match its schema: " + "; ".join(errs[:3]),
                            log="provenance:invalid")
    res["provenance"] = prov
    if src.local:
        path = src.root / (target.stamp_path if target.kind != "enterprise" else ENTERPRISE_STAMP)
        with fp.sidecar_lock(path):
            # Re-read under the lock: a generator may have just rewritten the sidecar; every other key stays its own.
            fp.replace_bytes(path, stamp_text(stamp_document(brand, target, read_stamp(target, src), inp, prov))
                             .encode("utf-8"))
        res["written"] = str(path)
    elif target.kind == "enterprise":
        res["logs"].append("provenance:enterprise-local-only")
    else:
        j = writer_job(target, stamp_text(stamp_document(brand, target, stamp_file, inp, prov)),
                       src.shas.get(target.stamp_path))
        res["jobs"].append(j)
        if jobs:
            from .records import append
            append(jobs, [j])
    res["result"] = "stamped"
    return res, OK


def _print_text(res: dict) -> None:
    if res.get("action") == "check-batch":
        for r in res["targets"]:
            _print_text(dict(r, action="check"))
        return
    tail = f" ({', '.join(res['changed'])})" if res.get("changed") else ""
    head = f"provenance {res.get('action', 'check')} {res.get('target')}: {res.get('status')}{tail}"
    if res.get("action") == "stamp":
        head += f" -> {res.get('result')}"
        if res.get("written"):
            head += f", wrote {res['written']}"
        elif res.get("jobs"):
            head += f", {len(res['jobs'])} writer job(s)"
    print(head)
    if res.get("logs"):
        print("  logs: " + ", ".join(res["logs"]))


def _batch(args, b, resolver, gh, snap) -> tuple[dict, int]:
    lines = [ln.strip() for ln in Path(args.from_file).read_text(encoding="utf-8").splitlines()]
    if gh is not None and not gh.delay:
        gh.delay = 0.25   # batch: spaced read-only GETs
    rows, code = [], OK
    for t in (x for x in lines if x and not x.startswith("#")):
        try:
            r = check_one(t, b, resolver, gh=gh, snapshot=snap)
            rc = EXIT[r["status"]]
        except ShowcaseError as exc:
            r = {"status": None, "target": t, "changed": [], "surfaces": [], "logs": [exc.log], "error": str(exc)}
            rc = NEEDS_INPUT if isinstance(exc, NeedsInput) else USAGE
        rows.append(r)
        if rc in (NEEDS_INPUT, USAGE) and r["status"] is None:
            code = NEEDS_INPUT
            if r["logs"] == ["needs-input:gh-rate-limit"]:
                break  # stop the batch instead of hammering a rate-limited API
        elif rc == CHECK_FAILED and code == OK:
            code = CHECK_FAILED
    return {"command": "provenance", "action": "check-batch", "result": "ok", "targets": rows,
            "counts": {s: sum(1 for r in rows if r.get("status") == s) for s in STATUSES}, "logs": []}, code


def cmd(args, brand_loader):
    from .resolver import Resolver
    b = brand_loader(args)
    resolver = Resolver.from_paths(b, getattr(args, "registry", None), getattr(args, "approved", None),
                                   getattr(args, "approved_yaml", None), getattr(args, "actions", None))
    fmt = getattr(args, "prov_format", None) or args.format
    args.format = fmt  # `--format` after the action name wins, so showcase.py prints the JSON object
    root = getattr(args, "prov_repo_dir", None) or getattr(args, "out_dir", None) or \
        (args.repo_dir if not getattr(args, "no_repo_dir", False) else None)
    act = args.prov_action
    if act == "star":
        from . import ledger
        if args.decline:
            res = {"command": "provenance", "action": "star", "result": "declined", "state": ledger.decline(),
                   "logs": []}
        else:
            res = {"command": "provenance", "action": "star", "result": "ok", "state": ledger.load(),
                   "state_dir": str(ledger.state_dir()), "logs": []}
        return res, OK
    gh = None if args.offline else GH(delay=args.delay or 0.0)
    snap = _snapshot(args.snapshot)
    if act == "check":
        if args.from_file:
            res, code = _batch(args, b, resolver, gh, snap)
        else:
            if not args.target:
                raise ShowcaseError("provenance check needs TARGET or --from-file FILE", log="usage")
            r = check_one(args.target, b, resolver, root=root, meta_path=args.meta, gh=gh, snapshot=snap)
            res, code = {"command": "provenance", "action": "check", "result": r["status"], **r}, EXIT[r["status"]]
    else:
        if not args.target:
            raise ShowcaseError("provenance stamp needs TARGET", log="usage")
        res, code = stamp_one(args.target, b, resolver, root=root, meta_path=args.meta, gh=gh, snapshot=snap,
                              jobs=args.jobs, changed=args.changed, force=args.force)
        if args.propose_topic and code == OK and res["kind"] == "repo":
            target = parse_target(args.target, resolver)
            j, tlogs = topic_job(b, target, _repo_meta(target, args.meta, gh, resolver.same), args.approval_id or "provenance-topic")
            res["logs"] += tlogs
            if j:
                res["jobs"].append(j)
                if args.jobs:
                    from .records import append
                    append(args.jobs, [j])
    if fmt != "json" and not args.quiet:
        _print_text(res)
    if act == "stamp" and code == OK:
        # Decision 25: one successful `provenance stamp` is one completed run (written, emitted or fresh). The star
        # line, when due and allowed, prints on stderr after the result.
        from . import ledger
        ledger.record_run(b, fresh=res.get("result") == "fresh", fmt=fmt, quiet=args.quiet,
                          no_prompt=args.no_star_prompt)
    return (None if fmt != "json" else res), code


def register(sub, handler) -> None:
    """`provenance {check,stamp,star}` (decision 25). `handler(args)` is showcase.py's dispatcher."""
    import argparse
    p = sub.add_parser("provenance", help="run-once check and provenance stamp of a repository, org, profile or the "
                       "Enterprise (read-only toward GitHub; stamps leave as local writes or writer jobs)")
    ps = p.add_subparsers(dest="prov_action", required=True, metavar="{check,stamp,star}")

    def common(s):
        s.add_argument("target", nargs="?", help="OWNER/REPO, ORG or org:ORG, user:LOGIN, or enterprise:SLUG")
        s.add_argument("--repo-dir", dest="prov_repo_dir", metavar="DIR",
                       help="local checkout that holds the stamp (the repository, ORG/.github or LOGIN/LOGIN)")
        s.add_argument("--out-dir", metavar="DIR",
                       help="directory that holds the stamp (for the Enterprise: <estate root>/registry)")
        s.add_argument("--snapshot", metavar="FILE", help="enterprise snapshot (enterprise targets)")
        s.add_argument("--registry", metavar="FILE")
        s.add_argument("--approved", metavar="FILE")
        s.add_argument("--approved-yaml", metavar="FILE")
        s.add_argument("--actions", metavar="FILE")
        s.add_argument("--offline", action="store_true", help="no gh api GETs (local files and --meta only)")
        s.add_argument("--format", dest="prov_format", choices=("json", "text"), default=None)
        s.set_defaults(func=handler)

    c = ps.add_parser("check", help="never | fresh | stale | untracked | foreign, before running (read-only)")
    common(c)
    c.add_argument("--from-file", metavar="FILE", help="batch: one TARGET per line (# comments)")
    c.add_argument("--delay", type=float, default=0.0, help="seconds between gh api GETs (batch default 0.25)")
    s = ps.add_parser("stamp", help="write the stamp locally (--repo-dir/--out-dir) or emit it as a writer job")
    common(s)
    s.add_argument("--jobs", metavar="FILE", help="append the stamp writer job (scripts/writer.py JSON lines)")
    s.add_argument("--changed", choices=("auto", "yes", "no"), default="auto",
                   help="did this run change anything else? auto: the checkout's git status, else the jobs file")
    s.add_argument("--force", action="store_true", help="stamp a fresh target too (bumps last_run_at)")
    s.add_argument("--propose-topic", action="store_true",
                   help="also propose the attribution topic as a writer job that needs approval (off by default)")
    s.add_argument("--approval-id", metavar="ID", help="approval id for --propose-topic (default provenance-topic)")
    s.add_argument("--no-star-prompt", action="store_true",
                   help="never print the star line (also SHOWCASE_NO_STAR_PROMPT=1)")
    s.add_argument("--delay", type=float, default=0.0, help=argparse.SUPPRESS)
    st = ps.add_parser("star", help="the local run ledger: show it, or --decline the star line for good")
    st.add_argument("--decline", action="store_true")
    st.add_argument("--format", dest="prov_format", choices=("json", "text"), default=None)
    st.set_defaults(func=handler, target=None)


# -----------------------------------------------------------------------------------------------------------------
# Doctor rows (offline: local files only; the existing rows stay unchanged)
# -----------------------------------------------------------------------------------------------------------------
def _row(r: dict) -> dict:
    return {"status": r["status"], "changed": r["changed"], "last_run_at": r.get("last_run_at"), "logs": r["logs"]}


def doctor_repo(ctx, meta_path: str | None) -> dict:
    """The provenance row of repository `doctor`: the checkout's stamp against the captured metadata. No network."""
    if ctx.repo_dir is None or not meta_path:
        return {"status": "unknown", "changed": [], "last_run_at": None,
                "logs": ["needs-input:repo-dir" if ctx.repo_dir is None else "needs-input:metadata"]}
    resolver = ctx.brand.resolver()
    target = Target("repo", resolver.slug(f"{ctx.owner}/{ctx.repo}"), ctx.owner, ctx.repo)
    try:
        return _row(status(target, ctx.brand, resolver, Source(root=Path(ctx.repo_dir)), meta_path=meta_path))
    except ShowcaseError as exc:
        return {"status": "unknown", "changed": [], "last_run_at": None, "logs": [exc.log]}


def doctor_local(kind: str, ident: str, brand, resolver, root, snapshot: dict | None = None) -> dict:
    """The provenance row of `org doctor` (root: the ORG/.github checkout) and `enterprise doctor` (root: the estate
    registry directory). No network: About fields that were not read are skipped, never reported as changes."""
    if root is None:
        need = "dot-github" if kind == "org" else "estate-root"
        return {"status": "unknown", "changed": [], "last_run_at": None, "logs": [f"needs-input:{need}"]}
    target = Target(kind, resolver.canonical(ident) if kind == "org" else ident, ident)
    try:
        return _row(status(target, brand, resolver, Source(root=Path(root)), snapshot=snapshot))
    except ShowcaseError as exc:
        return {"status": "unknown", "changed": [], "last_run_at": None, "logs": [exc.log]}
