"""Red-team round: `meta --from-gh` records CQ-16 recency, takes --allow-t3 after sign-off, and `--meta-dir` is recursive.
Synthetic data only; `gh` is a local stub that answers read-only GETs."""
import json
import os
import stat
import sys

from conftest import ROOT

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


def _stub_gh(tmp_path, owner, repo):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / "repo.json").write_text(json.dumps({"name": repo, "full_name": f"{owner}/{repo}", "owner": {"login": owner},
                                                "private": False, "visibility": "public", "default_branch": "main",
                                                "pushed_at": "2026-10-06T00:00:00Z"}))
    (data / "commits.json").write_text(json.dumps(COMMITS))
    script = bin_dir / "gh"
    script.write_text(f"""#!{sys.executable}
import sys
args = sys.argv[1:]
if "-X" in args and args[args.index("-X") + 1] != "GET":
    sys.exit(9)
path = [a for a in args if a.startswith("repos/")][0]
d = {str(data)!r}
if path == "repos/{owner}/{repo}":
    print(open(d + "/repo.json").read())
elif "/commits?" in path:
    print(open(d + "/commits.json").read())
else:
    sys.exit(1)
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")


def test_meta_from_gh_t3_needs_allow_t3_and_records_recency(tmp_path):
    import subprocess
    env = _stub_gh(tmp_path, "Pick-Your-AI", "core")
    cmd = [sys.executable, str(ROOT / "scripts" / "showcase.py"), "meta", "--from-gh", "Pick-Your-AI/core"]
    refused = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    out = tmp_path / "m.json"
    ok = subprocess.run(cmd + ["--allow-t3", "--out", str(out)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    m = json.loads(out.read_text())
    assert m["last_substantive_commit"] == "2025-03-01T12:00:00Z" and m["pushed_at"] == "2026-10-06T00:00:00Z"


def test_load_metas_is_recursive(tmp_path, brand):
    from ctshowcase.resolver import Resolver
    (tmp_path / "Old-Org").mkdir()
    (tmp_path / "Old-Org" / "moved.json").write_text(json.dumps({"owner": "Old-Org", "repo": "moved", "visibility": "public"}))
    (tmp_path / "top.json").write_text(json.dumps({"owner": "New-Org", "repo": "top", "visibility": "public"}))
    est = O.Estate(brand, Resolver(brand, {"orgs": {}}, None))
    assert O.load_metas(tmp_path, est) == 2
    assert est.meta("Old-Org/moved") is not None
