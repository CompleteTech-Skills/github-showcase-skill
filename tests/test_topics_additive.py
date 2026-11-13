"""Topic plans preserve author facts and accept explicit organization vocabulary (#89)."""
import json

import pytest

from ctshowcase.errors import ConfigError
from ctshowcase.topics import merge


def test_vocabulary_poor_owner_preserves_discoverability(make_ctx):
    authored = ["ai-infrastructure", "ai-stack", "compatibility", "json-schema", "pricing", "research"]
    ctx = make_ctx(topics=authored, description="Research compatibility and pricing.")
    result = merge(ctx)
    assert result["proposed"][:len(authored)] == authored
    assert result["remove"] == []
    assert result["plan_allowed"]
    assert "review-remove:compatibility" in result["logs"]
    assert "topics-short" not in result["logs"]


def test_full_topic_set_never_drops_to_fit_required_topics(make_ctx):
    authored = [f"subject-{n}" for n in range(10)]
    result = merge(make_ctx(topics=authored))
    assert result["proposed"] == authored
    assert result["add"] == result["remove"] == []
    assert "needs-input:topics-capacity" in result["logs"]


def test_fork_and_profile_keep_authored_topics(make_ctx):
    for meta in ({"fork": True}, {"repo": ".github"}):
        result = merge(make_ctx(topics=["curated-topic"], **meta))
        assert "curated-topic" in result["proposed"]
        assert result["remove"] == []


def test_org_extra_vocabulary_is_derived_and_passes_r3(make_ctx):
    from ctshowcase.doctor import row
    ctx = make_ctx(topics=["completetech", "workspace", "compatibility", "research-area", "python"],
                   description="Explore compatibility in a research area.")
    ctx.org = dict(ctx.org, topics_extra=["compatibility", "research-area"])
    result = merge(ctx)
    assert result["equal_as_set"]
    assert not result["review_remove"]
    assert "needs-input:domain-topic" not in result["logs"]
    assert row(ctx)["cells"]["R3"] == "pass"


def test_org_extras_are_local_and_never_inferred_for_other_owners(make_ctx):
    approved = make_ctx(topics=["compatibility"], description="Explore compatibility.")
    approved.org = dict(approved.org, topics_extra=["compatibility"])
    assert "review-remove:compatibility" not in merge(approved)["logs"]
    other = make_ctx(topics=["compatibility"], description="Explore compatibility.")
    assert "review-remove:compatibility" in merge(other)["logs"]


@pytest.mark.parametrize("values", ["compatibility", ["Bad-Case"], ["x" * 51], ["has space"], [None], [""], ["-bad"]])
def test_invalid_org_extra_is_configuration_error(make_ctx, values):
    ctx = make_ctx()
    ctx.org = dict(ctx.org, topics_extra=values)
    with pytest.raises(ConfigError, match="topics_extra"):
        merge(ctx)


def test_internal_visibility_uses_private_safety(make_ctx):
    ctx = make_ctx(topics=["pokemon"], visibility="internal")
    result = merge(ctx)
    assert not result["plan_allowed"]
    assert "needs-review:topic-safety" in result["logs"]


def test_invalid_current_topic_is_held(make_ctx):
    ctx = make_ctx(topics=["has space"])
    assert not merge(ctx)["plan_allowed"]


def test_additive_cli_preserves_topics(tmp_path):
    from conftest import run_cli
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "support-triage-agent",
                               "description": "Research compatibility.", "topics": ["compatibility"],
                               "visibility": "public", "language": "Python"}), encoding="utf-8")
    result = run_cli("--meta", meta, "--no-repo-dir", "topics", "--gh")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "names[]=compatibility" in payload["gh"]
    assert payload["remove"] == []


def test_org_extras_cannot_propose_private_banned_topics(make_ctx):
    ctx = make_ctx(description="Play Pokemon.", visibility="private")
    ctx.org = dict(ctx.org, topics_extra=["pokemon"])
    result = merge(ctx)
    assert not result["plan_allowed"]
    assert "needs-review:topic-safety" in result["logs"]
