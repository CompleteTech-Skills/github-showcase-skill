"""Reconcile provenance across checkout-aware and metadata-only renderers."""

import json
import os
import subprocess

import pytest

import action_prepare
from conftest import meta_dict, run_cli
from ctshowcase import fingerprint as fp, staged


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", repo], check=True)
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    out = repo / "docs/images/custom/card.svg"

    def card(*args, in_checkout):
        location = ("--repo-dir", repo) if in_checkout else ("--no-repo-dir",)
        return run_cli("--meta", capture, *location, "card", "--out", out, *args)

    return repo, out, card


def sidecar_slot(repo, out, in_checkout):
    return ((repo / "docs/images", "docs/images/custom/card.svg") if in_checkout
            else (out.parent, out.name))


@pytest.mark.parametrize("in_checkout", [False, True])
def test_live_refresh_reconciles_existing_other_slot(checkout, monkeypatch, in_checkout):
    repo, out, card = checkout
    monkeypatch.chdir(repo)
    initial = card("--description", "Route support requests.", in_checkout=in_checkout)
    assert initial.returncode == 0, initial.stdout + initial.stderr
    existing, key = sidecar_slot(repo, out, in_checkout)
    absent, _ = sidecar_slot(repo, out, not in_checkout)
    assert action_prepare.has_staged_outputs()
    assert not (absent / fp.SIDECAR).exists()
    proposed = fp.read_sidecar(existing)["outputs"][key]
    assert proposed["staged_description"]["text"] == "Route support requests."

    live = card(in_checkout=not in_checkout)
    assert live.returncode == 0, live.stdout + live.stderr
    record = fp.read_sidecar(existing)["outputs"][key]
    assert record["sha256"] != proposed["sha256"]
    assert {"sha256": record["sha256"], "bytes": record["bytes"]} == fp.file_record(out)
    assert "staged_description" not in record
    assert not action_prepare.has_staged_outputs()
    assert not (absent / fp.SIDECAR).exists()


def test_reconcile_preserves_unrelated_existing_records(checkout):
    repo, out, card = checkout
    initial = card("--description", "Route support requests.", in_checkout=False)
    assert initial.returncode == 0, initial.stdout + initial.stderr
    existing, key = sidecar_slot(repo, out, False)
    data = fp.read_sidecar(existing)
    unrelated = {"sha256": "a" * 64, "bytes": 42, "staged_description": {"text": "Another draft"}}
    data["outputs"]["unrelated.svg"] = unrelated
    (existing / fp.SIDECAR).write_text(fp.sidecar_text(data), encoding="utf-8")

    live = card(in_checkout=True)
    assert live.returncode == 0, live.stdout + live.stderr
    outputs = fp.read_sidecar(existing)["outputs"]
    assert outputs["unrelated.svg"] == unrelated
    assert "staged_description" not in outputs[key]


def test_canonical_live_social_record_protects_artifact_in_metadata_only_mode(checkout):
    repo, out, card = checkout
    result = card("--description", "Route support requests.", in_checkout=True)
    assert result.returncode == 0, result.stdout + result.stderr
    directory, name = sidecar_slot(repo, out, True)
    data = fp.read_sidecar(directory)
    data["outputs"][name]["live_social_preview"] = True
    (directory / fp.SIDECAR).write_text(fp.sidecar_text(data), encoding="utf-8")
    original = out.read_bytes()

    result = card("--description", "Try a different draft.", in_checkout=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "must not replace a live social preview" in result.stderr
    assert out.read_bytes() == original


def test_special_adjacent_mode_uses_only_its_local_slot(checkout, make_ctx):
    repo, out, _ = checkout
    ctx = make_ctx(repo_dir=repo)
    assert staged._output_slots(ctx, out, adjacent=True) == ((out.parent, out.name, False),)


def test_reconcile_uses_both_existing_slots_for_the_same_artifact(checkout):
    repo, out, card = checkout
    result = card("--description", "Route support requests.", in_checkout=True)
    assert result.returncode == 0, result.stdout + result.stderr
    result = card("--description", "Route synthetic work to the owner.", in_checkout=False)
    assert result.returncode == 0, result.stdout + result.stderr
    for in_checkout in (False, True):
        directory, key = sidecar_slot(repo, out, in_checkout)
        record = fp.read_sidecar(directory)["outputs"][key]
        assert record["staged_description"]["text"] == "Route synthetic work to the owner."
        assert record["sha256"] == fp.file_record(out)["sha256"]


def test_alternate_sidecar_cannot_alias_the_primary_sidecar(checkout):
    repo, out, card = checkout
    result = card("--description", "Route support requests.", in_checkout=False)
    assert result.returncode == 0, result.stdout + result.stderr
    canonical = repo / "docs/images" / fp.SIDECAR
    adjacent = out.parent / fp.SIDECAR
    try:
        os.link(adjacent, canonical)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")
    original = out.read_bytes()
    record = adjacent.read_bytes()
    result = card(in_checkout=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "showcase sidecars must use distinct files" in result.stderr
    assert out.read_bytes() == original
    assert adjacent.read_bytes() == canonical.read_bytes() == record


def test_output_outside_declared_checkout_keeps_adjacent_placement(checkout, make_ctx, tmp_path):
    _, out, _ = checkout
    declared = tmp_path / "declared"
    declared.mkdir()
    ctx = make_ctx(repo_dir=declared)
    assert staged._output_slots(ctx, out) == ((out.parent, out.name, True),)


def test_metadata_only_ignores_inferred_sidecar_outside_enclosing_checkout(checkout, make_ctx, tmp_path):
    repo, _, _ = checkout
    external = tmp_path / "external"
    external.mkdir()
    images = repo / "docs/images"
    images.parent.mkdir()
    try:
        images.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    out = repo / "assets/card.svg"
    ctx = make_ctx()
    assert staged._output_slots(ctx, out) == ((out.parent, out.name, True),)
    staged.check_outputs(ctx, out)
