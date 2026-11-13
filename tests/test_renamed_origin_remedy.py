import subprocess

from conftest import EX, run_cli


def test_unrecorded_rename_names_safe_local_remedy(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    old = "https://github.com/Northwind-Trading-Co/old-synthetic-repo.git"
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", old], check=True)
    result = run_cli("--meta", EX / "meta/northwind-support-triage-agent.json", "--repo-dir", tmp_path, "doctor")
    assert result.returncode == 2
    diagnostic = result.stdout + result.stderr
    assert "remote set-url origin" in diagnostic
    assert "https://github.com/Northwind-Trading-Co/support-triage-agent.git" in diagnostic
    assert "verified rename" in diagnostic
    # The CLI only describes the fix; the user decides whether identity is verified.
    unchanged = subprocess.check_output(["git", "-C", str(tmp_path), "remote", "get-url", "origin"], text=True).strip()
    assert unchanged == old
