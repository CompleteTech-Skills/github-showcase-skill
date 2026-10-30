"""`brand add-family` / `brand add-org` (E6.1.5): dry run by default, --write validates, owners: is never edited.

Every case works on a temporary copy of brand.yaml passed with the global --config flag, so the committed config and its
lock copy are never changed by the test run. Fixtures are synthetic (Acme-Widgets / acme-widgets)."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from conftest import ROOT

from ctshowcase import config as C

SRC = ROOT / "references" / "brand.yaml"
ADD_FAMILY = ["brand", "add-family", "acme-widgets", "--company-label", "Acme Widgets", "--accent", "#22D3EE",
              "--background", "#0B1020"]
ADD_ORG = ["brand", "add-org", "Acme-Widgets", "--family", "acme-widgets", "--display-name", "Acme Widgets",
           "--tier", "T2"]


def _cli(config, *argv, meta=None, pre=()):
    cmd = [sys.executable, str(ROOT / "scripts" / "showcase.py"), *pre, "--config", str(config)]
    if meta is not None:
        cmd += ["--meta", str(meta), "--no-repo-dir"]
    return subprocess.run([*cmd, *map(str, argv)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ))


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "brand.yaml"
    path.write_bytes(SRC.read_bytes())
    return path


def _raw(path):
    return C.load_yaml_text(path.read_text(encoding="utf-8"))


def test_dry_run_prints_diff_and_changes_nothing(cfg):
    before = cfg.read_bytes()
    r = _cli(cfg, *ADD_FAMILY)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["result"] == "dry-run" and "+  acme-widgets:" in out["diff"]
    assert cfg.read_bytes() == before


def test_write_adds_family_measured_false_and_keeps_schema_valid(cfg):
    r = _cli(cfg, *ADD_FAMILY, "--write")
    assert r.returncode == 0, r.stderr
    raw = _raw(cfg)
    assert raw["families"]["acme-widgets"]["measured"] is False
    assert raw["families"]["acme-widgets"]["tokens"]["accent"] == "#22D3EE"
    assert C.schema_errors(raw) == []
    assert "# One row per in-scope owner" in cfg.read_text(encoding="utf-8")  # comments survive the insert


def test_write_adds_org_and_never_edits_owners(cfg):
    assert _cli(cfg, *ADD_FAMILY, "--write").returncode == 0
    before_owners = _raw(cfg)["owners"]
    dry = _cli(cfg, *ADD_ORG)
    assert dry.returncode == 0 and json.loads(dry.stdout)["result"] == "dry-run"
    assert "Acme-Widgets" not in _raw(cfg)["orgs"]
    r = _cli(cfg, *ADD_ORG, "--write")
    assert r.returncode == 0, r.stderr
    raw = _raw(cfg)
    assert raw["orgs"]["Acme-Widgets"]["footer"] == "hold"
    assert raw["orgs"]["Acme-Widgets"]["family"] == "acme-widgets"
    assert raw["owners"] == before_owners
    assert C.schema_errors(raw) == []


def test_explicit_config_leaves_the_committed_lock_alone(cfg):
    lock_before = C.LOCK.read_bytes()
    assert _cli(cfg, *ADD_FAMILY, "--write").returncode == 0
    assert C.LOCK.read_bytes() == lock_before


def test_light_background_is_refused_without_writing(cfg):
    before = cfg.read_bytes()
    argv = [a if a != "#0B1020" else "#FFFFFF" for a in ADD_FAMILY]
    r = _cli(cfg, *argv, "--write")
    assert r.returncode != 0 and "too light" in json.loads(r.stdout)["error"]
    assert cfg.read_bytes() == before


def test_existing_family_and_unknown_family_are_refused(cfg):
    assert _cli(cfg, *ADD_FAMILY, "--write").returncode == 0
    again = _cli(cfg, *ADD_FAMILY, "--write")
    assert again.returncode != 0 and "already exists" in json.loads(again.stdout)["error"]
    bad_org = _cli(cfg, "brand", "add-org", "Other-Org", "--family", "no-such-family", "--display-name", "Other")
    assert bad_org.returncode != 0 and "not in brand.yaml" in json.loads(bad_org.stdout)["error"]
    assert cfg.read_text(encoding="utf-8").count("\n  acme-widgets:\n") == 1  # refusals never add a second block


def test_strict_owner_accepts_the_onboarded_org(cfg, tmp_path):
    assert _cli(cfg, *ADD_FAMILY, "--write").returncode == 0
    assert _cli(cfg, *ADD_ORG, "--write").returncode == 0
    meta = tmp_path / "meta.json"
    fixture = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))
    meta.write_text(json.dumps(dict(fixture, owner="Acme-Widgets", repo="acme-widgets-synthetic")), encoding="utf-8")
    r = _cli(cfg, "doctor", "--strict-owner", meta=meta)
    # the owner gate refuses with exit 2 and a "refused" result; an onboarded org passes it (the synthetic repo has no
    # file tree, so doctor reports needs-input, which is not a refusal)
    assert r.returncode != 2 and "refused" not in r.stdout and "unknown-org" not in r.stdout, r.stdout


# ----------------------------------------------------------------------------------------------- review regressions (E6.1.5)
def test_yaml_looking_names_stay_strings(cfg):
    """`No` and `123` are a YAML boolean and integer when unquoted, and `no` as a family key failed the config check."""
    assert _cli(cfg, "brand", "add-family", "no", "--company-label", "No Co", "--accent", "#22D3EE",
                "--background", "#0B1020", "--write").returncode == 0
    assert _cli(cfg, "brand", "add-org", "No", "--family", "no", "--display-name", "Acme Widgets", "--write").returncode == 0
    assert _cli(cfg, "brand", "add-org", "123", "--family", "completetech", "--display-name", "Acme Widgets",
                "--write").returncode == 0
    raw = _raw(cfg)
    assert raw["families"]["no"]["measured"] is False
    assert raw["orgs"]["No"]["family"] == "no" and raw["orgs"]["123"]["family"] == "completetech"
    assert C.schema_errors(raw) == []


def test_t3_org_is_refused_without_owner_signoff(cfg):
    """A T3 org is co-owned. add-org never edits owners:, so without an owners.t3 entry the command must refuse; before
    this check an org added as T3 had no owner status and the --strict-owner gate passed it."""
    assert _cli(cfg, *ADD_FAMILY, "--write").returncode == 0
    owners_before = _raw(cfg)["owners"]
    r = _cli(cfg, "brand", "add-org", "Acme-Widgets", "--family", "acme-widgets", "--display-name", "Acme Widgets",
             "--tier", "T3", "--write")
    out = json.loads(r.stdout)
    assert r.returncode == 2 and out["result"] == "refused" and "t3-signoff" in out["logs"], r.stdout
    raw = _raw(cfg)
    assert "Acme-Widgets" not in raw["orgs"] and raw["owners"] == owners_before


def test_t3_org_is_accepted_after_owner_signoff_and_owners_stay_unchanged(cfg):
    assert _cli(cfg, *ADD_FAMILY, "--write").returncode == 0
    text = cfg.read_text(encoding="utf-8")
    signed = text.replace("t3: [Pick-Your-AI, Jevelopers-neatHack-2026]",
                          "t3: [Pick-Your-AI, Jevelopers-neatHack-2026, Acme-Widgets]", 1)
    assert signed != text  # the hand-reviewed sign-off row is the precondition
    cfg.write_text(signed, encoding="utf-8")
    owners_before = _raw(cfg)["owners"]
    r = _cli(cfg, "brand", "add-org", "Acme-Widgets", "--family", "acme-widgets", "--display-name", "Acme Widgets",
             "--tier", "T3", "--write")
    # the sign-off row alone is not enough: the global --allow-t3 gate must also be given (before the subcommand)
    assert r.returncode == 2 and "t3-signoff" in json.loads(r.stdout)["logs"], r.stdout
    assert "Acme-Widgets" not in _raw(cfg)["orgs"]
    r = _cli(cfg, "brand", "add-org", "Acme-Widgets", "--family", "acme-widgets", "--display-name", "Acme Widgets",
             "--tier", "T3", "--write", pre=("--allow-t3",))
    assert r.returncode == 0, r.stdout
    raw = _raw(cfg)
    assert raw["orgs"]["Acme-Widgets"]["tier"] == "T3" and raw["owners"] == owners_before


def test_former_slug_alias_of_an_existing_org_is_refused(cfg):
    """`Acme-Legacy` is a former login of Acme-Widgets, so it is the same org and must not get a second row."""
    assert _cli(cfg, *ADD_FAMILY, "--write").returncode == 0
    assert _cli(cfg, *ADD_ORG, "--write").returncode == 0
    text = cfg.read_text(encoding="utf-8")
    start = text.index("\n  Acme-Widgets:\n")
    at = text.index("former_slugs: []", start)
    cfg.write_text(text[:at] + "former_slugs: [Acme-Legacy]" + text[at + len("former_slugs: []"):], encoding="utf-8")
    before = cfg.read_bytes()
    r = _cli(cfg, "brand", "add-org", "Acme-Legacy", "--family", "acme-widgets", "--display-name", "Legacy", "--write")
    assert r.returncode != 0 and "already exists" in json.loads(r.stdout)["error"], r.stdout
    assert cfg.read_bytes() == before


def test_relative_path_to_default_config_still_regenerates_the_lock(tmp_path, monkeypatch):
    """A relative --config naming the default file is the default file: the lock copy must be regenerated (review fix).
    The default config and lock are redirected to temporary copies so the committed files are untouched."""
    from ctshowcase import brand_onboard as B
    (tmp_path / "references").mkdir()
    default = tmp_path / "references" / "brand.yaml"
    default.write_bytes(SRC.read_bytes())
    lock = tmp_path / "references" / "brand.lock.json"
    monkeypatch.setattr(B, "DEFAULT_CONFIG", default)
    monkeypatch.setattr(B, "LOCK", lock)
    monkeypatch.chdir(tmp_path)

    class A:
        name, company_label, accent, background = "acme-widgets", "Acme Widgets", "#22D3EE", "#0B1020"
        config, write = "references/brand.yaml", True

    obj, code = B.cmd_add_family(A)
    assert code == 0 and lock.exists() and obj["lock"] == str(lock)
