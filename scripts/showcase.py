#!/usr/bin/env python3
"""CompleteTech GitHub showcase CLI: generate banners, cards, tiles, intros and footers, check a repository against
the CompleteTech estate standard (ct-std-v1), and plan org, GitHub Project, Enterprise and content work. Read-only
toward GitHub: GitHub changes leave as JSON plans, `gh` argv and scripts/writer.py jobs; see SKILL.md.

Usage: python3 scripts/showcase.py [--config PATH] [--repo-dir DIR] [--meta FILE] [--format json|text] [--quiet]
                                   <command> [options]

Command groups: org {profile,about,pins,labels,health,doctor} · project {capture-query,normalize,copy-plan,readme,lint,
estate-plan} · enterprise {snapshot-query,discover,snapshot,doctor,seat-check,diff,plan} · content {social,icon,links,
linguist,actions,images,sidebar}. `content social` is the contract name for the social preview (`social-preview` is a
hidden, deprecated alias); `org-banner` and `org-tile` are top-level generators. `account-chart {capture-query,capture,
render}` maps one account's repositories, enterprises and organizations (Mermaid source, dark SVG, HD PNG).
`provenance {check,stamp,star}` (decision 25, a proposal) tells before a run whether a target was already showcased
and records the run.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from contextlib import nullcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctshowcase import STANDARD, __version__  # noqa: E402
from ctshowcase.errors import CHECK_FAILED, NEEDS_INPUT, OK, USAGE, ConfigError, ShowcaseError  # noqa: E402

GENERATORS = {"banner", "card", "org-tile", "intro", "contact-sheet", "social-preview", "org-banner"}
# commands whose default output is text (`--format json` for the JSON object): the generators and `provenance`
TEXT_DEFAULT = GENERATORS | {"provenance"}
# `enterprise` contract names (org/project/enterprise/content groups) that map onto the original action names
ENTERPRISE_ALIASES = {"snapshot_query": "snapshot-query"}
ENTERPRISE_ACTIONS = ("snapshot-query", "discover", "snapshot", "doctor", "seat-check", "diff", "plan")


# ---------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------
def emit(args, obj: dict) -> None:
    if args.quiet:
        return
    if args.format == "text":
        res = obj.get("result")
        head = f"{obj.get('command')}: {res}"
        if obj.get("owner"):
            head += f" ({obj['owner']}" + (f"/{obj['repo']})" if obj.get("repo") else ")")
        print(head)
        for k in ("out", "outputs", "text", "proposed", "logs", "staged_description"):
            if obj.get(k):
                print(f"  {k}: {obj[k]}")
        return
    print(json.dumps(obj, ensure_ascii=False, sort_keys=False))


def _origin_slug(rd: Path) -> str | None:
    """owner/repo of the checkout's GitHub origin when rd is itself a git checkout, else None."""
    if not (rd / ".git").exists():
        return None
    from ctshowcase.meta import from_repo_dir
    m = from_repo_dir(rd)
    return f"{m['owner']}/{m['repo']}" if m.get("owner") and m.get("repo") else None


def _same_slug(args, a: str, b: str) -> bool:
    """Two OWNER/REPO slugs name the same repository: the owners through the shared org resolver (any case, any former
    login, CQ-03), the names case-insensitively. A genuinely different repository never matches."""
    ao, _, ar = a.partition("/")
    bo, _, br = b.partition("/")
    if ar.lower() != br.lower():
        return False
    if ao.lower() == bo.lower():
        return True
    try:
        return brand(args, prefer_lock=True).resolver().same(ao, bo)
    except ShowcaseError:  # no brand data: plain comparison
        return False


def repo_dir(args) -> Path | None:
    """The target checkout. A missing --repo-dir is a usage error (exit 2). With --meta, the checkout must be the
    repository the metadata describes: run from inside it, or pass --repo-dir DIR / --no-repo-dir explicitly; a checkout
    whose origin names another repository is refused, so a command never writes into the wrong one (review A4)."""
    if args.no_repo_dir:
        return None
    if getattr(args, "_rd_checked", None) is not None:
        return args._rd_checked
    explicit = args.repo_dir is not None
    rd = Path(args.repo_dir if explicit else ".")
    if not rd.is_dir():
        raise ShowcaseError(f"--repo-dir {rd} does not exist", log="usage")
    if args.meta:
        from ctshowcase.meta import load_file
        m = load_file(args.meta)
        want = f"{m.get('owner')}/{m.get('repo')}"
        have = _origin_slug(rd)
        if have and not _same_slug(args, want, have):
            import shlex
            raise ShowcaseError(f"metadata describes {want} but {rd.resolve()} is a checkout of {have}; pass the right "
                                "--repo-dir, or --no-repo-dir to use the metadata alone. If this is a verified rename, "
                                f"update this checkout locally with git -C {shlex.quote(str(rd))} remote set-url origin "
                                f"https://github.com/{want}.git; the skill never changes remotes", log="usage")
        if not explicit and have is None:
            raise ShowcaseError(f"--meta {want} without --repo-dir: run from inside that repository's checkout, or pass "
                                "--repo-dir DIR or --no-repo-dir", log="usage")
    args._rd_checked = rd
    return rd


def default_out(args, rel: str) -> Path:
    """Default output path, resolved against the target checkout (never the current directory)."""
    rd = repo_dir(args)
    if rd is None:
        raise ShowcaseError(f"pass --out with --no-repo-dir (the default {rel} is inside the target checkout)", log="usage")
    return rd / rel


def brand(args, prefer_lock=False):
    from ctshowcase.config import load_brand
    return load_brand(args.config, prefer_lock=prefer_lock)


def context(args, b=None, *, for_coverage=False):
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import merged
    b = b or brand(args)
    rd = repo_dir(args)
    meta = merged(args.meta, str(rd) if rd else None)
    from ctshowcase.staged import prepare
    proposal_meta, staged = prepare(meta, getattr(args, "description", None))
    ctx = RepoContext(b, meta if args.command == "readme" else proposal_meta, rd,
                      type_override=getattr(args, "type_override", None), for_coverage=for_coverage,
                      metadata_path=args.meta)
    if staged is not None or getattr(args, "format_generated", False):
        ctx.meta_path = Path(args.meta).resolve() if args.meta else None
    if getattr(args, "format_generated", False):
        ctx.format_root = rd.resolve() if rd else None
    if staged is not None:
        ctx.staged_description = staged
        ctx.log("staged-description")
    return ctx


def base(cmd, ctx=None, **kw) -> dict:
    d = {"command": cmd}
    if ctx is not None:
        d.update(owner=ctx.owner, repo=ctx.repo)
    d.update(kw)
    if ctx is not None:
        d.setdefault("logs", ctx.logs)
        if getattr(ctx, "staged_description", None) is not None:
            d.setdefault("staged_description", ctx.staged_description)
    d.setdefault("logs", [])
    return d


def gate_owner(ctx, allow_hold=False) -> str | None:
    """Refuse excluded/hold/T3 (exit 2); return 'watching' for the watching org."""
    status = ctx.brand.check_owner(ctx.owner, repo=ctx.repo)
    if ctx.style.get("hold") and not allow_hold:
        raise ShowcaseError(f"{ctx.owner} family is on hold; pass --allow-hold", log="hold")
    return status


HOLD_REMEDY = "decide whether it is the user's own work, then pass --allow-hold"
# `readme` has no `--allow-hold`: its hold message must not name an option the command rejects.
README_HOLD_REMEDY = ("decide whether it is the user's own work; the README stays unchanged while the repository is "
                      "in the watching org (no `readme` option releases this hold)")


def gate_watching(ctx, allow_hold=False, remedy=HOLD_REMEDY) -> None:
    """A watching-org repository that is not a fork and not its `.github` (a detached upstream copy, or own work) is
    never changed by owner alone: refused (exit 2, `hold:watching-non-fork`) until decided, then `--allow-hold` (the
    generators that have it; `readme` passes its own `remedy`)."""
    why = ctx.watching_status()
    if why and why.startswith("hold") and not allow_hold:
        raise ShowcaseError(f"{ctx.owner}/{ctx.repo} is in the watching org but is not a fork: {remedy}", log=why)


def maybe_sidecar(ctx, out: Path, record: dict) -> None:
    from ctshowcase.staged import record_output

    record_output(ctx, out, record, always=out.parent.name == "images" and out.parent.parent.name == "docs")


def record_art_exemption(ctx, kind: str, out: str | None, reason: str) -> None:
    from ctshowcase.fingerprint import ART_EXEMPTIONS, ART_RECORDS, output_records, read_sidecar
    from ctshowcase.staged import lock_outputs, record_output

    if (ctx.repo_dir is None or getattr(ctx, "staged_description", None) is not None
            or ctx.style.get("hold") or ctx.watching_status() == "hold:watching-non-fork"
            or reason not in ART_EXEMPTIONS):
        return
    root = ctx.repo_dir.resolve()
    canonical = root / "docs" / "images" / ART_RECORDS[kind]
    if not canonical.parent.resolve().is_relative_to(root) or (out is not None and Path(out).resolve() != canonical):
        return
    with lock_outputs(ctx, canonical):
        if not canonical.parent.resolve().is_relative_to(root) or canonical.exists() or canonical.is_symlink():
            return
        previous = output_records(read_sidecar(canonical.parent)).get(canonical.name)
        if isinstance(previous, dict) and "staged_description" in previous:
            return
        record_output(ctx, canonical, {"exempt": reason}, always=True)


def ensure_distinct_outputs(*destinations: Path) -> None:
    for i, path in enumerate(destinations):
        for other in destinations[:i]:
            if path.resolve() == other.resolve() or (path.exists() and other.exists() and path.samefile(other)):
                raise ShowcaseError("output paths must be distinct", log="usage")


def _sidecar_text(ctx, path: Path, data: dict) -> str:
    from ctshowcase.fingerprint import sidecar_text
    from ctshowcase.formatting import format_text, same_json

    summary = sidecar_text(data)
    formatted = format_text(ctx.repo_dir, path, summary)
    if not same_json(summary, formatted):
        raise ShowcaseError("formatter changed the art sidecar data", log="formatter-content")
    return formatted


def write_art(ctx, out: Path, data: bytes, *, format_generated: bool, preview=None, **extra) -> None:
    from ctshowcase.fingerprint import bytes_record, has_staged_outputs
    from ctshowcase.formatting import target_relative, write_formatted_outputs
    from ctshowcase.staged import check_outputs, lock_outputs, plan_sidecars

    artifacts = [(out, data, extra)]
    if preview is not None:
        artifacts.append((*preview, {}))
    paths = [path for path, _, _ in artifacts]
    if not format_generated:
        check_outputs(ctx, *paths)
        write_rendered_art(ctx, *artifacts)
        return
    root = getattr(ctx, "format_root", None) or (ctx.repo_dir.resolve() if ctx.repo_dir else None)
    for path in paths:
        target_relative(root, path)
    capture = getattr(ctx, "meta_path", None)
    ensure_distinct_outputs(*paths, *((capture,) if capture else ()))
    with lock_outputs(ctx, *paths):
        check_outputs(ctx, *paths, format_root=root)
        records = [(path, bytes_record(content, **details),
                    path.parent.name == "images" and path.parent.parent.name == "docs")
                   for path, content, details in artifacts]
        planned = plan_sidecars(ctx, *records)
        if capture is not None:
            ensure_distinct_outputs(capture, *planned)
        provenance = [(path, _sidecar_text(ctx, path, summary).encode("utf-8")) for path, summary in planned.items()]
        for path in planned:
            target_relative(root, path)
        private_metadata = {path for path, summary in planned.items() if has_staged_outputs(summary)}
        artifacts_to_write = [(path, content) for path, content, _ in artifacts]
        staged = getattr(ctx, "staged_description", None) is not None
        outputs = provenance + artifacts_to_write if staged else artifacts_to_write + provenance
        write_formatted_outputs(outputs, repo_root=root, private=staged, private_metadata=private_metadata)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)



def write_artifact(ctx, path: Path, data: bytes) -> None:
    if getattr(ctx, "staged_description", None) is not None:
        from ctshowcase.fingerprint import replace_bytes
        replace_bytes(path, data, private=True)
    else:
        write_bytes(path, data)


# ---------------------------------------------------------------------------------------------------
# generators
# ---------------------------------------------------------------------------------------------------
def write_rendered_art(ctx, *artifacts: tuple[Path, bytes, dict], summarize_art: bool = True) -> None:
    from ctshowcase.fingerprint import bytes_record
    from ctshowcase.staged import check_outputs, lock_outputs, record_output, record_staged_writes

    staged = getattr(ctx, "staged_description", None) is not None
    paths = tuple(path for path, _, _ in artifacts)
    adjacent = not summarize_art
    with lock_outputs(ctx, *paths, adjacent=adjacent):
        check_outputs(ctx, *paths, adjacent=adjacent)
        guard = nullcontext()
        if staged:
            records = [(path, bytes_record(data, **details), False) for path, data, details in artifacts]
            guard = record_staged_writes(ctx, *records, adjacent=adjacent)
        with guard:
            for path, data, _ in artifacts:
                write_artifact(ctx, path, data)
        if not staged:
            for path, data, details in artifacts:
                record = bytes_record(data, **details)
                if summarize_art:
                    maybe_sidecar(ctx, path, record)
                else:
                    record_output(ctx, path, record, always=True, adjacent=adjacent)


def cmd_banner(args):
    from ctshowcase import banner
    from ctshowcase.typeset import Fonts
    ctx = context(args)
    gate_owner(ctx, args.allow_hold)
    why = ctx.art_status()["banner"]
    if why and why.startswith("exempt"):
        record_art_exemption(ctx, "banner", args.out, why)
        return base("banner", ctx, result="exempt", logs=[why]), OK
    gate_watching(ctx, args.allow_hold)
    ctx.require_measured(args.allow_unmeasured)
    if banner.selected_subtitle(ctx, args.subtitle) is not None:
        if not (ctx.meta.get("description") or "").strip():
            ctx.log("description-missing")
    else:
        ctx.require_description()
    out = Path(args.out) if args.out else default_out(args, "docs/images/banner.png")
    fonts = Fonts(ctx.brand)
    data, info = banner.render(ctx, fonts, scale=args.scale, budget=args.png_budget, subtitle=args.subtitle,
                               keys=args.key_chip or None, attrs=args.chip or None, category=args.category, icon=args.icon,
                               allow_few_chips=args.allow_few_chips)
    write_art(ctx, out, data, format_generated=args.format_generated, px=info["px"], scale=info["scale"],
              chips=info["chips"], icon_source=info["icon"]["source"])
    alt = f"{ctx.repo} by {ctx.company}"
    return base("banner", ctx, result="incomplete" if info["incomplete"] else "ok", out=str(out), bytes=info["bytes"], px=info["px"], save=info["save"],
                alt=alt, eyebrow=info["eyebrow"], title_lines=info["title_lines"], subtitle=info["subtitle"],
                subtitle_source=info["subtitle_source"], chips=info["chips"], icon=info["icon"]), OK


def cmd_card(args):
    from ctshowcase import card, svglint
    from ctshowcase.scene import png_bytes
    from ctshowcase.typeset import Fonts
    ctx = context(args)
    gate_owner(ctx, args.allow_hold)
    why = ctx.art_status()["card"]
    if why and why.startswith("exempt"):
        record_art_exemption(ctx, "card", args.out, why)
        return base("card", ctx, result="exempt", logs=[why]), OK
    gate_watching(ctx, args.allow_hold)
    ctx.require_measured(args.allow_unmeasured)
    out = Path(args.out) if args.out else default_out(args, "docs/images/card.svg")
    fonts = Fonts(ctx.brand)
    svg, scene, info = card.render(ctx, fonts, args.icon, keys=args.key_chip or None, attrs=args.chip or None)
    if args.format_generated:
        from ctshowcase.formatting import format_text, protect_svg_title, same_svg

        # Prettier's HTML parser wraps SVG title text, which must equal aria-label.
        formatted = format_text(ctx.repo_dir, out, protect_svg_title(svg))
        if not same_svg(svg, formatted):
            raise ShowcaseError("formatter changed the SVG drawing", log="formatter-content", code=CHECK_FAILED)
        svg = formatted
    lint = svglint.lint_bytes("card", svg.encode(), str(out))
    if lint["result"] != "PASS":
        return base("card", ctx, result="fail", lint=lint), CHECK_FAILED
    preview = (Path(args.png), png_bytes(card.preview_png(scene, fonts))) if args.png else None
    write_art(ctx, out, svg.encode(), format_generated=args.format_generated, preview=preview)
    outputs = [str(out)] + ([args.png] if preview else [])
    return base("card", ctx, result="ok", out=str(out), outputs=outputs, bytes=len(svg.encode()),
                alt=f"{ctx.repo}: {ctx.meta.get('description')}", items=info["items"], icon=info["icon"],
                lint=lint), OK


def cmd_social(args):
    from ctshowcase import social
    from ctshowcase.staged import SOCIAL_STAGING, check_outputs, check_social_path
    from ctshowcase.typeset import Fonts
    ctx = context(args)
    # R10 (ctx.social_applicable) includes backups and the personal-profile capstone: render whatever adopt uploads,
    # and keep both exempt wherever R10 leaves them out (the archive org, an archived capture)
    if gate_owner(ctx, args.allow_hold) == "watching" or ctx.is_fork or \
            (ctx.det["type"] in ("backup", "github-profile") and not ctx.social_applicable()):
        return base("social-preview", ctx, result="exempt", logs=["exempt:no-social-preview"]), OK
    ctx.require_measured(args.allow_unmeasured)
    staged = getattr(ctx, "staged_description", None) is not None
    job = getattr(args, "job", False)
    default_path = f"assets/{SOCIAL_STAGING}/social-preview.png" if staged else "assets/social-preview.png"
    out = Path(args.out) if args.out else default_out(args, default_path)
    check_social_path(out, staged=staged, job=job, checkout=ctx.repo_dir)
    r = getattr(args, "_content_resolver", None)  # set by `content social` from its --registry/--approved* flags
    data, fmt, info = social.social_render(ctx, Fonts(ctx.brand), args.title, args.icon,
                                           login=r.canonical(ctx.owner) if r else None,
                                           keys=args.key_chip or None, attrs=args.chip or None)
    if fmt == "jpg":
        out = out.with_suffix(".jpg")
        check_social_path(out, staged=staged, job=job, checkout=ctx.repo_dir)
    report = getattr(args, "report", None)
    check_outputs(ctx, out, auxiliary=(Path(report),) if staged and report else (), adjacent=True)
    details = {} if staged else {"live_social_preview": True}
    write_rendered_art(ctx, (out, data, details), summarize_art=False)
    res = base("social-preview", ctx, result="ok", out=str(out), bytes=len(data), format=fmt, **info)
    if args.command == "social-preview":  # the hidden, deprecated top-level alias of `content social`
        res["logs"] = list(res["logs"]) + ["deprecated:social-preview (use content social)"]
    return res, OK


def cmd_org_banner(args):
    from ctshowcase import social
    from ctshowcase.typeset import Fonts
    b = brand(args)
    b.check_owner(args.org)
    if not b.org(args.org).get("known"):
        raise ShowcaseError(f"no brand.yaml org row for {args.org}", log="needs-input:org-row")
    data = social.org_banner_render(b, Fonts(b), args.org, args.illustration)
    write_bytes(Path(args.out), data)
    return {"command": "org-banner", "owner": args.org, "result": "ok", "out": args.out, "bytes": len(data),
            "logs": [] if args.illustration else ["needs-input:org-illustration"]}, OK


def cmd_org_tile(args):
    from ctshowcase import svglint, tile
    from ctshowcase.scene import png_bytes
    from ctshowcase.typeset import Fonts
    b = brand(args)
    b.check_owner(args.org)
    fonts = Fonts(b)
    svg, scene = tile.render(b, fonts, args.org, args.avatar, args.illustration)
    lint = svglint.lint_bytes("tile", svg.encode(), args.out)
    if lint["result"] != "PASS":
        return {"command": "org-tile", "owner": args.org, "result": "fail", "lint": lint, "logs": []}, CHECK_FAILED
    write_bytes(Path(args.out), svg.encode())
    outs = [args.out]
    if args.png:
        write_bytes(Path(args.png), png_bytes(tile.preview_png(scene, fonts)))
        outs.append(args.png)
    logs = [] if args.avatar else ["needs-input:org-avatar"]
    return {"command": "org-tile", "owner": args.org, "result": "ok", "outputs": outs, "lint": lint, "logs": logs}, OK


def cmd_intro(args):
    from ctshowcase import intro, svglint
    from ctshowcase.typeset import Fonts
    b = brand(args)
    owner = args.profile or args.org
    if not owner:
        raise ShowcaseError("pass --profile CompleteDotTech or --org OWNER", log="usage")
    b.check_owner(owner)
    org = b.org(owner)
    if not org.get("known"):
        raise ShowcaseError(f"no brand.yaml org row for {owner}", log="needs-input:org-row", code=NEEDS_INPUT)
    logs = []
    prof = org.get("profile") or {}
    if args.profile:
        name = args.name or prof.get("name") or org.get("display_name")
        eyebrow = args.eyebrow or prof.get("eyebrow")
        chips_raw = args.chip or prof.get("chips") or []
    else:
        st = b.style(owner)
        name = args.name or org.get("display_name") or owner
        lab = st["company_label"]
        eyebrow = args.eyebrow or (f"{lab} · {org['eyebrow']}" if org.get("eyebrow") else lab)
        if st.get("eyebrow_case") == "upper":
            eyebrow = eyebrow.upper()
        chips_raw = args.chip or []
    for field, value in (("name", name), ("eyebrow", eyebrow)):
        if not value or not value.strip():
            raise ShowcaseError(f"supply this profile's --{field}", log=f"needs-input:{field}", code=NEEDS_INPUT)
    chips = []
    for c in chips_raw:
        kind, _, text = c.partition(":")
        if kind not in ("key", "attr") or not text:
            raise ShowcaseError(f"--chip must be key:TEXT or attr:TEXT ({c})", log="usage")
        chips.append((text, kind))
    static = args.static or not org.get("flagship")
    if static and not args.static:
        logs.append("static:not-flagship")
    complete_tech = org.get("family") == "completetech"
    if args.mark:
        mark = Path(args.mark)
    elif complete_tech:
        mark = b.mark_dark()
        if not mark:
            mark = b.dark_master()
            logs.append("needs-input:mark-dark")
    else:
        mark = b.asset(org.get("mark"))
        if not mark or not mark.is_file():
            raise ShowcaseError("supply this organization's own --mark", log="needs-input:org-mark", code=NEEDS_INPUT)
    tagline = args.tagline or prof.get("tagline")
    if not tagline:
        if complete_tech:
            tagline = b.strings["tagline"]
        else:
            raise ShowcaseError("supply this organization's own --tagline", log="needs-input:tagline", code=NEEDS_INPUT)
    svg = intro.build(b, Fonts(b), owner=owner, name=name, eyebrow=eyebrow, tagline=tagline,
                      chips=chips, mark_path=mark, height=args.height, static=static)
    lint = svglint.lint_bytes("intro", svg.encode(), args.out)
    if lint["result"] != "PASS":
        return {"command": "intro", "owner": owner, "result": "fail", "lint": lint, "logs": logs}, CHECK_FAILED
    write_bytes(Path(args.out), svg.encode())
    return {"command": "intro", "owner": owner, "result": "ok", "out": args.out, "animated": not static, "lint": lint,
            "logs": logs}, OK


def cmd_footer(args):
    from ctshowcase import footer
    b = brand(args)
    # Use the same repository applicability as doctor, including fork status.
    # An explicit --org remains useful for raw markup without a checkout.
    ctx = None
    if args.meta or args.repo_dir is not None or (args.check and not args.org and _origin_slug(Path("."))):
        # Applicability needs no renderable family identity. The coverage context
        # keeps pending identity read-only; the scoped consent gate still runs below.
        ctx = context(args, b, for_coverage=True)
        if args.org and not b.resolver().same(args.org, ctx.owner):
            raise ShowcaseError("--org does not match the repository metadata", log="usage")
        b.check_owner(ctx.owner, repo=ctx.repo)
        reason = ctx.footer_status()
        if reason:
            result = "exempt" if reason.startswith("exempt") else "hold"
            return {"command": "footer", "owner": ctx.owner, "repo": ctx.repo,
                    "result": result, "logs": [reason]}, OK
    elif args.org:
        status = b.check_owner(args.org)
        # Without repository metadata a watching owner can describe a fork or
        # its own .github; --check must inspect the footer conservatively.
        if status == "watching" and not args.check:
            return {"command": "footer", "owner": args.org, "result": "exempt", "logs": ["exempt"]}, OK
        if status != "watching":
            fv = b.org(args.org).get("footer", True)
            if fv == "hold":
                return {"command": "footer", "owner": args.org, "result": "hold", "logs": ["hold"]}, OK
            if fv is False:
                return {"command": "footer", "owner": args.org, "result": "exempt", "logs": ["exempt:footer"]}, OK
    if args.online and not args.check:
        raise ShowcaseError("--online goes with --check README.md", log="usage")
    if args.check:
        p = Path(args.check)
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        st, logs = footer.check(b, text)
        out = {"command": "footer", "file": str(p), "result": st, "logs": logs}
        if args.online:  # Phase 4.0 hard gate: both raw logo URLs must answer 200 (read-only HEAD)
            ost, rows = footer.online(b)
            out["online"] = rows
            if ost != "pass":
                out["logs"] = logs + ["footer-urls-offline"]
                if st == "pass":
                    out["result"] = ost
        return out, OK if out["result"] == "pass" else CHECK_FAILED
    if args.format == "json" and not args.raw:
        return {"command": "footer", "result": "ok", "markup": footer.block(b), "logs": []}, OK
    print(footer.block(b))
    return None, OK


def _authored_footer_refusal(ctx, text):
    """[] when every marked footer block of `text` is a footer copy the footer refresh may replace; otherwise the
    refusal (a partner or foreign image is authored content, and the refresh would remove it)."""
    from ctshowcase import readme
    for fm in readme.find_blocks(readme.MARK, readme.normalize_text(text)):
        if fm.group(1) == "footer" and not readme.is_footer_copy(fm.group(2), ctx.brand, own_site=True):
            return ["readme-shrink: the marked footer holds authored content (a partner or foreign image) that the "
                    "footer refresh would remove; README left unchanged"]
    return []


def readme_diff(before: str, after: str) -> str:
    """A unified patch over exact file bytes, using Git's LF line framing."""
    def patch_lines(text):
        *lines, tail = text.split("\n")
        return [line + "\n" for line in lines] + ([tail] if tail else [])

    diff = difflib.unified_diff(patch_lines(before), patch_lines(after), "a/README.md", "b/README.md")
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in diff)


def cmd_readme(args):
    from ctshowcase import readme, records
    ctx = context(args)
    gate_owner(ctx, allow_hold=True)
    rd = ctx.repo_dir
    if rd is None:
        raise ShowcaseError("readme needs the repository checkout (--repo-dir DIR, or run inside it)", log="usage")
    path = rd / "README.md"
    contrib_path = rd / "CONTRIBUTING.md"
    if args.format_generated and getattr(args, "no_regroup", False):
        raise ShowcaseError("--no-regroup preserves outside bytes and cannot be combined with --format-generated",
                            log="usage")
    if ctx.watching_status() == "exempt:watching-fork":
        return base("readme", ctx, result="exempt", logs=["exempt"]), OK
    # a watching-org non-fork other than `.github`: held until decided (no README change, no --allow-hold)
    gate_watching(ctx, remedy=README_HOLD_REMEDY)
    if args.format_generated:
        from ctshowcase.formatting import target_relative
        target_relative(rd, path)
    original_readme = path.read_bytes() if path.is_file() else None
    raw = (original_readme or b"").decode("utf-8")
    before = readme.normalize_text(raw)
    if args.variant and args.variant != "auto":
        ctx.det["variant"] = args.variant
    ctx.local_badges = args.badges == "local"
    def preservation(old, new, removed):
        problems = readme.preservation(old, new, removed, ctx=ctx)
        if problems and args.format_generated:
            from ctshowcase.formatting import match_formatted_managed_blocks
            comparable = match_formatted_managed_blocks(rd, path, old, new)
            problems = readme.preservation(old, comparable, removed, ctx=ctx)
        return problems

    reason = readme.managed_reason(ctx, before)
    if reason:
        proposed = readme.header(ctx)
        ctx.log("needs-input:readme-managed")
        if args.format == "text":
            if not args.quiet:
                print(f"readme: needs-input:readme-managed ({reason})", file=sys.stderr)
                if not args.write:
                    print(proposed)
                if getattr(ctx, "staged_description", None) is not None:
                    sys.stderr.write(f"staged-description: {json.dumps(ctx.staged_description, ensure_ascii=False)}\n")
            return None, NEEDS_INPUT if args.write else OK
        return base("readme", ctx, result="needs-input", written=False, reason=reason,
                    proposed_header=proposed), NEEDS_INPUT if args.write else OK
    mode = args.mode
    if args.no_regroup and (args.bootstrap or mode == "scaffold"):
        raise ShowcaseError("--no-regroup cannot be combined with --bootstrap or --mode scaffold", log="usage")
    contrib_new = None
    original_contrib = None
    if args.bootstrap:
        state = readme.bootstrap_state(before)
        removed = []
        # every state (pristine, edited, none) refuses before any write: the footer refresh below would replace it
        problems = _authored_footer_refusal(ctx, before)
        if problems:
            return base("readme", ctx, result="fail", mode="bootstrap", problems=problems,
                        logs=ctx.logs + ["readme-shrink"]), CHECK_FAILED
        if state == "pristine":
            after = readme.bootstrap(ctx, before, already_normalized=True)
            if contrib_path.is_file() and after != before:
                if args.format_generated:
                    target_relative(rd, contrib_path)
                original_contrib = contrib_path.read_bytes()
                c0 = original_contrib.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                c1 = readme.bootstrap_contributing(ctx, c0)
                contrib_new = c1 if c1 != c0 else None
        elif state == "edited":
            # a person wrote inside the template body: the block is theirs. Drop the marker and upgrade with the
            # never-drop-a-line check; if that check objects, only the marker goes and the header blocks refresh.
            ctx.log("bootstrap:edited")
            base_text = readme.drop_pristine(before)
            after, removed = readme.upgrade(ctx, base_text, already_normalized=True)
            problems = preservation(base_text, after, removed)
            if problems:
                # a marked footer that holds authored content (partner or foreign image) must never be regenerated
                refusal = _authored_footer_refusal(ctx, base_text)
                if refusal:
                    return base("readme", ctx, result="fail", mode="bootstrap",
                                problems=refusal + problems[:19],
                                logs=ctx.logs + ["readme-shrink"]), CHECK_FAILED
                ctx.log("readme-shrink")
                after, removed = readme.header_only(ctx, base_text, already_normalized=True), []
        else:
            after = readme.header_only(ctx, before, already_normalized=True)
    elif args.no_regroup:
        mode = "header"
        before = raw
        problems = _authored_footer_refusal(ctx, readme.normalize_text(before))
        if problems:
            return base("readme", ctx, result="fail", mode=mode, problems=problems,
                        logs=ctx.logs + ["readme-shrink"]), CHECK_FAILED
        after = readme.header_only(ctx, before, preserve_structure=True)
    else:
        if mode == "auto":
            mode = "scaffold" if len([ln for ln in readme.source_lines(before) if ln.strip(" \t")]) < 3 else "upgrade"
        removed = []
        if mode == "scaffold":
            after = readme.scaffold(ctx, before)
        elif mode == "header":
            after = readme.header_only(ctx, before, already_normalized=True)
        else:
            after, removed = readme.upgrade(ctx, before, already_normalized=True)
            problems = preservation(before, after, removed)
            if problems:
                return base("readme", ctx, result="fail", mode=mode, problems=problems[:20],
                            logs=ctx.logs + ["readme-shrink"]), CHECK_FAILED
    from ctshowcase.fingerprint import bytes_record, has_staged_outputs
    from ctshowcase.staged import (
        check_outputs, lock_outputs, plan_sidecars, protected_auxiliary, record_output, record_staged_writes,
        tagline_blocks, tagline_digest,
    )

    staged = getattr(ctx, "staged_description", None) is not None
    captured_description = str(ctx.meta.get("description") or "")
    tagline = readme.tagline_body(ctx).strip() if args.write and (staged or captured_description.strip()) else ""
    # Identify generated blocks before the formatter can reflow their Markdown.
    planned_taglines = tagline_blocks(after) if tagline else []
    tagline_indices = [index for index, body in enumerate(planned_taglines) if body == tagline]
    if staged and tagline:
        untracked = after.count(tagline) - len(tagline_indices)
        if untracked > 0 and untracked > before.count(tagline) - tagline_blocks(before).count(tagline):
            raise ShowcaseError("generated staged tagline is outside a provable README block",
                                log="staged-description:provenance", code=CHECK_FAILED)
    if args.format_generated:
        from ctshowcase.formatting import format_text, markdown_source_style
        encoding_bom = "\ufeff" if raw.startswith("\ufeff") else ""
        formatted = format_text(rd, path, encoding_bom + markdown_source_style(after, raw))
        before_blocks = readme.find_blocks(readme.MARK, after)
        formatted_blocks = readme.find_blocks(readme.MARK, formatted)
        if [m.group(1) for m in before_blocks] != [m.group(1) for m in formatted_blocks]:
            raise ShowcaseError("formatter changed the README managed blocks", log="formatter-content",
                                code=CHECK_FAILED)
        formatted = readme.reseal_formatted_badges(ctx, formatted, before_blocks, formatted_blocks)
        if formatted is None:
            raise ShowcaseError("formatter changed the README badge ownership", log="formatter-content",
                                code=CHECK_FAILED)
        # Badge resealing precedes this scan; never reuse potentially stale offsets.
        formatted = readme.reseal_formatted_taglines(
            formatted, before_blocks, readme.find_blocks(readme.MARK, formatted))
        if formatted is None:
            raise ShowcaseError("formatter changed the README tagline ownership", log="formatter-content",
                                code=CHECK_FAILED)
        if readme.bootstrap_state(after) == "pristine":
            formatted = readme.reseal_pristine(formatted)
            if formatted is None:
                raise ShowcaseError("formatter changed the README template-body markers", log="formatter-content",
                                    code=CHECK_FAILED)
        elif readme.bootstrap_state(formatted) == "pristine":
            raise ShowcaseError("formatter changed the README template-body ownership", log="formatter-content",
                                code=CHECK_FAILED)
        if readme.generated_license(formatted) and not readme.generated_license(after):
            raise ShowcaseError("formatter changed the README license ownership", log="formatter-content",
                                code=CHECK_FAILED)
        after = formatted
        # Prettier can emit CRLF. Compare against the exact bytes used for the plan.
        if contrib_new is not None:
            contrib_new = format_text(rd, contrib_path, markdown_source_style(contrib_new, original_contrib.decode("utf-8")))
    if args.format_generated or args.no_regroup:
        restored = after
    elif after != before:
        bom = readme.BOM if raw.startswith(readme.BOM) else ""
        restored = bom + readme.restore_line_endings(raw, before, after)
    else:
        restored = raw
    changed = restored != raw
    badge_outputs = {}
    if getattr(ctx, "badge_files", None):
        from ctshowcase import badge
        from ctshowcase.typeset import Fonts
        fonts = Fonts(ctx.brand)
        for rel, (label, message, colour) in sorted(ctx.badge_files.items()):
            drawing = badge.svg(ctx.brand, fonts, label, message, colour, style=ctx.style)
            if args.format_generated:
                from ctshowcase.formatting import protect_svg_title, same_svg
                formatted = format_text(rd, rd / rel, protect_svg_title(drawing))
                if not same_svg(drawing, formatted):
                    raise ShowcaseError("formatter changed the local badge drawing", log="formatter-content",
                                        code=CHECK_FAILED)
                drawing = formatted
            badge_outputs[rel] = drawing.encode("utf-8")
    report = (Path(args.records),) if staged and args.records and changed else ()
    capture = getattr(ctx, "meta_path", None)
    change_records = []
    if args.records and changed:
        change_records.append(records.record(ctx.owner, ctx.repo, "readme", "README.md", raw, restored,
                                             f"§7 variant {ctx.det['variant']} ({mode})"))
    if args.no_regroup and change_records and not staged:
        metadata_path = ctx.facts.metadata_path
        ensure_distinct_outputs(Path(args.records), path, rd / ".showcase.json", rd / "docs/images/.showcase.json",
                                *(rd / rel for rel in badge_outputs), *((metadata_path,) if metadata_path else ()))
    if args.format_generated and change_records:
        ensure_distinct_outputs(Path(args.records), path, contrib_path, *(rd / rel for rel in badge_outputs),
                                *((capture,) if capture else ()))
    if args.write:
        if badge_outputs or (changed and contrib_new is not None):
            ensure_distinct_outputs(path, contrib_path, *(rd / rel for rel in badge_outputs))
        outputs = [(rd / rel, content) for rel, content in badge_outputs.items()]
        rendered_readme = restored.encode("utf-8")
        if changed:
            outputs.append((path, rendered_readme))
            if contrib_new is not None:
                outputs.append((contrib_path, contrib_new.encode("utf-8")))
        rendered_taglines = tagline_blocks(after) if tagline_indices and args.format_generated else planned_taglines
        if len(rendered_taglines) != len(planned_taglines):
            raise ShowcaseError("formatter changed the README tagline markers", log="formatter-content",
                                code=CHECK_FAILED)
        matched_taglines = [rendered_taglines[index] for index in tagline_indices]
        reflowed = any(body != tagline for body in matched_taglines)
        tagline_record = {}
        if matched_taglines and (staged or reflowed):
            digests = sorted({tagline_digest(body) for body in matched_taglines})
            tagline_record["tagline_sha256"] = digests[0]
            if len(digests) > 1:
                tagline_record["tagline_sha256s"] = digests
            if not staged:
                tagline_record["description_sha256"] = tagline_digest(captured_description.strip())
        destinations = [target for target, _ in outputs]
        if matched_taglines and path not in destinations:
            destinations.append(path)
        snapshots = {path: original_readme}
        if contrib_new is not None:
            snapshots[contrib_path] = original_contrib
        output_locks = lock_outputs(ctx, path, *destinations, auxiliary=report) if report else lock_outputs(
            ctx, path, *destinations)
        with output_locks:
            check_outputs(ctx, *destinations, auxiliary=report,
                          format_root=getattr(ctx, "format_root", None))
            if not args.format_generated:
                for target, original in snapshots.items():
                    current = target.read_bytes() if target.is_file() else None
                    if current != original:
                        raise ShowcaseError(f"{target.name} changed while the refresh was being prepared",
                                            log="readme-source-changed", code=CHECK_FAILED)
            if args.format_generated:
                from ctshowcase.formatting import write_formatted_outputs
                from ctshowcase.output_lock import output_lock
                ensure_distinct_outputs(*(target for target, _ in outputs), *((capture,) if capture else ()))
                for target, original in snapshots.items():
                    target_relative(ctx.format_root, target)
                    current = target.read_bytes() if target.is_file() else None
                    if current != original:
                        raise ShowcaseError("README inputs changed during formatting", log="formatter-source-changed",
                                            code=CHECK_FAILED)
                planned = (
                    plan_sidecars(ctx, (path, bytes_record(rendered_readme, **tagline_record), reflowed))
                    if matched_taglines else {}
                )
                if capture is not None:
                    ensure_distinct_outputs(capture, *planned)
                for sidecar in planned:
                    target_relative(ctx.format_root, sidecar)
                provenance = [(target, _sidecar_text(ctx, target, data).encode("utf-8")) for target, data in planned.items()]
                private_metadata = {target for target, data in planned.items() if has_staged_outputs(data)}
                output_group = provenance + outputs if staged else outputs + provenance
                record_path = Path(args.records) if change_records else None
                append_output = None
                if record_path is not None:
                    ensure_distinct_outputs(record_path, *(target for target, _ in output_group))
                    encoded = records.json_lines(change_records).replace("\n", os.linesep).encode("utf-8")
                    append_output = (record_path, encoded)
                    if staged:
                        private_metadata.add(record_path)
                with output_lock(record_path):
                    if record_path is not None:
                        if staged:
                            check_outputs(ctx, *destinations, auxiliary=report)
                        ensure_distinct_outputs(record_path, path, contrib_path, *(target for target, _ in provenance),
                                                *(rd / rel for rel in badge_outputs), *((capture,) if capture else ()))
                    write_formatted_outputs(output_group, repo_root=ctx.format_root, snapshots=snapshots,
                                            private=staged, private_metadata=private_metadata, append_output=append_output)
            else:
                guard = nullcontext()
                if staged and matched_taglines:
                    record = (path, bytes_record(rendered_readme, **tagline_record), False)
                    guard = record_staged_writes(ctx, record)
                with guard:
                    for target, data in outputs:
                        if target == contrib_path and not staged:
                            target.write_text(contrib_new, encoding="utf-8")
                        else:
                            write_artifact(ctx, target, data)
                if not staged and matched_taglines:
                    record_output(ctx, path, bytes_record(rendered_readme))
    if change_records and not (args.format_generated and args.write):
        if staged and not args.write:
            check_outputs(ctx, path, auxiliary=report)
        if staged:
            with protected_auxiliary(capture, ctx.repo_dir, Path(args.records)):
                records.append(args.records, change_records, private=True)
        else:
            records.append(args.records, change_records)
    res = base("readme", ctx, result="changed" if changed else "unchanged", mode="bootstrap" if args.bootstrap else mode,
               variant=ctx.det["variant"], written=bool(args.write and changed),
               heading_moves=[] if args.no_regroup else readme.heading_moves(before, after, ctx.det["variant"]))
    if args.diff or not args.write:
        diff = readme_diff(raw, restored)
        if args.format == "text":
            if getattr(ctx, "staged_description", None) is not None:
                sys.stderr.write(f"staged-description: {json.dumps(ctx.staged_description, ensure_ascii=False)}\n")
            for move in res["heading_moves"]:
                if move.get("ambiguous"):
                    sys.stdout.write(f"Heading: {move['heading']} (ambiguous duplicate; "
                                     f"old levels {move['old_levels']}, new levels {move['new_levels']})\n")
                else:
                    sys.stdout.write(f"Heading: {move['heading']} (H{move['from']} -> H{move['to']}: {move['new_heading']})\n")
            output = getattr(sys.stdout, "buffer", None)
            if output is None:
                sys.stdout.write(diff)
            else:
                sys.stdout.flush()
                output.write(diff.encode("utf-8"))
            return None, OK
        res["diff"] = diff
    return res, OK


# ---------------------------------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------------------------------
def cmd_describe(args):
    from ctshowcase import describe, records
    ctx = context(args)
    gate_owner(ctx, allow_hold=True)
    text = args.text if args.text is not None else (ctx.meta.get("description") or "")
    rd = ctx.repo_dir
    has_ba = (rd / "BRAND_ASSETS.md").is_file() if rd else (ctx.facts.exists("BRAND_ASSETS.md") if ctx.facts.known else None)
    prop = describe.propose(text, slug=ctx.repo, type_=args.type or ctx.det["type"], has_brand_assets=has_ba,
                            product=ctx.facts.h1(), owner=ctx.owner)
    if args.records and prop["action"] == "edit":
        records.append(args.records, [records.record(ctx.owner, ctx.repo, "description", "description", text, prop["text"],
                                                     "§4.1 keep-or-edit")])
    if "text" in prop:  # the edited sentence; "text" in the result stays the current description
        prop = dict(prop, proposed=prop.pop("text"))
    failed = prop["action"] != "keep"
    logs = ctx.logs + (["needs-input:description"] if prop["action"] == "needs-writer" else [])
    return base("describe", ctx, result="fail" if failed else "pass", text=text, logs=logs, **prop), \
        CHECK_FAILED if failed else OK


def _stamp_signoff_ids(rec: dict, association_ids, ctx) -> None:
    """The topics change record names every record that authorized it, the target owner's
    own grant first (a T3 target) and then each T3 `also_in` association's (topics.merge `signoff_ids`).
    `signoff_id` is the first; `signoff_ids` lists all of them only when there is more than one."""
    from ctshowcase import signoff
    signoff.stamp_associations(rec, association_ids, ctx.owner, ctx.repo)  # shared with intake.adopt


def cmd_topics(args):
    from ctshowcase import records, topics
    ctx = context(args)
    gate_owner(ctx, allow_hold=True)
    also_in = None
    if args.also_in is not None:
        also_in = [x for x in args.also_in.split(",") if x.strip()]
    elif args.registry:
        from ctshowcase.resolver import Resolver
        res = Resolver.from_paths(ctx.brand, None if args.registry == "auto" else args.registry, require_registry=True)
        also_in = topics.registry_also_in(res, ctx.owner, ctx.repo)
    r = topics.merge(ctx, also_in)
    allowed = r["plan_allowed"]
    if args.records and allowed and not r["equal_as_set"]:
        rec = records.record(ctx.owner, ctx.repo, "topics", "topics", r["current"], r["proposed"], "§5.6 merge")
        _stamp_signoff_ids(rec, r.get("signoff_ids"), ctx)
        records.append(args.records, [rec])
    brand_hold = "needs-input:brand-topic" in r["logs"]
    complete = allowed and r["equal_as_set"] and "needs-input:topics-capacity" not in r["logs"]
    out = base("topics", ctx, result="needs-input" if brand_hold else "pass" if complete else "fail",
               **{k: v for k, v in r.items() if k != "logs"}, logs=ctx.logs + r["logs"])
    if args.gh and allowed and not r["equal_as_set"]:
        out["gh"] = topics.gh_command(ctx.owner, ctx.repo, r["proposed"])
    return out, NEEDS_INPUT if brand_hold else OK if complete else CHECK_FAILED


def cmd_labels(args):
    """§6 labels: emit labels.yml or plan passes A and B. Read-only toward GitHub: the plan leaves as `gh` argv and
    scripts/writer.py jobs (`--jobs FILE`); standalone users run the printed argv themselves after approving it."""
    from ctshowcase import labels, records
    from ctshowcase.org import PHASE, append_jobs, job, label_job_id, label_ops_argv
    if args.emit_yml:
        sys.stdout.write(labels.emit_yml())
        return None, OK
    ctx = context(args)
    ctx.brand.check_owner(ctx.owner, repo=ctx.repo)
    # the gates `org labels` applies (labels.md Scope): a family on hold is refused like banner and card
    if (ctx.style.get("hold") or ctx.brand.resolver().family_hold(ctx.owner)) and not args.allow_hold:
        raise ShowcaseError(f"{ctx.owner} family is on hold: labels are not applied; pass --allow-hold", log="hold")
    if ctx.is_fork or ctx.tier in ("T2-R", "T3") or ctx.style.get("name") == "romgenie":
        return base("labels", ctx, result="n/a", logs=["exempt"]), OK
    if ctx.meta.get("archived"):  # as `org labels` (labels.md Scope: never archived repos)
        return base("labels", ctx, result="n/a", logs=["archived"]), OK
    if ctx.meta.get("has_issues") is False and ctx.repo != ".github":  # `.github` always gets the standard set
        return base("labels", ctx, result="n/a", logs=["exempt", "has_issues:false"]), OK
    ai_ascension = ctx.same_owner("AI-Ascension")  # keeps its labels.yml; R6 there is only `dependencies` (q64)

    def live_labels():
        from ctshowcase.meta import _gh
        got = _gh(f"repos/{ctx.owner}/{ctx.repo}/labels?per_page=100", paginate=True)
        if got is None:
            raise ShowcaseError(f"cannot read the live labels of {ctx.owner}/{ctx.repo}", log="needs-input:gh",
                               code=NEEDS_INPUT)
        return [{"name": x["name"], "color": x.get("color", ""), "description": x.get("description") or ""} for x in got]

    existing = ctx.meta.get("labels")
    # no captured labels ([] is also what a failed capture records): anything that leaves as argv, jobs, records or gh
    # lines is planned against the live labels, never against [] (every standard label created beside GitHub's
    # defaults, no rename)
    if not existing and (args.plan or args.jobs or args.records or args.gh):
        existing = live_labels()  # read-only GET; the writer re-reads the live labels before it applies the jobs
    if ai_ascension:
        dep = next(lb for lb in labels.standard_labels() if lb["name"] == "dependencies")
        cur = next((lb for lb in existing or [] if lb["name"] == "dependencies"), None)
        ops, logs = ([{"op": "skip", "name": "dependencies", "rule": "§6.1 AI-Ascension dependencies"}]
                     if cur and cur.get("color") == dep["color"] else
                     [{"op": "patch" if cur else "create", "name": "dependencies", "color": dep["color"],
                       "description": dep["description"], "rule": "§6.1 AI-Ascension dependencies"}]), \
            ["labels:ai-ascension"]
    else:
        # §6.4 rule 0 always runs: in the checkout, else against the captured file list (unproven renames are held)
        ops, logs = labels.plan(existing or [], ctx.repo_dir, files=ctx.meta.get("files"),
                                complete=ctx.meta.get("files_complete") is True,
                                defaults=labels.defaults_for(ctx.owner, ctx.repo, repo_dir=ctx.repo_dir, meta=ctx.meta,
                                                             path=getattr(args, "org_defaults", None),
                                                             resolver=ctx.brand.resolver()))
    writes = [o for o in ops if o["op"] != "skip"]
    if args.records:
        records.append(args.records, [records.record(ctx.owner, ctx.repo, "label", o["name"], o["name"], o, o["rule"])
                                      for o in writes])
    # §6.4 rule 0: a rename a form or dependabot.yml still names is held out of the jobs; its lines are rewritten in
    # the estate/polish PR first, and a re-plan of the merged checkout then emits the rename
    held = [{"label": o["name"], "new_name": o["new_name"], **h} for o in ops for h in o.get("rewrite_references") or []]
    # a rename rule 0 could not check (no checkout, and no captured file list proving no reference file exists)
    unchecked = [{"label": o["name"], "new_name": o["new_name"], "check_files": o["check_files"]} for o in ops
                 if o.get("log") == labels.NEEDS_CHECKOUT]
    result = "fail" if writes or held else "needs-input" if unchecked else "pass"
    out = base("labels", ctx, result=result, ops=ops, logs=ctx.logs + logs)
    if unchecked:
        out["needs_checkout"] = unchecked
        for u in unchecked if not args.quiet else ():
            print(f"labels: rename {u['label']} -> {u['new_name']} held: rule 0 needs a checkout to read "
                  f"{', '.join(u['check_files'])}; re-plan with --repo-dir (and --org-defaults for the owner's "
                  ".github)", file=sys.stderr)
    if held:
        out["rewrite_first"] = held
        for h in held if not args.quiet else ():
            where = f"{h['repo']}:{h['path']}" if h.get("repo") else h["path"]
            print(f"labels: rewrite {where}:{h['line']} ({h['text']}) from {h['label']} to {h['new_name']} in the "
                  f"estate/polish PR; the rename job is withheld until then", file=sys.stderr)
    full = f"{ctx.owner}/{ctx.repo}"
    argvs = label_ops_argv(full, writes)
    if args.plan or args.jobs:
        out["argv"] = argvs
        out["jobs"] = [job(label_job_id(PHASE["labels"], full, argv), PHASE["labels"], "labels", argv,
                           repo=full, note="§6.3 pass A renames before pass B creates; never --force, never a delete.")
                       for argv in argvs]
        if args.jobs and out["jobs"]:
            append_jobs(args.jobs, out["jobs"])
    if args.gh:
        out["gh"] = labels.gh_lines(ctx.owner, ctx.repo, writes)
    return out, CHECK_FAILED if writes or held else NEEDS_INPUT if unchecked else OK


def cmd_meta(args):
    from ctshowcase import config as C
    from ctshowcase import meta as M
    from ctshowcase.context import same_repository
    from ctshowcase.detect import detect
    from ctshowcase.facts import RepoFacts
    try:
        b = brand(args, prefer_lock=True)
    except ShowcaseError:
        if args.from_gh:
            raise
        b = None
    rd = None
    if args.from_gh:
        owner = args.from_gh.split("/")[0]
        status = b.owner_status(owner)
        if status in ("excluded", "hold", "t3"):
            # raises Refused (exit 2); --allow-t3 only after an approved t3-metadata or t3-signoff row
            b.check_owner(owner, allow_t3=args.allow_t3, repo=args.from_gh.split("/")[1] if "/" in args.from_gh else None)
        m = M.from_gh(args.from_gh)
    else:
        rd = repo_dir(args)
        m = M.merged(args.meta, str(rd) if rd else None)
    resolver = b.resolver() if b else None
    facts = RepoFacts(m, rd, metadata_path=args.meta, metadata_output=args.out)
    unread_override = False
    override = {}
    override_errors = (ConfigError, OSError, ValueError, RecursionError)
    if C.yaml is not None:
        override_errors += (C.yaml.YAMLError,)
    try:
        override = (C.load_repo_override(rd, facts=facts)[0] if rd
                    else C.override_from_manifests(m.get("manifests"), m.get("files")))
    except override_errors:
        # Preserve the capture on the stdlib-only Action step and for invalid
        # config. A later config-aware command reports the exact failure.
        unread_override = True
    if override.get("for") and not same_repository(override["for"], m["owner"], m["repo"], resolver):
        override = {}
    m["detected"] = detect(m, facts, override, type_override=args.type_override,
                           same_owner=resolver.same if resolver else None)
    if unread_override:
        m["detected"].pop("suggestion", None)
    if b:
        try:
            m["detected"]["family"] = b.org(m["owner"]).get("family")
            m["detected"]["owner_status"] = b.owner_status(m["owner"])
        except ShowcaseError:
            pass
    text = json.dumps(m, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        suggestion = m["detected"].get("suggestion")
        return {"command": "meta", "owner": m["owner"], "repo": m["repo"], "result": "ok", "out": args.out,
                "detected": m["detected"], "logs": [suggestion] if suggestion else []}, OK
    sys.stdout.write(text)
    return None, OK


def cmd_fingerprint(args):
    from ctshowcase import fingerprint as fp
    from ctshowcase.meta import merged
    rd = repo_dir(args)
    m = merged(args.meta, str(rd) if rd else None)
    out_dir = (rd or Path(".")) / args.out_dir if not Path(args.out_dir).is_absolute() else Path(args.out_dir)
    b = brand(args, prefer_lock=True) if args.config else None
    inp = fp.inputs(m, rd, same_owner=b.resolver().same if b else None, metadata_path=args.meta)
    f = fp.fingerprint(inp, fp.config_sha256(b))
    selected = None
    if args.outputs is not None or args.readme is not None:
        selected = {fp.ART_RECORDS[kind] for kind in (args.outputs or "").split(",") if kind in fp.ART_RECORDS}
        if args.readme in ("header", "bootstrap"):
            selected.add("README.md")
    changed = fp.outputs_changed(fp.read_sidecar(out_dir), f, selected, out_dir=out_dir)
    if args.github_output and os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\nfingerprint={f}\n")
    return {"command": "fingerprint", "owner": m.get("owner"), "repo": m.get("repo"), "result": "ok", "fingerprint": f,
            "changed": changed, "logs": []}, OK


def cmd_fonts(args):
    from ctshowcase import fonts
    rows = fonts.fetch() if args.fetch else fonts.check()
    bad = [r for r in rows if r["result"] == "fail"]
    return {"command": "fonts", "result": "fail" if bad else "pass", "fonts": rows, "logs": []}, CHECK_FAILED if bad else OK


def cmd_lint(args):
    from ctshowcase import pnglint, readmelint, svglint
    results = []
    if args.what == "svg":
        if not args.kind:
            raise ShowcaseError("lint svg needs --kind", log="usage")
        results = [svglint.lint_file(args.kind, f) for f in args.files]
    elif args.what == "banner":
        results = [pnglint.lint_banner(f) for f in (args.files or ["docs/images/banner.png"])]
    elif args.what == "readme":
        ctx = context(args)
        gate_owner(ctx, allow_hold=True)  # excluded, hold and T3 owners are refused like every other repo command
        f = Path(args.files[0]) if args.files else (ctx.repo_dir or Path(".")) / "README.md"
        r = readmelint.lint(ctx, f, args.variant)
        results = [r]
    elif args.what == "all":
        from ctshowcase import readme as readmemod
        ctx = context(args)
        gate_owner(ctx, allow_hold=True)
        rd = ctx.repo_dir or Path(".")
        status = ctx.art_status()
        readme_path = rd / "README.md"
        if readme_path.is_file():
            results.append(readmelint.lint(ctx, readme_path))
            if ctx.preserve_unchanged() and readmemod.preserved(ctx, readme_path.read_text(encoding="utf-8")):
                status["banner"] = status["banner"] or "exempt:preserve-banner"  # q57 pres: "Leave them unchanged"
        # an applicable banner or card that is missing fails; an exempt one is only linted if it exists
        for kind, pattern in (("banner", "docs/images/banner.png"), ("card", "docs/images/card.svg"),
                              ("intro", "assets/intro.svg"), ("tile", "docs/images/org-tile.svg")):
            p = rd / pattern
            if not p.is_file() and not (kind in status and status[kind] is None):
                continue
            results.append(pnglint.lint_banner(p) if kind == "banner" else svglint.lint_file(kind, p))
    elif args.what == "public-leak":
        results = lint_public_leak(args)
    elif args.what == "prose":
        results = lint_prose(args)
    bad = any(str(r.get("result")).lower() == "fail" for r in results)
    if not args.quiet:
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
    return None, CHECK_FAILED if bad else OK


def lint_public_leak(args) -> list[dict]:
    """OPS-03: no private slug, distinctive private name, members-only pin or internal note in any public file the run
    writes. Wraps the `org profile` leak check with the whole estate's private set (or --org ORG[,ORG]); needs the
    private registry (read only) and the repositories' metadata (--meta-dir) to tell public from private."""
    from ctshowcase.org import Estate, estate_leak_scope, load_flags, load_metas, public_leaks, _default_decisions
    from ctshowcase.resolver import Resolver
    if not args.files:
        raise ShowcaseError("lint public-leak needs FILE...", log="usage")
    if getattr(args, "denylist", None) is not None:
        if any((args.registry, args.meta_dir, args.decisions, args.org, args.approved, args.approved_yaml, args.actions)):
            raise ShowcaseError("use --denylist without registry, metadata, org or approval inputs", log="usage")
        from ctshowcase.publicleak import check_files
        return check_files(args.files, args.denylist)
    b = brand(args)
    res = Resolver.from_paths(b, args.registry, args.approved, args.approved_yaml, args.actions, require_registry=True)
    estate = Estate(b, res, flags=load_flags(args.decisions or _default_decisions()))
    n = load_metas(args.meta_dir, estate)
    orgs = [x for x in (args.org or "").split(",") if x.strip()] or None
    scope, logs = estate_leak_scope(estate, orgs)
    if not n:
        logs.append("needs-input:meta-dir (no metadata: every repository counts as private, fails closed)")
    out = []
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            out.append({"file": f, "result": "fail", "hits": [], "fails": ["file not found"], "logs": logs})
            continue
        hits = public_leaks(p.read_text(encoding="utf-8", errors="replace"), scope)
        out.append({"file": f, "result": "fail" if hits else "pass", "hits": hits, "logs": logs})
    return out


def lint_prose(args) -> list[dict]:
    """CQ-17 on text the run writes: §1.2 brand strings, no emoji, no placeholders, typos (optional codespell), and the
    §4.1 formula for descriptions and taglines. --preserved turns brand, emoji and typo findings into warnings."""
    from ctshowcase import describe, prose
    items = [(f, Path(f).read_text(encoding="utf-8", errors="replace") if Path(f).is_file() else None) for f in args.files]
    items += [("--text", x) for x in args.text or []]
    if not items:
        raise ShowcaseError("lint prose needs FILE... or --text TEXT", log="usage")
    ctx = None
    if args.meta:
        from ctshowcase.context import RepoContext
        from ctshowcase.meta import load_file
        ctx = RepoContext(brand(args), load_file(args.meta), None, type_override=getattr(args, "type_override", None))
    dictionary = prose._codespell_dictionary()
    allow = {w.lower() for w in args.allow or []}
    out = []
    for name, text in items:
        if text is None:
            out.append({"file": name, "kind": args.prose_kind, "result": "fail", "fails": ["file not found"], "warns": [],
                        "logs": []})
            continue
        chk = None
        if args.prose_kind in ("description", "tagline"):
            line = text.strip()
            if ctx is not None:
                chk = describe.checks(line, slug=ctx.repo, type_=ctx.det["type"], has_brand_assets=None, owner=ctx.owner)
            else:  # no repository context: the format rules only (voice, slug words and brand mention need the repo)
                chk = [c for c in describe.checks(line, slug="", type_="", has_brand_assets=None)
                       if c["rule"] not in ("V1", "D8", "B1", "P1")]
        out.append(prose.lint_text(text, kind=args.prose_kind, preserved=args.preserved, describe_checks=chk,
                                   dictionary=dictionary, allow=allow, name=name))
    return out


def cmd_contact(args):
    from ctshowcase import contact
    from ctshowcase.typeset import Fonts
    b = brand(args)
    if args.cross_surface:
        if not args.org:
            raise ShowcaseError("--cross-surface needs --org ORG", log="usage")
        b.check_owner(args.org)
        surfaces = {"avatar": args.avatar, "banner": args.banner, "card": args.card, "social": args.social,
                    "org_banner": args.org_banner}
        outs, logs = contact.build_cross_surface(args.org, surfaces, Path(args.out), b, Fonts(b))
        return {"command": "contact-sheet", "owner": args.org, "result": "incomplete" if logs else "ok",
                "outputs": [str(o) for o in outs], "logs": logs}, OK
    if not args.inputs:
        raise ShowcaseError("contact-sheet needs INPUT... (or --org ORG --cross-surface)", log="usage")
    widths = tuple(int(x) for x in args.widths.split(","))
    outs = contact.build([Path(p) for p in args.inputs], Path(args.out), b, Fonts(b), args.mode, args.tile, args.cols,
                         args.gap, widths, args.mask, args.labels, args.title)
    return {"command": "contact-sheet", "result": "ok", "outputs": [str(o) for o in outs], "logs": []}, OK


def _resolver_args(args, require_registry=False):
    from ctshowcase.resolver import Resolver
    return Resolver.from_paths(brand(args), getattr(args, "registry", None), getattr(args, "approved", None),
                               getattr(args, "approved_yaml", None), getattr(args, "actions", None),
                               require_registry=require_registry)


def _intake_jobs(args, res):
    from ctshowcase import records
    from ctshowcase.org import append_jobs
    if args.records:
        records.append(args.records, res.get("records") or [])
    if args.jobs:
        append_jobs(args.jobs, res.get("jobs") or [])


def cmd_adopt(args):
    """OPS-06 / RP-13: Phase 3 change records and writer jobs for a repository (read-only; metadata from --meta, or
    read-only `gh api` GETs)."""
    from ctshowcase import intake
    from ctshowcase import meta as M
    from ctshowcase.context import RepoContext
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+", args.slug or ""):
        raise ShowcaseError("adopt needs OWNER/REPO", log="usage")
    b = brand(args)
    b.check_owner(args.slug.split("/")[0], repo=args.slug.split("/")[1] if "/" in args.slug else None)
    if args.meta:
        m = M.load_file(args.meta)
        if not _same_slug(args, f"{m.get('owner')}/{m.get('repo')}", args.slug):
            raise ShowcaseError(f"--meta describes {m.get('owner')}/{m.get('repo')}, not {args.slug}", log="usage")
    else:
        m = M.from_gh(args.slug)
    rd = Path(args.repo_dir) if args.repo_dir and not args.no_repo_dir else None
    ctx = RepoContext(b, m, rd, type_override=getattr(args, "type_override", None), metadata_path=args.meta)
    if ctx.style.get("hold") or b.resolver().family_hold(ctx.owner):
        # STANDARD §12.5 #4: a family on hold gets only the decision 18 footer (as `org labels` refuses it): no
        # settings, topics, label, security or social-preview jobs
        raise ShowcaseError(f"{ctx.owner} family is on hold: adopt plans nothing for it", log="hold")
    res = intake.adopt(ctx, _resolver_args(args), approval_id=args.approval_id, org_defaults=getattr(args, "org_defaults", None))
    _intake_jobs(args, res)
    return res, OK


def cmd_new(args):
    """OPS-06: the create-from-template writer job, then `adopt` on the planned repository (read-only)."""
    from ctshowcase import intake
    res = intake.new_plan(brand(args), args.slug, args.type, template=args.template, description=args.description or "",
                          resolver=_resolver_args(args), approval_id=args.approval_id)
    _intake_jobs(args, res)
    return res, OK


def cmd_doctor(args):
    from ctshowcase import doctor
    if args.estate:
        from ctshowcase import intake
        if not args.meta_dir:
            raise ShowcaseError("doctor --estate needs --meta-dir (metadata of every repository found)", log="usage")
        seen: dict = {}
        # recursive, like `org --meta-dir`, so `state/meta` covers every state/meta/<org>/ folder; one entry per slug
        for f in sorted(Path(args.meta_dir).rglob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            for x in (data if isinstance(data, list) else [data]):
                if isinstance(x, dict):
                    o = x.get("owner")
                    o = o.get("login") if isinstance(o, dict) else o
                    key = f"{o}/{x.get('repo') or x.get('name')}".lower() if o else f"#{len(seen)}"
                    seen[key] = x
        metas = list(seen.values())
        res = intake.estate_doctor(brand(args), _resolver_args(args, require_registry=True), metas,
                                   template_dir=args.template_dir, checkouts=args.checkouts, out=args.out)
        return res, OK
    ctx = context(args, for_coverage=True)
    ctx.brand.check_owner(ctx.owner, allow_t3=True, repo=ctx.repo, verify_signoff=False)  # read-only: doctor.row shows R7 hold
    r = doctor.row(ctx)
    from ctshowcase import provenance
    prov = provenance.doctor_repo(ctx, args.meta)  # decision 25: a row of its own, never a cell or the done verdict
    fmt = args.doctor_format
    if fmt == "tsv":
        print(doctor.as_tsv(r, args.header))
    elif fmt == "md":
        print(doctor.as_md(r, args.header))
    else:
        print(json.dumps({**r, "provenance": prov}, ensure_ascii=False))
    if fmt != "json":
        print("Provenance (not a cell): " + json.dumps(prov, ensure_ascii=False), file=sys.stderr)
    if fmt != "json" and (r["tooling"]["formatters"] or r["tooling"]["validators"]):
        print("Tooling preflight (not run): " + json.dumps(r["tooling"], ensure_ascii=False), file=sys.stderr)
    return None, CHECK_FAILED if any(v == "fail" for v in r["cells"].values()) else OK


def cmd_enterprise(args):
    """Decision 24: read-only enterprise discover/snapshot, offline doctor, seat-check, diff and plan."""
    from ctshowcase import enterprise as E
    from ctshowcase import records

    def load(path, flag):
        if not path:
            raise ShowcaseError(f"enterprise {args.action} needs {flag}", log="usage")
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ShowcaseError(f"cannot read {path}: {exc}", log="usage")

    act = ENTERPRISE_ALIASES.get(args.action, args.action)
    if act == "snapshot-query":
        from ctshowcase.resolver import enterprise_snapshot_query
        return {"command": "enterprise", "action": act, "result": "ok", **enterprise_snapshot_query(args.slug or ""),
                "logs": []}, OK
    if act == "discover":
        return {"command": "enterprise", "action": act, "result": "ok", **E.discover(), "logs": []}, OK
    if act == "snapshot":
        if not args.slug:
            raise ShowcaseError("enterprise snapshot needs --slug (from `enterprise discover`)", log="usage")
        snap = E.snapshot(args.slug)
        if args.out:
            write_bytes(Path(args.out), (json.dumps(snap, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode())
        return {"command": "enterprise", "action": act, "result": "ok", "slug": snap["slug"], "out": args.out,
                "counts": {k: len(v) for k, v in snap["sections"].items() if isinstance(v, list)},
                "sha256": snap["sha256"], "logs": []}, OK
    snap = load(args.snapshot, "--snapshot FILE")
    if act == "doctor":
        from ctshowcase.resolver import Resolver
        b = brand(args)
        res = Resolver.from_paths(b, args.registry, args.approved, args.approved_yaml, args.actions)  # CQ-03
        r = E.doctor(snap, E.desired(), b, load(args.baseline, "--baseline") if args.baseline else None, resolver=res)
        from ctshowcase import provenance  # decision 25: the private estate stamp against this snapshot
        r["provenance"] = provenance.doctor_local("enterprise", str(snap.get("slug") or ""), b, res,
                                                  provenance.enterprise_stamp_dir(), snapshot=snap)
        return {"command": "enterprise", "action": act, **r, "logs": []}, CHECK_FAILED if r["result"] == "fail" else OK
    if act == "seat-check":
        r = E.seat_check(snap, args.user or E.desired().get("seat_free_user") or "romgenie")
        return {"command": "enterprise", "action": act, **r, "logs": []}, CHECK_FAILED if r["result"] == "fail" else OK
    if act == "diff":
        r = E.diff(load(args.baseline, "--baseline OLD"), snap)
        return {"command": "enterprise", "action": act, "result": "changed" if r["changed"] else "unchanged", **r,
                "logs": []}, OK
    recs = E.plan(snap, E.desired())
    records.append(args.records, recs)
    jobs = E.plan_jobs(snap, recs)
    if args.jobs and jobs:
        from ctshowcase.org import append_jobs
        append_jobs(args.jobs, jobs)
    return {"command": "enterprise", "action": act, "result": "ok", "records": recs, "jobs": jobs, "logs": []}, OK


def cmd_provenance(args):
    """Decision 25 (PROPOSAL): `provenance check|stamp|star`; read-only toward GitHub."""
    from ctshowcase import provenance
    return provenance.cmd(args, brand)


def cmd_config(args):
    from ctshowcase import config as C
    from ctshowcase.detect import STANDARD_LOCK, standard_lock_text
    b = brand(args)
    errs = C.schema_errors(b.raw)
    crops = C.write_crops(b) if args.crop and not errs else None  # NeedsInput (exit 4) until the boxes are measured
    if args.write_lock:
        # LF on every OS: the committed locks are LF, and a CRLF rewrite on Windows would change every line
        C.LOCK.write_text(C.lock_text(b.raw), encoding="utf-8", newline="\n")
        STANDARD_LOCK.write_text(standard_lock_text(), encoding="utf-8", newline="\n")
    in_sync = C.lock_in_sync(b) and STANDARD_LOCK.is_file() and STANDARD_LOCK.read_text(encoding="utf-8") == standard_lock_text()
    ok = not errs and in_sync
    out = {"command": "config", "result": "pass" if ok else "fail", "schema_errors": errs, "lock_in_sync": in_sync,
           "config_sha256": b.sha256, "logs": []}
    if crops is not None:
        out["crops"] = crops
    return out, OK if ok else CHECK_FAILED


# ---------------------------------------------------------------------------------------------------
# argument parser
# ---------------------------------------------------------------------------------------------------
def _resolver_flags(s, prefix: str) -> None:
    s.add_argument("--registry", help=f"{prefix}registry/estate.yaml (default: the bundle beside the skill; read only)")
    for flag, what in (("--approved", "decisions/approved.tsv"), ("--approved-yaml", "decisions/APPROVED_ACTIONS.yaml"),
                       ("--actions", "decisions/estate-actions.json")):
        s.add_argument(flag, help=f"{prefix}{what} for the org resolver (default: the bundle's)")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="showcase.py", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=f"github-showcase-skill {__version__} · {STANDARD} · exit codes: 0 ok, 1 check failed, "
                                       "2 usage/config/refused owner, 3 art-fail, 4 needs-input")
    p.add_argument("--config", help="brand config (default references/brand.yaml beside the script)")
    p.add_argument("--repo-dir", default=None,
                   help="target repository checkout (default: the current directory, which must then be the checkout the "
                        "--meta file describes)")
    p.add_argument("--no-repo-dir", action="store_true", help="ignore --repo-dir; use --meta facts only")
    p.add_argument("--meta", help="metadata JSON (scratch format, gh api output or `meta` output)")
    p.add_argument("--type", dest="type_override", metavar="TYPE", help="§5.4 type to use instead of automatic detection, including for low-confidence results")
    p.add_argument("--format", choices=("json", "text"), default=None, help="output style")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--allow-t3", action="store_true",
                   help="treat a T3 (co-owned) owner as signed off for this run: every repository command and generator, not just `meta`; pass only when a t3-metadata or t3-signoff row is approved (default: T3 owners are refused, exit 2). It also needs a valid sign-off record, by default in <estate root>/decisions/t3-signoffs.yaml (see --t3-signoff-file and references/t3-signoff.md); there is no opt-out")
    p.add_argument("--t3-signoff-file", metavar="PATH",
                   help="the sign-off record file to read instead of the default <estate root>/decisions/t3-signoffs.yaml "
                        "(env SHOWCASE_T3_SIGNOFF_FILE; format: references/t3-signoff.md). Order: this flag, the env, the default. "
                        "The file is read, never created")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__} ({STANDARD})")
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    s = sub.add_parser("banner", help="README hero banner PNG (decision 13 golden layout)")
    s.add_argument("--out", help="default: <repo-dir>/docs/images/banner.png")
    s.add_argument("--scale", type=int, choices=(1, 2), default=2)
    s.add_argument("--icon")
    s.add_argument("--subtitle")
    s.add_argument("--key-chip", action="append", default=[])
    s.add_argument("--chip", action="append", default=[])
    s.add_argument("--category")
    s.add_argument("--allow-unmeasured", action="store_true")
    s.add_argument("--allow-hold", action="store_true")
    s.add_argument("--png-budget", type=int, default=300_000)
    s.add_argument("--allow-few-chips", action="store_true",
                   help="render with fewer than 2 chips (result incomplete, needs-input:banner-chips) instead of exit 4")
    s.add_argument("--description", help="render a staged description; log and record it without changing GitHub")
    s.add_argument("--format-generated", action="store_true",
                   help="format the shared JSON sidecar with the target's pinned local Prettier")
    s.set_defaults(func=cmd_banner)

    s = sub.add_parser("card", help="repo card SVG (dark only)")
    s.add_argument("--out", help="default: <repo-dir>/docs/images/card.svg")
    s.add_argument("--png")
    s.add_argument("--icon")
    s.add_argument("--allow-unmeasured", action="store_true")
    s.add_argument("--allow-hold", action="store_true")
    s.add_argument("--description", help="render a staged description; log and record it without changing GitHub")
    s.add_argument("--key-chip", action="append", default=[])
    s.add_argument("--chip", action="append", default=[])
    s.add_argument("--format-generated", action="store_true", help="format SVG with the target's pinned local Prettier")
    s.set_defaults(func=cmd_card)

    # deprecated alias of the contract name `content social` (same options, same file); added without `help`, so
    # argparse leaves it out of the command list in --help (it still parses)
    s = sub.add_parser("social-preview", description="Deprecated alias of `content social` (R10 social preview).")
    s.add_argument("--out", help="default: <repo-dir>/assets/social-preview.png (.jpg when over 900 KB)")
    s.add_argument("--title", help="title text (default: README H1, else the title-cased slug)")
    s.add_argument("--icon")
    s.add_argument("--allow-unmeasured", action="store_true")
    s.add_argument("--allow-hold", action="store_true")
    s.add_argument("--description", help="render a staged description; log and record it without changing GitHub")
    s.add_argument("--key-chip", action="append", default=[])
    s.add_argument("--chip", action="append", default=[])
    s.set_defaults(func=cmd_social)

    s = sub.add_parser("org-banner", help="1600x400 org profile banner JPG (.github/profile/assets/banner.jpg)")
    s.add_argument("--org", required=True)
    s.add_argument("--illustration")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_org_banner)

    s = sub.add_parser("org-tile", help="org tile SVG (dark only)")
    s.add_argument("--org", required=True)
    s.add_argument("--avatar")
    s.add_argument("--illustration")
    s.add_argument("--out", default="org-tile.svg")
    s.add_argument("--png")
    s.set_defaults(func=cmd_org_tile)

    s = sub.add_parser("intro", help="profile intro SVG (animated for the profile and flagship orgs)")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--profile")
    g.add_argument("--org")
    s.add_argument("--name")
    s.add_argument("--eyebrow")
    s.add_argument("--tagline")
    s.add_argument("--chip", action="append", default=[], help="key:TEXT or attr:TEXT")
    s.add_argument("--mark")
    s.add_argument("--height", type=int, choices=(320, 360), default=320)
    s.add_argument("--static", action="store_true")
    s.add_argument("--out", default="assets/intro.svg")
    s.set_defaults(func=cmd_intro)

    s = sub.add_parser("footer", help="decision 18 footer markup, or --check a README")
    s.add_argument("--check")
    s.add_argument("--org")
    s.add_argument("--raw", action="store_true", help="print the markup even with --format json")
    s.add_argument("--online", action="store_true",
                   help="with --check: HEAD both decision 18 raw logo URLs (read only); fails unless both return 200")
    s.set_defaults(func=cmd_footer)

    s = sub.add_parser("readme", help="scaffold or upgrade README.md to its §7 variant (dry run by default)")
    s.add_argument("--mode", choices=("auto", "scaffold", "upgrade", "header"), default="auto")
    s.add_argument("--variant", default="auto", choices=("auto", *"ABCDEFGHIJ"))
    s.add_argument("--write", action="store_true")
    s.add_argument("--diff", action="store_true")
    s.add_argument("--records")
    s.add_argument("--bootstrap", action="store_true")
    s.add_argument("--no-regroup", action="store_true",
                   help="refresh existing marker blocks in place and preserve all surrounding bytes")
    s.add_argument("--badges", choices=("shields", "local"), default="shields",
                   help="local renders badges offline to docs/images/badges/*.svg (profile READMEs)")
    s.add_argument("--description", help="render a staged description; log and record it without changing GitHub")
    s.add_argument("--format-generated", action="store_true", help="format generated text with the target's pinned local Prettier")
    s.set_defaults(func=cmd_readme)

    s = sub.add_parser("describe", help="lint a description against §4.1 and propose keep/edit")
    s.add_argument("--text")
    s.add_argument("--type")
    s.add_argument("--records")
    s.set_defaults(func=cmd_describe)

    s = sub.add_parser("topics", help="§5.6 topic merge proposal")
    s.add_argument("--records")
    s.add_argument("--gh", action="store_true")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--also-in", metavar="ORG[,ORG]",
                   help="§5.3a: add one org membership topic per also_in org (after the family topics; never the home org's)")
    g.add_argument("--registry", nargs="?", const="auto", metavar="FILE",
                   help="read the repo's also_in from registry/estate.yaml (default: the bundle beside the skill); read only")
    s.set_defaults(func=cmd_topics)

    s = sub.add_parser("labels", help="§6 label standard: --emit-yml, or --plan (gh argv and writer jobs; never writes)")
    s.add_argument("--emit-yml", action="store_true")
    s.add_argument("--plan", action="store_true", help="plan passes A and B; prints the gh argv and scripts/writer.py jobs")
    s.add_argument("--references", action="store_true",
                   help="kept for compatibility: the §6.4 rule 0 reference check always runs (a rename it cannot check "
                        "without --repo-dir is held as needs-input:label-references)")
    s.add_argument("--org-defaults", metavar="PATH",
                   help="§6.4 rule 0 in the owner's .github repository, whose default issue forms apply to a repository "
                        "without .github/ISSUE_TEMPLATE/: a checkout of it, or its `meta --from-gh OWNER/.github` JSON "
                        "(without it, such a rename is held as needs-input:label-references)")
    s.add_argument("--records")
    s.add_argument("--gh", action="store_true", help="also print the plan as gh command lines")
    s.add_argument("--jobs", metavar="FILE", help="append the writer jobs (JSON lines) to FILE")
    s.add_argument("--allow-hold", action="store_true", help="plan for a family on hold (refused otherwise, as `org labels`)")
    s.set_defaults(func=cmd_labels)

    s = sub.add_parser("meta", help="normalized metadata (read-only gh api GETs with --from-gh)")
    s.add_argument("--from-gh", metavar="OWNER/REPO")
    s.add_argument("--out")
    s.add_argument("--allow-t3", action="store_true", default=argparse.SUPPRESS,
                   help="read a T3 (co-owned) repository; pass only when a t3-metadata or t3-signoff row is approved")
    s.set_defaults(func=cmd_meta)

    s = sub.add_parser("fingerprint", help="input fingerprint vs docs/images/.showcase.json")
    s.add_argument("--out-dir", default="docs/images")
    s.add_argument("--github-output", action="store_true")
    s.add_argument("--outputs", help="restrict the check to selected Action art surfaces (comma-separated banner,card)")
    s.add_argument("--readme", help="include README provenance for Action modes header and bootstrap")
    s.set_defaults(func=cmd_fingerprint)

    s = sub.add_parser("fonts", help="verify or fetch the pinned OFL fonts")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--fetch", action="store_true")
    s.set_defaults(func=cmd_fonts)

    s = sub.add_parser("lint", help="lint svg|readme|banner|all|public-leak|prose")
    s.add_argument("what", choices=("svg", "readme", "banner", "all", "public-leak", "prose"))
    s.add_argument("files", nargs="*")
    s.add_argument("--kind", choices=("intro", "card", "tile", "plate", "divider", "chart"))
    s.add_argument("--variant", default="auto")
    s.add_argument("--denylist", help="public-leak: UTF-8 literal names, one per line; case-insensitive; never echoed")
    s.add_argument("--registry", help="public-leak: registry/estate.yaml (default: the bundle beside the skill; read only)")
    s.add_argument("--meta-dir", help="public-leak: per-repository metadata JSONs (visibility; without them every "
                                      "repository counts as private)")
    s.add_argument("--decisions", help="public-leak: decisions/decisions.json (exposure flags)")
    for flag in ("--approved", "--approved-yaml", "--actions"):
        s.add_argument(flag, help="public-leak: approval files for the org resolver (default: the bundle's)")
    s.add_argument("--org", help="public-leak: limit the private set to ORG[,ORG] (default: every registry org)")
    s.add_argument("--prose-kind", choices=("text", "description", "tagline"), default="text",
                   help="prose: text (README, org and profile prose), or one description / tagline per FILE or --text")
    s.add_argument("--text", action="append", help="prose: check this text (repeatable)")
    s.add_argument("--preserved", action="store_true", help="prose: text kept verbatim from a repository (warn only)")
    s.add_argument("--allow", action="append", help="prose: extra allowlisted word for the typo check (repeatable)")
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("contact-sheet", help="review sheets on GitHub dark and light")
    s.add_argument("inputs", nargs="*")
    s.add_argument("--out", required=True)
    s.add_argument("--mode", choices=("grid", "stack", "avatar"), default="grid")
    s.add_argument("--tile", type=int, default=400)
    s.add_argument("--cols", type=int)
    s.add_argument("--gap", type=int, default=24)
    s.add_argument("--widths", default="1012,390")
    s.add_argument("--mask", choices=("none", "circle", "rounded"), default="none")
    s.add_argument("--labels", action="store_true")
    s.add_argument("--title")
    s.add_argument("--org", help="--cross-surface: the org whose set is judged (G4)")
    s.add_argument("--cross-surface", action="store_true",
                   help="G4: org avatar at 32 px, hero banner, repo card, social preview and org banner on one sheet")
    for flag, what in (("--avatar", "org avatar PNG"), ("--banner", "a repo's docs/images/banner.png"),
                       ("--card", "a repo card (SVG with a .png preview sibling, or PNG)"),
                       ("--social", "a repo's assets/social-preview.png"), ("--org-banner", "the org banner JPG")):
        s.add_argument(flag, help=f"--cross-surface: {what}")
    s.set_defaults(func=cmd_contact)

    s = sub.add_parser("doctor", help="definition-of-done coverage row; --estate: intake proposals and template drift")
    s.add_argument("--format", dest="doctor_format", choices=("tsv", "json", "md"), default="tsv")
    s.add_argument("--header", action="store_true")
    s.add_argument("--allow-unmeasured", action="store_true",
                   help="accepted for consistency; doctor checks existing outputs and does not render art")
    s.add_argument("--estate", action="store_true",
                   help="classify repositories missing from the registry with POLICY.md into NEW_PROPOSALS entries and "
                        "diff template-managed files against the template (read only)")
    s.add_argument("--meta-dir", help="--estate: metadata JSONs of every repository found (Phase 0 / 9 capture)")
    s.add_argument("--template-dir", help="--estate: checkout of the current template repository")
    s.add_argument("--checkouts", help="--estate: directory of repository checkouts to diff against the template")
    s.add_argument("--out", help="--estate: merge the proposals into this NEW_PROPOSALS.yaml")
    _resolver_flags(s, "--estate: ")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("adopt", help="Phase 3 change records and writer jobs for a repository: settings, topics, labels, "
                                     "security baseline, UI checklist (OPS-06; read only)")
    s.add_argument("slug", metavar="OWNER/REPO")
    s.add_argument("--records", help="append change records (JSON lines)")
    s.add_argument("--jobs", help="append the scripts/writer.py jobs (JSON lines)")
    s.add_argument("--approval-id", help="approval id stamped on every job (the approved NEW_PROPOSALS item)")
    s.add_argument("--org-defaults", metavar="PATH",
                   help="a checkout or the metadata JSON of the owner's .github repository, for §6.4 rule 0 (labels)")
    _resolver_flags(s, "")
    s.set_defaults(func=cmd_adopt)

    s = sub.add_parser("new", help="plan a new repository from the template (create job, then adopt; read only)")
    s.add_argument("slug", metavar="OWNER/NAME")
    s.add_argument("--type", dest="type", required=True, help="§5.4 type of the new repository")
    s.add_argument("--description", help="the one-sentence description (§4.1), if already written")
    s.add_argument("--template", default="CompleteTech-LLC/completetech-repo-template", help="template OWNER/REPO")
    s.add_argument("--records", help="append change records (JSON lines)")
    s.add_argument("--jobs", help="append the scripts/writer.py jobs (JSON lines)")
    s.add_argument("--approval-id", help="approval id stamped on every job (create-repo)")
    _resolver_flags(s, "")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("enterprise", help="decision 24: read-only enterprise snapshot-query, snapshot, doctor, seat-check, "
                                          "diff, plan")
    s.add_argument("action", choices=(*ENTERPRISE_ACTIONS, *ENTERPRISE_ALIASES), metavar="{" + ",".join(ENTERPRISE_ACTIONS) + "}",
                   help="snapshot-query prints the validated read queries (no network); discover and snapshot run them; "
                        "doctor, seat-check, diff and plan work offline on snapshot files")
    s.add_argument("--slug", help="enterprise slug (snapshot-query, snapshot)")
    s.add_argument("--out", help="snapshot output (registry/enterprise.snapshot.json)")
    s.add_argument("--snapshot", help="snapshot file to check (doctor, seat-check, diff NEW, plan)")
    s.add_argument("--baseline", help="earlier snapshot (doctor E10/E12, diff OLD)")
    s.add_argument("--user", help="seat-check user (default: seat_free_user in references/enterprise.yaml)")
    s.add_argument("--records", help="append plan change records (JSON lines)")
    s.add_argument("--jobs", help="plan: append the scripts/writer.py jobs (JSON lines) to FILE")
    for flag, what in (("--registry", "registry/estate.yaml"), ("--approved", "decisions/approved.tsv"),
                       ("--approved-yaml", "decisions/APPROVED_ACTIONS.yaml"), ("--actions", "decisions/estate-actions.json")):
        s.add_argument(flag, help=f"doctor: {what} for the shared org resolver (renamed orgs resolve, CQ-03); "
                                  "default: the bundle beside the skill")
    s.set_defaults(func=cmd_enterprise)

    s = sub.add_parser("config", help="validate brand.yaml and its lock copies (--write-lock regenerates them)")
    s.add_argument("--write-lock", action="store_true")
    s.add_argument("--crop", action="store_true",
                   help="write brand_assets mark_dark and bulb_dark from the measured brand_assets.crops boxes (Phase 0.12)")
    s.set_defaults(func=cmd_config)

    # command groups (decisions 5, 14, 15, 18, 21, 23 and 24; COVERAGE gaps): each module registers its own parser, and
    # every org lookup inside them goes through ctshowcase.resolver (old and new logins resolve alike, CQ-03)
    from ctshowcase import account, brand_commands, content, org, project
    brand_commands.register(sub)
    org.register(sub)
    project.register(sub)
    account.register(sub)
    content.add_parser(sub, sys.modules.get(__name__))  # None when loaded by path: content finds showcase.py itself
    from ctshowcase import provenance
    provenance.register(sub, cmd_provenance)  # decision 25: run-once check, stamp and the local run ledger
    return p


def main(argv=None) -> int:
    """Run one invocation. `--allow-t3` and the sign-off record file hold only for this call (and this context): the prior
    values, and the sign-off grants of any enclosing run, are restored on every exit."""
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off, t3_signed_off
    from ctshowcase import signoff
    token = set_t3_signed_off(t3_signed_off())
    file_token = signoff.set_file(signoff._FILE.get())
    run_token = signoff.reset()
    try:
        return _main(argv)
    finally:
        signoff.restore(run_token)
        signoff.reset_file(file_token)
        reset_t3_signed_off(token)


def _main(argv=None) -> int:
    # Redirected Windows streams can start as cp1252 even when their consumers
    # expect UTF-8. Configure before argparse, which also writes help and errors.
    # StringIO and embedding hosts may replace either stream without reconfigure.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # Supplying encoding alone resets errors to strict. Keep stderr's
            # backslashreplace and POSIX stdout's surrogateescape for paths
            # containing undecodable filesystem bytes.
            reconfigure(encoding="utf-8", errors=stream.errors)
    cli = parser()
    args, remaining = cli.parse_known_args(argv)
    # Older Python 3.12 argparse stops a '*' positional after an intervening
    # option: `lint svg --kind card file.svg` leaves the file unconsumed.
    # Only lint's file operands may continue here; unknown options still fail.
    if remaining and args.command == "lint" and all(not item.startswith("-") for item in remaining):
        args.files.extend(remaining)
    elif remaining:
        cli.error("unrecognized arguments: " + " ".join(remaining))
    from ctshowcase.config import set_t3_signed_off
    set_t3_signed_off(getattr(args, "allow_t3", False))
    from ctshowcase import signoff
    signoff.set_file(getattr(args, "t3_signoff_file", None))
    if args.format is None:
        args.format = "text" if args.command in TEXT_DEFAULT else "json"
    try:
        obj, code = args.func(args)
    except ShowcaseError as exc:
        obj = {"command": args.command, "result": "refused" if exc.code == USAGE and (exc.log in ("hold", "t3-signoff", "exempt") or exc.log.startswith("t3-signoff:"))
               else exc.log.split(":")[0], "error": str(exc), "logs": [exc.log]}
        code = exc.code
        if args.format == "text" and not args.quiet:
            print(f"{args.command}: {exc}", file=sys.stderr)
            return code
    except OSError as exc:  # a path the caller named (--jobs, --out, --records, ...) cannot be read or written
        obj = {"command": args.command, "result": "usage", "error": f"{exc.filename or ''}: {exc.strerror or exc}",
               "logs": ["usage"]}
        code = USAGE
        if args.format == "text" and not args.quiet:
            print(f"{args.command}: {obj['error']}", file=sys.stderr)
            return code
    if obj is not None:
        for key in ("jobs", "records", "proposals"):  # writer jobs, change records, writer-shaped proposals
            if isinstance(obj.get(key), list):
                signoff.stamp(obj[key])  # the granting record
        emit(args, obj)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
