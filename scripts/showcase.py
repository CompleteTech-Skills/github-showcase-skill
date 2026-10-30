#!/usr/bin/env python3
"""CompleteTech GitHub showcase CLI: generate banners, cards, tiles, intros and footers, check a repository against
the CompleteTech estate standard (ct-std-v1), and plan org, GitHub Project, Enterprise and content work. Read-only
toward GitHub: GitHub changes leave as JSON plans, `gh` argv and scripts/writer.py jobs; see SKILL.md.

Usage: python3 scripts/showcase.py [--config PATH] [--repo-dir DIR] [--meta FILE] [--format json|text] [--quiet]
                                   <command> [options]

Command groups: org {profile,about,pins,labels,health,doctor} · project {capture-query,normalize,copy-plan,readme,lint,
estate-plan} · enterprise {snapshot-query,discover,snapshot,doctor,seat-check,diff,plan} · content {social,icon,links,
linguist,actions,images,sidebar}. `content social` is the contract name for the social preview (`social-preview` is a
hidden, deprecated alias); `org-banner` and `org-tile` are top-level generators.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctshowcase import STANDARD, __version__  # noqa: E402
from ctshowcase.errors import CHECK_FAILED, NEEDS_INPUT, OK, USAGE, ShowcaseError  # noqa: E402

GENERATORS = {"banner", "card", "org-tile", "intro", "contact-sheet", "social-preview", "org-banner"}
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
        for k in ("out", "outputs", "text", "proposed", "logs"):
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
            raise ShowcaseError(f"metadata describes {want} but {rd.resolve()} is a checkout of {have}; pass the right "
                                "--repo-dir, or --no-repo-dir to use the metadata alone", log="usage")
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


def context(args, b=None):
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import merged
    b = b or brand(args)
    rd = repo_dir(args)
    meta = merged(args.meta, str(rd) if rd else None)
    return RepoContext(b, meta, rd, type_override=getattr(args, "type_override", None))


def base(cmd, ctx=None, **kw) -> dict:
    d = {"command": cmd}
    if ctx is not None:
        d.update(owner=ctx.owner, repo=ctx.repo)
    d.update(kw)
    if ctx is not None:
        d.setdefault("logs", ctx.logs)
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
    from ctshowcase import fingerprint as fp
    if out.parent.name == "images" and out.parent.parent.name == "docs":
        inp = fp.inputs(ctx.meta, ctx.repo_dir)
        # the repository's immutable id (`meta --from-gh`): `action_prepare.py foreign` tells a rename or transfer
        # (same id) from art copied out of another repository (a template copy gets a new id). Kept out of the
        # fingerprint inputs, so the fingerprint is unchanged.
        if isinstance(ctx.meta.get("id"), int) and not isinstance(ctx.meta.get("id"), bool):
            record = dict(record, repository_id=ctx.meta["id"])
        fp.write_sidecar(out.parent, inp, ctx.brand.sha256, out.name, record)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# ---------------------------------------------------------------------------------------------------
# generators
# ---------------------------------------------------------------------------------------------------
def cmd_banner(args):
    from ctshowcase import banner
    from ctshowcase.fingerprint import file_record
    from ctshowcase.typeset import Fonts
    ctx = context(args)
    gate_owner(ctx, args.allow_hold)
    why = ctx.art_status()["banner"]
    if why and why.startswith("exempt"):
        return base("banner", ctx, result="exempt", logs=[why]), OK
    gate_watching(ctx, args.allow_hold)
    ctx.require_measured(args.allow_unmeasured)
    ctx.require_description()
    out = Path(args.out) if args.out else default_out(args, "docs/images/banner.png")
    fonts = Fonts(ctx.brand)
    data, info = banner.render(ctx, fonts, scale=args.scale, budget=args.png_budget, subtitle=args.subtitle,
                               keys=args.key_chip or None, attrs=args.chip or None, category=args.category, icon=args.icon,
                               allow_few_chips=args.allow_few_chips)
    write_bytes(out, data)
    maybe_sidecar(ctx, out, file_record(out, px=info["px"], scale=info["scale"], chips=info["chips"],
                                        icon_source=info["icon"]["source"]))
    alt = f"{ctx.repo} by {ctx.company}"
    return base("banner", ctx, result="incomplete" if info["incomplete"] else "ok", out=str(out), bytes=info["bytes"], px=info["px"], save=info["save"],
                alt=alt, eyebrow=info["eyebrow"], title_lines=info["title_lines"], subtitle=info["subtitle"],
                subtitle_source=info["subtitle_source"], chips=info["chips"], icon=info["icon"]), OK


def cmd_card(args):
    from ctshowcase import card, svglint
    from ctshowcase.fingerprint import file_record
    from ctshowcase.scene import png_bytes
    from ctshowcase.typeset import Fonts
    ctx = context(args)
    gate_owner(ctx, args.allow_hold)
    why = ctx.art_status()["card"]
    if why and why.startswith("exempt"):
        return base("card", ctx, result="exempt", logs=[why]), OK
    gate_watching(ctx, args.allow_hold)
    ctx.require_measured(args.allow_unmeasured)
    out = Path(args.out) if args.out else default_out(args, "docs/images/card.svg")
    fonts = Fonts(ctx.brand)
    svg, scene, info = card.render(ctx, fonts, args.icon)
    lint = svglint.lint_bytes("card", svg.encode(), str(out))
    if lint["result"] != "PASS":
        return base("card", ctx, result="fail", lint=lint), CHECK_FAILED
    write_bytes(out, svg.encode())
    outputs = [str(out)]
    if args.png:
        write_bytes(Path(args.png), png_bytes(card.preview_png(scene, fonts)))
        outputs.append(args.png)
    maybe_sidecar(ctx, out, file_record(out))
    return base("card", ctx, result="ok", out=str(out), outputs=outputs, bytes=len(svg.encode()),
                alt=f"{ctx.repo}: {ctx.meta.get('description')}", items=info["items"], icon=info["icon"],
                lint=lint), OK


def cmd_social(args):
    from ctshowcase import social
    from ctshowcase.typeset import Fonts
    ctx = context(args)
    # R10 (ctx.social_applicable) includes backups and the personal-profile capstone: render whatever adopt uploads,
    # and keep both exempt wherever R10 leaves them out (the archive org, an archived capture)
    if gate_owner(ctx, args.allow_hold) == "watching" or ctx.is_fork or \
            (ctx.det["type"] in ("backup", "github-profile") and not ctx.social_applicable()):
        return base("social-preview", ctx, result="exempt", logs=["exempt:no-social-preview"]), OK
    ctx.require_measured(args.allow_unmeasured)
    r = getattr(args, "_content_resolver", None)  # set by `content social` from its --registry/--approved* flags
    data, fmt, info = social.social_render(ctx, Fonts(ctx.brand), args.title, args.icon,
                                           login=r.canonical(ctx.owner) if r else None)
    out = Path(args.out) if args.out else default_out(args, "assets/social-preview.png")
    if fmt == "jpg":
        out = out.with_suffix(".jpg")
    write_bytes(out, data)
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
    chips = []
    for c in chips_raw:
        kind, _, text = c.partition(":")
        if kind not in ("key", "attr") or not text:
            raise ShowcaseError(f"--chip must be key:TEXT or attr:TEXT ({c})", log="usage")
        chips.append((text, kind))
    static = args.static or not org.get("flagship")
    if static and not args.static:
        logs.append("static:not-flagship")
    if args.mark:
        mark = Path(args.mark)
    else:
        mark = b.mark_dark()
        if not mark:
            mark = b.dark_master()
            logs.append("needs-input:mark-dark")
    svg = intro.build(b, Fonts(b), owner=owner, name=name, eyebrow=eyebrow, tagline=args.tagline or b.strings["tagline"],
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
    # the watching org's exemption covers only its forks, which `--org` cannot tell from its `.github` (which gets the
    # footer): `--check` reads the README there instead of answering `exempt` (fail closed)
    if args.org and not (args.check and b.owner_status(args.org) == "watching"):
        status = b.owner_status(args.org)
        if status in ("excluded", "hold", "t3"):
            b.check_owner(args.org)
        if status == "watching":
            return {"command": "footer", "owner": args.org, "result": "exempt", "logs": ["exempt"]}, OK
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


def cmd_readme(args):
    from ctshowcase import readme, records
    ctx = context(args)
    gate_owner(ctx, allow_hold=True)
    rd = ctx.repo_dir
    if rd is None:
        raise ShowcaseError("readme needs the repository checkout (--repo-dir DIR, or run inside it)", log="usage")
    path = rd / "README.md"
    before = readme.read_text(path)
    if ctx.watching_status() == "exempt:watching-fork":
        return base("readme", ctx, result="exempt", logs=["exempt"]), OK
    # a watching-org non-fork other than `.github`: held until decided (no README change, no --allow-hold)
    gate_watching(ctx, remedy=README_HOLD_REMEDY)
    if args.variant and args.variant != "auto":
        ctx.det["variant"] = args.variant
    ctx.local_badges = args.badges == "local"
    mode = args.mode
    contrib_new = None
    if args.bootstrap:
        state = readme.bootstrap_state(before)
        removed = []
        if state == "pristine":
            after = readme.bootstrap(ctx, before)
            cp = rd / "CONTRIBUTING.md"
            if cp.is_file() and after != before:
                c0 = cp.read_text(encoding="utf-8")
                c1 = readme.bootstrap_contributing(ctx, c0)
                contrib_new = c1 if c1 != c0 else None
        elif state == "edited":
            # a person wrote inside the template body: the block is theirs. Drop the marker and upgrade with the
            # never-drop-a-line check; if that check objects, only the marker goes and the header blocks refresh.
            ctx.log("bootstrap:edited")
            base_text = readme.drop_pristine(before)
            after, removed = readme.upgrade(ctx, base_text)
            if readme.preservation(base_text, after, removed):
                ctx.log("readme-shrink")
                after, removed = readme.header_only(ctx, base_text), []
        else:
            after = readme.header_only(ctx, before)
    else:
        if mode == "auto":
            mode = "scaffold" if len([ln for ln in before.splitlines() if ln.strip()]) < 3 else "upgrade"
        removed = []
        if mode == "scaffold":
            after = readme.scaffold(ctx, before)
        elif mode == "header":
            after = readme.header_only(ctx, before)
        else:
            after, removed = readme.upgrade(ctx, before)
            problems = readme.preservation(before, after, removed)
            if problems:
                return base("readme", ctx, result="fail", mode=mode, problems=problems[:20],
                            logs=ctx.logs + ["readme-shrink"]), CHECK_FAILED
    changed = after != before
    diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), "a/README.md", "b/README.md"))
    if args.write and getattr(ctx, "badge_files", None):
        from ctshowcase import badge
        from ctshowcase.typeset import Fonts
        fonts = Fonts(ctx.brand)
        for rel, (label, message, colour) in sorted(ctx.badge_files.items()):
            write_bytes(rd / rel, badge.svg(ctx.brand, fonts, label, message, colour).encode())
    if args.write and changed:
        path.write_text(after, encoding="utf-8")
        if contrib_new is not None:
            (rd / "CONTRIBUTING.md").write_text(contrib_new, encoding="utf-8")
    if args.records and changed:
        records.append(args.records, [records.record(ctx.owner, ctx.repo, "readme", "README.md", before, after,
                                                     f"§7 variant {ctx.det['variant']} ({mode})")])
    res = base("readme", ctx, result="changed" if changed else "unchanged", mode="bootstrap" if args.bootstrap else mode,
               variant=ctx.det["variant"], written=bool(args.write and changed))
    if args.diff or not args.write:
        if args.format == "text":
            sys.stdout.write(diff)
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
    if args.records and not r["equal_as_set"]:
        records.append(args.records, [records.record(ctx.owner, ctx.repo, "topics", "topics", r["current"], r["proposed"],
                                                     "§5.6 merge")])
    out = base("topics", ctx, result="pass" if r["equal_as_set"] else "fail", **{k: v for k, v in r.items() if k != "logs"},
               logs=ctx.logs + r["logs"])
    if args.gh and not r["equal_as_set"]:
        out["gh"] = topics.gh_command(ctx.owner, ctx.repo, r["proposed"])
    return out, OK if r["equal_as_set"] else CHECK_FAILED


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
    from ctshowcase import meta as M
    from ctshowcase.detect import detect
    from ctshowcase.facts import RepoFacts
    if args.from_gh:
        owner = args.from_gh.split("/")[0]
        status = brand(args, prefer_lock=True).owner_status(owner)
        if status in ("excluded", "hold", "t3"):
            # raises Refused (exit 2); --allow-t3 only after an approved t3-metadata or t3-signoff row
            brand(args, prefer_lock=True).check_owner(owner, allow_t3=args.allow_t3, repo=args.from_gh.split("/")[1] if "/" in args.from_gh else None)
        m = M.from_gh(args.from_gh)
    else:
        rd = repo_dir(args)
        m = M.merged(args.meta, str(rd) if rd else None)
    m["detected"] = detect(m, RepoFacts(m, None if args.from_gh else repo_dir(args)))
    try:
        b = brand(args, prefer_lock=True)
        m["detected"]["family"] = b.org(m["owner"]).get("family")
        m["detected"]["owner_status"] = b.owner_status(m["owner"])
    except ShowcaseError:
        pass
    text = json.dumps(m, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        return {"command": "meta", "owner": m["owner"], "repo": m["repo"], "result": "ok", "out": args.out,
                "detected": m["detected"], "logs": []}, OK
    sys.stdout.write(text)
    return None, OK


def cmd_fingerprint(args):
    from ctshowcase import fingerprint as fp
    from ctshowcase.meta import merged
    rd = repo_dir(args)
    m = merged(args.meta, str(rd) if rd else None)
    out_dir = (rd or Path(".")) / args.out_dir if not Path(args.out_dir).is_absolute() else Path(args.out_dir)
    inp = fp.inputs(m, rd)
    f = fp.fingerprint(inp, fp.config_sha256())
    old = fp.read_sidecar(out_dir).get("fingerprint")
    changed = f != old
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
    b.check_owner(args.slug.split("/")[0])
    if args.meta:
        m = M.load_file(args.meta)
        if not _same_slug(args, f"{m.get('owner')}/{m.get('repo')}", args.slug):
            raise ShowcaseError(f"--meta describes {m.get('owner')}/{m.get('repo')}, not {args.slug}", log="usage")
    else:
        m = M.from_gh(args.slug)
    rd = Path(args.repo_dir) if args.repo_dir and not args.no_repo_dir else None
    ctx = RepoContext(b, m, rd, type_override=getattr(args, "type_override", None))
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
    ctx = context(args)
    ctx.brand.check_owner(ctx.owner, allow_t3=True, repo=ctx.repo)
    r = doctor.row(ctx)
    fmt = args.doctor_format
    if fmt == "tsv":
        print(doctor.as_tsv(r, args.header))
    elif fmt == "md":
        print(doctor.as_md(r, args.header))
    else:
        print(json.dumps(r, ensure_ascii=False))
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


def cmd_config(args):
    from ctshowcase import config as C
    from ctshowcase.detect import STANDARD_LOCK, standard_lock_text
    b = brand(args)
    errs = C.schema_errors(b.raw)
    crops = C.write_crops(b) if args.crop and not errs else None  # NeedsInput (exit 4) until the boxes are measured
    if args.write_lock:
        C.LOCK.write_text(C.lock_text(b.raw), encoding="utf-8")
        STANDARD_LOCK.write_text(standard_lock_text(), encoding="utf-8")
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
    p.add_argument("--type", dest="type_override", metavar="TYPE", help="§5.4 type to use instead of detection (when the file tree is not available); logged")
    p.add_argument("--format", choices=("json", "text"), default=None, help="output style")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--allow-t3", action="store_true",
                   help="treat a T3 (co-owned) owner as signed off for this run: every repository command and generator, not just `meta`; pass only when a t3-metadata or t3-signoff row is approved (default: T3 owners are refused, exit 2)")
    p.add_argument("--require-t3-signoff", action="store_true",
                   help="opt-in (env SHOWCASE_REQUIRE_T3_SIGNOFF=1): honour --allow-t3 only when a valid, unexpired sign-off record "
                        "in the estate bundle (decisions/t3-signoffs.yaml) covers the owner and repository; otherwise exit 2 "
                        "(t3-signoff:missing|expired|scope). Default off: --allow-t3 behaves as before")
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
    s.set_defaults(func=cmd_banner)

    s = sub.add_parser("card", help="repo card SVG (dark only)")
    s.add_argument("--out", help="default: <repo-dir>/docs/images/card.svg")
    s.add_argument("--png")
    s.add_argument("--icon")
    s.add_argument("--allow-unmeasured", action="store_true")
    s.add_argument("--allow-hold", action="store_true")
    s.set_defaults(func=cmd_card)

    # deprecated alias of the contract name `content social` (same options, same file); added without `help`, so
    # argparse leaves it out of the command list in --help (it still parses)
    s = sub.add_parser("social-preview", description="Deprecated alias of `content social` (R10 social preview).")
    s.add_argument("--out", help="default: <repo-dir>/assets/social-preview.png (.jpg when over 900 KB)")
    s.add_argument("--title", help="title text (default: README H1, else the title-cased slug)")
    s.add_argument("--icon")
    s.add_argument("--allow-unmeasured", action="store_true")
    s.add_argument("--allow-hold", action="store_true")
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
    s.add_argument("--badges", choices=("shields", "local"), default="shields",
                   help="local renders badges offline to docs/images/badges/*.svg (profile READMEs)")
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
    s.set_defaults(func=cmd_fingerprint)

    s = sub.add_parser("fonts", help="verify or fetch the pinned OFL fonts")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--fetch", action="store_true")
    s.set_defaults(func=cmd_fonts)

    s = sub.add_parser("lint", help="lint svg|readme|banner|all|public-leak|prose")
    s.add_argument("what", choices=("svg", "readme", "banner", "all", "public-leak", "prose"))
    s.add_argument("files", nargs="*")
    s.add_argument("--kind", choices=("intro", "card", "tile", "plate", "divider"))
    s.add_argument("--variant", default="auto")
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
    from ctshowcase import content, org, project
    org.register(sub)
    project.register(sub)
    content.add_parser(sub, sys.modules.get(__name__))  # None when loaded by path: content finds showcase.py itself
    return p


def main(argv=None) -> int:
    """Run one invocation. `--allow-t3` holds only for this call: the previous value is restored on every exit."""
    from ctshowcase.config import set_t3_signed_off, t3_signed_off
    from ctshowcase import signoff
    previous, previous_required = t3_signed_off(), signoff.required()
    try:
        return _main(argv)
    finally:
        set_t3_signed_off(previous)
        signoff.set_required(previous_required)
        signoff.reset()


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
    signoff.set_required(getattr(args, "require_t3_signoff", False) or signoff.env_required())
    if args.format is None:
        args.format = "text" if args.command in GENERATORS else "json"
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
        if signoff.required() and isinstance(obj.get("jobs"), list):
            signoff.stamp(obj["jobs"])
        emit(args, obj)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
