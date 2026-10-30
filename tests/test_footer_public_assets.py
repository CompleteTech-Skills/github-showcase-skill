"""The footer uses published masters and migrates the former broken asset paths."""
import copy
import json

import pytest

from conftest import ROOT, meta_dict, run_cli
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


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("marked", [True, False])
def test_callout_upgrade_migrates_legacy_footer(brand, tmp_path, variant, marked):
    metadata = meta_dict(owner="CompleteTech-Skills", fork=variant == "G", archived=variant == "H",
                         parent={"full_name": "Upstream-Synth/tool", "default_branch": "main"}, ahead_by=0)
    ctx = RepoContext(relocated(brand), normalize(metadata), tmp_path)
    ctx.det["variant"] = variant
    old = footer.block(old_brand(brand)) if marked else footer.markup(old_brand(brand))
    before = "# Synthetic upstream\n\nAuthored upstream instructions.\n\n" + old + "\n"
    after, removed = readme.upgrade(ctx, before)
    assert readme.preservation(before, after, removed) == []
    assert LEGACY not in after
    assert "Authored upstream instructions." in after
    assert footer.check(ctx.brand, after)[0] == "pass"
    assert readme.upgrade(ctx, after)[0] == after

    (tmp_path / "README.md").write_text(before, encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(metadata), encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--variant", variant, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    written = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert LEGACY not in written
    assert footer.check(ctx.brand, written)[0] == "pass"
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--variant", variant, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == written


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("marked", [True, False])
def test_callout_upgrade_preserves_authored_footer_content(brand, tmp_path, variant, marked):
    ctx = RepoContext(relocated(brand), normalize(meta_dict()), tmp_path)
    ctx.det["variant"] = variant
    content = footer.markup(old_brand(brand)).replace("</p>", "Authored partner acknowledgement.\n</p>")
    old = readme.wrap("footer", content) if marked else content
    before = "# Synthetic upstream\n\nAuthored instructions.\n\n" + old + "\n"
    after, removed = readme.upgrade(ctx, before)
    assert old in after
    assert readme.preservation(before, after, removed) == []
    assert LEGACY in after


def test_watching_fork_keeps_legacy_footer_exemption(brand, tmp_path):
    metadata = meta_dict(owner="romgenie-following-repos", fork=True,
                         parent={"full_name": "Upstream-Synth/tool"}, ahead_by=0)
    ctx = RepoContext(relocated(brand), normalize(metadata), tmp_path)
    before = "# Upstream\n\nOriginal instructions.\n\n" + footer.block(old_brand(brand)) + "\n"
    after, removed = readme.upgrade(ctx, before)
    assert LEGACY in after
    assert not removed
    path = tmp_path / "README.md"
    path.write_text(before, encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(metadata), encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["result"] == "exempt"
    assert path.read_text(encoding="utf-8") == before
