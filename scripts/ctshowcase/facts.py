"""Repository facts from a checkout (--repo-dir) or from metadata captured by `meta` (files, manifests).

Facts are never invented: when neither source knows something, the answer is None ("unknown").
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    tomllib = None

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".showcase-cache"}
MANIFESTS = ("pyproject.toml", "package.json", "requirements.txt", "setup.py", "setup.cfg", "requirements-dev.txt")
LOCKFILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Pipfile.lock", "bun.lockb")
_REQ = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _req_name(line: str) -> str | None:
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", "git+", "http")):
        return None
    m = _REQ.match(line)
    return m.group(1).lower() if m else None


class RepoFacts:
    def __init__(self, meta: dict | None = None, repo_dir: str | Path | None = None):
        self.meta = meta or {}
        self.dir = Path(repo_dir) if repo_dir else None
        self._files: list[str] | None = None

    # -- raw access ---------------------------------------------------------------------------------
    @property
    def known(self) -> bool:
        """True when the file tree is known (checkout or captured tree)."""
        return self.dir is not None or isinstance(self.meta.get("files"), list)

    @property
    def files(self) -> list[str]:
        if self._files is None:
            if self.dir is not None:
                out = []
                for base, dirs, names in os.walk(self.dir):
                    dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                    rel = Path(base).relative_to(self.dir)
                    for n in sorted(names):
                        out.append((rel / n).as_posix() if str(rel) != "." else n)
                self._files = out
            else:
                self._files = list(self.meta.get("files") or [])
        return self._files

    def read(self, rel: str) -> str | None:
        if self.dir is not None:
            p = self.dir / rel
            if p.is_file():
                try:
                    return p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return None
            return None
        manifests = self.meta.get("manifests") or {}
        return manifests.get(rel)

    def exists(self, rel: str) -> bool:
        if self.dir is not None:
            return (self.dir / rel).exists()
        return rel in set(self.files) or any(f.startswith(rel.rstrip("/") + "/") for f in self.files)

    def root_files(self) -> list[str]:
        return [f for f in self.files if "/" not in f]

    # -- manifests ------------------------------------------------------------------------------------
    def pyproject(self) -> dict:
        t = self.read("pyproject.toml")
        if not t or tomllib is None:
            return {}
        try:
            return tomllib.loads(t)
        except Exception:
            return {}

    def package_json(self) -> dict:
        t = self.read("package.json")
        if not t:
            return {}
        try:
            d = json.loads(t)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}

    def requirements(self) -> list[str]:
        names = []
        for f in self.root_files() or [m for m in (self.meta.get("manifests") or {})]:
            if re.fullmatch(r"requirements[^/]*\.txt", f):
                for line in (self.read(f) or "").splitlines():
                    n = _req_name(line)
                    if n:
                        names.append(n)
        return names

    def dependencies(self) -> list[str]:
        """Dependency names in manifest order (§5.4 'dependency' definition)."""
        out: list[str] = []
        out += self.requirements()
        pp = self.pyproject()
        for spec in (pp.get("project", {}) or {}).get("dependencies", []) or []:
            n = _req_name(str(spec))
            if n:
                out.append(n)
        poetry = ((pp.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
        out += [k.lower() for k in poetry if k.lower() != "python"]
        pj = self.package_json()
        for sect in ("dependencies", "devDependencies"):
            out += [k.lower() for k in (pj.get(sect) or {})]
        seen, res = set(), []
        for n in out:
            if n not in seen:
                seen.add(n)
                res.append(n)
        return res

    def runtime_dependencies(self) -> list[str] | None:
        """Runtime deps only (no dev); None when no manifest is known at all."""
        if not self.known:
            return None
        out: list[str] = []
        for f in self.root_files():
            if f == "requirements.txt":
                out += [n for n in (_req_name(x) for x in (self.read(f) or "").splitlines()) if n]
        pp = self.pyproject()
        out += [n for n in (_req_name(str(s)) for s in (pp.get("project", {}) or {}).get("dependencies", []) or []) if n]
        out += list((self.package_json().get("dependencies") or {}).keys())
        return out

    def has_lockfile(self) -> bool:
        return any(f in LOCKFILES for f in self.root_files())

    def requires_python(self) -> str | None:
        pp = self.pyproject()
        rp = (pp.get("project", {}) or {}).get("requires-python")
        if rp:
            m = re.search(r">=\s*(\d+\.\d+)", rp)
            return m.group(1) if m else None
        return None

    def engines_node(self) -> str | None:
        e = (self.package_json().get("engines") or {}).get("node")
        if e:
            m = re.search(r"(\d+)", str(e))
            return m.group(1) if m else None
        return None

    def has_scripts(self) -> bool:
        pp = self.pyproject()
        if (pp.get("project", {}) or {}).get("scripts"):
            return True
        setup = (self.read("setup.py") or "") + (self.read("setup.cfg") or "")
        if "console_scripts" in setup:
            return True
        return bool(self.package_json().get("bin"))

    def is_library(self) -> bool:
        if "pyproject.toml" in self.root_files() or "setup.py" in self.root_files():
            return True
        pj = self.package_json()
        return bool(pj.get("main") or pj.get("exports"))

    # -- README -----------------------------------------------------------------------------------------
    def readme(self) -> str | None:
        if self.dir is not None:
            for n in ("README.md", "readme.md", "Readme.md"):
                if (self.dir / n).is_file():
                    return (self.dir / n).read_text(encoding="utf-8", errors="replace")
            return None
        return self.meta.get("readme_head")

    def h1(self) -> str | None:
        text = self.readme() or ""
        in_code = False
        for line in text.splitlines():
            if line.startswith("```"):
                in_code = not in_code
            if not in_code and re.match(r"^# \S", line):
                return line[2:].strip()
        m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S | re.I)
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else None
