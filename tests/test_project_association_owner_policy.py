"""Frozen source-blind Org-association CLI cases for issue 213.

Owner-list consent applies independently of row tier. Synthetic captures and
contact details only; the imported fixture blocks all transport/process calls.
"""
import json

import pytest
import yaml

from ctshowcase import project
from test_owner_policy_intersections import (
    FORMER, OWNER, cli, inputs, offline as offline, record,
)
from test_t3_emission_scope import _estate_capture

CONTROL = "Northwind-Trading-Co"
LABEL = "Northwind Policy Org"
CASES = {
    "no-opt-in": ([record()], False),
    "missing": ([], True),
    "expired": ([record(expires="2001-01-01")], True),
    "revoked": ([record(), record("synthetic-withdrawal", approved=False, approved_on="2000-02-01")], True),
    "repository-only": ([record(repos=["only-one-repository"])], True),
    "authorized": ([record()], True),
}


def run_plan(tmp_path, monkeypatch, capsys, *, command, login, restriction, case):
    monkeypatch.setattr(project, "STEWARD", ("Synthetic Steward", "steward@northwind.example"))
    records, opt_in = CASES[case]
    prefix, registry = inputs(tmp_path, records, t3=False)
    config = tmp_path / "brand.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    for key in ("t3", "hold", "excluded", "watching"):
        raw["owners"][key] = [name for name in raw["owners"][key]
                               if name.casefold() not in {OWNER.casefold(), FORMER.casefold()}]
    if restriction in ("owner-current", "owner-former"):
        raw["owners"]["t3"].append(OWNER if restriction == "owner-current" else FORMER.swapcase())
    tier = "T3" if restriction == "row-tier" else "T1"
    raw["orgs"][OWNER].update(tier=tier, display_name=LABEL)
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    reg = yaml.safe_load(registry.read_text(encoding="utf-8"))
    reg["orgs"][OWNER]["tier"] = tier
    reg["orgs"][CONTROL] = {"tier": "T1", "profile": {"name": "Synthetic Control"}}
    reg["profile"] = {"name": "Synthetic Steward", "org_directory": [
        {"group": "Synthetic organizations", "orgs": [CONTROL, login]}]}
    registry.write_text(yaml.safe_dump(reg), encoding="utf-8")
    captured = _estate_capture(LABEL, f"{tier}: {login}", recolor=True)
    capture = tmp_path / "captured.json"
    capture.write_text(json.dumps(captured), encoding="utf-8")
    before = capture.read_bytes()
    jobsfile = tmp_path / "jobs.jsonl"
    extra = ["--target", "@me", "--role", "estate"] if command == "copy-plan" else []
    code, result = cli(capsys, prefix + (["--allow-t3"] if opt_in else []), "project", command, *extra,
                       "--registry", registry, "--copied", capture, "--user-id", "100",
                       "--jobs", jobsfile, "--files-dir", tmp_path / "bodies", "--reviewed", "2026-01-01")
    assert code == 0, ("CLI failed", code, result.get("logs"))
    capture_unchanged = capture.read_bytes() == before
    assert capture_unchanged, "planning must preserve every captured Org option and id"
    saved = [json.loads(line) for line in jobsfile.read_text(encoding="utf-8").splitlines()]
    return result, saved


def assert_association(result, saved, *, allowed, signed, command):
    for source, jobs in (("stdout", result["jobs"]), ("jobs-file", saved)):
        assert any(job["id"].endswith("-workflows") for job in jobs), \
            (source, "unrelated valid planning must remain available")
        org_jobs = [job for job in jobs if job["id"].endswith(("-options-org", "-field-org"))]
        readmes = [job for job in jobs if "--readme" in job.get("argv", [])]
        org_count, readme_count = len(org_jobs), len(readmes)
        if not allowed:
            assert org_count == 0, (source, "Org field mutation escaped independent owner-list consent")
            assert readme_count == 0, (source, "README naming the captured association escaped consent")
            assert any(log.startswith("t3-signoff:") for log in result["logs"]), "missing consent diagnostic"
            continue
        assert readme_count > 0, (source, "an authorized Org association must retain README planning")
        assert all(LABEL in job["argv"][job["argv"].index("--readme") + 1] for job in readmes), \
            (source, "authorized association was omitted from README")
        if command == "estate-plan":
            assert org_count > 0, (source, "the captured wrong-colour control must trigger an Org options update")
        for job in org_jobs:
            payload = " ".join(job.get("argv", []))
            assert "optorg1" in payload and "optnw" in payload, "authorized updates must preserve captured option ids"
        for job in org_jobs + readmes:
            ids = set(job.get("signoff_ids", [])) | ({job["signoff_id"]} if job.get("signoff_id") else set())
            assert ids == ({"synthetic-grant"} if signed else set()), \
                (source, "association provenance must match the granting record")
            assert "approval_id" not in job, "consent provenance must not supply writer approval"


@pytest.mark.parametrize("command", ["estate-plan", "copy-plan"])
@pytest.mark.parametrize("login", [OWNER, FORMER.lower()], ids=["current-reference", "former-reference"])
@pytest.mark.parametrize("restriction", ["owner-current", "owner-former"])
@pytest.mark.parametrize("case", CASES)
def test_owner_list_t3_association_is_independent_of_t1_rows(tmp_path, monkeypatch, capsys,
                                                           command, login, restriction, case):
    result, saved = run_plan(tmp_path, monkeypatch, capsys, command=command, login=login,
                             restriction=restriction, case=case)
    assert_association(result, saved, allowed=case == "authorized", signed=case == "authorized", command=command)


@pytest.mark.parametrize("command", ["estate-plan", "copy-plan"])
@pytest.mark.parametrize("case", ["no-opt-in", "missing", "authorized"])
def test_existing_row_tier_t3_association_remains_enforced(tmp_path, monkeypatch, capsys, command, case):
    result, saved = run_plan(tmp_path, monkeypatch, capsys, command=command, login=FORMER.lower(),
                             restriction="row-tier", case=case)
    assert_association(result, saved, allowed=case == "authorized", signed=case == "authorized", command=command)


@pytest.mark.parametrize("command", ["estate-plan", "copy-plan"])
def test_ordinary_non_t3_association_needs_no_opt_in_or_record(tmp_path, monkeypatch, capsys, command):
    result, saved = run_plan(tmp_path, monkeypatch, capsys, command=command, login=FORMER.lower(),
                             restriction="ordinary", case="no-opt-in")
    assert_association(result, saved, allowed=True, signed=False, command=command)


def direct_policy_plan(tmp_path, monkeypatch, *, policy, login, proposed, case="authorized"):
    """Public direct planner contract supports explicitly proposed extra fields."""
    import copy

    from ctshowcase.config import Brand, reset_t3_signed_off, set_t3_signed_off
    from ctshowcase.resolver import Resolver
    from test_t3_emission_scope import _Strict

    monkeypatch.setattr(project, "STEWARD", ("Synthetic Steward", "steward@northwind.example"))
    records, opt_in = CASES[case]
    prefix, registry = inputs(tmp_path, records, t3=False)
    config = tmp_path / "brand.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    for key in ("hold", "t3", "excluded", "watching"):
        raw["owners"][key] = [name for name in raw["owners"][key]
                               if name.casefold() not in {OWNER.casefold(), FORMER.casefold()}]
    tier = "T1" if policy in ("alias-tier", "ordinary") else "T3"
    raw["orgs"][OWNER].update(tier=tier, display_name=LABEL)
    if policy not in ("alias-tier", "ordinary"):
        raw["owners"]["t3"].append(OWNER)
    if policy in ("hold", "excluded"):
        raw["owners"][policy].append(FORMER.swapcase())
    if policy == "family-hold":
        raw["orgs"][OWNER]["family"] = "touchedbyanagent"
    if policy == "alias-tier":
        raw["orgs"][FORMER] = copy.deepcopy(raw["orgs"][OWNER])
        raw["orgs"][FORMER].update(tier="T3", former_slugs=[], display_name="Northwind Former Tier")
    reg = yaml.safe_load(registry.read_text(encoding="utf-8"))
    reg["orgs"][OWNER]["tier"] = tier
    reg["orgs"][CONTROL] = {"tier": "T1"}
    if policy == "placeholder":
        reg["placeholders"] = [{"login": OWNER, "successor": CONTROL}]
    resolver = Resolver(Brand(raw, config), reg)
    capture = _estate_capture(LABEL, f"{tier}: {login}", recolor=True)
    if proposed:
        fields = capture["data"]["user"]["projectV2"]["fields"]["nodes"]
        fields[:] = [field for field in fields if field["name"] != "Org"]
    before = copy.deepcopy(capture)
    field = dict(project.ESTATE_FIELDS[0], options=[
        ("Northwind Trading Co.", "BLUE", f"T1: {CONTROL}"), (LABEL, "GRAY", f"{tier}: {login}")])
    with _Strict(monkeypatch, tmp_path / "signoffs.yaml"):
        token = set_t3_signed_off(opt_in)
        try:
            result = project.copy_plan("@me", role="estate", copied=capture, resolver=resolver,
                                       extra_fields=[field], allow_t3=opt_in, user_id=100, reviewed="2026-01-01")
        finally:
            reset_t3_signed_off(token)
    unchanged = capture == before
    assert unchanged, "direct planning must preserve the captured Org options and ids"
    return result


def assert_direct_policy(result, *, allowed, signed, proposed):
    jobs = result["jobs"]
    assert any(job["id"].endswith("-workflows") for job in jobs), "unrelated planning must remain available"
    org_jobs = [job for job in jobs if job["id"].endswith(("-options-org", "-field-org"))]
    readmes = [job for job in jobs if "--readme" in job.get("argv", [])]
    counts = len(org_jobs), len(readmes)
    if not allowed:
        assert counts == (0, 0), "independent owner policy must withhold Org association mutation and README"
        named_elsewhere = any(LABEL in json.dumps(job) for job in jobs)
        assert not named_elsewhere, "another emitted job must not carry the refused association"
        return
    assert counts[0] > 0 and counts[1] > 0, "authorized captured/proposed associations must produce both jobs"
    org_names_association = all(LABEL in " ".join(job.get("argv", [])) for job in org_jobs)
    assert org_names_association, "the authorized Org field must retain its association"
    for job in org_jobs + readmes:
        ids = set(job.get("signoff_ids", [])) | ({job["signoff_id"]} if job.get("signoff_id") else set())
        names_association = LABEL in " ".join(job.get("argv", []))
        assert ids == ({"synthetic-grant"} if signed and names_association else set()), \
            "association provenance must match consent and the association actually named"
        assert "approval_id" not in job, "T3 consent does not supply writer approval"
    if not proposed:
        ids_kept = all("optorg1" in " ".join(job.get("argv", [])) and "optnw" in " ".join(job.get("argv", []))
                       for job in org_jobs)
        assert ids_kept, "authorized updates must retain every captured option id"


@pytest.mark.parametrize("proposed", [False, True], ids=["captured", "direct-proposed"])
@pytest.mark.parametrize("login", [OWNER, FORMER.lower()], ids=["current-reference", "former-reference"])
@pytest.mark.parametrize("policy", ["hold", "family-hold", "excluded", "placeholder", "signed", "ordinary"])
def test_current_t3_grant_never_releases_independent_association_restrictions(tmp_path, monkeypatch,
                                                                           proposed, login, policy):
    result = direct_policy_plan(tmp_path, monkeypatch, policy=policy, login=login, proposed=proposed)
    assert_direct_policy(result, allowed=policy in ("signed", "ordinary"), signed=policy == "signed", proposed=proposed)


@pytest.mark.parametrize("proposed", [False, True], ids=["captured", "direct-proposed"])
@pytest.mark.parametrize("login", [OWNER, FORMER.lower()], ids=["current-reference", "former-reference"])
@pytest.mark.parametrize("case", CASES)
def test_retained_alias_t3_tier_is_authoritative_for_associations(tmp_path, monkeypatch, proposed, login, case):
    result = direct_policy_plan(tmp_path, monkeypatch, policy="alias-tier", login=login, proposed=proposed, case=case)
    assert_direct_policy(result, allowed=case == "authorized", signed=case == "authorized", proposed=proposed)
