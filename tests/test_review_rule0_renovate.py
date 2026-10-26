"""Review: §6.4 rule 0 reads every Renovate config location Renovate itself reads, not only `renovate.json` and
`.github/renovate.json`. A label named in `renovate.json5`, `.gitlab/renovate.json`, `.renovaterc`, the `renovate` key
of `package.json` and the rest blocks the rename on a checkout, and without a checkout each file must be proven absent
from the captured tree. Synthetic Northwind data only."""
import json

import pytest

from ctshowcase import labels

LIVE = [{"name": "bug", "color": "d73a4a", "description": "Something isn't working"}]
PLAIN = ["README.md", "LICENSE", "src/triage/agent.py", ".github/CODEOWNERS"]
HOLD = "needs-input:label-references"
CLEAN = labels.defaults_source("Northwind-Trading-Co/.github",
                               meta={"files": ["README.md", "profile/README.md"], "files_complete": True})
# Renovate's documented repository config files (besides package.json's "renovate" key)
RENOVATE = ["renovate.json", "renovate.json5", ".github/renovate.json", ".github/renovate.json5",
            ".gitlab/renovate.json", ".gitlab/renovate.json5", ".renovaterc", ".renovaterc.json", ".renovaterc.json5",
            ".gitea/renovate.json", ".gitea/renovate.json5", ".forgejo/renovate.json", ".forgejo/renovate.json5"]
CONFIG = '{\n  // Northwind triage bot\n  labels: ["dependencies", "bug"],\n}\n'


def _ops(ops):
    return {o["name"]: o for o in ops}


@pytest.mark.parametrize("path", RENOVATE)
def test_checkout_renovate_config_blocks_the_rename(tmp_path, path):
    f = tmp_path / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(CONFIG, encoding="utf-8")
    ops, logs = labels.plan(LIVE, tmp_path, defaults=CLEAN)
    assert _ops(ops)["bug"]["op"] == "skip" and _ops(ops)["bug"]["log"] == "label-referenced", ops
    assert "label-referenced" in logs


@pytest.mark.parametrize("path", RENOVATE)
def test_capture_listing_a_renovate_config_holds_the_rename(path):
    ops, logs = labels.plan(LIVE, files=PLAIN + [path], complete=True, defaults=CLEAN)
    held = _ops(ops)["bug"]
    assert held["op"] == "skip" and held["log"] == HOLD and held["check_files"] == [path], ops
    assert HOLD in logs


def test_unproven_capture_names_every_renovate_location():
    pats = set(labels.REFERENCE_PATTERNS)
    for path in RENOVATE:
        assert path in pats or path.replace(".github/", ".github/**/") in pats, path
    ops, _ = labels.plan(LIVE, files=PLAIN, complete=False, defaults=CLEAN)
    assert set(RENOVATE) - {".github/renovate.json", ".github/renovate.json5"} <= set(_ops(ops)["bug"]["check_files"])


def test_package_json_renovate_key_blocks_the_rename(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps(
        {"name": "northwind-triage", "renovate": {"packageRules": [{"matchPackageNames": ["x"], "labels": ["bug"]}]}}))
    ops, logs = labels.plan(LIVE, tmp_path, defaults=CLEAN)
    assert _ops(ops)["bug"]["log"] == "label-referenced" and "label-referenced" in logs


def test_package_json_without_renovate_key_does_not_hold(tmp_path):
    # a label word elsewhere in package.json (a description, a keyword) is not a Renovate reference
    (tmp_path / "package.json").write_text(json.dumps(
        {"name": "northwind-triage", "description": "File a bug", "keywords": ["bug"]}))
    ops, logs = labels.plan(LIVE, tmp_path, defaults=CLEAN)
    assert _ops(ops)["bug"]["op"] == "rename" and "label-referenced" not in logs


def test_package_json_renovate_key_without_the_label_does_not_hold(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps(
        {"name": "northwind-triage", "description": "File a bug", "renovate": {"labels": ["dependencies"]}}))
    ops, _ = labels.plan(LIVE, tmp_path, defaults=CLEAN)
    assert _ops(ops)["bug"]["op"] == "rename"


def test_unparseable_package_json_with_renovate_and_the_label_blocks(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "northwind-triage", "renovate": {"labels": ["bug"]},}')
    ops, _ = labels.plan(LIVE, tmp_path, defaults=CLEAN)
    assert _ops(ops)["bug"]["log"] == "label-referenced"


def test_nested_package_json_is_not_renovate_config(tmp_path):
    # Renovate reads only the root package.json
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text(json.dumps({"renovate": {"labels": ["bug"]}}))
    ops, _ = labels.plan(LIVE, tmp_path, defaults=CLEAN)
    assert _ops(ops)["bug"]["op"] == "rename"


def test_complete_capture_with_package_json_alone_does_not_hold():
    # without a checkout the capture cannot see a `renovate` key; package.json alone does not hold (references/labels.md)
    ops, logs = labels.plan(LIVE, files=PLAIN + ["package.json", "web/package.json"], complete=True, defaults=CLEAN)
    assert _ops(ops)["bug"]["op"] == "rename" and HOLD not in logs
