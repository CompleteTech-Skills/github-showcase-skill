"""Platform boundary regressions: UTF-8 transport and an actual local Action shell."""
import locale
import json
import os
import subprocess
from pathlib import Path

import pytest

import conftest


def test_cli_capture_decodes_utf8_even_with_legacy_locale(monkeypatch):
    monkeypatch.setattr(locale, "getencoding", lambda: "cp1252")
    result = conftest.run_cli("footer", "--raw")
    assert result.returncode == 0, result.stderr
    assert " · Innovation at Every Integration" in result.stdout
    assert "Â·" not in result.stdout


def test_windows_bash_comes_from_git_not_the_wsl_launcher(tmp_path, monkeypatch):
    git = tmp_path / "Git With Spaces" / "cmd" / "git.exe"
    bash = git.parent.parent / "bin" / "bash.exe"
    git.parent.mkdir(parents=True)
    bash.parent.mkdir()
    git.touch()
    bash.touch()
    monkeypatch.setattr(conftest.shutil, "which", lambda name: str(git) if name == "git" else "C:/Windows/bash.exe")
    assert Path(conftest.find_bash(windows=True)) == bash
    bash.unlink()
    assert conftest.find_bash(windows=True) is None


@pytest.mark.parametrize(("git_relative", "installation_relative"), [
    ("scoop with spaces/shims/git.exe", "scoop with spaces/apps/git/current"),
    ("Git With Spaces/mingw64/bin/git.exe", "Git With Spaces"),
], ids=["scoop-shim", "mingw64-bin"])
def test_windows_bash_follows_git_exec_path(tmp_path, monkeypatch, git_relative, installation_relative):
    shim = tmp_path / git_relative
    installation = tmp_path / installation_relative
    bash = installation / "bin" / "bash.exe"
    shim.parent.mkdir(parents=True)
    shim.touch()
    bash.parent.mkdir(parents=True)
    bash.touch()
    monkeypatch.setattr(conftest.shutil, "which", lambda name: str(shim) if name == "git" else "C:/Windows/bash.exe")
    calls = []

    def git_exec_path(argv, **kwargs):
        calls.append(argv)
        assert kwargs["timeout"] == 10
        return subprocess.CompletedProcess(argv, 0, str(installation / "mingw64/libexec/git-core") + "\n", "")

    monkeypatch.setattr(conftest.subprocess, "run", git_exec_path)
    assert Path(conftest.find_bash(windows=True)) == bash
    assert calls == [[str(shim), "--exec-path"]]


@pytest.mark.requires_bash
def test_shell_stdin_preserves_quotes_expansion_and_spaced_paths(tmp_path):
    cwd = tmp_path / "work tree"
    cwd.mkdir()
    env = dict(os.environ, SAMPLE="a quoted value", GITHUB_ACTION_PATH=str(cwd))
    result = conftest.run_bash(
        'set -eu\nprintf "%s\\n" "$SAMPLE"\n'
        'printf "%s\\n" "$(printf \'nested "quotes"\')"\n'
        'test -d "$GITHUB_ACTION_PATH"\n', cwd=cwd, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == ["a quoted value", 'nested "quotes"']


@pytest.mark.parametrize("arguments", [
    ["--kind", "card", "first.svg"],
    ["first.svg", "--kind", "card"],
    ["first.svg", "--kind", "card", "second.svg"],
])
def test_lint_accepts_files_around_options_on_supported_pythons(tmp_path, arguments):
    result = conftest.run_cli("lint", "svg", *arguments, cwd=tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    reports = [json.loads(line) for line in result.stdout.splitlines()]
    assert [Path(row["file"]).name for row in reports] == [arg for arg in arguments if arg.endswith(".svg")]
    assert all(row["fails"] == ["missing"] for row in reports)


def test_lint_still_rejects_unknown_options():
    result = conftest.run_cli("lint", "svg", "--bogus", "first.svg")
    assert result.returncode == 2 and "unrecognized arguments" in result.stderr
