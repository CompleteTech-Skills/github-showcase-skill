"""Round-2 review: a label rename is emitted only when §6.4 rule 0 could be checked. Without a checkout, the captured file
list must prove that no file rule 0 reads exists; otherwise the rename is held (`needs-input:label-references`) and
the plan names the files a checkout must be read for. Synthetic Northwind data only."""
import json

import pytest

from conftest import ROOT, meta_dict, run_cli
from ctshowcase import labels
from ctshowcase import org as O
from ctshowcase.config import load_yaml_text
from ctshowcase.resolver import Resolver

LIVE = [{"name": "bug", "color": "d73a4a", "description": "Something isn't working"},
        {"name": "enhancement", "color": "a2eeef", "description": "New feature or request"}]
PLAIN = ["README.md", "LICENSE", "src/triage/agent.py", ".github/CODEOWNERS", ".github/pull_request_template.md"]
HOLD = "needs-input:label-references"
GH = "Northwind-Trading-Co/.github"
CLEAN = labels.defaults_source(GH, meta={"files": ["README.md", "profile/README.md"], "files_complete": True})


def _renames(ops):
    return {o["name"]: o["new_name"] for o in ops if o["op"] == "rename"}


def _held(ops):
    return {o["name"]: o for o in ops if o.get("log") == HOLD}


def test_no_checkout_and_no_file_list_holds_every_rename():
    ops, logs = labels.plan(LIVE)
    assert _renames(ops) == {}, "a bare rename left without any reference check"
    held = _held(ops)
    assert set(held) == {"bug", "enhancement"} and all(o["op"] == "skip" for o in held.values())
    assert held["bug"]["new_name"] == "type:bug" and held["bug"]["check_files"]  # names what a checkout must show
    assert HOLD in logs
    # the creates and recolours that are not renames still plan
    assert any(o["op"] == "create" and o["name"] == "type:docs" for o in ops)


def test_complete_file_list_without_reference_files_emits_the_rename():
    ops, logs = labels.plan(LIVE, files=PLAIN, complete=True, defaults=CLEAN)
    assert _renames(ops) == {"bug": "type:bug", "enhancement": "type:feature"}
    assert HOLD not in logs


@pytest.mark.parametrize("path", [".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/docs.md",
                                  ".github/dependabot.yml", ".github/workflows/triage.yml", ".github/release.yml",
                                  ".github/labeler.yml", "renovate.json", ".github/renovate.json"])
def test_file_list_naming_a_reference_file_holds_the_rename(path):
    ops, logs = labels.plan(LIVE, files=PLAIN + [path], complete=True, defaults=CLEAN)
    assert _renames(ops) == {}
    assert _held(ops)["bug"]["check_files"] == [path] and HOLD in logs


def test_fixture_file_map_cannot_prove_absence():
    # the fixtures' {path: value} map lists only some paths, so an unlisted form may still exist
    ops, logs = labels.plan(LIVE, files={"README.md": True, ".github/ISSUE_TEMPLATE/bug_report.yml": False})
    assert _renames(ops) == {} and HOLD in logs


def test_checkout_keeps_the_scan(tmp_path):
    (tmp_path / "src").mkdir()
    ops, logs = labels.plan(LIVE, tmp_path, files=[".github/workflows/x.yml"], complete=True,
                            defaults=CLEAN)  # a checkout wins over the capture
    assert _renames(ops) == {"bug": "type:bug", "enhancement": "type:feature"} and HOLD not in logs


def test_labels_cli_without_repo_dir_holds_the_rename(tmp_path):
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(labels=LIVE)))
    jobs = tmp_path / "jobs.jsonl"
    p = run_cli("--format", "json", "--meta", m, "--no-repo-dir", "labels", "--plan", "--jobs", jobs)
    out = json.loads(p.stdout)
    argvs = [json.loads(x)["argv"] for x in jobs.read_text().splitlines()] if jobs.is_file() else []
    assert not any(a[:3] == ["gh", "label", "edit"] and "--name" in a for a in argvs + out["argv"]), argvs
    assert HOLD in out["logs"] and out["result"] != "pass" and p.returncode != 0
    assert {x["label"] for x in out["needs_checkout"]} == {"bug", "enhancement"}
    # with a complete tree that has no reference file, the renames leave as jobs
    m.write_text(json.dumps(meta_dict(labels=LIVE, files=PLAIN, files_complete=True)))
    gh = tmp_path / "dot-github.json"
    gh.write_text(json.dumps(meta_dict(repo=".github", files=["README.md", "profile/README.md"], files_complete=True)))
    jobs.unlink(missing_ok=True)
    out = json.loads(run_cli("--format", "json", "--meta", m, "--no-repo-dir", "labels", "--plan", "--jobs", jobs,
                             "--org-defaults", gh).stdout)
    assert any(a[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for a in out["argv"])
    assert HOLD not in out["logs"] and "needs_checkout" not in out


def test_adopt_without_repo_dir_holds_the_rename(tmp_path):
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(labels=LIVE, files=PLAIN + [".github/ISSUE_TEMPLATE/bug_report.yml"])))
    out = json.loads(run_cli("--meta", m, "--no-repo-dir", "adopt", "Northwind-Trading-Co/support-triage-agent").stdout)
    argvs = [j.get("argv") or [] for j in out["jobs"]]
    assert not any(a[:3] == ["gh", "label", "edit"] and "--name" in a for a in argvs), argvs
    assert HOLD in out["logs"]
    assert any("--repo-dir" in (p.get("next") or "") and "labels" in p.get("why", "") for p in out["pending"])


def test_org_labels_holds_renames_it_cannot_check(brand):
    from test_org import approvals
    fix = ROOT / "tests" / "fixtures" / "org"
    est = O.Estate(brand, Resolver(brand, load_yaml_text((fix / "registry.yaml").read_text(encoding="utf-8")), approvals()))
    O.load_metas(fix / "meta", est)
    full = "Northwind-Trading-Co/support-triage-agent"
    res, _ = O.labels_plan(est, "Northwind-Trading-Co")
    argvs = [j.get("argv") or [] for j in res["jobs"] if j.get("repo") == full]
    assert not any(a[:3] == ["gh", "label", "edit"] and "--name" in a for a in argvs), argvs
    by = {r["repo"]: r for r in res["repos"]}
    assert by[full]["needs_checkout"][0]["label"] == "bug" and HOLD in res["logs"]
    # a captured tree with no reference file lets the rename through
    est.meta(full).update(files=list(PLAIN), files_complete=True)
    est.meta(GH).update(files=["README.md", "profile/README.md"], files_complete=True)
    res, _ = O.labels_plan(est, "Northwind-Trading-Co")
    first = next(j for j in res["jobs"] if j.get("repo") == full)
    assert first["argv"][:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"]


def test_labels_cli_hold_only_is_needs_input_not_pass(tmp_path):
    rows = [{k: lb[k] for k in ("name", "color", "description")} for lb in labels.standard_labels() if lb["name"] != "type:bug"]
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(labels=rows + [{"name": "bug", "color": "d73a4a", "description": ""}])))
    p = run_cli("--format", "json", "--meta", m, "--no-repo-dir", "labels", "--plan")
    out = json.loads(p.stdout)
    assert out["argv"] == [] and out["result"] == "needs-input" and p.returncode == 4
    assert out["needs_checkout"][0]["check_files"] == list(labels.REFERENCE_PATTERNS) + [
        f"{GH}:{p}" for p in labels.DEFAULT_PATTERNS]  # no capture: R's own files and the owner's default forms
