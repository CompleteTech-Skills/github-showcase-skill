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


def emit_yml() -> str:
    return LABELS_YML.read_text(encoding="utf-8")


def standard_labels() -> list[dict]:
    import yaml
    return yaml.safe_load(emit_yml())


def _referenced(repo_dir: Path | None, name: str) -> str | None:
    """§6.4 rule 0: 'block' when referenced in workflows/release/labeler/renovate; 'rewrite' for forms/dependabot."""
    if repo_dir is None:
        return None
    pat = re.compile(rf"(?<![\w:-]){re.escape(name)}(?![\w:-])")
    found = None
    cands = list((repo_dir / ".github").rglob("*")) if (repo_dir / ".github").is_dir() else []
    if (repo_dir / "renovate.json").is_file():
        cands.append(repo_dir / "renovate.json")
    for p in cands:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not pat.search(text):
            continue
        rel = p.relative_to(repo_dir).as_posix()
        if rel.startswith(".github/workflows/") or rel.endswith(REF_FILES_BLOCK[1:]):
            return "block"
        found = "rewrite"
    return found


def plan(existing: list[dict], repo_dir: str | Path | None = None, references: bool = True) -> tuple[list[dict], list[str]]:
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
            ref = _referenced(rd, cur["name"]) if references else None
            claimed.add(a)
            if ref == "block":
                ops.append({"op": "skip", "name": cur["name"], "new_name": name, "rule": "§6.4 rule 0", "log": "label-referenced"})
                logs.append("label-referenced")
                continue
            op = {"op": "rename", "name": cur["name"], "new_name": name, "color": L["color"],
                  "description": L["description"], "rule": f"§6.3 {cur['name']}→{name}"}
            if ref == "rewrite":
                op["rewrite_references"] = True
            ops.append(op)
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
        ops.append({"op": "rename", "name": by_low["epic"]["name"], "new_name": "scope:epic", "color": NAMESPACE_COLORS["scope"],
                    "description": "Scope: epic", "rule": "§6.3 epic→scope:epic"})
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
