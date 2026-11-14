"""Opt-in target formatting preserves default behavior and fails before writes."""
import importlib.util
import json
from pathlib import Path

from ctshowcase.errors import NeedsInput
from conftest import ROOT, meta_dict, run_cli


def target(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(files=["main.py"])), encoding="utf-8")
    return repo, meta


def test_missing_pinned_formatter_refuses_readme_without_writes(tmp_path):
    repo, meta = target(tmp_path)
    original = "# Authored title\n\nAuthored paragraph.\n"
    (repo / "README.md").write_text(original, encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--write", "--format-generated")
    assert result.returncode == 4, result.stderr
    assert "needs-input:formatter" in json.loads(result.stdout)["logs"]
    assert (repo / "README.md").read_text(encoding="utf-8") == original
    assert not (repo / "docs").exists()


def test_doctor_exposes_declared_validation_without_execution(tmp_path):
    repo, meta = target(tmp_path)
    (repo / "package.json").write_text(json.dumps({"scripts": {"lint": "do-not-execute-this"}}), encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", repo, "doctor", "--format", "json")
    payload = json.loads(result.stdout)
    assert payload["tooling"]["validators"] == [
        {"source": "package.json#scripts.lint", "command": "do-not-execute-this", "status": "not run"}]


def test_doctor_default_reports_tooling_without_running_it(tmp_path):
    repo, meta = target(tmp_path)
    (repo / ".prettierrc.json5").write_text("{}", encoding="utf-8")
    (repo / "AGENTS.md").write_text("Run `python -m pytest -q` before submitting.\n", encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", repo, "doctor")
    assert "Tooling preflight (not run)" in result.stderr
    assert ".prettierrc.json5" in result.stderr and "python -m pytest -q" in result.stderr
    assert len(result.stdout.strip().splitlines()) == 1


def test_no_regroup_cannot_silently_reformat_outside_bytes(tmp_path):
    repo, meta = target(tmp_path)
    original = "# Exact title\r\n\r\n  Authored text.\r\n"
    (repo / "README.md").write_bytes(original.encode())
    result = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--write", "--no-regroup", "--format-generated")
    assert result.returncode == 2
    assert (repo / "README.md").read_bytes() == original.encode()
    assert not (repo / "docs").exists()


def test_card_formats_asset_and_sidecar_before_writing(tmp_path, monkeypatch):
    repo, meta = target(tmp_path)
    (repo / ".github").mkdir()
    (repo / ".github/showcase.yml").write_text("chips:\n  key: [Test]\n  attrs: [Python]\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("formatting_test_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    calls = []

    def format_value(root, path, value):
        assert not (repo / "docs/images/card.svg").exists()
        calls.append(Path(path).name)
        if Path(path).suffix == ".json":
            return json.dumps(json.loads(value), indent=2) + "\n"
        return value

    monkeypatch.setattr("ctshowcase.formatting.format_text", format_value)
    assert cli.main(["--meta", str(meta), "--repo-dir", str(repo), "card", "--format-generated"]) == 0
    assert calls == ["card.svg", ".showcase.json"]
    sidecar = (repo / "docs/images/.showcase.json").read_text(encoding="utf-8")
    assert sidecar.startswith('{\n  "')
    data = json.loads(sidecar)
    assert data["outputs"]["card.svg"]["bytes"] == (repo / "docs/images/card.svg").stat().st_size


def test_sidecar_formatter_failure_leaves_card_and_existing_outputs_unchanged(tmp_path, monkeypatch):
    repo, meta = target(tmp_path)
    output = repo / "docs/images"
    output.mkdir(parents=True)
    (output / "card.svg").write_text("existing card", encoding="utf-8")
    (output / ".showcase.json").write_text('{"outputs": {}}', encoding="utf-8")
    spec = importlib.util.spec_from_file_location("formatting_failure_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    def fail_sidecar(root, path, value):
        if Path(path).suffix == ".json":
            raise NeedsInput("formatter", "synthetic sidecar formatter failure")
        return value

    monkeypatch.setattr("ctshowcase.formatting.format_text", fail_sidecar)
    assert cli.main(["--meta", str(meta), "--repo-dir", str(repo), "card", "--format-generated"]) == 4
    assert (output / "card.svg").read_text(encoding="utf-8") == "existing card"
    assert (output / ".showcase.json").read_text(encoding="utf-8") == '{"outputs": {}}'


def test_formatter_cannot_remove_authored_readme_text(tmp_path, monkeypatch):
    repo, meta = target(tmp_path)
    original = "# Exact title\n\nKeep this authored explanation.\n"
    (repo / "README.md").write_text(original, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("formatting_preservation_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr("ctshowcase.formatting.format_text",
                        lambda root, path, text: text.replace("Keep this authored explanation.", ""))
    assert cli.main(["--meta", str(meta), "--repo-dir", str(repo), "readme", "--write", "--format-generated"]) == 1
    assert (repo / "README.md").read_text(encoding="utf-8") == original
    assert not (repo / "docs").exists()
