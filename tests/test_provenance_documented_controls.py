"""Additive source-blind controls for the documented issue-201 contract.

Premises: references/provenance.md (recorded snapshot bytes, four supplied
sections, whole configured credit, version/HTML equivalence and no-regroup),
BRANDING.md and issue159/201. This module does not replace the frozen 29 cases.
All execution is disposable local CLI execution with transport tripwires.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys

import pytest

from ctshowcase import footer

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "examples/meta/northwind-support-triage-agent.json"
SLUG = "Northwind-Trading-Co/support-triage-agent"
SECTIONS = ("profile", "organizations", "members", "outside_collaborators")
AUTHORED = b"## Authored notes\n\nKeep these exact bytes.  \n\tIndented detail.\n"
# Independent exact footer contract, from decision18 and the public brand URLs.
DECISION18 = '''<p align="center">
  <a href="https://www.complete.tech">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/CompleteTech-Skills/github-showcase-skill/main/assets/brand/logo-dark.png">
      <img src="https://raw.githubusercontent.com/CompleteTech-Skills/github-showcase-skill/main/assets/brand/logo.png" alt="CompleteTech LLC" width="200">
    </picture>
  </a>
  <br>
  Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration
</p>'''


@pytest.fixture(autouse=True)
def prohibit_parent_sockets(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("documented controls prohibit live sockets")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def guarded_env(tmp_path):
    guard = tmp_path / "transport-guard"
    guard.mkdir()
    tripwire = guard / "attempted-transport"
    (guard / "sitecustomize.py").write_text(
        "import os, pathlib, socket, sys\n"
        "def denied(*a, **k):\n"
        " pathlib.Path(os.environ['DOCUMENTED_TRANSPORT_TRIPWIRE']).write_text('blocked')\n"
        " raise AssertionError('documented controls prohibit transport')\n"
        "def audit(event, args):\n"
        " if event == 'subprocess.Popen' and pathlib.Path(str(args[0])).name "
        "in ('gh', 'curl', 'wget'):\n  denied()\n"
        "sys.addaudithook(audit)\n"
        "socket.socket.connect = denied\nsocket.create_connection = denied\n",
        encoding="utf-8",
    )
    for name in ("gh", "curl", "wget"):
        shim = guard / name
        shim.write_text(
            '#!/bin/sh\nprintf blocked > "$DOCUMENTED_TRANSPORT_TRIPWIRE"\nexit 97\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
    return dict(os.environ, PATH=str(guard) + os.pathsep + os.environ["PATH"],
                PYTHONPATH=str(guard), PYTHONDONTWRITEBYTECODE="1", CI="true",
                SHOWCASE_STATE_DIR=str(guard / "state"),
                DOCUMENTED_TRANSPORT_TRIPWIRE=str(tripwire))


def cli(env, *args):
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts/showcase.py"), *map(str, args)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert not Path(env["DOCUMENTED_TRANSPORT_TRIPWIRE"]).exists(), (p.stdout, p.stderr)
    return p


def enterprise(env, registry, supplied, action):
    p = cli(env, "provenance", action, "enterprise:completetech", "--out-dir", registry,
            "--snapshot", supplied, "--offline", "--format", "json")
    assert p.stdout.strip(), (p.returncode, p.stderr)
    return p, json.loads(p.stdout)


@pytest.fixture
def complete_capture(tmp_path):
    # Captured empty collections are known data, not absent sections. This is a
    # synthetic capture, not an assertion that Enterprise doctor would pass.
    data = json.loads((ROOT / "tests/fixtures/enterprise/snapshot-before.json").read_text())
    profile = data["sections"]["profile"]
    profile.update(description="Synthetic captured enterprise", location="Synthetic location",
                   readme="Synthetic captured README", billingInfo={
                       "totalLicenses": 0, "totalAvailableLicenses": 0,
                       "allLicensableUsersCount": 0})
    profile["ownerInfo"]["admins"]["edges"] = []
    profile["ownerInfo"]["domains"]["nodes"] = []
    profile["ownerInfo"]["pendingMemberInvitations"] = {"totalCount": 0, "nodes": []}
    for section in SECTIONS[1:]:
        data["sections"][section] = []
    data["sha256"] = {
        key: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        for key, value in data["sections"].items()
    }
    registry = tmp_path / "registry"
    registry.mkdir()
    actual = registry / "enterprise.snapshot.json"
    actual.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    supplied = tmp_path / "independent-captured-input.json"
    shutil.copyfile(actual, supplied)
    return registry, actual, supplied


def require_fresh(p, report):
    assert p.returncode == 0 and report["status"] == "fresh", (p.stderr, report)
    assert report["verification_scope"] == "recorded-outputs"
    assert report["skip"] is False


def test_complete_private_snapshot_is_fresh_and_stamp_is_idempotent(guarded_env, complete_capture):
    registry, actual, supplied = complete_capture
    jobs = registry.parent / "public-jobs.jsonl"
    p = cli(guarded_env, "provenance", "stamp", "enterprise:completetech", "--out-dir", registry,
            "--snapshot", actual, "--jobs", jobs, "--offline", "--format", "json")
    assert p.returncode == 0, (p.stdout, p.stderr)
    stamp = registry / "enterprise.showcase.json"
    assert stamp.is_file()
    assert not jobs.exists() or not jobs.read_bytes().strip()
    require_fresh(*enterprise(guarded_env, registry, supplied, "check"))
    before = stamp.read_bytes()
    p, _ = enterprise(guarded_env, registry, actual, "stamp")
    assert p.returncode == 0, p.stderr
    assert stamp.read_bytes() == before


@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_recorded_snapshot_bytes_are_required(guarded_env, complete_capture, mutation):
    registry, actual, supplied = complete_capture
    p, _ = enterprise(guarded_env, registry, actual, "stamp")
    assert p.returncode == 0, p.stderr
    require_fresh(*enterprise(guarded_env, registry, supplied, "check"))
    original_input = supplied.read_bytes()
    if mutation == "missing":
        actual.unlink()
    else:
        data = json.loads(actual.read_text())
        data["sections"]["profile"]["description"] = "Changed synthetic recorded output"
        actual.write_text(json.dumps(data), encoding="utf-8")
    p, report = enterprise(guarded_env, registry, supplied, "check")
    assert p.returncode != 0 and report["status"] != "fresh", report
    assert "snapshot" in json.dumps(report).lower(), report
    assert supplied.read_bytes() == original_input


@pytest.mark.parametrize("section", SECTIONS)
def test_missing_capture_section_cannot_be_fresh(guarded_env, complete_capture, section):
    registry, actual, supplied = complete_capture
    data = json.loads(actual.read_text())
    del data["sections"][section]
    data["sha256"].pop(section)
    actual.write_text(json.dumps(data), encoding="utf-8")
    shutil.copyfile(actual, supplied)
    p, stamped = enterprise(guarded_env, registry, supplied, "stamp")
    assert p.returncode in (0, 1, 2, 4), (p.stdout, p.stderr)
    p, report = enterprise(guarded_env, registry, supplied, "check")
    assert report.get("status") != "fresh", report
    assert section in json.dumps([stamped, report]).lower(), (stamped, report)


def checkout(tmp_path, brand, credit):
    repo = tmp_path / "checkout"
    shutil.copytree(ROOT / "examples/repos/northwind-support-triage-agent", repo)
    for argv in (("init", "-q"), ("remote", "add", "origin", "https://github.com/" + SLUG + ".git")):
        subprocess.run(["git", "-C", str(repo), *argv], check=True, capture_output=True, timeout=10)
    path = repo / "README.md"
    path.write_bytes(b"# Synthetic tool\n\n" + AUTHORED + b"\n" +
                     footer.footer_block(brand).encode() + b"\n\n" + credit.encode() + b"\n")
    return repo, path


def older_credit(brand):
    current = footer.credit_block(brand)
    assert "README styled with" in current  # configured documented visible wording
    older, count = re.subn(r"(?<= v=)[^\s>]+", "0.9.0", current)
    assert count == 1 and older != current
    return older


def refresh(env, repo, *extra):
    return cli(env, "--meta", META, "--repo-dir", repo, "readme", "--mode", "upgrade",
               "--write", *extra)


@pytest.mark.parametrize("equivalent_html", [False, True], ids=["version-only", "equivalent-html"])
def test_proven_credit_moves_before_exact_final_footer(guarded_env, tmp_path, brand, equivalent_html):
    credit = older_credit(brand)
    if equivalent_html:
        credit = credit.replace('align="center"', "align='center'")
    repo, path = checkout(tmp_path, brand, credit)
    p = refresh(guarded_env, repo)
    assert p.returncode == 0, (p.stdout, p.stderr)
    after = path.read_bytes()
    text = after.decode()
    assert AUTHORED in after
    assert footer.credit_line(brand) in text
    assert "v=0.9.0" not in text
    assert text.count(footer.CREDIT_START) == 1
    assert text.count(DECISION18) == 1 and text.count("<picture>") == 1
    assert text.rstrip().endswith(footer.END)
    assert text.index(footer.CREDIT_START) < text.index(DECISION18)
    assert footer.check(brand, text)[0] == "pass"
    p = refresh(guarded_env, repo)
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert path.read_bytes() == after


@pytest.mark.parametrize("reason", ["altered-prefix", "no-regroup"])
def test_ambiguous_credit_or_forbidden_regroup_refuses_atomically(guarded_env, tmp_path, brand, reason):
    credit = older_credit(brand)
    if reason == "altered-prefix":
        credit = credit.replace("README styled with", "Styled with")
    repo, _ = checkout(tmp_path, brand, credit)
    before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    p = refresh(guarded_env, repo, *(["--no-regroup"] if reason == "no-regroup" else []))
    assert p.returncode != 0, (p.stdout, p.stderr)
    after = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    assert after == before, (p.stdout, p.stderr)
