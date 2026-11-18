"""Provenance records and bounded comparisons of supplied inputs and recorded output bytes.

A stamp records an observation, never whole-showcase completion or successful writer execution. `fresh` means
only that the recorded outputs match supplied inputs; `skip` stays false because this cannot verify live metadata,
publication, coverage, or visual review. `changed` contains reasons and `rerun` contains source-relative paths.

| Target | Stamp |
|---|---|
| repository `OWNER/REPO` | the `provenance` block of `docs/images/.showcase.json` (the existing sidecar, extended) |
| organization `ORG` (or `org:ORG`) | `.github/showcase.json` in the `ORG/.github` repository |
| personal profile `user:LOGIN` | `.github/showcase.json` in the `LOGIN/LOGIN` repository |
| Enterprise `enterprise:SLUG` | `<estate root>/registry/enterprise.showcase.json`, beside the snapshot; never a public repository |

The sibling `evidence` block preserves generator-owned inputs/outputs, records the compared byte hashes, and lists
missing inputs or pending writers. Empty or partial observations remain incomplete. Counts and timestamps are
outside the fingerprint; unchanged observations write nothing. GitHub access is GET-only, and offline commands
also disable the operator ledger's star-status GET. Writes are local or proposed as writer jobs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from . import REFERENCES, STANDARD, __version__
from . import fingerprint as fp
from .errors import CHECK_FAILED, NEEDS_INPUT, OK, USAGE, NeedsInput, ShowcaseError

SCHEMA = REFERENCES / "provenance.schema.json"
REPO_STAMP = "docs/images/.showcase.json"
DOT_STAMP = ".github/showcase.json"
ENTERPRISE_STAMP = "enterprise.showcase.json"   # in <estate root>/registry/
STATUSES = ("never", "fresh", "stale", "incomplete", "untracked", "foreign")
# Exit codes (errors.py): fresh 0 (recorded outputs only); never, stale, incomplete, untracked 1; foreign 2 (refused owner,
# like every other command); 4 needs-input (no metadata, gh unavailable). A batch exits 4 if any target needs input,
# else 1 if any target has work to do, else 0; a foreign target in a batch is reported, not escalated.
EXIT = {"fresh": OK, "never": CHECK_FAILED, "stale": CHECK_FAILED, "incomplete": CHECK_FAILED,
        "untracked": CHECK_FAILED, "foreign": USAGE}
JOB_PHASE = "9"   # after every other phase of the run: the stamp records the run that the earlier jobs made
COMMIT_MESSAGE = "docs: record showcase provenance (ct-std-v1) [skip ci]"
MANAGED = ("docs/images", "README.md", "CONTRIBUTING.md", ".github/showcase.json", "profile")
UNKNOWN = object()  # unavailable evidence: never grounds a fresh verdict


def relative_path(rel: str) -> str:
    """Validate before joining a filesystem path or constructing a contents API URL."""
    if (not isinstance(rel, str) or not rel or any(c in rel for c in "\\\\:?#%\x00")
            or any(ord(c) < 32 or ord(c) == 127 for c in rel) or rel.startswith("/")
            or any(part.casefold() in ("", ".", "..", ".git") for part in rel.split("/"))):
        raise ShowcaseError("provenance path must stay inside the selected source", log="provenance:path")
    return rel


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
        data = self.json(f"repos/{repo}/contents/{relative_path(path)}")
        if not isinstance(data, dict) or data.get("type") != "file":
            return None, None
        try:
            return base64.b64decode(data.get("content") or ""), data.get("sha")
        except (ValueError, TypeError):
            raise NeedsInput("gh", f"unreadable content for {repo}/{path}") from None


class Source:
    """Where a target's files are read: a local checkout (`--repo-dir`/`--out-dir`) or a repository through GH."""

    def __init__(self, *, root: Path | None = None, gh: GH | None = None, repo: str | None = None):
        self.root, self.gh, self.repo, self.shas = Path(root).absolute() if root is not None else None, gh, repo, {}

    def path(self, rel: str) -> Path:
        rel = relative_path(rel)
        if self.root.exists() and not self.root.is_dir():
            raise ShowcaseError("provenance source must be a directory", log="provenance:path")
        p = self.root / rel
        if any(part.is_symlink() for part in (p, *p.parents)):
            raise ShowcaseError("provenance cannot follow a symlink", log="provenance:path")
        if p.exists() and not p.is_file():
            raise ShowcaseError("provenance needs a regular file", log="provenance:path")
        return p

    @property
    def local(self) -> bool:
        return self.root is not None

    def read(self, rel: str) -> bytes | None:
        relative_path(rel)
        if self.root is not None:
            p = self.path(rel)
            try:
                return p.read_bytes() if p.is_file() else None
            except OSError:
                raise NeedsInput("provenance-file", "cannot read the selected source file") from None
        if self.gh is None or not self.repo:
            raise NeedsInput("provenance-source", "pass a local source or allow read-only GitHub access")
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
            raise NeedsInput("provenance-stamp", "existing stamp is not readable JSON; repair it before stamping") from None
        if not isinstance(obj, dict):
            raise NeedsInput("provenance-stamp", "existing stamp must be a JSON object")
        return obj


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
    if (not re.fullmatch(r"(?:(?:enterprise|org|user):)?[A-Za-z0-9][A-Za-z0-9-]*(?:/[A-Za-z0-9_.-]+)?", raw)
            or raw.rsplit("/", 1)[-1] in (".", "..")):
        raise ShowcaseError("invalid provenance target", log="usage")
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
        raw = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        named = f"{m.get('owner')}/{m.get('repo')}"
        owner_ok = bool(m.get("owner")) and (same(m["owner"], target.owner) if same else
                                             str(m["owner"]).lower() == target.owner.lower())
        if (m.get("repo") or "").lower() != target.repo.lower() or not owner_ok:  # any login of a renamed org
            raise ShowcaseError(f"--meta describes {named}, not {target.id}", log="usage")
        m["_provenance_unknown_inputs"] = [k for k in ("description", "topics", "license", "language") if k not in raw]
        return m
    if gh is None:
        raise NeedsInput("metadata", f"{target.id}: pass --meta FILE, or allow read-only gh api GETs")
    raw = gh.json(f"repos/{target.id}")
    if not isinstance(raw, dict):
        raise NeedsInput("metadata", f"{target.id}: repository not found or not readable")
    return normalize(raw)


def _repo_inputs(meta: dict, src: Source, same_owner=None, meta_path=None) -> dict:
    """The generators' input contract, with every local file read bounded by Source."""
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
    if src.local:
        from .detect import detect
        from .facts import RepoFacts

        class SafeFacts(RepoFacts):
            def read(self, rel):
                value = src.read(rel)
                return value.decode("utf-8", errors="replace") if value is not None else None

            def is_file(self, rel):
                return src.path(rel).is_file()

            def readme(self):
                return next((self.read(n) for n in ("README.md", "readme.md", "Readme.md") if self.is_file(n)), None)

        inp["type"] = detect(meta, SafeFacts(meta, src.root, metadata_path=meta_path), same_owner=same_owner)["type"]
    for name in meta.get("_provenance_unknown_inputs", []):
        inp[name] = UNKNOWN
    if meta.get("files_complete") is False:
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
        inp = _repo_inputs(meta, src, same_owner, meta_path)
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
        # Recompute from captured content: supplied section digests can themselves be stale.
        from .config import canonical
        snap_sha = (hashlib.sha256(canonical(snapshot["sections"]).encode()).hexdigest()
                    if snapshot.get("sections") else None)
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


def _output_path(name: str) -> str:
    # Generator records use bare art filenames, README.md, and root-relative paths (optionally prefixed ./).
    relative_path(name[2:] if isinstance(name, str) and name.startswith("./") else name)
    return name[2:] if name.startswith("./") else name if "/" in name or name == "README.md" else "docs/images/" + name


def _readme_art(target: Target, path: str, data: bytes) -> set[str]:
    from .readmelint import _images, _outside_code
    text = data.decode("utf-8", errors="replace")
    paths = set()
    for _, url in _images(_outside_code(text), text):
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise ShowcaseError("invalid README image URL", log="provenance:path") from None
        if parsed.scheme or parsed.netloc:
            parts = parsed.path.lstrip("/").split("/")
            if (parsed.hostname != "raw.githubusercontent.com" or len(parts) < 4
                    or "/".join(parts[:2]).lower() != (target.stamp_repo or "").lower()):
                continue  # External images are outside this bounded comparison.
            rel = "/".join(parts[3:])
        else:
            rel = str(PurePosixPath(path).parent / unquote(parsed.path).removeprefix("./"))
        paths.add(relative_path(rel))
    return paths


def evidence_for(target: Target, src: Source, stamp_file: dict, inp: dict, cfg: str, snapshot=None) -> dict:
    """Collect bounded bytes, never a completion receipt for lint, a writer, or live publication."""
    records, outputs, missing = fp.output_records(stamp_file), {}, []
    paths = set()
    if target.kind == "repo":
        paths.add("README.md")
        for name in sorted(set(records) | fp.ART_NAMES):
            path = _output_path(name)
            paths.add(path)
            record = records.get(name)
            if not isinstance(record, dict):
                missing.append(f"record:{path}")
                continue
            data = src.read(path)
            if record.get("exempt") in fp.ART_EXEMPTIONS and name in fp.ART_NAMES:
                if data is None and record.get("fingerprint") == fingerprint_of(inp, cfg):
                    outputs[path] = {"exempt": record["exempt"]}
                    paths.discard(path)
                    continue
                missing.append(f"exemption:{path}")
            digest = record.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
                missing.append(f"digest:{path}")
            elif sha(data) != digest:
                missing.append(f"output:{path}")
            if record.get("fingerprint", stamp_file.get("fingerprint")) != fingerprint_of(inp, cfg):
                missing.append(f"generation:{path}")
            if "staged_description" in record:
                missing.append(f"staged:{path}")
    elif target.kind in ("org", "profile"):
        paths.update(("profile/README.md", "profile/data.json") if target.kind == "org" else ("README.md", "data.json"))
    else:
        from .config import canonical
        paths.add("enterprise.snapshot.json")
        sections = (snapshot or {}).get("sections")
        sections = sections if isinstance(sections, dict) else {}
        for name in ("profile", "organizations", "members", "outside_collaborators"):
            if not isinstance(sections.get(name), dict if name == "profile" else list):
                missing.append(f"snapshot:{name}")
        captured = src.read_json("enterprise.snapshot.json")
        if captured and inp.get("snapshot_sha256") is not UNKNOWN and (
                str(captured.get("slug") or "").lower() != target.id.lower()
                or hashlib.sha256(canonical(captured.get("sections")).encode()).hexdigest() != inp["snapshot_sha256"]):
            missing.append("snapshot:source-mismatch")
    for path in sorted(paths):
        if path.endswith("README.md"):
            data = src.read(path)
            if data is not None:
                if not _managed_markers(data.decode("utf-8", errors="replace")):
                    missing.append(f"managed:{path}")
                art = _readme_art(target, path, data)
                paths.update(art)
                if target.kind in ("org", "profile") and not art:
                    missing.append("art-inventory")
    for path in sorted(paths):
        data = src.read(path)
        if data is None:
            missing.append(f"file:{path}")
        else:
            outputs[path] = {"sha256": sha(data)}
    missing += [f"input:{k}" for k, value in sorted(inp.items()) if value is UNKNOWN]
    if target.kind == "repo" and inp.get("visibility") not in ("public", "private", "internal"):
        missing.append("input:visibility")
    return {"version": 1, "scope": "recorded-outputs", "inputs": _known(inp), "config_sha256": cfg,
            "outputs": outputs, "missing": sorted(set(missing)), "pending_jobs": False}


def _evidence_changes(stored: object, current: dict) -> tuple[list[str], list[str]]:
    if not isinstance(stored, dict) or stored.get("version") != 1 or stored.get("scope") != "recorded-outputs":
        return [], ["evidence:recorded-outputs"]
    outputs = stored.get("outputs")
    if (not isinstance(outputs, dict) or not isinstance(stored.get("inputs"), dict)
            or not isinstance(stored.get("missing"), list) or type(stored.get("pending_jobs")) is not bool):
        return [], ["evidence:invalid"]
    changed, missing = [], []
    for path, record in outputs.items():
        relative_path(path)
        if not isinstance(record, dict) or not (set(record) == {"sha256"}
                and isinstance(record["sha256"], str) and re.fullmatch("[0-9a-f]{64}", record["sha256"])
                or set(record) == {"exempt"} and record["exempt"] in fp.ART_EXEMPTIONS):
            missing.append(f"evidence:{path}")
        elif current["outputs"].get(path) != record:
            changed.append(f"output:{path}")
    for path in current["outputs"].keys() - outputs.keys():
        missing.append(f"unrecorded:{path}")
    if not outputs:
        missing.append("evidence:outputs")
    if not all(isinstance(reason, str) for reason in stored["missing"]):
        missing.append("evidence:invalid")
    else:
        missing += [f"recorded:{reason}" for reason in stored["missing"]]
    missing += [f"unrecorded-input:{k}" for k in current["inputs"].keys() - stored["inputs"].keys()]
    if stored["pending_jobs"]:
        missing.append("writer:pending")
    return changed, missing


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


def _same_target(saved, target, resolver) -> bool:
    if not isinstance(saved, dict) or saved.get("kind") != target.kind or not isinstance(saved.get("id"), str):
        return False
    if target.kind == "repo":
        from .context import same_repository
        return same_repository(saved["id"], target.owner, target.repo, resolver)
    return resolver.same(saved["id"], target.id) if target.kind == "org" else saved["id"].lower() == target.id.lower()


def status(target: Target, brand, resolver, src: Source, *, meta_path: str | None = None, gh: GH | None = None,
           snapshot: dict | None = None) -> dict:
    """`changed` contains reasons; `rerun` names files to review/regenerate. Neither is a whole-target skip plan."""
    logs = list(target.logs)
    out = {"status": None, "target": target.id, "kind": target.kind, "changed": [], "surfaces": [],
           "last_run_at": None, "fingerprint": None, "missing": [], "rerun": [], "skip": False,
           "verification_scope": "recorded-outputs",
           "stamp": {"repo": target.stamp_repo, "path": target.stamp_path}, "logs": logs}
    refusal, owner_st = owner_refusal(target, resolver)
    if refusal:  # never suggest running, and read nothing of the target
        out.update(status="foreign")
        logs.append(refusal)
        return out
    stamp_file = read_stamp(target, src)
    prov = stamp_file.get("provenance") if isinstance(stamp_file.get("provenance"), dict) else None
    if prov and not _same_target(prov.get("target"), target, resolver):
        out.update(status="foreign")
        logs.append("provenance:target-mismatch")
        return out
    if prov:
        from .footer import attribution
        identity = attribution(brand) or {}
        if (prov.get("skill") != identity.get("skill", "github-showcase-skill")
                or prov.get("skill_url") != identity.get("skill_url", "")):
            out.update(status="foreign")
            logs.append("provenance:foreign-skill")
            return out
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
    if meta_path:
        logs.append("provenance:metadata-capture-only")
    evidence = evidence_for(target, src, stamp_file, inp, cfg, snapshot)
    out["missing"] = evidence["missing"]
    out["surfaces"] = sorted(evidence["outputs"])
    out["rerun"] = sorted(set(out["surfaces"]) | {m.split(":", 1)[1] for m in out["missing"]
                                                if m.startswith(("file:", "record:"))})
    if prov is None:
        out["status"] = "untracked" if _untracked(target, src, stamp_file) else "never"
        if out["status"] == "untracked":
            logs.append("provenance:backfill-available")
        return out
    errs = validate(stamp_file)
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
    stored_evidence = stamp_file.get("evidence")
    stored_inputs = stored_evidence.get("inputs") if isinstance(stored_evidence, dict) else stamp_file.get("inputs")
    stored_inputs = stored_inputs if isinstance(stored_inputs, dict) else {}
    changed += [f"inputs:{k}" for k in _changes(stored_inputs, inp)]
    unknown = any(v is UNKNOWN for v in inp.values())
    if target.kind == "repo":
        side_fp = stamp_file.get("fingerprint")
        if side_fp and side_fp != prov.get("fingerprint"):
            changed.append("unstamped-generation")  # art regenerated after the last stamp
        elif not side_fp and not errs and not unknown and prov.get("fingerprint") != fingerprint_of(inp, cfg):
            changed.append("fingerprint")  # stamped before any art: compare the inputs themselves
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
    output_changes, missing = _evidence_changes(stored_evidence, evidence)
    changed += output_changes
    out["missing"] = sorted(set(out["missing"] + missing))
    if isinstance(stored_evidence, dict) and stored_evidence.get("config_sha256") != cfg:
        changed.append("config")
    out["changed"] = sorted(set(changed), key=changed.index)
    out["rerun"] = sorted(set(out["rerun"]) | {c[len("output:"):] for c in output_changes})
    out["status"] = "stale" if out["changed"] else "incomplete" if out["missing"] else "fresh"
    if out["status"] == "fresh":
        out["rerun"] = []
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
    """A queue entry is pending work, including attribution and provenance proposals, never an execution receipt."""
    if not path or not Path(path).is_file():
        return False
    names = {x.lower() for x in (target.id, target.stamp_repo or "") if x}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            raise NeedsInput("writer-jobs", "cannot determine pending work from an invalid jobs file") from None
        if not isinstance(j, dict):
            raise NeedsInput("writer-jobs", "writer jobs must be objects")
        if str(j.get("repo") or j.get("org") or "").lower() in names:
            return True
    return False


def _jobs_preflight(path: Path, target: Target, src: Source, meta_path=None, snapshot_path=None) -> bytes | None:
    """Validate a queue without changing it; a JSON object alone is not a writer job."""
    from .staged import check_auxiliary, check_capture
    if any(part.casefold() == ".git" for part in path.parts) or any(p.is_symlink() for p in (path, *path.parents)):
        raise ShowcaseError("jobs destination cannot use Git internals or symlinks", log="provenance:jobs-path")
    if any(p.exists() and not p.is_dir() for p in path.parents):
        raise ShowcaseError("jobs destination needs directory parents", log="provenance:jobs-path")
    check_auxiliary(Path(meta_path) if meta_path else None, src.root, path)
    protected = [Path(p) for p in (meta_path, snapshot_path) if p]
    if src.local:
        document = read_stamp(target, src)
        names = {target.stamp_path, "README.md", "CONTRIBUTING.md", "profile/README.md", "profile/data.json",
                 "data.json", "enterprise.snapshot.json", DOT_STAMP, REPO_STAMP}
        names.update(_output_path(name) for name in fp.output_records(document))
        recorded = document.get("evidence")
        if isinstance(recorded, dict) and isinstance(recorded.get("outputs"), dict):
            names.update(relative_path(name) for name in recorded["outputs"])
        protected += [src.path(name) for name in names]
    for source in protected:
        check_capture(source, path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ShowcaseError("jobs destination needs an unlinked regular file", log="provenance:jobs-path")
    before = path.read_bytes()
    try:
        for line in before.decode("utf-8").splitlines():
            if not line.strip():
                continue
            job = json.loads(line)
            if (not isinstance(job, dict) or not all(isinstance(job.get(k), str) and job[k] for k in ("id", "kind"))
                    or type(job.get("phase")) not in (str, int) or not str(job["phase"])
                    or not isinstance(job.get("repo") or job.get("org"), str) or not (job.get("repo") or job.get("org"))):
                raise ValueError
            command = job.get("steps") if job["kind"] == "browser" else job.get("argv")
            if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
                raise ValueError
    except (UnicodeError, ValueError):
        raise NeedsInput("writer-jobs", "existing queue must contain writer-job JSON lines") from None
    return before


def _publish_stamp(path, data, queued, jobs, before_queue, target, src, meta_path, snapshot_path):
    """Publish the local stamp and queue append together, restoring both if either replacement fails."""
    if jobs and _jobs_preflight(jobs, target, src, meta_path, snapshot_path) != before_queue:
        raise NeedsInput("writer-jobs", "jobs queue changed while preparing provenance; retry")
    if jobs and queued:
        from .formatting import write_formatted_outputs
        from .records import json_lines
        prefix = b"\n" if before_queue and not before_queue.endswith(b"\n") else b""
        write_formatted_outputs([(path, data)] if path else [], snapshots={jobs: before_queue},
                                append_output=(jobs, prefix + json_lines(queued).encode("utf-8")),
                                private_metadata={path} if target.kind == "enterprise" else set())
    elif path:
        fp.replace_bytes(path, data, private=target.kind == "enterprise")


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
               approval_id=approval_id, note=f"Optional attribution topic `{topic}`: adds it after the "
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


def source_for(target: Target, *, root: str | Path | None, gh: GH | None, resolver=None, meta_path=None) -> Source:
    """An explicit export folder is allowed; a checkout must prove the intended destination identity."""
    if target.kind == "enterprise":
        root = root or _estate_registry_dir()
        if root is None:
            raise NeedsInput("estate-root", "the Enterprise stamp lives in the private estate bundle "
                             "(<estate root>/registry/); set SHOWCASE_ESTATE_ROOT or pass --out-dir DIR")
    if root is None:
        return Source(gh=gh, repo=target.stamp_repo)
    src = Source(root=Path(root))
    src.path(target.stamp_path)  # includes the source root and every ancestor, even before mkdir
    probe = next(p for p in (src.root, *src.root.parents) if p.exists())
    try:
        p = subprocess.run(["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, encoding="utf-8", timeout=10)
        top = Path(p.stdout.strip()).resolve() if p.returncode == 0 and p.stdout.strip() else None
        if top is not None:
            p = subprocess.run(["git", "-C", str(top), "remote", "get-url", "origin"],
                               capture_output=True, text=True, encoding="utf-8", timeout=10)
            origin = p.stdout.strip() if p.returncode == 0 else ""
        else:
            origin = ""
    except (OSError, subprocess.SubprocessError):
        top, origin = None, ""
    if top is None:
        if any((p / ".git").exists() for p in (src.root, *src.root.parents)):
            raise NeedsInput("destination-identity", "cannot verify the selected checkout")
        return src  # deliberately selected non-checkout output folder
    if target.kind == "enterprise":
        estate = _estate_registry_dir()
        if estate is not None and src.root == estate.absolute():
            return src
        raise ShowcaseError("Enterprise provenance belongs in the private estate registry", log="provenance:destination")
    from .context import same_repository
    match = re.fullmatch(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?", origin)
    owner, repo = target.stamp_repo.split("/", 1)
    if top == src.root and match and same_repository(match[1], owner, repo, resolver):
        return src
    # The package's explicitly synthetic metadata supports git fixtures without creating fake remotes.
    if top == src.root and not origin and meta_path:
        try:
            raw = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = None
        if isinstance(raw, dict) and isinstance(raw.get("_synthetic"), str) and raw["_synthetic"].strip():
            return src
    raise ShowcaseError("selected checkout does not prove the target repository identity", log="provenance:destination")


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
    if owner_refusal(target, resolver)[0]:
        return status(target, brand, resolver, Source())
    src = source_for(target, root=root, gh=gh, resolver=resolver, meta_path=meta_path)
    return status(target, brand, resolver, src, meta_path=meta_path, gh=_meta_gh(target, meta_path, gh),
                  snapshot=snapshot)


def stamp_one(text: str, brand, resolver, *, root=None, meta_path=None, gh=None, snapshot=None, jobs=None,
              changed: str = "auto", force: bool = False, now: str | None = None,
              pending_jobs: bool = False, extra_jobs=(), snapshot_path=None) -> tuple[dict, int]:
    """Write (with a local root) or emit as a writer job the stamp of one target. Returns (result, exit code)."""
    from .output_lock import output_lock
    target = parse_target(text, resolver, gh)
    refused = owner_refusal(target, resolver)[0]
    src = (Source() if refused else
           source_for(target, root=root, gh=gh, resolver=resolver, meta_path=meta_path))
    queue = Path(jobs).absolute() if jobs and not refused else None
    if queue:
        _jobs_preflight(queue, target, src, meta_path, snapshot_path)
    with output_lock(queue):
        before_queue = _jobs_preflight(queue, target, src, meta_path, snapshot_path) if queue else None
        return _stamp_one(target, brand, resolver, src, meta_path=meta_path, gh=gh, snapshot=snapshot, jobs=queue,
                          changed=changed, force=force, now=now, pending_jobs=pending_jobs, extra_jobs=extra_jobs,
                          snapshot_path=snapshot_path, before_queue=before_queue)


def _stamp_one(target, brand, resolver, src, *, meta_path, gh, snapshot, jobs, changed, force, now, pending_jobs,
               extra_jobs, snapshot_path, before_queue) -> tuple[dict, int]:
    mgh = _meta_gh(target, meta_path, gh)
    st = status(target, brand, resolver, src, meta_path=meta_path, gh=mgh, snapshot=snapshot)
    res = {"command": "provenance", "action": "stamp", "target": target.id, "kind": target.kind,
           "status": st["status"], "changed": st["changed"], "stamp": st["stamp"], "written": None, "jobs": list(extra_jobs),
           "logs": st["logs"], "missing": st["missing"], "rerun": st["rerun"], "skip": False,
           "verification_scope": "recorded-outputs", "completed": False}
    if st["status"] == "foreign":
        res["result"] = "refused"
        res["jobs"] = []
        return res, USAGE
    other = {"yes": True, "no": False}.get(changed)
    if other is None and src.local and target.kind != "enterprise":
        other = local_changes(src.root, target.stamp_path)
    if other is None:
        other = jobs_for(jobs, target)
    pending = pending_jobs or bool(extra_jobs) or jobs_for(jobs, target) or not src.local
    if not (force or st["status"] != "fresh" or other or pending):
        res["result"] = "fresh"
        res["completed"] = True  # verified local output comparison, never proof of a live writer run
        res["logs"].append("provenance:fresh-no-write")  # no commit just to bump the time
        return res, OK
    stamp_file = read_stamp(target, src)
    previous = stamp_file.get("provenance") if isinstance(stamp_file.get("provenance"), dict) else None
    inp, _ = current_inputs(target, brand, src, meta_path=meta_path, gh=mgh, snapshot=snapshot,
                            same_owner=resolver.same)
    evidence = evidence_for(target, src, stamp_file, inp, fp.config_sha256(brand), snapshot)
    evidence["pending_jobs"] = pending
    if pending:
        evidence["missing"].append("writer:pending")
    res["missing"] = evidence["missing"]
    if previous and evidence == stamp_file.get("evidence") and not st["changed"] and not (force or other):
        res["result"] = st["status"]
        res["logs"].append("provenance:incomplete-no-write")
        return res, OK
    now = now or utc_now()
    # Any recorded difference is a change (art regenerated since the last stamp shows as `unstamped-generation`,
    # because the generators already refreshed the sidecar's inputs); other changes alone only bump last_run_at.
    inputs_changed = previous is None or bool(st["changed"]) or evidence != stamp_file.get("evidence")
    prov = build_provenance(brand, target, inp, sorted(evidence["outputs"]), previous, now=now,
                            inputs_changed=inputs_changed)
    if target.kind == "repo" and isinstance(stamp_file.get("fingerprint"), str) and len(stamp_file["fingerprint"]) == 64:
        prov["fingerprint"] = stamp_file["fingerprint"]  # the generated art's fingerprint (the sidecar's own inputs)
    errs = validate({"provenance": prov, "evidence": evidence})
    if errs:
        raise ShowcaseError("provenance stamp does not match its schema: " + "; ".join(errs[:3]),
                            log="provenance:invalid")
    res["provenance"] = prov
    if src.local:
        path = src.path(target.stamp_path)
        with fp.sidecar_lock(path):
            # Re-read under the lock: a generator may have just rewritten the sidecar; every other key stays its own.
            current = read_stamp(target, src)
            if current != stamp_file:
                raise NeedsInput("provenance-race", "outputs changed while preparing the stamp; retry")
            locked_inp, _ = current_inputs(target, brand, src, meta_path=meta_path, gh=mgh, snapshot=snapshot,
                                           same_owner=resolver.same)
            locked_evidence = evidence_for(target, src, current, locked_inp, fp.config_sha256(brand), snapshot)
            expected_evidence = dict(evidence, pending_jobs=False,
                                     missing=[reason for reason in evidence["missing"] if reason != "writer:pending"])
            if locked_inp != inp or locked_evidence != expected_evidence:
                raise NeedsInput("provenance-race", "source changed while preparing the stamp; retry")
            src.path(target.stamp_path)
            doc = dict(stamp_document(brand, target, current, inp, prov), evidence=evidence)
            _publish_stamp(path, stamp_text(doc).encode("utf-8"), res["jobs"], jobs, before_queue, target, src,
                           meta_path, snapshot_path)
        res["written"] = str(path)
    elif target.kind == "enterprise":
        res["logs"].append("provenance:enterprise-local-only")
    else:
        j = writer_job(target, stamp_text(dict(stamp_document(brand, target, stamp_file, inp, prov), evidence=evidence)),
                       src.shas.get(target.stamp_path))
        res["jobs"].insert(0, j)
        _publish_stamp(None, None, res["jobs"], jobs, before_queue, target, src, meta_path, snapshot_path)
    res["result"] = "stamped"
    res["completed"] = src.local and not evidence["missing"] and not pending
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
            r = {"status": None, "target": t, "changed": [], "surfaces": [], "logs": [exc.log], "error": str(exc),
                 "missing": [exc.log], "rerun": [], "skip": False, "verification_scope": "recorded-outputs"}
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
        j, tlogs = None, []
        if args.propose_topic:
            target = parse_target(args.target, resolver)
            if target.kind == "repo" and not owner_refusal(target, resolver)[0]:
                j, tlogs = topic_job(b, target, _repo_meta(target, args.meta, gh, resolver.same),
                                    args.approval_id or "provenance-topic")
        res, code = stamp_one(args.target, b, resolver, root=root, meta_path=args.meta, gh=gh, snapshot=snap,
                              jobs=args.jobs, changed=args.changed, force=args.force, extra_jobs=[j] if j else [],
                              snapshot_path=args.snapshot)
        if code == OK:
            res["logs"] += tlogs
    if fmt != "json" and not args.quiet:
        _print_text(res)
    if act == "stamp" and code == OK and res.get("completed"):
        # Only verified local output captures count. Proposals and incomplete captures are not completed runs.
        from . import ledger
        ledger.record_run(b, fresh=res.get("result") == "fresh", fmt=fmt, quiet=args.quiet,
                          no_prompt=args.no_star_prompt, offline=args.offline)
    return (None if fmt != "json" else res), code


def register(sub, handler) -> None:
    """`provenance {check,stamp,star}`. `handler(args)` is showcase.py's dispatcher."""
    import argparse
    p = sub.add_parser("provenance", help="recorded-output comparison and stamp of a repository, org, profile or the "
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

    c = ps.add_parser("check", help="never | fresh | stale | incomplete | untracked | foreign (read-only)")
    common(c)
    c.add_argument("--from-file", metavar="FILE", help="batch: one TARGET per line (# comments)")
    c.add_argument("--delay", type=float, default=0.0, help="seconds between gh api GETs (batch default 0.25)")
    s = ps.add_parser("stamp", help="write the stamp locally (--repo-dir/--out-dir) or emit it as a writer job")
    common(s)
    s.add_argument("--jobs", metavar="FILE", help="append the stamp writer job (scripts/writer.py JSON lines)")
    s.add_argument("--changed", choices=("auto", "yes", "no"), default="auto",
                   help="did this run change anything else? auto: the checkout's git status, else the jobs file")
    s.add_argument("--force", action="store_true", help="record unchanged evidence too (bumps last_run_at)")
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
    return {key: r.get(key) for key in ("status", "changed", "missing", "rerun", "skip", "verification_scope",
                                      "last_run_at", "logs")}


def _unknown_row(log: str) -> dict:
    return {"status": "unknown", "changed": [], "missing": [log], "rerun": [], "skip": False,
            "verification_scope": "recorded-outputs", "last_run_at": None, "logs": [log]}


def doctor_repo(ctx, meta_path: str | None) -> dict:
    """The provenance row of repository `doctor`: the checkout's stamp against the captured metadata. No network."""
    if ctx.repo_dir is None or not meta_path:
        return _unknown_row("needs-input:repo-dir" if ctx.repo_dir is None else "needs-input:metadata")
    resolver = ctx.brand.resolver()
    target = Target("repo", resolver.slug(f"{ctx.owner}/{ctx.repo}"), ctx.owner, ctx.repo)
    try:
        src = (Source() if owner_refusal(target, resolver)[0] else
               source_for(target, root=ctx.repo_dir, gh=None, resolver=resolver, meta_path=meta_path))
        return _row(status(target, ctx.brand, resolver, src, meta_path=meta_path))
    except ShowcaseError as exc:
        return _unknown_row(exc.log)


def doctor_local(kind: str, ident: str, brand, resolver, root, snapshot: dict | None = None) -> dict:
    """The provenance row of `org doctor` (root: the ORG/.github checkout) and `enterprise doctor` (root: the estate
    registry directory). No network: unread About fields remain explicit missing evidence, never a change."""
    if root is None:
        need = "dot-github" if kind == "org" else "estate-root"
        return _unknown_row(f"needs-input:{need}")
    target = Target(kind, resolver.canonical(ident) if kind == "org" else ident, ident)
    try:
        src = Source() if owner_refusal(target, resolver)[0] else source_for(target, root=root, gh=None, resolver=resolver)
        return _row(status(target, brand, resolver, src, snapshot=snapshot))
    except ShowcaseError as exc:
        return _unknown_row(exc.log)
