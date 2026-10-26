import shutil

from conftest import EX, FIX, run_cli
from ctshowcase import doctor


def test_unknown_without_repo_dir():
    p = run_cli("--meta", FIX / "CompleteTech-Skills__agentic-email-skill.json", "--no-repo-dir", "doctor", "--header")
    head, row = p.stdout.strip().splitlines()
    assert head.split("\t")[:4] == ["owner/repo", "type", "variant", "R1"]
    cells = dict(zip(head.split("\t"), row.split("\t")))
    assert cells["R7"] == "unknown" and cells["banner"] == "unknown" and cells["R10"] == "unknown"
    assert p.returncode == 1  # topics differ from the §5.6 proposal (R3 fail)


def test_full_repo_dir(tmp_path):
    shutil.copytree(EX / "repos" / "northwind-support-triage-agent", tmp_path, dirs_exist_ok=True)
    meta = EX / "meta" / "northwind-support-triage-agent.json"
    run_cli("--meta", meta, "--repo-dir", tmp_path, "banner", "--out", tmp_path / "docs/images/banner.png")
    run_cli("--meta", meta, "--repo-dir", tmp_path, "card", "--out", tmp_path / "docs/images/card.svg")
    run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "scaffold", "--write")
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "doctor", "--format", "json")
    import json
    r = json.loads(p.stdout)
    assert r["cells"]["banner"] == "pass" and r["cells"]["card"] == "pass" and r["cells"]["footer"] == "pass"
    assert r["cells"]["icon"] == "fail"  # decision 12: no assets/icon.png yet
    assert r["cells"]["R7"] in ("pass", "incomplete")
    assert doctor.COLUMNS[-4:] == ["banner", "icon", "card", "footer"]
