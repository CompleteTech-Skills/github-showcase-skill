"""Epic #105 integration: the four issues (#116, #112, #119, #106) coexist on one CLI. Synthetic values only."""
from __future__ import annotations

import json

from conftest import ROOT, run_cli

META = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))


def _meta(tmp_path, owner):
    p = tmp_path / "meta.json"
    p.write_text(json.dumps(dict(META, owner=owner)), encoding="utf-8")
    return p


def test_global_and_subcommand_flags_from_all_four_issues_are_registered():
    assert "--assume-repo" in run_cli("--help").stdout  # 116
    assert "--denylist" in run_cli("lint", "--help").stdout + run_cli("lint", "public-leak", "--help").stdout  # 112
    doctor_help = run_cli("doctor", "--help").stdout
    for flag in ("--skill-verdict", "--strict-owner", "--allow-hold"):  # 119, 106
        assert flag in doctor_help, flag
    assert run_cli("brand", "add-org", "--help").returncode == 0  # 106


def test_skill_verdict_and_strict_owner_combine(tmp_path):
    r = run_cli("--meta", _meta(tmp_path, META["owner"]), "--no-repo-dir", "--assume-repo",
                f"{META['owner']}/{META['repo']}", "doctor", "--strict-owner", "--skill-verdict", "--format", "json")
    assert r.returncode in (0, 1), (r.stdout, r.stderr)
    row = json.loads(r.stdout)
    assert row["skill_complete"] in ("yes", "no")
    assert isinstance(row["owner_pending"], list)


def test_strict_owner_refusal_wins_over_skill_verdict(tmp_path):
    r = run_cli("--meta", _meta(tmp_path, "Pick-Your-AI"), "--no-repo-dir",
                "doctor", "--strict-owner", "--skill-verdict")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "t3-signoff" in r.stdout + r.stderr
