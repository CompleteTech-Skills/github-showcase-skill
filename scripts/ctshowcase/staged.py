"""Explicit staged descriptions and per-output provenance; no GitHub writes."""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

from . import fingerprint as fp
from .errors import NeedsInput, ShowcaseError

SOCIAL_STAGING = ".showcase-staging"


def prepare(meta: dict, description: str | None) -> tuple[dict, dict | None]:
    """Keep the captured metadata untouched and fingerprint the proposed sentence separately."""
    if description is None:
        return meta, None
    text = description.strip()
    if not text or "\n" in text or "\r" in text:
        raise NeedsInput("description", "--description needs one non-empty line")
    if re.search(r"<!--\s*showcase:", text, re.I):
        raise NeedsInput("description", "--description may not contain managed README markers")
    captured = str(meta.get("description") or "")
    info = {"text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "live_description_sha256": hashlib.sha256(captured.encode("utf-8")).hexdigest()}
    return dict(meta, description=text), info


def check_social_path(path: Path, *, staged: bool, job: bool) -> None:
    in_staging = SOCIAL_STAGING in map(str.casefold, path.absolute().parent.parts)
    resolves_to_staging = SOCIAL_STAGING in map(str.casefold, path.resolve().parent.parts)
    if staged and not (in_staging and resolves_to_staging):
        raise ShowcaseError(f"a staged social preview needs an output inside {SOCIAL_STAGING}",
                            log="staged-description:path")
    if job and (in_staging or resolves_to_staging):
        raise ShowcaseError("a social preview upload job needs a live output path",
                            log="staged-description:upload")


def record_output(ctx, path: Path, record: dict, *, always: bool = False) -> Path | None:
    """Record staged output beside external art, or in a checkout's docs/images sidecar.

    A per-output record remains truthful when only one of several surfaces is refreshed.
    An ordinary refresh replaces an existing record, removing staged provenance.
    """
    info = getattr(ctx, "staged_description", None)
    path = Path(path).resolve()
    root = Path(ctx.repo_dir).resolve() if ctx.repo_dir else None
    if root is not None and path.is_relative_to(root):
        directory = root / "docs" / "images"
        if not directory.resolve().is_relative_to(root):
            raise ShowcaseError("the showcase sidecar must stay inside the target checkout", log="staged-description:path")
        relative = path.relative_to(root).as_posix()
        if path.parent == directory and path.name != "README.md":
            name = path.name
        elif (path.parent == root and path.name != "README.md") or path.parent == directory:
            name = "./" + relative
        else:
            name = relative
        summarize = path.parent == directory and name in fp.ART_NAMES and "exempt" not in record
    else:
        directory, name = path.parent, path.name
        summarize = True
    if not always and info is None and name not in fp.output_records(fp.read_sidecar(directory)):
        return None
    directory.mkdir(parents=True, exist_ok=True)
    if isinstance(ctx.meta.get("id"), int) and not isinstance(ctx.meta.get("id"), bool):
        record = dict(record, repository_id=ctx.meta["id"])
    if info is not None:
        record = dict(record, staged_description=info)
    return fp.write_sidecar(directory, fp.inputs(ctx.meta, ctx.repo_dir), ctx.brand.sha256, name,
                            record, summarize=summarize)


def tagline_forms(ctx) -> set[str]:
    """Every tagline block body `readme` writes for the live description, across all variants.

    The format comes only from readme.tagline_body, so a change there cannot drift from this check. Every variant is
    tried because `readme --variant X` may have written a README whose variant `doctor` does not auto-detect. Only
    Variant F uses a different tagline form.
    Callers must pass a non-empty description: tagline_body logs needs-input:description otherwise.
    """
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


def tagline_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _matches_staged_readme(ctx, blocks: list[str], path: Path | None) -> bool:
    if path is None or ctx.repo_dir is None:
        return False
    outputs = fp.output_records(fp.read_sidecar(ctx.repo_dir / "docs/images"))
    record = outputs.get("README.md")
    info = record.get("staged_description") if isinstance(record, dict) else None
    proposal = info.get("text") if isinstance(info, dict) else None
    if not isinstance(proposal, str) or not proposal.strip():
        return False
    digest = record.get("tagline_sha256")
    if digest is not None:
        return any(tagline_digest(block) == digest for block in blocks)
    if record.get("sha256") != fp.file_record(path)["sha256"]:
        return False
    staged = copy.copy(ctx)
    staged.meta = dict(ctx.meta, description=proposal)
    return bool(tagline_forms(staged).intersection(blocks))


def tagline_drift(ctx, text: str, path: Path | None = None) -> bool:
    """True when a managed tagline block differs from what `readme` would write for the live description.

    Only the managed tagline block is compared, never a matching sentence elsewhere in the README, and fenced code
    examples are ignored. With an empty live description, authored taglines are preserved. A managed tagline matching
    its recorded staged digest demonstrates drift even against an empty About.
    """
    blocks = tagline_blocks(text)
    if not blocks:
        return False
    if not str(ctx.meta.get("description") or "").strip():
        return _matches_staged_readme(ctx, blocks, path)
    forms = tagline_forms(ctx)
    return any(block not in forms for block in blocks)
