"""The footer uses published masters and migrates the former broken asset paths."""
import copy

from conftest import ROOT, meta_dict
from ctshowcase import footer, readme
from ctshowcase.config import Brand
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize


PUBLIC = "https://raw.githubusercontent.com/CompleteTech-Skills/github-showcase-skill/main/assets/brand/"
LEGACY = "https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/"


def relocated(brand):
    raw = copy.deepcopy(brand.raw)
    raw["footer"].update(
        logo_light_url=PUBLIC + "logo.png",
        logo_dark_url=PUBLIC + "logo-dark.png",
        legacy_logo_urls=[LEGACY + "logo.png", LEGACY + "logo-dark.png"],
    )
    return Brand(raw, brand.path)


def old_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["footer"].update(logo_light_url=LEGACY + "logo.png", logo_dark_url=LEGACY + "logo-dark.png")
    return Brand(raw, brand.path)


def test_configured_footer_points_to_the_published_bundled_masters(brand):
    for key, filename in (("logo_light_url", "logo.png"), ("logo_dark_url", "logo-dark.png")):
        assert brand.raw["footer"][key] == PUBLIC + filename
        assert (ROOT / "assets" / "brand" / filename).is_file()
    seen = []

    def published(url):
        seen.append(url)
        return 200 if url.startswith(PUBLIC) else 404

    assert footer.online(brand, head=published)[0] == "pass"
    assert seen == [PUBLIC + "logo.png", PUBLIC + "logo-dark.png"]


def test_upgrade_replaces_marked_legacy_footer_without_shrink(brand, tmp_path):
    before_ctx = RepoContext(old_brand(brand), normalize(meta_dict()), tmp_path)
    after_ctx = RepoContext(relocated(brand), normalize(meta_dict()), tmp_path)
    before = readme.scaffold(before_ctx)
    after, removed = readme.upgrade(after_ctx, before)
    assert readme.preservation(before, after, removed) == []
    assert LEGACY not in after
    assert footer.check(after_ctx.brand, after)[0] == "pass"
    again, _ = readme.upgrade(after_ctx, after)
    assert again == after


def test_unmarked_legacy_footer_is_replaced_but_partner_credit_is_not(brand):
    current = relocated(brand)
    old = footer.markup(old_brand(brand))
    body, removed = readme.drop_old_footer("# Synthetic\n\n" + old + "\n", current)
    assert body == "# Synthetic\n"
    assert removed == [line for line in old.splitlines() if line.strip()]
    partner = old.replace(LEGACY + "logo.png", "https://example.test/partner.png").replace(
        'alt="CompleteTech LLC"', 'alt="Partner"'
    )
    assert not readme.is_footer_copy(partner, current)
    assert readme.drop_old_footer("# Synthetic\n\n" + partner, current)[1] == []


def test_legacy_url_matching_is_limited_to_configured_asset_files(brand):
    current = relocated(brand)
    assert readme._footer_logo_url(LEGACY + "logo.png", current)
    assert readme._footer_logo_url(LEGACY.replace("/main/", "/release/") + "logo-dark.png?v=2", current)
    assert not readme._footer_logo_url(LEGACY + "partner-logo.png", current)


def test_authored_content_inside_footer_markers_is_not_exempt(brand, tmp_path):
    current = relocated(brand)
    ctx = RepoContext(current, normalize(meta_dict()), tmp_path)
    before = readme.scaffold(ctx).replace(
        footer.END, "Authored partner acknowledgement.\n" + footer.END
    )
    after, removed = readme.upgrade(ctx, before)
    assert "Authored partner acknowledgement." not in removed
    assert any("Authored partner acknowledgement." in problem
               for problem in readme.preservation(before, after, removed))


def test_scheduled_workflow_really_heads_the_footer_logos():
    import re

    import yaml

    text = (ROOT / ".github" / "workflows" / "footer-assets.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    triggers = wf.get("on", wf.get(True))  # PyYAML reads the bare key `on` as True
    assert triggers["schedule"] and "cron" in triggers["schedule"][0]
    assert "workflow_dispatch" in triggers
    steps = [s for job in wf["jobs"].values() for s in job["steps"]]
    online = [s for s in steps if s.get("run", "").strip() == "python scripts/showcase.py footer --check README.md --online"]
    assert len(online) == 1
    assert "continue-on-error" not in online[0]
    assert not any("continue-on-error" in job for job in wf["jobs"].values())
    assert not re.search(r"\|\|\s*(true|:)", text)
