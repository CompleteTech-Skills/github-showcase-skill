"""Onboarding cannot erase identity guards or leave assets after failed writes."""
from pathlib import Path

import pytest
from PIL import Image

from conftest import ROOT, run_cli
from ctshowcase import brand_commands
from ctshowcase.config import load_yaml_text, schema_errors, yaml
from ctshowcase.errors import ConfigError
from test_brand_onboarding import args_for


@pytest.fixture
def isolated_config(tmp_path):
    config = tmp_path / "package" / "references" / "brand.yaml"
    config.parent.mkdir(parents=True)
    raw = load_yaml_text((ROOT / "references" / "brand.yaml").read_text(encoding="utf-8"))
    raw["orgs"] = {"Northwind-Seed": raw["orgs"]["Northwind-Trading-Co"]}
    raw["owners"] = {key: [] for key in raw["owners"]}
    assert not schema_errors(raw)
    config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return config


def org_args(config, org, *extra):
    return ("--config", config, "brand", "add-org", "--family", "completetech",
            "--org", org, "--tier", "T1", "--display-name", "Northwind Demonstration",
            "--footer", "no", *extra)


@pytest.mark.parametrize("org", ["Pick-Your-AI", "pick-your-ai", "BunsDev", "bunsdev",
                                  "CompleTetech-Security", "CompleteTech-Security"])
@pytest.mark.parametrize("write", [False, True])
def test_external_config_cannot_remove_bundled_reserved_identities(isolated_config, org, write):
    before = isolated_config.read_bytes()
    result = run_cli(*org_args(isolated_config, org, *(('--write',) if write else ())))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "exists or is reserved" in result.stdout
    assert isolated_config.read_bytes() == before
    assert not isolated_config.with_name("brand.lock.json").exists()
    assert not (isolated_config.parent.parent / "assets").exists()


def test_family_and_org_combined_cannot_reclassify_reserved_identity(isolated_config):
    before = isolated_config.read_bytes()
    result = run_cli("--config", isolated_config, "brand", "add-family", "--name", "northwind-new",
                     "--label", "Northwind New", "--canvas", "#101820", "--ink", "#F5F5F5",
                     "--accent", "#FFB81C", "--org", "Pick-Your-AI", "--tier", "T1",
                     "--display-name", "Northwind New", "--footer", "no", "--write")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "exists or is reserved" in result.stdout
    assert isolated_config.read_bytes() == before
    assert not isolated_config.with_name("brand.lock.json").exists()


def test_custom_reserved_alias_stays_reserved_and_genuinely_new_org_is_allowed(isolated_config):
    raw = load_yaml_text(isolated_config.read_text(encoding="utf-8"))
    raw["orgs"]["Northwind-Seed"]["former_slugs"] = ["Northwind-Former"]
    raw["owners"]["hold"] = ["Northwind-Held"]
    isolated_config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    before = isolated_config.read_bytes()
    for name in ("Northwind-Former", "northwind-former", "Northwind-Held"):
        result = run_cli(*org_args(isolated_config, name, "--write"))
        assert result.returncode == 2 and "reserved" in result.stdout
        assert isolated_config.read_bytes() == before
    result = run_cli(*org_args(isolated_config, "Northwind-New", "--write"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert load_yaml_text(isolated_config.read_text(encoding="utf-8"))["orgs"]["Northwind-New"]["tier"] == "T1"


def test_reserved_lookup_never_discovers_private_approvals(isolated_config, monkeypatch):
    from ctshowcase import resolver
    def forbidden(*args, **kwargs):
        pytest.fail("local onboarding must not discover estate inputs")
    monkeypatch.setattr(resolver, "load_approvals", forbidden)
    monkeypatch.setattr(resolver, "load_registry", forbidden)
    args = args_for(isolated_config, "add-org", "--family", "completetech", "--org", "Northwind-New",
                    "--display-name", "Northwind New", "--tier", "T2", "--footer", "no")
    result, code = brand_commands.cmd_brand(args)
    assert code == 0 and result["result"] == "planned"


@pytest.mark.parametrize("readonly", ["brand", "lock"])
def test_readonly_existing_file_leaves_all_inputs_and_mark_untouched(isolated_config, tmp_path, readonly):
    mark = tmp_path / "authorized.png"
    Image.new("RGBA", (12, 12), (30, 80, 140, 255)).save(mark)
    lock = isolated_config.with_name("brand.lock.json")
    lock.write_bytes(b"previous lock\n")
    before = {path: path.read_bytes() for path in (isolated_config, lock, mark)}
    target = isolated_config.parent.parent / "assets" / "orgs" / "Northwind-Atomic" / "mark.png"
    protected = isolated_config if readonly == "brand" else lock
    protected.chmod(0o444)
    try:
        result = run_cli(*org_args(isolated_config, "Northwind-Atomic", "--mark", mark, "--write"))
        assert result.returncode == 2, result.stdout + result.stderr
        assert all(path.read_bytes() == value for path, value in before.items())
        assert not target.exists()
        assert not (isolated_config.parent.parent / "assets").exists()
    finally:
        protected.chmod(0o644)
    # A refused attempt must not leave an asset that blocks the corrected retry.
    retried = run_cli(*org_args(isolated_config, "Northwind-Atomic", "--mark", mark, "--write"))
    assert retried.returncode == 0, retried.stdout + retried.stderr
    assert target.read_bytes() == mark.read_bytes()


def test_late_lock_failure_restores_bytes_and_cleans_new_asset(isolated_config, tmp_path, monkeypatch):
    # Include CRLF so rollback must restore the bytes, not a newline-normalized read.
    isolated_config.write_bytes(isolated_config.read_bytes().replace(b"\n", b"\r\n"))
    mark = tmp_path / "authorized.png"
    Image.new("RGBA", (12, 12), (30, 80, 140, 255)).save(mark)
    lock = isolated_config.with_name("brand.lock.json")
    lock.write_bytes(b"previous lock\n")
    before = {path: path.read_bytes() for path in (isolated_config, lock, mark)}
    target = isolated_config.parent.parent / "assets" / "orgs" / "Northwind-Atomic" / "mark.png"
    original_write = Path.write_text
    original_bytes = Path.write_bytes
    def fail_lock_write(self, data, *args, **kwargs):
        if self == lock:
            raise PermissionError("synthetic late lock failure")
        return original_write(self, data, *args, **kwargs)
    def refuse_redundant_lock_restore(self, data, *args, **kwargs):
        if self == lock:
            raise PermissionError("unchanged lock cannot be written")
        return original_bytes(self, data, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", fail_lock_write)
    monkeypatch.setattr(Path, "write_bytes", refuse_redundant_lock_restore)
    args = args_for(isolated_config, "add-org", "--family", "completetech", "--org", "Northwind-Atomic",
                    "--display-name", "Northwind Atomic", "--tier", "T2", "--footer", "no",
                    "--mark", str(mark), "--write")
    with pytest.raises(ConfigError, match="write failed"):
        brand_commands.cmd_brand(args)
    assert all(path.read_bytes() == value for path, value in before.items())
    assert not target.exists()
    assert not (isolated_config.parent.parent / "assets").exists()


def test_lock_directory_refuses_before_creating_outputs(isolated_config, tmp_path):
    mark = tmp_path / "authorized.png"
    Image.new("RGBA", (12, 12), (30, 80, 140, 255)).save(mark)
    lock = isolated_config.with_name("brand.lock.json")
    lock.mkdir()
    before = isolated_config.read_bytes()
    result = run_cli(*org_args(isolated_config, "Northwind-Atomic", "--mark", mark, "--write"))
    assert result.returncode == 2 and "existing lock" in result.stdout
    assert isolated_config.read_bytes() == before
    assert lock.is_dir()
    assert not (isolated_config.parent.parent / "assets").exists()


def test_failed_restore_still_cleans_mark_and_reports_incomplete_rollback(isolated_config, tmp_path, monkeypatch):
    mark = tmp_path / "authorized.png"
    Image.new("RGBA", (12, 12), (30, 80, 140, 255)).save(mark)
    lock = isolated_config.with_name("brand.lock.json")
    lock.write_bytes(b"previous lock\n")
    before = isolated_config.read_bytes()
    original_bytes = Path.write_bytes
    lock_attempts = 0
    def fail_restore_lock(self, data, *args, **kwargs):
        nonlocal lock_attempts
        if self == lock:
            lock_attempts += 1
            if lock_attempts == 1:
                original_bytes(self, b"partial lock")
                raise OSError("synthetic full disk")
            raise OSError("synthetic restoration failure")
        return original_bytes(self, data, *args, **kwargs)
    monkeypatch.setattr(Path, "write_bytes", fail_restore_lock)
    args = args_for(isolated_config, "add-org", "--family", "completetech", "--org", "Northwind-Atomic",
                    "--display-name", "Northwind Atomic", "--tier", "T2", "--footer", "no",
                    "--mark", str(mark), "--write")
    with pytest.raises(ConfigError, match="rollback incomplete for lock"):
        brand_commands.cmd_brand(args)
    assert isolated_config.read_bytes() == before
    assert lock.read_bytes() == b"partial lock"
    assert not (isolated_config.parent.parent / "assets").exists()


def test_malformed_base_policy_is_rejected_without_writes(isolated_config):
    raw = load_yaml_text(isolated_config.read_text(encoding="utf-8"))
    raw["owners"]["hold"] = "Northwind-Held"
    isolated_config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    before = isolated_config.read_bytes()
    result = run_cli(*org_args(isolated_config, "Northwind-New", "--write"))
    assert result.returncode == 2 and "schema validation failed" in result.stdout
    assert isolated_config.read_bytes() == before
    assert not isolated_config.with_name("brand.lock.json").exists()
