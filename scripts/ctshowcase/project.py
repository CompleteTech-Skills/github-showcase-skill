"""GitHub Projects module (decision 23; STANDARD §13; audit/research/orgs-and-projects.md §3–§4).

`showcase.py project {capture-query,normalize,copy-plan,readme,lint,estate-plan}`. Read-only toward GitHub: it prints
the capture query, normalizes a captured board into the template spec, checks a board against the standard, writes
the board README, and plans writer jobs (`{id, phase, kind, repo|org, approval_id?, argv, note}`; `browser` jobs for
UI-only settings). Rules it never bends: no `--drafts` and no items in a copy; nothing is deleted (projects, fields,
items, views, workflows); every mutation is printed inline (`-f query='mutation …'` with literal values or `-f`
variables); only read queries load from a file (`-F query=@file`); Pick-Your-AI (T3) is read, never changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from . import STANDARD
from .errors import CHECK_FAILED, OK, NeedsInput, Refused, ShowcaseError
from .resolver import Resolver, read_command

PHASE = "6.3"
USER_LOGIN = "CompleteDotTech"
REFERENCE = ("Pick-Your-AI", 1)
TEMPLATE_OWNER = "CompleteTech-LLC"
TEMPLATE_TITLE = "TEMPLATE — Workstream Portfolio"
ESTATE_TITLE = "CompleteTech — Estate"
STEWARD = ("Timothy Wayne Gregg", "Timothy.Gregg@complete.tech")
SHORT_MAX = 120
ANCHOR, CYCLE_DAYS, CYCLES = "2026-11-02", 14, 3
DESC = {"org": "{name} workstreams: what is in flight, what is next and what has shipped, updated weekly.",
        "template": "Template for CompleteTech organization workstream boards: fields, views and workflows only, no items.",
        "estate": "Cross-organization roll-up of CompleteTech LLC initiatives, health and target dates, updated weekly."}

# §13.4 workstream kinds: the same eight colours in every org
KINDS = [("Product", "Product / Build", "BLUE"), ("Research", "Research / Discovery", "PURPLE"),
         ("Growth", "Growth / Marketing / Community", "PINK"), ("Revenue", "Revenue / Sales / Partnerships", "ORANGE"),
         ("Content", "Content / Docs / Education", "GREEN"), ("Ops", "Ops / Infra / Security / Admin", "GRAY"),
         ("Risk", "Risk / Compliance / Incidents", "RED"), ("Experiments", "Experiments / Ideas", "YELLOW")]
KIND_COLOR = {w.lower(): c for _, label, c in KINDS for w in label.split(" / ")}

# §13.3 field schema (the capture wins where the reference board already has a field)
FIELDS = [
    {"name": "Status", "dataType": "SINGLE_SELECT", "required": True, "builtin": True, "options": [
        ("Backlog", "GRAY", "Captured, not committed"), ("Ready", "BLUE", "Specified; can start"),
        ("In progress", "YELLOW", "Actively worked"), ("In review", "PURPLE", "PR open or being verified"),
        ("Blocked", "RED", "Waiting on a dependency; blocker noted in the issue"),
        ("Done", "GREEN", "Merged, shipped or closed")]},
    {"name": "Priority", "dataType": "SINGLE_SELECT", "required": True, "options": [
        ("Urgent", "RED", "This cycle; drop other work"), ("High", "ORANGE", "This or next cycle"),
        ("Medium", "YELLOW", "This quarter"), ("Low", "GRAY", "When there is room")]},
    {"name": "Size", "dataType": "SINGLE_SELECT", "required": True, "options": [
        ("XS", "GRAY", "1 hour or less"), ("S", "GREEN", "Half a day or less"), ("M", "BLUE", "2 days or less"),
        ("L", "ORANGE", "1 week or less"), ("XL", "RED", "Too big; split into sub-issues")]},
    {"name": "Estimate", "dataType": "NUMBER", "required": False},
    {"name": "Iteration", "dataType": "ITERATION", "required": True},
    {"name": "Start date", "dataType": "DATE", "required": True},
    {"name": "Target date", "dataType": "DATE", "required": True},
    {"name": "Workstream", "dataType": "SINGLE_SELECT", "required": True,
     "options": [(short, color, f"[{short}] {label}") for short, label, color in KINDS]},
    {"name": "Tags", "dataType": "MULTI_SELECT", "required": False},
]

# §13.5 views, in tab order. REST bodies use integer field ids; anything else is a browser step.
VIEWS = [
    {"name": "Workstream Overview", "layout": "board", "filter": "", "vertical_group_by": ["Status"],
     "group_by": ["Workstream"], "sort_by": [("Priority", "asc")],
     "visible_fields": ["Title", "Assignees", "Priority", "Size", "Target date", "Repository", "Sub-issues progress"],
     "ui": ["Set the column limit on 'In progress' to 3.", "Field sum: Count (plus Estimate)."],
     "answers": "What is moving in each workstream?"},
    {"name": "Roadmap", "layout": "roadmap", "filter": "type:Initiative,Feature -status:Done", "group_by": ["Workstream"],
     "sort_by": [("Target date", "asc")],
     "ui": ["Dates: Start date to Target date.", "Markers: Iterations and Milestones.", "Zoom: Quarter."],
     "answers": "What lands when?"},
    {"name": "Priorities", "layout": "table", "filter": "-status:Done", "group_by": ["Priority"],
     "sort_by": [("Target date", "asc")], "ui": ["Slice by Workstream.", "Field sums: Count and Estimate."],
     "answers": "What matters most right now?"},
    {"name": "Current cycle", "layout": "board", "filter": "iteration:@current", "vertical_group_by": ["Status"],
     "sort_by": [("Priority", "asc")], "ui": ["Set a column limit on 'In progress'.", "Field sum: Estimate."],
     "answers": "What is committed for this two-week cycle?"},
    {"name": "Backlog", "layout": "table", "filter": "status:Backlog,Ready", "group_by": ["Workstream"],
     "sort_by": [("Priority", "asc")], "ui": ["Slice by Priority.", "Turn Show hierarchy on."],
     "answers": "What is captured but not started?"},
    {"name": "My items", "layout": "table", "filter": "assignee:@me -status:Done", "group_by": ["Status"],
     "sort_by": [("Priority", "asc"), ("Target date", "asc")], "ui": [], "answers": "What is assigned to me?"},
    {"name": "Shipped", "layout": "table", "filter": "status:Done updated:>=@today-30d", "group_by": ["Workstream"],
     "sort_by": [("Updated", "desc")], "ui": [], "answers": "What finished in the last 30 days?"},
]
# §13.6 built-in workflows: (match words, expected on in an org board, expected on in the template)
WORKFLOWS = [("item added", True, True), ("item reopened", True, True), ("item closed", True, True),
             ("pull request merged", True, True), ("auto-archive", True, True), ("auto-add", True, False)]
WORKFLOW_UI = {"item added": "When: Item added to project. Set: Status to Backlog.",
               "item reopened": "When: Item reopened. Set: Status to In progress.",
               "item closed": "When: Item closed. Set: Status to Done.",
               "pull request merged": "When: Pull request merged. Set: Status to Done.",
               "auto-archive": "Filter: is:closed updated:<@today-1m (it must archive items not updated in the last month).",
               "auto-add": "Filter: is:issue,pr is:open on the org's main repository (Free plans allow one rule)."}
# §13.10 Estate extra fields and views
ESTATE_FIELDS = [
    {"name": "Org", "dataType": "SINGLE_SELECT"},
    {"name": "Stream kind", "dataType": "SINGLE_SELECT",
     "options": [(label, color, f"[{short}] {label}") for short, label, color in KINDS]},
    {"name": "Workstream", "dataType": "TEXT"},
    {"name": "Health", "dataType": "SINGLE_SELECT", "options": [
        ("On track", "GREEN", "The org board's latest status is on track"), ("At risk", "YELLOW", "Latest status: at risk"),
        ("Off track", "RED", "Latest status: off track"), ("Inactive", "GRAY", "Latest status: inactive"),
        ("Complete", "PURPLE", "Latest status: complete")]},
]
TIER_COLOR = {"T1": "BLUE", "T2": "GREEN", "T2-R": "GRAY", "T3": "YELLOW"}
ESTATE_VIEWS = [
    {"name": "Estate Overview", "layout": "table", "filter": "", "group_by": ["Org"], "sort_by": [("Priority", "asc")],
     "ui": [], "answers": "What is in flight in each organization?"},
    {"name": "Health", "layout": "board", "filter": "", "vertical_group_by": ["Health"], "sort_by": [("Priority", "asc")],
     "ui": [], "answers": "Which organizations are on track?"},
    {"name": "Estate Roadmap", "layout": "roadmap", "filter": "-status:Done", "group_by": ["Org"],
     "sort_by": [("Target date", "asc")], "ui": ["Dates: Start date to Target date.", "Zoom: Quarter."],
     "answers": "What lands when, across the estate?"},
    {"name": "This cycle", "layout": "table", "filter": "iteration:@current -status:Done", "group_by": ["Org"],
     "sort_by": [("Priority", "asc")], "ui": [], "answers": "What is committed this cycle?"},
    {"name": "At risk", "layout": "table", "filter": 'health:"At risk","Off track"', "group_by": ["Org"],
     "sort_by": [("Target date", "asc")], "ui": [], "answers": "What needs attention?"},
    {"name": "My items", "layout": "table", "filter": "assignee:@me -status:Done", "group_by": ["Status"],
     "sort_by": [("Priority", "asc")], "ui": [], "answers": "What is assigned to me?"},
]
GQL_LAYOUT = {"board": "BOARD_LAYOUT", "roadmap": "ROADMAP_LAYOUT", "table": "TABLE_LAYOUT"}


# =====================================================================================================
# helpers
# =====================================================================================================
def _q(s) -> str:
    """A GraphQL string literal (JSON escapes are valid GraphQL escapes)."""
    return json.dumps(str(s), ensure_ascii=False)


# review question ids (decisions/APPROVED_ACTIONS.yaml `question_approvals`, scripts/build_approvals.py q41) that approve a
# `gh project copy`; scripts/writer.py refuses a create-project job whose approval_id is not approved there
CREATE_APPROVAL = {"org": "q41.orgs", "estate": "q41.estate"}


def _job(jid: str, kind: str, argv: list[str] | None, owner: str, note: str, approval_id: str | None = None, **extra) -> dict:
    j = {"id": jid, "phase": PHASE, "kind": kind, "org": owner}
    if approval_id:
        j["approval_id"] = approval_id
    if argv is not None:
        j["argv"] = argv
    j["note"] = note
    j.update(extra)
    return j


def _browser(jid: str, owner: str, url: str, steps: list[str], ui_action: str, note: str) -> dict:
    return _job(jid, "browser", None, owner, note, ui_action=ui_action, url=url, steps=steps)


def _gql_job(jid: str, owner: str, mutation: str, note: str, variables: dict | None = None, **extra) -> dict:
    argv = ["gh", "api", "graphql", "-f", f"query={mutation}"]
    for k, v in (variables or {}).items():
        argv += ["-f", f"{k}={v}"]
    return _job(jid, "project", argv, owner, note, **extra)


def is_user(owner: str) -> bool:
    return owner in ("@me", USER_LOGIN) or owner.lower() == USER_LOGIN.lower()


def project_url(owner: str, number) -> str:
    base = f"https://github.com/users/{USER_LOGIN}" if is_user(owner) else f"https://github.com/orgs/{owner}"
    return f"{base}/projects/{number}"


def _slug(owner: str) -> str:
    return "me" if is_user(owner) else owner


def _gate_target(resolver: Resolver | None, owner: str, *, allow_t3: bool = False) -> str:
    """Targets of a write: never T3 without sign-off, never excluded or HOLD. Returns the resolved login."""
    if is_user(owner):
        return "@me"
    if resolver is None:
        return owner
    st = resolver.owner_status(owner)
    if st == "excluded":
        raise Refused(f"{owner} is out of scope; no project writes", log="exempt")
    if st == "hold" or resolver.family_hold(owner):
        raise Refused(f"{owner} is on HOLD", log="hold")
    if st == "t3" and not allow_t3:
        raise Refused(f"{owner} is T3: reading its project is fine, changing anything needs co-owner sign-off",
                      log="t3-signoff")
    if st == "t3":  # registers the grant so writer jobs carry signoff_id; refuses t3-signoff:<why>
        from . import signoff
        signoff.require(owner, None, resolver.aliases(owner))
    return resolver.canonical(owner)


# =====================================================================================================
# capture-query
# =====================================================================================================
REFERENCE_BOARD = ("pick-your-ai", 1)  # §13: the Workstream Overview board every org board is copied from


def capture_query(owner: str, number: int, *, rel_to: Path | None = None) -> dict:
    """The read-only capture for OWNER/NUMBER (§4.1): GraphQL primary, REST for integer field ids, gh as a cross-check."""
    if not re.match(r"^[A-Za-z0-9-]+$|^@me$", owner or "") or int(number) < 1:
        raise ShowcaseError("capture-query needs --owner LOGIN and --number N", log="usage")
    user = is_user(owner)
    login = USER_LOGIN if owner == "@me" else owner
    base = f"users/{login}" if user else f"orgs/{owner}"
    # the reference board (Pick-Your-AI/1) is saved RAW where scripts/writer.py reads its node ids (PROJECT_CAPTURE);
    # its normalized spec goes beside it, so the writer's T3 node-id check sees every id the capture returned
    ref = (owner.lower(), int(number)) == REFERENCE_BOARD
    name = "workstream-overview" if ref else re.sub(r"[^a-z0-9]+", "-", f"{_slug(owner)}-{number}".lower())
    gql = read_command("project_capture_user" if user else "project_capture", rel_to=rel_to,
                       **({"login": login} if user else {"org": owner}), number=int(number))
    capture_out = f"registry/projects/{name}.template.json" if ref else f"registry/projects/{name}.capture.json"
    spec_out = f"registry/projects/{name}.spec.json"
    reads = [{"name": "graphql", "argv": gql, "out": capture_out},
             {"name": "rest-project", "argv": ["gh", "api", f"{base}/projectsV2/{number}"],
              "out": f"registry/projects/{name}.rest-project.json"},
             {"name": "rest-fields", "argv": ["gh", "api", "--paginate", f"{base}/projectsV2/{number}/fields"],
              "out": f"registry/projects/{name}.rest-fields.json"},
             {"name": "cross-check", "argv": ["gh", "project", "field-list", str(number), "--owner", owner, "--format",
                                              "json", "--limit", "100"], "out": None}]
    return {"command": "project", "action": "capture-query", "owner": owner, "number": int(number), "result": "ok",
            "query": (Path(__file__).parent / "queries" / ("project_capture_user.graphql" if user else
                                                          "project_capture.graphql")).read_text(encoding="utf-8"),
            "reads": reads, "screens": f"state/screens/projects/{name}/",
            "mkdir": ["registry/projects", f"state/screens/projects/{name}"],
            "normalize": f"project normalize --capture {capture_out} --rest-fields registry/projects/{name}.rest-fields.json "
                         f"--out {spec_out}",
            "note": "Read-only; never captures items. Screenshot every view, the workflows page, insights and settings "
                    "in the browser (UI-only settings have no API read).", "logs": []}


# =====================================================================================================
# normalize: captured JSON -> template spec (§3 / STANDARD §13)
# =====================================================================================================
def _project_node(capture: dict) -> dict:
    d = capture.get("data", capture) if isinstance(capture, dict) else {}
    for k in ("organization", "user"):
        if isinstance(d.get(k), dict) and d[k].get("projectV2") is not None:
            return d[k]["projectV2"]
    if "projectV2" in d:
        return d["projectV2"]
    if "fields" in d or "views" in d or "title" in d:
        return d
    raise ShowcaseError("not a project capture (expected data.organization.projectV2 or data.user.projectV2)", log="usage")


def _names(conn) -> list[str]:
    return [n.get("name") for n in (conn or {}).get("nodes") or [] if n and n.get("name")]


def short_description_checks(text: str, limit: int = SHORT_MAX, names: tuple = ()) -> list[dict]:
    """§13.2: one sentence ending with a period, at most 120 characters, no emoji or dash, exact brand strings.
    `names` (display names such as "Northwind Trading Co.") are masked for the one-sentence rule."""
    from .describe import checks
    from .detect import standard
    masked = text or ""
    for n in names:
        if n:
            masked = masked.replace(n, "Name")
    base = {c["rule"]: c for c in checks(masked, slug="project", type_="other", has_brand_assets=None)}
    if not (text or "").strip():  # one clear note, not "0 > 120" plus empty sub-rule spans
        return [{"rule": "D1", "result": "fail", "span": "empty (set the §13.2 short description)"}]
    out = [{"rule": "D1", "result": "pass" if len(text) <= limit else "fail",
            **({"span": f"{len(text)} > {limit}"} if len(text) > limit else {})}]
    out += [base[r] for r in ("D2", "D3", "D6") if r in base]
    bad = [b for b in standard("descriptions").get("brand_fixes", {}) if b in (text or "")]
    out.append({"rule": "B2", "result": "fail" if bad else "pass", **({"span": bad[0]} if bad else {})})
    out.append({"rule": "P0", "result": "fail" if re.search(r"[{}]|\bTODO\b|\bTBD\b", text or "") else "pass"})
    return out


def text_checks(text: str) -> list[str]:
    """README rules: no emoji, no leftover braces or placeholders."""
    from .describe import _EMOJI
    errs = []
    if _EMOJI.search(text or ""):
        errs.append("emoji")
    if re.search(r"\{[^}\n]*\}", text or ""):
        errs.append("placeholder-braces")
    # TODO and TBD in capitals only: "Todo" is GitHub's default Status option, which a README documents by name
    if re.search(r"\b(TODO|TBD)\b", text or "") or re.search(r"\blorem ipsum\b", text or "", re.I):
        errs.append("placeholder-text")
    return errs


def _kind_of(option: dict) -> str | None:
    m = re.match(r"^\[([^\]]+)\]", option.get("description") or "")
    if m:
        return m.group(1).strip()
    word = (option.get("name") or "").split()[0].lower() if option.get("name") else ""
    return word.title() if word in KIND_COLOR else None


def normalize(capture: dict, rest_fields: list | None = None) -> dict:
    p = _project_node(capture)
    fields = []
    rest_ids = {f.get("name", "").lower(): f.get("id") for f in rest_fields or [] if isinstance(f, dict)}
    for f in (p.get("fields") or {}).get("nodes") or []:
        if not f or not f.get("name"):
            continue
        opts = f.get("options") or f.get("multiSelectOptions")
        fields.append({"name": f["name"], "dataType": f.get("dataType"), "id": f.get("id"),
                       "databaseId": f.get("databaseId") or rest_ids.get(f["name"].lower()),
                       "isIssueField": bool(f.get("isIssueField")),
                       **({"options": [{k: o.get(k) for k in ("id", "name", "color", "description")} for o in opts]}
                          if opts is not None else {}),
                       **({"configuration": f["configuration"]} if f.get("configuration") else {})})
    views = []
    for v in (p.get("views") or {}).get("nodes") or []:
        if not v:
            continue
        views.append({"number": v.get("number"), "id": v.get("id"), "name": v.get("name"),
                      "layout": (v.get("layout") or "").replace("_LAYOUT", "").lower(), "filter": v.get("filter") or "",
                      "visible_fields": _names(v.get("fields")), "group_by": _names(v.get("groupByFields")),
                      "vertical_group_by": _names(v.get("verticalGroupByFields")),
                      "sort_by": [[(s.get("field") or {}).get("name"), (s.get("direction") or "").lower()]
                                  for s in (v.get("sortByFields") or {}).get("nodes") or [] if s]})
    ws = next((f for f in fields if f["name"].lower() == "workstream"), None)
    workstreams = []
    for o in (ws or {}).get("options") or []:
        kind = _kind_of(o)
        want = KIND_COLOR.get((kind or "").split(" / ")[0].lower())
        workstreams.append({"name": o.get("name"), "color": o.get("color"), "description": o.get("description"),
                            "kind": kind, "expected_color": want, "ok": bool(want) and o.get("color") == want})
    spec = {"std": STANDARD, "id": p.get("id"), "number": p.get("number"), "url": p.get("url"), "title": p.get("title"),
            "short_description": p.get("shortDescription") or "", "readme": p.get("readme") or "",
            "public": p.get("public"), "closed": p.get("closed"), "template": p.get("template"),
            "repositories": _names({"nodes": [{"name": r.get("nameWithOwner")} for r in
                                              (p.get("repositories") or {}).get("nodes") or [] if r]}),
            "teams": [t.get("slug") for t in (p.get("teams") or {}).get("nodes") or [] if t],
            "fields": fields, "views": views,
            "workflows": [{k: w.get(k) for k in ("id", "number", "name", "enabled")}
                          for w in (p.get("workflows") or {}).get("nodes") or [] if w],
            "status_updates": list((p.get("statusUpdates") or {}).get("nodes") or []),
            "workstreams": workstreams,
            "mode": "needs-user-choice" if any(f["isIssueField"] for f in fields) else "A",
            "short_description_checks": short_description_checks(p.get("shortDescription") or "")}
    spec["diff"] = diff_standard(spec)
    return spec


def _field(spec: dict, name: str) -> dict | None:
    return next((f for f in spec.get("fields") or [] if (f.get("name") or "").lower() == name.lower()), None)


def _view(spec: dict, name: str) -> dict | None:
    return next((v for v in spec.get("views") or [] if (v.get("name") or "").lower() == name.lower()), None)


def diff_standard(spec: dict, views: list[dict] | None = None, fields: list[dict] | None = None) -> dict:
    """What the board lacks against §13.3–13.5 (the capture's own names win where it has the field)."""
    out = {"missing_fields": [], "type_mismatch": [], "option_mismatch": [], "missing_views": [], "view_mismatch": [],
           "capture_wins": []}
    for want in fields or FIELDS:
        have = _field(spec, want["name"])
        if have is None:
            out["missing_fields"].append(want["name"])
            continue
        if have.get("dataType") and have["dataType"] != want["dataType"] and not want.get("builtin"):
            out["type_mismatch"].append({"field": want["name"], "have": have["dataType"], "want": want["dataType"]})
        if want.get("options") and capture_wins(want, have.get("options")):
            out["capture_wins"].append(want["name"])
        elif want.get("options") and want["name"] != "Workstream":
            opts = {(o.get("name") or "").lower(): o for o in have.get("options") or []}
            for name, color, desc in want["options"]:
                o = opts.get(name.lower())
                if o is None or o.get("color") != color or (o.get("description") or "") != desc:
                    out["option_mismatch"].append({"field": want["name"], "option": name,
                                                   "have": None if o is None else [o.get("color"), o.get("description")],
                                                   "want": [color, desc]})
    for want in views or VIEWS:
        have = _view(spec, want["name"])
        if have is None:
            out["missing_views"].append(want["name"])
            continue
        probs = []
        if have.get("layout") != want["layout"]:
            probs.append(f"layout {have.get('layout')} != {want['layout']}")
        if (have.get("filter") or "") != want["filter"]:
            probs.append(f"filter {have.get('filter')!r} != {want['filter']!r}")
        for k in ("group_by", "vertical_group_by"):
            if want.get(k) and [x.lower() for x in have.get(k) or []] != [x.lower() for x in want[k]]:
                probs.append(f"{k} {have.get(k)} != {want[k]}")
        if probs:
            out["view_mismatch"].append({"view": want["name"], "problems": probs})
    return out


# =====================================================================================================
# readme (§13.7)
# =====================================================================================================
def doc_fields(spec: dict | None, planned: dict | None = None, *, estate: bool = False) -> list[dict]:
    """The fields a board README documents: the §13.3 list in its order, each with the options the board has (from
    the capture) or will have once the plan's option jobs run (`planned`). The board's own scale (capture wins,
    §13.1) and its own workstreams are documented as they are, never replaced by the template defaults; a field the
    plan creates is documented from the standard."""
    std = {f["name"]: f for f in FIELDS + (ESTATE_FIELDS if estate else [])}
    out = []
    for name, f in std.items():
        if planned and name in planned:
            out.append(dict(f, options=planned[name]))
            continue
        have = _field(spec or {}, name)
        if have is None:
            out.append(f)
        elif have.get("dataType") != f["dataType"]:
            out.append({"name": name, "dataType": have.get("dataType") or "", "options": have.get("options") or []})
        elif have.get("options") is not None:
            out.append(dict(f, options=have["options"]))
        else:
            out.append(f)
    return out


def _opt_name(o) -> str:
    return o[0] if isinstance(o, tuple) else (o.get("name") or "")


def readme(org: str, display_name: str, number, view_numbers: dict, *, fields: list[dict] | None = None,
           repositories: list[str] | None = None, out_of_scope: str | None = None, reviewed: str | None = None,
           views: list[dict] | None = None, estate: bool = False) -> tuple[str, list[str]]:
    """Fill the §13.7 template. Every {…} is filled; a missing view number is needs-input (exit 4)."""
    views = views or (ESTATE_VIEWS if estate else VIEWS)
    logs = []
    missing = [v["name"] for v in views if not view_numbers.get(v["name"])]
    if missing:
        raise NeedsInput("view-numbers", f"view numbers missing for {', '.join(missing)}: capture the board after the "
                                         "copy (project capture-query) and pass it with --copied")
    base = project_url(org, number)
    if not out_of_scope:
        out_of_scope = ("work tracked on another organization's board" if not estate
                        else "tasks; each organization's board holds those")
        logs.append("default:out-of-scope")
    purpose = (f"This board tracks {display_name} work across its workstreams: what is in flight, what is next and what "
               f"has shipped. It does not track {out_of_scope.rstrip('.')}." if not estate else
               "This board rolls up CompleteTech LLC initiatives and top-level features from every in-scope "
               f"organization, with their health and target dates. It does not track {out_of_scope.rstrip('.')}.")
    lines = ["## Purpose", purpose, "", "## Views", "| View | Answers |", "|---|---|"]
    for v in views:
        lines.append(f"| [{v['name']}]({base}/views/{view_numbers[v['name']]}) | {v['answers']} |")
    lines += ["", "## Fields", "| Field | Options |", "|---|---|"]
    flist = {f["name"]: f for f in (fields or FIELDS + (ESTATE_FIELDS if estate else []))}
    from .describe import _EMOJI

    def plain(t: str, where: str) -> str:
        """A board's own option text, without the emoji the §13.7 README rules forbid (the option keeps its name)."""
        clean = re.sub(r"\s{2,}", " ", _EMOJI.sub("", t or "")).strip()
        if clean != (t or "").strip():
            logs.append(f"readme-emoji-stripped:{where}")
        return clean.replace("|", "\\|")

    for f in flist.values():
        opts = [(o[0], o[2]) if isinstance(o, tuple) else (o.get("name") or "", o.get("description") or "")
                for o in f.get("options") or []]
        cell = "; ".join(f"{plain(n, f['name'] + '/' + n)}: {plain(d, f['name'] + '/' + n)}".rstrip(": ")
                         for n, d in opts)
        lines.append(f"| {f['name']} | {cell or f.get('dataType', '').replace('_', ' ').lower()} |")
    # the workflow line follows the board's own Status options (a board that kept Todo / In Progress / Done says so)
    status = [n for n in (_EMOJI.sub("", _opt_name(o)).strip() for o in (flist.get("Status") or {}).get("options") or [])
              if n]
    blocked = [n for n in status if n.lower() == "blocked"] or ([] if status else ["Blocked"])
    flow = [n for n in status if n.lower() != "blocked"] or ["Backlog", "Ready", "In progress", "In review", "Done"]
    done = next((n for n in status if n.lower() == "done"), flow[-1])
    lines += ["", "## Workflow",
              " → ".join(flow) + "." + (f" {blocked[0]} means waiting on something outside the team's control; the "
                                        "blocker is noted in the issue." if blocked else ""),
              f"Automations: new items start in {flow[0]}; closed or merged items move to {done}; closed items are "
              "archived after one month.", "", "## Cadence",
              ("A status update every Monday, after the organization updates. " if estate else
               "A status update every Friday. ") + "Cycles are two weeks long and start on Monday.", "", "## Links"]
    home = f"https://github.com/{USER_LOGIN}" if estate else f"https://github.com/{org}"
    links = [f"[{display_name} on GitHub]({home})"]
    links += [f"[{r}](https://github.com/{r})" for r in repositories or []]
    links.append(f"Contact: {STEWARD[0]}, {STEWARD[1]}")
    lines += [" · ".join(links), "", f"Last reviewed: {reviewed or date.today().isoformat()}"]
    text = "\n".join(lines) + "\n"
    errs = text_checks(text)
    if errs:
        raise ShowcaseError(f"README fails the text rules: {', '.join(errs)}", log="readme-text", code=CHECK_FAILED)
    return text, logs


def view_numbers(spec: dict | None) -> dict:
    return {v["name"]: v.get("number") for v in (spec or {}).get("views") or [] if v.get("name")}


# =====================================================================================================
# mutations (printed inline; literal values)
# =====================================================================================================
def _options_literal(opts: list[tuple] | list[dict]) -> str:
    parts = []
    for o in opts:
        if isinstance(o, tuple):
            o = {"name": o[0], "color": o[1], "description": o[2]}
        idp = f"id: {_q(o['id'])}, " if o.get("id") else ""
        parts.append(f"{{{idp}name: {_q(o['name'])}, color: {o['color']}, description: {_q(o.get('description') or '')}}}")
    return "[" + ", ".join(parts) + "]"


def m_create_field(project_id: str, f: dict) -> str:
    dt = f["dataType"]
    extra = ""
    if dt == "SINGLE_SELECT":
        extra = f", singleSelectOptions: {_options_literal(f['options'])}"
    elif dt == "MULTI_SELECT":
        extra = f", multiSelectOptions: {_options_literal(f.get('options') or [('Tag', 'GRAY', 'Cross-cutting tag')])}"
    elif dt == "ITERATION":
        its = []
        y, m, d = (int(x) for x in ANCHOR.split("-"))
        start = date(y, m, d)
        for i in range(CYCLES):
            s = date.fromordinal(start.toordinal() + i * CYCLE_DAYS).isoformat()
            its.append(f"{{title: {_q('Cycle ' + s)}, startDate: {_q(s)}, duration: {CYCLE_DAYS}}}")
        extra = (f", iterationConfiguration: {{startDate: {_q(ANCHOR)}, duration: {CYCLE_DAYS}, "
                 f"iterations: [{', '.join(its)}]}}")
    return (f"mutation {{ createProjectV2Field(input: {{projectId: {_q(project_id)}, dataType: {dt}, name: {_q(f['name'])}"
            f"{extra}}}) {{ projectV2Field {{ ... on ProjectV2FieldCommon {{ id databaseId name }} }} }} }}")


def m_update_options(field_id: str, options: list[dict]) -> str:
    return (f"mutation {{ updateProjectV2Field(input: {{fieldId: {_q(field_id)}, singleSelectOptions: "
            f"{_options_literal(options)}}}) {{ projectV2Field {{ ... on ProjectV2SingleSelectField {{ id name "
            "options { id name color description } } } } }")


def m_view_filter(view_id: str, flt: str) -> str:
    return (f"mutation {{ updateProjectV2View(input: {{viewId: {_q(view_id)}, filter: {_q(flt)}}}) "
            "{ projectV2View { id number name filter } } }")


def m_status_update(start: str, target: str) -> str:
    return ("mutation($p: ID!, $body: String!) { createProjectV2StatusUpdate(input: {projectId: $p, status: ON_TRACK, "
            f"startDate: {_q(start)}, targetDate: {_q(target)}, body: $body}}) {{ statusUpdate {{ id }} }} }}")


def capture_wins(want: dict, have: list[dict] | None) -> bool:
    """§13.1 principle 1: the reference board's own option scale (no option name in common with the standard, such as
    P0/P1/P2 for Priority) wins over the defaults, so the two scales are never merged into one list. Status always takes
    the standard list (its first option is renamed to Backlog, §13.3); Workstream has its own rules."""
    if want["name"] in ("Status", "Workstream") or not have or not want.get("options"):
        return False
    names = {n.lower() for n, _c, _d in want["options"]}
    return not any((o.get("name") or "").lower() in names for o in have)


def merged_options(have: list[dict], want: list[tuple], *, rename_first: str | None = None) -> tuple[list[dict], list[str]]:
    """The full option list for updateProjectV2Field: every existing option keeps its id (the list replaces all
    options, and a dropped id clears item values), the standard names, colours and descriptions win, and extra
    existing options are kept (never dropped)."""
    logs = []
    by_name = {(o.get("name") or "").lower(): o for o in have}
    used, out = set(), []
    for i, (name, color, desc) in enumerate(want):
        o = by_name.get(name.lower())
        if o is None and i == 0 and rename_first and rename_first.lower() in by_name:
            o = by_name[rename_first.lower()]  # Todo -> Backlog keeps the option the item-added workflow sets
            logs.append(f"rename-option:{o.get('name')}->{name}")
        if o is not None:
            used.add(o.get("id"))
        out.append({"id": o.get("id") if o else None, "name": name, "color": color, "description": desc})
    for o in have:
        if o.get("id") not in used:
            out.append({"id": o.get("id"), "name": o.get("name"), "color": o.get("color") or "GRAY",
                        "description": o.get("description") or ""})
            logs.append(f"keep-option:{o.get('name')}")
    return out, logs


def workstream_options(have: list[dict], wanted: list[dict]) -> tuple[list[dict], list[str], dict]:
    """Org workstreams onto the copied generic options, one per kind: reuse an option of the same kind (its id is
    kept), colour by kind, description `[Kind] …`. Unused generic options are kept. Returns (options, logs, renames)."""
    logs, renames, out, used = [], {}, [], set()
    for w in wanted:
        kind = (w.get("kind") or "").split(" / ")[0].strip().title()
        color = KIND_COLOR.get(kind.lower())
        if not color:
            raise ShowcaseError(f"workstream {w.get('name')!r}: unknown kind {w.get('kind')!r} (§13.4)", log="usage")
        desc = w.get("description") or ""
        desc = desc if desc.startswith(f"[{kind}]") else f"[{kind}] {desc}".strip()
        reuse = next((o for o in have if o.get("id") not in used and (_kind_of(o) or "").lower().startswith(kind.lower())),
                     None)
        if reuse:
            used.add(reuse.get("id"))
            if reuse.get("name") != w["name"]:
                renames[reuse.get("name")] = w["name"]
        out.append({"id": reuse.get("id") if reuse else None, "name": w["name"], "color": color, "description": desc})
    for o in have:
        if o.get("id") not in used:
            out.append({k: o.get(k) for k in ("id", "name", "color", "description")})
            logs.append(f"keep-option:{o.get('name')}")
    if len(out) > 50:
        raise ShowcaseError("more than 50 Workstream options (single-select limit)", log="usage")
    return out, logs, renames


_FILTER_TOKEN = re.compile(r'(?:[^\s"]+|"[^"]*")+')
_WS_PREDICATE = re.compile(r"^(-?workstream:)(.+)$", re.I | re.S)


def rename_filter_values(flt: str, renames: dict) -> str:
    """Point a view filter's Workstream predicates (`workstream:` and `-workstream:`, comma lists, quoted
    `workstream:"Research"` or bare `workstream:Research` values) at renamed options, in one pass so swapped names
    never chain. Only Workstream values change: a label, another field or free text that happens to share the old
    name is left as it is. A quoted value stays quoted; a bare one is quoted when the new name has a space or comma."""
    if not flt or not renames:
        return flt

    def value(v: str) -> str:
        quoted = len(v) >= 2 and v[0] == v[-1] == '"'
        old = v[1:-1] if quoted else v
        if old not in renames:
            return v
        new_name = renames[old]
        return f'"{new_name}"' if quoted or re.search(r"[\s,]", new_name) else new_name

    def token(m):
        pm = _WS_PREDICATE.match(m.group(0))
        if not pm:
            return m.group(0)
        return pm.group(1) + ",".join(value(v) for v in re.findall(r'"[^"]*"|[^,]+', pm.group(2)))
    return _FILTER_TOKEN.sub(token, flt)


_REPO_QUALIFIER = re.compile(r"^repo:(.+)$", re.I)


def _filter_repo_refs(flt: str) -> list[str]:
    """Repository references named by the POSITIVE `repo:` qualifiers of a Projects view filter, in order and
    de-duplicated case-insensitively. A comma list is split (`repo:A/x,B/y`) and quotes and whitespace are stripped from
    each part. An empty part or one with a `*` wildcard names no single repository, so it is skipped. A negative
    `-repo:` token is ignored: an exclusion names no association."""
    out: list[str] = []
    seen: set[str] = set()
    for tok in _FILTER_TOKEN.findall(flt or ""):
        m = _REPO_QUALIFIER.match(tok)
        if not m:
            continue
        for part in re.findall(r'"[^"]*"|[^,]+', m.group(1)):
            for piece in part.split(","):  # a quoted part may still hold a comma list: "A/x,A/y"
                p = piece.strip().strip('"').strip()
                if not p or "*" in p or p.lower() in seen:
                    continue
                seen.add(p.lower())
                out.append(p)
    return out


def view_body(want: dict, spec: dict) -> tuple[dict, list[str]]:
    """REST view body with integer field ids (databaseId); a field without an id becomes a browser step."""
    ids = {(f.get("name") or "").lower(): f.get("databaseId") for f in spec.get("fields") or []}
    ui = []

    def fid(name):
        v = ids.get(name.lower())
        if not v:
            ui.append(f"field '{name}' has no integer id in the capture: set it in the view menu")
        return v
    body = {"name": want["name"], "layout": want["layout"], "filter": want["filter"]}
    for k in ("vertical_group_by", "group_by"):
        vals = [fid(n) for n in want.get(k) or []]
        if vals and all(vals):
            body[k] = vals[:1]
        elif want.get(k):
            ui.append(f"{'Columns' if k == 'vertical_group_by' else 'Group'}: {', '.join(want[k])}")
    sorts = [[fid(n), d] for n, d in want.get("sort_by") or []]
    if sorts and all(s[0] for s in sorts):
        body["sort_by"] = sorts
    elif want.get("sort_by"):
        ui.append("Sort: " + ", then ".join(f"{n} {d}" for n, d in want["sort_by"]))
    if want.get("visible_fields") and want["layout"] != "roadmap":
        vis = [fid(n) for n in want["visible_fields"]]
        if all(vis):
            body["visible_fields"] = vis
        else:
            ui.append("Fields shown: " + ", ".join(want["visible_fields"]))
    return body, ui


# =====================================================================================================
# copy-plan (§13.9): template stage, org rollout, and the Estate (estate-plan)
# =====================================================================================================
def brand_display_name(resolver: Resolver | None, owner: str | None) -> str | None:
    """The org's brand.yaml `display_name`, under any of its logins (CQ-03); None when the org has no brand row. The
    raw login is never a display name (a not-yet-approved rename target has no row and must not be titled by its login)."""
    if resolver is None or not owner or is_user(owner):
        return None
    row = resolver.brand_org(owner, strict=False)
    return row.get("display_name") if row.get("known") else None


def _readme_repos(spec: dict, owner: str, role: str, resolver, repos) -> tuple[list, list]:
    """The repositories a §13.7 board README may name (copy-plan and `project readme` alike). A board that is public
    (as captured, approved or not: nothing here makes it private) or may go public (an org board with an approved
    visibility item) names none: neither reads repository metadata, so neither can tell a private linked repository
    from a public one."""
    repos = list(repos or spec.get("repositories") or [])
    may_go_public = bool(spec.get("public")) or (role == "org" and resolver is not None and owner != "@me"
                                                 and resolver.project_visibility_approved(owner))
    if may_go_public and repos:
        return [], ["readme-links:repositories-omitted (the board may go public)"]
    return repos, []


def _grant_key(resolver, ro: str, rn: str) -> str:
    """The lowercase RESOLVED `<canonical owner>/<repo>` key of grants and held_lower: a former login of an org keys
    the same as its current one, so a same-owner reference matches the link loop's key."""
    owner_key = resolver.canonical(ro) if resolver is not None else ro
    return f"{owner_key}/{rn}".lower()


def _normalize_repo_entries(entries, board_owner: str | None, role: str, resolver, logs: list) -> list[str]:
    """Each repository entry in canonical form, once: `NAME` or `OWNER/NAME`, stripped, with no trailing `/` and no
    `.git` (signoff.canonical_repo). A malformed entry is dropped and logged (`repos-malformed:`). On an org board a bare
    NAME means <board owner>/<NAME>; on any other board it stays bare, which no sign-off can authorise. Duplicates fold
    case-insensitively, keeping the first spelling and the order."""
    from . import signoff
    out: list[str] = []
    seen: set[str] = set()
    for entry in entries or []:
        c = signoff.canonical_repo(entry)
        if c is None:
            logs.append(f"repos-malformed:{entry!r}")
            continue
        if "/" not in c:
            if role == "org" and board_owner and board_owner != "@me":
                c = f"{board_owner}/{c}"
        else:
            owner, name = c.split("/", 1)
            c = f"{owner.strip()}/{name}"
        if c.lower() in seen:
            continue
        seen.add(c.lower())
        out.append(c)
    return out


def _authorize_readme_repos(readme_repos, resolver, allow_t3: bool, grants: dict, held_lower: set,
                            logs: list, *, board_owner: str | None = None, role: str = "org") -> list[str]:
    """Keep the README repositories this copy may name. Every entry is normalised once first (_normalize_repo_entries).
    An entry whose owner cannot be resolved (a bare name off an org board, no resolver, or an unknown status) is held.
    A T3 owner's repository is dropped with `t3-signoff:readme:<owner>/<repo>` when --allow-t3 is not passed; with it,
    the repository needs a valid sign-off record that covers it on its own owner and name (checked on its own owner and
    name, whatever the board owner is). A denied one is logged and dropped, a granted one is recorded in grants for the
    README job's sign-off ids. Other owners' references are kept unchanged."""
    from . import signoff
    kept: list[str] = []
    for r0 in _normalize_repo_entries(readme_repos, board_owner, role, resolver, logs):
        if "/" not in r0 or resolver is None:
            logs.append(f"readme-held:{r0} (owner cannot be resolved)")
            continue
        ro, rn = r0.split("/", 1)
        ro = resolver.canonical(ro)
        status = resolver.owner_status(ro)
        if status not in (None, "excluded", "hold", "t3", "watching"):
            logs.append(f"readme-held:{r0} (owner cannot be resolved)")
            continue
        if status != "t3":
            kept.append(r0)
            continue
        if not allow_t3:
            logs.append(f"t3-signoff:readme:{ro}/{rn}")
            continue
        key = _grant_key(resolver, ro, rn)
        if key in grants:  # already authorized by the link loop or an earlier reference
            kept.append(r0)
            continue
        if key in held_lower:
            continue
        rec, why = signoff.evaluate([ro, *resolver.aliases(ro)], rn)
        if rec is None:
            logs.append(f"t3-signoff:{(why or 'missing').partition(':')[0]}:{ro}/{rn}")
            logs.append(f"readme-held:{ro}/{rn} (no valid T3 sign-off covers this repository)")
            held_lower.add(key)
            continue
        grants[key] = rec
        kept.append(r0)
    return kept


def _is_t3(row: dict) -> bool:
    """A brand or registry org row whose tier starts with T3 (a row with no tier is never T3)."""
    words = str(row.get("tier") or "").split()
    return bool(words) and words[0] == "T3"


def _captured_spec(copied: dict | None) -> dict | None:
    """The normalized spec of a captured board; copy_plan and estate_plan derive it the same way."""
    if copied is None:
        return None
    return copied if "fields" in copied and "views" in copied and "std" in copied else normalize(copied)


def captured_t3(resolver: Resolver | None, spec: dict | None, allow_t3: bool) -> tuple[list[str], list[dict]]:
    """Sign-off check of the T3 orgs that the CAPTURED Estate Org field names (an option whose description is
    `T3: <login>`, or whose name is a T3 org's display name) while --allow-t3 is passed. Returns (refusals, retained):
    refusals are `t3-signoff:<code>:<login>` for each such org with no valid sign-off record, and retained are
    {login, name, tier, signoff_id, labels} for each such org whose record is valid. The description remainder and the
    option name are resolved independently: the remainder is tried first, and the option name only when the remainder
    does not resolve (an empty remainder yields no candidate), so a T3 name is still checked when its description is
    unresolved or obsolete. labels are the lowercased, stripped option name and description (empties omitted, duplicates
    removed); an org retained from two options gets one entry whose labels are merged. Identities resolve through
    references/brand.yaml (current logins, former slugs, approved renames) as well as the registry, so an org that is
    no longer in registry.orgs is still checked. copy_plan keeps every captured option (ids are never dropped) and the
    README documents them, so a withdrawn association would otherwise survive into the option-update job and the README
    (tests/test_t3_signoff_require.py::test_estate_replan_holds_a_captured_t3_org_after_withdrawal). This only reads.
    Empty without --allow-t3 or without a resolver."""
    if not allow_t3 or resolver is None:
        return [], []
    have = _field(spec or {}, "Org")
    if not have:
        return [], []
    from . import signoff
    t3, rows = {}, {}

    def _index(key: str, row: dict) -> None:
        rows[key] = row
        for alias in resolver.aliases(key):  # a description written under a former login still names this org
            t3[alias.lower()] = key
        t3[resolver.canonical(key).lower()] = key
        t3[str(row.get("display_name") or key).lower()] = key

    sources = [list(resolver.registry.get("orgs") or {})]
    if resolver.brand is not None:
        sources.append(list((resolver.brand.raw.get("orgs") or {}).keys()))
    for keys in sources:
        for key in keys:
            try:
                row = resolver.brand_org(key)
            except NeedsInput:
                continue
            if _is_t3(row):
                _index(key, row)
    def _resolve(ident: str) -> str | None:
        """The T3 org key that one captured identifier names (a login, rename, display name or former slug), or None."""
        ident = ident.strip().lower()
        if not ident:
            return None
        key = t3.get(ident)
        if key is None:  # an approved rename: resolve the identifier to its current login
            try:
                key = t3.get(resolver.canonical(ident).lower())
            except NeedsInput:
                key = None
        if key is None:  # a former login: brand former_slugs resolve it without registry membership
            bk = resolver.brand_key(ident)
            if bk is not None:
                try:
                    row = resolver.brand_org(bk)
                except NeedsInput:
                    row = {}
                if _is_t3(row):
                    key = bk
                    rows[bk] = row
        return key

    refusals, retained, seen = [], [], set()
    for o in have.get("options") or []:
        desc = str(o.get("description") or "")
        name = str(o.get("name") or "")
        # the description remainder and the option name are resolved independently: the remainder first (only with the
        # T3 prefix), the option name when the remainder does not resolve
        candidates = [desc[len(TIER_PREFIX_T3):]] if desc.startswith(TIER_PREFIX_T3) else []
        candidates.append(name)
        key = None
        for ident in candidates:
            key = _resolve(ident)
            if key is not None:
                break
        if key is None:
            continue
        labels = list(dict.fromkeys(x for x in (name.strip().lower(), desc.strip().lower()) if x))
        login = resolver.canonical(key)
        rec, why = signoff.evaluate([key, *resolver.aliases(key)])
        if rec is None:
            refusals.append(f"t3-signoff:{(why or 'missing').partition(':')[0]}:{login}")
            continue
        if login.lower() in seen:  # the same org under another captured option: its labels join the one entry
            entry = next(r for r in retained if r["login"].lower() == login.lower())
            entry["labels"] = list(dict.fromkeys([*entry["labels"], *labels]))
            continue
        seen.add(login.lower())
        retained.append({"login": login, "name": (rows.get(key) or {}).get("display_name") or key, "tier": "T3",
                         "signoff_id": str(rec["id"]), "labels": labels})
    return list(dict.fromkeys(refusals)), retained


def held_captured_t3(resolver: Resolver | None, spec: dict | None, allow_t3: bool) -> list[str]:
    """The refusals (`t3-signoff:<code>:<login>`) for the captured T3 orgs that have no valid sign-off record while
    --allow-t3 is passed. Identities resolve through references/brand.yaml as well as the registry; see captured_t3,
    whose refusals this returns. Empty without --allow-t3 or without a resolver."""
    return captured_t3(resolver, spec, allow_t3)[0]


def copy_plan(target: str, *, role: str = "org", source: str | None = None, title: str | None = None,
              display_name: str | None = None, copied: dict | None = None, workstreams: list[dict] | None = None,
              repositories: list[str] | None = None, approval_id: str | None = None, resolver: Resolver | None = None,
              user_id: int | None = None, out_of_scope: str | None = None, reviewed: str | None = None,
              status_update: bool = True, allow_t3: bool = False, extra_fields: list[dict] | None = None,
              views: list[dict] | None = None, readme_text: str | None = None) -> dict:
    """Writer jobs for one board. Stage 1 (no --copied): the copy job and the re-capture read. Stage 2 (with the
    post-copy capture): fields, options, views, filters, text, links, status update and the browser steps."""
    if role not in ("org", "template", "estate"):
        raise ShowcaseError("role is org, template or estate", log="usage")
    owner = _gate_target(resolver, target, allow_t3=allow_t3)
    src = source or (f"{REFERENCE[0]}/{REFERENCE[1]}" if role == "template" else None)
    logs, jobs, reads, pending, files = [], [], [], [], {}
    if not src:
        src = f"{REFERENCE[0]}/{REFERENCE[1]}"
        if copied is None:  # stage 2 creates nothing, so only the copy itself is a fallback
            logs.append("fallback:direct-copy (no template number given; §13.9 fallback)")
    m = re.match(r"^([A-Za-z0-9-]+)/(\d+)$", src)
    if not m:
        raise ShowcaseError("--source must be OWNER/NUMBER", log="usage")
    src_owner, src_num = m.group(1), int(m.group(2))
    if resolver is not None:
        src_owner = resolver.canonical(src_owner)
    name = display_name or (brand_display_name(resolver, owner) if owner != "@me" else None)
    if not name:
        if role == "org":
            # never the raw login (CompleteTech-TCG before its rename is approved has no brand row): exit 4, append nothing
            raise NeedsInput("display-name", f"{owner} has no display_name in references/brand.yaml (add the org row, its "
                                             "former_slugs, or pass --display-name); nothing was planned")
        name = {"template": "CompleteTech LLC", "estate": "CompleteTech Estate"}[role]
    title = title or {"template": TEMPLATE_TITLE, "estate": ESTATE_TITLE}.get(role) or f"{name} — Workstreams"
    short = DESC[role].format(name=name)
    sd = short_description_checks(short, names=(name,))
    if any(c["result"] == "fail" for c in sd):
        raise ShowcaseError(f"short description fails §13.2: {short!r}", log="usage", code=CHECK_FAILED)
    if role == "template" and not resolver_same(resolver, owner, TEMPLATE_OWNER):
        logs.append("template-owner: §13.2 puts the template in CompleteTech-LLC")
    sid = _slug(owner)
    pid = f"p{PHASE}-{sid}-project"
    if copied is None and resolver is not None and not resolver.approved("create-project", "@me" if owner == "@me" else owner):
        logs.append(f"needs-approval:create-project:{owner}")
    if copied is None:
        jobs.append(_job(f"{pid}-copy", "create-project",
                         ["gh", "project", "copy", str(src_num), "--source-owner", src_owner, "--target-owner", owner,
                          "--title", title], owner,
                         "Copy the structure only (fields, views, workflows): never --drafts, never items (§13.1).",
                         approval_id=approval_id or CREATE_APPROVAL["estate" if role == "estate" else "org"]))
        reads.append({"name": "node-ids", "argv": read_command("node_ids", o=src_owner if owner == "@me" else owner)})
        pending.append({"why": "re-capture the copy to learn its number, field and view ids",
                        "next": f"project capture-query --owner {owner} --number N, then copy-plan --copied FILE"})
        return {"command": "project", "action": "copy-plan", "owner": owner, "role": role, "stage": 1, "title": title,
                "short_description": short, "result": "ok", "jobs": jobs, "reads": reads, "pending": pending,
                "files": files, "logs": logs}
    spec = _captured_spec(copied)
    number, project_id = spec.get("number"), spec.get("id")
    if not number or not project_id:
        raise ShowcaseError("the --copied capture has no project number or id", log="usage")
    _check_board_owner(spec, owner, target, resolver)
    num = str(number)
    own_flag = owner
    # 1. fields: create what is missing, fix standard options keeping ids
    std_fields = list(FIELDS) + list(extra_fields or [])
    planned: dict[str, list] = {}  # the options each field will have once these jobs run (for the README)
    held_t3, retained_t3 = captured_t3(resolver, spec, allow_t3) if role == "estate" else ([], [])
    logs += held_t3
    for f in std_fields:
        have = _field(spec, f["name"])
        if held_t3 and f["name"] == "Org" and have is not None:
            # a captured T3 association lost its sign-off: leave the option list as captured (no ids dropped) and plan
            # no option write or README that would carry it on
            logs.append("hold:org-options (a captured T3 org option has no valid sign-off)")
            planned[f["name"]] = have.get("options") or []
            continue
        if have is None:
            if not f.get("required") and f["dataType"] == "MULTI_SELECT":
                logs.append(f"optional-field-skipped:{f['name']}")
                continue
            if role == "estate" and f["name"] == "Workstream" and f["dataType"] == "SINGLE_SELECT":
                continue
            jobs.append(_gql_job(f"{pid}-{num}-field-{_k(f['name'])}", owner, m_create_field(project_id, f),
                                 f"§13.3 field {f['name']} ({f['dataType']}), colours and descriptions inline."))
            continue
        if f.get("options") and capture_wins(f, have.get("options")):
            logs.append(f"capture-wins:{f['name']}")  # keep the reference board's own scale; never merge two scales
            planned[f["name"]] = have.get("options") or []
            continue
        if f.get("options") and f["name"] != "Workstream" and have.get("options") is not None:
            opts, lg = merged_options(have["options"], f["options"], rename_first="Todo" if f["name"] == "Status" else None)
            planned[f["name"]] = opts
            logs += lg
            cur = {o.get("id"): o for o in have["options"]}
            if any(o["id"] is None or cur[o["id"]].get("name") != o["name"] or cur[o["id"]].get("color") != o["color"]
                   or (cur[o["id"]].get("description") or "") != o["description"] for o in opts):
                jobs.append(_gql_job(f"{pid}-{num}-options-{_k(f['name'])}", owner, m_update_options(have["id"], opts),
                                     f"§13.3 {f['name']} options: full list, every existing option id kept."))
    # 2. workstreams (org boards): rename and recolour the generic options, keeping their ids
    renames = {}
    ws = _field(spec, "Workstream")
    if role == "template" and ws and ws.get("options") is not None and not workstreams:
        workstreams = [{"name": short, "kind": short, "description": label} for short, label, _c in KINDS]
    if role == "estate" and ws and ws.get("dataType") == "SINGLE_SELECT":
        logs.append("estate-workstream: the template's single-select Workstream stays (never deleted); §13.10 wants TEXT, "
                    "so rename it in the UI first or keep it")
    if role in ("org", "template") and ws and ws.get("options") is not None:
        if workstreams:
            opts, lg, renames = workstream_options(ws["options"], workstreams)
            planned["Workstream"] = opts
            logs += lg
            jobs.append(_gql_job(f"{pid}-{num}-options-workstream", owner, m_update_options(ws["id"], opts),
                                 "§13.4 workstreams onto the copied options (ids kept, colour by kind)."))
        else:
            logs.append("needs-input:workstreams")
    # 3. views: fix filters on copied views (view 1 stays as captured), create missing ones through REST
    vlist = [dict(v) for v in (views or (ESTATE_VIEWS if role == "estate" else VIEWS))]
    base = (f"users/{user_id}/projectsV2/{num}/views" if owner == "@me" and user_id else
            f"orgs/{owner}/projectsV2/{num}/views")
    filter_jobs: list[tuple[dict, str]] = []  # (view-filter job, its new filter): authorized after the README repos
    for i, want in enumerate(vlist):
        have = _view(spec, want["name"])
        if have is not None:
            flt = have.get("filter") or ""
            new = rename_filter_values(flt, renames)
            if i > 0 and flt != want["filter"] and role != "org":
                new = want["filter"]
            if new != flt and have.get("id"):
                fj = _gql_job(f"{pid}-{num}-view-{have.get('number')}-filter", owner, m_view_filter(have["id"], new),
                              f"View '{want['name']}' filter (§13.5{'; renamed options' if renames else ''}).")
                jobs.append(fj)
                filter_jobs.append((fj, new))
            continue
        if owner == "@me" and not user_id:
            pending.append({"view": want["name"], "why": "numeric user id (gh api user --jq .id) for the user views path"})
            reads.append({"name": "user-id", "argv": ["gh", "api", "user", "--jq", ".id"]})
            continue
        body, ui = view_body(want, spec)
        rel = f"work/projects/{sid}-{num}/view-{i + 1}-{_k(want['name'])}.json"
        files[rel] = body
        jobs.append(_job(f"{pid}-{num}-view-{_k(want['name'])}", "project",
                         ["gh", "api", "-X", "POST", base, "--input", rel], owner,
                         f"§13.5 view {i + 1} '{want['name']}' through REST (integer field ids). Read the view number back."))
        if ui:
            want = dict(want, ui=list(want.get("ui") or []) + ui)
        vlist[i] = want
    # 0. repository sign-off (org boards), decided before the README and the browser steps: the links, the README text,
    # the default repository and auto-add all take their repositories from this one filtered set, so a withdrawn one is
    # named by none of them
    authorized: list[tuple[str, dict | None]] = []  # (repo, sign-off record or None): the only repos the settings job may name
    link_jobs: list[dict] = []  # repository-link jobs, emitted right after the text job
    held_lower: set[str] = set()  # lowercase owner/repo names held for lack of a valid sign-off
    captured_populated = False  # a populated captured repository list with no explicit --repos
    grants: dict[str, dict | None] = {}  # lowercase owner/repo -> the sign-off record that covers it
    if repositories:  # the explicit list, normalised once: canonical OWNER/NAME entries for the link loop and the README
        repositories = _normalize_repo_entries(repositories, owner, role, resolver, logs)
    readme_repos, lg = _readme_repos(spec, owner, role, resolver, repositories)
    logs += lg
    if role == "org":
        linked = set()
        for r in repositories or []:
            if "/" not in r or not resolver_same(resolver, r.split("/", 1)[0], owner):
                logs.append(f"link-skipped:{r} (links need the same owner)")
                continue
            r = f"{owner}/{r.split('/', 1)[1]}"  # a former login of the org links under its current one (CQ-03)
            if r.lower() in linked:
                continue  # listed twice: one link job
            rec = None
            if allow_t3 and resolver is not None and resolver.owner_status(owner) == "t3":
                # the owner-wide grant does not settle a repository that a later withdrawal names: check each link
                from . import signoff
                rec, why = signoff.evaluate([owner, *resolver.aliases(owner)], r.split("/", 1)[1])
                if rec is None:
                    logs.append(f"t3-signoff:{(why or 'missing').partition(':')[0]}:{r}")
                    logs.append(f"link-held:{r} (no valid T3 sign-off covers this repository)")
                    held_lower.add(r.lower())
                    continue
            linked.add(r.lower())
            authorized.append((r, rec))
            grants[r.lower()] = rec
            link = _job(f"{pid}-{num}-link-{_repo_key(r.split('/', 1)[1])}", "project",
                        ["gh", "project", "link", num, "--owner", owner, "--repo", r], owner,
                        "Link before the §10.1 settings pass, or re-run R5 afterwards (§13.11).")
            if rec is not None and rec.get("id"):  # the repository's own granting id; approval_id is never touched
                signoff.stamp_associations(link, [str(rec["id"])])
            link_jobs.append(link)
        reads.append({"name": "org-projects-setting", "argv": ["gh", "api", f"orgs/{owner}", "--jq", ".has_organization_projects"]})
        if not repositories:
            # no explicit list: the captured same-owner repositories feed the default repository and auto-add, each
            # authorized on its own resolved owner and name. They never create a link job (no new association).
            captured_repos = [str(x) for x in (spec.get("repositories") or [])]
            captured_populated = bool(captured_repos)
            same = [x for x in captured_repos if "/" in x and resolver_same(resolver, x.split("/", 1)[0], owner)]
            for r in _authorize_readme_repos([f"{owner}/{x.split('/', 1)[1]}" for x in same], resolver, allow_t3,
                                             grants, held_lower, logs, board_owner=owner, role=role):
                if r.lower() not in {a.lower() for a, _ in authorized}:
                    authorized.append((r, grants.get(_grant_key(resolver, *r.split("/", 1)))))
    # every README repository (explicit or captured) is authorized on its own resolved owner and name, for every role
    readme_repos = _authorize_readme_repos(readme_repos, resolver, allow_t3, grants, held_lower, logs,
                                           board_owner=owner, role=role)
    # view filters: every repository a proposed filter names by a positive repo: qualifier is authorized like a README
    # repository before the filter mutation goes out. A filter that names a denied repository is held (its job is
    # removed); a permitted one carries the sign-off ids of the repositories it names. Bare names that do not resolve
    # to an owner/name pair are left alone.
    for fj, flt in (filter_jobs if resolver is not None else []):  # no resolver: nothing to authorize against, unchanged
        refs = [r for r in _normalize_repo_entries(_filter_repo_refs(flt), owner, role, resolver, []) if "/" in r]
        if not refs:
            continue
        kept = _authorize_readme_repos(refs, resolver, allow_t3, grants, held_lower, logs, board_owner=owner, role=role)
        kept_keys = {_grant_key(resolver, *r.split("/", 1)) for r in kept if "/" in r}
        if any(_grant_key(resolver, *r.split("/", 1)) not in kept_keys for r in refs):
            jobs[:] = [j for j in jobs if j is not fj]
            logs.append(f"view-filter-held:{fj['id']} (a repository in the proposed filter has no valid T3 sign-off or "
                        "is not authorized)")
            pending.append({"why": "view filter held: it names a repository without a valid T3 sign-off",
                            "needs": "a valid record covering that repository, or remove it from the filter"})
            continue
        ids = [str(g["id"]) for r in kept if "/" in r
               and (g := grants.get(_grant_key(resolver, *r.split("/", 1))))
               and g.get("id")]
        if ids:
            from . import signoff
            signoff.stamp_associations(fj, list(dict.fromkeys(ids)), owner)
    # 4. text: short description and README (README needs every view number)
    nums = view_numbers(spec)
    edit = ["gh", "project", "edit", num, "--owner", own_flag, "--description", short]
    text = readme_text
    if held_t3:
        text = None
        pending.append({"why": "README held: the Org field names a T3 org with no valid sign-off record",
                        "needs": "a valid record in the sign-off file, or remove the option on the board"})
    elif text is None:
        try:
            text, lg = readme(owner, name, number, nums, repositories=readme_repos,
                              out_of_scope=out_of_scope, reviewed=reviewed, views=vlist, estate=role == "estate",
                              fields=doc_fields(spec, planned, estate=role == "estate"))
            logs += lg
        except NeedsInput:
            pending.append({"why": "README needs every view number: re-capture after the view jobs run"})
    if text is not None:
        edit += ["--readme", text]
    # ids carry a content hash: the README-bearing re-plan (after the view jobs ran) is a new job, never the earlier id
    # with other content, which the writer refuses together with its whole batch
    text_job = _job(f"{pid}-{num}-text-{_digest(edit)}", "project", edit, owner,
                    "§13.2 short description" + (" and §13.7 README" if text is not None else " (README after re-capture)"))
    if text is not None:
        # the board owner's own grant is merged first (owner passed), then the granting records of the repositories
        # the README names (a retained authorized one carries its own)
        ids: list[str] = []
        for r in readme_repos:
            if "/" in r:
                rec = grants.get(_grant_key(resolver, *r.split("/", 1)))
                if rec and rec.get("id"):
                    ids.append(str(rec["id"]))
        if ids:
            from . import signoff
            signoff.stamp_associations(text_job, list(dict.fromkeys(ids)), owner)
    if text is not None and retained_t3:
        # the README documents every retained captured Org option, so the job carries the granting ids of retained_t3
        # directly instead of rediscovering them from the rendered text (a former login with a different captured label
        # has no match in the text) (tests/test_t3_emission_scope.py::test_captured_org_option_under_former_login_and_other_label_carries_signoff_id)
        ids = [str(o["signoff_id"]) for o in retained_t3 if o.get("signoff_id")]
        if ids:
            from . import signoff
            signoff.stamp_associations(text_job, list(dict.fromkeys(ids)), owner)
    jobs.append(text_job)
    # 5. repository links (org boards: same owner only), decided in step 0 and emitted here, before the browser steps
    jobs.extend(link_jobs)
    # 6. browser: UI-only view settings, workflows, insights, default repo, auto-add, recommended template
    url = project_url(owner, number)
    for v in vlist:
        if v.get("ui"):
            nv = nums.get(v["name"])
            jobs.append(_browser(f"{pid}-{num}-ui-{_k(v['name'])}", owner, f"{url}/views/{nv}" if nv else url,
                                 [f"Open {url} and select the '{v['name']}' view tab." if not nv else f"Open {url}/views/{nv}.",
                                  "Open the view menu (the arrow beside the view name).",
                                  *[f"Set: {u}" for u in v["ui"]],
                                  "Click 'Save changes' on the view.",
                                  f"Screenshot the view into state/screens/projects/{sid}/."],
                                 "project-view-settings", "§13.5 UI-only view settings (no API)."))
    wf_steps = [f"Open {url}/workflows."]
    for words, on_org, on_tpl in WORKFLOWS:
        on = on_tpl if role == "template" else on_org
        if words == "auto-add" and role == "estate":
            continue
        if words == "auto-add" and role == "org" and (repositories or captured_populated) and not authorized:
            # no repository may be chosen for the auto-add rule: the step names none, so it is held rather than emitted
            logs.append("workflows-held:auto-add (no authorized repository remains to choose; links held or skipped)")
            continue
        have = next((w for w in spec.get("workflows") or [] if words.split()[-1] in (w.get("name") or "").lower()), None)
        label = have.get("name") if have else words.title()
        if on and words == "auto-add" and role == "org" and authorized:
            wf_steps.append(f"Select '{label}', click 'Edit', choose {authorized[0][0]}, set {WORKFLOW_UI[words]} "
                            "Click 'Save and turn on workflow'.")
        elif on:
            wf_steps.append(f"Select '{label}', click 'Edit', set {WORKFLOW_UI[words]} Click 'Save and turn on workflow'.")
        else:
            wf_steps.append(f"Leave '{label}' off on the template (auto-add is set per org after the copy).")
    wf_steps.append(f"Screenshot the workflows list into state/screens/projects/{sid}/workflows.png.")
    wf_job = _browser(f"{pid}-{num}-workflows", owner, f"{url}/workflows", wf_steps, "project-workflows",
                      "§13.6 built-in workflows: UI only; never delete a workflow (no API can recreate it).")
    if authorized and authorized[0][1] and authorized[0][1].get("id"):  # the granting record of the repository auto-add names
        from . import signoff
        signoff.stamp_associations(wf_job, [str(authorized[0][1]["id"])])
    jobs.append(wf_job)
    if role == "template":
        jobs.append(_browser(f"{pid}-{num}-insights", owner, f"{url}/insights",
                             [f"Open {url}/insights.", "Keep the default 'Burn up' chart.",
                              "Click 'New chart', name it 'Open by Workstream and Status': layout Stacked column, X-axis "
                              "Workstream, Group by Status, filter is:open. Save.",
                              "Click 'New chart', name it 'Estimate by Workstream': layout Bar, X-axis Workstream, Y-axis "
                              "Sum of Estimate. Save.", "Screenshot the charts."], "project-insights", "§13.6 insights."))
        jobs.append(_job(f"{pid}-{num}-mark-template", "project", ["gh", "project", "mark-template", num, "--owner", owner],
                         owner, "Mark as a template LAST (§13.9 step 6)."))
        jobs.append(_browser(f"{pid}-{num}-recommended", owner, f"https://github.com/organizations/{owner}/settings/profile",
                             [f"Open https://github.com/organizations/{owner}/settings and go to 'Code, planning, and "
                              "automation' > 'Projects'.", "Under 'Recommended templates', click 'Customize recommended "
                              f"templates', tick '{title}' and save.", "Screenshot the setting."],
                             "project-recommended-template", "§13.9 step 6: offer the template in the org's dialog."))
    if role == "org":
        if (repositories or captured_populated) and not authorized:
            # every listed repository is withdrawn, unauthorized or on another owner: the default-repository and
            # auto-add steps would name one of them, so the settings job is held instead of emitted
            logs.append("settings-held:default-repository-and-auto-add (no authorized repository remains to choose; links held or skipped)")
        else:
            main, main_rec = authorized[0] if authorized else (None, None)
            steps = [f"Open {url}/settings.",
                     f"Under 'Default repository', choose {main}." if main else "Under 'Default repository', choose the org's main repository.",
                     f"Open {url}/workflows, select 'Auto-add to project', click 'Edit', choose {main or 'the main repository'} "
                     "and the filter is:issue,pr is:open, then click 'Save and turn on workflow'.",
                     "Check every view against the template screenshots and fix any UI-only setting that differs.",
                     f"Screenshot every view into state/screens/projects/{sid}/."]
            settings_job = _browser(f"{pid}-{num}-settings", owner, f"{url}/settings", steps, "project-settings",
                                    "§13.9 step 7: default repository, auto-add and view checks (UI only).")
            if main_rec is not None and main_rec.get("id"):  # the granting record of the repository the job names
                from . import signoff
                signoff.stamp_associations(settings_job, [str(main_rec["id"])])
            jobs.append(settings_job)
        if status_update and spec.get("status_updates"):
            # createProjectV2StatusUpdate is not idempotent: a board that already has an update never gets another "first"
            logs.append("status-update:exists")
        elif status_update and not nums.get("Shipped"):
            # the Shipped view is one this plan creates: plan the update from the re-capture (the README waits the same
            # way), so it links the view and is planned once, never first with a placeholder body and then again
            logs.append("status-update:shipped-view-pending")
            pending.append({"why": "the first status update links the Shipped view, which this plan creates",
                            "next": f"run the view jobs, re-capture board {num} and plan copy-plan --copied again"})
        elif status_update:
            body = ("**Summary**\nBoard set up from the CompleteTech workstream template.\n\n**Shipped**\n"
                    f"[Shipped view]({url}/views/{nums['Shipped']})\n\n**Next**\nAdd this cycle's work to the board."
                    "\n\n**Risks and blocks**\nNone recorded.\n\n**Asks and dependencies**\nNone recorded.")
            # the dates are the current quarter's (not today), so a re-plan within the quarter is byte-identical and
            # the writer skips it as already queued; the id hashes the whole mutation, so one id never has two contents
            mutation = m_status_update(_quarter_start(), _quarter_end())
            jobs.append(_gql_job(f"{pid}-{num}-status-1-{_digest([mutation, project_id, body])}", owner, mutation,
                                 "§13.8 first status update, right after rollout.", {"p": project_id, "body": body}))
    if role != "org":  # §13.2: the template and the Estate always stay private, whatever is approved
        logs.append(f"visibility:private ({role} stays private)")
    elif resolver is not None and owner != "@me" and resolver.project_visibility_approved(owner):
        jobs.append(_browser(f"{pid}-{num}-visibility", owner, f"{url}/settings",
                             [f"Open {url}/settings.", "Under 'Visibility', choose Public and confirm.", "Screenshot it."],
                             "project-visibility", "Approved visibility item only (§13.2)."))
    else:  # a board captured public without approval stays as it is here; lint's visibility cell fails
        logs.append("visibility:public (no approval)" if spec.get("public") else "visibility:private (no approval)")
    for j in jobs:
        argv = j.get("argv") or []
        if "--drafts" in argv or any(re.search(r"\bdelete", a, re.I) for a in argv if a.startswith("query=")):
            raise ShowcaseError(f"refused to plan {j['id']}: drafts or a delete", log="usage")
    seen_ids: set[str] = set()
    for j in jobs:  # the writer refuses a whole batch that uses an id twice, losing every job of the plan
        if j["id"] in seen_ids:
            raise ShowcaseError(f"refused to plan: job id {j['id']} is used twice", log="usage")
        seen_ids.add(j["id"])
    return {"command": "project", "action": "copy-plan", "owner": owner, "role": role, "stage": 2, "number": number,
            "title": title, "short_description": short, "result": "ok", "jobs": jobs, "reads": reads, "pending": pending,
            "files": files, "readme": text, "logs": sorted(set(logs))}


def resolver_same(resolver, a, b) -> bool:
    return resolver.same(a, b) if resolver else a.lower() == b.lower()


def _k(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _digest(obj) -> str:
    """Eight hex characters of sha256 over `obj` (canonical JSON): a job-id suffix that changes with the content."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]


def _repo_key(name: str) -> str:
    """A job-id segment for a repository name that keeps names apart: `_k` folds `.`, `_` and `-` together, so
    `order_ledger` and `order.ledger` would share an id. Writer ids allow `.` and `+` but not `_` (scripts/writer.py
    ID_RE), so `_` becomes `+`; a name of letters, digits and single hyphens keeps its earlier id."""
    return re.sub(r"[^a-z0-9.+-]", "-", (name or "").lower().replace("_", "+"))


def _board_owner(spec: dict) -> tuple[str, str] | None:
    """("orgs" | "users", login) of a captured board, from its url (github.com/orgs/LOGIN/projects/N)."""
    m = re.match(r"^https://github\.com/(orgs|users)/([A-Za-z0-9-]+)/projects/\d+", spec.get("url") or "")
    return (m.group(1), m.group(2)) if m else None


def _check_board_owner(spec: dict, owner: str, target: str, resolver) -> None:
    """Stage 2 plans node-id mutations and `gh project edit|link NUMBER --owner TARGET` against the captured board, so
    the capture must be a board of the target (any of its logins, CQ-03; the user's own board for @me). Another
    owner's board (another org, the template, the Pick-Your-AI reference) is refused: its node ids would be changed
    under the target's name, and the number-plus-owner jobs would overwrite an unrelated board of the target."""
    board = _board_owner(spec)
    if board is None:
        raise ShowcaseError("the --copied capture does not say whose board it is (no project url): re-capture the "
                            "board with `project capture-query`; nothing was planned", log="usage")
    kind, login = board
    mine = kind == "users" and is_user(login) if owner == "@me" else kind == "orgs" and resolver_same(resolver, login, owner)
    if not mine:
        raise ShowcaseError(f"the --copied capture is {login}'s board {spec.get('number')}, not a board of {target}: "
                            "pass the capture of the board copied into the target; nothing was planned", log="usage")


def _quarter_start(today: date | None = None) -> str:
    t = today or date.today()
    return date(t.year, (t.month - 1) // 3 * 3 + 1, 1).isoformat()


def _quarter_end(today: date | None = None) -> str:
    t = today or date.today()
    q_end_month = ((t.month - 1) // 3 + 1) * 3
    nxt = date(t.year + (q_end_month == 12), 1 if q_end_month == 12 else q_end_month + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1).isoformat()


def write_files(files: dict, out_dir: str | Path) -> list[str]:
    out = []
    for rel, body in files.items():
        p = Path(out_dir) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
        out.append(str(p))
    return out


# =====================================================================================================
# lint (§13): a captured board against the standard
# =====================================================================================================
def lint(capture: dict, *, role: str = "org", owner: str | None = None, display_name: str | None = None,
         resolver: Resolver | None = None) -> dict:
    spec = capture if "std" in capture and "fields" in capture else normalize(capture)
    estate = role == "estate"
    cells, notes = {}, []
    want_title = {"template": TEMPLATE_TITLE, "estate": ESTATE_TITLE}.get(role) or (f"{display_name} — Workstreams"
                                                                                   if display_name else None)
    cells["title"] = "pass" if not want_title or spec.get("title") == want_title else "fail"
    if cells["title"] == "fail":
        notes.append(f"title {spec.get('title')!r} != {want_title!r}")
    sd = short_description_checks(spec.get("short_description") or "")
    cells["short-description"] = "fail" if any(c["result"] == "fail" for c in sd) else "pass"
    notes += [f"short description {c['rule']}: {c.get('span', '')}" for c in sd if c["result"] == "fail"]
    rd = spec.get("readme") or ""
    errs = text_checks(rd) + ([] if rd.strip() else ["empty"])
    for h in ("## Purpose", "## Views", "## Fields", "## Workflow", "## Cadence", "## Links"):
        if rd.strip() and h not in rd:
            errs.append(f"missing {h}")
    cells["readme"] = "fail" if errs else "pass"
    notes += [f"README {e}" for e in errs]
    flist = ([f for f in FIELDS if f["name"] != "Workstream"] + ESTATE_FIELDS) if estate else FIELDS
    d = diff_standard(spec, views=ESTATE_VIEWS if estate else VIEWS, fields=flist)
    if estate:
        d["type_mismatch"] = [x for x in d["type_mismatch"] if x["field"] != "Workstream"]
    req = {f["name"] for f in flist if f.get("required", True)}
    miss_req = [f for f in d["missing_fields"] if f in req]
    cells["fields"] = "fail" if miss_req or d["type_mismatch"] else ("warn" if d["missing_fields"] else "pass")
    notes += [f"missing field {f}" for f in d["missing_fields"]] + [f"type {t}" for t in d["type_mismatch"]]
    cells["options"] = "fail" if d["option_mismatch"] else "pass"
    notes += [f"option {o['field']}/{o['option']}: {o['have']} != {o['want']}" for o in d["option_mismatch"]]
    notes += [f"options {f}: the board's own scale is kept (capture wins, §13.1)" for f in d.get("capture_wins", [])]
    bad_ws = [w for w in spec.get("workstreams") or [] if not w["ok"]]
    cells["workstreams"] = "n/a" if estate else ("fail" if bad_ws or not spec.get("workstreams") else "pass")
    notes += [f"workstream {w['name']}: {w['color']} but kind {w['kind']} wants {w['expected_color']}" if w["kind"] else
              f"workstream {w['name']}: no §13.4 kind (start its description with [Product], [Research], [Growth], "
              "[Revenue], [Content], [Ops], [Risk] or [Experiments]; the kind sets the colour)" for w in bad_ws]
    it = _field(spec, "Iteration")
    conf = (it or {}).get("configuration") or {}
    cells["iteration"] = "unknown" if not conf else ("pass" if conf.get("duration") == CYCLE_DAYS and
                                                     str(conf.get("startDay")) in ("1", "MONDAY") else "fail")
    vm = d["view_mismatch"] if role != "org" else [v for v in d["view_mismatch"] if v["view"] != "Workstream Overview"]
    cells["views"] = "fail" if d["missing_views"] else ("warn" if vm else "pass")
    notes += [f"missing view {v}" for v in d["missing_views"]] + [f"view {v['view']}: {'; '.join(v['problems'])}" for v in vm]
    order = [v["name"] for v in spec.get("views") or []]
    want_order = [v["name"] for v in (ESTATE_VIEWS if estate else VIEWS) if v["name"] in order]
    if [n for n in order if n in want_order] != want_order:
        cells["views"] = "warn" if cells["views"] == "pass" else cells["views"]
        notes.append("view tabs are not in §13.5 order (reorder in the UI)")
    wf_bad = []
    for words, on_org, on_tpl in WORKFLOWS:
        if estate and words == "auto-add":
            continue
        want = on_tpl if role == "template" else on_org
        have = next((w for w in spec.get("workflows") or [] if words.split()[-1] in (w.get("name") or "").lower()), None)
        if have is None:
            wf_bad.append(f"{words}: not captured")
        elif bool(have.get("enabled")) != want:
            wf_bad.append(f"{have.get('name')}: enabled={have.get('enabled')} (want {want})")
    cells["workflows"] = "warn" if wf_bad else "pass"
    notes += [f"workflow {w}" for w in wf_bad]
    approved_public = bool(resolver and owner and resolver.project_visibility_approved(owner))
    cells["visibility"] = "pass" if not spec.get("public") or (approved_public and role == "org") else "fail"
    if cells["visibility"] == "fail":
        notes.append("public without an approved visibility item (the template and the Estate stay private)")
    cells["template"] = "pass" if bool(spec.get("template")) == (role == "template") else "warn"
    cells["mode"] = "pass" if spec.get("mode") == "A" else "warn"
    if spec.get("mode") != "A":
        notes.append("issue fields on the board: the user chooses Mode A or B before the template is built (§13.1)")
    fail = any(v == "fail" for v in cells.values())
    return {"command": "project", "action": "lint", "owner": owner, "number": spec.get("number"), "role": role,
            "result": "fail" if fail else "pass", "cells": cells, "notes": notes, "logs": []}


# =====================================================================================================
# estate-plan (§13.10): the cross-org personal Estate project on CompleteDotTech
# =====================================================================================================
def estate_orgs(resolver: Resolver, *, allow_t3: bool = False, refusals: list[str] | None = None) -> list[dict]:
    """In-scope orgs for the Estate's Org field: T1, T2, T2-R (T3 only after sign-off; never HOLD or excluded).
    A T3 org also needs a valid record, and its entry keeps that record's id as
    `signoff_id` so estate_plan can carry it onto the jobs that bring the org into the personal board.
    A T3 org without a valid record is omitted; when `refusals` is a list, each such org is reported there as
    `t3-signoff:<code>:<login>`."""
    from . import signoff
    out = []
    groups = (resolver.registry.get("profile") or {}).get("org_directory") or []
    keys = [o for g in groups for o in (g or {}).get("orgs") or []] or list(resolver.registry.get("orgs") or {})
    for key in keys:
        st = resolver.owner_status(key)
        if st in ("excluded", "hold") or resolver.family_hold(key) or resolver.is_placeholder(key):
            continue
        try:
            row = resolver.brand_org(key)
        except NeedsInput:
            continue
        tier = str(row.get("tier") or "").split()[0]
        rec = None
        if tier == "T3":
            if not allow_t3:
                continue
            rec, why = signoff.evaluate([key, *resolver.aliases(key)])
            if rec is None:
                code = (why or "missing").partition(":")[0]
                if refusals is not None:
                    refusals.append(f"t3-signoff:{code}:{resolver.canonical(key)}")
                continue
        if tier in TIER_COLOR:
            entry = {"login": resolver.canonical(key), "name": row.get("display_name") or key, "tier": tier}
            if rec is not None and rec.get("id"):
                entry["signoff_id"] = str(rec["id"])
            out.append(entry)
    return out


TIER_PREFIX_T3 = "T3: "  # the Org-field option description is "{tier}: {login}" (estate_plan)
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _job_tokens(job: dict) -> set[str]:
    """Whole values a job names, lowercased: every string in it, the value of a `key=value` argv element and every
    double-quoted literal inside a GraphQL string. An org matches only a whole token, never a substring, so a job
    for `Acme-Tools` or `Acme Tools` is not credited to a T3 org named `Acme`
    (tests/test_t3_signoff_require.py::test_estate_plan_stamping_matches_whole_names_not_substrings)."""
    out: set[str] = set()

    def walk(v):
        if isinstance(v, str):
            out.add(v.lower())
            out.add(v.partition("=")[2].lower())
            for m in _QUOTED.finditer(v):
                try:
                    out.add(json.loads(m.group(0)).lower())
                except ValueError:
                    out.add(m.group(1).lower())
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(job)
    out.discard("")
    return out


def _readme_signoff_ids(orgs: list[dict], text: str, others: tuple[str, ...] = ()) -> list[str]:
    """The signoff_id of every org in ORGS that carries one and whose login or display name appears in TEXT
    (a README Markdown table, say). Case-insensitive, on word boundaries: a name inside a longer word or a
    hyphenated name (`Acme` in `Acme-Tools`) does not match. OTHERS are the names of non-T3 orgs: they are blanked out of
    TEXT first, so `Acme` does not match inside the longer `Acme Tools`. An empty name matches nothing."""
    out: list[str] = []
    for x in sorted((x for x in others if x), key=len, reverse=True):
        text = re.sub(r"(?<![\w-])" + re.escape(str(x)) + r"(?![\w-])", " ", text, flags=re.IGNORECASE)
    for o in orgs:
        if not o.get("signoff_id"):
            continue
        for name in (o.get("login"), o.get("name")):
            if not name:
                continue
            if re.search(r"(?<![\w-])" + re.escape(str(name)) + r"(?![\w-])", text, re.IGNORECASE):
                out.append(str(o["signoff_id"]))
                break
    return out


def _stamp_estate_orgs(jobs: list[dict], orgs: list[dict]) -> None:
    """Each job that names a signed-off T3 org (its Org-field option, its login) carries
    that org's record. The jobs target @me, so stamping by target owner never finds the T3 grant; several T3 orgs on
    one job give `signoff_ids` (signoff.stamp_associations). A `--readme` Markdown value names orgs inside its text,
    so it is also searched by name. An org's `labels` (its captured option names and descriptions, see captured_t3)
    credit a job that quotes one of them as a whole token. No-op when no org carries a signoff_id.
    (tests/test_t3_signoff_require.py::test_estate_plan_jobs_carry_the_t3_orgs_signoff)"""
    from . import signoff
    t3 = [o for o in orgs if o.get("signoff_id")]
    if not t3:
        return
    # a name that is also another org's login or display name is ambiguous: only that org's login or its
    # `T3: login` description credits the job (exact identity, never a shared label)
    others = {x.lower() for o in orgs if not o.get("signoff_id") for x in (o["login"], o["name"])}
    # for README text the display name counts only when it is not ambiguous; the login always may
    readme_orgs = [o if o["name"].lower() not in others else {**o, "name": ""} for o in t3]
    for j in jobs:
        tokens = _job_tokens(j)
        ids = [o["signoff_id"] for o in t3
               if o["login"].lower() in tokens or f"{TIER_PREFIX_T3}{o['login']}".lower() in tokens
               or (o["name"].lower() in tokens and o["name"].lower() not in others)
               or any(lab in tokens and lab not in others for lab in o.get("labels", []))]
        argv = j.get("argv") if isinstance(j.get("argv"), list) else []
        for i, arg in enumerate(argv[:-1]):
            if arg == "--readme" and isinstance(argv[i + 1], str):
                ids += _readme_signoff_ids(readme_orgs, argv[i + 1], tuple(others))
        signoff.stamp_associations(j, list(dict.fromkeys(ids)))


def estate_plan(resolver: Resolver, *, source: str | None = None, copied: dict | None = None, user_id: int | None = None,
                approval_id: str | None = None, allow_t3: bool = False, reviewed: str | None = None) -> dict:
    t3_refusals: list[str] = []
    orgs = estate_orgs(resolver, allow_t3=allow_t3, refusals=t3_refusals)
    if len(orgs) > 50:
        raise ShowcaseError("more than 50 orgs for the Org single-select", log="usage")
    org_field = dict(ESTATE_FIELDS[0], options=[(o["name"], TIER_COLOR[o["tier"]], f"{o['tier']}: {o['login']}") for o in orgs])
    extra = [org_field, *ESTATE_FIELDS[1:]]
    plan = copy_plan("@me", role="estate", source=source, copied=copied, resolver=resolver, approval_id=approval_id,
                     user_id=user_id, extra_fields=extra, views=[dict(v) for v in ESTATE_VIEWS], reviewed=reviewed,
                     display_name="CompleteTech Estate", status_update=False, allow_t3=allow_t3)
    plan["action"] = "estate-plan"
    plan["orgs"] = orgs
    plan["logs"] = list(dict.fromkeys([*plan.get("logs", []), *t3_refusals]))
    plan["reads"] +=[{"name": f"estate-items:{o['login']}",
                       "argv": ["gh", "search", "issues", "--owner", o["login"], "--label", "estate", "--state", "open",
                                "--json", "url", "--limit", "200"]} for o in orgs]
    plan["pending"].append({"why": "add each labelled Initiative or Feature with `gh project item-add N --owner @me --url URL` "
                                   "(test cross-org adding with one item first, T4)"})
    if copied is not None:
        url = project_url("@me", plan.get("number"))
        plan["jobs"].append(_browser(f"p{PHASE}-me-project-{plan.get('number')}-private", "@me", f"{url}/settings",
                                     [f"Open {url}/settings.", "Check that 'Visibility' reads Private; change nothing.",
                                      "Screenshot it into state/screens/projects/me/."], "project-check",
                                     "§13.2: the Estate stays private."))
    _, retained = captured_t3(resolver, _captured_spec(copied), allow_t3)
    listed = {o["login"].lower() for o in orgs}
    # an org both listed and retained is stamped with its captured labels; copies keep plan["orgs"] unchanged
    retained_labels = {r["login"].lower(): r["labels"] for r in retained}
    stamp_orgs = [{**o, "labels": list(dict.fromkeys([*o.get("labels", []), *retained_labels[o["login"].lower()]]))}
                  if o["login"].lower() in retained_labels else o for o in orgs]
    _stamp_estate_orgs(plan["jobs"], stamp_orgs + [o for o in retained if o["login"].lower() not in listed])
    return plan


# =====================================================================================================
# CLI
# =====================================================================================================
ACTIONS = ("capture-query", "normalize", "copy-plan", "readme", "lint", "estate-plan")


def register(sub) -> None:
    s = sub.add_parser("project", help="GitHub Projects: capture query, template spec, copy plans, README, lint, Estate")
    s.add_argument("action", choices=ACTIONS)
    s.add_argument("--owner", help="project owner (org login, CompleteDotTech or @me)")
    s.add_argument("--number", type=int, help="project number")
    s.add_argument("--capture", help="captured GraphQL JSON (normalize, lint, readme)")
    s.add_argument("--rest-fields", help="REST fields JSON (integer field ids) for normalize")
    s.add_argument("--copied", help="copy-plan/estate-plan: capture (or normalized spec) of the board after the copy")
    s.add_argument("--target", help="copy-plan: target org (or @me)")
    s.add_argument("--source", help="copy-plan: OWNER/NUMBER to copy (the CompleteTech-LLC template; fallback Pick-Your-AI/1)")
    s.add_argument("--role", choices=("org", "template", "estate"), default="org")
    s.add_argument("--title")
    s.add_argument("--display-name", help="org display name (default: brand.yaml)")
    s.add_argument("--workstreams", help="YAML or JSON list of {name, kind, description} for the org's Workstream options")
    s.add_argument("--repos", help="comma-separated OWNER/REPO to link (same owner)")
    s.add_argument("--approval-id", help="the create-project job's approval_id (default q41.orgs; estate-plan q41.estate)")
    s.add_argument("--user-id", type=int, help="numeric user id for user-owned view paths (gh api user --jq .id)")
    s.add_argument("--out-of-scope", help="README: what the board does not track")
    s.add_argument("--reviewed", help="README 'Last reviewed' date (default today)")
    s.add_argument("--registry", help="registry/estate.yaml (estate-plan; display names)")
    s.add_argument("--approved", help="decisions/approved.tsv")
    s.add_argument("--approved-yaml", help="decisions/APPROVED_ACTIONS.yaml (approved org renames and merges, CQ-03)")
    s.add_argument("--actions", help="decisions/estate-actions.json (the old and new names of approved org renames)")
    s.add_argument("--allow-t3", action="store_true", default=argparse.SUPPRESS)
    s.add_argument("--no-status-update", action="store_true")
    s.add_argument("--files-dir", help="copy-plan: write the REST view bodies under DIR (paths as in `files`)")
    s.add_argument("--out", help="normalize: write the template spec JSON here; readme: write the README here")
    s.add_argument("--jobs", help="append the writer jobs (JSON lines) to FILE")
    s.set_defaults(func=cmd_project)


def _load(path):
    if not path:
        return None
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ShowcaseError(f"cannot read {path}: {exc}", log="usage")
    if str(path).endswith((".yaml", ".yml")):
        from .config import load_yaml_text
        return load_yaml_text(text)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ShowcaseError(f"{path}: not JSON: {exc}", log="usage")


def _resolver(args) -> Resolver:
    from .config import load_brand
    return Resolver.from_paths(load_brand(getattr(args, "config", None)), args.registry, args.approved,
                               getattr(args, "approved_yaml", None), getattr(args, "actions", None))


def _parse_repos_arg(raw: str | None) -> list[str]:
    """The --repos list: split on ',', every entry stripped, empty entries skipped (a trailing comma is fine), each one
    canonicalised (signoff.canonical_repo). A malformed entry refuses the whole command (usage), so nothing is planned."""
    from . import signoff
    out: list[str] = []
    for piece in (raw or "").split(","):
        entry = piece.strip()
        if not entry:
            continue
        canon = signoff.canonical_repo(entry)
        if canon is None:
            raise ShowcaseError(f"--repos entry {entry!r} is not a valid [OWNER/]REPO name", log="usage")
        out.append(canon)
    return out


def cmd_project(args):
    from .org import append_jobs
    act = args.action
    if act == "capture-query":
        if not args.owner or not args.number:
            raise ShowcaseError("capture-query needs --owner and --number", log="usage")
        owner = args.owner if is_user(args.owner) else _resolver(args).canonical(args.owner)  # a renamed org (CQ-03)
        res = capture_query(owner, args.number)
        if owner != args.owner:
            res["logs"] = [*res["logs"], f"org-alias:{args.owner}->{owner}"]
        return res, OK
    if act == "normalize":
        cap = _load(args.capture)
        if cap is None:
            raise ShowcaseError("normalize needs --capture FILE", log="usage")
        spec = normalize(cap, _load(args.rest_fields))
        if args.out:
            Path(args.out).write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"command": "project", "action": act, "result": "ok", "spec": spec, "out": args.out,
                "logs": ["needs-user-choice:issue-fields"] if spec["mode"] != "A" else []}, OK
    r = _resolver(args)
    if act == "lint":
        cap = _load(args.capture)
        if cap is None:
            raise ShowcaseError("lint needs --capture FILE", log="usage")
        owner = args.owner
        name = args.display_name or brand_display_name(r, owner)
        res = lint(cap, role=args.role, owner=owner, display_name=name, resolver=r)
        return res, CHECK_FAILED if res["result"] == "fail" else OK
    if act == "readme":
        cap = _load(args.capture or args.copied)
        if cap is None:
            raise ShowcaseError("readme needs --capture FILE (the board after the copy)", log="usage")
        spec = cap if "std" in cap and "fields" in cap else normalize(cap)
        owner = args.owner or args.target
        if not owner:
            raise ShowcaseError("readme needs --owner", log="usage")
        estate = args.role == "estate" or is_user(owner)
        name = args.display_name or ("CompleteTech Estate" if estate else brand_display_name(r, owner))
        if not name:
            raise NeedsInput("display-name", f"{owner} has no display_name in references/brand.yaml (pass --display-name)")
        canon = r.canonical(owner) if not estate else "@me"
        # the same privacy gate as copy-plan: a board that is public or may go public names no repository
        repos, gate = _readme_repos(spec, canon, "estate" if estate else "org", r, _parse_repos_arg(args.repos))
        text, logs = readme(canon, name, spec.get("number"), view_numbers(spec),
                            fields=doc_fields(spec, estate=estate), repositories=repos,
                            out_of_scope=args.out_of_scope, reviewed=args.reviewed, estate=estate)
        logs = gate + logs
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        return {"command": "project", "action": act, "owner": owner, "result": "ok", "readme": text, "out": args.out,
                "logs": logs}, OK
    copied = _load(args.copied)
    if act == "estate-plan":
        res = estate_plan(r, source=args.source, copied=copied, user_id=args.user_id, approval_id=args.approval_id,
                          allow_t3=getattr(args, "allow_t3", False), reviewed=args.reviewed)
    else:
        if not args.target:
            raise ShowcaseError("copy-plan needs --target ORG (or @me)", log="usage")
        ws = _load(args.workstreams)
        res = copy_plan(args.target, role=args.role, source=args.source, title=args.title, display_name=args.display_name,
                        copied=copied, workstreams=ws, repositories=_parse_repos_arg(args.repos) or None,
                        approval_id=args.approval_id, resolver=r, user_id=args.user_id, out_of_scope=args.out_of_scope,
                        reviewed=args.reviewed, status_update=not args.no_status_update, allow_t3=getattr(args, "allow_t3", False))
    if args.jobs and res.get("files") and not args.files_dir:
        # each REST view job reads its body with --input; the writer's guard refuses a body it cannot read
        raise ShowcaseError("copy-plan writes REST view bodies: pass --files-dir DIR with --jobs so each view job's --input "
                            "names a file that exists (nothing was appended)", log="usage")
    if args.files_dir and res.get("files"):
        res["written"] = write_files(res["files"], args.files_dir)
        # the writer and its guard must read each body from where it was written, whatever --files-dir was
        base = Path(args.files_dir).resolve()
        for j in res.get("jobs") or []:
            argv = j.get("argv") or []
            for i, a in enumerate(argv[:-1]):
                if a == "--input" and argv[i + 1] in res["files"]:
                    argv[i + 1] = str(base / argv[i + 1])
    append_jobs(args.jobs, res.get("jobs") or [])
    return res, OK
