"""Opt-in target formatting preserves default behavior and fails before writes."""
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
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


@pytest.mark.parametrize("directory", ["card.png", ".showcase.json"])
def test_formatted_card_preflights_every_artifact(tmp_path, monkeypatch, make_ctx, directory):
    import showcase
    from ctshowcase.errors import ShowcaseError

    images = tmp_path / "docs/images"
    images.mkdir(parents=True)
    out = images / "card.svg"
    out.write_bytes(b"original card")
    sidecar = images / ".showcase.json"
    (images / directory).mkdir()
    if sidecar.is_dir():
        original_sidecar = None
    else:
        original_sidecar = b'{"outputs":{}}'
        sidecar.write_bytes(original_sidecar)
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda root, path, text: text)
    with pytest.raises(ShowcaseError, match="must be a regular file"):
        showcase.write_art(make_ctx(repo_dir=tmp_path), out, b"new card", format_generated=True,
                           preview=(images / "card.png", b"new preview"))
    assert out.read_bytes() == b"original card"
    if original_sidecar is not None:
        assert sidecar.read_bytes() == original_sidecar
    else:
        assert not (images / "card.png").exists()


def test_formatted_outputs_roll_back_a_failed_replacement(tmp_path, monkeypatch):
    from ctshowcase.formatting import write_formatted_outputs

    card = tmp_path / "card.svg"
    preview = tmp_path / "card.png"
    card.write_bytes(b"original card")
    replace = Path.replace

    def fail_preview(source, destination):
        if destination == preview:
            raise PermissionError("synthetic replacement failure")
        return replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_preview)
    with pytest.raises(PermissionError, match="synthetic replacement failure"):
        write_formatted_outputs([(card, b"new card"), (preview, b"new preview")])
    assert card.read_bytes() == b"original card"
    assert not preview.exists()


def test_formatted_card_replaces_a_hard_link_without_writing_through_it(tmp_path, monkeypatch, make_ctx):
    import showcase

    images = tmp_path / "repo/docs/images"
    images.mkdir(parents=True)
    outside = tmp_path / "unrelated.svg"
    outside.write_bytes(b"original external file")
    card = images / "card.svg"
    try:
        card.hardlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"hard links are unavailable: {exc}")
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda root, path, text: text)
    showcase.write_art(make_ctx(repo_dir=tmp_path / "repo"), card, b"new card", format_generated=True)
    assert card.read_bytes() == b"new card"
    assert outside.read_bytes() == b"original external file"


def test_formatter_cannot_retarget_readme_to_same_bytes_outside_checkout(tmp_path, monkeypatch):
    import showcase

    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    original = b"# Northwind\n\nSynthetic body.\n"
    readme.write_bytes(original)
    outside = tmp_path / "unrelated.md"
    outside.write_bytes(original)
    link = repo / "replacement"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")

    def retarget(root, destination, text):
        readme.unlink()
        link.replace(readme)
        return text

    monkeypatch.setattr("ctshowcase.formatting.format_text", retarget)
    assert showcase.main(["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "scaffold",
                          "--write", "--format-generated"]) == 2
    assert readme.is_symlink()
    assert outside.read_bytes() == original


@pytest.mark.parametrize("write", [False, True])
def test_formatter_records_cannot_alias_readme(tmp_path, monkeypatch, write):
    import showcase

    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    original = b"# Northwind\n"
    readme.write_bytes(original)
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda root, path, text: text)
    argv = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "scaffold",
            "--records", str(readme), "--format-generated"]
    if write:
        argv.append("--write")
    assert showcase.main(argv) == 2
    assert readme.read_bytes() == original


@pytest.mark.parametrize("ending", ["\r\n", "\r"])
def test_formatter_keeps_markers_after_fences_and_reseals_pristine_body(tmp_path, monkeypatch, ending):
    import showcase
    from ctshowcase import readme

    repo, meta = target(tmp_path)
    path = repo / "README.md"
    original = ("# Northwind\n\n"
                "```sh\nprintf sample\n```\n\n"
                "<!-- showcase:tagline:start -->\n\nOld tagline.\n\n<!-- showcase:tagline:end -->\n\n"
                + readme.pristine_block("## Install\n\nSynthetic install instructions.") + "\n")
    path.write_bytes(original.encode("utf-8"))
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda root, path, text: text.replace("\n", ending))
    argv = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "header", "--write", "--format-generated"]
    assert showcase.main(argv) == 0
    rendered = path.read_bytes()
    assert ending.encode() in rendered
    assert readme.bootstrap_state(rendered.decode().replace("\r\n", "\n").replace("\r", "\n")) == "pristine"
    assert showcase.main(argv) == 0
    assert path.read_bytes() == rendered


@pytest.mark.parametrize("explicit", [False, True])
def test_formatted_readme_from_relative_or_implicit_checkout(tmp_path, monkeypatch, explicit):
    import showcase

    repo, meta = target(tmp_path)
    target_path = repo / "README.md"
    target_path.write_text("# Northwind\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    "https://github.com/Northwind-Trading-Co/support-triage-agent.git"], check=True)
    monkeypatch.chdir(tmp_path if explicit else repo)
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda root, destination, text: text)
    args = ["--meta", str(meta)] + (["--repo-dir", "repo"] if explicit else [])
    assert showcase.main([*args, "readme", "--mode", "scaffold", "--write", "--format-generated"]) == 0
    assert "showcase:tagline:start" in target_path.read_text(encoding="utf-8")


def test_reformatted_managed_nav_is_idempotent_and_authored_nav_is_preserved(tmp_path, monkeypatch):
    import showcase

    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    readme.write_text("# Human Title\n\nAuthored overview.\n\n## About\n\nExisting information.\n", encoding="utf-8")

    def wrap_nav(root, target, text):
        return text.replace(" · [All repositories]", " ·\n[All repositories]").replace(" · [Contributing]", " ·\n[Contributing]")

    monkeypatch.setattr("ctshowcase.formatting.format_text", wrap_nav)
    args = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--write", "--format-generated"]
    assert showcase.main(args) == 0
    first = readme.read_bytes()
    assert b"\n[All repositories]" in first
    assert showcase.main(args) == 0
    assert readme.read_bytes() == first
    authored = first.replace(b"<!-- showcase:nav:end -->",
                             b"Authored navigation note.\n\n<!-- showcase:nav:end -->")
    readme.write_bytes(authored)
    assert showcase.main(args) == 1
    assert readme.read_bytes() == authored


def test_workflow_preflight_reports_simple_validator_chain(tmp_path):
    repo, meta = target(tmp_path)
    workflows = repo / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "validation.yml").write_text(
        "name: 2026-11-17\njobs:\n  validate:\n    steps:\n"
        "      - run: npm run format && npm run lint && npm run typecheck && npm run contracts\n"
        "      - run: echo 'literal && npm run test'\n", encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", repo, "doctor", "--format", "json")
    assert json.loads(result.stdout)["tooling"]["validators"] == [
        {"source": ".github/workflows", "command": "npm run " + name, "status": "not run"}
        for name in ("format", "lint", "typecheck", "contracts")
    ]


def test_workflow_preflight_handles_quoted_arguments_and_bare_globs(tmp_path):
    repo, meta = target(tmp_path)
    workflows = repo / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "validation.yml").write_text(
        "jobs:\n  validate:\n    steps:\n"
        '      - run: npx prettier --check "**/*" && npm run lint && npm run typecheck\n'
        "      - run: npx prettier --check **/* && npm run format\n"
        "      - run: echo 'synthetic value && npm run test' && npm run contracts\n"
        '      - run: echo "synthetic value \\" && npm run verify" && npm run validate\n',
        encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", repo, "doctor", "--format", "json")
    assert json.loads(result.stdout)["tooling"]["validators"] == [
        {"source": ".github/workflows", "command": command, "status": "not run"}
        for command in ("npx prettier --check", "npm run lint", "npm run typecheck", "npx prettier --check",
                        "npm run format", "npm run contracts", "npm run validate")
    ]


@pytest.mark.parametrize("failure", ["directory", "hard-link", "replacement"])
def test_formatted_readme_and_explicit_records_publish_together(tmp_path, monkeypatch, failure):
    import showcase

    repo, meta = target(tmp_path)
    readme = repo / "README.md"
    original = b"# Human Title\n\nAuthored overview.\n\n## About\n\nExisting information.\n"
    readme.write_bytes(original)
    log = tmp_path / "queue.jsonl"
    alias = tmp_path / "queue-alias.jsonl"
    if failure == "directory":
        log.mkdir()
    else:
        log.write_bytes(b'{"previous":true}\n')
        if failure == "hard-link":
            try:
                alias.hardlink_to(log)
            except OSError as exc:
                pytest.skip(f"hard links are unavailable: {exc}")
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda _root, _path, text: text)
    argv = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--write", "--format-generated",
            "--records", str(log)]
    replace = Path.replace

    def fail_log(source, destination):
        if destination == log:
            raise PermissionError("synthetic change record replacement failure")
        return replace(source, destination)

    with monkeypatch.context() as failing:
        if failure == "replacement":
            failing.setattr(Path, "replace", fail_log)
        assert showcase.main(argv) == 2
    assert readme.read_bytes() == original
    if failure == "directory":
        log.rmdir()
    else:
        assert log.read_bytes() == b'{"previous":true}\n'
    if failure == "hard-link":
        assert alias.samefile(log)
        assert alias.read_bytes() == b'{"previous":true}\n'
        alias.unlink()

    assert showcase.main(argv) == 0
    queued = log.read_bytes()
    assert json.loads(queued.splitlines()[-1])["target"] == "README.md"
    if failure != "directory":
        assert queued.startswith(b'{"previous":true}\n')
    assert showcase.main(argv) == 0
    assert log.read_bytes() == queued


def test_output_lock_namespace_is_shared_across_process_temporary_directories(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    queue = tmp_path / "queue.jsonl"
    script = """
import sys
from pathlib import Path
from ctshowcase.output_lock import output_lock

original_open = Path.open

def capture_open(path, mode="r", *args, **kwargs):
    if mode == "a+b":
        print(path)
    return original_open(path, mode, *args, **kwargs)

Path.open = capture_open
with output_lock(Path(sys.argv[1])):
    pass
"""
    locked_paths = []
    for name in ("first-temp", "second-temp"):
        temporary = tmp_path / name
        temporary.mkdir()
        result = subprocess.run(
            [sys.executable, "-c", script, str(queue)],
            cwd=ROOT / "scripts",
            env={**os.environ, "HOME": str(home), "USERPROFILE": str(home),
                 "TMPDIR": str(temporary), "TEMP": str(temporary), "TMP": str(temporary)},
            capture_output=True, text=True, check=True, timeout=10,
        )
        locked_paths.append(Path(result.stdout.strip()))
    assert locked_paths[0] == locked_paths[1]
    assert locked_paths[0].is_relative_to(home)
    assert locked_paths[0].is_file()


def test_formatted_readme_queue_replacement_serializes_normal_append(tmp_path, monkeypatch):
    import showcase
    from ctshowcase import records

    repo, meta = target(tmp_path)
    (repo / "README.md").write_text("# Northwind\n", encoding="utf-8")
    queue = tmp_path / "queue.jsonl"
    queue.write_text('{"previous": true}\n', encoding="utf-8")
    appended = {"ordinary": True}
    start_append = Event()
    append_opened = Event()
    append_finished = Event()
    opened_paths = []
    original_open = Path.open
    original_replace = Path.replace

    def observe_open(path, mode="r", *args, **kwargs):
        if mode == "a+b" or (path == queue and mode == "a"):
            if start_append.is_set() and not append_opened.is_set():
                opened_paths.append(path)
                append_opened.set()
        return original_open(path, mode, *args, **kwargs)

    def append_record():
        assert start_append.wait(10)
        records.append(queue, [appended])
        append_finished.set()

    def replace_at_race(source, destination):
        if destination == queue:
            start_append.set()
            assert append_opened.wait(10)
            if opened_paths[0] == queue:
                # With an unlocked writer, finish its append before replacing the queue.
                assert append_finished.wait(10)
        return original_replace(source, destination)

    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda _root, _path, text: text)
    monkeypatch.setattr(Path, "open", observe_open)
    monkeypatch.setattr(Path, "replace", replace_at_race)
    with ThreadPoolExecutor(max_workers=1) as workers:
        writer = workers.submit(append_record)
        assert showcase.main(["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "scaffold",
                              "--write", "--format-generated", "--records", str(queue)]) == 0
        writer.result(timeout=10)

    previous, formatted_readme, ordinary = map(json.loads, queue.read_text(encoding="utf-8").splitlines())
    assert previous == {"previous": True}
    assert formatted_readme["target"] == "README.md"
    assert ordinary == appended
