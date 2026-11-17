"""Input fingerprint and the docs/images/.showcase.json sidecar (spec A6.0). Stdlib only."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

from . import STANDARD, __version__
from .config import LOCK, canonical

SIDECAR = ".showcase.json"
ART_RECORDS = {"banner": "banner.png", "card": "card.svg"}
ART_NAMES = frozenset(ART_RECORDS.values())
ART_EXEMPTIONS = ("exempt:no-card", "exempt:profile-readme", "exempt:placeholder-org")


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
    if not p.is_symlink() and p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
    return {}


def output_records(data: dict) -> dict:
    outputs = data.get("outputs")
    return outputs if isinstance(outputs, dict) else {}


def outputs_changed(data: dict, current: str, selected: set[str] | None = None) -> bool:
    """Compare recorded outputs independently, falling back to the original cache for legacy records."""
    previous = data.get("fingerprint")
    if "outputs" in data and not isinstance(data["outputs"], dict):
        return True
    outputs = output_records(data)
    modern = any(isinstance(record, dict) and "fingerprint" in record for record in outputs.values())
    if selected is not None and modern:
        required_art = selected.intersection(ART_NAMES)
        if required_art.difference(outputs):
            return True
    records = {name: record for name, record in outputs.items() if selected is None or name in selected}
    if not records:
        return previous != current
    for name, record in records.items():
        if not isinstance(record, dict) or record.get("staged_description"):
            return True
        if record.get("fingerprint", previous) != current:
            return True
        if name in ART_NAMES and record.get("exempt") in ART_EXEMPTIONS and record.get("fingerprint") == current:
            continue
        digest = record.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return True
    return False


def replace_bytes(path: Path, data: bytes, *, private: bool = False) -> None:
    """Replace the directory entry instead of writing through an existing link."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    regular = existing is not None and stat.S_ISREG(existing.st_mode)
    if private and existing is not None:
        if not regular:
            raise OSError(f"staged output is not a regular file: {path}")
        # An atomic rename only needs directory permissions. Retain the existing file's write check.
        fd = os.open(path, os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0))
        os.close(fd)

    with TemporaryDirectory(dir=path.parent) as directory:
        source = Path(directory) / path.name
        source.write_bytes(data)
        if existing is not None and regular:
            source.chmod(existing.st_mode & 0o777)
        elif private:
            source.chmod(0o600)
        source.replace(path)


def write_sidecar(out_dir: Path, inp: dict, cfg_sha: str, name: str, record: dict, *, summarize: bool = True) -> Path:
    data = read_sidecar(out_dir)
    previous = data.get("fingerprint")
    outputs = {key: {"fingerprint": previous, **value} if isinstance(value, dict) else value
               for key, value in output_records(data).items()}
    current = fingerprint(inp, cfg_sha)
    outputs[name] = dict(record, fingerprint=current)
    data.update(schema=1, skill_version=__version__, standard=STANDARD, outputs=outputs)
    if summarize:
        data.update(config_sha256=cfg_sha, inputs=inp, fingerprint=current)
    p = out_dir / SIDECAR
    replace_bytes(p, (json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    return p


def file_record(path: Path, **extra) -> dict:
    return bytes_record(path.read_bytes(), **extra)


def bytes_record(data: bytes, **extra) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), **extra}
