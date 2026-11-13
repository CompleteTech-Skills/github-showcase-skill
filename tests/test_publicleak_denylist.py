"""Synthetic-only privacy coverage; output must not contain matched private text."""
import json

import pytest

from ctshowcase.errors import NeedsInput, ShowcaseError
from ctshowcase.publicleak import check_files


def test_literal_case_insensitive_entries_and_line_only_evidence(tmp_path):
    denied = tmp_path / "denylist.txt"
    denied.write_text("\nNorthwind Secret+Repo\ninternal.example\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text("Public text\nNORTHWIND SECRET+REPO details\ninternalXexample\nhttps://INTERNAL.EXAMPLE/a\n",
                      encoding="utf-8")
    result = check_files([str(source)], denied)
    assert result[0]["hits"] == [{"line": 2}, {"line": 4}]
    assert result[0]["result"] == "fail"
    output = json.dumps(result).casefold()
    assert "northwind secret+repo" not in output
    assert "internal.example" not in output
    source.write_text("Northwind public tools\n", encoding="utf-8")
    assert check_files([str(source)], denied)[0]["result"] == "pass"


def test_private_file_name_is_redacted_and_input_remains_unchanged(tmp_path):
    denied = tmp_path / "denylist.txt"
    denied.write_text("northwind-secret\n", encoding="utf-8")
    source = tmp_path / "Northwind-Secret.md"
    source.write_text("northwind-secret\n", encoding="utf-8")
    before = {p: p.read_bytes() for p in (source, denied)}
    result = check_files([str(source)], denied)
    assert result[0]["file"] == "[redacted path]"
    assert "northwind-secret" not in json.dumps(result).lower()
    assert all(p.read_bytes() == data for p, data in before.items())


def test_missing_and_malformed_input_fail_closed(tmp_path):
    denied = tmp_path / "deny.txt"
    denied.write_text("synthetic-secret\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_bytes(b"\xff")
    assert check_files([str(source), str(tmp_path / "missing")], denied) == [
        {"file": str(path), "result": "fail", "hits": [], "logs": ["privacy:denylist-only"],
         "fails": ["cannot read input as UTF-8"]} for path in (source, tmp_path / "missing")]
    denied.write_bytes(b"\xff")
    with pytest.raises(ShowcaseError, match="cannot read denylist"):
        check_files([str(source)], denied)
    denied.write_text(" \n", encoding="utf-8")
    with pytest.raises(NeedsInput, match="no entries"):
        check_files([str(source)], denied)


def test_cli_needs_no_registry_and_never_echoes_private_content(tmp_path, monkeypatch):
    from conftest import run_cli
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "absent"))
    denied = tmp_path / "deny.txt"
    denied.write_text("northwind-private-demo\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text("Public\nNORTHWIND-PRIVATE-DEMO\n", encoding="utf-8")
    result = run_cli("lint", "public-leak", source, "--denylist", denied)
    assert result.returncode == 1
    assert json.loads(result.stdout)["hits"] == [{"line": 2}]
    assert "northwind-private-demo" not in (result.stdout + result.stderr).lower()
    source.write_text("Public\n", encoding="utf-8")
    assert run_cli("lint", "public-leak", source, "--denylist", denied).returncode == 0


def test_cli_denylist_rejects_registry_inputs(tmp_path):
    from conftest import run_cli
    denied = tmp_path / "deny.txt"
    denied.write_text("synthetic-private-name\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text("Public\n", encoding="utf-8")
    result = run_cli("lint", "public-leak", source, "--denylist", denied, "--registry", tmp_path / "missing.yml")
    assert result.returncode == 2
    assert "use --denylist without" in result.stdout + result.stderr


def test_cli_empty_denylist_never_falls_back_to_estate(tmp_path, monkeypatch):
    from conftest import run_cli, ROOT
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(ROOT / "examples" / "estate"))
    source = tmp_path / "README.md"
    source.write_text("Northwind-Trading-Co/support-triage-agent\n", encoding="utf-8")
    result = run_cli("lint", "public-leak", source, "--denylist", "")
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["logs"] == ["usage"]
    assert "cannot read denylist" in payload["error"]
    assert "Northwind-Trading-Co" not in result.stdout + result.stderr


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_cli_first_entry_matches_and_redacts_path_with_optional_bom(tmp_path, monkeypatch, encoding):
    from conftest import run_cli
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "absent"))
    denied = tmp_path / "deny.txt"
    denied.write_text("northwind-private-demo\nsecond-synthetic-secret\n", encoding=encoding)
    source = tmp_path / "NORTHWIND-PRIVATE-DEMO.md"
    source.write_text("Public\nnorthwind-private-demo\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (source, denied)}

    result = run_cli("lint", "public-leak", source, "--denylist", denied)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["result"] == "fail"
    assert payload["hits"] == [{"line": 2}]
    assert payload["file"] == "[redacted path]"
    assert "northwind-private-demo" not in (result.stdout + result.stderr).casefold()
    assert "second-synthetic-secret" not in (result.stdout + result.stderr).casefold()
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize("text", ["", " \n\t\r\n"])
def test_cli_bom_only_or_blank_denylist_refuses_without_privacy_claim(tmp_path, text):
    from conftest import run_cli
    denied = tmp_path / "deny.txt"
    denied.write_text(text, encoding="utf-8-sig")
    source = tmp_path / "README.md"
    source.write_text("Public\n", encoding="utf-8")

    result = run_cli("lint", "public-leak", source, "--denylist", denied)

    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert "needs-input:denylist" in payload["logs"]
    assert "no privacy check was performed" in result.stdout + result.stderr
