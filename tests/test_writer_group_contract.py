"""Plans preserve the writer's per-repository reconciliation boundaries."""
import json

import pytest

from conftest import meta_dict, run_cli
from ctshowcase.org import job


def test_shared_label_factory_supplies_group():
    plan = job("northwind-label", "3.2", "labels", ["gh", "label", "create", "type:bug"],
               repo="Northwind-Trading-Co/support-triage-agent")
    assert plan["group"] == "labels:Northwind-Trading-Co/support-triage-agent"


def test_explicit_group_preserved():
    plan = job("northwind-label", "3.2", "labels", [], repo="Northwind-Trading-Co/legacy",
               group="polish-archived:Northwind-Trading-Co/legacy")
    assert plan["group"] == "polish-archived:Northwind-Trading-Co/legacy"


@pytest.mark.parametrize("command", ["labels", "adopt"])
def test_label_cli_job_groups(tmp_path, command):
    full = "Northwind-Trading-Co/support-triage-agent"
    meta = tmp_path / "northwind.json"
    meta.write_text(json.dumps(meta_dict(has_issues=True, files=["README.md"], files_complete=True,
                                        labels=[{"name": "dependencies", "color": "0366d6", "description": "Updates"}])
                              ), encoding="utf-8")
    args = ("labels", "--plan") if command == "labels" else ("adopt", full)
    result = run_cli("--meta", meta, "--no-repo-dir", *args)
    assert result.returncode in (0, 1), result.stderr
    label_jobs = [j for j in json.loads(result.stdout)["jobs"] if j["kind"] == "labels"]
    assert label_jobs
    assert {j["group"] for j in label_jobs} == {f"labels:{full}"}


def test_archived_adopt_waits_for_approved_unarchive(tmp_path):
    meta = tmp_path / "northwind.json"
    data = meta_dict(archived=True, has_issues=True)
    meta.write_text(json.dumps(data), encoding="utf-8")
    args = ("--meta", meta, "--no-repo-dir", "adopt", "Northwind-Trading-Co/support-triage-agent")
    result = run_cli(*args)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["jobs"] == [] and plan["records"] == []
    assert any("unarchive" in p["why"] for p in plan["pending"])
    data["archived"] = False  # recapture inside the approved window
    meta.write_text(json.dumps(data), encoding="utf-8")
    active = json.loads(run_cli(*args).stdout)
    assert {j["kind"] for j in active["jobs"]} >= {"repo-settings", "security"}
