"""Source-blind issue 213 consumer cases, frozen before execution on original 7ce.

Only supported CLI inputs and synthetic estate data are used. The shared fixture
blocks transport and subprocess execution; no emitted writer job is executed.
"""
from __future__ import annotations

import json

import pytest
import yaml

from test_owner_policy_intersections import (
    FORMER, OWNER, ROOT, cli, inputs, offline as offline, record,
)

BOARD_OWNER = "Northwind-Trading-Co"
PERSONAL_ACTOR = "CompleteDotTech"  # The existing CLI supports only this fixed actor.
LAYOUTS = ("same-login", "hold-former", "t3-former", "excluded-former", "t3-only")
CONSENT = {
    "no-opt-in": ([record()], False),
    "missing": ([], True),
    "expired": ([record(expires="2001-01-01")], True),
    "revoked": ([record(), record("owner-withdrawal", approved=False, approved_on="2000-02-01")], True),
    "repository-withdrawn": ([record(), record("repo-withdrawal", repos=[f"{FORMER}/protected-site"],
                                             approved=False, approved_on="2000-02-01")], True),
    "authorized": ([record()], True),
}


def fixture_inputs(tmp_path, records, layout, *, personal=False):
    prefix, registry = inputs(tmp_path, records)
    config = tmp_path / "brand.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    for restriction in ("hold", "t3", "excluded"):
        raw["owners"][restriction] = [name for name in raw["owners"][restriction]
                                      if name.casefold() not in {OWNER.casefold(), FORMER.casefold()}]
    raw["owners"]["t3"].append(FORMER.swapcase() if layout == "t3-former" else OWNER)
    if layout in ("same-login", "t3-former"):
        raw["owners"]["hold"].append(OWNER)
    elif layout == "hold-former":
        raw["owners"]["hold"].append(FORMER.swapcase())
    elif layout == "excluded-former":
        raw["owners"]["excluded"].append(FORMER.swapcase())
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    if personal:
        reg = yaml.safe_load(registry.read_text(encoding="utf-8"))
        reg["orgs"][BOARD_OWNER] = {"tier": "T1", "profile": {"name": "Synthetic Public Control"}}
        reg["profile"] = {
            "name": "Synthetic Steward", "who_what": "Synthetic public directory fixture.",
            "email": "steward@northwind.example", "socials": [], "pins": [], "more_projects": [],
            "intro": {"headline": "Synthetic Steward", "tagline": "Synthetic public projects."},
            "org_directory": [{"group": "Synthetic organizations", "orgs": [BOARD_OWNER, FORMER.lower()]}],
        }
        registry.write_text(yaml.safe_dump(reg), encoding="utf-8")
    return prefix, registry


def proposed_view_capture(tmp_path, protected):
    capture = json.loads((ROOT / "tests/fixtures/project/copy-capture.json").read_text(encoding="utf-8"))
    board = capture["data"]["organization"]["projectV2"]
    board["url"] = f"https://github.com/orgs/{BOARD_OWNER}/projects/{board['number']}"
    for view in board["views"]["nodes"]:
        if view["name"] == "Backlog":
            # Supported workstream rename triggers a real proposed view update.
            view["filter"] = f"repo:{protected} status:Backlog,Ready workstream:Research"
    path = tmp_path / "board.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    ws = tmp_path / "workstreams.json"
    ws.write_text(json.dumps([{"name": "Pricing research", "kind": "Research",
                               "description": "Synthetic workstream."}]), encoding="utf-8")
    return path, ws


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("consent", CONSENT)
def test_t1_copy_plan_view_respects_every_referenced_owner_restriction(tmp_path, capsys, layout, consent):
    records, opt_in = CONSENT[consent]
    # A valid repository-scoped grant is enough for a view reference, even when
    # it does not grant an owner-wide read. HOLD/exclusion still apply separately.
    if consent == "authorized":
        records = [record(repos=[f"{FORMER}/protected-site"])]
    prefix, registry = fixture_inputs(tmp_path, records, layout)
    target = f"{FORMER.lower()}/protected-site"
    capture, ws = proposed_view_capture(tmp_path, target)
    jobsfile = tmp_path / "jobs.jsonl"
    code, result = cli(capsys, prefix + (["--allow-t3"] if opt_in else []), "project", "copy-plan",
                       "--target", BOARD_OWNER, "--registry", registry, "--copied", capture,
                       "--workstreams", ws, "--jobs", jobsfile, "--files-dir", tmp_path / "bodies")
    assert code == 0, result
    emitted = [json.loads(line) for line in jobsfile.read_text(encoding="utf-8").splitlines()]
    allowed = layout == "t3-only" and consent == "authorized"
    for channel, jobs in (("stdout", result["jobs"]), ("jobs-file", emitted)):
        assert any("updateProjectV2Field" in " ".join(job.get("argv", [])) for job in jobs), \
            (channel, "independent workstream planning must remain available")
        updates = [job for job in jobs if "updateProjectV2View" in " ".join(job.get("argv", []))
                   and "protected-site" in " ".join(job.get("argv", []))]
        assert bool(updates) == allowed, (channel, layout, consent, "protected view mutation escaped its owner gates")
        if allowed:
            assert all(job.get("signoff_id") == "synthetic-grant" for job in updates), updates
            assert all("approval_id" not in job for job in updates), updates


@pytest.mark.parametrize("layout", ("same-login", "hold-former", "t3-former", "excluded-former"))
@pytest.mark.parametrize("consent", CONSENT)
def test_fixed_personal_directory_requires_independent_org_consent(tmp_path, capsys, layout, consent):
    records, opt_in = CONSENT[consent]
    prefix, registry = fixture_inputs(tmp_path, records, layout, personal=True)
    output = tmp_path / "personal"
    code, result = cli(capsys, prefix + (["--allow-t3"] if opt_in else []), "org", "profile",
                       "--user", PERSONAL_ACTOR, "--registry", registry, "--out-dir", output)
    assert code == 0, result
    # A repository-only withdrawal leaves the wildcard owner grant valid for
    # this org directory link. A full withdrawal or missing opt-in never does.
    allowed = layout != "excluded-former" and consent in ("authorized", "repository-withdrawn")
    saved = json.loads((output / "data.json").read_text(encoding="utf-8"))
    for channel, data in (("stdout", result["data"]), ("data-file", saved)):
        listed = {org["login"] for group in data["org_directory"] for org in group["orgs"]}
        assert BOARD_OWNER in listed, (channel, "unrestricted synthetic control must remain in the directory")
        assert (OWNER in listed) == allowed, (channel, layout, consent, "protected org directory link escaped consent")
    text = (output / "README.md").read_text(encoding="utf-8")
    assert f"https://github.com/{BOARD_OWNER}" in text
    assert (f"https://github.com/{OWNER}" in text) == allowed, "README must use the same consent-filtered directory"


def test_personal_directory_does_not_expand_the_supported_actor(tmp_path, capsys):
    prefix, registry = fixture_inputs(tmp_path, [record()], "same-login", personal=True)
    output = tmp_path / "unsupported-personal"
    code, result = cli(capsys, prefix + ["--allow-t3"], "org", "profile", "--user", "northwind-synthetic-user",
                       "--registry", registry, "--out-dir", output)
    assert code == 2 and "supports only" in result["error"], result
    assert not output.exists(), "directory consent repair must preserve the fixed actor restriction"
