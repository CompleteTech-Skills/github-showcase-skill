"""Missing-input diagnostics describe the wording selected for the actual surface."""
import copy
import json

import pytest
import yaml

from conftest import run_cli
from ctshowcase import readme
from ctshowcase.config import Brand
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize


@pytest.mark.parametrize("general,skills,assets,selected,missing", [
    (None, "Explicit synthetic asset terms.", True, "Explicit synthetic asset terms.", False),
    (None, None, True, None, True),
    ("Explicit synthetic general terms.", None, True, "Explicit synthetic general terms.", False),
    ("Explicit synthetic general terms.", "Explicit synthetic asset terms.", True,
     "Explicit synthetic asset terms.", False),
    ("Explicit synthetic general terms.", " ", True, None, True),
    (None, "Explicit synthetic asset terms.", False, None, True),
    ("Explicit synthetic general terms.", "Explicit synthetic asset terms.", False,
     "Explicit synthetic general terms.", False),
])
def test_missing_wording_describes_the_selected_surface(brand, general, skills, assets, selected, missing):
    raw = copy.deepcopy(brand.raw)
    row = raw["orgs"]["LibreEvolve"]
    row.pop("license_wording", None)
    row.pop("skills_license_wording", None)
    for key, value in (("license_wording", general), ("skills_license_wording", skills)):
        if value is not None:
            row[key] = value
    ctx = RepoContext(Brand(raw, brand.path), normalize({
        "owner": "LibreEvolve", "repo": "sample-tool", "visibility": "public", "license": "MIT",
        "description": "Inspect synthetic records.", "files": ["BRAND_ASSETS.md"] if assets else [],
    }))
    title, body = readme.license_section(ctx)
    assert title == "License"
    assert ("needs-input:license-wording" in ctx.logs) is missing
    assert ("Code, templates, and documentation" in body) is assets
    for wording in ("Explicit synthetic general terms.", "Explicit synthetic asset terms."):
        assert (wording in body) is (wording == selected)


@pytest.mark.parametrize("general,skills,expected,missing", [
    (None, "Explicit synthetic asset terms.", "Explicit synthetic asset terms.", False),
    (None, None, None, True),
    ("Explicit synthetic general terms.", None, "Explicit synthetic general terms.", False),
])
def test_cli_skills_wording_diagnostic_matches_its_generated_section(
        brand, tmp_path, general, skills, expected, missing):
    raw = copy.deepcopy(brand.raw)
    row = raw["orgs"]["LibreEvolve"]
    row.pop("license_wording", None)
    row.pop("skills_license_wording", None)
    for key, value in (("license_wording", general), ("skills_license_wording", skills)):
        if value is not None:
            row[key] = value
    config = tmp_path / "brand.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "LibreEvolve", "repo": "sample-tool", "visibility": "public",
                               "license": "MIT", "description": "Inspect synthetic records.",
                               "files": ["BRAND_ASSETS.md"], "files_complete": True}), encoding="utf-8")
    (tmp_path / "BRAND_ASSETS.md").write_text("Synthetic asset notice.\n", encoding="utf-8")
    result = run_cli("--format", "json", "--config", config, "--meta", meta, "--repo-dir", tmp_path,
                     "readme", "--mode", "scaffold")
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert ("needs-input:license-wording" in output["logs"]) is missing
    if expected:
        assert expected in output["diff"]
    assert not (tmp_path / "README.md").exists()


@pytest.mark.parametrize("field", ["license_wording", "skills_license_wording", "private_license_wording"])
@pytest.mark.parametrize("value", [None, ["not a wording string"]])
def test_cli_invalid_wording_types_refuse_before_writes(brand, tmp_path, field, value):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"]["LibreEvolve"][field] = value
    config = tmp_path / "brand.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "LibreEvolve", "repo": "sample-tool", "license": "MIT",
                               "visibility": "private" if field == "private_license_wording" else "public",
                               "description": "Inspect synthetic records.", "created_at": "2024-01-01",
                               "files": ["BRAND_ASSETS.md"], "files_complete": True}), encoding="utf-8")
    (tmp_path / "BRAND_ASSETS.md").write_text("Synthetic asset notice.\n", encoding="utf-8")
    result = run_cli("--format", "json", "--config", config, "--meta", meta, "--repo-dir", tmp_path,
                     "readme", "--mode", "scaffold", "--write")
    assert result.returncode == 2, result.stdout + result.stderr
    assert field in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert not (tmp_path / "README.md").exists()
