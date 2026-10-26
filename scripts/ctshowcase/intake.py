"""Intake for repositories created after the run (COVERAGE OPS-06, RP-13; decisions/POLICY.md "Repos created after the
run"). Read-only toward GitHub: plans leave as change records and scripts/writer.py jobs.

- `new OWNER/NAME --type T`: the `gh repo create OWNER/NAME --template <template> --private` writer job, then `adopt`.
- `adopt OWNER/REPO`: what "Use this template" does not carry, as Phase 3 change records and writer jobs: the §10.1
  settings, the §5.6 topics, the §6 label passes, private vulnerability reporting and Dependabot alerts on public
  non-forks, plus a UI checklist (social preview, About sidebar).
- `doctor --estate`: repositories that are not in `registry/estate.yaml`, classified with POLICY.md into
  `NEW_PROPOSALS.yaml` entries (never acted on), and template-managed files that drifted from the current template.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import STANDARD
from .errors import NeedsInput, Refused, ShowcaseError

TEMPLATE_REPO = "CompleteTech-LLC/completetech-repo-template"
# files the template owns: a repository born from it keeps them byte-identical until a bump PR updates them
TEMPLATE_MANAGED = (".github/workflows/showcase.yml", ".github/showcase/LICENSE-POLICY.md", ".editorconfig",
                    ".gitattributes")
PHASE = "3.2"
INTAKE_SOURCE = "showcase.py doctor --estate"


def _jid(*parts) -> str:
    from .content import job_id
    return job_id(*parts)


def _job(jid: str, argv: list[str], full: str, note: str, approval_id: str | None, kind: str = "repo-settings",
         phase: str = PHASE) -> dict:
    from .org import job
    return job(jid, phase, kind, argv, repo=full, note=note, approval_id=approval_id)


# ------------------------------------------------------------------------------------------------------------------
# adopt
# ------------------------------------------------------------------------------------------------------------------
def adopt(ctx, resolver=None, *, approval_id: str | None = None, fresh: bool = False, org_defaults=None) -> dict:
    """Phase 3 change records and writer jobs for one repository. `fresh` marks a repository `new` has just planned:
    it has no wiki, Projects or Discussions yet and its live labels are unknown until it exists. `org_defaults` is a
    checkout or the metadata JSON of the owner's `.github` repository, which §6.4 rule 0 also reads."""
    from . import labels as labelsmod
    from . import records
    from . import topics as topicsmod
    from .content import sidebar_plan, social_job
    from .org import label_ops_argv
    owner, repo = ctx.owner, ctx.repo
    status = ctx.brand.check_owner(owner)  # excluded, HOLD and T3 owners refuse (exit 2)
    if ctx.style.get("hold") or (resolver.family_hold(owner) if resolver else False):  # as showcase.cmd_adopt refuses
        raise Refused(f"{owner} family is on hold: adopt plans nothing for it", log="hold")
    full = f"{resolver.canonical(owner) if resolver else owner}/{repo}"
    meta, det = ctx.meta, ctx.det
    fork, archived, private = bool(meta.get("fork")), bool(meta.get("archived")), not ctx.public
    watching = status == "watching"
    utility = ctx.tier in ("T2-R",) or watching
    recs, jobs, pending, checklist, logs = [], [], [], [], list(ctx.logs)
    sid = full.replace("/", "__")
    if archived:
        logs.append("archived (decision 6: apply in the approved polish-archived cycle: unarchive, polish, re-archive)")
    # §10.1 settings ---------------------------------------------------------------------------------------------
    want: dict = {}
    if not fork and repo != ".github":
        want["has_issues"] = True
    elif fork and utility:
        want["has_issues"] = False  # forks in the watching and archive orgs
    if not fork:
        want["delete_branch_on_merge"] = True
    if fresh:  # a repository created from the template has no wiki, Projects board or Discussions yet
        want.update(has_wiki=False, has_projects=False, has_discussions=False)
    else:
        pending += [{"why": "has_wiki=false only when `git ls-remote` of the .wiki.git reports none (§10.1)",
                     "read": ["git", "ls-remote", f"https://github.com/{full}.wiki.git"]},
                    {"why": "has_projects=false unless projectsV2 totalCount > 0; has_discussions=false unless "
                            "discussions totalCount > 0 (§10.1)",
                     "read": ["gh", "api", "graphql", "-f", "query={repository(owner:\"%s\",name:\"%s\"){projectsV2(first:1)"
                              "{totalCount} discussions(first:1){totalCount}}}" % (full.split("/")[0], repo)]}]
    patch = {k: v for k, v in want.items() if meta.get(k) is not v}
    if patch:
        argv = ["gh", "api", "-X", "PATCH", f"repos/{full}"] + [a for k, v in patch.items()
                                                                 for a in ("-F", f"{k}={str(v).lower()}")]
        jobs.append(_job(_jid("p3", "settings", sid), argv, full, "§10.1 settings baseline (RP-13: a template-born "
                         "repository gets none of them).", approval_id))
        recs.append(records.record(owner, repo, "settings", "settings", {k: meta.get(k) for k in patch}, patch, "§10.1"))
    if (meta.get("default_branch") or "main") != "main" and not fork:
        checklist.append(f"default branch is {meta.get('default_branch')}: propose `rename-default-branch` in "
                         "NEW_PROPOSALS.yaml (§10.1, q52); never renamed by adopt")
    # §5.6 topics ------------------------------------------------------------------------------------------------
    tp = topicsmod.merge(ctx)
    logs += tp["logs"]
    if not tp["equal_as_set"] and tp["proposed"]:
        argv = ["gh", "api", "-X", "PUT", f"repos/{full}/topics"] + [a for x in tp["proposed"] for a in ("-f", f"names[]={x}")]
        jobs.append(_job(_jid("p3", "topics", sid), argv, full, "§5.6 topics (full ordered list; PUT replaces the set).",
                         approval_id, kind="topics"))
        recs.append(records.record(owner, repo, "topics", "topics", tp["current"], tp["proposed"], "§5.6 merge"))
    # §6 labels --------------------------------------------------------------------------------------------------
    if fork or archived or ctx.tier in ("T2-R", "T3") or watching:
        logs.append("labels:n/a")
    elif (resolver.same(owner, "AI-Ascension") if resolver else owner.lower() == "ai-ascension"):  # any spelling, CQ-03
        logs.append("labels:ai-ascension (keeps its labels.yml; R6 is only `dependencies`)")
    elif fresh or not meta.get("labels"):
        # unknown live labels: a missing key, or the [] that normalize and a failed labels GET leave, is never planned
        # against (it would create every standard label beside GitHub's defaults and rename none)
        pending.append({"why": "labels: plan against the live labels (none were captured; org default labels may "
                               "already seed them)", "next": f"showcase.py meta --from-gh {full}, then adopt again or "
                               "labels --plan --jobs FILE"})
        if not fresh:
            logs.append("needs-input:labels")
    else:
        ops, lg = labelsmod.plan(meta.get("labels") or [], ctx.repo_dir, files=meta.get("files"),
                                 complete=meta.get("files_complete") is True,
                                 defaults=labelsmod.defaults_for(owner, repo, repo_dir=ctx.repo_dir, meta=meta,
                                                                 path=org_defaults, resolver=resolver))
        logs += lg
        unchecked = [o for o in ops if o.get("log") == labelsmod.NEEDS_CHECKOUT]
        if unchecked:  # §6.4 rule 0 could not run: the rename stays out of the jobs until a checkout is read
            pending.append({"why": "labels: renames held until §6.4 rule 0 reads " +
                                   ", ".join(sorted({f for o in unchecked for f in o["check_files"]})) + " (" +
                                   ", ".join(f"{o['name']} -> {o['new_name']}" for o in unchecked) + ")",
                            "next": f"showcase.py --repo-dir <checkout of {full}> adopt {full} --org-defaults "
                                    f"<checkout of {full.split('/')[0]}/.github> (or labels --plan)"})
        writes = [o for o in ops if o["op"] != "skip"]
        for argv in label_ops_argv(full, writes):  # ids from the operation, never its position
            new = f"-to-{argv[argv.index('--name') + 1]}" if "--name" in argv else ""
            jid = _jid("p3", "label", sid, argv[2], argv[3] + new,
                       hashlib.sha256(json.dumps(argv, ensure_ascii=False).encode()).hexdigest()[:8])
            jobs.append(_job(jid, argv, full, "§6.3 pass A renames before pass B "
                             "creates; never --force, never a delete.", approval_id, kind="labels"))
        recs += [records.record(owner, repo, "label", o["name"], o["name"], o, o["rule"]) for o in writes]
    # security baseline on public non-fork T1/T2 repositories ----------------------------------------------------
    if not private and not fork and str(ctx.tier).startswith(("T1", "T2")) and ctx.tier != "T2-R" and not watching:
        for name, path, note in (("pvr", "private-vulnerability-reporting", "Private vulnerability reporting (§10.1, SEC-04)."),
                                 ("vuln-alerts", "vulnerability-alerts", "Dependabot alerts (§10.1); alerts, not version "
                                                                         "updates.")):
            jobs.append(_job(_jid("p3", name, sid), ["gh", "api", "-X", "PUT", f"repos/{full}/{path}"], full, note,
                             approval_id, kind="security"))
            recs.append(records.record(owner, repo, "security", path, "unknown", "enabled", "§10.1"))
    elif private:
        logs.append("security:private (PVR and Dependabot alerts apply to public non-forks; re-run adopt if it goes "
                    "public)")
    # UI checklist: social preview and About sidebar ---------------------------------------------------------------
    sj = social_job(ctx, resolver, "assets/social-preview.png")
    if sj:
        jobs.append(sj)
        checklist.append("social preview: `showcase.py content social` renders assets/social-preview.png; the browser "
                         "job uploads it (R10)")
    facts = {k: meta[k] for k in ("releases", "deployments", "packages", "environments", "has_pages") if k in meta}
    if not fork:
        sb = sidebar_plan(meta, facts, resolver=resolver)
        if sb.get("job"):
            jobs.append(sb["job"])
        checklist.append("About sidebar: Releases, Packages and Deployments shown only where they exist (decision 7; "
                         "`showcase.py content sidebar --facts FILE` when the counts are not in the metadata)")
    if not meta.get("description"):
        logs.append("needs-input:description")
        checklist.append("description: write it from the §4.2 template, then `showcase.py describe --text ...`")
    return {"command": "adopt", "owner": full.split("/")[0], "repo": repo, "type": det["type"], "variant": det["variant"],
            "result": "ok", "records": recs, "jobs": jobs, "pending": pending, "checklist": checklist,
            "logs": sorted(set(logs))}


# ------------------------------------------------------------------------------------------------------------------
# new
# ------------------------------------------------------------------------------------------------------------------
def name_ok(name: str) -> bool:
    from .detect import standard
    n = standard("naming")
    if not (re.match(n["n1"], name) and re.match(n["n2"], name)) or re.search(n["n4_filler"], name):
        return False
    return not ("." in name and not re.search(n["n1_dot_suffix"], name))


def new_plan(brand, slug: str, type_: str, *, template: str = TEMPLATE_REPO, description: str = "",
             resolver=None, approval_id: str | None = None) -> dict:
    """`new OWNER/NAME --type T`: the create job (from the template, private), then `adopt` on the planned repository."""
    from .context import RepoContext
    from .detect import standard
    from .meta import normalize
    m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+)", slug or "")
    if not m:
        raise ShowcaseError("new needs OWNER/NAME", log="usage")
    owner, name = m.group(1), m.group(2)
    status = brand.check_owner(owner)
    if status == "watching":
        raise ShowcaseError(f"{owner} is the watching org: it holds forks only, never new repositories", log="exempt")
    if resolver is not None and resolver.is_placeholder(owner):
        raise ShowcaseError(f"{owner} is a placeholder org (never written)", log="exempt")
    if type_ not in set(standard("topics")["type_topics"]):
        raise ShowcaseError(f"--type {type_!r} is not a §5.4 type", log="usage")
    if not name_ok(name):
        raise ShowcaseError(f"{name} fails the naming rules N1-N4 (lowercase kebab-case, no filler suffix)", log="usage")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+", template):
        raise ShowcaseError("--template must be OWNER/REPO", log="usage")
    full = f"{resolver.canonical(owner) if resolver else owner}/{name}"
    argv = ["gh", "repo", "create", full, "--template", template, "--private"]
    if description:
        argv += ["--description", description]
    create = _job(_jid("p3", "create", full.replace("/", "__")), argv, full,
                  "Create from the CompleteTech template, private (OPS-06). Push `main` first; never change visibility.",
                  approval_id, kind="create-repo")
    meta = normalize({"owner": owner, "repo": name, "visibility": "private", "default_branch": "main",
                      "description": description, "topics": [], "is_template": False, "fork": False})
    ctx = RepoContext(brand, meta, None, type_override=type_)
    res = adopt(ctx, resolver, approval_id=approval_id, fresh=True)
    res.update(command="new", template=template, jobs=[create] + res["jobs"])
    res["checklist"] = ["after creation: the template's Showcase workflow bootstraps the README for this type "
                        "(`readme --bootstrap`); then work through its setup checklist"] + res["checklist"]
    return res


# ------------------------------------------------------------------------------------------------------------------
# doctor --estate
# ------------------------------------------------------------------------------------------------------------------
def _registered(resolver) -> set[str]:
    reg = resolver.registry
    out = set()
    for key, row in (reg.get("orgs") or {}).items():
        for n in (row or {}).get("final_repos") or []:
            out.add(resolver.slug(f"{key}/{n}").lower())
            before = resolver.repo_before(f"{key}/{n}")
            if before:
                out.add(resolver.slug(before[0]).lower())
    return out


def classify(meta: dict, brand, resolver) -> list[dict]:
    """POLICY.md rules for one unregistered repository: a list of proposals (kind, reason). Never an action."""
    from .detect import standard
    repo = meta["repo"]
    n = standard("naming")
    out = []

    def add(kind, reason, **extra):
        out.append({"kind": kind, "reason": reason, **extra})
    files = meta.get("files")
    if repo == ".github":
        add("keep", "An org `.github` repo is kept (POLICY).")
        return out
    if files == [] or meta.get("size") == 0:
        add("delete", "Empty repository: delete only if the user approves (POLICY: delete if empty).")
        return out
    parent = meta.get("parent") or {}
    if meta.get("fork"):
        powner = (parent.get("full_name") or "/").split("/")[0]
        own_parent = bool(powner) and brand.owner_status(powner) is None and brand.org(powner).get("known")
        ahead = meta.get("ahead_by")
        if own_parent:
            add("merge", f"Fork of the user's own {parent.get('full_name')}: pick one canonical home; the other org lists "
                         "it through also_in (POLICY).")
        elif ahead == 0:
            add("move", "Fork with no commits ahead of upstream: move to the watching org (POLICY).",
                target_owner=resolver.canonical("romgenie-following-repos") if resolver else "romgenie-following-repos")
        elif ahead is None:
            add("keep", "Fork whose commits ahead are unknown: capture `ahead_by` (meta --from-gh) before deciding.",
                needs="ahead_by")
        else:
            add("keep", f"Fork with {ahead} own commits: keep it in its product org (POLICY; README per q27).")
    elif re.search(n["n4_backup"], repo) or re.search(r"(?i)(^|[-_])(backup|bak|old|legacy|copy)([-_]|$)", repo):
        add("archive", "Backup or legacy copy: move to the archive org and archive it there; when in doubt, archive "
                       "(POLICY).", target_owner=resolver.canonical("romgenie-archive-repostiory") if resolver else
            "romgenie-archive-repostiory")
    else:
        add("keep", "Repository with the user's own work: keep and dress it (Phases 3 to 6 after approval).")
    if not name_ok(repo) and not meta.get("fork"):
        new = re.sub(r"[^a-z0-9]+", "-", repo.lower()).strip("-")
        add("rename", "Typo, leading underscore or digit, or inconsistent casing: rename to kebab-case (POLICY).",
            new_name=new)
    if (meta.get("default_branch") or "main") != "main":
        add("rename-default-branch", f"Default branch is {meta.get('default_branch')}: forks keep upstream's; "
                                     "feature-named defaults on uncoupled repos rename to main (POLICY, q52).")
    if meta.get("visibility") == "private":
        for p in out:
            p.setdefault("note", "Private: never made public.")
    return out


def _checkout_slug(d: Path) -> str | None:
    from .meta import from_repo_dir
    m = from_repo_dir(d)
    if m.get("owner") and m.get("repo"):
        return f"{m['owner']}/{m['repo']}"
    if "__" in d.name:
        return d.name.replace("__", "/", 1)
    return None


def drift(template_dir: Path, checkouts: Path) -> tuple[list[dict], list[str]]:
    """Template-managed files in each checkout that differ from (or are missing against) the current template."""
    rows, logs = [], []
    want = {}
    for rel in TEMPLATE_MANAGED:
        p = template_dir / rel
        if p.is_file():
            want[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            logs.append(f"template-missing:{rel}")
    for d in sorted(x for x in checkouts.iterdir() if x.is_dir()):
        if not (d / ".github" / "workflows" / "showcase.yml").is_file():
            continue  # not template-born (or it removed the workflow): nothing the template manages here
        slug = _checkout_slug(d) or d.name
        for rel, sha in want.items():
            p = d / rel
            if not p.is_file():
                rows.append({"repo": slug, "file": rel, "status": "missing"})
            elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
                rows.append({"repo": slug, "file": rel, "status": "differs"})
    return rows, logs


def estate_doctor(brand, resolver, metas: list[dict], *, template_dir: str | None = None, checkouts: str | None = None,
                  out: str | None = None) -> dict:
    from .meta import normalize
    registered = _registered(resolver)
    if not registered:
        raise NeedsInput("registry", "the registry lists no final_repos; pass --registry")
    unregistered, proposals, logs = [], [], []
    for raw in metas:
        try:
            m = normalize(raw)
        except ShowcaseError:
            continue
        owner = m["owner"]
        if brand.owner_status(owner) == "excluded" or (resolver and resolver.is_placeholder(owner)):
            continue
        full = resolver.slug(f"{owner}/{m['repo']}")
        if full.lower() in registered:
            continue
        unregistered.append(full)
        st = brand.owner_status(owner)
        for p in classify(m, brand, resolver):
            entry = {"owner": full.split("/")[0], "repo": m["repo"], **p, "source": INTAKE_SOURCE, "std": STANDARD,
                     "status": "proposed"}
            if st == "t3":
                entry["note"] = "T3 org: co-owner sign-off first."
            proposals.append(entry)
    for i, p in enumerate(proposals, 1):
        p["id"] = f"intake-{i:03d}"
    rows = []
    if template_dir and checkouts:
        rows, dl = drift(Path(template_dir), Path(checkouts))
        logs += dl
    elif template_dir or checkouts:
        raise ShowcaseError("template drift needs both --template-dir and --checkouts", log="usage")
    else:
        logs.append("drift:skipped (pass --template-dir and --checkouts)")
    if out:
        write_proposals(Path(out), proposals)
    return {"command": "doctor", "action": "estate", "result": "proposals" if proposals or rows else "clean",
            "unregistered": sorted(unregistered), "proposals": proposals, "drift": rows,
            "bump": sorted({r["repo"] for r in rows}), "out": out, "logs": sorted(set(logs))}


def write_proposals(path: Path, proposals: list[dict]) -> None:
    """Merge into NEW_PROPOSALS.yaml: entries other runs or people wrote stay; this command's own entries are replaced."""
    import yaml
    existing = []
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        existing = data.get("proposals") if isinstance(data, dict) else data
        existing = [e for e in existing or [] if not (isinstance(e, dict) and e.get("source") == INTAKE_SOURCE)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"proposals": existing + proposals}, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
