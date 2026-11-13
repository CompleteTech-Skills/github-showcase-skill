import json
from types import SimpleNamespace

import pytest

from ctshowcase.errors import NeedsInput, ShowcaseError
from ctshowcase.formatting import discover, format_text


def test_discovery_is_read_only_and_reports_sources(tmp_path):
    (tmp_path / ".prettierrc.json").write_text('{}')
    (tmp_path / ".editorconfig").write_text('root = true')
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"lint": "never-execute-this", "start": "server"}}))
    (tmp_path / "AGENTS.md").write_text('```bash\npython -m pytest\n```\n')
    workflow = tmp_path / ".github/workflows/check.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text('jobs:\n  checks:\n    steps:\n      - run: make verify\n')
    result = discover(tmp_path)
    assert result["formatters"] == [".prettierrc.json", ".editorconfig"]
    assert [v["command"] for v in result["validators"]] == ["never-execute-this", "python -m pytest", "make verify"]
    assert all(v["status"] == "not run" for v in result["validators"])


def local_prettier(tmp_path, version="3.6.2", pin="3.6.2"):
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"prettier": pin}}))
    p = tmp_path / "node_modules/prettier"
    p.mkdir(parents=True)
    (p / "package.json").write_text(json.dumps({"version": version, "bin": "bin/prettier.cjs"}))
    (p / "bin").mkdir()
    (p / "bin/prettier.cjs").write_text('')


@pytest.mark.parametrize("pin,version", [("^3.6.2", "3.6.2"), ("3.6.2", "3.0.0")])
def test_formatter_refuses_unpinned_or_mismatched_install(tmp_path, pin, version):
    local_prettier(tmp_path, version=version, pin=pin)
    with pytest.raises(NeedsInput):
        format_text(tmp_path, tmp_path / "README.md", "content")


def test_formatter_uses_stdin_local_exact_version_without_shell(tmp_path, monkeypatch):
    local_prettier(tmp_path)
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    called = []

    def run(argv, **kwargs):
        called.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="# Formatted\n", stderr="")

    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", run)
    assert format_text(tmp_path, tmp_path / "README.md", "# Formatted") == "# Formatted\n"
    argv, kwargs = called[0]
    assert argv[0] == "/node" and argv[-2:] == ["--stdin-filepath", "README.md"]
    assert kwargs["input"] == "# Formatted" and not kwargs.get("shell")
    assert not (tmp_path / "README.md").exists()


def test_formatter_refuses_external_destination(tmp_path):
    with pytest.raises(ShowcaseError):
        format_text(tmp_path, tmp_path.parent / "README.md", "content")


def test_formatter_does_not_execute_escaping_package_bin(tmp_path):
    local_prettier(tmp_path)
    package = tmp_path / "node_modules/prettier/package.json"
    package.write_text(json.dumps({"version": "3.6.2", "bin": "../../outside.js"}))
    with pytest.raises(NeedsInput):
        format_text(tmp_path, tmp_path / "README.md", "content")


def test_malformed_metadata_is_reported_without_crash(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": [], "dependencies": "bad"}')
    assert discover(tmp_path)["validators"] == []


def test_npm_lock_pin_is_supported(tmp_path, monkeypatch):
    local_prettier(tmp_path, pin="^3.6.2")
    (tmp_path / "package-lock.json").write_text(json.dumps({"packages": {"node_modules/prettier": {"version": "3.6.2"}}}))
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    assert format_text(tmp_path, tmp_path / "README.md", "ok") == "ok"
