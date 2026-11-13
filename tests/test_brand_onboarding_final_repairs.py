"""Public onboarding failures preserve files and outside identities stay their own."""
import json

import pytest
from PIL import Image

from conftest import ROOT, meta_dict, run_cli
from ctshowcase.config import load_yaml_text, schema_errors, yaml
from test_brand_onboarding_cli import family_args


@pytest.fixture
def copied_config(tmp_path):
    config = tmp_path / "package" / "references" / "brand.yaml"
    config.parent.mkdir(parents=True)
    config.write_bytes((ROOT / "references" / "brand.yaml").read_bytes())
    return config


@pytest.mark.parametrize("existing_lock", [False, True])
@pytest.mark.parametrize("action", ["add-family", "add-org"])
def test_non_json_yaml_scalar_refuses_before_any_write_and_allows_retry(copied_config, tmp_path, existing_lock, action):
    raw = load_yaml_text(copied_config.read_text(encoding="utf-8"))
    # YAML's ordinary date type is permitted by this mapping's additional fields,
    # but cannot be represented in the adjacent JSON lock without changing its value.
    raw["brand_strings"]["review_date"] = load_yaml_text("value: 2026-11-13")["value"]
    assert not schema_errors(raw)
    copied_config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    lock = copied_config.with_name("brand.lock.json")
    if existing_lock:
        lock.write_bytes(b"previous lock\r\n")
    mark = tmp_path / "authorized.png"
    Image.new("RGBA", (12, 12), (30, 80, 140, 255)).save(mark)
    before = {p: p.read_bytes() for p in (copied_config, mark, *([lock] if existing_lock else []))}
    if action == "add-family":
        arguments = family_args(copied_config, "--mark", mark)
    else:
        arguments = ("--config", copied_config, "brand", "add-org", "--family", "completetech",
                     "--org", "Northwind-Onboard", "--display-name", "Northwind Onboard",
                     "--tier", "T2", "--footer", "no", "--mark", mark)
    refused = run_cli(*arguments, "--write")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "JSON lock" in refused.stdout
    assert "Traceback" not in refused.stdout + refused.stderr
    assert all(p.read_bytes() == value for p, value in before.items())
    assert lock.exists() == existing_lock
    assert not (copied_config.parent.parent / "assets").exists()

    raw["brand_strings"].pop("review_date")
    copied_config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    retried = run_cli(*arguments, "--write")
    assert retried.returncode == 0, retried.stdout + retried.stderr
    assert json.loads(lock.read_text(encoding="utf-8")) == load_yaml_text(copied_config.read_text(encoding="utf-8"))
    target = copied_config.parent.parent / "assets" / "orgs" / "Northwind-Onboard" / "mark.png"
    assert target.read_bytes() == mark.read_bytes()


def test_new_outside_org_profile_topics_do_not_infer_completetech(copied_config, tmp_path):
    written = run_cli(*family_args(copied_config, "--write"))
    assert written.returncode == 0, written.stdout + written.stderr
    meta = tmp_path / "profile.json"
    meta.write_text(json.dumps(meta_dict(owner="Northwind-Onboard", repo=".github", language="Markdown")),
                    encoding="utf-8")
    records = tmp_path / "records.jsonl"
    checked = run_cli("--config", copied_config, "--meta", meta, "--no-repo-dir", "topics",
                      "--gh", "--records", records)
    assert checked.returncode == 4, checked.stdout + checked.stderr
    result = json.loads(checked.stdout)
    assert result["result"] == "needs-input"
    assert result["proposed"] == ["github-profile"]
    assert result["plan_allowed"] is False
    assert "needs-input:brand-topic" in result["logs"]
    assert "gh" not in result
    assert not records.exists()

    # An explicitly configured affiliation continues to be used, including renamed
    # or recased resolver identities; onboarding does not override existing policy.
    meta.write_text(json.dumps(meta_dict(owner="completetech-security", repo=".github", language="Markdown")),
                    encoding="utf-8")
    checked = run_cli("--config", copied_config, "--meta", meta, "--no-repo-dir", "topics")
    assert checked.returncode == 1, checked.stdout + checked.stderr
    result = json.loads(checked.stdout)
    assert result["proposed"] == ["completetech", "github-profile"]
    assert "needs-input:brand-topic" not in result["logs"]


@pytest.mark.parametrize("current", [["github-profile"], ["northwind", "github-profile", "client-docs"]])
def test_missing_brand_profile_holds_topics_in_cli_doctor_and_adopt(copied_config, tmp_path, current):
    assert run_cli(*family_args(copied_config, "--write")).returncode == 0
    meta = tmp_path / "profile.json"
    meta.write_text(json.dumps(meta_dict(owner="Northwind-Onboard", repo=".github", language="Markdown",
                                        topics=current)), encoding="utf-8")
    common = ("--config", copied_config, "--meta", meta, "--no-repo-dir", "--format", "json")
    records = tmp_path / "records.jsonl"
    checked = run_cli(*common, "topics", "--gh", "--records", records)
    assert checked.returncode == 4, checked.stdout + checked.stderr
    result = json.loads(checked.stdout)
    assert result["result"] == "needs-input"
    assert result["current"] == current
    assert result["proposed"] == current
    assert result["remove"] == []
    assert result["plan_allowed"] is False
    assert "gh" not in result and not records.exists()

    checked = run_cli(*common, "doctor", "--format", "json")
    result = json.loads(checked.stdout)
    assert result["cells"]["R3"] == "hold", result
    assert "needs-input:brand-topic" in result["logs"]

    checked = run_cli(*common, "adopt", "Northwind-Onboard/.github")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    result = json.loads(checked.stdout)
    assert not [job for job in result["jobs"] if job.get("kind") == "topics"]
    assert not [record for record in result["records"] if record.get("kind") == "topics"]
    assert any("brand topic" in pending["why"] for pending in result["pending"])
    assert "needs-input:brand-topic" in result["logs"]
