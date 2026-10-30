"""E5/#89: topics merge is additive by default; `topics_extra` approves extras per org; `--prune` is the legacy removal.

Synthetic repositories and topics only."""
import copy
import sys

import pytest

from ctshowcase.config import Brand
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize
from ctshowcase.topics import merge
from conftest import meta_dict

OWNER = "Northwind-Trading-Co"


def _ctx(brand, extra=None, **kw):
    raw = copy.deepcopy(brand.raw)
    if extra is not None:
        raw["orgs"][OWNER] = dict(raw["orgs"].get(OWNER, {"family": "completetech", "tier": "T1", "display_name": OWNER}),
                                  topics_extra=extra)
    return RepoContext(Brand(raw, brand.path), normalize(meta_dict(**kw)), None)


def test_default_keeps_out_of_vocabulary_topic_and_logs(brand):
    r = merge(_ctx(brand, topics=["custom-topic"]))
    assert "custom-topic" in r["proposed"] and "custom-topic" not in r["remove"]
    assert "review-remove:custom-topic" in r["logs"]


def test_prune_restores_legacy_removal(brand):
    r = merge(_ctx(brand, topics=["custom-topic"]), prune=True)
    assert "custom-topic" not in r["proposed"] and "custom-topic" in r["remove"]
    assert not any(x.startswith("review-remove:") for x in r["logs"])


def test_extras_beyond_curated_limit_are_never_removed(brand):
    topics = ["custom-one", "custom-two", "custom-three", "custom-four", "custom-five", "custom-six", "custom-seven",
              "custom-eight", "custom-nine", "custom-ten", "custom-eleven", "custom-twelve"]
    r = merge(_ctx(brand, topics=topics))
    assert r["remove"] == [] and set(topics) <= set(r["proposed"]) and len(r["proposed"]) <= 20


def test_overflow_beyond_github_limit_is_held_not_removed(brand):
    topics = [f"custom-{i}" for i in range(20)]
    r = merge(_ctx(brand, topics=topics))
    assert len(r["proposed"]) <= 20
    held = [x for x in topics if x not in r["proposed"]]
    assert held and r["remove"] == []
    assert all(f"review-remove:{x}" in r["logs"] for x in held)
    # the topics PUT replaces the whole set, so held topics block it instead of being silently deleted
    assert r["held"] == held and "needs-input:topics-over-limit" in r["logs"]


def test_overflow_emits_no_record_or_gh_line(brand, monkeypatch, tmp_path):
    """showcase.py topics must not write a record/gh line whose PUT would delete held topics (reviewer A/B)."""
    import argparse
    import showcase
    ctx = _ctx(brand, topics=[f"custom-{i}" for i in range(20)])
    monkeypatch.setattr(showcase, "context", lambda a: ctx)
    monkeypatch.setattr(showcase, "gate_owner", lambda *a, **k: None)
    rec = tmp_path / "rec.json"
    args = argparse.Namespace(also_in=None, registry=None, prune=False, records=str(rec), gh=True)
    out, _ = showcase.cmd_topics(args)
    assert out["held"] and "gh" not in out and not rec.exists()


def test_vocabulary_topics_cut_by_caps_are_kept_silently(brand):
    """Reviewer A/B: in-vocabulary topics the domain/tech [:3] caps cut are clean; never in remove, no review log."""
    topics = ["python", "javascript", "typescript", "rust", "go", "finance", "trading", "ecommerce", "marketing", "sales"]
    r = merge(_ctx(brand, topics=topics))
    assert r["remove"] == [] and set(topics) <= set(r["proposed"])
    assert not any(x.startswith("review-remove:") for x in r["logs"])
    assert set(merge(_ctx(brand, topics=topics), prune=True)["remove"])  # legacy removal stays behind the flag


@pytest.mark.parametrize("kw", [{"fork": True, "parent": {"topics": ["python"]}}, {"repo": ".github"}])
def test_fork_and_profile_paths_are_additive(brand, kw):
    r = merge(_ctx(brand, topics=["custom-topic"], **kw))
    assert "custom-topic" in r["proposed"] and r["remove"] == []
    assert "review-remove:custom-topic" in r["logs"]


def test_topics_extra_keeps_without_log(brand):
    ctx = _ctx(brand, extra=["custom-topic"], topics=["custom-topic"])
    r = merge(ctx)
    assert "custom-topic" in r["proposed"] and r["remove"] == []
    assert not any(x.startswith("review-remove:") for x in r["logs"])
    assert "custom-topic" in merge(ctx, prune=True)["proposed"]  # approved topics survive the legacy flag too


def test_topics_extra_ignores_invalid_entries(brand):
    ctx = _ctx(brand, extra=["Bad Topic", "custom-topic\n", 5, "ok-topic"], topics=["custom-topic", "ok-topic"])
    r = merge(ctx)
    assert "review-remove:custom-topic" in r["logs"] and "review-remove:ok-topic" not in r["logs"]


def _r3(ctx):
    from ctshowcase import doctor
    r = doctor.row(ctx)
    return (r.get("cells") or r)["R3"]


def test_doctor_r3_cells(brand):
    d = {"description": "Invoice billing PDF email triage agent for Python."}
    base = merge(_ctx(brand, topics=[], **d))["proposed"]  # the required set for this synthetic repository
    assert _r3(_ctx(brand, topics=base, **d)) == "pass"
    assert _r3(_ctx(brand, topics=base + ["custom-topic"], **d)) == "warn"  # unreviewed extra reaches the doctor
    assert _r3(_ctx(brand, extra=["custom-topic"], topics=base + ["custom-topic"], **d)) == "pass"  # approved extra
    assert _r3(_ctx(brand, topics=["custom-topic"], **d)) == "fail"


def test_cli_prune_flag_is_wired(monkeypatch):
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import showcase
    import inspect
    src = inspect.getsource(showcase.cmd_topics)
    assert "prune=args.prune" in src
    # parser construction lives in main(); check the flag is declared
    assert '"--prune"' in inspect.getsource(showcase)


def test_approved_vocabulary_topics_cut_by_caps_are_not_duplicated(brand):
    """Reviewer A/B: a topics_extra entry that is also in the vocabulary and cut by the tech cap appeared twice."""
    topics = ["python", "javascript", "typescript", "rust", "go", "finance"]
    r = merge(_ctx(brand, extra=topics[:4], topics=topics))
    assert len(r["proposed"]) == len(set(r["proposed"])) and r["remove"] == []
    assert not any(x.startswith("review-remove:") for x in r["logs"])


def test_approved_topics_fill_all_twenty_slots_without_review_remove(brand):
    """Reviewer B: approved topics are never logged review-remove nor dropped; new generated topics are deferred."""
    topics = [f"custom-{i}" for i in range(20)]
    r = merge(_ctx(brand, extra=topics, topics=topics))
    assert set(topics) <= set(r["proposed"]) and len(r["proposed"]) == 20
    assert r["remove"] == [] and not any(x.startswith("review-remove:") for x in r["logs"])
    assert r["held"] and "needs-input:topics-over-limit" in r["logs"]  # the PUT stays blocked


def test_internal_repo_still_drops_private_banned_topics(brand):
    """Reviewer B: internal is non-public; the private-banned rule must apply to it as it did on base."""
    r = merge(_ctx(brand, topics=["nintendo"], visibility="internal"))
    assert "nintendo" not in r["proposed"]


def test_explicitly_excluded_family_topic_is_removed_not_kept(brand):
    """Reviewer A: family_topics_omit is explicit config, so an excluded family topic stays removable, as on base."""
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][OWNER] = dict(raw["orgs"].get(OWNER, {"family": "completetech", "tier": "T1", "display_name": OWNER}),
                              family_topics=["fam-x"], family_topics_omit={"support-triage-agent": ["fam-x"]})
    b = Brand(raw, brand.path)
    from ctshowcase import topics as tm
    old = tm.standard
    def std(name):
        d = dict(old(name))
        if name == "topics":
            d["family_topics"] = list(d["family_topics"]) + ["fam-x"]
        return d
    tm.standard = std
    try:
        r = merge(RepoContext(b, normalize(meta_dict(topics=["fam-x"])), None))
    finally:
        tm.standard = old
    assert "fam-x" in r["remove"] and "fam-x" not in r["proposed"]


def test_other_orgs_brand_topic_is_kept_but_logged_for_review(brand):
    """Reviewer A: an in-vocabulary topic the generator did not select (another org's brand topic) is not known to be
    accurate: kept, logged review-remove, so doctor R3 is not a silent pass."""
    d = {"description": "Invoice billing PDF email triage agent for Python."}
    base = merge(_ctx(brand, topics=[], **d))["proposed"]
    r = merge(_ctx(brand, topics=base + ["touchedbyanagent"], **d))
    assert r["remove"] == [] and "review-remove:touchedbyanagent" in r["logs"]
    assert _r3(_ctx(brand, topics=base + ["touchedbyanagent"], **d)) == "warn"


@pytest.mark.parametrize("approved", [False, True])
def test_forbidden_topic_is_never_kept_even_if_approved(brand, approved):
    """Reviewer B: topics.md forbids nsfw; neither the additive default nor topics_extra may preserve it."""
    r = merge(_ctx(brand, extra=["nsfw"] if approved else None, topics=["nsfw", "python"]))
    assert "nsfw" not in r["proposed"] and "nsfw" in r["remove"]
    assert not any(x.endswith(":nsfw") for x in r["logs"])


def test_deferred_required_topics_are_not_a_pass(brand):
    """Reviewer B: twenty approved topics defer the required ones (held); equal_as_set alone must not report pass."""
    topics = [f"custom-{i}" for i in range(20)]
    ctx = _ctx(brand, extra=topics, topics=topics)
    r = merge(ctx)
    assert r["equal_as_set"] and r["held"]
    assert _r3(ctx) == "fail"
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))
    import inspect
    import showcase
    assert 'not r["held"]' in inspect.getsource(showcase.cmd_topics)
