"""Safety holds and count exceptions must survive additive topic planning."""
import json

import pytest

from conftest import run_cli
from ctshowcase import doctor, intake, topics


@pytest.mark.parametrize("meta", [
    {},
    {"visibility": "private"},
    {"visibility": "internal"},
    {"repo": ".github"},
    {"fork": True, "parent": {"topics": ["python"]}},
])
def test_prohibited_authored_topic_is_evidence_not_an_approved_plan(make_ctx, meta):
    ctx = make_ctx(topics=["nsfw"], **meta)
    result = topics.merge(ctx)

    assert result["current"] == ["nsfw"]
    assert "nsfw" in result["proposed"]
    assert result["remove"] == []
    assert not result["plan_allowed"]
    assert not result["equal_as_set"]
    assert "needs-review:topic-safety" in result["logs"]
    assert doctor.row(ctx)["cells"]["R3"] == "fail"


def test_org_extra_cannot_authorize_prohibited_topic(make_ctx):
    ctx = make_ctx(description="Explore nsfw tooling.")
    ctx.org = dict(ctx.org, topics_extra=["nsfw"])
    result = topics.merge(ctx)
    assert "nsfw" in result["proposed"]
    assert not result["plan_allowed"]
    assert "needs-review:topic-safety" in result["logs"]


def test_prohibited_topics_hold_cli_and_adopt_mutations(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({
        "owner": "Northwind-Trading-Co", "repo": "support-triage-agent",
        "description": "Explore compatibility.", "topics": ["nsfw"],
        "visibility": "public", "language": "Python",
    }), encoding="utf-8")
    records = tmp_path / "records.jsonl"
    result = run_cli("--meta", meta, "--no-repo-dir", "topics", "--gh", "--records", records)
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert not payload["plan_allowed"]
    assert "needs-review:topic-safety" in payload["logs"]
    assert payload["remove"] == []
    assert "nsfw" in payload["proposed"]
    assert "gh" not in payload
    assert not records.exists()

    result = run_cli("--meta", meta, "--no-repo-dir", "adopt", "Northwind-Trading-Co/support-triage-agent")
    payload = json.loads(result.stdout)
    assert "needs-review:topic-safety" in payload["logs"]
    assert not any(job["kind"] == "topics" for job in payload["jobs"])
    assert not any(record.get("kind") == "topics" for record in payload["records"])


@pytest.mark.parametrize("meta, expected", [
    ({"repo": ".github", "topics": ["completetech", "github-profile"]}, ["completetech", "github-profile"]),
    ({"fork": True, "topics": ["fork", "python"], "parent": {"topics": ["python"]}}, ["fork", "python"]),
    ({"fork": True, "topics": ["fork"], "parent": {"topics": []}}, ["fork"]),
])
@pytest.mark.parametrize("visibility", ["public", "private", "internal"])
def test_canonical_fork_and_profile_topic_sets_have_no_normal_minimum(make_ctx, meta, expected, visibility):
    ctx = make_ctx(visibility=visibility, **meta)
    result = topics.merge(ctx)
    assert result["proposed"] == expected
    assert result["equal_as_set"]
    assert result["plan_allowed"]
    assert "topics-short" not in result["logs"]
    assert doctor.row(ctx)["cells"]["R3"] == "pass"


def test_regular_public_repository_still_reports_minimum_and_safe_adopt_plan(make_ctx):
    ctx = make_ctx(topics=["completetech", "workspace", "python"], description="Explore compatibility.")
    result = topics.merge(ctx)
    assert result["equal_as_set"]
    assert "topics-short" in result["logs"]
    assert doctor.row(ctx)["cells"]["R3"] == "warn"
    changed = make_ctx(topics=["accurate-subject"], description="Explore compatibility.")
    plan = intake.adopt(changed)
    jobs = [job for job in plan["jobs"] if job["kind"] == "topics"]
    assert len(jobs) == 1
    assert "names[]=accurate-subject" in jobs[0]["argv"]


@pytest.mark.parametrize("meta, expected", [
    ({"repo": ".github", "topics": ["completetech", "github-profile"]}, ["completetech", "github-profile"]),
    ({"fork": True, "topics": ["fork", "python"], "parent": {"topics": ["python"]}}, ["fork", "python"]),
])
def test_cli_keeps_canonical_short_sets_complete(tmp_path, meta, expected):
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "support-triage-agent",
                                "description": "Explore compatibility.", "visibility": "public", **meta}),
                    encoding="utf-8")
    result = run_cli("--meta", path, "--no-repo-dir", "topics", "--gh")
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["proposed"] == expected
    assert "topics-short" not in payload["logs"]
    assert "gh" not in payload
    audited = run_cli("--meta", path, "--no-repo-dir", "doctor", "--format", "json")
    assert json.loads(audited.stdout)["cells"]["R3"] == "pass"
