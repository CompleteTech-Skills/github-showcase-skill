"""Definition-of-done coverage row (§1.3 R1-R11 + decision columns; spec A6.13). No network."""
from __future__ import annotations

import hashlib
import re

from PIL import Image

from . import describe, footer as footermod, labels as labelsmod, pnglint, readmelint, svglint, topics as topicsmod
from . import readme as readmemod
from .config import t3_signed_off
from .context import RepoContext
from .detect import standard

COLUMNS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "banner", "icon", "card", "footer"]
LOGO_SHA = {"assets/logo.png": "a5c3c4ef55336ed4b883d3bc3bb6e1e942b836469bd2b2933bc8cc230b321621",
            "assets/logo-dark.png": "0dc00c0e5159518ff1d552b7052293b4e545ddd35be489e6d114e3ea64db27ec"}


def r1(ctx) -> str:
    n = standard("naming")
    name = ctx.repo
    # GitHub forks keep the upstream name (§3.1); a non-network copy follows `UPSTREAM-fork`, as the estate proposals
    if ctx.meta.get("fork") or name in n["exempt_names"] or any(re.search(p, name) for p in n["exempt_patterns"]) \
            or f"{ctx.owner}/{name}" in n["exempt_full"]:
        return "n/a"
    ok = re.match(n["n1"], name) and re.match(n["n2"], name)
    if ok and "." in name and not re.search(n["n1_dot_suffix"], name):
        ok = False
    if ok and re.search(n["n4_filler"], name):
        ok = False
    if ok and re.search(n["n4_date"], name) and not re.search(n["n4_backup"], name):
        ok = False
    if not ok:
        return "fail"
    return "warn" if len(name) > n["n5_max"] else "pass"


def _cell(code: str) -> str:
    """Doctor cell for a surface that does not apply: exempt -> n/a; hold and t3-signoff -> hold."""
    return "n/a" if code.startswith("exempt") else "hold"


def row(ctx: RepoContext) -> dict:
    cells: dict[str, str] = {}
    logs: list[str] = []
    rd = ctx.repo_dir
    cells["R1"] = r1(ctx)
    has_ba = (rd / "BRAND_ASSETS.md").is_file() if rd else (ctx.facts.exists("BRAND_ASSETS.md") if ctx.facts.known else None)
    chk = describe.checks(ctx.meta.get("description") or "", slug=ctx.repo, type_=ctx.det["type"], has_brand_assets=has_ba,
                          owner=ctx.owner)
    cells["R2"] = "fail" if any(c["result"] == "fail" for c in chk) else "pass"
    tp = topicsmod.merge(ctx)
    cells["R3"] = ("warn" if "topics-short" in tp["logs"] else "pass") if tp["equal_as_set"] else "fail"
    hp = ctx.meta.get("homepage") or ""
    cells["R4"] = "pass" if not hp or ctx.meta.get("homepage_status") == 200 else (
        "unknown" if ctx.meta.get("homepage_status") is None else "warn")
    kept_default = ctx.meta.get("default_branch_policy") == "keep" and ctx.meta.get("default_branch") != "main"
    if kept_default and not ctx.is_fork:
        logs.append("default-branch kept (user)")
    if ctx.is_fork:
        # upstream default and merge settings are preserved (§10.1); watching and archive org forks turn Issues off
        utility = ctx.tier == "T2-R" or ctx.brand.owner_status(ctx.owner) == "watching"
        issues = ctx.meta.get("has_issues")
        cells["R5"] = "pass" if not utility or issues is False else ("unknown" if issues is None else "fail")
    elif ctx.meta.get("delete_branch_on_merge") is None:
        cells["R5"] = "unknown"
    else:
        ok = (ctx.meta.get("default_branch") == "main" or kept_default) and \
            ctx.meta.get("delete_branch_on_merge") is True and (ctx.repo == ".github" or ctx.meta.get("has_issues") is True)
        cells["R5"] = "pass" if ok else "fail"
    # archived repositories are in scope (decision 6: unarchive, polish, re-archive), so R6 applies to them
    if ctx.tier in ("T2-R", "T3") or ctx.is_fork or \
            (ctx.meta.get("has_issues") is False and ctx.repo != ".github"):
        cells["R6"] = "n/a"
    elif not ctx.meta.get("labels"):
        cells["R6"] = "unknown"
    elif ctx.same_owner("AI-Ascension"):  # any spelling or former login (CQ-03)
        cells["R6"] = "pass" if any(lb["name"] == "dependencies" and lb["color"] == "0366d6" for lb in ctx.meta["labels"]) else "fail"
    else:
        ops, lg = labelsmod.plan(ctx.meta["labels"], rd, files=ctx.meta.get("files"),
                                 complete=ctx.meta.get("files_complete") is True,
                                 defaults=labelsmod.defaults_for(ctx.owner, ctx.repo, repo_dir=rd, meta=ctx.meta))
        cells["R6"] = "pass" if all(o["op"] == "skip" and not o.get("log") for o in ops) else "fail"
    readme = rd / "README.md" if rd else None
    if readme and readme.is_file():
        rl = readmelint.lint(ctx, readme)
        cells["R7"] = rl["result"]
        logs += rl.get("logs", [])
    else:
        cells["R7"] = "unknown" if not rd else "fail"
    if ctx.brand.owner_status(ctx.owner) == "t3" and not t3_signed_off(ctx.owner, ctx.repo):
        cells["R7"] = "hold"  # T3: no README change before co-owner sign-off (lint readme refuses)
    lic = ctx.meta.get("license")
    cells["R8"] = "pass" if lic or not ctx.public else "warn"
    if ctx.same_owner("CompleteTech-Skills") and ctx.det["type"] == "agent-skills":
        if rd:
            ok = all((rd / p).is_file() and hashlib.sha256((rd / p).read_bytes()).hexdigest() == h for p, h in LOGO_SHA.items())
            cells["R9"] = "pass" if ok else "fail"
        else:
            cells["R9"] = "unknown"
    else:
        cells["R9"] = "n/a"
    og = ctx.meta.get("uses_custom_og_image")
    cells["R10"] = ("unknown" if og is None else ("pass" if og else "fail")) if ctx.social_applicable() else "n/a"
    hpct = ctx.meta.get("health_percentage")
    if not ctx.public or ctx.meta.get("archived") or ctx.is_fork or ctx.det["type"] == "github-profile" or \
            ctx.tier not in ("T1", "T2"):
        cells["R11"] = "n/a"
    else:
        cells["R11"] = "unknown" if hpct is None else ("pass" if hpct == 100 else "fail")
    # decisions 12, 13 and 18: only watching-org forks are metadata only; the watching org's `.github` is checked like
    # any `.github`, and its other non-fork repositories are held until decided (RepoContext.watching_status)
    watching = ctx.watching_status()
    status = ctx.art_status()
    fstat = ctx.footer_status()
    if watching:
        cells.update(banner=_cell(watching), icon=_cell(watching), card=_cell(status["card"] or watching),
                     footer=_cell(watching))  # art_status keeps exempt:no-card for forks, backups, profiles
    elif not rd:
        cells.update(banner="unknown", icon="unknown", card="unknown", footer="unknown")
    else:
        text = readme.read_text(encoding="utf-8") if readme is not None and readme.is_file() else ""
        # R14: a preserve-list README is n/a only when q57 `pres` is "Leave them unchanged" (`preserve-list`)
        if text and ctx.preserve_unchanged() and readmemod.preserved(ctx, text) and "docs/images/banner.png" not in text:
            status["banner"] = status["banner"] or "exempt:preserve-banner"
        if status["banner"]:
            cells["banner"] = _cell(status["banner"])
        else:
            bl = pnglint.lint_banner(rd / "docs" / "images" / "banner.png")
            ok = bl["result"] in ("PASS", "INCOMPLETE") and "docs/images/banner.png" in text
            cells["banner"] = ("incomplete" if bl["result"] == "INCOMPLETE" else "pass") if ok else "fail"
            logs += bl.get("logs", [])
        icon = rd / "assets" / "icon.png"
        if status.get("icon"):
            # R13: n/a only for watching-org forks (handled above) and a placeholder org's `.github`; hold for T3/HOLD
            cells["icon"] = _cell(status["icon"])
        elif icon.is_file():
            try:
                im = Image.open(icon)
                ok = im.size == (1024, 1024) and im.mode == "RGBA" and icon.stat().st_size <= 300_000
            except OSError:
                ok = False
            cells["icon"] = "pass" if ok else "warn"
        else:
            cells["icon"] = "fail"
        card = rd / "docs" / "images" / "card.svg"
        if status["card"]:
            cells["card"] = _cell(status["card"])
        else:
            cells["card"] = "pass" if card.is_file() and svglint.lint_file("card", card)["result"] == "PASS" else "fail"
        if fstat:  # hold (`footer: hold`, T3) or n/a (`footer: false`); RepoContext.footer_status
            cells["footer"] = _cell(fstat)
        elif readme and readme.is_file():
            st, _ = footermod.check(ctx.brand, readme.read_text(encoding="utf-8"))
            cells["footer"] = "pass" if st == "pass" else "fail"
        else:
            cells["footer"] = "fail"
    # a banner with fewer than two chips is reported incomplete and is not done (decision 13: two to four chips)
    done = all(cells[c] in ("pass", "warn", "incomplete", "n/a") for c in COLUMNS) and cells["banner"] != "incomplete"
    if (rd / "README.md").is_file() if rd else False:
        if re.search(r"<!-- showcase:checklist:start -->.*- \[ \].*<!-- showcase:checklist:end -->",
                     (rd / "README.md").read_text(encoding="utf-8"), re.S):
            logs.append("checklist: open")
    row = {"repo": f"{ctx.owner}/{ctx.repo}", "type": ctx.det["type"], "variant": ctx.det["variant"], "cells": cells,
           "done": "yes" if done else "no", "logs": sorted(set(logs + ctx.logs))}
    from . import signoff
    rec = signoff.record_for(ctx.owner, ctx.repo)
    if rec is not None:  # only under --require-t3-signoff with a valid record: show which sign-off lifted the hold
        row["signoff_id"] = str(rec.get("id") or "")
        row["signoff_expires"] = str(rec.get("expires") or "")
    return row


def as_tsv(r: dict, header: bool = False) -> str:
    cols = ["owner/repo", "type", "variant", *COLUMNS, "done"]
    line = "\t".join([r["repo"], r["type"], r["variant"], *[r["cells"][c] for c in COLUMNS], r["done"]])
    return ("\t".join(cols) + "\n" if header else "") + line


def as_md(r: dict, header: bool = False) -> str:
    cols = ["owner/repo", "type", "variant", *COLUMNS, "done"]
    vals = [r["repo"], r["type"], r["variant"], *[r["cells"][c] for c in COLUMNS], r["done"]]
    head = ("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n") if header else ""
    return head + "| " + " | ".join(vals) + " |"
