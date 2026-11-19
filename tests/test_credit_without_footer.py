"""Decision 25 credit independent of the decision 18 footer (the user, 2026-11-18): every managed README names the
skill and its publisher, also when the footer is exempt; held and refused READMEs get neither."""
import copy
import json
import re

import pytest
import yaml

from conftest import run_cli, without_exact_credit
from ctshowcase import footer as footermod
from ctshowcase import readme
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

OUTSIDE = "octocat-labs"
# CompleteTech target identity: none of it may reach an outside owner outside the exact credit block
IDENTITY = re.compile(r"complete\.tech|Built by|@CompleteDotTech|CompleteTechLLC|assets/brand/logo|\bcompletetech\b|"
                      r"#005ADD|#00A7FD|CompleteTech LLC", re.I)


def _meta(tmp_path, owner=OUTSIDE, **kw):
    m = tmp_path / "meta.json"
    m.write_text(json.dumps({"owner": owner, "repo": "sample-cli", "visibility": "public", "fork": False,
                             "description": "Inspect synthetic records from the command line.",
                             "topics": ["cli", "python"], "language": "Python", "license": "MIT",
                             "files": ["main.py", "README.md"], **kw}), encoding="utf-8")
    return m


@pytest.fixture(autouse=True)
def _no_estate(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "no-estate"))


def _scaffold(tmp_path, *extra):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    p = run_cli("--format", "json", "--meta", _meta(tmp_path), "--repo-dir", repo, *extra,
                "readme", "--mode", "scaffold", "--write")
    assert p.returncode == 0, p.stdout + p.stderr
    return repo / "README.md", json.loads(p.stdout)


def test_unknown_owner_gets_the_credit_and_no_footer(tmp_path, brand):
    path, out = _scaffold(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "exempt:footer" in out["logs"]
    assert footermod.START not in text
    assert text.rstrip().endswith(footermod.credit_block(brand))
    assert text.count(footermod.CREDIT_START) == 1
    assert not IDENTITY.search(without_exact_credit(text, brand)), IDENTITY.search(without_exact_credit(text, brand))


def test_unknown_owner_readme_diff_has_the_credit(tmp_path, brand):
    repo = tmp_path / "repo"
    repo.mkdir()
    p = run_cli("--format", "json", "--meta", _meta(tmp_path), "--repo-dir", repo, "readme", "--mode", "scaffold")
    diff = json.loads(p.stdout)["diff"]
    assert footermod.CREDIT_START in diff and footermod.START not in diff
    assert "github-showcase-skill" in diff and brand.raw["attribution"]["publisher"] in diff


def test_regeneration_never_emits_the_credit_twice(tmp_path):
    path, _ = _scaffold(tmp_path)
    first = path.read_text(encoding="utf-8")
    for mode in ("upgrade", "header"):
        p = run_cli("--format", "json", "--meta", _meta(tmp_path), "--repo-dir", tmp_path / "repo",
                    "readme", "--mode", mode, "--write")
        assert p.returncode in (0, 4), p.stdout + p.stderr
        text = path.read_text(encoding="utf-8")
        assert text.count(footermod.CREDIT_START) == 1, mode
        assert text.rstrip().endswith(footermod.CREDIT_END), mode
    assert first.count(footermod.CREDIT_START) == 1


def test_header_mode_adds_the_credit_once_to_a_managed_readme(brand, make_ctx):
    ctx = RepoContext(brand, normalize({"owner": OUTSIDE, "repo": "sample-cli", "visibility": "public",
                                        "description": "Inspect synthetic records."}), None)
    managed = readme.wrap("nav", "**octocat-labs**") + "\n\n# Sample CLI\n\nBody.\n"
    once = readme.header_only(ctx, managed)
    assert once.count(footermod.CREDIT_START) == 1 and once.rstrip().endswith(footermod.CREDIT_END)
    assert readme.header_only(ctx, once).count(footermod.CREDIT_START) == 1
    authored = "# Someone else's README\n\nNo showcase blocks here.\n"
    assert footermod.CREDIT_START not in readme.header_only(ctx, authored)


def test_footer_check_and_lint_for_an_exempt_owner(tmp_path, brand):
    path, _ = _scaffold(tmp_path)
    meta, repo = _meta(tmp_path), tmp_path / "repo"
    ok = run_cli("--format", "json", "--meta", meta, "--repo-dir", repo, "footer", "--check", path)
    assert ok.returncode == 0 and json.loads(ok.stdout)["result"] == "exempt", ok.stdout
    drifted = path.read_text(encoding="utf-8").replace("Get the skill", "Get it")
    path.write_text(drifted, encoding="utf-8")
    bad = run_cli("--format", "json", "--meta", meta, "--repo-dir", repo, "footer", "--check", path)
    assert bad.returncode == 1 and json.loads(bad.stdout)["result"] == "fail:credit-drift"
    path.write_text(footermod.split_credit(drifted)[0], encoding="utf-8")
    missing = run_cli("--format", "json", "--meta", meta, "--repo-dir", repo, "footer", "--check", path)
    assert missing.returncode == 1 and json.loads(missing.stdout)["result"] == "fail:credit-missing"
    lint = run_cli("--format", "json", "--meta", meta, "--repo-dir", repo, "lint", "readme")
    assert "D25 credit fail:credit-missing" in json.loads(lint.stdout)["fails"]


def test_footer_command_output_for_an_exempt_owner(tmp_path, brand):
    p = run_cli("--format", "json", "--meta", _meta(tmp_path), "--no-repo-dir", "footer")
    out = json.loads(p.stdout)
    assert out["result"] == "exempt" and out["logs"] == ["exempt:footer"]
    assert out["credit"] == footermod.credit_block(brand)


def test_held_footer_gets_neither(tmp_path, brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"]["Northwind-Trading-Co"]["footer"] = "hold"
    cfg = tmp_path / "brand.yaml"
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    p = run_cli("--config", cfg, "--format", "json", "--meta", _meta(tmp_path, owner="Northwind-Trading-Co"),
                "--repo-dir", repo, "readme", "--mode", "scaffold")
    diff = json.loads(p.stdout).get("diff", "")
    assert footermod.CREDIT_START not in diff and footermod.START not in diff


def test_estate_footer_owner_keeps_footer_then_credit(tmp_path, brand):
    repo = tmp_path / "repo"
    repo.mkdir()
    p = run_cli("--format", "json", "--meta", _meta(tmp_path, owner="CompleteTech-LLC"), "--repo-dir", repo,
                "readme", "--mode", "scaffold", "--write")
    assert p.returncode == 0, p.stdout
    text = (repo / "README.md").read_text(encoding="utf-8")
    assert text.rstrip().endswith(footermod.block(brand))
    assert text.count(footermod.CREDIT_START) == 1
