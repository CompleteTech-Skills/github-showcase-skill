"""Direct change-record consumers receive live target provenance before serialization."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ctshowcase import intake, records, signoff
from ctshowcase.config import load_brand, reset_t3_signed_off, set_t3_signed_off
from ctshowcase.context import RepoContext
from ctshowcase.errors import Refused

OWNER = "Pick-Your-AI"
REPO = "northwind-synthetic"


def grant(id="target-grant", *, repos=None, approved=True):
    return {"id": id, "owner": OWNER, "repos": repos or [REPO], "approved": approved,
            "approver": "synthetic-co-owner", "approved_on": "2026-01-01"}


@pytest.fixture
def consent(tmp_path):
    path = tmp_path / "synthetic-consent.json"
    path.write_text(json.dumps({"signoffs": [grant()]}), encoding="utf-8")
    run = signoff.reset()
    file = signoff.set_file(path)
    flag = set_t3_signed_off(True)
    try:
        yield path
    finally:
        reset_t3_signed_off(flag)
        signoff.reset_file(file)
        signoff.restore(run)


def make_record(repo=REPO, owner=OWNER):
    return records.record(owner, repo, "settings", "settings", {"has_issues": False},
                          {"has_issues": True}, "synthetic rule")


@pytest.mark.parametrize("entry", ["adopt", "new"])
def test_direct_intake_returns_stamped_records_without_serializing(consent, entry):
    brand = load_brand()
    if entry == "new":
        result = intake.new_plan(brand, f"{OWNER}/{REPO}", "library", description="Synthetic Python library",
                                 approval_id="synthetic-writer-approval")
    else:
        ctx = RepoContext(brand, {"owner": OWNER, "repo": REPO, "visibility": "private",
                                 "description": "Synthetic Python library", "topics": [],
                                 "files": ["pyproject.toml"], "files_complete": True,
                                 "releases": 0, "packages": 0, "deployments": 0})
        result = intake.adopt(ctx, fresh=True, approval_id="synthetic-writer-approval")
    assert {r["kind"] for r in result["records"]} == {"settings", "topics"}
    assert all(r["signoff_id"] == "target-grant" and "approval_id" not in r for r in result["records"])
    assert result["jobs"] and all(j["signoff_id"] == "target-grant" for j in result["jobs"])
    assert all(j["approval_id"] == "synthetic-writer-approval" for j in result["jobs"] if j["kind"] != "browser")


def test_constructing_record_does_not_authorize_or_register_grant(consent):
    assert signoff.granted(OWNER, REPO)  # a valid file alone is not a prior gate
    rec = make_record()
    assert "signoff_id" not in rec and not signoff._granted()
    flag = set_t3_signed_off(False)
    try:
        with pytest.raises(Refused):
            intake.new_plan(load_brand(), f"{OWNER}/{REPO}", "library")
    finally:
        reset_t3_signed_off(flag)


def test_record_scope_and_unchanged_payload(consent):
    signoff.require(OWNER, REPO)
    assert make_record()["signoff_id"] == "target-grant"
    assert "signoff_id" not in make_record("unapproved-repository")
    assert "signoff_id" not in make_record(owner="CompleteTech-Data")
    rec = make_record()
    assert rec["before_sha256"] == hashlib.sha256(json.dumps({"has_issues": False}, sort_keys=True).encode()).hexdigest()
    assert rec["after"] == {"has_issues": True} and rec["rule"] == "synthetic rule"


@pytest.mark.parametrize("replacement", [[], [grant(approved=False)], [grant(id="replacement-grant")],
                                          [dict(grant(), expires="2000-01-01")]])
def test_cached_grant_is_revalidated_before_record_return(consent, replacement):
    signoff.require(OWNER, REPO)
    consent.write_text(json.dumps({"signoffs": replacement}), encoding="utf-8")
    assert "signoff_id" not in make_record()


def test_repository_grants_and_association_ids_keep_their_identity(consent):
    consent.write_text(json.dumps({"signoffs": [grant(id="first", repos=[REPO]),
                                               grant(id="second", repos=["another-synthetic"])]}), encoding="utf-8")
    signoff.require(OWNER, REPO)
    signoff.require(OWNER, "another-synthetic")
    first, second = make_record(), make_record("another-synthetic")
    assert first["signoff_id"] == "first" and second["signoff_id"] == "second"
    first["approval_id"] = "existing-writer-approval"
    signoff.stamp_associations(first, ["association-grant", "first"], OWNER, REPO)
    signoff.stamp([first])  # serialization must preserve all existing, scoped provenance
    assert first["signoff_id"] == "first" and first["signoff_ids"] == ["first", "association-grant"]
    assert first["approval_id"] == "existing-writer-approval"


def test_content_writer_returns_keep_live_scope_and_existing_approval(consent):
    from ctshowcase.content import actions_report, sidebar_plan, writer_job
    meta = {"owner": OWNER, "repo": REPO, "visibility": "private", "fork": True}
    assert "signoff_id" not in writer_job("synthetic", 3, "test", f"{OWNER}/{REPO}", [], "synthetic")
    signoff.require(OWNER, REPO)
    sidebar = sidebar_plan(meta, {"releases": 0, "packages": 0, "deployments": 0})["job"]
    assert sidebar["signoff_id"] == "target-grant" and "approval_id" not in sidebar
    report = actions_report(meta, workflow_files={".github/workflows/cla.yml":
                            "on: pull_request\njobs:\n  cla:\n    steps:\n      - uses: contributor-assistant/github-action@v2\n"})
    assert report["proposals"] and report["proposals"][0]["signoff_id"] == "target-grant"
    own = writer_job("synthetic", 3, "test", f"{OWNER}/{REPO}", [], "synthetic", "existing-approval")
    assert own["signoff_id"] == "target-grant" and own["approval_id"] == "existing-approval"
    assert "signoff_id" not in writer_job("other", 3, "test", f"{OWNER}/unapproved", [], "synthetic")
    consent.write_text(json.dumps({"signoffs": [grant(approved=False)]}), encoding="utf-8")
    assert "signoff_id" not in writer_job("withdrawn", 3, "test", f"{OWNER}/{REPO}", [], "synthetic")
