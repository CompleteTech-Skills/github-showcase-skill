"""Footer upgrade preservation for partner and foreign images through `readme.upgrade` (issue 47, adjudication
t47-upgrade-preservation-adjudication.md and t47-source-trust-adjudication.md).

An unmarked footer whose <img> alt is exactly the company does not vouch for an arbitrary src. Partner images
(`assets/partner.png`), foreign hosts and look-alike hosts must survive `upgrade()`, and only the demonstrated own-site
legacy logos (the company website host derived from brand data, and the conventional local `docs/images/logo.svg`)
may migrate. These tests exercise the real path `RepoContext(brand, ...)` -> `readme.upgrade` -> `readme.preservation`.

Scope notes:
- The helper `unmarked` and the constants are copied locally from tests/test_footer_r6_regressions.py. No test module
  is imported from another test module.
- The write-flow test is intentionally absent. The only caller of `readme.preservation` on the write path is the
  gate in scripts/showcase.py (upgrade, then preservation) inside the full README command, which needs watching
  status, gate and ctx plumbing. No cheap public entry point exists, so no entry point was invented.
- At the owner head e58465e the partner, foreign and look-alike cases fail (`upgrade()` deletes them) and the
  `own_site=True` helper tests fail with TypeError until the readme.py fix lands. This file is a reproduction of that
  state and does not weaken any existing test.
"""
import copy

import pytest

from conftest import meta_dict
from ctshowcase import footer, readme
from ctshowcase.config import Brand
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

CREDIT = ('<sub>Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration'
          "</sub>")
OWN_SITE_HOST = "https://www.complete.tech"
DERIVED_HOST = "https://www.example-co.test"

NEGATIVE_SRCS = [
    "assets/partner.png",
    "https://example.test/assets/logo.png",
    "https://www.complete.tech.evil.test/wp-content/uploads/logo.png",
    "https://notcomplete.tech/logo.png",
]
POSITIVE_SRCS = [
    "https://www.complete.tech/wp-content/uploads/logo.png",
    "docs/images/logo.svg",
]


def unmarked(src, alt="CompleteTech LLC", href=OWN_SITE_HOST):
    return ('<p align="center"><a href="%s"><img src="%s" alt="%s" width="160"></a><br>%s</p>'
            % (href, src, alt, CREDIT.replace(OWN_SITE_HOST, href)))


def image_lines(text, src):
    return sum(1 for ln in text.splitlines() if src in ln)


@pytest.mark.parametrize("src", NEGATIVE_SRCS)
def test_company_alt_partner_or_foreign_image_is_kept_through_upgrade(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src))
    assert src in before and footer.block(brand) not in before
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if src in ln], f"{src} was reported as removed"
    assert image_lines(after, src) == image_lines(before, src)
    assert image_lines(after, src) >= 1
    assert readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("src", ["https://www.complete.tech/wp-content/uploads/logo.png"])
def test_wrong_alt_image_is_kept_through_upgrade(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src, alt="Partner"))
    assert src in before
    after, removed = readme.upgrade(ctx, before)
    assert not [ln for ln in removed if src in ln], f"{src} was reported as removed"
    assert image_lines(after, src) == image_lines(before, src)
    assert image_lines(after, src) >= 1
    assert readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("src", POSITIVE_SRCS)
def test_own_site_legacy_logo_still_migrates_through_upgrade(brand, tmp_path, src):
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(brand), unmarked(src))
    assert src in before
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1
    assert src not in after
    assert readme.preservation(before, after, removed) == []


def test_own_site_host_is_derived_from_brand_data(brand, tmp_path):
    raw = copy.deepcopy(brand.raw)
    raw["brand_strings"]["website"] = DERIVED_HOST
    raw["footer"]["href"] = DERIVED_HOST
    own = DERIVED_HOST + "/wp-content/uploads/logo.png"
    # the own-site logo is configured data (footer.legacy_logo_urls), never a path table in Python
    raw["footer"]["legacy_logo_urls"] = [u for u in raw["footer"]["legacy_logo_urls"] if "wp-content" not in u] + [own]
    derived = Brand(raw, brand.path)
    ctx = RepoContext(derived, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(footer.block(derived), unmarked(own, href=DERIVED_HOST))
    assert own in before
    after, removed = readme.upgrade(ctx, before)
    assert after.count("Built by") == 1 and own not in after
    assert readme.preservation(before, after, removed) == []
    # the previous public host is no longer this brand's own site, so its logo is kept as foreign
    foreign = OWN_SITE_HOST + "/wp-content/uploads/logo.png"
    before2 = readme.scaffold(ctx).replace(footer.block(derived), unmarked(foreign))
    after2, removed2 = readme.upgrade(ctx, before2)
    assert image_lines(after2, foreign) == image_lines(before2, foreign)
    assert image_lines(after2, foreign) >= 1
    assert not [ln for ln in removed2 if foreign in ln]


@pytest.mark.parametrize("src", NEGATIVE_SRCS)
def test_helper_rejects_non_own_site_images_with_own_site_flag(brand, src):
    block = unmarked(src)
    assert readme.is_footer_copy(block, brand, own_site=True) is False
    text = "# A\n\n" + block
    assert readme.drop_old_footer(text, brand, own_site=True) == (text, [])


def test_helper_wrong_alt_partner_is_rejected_with_own_site_flag(brand):
    block = unmarked(POSITIVE_SRCS[0], alt="Partner")
    assert readme.is_footer_copy(block, brand, own_site=True) is False
    text = "# A\n\n" + block
    assert readme.drop_old_footer(text, brand, own_site=True) == (text, [])


@pytest.mark.parametrize("src", POSITIVE_SRCS)
def test_helper_accepts_own_site_legacy_logos_with_own_site_flag(brand, src):
    assert readme.is_footer_copy(unmarked(src), brand, own_site=True) is True


def test_strict_default_drop_old_footer_keeps_company_alt_svg(brand):
    text = "# A\n\n" + unmarked("docs/images/logo.svg")
    assert readme.drop_old_footer(text, brand) == (text, [])


def _with_legacy(brand, legacy):
    raw = copy.deepcopy(brand.raw)
    if legacy is None:
        raw["footer"].pop("legacy_logo_urls", None)
    else:
        raw["footer"]["legacy_logo_urls"] = legacy
    return Brand(raw, brand.path)


def test_no_brand_logo_path_in_python_source():
    import pathlib
    src = pathlib.Path(readme.__file__).read_text(encoding="utf-8")
    assert "OWN_SITE_LOGO_PATHS" not in src and "wp-content" not in src


@pytest.mark.parametrize("url,expected", [
    ("https://www.complete.tech/wp-content/uploads/logo.png", True),
    ("https://WWW.Complete.Tech/wp-content/uploads/logo.png", True),
    ("https://www.complete.tech/wp-content/uploads/logo.png?ver=2", True),
    ("http://www.complete.tech/wp-content/uploads/logo.png", False),
    ("https://www.complete.tech/wp-content/uploads/team-photo.png", False),
    ("https://www.complete.tech.evil.test/wp-content/uploads/logo.png", False),
    ("https://user@www.complete.tech/wp-content/uploads/logo.png", False),
    ("https://www.complete.tech:8443/wp-content/uploads/logo.png", False),
    ("docs/images/logo.svg", True),
])
def test_own_site_logo_is_derived_from_legacy_logo_urls(brand, url, expected):
    assert readme._own_site_logo(url, brand) is expected


@pytest.mark.parametrize("legacy", [None, [], ["not a url", 7, None, {"a": 1}]])
def test_own_site_logo_without_usable_legacy_urls(brand, legacy):
    b = _with_legacy(brand, legacy)
    assert readme._own_site_logo("https://www.complete.tech/wp-content/uploads/logo.png", b) is False
    assert readme._own_site_logo("docs/images/logo.svg", b) is True


def test_own_site_logo_duplicate_legacy_entries(brand):
    url = "https://www.complete.tech/wp-content/uploads/logo.png"
    assert readme._own_site_logo(url, _with_legacy(brand, [url, url])) is True


def test_schema_accepts_website_legacy_logo_and_rejects_bad_entries(brand):
    from ctshowcase.config import schema_errors
    assert "https://www.complete.tech/wp-content/uploads/logo.png" in brand.raw["footer"]["legacy_logo_urls"]
    assert schema_errors(brand.raw) == []
    assert schema_errors(_with_legacy(brand, None).raw) == []  # omitted is valid
    url = brand.raw["footer"]["legacy_logo_urls"][0]
    assert schema_errors(_with_legacy(brand, [url, url]).raw) != []  # duplicates
    assert schema_errors(_with_legacy(brand, [7]).raw) != []  # invalid entry type
    assert schema_errors(_with_legacy(brand, ["http://www.complete.tech/logo.png"]).raw) != []  # not https



# ------------------------------------------------------------------ bootstrap write path (issue 47, r1 finding P1)
PARTNER_LIGHT = "https://example.test/partner-badge.png"


def edited_template_readme(footer_block):
    """A README whose template-body block was edited (marker hash does not match), followed by `footer_block`."""
    body = (readme.start("template-body") + "\n<!-- showcase:template-body:pristine sha256=" + "0" * 64 + " -->\n"
            + "Edited by a person.\n" + readme.end("template-body"))
    return "# New Thing\n\n" + body + "\n\n" + footer_block + "\n"


def run_bootstrap_write(tmp_path, text, name):
    import json

    from conftest import run_cli

    repo = tmp_path / name
    repo.mkdir()
    meta = tmp_path / (name + ".json")
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    (repo / "README.md").write_bytes(text.encode("utf-8"))
    p = run_cli("--meta", meta, "--repo-dir", repo, "--format", "json", "readme", "--bootstrap", "--write")
    return p, repo / "README.md"


def test_bootstrap_write_refuses_marked_footer_with_a_partner_image(brand, tmp_path):
    partner = footer.block(brand).replace(brand.raw["footer"]["logo_light_url"], PARTNER_LIGHT)
    assert PARTNER_LIGHT in partner
    text = edited_template_readme(partner)
    assert readme.bootstrap_state(text) == "edited"
    p, path = run_bootstrap_write(tmp_path, text, "partner")
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)  # CHECK_FAILED
    assert "readme-shrink" in p.stdout
    assert path.read_bytes() == text.encode("utf-8"), "a refused bootstrap write must leave README.md byte-identical"


def test_bootstrap_write_positive_control_plain_old_footer_still_falls_back(brand, tmp_path):
    old = footer.block(legacy_brand_urls(brand))
    text = edited_template_readme(old)
    assert readme.bootstrap_state(text) == "edited"
    p, path = run_bootstrap_write(tmp_path, text, "plain")
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    after = path.read_text(encoding="utf-8")
    assert "Edited by a person." in after and footer.check(brand, after)[0] == "pass"


def legacy_brand_urls(brand):
    raw = copy.deepcopy(brand.raw)
    legacy = "https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/"
    raw["footer"].update(logo_light_url=legacy + "logo.png", logo_dark_url=legacy + "logo-dark.png")
    return Brand(raw, brand.path)


# ------------------------------------------------------------------ G/H historical own-site sources (issue 47, r1 finding P2)
# The context construction below is copied locally from tests/test_footer_legacy_gh.py (no test module imports another).
GH_PARENT = {"full_name": "someone/upstream", "default_branch": "main"}
GH_VARIANTS = {"G": dict(fork=True, parent=GH_PARENT), "H": dict(repo="host-backup-20260914")}
GH_UPSTREAM = "# Upstream project\n\nAuthored upstream text, kept as written.\n\n## Usage\n\nRun it.\n"
WEBSITE_LOGO = "https://www.complete.tech/wp-content/uploads/logo.png"


def gh_ctx(brand, variant, tmp_path):
    ctx = RepoContext(brand, normalize(meta_dict(**GH_VARIANTS[variant])), tmp_path)
    assert ctx.det["variant"] == variant
    return ctx


@pytest.mark.parametrize("src", [WEBSITE_LOGO, "docs/images/logo.svg"], ids=["website-logo", "docs-svg"])
@pytest.mark.parametrize("variant", ["G", "H"])
def test_gh_unmarked_own_site_footer_migrates_to_one_compliant_footer(brand, tmp_path, variant, src):
    ctx = gh_ctx(brand, variant, tmp_path)
    before = GH_UPSTREAM + "\n" + unmarked(src) + "\n"
    assert footer.check(brand, before)[0] != "pass"
    after, removed = readme.upgrade(ctx, before)
    assert src not in after and after.count("Built by") == 1
    assert footer.check(brand, after)[0] == "pass"
    assert removed and readme.preservation(before, after, removed) == []
    assert GH_UPSTREAM.strip() in after
    again, _ = readme.upgrade(gh_ctx(brand, variant, tmp_path), after)
    assert again == after


@pytest.mark.parametrize("case", ["partner-file", "foreign-host", "look-alike-host", "other-domain", "wrong-alt"])
@pytest.mark.parametrize("variant", ["G", "H"])
def test_gh_unmarked_partner_or_foreign_footer_image_is_preserved(brand, tmp_path, variant, case):
    src, alt = {
        "partner-file": (NEGATIVE_SRCS[0], "CompleteTech LLC"),
        "foreign-host": (NEGATIVE_SRCS[1], "CompleteTech LLC"),
        "look-alike-host": (NEGATIVE_SRCS[2], "CompleteTech LLC"),
        "other-domain": (NEGATIVE_SRCS[3], "CompleteTech LLC"),
        "wrong-alt": (WEBSITE_LOGO, "Partner"),
    }[case]
    ctx = gh_ctx(brand, variant, tmp_path)
    before = GH_UPSTREAM + "\n" + unmarked(src, alt=alt) + "\n"
    after, removed = readme.upgrade(ctx, before)
    assert image_lines(after, src) == image_lines(before, src) >= 1
    assert not [ln for ln in removed if src in ln], f"{src} was reported as removed"
    assert readme.preservation(before, after, removed) == []


# ---------------------------------------------------------------- bootstrap write path (issue 47, r1 finding P1)
EDITED_BODY = (f"{readme.start('template-body')}\n<!-- showcase:template-body:pristine sha256={'0' * 64} -->\n"
               f"## About\n\nWritten by a person.\n{readme.end('template-body')}")


def legacy_brand_for(brand):
    raw = copy.deepcopy(brand.raw)
    base = "https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/"
    raw["footer"].update(logo_light_url=base + "logo.png", logo_dark_url=base + "logo-dark.png")
    return Brand(raw, brand.path)


def _bootstrap_cli(brand, tmp_path, footer_block):
    """Run the real `readme --bootstrap --write` on an edited template body whose marked footer is `footer_block`."""
    import json

    from conftest import run_cli

    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    text = readme.scaffold(ctx).replace(footer.block(brand), footer_block) + "\n" + EDITED_BODY + "\n"
    assert readme.bootstrap_state(text) == "edited"
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    path = tmp_path / "README.md"
    path.write_bytes(text.encode("utf-8"))
    return run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--bootstrap", "--write"), path, text


def test_bootstrap_write_refuses_to_regenerate_a_marked_footer_with_a_partner_image(brand, tmp_path):
    partner = footer.block(brand).replace(brand.raw["footer"]["logo_light_url"], "https://example.test/partner-badge.png")
    p, path, text = _bootstrap_cli(brand, tmp_path, partner)
    assert "https://example.test/partner-badge.png" in text
    assert p.returncode == 1, p.stdout + p.stderr  # CHECK_FAILED
    assert "readme-shrink" in p.stdout + p.stderr
    assert path.read_bytes() == text.encode("utf-8"), "a refused bootstrap write must leave README.md unchanged"


def test_bootstrap_write_fallback_still_works_for_a_plain_old_footer_copy(brand, tmp_path):
    p, path, text = _bootstrap_cli(brand, tmp_path, footer.block(legacy_brand_for(brand)))
    assert p.returncode == 0, p.stdout + p.stderr
    after = path.read_text(encoding="utf-8")
    assert "Written by a person." in after and "template-body:pristine" not in after
    assert after.count("Built by") == 1 and footer.check(brand, after)[0] == "pass"


# ---------------------------------------------------------------- G/H historical own-site sources (copied context)
PARENT = {"full_name": "someone/upstream", "default_branch": "main"}
UPSTREAM = "# Upstream project\n\nAuthored upstream text, kept as written.\n\n## Usage\n\nRun it.\n"
GH_VARIANTS = {"G": dict(fork=True, parent=PARENT), "H": dict(repo="host-backup-20260914")}


def gh_ctx(brand, variant, tmp_path):
    ctx = RepoContext(brand, normalize(meta_dict(**GH_VARIANTS[variant])), tmp_path)
    assert ctx.det["variant"] == variant
    return ctx


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("src", POSITIVE_SRCS, ids=["website-logo", "docs-svg"])
def test_gh_callout_only_migrates_an_unmarked_own_site_footer(brand, tmp_path, variant, src):
    before = UPSTREAM + "\n" + unmarked(src) + "\n"
    assert footer.check(brand, before)[0] != "pass"
    after, removed = readme.upgrade(gh_ctx(brand, variant, tmp_path), before)
    assert src not in after and after.count("Built by") == 1
    assert footer.check(brand, after)[0] == "pass"
    assert UPSTREAM.strip() in after
    assert readme.preservation(before, after, removed) == []


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("src", NEGATIVE_SRCS)
def test_gh_callout_only_keeps_partner_and_foreign_footer_images(brand, tmp_path, variant, src):
    before = UPSTREAM + "\n" + unmarked(src) + "\n"
    after, removed = readme.upgrade(gh_ctx(brand, variant, tmp_path), before)
    assert image_lines(after, src) == image_lines(before, src) >= 1
    assert not [ln for ln in removed if src in ln], "preservation must report no allowance for the partner image"
    assert readme.preservation(before, after, removed) == []
