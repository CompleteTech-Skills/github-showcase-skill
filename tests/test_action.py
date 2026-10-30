import json
import os
import subprocess

import yaml
import pytest

from conftest import EX, ROOT, run_bash, run_cli


def test_action_contract():
    a = yaml.safe_load((ROOT / "action.yml").read_text())
    assert {"token", "outputs", "readme", "commit", "commit-message", "on-protected", "force", "python-version"} <= set(a["inputs"])
    assert {"changed", "fingerprint"} <= set(a["outputs"]) and a["runs"]["using"] == "composite"
    steps = " ".join(json.dumps(s) for s in a["runs"]["steps"])
    assert "fingerprint --github-output" in steps and "requirements.txt" in steps


def test_fingerprint_changed_flag(tmp_path):
    meta = EX / "meta" / "northwind-support-triage-agent.json"
    out = tmp_path / "gh_out"
    env = dict(os.environ, GITHUB_OUTPUT=str(out))
    p = subprocess.run(["python3" if False else __import__("sys").executable, str(ROOT / "scripts/showcase.py"), "--meta", str(meta),
                        "--repo-dir", str(tmp_path), "fingerprint", "--github-output"], env=env, capture_output=True, text=True)
    assert json.loads(p.stdout)["changed"] is True and "changed=true" in out.read_text()
    run_cli("--meta", meta, "--repo-dir", tmp_path, "banner", "--out", tmp_path / "docs/images/banner.png")
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "fingerprint")
    assert json.loads(p.stdout)["changed"] is False


@pytest.mark.requires_bash
def test_commit_script_dry_run(tmp_path):
    script = ROOT / "scripts" / "action_commit.sh"
    if not script.is_file():
        import pytest
        pytest.skip("action_commit.sh not present")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "init"], check=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e"))
    p = run_bash(script.read_text(encoding="utf-8"), "msg [skip ci]", "fail", cwd=tmp_path,
                 env=dict(os.environ, SHOWCASE_DRY_RUN="1"))
    assert p.returncode == 0, p.stdout + p.stderr
