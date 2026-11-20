"""Older owned chart configs remain valid; new optional labels stay typed."""

import json
import socket

import pytest
import showcase
import yaml

from conftest import ROOT


def check_config(tmp_path, capsys, monkeypatch, change):
    def blocked(*args, **kwargs):
        raise AssertionError("config validation must remain offline")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    raw = json.loads((ROOT / "references" / "brand.lock.json").read_text(encoding="utf-8"))
    change(raw["chart"]["labels"])
    path = tmp_path / "owned-brand.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    before = path.read_bytes()
    code = showcase.main(["--config", str(path), "--format", "json", "config"])
    result = json.loads(capsys.readouterr().out)
    assert path.read_bytes() == before
    # This CLI compares an owned config with its own adjacent lock, which this
    # test never writes. Its expected lock mismatch must not be mistaken for a
    # schema failure or repaired here.
    assert code == 1
    assert result["lock_in_sync"] is False
    return result["schema_errors"]


@pytest.mark.parametrize("missing", [("no_language",), ("other_languages",), ("no_language", "other_languages")])
def test_pre_extension_labels_pass_owned_config_preflight(tmp_path, capsys, monkeypatch, missing):
    errors = check_config(tmp_path, capsys, monkeypatch, lambda labels: [labels.pop(key) for key in missing])
    assert errors == []


@pytest.mark.parametrize("key,value", [("no_language", ""), ("other_languages", ""),
                                      ("no_language", 42), ("other_languages", None)])
def test_present_invalid_optional_labels_are_still_rejected(tmp_path, capsys, monkeypatch, key, value):
    errors = check_config(tmp_path, capsys, monkeypatch, lambda labels: labels.update({key: value}))
    assert errors
    assert any(key in error for error in errors)


def test_existing_required_privacy_label_is_still_required(tmp_path, capsys, monkeypatch):
    errors = check_config(tmp_path, capsys, monkeypatch, lambda labels: labels.pop("legend_private"))
    assert errors
    assert any("legend_private" in error for error in errors)
