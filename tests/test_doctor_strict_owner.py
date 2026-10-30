"""`doctor --strict-owner` applies the banner/card/social owner gate; the default keeps the existing doctor behaviour."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]
META = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))


def _run(tmp_path, *argv, owner="Pick-Your-AI"):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner=owner, repo="northwind-synthetic")), encoding="utf-8")
    return subprocess.run([*SHOWCASE, "--meta", str(meta), "--no-repo-dir", *argv], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")


def test_doctor_default_unchanged_for_t3(tmp_path):
    r = _run(tmp_path, "doctor", "--format", "json")
    assert r.returncode in (0, 1), (r.stdout, r.stderr)
    assert json.loads(r.stdout)["cells"]["R7"] == "hold", r.stdout


def test_strict_owner_refuses_t3_without_allow(tmp_path):
    r = _run(tmp_path, "doctor", "--strict-owner")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "t3-signoff" in r.stdout + r.stderr


def test_strict_owner_with_global_allow_t3_runs(tmp_path):
    r = _run(tmp_path, "--allow-t3", "doctor", "--strict-owner")
    assert r.returncode != 2, (r.stdout, r.stderr)
    assert "t3-signoff" not in r.stdout + r.stderr


def test_strict_owner_refuses_unknown_org(tmp_path):
    r = _run(tmp_path, "doctor", "--strict-owner", owner="Acme-Widgets")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "unknown-org" in r.stdout + r.stderr


def test_strict_owner_accepts_known_org(tmp_path):
    r = _run(tmp_path, "doctor", "--strict-owner", owner="CompleteTech-Skills")
    assert r.returncode != 2, (r.stdout, r.stderr)
