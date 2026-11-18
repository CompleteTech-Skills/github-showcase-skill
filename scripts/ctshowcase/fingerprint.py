"""Input fingerprint and the docs/images/.showcase.json sidecar (spec A6.0). Stdlib only."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from tempfile import TemporaryDirectory

from . import STANDARD, __version__
from .config import LOCK, canonical

SIDECAR = ".showcase.json"
WRITE_SCRATCH_PREFIX = ".showcase-write-"
ART_RECORDS = {"banner": "banner.png", "card": "card.svg"}
ART_NAMES = frozenset(ART_RECORDS.values())
ART_EXEMPTIONS = ("exempt:no-card", "exempt:profile-readme", "exempt:placeholder-org")
_HELD_LOCKS = ContextVar("showcase_sidecar_locks", default=frozenset())


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


def inputs(meta: dict, repo_dir: str | Path | None, *, same_owner=None, metadata_path: str | Path | None = None) -> dict:
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
        type_ = detect(meta, RepoFacts(meta, rd, metadata_path=metadata_path), same_owner=same_owner)["type"]
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


def outputs_changed(data: dict, current: str, selected: set[str] | None = None, *, out_dir: Path | None = None) -> bool:
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
        art = out_dir / name if out_dir is not None and selected is not None and name in ART_NAMES else None
        if name in ART_NAMES and record.get("exempt") in ART_EXEMPTIONS and record.get("fingerprint") == current:
            if art is not None and (art.exists() or art.is_symlink()):
                return True
            continue
        digest = record.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return True
        if art is not None:
            try:
                if art.is_symlink() or _sha(art) != digest:
                    return True
            except OSError:
                return True
    return False


@contextmanager
def sidecar_lock(path: Path):
    """Serialize local readers that update an artifact group and its sidecar."""
    key = hashlib.sha256(os.fsencode(os.path.normcase(str(path.parent.resolve() / path.name)))).hexdigest()
    held = _HELD_LOCKS.get()
    if key in held:
        yield
        return
    # The Action and renderers can have different per-process scratch directories.
    directory = Path.home() / ".showcase-sidecar-locks"
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / key).open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + 90
            while True:
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("another generator still holds the showcase sidecar lock") from None
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        token = _HELD_LOCKS.set(held | {key})
        try:
            yield
        finally:
            _HELD_LOCKS.reset(token)


def replace_bytes(path: Path, data: bytes, *, private: bool = False, preserve_mode: bool = True) -> None:
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

    with TemporaryDirectory(dir=path.parent, prefix=WRITE_SCRATCH_PREFIX) as directory:
        source = Path(directory) / path.name
        source.write_bytes(data)
        if existing is not None and regular and preserve_mode:
            source.chmod(existing.st_mode & 0o777)
        elif private:
            source.chmod(0o600)
        source.replace(path)


def update_sidecar(data: dict, inp: dict, cfg_sha: str, name: str, record: dict, *, summarize: bool = True) -> dict:
    previous = data.get("fingerprint")
    outputs = {key: {"fingerprint": previous, **value} if isinstance(value, dict) else value
               for key, value in output_records(data).items()}
    current = fingerprint(inp, cfg_sha)
    outputs[name] = dict(record, fingerprint=current)
    updated = dict(data, schema=1, skill_version=__version__, standard=STANDARD, outputs=outputs)
    if summarize:
        updated.update(config_sha256=cfg_sha, inputs=inp, fingerprint=current)
    return updated


def sidecar_text(data: dict) -> str:
    return json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def has_staged_outputs(data: dict) -> bool:
    return any(isinstance(record, dict) and "staged_description" in record
               for record in output_records(data).values())


def write_sidecar(out_dir: Path, inp: dict, cfg_sha: str, name: str, record: dict, *, summarize: bool = True) -> Path:
    p = out_dir / SIDECAR
    with sidecar_lock(p):
        updated = update_sidecar(read_sidecar(out_dir), inp, cfg_sha, name, record, summarize=summarize)
        private = has_staged_outputs(updated)
        replace_bytes(p, sidecar_text(updated).encode("utf-8"), private=private, preserve_mode=not private)
    return p


def file_record(path: Path, **extra) -> dict:
    return bytes_record(path.read_bytes(), **extra)


def bytes_record(data: bytes, **extra) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), **extra}
