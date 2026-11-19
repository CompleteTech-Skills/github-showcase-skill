"""Org profile and About wording comes from the brand config's `operator.profile` block, never from code."""
import argparse
import copy
import json

import pytest
import yaml

from conftest import ROOT
from ctshowcase import org as O
from ctshowcase.config import load_brand

FIX = ROOT / "tests" / "fixtures" / "org"
N = "Northwind-Trading-Co"
OURS = ("CompleteTechLLC", "All CompleteTech", "Also from CompleteTech", "A CompleteTech LLC organization",
        "Steward: CompleteTech LLC", "github.com/CompleteDotTech", "Public CompleteTech projects")


def _run(tmp_path, action, config=None, *extra):
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    O.register(p.add_subparsers(dest="command"))
    argv = (["--config", str(config)] if config else []) + [
        "org", action, N, "--registry", str(FIX / "registry.yaml"), "--meta-dir", str(FIX / "meta"),
        "--approved", str(tmp_path / "none.tsv"), "--approved-yaml", str(tmp_path / "none.yaml"),
        "--actions", str(tmp_path / "none.json"), "--decisions", str(tmp_path / "none.json"), *extra]
    args = p.parse_args(argv)
    return args.func(args)


def _config_without_profile(tmp_path):
    raw = copy.deepcopy(load_brand().raw)
    raw["operator"].pop("profile")
    cfg = tmp_path / "brand.yaml"
    cfg.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return cfg


def test_no_estate_wording_left_in_org_py():
    src = (ROOT / "scripts" / "ctshowcase" / "org.py").read_text(encoding="utf-8")
    for needle in ("CompleteTechLLC", "All CompleteTech", "Also from CompleteTech", "A CompleteTech LLC organization",
                   "Steward: CompleteTech LLC", "PRIVATE_LINE", "X_HANDLE", "USER_LOGIN", 'family") == "completetech"'):
        assert needle not in src, needle


def test_our_config_keeps_our_wording(tmp_path):
    res, _ = _run(tmp_path, "profile", None, "--allow-t3")
    text = json.dumps(res)
    for needle in ("CompleteTechLLC", "All CompleteTech", "Also from CompleteTech", "A CompleteTech LLC organization"):
        assert needle in text, needle


def test_config_without_profile_strings_borrows_none(tmp_path):
    cfg = _config_without_profile(tmp_path)
    res, _ = _run(tmp_path, "profile", cfg, "--allow-t3")
    text = json.dumps(res)
    for needle in OURS:
        assert needle not in text, needle


def test_about_withholds_the_x_handle_without_one(tmp_path):
    ours, _ = _run(tmp_path, "about")
    assert "CompleteTechLLC" in json.dumps(ours)
    res, _ = _run(tmp_path, "about", _config_without_profile(tmp_path))
    assert "CompleteTechLLC" not in json.dumps(res)
    assert "needs-input:x-handle" in res["logs"]


def test_personal_profile_needs_an_operator_login(tmp_path):
    raw = copy.deepcopy(load_brand().raw)
    raw.pop("operator")
    cfg = tmp_path / "brand.yaml"
    cfg.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    from ctshowcase.config import Brand
    from ctshowcase.errors import NeedsInput
    from ctshowcase.resolver import Resolver
    b = Brand(raw, cfg)
    estate = O.Estate(b, Resolver(b, {}, None))
    assert estate.user_login is None and estate.profile_strings == {}
    with pytest.raises(NeedsInput) as e:
        O.user_profile(estate, "CompleteDotTech")
    assert e.value.log == "needs-input:operator-login"
