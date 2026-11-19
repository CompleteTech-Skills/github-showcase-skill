"""Frozen source-blind Org identity boundary cases; synthetic plans only."""
import copy

import pytest
import yaml

from ctshowcase import project
from ctshowcase.config import Brand
from ctshowcase.resolver import Resolver
from test_owner_policy_intersections import (
    FORMER, OWNER, inputs, offline as offline, record,
)
from test_t3_emission_scope import _Strict, _estate_capture

CONTROL = "Northwind-Trading-Co"
OTHER = "Northwind-Other-Identity"


def identity_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(project, "STEWARD", ("Synthetic Steward", "steward@northwind.example"))
    _, registry = inputs(tmp_path, [], t3=False)
    config = tmp_path / "brand.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    for key in ("hold", "t3", "excluded", "watching"):
        raw["owners"][key] = [name for name in raw["owners"][key]
                               if name.casefold() not in {OWNER.casefold(), FORMER.casefold()}]
    reg = yaml.safe_load(registry.read_text(encoding="utf-8"))
    reg["orgs"][CONTROL] = {"tier": "T1"}
    return raw, reg, config


def identity_plan(tmp_path, *, raw, reg, config, label, description, proposed, records, extra=()):
    from pytest import MonkeyPatch

    approvals = {"rows": set(), "ids": set(), "answers": {}, "actions": [], "extra": list(extra)}
    resolver = Resolver(Brand(raw, config), reg, approvals)
    captured = _estate_capture(label, description, recolor=True)
    if proposed:
        nodes = captured["data"]["user"]["projectV2"]["fields"]["nodes"]
        nodes[:] = [field for field in nodes if field["name"] != "Org"]
    before = copy.deepcopy(captured)
    fields = [dict(project.ESTATE_FIELDS[0], options=[
        ("Northwind Trading Co.", "BLUE", f"T1: {CONTROL}"), (label, "GRAY", description)])]
    signoffs = tmp_path / "identity-signoffs.yaml"
    signoffs.write_text(yaml.safe_dump({"signoffs": records}), encoding="utf-8")
    with MonkeyPatch.context() as context, _Strict(context, signoffs):
        result = project.copy_plan("@me", role="estate", copied=captured, resolver=resolver,
                                   extra_fields=fields, allow_t3=True, user_id=100, reviewed="2026-01-01")
    unchanged = captured == before
    assert unchanged, "identity resolution must preserve all captured option ids"
    return result


def assert_identity_plan(result, *, label, allowed, proposed, resolution_needed=False):
    jobs = result["jobs"]
    assert any(job["id"].endswith("-workflows") for job in jobs), "unrelated valid work must remain available"
    orgs = [job for job in jobs if job["id"].endswith(("-options-org", "-field-org"))]
    readmes = [job for job in jobs if "--readme" in job.get("argv", [])]
    counts = len(orgs), len(readmes)
    if not allowed:
        assert counts == (0, 0), "unresolved or refused identity must withhold association mutation and README"
        if resolution_needed:
            assert any("org-identity" in log for log in result["logs"]), "ambiguous association needs identity resolution"
        return
    assert counts[0] > 0 and counts[1] > 0, "an unambiguous authorized association must remain available"
    named_orgs = all(label in " ".join(job.get("argv", [])) for job in orgs)
    assert named_orgs, "authorized Org field must retain the intended association"
    for job in orgs + readmes:
        ids = set(job.get("signoff_ids", [])) | ({job["signoff_id"]} if job.get("signoff_id") else set())
        names_label = label in " ".join(job.get("argv", []))
        assert ids == ({"synthetic-identity-grant"} if names_label else set()), "provenance must identify the intended owner"
        assert "approval_id" not in job, "identity consent must not supply writer approval"
    if not proposed:
        kept = all("optorg1" in " ".join(job.get("argv", [])) and "optnw" in " ".join(job.get("argv", []))
                   for job in orgs)
        assert kept, "authorized updates must retain every captured option id"


@pytest.mark.parametrize("proposed", [False, True], ids=["captured", "direct-proposed"])
@pytest.mark.parametrize("login", [OWNER, FORMER.lower()], ids=["current-reference", "former-reference"])
@pytest.mark.parametrize("source", ["registry-placeholder", "approved-merge"])
def test_placeholder_identity_without_org_rows_is_still_withheld(tmp_path, monkeypatch, proposed, login, source):
    raw, reg, config = identity_inputs(tmp_path, monkeypatch)
    raw["orgs"].pop(OWNER)
    reg["orgs"].pop(OWNER)
    extra = [{"action": "org-rename", "owner": FORMER, "new_name": OWNER}]
    if source == "registry-placeholder":
        reg["placeholders"] = [{"login": OWNER, "successor": CONTROL}]
    else:
        extra.append({"action": "org-merge", "owner": OWNER, "target_owner": CONTROL})
    label = "Synthetic Retired Organization"
    result = identity_plan(tmp_path, raw=raw, reg=reg, config=config, label=label, description=f"T1: {login}",
                           proposed=proposed, records=[record("synthetic-identity-grant")], extra=extra)
    assert_identity_plan(result, label=label, allowed=False, proposed=proposed)


@pytest.mark.parametrize("proposed", [False, True], ids=["captured", "direct-proposed"])
@pytest.mark.parametrize("login", [OWNER, FORMER.lower()], ids=["current-reference", "former-reference"])
@pytest.mark.parametrize("exact_other", [False, True], ids=["held-exact-login", "authorized-exact-login"])
def test_description_exact_login_precedes_another_org_display_name(tmp_path, monkeypatch, proposed, login, exact_other):
    raw, reg, config = identity_inputs(tmp_path, monkeypatch)
    raw["owners"]["hold"].append(FORMER.swapcase())
    raw["orgs"][OTHER] = copy.deepcopy(raw["orgs"][OWNER])
    raw["orgs"][OTHER].update(former_slugs=[], display_name=login, tier="T3")
    raw["owners"]["t3"].append(OTHER)
    reg["orgs"][OTHER] = {"tier": "T3"}
    target = OTHER if exact_other else login
    result = identity_plan(tmp_path, raw=raw, reg=reg, config=config, label=login,
                           description=f"T3: {target}", proposed=proposed,
                           records=[record("synthetic-identity-grant", owner=OTHER)])
    assert_identity_plan(result, label=login, allowed=exact_other, proposed=proposed)


@pytest.mark.parametrize("proposed", [False, True], ids=["captured", "direct-proposed"])
@pytest.mark.parametrize("ambiguous", [True, False], ids=["ambiguous-display", "unique-display-control"])
def test_display_only_association_requires_unambiguous_identity(tmp_path, monkeypatch, proposed, ambiguous):
    raw, reg, config = identity_inputs(tmp_path, monkeypatch)
    label = "Northwind Shared Display"
    raw["orgs"][OWNER].update(display_name=label, tier="T3")
    raw["owners"]["t3"].append(OWNER)
    records = [record("synthetic-identity-grant")]
    if ambiguous:
        raw["orgs"][OTHER] = copy.deepcopy(raw["orgs"][OWNER])
        raw["orgs"][OTHER]["former_slugs"] = []
        raw["owners"]["t3"].append(OTHER)
        reg["orgs"][OTHER] = {"tier": "T3"}
        records.append(record("synthetic-other-grant", owner=OTHER))
    result = identity_plan(tmp_path, raw=raw, reg=reg, config=config, label=label, description="",
                           proposed=proposed, records=records)
    assert_identity_plan(result, label=label, allowed=not ambiguous, proposed=proposed, resolution_needed=ambiguous)


@pytest.mark.parametrize("proposed", [False, True], ids=["captured", "direct-proposed"])
@pytest.mark.parametrize("exact_description", [False, True], ids=["display-only", "exact-owner-description"])
@pytest.mark.parametrize("label", ["Northwind Open Work", "Northwind-Open-Work"], ids=["spaced-label", "login-shaped-label"])
@pytest.mark.parametrize("default_hold", [False, True], ids=["default-unheld", "default-held"])
def test_known_explicitly_unheld_family_overrides_default_for_org_identity(tmp_path, monkeypatch, proposed,
                                                                        exact_description, label, default_hold):
    raw, reg, config = identity_inputs(tmp_path, monkeypatch)
    inherited = raw["orgs"][CONTROL]["family"]
    raw["defaults"]["hold"] = default_hold
    raw["families"][inherited].pop("hold", None)
    raw["families"]["northwind-explicitly-open"] = dict(raw["families"][inherited], hold=False)
    # Both options in this capture name known ordinary owners with an explicit
    # release; an unrelated held option must not invalidate the positive control.
    raw["orgs"][OWNER].update(display_name=label, family="northwind-explicitly-open", tier="T1")
    raw["orgs"][CONTROL]["family"] = "northwind-explicitly-open"
    description = f"T1: {OWNER}" if exact_description else ""
    result = identity_plan(tmp_path, raw=raw, reg=reg, config=config, label=label, description=description,
                           proposed=proposed, records=[])
    jobs = result["jobs"]
    assert any(job["id"].endswith("-workflows") for job in jobs), "unrelated valid work must remain available"
    orgs = [job for job in jobs if job["id"].endswith(("-options-org", "-field-org"))]
    readmes = [job for job in jobs if "--readme" in job.get("argv", [])]
    counts = len(orgs), len(readmes)
    assert counts[0] > 0 and counts[1] > 0, "a known explicitly unheld owner must remain authorized"
    names_owner = all(label in " ".join(job.get("argv", [])) for job in orgs)
    assert names_owner, "authorized Org options must retain the intended known owner"
    for job in orgs + readmes:
        ids = set(job.get("signoff_ids", [])) | ({job["signoff_id"]} if job.get("signoff_id") else set())
        assert not ids, "ordinary T1 associations need no T3 grant provenance"
    if not proposed:
        ids_kept = all("optorg1" in " ".join(job.get("argv", [])) and "optnw" in " ".join(job.get("argv", []))
                       for job in orgs)
        assert ids_kept, "authorized updates must preserve the captured option ids"
