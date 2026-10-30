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
import sys
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


# Review follow-ups for detect_tuned (E4.4.2): the fingerprint, the explicit selectors and the private callout.
def test_fingerprint_type_follows_detect_tuned(tmp_path):
    # Tuned: planning JSON is ignored, so the tree is workspace. Adding a.csv (1500 of 2500 data bytes) makes it dataset.
    # The fingerprint must follow the tuned type, or the Action would skip a README regeneration.
    from ctshowcase import fingerprint  # noqa: E402

    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "showcase.yml").write_text("detect_tuned: true\n", encoding="utf-8")
    base = {"owner": "Northwind-Trading-Co", "repo": "field-data", "files": ["planning/plan.json", "src/build.py"],
            "file_sizes": {"planning/plan.json": 9000, "src/build.py": 1000}}
    grown = dict(base, files=base["files"] + ["a.csv"], file_sizes=dict(base["file_sizes"], **{"a.csv": 1500}))
    assert fingerprint.inputs(base, tmp_path)["type"] == "workspace"
    assert fingerprint.inputs(grown, tmp_path)["type"] == "dataset"
    assert fingerprint.fingerprint(fingerprint.inputs(base, tmp_path), "cfg") != \
        fingerprint.fingerprint(fingerprint.inputs(grown, tmp_path), "cfg")


def test_fingerprint_type_untouched_without_flag(tmp_path):
    from ctshowcase import fingerprint  # noqa: E402

    base = {"owner": "Northwind-Trading-Co", "repo": "field-data", "files": ["planning/plan.json", "src/build.py"],
            "file_sizes": {"planning/plan.json": 9000, "src/build.py": 1000}}
    assert fingerprint.inputs(base, tmp_path)["type"] == "dataset"
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "showcase.yml").write_text("detect_tuned: false\n", encoding="utf-8")
    assert fingerprint.inputs(base, tmp_path)["type"] == "dataset"


@pytest.mark.parametrize("text,want", [
    ("detect_tuned: true\n", True),
    ("detect_tuned: false\n", False),
    ("icon: assets/x.png\ndetect_tuned: yes  # comment\n", True),
    ("", False),
])
def test_override_tuned_with_and_without_pyyaml(text, want, monkeypatch):
    # yaml is None in sys.modules makes `import yaml` raise ImportError: the stdlib-only Action path.
    from ctshowcase import fingerprint  # noqa: E402

    assert fingerprint.override_tuned(text) is want
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert fingerprint.override_tuned(text) is want


def test_explicit_variant_k_is_accepted():
    assert config.parse_repo_override(".github/showcase.yml", "variant: K\n") == {"variant": "K"}


def test_readme_cli_accepts_variant_k():
    # run_cli lives in conftest (shared helper); the choices string shows K as the last variant
    from conftest import run_cli  # noqa: E402

    out = run_cli("readme", "--help")
    assert out.returncode == 0 and "J,K}" in out.stdout
