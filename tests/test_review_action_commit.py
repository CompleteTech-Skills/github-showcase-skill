"""Review regression: the Action commit lands the removal of a template icon (decision 12), and nothing else extra."""
import hashlib
import json
import os
import subprocess
import sys

from conftest import ROOT

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e",
           SHOWCASE_DRY_RUN="1")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=ENV).stdout


def _template_copy(repo):
    """A new Northwind repository created from the template: banner, sidecar and the template's icon all copied."""
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "docs" / "images").mkdir(parents=True)
    (repo / "assets").mkdir()
    icon = repo / "assets" / "icon.png"
    icon.write_bytes(b"\x89PNG template icon")
    sidecar = {"inputs": {"owner": "Northwind-Trading", "repo": "northwind-repo-template", "type": "template",
                          "icon_sha256": hashlib.sha256(icon.read_bytes()).hexdigest()},
               "outputs": {"banner.png": {}}}
    (repo / "docs" / "images" / ".showcase.json").write_text(json.dumps(sidecar))
    (repo / "docs" / "images" / "banner.png").write_bytes(b"template banner")
    (repo / "README.md").write_text("# northwind-support-triage-agent\n")
    (repo / "notes.txt").write_text("user file\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


def _prepare_and_commit(repo):
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "action_prepare.py"), "foreign",
                        "Northwind-Trading/northwind-support-triage-agent"], cwd=repo, capture_output=True, text=True)
    assert p.stdout.strip() == "true", p.stdout + p.stderr
    (repo / "docs" / "images" / "banner.png").write_bytes(b"own banner")  # the regenerated art
    p = subprocess.run(["bash", str(ROOT / "scripts" / "action_commit.sh"), "docs: regenerate [skip ci]", "fail"],
                       cwd=repo, capture_output=True, text=True, env=ENV)
    assert p.returncode == 0, p.stdout + p.stderr


def test_template_icon_removal_is_committed(tmp_path):
    repo = tmp_path / "repo"
    _template_copy(repo)
    _prepare_and_commit(repo)
    assert _git(repo, "status", "--porcelain") == ""  # no " D assets/icon.png" left behind
    assert _git(repo, "ls-tree", "--name-only", "HEAD", "assets/") == ""  # HEAD no longer carries the template icon


def test_only_the_icon_deletion_is_swept(tmp_path):
    repo = tmp_path / "repo"
    _template_copy(repo)
    (repo / "notes.txt").write_text("edited\n")
    (repo / "scratch.txt").write_text("untracked\n")
    _prepare_and_commit(repo)
    changed = _git(repo, "show", "--name-status", "--format=", "HEAD").split("\n")
    assert sorted(x for x in changed if x) == ["D\tassets/icon.png", "M\tdocs/images/banner.png"]
    assert _git(repo, "status", "--porcelain").splitlines() == [" M notes.txt", "?? scratch.txt"]


def test_own_icon_is_kept_and_unstaged_edits_untouched(tmp_path):
    repo = tmp_path / "repo"
    _template_copy(repo)
    (repo / "assets" / "icon.png").write_bytes(b"\x89PNG own icon, edited in the checkout")  # not the template's
    _prepare_and_commit(repo)
    assert (repo / "assets" / "icon.png").is_file()
    assert _git(repo, "status", "--porcelain").splitlines() == [" M assets/icon.png"]  # a modification is never staged
