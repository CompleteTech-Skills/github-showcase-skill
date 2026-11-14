"""Read-only coverage remains available while a family awaits real design inputs."""
import json

import pytest

from conftest import run_cli
from ctshowcase.errors import NeedsInput


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


@pytest.mark.parametrize("captured", [None, False, True])
@pytest.mark.parametrize("state", ["valid", "missing", "revoked", "wrong-scope"])
def test_org_doctor_pending_identity_preserves_row_and_consent(tmp_path, monkeypatch, captured, state):
    estate = tmp_path / "synthetic-estate"
    (estate / "decisions").mkdir(parents=True)
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(estate))
    grant = _signoff(tmp_path, "revoked" if state == "revoked" else "valid")
    rows = json.loads(grant.read_text(encoding="utf-8"))
    for row in rows["signoffs"]:
        row["repos"] = ["sample"] if state == "wrong-scope" else ["*"]
    if state == "missing":
        rows["signoffs"] = []
    grant.write_text(json.dumps(rows), encoding="utf-8")
    snapshot = tmp_path / "snapshot.json"
    repo = {"name": ".github", "visibility": "public"}
    if captured is not None:
        repo["files"] = {"profile/assets/banner.jpg": captured}
    snapshot.write_text(json.dumps({"org": {"name": "TicketStub", "description": "Synthetic captured facts."},
                                    "repos": [repo]}), encoding="utf-8")
    common = ["--format", "json", "--allow-t3", "--t3-signoff-file", grant]
    result = run_cli(*common, "org", "doctor", OWNER, "--snapshot", snapshot)
    row = json.loads(result.stdout)
    if state != "valid":
        assert result.returncode == 2, result.stdout + result.stderr
        assert f"t3-signoff:{'scope' if state == 'wrong-scope' else state}" in row["logs"]
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(row["cells"]) == {"O1", "O2", "O3", "O4", "O6", "O9", "O11"}
    assert row["cells"]["O9"] == "hold" and row["done"] == "no"
    assert row["reads"] and row["checked"]
    assert "needs-input:brand-identity" in row["logs"]
    assert any("O9 needs-input:brand-identity" in n for n in row["notes"])
    output = tmp_path / "banner.jpg"
    render = run_cli(*common, "org-banner", "--org", OWNER, "--out", output)
    assert render.returncode == 4, render.stdout + render.stderr
    assert "needs-input:brand-identity" in render.stdout
    assert not output.exists()


@pytest.mark.parametrize("error", [ValueError("synthetic programming error"),
                                  NeedsInput("unrelated")])
def test_org_doctor_does_not_swallow_other_style_errors(brand, monkeypatch, error):
    from ctshowcase.org import Estate, doctor
    from ctshowcase.resolver import Resolver

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(brand, "style", fail)
    estate = Estate(brand, Resolver(brand, {}, {}))
    with pytest.raises(type(error), match=str(error)):
        doctor(estate, "Northwind-Trading-Co", {"org": {}, "repos": []})
