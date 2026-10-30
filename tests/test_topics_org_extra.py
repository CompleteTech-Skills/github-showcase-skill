"""Org-approved topics (`topics_extra`, task 92). Synthetic Northwind data only."""
from ctshowcase import doctor
from ctshowcase.topics import _org_extra, merge

APPROVED = "acme-widget"


def _ctx(make_ctx, extra=None, **kw):
    kw.setdefault("owner", "Northwind-Trading-Co")
    kw.setdefault("repo", "support-triage-agent")
    kw.setdefault("description", "Run the Northwind triage agent.")
    ctx = make_ctx(**kw)
    ctx.org = dict(ctx.org)
    if extra is not None:
        ctx.org["topics_extra"] = extra
    return ctx


def test_org_extra_keeps_only_valid_lowercase_strings(make_ctx):
    ctx = _ctx(make_ctx, extra=[None, 7, "Bad Case", "two words", "a" * 51, "", APPROVED, "Acme-Gadget"])
    assert _org_extra(ctx) == {APPROVED, "acme-gadget"}


def test_org_extra_absent_key_is_empty(make_ctx):
    assert _org_extra(_ctx(make_ctx)) == set()


def test_org_extra_non_list_is_ignored(make_ctx):
    assert _org_extra(_ctx(make_ctx, extra="acme-widget")) == set()


def test_approved_topic_is_not_review_removed(make_ctx):
    ctx = _ctx(make_ctx, extra=[APPROVED], topics=[APPROVED])
    r = merge(ctx)
    assert APPROVED in r["proposed"]
    assert f"review-remove:{APPROVED}" not in r["logs"]


def test_unapproved_extra_still_review_removed(make_ctx):
    ctx = _ctx(make_ctx, extra=[APPROVED], topics=["zeta-tool"])
    r = merge(ctx)
    assert "zeta-tool" in r["proposed"]
    assert "review-remove:zeta-tool" in r["logs"]


def test_approved_topic_takes_tech_slot_ahead_of_extras(make_ctx):
    ctx = _ctx(make_ctx, extra=[APPROVED], topics=["zeta-tool", APPROVED], language="Python")
    p = merge(ctx)["proposed"]
    assert p.index(APPROVED) < p.index("zeta-tool")


def test_approved_topic_beyond_tech_cap_is_kept_without_log(make_ctx):
    extra = ["acme-one", "acme-two", "acme-three"]
    ctx = _ctx(make_ctx, extra=extra, topics=extra, language="Python")
    r = merge(ctx)
    for x in extra:
        assert x in r["proposed"]
        assert f"review-remove:{x}" not in r["logs"]


def test_approved_topic_not_on_repo_is_not_invented(make_ctx):
    ctx = _ctx(make_ctx, extra=[APPROVED], topics=[])
    assert APPROVED not in merge(ctx)["proposed"]


def test_hard_drops_are_not_overridden(make_ctx):
    # noise, owner name, type mismatch and private-banned all drop before the vocabulary check
    ctx = _ctx(make_ctx, extra=["wip", "northwind-trading-co-tools", "game", "pokemon"],
               topics=["wip", "northwind-trading-co-tools", "game", "pokemon"], visibility="private")
    p = merge(ctx)["proposed"]
    for x in ("wip", "northwind-trading-co-tools", "game", "pokemon"):
        assert x not in p


def test_doctor_row_carries_review_remove_logs_and_r3_stays_pass(make_ctx):
    base = merge(_ctx(make_ctx, topics=["completetech", "python", "ai", "llm", "rag"], language="Python"))["proposed"]
    assert len(base) >= 5  # the repo already carries its proposal, so R3 is decided by the review-remove extra alone
    ctx = _ctx(make_ctx, topics=base + ["zeta-tool"], language="Python")
    r = doctor.row(ctx)
    assert "review-remove:zeta-tool" in r["logs"]
    assert r["cells"]["R3"] == "pass"
