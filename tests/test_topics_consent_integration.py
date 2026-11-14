"""Additive topic payloads keep scoped consent evidence after current-main integration."""
import json

import pytest

from conftest import run_cli


@pytest.fixture
def topic_inputs(tmp_path):
    grants = tmp_path / "signoffs.json"
    grants.write_text(json.dumps({"signoffs": [{
        "id": "t3s-topic-integration", "owner": "Pick-Your-AI", "repos": ["*"],
        "approved": True, "approver": "synthetic-co-owner", "approved_on": "2026-01-15",
        "expires": "2099-12-31",
    }]}), encoding="utf-8")
    meta = {
        "owner": "Northwind-Trading-Co", "repo": "support-triage-agent",
        "description": "Explore compatibility.", "topics": ["curated-subject"],
        "visibility": "public", "language": "Python", "also_in": ["Pick-Your-AI"],
    }
    return grants, meta


def _run(tmp_path, inputs, *, command="topics", **changes):
    grants, metadata = inputs
    metadata = dict(metadata, **changes)
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    args = ["--meta", path, "--no-repo-dir", "--allow-t3", "--t3-signoff-file", grants, command]
    if command == "topics":
        args += ["--gh", "--records", tmp_path / "records.jsonl"]
    else:
        args += ["Northwind-Trading-Co/support-triage-agent"]
    result = run_cli(*args)
    assert result.returncode != 2, result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("fork", [False, True])
def test_additive_payload_preserves_authored_topics_and_association_evidence(tmp_path, topic_inputs, fork):
    payload = _run(tmp_path, topic_inputs, fork=fork, parent={"topics": ["python"]})
    assert "curated-subject" in payload["proposed"]
    assert "pick-your-ai" in payload["proposed"]
    assert payload["remove"] == []
    assert payload["signoff_ids"] == ["t3s-topic-integration"]
    records = [json.loads(row) for row in (tmp_path / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["after"] == payload["proposed"]
    assert records[0]["signoff_id"] == "t3s-topic-integration"
    assert "approval_id" not in records[0]


def test_capacity_does_not_claim_consent_for_an_omitted_association(tmp_path, topic_inputs):
    authored = [f"curated-{index}" for index in range(10)]
    payload = _run(tmp_path, topic_inputs, topics=authored)
    assert payload["proposed"] == authored
    assert "needs-input:topics-capacity" in payload["logs"]
    assert "signoff_ids" not in payload
    assert not (tmp_path / "records.jsonl").exists()


def test_safety_hold_with_valid_association_does_not_release_writer_material(tmp_path, topic_inputs):
    payload = _run(tmp_path, topic_inputs, topics=["nsfw"])
    assert "needs-review:topic-safety" in payload["logs"]
    assert not payload["plan_allowed"]
    assert "gh" not in payload
    assert not (tmp_path / "records.jsonl").exists()


def test_adopt_keeps_additive_payload_and_association_evidence(tmp_path, topic_inputs):
    payload = _run(tmp_path, topic_inputs, command="adopt")
    jobs = [job for job in payload["jobs"] if job["kind"] == "topics"]
    records = [record for record in payload["records"] if record["kind"] == "topics"]
    assert len(jobs) == len(records) == 1
    assert "names[]=curated-subject" in jobs[0]["argv"]
    assert "names[]=pick-your-ai" in jobs[0]["argv"]
    assert jobs[0]["signoff_id"] == records[0]["signoff_id"] == "t3s-topic-integration"
    assert "curated-subject" in records[0]["after"]
