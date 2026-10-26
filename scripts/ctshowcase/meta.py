"""Normalized repository metadata (spec A4). Stdlib only; network only via read-only `gh api` GETs."""
from __future__ import annotations

import ast
import base64
import json
import re
import subprocess
from pathlib import Path

from .errors import NeedsInput, ShowcaseError, USAGE

FIELDS = ("owner", "repo", "description", "homepage", "topics", "fork", "archived", "visibility", "is_template",
          "default_branch", "language", "languages", "license", "stargazers_count", "created_at", "labels",
          "readme_head", "parent", "health_percentage", "has_issues", "has_wiki", "has_projects", "has_discussions",
          "delete_branch_on_merge", "files", "manifests", "homepage_status", "file_sizes")
# STANDARD §0 / CQ-16: estate commits never count as substantive (the bulk transfer and the run's own commits move
# pushed_at, so recency uses the newest default-branch commit whose message does not match this)
NON_SUBSTANTIVE = re.compile(r"ct-std-v1|showcase banner and card|\[skip ci\]")
MANIFEST_PATHS = ("pyproject.toml", "package.json", "requirements.txt", "setup.py", "setup.cfg", "manifest.json",
                  "SKILL.md", "skill-package.json", "CLAW_HUB_PUBLISHING.md", ".github/showcase.yml")


def _license(v):
    if isinstance(v, dict):
        v = v.get("spdx_id") or v.get("key")
    return v or None


def normalize(raw: dict) -> dict:
    """Accept the scratch-data format, raw `gh api repos/{o}/{r}` output, or showcase.py meta output."""
    if not isinstance(raw, dict):
        raise ShowcaseError("metadata must be a JSON object", log="usage")
    if raw.get("error") and not raw.get("description") and "visibility" not in raw and "private" not in raw:
        # a capture that failed (for example "GitHub access to this repository is not enabled"): never treat it
        # as an empty repository, which would scaffold a private-looking README and an empty tagline
        raise NeedsInput("metadata", f"metadata capture failed: {str(raw['error'])[:160]}")
    m: dict = {}
    owner = raw.get("owner")
    if isinstance(owner, dict):
        owner = owner.get("login")
    if not owner and raw.get("full_name"):
        owner = raw["full_name"].split("/")[0]
    m["owner"] = owner or "unknown"
    m["repo"] = raw.get("repo") or raw.get("name") or (raw.get("full_name", "/").split("/")[1]) or "unknown"
    m["description"] = raw.get("description") or ""
    m["homepage"] = raw.get("homepage") or ""
    m["topics"] = list(raw.get("topics") or [])
    m["fork"] = bool(raw.get("fork", False))
    m["archived"] = bool(raw.get("archived", False))
    vis = raw.get("visibility") or ("private" if raw.get("private") else ("public" if "private" in raw else "unknown"))
    m["visibility"] = vis
    m["is_template"] = bool(raw.get("is_template", False))
    m["default_branch"] = raw.get("default_branch") or "main"
    m["language"] = raw.get("language")
    m["languages"] = dict(raw.get("languages") or {})
    if not m["language"] and m["languages"]:
        m["language"] = max(m["languages"], key=m["languages"].get)
    m["license"] = _license(raw.get("license"))
    m["stargazers_count"] = raw.get("stargazers_count", 0) or 0
    m["created_at"] = raw.get("created_at")
    labels = raw.get("labels") or []
    if isinstance(labels, str):  # scratch captures store the list as its Python repr
        try:
            labels = ast.literal_eval(labels)
        except (ValueError, SyntaxError):
            labels = []
    m["labels"] = [{"name": lb.get("name"), "color": (lb.get("color") or "").lower(), "description": lb.get("description") or ""}
                   for lb in (labels if isinstance(labels, list) else []) if isinstance(lb, dict) and lb.get("name")]
    m["readme_head"] = raw.get("readme_head")
    parent = raw.get("parent")
    if isinstance(parent, dict):
        parent = {"full_name": parent.get("full_name"), "default_branch": parent.get("default_branch"),
                  "topics": parent.get("topics") or []}
    m["parent"] = parent
    for k in ("health_percentage", "has_issues", "has_wiki", "has_projects", "has_discussions",
              "delete_branch_on_merge", "homepage_status"):
        m[k] = raw.get(k)
    for k in ("files", "manifests", "file_sizes", "pushed_at", "last_substantive_commit", "last_substantive_sha"):
        if raw.get(k) is not None:
            m[k] = raw[k]
    if raw.get("also_in") is not None:  # registry cross-listing (§5.3a org membership topics)
        m["also_in"] = [str(x) for x in raw["also_in"] or []]
    if raw.get("ahead_by") is not None:  # forks: commits ahead of the parent (§7.4 G short form when 0)
        m["ahead_by"] = int(raw["ahead_by"])
    if raw.get("detected"):
        m["detected"] = raw["detected"]
    return m


def load_file(path: str | Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShowcaseError(f"cannot read metadata {path}: {exc}", log="usage", code=USAGE)
    return normalize(raw)


# -- repo checkout --------------------------------------------------------------------------------------
def from_repo_dir(repo_dir: str | Path) -> dict:
    d = Path(repo_dir)
    out: dict = {}
    try:
        url = subprocess.run(["git", "-C", str(d), "remote", "get-url", "origin"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        url = ""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        out["owner"], out["repo"] = m.group(1), m.group(2)
    lic = d / "LICENSE"
    if lic.is_file():
        head = lic.read_text(encoding="utf-8", errors="replace")[:400]
        if "MIT License" in head:
            out["license"] = "MIT"
        elif "GNU AFFERO GENERAL PUBLIC LICENSE" in head:
            out["license"] = "AGPL-3.0"
        elif "Apache License" in head:
            out["license"] = "Apache-2.0"
    return out


def merged(meta_path: str | None, repo_dir: str | None) -> dict:
    """--meta wins; --repo-dir fills the gaps; anything else is 'unknown'."""
    base = load_file(meta_path) if meta_path else {}
    if repo_dir:
        extra = from_repo_dir(repo_dir)
        for k, v in extra.items():
            if not base.get(k) or base.get(k) == "unknown":
                base[k] = v
    if not base:
        base = normalize({"owner": "unknown", "repo": Path(repo_dir or ".").resolve().name})
    elif "visibility" not in base:
        base = normalize(base)
    return base


# -- read-only GitHub (gh api GET only) ------------------------------------------------------------------
def _gh(path: str, paginate: bool = False, raw: bool = False):
    cmd = ["gh", "api", "-X", "GET", path]
    if paginate:
        cmd.append("--paginate")
    if raw:
        cmd[2:2] = ["-H", "Accept: application/vnd.github.raw"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShowcaseError(f"gh api failed: {exc}", log="needs-input:gh")
    if p.returncode != 0:
        return None
    if raw:
        return p.stdout
    out = p.stdout.strip()
    if paginate and out.startswith("[") and "][" in out:
        out = "[" + out[1:-1].replace("][", ",") + "]"
    try:
        return json.loads(out) if out else None
    except ValueError:
        return None


def last_substantive(commits) -> tuple[str, str] | None:
    """(date, sha) of the newest commit whose message does not match NON_SUBSTANTIVE (CQ-16), from a
    `GET repos/O/R/commits?sha=<default>` page (newest first); None when every listed commit is an estate commit."""
    for c in commits if isinstance(commits, list) else []:
        if not isinstance(c, dict):
            continue
        info = c.get("commit") or {}
        if NON_SUBSTANTIVE.search(str(info.get("message") or "")):
            continue
        when = (info.get("committer") or {}).get("date") or (info.get("author") or {}).get("date")
        if when:
            return str(when), str(c.get("sha") or "")
    return None


def from_gh(full_name: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
        raise ShowcaseError(f"invalid OWNER/REPO: {full_name}", log="usage")
    repo = _gh(f"repos/{full_name}")
    if not repo:
        raise ShowcaseError(f"cannot read repos/{full_name}", log="needs-input:gh")
    raw = dict(repo)
    raw["languages"] = _gh(f"repos/{full_name}/languages") or {}
    lic = repo.get("license") or {}
    raw["license"] = lic.get("spdx_id") if isinstance(lic, dict) else None
    raw["labels"] = _gh(f"repos/{full_name}/labels?per_page=100", paginate=True) or []
    readme = _gh(f"repos/{full_name}/readme")
    if isinstance(readme, dict) and readme.get("content"):
        text = base64.b64decode(readme["content"]).decode("utf-8", errors="replace")
        raw["readme_head"] = text[:4000]
    branch = repo.get("default_branch") or "main"
    hit = last_substantive(_gh(f"repos/{full_name}/commits?sha={branch}&per_page=100"))
    if hit:
        raw["last_substantive_commit"], raw["last_substantive_sha"] = hit
    tree = _gh(f"repos/{full_name}/git/trees/{branch}?recursive=1")
    if isinstance(tree, dict) and isinstance(tree.get("tree"), list):
        blobs = [t for t in tree["tree"] if t.get("type") == "blob"]
        raw["files"] = sorted(t["path"] for t in blobs)
        raw["file_sizes"] = {t["path"]: t.get("size", 0) for t in blobs}
        manifests = {}
        for p in MANIFEST_PATHS:
            if p in raw["files"]:
                txt = _gh(f"repos/{full_name}/contents/{p}?ref={branch}", raw=True)
                if txt is not None:
                    manifests[p] = txt
        raw["manifests"] = manifests
    parent = repo.get("parent") if isinstance(repo.get("parent"), dict) else None
    if repo.get("fork") and parent and parent.get("full_name"):
        pb = parent.get("default_branch") or "main"
        cmp = _gh(f"repos/{parent['full_name']}/compare/{pb}...{full_name.split('/')[0]}:{branch}")
        if isinstance(cmp, dict) and isinstance(cmp.get("ahead_by"), int):
            raw["ahead_by"] = cmp["ahead_by"]
    community = _gh(f"repos/{full_name}/community/profile")
    if isinstance(community, dict):
        raw["health_percentage"] = community.get("health_percentage")
    return normalize(raw)
