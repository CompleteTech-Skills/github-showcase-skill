"""Missing onboarding vocabulary holds topic writes through the public CLI."""
import json

import pytest

from conftest import ROOT, meta_dict, run_cli
from ctshowcase.config import yaml
from test_brand_onboarding_cli import family_args


@pytest.fixture
def onboarded(tmp_path, monkeypatch):
    config = tmp_path / "package" / "references" / "brand.yaml"
    config.parent.mkdir(parents=True)
    config.write_bytes((ROOT / "references" / "brand.yaml").read_bytes())
    estate = tmp_path / "estate"
    (estate / "decisions").mkdir(parents=True)
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(estate))
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(estate / "absent-signoffs.yaml"))
    written = run_cli(*family_args(config, "--write"))
    assert written.returncode == 0, written.stdout + written.stderr
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["orgs"]["Northwind-Onboard"]["former_slugs"] = ["Northwind-Onboard-Old"]
    config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return config


def context_args(config, tmp_path, owner="Northwind-Onboard", repo="triage-tool", **extra):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner=owner, repo=repo, description="Run finance tools.", **extra)),
                    encoding="utf-8")
    checkout = tmp_path / "checkout"
    checkout.mkdir(exist_ok=True)
    (checkout / "README.md").write_text("# Finance tools\n", encoding="utf-8")
    return ("--config", config, "--meta", meta, "--repo-dir", checkout, "--format", "json")


@pytest.mark.parametrize("owner,repo,visibility,archived,current", [
    ("Northwind-Onboard", "triage-tool", "public", False, ["northwind", "client-docs", "py", "beta", "northwind"]),
    ("Northwind-Onboard", "triage-tool", "private", False, []),
    ("Northwind-Onboard", "triage-tool", "public", True, ["northwind", "python"]),
    ("northwind-onboard", "triage-tool", "public", False, ["workspace", "finance", "python"]),
    ("Northwind-Onboard-Old", "triage-tool", "private", False, ["northwind", "python"]),
    ("Northwind-Onboard", ".github", "public", False, ["northwind", "github-profile"]),
    ("Northwind-Onboard", ".github", "public", False, []),
])
def test_missing_brand_holds_cli_records_doctor_and_adopt(
        onboarded, tmp_path, owner, repo, visibility, archived, current):
    common = context_args(onboarded, tmp_path, owner, repo, visibility=visibility, archived=archived, topics=current)
    records = tmp_path / "topics.jsonl"
    result = run_cli(*common, "topics", "--gh", "--records", records)
    assert result.returncode == 4, result.stdout + result.stderr
    data = json.loads(result.stdout)
    expected = list(dict.fromkeys(current + ["github-profile"])) if repo == ".github" else current
    assert data["current"] == current and data["proposed"] == expected
    assert data["remove"] == [] and data["plan_allowed"] is False
    assert data["result"] == "needs-input" and "needs-input:brand-topic" in data["logs"]
    assert "gh" not in data and not records.exists()
    records.write_bytes(b"existing records\r\n")
    result = run_cli(*common, "topics", "--gh", "--records", records)
    assert result.returncode == 4
    assert records.read_bytes() == b"existing records\r\n"

    result = run_cli(*common, "doctor", "--format", "json")
    data = json.loads(result.stdout)
    assert data["cells"]["R3"] == "hold"
    assert "needs-input:brand-topic" in data["logs"]

    adopt_records, adopt_jobs = tmp_path / "adopt-records.jsonl", tmp_path / "adopt-jobs.jsonl"
    result = run_cli(*common, "adopt", f"{owner}/{repo}", "--records", adopt_records, "--jobs", adopt_jobs)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    for path in (adopt_records, adopt_jobs):
        emitted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
        assert not [item for item in emitted if item.get("kind") == "topics"]
    assert not [job for job in data["jobs"] if job.get("kind") == "topics"]
    assert not [record for record in data["records"] if record.get("kind") == "topics"]
    assert any("brand topic" in pending["why"] for pending in data["pending"])
    assert "needs-input:brand-topic" in data["logs"]
    if archived:
        assert data["jobs"] == data["records"] == []
        assert any("unarchive" in pending["why"] for pending in data["pending"])
    else:
        assert any(job["kind"] == "repo-settings" for job in data["jobs"])
        assert any(record["kind"] == "settings" for record in data["records"])


@pytest.mark.parametrize("fork,owner,repo,expected", [
    (True, "Northwind-Onboard", "triage-fork", ["fork", "python", "ai"]),
    (False, "Northwind-Onboard-Old", "triage-tool", ["northwind", "workspace", "finance", "python"]),
    (False, "Northwind-Onboard", ".github", ["northwind", "github-profile"]),
])
def test_brand_free_forks_and_explicit_topics_still_plan(onboarded, tmp_path, fork, owner, repo, expected):
    if not fork:
        raw = yaml.safe_load(onboarded.read_text(encoding="utf-8"))
        raw["orgs"]["Northwind-Onboard"]["brand_topic"] = "northwind"
        onboarded.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    common = context_args(onboarded, tmp_path, owner, repo, fork=fork, topics=[],
                          parent={"topics": ["python", "artificial-intelligence", "upstream-brand"]})
    records = tmp_path / "records.jsonl"
    result = run_cli(*common, "topics", "--gh", "--records", records)
    assert result.returncode == 1, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["proposed"] == expected and data.get("plan_allowed", True)
    assert "needs-input:brand-topic" not in data["logs"]
    assert "-X PUT" in data["gh"]
    assert json.loads(records.read_text(encoding="utf-8"))["after"] == expected
    coverage = json.loads(run_cli(*common, "doctor", "--format", "json").stdout)
    assert coverage["cells"]["R3"] == "fail"
    assert "needs-input:brand-topic" not in coverage["logs"]
    result = run_cli(*common, "adopt", f"{owner}/{repo}")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    jobs = [job for job in data["jobs"] if job.get("kind") == "topics"]
    assert len(jobs) == 1 and jobs[0]["repo"] == f"Northwind-Onboard/{repo}"
    assert [record["after"] for record in data["records"] if record.get("kind") == "topics"] == [expected]


@pytest.mark.parametrize("allow", [False, True])
def test_missing_brand_never_bypasses_t3_consent(onboarded, tmp_path, allow):
    raw = yaml.safe_load(onboarded.read_text(encoding="utf-8"))
    raw["orgs"]["Northwind-Onboard"]["tier"] = "T3"
    raw["owners"]["t3"].append("Northwind-Onboard")
    onboarded.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    common = context_args(onboarded, tmp_path, topics=["northwind"])
    result = run_cli(*(["--allow-t3"] if allow else []), *common, "topics", "--gh")
    assert result.returncode == 2, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["result"] == "refused" and "gh" not in data
    assert any(log.startswith("t3-signoff") for log in data["logs"])


def test_missing_brand_and_unsafe_topics_keep_both_holds(onboarded, tmp_path):
    common = context_args(onboarded, tmp_path, visibility="private", topics=["pokemon", "curated-subject"])
    result = run_cli(*common, "topics", "--gh", "--records", tmp_path / "records.jsonl")
    data = json.loads(result.stdout)
    assert result.returncode == 4
    assert data["proposed"] == ["pokemon", "curated-subject"]
    assert {"needs-input:brand-topic", "needs-review:topic-safety"} <= set(data["logs"])
    assert not data["plan_allowed"] and "gh" not in data
    assert not (tmp_path / "records.jsonl").exists()
    coverage = json.loads(run_cli(*common, "doctor", "--format", "json").stdout)
    assert coverage["cells"]["R3"] == "hold"
    assert "needs-review:topic-safety" in coverage["logs"]
    adopted = json.loads(run_cli(*common, "adopt", "Northwind-Onboard/triage-tool").stdout)
    assert not any(job["kind"] == "topics" for job in adopted["jobs"])
    assert not any(record.get("kind") == "topics" for record in adopted["records"])
