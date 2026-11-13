"""T3 social preview plans need a live repository-scoped consent record."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path

import pytest

from ctshowcase import signoff
from ctshowcase.config import Brand, reset_t3_signed_off, set_t3_signed_off
from ctshowcase.content import social_job
from ctshowcase.context import RepoContext

ROOT = Path(__file__).resolve().parents[1]
OWNER = "Pick-Your-AI"
REPO = "northwind-social"


def record_file(tmp_path, *, repos=None, approved=True, **overrides):
    row = {"id": "t3s-social", "owner": OWNER, "repos": repos or [REPO], "approved": approved,
           "approver": "synthetic-co-owner", "approved_on": "2026-01-15", "expires": "2099-12-31", **overrides}
    path = tmp_path / "signoffs.yaml"
    path.write_text(json.dumps({"signoffs": [row]}), encoding="utf-8")
    return path


@contextmanager
def scoped(path, *, enabled=True):
    file_token = signoff.set_file(path)
    run_token = signoff.reset()
    flag_token = set_t3_signed_off(enabled)
    try:
        yield
    finally:
        reset_t3_signed_off(flag_token)
        signoff.restore(run_token)
        signoff.reset_file(file_token)


def context(brand, **overrides):
    meta = {"owner": OWNER, "repo": REPO, "visibility": "public", "description": "Synthetic social preview.",
            "files": ["package.json"], **overrides}
    return RepoContext(brand, meta)


def test_direct_t3_job_carries_matching_record(brand, tmp_path):
    with scoped(record_file(tmp_path)):
        ctx = context(brand)
        assert ctx.social_applicable()
        job = social_job(ctx, brand.resolver(), "assets/social-preview.png")
        assert job["signoff_id"] == "t3s-social"
        assert "approval_id" not in job
        assert job["repo"] == f"{OWNER}/{REPO}"
        assert job["kind"] == "browser" and job["steps"]


@pytest.mark.parametrize("case", ["no-flag", "wrong-repo", "revoked", "missing"])
def test_t3_job_cannot_escape_scope(brand, tmp_path, case):
    path = (tmp_path / "missing.yaml" if case == "missing" else
            record_file(tmp_path, repos=["another-repository"] if case == "wrong-repo" else None,
                        approved=case != "revoked"))
    with scoped(path, enabled=case != "no-flag"):
        ctx = context(brand)
        assert not ctx.social_applicable()
        assert social_job(ctx, brand.resolver(), "assets/social-preview.png") is None


@pytest.mark.parametrize("overrides", [{"visibility": "private"}, {"archived": True}, {"fork": True},
                                      {"repo": ".github"}, {"repo": "northwind.github.io"}])
def test_t3_consent_does_not_expand_r10_surfaces(brand, tmp_path, overrides):
    with scoped(record_file(tmp_path, repos=["*"])):
        ctx = context(brand, **overrides)
        assert not ctx.social_applicable()
        assert social_job(ctx, brand.resolver(), "assets/social-preview.png") is None


@pytest.mark.parametrize("overrides", [{"expires": "2026-01-16"}, {"approved": "true"},
                                      {"repos": [None]}, {"approver": ""}])
def test_invalid_or_expired_record_never_plans_a_job(brand, tmp_path, overrides):
    with scoped(record_file(tmp_path, **overrides)):
        assert social_job(context(brand), brand.resolver(), "assets/social-preview.png") is None


def test_job_rechecks_record_after_context_was_constructed(brand, tmp_path):
    path = record_file(tmp_path)
    with scoped(path):
        ctx = context(brand)
        assert social_job(ctx, brand.resolver(), "assets/social-preview.png")["signoff_id"] == "t3s-social"
        record_file(tmp_path, approved=False)
        assert not ctx.social_applicable()
        assert social_job(ctx, brand.resolver(), "assets/social-preview.png") is None


def test_alias_job_uses_current_login_and_original_record(brand, tmp_path):
    raw = deepcopy(brand.raw)
    old_login = "Northwind-Old-CoOwned"
    raw["orgs"][OWNER]["former_slugs"] = [old_login]
    aliased = Brand(raw, brand.path)
    with scoped(record_file(tmp_path)):
        ctx = context(aliased, owner=old_login)
        job = social_job(ctx, aliased.resolver(), "assets/social-preview.png")
        assert job["repo"] == f"{OWNER}/{REPO}"
        assert job["signoff_id"] == "t3s-social"


def run_cli(tmp_path, path, *, enabled=True, owner=OWNER):
    meta = json.loads((ROOT / "examples/meta/northwind-support-triage-agent.json").read_text(encoding="utf-8"))
    meta.update(owner=owner, repo=REPO)
    mp = tmp_path / "meta.json"
    mp.write_text(json.dumps(meta), encoding="utf-8")
    out, jobs = tmp_path / "social.png", tmp_path / "jobs.jsonl"
    argv = [sys.executable, str(ROOT / "scripts/showcase.py"), "--meta", str(mp), "--no-repo-dir",
            "--t3-signoff-file", str(path)]
    if enabled:
        argv.append("--allow-t3")
    argv += ["content", "social", "--out", str(out), "--job", "--jobs", str(jobs), "--allow-unmeasured"]
    env = dict(os.environ)
    env.pop("SHOWCASE_T3_SIGNOFF_FILE", None)
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return result, out, jobs


def test_cli_scoped_consent_emits_and_serializes_upload_job(tmp_path):
    result, out, jobs = run_cli(tmp_path, record_file(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert out.is_file()
    job = data["job"]
    assert job["repo"] == f"{OWNER}/{REPO}" and job["signoff_id"] == "t3s-social"
    assert json.loads(jobs.read_text(encoding="utf-8")) == job
    assert data["footer"] == f"github.com/{job['repo']}"


@pytest.mark.parametrize("case", ["no-flag", "wrong-repo", "revoked", "missing", "excluded", "expired", "malformed"])
def test_cli_t3_refuses_before_render_or_job_write(tmp_path, case):
    path = (tmp_path / "missing.yaml" if case == "missing" else
            record_file(tmp_path, repos=["another-repository"] if case == "wrong-repo" else None,
                        approved="true" if case == "malformed" else case != "revoked",
                        expires="2026-01-16" if case == "expired" else "2099-12-31"))
    result, out, jobs = run_cli(tmp_path, path, enabled=case != "no-flag",
                                owner="BunsDev" if case == "excluded" else OWNER)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["result"] == "refused"
    assert not out.exists() and not jobs.exists()
