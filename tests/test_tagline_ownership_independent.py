"""Independent issue #189 CLI contract tests; synthetic inputs, no network or formatter.

The receipt oracle is deliberately independent of ctshowcase.readme. Core cases
execute scripts/showcase.py in a child process. Formatter cases invoke the same
CLI parser/main in-process with only the external formatting boundary mocked.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- showcase:tagline:start -->"
END = "<!-- showcase:tagline:end -->"
OLD = "Run the synthetic Northwind comparison tool offline."
NEW = "Check synthetic Northwind values offline with deterministic output."
BODY = "## About\n\nKeep  two spaces, a tab\there and trailing spaces.  \n\n```text\n<!-- showcase:tagline:start -->\n**Example only.**\n<!-- showcase:tagline:end -->\n```\n"


def normalize(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def receipt(payload):
    digest = hashlib.sha256(normalize(payload).encode("utf-8")).hexdigest()
    return f"<!-- showcase:tagline:generated sha256={digest} -->\n{payload}"


def block(body):
    return f"{START}\n{body}\n{END}"


def extract(text):
    """Read the first real block in our controlled fixtures; exclude separators."""
    normalized = normalize(text)
    return normalized.split(START + "\n", 1)[1].split("\n" + END, 1)[0]


def assert_receipt(body):
    stamp, separator, payload = normalize(body).partition("\n")
    assert separator, "new generated tagline lacks its first-line ownership receipt"
    match = re.fullmatch(r"<!-- showcase:tagline:generated sha256=([0-9a-f]{64}) -->", stamp)
    assert match, f"missing or malformed first-line receipt: {stamp!r}"
    assert match.group(1) == hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return payload


def target(tmp_path, description=OLD):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "LICENSE").write_text("Synthetic MIT license fixture.\n", encoding="utf-8")
    meta = tmp_path / "meta.json"
    capture = {
        "owner": "Northwind-Trading-Co", "repo": "offline-comparison-tool",
        "description": description, "topics": [], "visibility": "public",
        "language": "Python", "license": "MIT", "labels": [], "files": ["main.py", "LICENSE"],
    }
    meta.write_text(json.dumps(capture), encoding="utf-8")
    return repo, meta


def change_description(meta, description=NEW):
    capture = json.loads(meta.read_text(encoding="utf-8"))
    capture["description"] = description
    meta.write_text(json.dumps(capture), encoding="utf-8")


def cli(repo, meta, *args):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/showcase.py"), "--meta", str(meta), "--repo-dir", str(repo), *args],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def write_original(repo, tagline, ending="\n"):
    text = "# Synthetic Northwind Tool\n\n" + block(tagline) + "\n\n" + BODY
    original = text.replace("\n", ending).encode("utf-8")
    (repo / "README.md").write_bytes(original)
    return original


@pytest.mark.parametrize("variant", ["C", "F"])
def test_cli_new_tagline_receipt_refresh_and_idempotence(tmp_path, variant):
    repo, meta = target(tmp_path, "Compare synthetic values where 3 < 5 and 9 > 7, offline.")
    cli(repo, meta, "readme", "--mode", "scaffold", "--variant", variant, "--write")
    path = repo / "README.md"
    first = assert_receipt(extract(path.read_bytes().decode("utf-8")))
    assert "3 &lt; 5" in first or "3 < 5" in first
    change_description(meta)
    cli(repo, meta, "readme", "--mode", "header", "--variant", variant, "--write")
    payload = assert_receipt(extract(path.read_bytes().decode("utf-8")))
    assert NEW in payload and "3 < 5" not in payload and "3 &lt; 5" not in payload
    refreshed = path.read_bytes()
    cli(repo, meta, "readme", "--mode", "header", "--variant", variant, "--write")
    assert path.read_bytes() == refreshed


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])
def test_cli_verified_receipt_normalizes_only_line_endings_and_keeps_source(tmp_path, ending):
    repo, meta = target(tmp_path)
    original = write_original(repo, receipt(f"**{OLD}**"), ending)
    change_description(meta)
    cli(repo, meta, "readme", "--mode", "header", "--no-regroup", "--write")
    output = (repo / "README.md").read_bytes()
    new_body = extract(output.decode("utf-8"))
    assert NEW in assert_receipt(new_body)
    before, _, after = original.partition((START + ending).encode())
    _, _, suffix = after.partition((ending + END).encode())
    out_before, _, out_after = output.partition((START + ending).encode())
    _, _, out_suffix = out_after.partition((ending + END).encode())
    assert out_before == before
    assert out_suffix == suffix


@pytest.mark.parametrize("mode", ["header", "upgrade"])
@pytest.mark.parametrize("edit", ["same-shape", "leading-space", "trailing-space", "tab", "blank-line"])
def test_cli_edited_receipt_never_reacquires_ownership(tmp_path, mode, edit):
    repo, meta = target(tmp_path)
    payload = f"**{OLD}**"
    edited = {
        "same-shape": "**Keep this synthetic owner policy exactly.**",
        "leading-space": " " + payload,
        "trailing-space": payload + "  ",
        "tab": "\t" + payload,
        "blank-line": payload + "\n",
    }[edit]
    stamp = receipt(payload).split("\n", 1)[0]
    authored = stamp + "\n" + edited
    write_original(repo, authored)
    change_description(meta)
    cli(repo, meta, "readme", "--mode", mode, "--write")
    assert extract((repo / "README.md").read_bytes().decode("utf-8")) == authored


@pytest.mark.parametrize("invalid", ["wrong-hash", "short-hash", "duplicate", "later-line", "trailing-junk"])
def test_cli_invalid_receipt_does_not_fall_through_to_shape(tmp_path, invalid):
    repo, meta = target(tmp_path)
    payload = f"**{OLD}**"
    valid = receipt(payload).split("\n", 1)[0]
    authored = {
        "wrong-hash": "<!-- showcase:tagline:generated sha256=" + "0" * 64 + " -->\n" + payload,
        "short-hash": "<!-- showcase:tagline:generated sha256=abc -->\n" + payload,
        "duplicate": valid + "\n" + valid + "\n" + payload,
        "later-line": payload + "\n" + valid,
        "trailing-junk": valid + " extra\n" + payload,
    }[invalid]
    write_original(repo, authored)
    change_description(meta)
    cli(repo, meta, "readme", "--mode", "header", "--write")
    assert extract((repo / "README.md").read_bytes().decode("utf-8")) == authored


@pytest.mark.parametrize("legacy", ["bold", "html", "equals-description"])
def test_cli_ambiguous_unreceipted_legacy_body_is_authored(tmp_path, legacy):
    repo, meta = target(tmp_path)
    authored = {
        "bold": "**Keep this synthetic owner policy exactly.**",
        "html": '<p align="center"><b>Keep this synthetic owner policy exactly.</b></p>',
        "equals-description": f"**{OLD}**",
    }[legacy]
    write_original(repo, authored)
    change_description(meta)
    cli(repo, meta, "readme", "--mode", "header", "--write")
    assert extract((repo / "README.md").read_bytes().decode("utf-8")) == authored


def test_cli_canonical_header_shape_alone_is_not_ownership(tmp_path):
    repo, meta = target(tmp_path)
    cli(repo, meta, "readme", "--mode", "scaffold", "--write")
    path = repo / "README.md"
    generated = path.read_bytes().decode("utf-8")
    old_block = block(extract(generated))
    authored = "**Keep this synthetic owner policy exactly.**"
    path.write_bytes(generated.replace(old_block, block(authored), 1).encode("utf-8"))
    change_description(meta)
    cli(repo, meta, "readme", "--mode", "header", "--write")
    assert extract(path.read_bytes().decode("utf-8")) == authored


@pytest.mark.parametrize("initial", [None, "", "\n"])
def test_cli_missing_or_empty_tagline_can_receive_receipt(tmp_path, initial):
    repo, meta = target(tmp_path)
    if initial is None:
        (repo / "README.md").write_text("# Synthetic Tool\n\n" + BODY, encoding="utf-8")
    else:
        write_original(repo, initial)
    cli(repo, meta, "readme", "--mode", "upgrade", "--write")
    assert OLD in assert_receipt(extract((repo / "README.md").read_bytes().decode("utf-8")))


def test_mock_formatter_reseals_previously_owned_payload(tmp_path, monkeypatch):
    """CLI runtime, mocked formatter boundary: this is not real Prettier evidence."""
    import showcase

    repo, meta = target(tmp_path)
    path = repo / "README.md"
    write_original(repo, receipt(f"**{OLD}**"))
    calls = []

    def fold(_root, _path, value):
        calls.append(value)
        return value.replace(f"**{OLD}**", "**Run the synthetic Northwind\ncomparison tool offline.**")

    monkeypatch.setattr("ctshowcase.formatting.format_text", fold)
    args = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "header", "--write", "--format-generated"]
    assert showcase.main(args) == 0
    assert calls
    assert "Northwind\ncomparison" in assert_receipt(extract(path.read_bytes().decode("utf-8")))
    change_description(meta)
    cli(repo, meta, "readme", "--mode", "header", "--write")
    assert NEW in assert_receipt(extract(path.read_bytes().decode("utf-8")))


def test_mock_formatter_cannot_reseal_edited_payload(tmp_path, monkeypatch, capsys):
    """Reject a mock format pass that would turn edited text back into owned text."""
    import showcase

    repo, meta = target(tmp_path)
    payload = f"**{OLD}**"
    stamp = receipt(payload).split("\n", 1)[0]
    original = write_original(repo, stamp + "\n " + payload)
    records = tmp_path / "records.jsonl"

    def deindent(_root, _path, value):
        return value.replace("\n " + payload, "\n" + payload)

    monkeypatch.setattr("ctshowcase.formatting.format_text", deindent)
    args = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "header", "--write", "--format-generated", "--records", str(records)]
    assert showcase.main(args) == 1
    assert "formatter-content" in json.loads(capsys.readouterr().out)["logs"]
    assert (repo / "README.md").read_bytes() == original
    assert not records.exists()
