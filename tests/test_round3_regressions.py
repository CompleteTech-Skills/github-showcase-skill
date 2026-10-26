"""Regression tests for test round 3 (real-data run of the org, project and content groups).

Synthetic Northwind registry and metadata only (tests/fixtures/org, tests/fixtures/project)."""
import copy
import json

import pytest

from conftest import ROOT, run_cli

from ctshowcase import org as O
from ctshowcase import project as PJ
from ctshowcase.config import Brand, load_yaml_text
from ctshowcase.errors import NEEDS_INPUT, OK
from ctshowcase.resolver import Resolver

OFIX = ROOT / "tests" / "fixtures" / "org"
PFIX = ROOT / "tests" / "fixtures" / "project"
N, L = "Northwind-Trading-Co", "Northwind-Labs"
REN = {"id": "ren-901", "owner": N, "repo": "ledger", "action": "rename", "new_name": "order-ledger"}
MOVE = {"id": "move-901", "owner": L, "repo": "lab-notebook", "action": "transfer", "target_owner": N, "new_name": ""}


@pytest.fixture
def labs_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][L] = dict(raw["orgs"][N], display_name="Northwind Labs", nav_name="Northwind Labs", eyebrow="LABS")
    return Brand(raw, brand.path)


def _estate(brand, *, rows=(), ids=(), registry=None, before_rename=True, private_labs=False):
    """The org fixture, optionally captured before ren-901 ran (metadata under today's slug `ledger`)."""
    reg = registry or load_yaml_text((OFIX / "registry.yaml").read_text(encoding="utf-8"))
    appr = {"rows": set(rows), "ids": set(ids), "answers": {}, "actions": [REN, MOVE], "extra": []}
    est = O.Estate(brand, Resolver(brand, reg, appr))
    O.load_metas(OFIX / "meta", est)
    if before_rename:
        m = est.metas.pop(f"{N}/order-ledger".lower())
        raw = {k: v for k, v in m.items() if not k.startswith("_") and k not in ("name", "full_name")}
        est.add_meta(dict(raw, repo="ledger"))
    if private_labs:
        est.metas[f"{L}/lab-notebook".lower()]["visibility"] = "private"
    return est


# -- registry final slugs before a rename runs (jevplay-games lost 10 of 11 public games) --------------------------
def test_pending_same_org_rename_resolves_to_todays_slug(labs_brand):
    est = _estate(labs_brand)
    assert est.alias(f"{N}/order-ledger") == (f"{N}/ledger", "ren-901")
    data, logs = O.public_slice(est, N)
    ledgers = next(s for s in data["sections"] if s["title"] == "Ledgers")["repos"]
    assert ledgers[0]["repo"] == "ledger" and ledgers[0]["url"] == f"https://github.com/{N}/ledger"
    assert [e["repo"] for e in data["featured"]] == ["support-triage-agent", "ledger"]
    assert f"repo-alias:order-ledger->{N}/ledger:ren-901" in logs
    assert not any(x.startswith("needs-input:visibility:order-ledger") for x in logs)


def test_pending_transfer_resolves_only_once_approved(labs_brand):
    assert _estate(labs_brand).alias(f"{N}/lab-notebook") is None  # not in this org until move-901 is approved
    assert _estate(labs_brand, ids=["move-901"]).alias(f"{N}/lab-notebook") == (f"{L}/lab-notebook", "move-901")


def test_labels_and_pins_use_todays_slug(labs_brand):
    est = _estate(labs_brand)
    res, _ = O.labels_plan(est, N)
    assert f"{N}/ledger" in [r["repo"] for r in res["repos"]]
    assert all(j["argv"][-1] != f"{N}/order-ledger" for j in res["jobs"] if j.get("argv"))
    reg = load_yaml_text((OFIX / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"][N]["pins_public"][2]["depends_on"] = ""  # the registry often omits the rename dependency
    res, _ = O.pins(_estate(labs_brand, registry=reg), N)
    pin = next(c for c in res["checks"] if c["target"] == "public" and c["position"] == 3)
    assert pin["repo"] == "ledger" and pin["result"] == "pass" and "pin-current-slug:ledger:ren-901" in res["logs"]
    res, _ = O.pins(_estate(labs_brand, registry=reg, ids=["ren-901"]), N)
    pin = next(c for c in res["checks"] if c["target"] == "public" and c["position"] == 3)
    assert pin["repo"] == "order-ledger" and pin["gate"] == "after ren-901 runs"


def test_private_repo_under_a_pending_rename_is_guarded_under_both_slugs(labs_brand):
    est = _estate(labs_brand)
    est.metas[f"{N}/ledger".lower()]["visibility"] = "private"
    data, _ = O.public_slice(est, N)
    priv = O._private_names(est, N, data)
    assert {f"{N}/order-ledger", f"{N}/ledger"} <= priv
    text, _ = O.profile_readme(est, N, data)
    assert "ledger" not in text.replace("order-ledger", "")


# -- §8.2 item 2 is kept by the N = 0 variant --------------------------------------------------------------------
def test_private_org_profile_keeps_badges_and_contacts(labs_brand):
    est = _estate(labs_brand, private_labs=True)
    data, _ = O.public_slice(est, L)
    text, badges = O.profile_readme(est, L, data)
    assert data["public_repo_count"] == 0 and O.PRIVATE_LINE in text and "## Featured" not in text
    assert 3 <= len(badges) <= 5 and "profile/assets/badges/website.svg" in text
    assert "[All CompleteTech organizations](https://github.com/CompleteDotTech)" in text
    assert text.index("badges/website.svg") < text.index(O.PRIVATE_LINE)
    assert "lab-notebook" not in text


# -- §8.2: an existing profile is re-templated only with an approval ------------------------------------------------
def test_profile_write_needs_retemplate_approval(labs_brand, tmp_path):
    res, code = O.profile(_estate(labs_brand), N, out_dir=tmp_path)
    assert code == NEEDS_INPUT and res["result"] == "needs-approval" and res["readme"]
    assert not (tmp_path / "profile").exists()
    res, code = O.profile(_estate(labs_brand, rows=[("profile-retemplate", N, "*", "")]), N, out_dir=tmp_path)
    assert code == OK and (tmp_path / "profile" / "README.md").is_file()
    res, code = O.profile(_estate(labs_brand), N, out_dir=tmp_path)  # our own generated README: refresh freely
    assert code == OK and "needs-approval:profile-retemplate" not in res["logs"]
    (tmp_path / "profile" / "README.md").write_text("# Hand-made profile\n", encoding="utf-8")
    other = _estate(labs_brand)
    other.metas.pop(f"{N}/.github".lower())  # no capture: the hand-made file on disk is enough to gate
    res, code = O.profile(other, N, out_dir=tmp_path)
    assert code == NEEDS_INPUT and (tmp_path / "profile" / "README.md").read_text() == "# Hand-made profile\n"


# -- project: the reference board's own option scale wins (no 7-option Priority) -----------------------------------
def _p0_capture():
    c = json.loads((PFIX / "copy-capture.json").read_text(encoding="utf-8"))
    p = c["data"]["organization"]["projectV2"]
    for f in p["fields"]["nodes"]:
        if f.get("name") == "Priority":
            f["options"] = [{"id": f"p{i}", "name": f"P{i}", "color": col, "description": ""}
                            for i, col in enumerate(("RED", "ORANGE", "BLUE"))]
            return c
    p["fields"]["nodes"].append({"__typename": "ProjectV2SingleSelectField", "id": "PVTSSF_prio", "databaseId": 1999,
                                 "name": "Priority", "dataType": "SINGLE_SELECT", "isIssueField": False,
                                 "options": [{"id": f"p{i}", "name": f"P{i}", "color": col, "description": ""}
                                             for i, col in enumerate(("RED", "ORANGE", "BLUE"))]})
    return c


def _resolver(brand):
    return Resolver(brand, {}, {"rows": set(), "ids": set(), "answers": {}, "actions": [], "extra": []})


def test_capture_wins_for_a_disjoint_option_scale(brand):
    plan = PJ.copy_plan(N, copied=_p0_capture(), resolver=_resolver(brand))
    assert "capture-wins:Priority" in plan["logs"]
    assert not [j for j in plan["jobs"] if j["id"].endswith("-options-priority")]
    assert not any(x.startswith("keep-option:P") for x in plan["logs"])
    res = PJ.lint(_p0_capture(), owner=N)
    assert not any(n.startswith("option Priority/") for n in res["notes"])
    assert any(n.startswith("options Priority: the board's own scale is kept") for n in res["notes"])
    status = [j for j in plan["jobs"] if j["id"].endswith("-options-status")]  # Status still takes the standard list
    assert status and "Backlog" in status[0]["argv"][-1]


def test_status_update_never_links_an_unknown_view(brand):
    plan = PJ.copy_plan(N, copied=json.loads((PFIX / "copy-capture.json").read_text()), resolver=_resolver(brand))
    body = [a for j in plan["jobs"] if "-status-1-" in j["id"] for a in j["argv"] if a.startswith("body=")]
    # the Shipped view is not captured yet: no update at all (planned once from the re-capture), never a dead link
    assert not body and "status-update:shipped-view-pending" in plan["logs"]


def test_empty_short_description_is_one_clear_note():
    res = PJ.lint(json.loads((PFIX / "copy-capture.json").read_text()), owner=N)
    sd = [n for n in res["notes"] if n.startswith("short description")]
    assert sd == ["short description D1: empty (set the §13.2 short description)"]


def test_files_dir_inputs_point_at_the_written_files(tmp_path):
    jobs, files = tmp_path / "jobs.jsonl", tmp_path / "bodies"
    p = run_cli("project", "copy-plan", "--target", N, "--copied", PFIX / "copy-capture.json", "--files-dir", files,
                "--jobs", jobs, "--approved", tmp_path / "none.tsv")
    assert p.returncode == 0, p.stderr
    inputs = [j["argv"][j["argv"].index("--input") + 1] for j in map(json.loads, jobs.read_text().splitlines())
              if "--input" in (j.get("argv") or [])]
    assert inputs and all(json.loads(open(i).read()) for i in inputs)
