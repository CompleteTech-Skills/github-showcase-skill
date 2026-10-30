"""`brand add-family` / `brand add-org` (dry run by default, `--write` regenerates locks and rolls back on schema errors)
and the `doctor --strict-owner` gate in estate mode and for a family on hold. Fixtures are synthetic (Acme-Widgets)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]
META = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))
FAMILY = ["brand", "add-family", "acme-family", "--company-label", "Acme Widgets", "--canvas", "#101820",
          "--accent", "#FEE715"]
ORG = ["brand", "add-org", "Acme-Widgets", "--family", "completetech", "--tier", "T1", "--display-name", "Acme Widgets"]


def run(*argv, cwd=ROOT):
    return subprocess.run([*SHOWCASE, *argv], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "brand.yaml"
    shutil.copyfile(ROOT / "references" / "brand.yaml", p)
    return p


def test_dry_run_prints_block_and_diff_and_touches_nothing(cfg):
    before = cfg.read_bytes()
    tracked = {f: (ROOT / f).read_bytes() for f in ("references/brand.yaml", "references/brand.lock.json")}
    for argv in (FAMILY, ORG):
        r = run("--config", str(cfg), *argv)
        out = json.loads(r.stdout)
        assert r.returncode == 0 and out["result"] == "dry-run" and out["written"] is False, r.stdout
        assert out["yaml"].startswith("  ") and out["diff"].startswith("--- a/references/brand.yaml")
        assert out["schema_errors"] == []
    assert cfg.read_bytes() == before
    assert tracked == {f: (ROOT / f).read_bytes() for f in tracked}


def test_dry_run_default_config_leaves_repo_files_alone():
    before = (ROOT / "references" / "brand.yaml").read_bytes()
    assert run(*ORG).returncode == 0
    assert (ROOT / "references" / "brand.yaml").read_bytes() == before


def test_write_adds_family_then_org_and_config_stays_valid(cfg):
    assert run("--config", str(cfg), *FAMILY, "--write").returncode == 0
    r = run("--config", str(cfg), "brand", "add-org", "Acme-Widgets", "--family", "acme-family", "--tier", "T1",
            "--display-name", "Acme Widgets", "--write")
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["result"] == "written", r.stdout
    import yaml
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert raw["families"]["acme-family"]["measured"] is False
    assert raw["orgs"]["Acme-Widgets"]["family"] == "acme-family"
    assert run("--config", str(cfg), "config").returncode in (0, 1)  # lock_in_sync is false for a custom config
    assert json.loads(run("--config", str(cfg), "config").stdout)["schema_errors"] == []


def test_duplicates_are_refused_and_nothing_changes(cfg):
    before = cfg.read_bytes()
    for argv in (["brand", "add-family", "Ai-Ascension", "--company-label", "X", "--canvas", "#000000",
                  "--accent", "#FFFFFF"],
                 ["brand", "add-org", "completetech-skills", "--family", "completetech", "--tier", "T1",
                  "--display-name", "X"],
                 ["brand", "add-org", "Pick-Your-AI", "--family", "completetech", "--tier", "T1", "--display-name", "X"],
                 ["brand", "add-org", "Acme-Widgets", "--family", "no-such-family", "--tier", "T1", "--display-name", "X"]):
        r = run("--config", str(cfg), *argv, "--write")
        assert r.returncode == 2, (argv, r.stdout, r.stderr)
    assert cfg.read_bytes() == before


def test_bad_colour_is_a_usage_error(cfg):
    r = run("--config", str(cfg), "brand", "add-family", "x-fam", "--company-label", "X", "--canvas", "red",
            "--accent", "#FFFFFF")
    assert r.returncode == 2 and "#RRGGBB" in r.stdout + r.stderr


def test_write_regenerates_both_locks_like_config_write_lock(tmp_path, monkeypatch):
    from ctshowcase import config as C
    from ctshowcase import detect
    from ctshowcase import brandedit as B
    import showcase
    refs = tmp_path / "references"
    refs.mkdir()
    yml = refs / "brand.yaml"
    shutil.copyfile(ROOT / "references" / "brand.yaml", yml)
    lock, std = refs / "brand.lock.json", tmp_path / "standard.lock.json"
    monkeypatch.setattr(C, "DEFAULT_CONFIG", yml)
    monkeypatch.setattr(C, "LOCK", lock)
    monkeypatch.setattr(detect, "STANDARD_LOCK", std)
    assert showcase.main(["brand", "add-org", "Acme-Widgets", "--family", "completetech", "--tier", "T1",
                          "--display-name", "Acme Widgets", "--write"]) == 0
    assert "Acme-Widgets" in json.loads(lock.read_text(encoding="utf-8"))["orgs"]
    assert lock.read_text(encoding="utf-8") == C.lock_text(C.load_yaml_text(yml.read_text(encoding="utf-8")))
    assert std.read_text(encoding="utf-8") == detect.standard_lock_text()
    assert B.write  # the same code path is used by both families of edits


def test_schema_error_rolls_back_brand_yaml_and_locks_byte_for_byte(tmp_path):
    from ctshowcase import brandedit as B
    yml, lock = tmp_path / "brand.yaml", tmp_path / "brand.lock.json"
    original = (ROOT / "references" / "brand.yaml").read_bytes()
    yml.write_bytes(original)
    lock.write_bytes(b"old lock\n")
    bad = original.decode("utf-8").replace("orgs:\n", "orgs:\n  Acme-Widgets:\n    family: completetech\n"
                                           "    tier: T9\n    display_name: X\n", 1)
    errs = B.write(yml, bad, [(lock, lambda raw: "new lock\n")])
    assert errs and yml.read_bytes() == original and lock.read_bytes() == b"old lock\n"


def test_insert_keeps_crlf_and_following_comment(cfg):
    from ctshowcase import brandedit as B
    text = cfg.read_text(encoding="utf-8").replace("\n", "\r\n")
    new = B.insert(text, "orgs", ["  Acme-Widgets:", "    tier: T1"])
    assert "\r\n  Acme-Widgets:\r\n" in new and "\n" not in new.replace("\r\n", "")
    assert new.index("Acme-Widgets") < new.index("\r\nowners:")


# -- doctor --strict-owner: estate mode and held families -------------------------------------------------
def _estate_meta(tmp_path, owner):
    d = tmp_path / "meta"
    d.mkdir()
    (d / "m.json").write_text(json.dumps(dict(META, owner=owner, repo="acme-synthetic")), encoding="utf-8")
    return d


def test_strict_owner_applies_in_estate_mode(tmp_path):
    # Review note: the committed examples/estate corpus (Northwind-Trading-Co) IS in brand.yaml, so it passes strict mode;
    # the gate is shown here with an unregistered synthetic owner, which the pre-fix estate branch silently accepted.
    base = ["doctor", "--estate", "--meta-dir", str(_estate_meta(tmp_path, "Acme-Widgets")), "--registry",
            str(ROOT / "examples" / "estate" / "registry" / "estate.yaml")]
    assert run(*base).returncode == 0  # default: unchanged
    r = run(*base, "--strict-owner")
    assert r.returncode == 2 and "unknown-org" in r.stdout + r.stderr, (r.stdout, r.stderr)


def test_strict_owner_refuses_a_family_on_hold_unless_allowed(tmp_path, cfg):
    assert run("--config", str(cfg), "brand", "add-org", "Acme-Held", "--family", "touchedbyanagent", "--tier", "T1",
               "--display-name", "Acme Held", "--write").returncode == 0
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner="Acme-Held", repo="acme-synthetic")), encoding="utf-8")
    base = ["--config", str(cfg), "--meta", str(meta), "--no-repo-dir", "doctor"]
    assert run(*base, "--strict-owner").returncode == 2
    assert "hold" in (run(*base, "--strict-owner").stdout + run(*base, "--strict-owner").stderr)
    assert run(*base, "--strict-owner", "--allow-hold").returncode != 2
    assert run(*base).returncode != 2  # off by default
