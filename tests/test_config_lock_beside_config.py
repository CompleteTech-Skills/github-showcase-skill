"""`config --write-lock` writes the lock beside the selected config, never over the shipped lock (#214)."""
import shutil

from conftest import ROOT, run_cli

from ctshowcase.config import DEFAULT_CONFIG, LOCK, Brand, lock_in_sync, lock_path

SHIPPED_LOCK = ROOT / "references" / "brand.lock.json"


def _outside_config(tmp_path):
    cfg = tmp_path / "brand.yaml"
    shutil.copy(ROOT / "references" / "brand.yaml", cfg)
    text = cfg.read_text(encoding="utf-8").replace("company: CompleteTech LLC", "company: Octocat Labs", 1)
    assert text != (ROOT / "references" / "brand.yaml").read_text(encoding="utf-8")
    cfg.write_text(text, encoding="utf-8")
    return cfg


def test_outside_config_gets_its_own_lock(tmp_path):
    cfg = _outside_config(tmp_path)
    before = SHIPPED_LOCK.read_bytes()
    try:
        first = run_cli("--format", "json", "--config", cfg, "config")
        assert first.returncode == 1 and '"lock_in_sync": false' in first.stdout
        wrote = run_cli("--format", "json", "--config", cfg, "config", "--write-lock")
        assert wrote.returncode == 0, wrote.stdout + wrote.stderr
        assert '"lock_in_sync": true' in wrote.stdout
        assert "Octocat Labs" in (tmp_path / "brand.lock.json").read_text(encoding="utf-8")
        assert SHIPPED_LOCK.read_bytes() == before
        assert run_cli("--format", "json", "config").returncode == 0
    finally:
        # A regression must not leave the shared checkout's lock rewritten for other tests.
        if SHIPPED_LOCK.read_bytes() != before:
            SHIPPED_LOCK.write_bytes(before)


def test_shipped_config_keeps_the_shipped_lock():
    assert lock_path(Brand({}, DEFAULT_CONFIG)) == LOCK
    assert lock_path(Brand({}, None)) == LOCK


def test_config_beside_the_shipped_lock_has_no_lock_of_its_own():
    # A second config in references/ would otherwise share, and overwrite, the shipped brand.lock.json.
    other = Brand({}, DEFAULT_CONFIG.with_name("alt.yaml"))
    assert lock_path(other) is None
    assert not lock_in_sync(other)
