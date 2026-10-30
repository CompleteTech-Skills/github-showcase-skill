"""E5.1.4 (#89 task 93): topic merge with a vocabulary-poor org, and the additive default.

The default is additive (task 90): an existing out-of-vocabulary topic is kept as an extra while room is left, logged
`review-remove:TOPIC`, and only `--prune` (prune=True) restores the legacy removal. Per-org `topics_extra` (tasks 91-92)
silences the log for org-approved topics only. All data is synthetic: owner Northwind-Trading-Co, repo rates-research.
"""
import copy
import json

import pytest

from conftest import meta_dict, run_cli
from ctshowcase import doctor
from ctshowcase.config import Brand, load_brand, schema_errors
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize
from ctshowcase.topics import merge

OWNER = "Northwind-Trading-Co"
REPO = "rates-research"
DESC = "Rate research notes for Northwind."
CLEAN_EXTRAS = ["rate-card", "dataset-card", "pricing-grid", "fx-desk", "client-portal", "margin-model",
                "quarterly-review", "credit-limits", "invoice-ledger", "vendor-scorecard", "tariff-notes", "ops-runbook"]


def _vocab_poor_brand(base, topics_extra):
    """The base brand with the Northwind row replaced by a vocabulary-poor org that approves `topics_extra`."""
    raw = copy.deepcopy(base.raw)
    raw["orgs"]["Northwind-Trading-Co"] = {
        "family": "completetech", "former_slugs": [], "tier": "T1", "display_name": "Northwind", "nav_name": "Northwind",
        "description": None, "eyebrow": None, "brand_topic": "northwind", "family_topics": [], "footer": True,
        "topics_extra": topics_extra}
    return Brand(raw, base.path)


@pytest.fixture(scope="module")
def base_brand():
    return load_brand()


@pytest.fixture
def vocab_poor(base_brand):
    """Northwind with topics_extra=['rate-card','benchmarks'], the row the spec names."""
    return _vocab_poor_brand(base_brand, ["rate-card", "benchmarks"])


def _ctx(brand, **kw):
    kw.setdefault("repo", REPO)
    kw.setdefault("description", DESC)
    return RepoContext(brand, normalize(meta_dict(**kw)), None)


def test_default_keeps_accurate_existing_topics(make_ctx):
    ctx = make_ctx(repo=REPO, description=DESC, visibility="public", language="Python",
                   topics=["ai", "llm", "rate-card", "benchmarks", "dataset-card", "research"])
    r = merge(ctx)
    current = r["current"]
    # 'research' is a type topic that does not match this repository's type: a hard drop, the only removal allowed
    assert r["remove"] == ["research"]
    assert set(current) - {"research"} <= set(r["proposed"])
    assert "review-remove:rate-card" in r["logs"]
    assert "review-remove:dataset-card" in r["logs"]


def test_default_never_lists_removals_for_vocab_poor_org(make_ctx):
    current = ["completetech", "workspace", "python"] + CLEAN_EXTRAS[:7]
    assert len(current) == 10
    ctx = make_ctx(repo=REPO, description=DESC, visibility="public", language="Python", topics=current)
    r = merge(ctx)
    assert r["remove"] == []
    assert len(r["proposed"]) <= 10
    assert r["equal_as_set"] is True


def test_prune_flag_restores_legacy(make_ctx):
    current = ["completetech", "workspace", "python"] + CLEAN_EXTRAS[:7]
    ctx = make_ctx(repo=REPO, description=DESC, visibility="public", language="Python", topics=current)
    r = merge(ctx, prune=True)
    assert set(CLEAN_EXTRAS[:7]) <= set(r["remove"])
    assert not [x for x in r["logs"] if x.startswith("review-remove:")]


def test_hard_drops_still_removed(make_ctx):
    current = ["llms", "wip", "2024", "Bad_Topic", "completetech", "python"]
    ctx = make_ctx(repo=REPO, description=DESC, visibility="public", language="Python", topics=current)
    r = merge(ctx)
    assert {"wip", "2024", "Bad_Topic", "llms"} <= set(r["remove"])
    assert "llm" in r["proposed"]
    assert "wip" not in r["proposed"] and "2024" not in r["proposed"] and "llms" not in r["proposed"]


def test_private_limit_respected(make_ctx):
    current = ["completetech", "workspace", "python"] + [f"extra-{x}" for x in CLEAN_EXTRAS]
    ctx = make_ctx(repo=REPO, description=DESC, visibility="private", language="Python", topics=current)
    r = merge(ctx)
    assert len(r["proposed"]) <= 8
    assert "completetech" in r["proposed"] and "workspace" in r["proposed"]
    excess = [x for x in current if x.startswith("extra-") and x not in r["proposed"]]
    assert len(excess) >= 1
    assert set(excess) <= set(r["remove"])
    assert {f"review-remove:{x}" for x in excess} <= set(r["logs"])


def test_required_topics_not_displaced(make_ctx):
    current = ["completetech", "workspace", "python"] + [f"extra-{x}" for x in CLEAN_EXTRAS[:10]]
    ctx = make_ctx(repo=REPO, description=DESC, visibility="public", language="Python", topics=current)
    r = merge(ctx)
    assert "completetech" in r["proposed"] and "workspace" in r["proposed"]
    assert len(r["proposed"]) <= 10


def test_topics_extra_silences_review_remove(vocab_poor):
    ctx = _ctx(vocab_poor, visibility="public", language="Python",
               topics=["rate-card", "benchmarks", "dataset-card"])
    r = merge(ctx)
    assert "rate-card" in r["proposed"] and "benchmarks" in r["proposed"]
    assert "review-remove:rate-card" not in r["logs"]
    assert "review-remove:dataset-card" in r["logs"]  # not approved by the org, still logged


def test_topics_extra_does_not_invent(vocab_poor):
    ctx = _ctx(vocab_poor, visibility="public", language="Python", topics=["rate-card"])
    r = merge(ctx)
    assert "benchmarks" not in r["proposed"]


def test_topics_extra_ignores_invalid_entries(base_brand):
    brand = _vocab_poor_brand(base_brand, ["Bad Topic", 5, "ok-topic"])
    ctx = _ctx(brand, visibility="public", language="Python", topics=["ok-topic", "dataset-card"])
    r = merge(ctx)  # no exception on non-string and malformed entries
    assert "ok-topic" in r["proposed"]
    assert "review-remove:ok-topic" not in r["logs"]
    assert "review-remove:dataset-card" in r["logs"]
    assert "Bad Topic" not in r["proposed"] and "bad topic" not in r["proposed"]


def test_r3_pass_with_org_approved_topics(base_brand):
    brand = _vocab_poor_brand(base_brand, ["rate-card", "pricing-grid", "fx-desk"])
    ctx = _ctx(brand, visibility="public", language="Python",
               topics=["northwind", "rate-card", "pricing-grid", "fx-desk", "workspace", "python"])
    r = merge(ctx)
    assert r["equal_as_set"] is True and len(r["proposed"]) >= 5
    row = doctor.row(ctx)
    assert row["cells"]["R3"] == "pass"


def test_schema_topics_extra(base_brand):
    def errors_for(value):
        raw = copy.deepcopy(base_brand.raw)
        raw["orgs"]["Northwind-Trading-Co"]["topics_extra"] = value
        return [e for e in schema_errors(raw) if "topics_extra" in e]

    assert errors_for(["rate-card", "benchmarks"]) == []
    for bad in (["Upper"], ["has space"], ["x" * 51], "rate-card"):
        assert errors_for(bad), f"expected a topics_extra schema error for {bad!r}"


def test_cli_prune_flag(tmp_path):
    meta = tmp_path / "rates-research.json"
    meta.write_text(json.dumps(meta_dict(owner=OWNER, repo=REPO, description=DESC, visibility="public", language="Python",
                                         topics=["completetech", "workspace", "python", *CLEAN_EXTRAS[:7]])),
                    encoding="utf-8")
    p = run_cli("--meta", meta, "--no-repo-dir", "topics")
    default = json.loads(p.stdout)
    assert not (set(CLEAN_EXTRAS[:7]) & set(default["remove"]))
    p = run_cli("--meta", meta, "--no-repo-dir", "topics", "--prune")
    pruned = json.loads(p.stdout)
    assert set(CLEAN_EXTRAS[:7]) <= set(pruned["remove"])
