"""Projects module (decision 23, STANDARD §13): capture query, normalize, copy plans, README, lint and the Estate.
Fixtures are synthetic captures shaped like the documented GraphQL responses (tests/fixtures/project)."""
import argparse
import copy
import json
import os
import re

import pytest

from conftest import ROOT

from ctshowcase import project as PJ
from ctshowcase.config import Brand, load_yaml_text
from ctshowcase.errors import NeedsInput, OK, Refused, ShowcaseError
from ctshowcase.resolver import Resolver

FIX = ROOT / "tests" / "fixtures" / "project"
N = "Northwind-Trading-Co"


def cap(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def cap_of(name, owner):
    """The same capture as a board of another owner (copy-plan stage 2 refuses a board that is not the target's)."""
    c = cap(name)
    p = c["data"]["organization"]["projectV2"]
    p["url"] = f"https://github.com/orgs/{owner}/projects/{p['number']}"
    return c


def resolver(brand, rows=(), registry=None):
    return Resolver(brand, registry or {}, {"rows": set(rows), "ids": set(), "answers": {}, "actions": [], "extra": []})


def all_argv(plan):
    return [a for j in plan["jobs"] for a in j.get("argv") or []]


# ----------------------------------------------------------------------------------------------- capture-query
def test_capture_query_org_and_user():
    r = PJ.capture_query("Pick-Your-AI", 1)
    g = r["reads"][0]["argv"]
    assert g[:3] == ["gh", "api", "graphql"] and "org=Pick-Your-AI" in g and "number=1" in g
    assert g[-1].startswith("query=@") and g[-1].endswith("project_capture.graphql")
    assert r["reads"][2]["argv"] == ["gh", "api", "--paginate", "orgs/Pick-Your-AI/projectsV2/1/fields"]
    assert "mutation" not in r["query"] and "options { id name color description }" in r["query"]
    u = PJ.capture_query("@me", 7)
    assert "login=CompleteDotTech" in u["reads"][0]["argv"] and u["reads"][1]["argv"][2] == "users/CompleteDotTech/projectsV2/7"
    with pytest.raises(ShowcaseError):
        PJ.capture_query("bad owner", 1)


def test_capture_query_reference_board_saves_raw_where_writer_reads():
    r = PJ.capture_query("Pick-Your-AI", 1)
    assert r["reads"][0]["out"] == "registry/projects/workstream-overview.template.json"  # writer.py PROJECT_CAPTURE
    assert "--out registry/projects/workstream-overview.spec.json" in r["normalize"]
    assert "registry/projects" in r["mkdir"]
    assert PJ.capture_query("CompleteTech-LLC", 4)["reads"][0]["out"] == "registry/projects/completetech-llc-4.capture.json"


# ----------------------------------------------------------------------------------------------- normalize
def test_normalize_reference_capture():
    s = PJ.normalize(cap("reference-capture.json"))
    assert s["number"] == 1 and s["mode"] == "A" and s["public"] is False
    st = PJ._field(s, "Status")
    assert st["dataType"] == "SINGLE_SELECT" and [o["name"] for o in st["options"]] == ["Todo", "In Progress", "Done"]
    assert st["databaseId"] == 1003
    v1 = s["views"][0]
    assert v1 == {"number": 1, "id": "PVTV_n1", "name": "Workstream Overview", "layout": "board", "filter": "",
                  "visible_fields": ["Title", "Assignees", "Priority"], "group_by": ["Workstream"],
                  "vertical_group_by": ["Status"], "sort_by": [["Priority", "asc"]]}
    ws = {w["name"]: w for w in s["workstreams"]}
    assert ws["Model evals"]["ok"] and ws["Model evals"]["kind"] == "Research"
    assert not ws["Launch"]["ok"] and ws["Launch"]["expected_color"] == "PINK"  # Growth is pink (§13.4)
    d = s["diff"]
    assert set(d["missing_fields"]) == {"Size", "Estimate", "Tags"}
    assert {(o["field"], o["option"]) for o in d["option_mismatch"]} >= {("Status", "Backlog"), ("Status", "Blocked")}
    assert set(d["missing_views"]) == {"Current cycle", "Backlog", "My items", "Shipped"}
    assert any(v["view"] == "Roadmap" for v in d["view_mismatch"])
    assert any(c["rule"] == "D2" and c["result"] == "fail" for c in s["short_description_checks"])  # no final period
    assert '"items"' not in json.dumps(s)  # items are never captured into the template


def test_normalize_accepts_bare_and_user_shapes_and_flags_issue_fields():
    raw = cap("reference-capture.json")
    bare = raw["data"]["organization"]["projectV2"]
    assert PJ.normalize({"projectV2": bare})["number"] == 1
    assert PJ.normalize(cap("estate-copy-capture.json"))["number"] == 7
    bare = copy.deepcopy(bare)
    bare["fields"]["nodes"][2]["isIssueField"] = True
    assert PJ.normalize(bare)["mode"] == "needs-user-choice"
    with pytest.raises(ShowcaseError):
        PJ.normalize({"data": {"viewer": {}}})


def test_short_description_rules():
    longest = "CompleteTech ManageEngine Tools"  # the longest display name (31 characters)
    ok = PJ.DESC["org"].format(name=longest)
    assert len(ok) == 114 and all(c["result"] == "pass" for c in PJ.short_description_checks(ok))
    lower = PJ.DESC["org"].format(name="jevplay.games")  # a display name may start lower-case or carry a dot
    assert all(c["result"] == "pass" for c in PJ.short_description_checks(lower, names=("jevplay.games",)))
    for bad in ("No final period", "One. Two sentences.", "Has an emoji \U0001F680.", "Built by Complete Tech LLC.",
                "Fill {name} in.", "y" * 121 + "."):
        assert any(c["result"] == "fail" for c in PJ.short_description_checks(bad)), bad
    for role in ("template", "estate"):
        assert all(c["result"] == "pass" for c in PJ.short_description_checks(PJ.DESC[role]))


# ----------------------------------------------------------------------------------------------- copy-plan
def test_copy_plan_stage_one(brand):
    r = resolver(brand, rows=[("create-project", N, "*", "")])
    plan = PJ.copy_plan(N, source="CompleteTech-LLC/4", resolver=r, approval_id="cp-northwind")
    j = plan["jobs"][0]
    assert plan["stage"] == 1 and len(plan["jobs"]) == 1
    assert j["argv"] == ["gh", "project", "copy", "4", "--source-owner", "CompleteTech-LLC", "--target-owner", N,
                         "--title", "Northwind Trading Co. — Workstreams"]
    assert j["kind"] == "create-project" and j["approval_id"] == "cp-northwind" and j["phase"] == "6.3"
    assert "--drafts" not in j["argv"] and plan["pending"] and not any("needs-approval" in x for x in plan["logs"])
    fb = PJ.copy_plan(N, resolver=resolver(brand))
    assert fb["jobs"][0]["argv"][4:7] == ["--source-owner", "Pick-Your-AI", "--target-owner"]
    assert any(x.startswith("fallback:direct-copy") for x in fb["logs"]) and "needs-approval:create-project:" + N in fb["logs"]


def test_copy_plan_never_targets_t3_hold_or_excluded(brand):
    for owner in ("Pick-Your-AI", "MetatronAngelAgent"):
        with pytest.raises(Refused):
            PJ.copy_plan(owner, resolver=resolver(brand))
    # reading or copying FROM the T3 reference board is fine
    assert PJ.copy_plan(N, source="Pick-Your-AI/1", resolver=resolver(brand))["jobs"][0]["argv"][5] == "Pick-Your-AI"


def test_copy_plan_stage_two(brand):
    ws = [{"name": "Storefront", "kind": "Product", "description": "The online store"},
          {"name": "Pricing research", "kind": "Research", "description": "Price experiments"},
          {"name": "Community", "kind": "Growth", "description": "Customer community"}]
    plan = PJ.copy_plan(N, source="CompleteTech-LLC/4", copied=cap("copy-capture.json"), resolver=resolver(brand),
                        workstreams=ws, repositories=[f"{N}/support-triage-agent", "Other-Org/x"], reviewed="2026-10-25")
    assert plan["stage"] == 2 and plan["number"] == 3
    jobs = {j["id"]: j for j in plan["jobs"]}
    pre = "p6.3-Northwind-Trading-Co-project-3"
    # missing fields are created inline with colours and descriptions; optional Tags is not
    size = jobs[f"{pre}-field-size"]["argv"][4]
    assert size.startswith("query=mutation { createProjectV2Field(input: {projectId: \"PVT_copy3\", dataType: SINGLE_SELECT")
    assert 'name: "XL", color: RED, description: "Too big; split into sub-issues"' in size
    assert f"{pre}-field-estimate" in jobs and f"{pre}-field-tags" not in jobs
    # Status options: the full list, every existing id kept, Todo renamed to Backlog
    st = jobs[f"{pre}-options-status"]["argv"][4]
    assert '{id: "opt31", name: "Backlog", color: GRAY' in st and '{id: "opt32", name: "In progress"' in st
    assert '{id: "opt33", name: "Done", color: GREEN' in st and 'name: "Blocked", color: RED' in st
    assert f"{pre}-options-priority" not in jobs  # already standard
    # workstreams: the generic options' ids are reused by kind; the unused Ops option is kept, never dropped
    w = jobs[f"{pre}-options-workstream"]["argv"][4]
    assert '{id: "opt201", name: "Storefront", color: BLUE, description: "[Product] The online store"}' in w
    assert '{id: "opt202", name: "Pricing research", color: PURPLE' in w and 'name: "Community", color: PINK' in w
    assert 'id: "opt203", name: "Ops"' in w
    # the Backlog view filter names a renamed option
    f5 = jobs[f"{pre}-view-5-filter"]["argv"][4]
    assert 'viewId: "PVTV_n5", filter: "status:Backlog,Ready workstream:\\"Pricing research\\""' in f5
    # missing views through REST with integer field ids
    my = jobs[f"{pre}-view-my-items"]
    assert my["argv"] == ["gh", "api", "-X", "POST", f"orgs/{N}/projectsV2/3/views", "--input",
                          "work/projects/Northwind-Trading-Co-3/view-6-my-items.json"]
    shipped = plan["files"]["work/projects/Northwind-Trading-Co-3/view-7-shipped.json"]
    assert shipped == {"name": "Shipped", "layout": "table", "filter": "status:Done updated:>=@today-30d",
                       "group_by": [1009], "sort_by": [[1012, "desc"]]}
    # text: the README waits for the new view numbers; links only for the same owner
    text = next(j for i, j in jobs.items() if re.fullmatch(f"{re.escape(pre)}-text-[0-9a-f]{{8}}", i))["argv"]
    assert text[:6] == ["gh", "project", "edit", "3", "--owner", N] and "--readme" not in text
    assert any("README needs every view number" in p["why"] for p in plan["pending"])
    assert jobs[f"{pre}-link-support-triage-agent"]["argv"] == ["gh", "project", "link", "3", "--owner", N, "--repo",
                                                               f"{N}/support-triage-agent"]
    assert "link-skipped:Other-Org/x (links need the same owner)" in plan["logs"]
    # browser jobs: workflows and settings, with exact steps
    wf = jobs[f"{pre}-workflows"]
    assert wf["kind"] == "browser" and wf["url"].endswith("/projects/3/workflows")
    assert any("'Auto-archive items'" in s and "is:closed updated:<@today-1m" in s for s in wf["steps"])
    assert jobs[f"{pre}-settings"]["kind"] == "browser" and "visibility:private (no approval)" in plan["logs"]
    # the first status update waits for the Shipped view this plan creates (planned once, from the re-capture)
    assert not any("-status-1" in i for i in jobs) and "status-update:shipped-view-pending" in plan["logs"]
    assert any("first status update links the Shipped view" in p["why"] for p in plan["pending"])
    # never drafts, items or deletes
    joined = " ".join(all_argv(plan))
    assert "--drafts" not in joined and not re.search(r"\bdelete", joined, re.I) and "item-add" not in joined
    assert "public:" not in joined and "--visibility" not in joined


def test_copy_plan_full_board_sets_the_readme(brand):
    c = cap("copy-capture.json")
    p = c["data"]["organization"]["projectV2"]
    p["views"]["nodes"] += [dict(p["views"]["nodes"][2], id="PVTV_n6", number=6, name="My items", filter="assignee:@me -status:Done"),
                            dict(p["views"]["nodes"][2], id="PVTV_n7", number=7, name="Shipped",
                                 filter="status:Done updated:>=@today-30d")]
    plan = PJ.copy_plan(N, source="CompleteTech-LLC/4", copied=c, resolver=resolver(brand), reviewed="2026-10-25",
                        status_update=False)
    text = next(j for j in plan["jobs"] if re.search(r"-text-[0-9a-f]{8}$", j["id"]))["argv"]
    rd = text[text.index("--readme") + 1]
    assert "[Shipped](https://github.com/orgs/Northwind-Trading-Co/projects/3/views/7)" in rd
    assert "{" not in rd and "Last reviewed: 2026-10-25" in rd and "needs-input:workstreams" in plan["logs"]
    full = PJ.copy_plan(N, source="CompleteTech-LLC/4", copied=c, resolver=resolver(brand), reviewed="2026-10-25")
    su = next(j for j in full["jobs"] if re.search(r"-status-1-[0-9a-f]{8}$", j["id"]))["argv"]
    assert "createProjectV2StatusUpdate" in su[4] and "p=PVT_copy3" in su and any(a.startswith("body=**Summary**") for a in su)
    assert any(a.startswith("body=") and "projects/3/views/7)" in a for a in su)


def test_board_readme_documents_the_boards_own_options(brand):
    """Round-2 defect: the README listed the template's Priority scale and generic workstreams over the board's own
    (capture wins, §13.1), and 'Todo' (GitHub's default Status option) tripped the TODO placeholder rule."""
    c = cap("copy-capture.json")
    p = c["data"]["organization"]["projectV2"]
    pri = next(f for f in p["fields"]["nodes"] if f.get("name") == "Priority")
    pri["options"] = [{"id": f"p{i}", "name": n, "color": "RED", "description": ""} for i, n in enumerate(("P0", "P1", "P2"))]
    ws = next(f for f in p["fields"]["nodes"] if f.get("name") == "Workstream")
    ws["options"].append({"id": "w9", "name": "Community \U0001F680", "color": "PINK", "description": "[Growth] Launch posts"})
    p["views"]["nodes"] += [dict(p["views"]["nodes"][2], id="PVTV_n6", number=6, name="My items", filter="assignee:@me -status:Done"),
                            dict(p["views"]["nodes"][2], id="PVTV_n7", number=7, name="Shipped",
                                 filter="status:Done updated:>=@today-30d")]
    want = [{"name": "Storefront", "kind": "Product", "description": "The shop"}]
    plan = PJ.copy_plan(N, source="CompleteTech-LLC/4", copied=c, resolver=resolver(brand), reviewed="2026-10-25",
                        status_update=False, workstreams=want)
    argv = next(j for j in plan["jobs"] if re.search(r"-text-[0-9a-f]{8}$", j["id"]))["argv"]
    rd = argv[argv.index("--readme") + 1]
    assert "capture-wins:Priority" in plan["logs"] and "| Priority | P0; P1; P2 |" in rd and "Urgent" not in rd
    assert "Storefront: [Product] The shop" in rd and "Community: [Growth] Launch posts" in rd and "\U0001F680" not in rd
    assert "| Status | Backlog: Captured, not committed;" in rd  # the Status jobs rename Todo to Backlog first
    # `project readme` on a capture documents the board as it is: its own Status flow, no TODO false positive
    text, logs = PJ.readme(N, "Northwind Trading Co.", 3, PJ.view_numbers(PJ.normalize(c)) | {"Priorities": 4, "Current cycle": 5},
                           fields=PJ.doc_fields(PJ.normalize(c)), reviewed="2026-10-25")
    assert "| Status | Todo; In Progress; Done |" in text and "Todo → In Progress → Done." in text
    assert "new items start in Todo" in text and "Blocked means" not in text and PJ.text_checks(text) == []
    assert "readme-emoji-stripped:Workstream/Community \U0001F680" in logs
    assert PJ.text_checks("Status: TODO later") == ["placeholder-text"]


def test_lint_names_a_workstream_without_a_kind():
    c = cap("reference-capture.json")
    c["data"]["organization"]["projectV2"]["fields"]["nodes"] = [
        dict(f, options=[{"id": "x", "name": "Model routing", "color": "BLUE", "description": ""}])
        if f.get("name") == "Workstream" else f for f in c["data"]["organization"]["projectV2"]["fields"]["nodes"]]
    notes = PJ.lint(c, owner=N)["notes"]
    assert any(n.startswith("workstream Model routing: no §13.4 kind") for n in notes)
    assert not any("None" in n for n in notes if n.startswith("workstream"))


def test_template_role(brand):
    plan = PJ.copy_plan("CompleteTech-LLC", role="template", copied=cap_of("copy-capture.json", "CompleteTech-LLC"),
                        resolver=resolver(brand))
    ids = [j["id"] for j in plan["jobs"]]
    assert plan["title"] == PJ.TEMPLATE_TITLE and plan["short_description"] == PJ.DESC["template"]
    mark = ids.index(next(i for i in ids if i.endswith("-mark-template")))
    assert all(not j.get("argv") or j["kind"] == "browser" or i <= mark
               for i, j in enumerate(plan["jobs"]) if j["kind"] != "browser")  # mark-template is the last API job
    roadmap = next(j for j in plan["jobs"] if j["id"].endswith("-view-2-filter"))
    assert '"type:Initiative,Feature -status:Done"' in roadmap["argv"][4]
    assert any(i.endswith("-insights") for i in ids) and any(i.endswith("-recommended") for i in ids)
    wf = next(j for j in plan["jobs"] if j["id"].endswith("-workflows"))
    assert any("Leave 'Auto-add to project' off on the template" in s for s in wf["steps"])


SCHEMA = os.environ.get("SHOWCASE_GRAPHQL_SCHEMA")


@pytest.mark.skipif(not SCHEMA, reason="set SHOWCASE_GRAPHQL_SCHEMA to a GitHub schema SDL to validate printed mutations")
def test_printed_mutations_validate_against_the_schema(brand):
    graphql = pytest.importorskip("graphql")
    from pathlib import Path
    schema = graphql.build_schema(Path(SCHEMA).read_text(encoding="utf-8"), assume_valid=True)
    schema._validation_errors = []
    ws = [{"name": "Storefront", "kind": "Product", "description": "x"}]
    plans = [PJ.copy_plan(N, copied=cap("copy-capture.json"), resolver=resolver(brand), workstreams=ws),
             PJ.copy_plan("CompleteTech-LLC", role="template", copied=cap_of("copy-capture.json", "CompleteTech-LLC"),
                        resolver=resolver(brand)),
             PJ.estate_plan(resolver(brand, registry={"orgs": {N: {}}}), copied=cap("estate-copy-capture.json"), user_id=42)]
    n = 0
    for plan in plans:
        for j in plan["jobs"]:
            q = next((a[6:] for a in j.get("argv") or [] if a.startswith("query=") and "mutation" in a), None)
            if q:
                errs = graphql.validate(schema, graphql.parse(q))
                assert not errs, (j["id"], [e.message for e in errs])
                n += 1
    assert n >= 8


# ----------------------------------------------------------------------------------------------- readme
def test_readme_template():
    nums = {v["name"]: i + 1 for i, v in enumerate(PJ.VIEWS)}
    text, logs = PJ.readme(N, "Northwind Trading Co.", 3, nums, repositories=[f"{N}/support-triage-agent"],
                           out_of_scope="personal errands", reviewed="2026-10-25")
    heads = [h for h in ("## Purpose", "## Views", "## Fields", "## Workflow", "## Cadence", "## Links") if h in text]
    assert len(heads) == 6 and not logs
    assert "It does not track personal errands." in text
    assert "| [Roadmap](https://github.com/orgs/Northwind-Trading-Co/projects/3/views/2) | What lands when? |" in text
    assert "| Status | Backlog: Captured, not committed; Ready: Specified; can start;" in text
    assert "Contact: Timothy Wayne Gregg, Timothy.Gregg@complete.tech" in text and "{" not in text
    assert PJ.text_checks(text) == []
    with pytest.raises(NeedsInput) as e:
        PJ.readme(N, "Northwind Trading Co.", 3, {"Roadmap": 2})
    assert e.value.log == "needs-input:view-numbers"
    _, logs = PJ.readme(N, "Northwind Trading Co.", 3, nums)
    assert logs == ["default:out-of-scope"]


# ----------------------------------------------------------------------------------------------- lint
def test_lint_reference_and_copy():
    res = PJ.lint(cap("reference-capture.json"), owner=N, display_name="Northwind Trading Co.")
    c = res["cells"]
    assert res["result"] == "fail"
    assert c["title"] == "fail" and c["short-description"] == "fail" and c["readme"] == "fail"
    assert c["fields"] == "fail" and c["options"] == "fail" and c["workstreams"] == "fail"
    assert c["views"] == "fail" and c["iteration"] == "pass" and c["visibility"] == "pass" and c["mode"] == "pass"
    assert c["workflows"] == "warn" and any("Auto-archive items" in n for n in res["notes"])


def test_lint_public_board_needs_approval(brand):
    raw = cap("copy-capture.json")
    raw["data"]["organization"]["projectV2"]["public"] = True
    assert PJ.lint(raw, owner=N, resolver=resolver(brand))["cells"]["visibility"] == "fail"
    ok = resolver(brand, rows=[("project-visibility", N, "*", "")])
    assert PJ.lint(raw, owner=N, resolver=ok)["cells"]["visibility"] == "pass"
    assert PJ.lint(raw, role="estate")["cells"]["visibility"] == "fail"  # the Estate stays private


# ----------------------------------------------------------------------------------------------- estate-plan
@pytest.fixture
def estate_resolver(brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"]["Northwind-Labs"] = dict(raw["orgs"][N], display_name="Northwind Labs")
    b = Brand(raw, brand.path)
    reg = load_yaml_text((ROOT / "tests" / "fixtures" / "org" / "registry.yaml").read_text(encoding="utf-8"))
    reg["profile"]["org_directory"].append({"group": "T3", "orgs": ["Pick-Your-AI"]})
    reg["orgs"]["Pick-Your-AI"] = {}
    return resolver(b, rows=[("create-project", "@me", "*", "")], registry=reg)


def test_estate_plan_stage_one(estate_resolver, t3_record):
    plan = PJ.estate_plan(estate_resolver, source="CompleteTech-LLC/4")
    assert plan["action"] == "estate-plan" and plan["owner"] == "@me"
    assert plan["jobs"][0]["argv"] == ["gh", "project", "copy", "4", "--source-owner", "CompleteTech-LLC", "--target-owner",
                                      "@me", "--title", "CompleteTech — Estate"]
    assert [o["login"] for o in plan["orgs"]] == [N, "Northwind-Labs"]  # T3 waits for co-owner sign-off
    searches = [r["argv"] for r in plan["reads"] if r["name"].startswith("estate-items:")]
    assert searches[0][:6] == ["gh", "search", "issues", "--owner", N, "--label"]
    assert len(PJ.estate_plan(estate_resolver, allow_t3=True)["orgs"]) == 3


def test_estate_plan_stage_two(estate_resolver):
    plan = PJ.estate_plan(estate_resolver, source="CompleteTech-LLC/4", copied=cap("estate-copy-capture.json"), user_id=42)
    jobs = {j["id"]: j for j in plan["jobs"]}
    pre = "p6.3-me-project-7"
    org = jobs[f"{pre}-field-org"]["argv"][4]
    assert 'name: "Northwind Trading Co.", color: BLUE, description: "T1: Northwind-Trading-Co"' in org
    assert f"{pre}-field-health" in jobs and f"{pre}-field-stream-kind" in jobs
    view = jobs[f"{pre}-view-estate-overview"]["argv"]
    assert view[:5] == ["gh", "api", "-X", "POST", "users/42/projectsV2/7/views"]
    assert any(x.startswith("estate-workstream:") for x in plan["logs"])
    assert jobs[f"{pre}-private"]["kind"] == "browser" and not any(i.startswith(f"{pre}-status-1") for i in jobs)
    assert all(j["org"] == "@me" for j in plan["jobs"])
    nouser = PJ.estate_plan(estate_resolver, copied=cap("estate-copy-capture.json"))
    assert any("numeric user id" in p.get("why", "") for p in nouser["pending"])


# ----------------------------------------------------------------------------------------------- CLI layer
def test_register_and_cmd_project(tmp_path):
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    PJ.register(p.add_subparsers(dest="command"))
    out = tmp_path / "spec.json"
    args = p.parse_args(["project", "normalize", "--capture", str(FIX / "reference-capture.json"), "--out", str(out)])
    res, code = args.func(args)
    assert code == OK and json.loads(out.read_text())["number"] == 1
    jobs, files = tmp_path / "jobs.jsonl", tmp_path / "files"
    args = p.parse_args(["project", "copy-plan", "--target", N, "--copied", str(FIX / "copy-capture.json"),
                         "--registry", str(ROOT / "tests" / "fixtures" / "org" / "registry.yaml"),
                         "--approved", str(tmp_path / "none.tsv"), "--files-dir", str(files), "--jobs", str(jobs)])
    res, code = args.func(args)
    assert code == OK and (files / "work/projects/Northwind-Trading-Co-3/view-6-my-items.json").is_file()
    lines = [json.loads(x) for x in jobs.read_text().splitlines()]
    assert all(set(j) >= {"id", "phase", "kind", "org", "note"} for j in lines)
    assert all(("argv" in j) != (j["kind"] == "browser") for j in lines)
    args = p.parse_args(["project", "capture-query", "--owner", "Pick-Your-AI", "--number", "1"])
    assert args.func(args)[0]["reads"][0]["argv"][-1].endswith("project_capture.graphql")
