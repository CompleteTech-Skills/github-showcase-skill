"""Pins the current default detection for three misdetected repo shapes (E4.4.1, issue #80).

Fixtures under tests/fixtures/detect/ are synthetic (Northwind-*). These tests document today's
default behaviour; they must stay true while the related behaviour flags are off.

These are characterization tests, not regression tests for a bug. They pass on the base commit
2be04ac by design, because this unit changes no production code (E4.4.1 pins current defaults).
Evidence: copying this file and tests/fixtures/detect/ onto a clean `git archive` of 2be04ac gives
"3 passed". So these tests are not expected to fail on base; a failure on base would mean the
pinned default is wrong, not that the tests are broken.
A failure here means default detection changed, which needs a decision-record review before the
expected values are updated.
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


# E4.4.2 (issue #81): the OFF-by-default `detect_tuned` switch. Default behaviour is pinned above and must not change.
import pytest  # noqa: E402

from ctshowcase import config  # noqa: E402
from ctshowcase.detect import detect  # noqa: E402
from ctshowcase.errors import ConfigError  # noqa: E402


def test_planning_heavy_tuned_is_workspace():
    m = load("planning_heavy")
    out = detect(m, RepoFacts(m), {"detect_tuned": True})
    assert out["type"] == "workspace"
    assert out["rule"] == 25
    assert out["variant"] == "C"


def test_default_unchanged_without_flag():
    m = load("planning_heavy")
    out = detect(m, RepoFacts(m), {})
    assert (out["type"], out["rule"]) == ("dataset", 24)
    assert detect(m, RepoFacts(m), {"detect_tuned": False})["type"] == "dataset"


def test_real_dataset_still_dataset_when_tuned():
    m = {"owner": "Northwind-Trading-Co", "repo": "sales-data", "files": ["a.csv", "b.py"],
         "file_sizes": {"a.csv": 900, "b.py": 100}}
    assert detect_type(m, RepoFacts(m), tuned=True) == ("dataset", 24)


def test_mixed_planning_and_csv_tuned():
    # Planning JSON (5000) is excluded when tuned; the remaining 900 of 1000 bytes is data, so rule 24 still wins.
    m = {"owner": "Northwind-Trading-Co", "repo": "mixed-data",
         "files": ["planning/plan.json", "data.csv", "x.py"],
         "file_sizes": {"planning/plan.json": 5000, "data.csv": 900, "x.py": 100}}
    assert detect_type(m, RepoFacts(m), tuned=True) == ("dataset", 24)
    assert detect_type(m, RepoFacts(m)) == ("dataset", 24)


def test_mobile_variant_k_only_when_tuned():
    m = load("mobile_client")
    assert detect(m, RepoFacts(m), {})["variant"] == "B"
    assert detect(m, RepoFacts(m), {"detect_tuned": True})["variant"] == "K"
    assert variant_for("mobile-app", m) == "B"
    assert variant_for("mobile-app", m, tuned=True) == "K"
    private = dict(m, visibility="private")
    # mobile-app has no variant_private, so a private tuned repository still gets K
    assert variant_for("mobile-app", private, tuned=True) == "K"


def test_private_keeps_variant_private_when_tuned():
    m = dict(load("docs_only"), visibility="private")
    assert variant_for("workspace", m) == "I"
    assert variant_for("workspace", m, tuned=True) == "I"


def test_explicit_variant_override_wins():
    m = load("mobile_client")
    out = detect(m, RepoFacts(m), {"detect_tuned": True, "variant": "B"})
    assert out["variant"] == "B"
    assert detect(m, RepoFacts(m), {"detect_tuned": True, "type": "mobile-app"})["variant"] == "K"


def test_type_override_still_wins_when_tuned():
    m = load("planning_heavy")
    out = detect(m, RepoFacts(m), {"detect_tuned": True, "type": "dataset"})
    assert (out["type"], out["rule"]) == ("dataset", 0)


def test_file_sizes_missing_unchanged():
    m = {"owner": "Northwind-Trading-Co", "repo": "notes", "files": ["README.md"]}
    assert detect_type(m, RepoFacts(m), tuned=True) == detect_type(m, RepoFacts(m)) == ("workspace", 25)


@pytest.mark.parametrize("path,want", [
    ("planning/plan.json", True),
    ("planning/issues/001.json", True),
    (".github/ISSUE_TEMPLATE/bug.yml", True),
    ("issues/x.json", True),
    ("issue-12.json", True),
    ("docs/issue7.json", True),
    ("src/planning.json", False),
    ("data.csv", False),
    ("issue-12.yml", False),
])
def test_is_planning_helper(path, want):
    from ctshowcase.detect import _is_planning  # noqa: E402
    assert _is_planning(path) is want


def test_src_planning_json_not_excluded():
    # Path-prefix match only: a planning.json outside planning/ is ordinary data.
    m = {"owner": "Northwind-Trading-Co", "repo": "src-data", "files": ["src/planning.json", "x.py"],
         "file_sizes": {"src/planning.json": 5000, "x.py": 100}}
    assert detect_type(m, RepoFacts(m), tuned=True) == ("dataset", 24)


def test_schema_accepts_detect_tuned():
    assert config.parse_repo_override(".github/showcase.yml", "detect_tuned: true\n") == {"detect_tuned": True}
    assert config.parse_repo_override(".github/showcase.yml", "detect_tuned: false\n") == {"detect_tuned": False}


def test_schema_rejects_non_boolean_detect_tuned():
    with pytest.raises(ConfigError):
        config.parse_repo_override(".github/showcase.yml", "detect_tuned: maybe\n")
