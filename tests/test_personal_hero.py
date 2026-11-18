"""The personal README uses its applicable intro, while authored heroes stay authored."""
import json

import pytest

from conftest import run_cli


def metadata(tmp_path, *, owner="CompleteDotTech", repo="CompleteDotTech"):
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"owner": owner, "repo": repo, "visibility": "public", "license": "MIT",
                                "description": "Show synthetic public projects.", "topics": [],
                                "files": [], "files_complete": True}), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def intro_bytes(tmp_path_factory):
    path = tmp_path_factory.mktemp("personal-intro") / "intro.svg"
    result = run_cli("intro", "--profile", "CompleteDotTech", "--static", "--out", path)
    assert result.returncode == 0, result.stdout + result.stderr
    return path.read_bytes()


def put_intro(tmp_path, data):
    path = tmp_path / "assets" / "intro.svg"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)


def test_personal_scaffold_uses_generated_intro_and_lints_hero(tmp_path, intro_bytes):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "scaffold", "--badges", "local",
                     "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert '<img src="assets/intro.svg"' in text
    assert "docs/images/banner.png" not in text
    lint = run_cli("--meta", meta, "--repo-dir", tmp_path, "lint", "readme", tmp_path / "README.md")
    failures = json.loads(lint.stdout)["fails"]
    # Main's separate J-badge defect is owned by #7; this regression checks hero semantics.
    assert not [failure for failure in failures if "banner" in failure or "image" in failure], failures


def test_personal_scaffold_missing_intro_refuses_before_writes(tmp_path):
    meta = metadata(tmp_path)
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path,
                     "readme", "--mode", "scaffold", "--badges", "local", "--write")
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:intro" in result.stdout
    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / "docs").exists()


@pytest.mark.parametrize("link_asset_directory", [False, True])
def test_personal_scaffold_does_not_use_linked_intro_outside_the_checkout(tmp_path, intro_bytes, link_asset_directory):
    target = tmp_path / "repo"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "intro.svg").write_bytes(intro_bytes)
    assets = target / "assets"
    try:
        if link_asset_directory:
            assets.symlink_to(outside, target_is_directory=True)
        else:
            assets.mkdir()
            (assets / "intro.svg").symlink_to(outside / "intro.svg")
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"checkout links unavailable: {error}")
    records = tmp_path / "records.jsonl"

    result = run_cli("--meta", metadata(tmp_path), "--repo-dir", target, "--format", "json", "readme",
                     "--mode", "scaffold", "--badges", "local", "--records", records, "--write")

    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert not (target / "README.md").exists()
    assert not (target / "docs").exists()
    assert not records.exists()


@pytest.mark.parametrize("mode", ["auto", "scaffold"])
@pytest.mark.parametrize("with_intro", [False, True])
@pytest.mark.parametrize("hero", [b"hero.svg", b"assets/profile-cover-badge.svg"])
def test_personal_short_readme_keeps_authored_hero_when_scaffolding(tmp_path, intro_bytes, mode, with_intro, hero):
    meta = metadata(tmp_path)
    if with_intro:
        put_intro(tmp_path, intro_bytes)
    readme = tmp_path / "README.md"
    before = b"\xef\xbb\xbf![Custom hero](" + hero + b")  \r\n\r# Synthetic Profile\n"
    readme.write_bytes(before)
    records = tmp_path / "records.jsonl"
    modes = [] if mode == "auto" else ["--mode", mode]

    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "--format", "json", "readme",
                     *modes, "--records", records, "--write")

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "scaffold"
    assert report["result"] == "unchanged" and report["written"] is False
    assert readme.read_bytes() == before
    assert not records.exists()


@pytest.mark.parametrize("mode", ["header", "upgrade"])
@pytest.mark.parametrize("legacy_repo", ["CompleteDotTech", "completedottech"])
def test_personal_refresh_migrates_only_the_exact_old_generated_hero(tmp_path, intro_bytes, mode, legacy_repo):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    source = ('<!-- showcase:banner:start -->\n<p align="center">\n'
              f'  <img src="docs/images/banner.png" alt="{legacy_repo} by CompleteTech LLC" width="100%">\n'
              '</p>\n<!-- showcase:banner:end -->\n\n# Synthetic profile\n\nAuthored project notes stay.\n')
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", mode, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = path.read_text(encoding="utf-8")
    assert 'src="assets/intro.svg"' in text
    assert "docs/images/banner.png" not in text
    assert "Authored project notes stay." in text


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_personal_refresh_keeps_authored_marked_hero_without_intro(tmp_path, mode):
    meta = metadata(tmp_path)
    body = '<p align="center">\n  <img src="custom.svg" alt="Authored hero" width="840">\n</p>'
    source = f"<!-- showcase:banner:start -->\n{body}\n<!-- showcase:banner:end -->\n\n# Profile\n\nAuthored notes.\n"
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", mode, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = path.read_text(encoding="utf-8")
    assert body in text and "Authored notes." in text
    assert "assets/intro.svg" not in text and "docs/images/banner.png" not in text



def test_personal_scaffold_keeps_nonbreaking_space_in_authored_hero(tmp_path):
    meta = metadata(tmp_path)
    path = tmp_path / "README.md"
    before = "<!-- showcase:banner:start -->\r\n \n<!-- showcase:banner:end -->\r\n".encode("utf-8")
    path.write_bytes(before)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "scaffold", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == before

def test_personal_header_keeps_authored_bytes_and_crlf(tmp_path, intro_bytes):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    before = (b'\xef\xbb\xbf<!-- showcase:banner:start -->\r\n<p align="center">\r\n'
              b'  <img src="docs/images/banner.png" alt="CompleteDotTech by CompleteTech LLC" width="100%">\r\n'
              b'</p>\r\n<!-- showcase:banner:end -->\r\n\r\n# Profile\r\n\r\nAuthored  spaces.  \r\n')
    path = tmp_path / "README.md"
    path.write_bytes(before)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_bytes()
    assert after.startswith(b"\xef\xbb\xbf")
    assert b'\r\n\r\n# Profile\r\n\r\nAuthored  spaces.  \r\n' in after
    assert b'\n' not in after.replace(b'\r\n', b'')
    assert b'src="assets/intro.svg"' in after


@pytest.mark.parametrize("owner,repo", [("CompleteTech-Skills", ".github"),
                                         ("CompleteTech-Skills", "synthetic-project")])
def test_org_and_repository_scaffolds_keep_banner_contract(tmp_path, intro_bytes, owner, repo):
    meta = metadata(tmp_path, owner=owner, repo=repo)
    put_intro(tmp_path, intro_bytes)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "scaffold", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert '<img src="docs/images/banner.png"' in text
    assert 'src="assets/intro.svg"' not in text


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_missing_intro_refresh_does_not_write_readme_badges_or_records(tmp_path, mode):
    meta = metadata(tmp_path)
    source = ('<!-- showcase:banner:start -->\n<p align="center">\n'
              '  <img src="docs/images/banner.png" alt="CompleteDotTech by CompleteTech LLC" width="100%">\n'
              '</p>\n<!-- showcase:banner:end -->\n\n# Profile\n\nAuthored notes.\n')
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    records = tmp_path / "records.jsonl"
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "readme",
                     "--mode", mode, "--badges", "local", "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout
    assert path.read_bytes() == source.encode()
    assert not records.exists() and not (tmp_path / "docs").exists()


def test_personal_missing_identity_does_not_use_company_fallback(tmp_path, intro_bytes):
    import yaml
    from conftest import ROOT

    config = yaml.safe_load((ROOT / "references/brand.yaml").read_text(encoding="utf-8"))
    config["orgs"]["CompleteDotTech"]["profile"].pop("eyebrow")
    config_path = tmp_path / "brand.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    result = run_cli("--format", "json", "--config", config_path, "--meta", meta, "--repo-dir", tmp_path,
                     "readme", "--mode", "scaffold", "--badges", "local", "--write")
    assert result.returncode == 4 and "needs-input:intro-identity" in result.stdout
    assert not (tmp_path / "README.md").exists() and not (tmp_path / "docs").exists()


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_personal_unmarked_hero_and_significant_whitespace_stay_authored(tmp_path, mode):
    meta = metadata(tmp_path)
    source = b'<p align="center">\r\n  <img src="custom.svg" alt="Authored art">\n</p>\r\n\r\n# Profile\n\nNotes  stay.  \r\n'
    path = tmp_path / "README.md"
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", mode, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == source


def test_personal_intro_refresh_is_repeatable_with_case_insensitive_identity(tmp_path, intro_bytes):
    meta = metadata(tmp_path, owner="completedottech", repo="completedottech")
    put_intro(tmp_path, intro_bytes)
    base = ("--meta", meta, "--repo-dir", tmp_path, "readme", "--write")
    scaffold = run_cli(*base, "--mode", "scaffold", "--badges", "local")
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    for mode in ("upgrade", "header"):
        first = run_cli(*base, "--mode", mode, "--badges", "local")
        assert first.returncode == 0, first.stdout + first.stderr
        path = tmp_path / "README.md"
        before = path.read_bytes()
        second = run_cli(*base, "--mode", mode, "--badges", "local")
        assert second.returncode == 0, second.stdout + second.stderr
        assert path.read_bytes() == before
        assert before.count(b'src="assets/intro.svg"') == 1
        assert b"docs/images/banner.png" not in before


@pytest.mark.parametrize("marked", [False, True])
def test_personal_upgrade_does_not_claim_authored_banner_path(tmp_path, marked):
    meta = metadata(tmp_path)
    hero = '<p align="center">\n  <img src="docs/images/banner.png" alt="Authored banner" width="100%">\n</p>'
    if marked:
        hero = f"<!-- showcase:banner:start -->\n{hero}\n<!-- showcase:banner:end -->"
    source = hero + "\n\n# Profile\n\nAuthored notes.  \n"
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == source.encode()


def test_personal_banner_remains_exempt(tmp_path):
    meta = metadata(tmp_path)
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "banner")
    assert result.returncode == 0 and json.loads(result.stdout)["result"] == "exempt"
    assert "exempt:profile-readme" in result.stdout
    assert not (tmp_path / "docs/images/banner.png").exists()


def test_personal_changed_header_preserves_authored_mixed_line_endings(tmp_path, intro_bytes):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    suffix = b'\r\n\r\n# Profile\n\nAuthored  spaces.  \r\nAnother authored line.\rLast line.\n'
    source = (b'\xef\xbb\xbf<!-- showcase:banner:start -->\r\n<p align="center">\r\n'
              b'  <img src="docs/images/banner.png" alt="CompleteDotTech by CompleteTech LLC" width="100%">\r\n'
              b'</p>\r\n<!-- showcase:banner:end -->' + suffix)
    path = tmp_path / "README.md"
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_bytes()
    assert b'src="assets/intro.svg"' in after
    assert after.startswith(b'\xef\xbb\xbf') and after.endswith(suffix)


def test_personal_bootstrap_preserves_authored_hero_in_pristine_template(tmp_path):
    from ctshowcase.readme import pristine_block

    meta = metadata(tmp_path)
    hero = '<p align="center">\n  <img src="custom.svg" alt="Authored intro">\n</p>'
    source = ('<!-- showcase:banner:start -->\n' + hero + '\n<!-- showcase:banner:end -->\n\n'
              '# CompleteTech Repo Template\n\n<!-- showcase:tagline:start -->\n'
              '**Show synthetic public projects.**\n<!-- showcase:tagline:end -->\n\n---\n\n'
              + pristine_block('## About\n\nSynthetic template content.') + '\n')
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--bootstrap", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_text(encoding="utf-8")
    assert hero in after
    assert 'src="assets/intro.svg"' not in after and "docs/images/banner.png" not in after


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_unresolved_existing_intro_refuses_all_writes(tmp_path, intro_bytes, mode):
    import yaml
    from conftest import ROOT

    config = yaml.safe_load((ROOT / "references/brand.yaml").read_text(encoding="utf-8"))
    config["orgs"]["CompleteDotTech"]["profile"].pop("eyebrow")
    config_path = tmp_path / "brand.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    source = ('<!-- showcase:banner:start -->\n<p align="center">\n'
              '  <img src="assets/intro.svg" alt="Former identity" width="100%">\n'
              '</p>\n<!-- showcase:banner:end -->\n\n'
              '<!-- showcase:nav:start -->\nOld nav\n<!-- showcase:nav:end -->\n\n# Profile\n')
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    records = tmp_path / "records.jsonl"
    result = run_cli("--format", "json", "--config", config_path, "--meta", meta, "--repo-dir", tmp_path,
                     "readme", "--mode", mode, "--badges", "local", "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro-identity" in result.stdout
    assert path.read_bytes() == source.encode()
    assert not records.exists() and not (tmp_path / "docs").exists()


@pytest.mark.parametrize("asset", [b"not an SVG", b'<svg xmlns="http://www.w3.org/2000/svg"/>'])
def test_invalid_or_unrelated_intro_refuses_before_writes(tmp_path, asset):
    meta = metadata(tmp_path)
    put_intro(tmp_path, asset)
    records = tmp_path / "records.jsonl"
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "readme",
                     "--mode", "scaffold", "--badges", "local", "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout
    assert not (tmp_path / "README.md").exists()
    assert not records.exists() and not (tmp_path / "docs").exists()


def test_other_valid_generated_intro_is_not_assumed_applicable(tmp_path):
    meta = metadata(tmp_path)
    path = tmp_path / "assets" / "intro.svg"
    result = run_cli("intro", "--profile", "CompleteDotTech", "--name", "Synthetic Other", "--static", "--out", path)
    assert result.returncode == 0, result.stdout + result.stderr
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "scaffold", "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout
    assert not (tmp_path / "README.md").exists()


def test_org_personal_profile_output_stays_authored_on_readme_upgrade(tmp_path):
    from test_round5_regressions import _user_cli, _user_estate

    root = _user_estate(tmp_path, "Synthetic public profile text.")
    out = tmp_path / "profile"
    result = _user_cli(root, "--out-dir", out)
    assert result.returncode == 0, result.stdout + result.stderr
    path = out / "README.md"
    before = path.read_bytes()
    assert b'assets/intro.svg' in before
    meta = metadata(tmp_path)
    result = run_cli("--meta", meta, "--repo-dir", out, "readme", "--mode", "upgrade", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == before
    lint = run_cli("--meta", meta, "--repo-dir", out, "lint", "readme", path)
    failures = json.loads(lint.stdout)["fails"]
    assert any("banner" in failure or "nav" in failure for failure in failures), failures


def test_changed_intro_identity_refuses_ambiguous_managed_hero(tmp_path, intro_bytes):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    source = ('<!-- showcase:banner:start -->\n<p align="center">\n'
              '  <img src="assets/intro.svg" alt="Previous identity" width="100%">\n'
              '</p>\n<!-- showcase:banner:end -->\n\n# Profile\n')
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path,
                     "readme", "--mode", "header", "--write")
    assert result.returncode == 4 and "needs-input:intro-identity" in result.stdout
    assert path.read_bytes() == source.encode()


LEGACY_HERO = ('<!-- showcase:banner:start -->\n<p align="center">\n'
               '  <img src="docs/images/banner.png" alt="CompleteDotTech by CompleteTech LLC" width="100%">\n'
               '</p>\n<!-- showcase:banner:end -->\n\n')


@pytest.mark.parametrize("variant", ["G", "H"])
def test_personal_callout_variant_refreshes_managed_hero_to_intro(tmp_path, intro_bytes, variant):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    source = LEGACY_HERO + "> [!NOTE]\n> Synthetic callout.\n\n# Profile\n\nAuthored notes.\n"
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", variant,
                     "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = path.read_text(encoding="utf-8")
    assert text.count('src="assets/intro.svg"') == 1 and "docs/images/banner.png" not in text
    assert "> Synthetic callout." in text and "Authored notes." in text

    lint_args = ("--meta", meta, "--repo-dir", tmp_path, "lint", "readme", path, "--variant", variant)
    lint = run_cli(*lint_args)
    assert lint.returncode == 0, lint.stdout + lint.stderr
    (tmp_path / "assets/intro.svg").unlink()
    lint = run_cli(*lint_args)
    assert lint.returncode == 1
    assert "R7 local image does not resolve: assets/intro.svg" in json.loads(lint.stdout)["fails"]
    put_intro(tmp_path, intro_bytes)

    legacy = text.replace('src="assets/intro.svg"', 'src="docs/images/banner.png"', 1)
    path.write_text(legacy, encoding="utf-8")
    lint = run_cli(*lint_args)
    assert lint.returncode == 1
    assert "D13 the hero must be the first image (assets/intro.svg)" in json.loads(lint.stdout)["fails"]

    picture = text.replace('<p align="center">', '<picture>', 1).replace("</p>", "</picture>", 1)
    path.write_text(picture, encoding="utf-8")
    lint = run_cli(*lint_args)
    assert lint.returncode == 1
    assert "D13 banner must be a plain <img>, not <picture>" in json.loads(lint.stdout)["fails"]


@pytest.mark.parametrize("variant", ["G", "H"])
def test_personal_callout_variant_missing_intro_refuses_before_writes(tmp_path, variant):
    meta = metadata(tmp_path)
    source = LEGACY_HERO + "> [!NOTE]\n> Synthetic callout.\n\n# Profile\n\nAuthored notes.\n"
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    records = tmp_path / "records.jsonl"
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade",
                     "--variant", variant, "--badges", "local", "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert path.read_bytes() == source.encode("utf-8")
    assert not records.exists() and not (tmp_path / "docs").exists()


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_personal_refresh_validates_intro_and_preserves_the_authored_marker_seam(tmp_path, intro_bytes, variant, mode):
    meta = metadata(tmp_path)
    hero = LEGACY_HERO.replace("<!-- showcase:banner:end -->", "<!-- showcase:banner:end -->Authored marker seam.  ")
    source = ("> [!NOTE]\r\n> Synthetic callout.\r\n\r\n" + hero + "# Profile\r\n\rAuthored notes.\r")
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    records = tmp_path / "records.jsonl"
    args = ("--meta", meta, "--repo-dir", tmp_path, "--format", "json", "readme",
            "--mode", mode, "--variant", variant, "--records", records, "--write")

    missing = run_cli(*args)
    assert missing.returncode == 4 and "needs-input:intro" in missing.stdout, missing.stdout + missing.stderr
    assert path.read_bytes() == source.encode("utf-8")
    assert not records.exists()

    put_intro(tmp_path, intro_bytes)
    refreshed = run_cli(*args)
    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    after = path.read_bytes()
    assert b'src="assets/intro.svg"' in after and b"docs/images/banner.png" not in after
    seam = b"<!-- showcase:banner:end -->Authored marker seam.  \n\n# Profile\r\n\rAuthored notes.\r"
    assert seam in after


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("mode,authored", [("upgrade", False), ("header", False), ("scaffold", False), ("upgrade", True)])
def test_personal_callout_refuses_multiple_marked_heroes_before_writes(tmp_path, intro_bytes, variant, mode, authored):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    second = LEGACY_HERO.replace('width="100%"', 'width="840"') if authored else LEGACY_HERO
    source = ("> [!NOTE]\n> Synthetic callout.\n\n" + LEGACY_HERO + "# Profile\n\n"
              + second + "Authored notes.\n").encode("utf-8")
    path = tmp_path / "README.md"
    path.write_bytes(source)
    records = tmp_path / "records.jsonl"
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "--format", "json", "readme",
                     "--mode", mode, "--variant", variant, "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert path.read_bytes() == source
    assert not records.exists()


def test_full_personal_upgrade_preserves_authored_prose_naming_the_legacy_banner(tmp_path, intro_bytes):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    path = tmp_path / "README.md"
    authored = b"The old docs/images/banner.png is retired.  \r\n"
    source = (LEGACY_HERO.replace("\n", "\r\n").encode("utf-8") + b"# Synthetic profile\r\n\r\n" + authored
              + b"\r\n## Notes\n\nKeep these notes.\n")
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", "J", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    refreshed = path.read_bytes()
    assert authored in refreshed
    assert b'src="assets/intro.svg"' in refreshed
    assert b'src="docs/images/banner.png"' not in refreshed


@pytest.mark.parametrize("variant", ["G", "H"])
def test_personal_callout_variant_keeps_authored_hero_block(tmp_path, variant):
    meta = metadata(tmp_path)
    hero = '<p align="center">\n  <img src="custom.svg" alt="Authored hero" width="840">\n</p>'
    source = (f"<!-- showcase:banner:start -->\n{hero}\n<!-- showcase:banner:end -->\n\n"
              "> [!NOTE]\n> Synthetic callout.\n\n# Profile\n\nAuthored notes.\n")
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", variant,
                     "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = path.read_text(encoding="utf-8")
    assert hero in text and "assets/intro.svg" not in text and "docs/images/banner.png" not in text


def _preserve_list_readme() -> str:
    # Over 15,000 bytes puts any README on the §7.0 preserve list.
    filler = "\n\n".join(f"Synthetic Northwind paragraph {i} with authored notes that stay." for i in range(320))
    return LEGACY_HERO + "# Profile\n\n## Notes\n\n" + filler + "\n"


def test_personal_preserve_list_upgrade_opens_with_intro(tmp_path, intro_bytes):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    source = _preserve_list_readme()
    assert len(source.encode("utf-8")) > 15000
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = path.read_text(encoding="utf-8")
    assert text.count('src="assets/intro.svg"') == 1 and "docs/images/banner.png" not in text
    assert "Synthetic Northwind paragraph 319 with authored notes that stay." in text


def test_personal_preserve_list_upgrade_missing_intro_refuses_before_writes(tmp_path):
    meta = metadata(tmp_path)
    source = _preserve_list_readme()
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    records = tmp_path / "records.jsonl"
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade",
                     "--badges", "local", "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert path.read_bytes() == source.encode("utf-8")
    assert not records.exists() and not (tmp_path / "docs").exists()


def test_personal_bootstrap_missing_intro_refuses_before_writes(tmp_path):
    from ctshowcase.readme import pristine_block

    meta = metadata(tmp_path)
    source = (LEGACY_HERO + '# CompleteTech Repo Template\n\n<!-- showcase:tagline:start -->\n'
              '**Show synthetic public projects.**\n<!-- showcase:tagline:end -->\n\n---\n\n'
              + pristine_block('## About\n\nSynthetic template content.') + '\n')
    path = tmp_path / "README.md"
    path.write_bytes(source.encode("utf-8"))
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "readme", "--bootstrap", "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert path.read_bytes() == source.encode("utf-8")
    assert not (tmp_path / "CONTRIBUTING.md").exists()


@pytest.mark.parametrize("variant", ["G", "H"])
def test_hero_less_personal_callout_requires_intro_before_writes(tmp_path, variant):
    meta = metadata(tmp_path)
    path = tmp_path / "README.md"
    source = b"\xef\xbb\xbf> Legacy note\r\n\r\n# Profile\n\nAuthored notes.  \r\n"
    path.write_bytes(source)
    records = tmp_path / "records.jsonl"
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", variant,
                     "--badges", "local", "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert path.read_bytes() == source
    assert not records.exists() and not (tmp_path / "docs").exists()


@pytest.mark.parametrize("variant", ["G", "H"])
def test_hero_less_personal_callout_adds_verified_intro(tmp_path, intro_bytes, variant):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    path = tmp_path / "README.md"
    source = b"> Legacy note\r\n\r\n# Profile\n\nAuthored notes.  \r\n"
    path.write_bytes(b"\xef\xbb\xbf" + source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", variant,
                     "--badges", "local", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    updated = path.read_bytes()
    assert updated.startswith(b"\xef\xbb\xbf<!-- showcase:banner:start -->")
    assert updated.count(b'src="assets/intro.svg"') == 1
    assert source in updated


@pytest.mark.parametrize("variant", ["G", "H", "J"])
@pytest.mark.parametrize("destination", ["custom.svg", "docs/images/banner.png"])
def test_personal_upgrade_preserves_reference_hero_without_intro(tmp_path, variant, destination):
    meta = metadata(tmp_path)
    path = tmp_path / "README.md"
    source = (b"> Legacy note\r\n\r\n![Authored hero][art]\n\n"
              + f"[art]: {destination}\r\n\r\n".encode("utf-8")
              + b"# Profile\n\nAuthored notes.  \r\n")
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", variant,
                     "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes().startswith(source)
    assert b'assets/intro.svg' not in path.read_bytes()


@pytest.mark.parametrize("target", ["assets/other.svg", "assets/intro.svg.backup.svg"])
def test_personal_lint_requires_intro_image_source(tmp_path, intro_bytes, target):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    args = ("--meta", meta, "--repo-dir", tmp_path)
    scaffold = run_cli(*args, "readme", "--mode", "scaffold", "--badges", "local", "--write")
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    path = tmp_path / "README.md"
    (tmp_path / "assets" / "intro.svg").rename(tmp_path / target)
    source = path.read_text(encoding="utf-8")
    source = source.replace('src="assets/intro.svg" alt="', f'src="{target}" alt="assets/intro.svg ')
    path.write_text(source, encoding="utf-8")
    result = run_cli(*args, "lint", "readme", path)
    fails = json.loads(result.stdout)["fails"]
    assert any("hero banner must open" in failure for failure in fails), fails
    assert "D13 the hero must be the first image (assets/intro.svg)" in fails


def test_personal_preserve_unchanged_keeps_managed_intro_in_place(tmp_path, intro_bytes):
    import yaml
    from conftest import ROOT

    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    args = ("--meta", meta, "--repo-dir", tmp_path)
    scaffold = run_cli(*args, "readme", "--mode", "scaffold", "--badges", "local", "--write")
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    path = tmp_path / "README.md"
    source = path.read_bytes() + b"\n## Notes\n\n" + b"Long authored profile notes.\n" * 600
    path.write_bytes(source)
    config = yaml.safe_load((ROOT / "references" / "brand.yaml").read_text(encoding="utf-8"))
    config["readme"]["preserve_banner"] = "unchanged"
    brand = tmp_path / "brand.yaml"
    brand.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    (tmp_path / "assets" / "intro.svg").unlink()
    facts = json.loads(meta.read_text(encoding="utf-8"))
    facts["language"] = "Python"
    meta.write_text(json.dumps(facts), encoding="utf-8")
    result = run_cli("--config", brand, *args, "readme", "--mode", "upgrade", "--badges", "local", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    updated = path.read_bytes()
    opener = b"<!-- showcase:badges:start -->"
    closer = b"<!-- showcase:badges:end -->"
    assert updated.split(opener, 1)[0] == source.split(opener, 1)[0]
    assert updated.split(closer, 1)[1] == source.split(closer, 1)[1]
    assert b"![Language Python](docs/images/badges/language-python.svg)" in updated


@pytest.mark.parametrize("image", ["![Authored hero][hero]", "![hero][]", "![hero]"])
@pytest.mark.parametrize("has_intro", [False, True])
def test_personal_reference_hero_stays_authored_with_definition_after_section(tmp_path, intro_bytes, image,
                                                                           has_intro):
    meta = metadata(tmp_path)
    if has_intro:
        put_intro(tmp_path, intro_bytes)
    source = (f"\ufeff{image}\r\n\r\n# Profile\r\n\r\nAuthored  notes.  \r\n\r\n"
              "## Details\r\n\r\n[hero]: custom.svg\r\n").encode("utf-8")
    path = tmp_path / "README.md"
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == source
    assert not (tmp_path / "docs").exists()


@pytest.mark.parametrize("variant", ["G", "H"])
def test_personal_callout_variant_preserves_unmarked_reference_hero(tmp_path, variant):
    meta = metadata(tmp_path)
    source = ("![Authored hero][hero]\n\n# Profile\n\nAuthored notes.\n\n"
              "## Details\n\n[hero]: custom.svg\n").encode("utf-8")
    path = tmp_path / "README.md"
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade",
                     "--variant", variant, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == source


@pytest.mark.parametrize("variant", ["G", "H"])
@pytest.mark.parametrize("has_intro", [False, True])
def test_personal_callout_variant_without_banner_requires_intro(tmp_path, intro_bytes, variant, has_intro):
    meta = metadata(tmp_path)
    if has_intro:
        put_intro(tmp_path, intro_bytes)
    source = b"# Profile\r\n\r\nAuthored notes.\r\n"
    path, records = tmp_path / "README.md", tmp_path / "records.jsonl"
    path.write_bytes(source)
    result = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade",
                     "--variant", variant, "--badges", "local", "--records", records, "--write")
    if has_intro:
        assert result.returncode == 0, result.stdout + result.stderr
        updated = path.read_bytes()
        assert updated.count(b'src="assets/intro.svg"') == 1
        assert updated.index(b'src="assets/intro.svg"') < updated.index(b"# Profile")
        assert b"Authored notes.\r\n" in updated
        assert b"docs/images/banner.png" not in updated
    else:
        assert result.returncode == 4, result.stdout + result.stderr
        assert "needs-input:intro" in result.stdout
        assert path.read_bytes() == source
        assert not records.exists() and not (tmp_path / "docs").exists()


@pytest.mark.parametrize("variant", ["G", "H"])
def test_personal_callout_moves_managed_intro_out_of_the_authored_body(tmp_path, intro_bytes, variant):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    readme = tmp_path / "README.md"
    prefix = b"> [!NOTE]\r\n> Synthetic callout.\n\n# Profile\r\n\n## Notes\n\nAuthored body.  \r\n\n"
    before = prefix + LEGACY_HERO.encode("utf-8")
    readme.write_bytes(before)
    common = ("--meta", meta, "--repo-dir", tmp_path, "--format", "json")
    header = run_cli(*common, "readme", "--mode", "header", "--variant", variant, "--write")
    assert header.returncode == 4 and "needs-input:intro-order" in header.stdout
    assert readme.read_bytes() == before

    upgrade = run_cli(*common, "readme", "--mode", "upgrade", "--variant", variant, "--write")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    updated = readme.read_bytes()
    close = b"<!-- showcase:banner:end -->"
    intro, _, rest = updated.partition(close)
    assert b'src="assets/intro.svg"' in intro
    assert b"docs/images/banner.png" not in updated
    assert prefix.rstrip(b"\r\n") in rest
    lint_args = (*common, "lint", "readme", readme, "--variant", variant)
    assert run_cli(*lint_args).returncode == 0

    footer = b"<!-- showcase:footer:start -->"
    body, marker, ending = rest.lstrip(b"\r\n").partition(footer)
    assert marker
    readme.write_bytes(body + intro + close + b"\n\n" + marker + ending)
    late = run_cli(*lint_args)
    assert late.returncode == 1
    assert any(fail.startswith("D13 ") for fail in json.loads(late.stdout)["fails"])


CALLOUT_PREFIX = b"> [!NOTE]\r\n> Synthetic callout.\n\n"
CALLOUT_SUFFIX = b"# Profile\n\nAuthored notes.  \r\n"
LEADING_BUILD_BADGE = b"![Build](https://img.shields.io/badge/build-passing-green)"


@pytest.mark.parametrize("variant", ["G", "H"])
def test_personal_nonleading_managed_banner_missing_intro_refuses_before_writes(tmp_path, variant):
    meta = metadata(tmp_path)
    path = tmp_path / "README.md"
    source = CALLOUT_PREFIX + LEGACY_HERO.replace("\n", "\r\n").encode() + CALLOUT_SUFFIX
    path.write_bytes(source)
    records = tmp_path / "records.jsonl"
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", variant,
                     "--badges", "local", "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert path.read_bytes() == source
    assert not records.exists() and not (tmp_path / "docs").exists()


@pytest.mark.parametrize("variant", ["G", "H"])
def test_personal_nonleading_managed_banner_refreshes_in_place(tmp_path, intro_bytes, variant):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    path = tmp_path / "README.md"
    suffix = b"# Profile\n\nAuthored notes.  \r\n"
    source = b"\xef\xbb\xbf" + CALLOUT_PREFIX + LEGACY_HERO.replace("\n", "\r\n").encode() + suffix
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", variant,
                     "--badges", "local", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    updated = path.read_bytes()
    assert updated.startswith(b"\xef\xbb\xbf" + CALLOUT_PREFIX + b"<!-- showcase:banner:start -->")
    assert b'src="assets/intro.svg"' in updated and b"docs/images/banner.png" not in updated
    assert suffix in updated


@pytest.mark.parametrize("variant", ["G", "H"])
def test_personal_leading_badge_is_not_a_hero_for_missing_intro(tmp_path, variant):
    meta = metadata(tmp_path)
    path = tmp_path / "README.md"
    source = LEADING_BUILD_BADGE + b"\n\n" + CALLOUT_PREFIX + CALLOUT_SUFFIX
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--variant", variant,
                     "--badges", "local", "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert path.read_bytes() == source and not (tmp_path / "docs").exists()


def test_personal_upgrade_adds_intro_and_preserves_authored_leading_badge(tmp_path, intro_bytes):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    path = tmp_path / "README.md"
    path.write_bytes(LEADING_BUILD_BADGE + b"\n\n# Profile\n\nAuthored profile notes.\n")
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "upgrade", "--badges", "local",
                     "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    updated = path.read_bytes()
    assert updated.startswith(b"<!-- showcase:banner:start -->\n")
    assert b'src="assets/intro.svg"' in updated
    assert LEADING_BUILD_BADGE in updated and b"Authored profile notes." in updated


def test_personal_callout_does_not_treat_catalogo_as_a_logo(tmp_path, intro_bytes):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    path = tmp_path / "README.md"
    before = (b'<img src="assets/catalogo.svg" alt="Authored profile hero" width="100%">  \r\n'
              b'\r\n# Profile\n\nAuthored notes.\r')
    path.write_bytes(before)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme",
                     "--variant", "G", "--mode", "upgrade", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_personal_authored_marked_hero_keeps_mixed_ending_seam(tmp_path, mode):
    meta = metadata(tmp_path)
    path = tmp_path / "README.md"
    source = (b'\xef\xbb\xbf<!-- showcase:banner:start -->\r\n<p align="center">\n'
              b'  <img src="custom.svg" alt="Owned artwork">\r\n</p>\n<!-- showcase:banner:end -->'
              b'\r\n\n\r\n\r\n# Profile\r\n\r\nAuthored notes.  \n')
    path.write_bytes(source)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", mode, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == source


def test_unrenderable_profile_config_refuses_intro_applicability_before_writes(tmp_path, intro_bytes):
    import yaml

    from conftest import ROOT

    config = yaml.safe_load((ROOT / "references/brand.yaml").read_text(encoding="utf-8"))
    config["orgs"]["CompleteDotTech"]["profile"]["eyebrow"] = "Synthetic impossibly long eyebrow " * 50
    brand = tmp_path / "brand.yaml"
    brand.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    direct = run_cli("--config", brand, "intro", "--profile", "CompleteDotTech", "--static",
                     "--out", tmp_path / "attempt.svg")
    assert direct.returncode == 3, direct.stdout + direct.stderr
    records = tmp_path / "records.jsonl"
    result = run_cli("--config", brand, "--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "scaffold",
                     "--badges", "local", "--records", records, "--write")
    assert result.returncode == 4 and "needs-input:intro" in result.stdout, result.stdout + result.stderr
    assert not (tmp_path / "README.md").exists() and not (tmp_path / "docs").exists() and not records.exists()
