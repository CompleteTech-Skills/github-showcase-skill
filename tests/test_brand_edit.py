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
    # Existing rows below (completetech family, its orgs) are brand.yaml data, not hardcoded brand strings.
    # Exit code 2 alone is not evidence: argparse also exits 2 for an unknown subcommand, which is what the base does,
    # so each case must also carry the specific refusal reason.
    for argv, reason in ((["brand", "add-family", "completetech", "--company-label", "X", "--canvas", "#000000",
                           "--accent", "#FFFFFF"], "already exists"),
                         (["brand", "add-org", "completetech-skills", "--family", "completetech", "--tier", "T1",
                           "--display-name", "X"], "already"),
                         (["brand", "add-org", "Pick-Your-AI", "--family", "completetech", "--tier", "T1",
                           "--display-name", "X"], "already"),
                         (["brand", "add-org", "Acme-Widgets", "--family", "no-such-family", "--tier", "T1",
                           "--display-name", "X"], "unknown family")):
        r = run("--config", str(cfg), *argv, "--write")
        assert r.returncode == 2, (argv, r.stdout, r.stderr)
        assert reason in r.stdout + r.stderr and "invalid choice" not in r.stderr, (argv, r.stdout, r.stderr)
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


def _estate_two_metas(tmp_path, owners):
    d = tmp_path / "meta"
    d.mkdir()
    for i, o in enumerate(owners):
        (d / f"m{i}.json").write_text(json.dumps(dict(META, owner=o, repo=f"x-synth-{i}")), encoding="utf-8")
    return d


def test_strict_owner_estate_skips_excluded_owners_like_estate_doctor(tmp_path):
    # Review: estate_doctor skips excluded owners and placeholders, so the strict pre-gate must not refuse the whole run
    # for them. BunsDev is in owners.excluded; Northwind-Trading-Co is registered (synthetic).
    d = _estate_two_metas(tmp_path, ["Northwind-Trading-Co", "BunsDev"])
    base = ["doctor", "--estate", "--meta-dir", str(d), "--registry",
            str(ROOT / "examples" / "estate" / "registry" / "estate.yaml")]
    assert run(*base).returncode == 0
    r = run(*base, "--strict-owner")
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_strict_owner_estate_ignores_ownerless_metadata(tmp_path):
    d = tmp_path / "meta"
    d.mkdir()
    (d / "m.json").write_text(json.dumps({k: v for k, v in META.items() if k not in ("owner", "name")}), encoding="utf-8")
    base = ["doctor", "--estate", "--meta-dir", str(d), "--registry",
            str(ROOT / "examples" / "estate" / "registry" / "estate.yaml")]
    r = run(*base, "--strict-owner")
    assert "unknown-org" not in r.stdout + r.stderr, (r.stdout, r.stderr)


def test_strict_owner_estate_honours_registry_former_slugs(tmp_path):
    # Review: the gate must use the same alias-aware resolver as estate_doctor (--registry former_slugs).
    import yaml
    reg = yaml.safe_load((ROOT / "examples" / "estate" / "registry" / "estate.yaml").read_text(encoding="utf-8"))
    reg["orgs"]["Northwind-Trading-Co"]["former_slugs"] = ["Acme-Old"]
    rp = tmp_path / "reg.yaml"
    rp.write_text(yaml.safe_dump(reg), encoding="utf-8")
    d = _estate_two_metas(tmp_path, ["Acme-Old"])
    base = ["doctor", "--estate", "--meta-dir", str(d), "--registry", str(rp)]
    assert run(*base).returncode == 0
    r = run(*base, "--strict-owner")
    assert r.returncode == 0, (r.stdout, r.stderr)


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


def test_org_brand_topic_defaults_to_the_family_name(cfg):
    r = run("--config", str(cfg), "brand", "add-org", "Acme-Widgets", "--family", "completetech", "--tier", "T1",
            "--display-name", "Acme Widgets")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "brand_topic: \"completetech\"" in r.stdout or "brand_topic: completetech" in r.stdout, r.stdout


# -- review fixes: T3 sign-off, path spelling, YAML-reserved names, full_name owners ------------------------
def test_added_t3_org_stays_behind_the_signoff_gate(tmp_path, cfg):
    r = run("--config", str(cfg), "brand", "add-org", "Acme-Coowned", "--family", "completetech", "--tier", "T3",
            "--display-name", "Acme Coowned", "--write")
    assert r.returncode == 0, r.stdout
    import yaml
    assert "Acme-Coowned" in yaml.safe_load(cfg.read_text(encoding="utf-8"))["owners"]["t3"]
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner="Acme-Coowned", repo="acme-synthetic")), encoding="utf-8")
    base = ["--config", str(cfg), "--meta", str(meta), "--no-repo-dir"]
    r = run(*base, "doctor", "--strict-owner")
    assert r.returncode == 2 and "t3-signoff" in r.stdout + r.stderr, (r.stdout, r.stderr)
    assert run(*base, "--allow-t3", "doctor", "--strict-owner").returncode != 2


def test_relative_config_spelling_of_the_default_still_regenerates_locks(tmp_path, monkeypatch):
    import os
    from ctshowcase import config as C, detect
    import showcase
    refs = tmp_path / "references"
    refs.mkdir()
    yml, lock, std = refs / "brand.yaml", refs / "brand.lock.json", tmp_path / "standard.lock.json"
    shutil.copyfile(ROOT / "references" / "brand.yaml", yml)
    monkeypatch.setattr(C, "DEFAULT_CONFIG", yml)
    monkeypatch.setattr(C, "LOCK", lock)
    monkeypatch.setattr(detect, "STANDARD_LOCK", std)
    monkeypatch.chdir(tmp_path)
    assert os.path.join("references", "brand.yaml") != str(yml)  # a relative spelling, not equal to the absolute Path
    assert showcase.main(["--config", os.path.join("references", "brand.yaml"), "brand", "add-org", "Fabrikam-Co",
                          "--family", "completetech", "--tier", "T1", "--display-name", "Fabrikam", "--write"]) == 0
    assert "Fabrikam-Co" in json.loads(lock.read_text(encoding="utf-8"))["orgs"] and std.is_file()


def test_yaml_reserved_names_stay_string_keys(cfg):
    import yaml
    for name in ("yes", "123"):
        r = run("--config", str(cfg), "brand", "add-family", name, "--company-label", "X", "--canvas", "#101820",
                "--accent", "#FEE715", "--write")
        assert r.returncode == 0, r.stdout
    r = run("--config", str(cfg), "brand", "add-org", "true", "--family", "yes", "--tier", "T1", "--display-name", "T",
            "--write")
    assert r.returncode == 0, r.stdout
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert {"yes", "123"} <= set(raw["families"]) and "true" in raw["orgs"]
    assert all(isinstance(k, str) for sec in ("families", "orgs") for k in raw[sec])
    assert run("--config", str(cfg), "config").returncode in (0, 1)  # no crash


def test_strict_owner_gates_full_name_only_metadata(tmp_path):
    d = tmp_path / "meta"
    d.mkdir()
    m = {k: v for k, v in dict(META, repo="acme-synthetic", full_name="Pick-Your-AI/acme-synthetic").items()
         if k not in ("owner", "name")}
    (d / "m.json").write_text(json.dumps(m), encoding="utf-8")
    base = ["doctor", "--estate", "--meta-dir", str(d), "--registry",
            str(ROOT / "examples" / "estate" / "registry" / "estate.yaml")]
    r = run(*base, "--strict-owner")
    assert r.returncode == 2 and "t3-signoff" in r.stdout + r.stderr, (r.stdout, r.stderr)


# -- review round: owners.hold under estate strict mode, explicit 'unknown' login, YAML layout edge cases ----------
def _with_owner_hold(cfg, owner):
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("  t3: [", f"  hold: [{owner}]\n  t3: [", 1), encoding="utf-8")


def test_strict_owner_estate_refuses_owners_hold_like_single_repo(tmp_path, cfg):
    _with_owner_hold(cfg, "Northwind-Trading-Co")
    d = _estate_two_metas(tmp_path, ["Northwind-Trading-Co"])
    reg = str(ROOT / "examples" / "estate" / "registry" / "estate.yaml")
    r = run("--config", str(cfg), "doctor", "--estate", "--meta-dir", str(d), "--registry", reg, "--strict-owner")
    assert r.returncode == 2 and "HOLD" in r.stdout + r.stderr, (r.stdout, r.stderr)
    meta = tmp_path / "one.json"
    meta.write_text(json.dumps(dict(META, owner="Northwind-Trading-Co", repo="x")), encoding="utf-8")
    s = run("--config", str(cfg), "--meta", str(meta), "--no-repo-dir", "doctor", "--strict-owner")
    assert s.returncode == 2  # same verdict as the single-repo gate


def test_strict_owner_estate_gates_an_explicit_login_named_unknown(tmp_path):
    d = _estate_two_metas(tmp_path, ["unknown"])
    reg = str(ROOT / "examples" / "estate" / "registry" / "estate.yaml")
    r = run("doctor", "--estate", "--meta-dir", str(d), "--registry", reg, "--strict-owner")
    assert r.returncode == 2 and "unknown-org" in r.stdout + r.stderr, (r.stdout, r.stderr)


def test_add_org_t3_with_trailing_comment_on_owners_t3(cfg):
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("Jevelopers-neatHack-2026]", "Jevelopers-neatHack-2026]  # co-owned", 1),
                   encoding="utf-8")
    r = run("--config", str(cfg), *ORG[:2], "Acme-Coowned", "--family", "completetech", "--tier", "T3",
            "--display-name", "Acme Coowned", "--write")
    assert r.returncode == 0, (r.stdout, r.stderr)
    text = cfg.read_text(encoding="utf-8")
    assert "Acme-Coowned" in text and "# co-owned" in text


def test_add_org_when_orgs_is_the_last_section(cfg):
    lines = cfg.read_text(encoding="utf-8").split("\n")
    i = next(k for k, ln in enumerate(lines) if ln.startswith("orgs:"))
    j = next(k for k in range(i + 1, len(lines)) if lines[k][:1].isalpha())
    moved = lines[i:j]
    rest = lines[:i] + lines[j:]
    while rest and rest[-1] == "":
        rest.pop()
    cfg.write_text("\n".join(rest + [""] + moved).rstrip("\n") + "\n", encoding="utf-8")
    r = run("--config", str(cfg), *ORG[:2], "Acme-Last", "--family", "completetech", "--tier", "T1",
            "--display-name", "Acme Last", "--write")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "Acme-Last" in cfg.read_text(encoding="utf-8")
