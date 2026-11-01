"""Emission-boundary T3 sign-off regressions (issue 23): an owner-wide grant or captured metadata must not reintroduce a
scope that a later withdrawal removed. copy-plan repository links are checked per repository, captured Org options are
held whether or not the org is still in registry.orgs, and an authorized retained option carries its record id.
Synthetic records only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
OWNER = "Pick-Your-AI"
FIX = ROOT / "tests" / "fixtures" / "project"


def _file(tmp_path, records):
    d = tmp_path / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    full = []
    for r in records:
        base = {"owner": OWNER, "repos": ["*"], "approved": True, "approver": "synthetic-co-owner",
                "approved_on": "2026-01-15"}
        if r.get("approved", True):
            base["expires"] = "2099-12-31"
        full.append({**base, **r})
    p = d / "t3-signoffs.yaml"
    p.write_text(json.dumps({"signoffs": full}), encoding="utf-8")
    return p


class _Strict:
    """`--allow-t3` in this context, reading the given record file."""

    def __init__(self, monkeypatch, path):
        self.monkeypatch, self.path = monkeypatch, path

    def __enter__(self):
        from ctshowcase import signoff
        from ctshowcase.config import set_t3_signed_off
        self.monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(self.path))
        self.tokens = (set_t3_signed_off(True), signoff.reset())
        return self

    def __exit__(self, *exc):
        from ctshowcase import signoff
        from ctshowcase.config import reset_t3_signed_off
        t3, run = self.tokens
        signoff.restore(run)
        reset_t3_signed_off(t3)


def _resolver(brand, registry=None, extra=()):
    from ctshowcase.resolver import Resolver
    return Resolver(brand, registry or {}, {"rows": {("create-project", "@me", "*", "")}, "ids": set(), "answers": {},
                                            "actions": [], "extra": list(extra)})


def _links(plan):
    return {j["id"]: j for j in plan["jobs"] if "-link-" in j["id"]}


WILD = [{"id": "t3s-all"}, {"id": "t3s-drop-x", "repos": ["withdrawn-x"], "approved": False, "approved_on": "2026-10-01"}]


def _copy(brand, repos):
    from ctshowcase import project as PJ
    c = json.loads((FIX / "copy-capture.json").read_text(encoding="utf-8"))
    p = c["data"]["organization"]["projectV2"]
    p["url"] = f"https://github.com/orgs/{OWNER}/projects/{p['number']}"
    return PJ.copy_plan(OWNER, role="org", copied=c, resolver=_resolver(brand), repositories=repos, allow_t3=True,
                        reviewed="2026-10-25")


def test_copy_plan_does_not_link_a_withdrawn_repository(tmp_path, monkeypatch, brand):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _copy(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/ok-y"])
    links = _links(plan)
    assert not [i for i in links if i.endswith("-link-withdrawn-x")], list(links)
    assert any(i.endswith("-link-ok-y") for i in links), list(links)
    assert any(str(x).startswith(f"t3-signoff:revoked:{OWNER}/withdrawn-x") for x in plan["logs"]), plan["logs"]
    assert any(str(x).startswith(f"link-held:{OWNER}/withdrawn-x") for x in plan["logs"]), plan["logs"]
    ok = [j for i, j in links.items() if i.endswith("-link-ok-y")][0]
    assert ok.get("signoff_id") == "t3s-all", ok


def test_copy_plan_link_carries_the_repository_regrant(tmp_path, monkeypatch, brand):
    recs = [*WILD, {"id": "t3s-regrant", "repos": ["withdrawn-x"], "approved_on": "2026-10-02"}]
    with _Strict(monkeypatch, _file(tmp_path, recs)):
        plan = _copy(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/ok-y"])
    links = _links(plan)
    wx = [j for i, j in links.items() if i.endswith("-link-withdrawn-x")]
    oy = [j for i, j in links.items() if i.endswith("-link-ok-y")]
    assert wx and wx[0].get("signoff_id") == "t3s-regrant", links
    assert oy and oy[0].get("signoff_id") == "t3s-all", links
    assert not any(str(x).startswith("t3-signoff:") for x in plan["logs"]), plan["logs"]


def _settings(plan):
    return [j for j in plan["jobs"] if j["id"].endswith("-settings")]


def test_copy_plan_settings_excludes_withdrawn_repository(tmp_path, monkeypatch, brand):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _copy(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/ok-y"])
    settings = _settings(plan)
    assert len(settings) == 1, [j["id"] for j in plan["jobs"]]
    steps = settings[0]["steps"]
    default = [s for s in steps if "Default repository" in s]
    auto = [s for s in steps if "Auto-add" in s]
    assert default and "ok-y" in default[0] and "withdrawn-x" not in default[0], default
    assert auto and "ok-y" in auto[0] and "withdrawn-x" not in auto[0], auto
    for j in plan["jobs"]:
        if j.get("kind") == "browser":
            assert not any("withdrawn-x" in s for s in j["steps"]), j["id"]
    assert settings[0].get("signoff_id") == "t3s-all", settings[0]
    assert any(str(x).startswith(f"link-held:{OWNER}/withdrawn-x") for x in plan["logs"]), plan["logs"]


def test_copy_plan_settings_held_when_all_repositories_withdrawn(tmp_path, monkeypatch, brand):
    recs = [{"id": "t3s-all"},
            {"id": "t3s-drop-x", "repos": ["withdrawn-x", "withdrawn-z"], "approved": False, "approved_on": "2026-10-01"}]
    with _Strict(monkeypatch, _file(tmp_path, recs)):
        plan = _copy(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/withdrawn-z"])
    assert not _settings(plan), [j["id"] for j in plan["jobs"]]
    assert any(str(x).startswith("settings-held:") for x in plan["logs"]), plan["logs"]
    for j in plan["jobs"]:
        if j.get("kind") == "browser":
            steps = " ".join(j["steps"])
            assert "withdrawn-x" not in steps and "withdrawn-z" not in steps, j["id"]
    assert not [j for j in plan["jobs"] if "-link-" in j["id"]], [j["id"] for j in plan["jobs"]]


def test_copy_plan_settings_keeps_regrant_ids(tmp_path, monkeypatch, brand):
    recs = [*WILD, {"id": "t3s-regrant", "repos": ["withdrawn-x"], "approved_on": "2026-10-02"}]
    with _Strict(monkeypatch, _file(tmp_path, recs)):
        plan = _copy(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/ok-y"])
    settings = _settings(plan)
    assert len(settings) == 1, [j["id"] for j in plan["jobs"]]
    default = [s for s in settings[0]["steps"] if "Default repository" in s]
    assert default and "withdrawn-x" in default[0], default
    assert settings[0].get("signoff_id") == "t3s-regrant", settings[0]
    assert not any(str(x).startswith("settings-held:") for x in plan["logs"]), plan["logs"]


def test_copy_plan_without_repositories_keeps_generic_settings(tmp_path, monkeypatch, brand):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _copy(brand, None)
    settings = _settings(plan)
    assert len(settings) == 1, [j["id"] for j in plan["jobs"]]
    assert any("the org's main repository" in s for s in settings[0]["steps"]), settings[0]["steps"]
    assert not any(str(x).startswith("settings-held:") for x in plan["logs"]), plan["logs"]


def _add_org_field(cap, option_desc):
    cap["data"]["user"]["projectV2"]["fields"]["nodes"].append({
        "__typename": "ProjectV2SingleSelectField", "id": "PVTF_org", "databaseId": 1099, "name": "Org",
        "dataType": "SINGLE_SELECT", "isIssueField": False, "options": [
            {"id": "opt-t3-synthetic", "name": "Pick Your AI", "color": "GRAY", "description": option_desc},
            {"id": "opt-t1-synthetic", "name": "CompleteTech Skills", "color": "BLUE",
             "description": "T1: CompleteTech-Skills"}]})
    return cap


def _captured(option_desc):
    return _add_org_field(json.loads((FIX / "estate-copy-capture.json").read_text(encoding="utf-8")), option_desc)


def _registry(include_owner):
    from ctshowcase.config import load_yaml_text
    reg = load_yaml_text((ROOT / "tests" / "fixtures" / "org" / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"].pop(OWNER, None)
    if include_owner:
        reg["orgs"][OWNER] = {}
    for g in reg["profile"]["org_directory"]:
        g["orgs"] = [o for o in g.get("orgs", []) if o != OWNER]
    return reg


WITHDRAWN = [{"id": "t3s-g"}, {"id": "t3s-w", "approved": False, "approved_on": "2026-10-01"}]


@pytest.mark.parametrize("records", [WITHDRAWN, []], ids=["withdrawn", "missing"])
def test_estate_replan_holds_a_captured_t3_option_whose_org_left_the_registry(tmp_path, monkeypatch, brand, records):
    from ctshowcase import project as PJ
    reg = _registry(False)
    assert OWNER not in reg["orgs"]
    with _Strict(monkeypatch, _file(tmp_path, records)):
        plan = PJ.estate_plan(_resolver(brand, reg), copied=_captured(f"T3: {OWNER}"), user_id=100, allow_t3=True)
    assert any(str(x).startswith("t3-signoff:") and x.endswith(OWNER) for x in plan["logs"]), plan["logs"]
    assert any(str(x).startswith("hold:org-options") for x in plan["logs"]), plan["logs"]
    blob = json.dumps(plan["jobs"], ensure_ascii=False)
    assert "Pick Your AI" not in blob and OWNER not in blob, [j["id"] for j in plan["jobs"]]
    assert not any("-options-org" in j["id"] for j in plan["jobs"]), "a T1 option update was emitted with the T3 option"
    assert not any("--readme" in j.get("argv", []) for j in plan["jobs"]), plan["jobs"]


def test_estate_replan_holds_a_registry_free_captured_option_under_a_former_login(tmp_path, monkeypatch, brand):
    """An approved rename leaves the captured option described `T3: Pick-Your-AI` while the org is absent from
    registry.orgs and its sign-off is withdrawn: the hold still applies (no option write, no README naming it)."""
    from ctshowcase import project as PJ
    res = _resolver(brand, _registry(False), extra=[{"action": "org-rename", "owner": OWNER, "new_name": "Pick-Your-Stack"}])
    assert res.canonical(OWNER) == "Pick-Your-Stack"
    with _Strict(monkeypatch, _file(tmp_path, WITHDRAWN)):
        held = PJ.held_captured_t3(res, PJ.normalize(_captured(f"T3: {OWNER}")), True)
        plan = PJ.estate_plan(res, copied=_captured(f"T3: {OWNER}"), user_id=100, allow_t3=True)
    assert held and held[0].startswith("t3-signoff:revoked:"), held
    assert not any("-options-org" in j["id"] for j in plan["jobs"]), plan["jobs"]
    assert not any("--readme" in j.get("argv", []) for j in plan["jobs"]), plan["jobs"]


def test_registry_free_captured_t3_option_is_kept_when_authorized(tmp_path, monkeypatch, brand):
    """Control: with a valid wildcard record the same capture is not held."""
    from ctshowcase import project as PJ
    with _Strict(monkeypatch, _file(tmp_path, [{"id": "t3s-all"}])):
        held = PJ.held_captured_t3(_resolver(brand, _registry(False)), PJ.normalize(_captured(f"T3: {OWNER}")), True)
    assert held == [], held


def test_retained_authorized_captured_t3_option_carries_its_signoff_id(tmp_path, monkeypatch, brand):
    """The org keeps a valid wildcard record and is in registry.orgs, but a nonempty profile.org_directory excludes it:
    the captured option is retained, so the Org-update and README jobs naming it must carry the sign-off id."""
    from ctshowcase import project as PJ
    from test_t3_signoff_require import _complete_estate_capture
    reg = _registry(True)
    assert reg["profile"]["org_directory"]
    full = _complete_estate_capture()
    full["data"]["user"]["projectV2"]["fields"]["nodes"][-1]["options"].append(
        {"id": "opt-t1-synthetic", "name": "CompleteTech Skills", "color": "BLUE", "description": "T1: CompleteTech-Skills"})
    with _Strict(monkeypatch, _file(tmp_path, [{"id": "t3s-all"}])):
        plan = PJ.estate_plan(_resolver(brand, reg), copied=full, user_id=100, allow_t3=True)
    named = [j for j in plan["jobs"] if "Pick Your AI" in json.dumps(j, ensure_ascii=False) or OWNER in json.dumps(j)]
    assert any("--readme" in j.get("argv", []) for j in named), [j["id"] for j in plan["jobs"]]
    assert all(j.get("signoff_id") == "t3s-all" or "t3s-all" in (j.get("signoff_ids") or []) for j in named), named


# ---------------------------------------------------------------------------------------------- workflows and README
def _workflows(plan):
    return [j for j in plan["jobs"] if j["id"].endswith("-workflows")]


def _readme_jobs(plan):
    return [j for j in plan["jobs"] if "--readme" in (j.get("argv") or [])]


def _private_board():
    """The copy capture with every required view numbered (My items and Shipped added), still private."""
    c = json.loads((FIX / "copy-capture.json").read_text(encoding="utf-8"))
    p = c["data"]["organization"]["projectV2"]
    p["url"] = f"https://github.com/orgs/{OWNER}/projects/{p['number']}"
    p["views"]["nodes"] += [
        {**p["views"]["nodes"][2], "id": "PVTV_n6", "number": 6, "name": "My items", "filter": "assignee:@me -status:Done"},
        {**p["views"]["nodes"][2], "id": "PVTV_n7", "number": 7, "name": "Shipped", "filter": "status:Done updated:>=@today-30d"}]
    assert p["public"] is False, p["public"]
    return c


def _copy_private(brand, repos):
    from ctshowcase import project as PJ
    return PJ.copy_plan(OWNER, role="org", copied=_private_board(), resolver=_resolver(brand), repositories=repos,
                        allow_t3=True, reviewed="2026-10-25")


def test_copy_plan_workflows_job_omits_auto_add_when_all_withdrawn(tmp_path, monkeypatch, brand):
    recs = [{"id": "t3s-all"},
            {"id": "t3s-drop-x", "repos": ["withdrawn-x", "withdrawn-z"], "approved": False, "approved_on": "2026-10-01"}]
    with _Strict(monkeypatch, _file(tmp_path, recs)):
        plan = _copy(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/withdrawn-z"])
    for j in _workflows(plan):
        steps = " ".join(j["steps"])
        assert "withdrawn-x" not in steps and "withdrawn-z" not in steps, (j["id"], j["steps"])
        assert not any("auto-add" in s.lower() for s in j["steps"]), (j["id"], j["steps"])
    assert not _settings(plan), [j["id"] for j in plan["jobs"]]
    assert any(str(x).startswith(("workflows-held:", "settings-held:")) for x in plan["logs"]), plan["logs"]


def test_copy_plan_workflows_job_names_authorized_repo_and_id(tmp_path, monkeypatch, brand):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _copy(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/ok-y"])
    wf = _workflows(plan)
    assert len(wf) == 1, [j["id"] for j in plan["jobs"]]
    steps = wf[0]["steps"]
    auto = [s for s in steps if "auto-add" in s.lower()]
    assert auto and "ok-y" in auto[0] and "withdrawn-x" not in auto[0], steps
    assert not any("withdrawn-x" in s for s in steps), steps
    assert wf[0].get("signoff_id") == "t3s-all", wf[0]


def test_copy_plan_readme_omits_withdrawn_link_and_stamps_grant(tmp_path, monkeypatch, brand):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _copy_private(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/kept-y"])
    rd = _readme_jobs(plan)
    assert len(rd) == 1, [j["id"] for j in plan["jobs"]]
    text = rd[0]["argv"][rd[0]["argv"].index("--readme") + 1]
    assert "withdrawn-x" not in text, text
    assert "kept-y" in text, text
    assert rd[0].get("signoff_id") == "t3s-all", rd[0]


def test_copy_plan_readme_stamps_regrant_not_cached_wildcard(tmp_path, monkeypatch, brand):
    recs = [*WILD, {"id": "t3s-regrant", "repos": ["withdrawn-x"], "approved_on": "2026-10-02"}]
    with _Strict(monkeypatch, _file(tmp_path, recs)):
        plan = _copy_private(brand, [f"{OWNER}/withdrawn-x", f"{OWNER}/kept-y"])
    rd = _readme_jobs(plan)
    assert len(rd) == 1, [j["id"] for j in plan["jobs"]]
    text = rd[0]["argv"][rd[0]["argv"].index("--readme") + 1]
    assert "withdrawn-x" in text and "kept-y" in text, text
    ids = set(rd[0].get("signoff_ids") or [])
    assert {"t3s-regrant", "t3s-all"} <= ids, rd[0]


def test_copy_plan_without_repositories_readme_and_workflows_unchanged(tmp_path, monkeypatch, brand):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _copy(brand, None)
    wf = _workflows(plan)
    assert len(wf) == 1, [j["id"] for j in plan["jobs"]]
    assert any("auto-add" in s.lower() for s in wf[0]["steps"]), wf[0]["steps"]
    assert "signoff_id" not in wf[0], wf[0]
    assert not any(str(x).startswith("settings-held:") for x in plan["logs"]), plan["logs"]


# repository spelling canonicalization (t23-adjudication-repo-canonicalization-50f): in-library copy-plan, every valid
# spelling of a withdrawn repository is omitted from the README, workflows and link jobs; kept-y is retained.
@pytest.mark.parametrize("withdrawn", [f"{OWNER}/withdrawn-x/", f"{OWNER}/withdrawn-x.git", f" {OWNER}/withdrawn-x",
                                       f" {OWNER} /withdrawn-x", "withdrawn-x"])
def test_copy_plan_spelling_of_withdrawn_repository_is_omitted_everywhere(tmp_path, monkeypatch, brand, withdrawn):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _copy_private(brand, [f"{OWNER}/kept-y", withdrawn])
    rd = _readme_jobs(plan)
    assert len(rd) == 1, [j["id"] for j in plan["jobs"]]
    assert "kept-y" in rd[0]["argv"][rd[0]["argv"].index("--readme") + 1]
    assert "withdrawn-x" not in json.dumps(plan["jobs"]), [j["id"] for j in plan["jobs"]]


def test_copy_plan_malformed_repository_entry_is_dropped_with_a_log(tmp_path, monkeypatch, brand):
    with _Strict(monkeypatch, _file(tmp_path, WILD)):
        plan = _copy_private(brand, [f"{OWNER}/kept-y", "a b"])
    assert any(str(x).startswith("repos-malformed:") for x in plan["logs"]), plan["logs"]
    assert "a b" not in json.dumps(plan["jobs"])
