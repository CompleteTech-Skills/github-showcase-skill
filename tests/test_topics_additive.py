"""E5/#89: topics merge is additive by default; `topics_extra` approves extras per org; `--prune` is the legacy removal.

Synthetic repositories and topics only."""
import copy
import json
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
    ns = showcase.argparse.ArgumentParser  # parser construction lives in main(); check the flag is declared
    assert '"--prune"' in inspect.getsource(showcase)
