"""The direct copy planner enforces and returns Org-field association provenance."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from ctshowcase import project
from test_t3_emission_scope import (
    OWNER, WITHDRAWN, _Strict, _estate_capture, _file, _ids, _org_options_jobs,
    _readme_jobs, _registry, _renamed_resolver, _resolver,
)


def _t1_field():
    return dict(project.ESTATE_FIELDS[0], options=[
        ("Northwind Trading Co.", "BLUE", "T1: Northwind-Trading-Co")])


def _direct(brand, capture, fields, **kwargs):
    return project.copy_plan("@me", role="estate", copied=capture,
                             resolver=kwargs.pop("resolver", _resolver(brand, _registry(False))),
                             user_id=100, reviewed="2026-10-25", extra_fields=fields, **kwargs)


def test_direct_retained_org_mutation_and_readme_carry_the_record(tmp_path, monkeypatch, brand):
    cap = _estate_capture("Former Synthetic Name", f"T3: {OWNER}", recolor=True)
    before = deepcopy(cap)
    with _Strict(monkeypatch, _file(tmp_path, [{"id": "synthetic-association"}])):
        plan = _direct(brand, cap, [_t1_field()], allow_t3=True, resolver=_renamed_resolver(brand))
    jobs = _org_options_jobs(plan)
    assert jobs and all("synthetic-association" in _ids(job) for job in jobs)
    assert _readme_jobs(plan) and all("synthetic-association" in _ids(job) for job in _readme_jobs(plan))
    mutation = next(value for value in jobs[0]["argv"] if value.startswith("query="))
    assert 'id: "optnw"' in mutation and 'id: "optorg1"' in mutation
    assert cap == before
    independent = [job for job in plan["jobs"] if job["id"].endswith("-workflows")]
    assert independent and all(not _ids(job) for job in independent)


@pytest.mark.parametrize("records,allow", [
    ([{"id": "synthetic-record"}], False),
    ([], True),
    (WITHDRAWN, True),
    ([{"id": "synthetic-scope", "repos": ["one-repository"]}], True),
])
def test_direct_retained_org_is_held_without_current_owner_consent(tmp_path, monkeypatch, brand, records, allow):
    cap = _estate_capture("Former Synthetic Name", f"T3: {OWNER}", recolor=True)
    before = deepcopy(cap)
    with _Strict(monkeypatch, _file(tmp_path, records)):
        plan = _direct(brand, cap, [_t1_field()], allow_t3=allow)
    assert not _org_options_jobs(plan) and not _readme_jobs(plan)
    assert any(log.startswith("hold:org-options") for log in plan["logs"])
    assert any(log.startswith("t3-signoff:") for log in plan["logs"])
    assert "Former Synthetic Name" not in json.dumps(plan["jobs"])
    assert cap == before


@pytest.mark.parametrize("records,allow,permitted", [
    ([{"id": "synthetic-added-org"}], True, True),
    ([{"id": "synthetic-record"}], False, False),
    ([], True, False),
    (WITHDRAWN, True, False),
])
def test_direct_new_org_field_checks_and_stamps_its_association(tmp_path, monkeypatch, brand, records, allow, permitted):
    cap = _estate_capture("Pick Your AI", f"T3: {OWNER}")
    fields = cap["data"]["user"]["projectV2"]["fields"]["nodes"]
    fields[:] = [field for field in fields if field["name"] != "Org"]
    proposed = dict(project.ESTATE_FIELDS[0], options=[("Pick Your AI", "GRAY", f"T3: {OWNER}")])
    with _Strict(monkeypatch, _file(tmp_path, records)):
        plan = _direct(brand, cap, [proposed], allow_t3=allow)
    jobs = [job for job in plan["jobs"] if job["id"].endswith("-field-org")]
    if permitted:
        assert jobs and all("synthetic-added-org" in _ids(job) for job in jobs)
    else:
        assert not jobs and not _readme_jobs(plan)
        assert "Pick Your AI" not in json.dumps(plan["jobs"])


def test_custom_readme_not_naming_retained_org_is_not_stamped(tmp_path, monkeypatch, brand):
    cap = _estate_capture("Former Synthetic Name", f"T3: {OWNER}", recolor=True)
    with _Strict(monkeypatch, _file(tmp_path, [{"id": "synthetic-association"}])):
        plan = _direct(brand, cap, [_t1_field()], allow_t3=True, readme_text="Synthetic board notes only.")
    assert _org_options_jobs(plan) and all("synthetic-association" in _ids(j) for j in _org_options_jobs(plan))
    assert _readme_jobs(plan) and all(not _ids(job) for job in _readme_jobs(plan))


def test_custom_readme_naming_captured_label_keeps_association_record(tmp_path, monkeypatch, brand):
    cap = _estate_capture("Former Synthetic Name", f"T3: {OWNER}", recolor=True)
    with _Strict(monkeypatch, _file(tmp_path, [{"id": "synthetic-association"}])):
        plan = _direct(brand, cap, [_t1_field()], allow_t3=True,
                       readme_text="This board includes Former Synthetic Name.")
    assert _readme_jobs(plan) and all("synthetic-association" in _ids(job) for job in _readme_jobs(plan))


def test_another_option_name_does_not_create_unrelated_readme_provenance(tmp_path, monkeypatch, brand):
    cap = _estate_capture("Pick Your AI", f"T3: {OWNER}")
    cap["data"]["user"]["projectV2"]["fields"]["nodes"][-1]["options"].append(
        {"id": "synthetic-other-option", "name": "Pick Your AI Tools", "color": "BLUE",
         "description": "T1: Northwind-Trading-Co"})
    with _Strict(monkeypatch, _file(tmp_path, [{"id": "synthetic-association"}])):
        plan = _direct(brand, cap, [_t1_field()], allow_t3=True, readme_text="This board includes Pick Your AI Tools.")
    assert _readme_jobs(plan) and all(not _ids(job) for job in _readme_jobs(plan))


def test_option_provenance_merges_with_a_distinct_board_owner_grant(tmp_path, monkeypatch, brand):
    board_owner = "Jevelopers-neatHack-2026"
    cap = project.normalize(_estate_capture("Pick Your AI", f"T3: {OWNER}", recolor=True))
    cap["url"] = f"https://github.com/orgs/{board_owner}/projects/{cap['number']}"
    records = [{"id": "synthetic-association"}, {"id": "synthetic-board", "owner": board_owner}]
    with _Strict(monkeypatch, _file(tmp_path, records)):
        plan = project.copy_plan(board_owner, role="estate", copied=cap, resolver=_resolver(brand),
                                 extra_fields=[_t1_field()], allow_t3=True, reviewed="2026-10-25")
    assert _org_options_jobs(plan)
    assert all(_ids(job) == {"synthetic-association", "synthetic-board"} for job in _org_options_jobs(plan))


def test_no_opt_in_does_not_read_a_record_file(tmp_path, monkeypatch, brand):
    from ctshowcase import signoff

    def unexpected(*args, **kwargs):
        raise AssertionError("an omitted opt-in must not inspect sign-off records")

    monkeypatch.setattr(signoff, "evaluate", unexpected)
    cap = _estate_capture("Pick Your AI", f"T3: {OWNER}", recolor=True)
    plan = _direct(brand, cap, [_t1_field()], allow_t3=False)
    assert not _org_options_jobs(plan) and not _readme_jobs(plan)
    assert f"t3-signoff:missing-opt-in:{OWNER}" in plan["logs"]


def test_non_estate_copy_with_org_field_uses_same_association_gate(tmp_path, monkeypatch, brand):
    cap = project.normalize(_estate_capture("Pick Your AI", f"T3: {OWNER}", recolor=True))
    cap["url"] = "https://github.com/orgs/Northwind-Trading-Co/projects/7"
    cap["number"] = 7
    with _Strict(monkeypatch, _file(tmp_path, [])):
        plan = project.copy_plan("Northwind-Trading-Co", role="org", copied=cap,
                                 resolver=_resolver(brand), extra_fields=[_t1_field()], allow_t3=True,
                                 reviewed="2026-10-25")
    assert not _org_options_jobs(plan) and not _readme_jobs(plan)
    assert any(log.startswith("t3-signoff:") for log in plan["logs"])


@pytest.mark.parametrize("new_field", [False, True], ids=["captured", "proposed"])
def test_declared_unresolved_t3_identity_holds_only_association_outputs(tmp_path, monkeypatch, brand, new_field):
    name, description = "Synthetic Retired Org", "T3: unresolved-synthetic-login"
    cap = _estate_capture(name, description, recolor=True)
    fields = [_t1_field()]
    if new_field:
        nodes = cap["data"]["user"]["projectV2"]["fields"]["nodes"]
        nodes[:] = [field for field in nodes if field["name"] != "Org"]
        fields = [dict(project.ESTATE_FIELDS[0], options=[(name, "GRAY", description)])]
    before = deepcopy(cap)
    with _Strict(monkeypatch, _file(tmp_path, [{"id": "synthetic-unrelated-grant"}])):
        plan = _direct(brand, cap, fields, allow_t3=True)
    assert "needs-input:org-identity:unresolved-synthetic-login" in plan["logs"]
    assert not _org_options_jobs(plan) and not _readme_jobs(plan)
    assert not any(job["id"].endswith("-field-org") for job in plan["jobs"])
    assert plan["jobs"] and any(job["id"].endswith("-workflows") for job in plan["jobs"])
    assert name not in json.dumps(plan["jobs"]) and description not in json.dumps(plan["jobs"])
    assert cap == before


def test_unknown_description_still_resolves_a_known_option_name(tmp_path, monkeypatch, brand):
    cap = _estate_capture("Pick Your AI", "T3: obsolete-synthetic-login", recolor=True)
    with _Strict(monkeypatch, _file(tmp_path, [{"id": "synthetic-resolved-grant"}])):
        plan = _direct(brand, cap, [_t1_field()], allow_t3=True)
    assert not any(log.startswith("needs-input:org-identity:") for log in plan["logs"])
    assert _org_options_jobs(plan) and all("synthetic-resolved-grant" in _ids(j) for j in _org_options_jobs(plan))


@pytest.mark.parametrize("description", ["T2: unresolved-synthetic-login", "Legacy synthetic association"])
def test_unrelated_freeform_description_is_not_invented_as_t3(tmp_path, monkeypatch, brand, description):
    cap = _estate_capture("Synthetic Other Org", description, recolor=True)
    with _Strict(monkeypatch, _file(tmp_path, [])):
        plan = _direct(brand, cap, [_t1_field()], allow_t3=False)
    assert not any(log.startswith(("needs-input:org-identity:", "t3-signoff:")) for log in plan["logs"])
    assert _org_options_jobs(plan) and _readme_jobs(plan)
    assert all(not _ids(job) for job in _org_options_jobs(plan) + _readme_jobs(plan))
