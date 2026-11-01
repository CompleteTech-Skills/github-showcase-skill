"""Writer-shaped proposals carry the granting sign-off (issue 23, round 13). `content actions --allow-t3` on a kept fork of
a T3 owner with upstream-only automation proposes a `workflow-toggle` writer job under `proposals` (no --approval, so it is
not queued). The proposal carries `signoff_id` in the --report file and on stdout, stays out of the --jobs writer queue
and never gains an approval_id. Synthetic records and slugs only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]
META = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))
OWNER = "Pick-Your-AI"
CLA = ("name: CLA\non: [pull_request_target]\njobs:\n  c:\n    runs-on: x\n    steps:\n"
       "      - uses: contributor-assistant/github-action@v2\n")


def _rec(repos):
    return {"id": "t3s-fork", "owner": OWNER, "repos": repos, "approved": True, "approver": "synthetic-co-owner",
            "approved_on": "2026-01-15", "expires": "2099-12-31"}


def _setup(tmp_path, repos, repo="tool-fork"):
    (tmp_path / "repo" / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "repo" / ".github" / "workflows" / "cla.yml").write_text(CLA, encoding="utf-8")
    (tmp_path / "meta.json").write_text(json.dumps(dict(META, owner=OWNER, repo=repo, fork=True,
                                                         parent={"full_name": "upstream-org/tool"})), encoding="utf-8")
    (tmp_path / "wf.json").write_text(json.dumps({"workflows": [
        {"id": 21, "name": "CLA", "path": ".github/workflows/cla.yml", "state": "active"}]}), encoding="utf-8")
    (tmp_path / "s.yaml").write_text(json.dumps({"signoffs": [_rec(repos)]}), encoding="utf-8")


def _argv(tmp_path, *, allow=True):
    t = tmp_path
    return [*(["--allow-t3"] if allow else []), "--meta", str(t / "meta.json"), "--repo-dir", str(t / "repo"),
            "--t3-signoff-file", str(t / "s.yaml"), "content", "actions", "--workflows", str(t / "wf.json"),
            "--report", str(t / "report.json"), "--jobs", str(t / "jobs.jsonl")]


def _cli(tmp_path, **kw):
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(tmp_path))
    env.pop("SHOWCASE_T3_SIGNOFF_FILE", None)
    r = subprocess.run([*SHOWCASE, *_argv(tmp_path, **kw)], cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode in (0, 1), r.stdout + r.stderr
    return json.loads(r.stdout), json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))


def _toggle(obj):
    t = [p for p in obj["proposals"] if p.get("kind") == "workflow-toggle" and p.get("argv") and p.get("phase")]
    assert len(t) == 1, obj["proposals"]
    return t[0]


def _queued(tmp_path):
    p = tmp_path / "jobs.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() else []


def test_cli_stdout_and_report_proposal_carry_the_signoff_id(tmp_path):
    _setup(tmp_path, ["tool-fork"])
    out, rep = _cli(tmp_path)
    for obj in (out, rep):
        prop = _toggle(obj)
        assert prop["signoff_id"] == "t3s-fork" and "approval_id" not in prop, prop
        assert prop["repo"] == f"{OWNER}/tool-fork" and prop["argv"][:3] == ["gh", "workflow", "disable"]
    assert out["jobs"] == [] and _queued(tmp_path) == [], "an unapproved proposal must not enter the writer queue"


def test_wildcard_grant_stamps_the_proposal_too(tmp_path):
    _setup(tmp_path, ["*"])
    out, rep = _cli(tmp_path)
    assert _toggle(out)["signoff_id"] == "t3s-fork" and _toggle(rep)["signoff_id"] == "t3s-fork"


def test_control_without_allow_t3_stamps_nothing(tmp_path):
    _setup(tmp_path, ["tool-fork"])
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(tmp_path))
    r = subprocess.run([*SHOWCASE, *_argv(tmp_path, allow=False)], cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8")
    assert "signoff_id" not in r.stdout, r.stdout
    rep = tmp_path / "report.json"
    assert not rep.is_file() or "signoff_id" not in rep.read_text(encoding="utf-8")


def test_control_a_record_for_another_repository_stamps_nothing(tmp_path):
    _setup(tmp_path, ["some-other-repo"])
    r = subprocess.run([*SHOWCASE, *_argv(tmp_path)], cwd=ROOT, env=dict(os.environ, SHOWCASE_ESTATE_ROOT=str(tmp_path)),
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "t3-signoff:scope" in r.stdout + r.stderr, r.stdout + r.stderr
    assert "signoff_id" not in r.stdout


def test_in_process_finish_stamps_proposals_but_not_the_queue(tmp_path, monkeypatch):
    """cmd_content/_finish level: a writer-shaped proposal is stamped, a diff-style one (no phase) is untouched, and the
    --jobs file receives only `jobs`."""
    from types import SimpleNamespace
    from ctshowcase import content as C, signoff
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off
    _setup(tmp_path, ["tool-fork"])
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(tmp_path / "s.yaml"))
    t3, run = set_t3_signed_off(True), signoff.reset()
    try:
        signoff.require(OWNER, "tool-fork")  # registers the grant, as the command's owner gate does
        diff_style = {"path": "README.md", "old": "a", "new": "b"}
        writer = C.writer_job("x", 3, "workflow-toggle", f"{OWNER}/tool-fork",
                              ["gh", "workflow", "disable", "cla.yml", "-R", f"{OWNER}/tool-fork"], "n")
        obj = {"jobs": [], "proposals": [writer, diff_style]}
        args = SimpleNamespace(jobs=str(tmp_path / "q.jsonl"), report=str(tmp_path / "r.json"))
        C._finish(args, obj, 0)
        assert writer["signoff_id"] == "t3s-fork" and "signoff_id" not in diff_style
        assert not (tmp_path / "q.jsonl").exists()
        assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["proposals"][0]["signoff_id"] == "t3s-fork"
    finally:
        signoff.restore(run)
        reset_t3_signed_off(t3)
