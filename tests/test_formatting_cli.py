"""Opt-in target formatting preserves default behavior and fails before writes."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

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
        {"source": "package.json#scripts.lint", "command": "npm run lint", "status": "not run"}]


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
    from test_formatting import local_prettier

    local_prettier(repo)
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")

    real_run = subprocess.run

    def reject_changed_ast(argv, **kwargs):
        if argv[0] != "/node":
            return real_run(argv, **kwargs)
        assert "isDeepStrictEqual(original.ast, candidate.ast)" in argv[3]
        assert b"Keep this authored explanation." in kwargs["input"]
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"AST changed")

    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", reject_changed_ast)
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



@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_readme_writes_refuse_aliases_to_contributing(tmp_path, link):
    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    original = (ROOT / "tests/fixtures/template-README.md").read_bytes()
    original += b"\nSee https://github.com/CompleteTech-LLC/.github/blob/main/CONTRIBUTING.md for details.\n"
    readme.write_bytes(original)
    contrib = repo / "CONTRIBUTING.md"
    try:
        if link == "symlink":
            contrib.symlink_to(readme)
        else:
            os.link(readme, contrib)
    except OSError as error:
        pytest.skip(f"links unavailable: {error}")
    result = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--write", "--bootstrap")
    assert result.returncode == 2
    assert "output paths must be distinct" in result.stdout
    assert readme.read_bytes() == contrib.read_bytes() == original
    result = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--write", "--mode", "header")
    assert result.returncode == 0, result.stdout + result.stderr



def test_readme_accepts_prettier_table_alignment_after_ast_check(tmp_path, monkeypatch):
    from test_formatting import local_prettier

    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    readme.write_text("# Local table\n\n| Key | Value |\n|---|---|\n| x | y |\n", encoding="utf-8")
    local_prettier(repo)
    spec = importlib.util.spec_from_file_location("formatting_table_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    real_run = subprocess.run
    calls = []

    def format_table(argv, **kwargs):
        if argv[0] != "/node":
            return real_run(argv, **kwargs)
        assert "isDeepStrictEqual(original.ast, candidate.ast)" in argv[3]
        value = kwargs["input"]
        calls.append(value)
        formatted = value.replace(b"|---|---|", b"| --- | ----- |").replace(b"| x | y |", b"| x   | y     |")
        return SimpleNamespace(returncode=0, stdout=json.dumps(formatted.decode()).encode(), stderr=b"")

    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", format_table)
    assert cli.main(["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "header",
                     "--write", "--format-generated"]) == 0
    assert len(calls) == 1
    assert "| --- | ----- |\n| x   | y     |" in readme.read_text(encoding="utf-8")


def test_returned_readme_must_preserve_managed_markers(tmp_path, monkeypatch):
    repo, meta = target(tmp_path)
    path = repo / "README.md"
    original = (b"# Northwind\n\n<!-- showcase:notes:start -->\nA synthetic README.\n"
                b"<!-- showcase:notes:end -->\n")
    path.write_bytes(original)
    spec = importlib.util.spec_from_file_location("formatting_markers_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    def drop_notes_end(root, destination, text):
        assert "<!-- showcase:notes:end -->" in text
        return text.replace("<!-- showcase:notes:end -->", "")

    monkeypatch.setattr("ctshowcase.formatting.format_text", drop_notes_end)
    assert cli.main(["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "header",
                     "--write", "--format-generated"]) == 1
    assert path.read_bytes() == original


def test_formatter_cannot_remove_card_drawing(tmp_path, monkeypatch):
    repo, meta = target(tmp_path)
    spec = importlib.util.spec_from_file_location("formatting_svg_contents_showcase", ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    def remove_drawing(root, path, value):
        return value.split("</title>", 1)[0] + "</title>\n</svg>\n"

    monkeypatch.setattr("ctshowcase.formatting.format_text", remove_drawing)
    assert cli.main(["--meta", str(meta), "--repo-dir", str(repo), "card", "--key-chip", "Test",
                     "--chip", "Python", "--format-generated"]) == 1
    assert not (repo / "docs").exists()


def test_external_sidecar_is_refused_before_reading(tmp_path, monkeypatch, make_ctx):
    import showcase
    from ctshowcase.errors import ShowcaseError

    repo = tmp_path / "repo"
    images = repo / "docs/images"
    images.mkdir(parents=True)
    outside = tmp_path / "unrelated.json"
    outside.write_text("[]", encoding="utf-8")
    try:
        (images / ".showcase.json").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")
    monkeypatch.setattr(showcase, "_sidecar_text", lambda *_: pytest.fail("read before containment check"))
    ctx = make_ctx(repo_dir=repo)
    with pytest.raises(ShowcaseError, match="inside the target checkout"):
        showcase.write_art(ctx, images / "banner.png", b"banner", format_generated=True)
    assert outside.read_text(encoding="utf-8") == "[]"
    assert not (images / "banner.png").exists()


def test_concurrent_formatted_art_preserves_both_sidecar_records(tmp_path, monkeypatch, make_ctx):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import sleep
    import showcase

    ctx = make_ctx(repo_dir=tmp_path)
    start = Barrier(2)

    def formatting(repo, path, original):
        sleep(0.05)
        return original

    def write(name):
        start.wait(timeout=5)
        showcase.write_art(ctx, tmp_path / "docs/images" / name, name.encode(), format_generated=True)

    monkeypatch.setattr("ctshowcase.formatting.format_text", formatting)
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(write, ("banner.png", "card.svg")))
    sidecar = tmp_path / "docs/images/.showcase.json"
    assert set(json.loads(sidecar.read_text(encoding="utf-8"))["outputs"]) == {"banner.png", "card.svg"}


def test_readme_formats_each_local_badge_before_writing(tmp_path, monkeypatch):
    import showcase

    repo, meta = target(tmp_path)
    capture = meta_dict(repo=".github", files=["README.md"], license="MIT")
    meta.write_text(json.dumps(capture), encoding="utf-8")
    formatted_paths = []

    def formatting(root, path, value):
        formatted_paths.append(path)
        assert not path.exists()
        return value

    monkeypatch.setattr("ctshowcase.formatting.format_text", formatting)
    args = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "scaffold",
            "--write", "--badges", "local", "--format-generated"]
    assert showcase.main(args) == 0
    assert repo / "README.md" in formatted_paths
    badges = list((repo / "docs/images/badges").glob("*.svg"))
    assert len(badges) >= 2 and set(badges) <= set(formatted_paths)


def test_formatted_readme_keeps_concurrent_edit(tmp_path, monkeypatch):
    import showcase

    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    readme.write_text("# Original\n", encoding="utf-8")
    edit = b"# Edit made during formatting\n"

    def formatting(root, path, value):
        if path == readme:
            readme.write_bytes(edit)
        return value

    monkeypatch.setattr("ctshowcase.formatting.format_text", formatting)
    assert showcase.main(["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "scaffold",
                          "--write", "--format-generated"]) == 1
    assert readme.read_bytes() == edit


def test_local_badge_cannot_alias_unchanged_readme(tmp_path, monkeypatch):
    import showcase

    repo, meta = target(tmp_path)
    meta.write_text(json.dumps(meta_dict(repo=".github", files=["README.md"])), encoding="utf-8")
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda _r, _p, value: value)
    args = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "scaffold",
            "--write", "--badges", "local", "--format-generated"]
    assert showcase.main(args) == 0
    readme = repo / "README.md"
    original = readme.read_bytes()
    badge = next((repo / "docs/images/badges").glob("*.svg"))
    badge.unlink()
    try:
        badge.hardlink_to(readme)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"hard links are unavailable: {exc}")
    assert showcase.main(args) == 2
    assert readme.read_bytes() == original


def test_formatted_banner_refuses_external_art_before_sidecar_read(tmp_path, monkeypatch, make_ctx):
    import showcase
    from ctshowcase.errors import ShowcaseError

    repo = tmp_path / "repo"
    images = repo / "docs/images"
    images.mkdir(parents=True)
    outside = tmp_path / "unrelated.png"
    outside.write_bytes(b"unrelated")
    out = images / "banner.png"
    try:
        out.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")
    monkeypatch.setattr(showcase, "_sidecar_text", lambda *_: pytest.fail("read before containment check"))
    with pytest.raises(ShowcaseError, match="inside the target checkout"):
        showcase.write_art(make_ctx(repo_dir=repo), out, b"banner", format_generated=True)
    assert outside.read_bytes() == b"unrelated"
