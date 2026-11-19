"""Frozen CLI matrix: every retained alias brand row contributes family policy."""
import copy
import json

import pytest
import yaml

from ctshowcase import project
from test_owner_policy_consumers import BOARD_OWNER, proposed_view_capture
from test_owner_policy_intersections import (
    FORMER, OWNER, cli, inputs, offline as offline,
)


@pytest.mark.parametrize("held_row", ["canonical", "former", "none"], ids=["current-held", "former-held", "all-unheld"])
@pytest.mark.parametrize("pending", [False, True], ids=["identity-ready", "identity-pending"])
@pytest.mark.parametrize("login", [OWNER, FORMER.lower()], ids=["canonical-reference", "former-reference"])
@pytest.mark.parametrize("channel", ["readme", "view"])
def test_all_alias_brand_rows_contribute_family_hold(tmp_path, capsys, monkeypatch, held_row, pending, login, channel):
    monkeypatch.setattr(project, "STEWARD", ("Synthetic Steward", "steward@northwind.example"))
    prefix, registry = inputs(tmp_path, [], t3=False)
    config = tmp_path / "brand.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    for restriction in ("hold", "t3", "excluded", "watching"):
        raw["owners"][restriction] = [name for name in raw["owners"][restriction]
                                      if name.casefold() not in {OWNER.casefold(), FORMER.casefold()}]
    permitted = raw["orgs"][BOARD_OWNER]["family"]
    raw["families"]["northwind-held-policy"] = dict(raw["families"]["touchedbyanagent"], identity_pending=pending)
    raw["families"]["northwind-unheld-policy"] = dict(raw["families"][permitted], hold=False, identity_pending=pending)
    raw["orgs"][FORMER] = copy.deepcopy(raw["orgs"][OWNER])
    raw["orgs"][FORMER]["former_slugs"] = []
    for row, label in ((OWNER, "canonical"), (FORMER, "former")):
        raw["orgs"][row]["family"] = "northwind-held-policy" if held_row == label else "northwind-unheld-policy"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    protected = f"{login}/alias-policy-site"
    capture, workstreams = proposed_view_capture(tmp_path, protected)
    captured = json.loads(capture.read_text(encoding="utf-8"))
    views = captured["data"]["organization"]["projectV2"]["views"]["nodes"]
    for number, name, filter_ in ((6, "My items", "assignee:@me -status:Done"),
                                  (7, "Shipped", "status:Done updated:>=@today-30d")):
        views.append(dict(views[2], id=f"PVTV_n{number}", number=number, name=name, filter=filter_))
    capture.write_text(json.dumps(captured), encoding="utf-8")
    jobsfile = tmp_path / "jobs.jsonl"
    code, result = cli(capsys, prefix, "project", "copy-plan", "--target", BOARD_OWNER,
                       "--registry", registry, "--copied", capture, "--workstreams", workstreams,
                       "--repos", f"{protected},{BOARD_OWNER}/unrestricted-control", "--jobs", jobsfile,
                       "--files-dir", tmp_path / "bodies")
    assert code == 0, ("CLI failed", result.get("logs"))
    saved = [json.loads(line) for line in jobsfile.read_text(encoding="utf-8").splitlines()]
    for source, jobs in (("stdout", result["jobs"]), ("jobs-file", saved)):
        assert any("updateProjectV2Field" in " ".join(job.get("argv", [])) for job in jobs), \
            (source, "unrelated workstream proposals must remain available")
        if channel == "readme":
            texts = [job["argv"][job["argv"].index("--readme") + 1] for job in jobs
                     if "--readme" in job.get("argv", [])]
            assert len(texts) == 1 and "unrestricted-control" in texts[0], \
                (source, "expected one README retaining the unrestricted control")
            named = "alias-policy-site" in texts[0]
        else:
            named = any("updateProjectV2View" in " ".join(job.get("argv", []))
                        and "alias-policy-site" in " ".join(job.get("argv", [])) for job in jobs)
        assert named == (held_row == "none"), (source, channel, "an applicable alias family's HOLD was masked")
