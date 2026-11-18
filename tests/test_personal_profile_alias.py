"""Personal profile identity is shared by banner and README commands."""
import copy
import json

import yaml

from conftest import run_cli


def test_personal_owner_alias_uses_intro_instead_of_banner(tmp_path, monkeypatch, brand):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty-estate"))
    raw = copy.deepcopy(brand.raw)
    owner = "SyntheticOldProfile"
    raw["orgs"]["CompleteDotTech"]["former_slugs"] = [owner]
    config = tmp_path / "brand.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({
        "owner": owner, "repo": "CompleteDotTech", "visibility": "public", "license": "MIT",
        "description": "Show synthetic public projects.", "topics": [], "files": [], "files_complete": True,
    }), encoding="utf-8")
    args = ("--config", config, "--format", "json", "--meta", meta, "--repo-dir", tmp_path)

    banner = run_cli(*args, "banner")
    assert banner.returncode == 0, banner.stdout + banner.stderr
    assert json.loads(banner.stdout)["result"] == "exempt"
    assert "exempt:profile-readme" in banner.stdout
    docs = tmp_path / "docs"
    sidecar = docs / "images" / ".showcase.json"
    assert not (docs / "images" / "banner.png").exists()
    # Staged-description support can cache the live banner exemption without drawing it.
    before_docs = docs.exists(), set(docs.rglob("*"))
    before_sidecar = sidecar.read_bytes() if sidecar.is_file() else None
    if before_sidecar is not None:
        assert json.loads(before_sidecar)["outputs"]["banner.png"]["exempt"] == "exempt:profile-readme"

    readme_args = ("readme", "--mode", "scaffold", "--badges", "local", "--write")
    readme = run_cli(*args, *readme_args)
    assert readme.returncode == 4 and "needs-input:intro" in readme.stdout, readme.stdout + readme.stderr
    assert not (tmp_path / "README.md").exists()
    assert (docs.exists(), set(docs.rglob("*"))) == before_docs
    assert (sidecar.read_bytes() if sidecar.is_file() else None) == before_sidecar

    intro = run_cli("--config", config, "intro", "--profile", owner, "--static",
                    "--out", tmp_path / "assets" / "intro.svg")
    assert intro.returncode == 0, intro.stdout + intro.stderr
    readme = run_cli(*args, *readme_args)
    assert readme.returncode == 0, readme.stdout + readme.stderr
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert '<img src="assets/intro.svg"' in text
    assert "docs/images/banner.png" not in text


def test_alias_does_not_exempt_other_repositories(brand, monkeypatch, tmp_path):
    from ctshowcase.config import Brand
    from ctshowcase.context import RepoContext

    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty-estate"))
    raw = copy.deepcopy(brand.raw)
    owner = "SyntheticOldProfile"
    raw["orgs"]["CompleteDotTech"]["former_slugs"] = [owner]
    local_brand = Brand(raw, brand.path)
    for repo, facts in ((".github", {}), ("sample-project", {}), ("CompleteDotTech", {"fork": True})):
        ctx = RepoContext(local_brand, {"owner": owner, "repo": repo, "visibility": "public", **facts})
        assert not ctx.personal_profile
        assert ctx.art_status()["banner"] != "exempt:profile-readme"
