"""The CLI emits UTF-8 even when a Windows pipe starts with a legacy encoding."""
import io
import json
import os
import subprocess
import sys

from conftest import ROOT, meta_dict

import showcase


def legacy_cli(*args):
    env = dict(os.environ, PYTHONIOENCODING="cp1252:strict", PYTHONUTF8="0")
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), *map(str, args)],
                          cwd=ROOT, env=env, capture_output=True)


def test_legacy_stdout_label_plan_preserves_unicode_json(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(repo=".github", files=["README.md"], files_complete=True,
                                       labels=[{"name": "bug", "color": "d73a4a",
                                                "description": "Something isn't working"}])), encoding="utf-8")
    result = legacy_cli("--meta", meta, "--no-repo-dir", "labels", "--plan", "--gh")
    assert result.returncode == 1, result.stderr.decode("utf-8")  # differences to apply, not a crash
    text = result.stdout.decode("utf-8")
    payload = json.loads(text)
    assert any("bug→type:bug" in op["rule"] for op in payload["ops"])
    assert "→" in text and "\\u2192" not in text
    assert "UnicodeEncodeError" not in result.stderr.decode("utf-8")


def test_legacy_stdout_raw_footer_is_utf8():
    result = legacy_cli("footer", "--raw")
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert " · Innovation at Every Integration" in result.stdout.decode("utf-8")


def test_legacy_stdout_json_footer_keeps_content():
    result = legacy_cli("footer")
    assert result.returncode == 0, result.stderr.decode("utf-8")
    payload = json.loads(result.stdout.decode("utf-8"))
    assert " · Innovation at Every Integration" in payload["markup"]


def test_legacy_stderr_text_error_preserves_path(tmp_path):
    missing = tmp_path / "missing-→-😀.json"
    result = legacy_cli("--format", "text", "--meta", missing, "--no-repo-dir", "describe")
    assert result.returncode in (2, 4)
    error = result.stderr.decode("utf-8")
    assert missing.name in error
    assert "UnicodeEncodeError" not in error


def test_legacy_stderr_parser_error_preserves_argument():
    result = legacy_cli("unknown-→-😀")
    assert result.returncode == 2
    error = result.stderr.decode("utf-8")
    assert "unknown-→-😀" in error
    assert "UnicodeEncodeError" not in error


def test_main_supports_redirected_text_streams(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    assert showcase.main(["footer", "--raw"]) == 0
    assert " · Innovation at Every Integration" in output.getvalue()


def test_quality_gate_decodes_cli_utf8_under_legacy_locale():
    result = subprocess.run(
        [sys.executable, "-c", "from scripts import validate_quality; validate_quality.gate_labels()"],
        cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="cp1252:strict", PYTHONUTF8="0"), capture_output=True)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert b"labels.yml ok" in result.stdout
