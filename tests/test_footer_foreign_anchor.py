"""Foreign-anchor footer guard (issue 47, adjudication t47-adjudication-footer-anchor-97b.md).

A footer-shaped block whose first anchor points at a foreign host is authored content, not a footer copy. It must not be
classified by `is_footer_copy`, must not be removed by `upgrade()` (never reported in `removed`), must make
`preservation()` report its loss, and must survive the `readme --mode upgrade` CLI dry run. Own-host forms (apex, www,
http, query drift) stay footer copies and their replaced line stays allowed.

The expectations depend on the readme.py change that makes `is_footer_copy` compare the parsed anchor href host with the
configured `footer.href` host. Until that change lands these tests fail; nothing here is skipped.

Fixtures are synthetic (Northwind, example.test) and use only the existing `brand` fixture and public helpers.
"""
import json
import shutil

import pytest

from conftest import EX, meta_dict, run_cli
from ctshowcase import footer, readme
from ctshowcase.context import RepoContext
from ctshowcase.meta import load_file, normalize

FOREIGN = [
    "https://partner.example.test/?ref=complete.tech",
    "https://complete.tech.evil.test/",
    "https://notcomplete.tech/",
    "https://partner.example.test/complete.tech",
    "https://user@www.complete.tech/",
]
OWN_FORMS = [
    "https://complete.tech",
    "http://www.complete.tech/",
    "https://www.complete.tech/?utm_source=x",
]


def with_href(brand, block, href):
    """`block` with its first anchor (the configured footer href, the first occurrence) pointing at `href`."""
    own = brand.raw["footer"]["href"]
    assert f'href="{own}"' in block
    return block.replace(f'href="{own}"', f'href="{href}"', 1)


def ctx_for(brand, tmp_path):
    return RepoContext(brand, normalize(meta_dict()), tmp_path)


def test_unmodified_footer_is_a_footer_copy(brand):
    assert readme.is_footer_copy(footer.markup(brand), brand) is True


@pytest.mark.parametrize("href", FOREIGN)
def test_foreign_first_anchor_is_not_a_footer_copy(brand, href):
    block = with_href(brand, footer.markup(brand), href)
    assert f'href="{href}"' in block
    assert readme.is_footer_copy(block, brand) is False


@pytest.mark.parametrize("href", FOREIGN)
def test_foreign_first_anchor_unmarked_trailing_block_is_left_unchanged(brand, href):
    text = "# A\n\n" + with_href(brand, footer.markup(brand), href)
    assert readme.drop_old_footer(text, brand, own_site=True) == (text, [])


@pytest.mark.parametrize("href", OWN_FORMS)
def test_own_host_drift_is_still_a_footer_copy(brand, href):
    assert readme.is_footer_copy(with_href(brand, footer.markup(brand), href), brand) is True


@pytest.mark.parametrize("marked", [True, False], ids=["marked", "unmarked"])
@pytest.mark.parametrize("href", FOREIGN)
def test_upgrade_keeps_foreign_first_anchor(brand, tmp_path, href, marked):
    ctx = ctx_for(brand, tmp_path)
    if marked:
        before = readme.scaffold(ctx).replace(footer.block(brand), with_href(brand, footer.block(brand), href))
    else:
        before = readme.scaffold(ctx).replace(footer.block(brand), with_href(brand, footer.markup(brand), href))
    assert f'href="{href}"' in before
    after, removed = readme.upgrade(ctx, before)
    assert f'href="{href}"' in after, "the authored foreign anchor was dropped from the upgraded text"
    assert not [ln for ln in removed if href in ln], f"foreign anchor {href} was reported as removed"
    assert readme.preservation(before, after, removed) == []
    # the guard is real: losing that authored line without a removal entry is reported as a lost line
    lost = "\n".join(ln for ln in after.splitlines() if href not in ln) + "\n"
    problems = readme.preservation(before, lost, removed)
    assert problems and any(href in p or "lost line" in p for p in problems), problems


@pytest.mark.parametrize("marked", [True, False], ids=["marked", "unmarked"])
@pytest.mark.parametrize("href", OWN_FORMS)
def test_own_host_drift_replaced_line_is_allowed(brand, tmp_path, href, marked):
    ctx = ctx_for(brand, tmp_path)
    if marked:
        before = readme.scaffold(ctx).replace(footer.block(brand), with_href(brand, footer.block(brand), href))
    else:
        before = readme.scaffold(ctx).replace(footer.block(brand), with_href(brand, footer.markup(brand), href))
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1
    assert any(f'href="{href}"' in ln for ln in removed), "the replaced own-host footer line is not allowed in removed"
    assert readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("href", FOREIGN)
def test_cli_dry_run_does_not_drop_foreign_anchor(brand, tmp_path, href):
    shutil.copytree(EX / "repos" / "northwind-support-triage-agent", tmp_path, dirs_exist_ok=True)
    meta = EX / "meta" / "northwind-support-triage-agent.json"
    ctx = RepoContext(brand, load_file(meta), tmp_path)
    text = readme.scaffold(ctx).replace(footer.block(brand), with_href(brand, footer.block(brand), href))
    assert f'href="{href}"' in text
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade")
    out = json.loads(p.stdout)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == text, "a dry run must never write the README"
    if p.returncode == 1:
        assert "readme-shrink" in out["logs"], out
    else:
        assert p.returncode == 0, p.stderr
        dropped = [ln for ln in out.get("diff", "").splitlines() if ln.startswith("-") and href in ln]
        assert dropped == [], f"exit 0 but the foreign anchor was dropped: {dropped}"
