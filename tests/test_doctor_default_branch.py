"""R5 keeps upstream branch policy and explicit user keep decisions."""
import json

import pytest

from conftest import meta_dict, run_cli
from ctshowcase import doctor


@pytest.mark.parametrize("dbom", [None, False, True])
def test_forks_keep_upstream_default(make_ctx, dbom):
    ctx = make_ctx(fork=True, default_branch="develop", has_issues=False, delete_branch_on_merge=dbom)
    assert doctor.row(ctx)["cells"]["R5"] == "pass"


@pytest.mark.parametrize("policy,expected", [("keep", "pass"), (None, "fail"), (True, "fail"), ("rename", "fail")])
def test_nonmain_default_needs_explicit_keep(make_ctx, policy, expected):
    ctx = make_ctx(default_branch="master", default_branch_policy=policy, has_issues=True, delete_branch_on_merge=True)
    result = doctor.row(ctx)
    assert result["cells"]["R5"] == expected
    assert ("default-branch kept (user)" in result["logs"]) == (policy == "keep")


@pytest.mark.parametrize("issues,dbom,expected", [(False, True, "fail"), (True, False, "fail"), (True, None, "unknown")])
def test_keep_decision_preserves_other_settings(make_ctx, issues, dbom, expected):
    ctx = make_ctx(default_branch="master", default_branch_policy="keep", has_issues=issues, delete_branch_on_merge=dbom)
    assert doctor.row(ctx)["cells"]["R5"] == expected


def test_github_settings_do_not_require_issues(make_ctx):
    ctx = make_ctx(repo=".github", default_branch="main", has_issues=False, delete_branch_on_merge=True)
    assert doctor.row(ctx)["cells"]["R5"] == "pass"


def test_keep_policy_survives_cli_metadata_normalization(tmp_path):
    meta = tmp_path / "northwind.json"
    meta.write_text(json.dumps(meta_dict(default_branch="master", default_branch_policy="keep", has_issues=True,
                                        delete_branch_on_merge=True)), encoding="utf-8")
    result = run_cli("--meta", meta, "--no-repo-dir", "doctor", "--format", "json")
    assert result.returncode in (0, 1), result.stderr
    row = json.loads(result.stdout)
    assert row["cells"]["R5"] == "pass"
    assert "default-branch kept (user)" in row["logs"]
