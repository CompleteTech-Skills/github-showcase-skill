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


def _cli(config, *argv, meta=None):
    cmd = [sys.executable, str(ROOT / "scripts" / "showcase.py"), "--config", str(config)]
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
