"""Coverage cells follow the documented applicability of each surface."""
import json

import pytest

from conftest import meta_dict, run_cli
from ctshowcase import doctor
from ctshowcase.content import social_job


@pytest.mark.parametrize("has_issues,repo,archived,expected", [
    (False, "support-triage-agent", False, "n/a"),
    (False, "support-triage-agent", True, "n/a"),
    (False, ".github", False, "unknown"),
    (True, "support-triage-agent", True, "unknown"),
    (None, "support-triage-agent", False, "unknown"),
])
def test_r6_disabled_issues_and_archived_coverage(make_ctx, has_issues, repo, archived, expected):
    ctx = make_ctx(has_issues=has_issues, repo=repo, archived=archived)
    assert doctor.row(ctx)["cells"]["R6"] == expected


@pytest.mark.parametrize("surface", ["private", "archived", "fork", ".github", "pages", "watching", "co-owned"])
@pytest.mark.parametrize("captured", [False, True, None])
def test_r10_inapplicable_surfaces(make_ctx, surface, captured):
    kw = {"uses_custom_og_image": captured}
    if surface == "private":
        kw["visibility"] = "private"
    elif surface in ("archived", "fork"):
        kw[surface] = True
    elif surface in (".github", "pages"):
        kw["repo"] = ".github" if surface == ".github" else "northwind.github.io"
    ctx = make_ctx(**kw)
    if surface == "watching":
        ctx.org = dict(ctx.org, tier="T2-R")
    if surface == "co-owned":
        ctx.org = dict(ctx.org, tier="T3")
    assert doctor.row(ctx)["cells"]["R10"] == "n/a"
    assert social_job(ctx, ctx.brand.resolver(), "assets/social-preview.png") is None


@pytest.mark.parametrize("tier", ["T1", "T2", "T1-user"])
@pytest.mark.parametrize("captured,expected", [(False, "fail"), (True, "pass"), (None, "unknown")])
def test_r10_applicable_capture(make_ctx, tier, captured, expected):
    ctx = make_ctx(uses_custom_og_image=captured)
    ctx.org = dict(ctx.org, tier=tier)
    assert doctor.row(ctx)["cells"]["R10"] == expected


def test_r10_personal_profile_capstone(make_ctx):
    ctx = make_ctx(owner="Northwind-Trading-Co", repo="Northwind-Trading-Co", uses_custom_og_image=False)
    ctx.org = dict(ctx.org, tier="T1-user")
    ctx.det = dict(ctx.det, type="github-profile")
    assert doctor.row(ctx)["cells"]["R10"] == "fail"
    assert social_job(ctx, ctx.brand.resolver(), "assets/social-preview.png") is not None


@pytest.mark.parametrize("percentage", [50, 100, None])
def test_r11_archived_health_not_applicable(make_ctx, percentage):
    ctx = make_ctx(archived=True, health_percentage=percentage)
    assert doctor.row(ctx)["cells"]["R11"] == "n/a"


@pytest.mark.parametrize("percentage,expected", [(50, "fail"), (100, "pass"), (None, "unknown")])
def test_r11_active_capture(make_ctx, percentage, expected):
    assert doctor.row(make_ctx(health_percentage=percentage))["cells"]["R11"] == expected


def test_r11_coowned_health_not_applicable(make_ctx):
    ctx = make_ctx(health_percentage=50)
    ctx.org = dict(ctx.org, tier="T3")
    assert doctor.row(ctx)["cells"]["R11"] == "n/a"


def test_cli_reports_surface_applicability(tmp_path):
    meta = tmp_path / "northwind.json"
    meta.write_text(json.dumps(meta_dict(archived=True, has_issues=False,
                                        uses_custom_og_image=False, health_percentage=50)), encoding="utf-8")
    result = run_cli("--meta", meta, "--no-repo-dir", "doctor", "--format", "json")
    assert result.returncode in (0, 1), result.stderr
    cells = json.loads(result.stdout)["cells"]
    assert {key: cells[key] for key in ("R6", "R10", "R11")} == dict.fromkeys(("R6", "R10", "R11"), "n/a")
