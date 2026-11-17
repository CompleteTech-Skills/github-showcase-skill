"""Opt-in target formatting preserves default behavior and fails before writes."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

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
    message = result.stdout + result.stderr
    assert ("cannot be combined with --format-generated" in message
            or "unrecognized arguments: --no-regroup" in message)
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
        assert "<!-- prettier-ignore -->\n<title>" in value
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


def test_formatted_crlf_readme_is_stable_on_retry(tmp_path, monkeypatch, capsys):
    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    readme.write_bytes(b"# Original title\n\nAn authored paragraph.\n")
    spec = importlib.util.spec_from_file_location("formatting_crlf_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr("ctshowcase.formatting.format_text",
                        lambda root, path, text: text.replace("\n", "\r\n"))
    argv = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "header",
            "--write", "--format-generated"]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["written"]
    raw = readme.read_bytes()
    assert b"\r\n" in raw
    assert cli.main(argv) == 0
    assert not json.loads(capsys.readouterr().out)["written"]
    assert readme.read_bytes() == raw


def test_bootstrap_formats_generated_content_and_reseals_on_retry(tmp_path, monkeypatch, capsys):
    from ctshowcase.readme import bootstrap_state

    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    original = (ROOT / "tests/fixtures/template-README.md").read_bytes()
    readme.write_bytes(original)
    guide = repo / "CONTRIBUTING.md"
    guide.write_text("See https://github.com/CompleteTech-LLC/.github/blob/main/CONTRIBUTING.md for details.\n",
                     encoding="utf-8")
    spec = importlib.util.spec_from_file_location("formatting_bootstrap_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    def format_candidate(root, path, generated):
        if path.name == "README.md":
            assert "This repository is the starting point" not in generated
            assert "write from repository facts only" in generated
            return generated.replace("write from repository facts only", "write from repository\nfacts only")
        assert "/Northwind-Trading-Co/" in generated
        return generated.replace(" for details.", "\nfor details.")

    monkeypatch.setattr("ctshowcase.formatting.format_text", format_candidate)
    argv = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--bootstrap", "--write", "--format-generated"]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["written"]
    written = readme.read_bytes()
    assert b"write from repository\nfacts only" in written
    assert bootstrap_state(written.decode()) == "pristine"
    assert "/Northwind-Trading-Co/" in guide.read_text(encoding="utf-8")
    assert cli.main(argv) == 0
    assert not json.loads(capsys.readouterr().out)["written"]
    assert readme.read_bytes() == written


@pytest.mark.parametrize("first", ["banner", "card"])
def test_banner_and_card_share_a_formatted_sidecar_on_retry(tmp_path, monkeypatch, first):
    from ctshowcase import banner

    repo, meta = target(tmp_path)
    spec = importlib.util.spec_from_file_location("formatting_art_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(banner, "render", lambda *args, **kwargs: (b"synthetic raster", {
        "px": "1280x360", "scale": 1, "chips": [], "icon": {"source": "synthetic"}, "bytes": 16, "save": "original",
        "incomplete": False, "eyebrow": "Northwind", "title_lines": [], "subtitle": None, "subtitle_source": None,
    }))
    def format_value(root, path, value):
        return json.dumps(json.loads(value), indent=2) + "\n" if path.suffix == ".json" else value

    monkeypatch.setattr("ctshowcase.formatting.format_text", format_value)
    argv = ["--meta", str(meta), "--repo-dir", str(repo)]
    second = "card" if first == "banner" else "banner"
    for command in (first, second):
        flags = ["--key-chip", "Test", "--chip", "Python"] if command == "card" else []
        assert cli.main([*argv, command, *flags, "--format-generated"]) == 0
    sidecar = repo / "docs/images/.showcase.json"
    previous = sidecar.read_bytes()
    assert previous.startswith(b'{\n  "')
    assert set(json.loads(previous)["outputs"]) == {"banner.png", "card.svg"}
    flags = ["--key-chip", "Test", "--chip", "Python"] if first == "card" else []
    assert cli.main([*argv, first, *flags, "--format-generated"]) == 0
    assert sidecar.read_bytes() == previous


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_card_png_cannot_overwrite_other_outputs(tmp_path, monkeypatch, alias):
    repo, meta = target(tmp_path)
    output = repo / "docs/images"
    output.mkdir(parents=True)
    svg = output / "card.svg"
    sidecar = output / ".showcase.json"
    svg.write_bytes(b"existing SVG")
    sidecar.write_bytes(b'{"outputs":{}}')
    png = svg
    if alias != "same":
        png = output / "other.png"
        try:
            if alias == "symlink":
                png.symlink_to(sidecar)
            else:
                os.link(sidecar, png)
        except OSError as error:
            pytest.skip(f"links unavailable: {error}")
    spec = importlib.util.spec_from_file_location("formatting_alias_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda root, path, value: value)
    monkeypatch.setattr("ctshowcase.card.preview_png", lambda scene, fonts: "synthetic PNG")
    monkeypatch.setattr("ctshowcase.scene.png_bytes", lambda image: b"PNG")
    assert cli.main(["--meta", str(meta), "--repo-dir", str(repo), "card", "--key-chip", "Test",
                     "--chip", "Python", "--png", str(png), "--format-generated"]) == 2
    assert svg.read_bytes() == b"existing SVG"
    assert sidecar.read_bytes() == b'{"outputs":{}}'
