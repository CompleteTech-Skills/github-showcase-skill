"""Input fingerprint and the docs/images/.showcase.json sidecar (spec A6.0). Stdlib only."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import STANDARD, __version__
from .config import LOCK, canonical

SIDECAR = ".showcase.json"


def config_sha256(brand=None) -> str:
    if brand is not None:
        return brand.sha256
    return hashlib.sha256(canonical(json.loads(LOCK.read_text(encoding="utf-8"))).encode()).hexdigest()


def _sha(p: Path | None) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p and p.is_file() else None


def override_icon(text: str) -> str | None:
    """The override's `icon:` path, read as the renderer reads it (YAML via config.load_repo_override). Without PyYAML
    (the stdlib-only Action step) a top-level `icon:` line is read with its quotes and trailing `# comment` removed."""
    try:
        import yaml
    except ImportError:  # pragma: no cover - the Action's fingerprint step runs before pip install
        yaml = None
    if yaml is not None:
        try:
            obj = yaml.safe_load(text)
        except yaml.YAMLError:
            return None
        v = obj.get("icon") if isinstance(obj, dict) else None
        return v.strip() if isinstance(v, str) and v.strip() else None
    for line in text.splitlines():
        m = re.match(r"""^(?:icon|"icon"|'icon')\s*:\s*(?:"([^"]*)"|'([^']*)'|([^#\s][^#]*?))?\s*(?:#.*)?$""", line)
        if m:
            v = next((g for g in m.groups() if g is not None), "").strip()
            return v if v and v not in ("null", "~") else None
    return None


def inputs(meta: dict, repo_dir: str | Path | None) -> dict:
    rd = Path(repo_dir) if repo_dir else None
    override = None
    icon = None
    if rd is not None:
        for n in (".github/showcase.yml", ".github/showcase.yaml"):
            if (rd / n).is_file():
                override = rd / n
                break
        icon = rd / "assets" / "icon.png"
        if override is not None:
            v = override_icon(override.read_text(encoding="utf-8"))
            if v:
                icon = rd / v
    try:  # the detected type picks the README variant and the eyebrow: a new type (code landed) regenerates
        from .detect import detect
        from .facts import RepoFacts
        type_ = detect(meta, RepoFacts(meta, rd))["type"]
    except Exception:  # noqa: BLE001 - the fingerprint must never fail the stdlib-only Action step
        type_ = None
    return {"owner": meta.get("owner"), "repo": meta.get("repo"), "type": type_, "description": meta.get("description") or "",
            "topics": sorted(meta.get("topics") or []), "visibility": meta.get("visibility"),
            "license": meta.get("license"), "language": meta.get("language"),
            "icon_sha256": _sha(icon), "override_sha256": _sha(override)}


def fingerprint(inp: dict, cfg_sha: str) -> str:
    return hashlib.sha256(canonical({"inputs": inp, "skill_version": __version__, "config_sha256": cfg_sha}).encode()).hexdigest()


def read_sidecar(out_dir: Path) -> dict:
    p = out_dir / SIDECAR
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def write_sidecar(out_dir: Path, inp: dict, cfg_sha: str, name: str, record: dict) -> Path:
    data = read_sidecar(out_dir)
    outputs = dict(data.get("outputs") or {})
    outputs[name] = record
    data = {"schema": 1, "skill_version": __version__, "standard": STANDARD, "config_sha256": cfg_sha, "inputs": inp,
            "fingerprint": fingerprint(inp, cfg_sha), "outputs": outputs}
    p = out_dir / SIDECAR
    p.write_text(json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def file_record(path: Path, **extra) -> dict:
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), **extra}
