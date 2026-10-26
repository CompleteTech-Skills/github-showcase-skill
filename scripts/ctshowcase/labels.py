"""STANDARD §6 label standard: emit labels.yml, plan pass A/B, print gh commands (spec A6.9).

Never `--force`, never a delete, and never a GitHub write: plans leave as `gh` argv and scripts/writer.py jobs.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from . import REFERENCES

LABELS_YML = REFERENCES / "standard" / "labels.yml"
NAMESPACE_COLORS = {"area": "5319e7", "scope": "bfdadc"}
REF_FILES_BLOCK = (".github/workflows/", "release.yml", "labeler.yml", "renovate.json")
NEEDS_CHECKOUT = "needs-input:label-references"


def emit_yml() -> str:
    return LABELS_YML.read_text(encoding="utf-8")


def standard_labels() -> list[dict]:
    import yaml
    return yaml.safe_load(emit_yml())


_LABELS_KEY = re.compile(r"^(\s*(?:-\s+)?)labels\s*:(.*)$")


def _uncomment(text: str) -> str:
    return re.sub(r"\s+#.*$", "", text)


def _label_entries(rel: str, text: str) -> list[tuple[int, str]]:
    """The (line number, line) pairs that assign labels in a file rule 0 rewrites: the `labels:` key of an issue form
    (`.github/ISSUE_TEMPLATE/*.yml`), the `labels:` key in the front matter of a Markdown issue template, and the
    `labels:` entries of `.github/dependabot.yml`, each with its inline value or the `- item` lines under it. Prose
    (form descriptions and field labels, the PR template, CONTRIBUTING.md) names no label and is never returned."""
    low = rel.lower()
    in_templates = low.startswith(".github/issue_template/") and low.count("/") == 2
    if in_templates and low.endswith((".yml", ".yaml")) or low in (".github/dependabot.yml", ".github/dependabot.yaml"):
        lines = list(enumerate(text.splitlines(), 1))
    elif in_templates and low.endswith(".md"):
        raw = text.splitlines()
        end = next((i for i in range(1, len(raw)) if raw[i].strip() == "---"), None) if raw and raw[0].strip() == "---" else None
        lines = list(enumerate(raw[1:end], 2)) if end else []
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


# the paths rule 0 can act on, as glob patterns: a capture with none of them proves no rename needs a checkout
REFERENCE_PATTERNS = (".github/ISSUE_TEMPLATE/*", ".github/dependabot.yml", ".github/dependabot.yaml",
                      ".github/workflows/*", ".github/**/release.yml", ".github/**/labeler.yml", ".github/**/renovate.json",
                      "renovate.json")


def reference_file(rel: str) -> bool:
    """True for a path `_referenced` acts on (a block or a rewrite), case-insensitively so a capture errs toward a hold:
    `.github/workflows/*`, any `.github/**` file ending in release.yml, labeler.yml or renovate.json, the root
    renovate.json, an issue form or Markdown template directly in `.github/ISSUE_TEMPLATE/`, and dependabot.yml."""
    low = rel.lower().lstrip("/")
    if low == "renovate.json":
        return True
    if not low.startswith(".github/"):
        return False
    if low.startswith(".github/workflows/") or low.endswith(REF_FILES_BLOCK[1:]):
        return True
    if low.startswith(".github/issue_template/") and low.count("/") == 2 and low.endswith((".yml", ".yaml", ".md")):
        return True
    return low in (".github/dependabot.yml", ".github/dependabot.yaml")


def reference_files(files) -> tuple[list[str], bool]:
    """(reference-bearing paths the capture lists, complete) from a metadata `files` value: `meta --from-gh`'s complete
    list of blob paths, or the fixtures' partial {path: value} map. Only a complete list with none of them proves that
    rule 0 has nothing to find; a map, a missing capture or a listed reference file needs a checkout."""
    from .org import _captured_files
    cap, complete = _captured_files({"files": files})
    found = sorted(p for p, v in cap.items() if v is not None and v is not False and reference_file(p))
    return found, complete


def _referenced(repo_dir: Path | None, name: str) -> tuple[str | None, list[dict]]:
    """§6.4 rule 0: ('block', hits) when referenced in workflows/release/labeler/renovate; ('rewrite', hits) when an
    issue form's or template's `labels:` key or a dependabot.yml `labels:` entry assigns it, where hits are the
    {path, line, text} the estate/polish PR rewrites before the rename. A mention in prose is not a reference."""
    if repo_dir is None:
        return None, []
    pat = re.compile(rf"(?<![\w:-]){re.escape(name)}(?![\w:-])")
    key_pat = re.compile(pat.pattern, re.IGNORECASE)  # GitHub matches a form's label names case-insensitively
    hits: list[dict] = []
    cands = sorted((repo_dir / ".github").rglob("*")) if (repo_dir / ".github").is_dir() else []
    if (repo_dir / "renovate.json").is_file():
        cands.append(repo_dir / "renovate.json")
    for p in cands:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = p.relative_to(repo_dir).as_posix()
        if (rel.startswith(".github/workflows/") or rel.endswith(REF_FILES_BLOCK[1:])) and pat.search(text):
            return "block", [{"path": rel}]
        hits += [{"path": rel, "line": n, "text": ln.strip()} for n, ln in _label_entries(rel, text)
                 if key_pat.search(_uncomment(ln))]
    return ("rewrite" if hits else None), hits


def _rename_or_hold(rd: Path | None, files, cur: str, new: str, color: str, description: str, rule: str,
                    ops: list[dict], logs: list[str]) -> None:
    """Rule 0 for one rename. A form or dependabot.yml reference is a content change for the estate/polish PR, not a
    label job: the rename is held (op skip, log label-rewrite-first, with the lines to rewrite) until a re-plan of the
    merged checkout no longer finds them, so no plan ever emits a rename that leaves a form naming a missing label.
    Without a checkout the check fails closed: the rename leaves only when the captured file list proves no file rule 0
    reads exists; otherwise it is held (needs-input:label-references) with the files a checkout must be read for."""
    if rd is None:
        found, complete = reference_files(files)
        if found or not complete:  # an unlisted path of a partial (or missing) capture may still exist
            ops.append({"op": "skip", "name": cur, "new_name": new, "rule": "§6.4 rule 0", "log": NEEDS_CHECKOUT,
                        "check_files": found if complete else found + list(REFERENCE_PATTERNS)})
            logs.append(NEEDS_CHECKOUT)
            return
        ref, hits = None, []
    else:
        ref, hits = _referenced(rd, cur)
    if ref == "block":
        ops.append({"op": "skip", "name": cur, "new_name": new, "rule": "§6.4 rule 0", "log": "label-referenced"})
        logs.append("label-referenced")
    elif ref == "rewrite":
        ops.append({"op": "skip", "name": cur, "new_name": new, "rule": "§6.4 rule 0", "log": "label-rewrite-first",
                    "rewrite_references": hits})
        logs.append("label-rewrite-first")
    else:
        ops.append({"op": "rename", "name": cur, "new_name": new, "color": color, "description": description, "rule": rule})


def plan(existing: list[dict], repo_dir: str | Path | None = None, files=None) -> tuple[list[dict], list[str]]:
    """§6.3 passes A and B against the live labels. Every rename passes §6.4 rule 0: scanned in `repo_dir` when a
    checkout is given, else checked against `files` (the metadata's captured file list) and held when unproven."""
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
            _rename_or_hold(rd, files, cur["name"], name, L["color"], L["description"], f"§6.3 {cur['name']}→{name}",
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
        _rename_or_hold(rd, files, by_low["epic"]["name"], "scope:epic", NAMESPACE_COLORS["scope"], "Scope: epic",
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
