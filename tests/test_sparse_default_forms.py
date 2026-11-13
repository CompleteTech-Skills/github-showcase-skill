"""A missing indexed default form is unknown, not proof that a label rename is safe."""

import json
import subprocess

import pytest

from conftest import meta_dict, run_cli


OWNER = "Northwind-Trading-Co"
FORM_PATHS = (".github/ISSUE_TEMPLATE/bug.yml", "ISSUE_TEMPLATE/bug.yml", "docs/ISSUE_TEMPLATE/bug.yml")
LIVE = [{"name": "bug", "color": "d73a4a", "description": "Bug report"}]


def git(directory, *args):
    return subprocess.run(
        ["git", "-C", str(directory), *args], check=True, capture_output=True, text=True, encoding="utf-8"
    )


def checkout(directory, name):
    directory.mkdir(parents=True)
    git(directory, "init", "-q")
    git(directory, "remote", "add", "origin", f"https://github.com/{OWNER}/{name}.git")
    return directory


def default_checkout(tmp_path, relative, missing):
    directory = checkout(tmp_path / OWNER / ".github", ".github")
    form = directory / relative
    form.parent.mkdir(parents=True)
    form.write_text("name: Bug\nlabels: [bug]\n", encoding="utf-8")
    (directory / "src").mkdir()
    (directory / "src" / "app.py").write_text("pass\n", encoding="utf-8")
    git(directory, "add", ".")
    git(
        directory, "-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"
    )
    if missing == "sparse":
        git(directory, "sparse-checkout", "init", "--cone")
        git(directory, "sparse-checkout", "set", "src")
    else:
        form.unlink()
    assert not form.exists()
    return directory, form


def assert_held(result):
    assert not any("--name" in argv for argv in result.get("argv", [])), result
    assert not any("--name" in job.get("argv", []) for job in result.get("jobs", [])), result
    assert "needs-input:label-references" in result["logs"], result


@pytest.mark.parametrize("relative", FORM_PATHS)
@pytest.mark.parametrize("missing", ["sparse", "deleted"])
def test_direct_labels_holds_missing_indexed_org_form(tmp_path, relative, missing):
    defaults, form = default_checkout(tmp_path, relative, missing)
    member = checkout(tmp_path / "member", "support-triage-agent")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(labels=LIVE, files=[], files_complete=True)), encoding="utf-8")
    args = ("--meta", meta, "--repo-dir", member, "labels", "--plan", "--org-defaults", defaults)
    process = run_cli(*args)
    result = json.loads(process.stdout)
    assert process.returncode == 1, process.stderr
    assert_held(result)
    assert any(relative in path for row in result["needs_checkout"] for path in row["check_files"])
    if missing == "sparse":
        git(defaults, "sparse-checkout", "disable")
    else:
        git(defaults, "restore", "--", relative)
    visible = json.loads(run_cli(*args).stdout)
    assert "label-rewrite-first" in visible["logs"]
    form.write_text("name: Bug\nlabels: ['type:bug']\n", encoding="utf-8")
    repaired = json.loads(run_cli(*args).stdout)
    assert any(argv[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for argv in repaired["argv"])


@pytest.mark.parametrize("relative", FORM_PATHS)
@pytest.mark.parametrize("missing", ["sparse", "deleted"])
def test_org_labels_holds_missing_own_default_form(tmp_path, relative, missing):
    defaults, form = default_checkout(tmp_path, relative, missing)
    registry = tmp_path / "registry.yaml"
    registry.write_text(f"orgs:\n  {OWNER}:\n    tier: T1\n    final_repos: [.github]\n", encoding="utf-8")
    metadata = tmp_path / "meta"
    metadata.mkdir()
    (metadata / "default.json").write_text(
        json.dumps(meta_dict(repo=".github", labels=LIVE, files=[relative], files_complete=True)), encoding="utf-8"
    )
    args = (
        "org",
        "labels",
        OWNER,
        "--registry",
        registry,
        "--meta-dir",
        metadata,
        "--checkouts",
        tmp_path,
        "--dot-github",
        defaults,
    )
    process = run_cli(*args)
    result = json.loads(process.stdout)
    assert_held(result)
    assert result["repos"][0]["result"] == "needs-input"
    if missing == "sparse":
        git(defaults, "sparse-checkout", "disable")
    else:
        git(defaults, "restore", "--", relative)
    form.write_text("name: Bug\nlabels: ['type:bug']\n", encoding="utf-8")
    repaired = json.loads(run_cli(*args).stdout)
    assert any(
        job.get("argv", [])[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for job in repaired["jobs"]
    )


@pytest.mark.parametrize("relative", FORM_PATHS)
@pytest.mark.parametrize("source", ["index", "capture"])
def test_direct_github_labels_preserves_index_and_capture_holds(tmp_path, relative, source):
    """The defaults source is the target itself; a capture can name files absent from its index."""
    defaults, _ = default_checkout(tmp_path, relative, "deleted")
    if source == "capture":
        git(defaults, "rm", "--cached", relative)
    meta = tmp_path / "meta.json"
    meta.write_text(
        json.dumps(meta_dict(repo=".github", labels=LIVE, files=[relative], files_complete=True)), encoding="utf-8"
    )
    args = ("--meta", meta, "--repo-dir", defaults, "labels", "--plan")
    process = run_cli(*args)
    result = json.loads(process.stdout)
    assert process.returncode == 1, process.stderr
    assert_held(result)
    assert any(relative in path for row in result["needs_checkout"] for path in row["check_files"])
    form = defaults / relative
    form.write_text("name: Bug\nlabels: ['type:bug']\n", encoding="utf-8")
    repaired = json.loads(run_cli(*args).stdout)
    assert any(argv[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for argv in repaired["argv"])


@pytest.mark.parametrize("relative", FORM_PATHS)
@pytest.mark.parametrize("missing", ["sparse", "deleted", "capture"])
@pytest.mark.parametrize("mode", ["direct", "org"])
def test_visible_sibling_never_hides_missing_own_default_form(tmp_path, relative, missing, mode):
    defaults, form = default_checkout(tmp_path, relative, "deleted")
    git(defaults, "restore", "--", relative)
    sibling = defaults / ".github/ISSUE_TEMPLATE/question.yml"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_text("name: Question\nlabels: ['type:question']\n", encoding="utf-8")
    git(defaults, "add", ".")
    git(defaults, "-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "visible sibling")
    if missing == "sparse":
        git(defaults, "sparse-checkout", "set", "--no-cone", "/*", "!/" + relative)
    else:
        form.unlink()
        if missing == "capture":
            git(defaults, "rm", "--cached", relative)
    assert sibling.is_file() and not form.exists()
    capture = meta_dict(repo=".github", labels=LIVE,
                        files=[relative, ".github/ISSUE_TEMPLATE/question.yml"], files_complete=True)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(capture), encoding="utf-8")
    if mode == "direct":
        args = ("--meta", meta, "--repo-dir", defaults, "labels", "--plan")
    else:
        registry = tmp_path / "registry.yaml"
        registry.write_text(f"orgs:\n  {OWNER}:\n    tier: T1\n    final_repos: [.github]\n", encoding="utf-8")
        metadata = tmp_path / "meta"
        metadata.mkdir()
        (metadata / "default.json").write_text(json.dumps(capture), encoding="utf-8")
        args = ("org", "labels", OWNER, "--registry", registry, "--meta-dir", metadata,
                "--checkouts", tmp_path, "--dot-github", defaults)
    result = json.loads(run_cli(*args).stdout)
    assert_held(result)
    checks = result.get("needs_checkout", []) if mode == "direct" else result["repos"][0].get("needs_checkout", [])
    assert any(relative in path for row in checks for path in row["check_files"]), result
    if missing == "sparse":
        git(defaults, "sparse-checkout", "disable")
    form.parent.mkdir(parents=True, exist_ok=True)
    form.write_text("name: Bug\nlabels: ['type:bug']\n", encoding="utf-8")
    repaired = json.loads(run_cli(*args).stdout)
    jobs = repaired.get("argv", []) if mode == "direct" else [j.get("argv", []) for j in repaired["jobs"]]
    assert any(argv[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for argv in jobs)


def test_incomplete_inherited_defaults_do_not_override_complete_member_forms(tmp_path):
    from ctshowcase import labels
    defaults, _ = default_checkout(tmp_path, FORM_PATHS[0], "deleted")
    member = checkout(tmp_path / "member", "support-triage-agent")
    own = member / ".github/ISSUE_TEMPLATE/question.yml"
    own.parent.mkdir(parents=True)
    own.write_text("name: Question\nlabels: ['type:question']\n", encoding="utf-8")
    source = labels.defaults_for(OWNER, "support-triage-agent", path=defaults)
    ops, logs = labels.plan(LIVE, member, defaults=source)
    assert any(op["op"] == "rename" and op["name"] == "bug" for op in ops)
    assert "needs-input:label-references" not in logs
