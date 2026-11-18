"""Explicit staged descriptions and per-output provenance; no GitHub writes."""
from __future__ import annotations

import copy
import hashlib
import os
import re
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path

from . import fingerprint as fp
from .errors import NeedsInput, ShowcaseError

SOCIAL_STAGING = ".showcase-staging"


def prepare(meta: dict, description: str | None) -> tuple[dict, dict | None]:
    """Keep the captured metadata untouched and fingerprint the proposed sentence separately."""
    if description is None:
        return meta, None
    text = description.strip()
    if not text or len(text.splitlines()) != 1:
        raise NeedsInput("description", "--description needs one non-empty line")
    if re.search(r"<!--\s*showcase:", text, re.I):
        raise NeedsInput("description", "--description may not contain managed README markers")
    captured = str(meta.get("description") or "")
    info = {"text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "live_description_sha256": hashlib.sha256(captured.encode("utf-8")).hexdigest()}
    return dict(meta, description=text), info


def check_social_path(path: Path, *, staged: bool, job: bool, checkout: Path | None = None) -> None:
    in_staging = _in_social_staging(Path(os.path.abspath(path)), checkout)
    resolves_to_staging = _in_social_staging(path.resolve(), checkout)
    if staged and not (in_staging and resolves_to_staging):
        raise ShowcaseError(f"a staged social preview needs an output inside {SOCIAL_STAGING}",
                            log="staged-description:path")
    if staged and _action_managed_path(path, checkout):
        raise ShowcaseError("staged social previews must stay outside Action-managed paths",
                            log="staged-description:path")
    if job and (in_staging or resolves_to_staging):
        raise ShowcaseError("a social preview upload job needs a live output path",
                            log="staged-description:upload")


def _checkout_slot(path: Path, root: Path) -> tuple[Path, str, bool]:
    directory = root / "docs" / "images"
    resolved_directory = directory.resolve()
    if not resolved_directory.is_relative_to(root):
        raise ShowcaseError("the showcase sidecar must stay inside the target checkout", log="staged-description:path")
    at_images = path.parent == resolved_directory
    relative = path.relative_to(root).as_posix()
    if at_images:
        name = "./docs/images/README.md" if path.name == "README.md" else path.name
    elif path.parent == root and path.name != "README.md":
        name = "./" + relative
    else:
        name = relative
    return directory, name, at_images and name in fp.ART_NAMES


def _inferred_checkout(path: Path) -> Path | None:
    enclosing = next((parent for parent in path.parents if (parent / ".git").exists()), None)
    if enclosing is not None:
        return enclosing
    images = next((parent for parent in path.parents
                   if parent.name == "images" and parent.parent.name == "docs"), None)
    return images.parent.parent if images else None


def _in_social_staging(path: Path, checkout: Path | None) -> bool:
    """A surrounding directory name does not reserve output inside a checkout."""
    roots = [_inferred_checkout(path)]
    if checkout is not None:
        roots.extend((Path(os.path.abspath(checkout)), checkout.resolve()))
    parent = path.parent
    scope = max((root for root in roots if root is not None and parent.is_relative_to(root)),
                key=lambda root: len(root.parts), default=None)
    relative = parent.relative_to(scope) if scope is not None else parent
    return SOCIAL_STAGING in map(str.casefold, relative.parts)


def _adjacent_name(path: Path, root: Path | None) -> str:
    """Avoid the root README key when an adjacent slot shares its sidecar."""
    if path.name == "README.md":
        enclosing = root if root is not None and path.is_relative_to(root) else _inferred_checkout(path)
        if enclosing is not None and (enclosing / "docs/images").resolve() == path.parent:
            return _checkout_slot(path, enclosing)[1]
    return path.name


def _output_slots(ctx, path: Path, *, adjacent: bool = False) -> tuple[tuple[Path, str, bool], ...]:
    path = Path(path).resolve()
    root = Path(ctx.repo_dir).resolve() if ctx.repo_dir else None
    enclosing = _inferred_checkout(path) if root is None and not adjacent else None
    scope = root if root is not None and path.is_relative_to(root) else enclosing
    parent = path.parent.relative_to(scope) if scope is not None else path.parent
    name = _adjacent_name(path, root or enclosing)
    if adjacent or SOCIAL_STAGING in map(str.casefold, parent.parts):
        return ((path.parent, name, False),)
    adjacent_slot = (path.parent, name, True)
    if root is not None:
        if not path.is_relative_to(root):
            return (adjacent_slot,)
        primary, alternate = _checkout_slot(path, root), adjacent_slot
    else:
        primary = adjacent_slot
        # Metadata-only rendering still shares any existing checkout provenance.
        # A synthetic or exported checkout can have the same layout without .git.
        if enclosing is None or not (enclosing / "docs/images").resolve().is_relative_to(enclosing):
            return (primary,)
        alternate = _checkout_slot(path, enclosing)
    if primary[0].resolve() == alternate[0].resolve():
        # Shared location, distinct identity: a nested README.md must never
        # take the key used for the checkout's root README.md.
        key = primary[1] if root is not None else alternate[1]
        return ((primary[0], key, primary[2]),)
    return primary, alternate


def _sidecars(ctx, paths, *, adjacent: bool) -> set[Path]:
    return {directory / fp.SIDECAR for path in paths
            for directory, _, _ in _output_slots(ctx, path, adjacent=adjacent)}


def _existing_sidecar(sidecar: Path, *, formatted: bool = False) -> dict:
    """An absent group can start fresh; an unreadable group cannot lose ownership."""
    try:
        mode = sidecar.lstat().st_mode
    except FileNotFoundError:
        return {}
    except OSError:
        raise ShowcaseError("existing showcase provenance is unreadable; restore it before rendering",
                            log="staged-description:provenance") from None
    if not stat.S_ISREG(mode):
        if formatted:
            raise ShowcaseError("formatted output must be a regular file", log="formatter-output")
        raise ShowcaseError("existing showcase provenance must be a regular file", log="staged-description:provenance")
    data = fp.read_sidecar(sidecar.parent)
    outputs = data.get("outputs")
    # Keep legacy sparse records supported, but match the Action's minimum
    # provenance contract rather than turning an invalid group into an empty one.
    if not isinstance(outputs, dict) or any(not isinstance(record, dict) for record in outputs.values()):
        raise ShowcaseError("existing showcase provenance is unreadable or invalid; restore it before rendering",
                            log="staged-description:provenance")
    return data


def _aliases(left: Path, right: Path) -> bool:
    return left == right or (left.exists() and right.exists() and left.samefile(right))


def check_capture(capture: Path | None, *destinations: Path) -> None:
    if capture is not None and any(_aliases(capture.resolve(), path.resolve()) for path in destinations):
        raise ShowcaseError("write destination overlaps the metadata capture", log="staged-description:path")


def _action_roots(path: Path, checkout: Path | None) -> set[Path]:
    roots = {(checkout or Path.cwd()).resolve()}
    for destination in (path.absolute(), path.resolve()):
        enclosing = next((parent for parent in destination.parents if (parent / ".git").exists()), None)
        if enclosing is not None:
            roots.add(enclosing.resolve())
    return roots


def _action_managed_path(path: Path, checkout: Path | None) -> bool:
    candidates = (path.absolute(), path.resolve())
    for root in _action_roots(path, checkout):
        images = root / "docs/images"
        markdown = tuple((root / name).resolve() for name in ("README.md", "CONTRIBUTING.md"))
        for destination in candidates:
            if (destination.is_relative_to(images) or destination.is_relative_to(images.resolve())
                    or any(_aliases(destination, file) for file in markdown)):
                return True
    return False


def check_auxiliary(capture: Path | None, checkout: Path | None, *paths: Path) -> None:
    check_capture(capture, *paths)
    for path in paths:
        if path.name.casefold() == fp.SIDECAR.casefold():
            raise ShowcaseError("staged reports must not replace showcase provenance", log="staged-description:path")
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink > 1)):
            raise ShowcaseError("staged reports must use an unlinked regular file", log="staged-description:path")
        if _live_social_output(path, checkout):
            raise ShowcaseError("staged reports must not replace a live social preview", log="staged-description:path")
        if path.is_file():
            with path.open("rb") as stream:
                signature = stream.read(8)
            if signature.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
                raise ShowcaseError("staged reports must not replace an existing image", log="staged-description:path")
        if _action_managed_path(path, checkout):
            raise ShowcaseError("staged reports must stay outside Action-managed paths", log="staged-description:path")


@contextmanager
def protected_auxiliary(capture: Path | None, checkout: Path | None, path: Path):
    """Revalidate the report destination while the neighboring renderer is excluded."""
    with fp.sidecar_lock(path.resolve().parent / fp.SIDECAR):
        check_auxiliary(capture, checkout, path)
        yield


def _marked_live_social(record: object) -> bool:
    return isinstance(record, dict) and record.get("live_social_preview") is True


def _live_social_output(path: Path, checkout: Path | None) -> bool:
    resolved = path.resolve()
    if _in_social_staging(resolved, checkout):
        return False
    if resolved.name.casefold() in {"social-preview.png", "social-preview.jpg"}:
        return True
    if (resolved.parent / fp.SIDECAR).is_symlink():
        return True
    records = fp.output_records(fp.read_sidecar(resolved.parent))
    names = {os.path.normcase(name) for name in (resolved.name, _adjacent_name(resolved, None))}
    if any(os.path.normcase(name) in names and _marked_live_social(record)
           for name, record in records.items()):
        return True
    if not resolved.is_file():
        return False
    with resolved.open("rb") as stream:
        signature = stream.read(8)
        if not signature.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
            return False
        # Older jobs have only a file path. Preserve images at the published
        # social-preview dimensions even when there is no adjacent record.
        from PIL import Image
        from .social import SH, SW

        stream.seek(0)
        try:
            with Image.open(stream, formats=("PNG", "JPEG")) as image:
                return image.size == (SW, SH)
        except (OSError, Image.DecompressionBombError):
            return False


def check_outputs(ctx, *paths: Path, auxiliary: tuple[Path, ...] = (), adjacent: bool = False,
                  format_root: Path | None = None) -> None:
    """Keep renderer outputs and their provenance paths distinct before any write."""
    sidecars = _sidecars(ctx, paths, adjacent=adjacent)
    if format_root is not None:
        from .formatting import target_relative

        for sidecar in sidecars:
            target_relative(format_root, sidecar)
    real_sidecars = [path.resolve() for path in sorted(sidecars)]
    if any(_aliases(path, other) for index, path in enumerate(real_sidecars) for other in real_sidecars[:index]):
        raise ShowcaseError("showcase sidecars must use distinct files", log="staged-description:path")
    metadata_path = getattr(getattr(ctx, "facts", None), "metadata_path", None)
    check_capture(metadata_path, *real_sidecars)
    staged = getattr(ctx, "staged_description", None) is not None
    if staged:
        capture = getattr(ctx, "meta_path", None)
        check_capture(capture, *paths, *real_sidecars)
        check_auxiliary(capture, ctx.repo_dir, *auxiliary)
        for path in (*paths, *sidecars):
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ShowcaseError("staged output must be a regular file", log="staged-description:path")
        if any(_live_social_output(path, ctx.repo_dir) or any(
            _marked_live_social(fp.output_records(fp.read_sidecar(directory)).get(name))
            for directory, name, _ in _output_slots(ctx, path, adjacent=adjacent)
            if directory != path.resolve().parent
        ) for path in paths):
            raise ShowcaseError("staged output must not replace a live social preview", log="staged-description:path")
    declared_root = Path(os.path.abspath(ctx.repo_dir)) if ctx.repo_dir else None
    root = declared_root.resolve() if declared_root else None
    real_paths = []
    for path in (*paths, *auxiliary):
        resolved = path.resolve()
        if (path.name.casefold() == fp.SIDECAR.casefold()
                or any(_aliases(resolved, sidecar) for sidecar in real_sidecars)):
            raise ShowcaseError("render output overlaps its showcase sidecar", log="staged-description:path")
        if root is not None and (path.is_symlink() or not resolved.is_relative_to(root)):
            lexical = Path(os.path.abspath(path))
            if (lexical.is_relative_to(declared_root) or lexical.is_relative_to(root)
                    or any(parent.resolve() == root for parent in lexical.parents)):
                raise ShowcaseError("render output must not write through a link outside the checkout",
                                    log="staged-description:path")
        if any(_aliases(resolved, other) for other in real_paths):
            raise ShowcaseError("render output paths must be distinct", log="staged-description:path")
        real_paths.append(resolved)
    for sidecar in sidecars:
        _existing_sidecar(sidecar, formatted=format_root is not None)


@contextmanager
def _lock_sidecars(sidecars: set[Path]):
    with ExitStack() as locks:
        for sidecar in sorted(sidecars):
            locks.enter_context(fp.sidecar_lock(sidecar))
        yield


@contextmanager
def lock_outputs(ctx, *paths: Path, adjacent: bool = False, auxiliary: tuple[Path, ...] = ()):
    sidecars = _sidecars(ctx, paths, adjacent=adjacent)
    if getattr(ctx, "staged_description", None) is not None:
        for path in paths:
            sidecars.add(path.resolve().parent / fp.SIDECAR)
            if _action_managed_path(path, ctx.repo_dir):
                sidecars.update(root / "docs" / "images" / fp.SIDECAR for root in _action_roots(path, ctx.repo_dir))
    sidecars.update(path.resolve().parent / fp.SIDECAR for path in auxiliary)
    with _lock_sidecars(sidecars):
        yield


def plan_sidecars(ctx, *entries: tuple[Path, dict, bool], adjacent: bool = False) -> dict[Path, dict]:
    """Prepare output records while retaining earlier records in the same locked group."""
    planned = {}
    info = getattr(ctx, "staged_description", None)
    inputs = None
    for path, record, always in entries:
        slots = []
        for directory, name, summarize in _output_slots(ctx, path, adjacent=adjacent):
            sidecar = directory / fp.SIDECAR
            data = planned.get(sidecar)
            if data is None:
                data = _existing_sidecar(sidecar)
            previous = fp.output_records(data).get(name)
            slots.append((sidecar, name, summarize, data, previous))
        if not always and info is None and all(previous is None for _, _, _, _, previous in slots):
            continue
        if any(_marked_live_social(previous) for _, _, _, _, previous in slots):
            record = dict(record, live_social_preview=True)
        if isinstance(ctx.meta.get("id"), int) and not isinstance(ctx.meta.get("id"), bool):
            record = dict(record, repository_id=ctx.meta["id"])
        if info is not None:
            record = dict(record, staged_description=info)
        if inputs is None:
            metadata_path = getattr(getattr(ctx, "facts", None), "metadata_path", None)
            inputs = fp.inputs(ctx.meta, ctx.repo_dir, same_owner=lambda a, b: ctx.brand.resolver().same(a, b),
                               metadata_path=metadata_path)
        for index, (sidecar, name, summarize, data, previous) in enumerate(slots):
            if previous is None and (index or (not always and info is None)):
                continue
            current = fp.update_sidecar(data, inputs, ctx.brand.sha256, name, record,
                                        summarize=not index and summarize and info is None and "exempt" not in record)
            if index:
                current["outputs"] = {**fp.output_records(data), name: current["outputs"][name]}
            planned[sidecar] = current
    return planned


def record_output(ctx, path: Path, record: dict, *, always: bool = False,
                  adjacent: bool = False) -> Path | None:
    """Record a generated output and preserve provenance for untouched surfaces."""
    with _lock_sidecars(_sidecars(ctx, (path,), adjacent=adjacent)):
        planned = plan_sidecars(ctx, (path, record, always), adjacent=adjacent)
        for sidecar, data in planned.items():
            private = fp.has_staged_outputs(data)
            fp.replace_bytes(sidecar, fp.sidecar_text(data).encode("utf-8"), private=private, preserve_mode=not private)
    return next(iter(planned), None)


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

    source = normalize_text(text)
    return [m.group(2).strip("\n") for m in find_blocks(MARK, source) if m.group(1) == "tagline"]


def tagline_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _readme_record(ctx, path: Path | None) -> dict:
    if path is None or ctx.repo_dir is None:
        return {}
    outputs = fp.output_records(fp.read_sidecar(ctx.repo_dir / "docs/images"))
    record = outputs.get("README.md")
    return record if isinstance(record, dict) else {}


def _recorded_tagline_digests(record: dict) -> set[str]:
    multiple = record.get("tagline_sha256s")
    digests = {value for value in multiple if isinstance(value, str)} if isinstance(multiple, list) else set()
    if isinstance(single := record.get("tagline_sha256"), str):
        digests.add(single)
    return digests


def recorded_tagline(ctx, body: str) -> bool:
    """Recognize an exact formatter-produced body with description provenance."""
    checkout = ctx.repo_dir
    if checkout is None:
        return False
    record = _readme_record(ctx, checkout / "README.md")
    # Formatter-added separator lines are harmless, but indentation and trailing
    # spaces can change Markdown and must never be inferred from a legacy digest.
    if tagline_digest(body.strip("\r\n")) not in _recorded_tagline_digests(record):
        return False
    proposal = record.get("staged_description")
    if isinstance(proposal, dict):
        text = proposal.get("text")
        return isinstance(text, str) and tagline_digest(text) == proposal.get("sha256")
    description_digest = record.get("description_sha256")
    return isinstance(description_digest, str) and re.fullmatch(r"[0-9a-f]{64}", description_digest) is not None


def _matches_staged_readme(ctx, blocks: list[str], path: Path | None, record: dict) -> bool:
    info = record.get("staged_description")
    proposal = info.get("text") if isinstance(info, dict) else None
    if not isinstance(proposal, str) or not proposal.strip():
        return False
    digests = _recorded_tagline_digests(record)
    if digests:
        return any(tagline_digest(block) in digests for block in blocks)
    if path is None or record.get("sha256") != fp.file_record(path)["sha256"]:
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
    captured = str(ctx.meta.get("description") or "")
    if not captured.strip():
        return _matches_staged_readme(ctx, blocks, path, _readme_record(ctx, path))
    different = set(blocks).difference(tagline_forms(ctx))
    if not different:
        return False
    # Formatter output can reflow a generated tagline. The recorded digest
    # applies only to the description that produced that formatter input.
    record = _readme_record(ctx, path)
    staged = record.get("staged_description")
    rendered_description = staged.get("sha256") if isinstance(staged, dict) else record.get("description_sha256")
    return (rendered_description != tagline_digest(captured.strip())
            or not {tagline_digest(block) for block in different}.issubset(_recorded_tagline_digests(record)))
