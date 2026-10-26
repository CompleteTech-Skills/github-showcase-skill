"""Review sweep (core: Action helpers, repository context, metadata, labels CLI, doctor) regressions.

Synthetic Northwind data and brand.yaml's public rows only.

- `action_prepare.py foreign` removes `assets/icon.png` only when the sidecar provably came from another repository
  (a template's sidecar, or another recorded repository id); a renamed or transferred repository keeps its icon.
- The `.github/showcase.yml` `for:` scope, the checkout check and the `adopt` slug check compare owners through the
  shared resolver (CQ-03), so a former login of the org still matches.
- A re-cased owner (an origin URL in lower case) resolves to the org's spelling, so README variants, R9 and R6 match.
- `labels --plan` shares the `org labels` gates (family hold, AI-Ascension, has_issues false); `adopt` refuses a family
  on hold; label job ids come from the operation, not its position.
- A fork whose `parent` is a string is normalized; `.github/showcase.yaml` is captured and validated without a checkout.
- Only watching-org forks are exempt from the icon, banner and footer; the watching org's `.github` needs them, and its
  other non-fork repositories are held until decided explicitly.
"""
import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest
import yaml

from conftest import ROOT, meta_dict, run_cli
from ctshowcase.config import Brand, load_brand
from ctshowcase.context import RepoContext
from ctshowcase.errors import ConfigError
from ctshowcase.meta import MANIFEST_PATHS, normalize

PREP = [sys.executable, str(ROOT / "scripts" / "action_prepare.py")]
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")


def _brand_former(old="Northwind-Old") -> Brand:
    base = load_brand()
    raw = copy.deepcopy(base.raw)
    raw["orgs"]["Northwind-Trading-Co"]["former_slugs"] = [old]
    return Brand(raw, base.path)


def _config_former(tmp_path, old="Northwind-Old"):
    raw = yaml.safe_load((ROOT / "references" / "brand.yaml").read_text(encoding="utf-8"))
    raw["orgs"]["Northwind-Trading-Co"]["former_slugs"] = [old]
    p = tmp_path / "brand-former.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


def _git_checkout(path, origin):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin], check=True)
    return path


def _write_meta(tmp_path, name="meta.json", **kw):
    p = tmp_path / name
    p.write_text(json.dumps(meta_dict(**kw)), encoding="utf-8")
    return p


# -- 1: foreign art never deletes the repository's own icon ------------------------------------------------------------
def _sidecar_repo(tmp_path, **inputs):
    repo = tmp_path / "repo"
    (repo / "docs" / "images").mkdir(parents=True)
    (repo / "assets").mkdir()
    icon = repo / "assets" / "icon.png"
    icon.write_bytes(b"\x89PNG northwind widget icon")
    inp = {"owner": "Northwind-Trading-Co", "repo": "northwind-widget", "type": "cli",
           "icon_sha256": hashlib.sha256(icon.read_bytes()).hexdigest(), **inputs}
    records = {"banner.png": {"sha256": "x"}}
    if "repository_id" in inp:
        records["banner.png"]["repository_id"] = inp.pop("repository_id")
    (repo / "docs" / "images" / ".showcase.json").write_text(json.dumps({"inputs": inp, "outputs": records}))
    (repo / "docs" / "images" / "banner.png").write_bytes(b"own banner")
    return repo, icon


def _foreign(repo, slug, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("GITHUB_REPOSITORY_ID", "SHOWCASE_IS_TEMPLATE")}
    e.update(env)
    p = subprocess.run([*PREP, "foreign", slug], cwd=repo, capture_output=True, text=True, env=e)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip(), p.stderr


def test_renamed_repository_keeps_its_icon(tmp_path):
    repo, icon = _sidecar_repo(tmp_path)
    out, err = _foreign(repo, "Northwind-Trading-Co/northwind-gadget")
    assert icon.is_file(), err  # its own icon (decision 12) is never removed on a slug change alone
    assert out == "false" and "kept" in err


def test_transferred_repository_with_the_same_id_is_not_foreign(tmp_path):
    repo, icon = _sidecar_repo(tmp_path, repository_id=4242)
    out, _ = _foreign(repo, "Northwind-Other/northwind-widget", GITHUB_REPOSITORY_ID="4242")
    assert out == "false" and icon.is_file()


def test_another_recorded_repository_id_is_foreign(tmp_path):
    repo, icon = _sidecar_repo(tmp_path, repository_id=4242)
    out, _ = _foreign(repo, "Northwind-Trading-Co/northwind-copy", GITHUB_REPOSITORY_ID="9999")
    assert out == "true" and not icon.exists()


def test_template_sidecar_is_foreign_and_its_icon_removed(tmp_path):
    repo, icon = _sidecar_repo(tmp_path, repo="northwind-repo-template", type="template")
    out, _ = _foreign(repo, "Northwind-Trading-Co/northwind-new-agent")
    assert out == "true" and not icon.exists()


def test_the_template_itself_is_never_foreign(tmp_path):
    repo, icon = _sidecar_repo(tmp_path, repo="northwind-repo-template", type="template")
    out, _ = _foreign(repo, "Northwind-Trading-Co/northwind-renamed-template", SHOWCASE_IS_TEMPLATE="true")
    assert out == "false" and icon.is_file()


def test_sidecar_records_the_repository_id(tmp_path):
    from types import SimpleNamespace

    import showcase  # noqa: F401 - scripts/ is on sys.path (conftest)
    rd = tmp_path / "r"
    (rd / "docs" / "images").mkdir(parents=True)
    out = rd / "docs" / "images" / "banner.png"
    out.write_bytes(b"x")
    meta = normalize(dict(meta_dict(), id=4242, node_id="R_kgDONorthwind"))
    assert meta["id"] == 4242 and meta["node_id"] == "R_kgDONorthwind"
    ctx = SimpleNamespace(meta=meta, repo_dir=rd, brand=load_brand())
    showcase.maybe_sidecar(ctx, out, {"sha256": "x"})
    side = json.loads((rd / "docs" / "images" / ".showcase.json").read_text())
    assert side["outputs"]["banner.png"]["repository_id"] == 4242
    assert "id" not in side["inputs"]  # the fingerprint inputs are unchanged


# -- 2: `for:` scope through the resolver --------------------------------------------------------------------------------
def _override_dir(tmp_path, scope):
    rd = tmp_path / "ov"
    (rd / ".github").mkdir(parents=True)
    (rd / ".github" / "showcase.yml").write_text(
        f"for: {scope}\ntype: cli\nsubtitle: Inventory dashboards for Northwind stores\n", encoding="utf-8")
    return rd


def test_for_scope_accepts_a_former_login(tmp_path):
    ctx = RepoContext(_brand_former(), normalize(meta_dict(repo="northwind-widget")),
                      _override_dir(tmp_path, "Northwind-Old/northwind-widget"))
    assert ctx.override.get("subtitle") == "Inventory dashboards for Northwind stores"
    assert not any(x.startswith("override-for:") for x in ctx.logs) and "type-config:cli" in ctx.logs


def test_for_scope_still_drops_another_repository(tmp_path):
    ctx = RepoContext(_brand_former(), normalize(meta_dict(repo="northwind-widget")),
                      _override_dir(tmp_path, "Northwind-Old/northwind-repo-template"))
    assert ctx.override == {} and "override-for:Northwind-Old/northwind-repo-template" in ctx.logs


# -- 3: a re-cased owner resolves to the org's spelling ------------------------------------------------------------------
def test_lower_cased_owner_gets_the_skills_variant(brand):
    m = normalize(meta_dict(owner="completetech-skills", repo="northwind-skill", files=["SKILL.md", "README.md"],
                            files_complete=True))
    ctx = RepoContext(brand, m, None)
    assert ctx.owner == "CompleteTech-Skills"
    assert ctx.det["type"] == "agent-skills" and ctx.det["variant"] == "A"


def test_lower_cased_ai_ascension_r6_is_dependencies_only(brand):
    from ctshowcase import doctor
    labels = [{"name": "dependencies", "color": "0366d6", "description": ""}, {"name": "bug", "color": "d73a4a"}]
    ctx = RepoContext(brand, normalize(meta_dict(owner="ai-ascension", repo="demo-widget", labels=labels)), None)
    assert doctor.row(ctx)["cells"]["R6"] == "pass"


def test_rename_is_not_followed_for_the_owner(tmp_path):
    # only the case is fixed: a former login is not rewritten to a login GitHub may not have yet
    ctx = RepoContext(_brand_former(), normalize(meta_dict(owner="Northwind-Old")), None)
    assert ctx.owner == "Northwind-Old"


# -- 4: checkout and adopt slug checks through the resolver -------------------------------------------------------------
def test_checkout_under_a_former_login_is_the_same_repository(tmp_path):
    cfg = _config_former(tmp_path)
    rd = _git_checkout(tmp_path / "co", "https://github.com/Northwind-Old/northwind-widget.git")
    m = _write_meta(tmp_path, repo="northwind-widget")
    p = run_cli("--config", cfg, "--meta", m, "--repo-dir", rd, "topics")
    assert p.returncode in (0, 1), p.stdout + p.stderr
    other = _git_checkout(tmp_path / "co2", "https://github.com/Northwind-Old/northwind-gadget.git")
    p = run_cli("--config", cfg, "--meta", m, "--repo-dir", other, "topics")
    assert p.returncode == 2 and "is a checkout of Northwind-Old/northwind-gadget" in p.stdout


def test_adopt_accepts_metadata_under_the_current_login(tmp_path):
    cfg = _config_former(tmp_path)
    m = _write_meta(tmp_path, repo="northwind-widget", labels=[{"name": "bug", "color": "d73a4a"}])
    p = run_cli("--config", cfg, "--no-repo-dir", "--meta", m, "adopt", "Northwind-Old/northwind-widget")
    assert p.returncode == 0, p.stdout + p.stderr
    p = run_cli("--config", cfg, "--no-repo-dir", "--meta", m, "adopt", "Northwind-Old/northwind-gadget")
    assert p.returncode == 2


# -- 5: labels --plan shares the org labels gates; adopt refuses a family on hold ---------------------------------------
LIVE = [{"name": "bug", "color": "d73a4a", "description": ""}, {"name": "enhancement", "color": "a2eeef", "description": ""}]


def _labels(tmp_path, *extra, **kw):
    m = _write_meta(tmp_path, f"m-{kw.get('owner', 'x')}-{kw.get('repo', 'r')}.json",
                    **{"repo": "demo-widget", "labels": LIVE, "files": ["README.md"], "files_complete": True,
                       "has_issues": True, **kw})
    return run_cli("--no-repo-dir", "--meta", m, "labels", "--plan", *extra)


def test_labels_plan_ai_ascension_is_dependencies_only(tmp_path):
    p = _labels(tmp_path, owner="AI-Ascension")
    out = json.loads(p.stdout)
    assert [j["argv"][:4] for j in out["jobs"]] == [["gh", "label", "create", "dependencies"]], out["jobs"]


def test_labels_plan_refuses_a_family_on_hold(tmp_path):
    p = _labels(tmp_path, owner="TouchedByAnAgent")
    assert p.returncode == 2 and "hold" in p.stdout and '"jobs"' not in p.stdout


def test_labels_plan_skips_has_issues_false(tmp_path):
    p = _labels(tmp_path, has_issues=False)
    out = json.loads(p.stdout)
    assert out["result"] == "n/a" and "has_issues:false" in out["logs"] and p.returncode == 0
    p = _labels(tmp_path, repo=".github", has_issues=False)  # .github always gets the standard set
    assert json.loads(p.stdout).get("jobs")


def test_adopt_refuses_a_family_on_hold(tmp_path):
    m = _write_meta(tmp_path, owner="TouchedByAnAgent", repo="demo-widget", labels=LIVE)
    p = run_cli("--no-repo-dir", "--meta", m, "adopt", "TouchedByAnAgent/demo-widget")
    assert p.returncode == 2 and '"jobs"' not in p.stdout


# -- 6: content-derived label job ids -------------------------------------------------------------------------------------
def test_label_job_ids_follow_the_operation(tmp_path):
    a = json.loads(_labels(tmp_path).stdout)["jobs"]
    b = json.loads(_labels(tmp_path).stdout)["jobs"]
    assert [j["id"] for j in a] == [j["id"] for j in b]  # deterministic for identical plans
    assert len({j["id"] for j in a}) == len(a)
    # a later plan whose first job is another operation never reuses an id with different content
    later = [{"name": "type:bug", "color": "000000", "description": ""}, *LIVE]
    c = json.loads(_labels(tmp_path, labels=later).stdout)["jobs"]
    by_id = {j["id"]: j for j in a}
    for j in c:
        assert j["id"] not in by_id or by_id[j["id"]]["argv"] == j["argv"], j["id"]
    import re
    assert all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,199}", j["id"]) for j in a + c)


# -- 8: a string parent ---------------------------------------------------------------------------------------------------
def test_string_parent_is_normalized(tmp_path):
    m = normalize(meta_dict(fork=True, parent="Contoso-Upstream/support-triage-agent"))
    assert m["parent"] == {"full_name": "Contoso-Upstream/support-triage-agent", "default_branch": None, "topics": []}
    mp = _write_meta(tmp_path, fork=True, parent="Contoso-Upstream/support-triage-agent",
                     labels=[{"name": "bug", "color": "d73a4a"}])
    for cmd in (["topics"], ["doctor"], ["adopt", "Northwind-Trading-Co/support-triage-agent"]):
        p = run_cli("--no-repo-dir", "--meta", mp, *cmd)
        assert "Traceback" not in p.stderr, (cmd, p.stderr)


# -- 9: `.github/showcase.yaml` without a checkout --------------------------------------------------------------------------
def test_showcase_yaml_is_captured_and_read_without_a_checkout(brand):
    assert ".github/showcase.yaml" in MANIFEST_PATHS
    m = normalize(meta_dict(files=["README.md", ".github/showcase.yaml"], files_complete=True,
                            manifests={".github/showcase.yaml": "type: api\n"}))
    assert RepoContext(brand, m, None).det["type"] == "api"


def test_manifest_override_is_validated(brand):
    m = normalize(meta_dict(manifests={".github/showcase.yml": "- not\n- a mapping\n"}))
    with pytest.raises(ConfigError):
        RepoContext(brand, m, None)
    m = normalize(meta_dict(manifests={".github/showcase.yml": "colors: {title: '#ffffff'}\n"}))
    with pytest.raises(ConfigError):
        RepoContext(brand, m, None)


# -- 10: watching org: forks only --------------------------------------------------------------------------------------------
W = "romgenie-following-repos"


def test_watching_fork_stays_exempt(brand):
    ctx = RepoContext(brand, normalize(meta_dict(owner=W, repo="northwind-agent-kit", fork=True)), None)
    assert ctx.art_status()["icon"] == "exempt:watching-fork" and ctx.footer_status() == "exempt:watching-fork"


def test_watching_dot_github_needs_icon_banner_footer(brand, tmp_path):
    from ctshowcase import doctor
    ctx = RepoContext(brand, normalize(meta_dict(owner=W, repo=".github")), None)
    st = ctx.art_status()
    assert st["icon"] is None and st["banner"] is None and ctx.footer_status() is None
    rd = tmp_path / "dg"
    rd.mkdir()
    (rd / "README.md").write_text("# .github\n", encoding="utf-8")
    cells = doctor.row(RepoContext(brand, normalize(meta_dict(owner=W, repo=".github")), rd))["cells"]
    assert cells["icon"] == "fail" and cells["banner"] == "fail" and cells["footer"] == "fail"


def test_watching_non_fork_is_held_until_decided(brand, tmp_path):
    ctx = RepoContext(brand, normalize(meta_dict(owner=W, repo="northwind-notes-kit")), None)
    st = ctx.art_status()
    assert st["icon"] == st["banner"] == "hold:watching-non-fork" and ctx.footer_status() == "hold:watching-non-fork"
    m = _write_meta(tmp_path, owner=W, repo="northwind-notes-kit")
    p = run_cli("--no-repo-dir", "--meta", m, "--format", "json", "banner", "--out", tmp_path / "b.png")
    assert p.returncode == 2 and "hold:watching-non-fork" in p.stdout and not (tmp_path / "b.png").exists()
