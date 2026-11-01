"""Footer anchors must target the configured footer host (issue 47, t47-adjudication-footer-anchor-97b.md).

`is_footer_copy` once accepted any `<a>` whose attributes contained the substring complete.tech, so a foreign link such
as https://partner.example.test/?ref=complete.tech was treated as footer copy, exempted from the never-drop-a-line
check by `upgrade()` and silently deleted. Only a link whose href host equals the host of the brand `footer.href` (no
suffix, userinfo, port or attribute-substring match) is footer copy. The real brand href stays a valid control.
"""
import json

import pytest

from conftest import EX, meta_dict, run_cli
from ctshowcase import footer, readme
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

REAL = "https://www.complete.tech"
FOREIGN_ANCHORS = [
    'href="https://partner.example.test/?ref=complete.tech"',
    'href="https://complete.tech.evil.test/"',
    'href="https://notcomplete.tech/"',
    'href="https://www.complete.tech.evil.test/x"',
    'href="https://partner.test/#complete.tech"',
    'href="https://partner.test/" title="complete.tech"',
    'title="https://www.complete.tech" href="https://partner.test/"',
    'href="https://www.complete.tech@evil.test/"',
    'href="https://user@www.complete.tech/"',
    'href="https://www.complete.tech:8443/"',
    'href="ftp://www.complete.tech/"',
    'data-x="href=https://www.complete.tech" href="https://partner.test/"',
    'data-x="a" href="https://partner.test/?ref=complete.tech"',
]
REAL_ANCHORS = [
    'href="https://www.complete.tech"',
    'href="https://www.complete.tech/"',
    'href="https://COMPLETE.TECH/about?x=1#y"',
    "href='https://Complete.Tech'",
    "href=https://www.complete.tech/",
    'class="x" href="https://complete.tech/"',
]


def block(attrs):
    return ('<p align="center"><sub>Built by <a %s>CompleteTech LLC</a> · Innovation at Every Integration</sub></p>'
            % attrs)


def marked_with(brand, attrs):
    """The current marked footer with its first anchor replaced (so the marker block holds the foreign link)."""
    cur = footer.block(brand)
    assert 'href="%s"' % REAL in cur
    return cur.replace('href="%s"' % REAL, attrs, 1)


@pytest.mark.parametrize("attrs", FOREIGN_ANCHORS)
def test_foreign_anchor_is_not_footer_copy(brand, attrs):
    assert not readme.is_footer_copy(block(attrs), brand)


@pytest.mark.parametrize("attrs", REAL_ANCHORS)
def test_configured_host_anchor_is_footer_copy(brand, attrs):
    assert readme.is_footer_copy(block(attrs), brand)


@pytest.mark.parametrize("attrs", FOREIGN_ANCHORS)
def test_upgrade_and_preservation_keep_foreign_anchor_in_unmarked_footer(brand, tmp_path, attrs):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), block(attrs))
    assert attrs in before
    after, removed = readme.upgrade(ctx, before)
    assert attrs in after
    assert not [ln for ln in removed if attrs in ln]
    assert readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("attrs", FOREIGN_ANCHORS[:3])
def test_foreign_anchor_in_a_marked_footer_is_not_exempted_from_preservation(brand, tmp_path, attrs):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), marked_with(brand, attrs))
    assert attrs in before
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if attrs in ln], removed
    if attrs not in after:  # the replacement is only allowed when preservation then refuses it
        assert readme.preservation(before, after, removed), "foreign link dropped without a readme-shrink"


def test_cli_rejects_marked_footer_with_a_foreign_anchor_instead_of_dropping_it(brand, tmp_path):
    attrs = 'href="https://partner.example.test/?ref=complete.tech"'
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    text = readme.scaffold(ctx).replace(footer.block(brand), marked_with(brand, attrs))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(text, encoding="utf-8", newline="\n")
    p = run_cli("--meta", EX / "meta" / "northwind-support-triage-agent.json", "--repo-dir", repo, "--format", "json",
                "readme", "--mode", "upgrade")
    out = json.loads(p.stdout)
    assert p.returncode != 0 and "readme-shrink" in out["logs"], (p.returncode, out)
    assert (repo / "README.md").read_text(encoding="utf-8") == text


def test_real_brand_anchor_in_a_drifted_footer_is_still_replaced(brand, tmp_path):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    old = block('href="https://complete.tech"')
    before = readme.scaffold(ctx).replace(footer.block(brand), old)
    after, removed = readme.upgrade(ctx, before)
    assert footer.block(brand) in after
    assert readme.preservation(before, after, removed) == []
