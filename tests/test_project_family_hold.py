"""Frozen source-blind Project references to a family on HOLD (issue 213).

Synthetic owners have no owner-list restriction or T3 membership. The existing
held-family policy alone must prevent the unrelated board from naming them.
"""
import json

import pytest
import yaml

from test_owner_policy_consumers import BOARD_OWNER, proposed_view_capture
from test_owner_policy_intersections import (
    FORMER, OWNER, cli, inputs, offline as offline,
)


@pytest.mark.parametrize("held", [True, False], ids=["held-family", "unheld-family-control"])
@pytest.mark.parametrize("login", [OWNER, FORMER.lower()], ids=["canonical", "former-case-alias"])
@pytest.mark.parametrize("channel", ["readme", "view"])
def test_unrelated_project_does_not_name_a_held_family(tmp_path, capsys, held, login, channel):
    prefix, registry = inputs(tmp_path, [], t3=False)
    config = tmp_path / "brand.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    for restriction in ("hold", "t3", "excluded", "watching"):
        raw["owners"][restriction] = [name for name in raw["owners"][restriction]
                                      if name.casefold() not in {OWNER.casefold(), FORMER.casefold()}]
    raw["orgs"][OWNER]["family"] = ("touchedbyanagent" if held
                                             else raw["orgs"][BOARD_OWNER]["family"])
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    target = f"{login}/family-protected-site"
    capture, workstreams = proposed_view_capture(tmp_path, target)
    captured = json.loads(capture.read_text(encoding="utf-8"))
    views = captured["data"]["organization"]["projectV2"]["views"]["nodes"]
    # README planning requires captured numbers for every required view.
    for number, name, filter_ in ((6, "My items", "assignee:@me -status:Done"),
                                  (7, "Shipped", "status:Done updated:>=@today-30d")):
        views.append(dict(views[2], id=f"PVTV_n{number}", number=number, name=name, filter=filter_))
    capture.write_text(json.dumps(captured), encoding="utf-8")
    jobsfile = tmp_path / "jobs.jsonl"
    code, result = cli(capsys, prefix, "project", "copy-plan", "--target", BOARD_OWNER,
                       "--registry", registry, "--copied", capture, "--workstreams", workstreams,
                       "--repos", f"{target},{BOARD_OWNER}/unrestricted-control", "--jobs", jobsfile,
                       "--files-dir", tmp_path / "bodies")
    assert code == 0, result
    saved = [json.loads(line) for line in jobsfile.read_text(encoding="utf-8").splitlines()]
    for source, jobs in (("stdout", result["jobs"]), ("jobs-file", saved)):
        assert any("updateProjectV2Field" in " ".join(job.get("argv", [])) for job in jobs), \
            (source, "unrelated workstream proposals must remain available")
        if channel == "readme":
            readmes = [job["argv"][job["argv"].index("--readme") + 1] for job in jobs
                       if "--readme" in job.get("argv", [])]
            assert len(readmes) == 1 and "unrestricted-control" in readmes[0], (source, readmes)
            named = "family-protected-site" in readmes[0]
        else:
            named = any("updateProjectV2View" in " ".join(job.get("argv", []))
                        and "family-protected-site" in " ".join(job.get("argv", [])) for job in jobs)
        assert named == (not held), (source, channel, "a family HOLD must independently withhold its repository reference")
