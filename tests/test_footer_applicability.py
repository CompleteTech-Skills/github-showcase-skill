"""Footer and doctor share the same repository applicability (#44)."""
import copy
import json

import pytest
import yaml

from conftest import run_cli


@pytest.mark.parametrize("owner,repo,fork,footer,expected", [
    ("Northwind-Trading-Co", "sample", False, False, "n/a"),
    ("Northwind-Trading-Co", "sample", False, "hold", "hold"),
    ("Northwind-Trading-Co", "sample", False, True, "fail"),
    ("romgenie-following-repos", "sample", True, False, "n/a"),
    ("romgenie-following-repos", "sample", False, False, "hold"),
    ("romgenie-following-repos", ".github", False, False, "fail"),
])
def test_footer_doctor_agreement(brand, tmp_path, owner, repo, fork, footer, expected):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][owner]["footer"] = footer
    cfg = tmp_path / "brand.yaml"
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": owner, "repo": repo, "fork": fork, "visibility": "public",
                               "description": "Inspect synthetic records.", "license": "MIT"}), encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("# Synthetic test\n", encoding="utf-8")
    common = ("--config", cfg, "--meta", meta, "--repo-dir", tmp_path)
    checked = run_cli(*common, "footer", "--check", readme)
    row = run_cli(*common, "doctor", "--format", "json")
    actual = json.loads(checked.stdout)
    cells = json.loads(row.stdout)["cells"]
    assert cells["footer"].split(":")[0] == expected
    assert actual["result"].split(":")[0] == {"n/a": "exempt"}.get(expected, expected)
    if expected == "n/a":
        assert checked.returncode == 0
    elif expected == "fail":
        assert checked.returncode == 1


def test_explicit_footer_owner_must_match_metadata(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "sample"}), encoding="utf-8")
    out = run_cli("--meta", meta, "--no-repo-dir", "footer", "--org", "LibreEvolve")
    assert out.returncode == 2 and "does not match" in out.stdout + out.stderr


@pytest.mark.parametrize("grant_scope,approved,expiry,expected", [
    (["sample"], True, "2099-12-31", 1),
    (["*"], True, "2099-12-31", 1),
    (["other"], True, "2099-12-31", 2),
    (["sample"], False, "2099-12-31", 2),
    (["sample"], True, "2000-01-01", 2),
])
def test_repository_footer_rechecks_scoped_consent(brand, tmp_path, grant_scope, approved, expiry, expected):
    """The footer path must use its repo, and cannot turn an invalid grant into an exemption."""
    raw = copy.deepcopy(brand.raw)
    raw["owners"]["t3"].append("Northwind-Trading-Co")
    raw["orgs"]["Northwind-Trading-Co"]["footer"] = True
    config = tmp_path / "brand.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "sample", "visibility": "public"}),
                    encoding="utf-8")
    signoff = tmp_path / "signoffs.yaml"
    signoff.write_text(yaml.safe_dump({"signoffs": [{"id": "synthetic-footer", "owner": "Northwind-Trading-Co",
                       "repos": grant_scope, "approved": approved, "approver": "synthetic-co-owner",
                       "approved_on": "1990-01-01", "expires": expiry}]}), encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("# Synthetic fixture\n", encoding="utf-8")
    common = ("--config", config, "--meta", meta, "--repo-dir", tmp_path, "--allow-t3", "--t3-signoff-file", signoff)
    checked = run_cli(*common, "footer", "--check", readme)
    assert checked.returncode == expected, checked.stdout + checked.stderr
    if expected == 1:
        assert json.loads(checked.stdout)["result"] == "fail:missing"
        doctor = run_cli(*common, "doctor", "--format", "json")
        assert json.loads(doctor.stdout)["cells"]["footer"] == "fail"
    else:
        assert "t3-signoff" in checked.stdout + checked.stderr
