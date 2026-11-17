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


def tagline_forms(ctx) -> set[str]:
    """Every tagline block body `readme` writes for the live description, across all variants.

    The format comes only from readme.tagline_body, so a change there cannot drift from this check. Every variant is
    tried because `readme --variant X` may have written a README whose variant `doctor` does not auto-detect. G and H
    (fork and archive) write no tagline block at all (callout_only), so they only contribute the shared form.
    Callers must pass a non-empty description: tagline_body logs needs-input:description otherwise.
    """
    import copy

    from .readme import tagline_body

    forms = set()
    for variant in "ABCDEFGHIJ":
        proxy = copy.copy(ctx)
        proxy.det = dict(ctx.det, variant=variant)
        forms.add(tagline_body(proxy).strip())
    return forms


def tagline_blocks(text: str) -> list[str]:
    from .mdcode import find_blocks
    from .readme import MARK, normalize_text

    return [m.group(2).strip() for m in find_blocks(MARK, normalize_text(text)) if m.group(1) == "tagline"]


def tagline_drift(ctx, text: str) -> bool:
    """True when a managed tagline block differs from what `readme` would write for the live description.

    Only the managed tagline block is compared, never a matching sentence elsewhere in the README, and fenced code
    examples are ignored. An absent or unmanaged tagline is R7's concern, not drift. With an empty live description
    there is nothing to compare: readme keeps the authored tagline under needs-input:description, so it is not drift.
    """
    blocks = tagline_blocks(text)
    if not blocks or not str(ctx.meta.get("description") or "").strip():
        return False
    forms = tagline_forms(ctx)
    return any(block not in forms for block in blocks)
