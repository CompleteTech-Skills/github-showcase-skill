"""Actual offline CLI regressions for tagline receipts; formatter doubles are labelled."""
import base64
import hashlib
import importlib.util
import json
import re

import pytest

from conftest import ROOT, meta_dict, run_cli
from ctshowcase import meta as metadata
from ctshowcase import readme
from ctshowcase import tagline

OLD = "Run the previous workflow for teams."
NEW = "Run the current workflow for teams."


def body(text):
    return next(m.group(2) for m in readme.find_blocks(readme.MARK, text) if m.group(1) == "tagline")


def verify(value):
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    marker, content = normalized.split("\n", 1)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert marker == f"<!-- showcase:tagline:generated sha256={digest} -->"
    return content


def metadata_file(path, description, **extra):
    path.write_text(json.dumps(meta_dict(description=description, **extra)), encoding="utf-8")


def generated_checkout(tmp_path, variant="A", description=OLD):
    repo = tmp_path / "repo"
    repo.mkdir()
    meta = tmp_path / "meta.json"
    metadata_file(meta, description)
    argv = ("--meta", meta, "--repo-dir", repo, "readme", "--variant", variant, "--write")
    result = run_cli(*argv)
    assert result.returncode == 0, result.stdout + result.stderr
    return repo / "README.md", meta, argv


@pytest.mark.parametrize("mode", ["header", "upgrade", "auto"])
@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("variant", ["A", "F"])
def test_real_cli_receipt_refresh_and_line_endings(tmp_path, mode, ending, variant):
    path, meta, argv = generated_checkout(tmp_path, variant, "Compare 1 < 2 & 4 > 3 with *care*.")
    original = path.read_text(encoding="utf-8")
    assert "1 < 2" in verify(body(original))
    # An authored duplicate cannot be paid for by the generated replacement.
    original += f"\n**{NEW}**\nKeep this authored sentence.\n"
    path.write_bytes(original.replace("\n", ending).encode())
    metadata_file(meta, NEW)
    result = run_cli(*argv, "--mode", mode)
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_bytes().decode()
    assert NEW in verify(body(after))
    assert after.count(NEW) == 2
    assert "Keep this authored sentence." in after
    assert after == after.replace("\r\n", "\n").replace("\r", "\n").replace("\n", ending)
    rerun = run_cli(*argv, "--mode", mode)
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert path.read_bytes().decode() == after


@pytest.mark.parametrize("change", ["word", "leading", "trailing", "blank", "wrap", "digest", "duplicate"])
@pytest.mark.parametrize("description", [NEW, ""])
def test_real_cli_edited_receipt_survives_canonical_header(tmp_path, change, description):
    path, meta, argv = generated_checkout(tmp_path)
    original = path.read_text(encoding="utf-8")
    old = body(original)
    marker, payload = old.split("\n", 1)
    changes = {
        "word": marker + "\n" + payload.replace("previous", "authored"),
        "leading": marker + "\n " + payload,
        "trailing": marker + "\n" + payload + " ",
        "blank": marker + "\n\n" + payload,
        "wrap": marker + "\n" + payload.replace("workflow for", "workflow\nfor"),
        "digest": marker.replace("sha256=", "sha256=invalid") + "\n" + payload,
        "duplicate": marker + "\n" + old,
    }
    authored = changes[change]
    # A pristine body is deliberately unrelated proof and cannot clear the edit.
    path.write_text(original.replace(old, authored) + "\n" + readme.pristine_block("## Notes\n\nTemplate body."),
                    encoding="utf-8")
    metadata_file(meta, description, template_taglines=[payload])
    for options in [("--mode", "header"), ("--no-regroup",), ("--mode", "upgrade"), ("--bootstrap",)]:
        result = run_cli(*argv, *options)
        assert result.returncode == 0, result.stdout + result.stderr
        assert body(path.read_text(encoding="utf-8")) == authored
        assert tagline.payload(authored) is None


@pytest.mark.parametrize("canonical", [False, True])
def test_real_cli_legacy_shape_is_never_adopted(tmp_path, canonical):
    path, meta, argv = generated_checkout(tmp_path)
    original = path.read_text(encoding="utf-8")
    authored = "**Policy: ask the repository owner before migrating.**"
    source = (original.replace(body(original), authored) if canonical else
              "# Authored guide\n\n" + readme.wrap("tagline", authored) + "\n\n## Usage\n\nKeep this.\n")
    path.write_text(source, encoding="utf-8")
    metadata_file(meta, NEW)
    for mode in ("header", "upgrade", "auto"):
        result = run_cli(*argv, "--mode", mode)
        assert result.returncode == 0, result.stdout + result.stderr
        assert body(path.read_text(encoding="utf-8")) == authored
    metadata_file(meta, authored[2:-2])
    result = run_cli(*argv)
    assert result.returncode == 0, result.stdout + result.stderr
    assert body(path.read_text(encoding="utf-8")) == authored  # semantic equality does not grant future ownership


def test_meta_reads_payload_and_rejects_edited_receipt(tmp_path):
    path, _, _ = generated_checkout(tmp_path)
    source = path.read_text(encoding="utf-8")
    def capture(text):
        return {"content": base64.b64encode(text.encode()).decode()}
    assert metadata._tagline_of(capture(source)) == f"**{OLD}**"
    assert metadata._tagline_of(capture(source.replace(OLD, NEW))) is None


def test_lint_checks_live_block_not_matching_sentence_elsewhere(tmp_path):
    path, meta, _ = generated_checkout(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + f"\n**{NEW}**\n", encoding="utf-8")
    metadata_file(meta, NEW)
    result = run_cli("--meta", meta, "--repo-dir", path.parent, "lint", "readme", path)
    reports = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert reports, result.stdout + result.stderr
    assert any("R2 bold tagline must equal the GitHub description" in row.get("fails", []) for row in reports)


def formatter_cli(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def test_mock_formatter_reflow_is_resealed_then_real_cli_refreshes(tmp_path, monkeypatch):
    path, meta, argv = generated_checkout(tmp_path)
    cli = formatter_cli("tagline_reflow_cli")

    def synthetic_reflow(root, target, value):
        return value.replace(f"\n**{OLD}**", f"\n\n**{OLD}**").replace("previous workflow", "previous\nworkflow")

    monkeypatch.setattr("ctshowcase.formatting.format_text", synthetic_reflow)
    assert cli.main(list(map(str, (*argv, "--mode", "header", "--format-generated")))) == 0
    formatted = path.read_text(encoding="utf-8")
    assert verify(body(formatted)).startswith("\n**Run the previous\nworkflow")
    assert tagline.matches_description(body(formatted), OLD)
    capture = {"content": base64.b64encode(formatted.encode()).decode()}
    assert metadata._tagline_of(capture) == "**Run the previous\nworkflow for teams.**"
    metadata_file(meta, NEW)
    result = run_cli(*argv, "--mode", "header")
    assert result.returncode == 0, result.stdout + result.stderr
    assert NEW in verify(body(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
def test_mock_formatter_cannot_restore_edited_receipt(tmp_path, monkeypatch, ending):
    path, _, argv = generated_checkout(tmp_path)
    original = path.read_text(encoding="utf-8")
    authored = original.replace(f"**{OLD}**", f"**{OLD}** ")
    authored_bytes = authored.replace("\n", ending).encode("utf-8")
    path.write_bytes(authored_bytes)
    cli = formatter_cli("tagline_authored_formatter_cli")
    records = path.parent / "records.jsonl"

    def synthetic_trim(root, target, value):
        trimmed = re.sub(r" +(?=\r\n|\r|\n)", "", value)
        assert trimmed != value  # the formatter double must actually attempt the forbidden edit
        return trimmed

    monkeypatch.setattr("ctshowcase.formatting.format_text", synthetic_trim)
    assert cli.main(list(map(str, (*argv, "--mode", "header", "--format-generated", "--records", records)))) == 1
    assert path.read_bytes() == authored_bytes
    assert not records.exists()


@pytest.mark.parametrize("left,right", [(" ", ""), ("", " "), ("\n", ""), ("", "\n")])
def test_cli_r2_requires_bold_delimiters_even_with_verified_receipt(tmp_path, left, right):
    path, meta, _ = generated_checkout(tmp_path)
    source = path.read_text(encoding="utf-8")

    def r2_fails():
        result = run_cli("--meta", meta, "--repo-dir", path.parent, "lint", "readme", path, "--variant", "A")
        return any(fail.startswith("R2 ") for fail in json.loads(result.stdout)["fails"])

    assert not r2_fails()
    still_verified = tagline.generated(f"**{left}{OLD}{right}**")
    path.write_text(source.replace(body(source), still_verified), encoding="utf-8")
    assert verify(body(path.read_text(encoding="utf-8"))) == f"**{left}{OLD}{right}**"
    assert r2_fails()


def test_verified_wrapping_does_not_ignore_whitespace_inside_html_attributes(tmp_path):
    expected = "See <span data-note='one two'>the guide</span>."
    path, meta, _ = generated_checkout(tmp_path, description=expected)
    original = path.read_text(encoding="utf-8")
    args = ("--meta", meta, "--repo-dir", path.parent, "lint", "readme", path, "--variant", "A")
    control = run_cli(*args)
    assert not any(fail.startswith("R2 ") for fail in json.loads(control.stdout)["fails"])
    changed = tagline.generated("**See <span data-note='one\ntwo'>the guide</span>.**")
    path.write_text(original.replace(body(original), changed), encoding="utf-8")
    assert not tagline.matches_description(changed, expected)
    edited = run_cli(*args)
    assert any(fail.startswith("R2 ") for fail in json.loads(edited.stdout)["fails"])


def test_mock_formatter_cannot_reseal_changed_inline_code(tmp_path, monkeypatch):
    path, _, argv = generated_checkout(tmp_path, description="Print `one two` exactly.")
    original = path.read_bytes()
    cli = formatter_cli("tagline_changed_code_formatter_cli")
    records = path.parent / "records.jsonl"

    def changed_code(root, target, value):
        return value.replace("`one two`", "`one  two`") if target == path else value

    monkeypatch.setattr("ctshowcase.formatting.format_text", changed_code)
    assert cli.main(list(map(str, (*argv, "--mode", "header", "--format-generated", "--records", records)))) == 1
    assert path.read_bytes() == original
    assert not records.exists()
