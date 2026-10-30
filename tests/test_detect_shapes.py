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
# The fingerprint never parses the flag: when the override names `detect_tuned`, it records the untuned `type` and the
# `type_tuned`, so a change to either regenerates. These tests pin the reviewer scenarios: a `for:` scoped away,
# flow-style YAML with PyYAML hidden, and the default with no key.
from ctshowcase import fingerprint  # noqa: E402

NORTHWIND = {"owner": "Northwind-Trading-Co", "repo": "field-data"}


def _write_override(tmp_path, text):
    (tmp_path / ".github").mkdir(exist_ok=True)
    (tmp_path / ".github" / "showcase.yml").write_text(text, encoding="utf-8")


def _fp(meta, repo_dir):
    return fingerprint.fingerprint(fingerprint.inputs(meta, repo_dir), "cfg")


def test_fingerprint_type_follows_detect_tuned(tmp_path):
    # Tuned: planning JSON is ignored, so the tree is workspace. Adding a.csv (1500 of 2500 data bytes) makes it dataset.
    # The tuned type must be fingerprinted, or the Action would skip a README regeneration.
    _write_override(tmp_path, "detect_tuned: true\n")
    base = dict(NORTHWIND, files=["planning/plan.json", "src/build.py"],
                file_sizes={"planning/plan.json": 9000, "src/build.py": 1000})
    grown = dict(base, files=base["files"] + ["a.csv"], file_sizes=dict(base["file_sizes"], **{"a.csv": 1500}))
    b, g = fingerprint.inputs(base, tmp_path), fingerprint.inputs(grown, tmp_path)
    assert (b["type"], b["type_tuned"]) == ("dataset", "workspace")
    assert (g["type"], g["type_tuned"]) == ("dataset", "dataset")
    assert _fp(base, tmp_path) != _fp(grown, tmp_path)


def test_fingerprint_flow_mapping_without_pyyaml(tmp_path, monkeypatch):
    # `{detect_tuned: true}` is valid for the schema. With PyYAML hidden (the Action's pre-install step) the flag is still
    # recorded, so removing data.csv (tuned: dataset -> workspace) changes the fingerprint.
    monkeypatch.setitem(sys.modules, "yaml", None)
    _write_override(tmp_path, "{detect_tuned: true}\n")
    with_csv = dict(NORTHWIND, files=["planning/plan.json", "src/build.py", "data.csv"],
                    file_sizes={"planning/plan.json": 9000, "src/build.py": 1000, "data.csv": 1500})
    without = dict(NORTHWIND, files=["planning/plan.json", "src/build.py"],
                   file_sizes={"planning/plan.json": 9000, "src/build.py": 1000})
    assert fingerprint.inputs(with_csv, tmp_path)["type_tuned"] == "dataset"
    assert fingerprint.inputs(without, tmp_path)["type_tuned"] == "workspace"
    assert _fp(with_csv, tmp_path) != _fp(without, tmp_path)


def test_fingerprint_escaped_detect_tuned_key(tmp_path):
    # Review finding (E4.4.3 B): `"detect\x5ftuned": true` is a valid double-quoted YAML key that enables tuning but
    # lacks the literal substring. A backslash is treated conservatively as naming the key, so the tuned type is recorded.
    _write_override(tmp_path, '"detect\\x5ftuned": true\n')
    base = dict(NORTHWIND, files=["planning/plan.json", "src/build.py"],
                file_sizes={"planning/plan.json": 9000, "src/build.py": 1000})
    grown = dict(base, files=base["files"] + ["a.csv"], file_sizes=dict(base["file_sizes"], **{"a.csv": 1500}))
    assert fingerprint.inputs(base, tmp_path)["type_tuned"] == "workspace"
    assert _fp(base, tmp_path) != _fp(grown, tmp_path)


def test_fingerprint_scoped_away_override_follows_untuned_type(tmp_path):
    # `for:` names another repository, so RepoContext drops this override and renders the untuned type. Growing
    # src/build.py moves the untuned type dataset -> workspace; the fingerprint must change even though the tuned type
    # stays workspace throughout.
    _write_override(tmp_path, "for: Northwind-Trading-Co/other\ndetect_tuned: true\n")
    base = dict(NORTHWIND, files=["planning/plan.json", "src/build.py"],
                file_sizes={"planning/plan.json": 9000, "src/build.py": 1000})
    grown = dict(base, file_sizes=dict(base["file_sizes"], **{"src/build.py": 10000}))
    assert (fingerprint.inputs(base, tmp_path)["type"], fingerprint.inputs(grown, tmp_path)["type"]) == \
        ("dataset", "workspace")
    assert _fp(base, tmp_path) != _fp(grown, tmp_path)


def test_fingerprint_manifest_override_without_checkout():
    # The metadata-only path (no checkout) reads the override from `manifests`, as RepoContext does.
    meta = dict(NORTHWIND, files=["planning/plan.json", "src/build.py"],
                file_sizes={"planning/plan.json": 9000, "src/build.py": 1000},
                manifests={".github/showcase.yml": "detect_tuned: true\n"})
    assert fingerprint.inputs(meta, None)["type_tuned"] == "workspace"


def test_fingerprint_unchanged_without_detect_tuned_key(tmp_path):
    # No key named: the inputs are exactly today's, so a default repository's fingerprint does not move.
    base = dict(NORTHWIND, files=["planning/plan.json", "src/build.py"],
                file_sizes={"planning/plan.json": 9000, "src/build.py": 1000})
    assert fingerprint.inputs(base, tmp_path)["type"] == "dataset"
    assert "type_tuned" not in fingerprint.inputs(base, tmp_path)
    _write_override(tmp_path, "icon: assets/x.png\n")
    assert "type_tuned" not in fingerprint.inputs(base, tmp_path)


def test_fingerprint_detect_tuned_false_keeps_untuned_render(tmp_path):
    # `detect_tuned: false` renders the untuned type (dataset); the tuned type is recorded beside it for audit.
    _write_override(tmp_path, "detect_tuned: false\n")
    base = dict(NORTHWIND, files=["planning/plan.json", "src/build.py"],
                file_sizes={"planning/plan.json": 9000, "src/build.py": 1000})
    inp = fingerprint.inputs(base, tmp_path)
    assert (inp["type"], inp["type_tuned"]) == ("dataset", "workspace")


def test_explicit_variant_k_is_accepted():
    assert config.parse_repo_override(".github/showcase.yml", "variant: K\n") == {"variant": "K"}


def test_readme_cli_accepts_variant_k():
    # run_cli lives in conftest (shared helper); the choices string shows K as the last variant
    from conftest import run_cli  # noqa: E402

    out = run_cli("readme", "--help")
    assert out.returncode == 0 and "J,K}" in out.stdout


# E4.4.3 (issue #82): a `type-suggestion:<type>` log when rule 24 detection is low confidence. It never changes the
# detected type; the suggestion dict is added beside it and is on by default.
NORTHWIND_SHAPE = {"owner": "Northwind-Trading-Co", "repo": "shape-check"}


def test_planning_heavy_suggests_workspace():
    m = load("planning_heavy")
    out = detect(m, RepoFacts(m))
    assert out["suggestion"]["type"] == "workspace"
    assert out["suggestion"]["key"] == "type"
    assert out["suggestion"]["file"] == ".github/showcase.yml"
    assert out["suggestion"]["reason"] == "planning-json-share"
    assert out["type"] == "dataset" and out["rule"] == 24


def test_clear_dataset_no_suggestion():
    m = dict(NORTHWIND_SHAPE, files=["a.csv", "b.py"], file_sizes={"a.csv": 900, "b.py": 100})
    out = detect(m, RepoFacts(m))
    assert (out["type"], out["rule"]) == ("dataset", 24)
    assert "suggestion" not in out
    assert 900 / 1000 >= 0.75


def test_narrow_dataset_suggests():
    m = dict(NORTHWIND_SHAPE, files=["a.csv", "b.py"], file_sizes={"a.csv": 600, "b.py": 400})
    out = detect(m, RepoFacts(m))
    assert out["type"] == "dataset"
    assert out["suggestion"]["type"] == "workspace"
    assert out["suggestion"]["reason"] == "narrow-dataset-share"


def test_type_override_no_suggestion():
    m = load("planning_heavy")
    out = detect(m, RepoFacts(m), {"type": "dataset"})
    assert (out["type"], out["rule"]) == ("dataset", 0)
    assert "suggestion" not in out


def test_tuned_planning_no_suggestion():
    m = load("planning_heavy")
    out = detect(m, RepoFacts(m), {"detect_tuned": True})
    assert out["type"] == "workspace"
    assert "suggestion" not in out


def test_context_logs_type_suggestion(make_ctx):
    m = load("planning_heavy")
    ctx = make_ctx(files=m["files"], file_sizes=m["file_sizes"])
    assert ctx.det["type"] == "dataset"
    assert "type-suggestion:workspace" in ctx.logs


def test_docs_only_no_suggestion():
    m = load("docs_only")
    out = detect(m, RepoFacts(m))
    assert out["type"] == "workspace" and "suggestion" not in out


def test_all_planning_suggests_workspace():
    # Every byte is planning JSON: the planning-excluded data share is 0% (no kept bytes), so case (a) applies.
    # Tuned detection moves this repo to workspace (rule 25), so it needs no suggestion.
    m = dict(NORTHWIND_SHAPE, files=["planning/a.json", "issues/issue1.json"],
             file_sizes={"planning/a.json": 900, "issues/issue1.json": 100})
    out = detect(m, RepoFacts(m))
    assert (out["type"], out["rule"]) == ("dataset", 24)
    assert out["suggestion"]["type"] == "workspace"
    assert out["suggestion"]["reason"] == "planning-json-share"
    tuned = detect(m, RepoFacts(m), {"detect_tuned": True})
    assert (tuned["type"], tuned["rule"]) == ("workspace", 25)
    assert "suggestion" not in tuned


def test_tuned_zero_byte_retained_file_is_workspace():
    # Review finding (E4.4.3 B): tuned detection keeps only README.md (0 bytes); 0 * 2 >= 0 must not select dataset.
    # Untuned behaviour is unchanged (dataset/24).
    m = dict(NORTHWIND_SHAPE, files=["planning/a.json", "README.md"],
             file_sizes={"planning/a.json": 900, "README.md": 0})
    tuned = detect(m, RepoFacts(m), {"detect_tuned": True})
    assert (tuned["type"], tuned["rule"]) == ("workspace", 25)
    assert "suggestion" not in tuned
    assert detect(m, RepoFacts(m))["rule"] == 24


def test_tuned_mixed_planning_data_suggests_on_kept_share():
    # Review finding (E4.4.3 B): 9000 planning + 600 csv + 400 code. Kept data share is 60% (dataset, low confidence);
    # the raw share is 96%, which must not hide the suggestion when tuned. Untuned keeps the raw-share rule (no suggestion).
    m = dict(NORTHWIND_SHAPE, files=["planning/a.json", "d.csv", "x.py"],
             file_sizes={"planning/a.json": 9000, "d.csv": 600, "x.py": 400})
    tuned = detect(m, RepoFacts(m), {"detect_tuned": True})
    assert tuned["rule"] == 24
    assert tuned["suggestion"]["reason"] == "narrow-dataset-share"
    assert "suggestion" not in detect(m, RepoFacts(m))


def test_suggestion_edge_cases_without_sizes():
    # Empty file sizes, or a zero total, never divide: no suggestion and no exception.
    assert "suggestion" not in detect(dict(NORTHWIND_SHAPE, files=["README.md"]), RepoFacts(dict(NORTHWIND_SHAPE)))
    zero = dict(NORTHWIND_SHAPE, files=["a.csv"], file_sizes={"a.csv": 0})
    assert "suggestion" not in detect(zero, RepoFacts(zero))
    from ctshowcase.detect import suggestion
    assert suggestion(zero, "dataset", 24, False) is None
    assert suggestion(NORTHWIND_SHAPE, "workspace", 25, False) is None
