"""Review round 2 regressions: the first project status update is planned once (never twice, never one id with two
contents), the Action skips only a held README, a partner logo in a credited centred block is never taken for the
footer. Synthetic Northwind fixtures only."""
import copy
import datetime
import json
import os
import shutil
import sys

import yaml
import pytest

from conftest import EX, ROOT, run_bash, run_cli
from ctshowcase import footer, readme
from ctshowcase import project as PJ
from ctshowcase.resolver import Resolver

N = "Northwind-Trading-Co"
PFIX = ROOT / "tests" / "fixtures" / "project"
CAPTURE = json.loads((PFIX / "copy-capture.json").read_text(encoding="utf-8"))


def _resolver(brand):
    return Resolver(brand, {}, {"rows": [], "ids": set(), "actions": set()})


def _capture(*views, updates=()):
    c = copy.deepcopy(CAPTURE)
    p = c["data"]["organization"]["projectV2"]
    for i, name in views:
        p["views"]["nodes"].append(dict(p["views"]["nodes"][2], id=f"PVTV_n{i}", number=i, name=name, filter=""))
    p["statusUpdates"]["nodes"] = list(updates)
    return c


def _plan_on(day, capture, brand, monkeypatch):
    class Day(datetime.date):
        @classmethod
        def today(cls):
            return cls(*day)
    monkeypatch.setattr(PJ, "date", Day)
    plan = PJ.copy_plan(N, copied=capture, resolver=_resolver(brand), reviewed="2026-10-25")
    return plan, [j for j in plan["jobs"] if "-status-1" in j["id"]]


# ------------------------------------------------------------------------- the first status update, planned once
def test_first_status_update_is_planned_once_across_stage_two_replans(brand, monkeypatch):
    pending, s0 = _plan_on((2026, 10, 26), _capture(), brand, monkeypatch)  # the plan creates My items and Shipped
    assert s0 == [] and "status-update:shipped-view-pending" in pending["logs"]
    assert any("first status update" in p["why"] for p in pending["pending"])
    seen = {}
    for day in ((2026, 10, 26), (2026, 10, 27), (2026, 12, 31)):
        for views in (((7, "Shipped"),), ((6, "My items"), (7, "Shipped"))):  # My items still missing, then all views
            _, jobs = _plan_on(day, _capture(*views), brand, monkeypatch)
            assert len(jobs) == 1
            assert seen.setdefault(jobs[0]["id"], jobs[0]["argv"]) == jobs[0]["argv"], "one id, two contents"
    assert len(seen) == 1, sorted(seen)
    argv = next(iter(seen.values()))
    assert 'startDate: "2026-10-01", targetDate: "2026-12-31"' in argv[4]
    assert any(a.startswith("body=") and "projects/3/views/7)" in a for a in argv)


def test_no_status_update_when_the_board_already_has_one(brand, monkeypatch):
    plan, jobs = _plan_on((2026, 10, 26), _capture((6, "My items"), (7, "Shipped"),
                                                   updates=[{"id": "PVTSU_1", "body": "Board set up."}]), brand, monkeypatch)
    assert jobs == [] and "status-update:exists" in plan["logs"]


# ------------------------------------------------------------------------- Action: only a held README is skipped
def _generate(tmp_path, showcase_yml):
    step = next(s for s in yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))["runs"]["steps"] if s.get("id") == "generate")
    repo, rt = tmp_path / "repo", tmp_path / "rt"
    shutil.copytree(EX / "repos" / "northwind-support-triage-agent", repo)
    rt.mkdir()
    (repo / ".github").mkdir(exist_ok=True)
    (repo / ".github" / "showcase.yml").write_text(showcase_yml, encoding="utf-8")
    shutil.copy(EX / "meta" / "northwind-support-triage-agent.json", rt / "meta.json")
    out = tmp_path / "gh_out"
    out.write_text("", encoding="utf-8")
    env = dict(os.environ, GITHUB_ACTION_PATH=str(ROOT), RUNNER_TEMP=str(rt), GITHUB_OUTPUT=str(out),
               GITHUB_REPOSITORY=f"{N}/support-triage-agent", SHOWCASE_OUTPUTS="", SHOWCASE_README="header",
               SHOWCASE_IS_TEMPLATE="false", SHOWCASE_ALLOW_UNMEASURED="false",
               PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""))
    p = run_bash(step["run"], cwd=repo, env=env)
    return p, out.read_text(encoding="utf-8")


@pytest.mark.requires_bash
def test_action_fails_on_a_readme_config_error(tmp_path):
    p, outputs = _generate(tmp_path, 'accent: "#FF0000"\n')
    assert p.returncode == 2, p.stdout + p.stderr
    assert "skipped=1" not in outputs and "README skipped" not in p.stdout and '"config"' in p.stdout


# ------------------------------------------------------------------------- a partner logo is never the footer's
PARTNER = ('<p align="center">\n  <img src="docs/images/globex-logo.png" alt="Globex, our launch partner" width="120"><br>\n'
           '  Built by <a href="https://www.complete.tech">CompleteTech LLC</a>\n</p>\n')


def test_footer_copy_needs_the_footers_own_logo(brand):
    f = brand.raw["footer"]
    exact = footer.markup(brand)
    assert readme.is_footer_copy(exact, brand)
    drifted = exact.replace(f["logo_light_url"], f["logo_light_url"].replace("/main/", "/master/") + "?v=2")
    assert readme.is_footer_copy(drifted, brand)
    assert not readme.is_footer_copy(PARTNER, brand)
    assert not readme.is_footer_copy(exact.replace(f["logo_dark_url"], "https://example.com/acme-logo-dark.png"), brand)


def test_upgrade_keeps_a_partner_logo_in_a_credited_block(tmp_path, brand):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Support Triage Agent\n\nTriage agent.\n\n## Usage\n\nRun it.\n\n" + PARTNER, encoding="utf-8")
    p = run_cli("--meta", EX / "meta" / "northwind-support-triage-agent.json", "--repo-dir", repo, "--format", "json",
                "readme", "--mode", "upgrade", "--write")
    out = json.loads(p.stdout)
    assert p.returncode == 0 and out["result"] == "changed", p.stdout + p.stderr
    text = (repo / "README.md").read_text(encoding="utf-8")
    assert all(ln in text.splitlines() for ln in PARTNER.splitlines())  # the whole block, partner logo included
    assert footer.check(brand, text)[0] == "fail:duplicate"
