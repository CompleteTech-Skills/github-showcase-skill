"""Explicit legal wording and fail-closed brand identity regressions (#36, #40)."""
import copy
import json

import pytest

from conftest import run_cli
from ctshowcase import readme
from ctshowcase.config import Brand
from ctshowcase.context import RepoContext
from ctshowcase.errors import NeedsInput
from ctshowcase.meta import normalize


def context(brand, owner, **meta):
    return RepoContext(brand, normalize({"owner": owner, "repo": "sample-tool", "license": "MIT",
        "description": "Inspect synthetic records.", "visibility": "public", "files": [], **meta}))


@pytest.mark.parametrize("owner", ["LibreEvolve", "AI-Ascension", "Jev-Engineering", "Pick-Your-AI"])
def test_missing_wording_is_not_inferred_from_brand(brand, owner):
    ctx = context(brand, owner)
    _, body = readme.license_section(ctx)
    assert body == "Code and documentation are licensed under the MIT License; see `LICENSE`."
    assert "needs-input:license-wording" in ctx.logs
    private = context(brand, owner, visibility="private", created_at="2024-02-01T00:00:00Z")
    assert readme.license_section(private) is None
    assert "needs-input:license-wording" in private.logs


def test_legal_wording_is_exact_and_org_scoped(brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"]["LibreEvolve"]["license_wording"] = "An explicit synthetic rights statement."
    raw["orgs"]["LibreEvolve"]["private_license_wording"] = "Synthetic private terms, <year>."
    configured = Brand(raw, brand.path)
    assert readme.license_section(context(configured, "LibreEvolve"))[1].endswith("An explicit synthetic rights statement.")
    assert readme.license_section(context(configured, "LibreEvolve", visibility="private", created_at="2024-01-01"))[1] == "Synthetic private terms, 2024."
    assert "explicit synthetic" not in readme.license_section(context(configured, "Jev-Engineering"))[1]


def test_complete_tech_existing_wording_is_explicit(brand):
    ctx = context(brand, "CompleteTech-LLC")
    assert readme.license_section(ctx)[1].endswith(brand.org(ctx.owner)["license_wording"])
    private = context(brand, "CompleteTech-LLC", visibility="private", created_at="2024-01-01")
    assert readme.license_section(private)[1] == "Proprietary. Copyright (c) 2024 CompleteTech LLC. All rights reserved."


def test_all_non_complete_tech_rows_have_independent_families(brand):
    # CompleteDotTech is the owner's profile and Northwind is the documented
    # fictional CompleteTech demo. Neither is a third-party brand.
    for owner, org in brand.raw["orgs"].items():
        if owner in ("CompleteDotTech", "Northwind-Trading-Co") or org["display_name"].startswith("CompleteTech"):
            continue
        assert org["family"] != "completetech", owner


def test_unconfigured_ticketstub_identity_never_inherits_palette(brand, tmp_path):
    with pytest.raises(NeedsInput, match="owner-supplied palette and mark"):
        brand.family("ticketstub")
    m = tmp_path / "meta.json"
    m.write_text(json.dumps({"owner": "Jevelopers-neatHack-2026", "repo": "sample", "visibility": "public",
                             "description": "Inspect synthetic records."}), encoding="utf-8")
    p = run_cli("--meta", m, "--no-repo-dir", "banner", "--out", tmp_path / "banner.png", "--allow-unmeasured")
    assert p.returncode == 2  # Missing consent still takes precedence.
    assert not (tmp_path / "banner.png").exists()


@pytest.mark.parametrize("owner", ["AI-Ascension", "Jev-Engineering", "jevplay-games", "LibreEvolve", "TouchedByAnAgent",
                                    "romgenie-following-repos", "romgenie-archive-repostiory", "Pick-Your-AI"])
def test_non_complete_tech_header_uses_family_badge_colours(brand, owner):
    ctx = context(brand, owner, language="Python")
    header = readme.header(ctx)
    assert "005ADD" not in header.upper()
    # The configured decision 18 footer is separate from the header.
    assert "completetech" not in header.lower()
    assert "completedottech" not in header.lower()



def test_each_org_row_keeps_its_identity_across_surfaces(brand, tmp_path):
    """Exercise real CLI paths for every configured row, including refusal rows."""
    import re
    from ctshowcase import readmelint

    for owner, row in brand.raw["orgs"].items():
        directory = tmp_path / owner
        directory.mkdir()
        meta = directory / "meta.json"
        meta.write_text(json.dumps({"owner": owner, "repo": "synthetic-agent",
            "description": "Inspect synthetic records.", "visibility": "public",
            "language": "Python", "license": "MIT", "files": ["agent.py"]}), encoding="utf-8")
        common = ("--meta", meta, "--no-repo-dir", "--format", "json")
        banner = directory / "banner.png"
        card = directory / "card.svg"
        hold_flags = () if brand.owner_status(owner) == "watching" else ("--allow-hold",)
        rendered = run_cli(*common, "banner", "--out", banner, "--scale", "1",
            "--allow-unmeasured", *hold_flags, "--key-chip", "Synthetic", "--chip", "Python")
        card_result = run_cli(*common, "card", "--out", card, "--allow-unmeasured", *hold_flags)
        if row["tier"] == "T3":
            assert rendered.returncode == card_result.returncode == 2, owner
            assert not banner.exists() and not card.exists(), owner
            continue
        if brand.owner_status(owner) == "watching":
            # Non-forks require an owner decision. The row cannot be used to
            # sidestep the watching-org boundary merely to exercise rendering.
            assert rendered.returncode == card_result.returncode == 2, owner
            continue
        assert rendered.returncode == 0, (owner, rendered.stdout, rendered.stderr)
        assert card_result.returncode == 0, (owner, card_result.stdout, card_result.stderr)
        assert banner.is_file() and card.is_file(), owner
        ctx = context(brand, owner, language="Python", files=["agent.py"])
        header = readme.header(ctx)
        readme_path = directory / "README.md"
        readme_path.write_text(readme.scaffold(ctx), encoding="utf-8")
        linted = readmelint.lint(ctx, readme_path)
        assert not any("D13" in item or "off-palette" in item for item in linted["fails"]), (owner, linted)
        assert run_cli("lint", "banner", banner).returncode == 0, owner
        assert run_cli("lint", "svg", "--kind", "card", card).returncode == 0, owner
        if row["family"] != "completetech":
            for source in (rendered.stdout, card.read_text(encoding="utf-8"), header):
                assert not re.search(r"completetech|CompleteDotTech|005ADD", source, re.I), owner
