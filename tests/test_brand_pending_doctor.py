"""Read-only coverage remains available while a family awaits real design inputs."""
import json

import pytest

from conftest import run_cli


OWNER = "Jevelopers-neatHack-2026"


def _signoff(tmp_path, state):
    records = [{"id": "synthetic-brand-doctor", "owner": OWNER, "repos": ["sample"],
                "approved": True, "approver": "synthetic-co-owner", "approved_on": "2026-01-15"}]
    if state == "revoked":
        records.append({"id": "synthetic-brand-doctor-revoked", "owner": OWNER, "repos": ["sample"],
                        "approved": False, "approver": "synthetic-co-owner", "approved_on": "2026-01-16"})
    path = tmp_path / "synthetic-signoffs.json"
    path.write_text(json.dumps({"signoffs": records}), encoding="utf-8")
    return path


@pytest.mark.parametrize("state", ["unsigned", "valid", "revoked"])
@pytest.mark.parametrize("checkout", [False, True])
def test_pending_identity_doctor_reports_coverage_without_generating(tmp_path, state, checkout):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": OWNER, "repo": "sample", "visibility": "public",
                               "description": "Inspect synthetic records.", "files": ["main.py"]}), encoding="utf-8")
    target = tmp_path / "checkout"
    target.mkdir()
    readme = target / "README.md"
    readme.write_text("# Authored title\n\nKeep this exact text.\n", encoding="utf-8")
    original = readme.read_bytes()
    common = ["--meta", meta, "--repo-dir", target] if checkout else ["--meta", meta, "--no-repo-dir"]
    if state != "unsigned":
        common += ["--allow-t3", "--t3-signoff-file", _signoff(tmp_path, state)]
    result = run_cli(*common, "doctor", "--format", "json")
    assert result.returncode in (0, 1), result.stdout + result.stderr
    row = json.loads(result.stdout)
    assert row["repo"] == f"{OWNER}/sample"
    assert row["cells"]["R7"] == "hold"
    assert row["done"] == "no" and row["skill_complete"] == "no"
    assert "needs-input:brand-identity" in row["logs"]
    assert not any(log.startswith("t3-signoff") for log in row["logs"])
    assert (row.get("signoff_id") == "synthetic-brand-doctor") == (state == "valid")
    if checkout:
        assert all(row["cells"][surface] == "hold" for surface in ("banner", "card", "icon"))
    assert readme.read_bytes() == original
    assert sorted(p.name for p in target.iterdir()) == ["README.md"]

    # The coverage-only path must never change the ordinary generation/consent boundary.
    output = tmp_path / "banner.png"
    render = run_cli("--format", "json", *common, "banner", "--out", output, "--allow-unmeasured")
    assert render.returncode == (4 if state == "valid" else 2), render.stdout + render.stderr
    assert ("needs-input:brand-identity" if state == "valid" else "t3-signoff") in render.stdout + render.stderr
    assert not output.exists()


@pytest.mark.parametrize("owner", ["BunsDev", "MetatronAngelAgent"])
def test_doctor_still_refuses_excluded_owners(tmp_path, owner):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": owner, "repo": "sample", "visibility": "public"}), encoding="utf-8")
    result = run_cli("--meta", meta, "--no-repo-dir", "doctor", "--format", "json")
    assert result.returncode == 2
    assert json.loads(result.stdout)["result"] == "refused"
