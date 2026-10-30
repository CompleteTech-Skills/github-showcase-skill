"""Issue 36: License rows write a rights sentence only when the org row sets `license_wording` (synthetic owners only).

The gating itself landed in a192d1f (issue 36), which is already in the base 6dbeef6. This file is therefore a
characterization suite: all 40 tests pass on base by design, and they cannot be red on base without a source change,
which task 39 (test-only) does not make.

Red evidence is taken from the pre-gating tree, reproduced for the t#39 review: `git archive 2be04ac` with this file
and tests/test_readme_scaffold.py copied in gives 26 failed and 14 passed for this file. The 26 failures are every
no-holder, factual-line, blank-wording, holder-substitution and schema-acceptance case. The 14 passes pin unchanged
CompleteTech, CompleteTech-Security, fork and private-holder output, which is the regression they guard against.
"""
import copy

import pytest

from ctshowcase import readme
from ctshowcase.config import Brand, schema_errors
from ctshowcase.context import RepoContext
from ctshowcase.detect import standard
from ctshowcase.meta import normalize

from conftest import meta_dict

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


def test_touchedbyanagent_private_hold_unchanged_without_wording(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="TouchedByAnAgent", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    set_wording(ctx, "")
    assert readme.license_section(ctx) == ("License", RV["private_hold"])


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


# ------------------------------------------------------------------------------------------------
# Spec E2.1.3: synthetic owners and a brand copy with a test-only license_wording holder
# ------------------------------------------------------------------------------------------------
NO_CLAIM_WORDS = ("reserved", "names and logos", "Copyright", "rights")


def brand_copy(brand, mutate):
    """A copy of the loaded brand with `mutate(raw)` applied; the real references/brand.yaml is never edited."""
    raw = copy.deepcopy(brand.raw)
    mutate(raw)
    return Brand(raw, brand.path)


def wording_brand(brand, owner, value):
    return brand_copy(brand, lambda raw: raw["orgs"][owner].__setitem__("license_wording", value))


def ctx_for(b, repo_dir, **kw):
    return RepoContext(b, normalize(meta_dict(**kw)), repo_dir)


def test_org_without_wording_gets_no_claim_public_mit(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Pick-Your-AI", repo="thing", license="MIT")
    result = readme.license_section(ctx)
    assert result == ("License", "Code and documentation are licensed under the MIT License; see `LICENSE`.")
    assert not any(word in result[1] for word in NO_CLAIM_WORDS)
    assert "needs-input:license-wording" in ctx.logs


def test_org_without_wording_gets_no_claim_other_license(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="Apache-2.0")
    result = readme.license_section(ctx)
    assert result == ("License", "Licensed under the Apache-2.0; see `LICENSE`.")
    assert not any(word in result[1] for word in NO_CLAIM_WORDS)
    assert "needs-input:license-wording" in ctx.logs


def test_org_without_wording_skills_mit_keeps_factual_brand_assets_pointer(make_ctx, tmp_path):
    (tmp_path / "BRAND_ASSETS.md").write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner="AI-Ascension", repo="thing", license="MIT")
    result = readme.license_section(ctx)
    assert result == ("License", "Code, templates, and documentation are licensed under the MIT License. "
                                 "See `LICENSE` and `BRAND_ASSETS.md`.")
    assert "reserved" not in result[1]


def test_private_repo_without_wording_gets_no_copyright_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Pick-Your-AI", repo="thing", visibility="private", license=None,
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) is None
    assert "needs-input:license-wording" in ctx.logs
    out = readme.scaffold(ctx)
    assert "Copyright" not in out and "## License" not in out


def test_private_repo_with_wording_gets_copyright_line(brand, tmp_path):
    b = wording_brand(brand, "Pick-Your-AI", "Example Holder LLC")
    ctx = ctx_for(b, tmp_path, owner="Pick-Your-AI", repo="thing", visibility="private", license=None,
                  created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) == ("License", "Proprietary. Copyright (c) 2025 Example Holder LLC. All rights reserved.")


def test_public_mit_with_wording_names_the_configured_holder(brand, tmp_path):
    b = wording_brand(brand, "Pick-Your-AI", "Example Holder LLC")
    ctx = ctx_for(b, tmp_path, owner="Pick-Your-AI", repo="thing", license="MIT")
    result = readme.license_section(ctx)
    assert result == ("License", "Code and documentation are licensed under the MIT License; see `LICENSE`. "
                                 "Example Holder LLC names and logos are reserved and are not licensed for reuse except to "
                                 "identify this project.")
    assert "Pick Your AI" not in result[1]
    assert "needs-input:license-wording" not in ctx.logs


def test_blank_wording_counts_as_absent(brand, tmp_path):
    b = wording_brand(brand, "Pick-Your-AI", "   ")
    ctx = ctx_for(b, tmp_path, owner="Pick-Your-AI", repo="thing", license="MIT")
    assert readme.license_section(ctx) == ("License", "Code and documentation are licensed under the MIT License; see `LICENSE`.")
    assert "needs-input:license-wording" in ctx.logs


@pytest.mark.parametrize("owner,files,heading,row", [
    ("CompleteTech-LLC", (), "License", "t1_mit"),
    # base behaviour: CompleteTech-Security is the F (security) layout, so even a public MIT repo takes the security row
    ("CompleteTech-Security", (), "Licensing", "security"),
    ("CompleteTech-Skills", ("BRAND_ASSETS.md",), "License", "skills_mit"),
])
def test_completetech_output_unchanged(make_ctx, tmp_path, owner, files, heading, row):
    for name in files:
        (tmp_path / name).write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner=owner, repo="thing", license="MIT")
    assert readme.license_section(ctx) == (heading, RV[row])
    assert "needs-input:license-wording" not in ctx.logs


@pytest.mark.parametrize("owner", [
    "CompleteTech-LLC",
    # deliberate former slug, not a typo: references/brand.yaml lists `former_slugs: [CompleTetech-Security]` on the
    # CompleteTech-Security row, and the resolver (CQ-03) must keep renamed orgs resolving to the same row
    "CompleTetech-Security",
])
def test_completetech_private_output_unchanged(make_ctx, tmp_path, owner):
    ctx = make_ctx(repo_dir=tmp_path, owner=owner, repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) == ("License", RV["private"].replace("<year>", "2025"))


def test_security_agpl_row_unchanged_without_wording(brand, tmp_path):
    b = brand_copy(brand, lambda raw: raw["orgs"]["CompleteTech-Security"].pop("license_wording"))
    ctx = ctx_for(b, tmp_path, owner="CompleteTech-Security", repo="thing", license="AGPL-3.0")
    assert readme.license_section(ctx) == ("Licensing", RV["security"])


@pytest.mark.parametrize("value,accepted", [("Example Holder LLC", True), ("", False), (123, False)])
def test_schema_accepts_and_rejects_license_wording(brand, value, accepted):
    # schema_errors is the repository's own validator (the same entry point test_config.py uses); no new dependency
    raw = copy.deepcopy(brand.raw)
    raw["orgs"]["Pick-Your-AI"]["license_wording"] = value
    errors = schema_errors(raw)
    assert (errors == []) is accepted
    if not accepted:
        assert any("license_wording" in e for e in errors)


def test_brand_yaml_sets_wording_only_on_completetech_t1_rows(brand):
    orgs = brand.raw["orgs"]
    for name, row in orgs.items():
        if "license_wording" in row:
            assert row["family"] == "completetech", name
            assert row["tier"] in ("T1", "T1-user"), name
            assert row["license_wording"] == "CompleteTech LLC", name
    for name in ("Pick-Your-AI", "LibreEvolve", "AI-Ascension", "TouchedByAnAgent"):
        assert "license_wording" not in orgs[name], name
