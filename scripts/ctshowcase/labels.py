"""STANDARD §6 label standard: emit labels.yml, plan pass A/B, print gh commands (spec A6.9).

Never `--force`, never a delete, and never a GitHub write: plans leave as `gh` argv and scripts/writer.py jobs.
"""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from . import REFERENCES

LABELS_YML = REFERENCES / "standard" / "labels.yml"
NAMESPACE_COLORS = {"area": "5319e7", "scope": "bfdadc"}
REF_FILES_BLOCK = (".github/workflows/", "release.yml", "labeler.yml", "renovate.json", "renovate.json5")
# Renovate's repository config files, in the order Renovate reads them (its documented `configFileNames`, less the
# `renovate` key of the root package.json, which `_referenced` reads on a checkout): a label named in any of them blocks
RENOVATE_FILES = ("renovate.json", "renovate.json5", ".github/renovate.json", ".github/renovate.json5",
                  ".gitlab/renovate.json", ".gitlab/renovate.json5", ".gitea/renovate.json", ".gitea/renovate.json5",
                  ".forgejo/renovate.json", ".forgejo/renovate.json5", ".renovaterc", ".renovaterc.json",
                  ".renovaterc.json5")
_RENOVATE_LOW = frozenset(f.lower() for f in RENOVATE_FILES)
NEEDS_CHECKOUT = "needs-input:label-references"


def emit_yml() -> str:
    return LABELS_YML.read_text(encoding="utf-8")


def standard_labels() -> list[dict]:
    import yaml
    return yaml.safe_load(emit_yml())


_LABELS_KEY = re.compile(r"""^(\s*(?:-\s+)?)["']?labels["']?\s*:(.*)$""")
BOM = "﻿"


def _uncomment(text: str) -> str:
    return re.sub(r"\s+#.*$", "", text)


def _form_kind(rel: str) -> str | None:
    """'form' (an issue form directly in `.github/ISSUE_TEMPLATE/`), 'md' (a Markdown issue template there),
    'dependabot' (`.github/dependabot.yml`), else None: only these assign labels."""
    low = rel.lower()
    in_templates = low.startswith(".github/issue_template/") and low.count("/") == 2
    if in_templates and low.endswith((".yml", ".yaml")):
        return "form"
    if in_templates and low.endswith(".md"):
        return "md"
    return "dependabot" if low in (".github/dependabot.yml", ".github/dependabot.yaml") else None


def _front_matter(text: str) -> tuple[list[tuple[int, str]], bool]:
    """The (line number, line) pairs of a Markdown template's front matter and whether it is well formed: an
    unterminated block returns every line and False, so the caller fails closed."""
    raw = text.lstrip(BOM).splitlines()
    if not raw or raw[0].strip() != "---":
        return [], True
    end = next((i for i in range(1, len(raw)) if raw[i].strip() == "---"), None)
    if end is None:
        return list(enumerate(raw, 1)), False
    return list(enumerate(raw[1:end], 2)), True


def _label_entries(rel: str, text: str, kind: str | None = None) -> list[tuple[int, str]]:
    """The (line number, line) pairs that assign labels in a file rule 0 rewrites, for reporting `path:line`: the
    `labels:` key of an issue form, the `labels:` key in the front matter of a Markdown issue template, and the
    `labels:` entries of `.github/dependabot.yml`, each with its inline value or the `- item` lines under it. Whether
    the file names a label is decided by parsing it (`_names_label`), not by this scan."""
    kind = kind or _form_kind(rel)
    if kind in ("form", "dependabot"):
        lines = list(enumerate(text.lstrip(BOM).splitlines(), 1))
    elif kind == "md":
        lines = _front_matter(text)[0]
    else:
        return []
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        n, ln = lines[i]
        m = _LABELS_KEY.match(ln)
        i += 1
        if not m:
            continue
        if _uncomment(m.group(2)).strip():
            out.append((n, ln))  # inline: labels: [bug, x] / labels: bug / labels: "bug, x"
            continue
        col = len(m.group(1))  # block list: the `- item` lines indented under the key (or level with it)
        while i < len(lines):
            n2, ln2 = lines[i]
            body = ln2.lstrip()
            if not body or body.startswith("#"):
                i += 1
                continue
            ind = len(ln2) - len(body)
            if ind < col or not body.startswith("-") or (ind == col and not body.startswith("- ") and body != "-"):
                break
            out.append((n2, ln2))
            i += 1
    return out


def _label_values(v) -> set[str] | None:
    """The lower-cased label names a `labels` value assigns (a list, or a comma-separated string); None when the value
    has a shape GitHub's forms, templates and dependabot.yml do not use, so the caller fails closed."""
    if v is None:
        return set()
    if isinstance(v, str):
        return {x.strip().lower() for x in v.split(",") if x.strip()}
    if isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v):
        return {str(x).strip().lower() for x in v}
    return None


def _names_label(kind: str, text: str, name: str) -> bool | None:
    """Whether the parsed file assigns label `name` (case-insensitively, as GitHub matches it): the top-level `labels`
    of an issue form or of a Markdown template's front matter, or any `updates[*].labels` of dependabot.yml. None when
    the YAML cannot be read (a parse error, an unterminated front matter, an unexpected shape)."""
    import yaml
    body = text.lstrip(BOM)
    if kind == "md":
        lines, ok = _front_matter(body)
        if not ok:
            return None
        body = "\n".join(ln for _, ln in lines)
    try:
        doc = yaml.safe_load(body) if body.strip() else None
    except yaml.YAMLError:
        return None
    if doc is None:
        return False
    if not isinstance(doc, dict):
        return None
    if kind == "dependabot":
        ups = doc.get("updates")
        if ups is None:
            return False
        if not isinstance(ups, list) or not all(isinstance(u, dict) for u in ups):
            return None
        vals = [u["labels"] for u in ups if "labels" in u]
    else:
        vals = [doc["labels"]] if "labels" in doc else []
    want = name.lower()
    for v in vals:
        got = _label_values(v)
        if got is None:
            return None
        if want in got:
            return True
    return False


def _form_hits(rel: str, kind: str, text: str, name: str, repo: str | None = None) -> list[dict]:
    """The {path, line, text} to rewrite when the parsed file assigns `name`. A file that cannot be parsed fails closed:
    every line naming the label as a whole token is reported (a form's prose then holds the rename until the file
    parses). A file that parses and does not assign it returns nothing, whatever its prose says."""
    named = _names_label(kind, text, name)
    if named is False:
        return []
    key_pat = re.compile(rf"(?<![\w:-]){re.escape(name)}(?![\w:-])", re.IGNORECASE)
    lines = [(n, ln) for n, ln in _label_entries(rel, text, kind) if key_pat.search(_uncomment(ln))] if named else []
    if not lines:  # a multi-line flow sequence, an alias, or an unreadable file: report each line naming the label
        lines = [(n, ln) for n, ln in enumerate(text.lstrip(BOM).splitlines(), 1) if key_pat.search(ln)]
    if not lines and named:
        lines = [(1, "labels")]
    extra = {"repo": repo} if repo else {}
    return [{**extra, "path": rel, "line": n, "text": ln.strip()} for n, ln in lines]


# the paths rule 0 can act on, as glob patterns: a capture with none of them proves no rename needs a checkout
REFERENCE_PATTERNS = (".github/ISSUE_TEMPLATE/*", ".github/dependabot.yml", ".github/dependabot.yaml",
                      ".github/workflows/*", ".github/**/release.yml", ".github/**/labeler.yml", ".github/**/renovate.json",
                      ".github/**/renovate.json5", *(f for f in RENOVATE_FILES if not f.startswith(".github/")))
# where the owner's `.github` repository keeps the default issue forms GitHub applies to every repository without a
# `.github/ISSUE_TEMPLATE/` of its own (read case-insensitively, so a capture errs toward a hold)
DEFAULT_FORM_DIRS = (".github/ISSUE_TEMPLATE", "ISSUE_TEMPLATE", "docs/ISSUE_TEMPLATE")
DEFAULT_PATTERNS = tuple(f"{d}/*" for d in DEFAULT_FORM_DIRS)


def reference_file(rel: str) -> bool:
    """True for a path `_referenced` acts on (a block or a rewrite), case-insensitively so a capture errs toward a hold:
    `.github/workflows/*`, any `.github/**` file ending in release.yml, labeler.yml, renovate.json or renovate.json5,
    every other Renovate config file (RENOVATE_FILES), an issue form or Markdown template directly in
    `.github/ISSUE_TEMPLATE/`, and dependabot.yml. The root package.json is not one: a file list cannot show whether it
    holds a `renovate` key (see references/labels.md, rule 0)."""
    low = rel.lower().lstrip("/")
    if low in _RENOVATE_LOW:
        return True
    if not low.startswith(".github/"):
        return False
    if low.startswith(".github/workflows/") or low.endswith(REF_FILES_BLOCK[1:]):
        return True
    if low.startswith(".github/issue_template/") and low.count("/") == 2 and low.endswith((".yml", ".yaml", ".md")):
        return True
    return low in (".github/dependabot.yml", ".github/dependabot.yaml")


def default_form_file(rel: str) -> bool:
    """True for a file directly in one of DEFAULT_FORM_DIRS of the owner's `.github` repository (case-insensitive)."""
    low = rel.lower().lstrip("/")
    return any(low.startswith(d.lower() + "/") and "/" not in low[len(d) + 1:] for d in DEFAULT_FORM_DIRS)


def _capture(files, complete: bool) -> tuple[dict, bool]:
    from .org import _captured_files
    return _captured_files({"files": files, "files_complete": complete})


def reference_files(files, complete: bool = False) -> tuple[list[str], bool]:
    """(reference-bearing paths the capture lists, complete) from a metadata `files` value: `meta --from-gh`'s list of
    blob paths (complete only when the capture records `files_complete: true`, i.e. GitHub did not truncate the
    recursive tree), or the fixtures' partial {path: value} map. Only a complete list with none of them proves that rule
    0 has nothing to find; a map, a truncated or unmarked list, a missing capture or a listed reference file needs a
    checkout."""
    cap, complete = _capture(files, complete)
    found = sorted(p for p, v in cap.items() if v is not None and v is not False and reference_file(p))
    return found, complete


def defaults_source(repo: str, *, repo_dir: str | Path | None = None, meta: dict | None = None,
                    verified: bool = True) -> dict:
    """The owner's `.github` repository as rule 0 reads it: a checkout, else its captured metadata (None: unknown).
    `verified` False marks a checkout whose origin could not be read: a default form found in it still holds the
    rename, but finding none proves nothing (it may be another org's `.github`), so the rename stays held."""
    m = meta or {}
    return {"repo": repo, "dir": Path(repo_dir) if repo_dir else None, "files": m.get("files"),
            "complete": m.get("files_complete") is True, "verified": verified}


def _owner_resolver(resolver):
    """The org resolver for comparing logins (CQ-03): the caller's, else the default brand.yaml's, else None."""
    if resolver is not None:
        return resolver
    from .errors import ShowcaseError
    try:
        from .config import load_brand
        return load_brand().resolver()
    except (ShowcaseError, OSError, ValueError):
        return None


def _same_owner(resolver, a: str, b: str) -> bool:
    if resolver is not None:
        return resolver.same(a, b)
    return bool(a and b) and a.lower() == b.lower()


def _json_owner(raw: dict) -> str | None:
    """The owner login a `.github` metadata JSON names (`owner`, `owner.login` or `full_name`), else None."""
    o = raw.get("owner")
    if isinstance(o, dict):
        o = o.get("login")
    if isinstance(o, str) and o.strip():
        return o.strip()
    full = raw.get("full_name") or raw.get("nameWithOwner")
    if isinstance(full, str) and "/" in full:
        return full.split("/", 1)[0].strip() or None
    return None


def _checkout_origin(d: Path) -> tuple[str, str] | None:
    """(owner, repo) of a checkout's GitHub `origin`, read only from the directory itself (never an enclosing
    repository), else None."""
    if not (d / ".git").exists():
        return None
    from .meta import from_repo_dir
    m = from_repo_dir(d)
    return (m["owner"], m["repo"]) if m.get("owner") and m.get("repo") else None


def defaults_for(owner: str, repo: str, *, repo_dir=None, meta: dict | None = None, path: str | Path | None = None,
                 resolver=None) -> dict:
    """The owner's `.github` repository for rule 0 in R = owner/repo: R itself when R is `.github`, else `path` (a
    checkout of it, or its metadata JSON from `meta --from-gh OWNER/.github`), else unknown (renames then hold).
    `path` must be the OWNER's `.github` (old and new logins resolve alike through `resolver`): one that names another
    org or repository is refused (usage); one whose owner cannot be read holds the renames (`needs-input:label-references`)."""
    full = f"{owner}/.github"
    if repo == ".github":
        return defaults_source(full, repo_dir=repo_dir, meta=meta)
    if not path:
        return defaults_source(full)
    from .errors import ShowcaseError
    p = Path(path)
    if p.is_dir():
        origin = _checkout_origin(p)
        if origin is None:
            return defaults_source(full, repo_dir=p, verified=False)
        if origin[1].lower() != ".github" or not _same_owner(_owner_resolver(resolver), origin[0], owner):
            raise ShowcaseError(f"--org-defaults {p} is a checkout of {origin[0]}/{origin[1]}, not {full}", log="usage")
        return defaults_source(full, repo_dir=p)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ShowcaseError(f"--org-defaults {p}: neither a checkout of {full} nor its metadata JSON", log="usage") from None
    name = (raw.get("repo") or raw.get("name") or str(raw.get("full_name") or "/").split("/")[-1]) if isinstance(raw, dict) else None
    if name and name != ".github":
        raise ShowcaseError(f"--org-defaults {p} describes {name}, not {full}", log="usage")
    if not isinstance(raw, dict) or raw.get("error"):
        return defaults_source(full)
    who = _json_owner(raw)
    if who is None:
        return defaults_source(full)  # whose .github it is cannot be told: the renames stay held
    if not _same_owner(_owner_resolver(resolver), who, owner):
        raise ShowcaseError(f"--org-defaults {p} describes {who}/.github, not {full}", log="usage")
    return defaults_source(full, meta=raw)


def _own_forms(rd: Path | None, files, complete: bool) -> bool | None:
    """True when R has a file directly in its own `.github/ISSUE_TEMPLATE/` (exact case: GitHub then ignores the
    owner's default forms), False when a checkout or a complete capture shows none, None when the capture cannot tell."""
    if rd is not None:
        d = rd / ".github" / "ISSUE_TEMPLATE"
        return d.is_dir() and any(p.is_file() for p in d.iterdir())
    cap, complete = _capture(files, complete)
    if any(v is not None and v is not False and re.fullmatch(r"\.github/ISSUE_TEMPLATE/[^/]+", p) for p, v in cap.items()):
        return True
    return False if complete else None


def _default_forms(defaults: dict | None, name: str) -> tuple[str | None, list]:
    """Rule 0 on the owner's `.github` repository: ('rewrite', hits) when a default form there assigns `name`,
    ('unchecked', check_files) when its checkout is not given and its capture does not prove it has no default form,
    else (None, [])."""
    repo = (defaults or {}).get("repo") or "<owner>/.github"
    d = (defaults or {}).get("dir")
    if d is not None:
        hits: list[dict] = []
        for sub in DEFAULT_FORM_DIRS:
            parent = d
            for part in sub.split("/"):  # case-insensitive walk, so an unusual casing is still read
                parent = next((c for c in sorted(parent.iterdir()) if c.is_dir() and c.name.lower() == part.lower()), None) \
                    if parent is not None and parent.is_dir() else None
            for p in sorted(parent.iterdir()) if parent is not None else []:
                if not p.is_file():
                    continue
                low = p.name.lower()
                kind = "form" if low.endswith((".yml", ".yaml")) else "md" if low.endswith(".md") else None
                if kind:
                    hits += _form_hits(p.relative_to(d).as_posix(), kind, p.read_text(encoding="utf-8", errors="ignore"),
                                       name, repo=repo)
        if not hits and (defaults or {}).get("verified") is False:  # no origin: may be another org's .github
            return "unchecked", [f"{repo}:{p} (checkout without a GitHub origin)" for p in DEFAULT_PATTERNS]
        return ("rewrite" if hits else None), hits
    cap, complete = _capture((defaults or {}).get("files"), bool((defaults or {}).get("complete")))
    found = sorted(p for p, v in cap.items() if v is not None and v is not False and default_form_file(p))
    if found or not complete:
        return "unchecked", [f"{repo}:{p}" for p in found + ([] if complete else list(DEFAULT_PATTERNS))]
    return None, []


def _strings(v) -> list[str]:
    """Every string (keys included) in a parsed JSON value."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for k, x in v.items() for s in [str(k), *_strings(x)]]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def _package_renovate(text: str, pat: re.Pattern) -> bool:
    """True when the root package.json's `renovate` key (Renovate's package.json config) names the label. A file that
    does not parse fails closed: it blocks when it mentions "renovate" and the label as a token anywhere."""
    try:
        data = json.loads(text.lstrip(BOM))
    except (ValueError, RecursionError):
        return '"renovate"' in text and bool(pat.search(text))
    return isinstance(data, dict) and "renovate" in data and any(pat.search(s) for s in _strings(data["renovate"]))


def _renovate_paths(repo_dir: Path) -> list[Path]:
    """The checkout's Renovate config files outside `.github/` and its root package.json, matched case-insensitively
    so an unusual casing errs toward a block."""
    out: list[Path] = []
    for c in sorted(repo_dir.iterdir()):
        low = c.name.lower()
        if c.is_file() and (low in _RENOVATE_LOW or low == "package.json"):
            out.append(c)
        elif c.is_dir() and low in (".gitlab", ".gitea", ".forgejo"):
            out += [f for f in sorted(c.iterdir()) if f.is_file() and f"{low}/{f.name.lower()}" in _RENOVATE_LOW]
    return out


def _referenced(repo_dir: Path | None, name: str) -> tuple[str | None, list[dict]]:
    """§6.4 rule 0: ('block', hits) when referenced in workflows/release/labeler or any Renovate config file (the
    `renovate` key of the root package.json included); ('rewrite', hits) when an
    issue form's or template's `labels:` key or a dependabot.yml `labels:` entry assigns it, where hits are the
    {path, line, text} the estate/polish PR rewrites before the rename. A mention in prose is not a reference."""
    if repo_dir is None:
        return None, []
    pat = re.compile(rf"(?<![\w:-]){re.escape(name)}(?![\w:-])")
    hits: list[dict] = []
    cands = sorted((repo_dir / ".github").rglob("*")) if (repo_dir / ".github").is_dir() else []
    cands += _renovate_paths(repo_dir)
    for p in cands:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = p.relative_to(repo_dir).as_posix()
        if rel.lower() == "package.json":
            if _package_renovate(text, pat):
                return "block", [{"path": rel}]
            continue
        if (rel.startswith(".github/workflows/") or rel.endswith(REF_FILES_BLOCK[1:]) or rel.lower() in _RENOVATE_LOW) \
                and pat.search(text):
            return "block", [{"path": rel}]
        kind = _form_kind(rel)
        if kind:
            hits += _form_hits(rel, kind, text, name)
    return ("rewrite" if hits else None), hits


def _rename_or_hold(rd: Path | None, files, complete: bool, defaults: dict | None, cur: str, new: str, color: str,
                    description: str, rule: str, ops: list[dict], logs: list[str]) -> None:
    """Rule 0 for one rename, in R and in the owner's `.github` repository (whose default issue forms apply to R when R
    has no `.github/ISSUE_TEMPLATE/` of its own). A form or dependabot.yml reference is a content change for the
    estate/polish PR, not a label job: the rename is held (op skip, log label-rewrite-first, with the lines to rewrite)
    until a re-plan of the merged checkout no longer finds them, so no plan ever emits a rename that leaves a form
    naming a missing label. Without a checkout the check fails closed: the rename leaves only when the captured file
    lists prove no file rule 0 reads exists; otherwise it is held (needs-input:label-references) with the files a
    checkout must be read for."""
    check: list[str] = []
    if rd is None:
        found, proven = reference_files(files, complete)
        if found or not proven:  # an unlisted path of a partial, truncated or missing capture may still exist
            check = found if proven else found + list(REFERENCE_PATTERNS)
        ref, hits = None, []
    else:
        ref, hits = _referenced(rd, cur)
    if ref != "block" and _own_forms(rd, files, complete) is not True:
        dref, got = _default_forms(defaults, cur)
        if dref == "rewrite":
            ref, hits = "rewrite", hits + got
        elif dref == "unchecked":
            check += got
    if ref == "block":
        ops.append({"op": "skip", "name": cur, "new_name": new, "rule": "§6.4 rule 0", "log": "label-referenced"})
        logs.append("label-referenced")
    elif check:
        ops.append({"op": "skip", "name": cur, "new_name": new, "rule": "§6.4 rule 0", "log": NEEDS_CHECKOUT,
                    "check_files": check, **({"rewrite_references": hits} if hits else {})})
        logs.append(NEEDS_CHECKOUT)
    elif ref == "rewrite":
        ops.append({"op": "skip", "name": cur, "new_name": new, "rule": "§6.4 rule 0", "log": "label-rewrite-first",
                    "rewrite_references": hits})
        logs.append("label-rewrite-first")
    else:
        ops.append({"op": "rename", "name": cur, "new_name": new, "color": color, "description": description, "rule": rule})


def plan(existing: list[dict], repo_dir: str | Path | None = None, files=None, *, complete: bool = False,
         defaults: dict | None = None) -> tuple[list[dict], list[str]]:
    """§6.3 passes A and B against the live labels. Every rename passes §6.4 rule 0: scanned in `repo_dir` when a
    checkout is given, else checked against `files` (the metadata's captured file list, `complete` when the capture
    records `files_complete: true`), and held when unproven. `defaults` is the owner's `.github` repository
    (`defaults_source`); None means it is unknown, so a rename in a repository without forms of its own is held."""
    std = standard_labels()
    rd = Path(repo_dir) if repo_dir else None
    by_low = {lb["name"].lower(): dict(lb) for lb in existing}
    ops: list[dict] = []
    logs: list[str] = []
    claimed: set[str] = set()
    missing = []
    for L in std:
        name, low = L["name"], L["name"].lower()
        aliases = [a.lower() for a in L.get("aliases", [])]
        if low in by_low:
            cur = by_low[low]
            claimed.add(low)
            diff = {}
            if cur["name"] != name:
                diff["new_name"] = name
            if (cur.get("color") or "").lower() != L["color"]:
                diff["color"] = L["color"]
            if (cur.get("description") or "") != L["description"]:
                diff["description"] = L["description"]
            ops.append({"op": "patch" if diff else "skip", "name": cur["name"], **diff, "rule": "§6.4 rule 3"})
            for a in aliases:
                if a in by_low:
                    ops.append({"op": "skip", "name": by_low[a]["name"], "rule": "§6.4 rule 2", "log": "label-conflict"})
                    logs.append("label-conflict")
                    claimed.add(a)
            continue
        present = [a for a in aliases if a in by_low and a not in claimed]
        if present:
            a = present[0]
            cur = by_low[a]
            claimed.add(a)
            _rename_or_hold(rd, files, complete, defaults, cur["name"], name, L["color"], L["description"], f"§6.3 {cur['name']}→{name}",
                            ops, logs)
            for other in present[1:]:
                ops.append({"op": "skip", "name": by_low[other]["name"], "rule": "§6.4 rule 2", "log": "label-conflict"})
                logs.append("label-conflict")
                claimed.add(other)
            continue
        missing.append(L)
    for L in missing:
        ops.append({"op": "create", "name": L["name"], "color": L["color"], "description": L["description"], "rule": "§6.3 pass B"})
    # epic -> scope:epic extension, only if it exists
    if "epic" in by_low and "scope:epic" not in by_low:
        _rename_or_hold(rd, files, complete, defaults, by_low["epic"]["name"], "scope:epic", NAMESPACE_COLORS["scope"], "Scope: epic",
                        "§6.3 epic→scope:epic", ops, logs)
    return ops, sorted(set(logs))


def gh_lines(owner: str, repo: str, ops: list[dict]) -> list[str]:
    out = []
    r = f"{owner}/{repo}"
    for op in ops:
        if op["op"] in ("patch", "rename"):
            parts = ["gh", "label", "edit", op["name"]]
            if op.get("new_name"):
                parts += ["--name", op["new_name"]]
            if op.get("color"):
                parts += ["--color", op["color"]]
            if op.get("description"):
                parts += ["--description", op["description"]]
            out.append(" ".join(shlex.quote(p) for p in parts + ["-R", r]))
        elif op["op"] == "create":
            parts = ["gh", "label", "create", op["name"], "--color", op["color"], "--description", op["description"], "-R", r]
            out.append(" ".join(shlex.quote(p) for p in parts))
    return out
