"""Registry-free org checks use only synthetic local captures."""
import json
import os
import subprocess
import sys

from conftest import ROOT
from ctshowcase import org as O
from ctshowcase.resolver import Resolver

ORG = "Northwind-Trading-Co"


def cli(tmp_path, *args):
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(tmp_path), PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "org", *args],
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
