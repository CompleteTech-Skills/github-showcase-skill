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


@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_personal_refresh_migrates_only_the_exact_old_generated_hero(tmp_path, intro_bytes, mode):
    meta = metadata(tmp_path)
    put_intro(tmp_path, intro_bytes)
    source = ('<!-- showcase:banner:start -->\n<p align="center">\n'
              '  <img src="docs/images/banner.png" alt="CompleteDotTech by CompleteTech LLC" width="100%">\n'
              '</p>\n<!-- showcase:banner:end -->\n\n# Synthetic profile\n\nAuthored project notes stay.\n')
    path = tmp_path / "README.md"
    path.write_text(source, encoding="utf-8")
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
    path.write_text(source, encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", mode, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    text = path.read_text(encoding="utf-8")
    assert body in text and "Authored notes." in text
    assert "assets/intro.svg" not in text and "docs/images/banner.png" not in text


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
    path.write_text(source, encoding="utf-8")
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
    path.write_text(source, encoding="utf-8")
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
    suffix = b'\r\n\r\n# Profile\n\nAuthored  spaces.  \r\nAnother authored line.\n'
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
    path.write_text(source, encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--bootstrap", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_text(encoding="utf-8")
    assert hero in after
    assert 'src="assets/intro.svg"' not in after and "docs/images/banner.png" not in after
