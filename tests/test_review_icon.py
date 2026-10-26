"""Review 4373670969: `content icon` exempts only watching-org forks and a placeholder org's `.github` (decision 12).

Forks outside the watching org, backups and `.github` repositories need their own icon, the same as
RepoContext.art_status() and the doctor `icon` column say. Synthetic Northwind data only."""
import json

from conftest import ROOT, meta_dict
from test_content import NO_ESTATE, NW, _candidate, run_content

from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

FIX = ROOT / "tests" / "fixtures" / "content"
ART = ("--art-direction", FIX / "ART_DIRECTION.min.md")


def _meta(tmp_path, name="meta.json", **kw):
    p = tmp_path / name
    p.write_text(json.dumps(meta_dict(**kw)))
    return p


def test_in_scope_fork_icon_is_not_exempt(capsys, tmp_path, brand):
    meta = _meta(tmp_path, repo="upstream-fork", fork=True)
    assert RepoContext(brand, normalize(json.loads(meta.read_text())), None).art_status()["icon"] is None
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "prompt", *ART, *NO_ESTATE)
    assert res["result"] != "exempt" and res["result"] == "needs-writer" and code == 1, res
    card = brand.style(NW)["tokens"]["card_fill"]
    src, out = tmp_path / "cand.png", tmp_path / "repo" / "assets" / "icon.png"
    _candidate(card).save(src)
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "normalize", "--in", src,
                            "--out", out, *ART, *NO_ESTATE)
    assert code == 0 and res["result"] == "pass" and out.is_file(), res
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "check", "--out", out,
                            *ART, *NO_ESTATE)
    assert code == 0 and res["result"] == "pass", res
    missing = tmp_path / "none" / "icon.png"
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "check", "--out", missing,
                            *ART, *NO_ESTATE)
    assert code == 1 and res["result"] == "fail" and "needs-input:repo-icon" in res["logs"], res


def test_backup_and_dot_github_need_an_icon(capsys, tmp_path):
    for repo in ("ledger-sync-backup-20240101", ".github"):
        meta = _meta(tmp_path, repo=repo)
        code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "prompt", *ART, *NO_ESTATE)
        assert res["result"] == "needs-writer", (repo, res)


def test_watching_org_fork_stays_exempt(capsys, tmp_path):
    meta = _meta(tmp_path, owner="romgenie-following-repos", repo="up-fork", fork=True)
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "prompt", *NO_ESTATE)
    assert code == 0 and res["result"] == "exempt" and res["logs"] == ["exempt:watching-fork"], res


def test_placeholder_org_dot_github_stays_exempt(capsys, tmp_path):
    reg = tmp_path / "registry.yaml"
    reg.write_text((FIX / "registry.min.yaml").read_text()
                   + "placeholders:\n  - {login: Northwind-Old, successor: Northwind-Trading-Co}\n")
    args = [a if a != FIX / "registry.min.yaml" else reg for a in NO_ESTATE]
    meta = _meta(tmp_path, owner="Northwind-Old", repo=".github")
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "prompt", *args)
    assert code == 0 and res["result"] == "exempt" and res["logs"] == ["exempt:placeholder-org"], res
    # the successor's own `.github` is not a placeholder and needs an icon
    meta = _meta(tmp_path, "succ.json", repo=".github")
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "prompt", *ART, *args)
    assert res["result"] == "needs-writer", res
