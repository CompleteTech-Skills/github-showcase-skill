"""Public CLI coverage at the onboarding/brand-policy dependency boundary."""
import json
import xml.etree.ElementTree as ET

import pytest

from conftest import ROOT, meta_dict, run_cli
from ctshowcase.color import contrast
from test_brand_onboarding_cli import family_args


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "package/references/brand.yaml"
    path.parent.mkdir(parents=True)
    path.write_bytes((ROOT / "references/brand.yaml").read_bytes())
    return path


@pytest.mark.parametrize("visibility", ["public", "private"])
def test_onboarded_family_keeps_legal_wording_unknown_and_badges_readable(config, tmp_path, visibility):
    added = run_cli(*family_args(config, "--write"))
    assert added.returncode == 0, added.stdout + added.stderr
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner="Northwind-Onboard", repo="synthetic-tool",
        visibility=visibility, license="MIT", language="Python", files=["main.py", "LICENSE"])), encoding="utf-8")
    rendered = run_cli("--config", config, "--meta", meta, "--repo-dir", checkout,
        "--format", "json", "readme", "--mode", "scaffold", "--variant", "C", "--badges", "local", "--write")
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    assert "needs-input:license-wording" in json.loads(rendered.stdout)["logs"]
    text = (checkout / "README.md").read_text(encoding="utf-8")
    assert "CompleteTech" not in text and "CompleteDotTech" not in text
    assert "Proprietary" not in text and "Copyright" not in text
    if visibility == "public":
        assert "Code and documentation are licensed under the MIT License" in text
    else:
        assert "## License" not in text
    badges = list((checkout / "docs/images/badges").glob("*.svg"))
    assert badges
    namespace = {"s": "http://www.w3.org/2000/svg"}
    for path in badges:
        svg = ET.fromstring(path.read_text(encoding="utf-8"))
        backgrounds = svg.findall("s:g/s:rect", namespace)
        outlines = [g for g in svg.findall("s:g", namespace) if g.findall("s:use", namespace)]
        assert len(backgrounds) == len(outlines) == 2
        for background, outline in zip(backgrounds, outlines):
            assert contrast(background.attrib["fill"], outline.attrib["fill"]) >= 4.5


def test_add_org_to_pending_family_does_not_supply_an_identity(config, tmp_path):
    added = run_cli("--config", config, "brand", "add-org", "--family", "ticketstub",
        "--org", "Northwind-Pending", "--tier", "T2", "--display-name", "Northwind Pending",
        "--footer", "no", "--write")
    assert added.returncode == 0, added.stdout + added.stderr
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner="Northwind-Pending", repo="synthetic-tool")), encoding="utf-8")
    common = ("--config", config, "--meta", meta, "--no-repo-dir", "--format", "json")
    output = tmp_path / "card.svg"
    refused = run_cli(*common, "card", "--allow-unmeasured", "--out", output)
    assert refused.returncode == 4, refused.stdout + refused.stderr
    assert "needs-input:brand-identity" in refused.stdout
    assert not output.exists()
    coverage = run_cli(*common, "doctor", "--allow-unmeasured", "--format", "json")
    result = json.loads(coverage.stdout)
    assert "needs-input:brand-identity" in result["logs"]
    assert result["cells"]["R7"] == "hold"
