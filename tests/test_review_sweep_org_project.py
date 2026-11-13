"""Review sweep (round 3) for the org, project and intake modules: star List membership, copy-plan ownership and job
ids, pins behind an unrun move or on HOLD, exposure flags, the leak scope, T3 sign-off, labels with unknown live
labels, the AI-Ascension exemption and workstream-only filter renames. Synthetic Northwind fixtures only."""
import copy
import json

import pytest

from conftest import ROOT, meta_dict

from ctshowcase import intake
from ctshowcase import org as O
from ctshowcase import project as PJ
from ctshowcase.config import Brand, load_yaml_text
from ctshowcase.context import RepoContext
from ctshowcase.errors import ShowcaseError
from ctshowcase.meta import normalize
from ctshowcase.resolver import Resolver

OFIX = ROOT / "tests" / "fixtures" / "org"
PFIX = ROOT / "tests" / "fixtures" / "project"
N, L = "Northwind-Trading-Co", "Northwind-Labs"
PRE = f"p6.3-{N}-project-3"
REN = [{"id": "ren-901", "owner": N, "repo": "ledger", "action": "rename", "new_name": "order-ledger"}]


def approvals(rows=(), ids=(), actions=()):
    return {"rows": set(rows), "ids": set(ids), "answers": {}, "actions": list(actions), "extra": []}


@pytest.fixture
def labs_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][L] = dict(raw["orgs"][N], display_name="Northwind Labs", nav_name="Northwind Labs", eyebrow="LABS")
    return Brand(raw, brand.path)


def registry():
    return load_yaml_text((OFIX / "registry.yaml").read_text(encoding="utf-8"))


def estate(brand, reg=None, *, ids=(), actions=REN, rows=(), metas=True):
    est = O.Estate(brand, Resolver(brand, reg or registry(), approvals(rows, ids, actions)))
    if metas:
        O.load_metas(OFIX / "meta", est)
    return est


def pcap(name="copy-capture.json"):
    return json.loads((PFIX / name).read_text(encoding="utf-8"))


def pcap_all_views():
    """The copy capture with every §13.5 view captured (numbers known), so the README is written in stage 2."""
    c = pcap()
    nodes = c["data"]["organization"]["projectV2"]["views"]["nodes"]
    for i, name in ((6, "My items"), (7, "Shipped")):
        nodes.append(dict(nodes[-1], id=f"PVTV_n{i}", number=i, name=name, filter=""))
    return c


def presolver(brand, rows=(), reg=None):
    return Resolver(brand, reg or {}, approvals(rows))


# ======================================================================================== star List membership
def _node(lid, name, items, total=None):
    return {"id": lid, "name": name, "slug": O.list_slug(name), "description": "", "isPrivate": False,
            "items": {"totalCount": len(items) if total is None else total,
                      "nodes": [{"id": rid, "nameWithOwner": full} for full, rid in items]}}


def _lists(*nodes):
    return {"data": {"viewer": {"login": "CompleteDotTech", "lists": {"totalCount": len(nodes), "nodes": list(nodes)}}}}


def _two_org_registry():
    reg = registry()
    reg["orgs"][L]["star_list"] = {"name": "Northwind Labs: built on", "description": ""}
    reg["orgs"][L]["favorites"] = [{"full_name": "pallets/flask"}]
    return reg


def _item_lists(job):
    q = job["argv"][-1]
    return sorted(x.strip(' "') for x in q.split("listIds: [", 1)[1].split("]", 1)[0].split(","))


def test_star_lists_of_two_orgs_sharing_a_favorite_keep_every_membership(labs_brand):
    est = estate(labs_brand, _two_org_registry())
    cap = _lists(_node("UL_nw", "Northwind: built on", []), _node("UL_labs", "Northwind Labs: built on", []),
                 _node("UL_other", "Favourite tools", [("pallets/flask", "R_flask")]))
    want = ["UL_labs", "UL_nw", "UL_other"]
    for org in (N, L):
        res, _ = O.pins(est, org, lists_capture=cap)
        item = [j for j in res["star_list"]["jobs"] if "list-item-pallets__flask" in j["id"]]
        assert item and _item_lists(item[0]) == want, (org, [j["argv"][-1] for j in item])


def test_star_list_withholds_item_jobs_when_a_list_page_is_truncated(labs_brand):
    est = estate(labs_brand)
    big = [(f"someone/tool-{i}", f"R_{i}") for i in range(100)]  # flask is a member beyond the first page
    cap = _lists(_node("UL_nw", "Northwind: built on", []), _node("UL_other", "Favourite tools", big, total=150))
    res = O.star_list_plan(est, N, lists_capture=cap, repo_ids={"pallets/flask": "R_flask"})
    assert res["result"] == "needs-input"
    assert "needs-input:star-lists-items-paged" in res["logs"]
    assert not [j for j in res["jobs"] if "list-item" in j["id"]]
    # a node captured without its items says nothing about membership either
    cap = _lists(_node("UL_nw", "Northwind: built on", []), {"id": "UL_other", "name": "Favourite tools"})
    res = O.star_list_plan(est, N, lists_capture=cap, repo_ids={"pallets/flask": "R_flask"})
    assert res["result"] == "needs-input" and not [j for j in res["jobs"] if "list-item" in j["id"]]
    # a complete capture still plans the union
    cap = _lists(_node("UL_nw", "Northwind: built on", []), _node("UL_other", "Favourite tools", big[:3], total=3))
    res = O.star_list_plan(est, N, lists_capture=cap, repo_ids={"pallets/flask": "R_flask"})
    assert res["result"] == "ok" and [j for j in res["jobs"] if "list-item" in j["id"]]


# ======================================================================================== copy-plan ownership and ids
def test_copy_plan_refuses_a_capture_of_another_owners_board(brand):
    r = presolver(brand)
    with pytest.raises(ShowcaseError) as exc:
        PJ.copy_plan("LibreEvolve", copied=pcap(), resolver=r, display_name="LibreEvolve")
    assert exc.value.log == "usage" and "Northwind-Trading-Co" in str(exc.value)
    with pytest.raises(ShowcaseError):  # the template stage too
        PJ.copy_plan("CompleteTech-LLC", role="template", copied=pcap(), resolver=r)
    with pytest.raises(ShowcaseError):  # the Estate is the user's board, never an org's
        PJ.estate_plan(Resolver(brand, {"orgs": {N: {}}}, approvals()), copied=pcap(), user_id=42)
    with pytest.raises(ShowcaseError):  # a capture that does not say whose board it is fails closed
        c = pcap()
        del c["data"]["organization"]["projectV2"]["url"]
        PJ.copy_plan(N, copied=c, resolver=r)
    # the target's own board, and the user's own Estate, still plan
    assert PJ.copy_plan(N, copied=pcap(), resolver=r)["stage"] == 2
    assert PJ.estate_plan(Resolver(brand, {"orgs": {N: {}}}, approvals()), copied=pcap("estate-copy-capture.json"),
                          user_id=42)["stage"] == 2


def test_copy_plan_accepts_the_board_under_a_former_login(brand):
    old = "Northwind-Old-Co"
    c = pcap()
    c["data"]["organization"]["projectV2"]["url"] = f"https://github.com/orgs/{old}/projects/3"
    r = Resolver(brand, {"orgs": {N: {"former_slugs": [old]}}}, approvals())
    assert PJ.copy_plan(N, copied=c, resolver=r)["owner"] == N


def test_copy_plan_link_ids_stay_unique_for_dotted_names(brand):
    plan = PJ.copy_plan(N, copied=pcap(), resolver=presolver(brand),
                        repositories=[f"{N}/order_ledger", f"{N}/order.ledger", f"{N}/order_ledger"])
    ids = [j["id"] for j in plan["jobs"]]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    links = [j["argv"][-1] for j in plan["jobs"] if (j.get("argv") or [])[:3] == ["gh", "project", "link"]]
    assert links == [f"{N}/order_ledger", f"{N}/order.ledger"]


# ======================================================================================== project README privacy
def test_a_board_that_may_go_public_names_no_repository_in_its_readme(brand):
    repos = [f"{N}/support-triage-agent", f"{N}/private-pricing-engine"]
    ok = presolver(brand, rows=[("project-visibility", N, "*", "")])
    plan = PJ.copy_plan(N, copied=pcap_all_views(), resolver=ok, repositories=repos, reviewed="2026-10-25")
    assert any(j["id"] == f"{PRE}-visibility" for j in plan["jobs"])
    text_job = next(j for j in plan["jobs"] if j["id"].startswith(f"{PRE}-text-"))
    assert "private-pricing-engine" not in (plan["readme"] or "") and "private-pricing-engine" not in json.dumps(text_job)
    assert "readme-links:repositories-omitted (the board may go public)" in plan["logs"]
    # the links themselves are still planned, and a board that stays private keeps the list
    assert any((j.get("argv") or [])[-1:] == [f"{N}/private-pricing-engine"] for j in plan["jobs"])
    assert plan["readme"] and "## Links" in plan["readme"]
    private = PJ.copy_plan(N, copied=pcap_all_views(), resolver=presolver(brand), repositories=repos,
                           reviewed="2026-10-25")
    assert f"{N}/private-pricing-engine" in private["readme"]


# ======================================================================================== filter renames
def test_rename_touches_only_workstream_predicates():
    ren = {"Research": "Lab notebooks"}
    assert PJ.rename_filter_values("workstream:Research label:Research", ren) == 'workstream:"Lab notebooks" label:Research'
    assert PJ.rename_filter_values('Research -workstream:"Research",Ops priority:Research', ren) == \
        'Research -workstream:"Lab notebooks",Ops priority:Research'
    assert PJ.rename_filter_values("Workstream:Research status:Done", ren) == 'Workstream:"Lab notebooks" status:Done'
    assert PJ.rename_filter_values('label:"Research" no:workstream', ren) == 'label:"Research" no:workstream'


# ======================================================================================== pins
def _ledger_estate(brand, ids):
    est = estate(brand, ids=ids)
    del est.metas[f"{N}/order-ledger".lower()]
    est.add_meta({"owner": N, "repo": "ledger", "visibility": "public", "description": "Orders."})  # not moved yet
    return est


def test_pin_waits_for_an_approved_move_that_has_not_run(labs_brand):
    res, _ = O.pins(_ledger_estate(labs_brand, ["ren-901"]), N)
    c = next(c for c in res["checks"] if c["target"] == "public" and c["position"] == 3)
    assert c["repo"] == "order-ledger" and c["result"] == "blocked"
    assert "pin-gated:order-ledger:ren-901" in res["logs"]
    ids = [j["id"] for j in res["jobs"]]
    assert f"p6.2-{N}-pin-public-3" not in ids
    order = next(j for j in res["jobs"] if j["id"].endswith("pin-public-order"))
    assert "order-ledger" not in " ".join(order["steps"])
    # once the move ran and the metadata was re-captured under the final slug, the pin is planned
    res, _ = O.pins(estate(labs_brand, ids=["ren-901"]), N)
    assert f"p6.2-{N}-pin-public-3" in [j["id"] for j in res["jobs"]]


def test_pins_on_a_hold_org_only_report(brand):
    org = "TouchedByAnAgent"
    reg = {"orgs": {org: {"tier": "T2", "final_repos": ["agent-demo"], "pins_public": [{"repo": "agent-demo"}]}}}
    est = O.Estate(brand, Resolver(brand, reg, approvals()))
    est.add_meta({"owner": org, "repo": "agent-demo", "visibility": "public", "description": "Demo."})
    res, _ = O.pins(est, org)
    assert [c["result"] for c in res["checks"]] == ["hold"]
    assert res["jobs"] == [] and "pins:hold" in res["logs"] and res["result"] == "hold"


# ======================================================================================== exposure flags
@pytest.mark.parametrize("flag", ["private-keep-private", "copyrighted-third-party-pdf-must-stay-private",
                                  "game-reverse-engineering-keep-private", "do-not-publish", "private-by-design",
                                  "possible-pii-in-output", "lan-device-inventory", "secrets-risk"])
def test_exposure_flags_match_anywhere_in_the_flag(labs_brand, flag):
    est = estate(labs_brand)
    est.flags = {f"{N}/order-ledger".lower(): [flag]}
    assert not est.is_public(f"{N}/order-ledger")
    data, _ = O.public_slice(est, N)
    assert "order-ledger" not in json.dumps(data)


def test_false_positive_exposure_flag_still_counts_as_public(labs_brand):
    est = estate(labs_brand)
    est.flags = {f"{N}/order-ledger".lower(): ["exposure-false-positive"]}
    assert est.is_public(f"{N}/order-ledger")


def test_exposure_flag_follows_a_move_to_its_target_slug(labs_brand, tmp_path):
    dec = tmp_path / "decisions.json"
    dec.write_text(json.dumps([{"owner": L, "repo": "lan-map-tool", "target_owner": N, "action": "move",
                                "flags": ["secrets-risk"]},
                               {"owner": N, "repo": "old-name", "new_name": "order-ledger", "action": "rename",
                                "flags": ["do-not-publish"]}]), encoding="utf-8")
    flags = O.load_flags(dec)
    assert flags[f"{N}/lan-map-tool"] == ["secrets-risk"] and flags[f"{L}/lan-map-tool"] == ["secrets-risk"]
    reg = registry()
    reg["orgs"][N]["final_repos"].append("lan-map-tool")
    reg["orgs"][N]["sections"][0]["repos"].append("lan-map-tool")
    est = O.Estate(labs_brand, Resolver(labs_brand, reg, approvals(actions=REN)), flags=flags)
    O.load_metas(OFIX / "meta", est)
    est.add_meta({"owner": N, "repo": "lan-map-tool", "visibility": "public", "description": "LAN map."})  # re-captured
    assert not est.is_public(f"{N}/lan-map-tool") and not est.is_public(f"{N}/order-ledger")
    data, _ = O.public_slice(est, N)
    assert "lan-map-tool" not in json.dumps(data) and "order-ledger" not in json.dumps(data)


def test_exposure_flag_keyed_by_the_final_slug_guards_the_repository_before_the_move(labs_brand):
    est = estate(labs_brand, ids=["ren-901"])
    del est.metas[f"{N}/order-ledger".lower()]
    est.add_meta({"owner": N, "repo": "ledger", "visibility": "public", "description": "Orders."})
    est.flags = {f"{N}/order-ledger".lower(): ["keep-private"]}
    assert not est.is_public(f"{N}/ledger")


# ======================================================================================== leak scope
def test_leak_check_finds_a_private_slug_under_a_former_login(labs_brand):
    reg = registry()
    reg["orgs"][N]["former_slugs"] = ["Northwind-Old-Co"]
    est = estate(labs_brand, reg)
    est.add_meta({"owner": N, "repo": "pricingengine", "visibility": "private"})
    scope, _ = O.estate_leak_scope(est)
    assert O.public_leaks("See github.com/Northwind-Trading-Co/pricingengine.", scope)
    assert O.public_leaks("See https://github.com/Northwind-Old-Co/pricingengine for details.", scope)
    assert O.public_leaks("Northwind-Old-Co/pricingengine", scope)


def test_leak_scope_covers_registry_notes_outside_org_rows(labs_brand):
    reg = registry()
    lines = {"top": "The registry keeps the steward seat open until the pricing audit closes in November.",
             "judge": "The judge moved the ledger pin down because its README still names the pilot client.",
             "pnote": "The steward account keeps the Northwind seat until the pricing audit closes in November.",
             "rom": "Free the second Northwind seat only after the billing contact confirms the transfer.",
             "why": "Pinned first because the investor demo next month opens with the triage agent walkthrough."}
    reg["notes"] = [lines["top"]]
    reg["judge_changes"] = [{"id": "jc-1", "change": lines["judge"]}]
    reg["profile"].update(notes=[lines["pnote"]], romgenie=lines["rom"],
                          pins=[{"repo": f"{N}/support-triage-agent", "why": lines["why"]}],
                          bio="Builds small tools and agents for the Northwind demo, one public repository at a time.")
    est = estate(labs_brand, reg)
    scope, _ = O.estate_leak_scope(est)
    for key, s in lines.items():
        assert any(h.startswith("internal-note:") for h in O.public_leaks(f"# Profile\n\n{s}\n", scope)), key
    assert O.public_leaks(f"# Profile\n\n{reg['profile']['bio']}\n", scope) == []  # public profile text is not a note


# ======================================================================================== T3 sign-off
def _t3_estate(labs_brand):
    reg = registry()
    reg["profile"]["pins"] = [f"{N}/support-triage-agent", "Pick-Your-AI/demo-board"]
    reg["profile"]["more_projects"] = ["Pick-Your-AI/demo-board"]
    reg["orgs"]["Pick-Your-AI"] = {"tier": "T3", "final_repos": ["demo-board"],
                                   "also_in_outgoing": [{"repo": "demo-board", "also_in": [N]}]}
    reg["orgs"][N]["favorites"] = list(reg["orgs"][N]["favorites"]) + [{"full_name": "Pick-Your-AI/demo-board"}]
    est = estate(labs_brand, reg)
    est.add_meta({"owner": "Pick-Your-AI", "repo": "demo-board", "visibility": "public", "description": "Demo board."})
    return est


def test_t3_repositories_wait_for_sign_off_on_public_profiles(labs_brand, t3_record):
    est = _t3_estate(labs_brand)
    data, logs = O.user_slice(est, "CompleteDotTech")
    assert "Pick-Your-AI/demo-board" not in json.dumps(data["pins"] + data["more_projects"])
    assert "t3-signoff:Pick-Your-AI/demo-board" in logs
    data, logs = O.public_slice(est, N)
    assert "demo-board" not in json.dumps(data["also_from"]) and "demo-board" not in json.dumps(data["favorites"])
    assert "t3-signoff:Pick-Your-AI/demo-board" in logs
    assert "demo-board" not in json.dumps(O.star_list_plan(est, N)["items"])
    # after co-owner sign-off the same repository is listed
    data, _ = O.user_slice(est, "CompleteDotTech", allow_t3=True)
    assert "Pick-Your-AI/demo-board" in [e["full_name"] for e in data["pins"]]
    data, _ = O.public_slice(est, N, allow_t3=True)
    assert "Pick-Your-AI/demo-board" in [e["full_name"] for e in data["also_from"]]


# ======================================================================================== labels with unknown live labels
def _nolabels_meta():
    raw = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))
    raw.pop("labels")
    raw.update(files=["README.md"], files_complete=True)
    return raw


def test_adopt_holds_labels_when_the_live_labels_are_unknown(brand):
    ctx = RepoContext(brand, normalize(_nolabels_meta()), None)
    res = intake.adopt(ctx, Resolver(brand, {}, approvals()))
    assert not [j for j in res["jobs"] if j["kind"] == "labels"], [j["argv"] for j in res["jobs"] if j["kind"] == "labels"]
    assert any("live labels" in p["why"] for p in res["pending"])


def test_org_labels_holds_a_repository_whose_labels_were_not_captured(labs_brand):
    est = estate(labs_brand)
    full = f"{N}/support-triage-agent"
    m = est.meta(full)
    m.pop("labels")
    m.update(files=["README.md"], files_complete=True)
    est.meta(f"{N}/.github").update(files=["README.md"], files_complete=True)
    res, _ = O.labels_plan(est, N)
    by = {r["repo"]: r for r in res["repos"]}
    assert by[full]["result"] == "unknown" and by[full]["log"] == "needs-input:labels"
    assert not [j for j in res["jobs"] if j.get("repo") == full]
    assert by[f"{N}/.github"]["result"] == "unknown"  # the .github capture has no labels either


def test_adopt_keeps_the_ai_ascension_exemption_under_any_spelling(brand):
    ctx = RepoContext(brand, normalize(meta_dict(owner="ai-ascension", repo="demo-tool",
                                                 labels=[{"name": "bug", "color": "d73a4a", "description": ""}])), None)
    res = intake.adopt(ctx, Resolver(brand, {}, approvals()))
    assert not [j for j in res["jobs"] if j["kind"] == "labels"]
    assert any(x.startswith("labels:ai-ascension") for x in res["logs"])
