"""Decision 24 enterprise module: read-only queries, offline checks on a synthetic snapshot."""
import copy
import json
import re

from conftest import ROOT, run_cli

from ctshowcase import enterprise as E

SNAP = ROOT / "tests" / "fixtures" / "enterprise" / "snapshot-before.json"


def load():
    return json.loads(SNAP.read_text())


def test_no_executed_query_contains_a_mutation():
    for f in E.QUERIES.glob("*.graphql"):
        assert not re.search(r"\bmutation\b", f.read_text(), re.I), f.name
        E.query_text(f.stem)
    for f in E.MUTATIONS.glob("*.graphql"):
        assert f.read_text().lstrip().startswith("mutation"), f.name


def test_snapshot_paginates_with_a_fake_runner():
    pages = {"q_orgs": [({"login": "A"}, True), ({"login": "B"}, False)]}
    calls = []

    def run(name, **v):
        calls.append((name, v.get("after")))
        if name == "q_profile":
            return {"enterprise": {"id": "E", "slug": "s", "ownerInfo": {}}}
        if name == "q_orgs":
            node, more = pages["q_orgs"][0 if v.get("after") is None else 1]
            return {"enterprise": {"organizations": {"nodes": [node], "pageInfo": {"hasNextPage": more, "endCursor": "c1"}}}}
        if name == "q_members":
            return {"enterprise": {"members": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}
        return {"enterprise": {"ownerInfo": {"outsideCollaborators": {"edges": [], "pageInfo": {"hasNextPage": False}}}}}
    snap = E.snapshot("s", run=run)
    assert [o["login"] for o in snap["sections"]["organizations"]] == ["A", "B"]
    assert ("q_orgs", "c1") in calls and set(snap["sha256"]) == {"profile", "organizations", "members", "outside_collaborators"}


def test_seat_check_lists_every_blocker():
    r = E.seat_check(load(), "romgenie")
    assert r["result"] == "fail"
    assert r["blockers"] == ["org-role:CompleteTech-LLC:OWNER", "collaborator:CompleteTech-Data/ohio-index",
                             "invitation:CompleteTech-Data"]


def test_doctor_cells(brand):
    r = E.doctor(load(), E.desired(), brand)
    c = r["cells"]
    assert c["E1"] == "fail" and c["E4"] == "pass" and c["E5"] == "fail" and c["E6"] == "fail"
    assert c["E7"] == "fail" and c["E13"] == "warn" and c["E10"] == "unknown"
    assert any("MetatronAngelAgent" in n for n in r["notes"])


def test_diff_and_danger_drift(brand):
    a, b = load(), copy.deepcopy(load())
    b["sections"]["profile"]["ownerInfo"]["twoFactorRequiredSetting"] = "ENABLED"
    b["sections"]["profile"]["billingInfo"]["allLicensableUsersCount"] = 1
    d = E.diff(a, b)
    assert d["changed"] and d["seats"] == [2, 1] and d["settings"]["twoFactorRequiredSetting"] == ["NO_POLICY", "ENABLED"]
    assert E.doctor(b, E.desired(), brand, baseline=a)["cells"]["E10"] == "fail"


def test_plan_prints_records_only(tmp_path):
    recs = E.plan(load(), E.desired())
    kinds = [r["kind"] for r in recs]
    assert kinds == ["enterprise-profile", "enterprise-domain-verify", "enterprise-domain-add"]
    assert all(r["approval"].startswith("enterprise/") for r in recs)
    out = tmp_path / "rec.jsonl"
    p = run_cli("enterprise", "plan", "--snapshot", SNAP, "--records", out)
    assert p.returncode == 0 and len(out.read_text().splitlines()) == 3


def test_cli_doctor_exit_code():
    p = run_cli("enterprise", "doctor", "--snapshot", SNAP)
    assert p.returncode == 1 and json.loads(p.stdout)["cells"]["E6"] == "fail"
    assert run_cli("enterprise", "snapshot").returncode == 2


def test_doctor_resolves_renamed_and_recased_org_logins(brand):
    """CQ-03: the snapshot shows the org's new login (CompleteTech-Security after org-001) while brand.yaml still keys the
    row by the old one; E5, E8 and E13 must still treat it as the in-scope org, and a re-cased login is the same org."""
    from ctshowcase.resolver import Resolver
    snap = copy.deepcopy(load())
    snap["sections"]["organizations"] = [{"login": "CompleteTech-Security", "isVerified": False},
                                         {"login": "metatronangelagent", "isVerified": False}]
    for m in snap["sections"]["members"]:
        if m["login"] == "CompleteDotTech":
            m["organizations"]["edges"] = [{"node": {"login": "CompleteTech-Security"}, "role": "MEMBER"}]
    rows = {("org-rename", "CompleTetech-Security", "*", "CompleteTech-Security")}
    res = Resolver(brand, {}, {"rows": rows, "ids": set(), "answers": {}, "actions": [], "extra": []})
    r = E.doctor(snap, E.desired(), brand, resolver=res)
    assert r["cells"]["E5"] == "fail" and any("E5" in n and "CompleteTech-Security" in n for n in r["notes"])
    assert r["cells"]["E8"] == "warn" and any("E8" in n and "CompleteTech-Security" in n for n in r["notes"])
    assert r["cells"]["E13"] == "warn" and any("E13" in n and "metatronangelagent" in n for n in r["notes"])
