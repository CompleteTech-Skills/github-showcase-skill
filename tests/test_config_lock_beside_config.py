"""`config --write-lock` writes the lock beside the selected config, never over the shipped lock."""
import shutil

from conftest import ROOT, run_cli

SHIPPED_LOCK = ROOT / "references" / "brand.lock.json"


def test_outside_config_gets_its_own_lock(tmp_path):
    cfg = tmp_path / "brand.yaml"
    shutil.copy(ROOT / "references" / "brand.yaml", cfg)
    text = cfg.read_text(encoding="utf-8").replace("company: CompleteTech LLC", "company: Octocat Labs", 1)
    cfg.write_text(text, encoding="utf-8")
    before = SHIPPED_LOCK.read_bytes()
    first = run_cli("--format", "json", "--config", cfg, "config")
    assert first.returncode == 1 and '"lock_in_sync": false' in first.stdout
    wrote = run_cli("--format", "json", "--config", cfg, "config", "--write-lock")
    assert wrote.returncode == 0, wrote.stdout + wrote.stderr
    assert (tmp_path / "brand.lock.json").is_file()
    assert "Octocat Labs" in (tmp_path / "brand.lock.json").read_text(encoding="utf-8")
    assert SHIPPED_LOCK.read_bytes() == before
    assert run_cli("--format", "json", "config").returncode == 0
