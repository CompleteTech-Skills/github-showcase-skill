"""PR #1 review round 2, project unit: view filters follow quoted workstream renames, and the public-visibility job
is planned for org rollout boards only. Synthetic Northwind fixtures (tests/fixtures/project)."""
import json

from conftest import ROOT

from ctshowcase import project as PJ
from ctshowcase.resolver import Resolver

FIX = ROOT / "tests" / "fixtures" / "project"
N = "Northwind-Trading-Co"
PRE = "p6.3-Northwind-Trading-Co-project-3"


def cap(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def resolver(brand, rows=()):
    return Resolver(brand, {}, {"rows": set(rows), "ids": set(), "answers": {}, "actions": [], "extra": []})


def with_backlog_filter(flt, ws_names=None):
    c = cap("copy-capture.json")
    p = c["data"]["organization"]["projectV2"]
    for v in p["views"]["nodes"]:
        if v.get("number") == 5:
            v["filter"] = flt
    if ws_names:
        for f in p["fields"]["nodes"]:
            if f.get("name") == "Workstream":
                for o in f["options"]:
                    o["name"] = ws_names.get(o["name"], o["name"])
    return c


def backlog_filter_job(plan):
    return next((j for j in plan["jobs"] if j["id"] == f"{PRE}-view-5-filter"), None)


# ----------------------------------------------------------------------------------- 4373814815 quoted filter values
def test_quoted_workstream_value_follows_the_rename(brand):
    ws = [{"name": "Lab notebooks", "kind": "Research", "description": "Experiment logs"}]
    plan = PJ.copy_plan(N, copied=with_backlog_filter('status:Backlog,Ready workstream:"Research"'),
                        resolver=resolver(brand), workstreams=ws)
    assert any(j["id"] == f"{PRE}-options-workstream" for j in plan["jobs"])
    job = backlog_filter_job(plan)
    assert job is not None, "the option is renamed but the view still filters on the old name"
    assert 'filter: "status:Backlog,Ready workstream:\\"Lab notebooks\\""' in job["argv"][4]


def test_quoted_single_word_rename_keeps_valid_quotes(brand):
    ws = [{"name": "Discovery", "kind": "Research", "description": "Interviews"}]
    plan = PJ.copy_plan(N, copied=with_backlog_filter('workstream:"Research"'), resolver=resolver(brand), workstreams=ws)
    assert 'filter: "workstream:\\"Discovery\\""' in backlog_filter_job(plan)["argv"][4]


def test_second_rename_of_a_multiword_name_this_code_quoted(brand):
    # a first run renamed Research to "Pricing research" and quoted it in the filter; the second rename must follow
    c = with_backlog_filter('status:Backlog,Ready workstream:"Pricing research",Ops', {"Research": "Pricing research"})
    ws = [{"name": "Lab notebooks", "kind": "Research", "description": "Experiment logs"}]
    plan = PJ.copy_plan(N, copied=c, resolver=resolver(brand), workstreams=ws)
    assert 'filter: "status:Backlog,Ready workstream:\\"Lab notebooks\\",Ops"' in backlog_filter_job(plan)["argv"][4]


def test_unquoted_value_still_follows_and_word_boundaries_hold(brand):
    ws = [{"name": "Pricing research", "kind": "Research", "description": "Price experiments"}]
    plan = PJ.copy_plan(N, copied=with_backlog_filter("workstream:Research,Ops -label:Researchers"),
                        resolver=resolver(brand), workstreams=ws)
    assert 'filter: "workstream:\\"Pricing research\\",Ops -label:Researchers"' in backlog_filter_job(plan)["argv"][4]


def test_renames_apply_in_one_pass_not_chained(brand):
    # Product's option becomes "Research" while Research's becomes "Lab notebooks": a Product filter must land on
    # "Research", not be renamed a second time to "Lab notebooks" (and vice versa)
    ws = [{"name": "Research", "kind": "Product", "description": "Product research"},
          {"name": "Lab notebooks", "kind": "Research", "description": "Experiment logs"}]
    plan = PJ.copy_plan(N, copied=with_backlog_filter("workstream:Product -workstream:Research"),
                        resolver=resolver(brand), workstreams=ws)
    assert 'filter: "workstream:Research -workstream:\\"Lab notebooks\\""' in backlog_filter_job(plan)["argv"][4]


# ----------------------------------------------------------------------------------- 4373814820 template stays private
def test_template_never_gets_a_public_visibility_job(brand):
    ok = resolver(brand, rows=[("project-visibility", "CompleteTech-LLC", "*", "")])
    plan = PJ.copy_plan("CompleteTech-LLC", role="template", copied=cap("copy-capture.json"), resolver=ok)
    assert not [j for j in plan["jobs"] if j["id"].endswith("-visibility")]
    assert not any("Public" in s for j in plan["jobs"] for s in j.get("steps") or [])
    assert "visibility:private (template stays private)" in plan["logs"]
    guard_form = resolver(brand, rows=[("graphql", "project-visibility", "*", "")])
    plan = PJ.copy_plan("CompleteTech-LLC", role="template", copied=cap("copy-capture.json"), resolver=guard_form)
    assert not [j for j in plan["jobs"] if j["id"].endswith("-visibility")]


def test_org_board_with_approval_still_gets_the_visibility_job(brand):
    ok = resolver(brand, rows=[("project-visibility", N, "*", "")])
    ws = [{"name": "Storefront", "kind": "Product", "description": "The online store"}]
    plan = PJ.copy_plan(N, copied=cap("copy-capture.json"), resolver=ok, workstreams=ws)
    vis = [j for j in plan["jobs"] if j["id"] == f"{PRE}-visibility"]
    assert vis and vis[0]["kind"] == "browser" and any("Public" in s for s in vis[0]["steps"])
    assert "visibility:private (no approval)" not in plan["logs"]


def test_estate_never_gets_a_public_visibility_job(brand):
    reg = {"orgs": {N: {}}}
    r = Resolver(brand, reg, {"rows": {("project-visibility", "CompleteDotTech", "*", ""),
                                       ("graphql", "project-visibility", "*", "")},
                              "ids": set(), "answers": {}, "actions": [], "extra": []})
    plan = PJ.estate_plan(r, copied=cap("estate-copy-capture.json"), user_id=42)
    assert not [j for j in plan["jobs"] if j["id"].endswith("-visibility")]
    assert "visibility:private (estate stays private)" in plan["logs"]
