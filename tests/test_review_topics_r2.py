"""Review round 2, topics: an approved org rename must not change a repository's required topics (CQ-03).

Review 4373814830: the CVE-check vendor exemption (step 2) and the vendor-first domain ranking (§5.9) compared the owner
with the bare old login `CompleTetech-Security`, so after the approved `org-001` rename to `CompleteTech-Security` the
same repository lost its vendor topic. Same pattern: the TouchedByAnAgent domain vocabulary. Synthetic repository names
and approvals; public org logins only."""
import pytest

from ctshowcase import resolver as R
from ctshowcase.config import Brand
from ctshowcase.topics import merge

OLD, NEW = "CompleTetech-Security", "CompleteTech-Security"
CVE_REPO = "northwind-cve-2026-40404-check"
CVE_DESC = "Check Northwind gateway versions for CVE-2026-40404, offline and dependency-free."


def _approvals(rows):
    return {"rows": set(rows), "ids": set(), "answers": {}, "actions": [], "extra": []}


@pytest.fixture
def renamed_ctx(brand):
    """make_ctx over a Brand whose shared resolver carries the given approved org-rename rows."""
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    from conftest import meta_dict

    def _make(rows, **kw):
        b = Brand(brand.raw, brand.path)
        b._resolver = R.Resolver(b, {}, _approvals(rows))
        return RepoContext(b, normalize(meta_dict(**kw)), None)
    return _make


SEC_RENAME = [("org-rename", OLD, "*", NEW)]


@pytest.mark.parametrize("owner", [OLD, NEW])
def test_cve_vendor_topic_survives_approved_rename(renamed_ctx, owner):
    ctx = renamed_ctx(SEC_RENAME, owner=owner, repo=CVE_REPO, description=CVE_DESC,
                      topics=["completetech", "security", "cve", "security-check", "northwind", "python"])
    r = merge(ctx)
    assert r["proposed"] == ["completetech", "security", "cve", "security-check", "northwind", "python"]
    assert r["remove"] == [] and r["equal_as_set"]
    assert "needs-input:domain-topic" not in r["logs"] and "topics-short" not in r["logs"]


def test_cve_vendor_topic_is_proposed_under_new_login(renamed_ctx):
    old = merge(renamed_ctx(SEC_RENAME, owner=OLD, repo=CVE_REPO, description=CVE_DESC, topics=[]))
    new = merge(renamed_ctx(SEC_RENAME, owner=NEW, repo=CVE_REPO, description=CVE_DESC, topics=[]))
    assert old["proposed"] == new["proposed"] == ["completetech", "security", "cve", "security-check", "northwind", "python"]
    assert old["logs"] == new["logs"]


def test_vendor_rule_stays_scoped_to_the_security_org(renamed_ctx):
    ctx = renamed_ctx(SEC_RENAME, owner="Northwind-Trading-Co", repo=CVE_REPO, description=CVE_DESC,
                      topics=["northwind"])
    p = merge(ctx)["proposed"]
    assert "northwind" not in p


def test_touchedbyanagent_domain_vocab_follows_the_resolver(renamed_ctx):
    desc = "Invoice wearables over BLE for the smart ring."
    rows = [("org-rename", "TouchedByAnAgent", "*", "Northwind-Agents")]
    base = merge(renamed_ctx([], owner="TouchedByAnAgent", repo="ring-sync", description=desc))
    assert "invoice" not in base["proposed"]
    for owner in ("touchedbyanagent", "Northwind-Agents"):
        ctx = renamed_ctx(rows, owner=owner, repo="ring-sync", description=desc)
        assert merge(ctx)["proposed"] == base["proposed"], owner
