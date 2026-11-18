"""Source-blind issue #201 regressions against the public showcase CLI.

Contract sources: issue acceptance, CLI --help, provenance.schema.json,
meta.schema.json, banner-layout.md and the public conftest fixture conventions.
These tests neither import the feature nor construct its private fingerprint.
All metadata and git identities are synthetic; every child process is isolated.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "showcase.py"
OWNER = "Northwind-Trading-Co"
TARGET = f"{OWNER}/support-triage-agent"


class Sandbox:
    def __init__(self, root):
        self.root = root
        self.repo = root / "target"
        self.repo.mkdir()
        self.meta = root / "meta.json"
        self.state = root / "state"
        self.tripwire = root / "network-attempts.txt"
        tools = root / "bin"
        tools.mkdir()
        guard = root / "guard"
        guard.mkdir()
        # Catch Python HTTP clients as well as requests made through gh/curl.
        (guard / "sitecustomize.py").write_text(
            "import os,sys\n"
            "def guard(event,args):\n"
            " if event in ('socket.connect','socket.getaddrinfo'):\n"
            "  with open(os.environ['CONTRACT_TRIPWIRE'],'a') as f: f.write(event+'\\n')\n"
            "  raise RuntimeError('network forbidden by synthetic test')\n"
            "sys.addaudithook(guard)\n", encoding="utf-8")
        real_git = shutil.which("git")
        assert real_git, "git is required for synthetic local origin fixtures"
        for name in ("gh", "curl", "wget", "ssh", "git"):
            script = tools / name
            script.write_text(
                f"#!{sys.executable}\nimport os,sys\n"
                + (f"if len(sys.argv)>1 and sys.argv[1] not in ('fetch','push','clone','pull','ls-remote'):\n"
                   f" os.execv({real_git!r}, [{real_git!r}]+sys.argv[1:])\n" if name == "git" else "")
                + "with open(os.environ['CONTRACT_TRIPWIRE'],'a') as f: f.write(os.path.basename(sys.argv[0])+' '+repr(sys.argv[1:])+'\\n')\n"
                + ("if os.environ.get('CONTRACT_GH_NOT_STARRED') == '1':\n print('HTTP/2.0 404 Not Found')\n sys.exit(1)\n" if name == "gh" else "")
                + "sys.exit(86)\n", encoding="utf-8")
            script.chmod(0o755)
        home = root / "home"
        home.mkdir()
        # Do not inherit authentication, host-specific config or personal identity.
        self.env = {
            "PATH": str(tools) + os.pathsep + str(Path(sys.executable).parent) + os.pathsep + os.defpath,
            "HOME": str(home), "USERPROFILE": str(home), "APPDATA": str(home),
            "XDG_CONFIG_HOME": str(home / "config"), "PYTHONPATH": str(guard),
            "SHOWCASE_STATE_DIR": str(self.state), "SHOWCASE_ESTATE_ROOT": str(root / "empty-estate"),
            "CONTRACT_TRIPWIRE": str(self.tripwire), "TMPDIR": os.environ.get("TMPDIR", str(root)),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        }
        signoff = root / "synthetic-signoffs.yaml"
        signoff.write_text(
            f"signoffs:\n  - id: synthetic-contract-only\n    owner: {OWNER}\n"
            '    repos: ["*"]\n    approved: true\n    approver: synthetic-co-owner\n'
            '    approved_on: 2026-01-15\n    expires: 2099-12-31\n', encoding="utf-8")
        self.env["SHOWCASE_T3_SIGNOFF_FILE"] = str(signoff)
        self.metadata = {
            "owner": OWNER, "repo": "support-triage-agent", "id": 12001,
            "description": "Run the Northwind support triage agent from the command line.",
            "topics": ["northwind", "cli", "python", "support", "automation"],
            "visibility": "public", "language": "Python", "license": "MIT",
            "labels": [], "files_complete": True, "files": ["README.md", "LICENSE", "pyproject.toml"],
            "homepage": "https://northwind.example/triage", "homepage_status": 200,
            "uses_custom_og_image": True, "releases": 0, "deployments": 0,
            "packages": 0, "environments": 0,
            "manifests": {"pyproject.toml": '[project]\nname="support-triage-agent"\nversion="1.0.0"\n'},
        }
        self.save_meta()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Synthetic Northwind")
        self.git("config", "user.email", "synthetic@northwind.example")
        self.git("remote", "add", "origin", f"https://github.com/{TARGET}.git")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.repo, env=self.env,
                                capture_output=True, text=True, encoding="utf-8", timeout=20)
        assert result.returncode == 0, result.stderr

    def save_meta(self):
        self.meta.write_text(json.dumps(self.metadata), encoding="utf-8")

    def cli(self, *args, meta=True, repo=True, overrides=None, json_format=True):
        argv = [sys.executable, str(CLI), "--allow-t3"]
        if meta:
            argv += ["--meta", str(self.meta)]
        argv += ["--repo-dir", str(self.repo)] if repo else ["--no-repo-dir"]
        if json_format:
            argv += ["--format", "json"]
        result = subprocess.run([*argv, *map(str, args)], cwd=self.root,
                                env={**self.env, **(overrides or {})}, capture_output=True,
                                text=True, encoding="utf-8", timeout=45)
        return result

    def check(self, *args, **kwargs):
        return self.cli("provenance", "check", TARGET, "--offline", *args, **kwargs)

    def stamp(self, *args, **kwargs):
        return self.cli("provenance", "stamp", TARGET, "--offline", *args, **kwargs)

    def data(self, result):
        assert result.stdout.strip(), (result.returncode, result.stderr)
        return json.loads(result.stdout)

    def no_network(self):
        assert not self.tripwire.exists(), self.tripwire.read_text(encoding="utf-8") if self.tripwire.exists() else ""

    def complete(self):
        (self.repo / "README.md").write_text("# Northwind support triage\n\nSynthetic local documentation.\n", encoding="utf-8")
        (self.repo / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026 Synthetic Northwind\n", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text(self.metadata["manifests"]["pyproject.toml"], encoding="utf-8")
        # Fixture input, not a replacement for generated showcase output.
        from PIL import Image
        (self.repo / "assets").mkdir()
        Image.new("RGB", (64, 64), (23, 91, 137)).save(self.repo / "assets" / "icon.png")
        for args in (("banner", "--key-chip", "Command line", "--chip", "Python"),
                     ("card", "--key-chip", "Command line", "--chip", "Python"),
                     ("content", "social", "--key-chip", "Command line", "--chip", "Python"),
                     ("readme", "--write")):
            result = self.cli(*args)
            assert result.returncode == 0, (args, result.stdout, result.stderr)
        result = self.stamp()
        assert result.returncode == 0, (result.stdout, result.stderr)
        result = self.check()
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert self.data(result)["status"] == "fresh", result.stdout
        self.no_network()


def snapshot(root):
    """Every fixture file, including git metadata, names, bytes and nanosecond mtimes."""
    return {str(p.relative_to(root)): (p.lstat().st_mode, p.lstat().st_mtime_ns,
                                      os.readlink(p) if p.is_symlink() else p.read_bytes())
            for p in root.rglob("*") if p.is_file() or p.is_symlink()}


@pytest.fixture
def box(tmp_path):
    return Sandbox(tmp_path)


def assert_not_fresh(box, result):
    assert result.returncode in (0, 1, 2, 4), (result.stdout, result.stderr)
    data = box.data(result)
    assert data.get("status") != "fresh", data
    assert data.get("complete") is not True, data


def test_empty_target_cannot_be_verified_by_stamp(box):
    assert_not_fresh(box, box.stamp())
    assert_not_fresh(box, box.check())
    box.no_network()


def test_missing_metadata_never_claims_fresh(box):
    box.metadata = {"owner": OWNER, "repo": "support-triage-agent"}
    box.save_meta()
    box.stamp()
    assert_not_fresh(box, box.check())
    box.no_network()


def test_offline_without_metadata_never_claims_fresh(box):
    assert_not_fresh(box, box.check(meta=False))
    box.no_network()


def test_complete_local_fixture_is_fresh_and_not_whole_target_skip(box):
    box.complete()
    data = box.data(box.check())
    assert data.get("skip") is False
    assert data.get("verification_scope") == "recorded-outputs"


def test_idempotent_stamp_preserves_every_target_byte_and_timestamp(box):
    box.complete()
    before = snapshot(box.repo)
    result = box.stamp("--changed", "no")
    assert result.returncode == 0, result.stdout
    assert box.data(result)["status"] == "fresh"
    assert snapshot(box.repo) == before
    box.no_network()


@pytest.mark.parametrize("name", ["banner.png", "card.svg"])
@pytest.mark.parametrize("mutation", ["delete", "change"])
def test_recorded_art_bytes_are_verified(box, name, mutation):
    box.complete()
    art = box.repo / "docs" / "images" / name
    assert art.is_file()
    if mutation == "delete":
        art.unlink()
    else:
        art.write_bytes(art.read_bytes() + b"\nsynthetic-change\n")
    result = box.check()
    assert_not_fresh(box, result)
    data = box.data(result)
    assert f"docs/images/{name}" in data.get("rerun", []), data
    box.no_network()


@pytest.mark.parametrize("mutation", ["delete", "change"])
def test_recorded_readme_is_verified(box, mutation):
    box.complete()
    readme = box.repo / "README.md"
    if mutation == "delete":
        readme.unlink()
    else:
        readme.write_text(readme.read_text(encoding="utf-8") + "\nSynthetic authored change.\n", encoding="utf-8")
    result = box.check()
    assert_not_fresh(box, result)
    assert "README.md" in box.data(result).get("rerun", []), result.stdout
    box.no_network()


@pytest.mark.parametrize("action", ["check", "stamp"])
def test_foreign_origin_refused_without_any_fixture_write(box, action):
    box.git("remote", "set-url", "origin", "https://github.com/Northwind-Other/foreign-secret-repo.git")
    (box.repo / "README.md").write_text("synthetic-foreign-sentinel-never-disclose\n", encoding="utf-8")
    before = snapshot(box.root)
    result = box.cli("provenance", action, TARGET, "--offline")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "synthetic-foreign-sentinel-never-disclose" not in result.stdout + result.stderr
    assert snapshot(box.root) == before
    box.no_network()


def test_foreign_origin_refuses_before_malformed_target_state_read(box):
    box.git("remote", "set-url", "origin", "https://github.com/Northwind-Other/foreign.git")
    sidecar = box.repo / "docs" / "images" / ".showcase.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("{malformed-foreign-sentinel", encoding="utf-8")
    before = snapshot(box.root)
    result = box.stamp()
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "malformed-foreign-sentinel" not in result.stdout + result.stderr
    assert snapshot(box.root) == before


def test_pending_writer_jobs_do_not_count_completed_runs(box):
    jobs = box.root / "pending.jsonl"
    for _ in range(5):
        result = box.stamp("--jobs", jobs, repo=False,
                           overrides={"SHOWCASE_STAR_PROMPT": "1"}, json_format=False)
        assert result.returncode in (0, 1, 4), (result.stdout, result.stderr)
    ledger = box.data(box.cli("provenance", "star"))["state"]
    assert ledger["completed_runs"] == 0, ledger
    box.no_network()


def test_pending_writer_jobs_do_not_establish_local_freshness(box):
    jobs = box.root / "pending.jsonl"
    box.stamp("--jobs", jobs, repo=False)
    assert_not_fresh(box, box.check())
    assert not (box.repo / "docs/images/.showcase.json").exists()
    box.no_network()


def test_offline_fifth_run_never_calls_network_with_tty_override(box):
    box.complete()
    for _ in range(5):
        result = box.stamp("--changed", "no", json_format=False,
                           overrides={"SHOWCASE_STAR_PROMPT": "1"})
        assert result.returncode == 0, (result.stdout, result.stderr)
    box.no_network()


def test_non_tty_marketing_silent_even_with_override(box):
    box.complete()
    for _ in range(5):
        result = box.cli("provenance", "stamp", TARGET, "--changed", "no", json_format=False,
                         overrides={"SHOWCASE_STAR_PROMPT": "1", "CONTRACT_GH_NOT_STARRED": "1"})
        assert "gh repo star" not in result.stderr, result.stderr
        assert "https://github.com/CompleteTech-Skills/github-showcase-skill" not in result.stderr
    box.no_network()


def test_unknown_network_failure_never_records_not_starred(box):
    box.complete()
    for _ in range(5):
        # Deliberately online syntax, but local synthetic evidence only. The
        # subprocess tripwire turns any attempted GET into an unknown failure.
        box.cli("provenance", "stamp", TARGET, "--changed", "no", json_format=False,
                overrides={"SHOWCASE_STAR_PROMPT": "1"})
    state = box.data(box.cli("provenance", "star"))["state"]
    assert state["star"]["status"] == "unknown", state


@pytest.mark.parametrize("foreign", ["other-showcase-tool", "github-showcase-skill-foreign"])
def test_readme_foreign_credit_preserved_or_atomically_refused(box, foreign):
    block = ("<!-- showcase:credit:start -->\n"
             f"<!-- generated-by: {foreign} v=1.0.0 std=ct-std-v1 -->\n"
             f"Foreign credit owned by {foreign}.\n<!-- showcase:credit:end -->\n")
    readme = box.repo / "README.md"
    readme.write_text("# Northwind\n\nAuthored synthetic paragraph.\n\n" + block, encoding="utf-8")
    before = snapshot(box.repo)
    result = box.cli("readme", "--write")
    if result.returncode == 0:
        assert block in readme.read_text(encoding="utf-8")
        assert "Authored synthetic paragraph." in readme.read_text(encoding="utf-8")
    else:
        assert result.returncode in (1, 2, 4), (result.stdout, result.stderr)
        assert snapshot(box.repo) == before
    box.no_network()
