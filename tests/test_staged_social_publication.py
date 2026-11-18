"""A staged social proposal and a live upload must not share a destination."""
import json
import os
import stat
from pathlib import Path

import pytest

import showcase
from conftest import meta_dict, run_cli


@pytest.mark.parametrize("remove_after_queue", [False, True])
def test_staged_report_cannot_replace_a_live_preview_created_during_render(tmp_path, monkeypatch, capsys,
                                                                         remove_after_queue):
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict(description="Run the synthetic support queue.")), encoding="utf-8")
    checkout = tmp_path / "repo"
    checkout.mkdir()
    upload = checkout / "assets" / "custom-queued-preview.png"
    jobs = tmp_path / "jobs.jsonl"
    common = ("--meta", str(capture), "--repo-dir", str(checkout), "--format", "json", "content", "social")
    real_social = showcase.cmd_social
    output = None
    original = None

    def interleave_live_render(args):
        nonlocal output, original
        staged_result = real_social(args)
        result = run_cli(*common, "--job", "--jobs", jobs, "--out", upload)
        assert result.returncode == 0, result.stdout + result.stderr
        output = Path(json.loads(result.stdout)["out"])
        original = output.read_bytes()
        if remove_after_queue:
            output.unlink()
        return staged_result

    monkeypatch.setattr(showcase, "cmd_social", interleave_live_render)
    result = showcase.main([*common, "--description", "A synthetic private proposal.", "--report", str(upload)])
    assert result == 2
    assert "staged-description:path" in json.loads(capsys.readouterr().out)["logs"]
    assert output == upload
    if remove_after_queue:
        assert not upload.exists()
    else:
        assert upload.read_bytes() == original
    job = json.loads(jobs.read_text(encoding="utf-8"))
    assert any(str(upload) in step for step in job["steps"])


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits required")
def test_private_preview_and_its_proposal_sidecar_default_to_owner_only(tmp_path):
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict(description="Run the synthetic support queue.")), encoding="utf-8")
    result = run_cli("--meta", capture, "--repo-dir", tmp_path, "--format", "json", "content", "social",
                     "--description", "A synthetic private proposal.")
    assert result.returncode == 0, result.stdout + result.stderr
    out = Path(json.loads(result.stdout)["out"])
    sidecar = out.parent / ".showcase.json"
    assert stat.S_IMODE(out.stat().st_mode) == stat.S_IMODE(sidecar.stat().st_mode) == 0o600
    record = json.loads(sidecar.read_text(encoding="utf-8"))["outputs"][out.name]
    assert record["staged_description"]["text"] == "A synthetic private proposal."


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits required")
def test_staged_provenance_restricts_an_existing_public_sidecar(tmp_path):
    from ctshowcase.fingerprint import write_sidecar

    sidecar = write_sidecar(tmp_path, {}, "config", "banner.png", {"sha256": "live"})
    sidecar.chmod(0o644)
    write_sidecar(tmp_path, {}, "config", "banner.png", {"staged_description": {"text": "Private proposal."}})
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


@pytest.mark.parametrize("format_generated", [False, True])
@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits required")
def test_readme_staged_records_and_provenance_restrict_existing_permissions(tmp_path, monkeypatch, format_generated):
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict(description="Run the synthetic support queue.")), encoding="utf-8")
    checkout = tmp_path / "repo"
    images = checkout / "docs/images"
    images.mkdir(parents=True)
    sidecar = images / ".showcase.json"
    sidecar.write_text('{"outputs":{}}', encoding="utf-8")
    sidecar.chmod(0o644)
    records = tmp_path / "records.jsonl"
    records.touch(mode=0o644)
    records.chmod(0o644)
    monkeypatch.setattr("ctshowcase.formatting.format_text", lambda root, path, text: text)
    flags = ["--format-generated"] if format_generated else []
    assert showcase.main(["--meta", str(capture), "--repo-dir", str(checkout), "readme", "--write",
                          "--description", "A synthetic private proposal.", "--records", str(records), *flags]) == 0
    assert stat.S_IMODE(sidecar.stat().st_mode) == stat.S_IMODE(records.stat().st_mode) == 0o600
    assert json.loads(sidecar.read_text(encoding="utf-8"))["outputs"]["README.md"]["staged_description"]
    assert "A synthetic private proposal." in json.loads(records.read_text(encoding="utf-8"))["after"]
