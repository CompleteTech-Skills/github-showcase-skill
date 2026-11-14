"""Explicit staged descriptions and per-output provenance; no GitHub writes."""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import fingerprint as fp
from .errors import NeedsInput


def prepare(meta: dict, description: str | None) -> tuple[dict, dict | None]:
    """Keep the captured metadata untouched and fingerprint the proposed sentence separately."""
    if description is None:
        return meta, None
    text = description.strip()
    if not text or "\n" in text or "\r" in text:
        raise NeedsInput("description", "--description needs one non-empty line")
    captured = str(meta.get("description") or "")
    info = {"text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "live_description_sha256": hashlib.sha256(captured.encode("utf-8")).hexdigest()}
    return dict(meta, description=text), info


def record_output(ctx, path: Path, record: dict) -> Path | None:
    """Record staged output beside external art, or in a checkout's docs/images sidecar.

    A per-output record remains truthful when only one of several surfaces is refreshed.
    An ordinary refresh replaces an existing record, removing staged provenance.
    """
    info = getattr(ctx, "staged_description", None)
    path = Path(path).resolve()
    root = Path(ctx.repo_dir).resolve() if ctx.repo_dir else None
    if root is not None and path.is_relative_to(root):
        directory = root / "docs" / "images"
        name = path.name if path.parent == directory else path.relative_to(root).as_posix()
    else:
        directory, name = path.parent, path.name
    if info is None and name not in (fp.read_sidecar(directory).get("outputs") or {}):
        return None
    directory.mkdir(parents=True, exist_ok=True)
    if isinstance(ctx.meta.get("id"), int) and not isinstance(ctx.meta.get("id"), bool):
        record = dict(record, repository_id=ctx.meta["id"])
    if info is not None:
        record = dict(record, staged_description=info)
    return fp.write_sidecar(directory, fp.inputs(ctx.meta, ctx.repo_dir), ctx.brand.sha256, name,
                            record)


def tagline_drift(ctx, text: str) -> bool:
    """Compare the actual managed tagline, never a matching sentence elsewhere in the README."""
    from .mdcode import find_blocks
    from .readme import MARK, normalize_text

    text = normalize_text(text)
    blocks = [m.group(2).strip() for m in find_blocks(MARK, text) if m.group(1) == "tagline"]
    if not blocks:
        return False  # an unmanaged/missing tagline is covered by R7
    description = str(ctx.meta.get("description") or "").strip()
    expected = {f"**{description}**", f"<b>{description}</b>",
                f'<p align="center"><b>{description}</b></p>'} if description else {""}
    return any(block not in expected for block in blocks)
