"""Explicit wording and brand identity regressions (#36, #40, #175).

The all-row evidence samples the banner's bar, inspects card SVG source and
reported mark provenance, and examines generated README/profile text. It is
not an exhaustive pixel, outlined-text, or embedded-image recognition test.
SVG visual inspection needs an optional renderer; detecting arbitrary outlined
text or marks would require an OCR/image-recognition oracle. Representative
contact-sheet inspection remains separate from automated tests.
"""
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
        "description": "Inspect synthetic records.", "visibility": "public", "files": ["LICENSE"], **meta}))


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



def assert_banner_bar(image, colour):
    """Check the gradient start with a small allowance for raster rounding."""
    expected = tuple(bytes.fromhex(colour.lstrip("#")))
    actual = image.convert("RGB").getpixel((1, image.height - 3))
    assert all(abs(a - b) <= 3 for a, b in zip(actual, expected)), (actual, expected)


def assert_wordmark_provenance(icon, svg):
    assert icon["source"] == "family-wordmark" and icon["path"] is None
    assert "data:image/" not in svg.lower()


def test_banner_bar_evidence_rejects_cross_family_colour(brand):
    # The former file-existence assertion accepts this substituted foreign bar.
    from PIL import Image
    own = brand.family("completetech")["tokens"]["bar"]["from"]
    foreign = brand.style("jevplay-games")["tokens"]["bar"]["from"]
    with pytest.raises(AssertionError):
        assert_banner_bar(Image.new("RGB", (1280, 360), foreign), own)


def test_wordmark_evidence_rejects_foreign_embedded_mark():
    info = {"source": "family-wordmark", "path": None}
    with pytest.raises(AssertionError):
        assert_wordmark_provenance(info, '<image href="data:image/png;base64,foreign"/>')
    with pytest.raises(AssertionError):
        assert_wordmark_provenance({"source": "org-mark", "path": "foreign.png"}, "<svg/>")


def test_each_org_row_keeps_its_identity_across_surfaces(brand, tmp_path):
    """Exercise real CLI paths for every configured row, including refusal rows."""
    import re
    from PIL import Image
    from ctshowcase import readmelint

    for owner, row in brand.raw["orgs"].items():
        directory = tmp_path / owner
        directory.mkdir()
        meta = directory / "meta.json"
        meta.write_text(json.dumps({"owner": owner, "repo": "synthetic-agent",
            "description": "Inspect synthetic records.", "visibility": "public",
            "language": "Python", "license": "MIT", "files": ["agent.py"]}), encoding="utf-8")
        common = ("--meta", meta, "--no-repo-dir", "--format", "json")
        if row["tier"] == "T3":
            signoff = directory / "synthetic-signoff.json"
            signoff.write_text(json.dumps({"signoffs": [{"id": "synthetic-brand-row", "owner": owner,
                "repos": ["synthetic-agent"], "approved": True, "approver": "synthetic-co-owner",
                "approved_on": "2026-01-15", "expires": "2099-12-31"}]}), encoding="utf-8")
            common += ("--allow-t3", "--t3-signoff-file", signoff)
        banner = directory / "banner.png"
        card = directory / "card.svg"
        hold_flags = () if brand.owner_status(owner) == "watching" else ("--allow-hold",)
        rendered = run_cli(*common, "banner", "--out", banner, "--scale", "1",
            "--allow-unmeasured", *hold_flags, "--key-chip", "Synthetic", "--chip", "Python")
        card_result = run_cli(*common, "card", "--out", card, "--allow-unmeasured", *hold_flags)
        if (brand.raw["families"][row["family"]]).get("identity_pending"):
            assert rendered.returncode == card_result.returncode == 4, owner
            assert "needs-input:brand-identity" in rendered.stdout + card_result.stdout, owner
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
        tokens = brand.style(owner)["tokens"]
        with Image.open(banner) as image:
            assert_banner_bar(image, tokens["bar"]["from"])
        svg = card.read_text(encoding="utf-8")
        for colour in (tokens["bar"]["from"], tokens["bar"].get("to") or tokens["bar"]["from"]):
            assert colour.lower() in svg.lower(), (owner, colour)
        banner_icon = json.loads(rendered.stdout)["icon"]
        card_icon = json.loads(card_result.stdout)["icon"]
        if row.get("mark"):
            assert banner_icon["source"] == card_icon["source"] == "org-mark", owner
            assert banner_icon["path"] == card_icon["path"] == row["mark"], owner
        elif row["family"] != "completetech":
            assert_wordmark_provenance(banner_icon, svg)
            assert_wordmark_provenance(card_icon, svg)
        checkout = directory / "checkout"
        checkout.mkdir()
        consent = common[5:] if row["tier"] == "T3" else ()
        generated = run_cli("--meta", meta, "--repo-dir", checkout, "--format", "json", *consent, "readme", "--write")
        assert generated.returncode == 0, (owner, generated.stdout, generated.stderr)
        cli_readme = (checkout / "README.md").read_text(encoding="utf-8")
        if row["family"] != "completetech":
            body = cli_readme.split("<!-- showcase:footer:start -->", 1)[0]
            assert not re.search(r"completetech|CompleteDotTech|005ADD", body, re.I), owner
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


@pytest.mark.parametrize("command", ["banner", "card", "readme", "social", "icon"])
@pytest.mark.parametrize("scope,expected", [("sample", "needs-input:brand-identity"), ("another-repo", "t3-signoff:scope")])
def test_pending_identity_preserves_repository_scoped_consent(tmp_path, command, scope, expected):
    """A valid repository grant reaches needs-input; a different grant never does."""
    owner = "Jevelopers-neatHack-2026"
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": owner, "repo": "sample", "visibility": "public",
                               "description": "Inspect synthetic records."}), encoding="utf-8")
    signoff = tmp_path / "synthetic-signoff.yaml"
    signoff.write_text(f'''signoffs:
  - id: synthetic-identity-scope
    owner: {owner}
    repos: ["{scope}"]
    approved: true
    approver: synthetic-co-owner
    approved_on: 2026-01-15
    expires: 2099-12-31
''', encoding="utf-8")
    output = tmp_path / ("out" if command == "readme" else "out.png" if command == "banner" else "out.svg")
    output_args = () if command == "readme" else ("--out", output)
    if command in ("banner", "card", "social"):
        output_args += ("--allow-unmeasured",)
    command_args = ("content", command, "prompt") if command == "icon" else ("content", command) if command == "social" else (command,)
    result = run_cli("--format", "json", "--meta", meta, "--no-repo-dir", "--allow-t3", "--t3-signoff-file", signoff,
                     *command_args, *output_args)
    assert result.returncode == (4 if scope == "sample" else 2), result.stdout + result.stderr
    assert expected in result.stdout + result.stderr
    assert not output.exists()


def test_content_style_boundary_retains_the_repository_scope(brand, tmp_path):
    from ctshowcase import content, signoff
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off
    from ctshowcase.errors import Refused

    owner = "Jevelopers-neatHack-2026"
    record = tmp_path / "synthetic-signoff.json"
    record.write_text(json.dumps({"signoffs": [{"id": "synthetic-content-style", "owner": owner,
        "repos": ["sample"], "approved": True, "approver": "synthetic-co-owner",
        "approved_on": "2026-01-15", "expires": "2099-12-31"}]}), encoding="utf-8")
    consent_token = set_t3_signed_off(True)
    file_token = signoff.set_file(record)
    try:
        with pytest.raises(NeedsInput, match="owner-supplied palette and mark"):
            content.org_style(brand.resolver(), brand, owner, repo="sample")
        with pytest.raises(Refused):
            content.org_style(brand.resolver(), brand, owner, repo="other")
        with pytest.raises(Refused):
            content.org_style(brand.resolver(), brand, owner)
    finally:
        signoff.reset_file(file_token)
        reset_t3_signed_off(consent_token)


def test_profile_badges_respect_each_configured_family(brand, tmp_path, monkeypatch):
    """Synthetic org profiles retain their own fills, or their normal refusal."""
    import yaml
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty"))
    global_fill = "#" + brand.raw["badges"]["accent"].upper()
    for owner, row in brand.raw["orgs"].items():
        directory = tmp_path / owner
        directory.mkdir()
        registry = directory / "registry.yaml"
        registry.write_text(yaml.safe_dump({"orgs": {owner: {"tier": row["tier"],
            "profile": {"name": "Synthetic organization", "description": "Inspect synthetic records.",
                        "blog": "https://example.invalid"}, "final_repos": [], "sections": []}}}), encoding="utf-8")
        result = run_cli("--format", "json", "org", "profile", owner, "--registry", registry,
                         "--banner", "assets/existing.jpg", "--render", "--out-dir", directory / "output")
        payload = json.loads(result.stdout)
        if result.returncode != 0:
            assert result.returncode in (2, 4), (owner, payload)
            assert any(x.startswith(("hold", "exempt", "t3-signoff", "needs-input:brand-identity", "needs-input:badge-contrast")) for x in payload["logs"]), (owner, payload)
            continue
        if row["family"] == "completetech":
            continue
        profile = (directory / "output" / "profile" / "README.md").read_text(encoding="utf-8")
        body = profile.split("<!-- showcase:footer:start -->", 1)[0]
        # Explicit brand affiliations are facts, not leaks; focused tests cover them.
        if "completetech" not in json.dumps(row).lower():
            assert "completetech" not in body.lower(), owner
            assert "completedottech" not in body.lower(), owner
        style = brand.style(owner)
        allowed = {style["tokens"].get("chip_attr", {}).get("bg"), style["tokens"].get("accent_deep")}
        for badge in (a for a in payload["assets"] if a["kind"] == "badge"):
            assert badge["colour"] in allowed, owner
            # An explicitly configured family colour is an exception even if it matches the global accent.
            if global_fill not in {str(c).upper() for c in allowed}:
                assert badge["colour"].upper() != global_fill, owner
