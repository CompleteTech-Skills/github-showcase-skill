"""Pins the current default detection for three misdetected repo shapes (E4.4.1, issue #80).

Fixtures under tests/fixtures/detect/ are synthetic (Northwind-*). These tests document today's
default behaviour; they must stay true while the related behaviour flags are off.

These are characterization tests, not regression tests for a bug. They pass on the base commit
2be04ac by design, because this unit changes no production code (E4.4.1 pins current defaults).
A failure here means default detection changed, which needs a decision-record review before the
expected values are updated. Verify on base by copying this file and tests/fixtures/detect/ onto
2be04ac; all three tests should pass there.
"""
import json
from pathlib import Path

from ctshowcase.detect import detect_type, variant_for
from ctshowcase.facts import RepoFacts

FIXTURES = Path(__file__).parent / "fixtures" / "detect"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_planning_heavy_default_is_dataset():
    # Planning JSON is 9000 of 10500 bytes (>= half), so rule 24 wins by default.
    m = load("planning_heavy")
    assert detect_type(m, RepoFacts(m)) == ("dataset", 24)


def test_docs_only_is_workspace():
    m = load("docs_only")
    assert detect_type(m, RepoFacts(m)) == ("workspace", 25)
    assert variant_for("workspace", m) == "C"


def test_mobile_client_default_variant():
    m = load("mobile_client")
    assert detect_type(m, RepoFacts(m)) == ("mobile-app", 13)
    assert variant_for("mobile-app", m) == "B"
