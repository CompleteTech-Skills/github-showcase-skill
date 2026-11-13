"""Omitting a public planner's resolver never disables committed T3 consent gates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctshowcase import project, signoff
from ctshowcase.errors import NeedsInput, Refused
from ctshowcase.resolver import Resolver

OWNER = "Pick-Your-AI"
FIX = Path(__file__).parent / "fixtures" / "project" / "copy-capture.json"


def grant(**overrides):
    return {"id": "synthetic-owner-grant", "owner": OWNER, "repos": ["*"], "approved": True,
            "approver": "synthetic-co-owner", "approved_on": "2026-01-01", **overrides}


@pytest.fixture
def record_file(tmp_path):
    path = tmp_path / "synthetic-signoffs.json"
    token = signoff.set_file(path)
    try:
        yield path
    finally:
        signoff.reset_file(token)


def write_records(path, *records):
    path.write_text(json.dumps({"signoffs": list(records)}), encoding="utf-8")


def capture(owner=OWNER):
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    board = raw["data"]["organization"]["projectV2"]
    board["url"] = f"https://github.com/orgs/{owner}/projects/{board['number']}"
    return raw


@pytest.mark.parametrize("allow_t3", [False, True])
def test_default_resolver_refuses_missing_record_before_returning_jobs(record_file, allow_t3):
    assert not record_file.exists()
    with pytest.raises(Refused) as exc:
        project.copy_plan(OWNER, display_name="Pick Your AI", allow_t3=allow_t3)
    assert exc.value.log == ("t3-signoff:no-file" if allow_t3 else "t3-signoff")
    assert not record_file.exists() and not signoff._granted()


@pytest.mark.parametrize("record,code", [
    (grant(id="synthetic-withdrawal", approved=False), "revoked"),
    (grant(repos=["one-repository"]), "scope"),
    (grant(expires="2020-01-01", approved_on="2019-01-01"), "expired"),
])
def test_default_resolver_rejects_withdrawn_scoped_or_expired_owner_grant(record_file, record, code):
    # A later withdrawal vetoes a prior broad grant; scoped and expired grants
    # independently fail the owner-wide operation rather than becoming an opt-out.
    records = [grant(approved_on="2025-01-01"), record] if not record["approved"] else [record]
    write_records(record_file, *records)
    with pytest.raises(Refused) as exc:
        project.copy_plan(OWNER, display_name="Pick Your AI", allow_t3=True)
    assert exc.value.log == f"t3-signoff:{code}"
    assert not signoff._granted()


def test_direct_default_resolver_registers_and_returns_verified_owner_provenance(record_file):
    write_records(record_file, grant())
    plan = project.copy_plan(OWNER.lower(), allow_t3=True, approval_id="synthetic-writer-approval")
    assert plan["owner"] == OWNER and plan["stage"] == 1
    assert plan["jobs"] and all(job["signoff_id"] == "synthetic-owner-grant" for job in plan["jobs"])
    assert plan["jobs"][0]["approval_id"] == "synthetic-writer-approval"


def test_default_resolver_still_requires_explicit_opt_in(record_file):
    write_records(record_file, grant())
    with pytest.raises(Refused) as exc:
        project.copy_plan(OWNER, allow_t3=False)
    assert exc.value.log == "t3-signoff"
    assert not signoff._granted()


def test_default_resolver_keeps_repository_withdrawal_at_stage_two(record_file):
    write_records(record_file, grant(approved_on="2025-01-01"),
                  grant(id="synthetic-withdrawal", repos=["withdrawn-x"], approved=False))
    plan = project.copy_plan(OWNER, copied=capture(), repositories=[f"{OWNER}/withdrawn-x", f"{OWNER}/kept-y"],
                             allow_t3=True, reviewed="2026-10-25")
    links = [job for job in plan["jobs"] if "-link-" in job["id"]]
    assert len(links) == 1 and links[0]["argv"][-1] == f"{OWNER}/kept-y"
    assert links[0]["signoff_id"] == "synthetic-owner-grant"
    assert any(log.startswith(f"link-held:{OWNER}/withdrawn-x") for log in plan["logs"])
    assert not any("withdrawn-x" in " ".join(job.get("argv") or []) for job in plan["jobs"])


def test_default_resolver_checks_t3_repositories_in_another_owners_new_view(record_file):
    write_records(record_file, grant(approved_on="2025-01-01"),
                  grant(id="synthetic-withdrawal", repos=["withdrawn-x"], approved=False))
    owner = "Northwind-Trading-Co"
    view = {"name": "Synthetic consent view", "layout": "table", "filter": f"repo:{OWNER}/withdrawn-x",
            "group_by": [], "sort_by": [], "ui": []}
    plan = project.copy_plan(owner, copied=capture(owner), views=[view], allow_t3=True, reviewed="2026-10-25")
    assert any(log.startswith("view-filter-held:") for log in plan["logs"])
    assert not any("withdrawn-x" in " ".join(job.get("argv") or []) for job in plan["jobs"])


@pytest.mark.parametrize("owner", ["MetatronAngelAgent", "TouchedByAnAgent"])
def test_default_resolver_preserves_excluded_and_hold_refusals(record_file, owner):
    with pytest.raises(Refused):
        project.copy_plan(owner, display_name="Synthetic target", allow_t3=True)


def test_default_resolver_reads_only_committed_identity_and_preserves_unknown_needs_input(record_file, monkeypatch):
    import ctshowcase.resolver as resolver_module

    def unexpected(*args, **kwargs):
        raise AssertionError("default library planning must not discover private registry or approvals")

    monkeypatch.setattr(resolver_module, "load_registry", unexpected)
    monkeypatch.setattr(resolver_module, "load_approvals", unexpected)
    plan = project.copy_plan("Northwind-Trading-Co")
    assert plan["owner"] == "Northwind-Trading-Co"
    assert "needs-approval:create-project:Northwind-Trading-Co" in plan["logs"]
    with pytest.raises(NeedsInput) as exc:
        project.copy_plan("Synthetic-Unknown-Org")
    assert exc.value.log == "needs-input:display-name"
    explicit = project.copy_plan("Synthetic-Unknown-Org", display_name="Synthetic Owner")
    assert explicit["title"] == "Synthetic Owner — Workstreams"


def test_explicit_custom_resolver_still_controls_identity_and_scope(record_file, brand):
    from copy import deepcopy
    from ctshowcase.config import Brand

    raw = deepcopy(brand.raw)
    raw["orgs"][OWNER]["former_slugs"] = ["Synthetic-Former-Co-Owner"]
    resolver = Resolver(Brand(raw, brand.path))
    write_records(record_file, grant(owner="Synthetic-Former-Co-Owner"))
    plan = project.copy_plan("Synthetic-Former-Co-Owner", resolver=resolver, allow_t3=True)
    assert plan["owner"] == OWNER
    assert plan["jobs"][0]["signoff_id"] == "synthetic-owner-grant"


def test_read_only_capture_remains_available_without_signoff(record_file):
    result = project.capture_query(OWNER, 1)
    assert result and not record_file.exists() and not signoff._granted()
