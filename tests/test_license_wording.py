"""Issue 36: License rows write a rights sentence only when the org row sets `license_wording` (synthetic owners only)."""
import pytest

from ctshowcase import readme
from ctshowcase.detect import standard

FACTUAL_MIT = "Code and documentation are licensed under the MIT License; see `LICENSE`."
FACTUAL_MIT_SKILLS = "Code, templates, and documentation are licensed under the MIT License. See `LICENSE` and `BRAND_ASSETS.md`."
RV = standard("readme-variants")["license_rows"]


def set_wording(ctx, value):
    """Give the resolved org row a holder value (a test double for a brand.yaml edit)."""
    ctx.org = dict(ctx.org, license_wording=value)


def test_unknown_owner_public_mit_gets_factual_line_only(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT)
    assert "needs-input:license-wording" in ctx.logs


def test_unknown_owner_public_mit_scaffold_has_no_reserved_names(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    out = readme.scaffold(ctx)
    assert "## License\n\n" + FACTUAL_MIT in out
    assert "reserved" not in out


def test_unknown_owner_mit_with_brand_assets_gets_factual_skills_line(make_ctx, tmp_path):
    (tmp_path / "BRAND_ASSETS.md").write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT_SKILLS)
    assert "needs-input:license-wording" in ctx.logs


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_whitespace_wording_counts_as_absent(make_ctx, tmp_path, blank):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license="MIT")
    set_wording(ctx, blank)
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT)


def test_t2_org_without_wording_does_not_use_display_name(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
    assert ctx.org["display_name"] == "LibreEvolve" and "license_wording" not in ctx.org
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT)


def test_completetech_mit_keeps_reserved_names_sentence(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license="MIT")
    assert readme.license_section(ctx) == ("License", RV["t1_mit"])
    assert "needs-input:license-wording" not in ctx.logs


def test_configured_t2_wording_substitutes_holder_not_display_name(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
    set_wording(ctx, "Example Steward Inc.")
    assert readme.license_section(ctx) == ("License", RV["t2_mit"].replace("<Brand>", "Example Steward Inc."))


def test_configured_skills_wording_substitutes_holder(make_ctx, tmp_path):
    (tmp_path / "BRAND_ASSETS.md").write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-Skills", repo="x-skill", license="MIT")
    set_wording(ctx, "Acme Holdings")
    assert readme.license_section(ctx) == ("License", RV["skills_mit"].replace("CompleteTech LLC", "Acme Holdings"))


def test_unknown_owner_other_license_gets_factual_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="Apache-2.0")
    assert readme.license_section(ctx) == ("License", "Licensed under the Apache-2.0; see `LICENSE`.")
    assert "needs-input:license-wording" in ctx.logs


def test_configured_other_license_keeps_reserved_names(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license="Apache-2.0")
    assert readme.license_section(ctx) == (
        "License", RV["other"].replace("<license>", "Apache-2.0").replace("<path>", "LICENSE").replace("<Brand>", "CompleteTech LLC"))


def test_configured_other_license_substitutes_holder(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="Apache-2.0")
    set_wording(ctx, "Example Steward Inc.")
    assert readme.license_section(ctx) == (
        "License", "Licensed under the Apache-2.0; see `LICENSE`. Example Steward Inc. names and logos are reserved and are "
                   "not licensed for reuse except to identify this project.")


def test_private_unknown_owner_has_no_copyright_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) is None
    assert "needs-input:license-wording" in ctx.logs
    out = readme.scaffold(ctx)
    assert "## License" not in out and "Copyright" not in out


def test_private_unknown_owner_with_license_still_takes_private_branch(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT", visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) is None
    assert "needs-input:license-wording" in ctx.logs


def test_private_completetech_keeps_copyright_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) == ("License", "Proprietary. Copyright (c) 2025 CompleteTech LLC. All rights reserved.")


def test_private_configured_holder_replaces_copyright_name(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    set_wording(ctx, "Example Steward Ltd")
    assert readme.license_section(ctx) == ("License", "Proprietary. Copyright (c) 2025 Example Steward Ltd. All rights reserved.")


def test_touchedbyanagent_private_without_wording_omits_hold_row(make_ctx, tmp_path):
    # the "Proprietary. All rights reserved." hold row is a reserved-rights sentence, so it needs wording too (issue 36)
    ctx = make_ctx(repo_dir=tmp_path, owner="TouchedByAnAgent", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) is None
    assert "needs-input:license-wording" in ctx.logs


def test_touchedbyanagent_private_with_wording_keeps_hold_row(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="TouchedByAnAgent", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    set_wording(ctx, "Example Steward Ltd")
    assert readme.license_section(ctx) == ("License", RV["private_hold"])


def _template():
    from conftest import ROOT
    return (ROOT / "tests" / "fixtures" / "template-README.md").read_text(encoding="utf-8")


def test_bootstrap_private_without_wording_removes_managed_license(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, owner="LibreEvolve", repo="new-thing", description="", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    out = readme.bootstrap(ctx, _template())
    assert "## License" not in out and "showcase:license" not in out.split("showcase:footer")[0].split("template-body:pristine")[-1][-200:]
    assert "needs-input:license-wording" in ctx.logs


def test_header_refresh_private_without_wording_removes_license_and_lints(make_ctx, tmp_path):
    from ctshowcase import readmelint
    kw = dict(owner="LibreEvolve", repo="thing", description="A thing.", license="MIT", visibility="private",
              created_at="2025-01-01T00:00:00Z")
    text = readme.scaffold(make_ctx(tmp_path, **kw))
    assert "## License" not in text
    # an older managed License paragraph from before the opt-in is removed on refresh, not preserved
    block = "## License\n\n<!-- showcase:license -->\nProprietary. Copyright (c) 2025 X. All rights reserved.\n\n"
    old = text.replace("<!-- showcase:footer:start -->", block + "<!-- showcase:footer:start -->", 1)
    ctx = make_ctx(tmp_path, **kw)
    refreshed = readme.header_only(ctx, old)
    assert "All rights reserved" not in refreshed and "## License" not in refreshed
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    res = readmelint.lint(make_ctx(tmp_path, **kw), tmp_path / "README.md")
    assert not any("License must be the last H2" in f for f in res["fails"])


def test_fork_upstream_path_still_returns_none(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing-fork", license="MIT")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "LICENSE").write_text("x", encoding="utf-8")
    assert readme.license_section(ctx) is None
    assert "needs-input:upstream" in ctx.logs


def test_security_agpl_row_unchanged_for_renamed_org(make_ctx, tmp_path):
    (tmp_path / "LICENSING.md").write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleTetech-Security", repo="x-check", license="AGPL-3.0")
    assert readme.license_section(ctx) == ("Licensing", RV["security"])


def test_renamed_org_inherits_wording_for_private_copyright(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleTetech-Security", repo="x-check", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert ctx.org["known"] and ctx.org["owner"] == "CompleteTech-Security"
    assert readme.license_section(ctx) == ("License", "Proprietary. Copyright (c) 2025 CompleteTech LLC. All rights reserved.")


def test_unknown_owner_has_no_key_so_no_claim(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Nobody-Here", repo="thing", license="MIT")
    assert not ctx.org["known"] and "license_wording" not in ctx.org
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT)


def test_wording_log_is_recorded_once_per_context(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    readme.license_section(ctx)
    readme.license_section(ctx)
    assert ctx.logs.count("needs-input:license-wording") == 1


# --- review round: upgrade must never delete authored License text, and must gate managed sections (issue 36) ---
AUTHORED = "Internal use only by the Example team; contact the owners before sharing."


def _readme_with_license(body):
    return f"# thing\n\nA thing.\n\n## Usage\n\nRun it.\n\n## License\n\n{body}\n"


def test_upgrade_private_no_wording_keeps_authored_license_section(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    text = _readme_with_license(AUTHORED)
    out, removed = readme.upgrade(ctx, text)
    assert AUTHORED in out and AUTHORED not in removed
    assert readme.preservation(text, out, removed) == []
    assert "needs-input:license-wording" in ctx.logs


def test_upgrade_private_no_wording_drops_only_generated_license_text(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    out, _ = readme.upgrade(ctx, _readme_with_license("Proprietary. Copyright (c) 2025 X. All rights reserved."))
    assert "All rights reserved" not in out and "## License" not in out


def test_upgrade_public_managed_rights_sentence_becomes_factual_line(make_ctx, tmp_path):
    managed = "<!-- showcase:license -->\n" + RV["t1_mit"]
    text = _readme_with_license(managed)
    for preserve in (False, True):
        c = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
        if preserve:
            c.org = dict(c.org, readme_preserve=["thing"])
        out, removed = readme.upgrade(c, text)
        assert FACTUAL_MIT in out and "reserved" not in out
        assert "needs-input:license-wording" in c.logs
