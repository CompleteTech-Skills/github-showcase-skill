"""Red-team round: `meta --from-gh` records CQ-16 recency, takes --allow-t3 after sign-off, and `--meta-dir` is recursive.
Synthetic data only; the subprocess transport stub answers read-only GETs on every platform."""
import json
import subprocess

import showcase

from ctshowcase import meta as M
from ctshowcase import org as O

COMMITS = [
    {"sha": "c3", "commit": {"message": "docs: ct-std-v1 README [skip ci]", "committer": {"date": "2026-10-20T00:00:00Z"}}},
    {"sha": "c2", "commit": {"message": "Add showcase banner and card", "committer": {"date": "2026-10-19T00:00:00Z"}}},
    {"sha": "c1", "commit": {"message": "Fix the parser", "committer": {"date": "2025-03-01T12:00:00Z"}}},
]


def test_last_substantive_skips_estate_commits():
    assert M.last_substantive(COMMITS) == ("2025-03-01T12:00:00Z", "c1")
    assert M.last_substantive(COMMITS[:2]) is None
    assert M.last_substantive(None) is None


def test_normalize_keeps_recency_fields():
    m = M.normalize({"owner": "Northwind-Trading-Co", "repo": "x", "private": False, "pushed_at": "2026-10-06T00:00:00Z",
                     "last_substantive_commit": "2025-03-01T12:00:00Z", "last_substantive_sha": "c1"})
    assert m["pushed_at"] == "2026-10-06T00:00:00Z"
    assert m["last_substantive_commit"] == "2025-03-01T12:00:00Z" and m["last_substantive_sha"] == "c1"


def _stub_gh(monkeypatch, owner, repo):
    requests = []
    repo_data = {"name": repo, "full_name": f"{owner}/{repo}", "owner": {"login": owner},
                 "private": False, "visibility": "public", "default_branch": "main",
                 "pushed_at": "2026-10-06T00:00:00Z"}

    def run(argv, **kwargs):
        assert argv[:4] == ["gh", "api", "-X", "GET"], argv
        assert kwargs["capture_output"] and kwargs["text"] and kwargs["timeout"] == 60
        path = argv[4]
        requests.append(path)
        data = repo_data if path == f"repos/{owner}/{repo}" else COMMITS if "/commits?" in path else None
        return subprocess.CompletedProcess(argv, 0 if data is not None else 1,
                                           json.dumps(data) if data is not None else "", "")

    monkeypatch.setattr(M.subprocess, "run", run)
    return requests


def test_meta_from_gh_t3_needs_allow_t3_and_records_recency(tmp_path, monkeypatch, capsys, t3_record):
    requests = _stub_gh(monkeypatch, "Pick-Your-AI", "core")
    cmd = ["meta", "--from-gh", "Pick-Your-AI/core"]
    assert showcase.main(cmd) == 2
    refused = json.loads(capsys.readouterr().out)
    assert refused["result"] == "refused" and any("t3-signoff" in code for code in refused["logs"])
    out = tmp_path / "m.json"
    assert showcase.main(cmd + ["--allow-t3", "--out", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "ok"
    m = json.loads(out.read_text(encoding="utf-8"))
    assert m["last_substantive_commit"] == "2025-03-01T12:00:00Z" and m["pushed_at"] == "2026-10-06T00:00:00Z"
    assert "repos/Pick-Your-AI/core/commits?sha=main&per_page=100" in requests


def test_load_metas_is_recursive(tmp_path, brand):
    from ctshowcase.resolver import Resolver
    (tmp_path / "Old-Org").mkdir()
    (tmp_path / "Old-Org" / "moved.json").write_text(json.dumps({"owner": "Old-Org", "repo": "moved", "visibility": "public"}))
    (tmp_path / "top.json").write_text(json.dumps({"owner": "New-Org", "repo": "top", "visibility": "public"}))
    est = O.Estate(brand, Resolver(brand, {"orgs": {}}, None))
    assert O.load_metas(tmp_path, est) == 2
    assert est.meta("Old-Org/moved") is not None
