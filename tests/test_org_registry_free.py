"""Registry-free org checks use only synthetic local captures."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT
from ctshowcase import org as O
from ctshowcase.resolver import Resolver

ORG = "Northwind-Trading-Co"


def cli(tmp_path, *args):
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(tmp_path), PYTHONIOENCODING="utf-8")
    # An empty SHOWCASE_ESTATE_ROOT does not disable fallback discovery. Restrict the child to
    # the explicit synthetic root so tests cannot inspect a developer's sibling estate bundle.
    bootstrap = """import runpy, sys
from pathlib import Path
script = Path(sys.argv.pop(1))
sys.path.insert(0, str(script.parent))
import ctshowcase
ctshowcase.estate_candidates = lambda: []
from ctshowcase import resolver
resolver.estate_candidates = lambda: []
runpy.run_path(str(script), run_name="__main__")
"""
    proc = subprocess.run([sys.executable, "-c", bootstrap, str(ROOT / "scripts/showcase.py"), "org", *args],
                          capture_output=True, encoding="utf-8", env=env)
    return proc, json.loads(proc.stdout)


def checkout(tmp_path):
    repo = tmp_path / ".github"
    for name in O.T1_FILES + O.FORMS + ("profile/assets/banner.jpg",):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic content", encoding="utf-8")
    return repo


def snapshot(brand):
    row = brand.org(ORG)
    return {"org": {"login": ORG, "name": row["display_name"], "description": row["description"],
                    "is_verified": True, "avatar_url": "https://example.test/identicon.png"},
            "profile_readme": "Synthetic public profile", "repos": [
                {"name": ".github", "visibility": "public", "files": ["profile/assets/banner.jpg"],
                 "files_complete": True}]}


def test_health_cli_without_registry_checks_checkout(tmp_path):
    proc, result = cli(tmp_path, "health", ORG, "--dot-github", str(checkout(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert result["result"] == "pass" and result["source"] == "checkout"
    assert result["cells"]["SECURITY.md"] == "pass"
    assert not result.get("jobs")
    (tmp_path / ".github" / "SECURITY.md").unlink()
    proc, result = cli(tmp_path, "health", ORG, "--dot-github", str(tmp_path / ".github"))
    assert proc.returncode == 1
    assert result["cells"]["SECURITY.md"] == "missing"


def test_health_without_evidence_does_not_invent_missing_repository(tmp_path):
    proc, result = cli(tmp_path, "health", ORG)
    assert proc.returncode == 0, proc.stderr
    assert result["result"] == "unknown"
    assert "needs-input:dot-github-files" in result["logs"]
    assert not result["add"]


def test_doctor_cli_without_registry_reports_partial_coverage(tmp_path, brand):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot(brand)), encoding="utf-8")
    proc, result = cli(tmp_path, "doctor", ORG, "--snapshot", str(path))
    assert proc.returncode == 0, proc.stderr
    assert result["cells"]["O1"] == "fail"  # captured identicon still checked
    assert result["cells"]["O9"] == "pass"  # captured tree must survive snapshot ingestion
    assert result["cells"]["O11"] == "pass"
    for cell in ("O2", "O3", "O6"):
        assert result["cells"][cell] == "needs-input:registry"
    assert "needs-input:registry" in result["logs"]
    assert result["done"] == "no"


def test_registry_free_doctor_reports_definite_identity_and_private_link_failures(brand):
    snap = snapshot(brand)
    snap["org"]["name"] = "Wrong brand identity"
    snap["repos"].append({"name": "synthetic-private", "visibility": "private"})
    snap["profile_readme"] = f"See https://github.com/{ORG}/synthetic-private"
    estate = O.Estate(brand, Resolver(brand))
    result = O.doctor(estate, ORG, snap)
    assert result["cells"]["O2"] == "fail"
    assert result["cells"]["O3"] == "fail"
    assert any("O2 name" in line for line in result["notes"])
    assert any("leak" in line for line in result["notes"])


def test_health_preserves_brand_alias_resolution_without_registry(tmp_path):
    proc, result = cli(tmp_path, "health", "CompleTetech-Security", "--dot-github", str(checkout(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert result["owner"] == "CompleteTech-Security"


def test_other_actions_still_require_registry_and_explicit_bad_path_is_not_ignored(tmp_path):
    proc, result = cli(tmp_path, "profile", ORG)
    assert proc.returncode == 4 and "needs-input:registry" in result["logs"]
    proc, result = cli(tmp_path, "health", ORG, "--registry", str(tmp_path / "missing.yaml"),
                       "--dot-github", str(checkout(tmp_path)))
    assert proc.returncode == 4 and "needs-input:registry" in result["logs"]


def test_registry_free_checks_still_refuse_excluded_and_unsigned_t3(tmp_path):
    for org in ("BunsDev", "Pick-Your-AI"):
        proc, result = cli(tmp_path, "health", org, "--dot-github", str(checkout(tmp_path)))
        assert proc.returncode == 2
        assert "cells" not in result


@pytest.mark.parametrize("name", [None, ""])
def test_captured_cleared_identity_differs_from_missing_identity(brand, name):
    snap = snapshot(brand)
    snap["org"]["name"] = name
    result = O.doctor(O.Estate(brand, Resolver(brand)), ORG, snap)
    assert result["cells"]["O2"] == "fail"
    assert any("O2 name" in note for note in result["notes"])
    del snap["org"]["name"]
    result = O.doctor(O.Estate(brand, Resolver(brand)), ORG, snap)
    assert result["cells"]["O2"] == "needs-input:registry"


def test_snapshot_file_evidence_supplements_metadata_without_tree(brand):
    snap = snapshot(brand)
    snap["repos"][0]["files"] = []
    estate = O.Estate(brand, Resolver(brand))
    estate.add_meta({"owner": ORG, "repo": ".github", "visibility": "public", "description": "Preserve metadata"})
    result = O.doctor(estate, ORG, snap)
    assert result["cells"]["O4"] == "fail"
    assert result["cells"]["O9"] == "fail"
    assert any("O4 missing: SECURITY.md" == note for note in result["notes"])
    assert estate.meta(f"{ORG}/.github")["description"] == "Preserve metadata"


def test_incomplete_snapshot_does_not_replace_complete_metadata_tree(brand):
    snap = snapshot(brand)
    snap["repos"][0].update(files=[], files_complete=False)
    estate = O.Estate(brand, Resolver(brand))
    estate.add_meta({"owner": ORG, "repo": ".github", "visibility": "public",
                     "files": list(O.T1_FILES + O.FORMS) + ["profile/assets/banner.jpg"], "files_complete": True})
    result = O.doctor(estate, ORG, snap)
    assert result["cells"]["O4"] == result["cells"]["O9"] == "pass"


@pytest.mark.parametrize(("org", "reason"), [("CompleteTech-LLC", "email-blank"), ("TouchedByAnAgent", "hold")])
def test_unverified_snapshot_has_available_reason_without_registry(brand, org, reason):
    snap = {"org": {"is_verified": False, "blog": "https://www.complete.tech", "email": None}}
    result = O.doctor(O.Estate(brand, Resolver(brand)), org, snap)
    assert result["cells"]["O11"] == "warn"
    assert f"O11 not verified: {reason}" in result["notes"]


@pytest.mark.parametrize("action", ["health", "doctor"])
@pytest.mark.parametrize("discovered", [False, True])
def test_supplied_registry_missing_org_is_not_a_registry_free_run(tmp_path, action, discovered):
    registry = ROOT / "tests/fixtures/org/registry.yaml"
    if discovered:
        destination = tmp_path / "registry/estate.yaml"
        destination.parent.mkdir()
        shutil.copyfile(registry, destination)
        args = []
    else:
        args = ["--registry", str(registry)]
    proc, result = cli(tmp_path, action, "CompleteTech-Skills", *args)
    assert proc.returncode == 4
    assert "needs-input:org" in result["logs"]
    assert "needs-input:registry" not in result["logs"]


def test_positive_partial_snapshot_tree_is_not_suppressed_by_partial_metadata(brand):
    snap = snapshot(brand)
    snap["repos"][0]["files_complete"] = False
    estate = O.Estate(brand, Resolver(brand))
    estate.add_meta({"owner": ORG, "repo": ".github", "visibility": "public", "files": [],
                     "files_complete": False})
    result = O.doctor(estate, ORG, snap)
    assert result["cells"]["O9"] == "pass"
    assert result["cells"]["O4"] == "unknown"
    assert estate.meta(f"{ORG}/.github")["files_complete"] is False


@pytest.mark.parametrize("captured", [{}, {"blog": "https://www.complete.tech"}])
def test_unverified_missing_reason_inputs_are_unknown(brand, captured):
    snap = {"org": {"is_verified": False, **captured}}
    result = O.doctor(O.Estate(brand, Resolver(brand)), "CompleteTech-LLC", snap)
    assert result["cells"]["O11"] == "unknown"
    assert not any("blog-other-domain" in note or "email-blank" in note for note in result["notes"])


def test_cli_helper_ignores_ambient_sibling_registry(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    skill = bundle / "skill"
    shutil.copytree(ROOT / "scripts", skill / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "references", skill / "references")
    registry = bundle / "registry/estate.yaml"
    registry.parent.mkdir()
    registry.write_text("version: 1\norgs:\n  Northwind-Labs: {}\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", skill)
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    proc, result = cli(isolated, "health", ORG, "--dot-github", str(checkout(isolated)))
    assert proc.returncode == 0, result
    assert result["result"] == "pass"
