"""Actual footer CLI checks need applicability, not a pending family's palette (#162)."""
import copy
import json

import pytest
import yaml

from conftest import run_cli

OWNER = "Jevelopers-neatHack-2026"
ALIAS = "Northwind-Co-Owned"


@pytest.fixture
def pending_footer(brand, tmp_path, monkeypatch):
    # Isolate all resolver/consent discovery from any real estate bundle.
    estate = tmp_path / "synthetic-estate"
    (estate / "decisions").mkdir(parents=True)
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(estate))
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][OWNER]["former_slugs"] = [ALIAS]
    raw["owners"]["hold"].append("Northwind-Held")
    config = tmp_path / "brand.yaml"
    meta = tmp_path / "meta.json"
    readme = tmp_path / "README.md"
    readme.write_text("# Synthetic authored text\n", encoding="utf-8")
    grant = tmp_path / "synthetic-signoffs.json"

    def setup(*, owner=OWNER, footer=False, state="valid", scoped=True):
        raw["orgs"][OWNER]["footer"] = footer
        config.write_text(yaml.safe_dump(raw), encoding="utf-8")
        meta.write_text(json.dumps({"owner": owner, "repo": "sample", "visibility": "public",
                                    "description": "Inspect synthetic records.", "files": ["main.py"]}),
                        encoding="utf-8")
        record = {"id": "synthetic-footer", "owner": OWNER, "repos": ["sample" if scoped else "*"],
                  "approved": True, "approver": "synthetic-co-owner", "approved_on": "2020-01-15"}
        records = [record]
        if state == "missing":
            records = []
        elif state == "wrong-owner":
            record["owner"] = "Northwind-Trading-Co"
        elif state == "scope":
            record["repos"] = ["other"]
        elif state == "expired":
            record["expires"] = "2020-01-16"
        elif state == "revoked":
            records.append(dict(record, id="synthetic-withdrawal", approved=False, approved_on="2020-01-16"))
        grant.write_text(json.dumps({"signoffs": records}), encoding="utf-8")
        common = ["--config", config, "--meta", meta, "--repo-dir", tmp_path,
                  "--allow-t3", "--t3-signoff-file", grant]
        return common, readme, tmp_path

    return setup


@pytest.mark.parametrize("owner,explicit", [(OWNER, None), (ALIAS, None), (ALIAS, OWNER), (OWNER, ALIAS)])
@pytest.mark.parametrize("footer,expected,cell,code", [
    (False, "exempt", "n/a", 0), ("hold", "hold", "hold", 0), (True, "fail:missing", "fail", 1),
])
def test_pending_footer_matches_doctor(pending_footer, owner, explicit, footer, expected, cell, code):
    common, readme, target = pending_footer(owner=owner, footer=footer)
    original = readme.read_bytes()
    before = sorted(p.name for p in target.iterdir())
    args = ["--org", explicit] if explicit else []
    checked = run_cli(*common, "footer", "--check", readme, *args)
    assert checked.returncode == code, checked.stdout + checked.stderr
    assert json.loads(checked.stdout)["result"] == expected
    doctor = run_cli(*common, "doctor", "--format", "json")
    assert doctor.returncode == 1, doctor.stdout + doctor.stderr
    assert json.loads(doctor.stdout)["cells"]["footer"] == cell
    assert readme.read_bytes() == original
    assert sorted(p.name for p in target.iterdir()) == before


@pytest.mark.parametrize("state,log", [("missing", "missing"), ("wrong-owner", "missing"),
                                     ("revoked", "revoked"), ("expired", "expired"), ("scope", "scope")])
def test_pending_footer_does_not_bypass_scoped_consent(pending_footer, state, log):
    common, readme, _ = pending_footer(state=state)
    result = run_cli(*common, "footer", "--check", readme, "--org", ALIAS)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"t3-signoff:{log}" in json.loads(result.stdout)["logs"]


def test_pending_footer_still_requires_opt_in_and_matching_owner(pending_footer):
    common, readme, _ = pending_footer()
    unsigned = [arg for arg in common if arg != "--allow-t3"]
    result = run_cli(*unsigned, "footer", "--check", readme)
    assert result.returncode == 2 and "t3-signoff" in json.loads(result.stdout)["logs"]
    result = run_cli(*common, "footer", "--check", readme, "--org", "Northwind-Trading-Co")
    assert result.returncode == 2 and "usage" in json.loads(result.stdout)["logs"]


def test_pending_applicable_footer_checks_and_raw_output_preserve_markup(pending_footer):
    common, readme, _ = pending_footer(footer=True)
    # Exercise the product CLI for raw output and then inspect exactly those bytes.
    raw = run_cli(*common, "footer", "--raw")
    assert raw.returncode == 0, raw.stdout + raw.stderr
    baseline = run_cli("footer", "--raw")
    assert raw.stdout == baseline.stdout
    assert '<picture>' in raw.stdout
    assert '/main/assets/brand/logo-dark.png' in raw.stdout
    assert '/main/assets/brand/logo.png' in raw.stdout
    readme.write_text("# Synthetic authored text\n\n" + raw.stdout, encoding="utf-8")
    checked = run_cli(*common, "footer", "--check", readme)
    assert checked.returncode == 0 and json.loads(checked.stdout)["result"] == "pass"

    # Neither read-only inspection nor the applicable footer supplies a missing palette.
    output = readme.parent / "banner.png"
    render = run_cli("--format", "json", *common, "banner", "--out", output, "--allow-unmeasured")
    assert render.returncode == 4
    assert "needs-input:brand-identity" in json.loads(render.stdout)["logs"]
    assert not output.exists()


@pytest.mark.parametrize("owner,log", [("BunsDev", "exempt"), ("Northwind-Held", "hold")])
def test_footer_preserves_excluded_and_held_owner_refusals(pending_footer, owner, log):
    common, readme, _ = pending_footer(owner=owner)
    result = run_cli(*common, "footer", "--check", readme)
    assert result.returncode == 2, result.stdout + result.stderr
    assert log in json.loads(result.stdout)["logs"]


def test_raw_pending_org_still_requires_owner_wide_consent(pending_footer):
    common, _, _ = pending_footer()
    # An --org-only call cannot use a repository-scoped grant.
    org_only = common[:2] + common[6:]
    scoped = run_cli(*org_only, "footer", "--org", ALIAS, "--raw")
    assert scoped.returncode == 2 and "t3-signoff:scope" in json.loads(scoped.stdout)["logs"]
    common, _, _ = pending_footer(scoped=False)
    org_only = common[:2] + common[6:]
    granted = run_cli(*org_only, "footer", "--org", ALIAS, "--raw")
    assert granted.returncode == 0
    assert json.loads(granted.stdout)["result"] == "exempt"
