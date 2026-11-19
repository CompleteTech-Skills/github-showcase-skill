"""Recorded-output evidence rejects unsafe paths and malformed completion claims."""
from copy import deepcopy

import pytest

from ctshowcase import provenance as P
from ctshowcase.errors import ShowcaseError


def document(brand):
    target = P.Target("repo", "Northwind-Trading-Co/tool", "Northwind-Trading-Co", "tool")
    prov = P.build_provenance(brand, target, {}, ["README.md"], None,
                              inputs_changed=True, now="2026-11-18T12:00:00Z")
    return {"provenance": prov, "evidence": {
        "version": 1, "scope": "recorded-outputs", "inputs": {}, "config_sha256": "a" * 64,
        "outputs": {"README.md": {"sha256": "b" * 64}}, "missing": [], "pending_jobs": False}}


def test_valid_and_legacy_shapes_remain_readable(brand):
    doc = document(brand)
    assert P.validate(doc) == []
    assert P.validate({"provenance": doc["provenance"]}) == []
    for reason in ("exempt:no-card", "exempt:profile-readme", "exempt:placeholder-org"):
        exempt = deepcopy(doc)
        exempt["evidence"]["outputs"]["docs/images/card.svg"] = {"exempt": reason}
        assert P.validate(exempt) == []


@pytest.mark.parametrize("path", ["../outside", "/absolute", "a//b", "a/./b", "a/../b", ".git/config",
                                  ".GIT/config", "nested/.Git/config", "a\\b", "C:relative", "a?b", "a#b",
                                  "a%b", "a\x00b", "a\x1fb", "a\x7fb"])
def test_unsafe_paths_fail_schema_and_source_preflight(brand, tmp_path, path):
    doc = document(brand)
    doc["evidence"]["outputs"] = {path: {"sha256": "b" * 64}}
    assert P.validate(doc)
    with pytest.raises(ShowcaseError, match="inside the selected source"):
        P.Source(root=tmp_path).read(path)


@pytest.mark.parametrize("field,value", [("version", True), ("scope", "whole-workflow"),
                                        ("pending_jobs", 0), ("missing", ["", "x"]),
                                        ("missing", ["x", "x"]), ("config_sha256", "short")])
def test_malformed_evidence_is_rejected(brand, field, value):
    doc = document(brand)
    doc["evidence"][field] = value
    assert P.validate(doc)


def test_unknown_output_claim_is_not_an_exemption(brand):
    doc = document(brand)
    doc["evidence"]["outputs"]["README.md"] = {"exempt": "trust-me"}
    assert P.validate(doc)


def test_unknown_evidence_fields_are_rejected(brand):
    doc = document(brand)
    doc["evidence"]["completed"] = True
    assert P.validate(doc)
