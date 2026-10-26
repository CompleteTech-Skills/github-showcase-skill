"""The command-group contract wired into showcase.py: org, project, enterprise and content (synthetic data only)."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
from conftest import EX, ROOT

import showcase

CONTRACT = {"org": {"profile", "about", "pins", "labels", "health", "doctor"},
            "project": {"capture-query", "normalize", "copy-plan", "readme", "lint", "estate-plan"},
            "enterprise": {"snapshot-query", "doctor", "plan"},
            "content": {"social", "icon", "links", "linguist", "actions", "images", "sidebar"}}
EXISTING = {"banner", "card", "social-preview", "org-banner", "org-tile", "intro", "footer", "readme", "describe", "topics",
            "labels", "meta", "fingerprint", "fonts", "lint", "contact-sheet", "doctor", "enterprise", "config"}
JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,199}$")  # scripts/writer.py ID_RE
ESTATE = EX / "estate"
META = EX / "meta" / "northwind-support-triage-agent.json"
REPO = EX / "repos" / "northwind-support-triage-agent"
FIXC = ROOT / "tests" / "fixtures" / "content"
SNAP = ROOT / "tests" / "fixtures" / "enterprise" / "snapshot-before.json"


def cli(*args, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True, env=e)


def subparsers(p):
    return next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))


def assert_job(j):
    assert JOB_ID.match(j["id"]), j["id"]
    assert str(j["phase"]).strip() and j["kind"] and j.get("note") is not None
    assert bool(j.get("repo")) != bool(j.get("org")), j
    if j["kind"] == "browser":
        assert j["steps"] and j["url"].startswith("https://github.com/") and j.get("ui_action")
    else:
        assert isinstance(j["argv"], list) and j["argv"] and j["argv"][0] in ("gh", "git")
        q = next((a for a in j["argv"] if a.startswith("query=")), "")
        assert not q.startswith("query=@") or "mutation" not in q  # mutations are inline, never loaded from a file


# ----------------------------------------------------------------------------------------------- parser
def test_every_contract_name_and_existing_command_parses():
    sub = subparsers(showcase.parser())
    assert EXISTING | set(CONTRACT) <= set(sub.choices)
    for group in ("org", "project"):
        action = next(a for a in sub.choices[group]._actions if a.dest == "action")
        assert CONTRACT[group] <= set(action.choices)
    ent = next(a for a in sub.choices["enterprise"]._actions if a.dest == "action")
    assert CONTRACT["enterprise"] | {"discover", "snapshot", "seat-check", "diff"} <= set(ent.choices)
    assert set(subparsers(sub.choices["content"]).choices) == CONTRACT["content"]


@pytest.mark.parametrize("argv", [["org", "about", "X"], ["project", "lint"], ["enterprise", "snapshot-query"],
                                  ["content", "links"], ["content", "icon", "check"], ["banner"], ["labels", "--plan"]])
def test_contract_argv_parses(argv):
    args = showcase.parser().parse_args(argv)
    assert callable(args.func)


# ----------------------------------------------------------------------------------------------- content
def test_content_social_is_social_preview(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    p = cli("--meta", META, "--repo-dir", REPO, "content", "social", "--out", a, "--job")
    assert p.returncode == 0, p.stderr
    res = json.loads(p.stdout)
    assert res["command"] == "content" and res["action"] == "social" and res["alias_of"] == "social-preview"
    assert cli("--meta", META, "--repo-dir", REPO, "social-preview", "--out", b).returncode == 0
    assert a.read_bytes() == b.read_bytes()


def test_content_links_runs_without_the_bundle(tmp_path):
    p = cli("--meta", META, "--repo-dir", REPO, "content", "links", "--report", tmp_path / "r.json",
            env={"SHOWCASE_ESTATE_ROOT": str(tmp_path / "none")})
    assert p.returncode == 0, p.stderr
    assert json.loads((tmp_path / "r.json").read_text())["result"] == "pass"


# ----------------------------------------------------------------------------------------------- enterprise
def test_enterprise_snapshot_query_prints_reads_only():
    p = cli("enterprise", "snapshot-query", "--slug", "completetech")
    res = json.loads(p.stdout)
    assert p.returncode == 0 and res["action"] == "snapshot-query" and res["slug"] == "completetech"
    for r in res["reads"]:
        f = next(a for a in r["argv"] if a.startswith("query=@"))[len("query=@"):]
        assert "mutation" not in re.sub(r"(?m)#.*$", "", open(f, encoding="utf-8").read()).lower()
    assert cli("enterprise", "snapshot-query", "--slug", "Bad Slug").returncode == 2
    assert cli("enterprise", "snapshot_query", "--slug", "completetech").returncode == 0  # alias


def test_enterprise_plan_writes_writer_jobs(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    p = cli("enterprise", "plan", "--snapshot", SNAP, "--jobs", jobs)
    assert p.returncode == 0, p.stderr
    res = json.loads(p.stdout)
    lines = [json.loads(x) for x in jobs.read_text().splitlines()]
    assert lines == res["jobs"] and len(lines) == len(res["records"]) == 3
    for j, r in zip(lines, res["records"]):
        assert_job(j)
        # the writer checks approval_id against APPROVED_ACTIONS.yaml row ids (ent-001 profile, ent-002 domains)
        assert j["kind"] == "enterprise" and j["phase"] == "1" and j["approval_id"] == r["approval_id"]
        assert j["approval_id"] == ("ent-001" if r["kind"] == "enterprise-profile" else "ent-002")
        assert any(a.startswith("query=mutation") for a in j["argv"])
        assert not any("mutation" in a for a in j["read"])


# ----------------------------------------------------------------------------------------------- org
def test_org_actions_on_the_example_estate(tmp_path):
    env = {"SHOWCASE_ESTATE_ROOT": str(ESTATE)}
    jobs = tmp_path / "jobs.jsonl"
    for action in ("about", "pins", "labels"):
        p = cli("org", action, "Northwind-Trading-Co", "--meta-dir", ESTATE / "meta", "--jobs", jobs, env=env)
        assert p.returncode == 0, (action, p.stdout, p.stderr)
    for line in jobs.read_text().splitlines():
        assert_job(json.loads(line))
    out = tmp_path / "dotgithub"
    # the example's .github already has a profile: without the profile-retemplate approval nothing is written (§8.2)
    p = cli("org", "profile", "Northwind-Trading-Co", "--meta-dir", ESTATE / "meta", "--out-dir", out,
            "--approved", tmp_path / "none.tsv", env=env)
    assert p.returncode == 4 and json.loads(p.stdout)["result"] == "needs-approval" and not out.exists()
    p = cli("org", "profile", "Northwind-Trading-Co", "--meta-dir", ESTATE / "meta", "--out-dir", out, env=env)
    assert p.returncode == 0, p.stderr
    text = (out / "profile" / "README.md").read_text()
    assert "support-triage-agent" in text and "private-pricing-engine" not in text
    assert "never reaches the public profile" not in text  # registry `why` notes stay private
    assert text.rstrip().endswith("<!-- showcase:footer:end -->")
    p = cli("org", "doctor", "Northwind-Trading-Co", "--meta-dir", ESTATE / "meta", "--doctor-format", "tsv", "--header",
            env=env)
    assert p.returncode == 0 and p.stdout.splitlines()[0].startswith("org\ttier\tO1")


def test_org_without_a_registry_is_needs_input(tmp_path):
    p = cli("org", "about", "Northwind-Trading-Co", "--registry", tmp_path / "missing.yaml")
    assert p.returncode == 4 and json.loads(p.stdout)["logs"] == ["needs-input:registry"]


# ----------------------------------------------------------------------------------------------- org renames (CQ-03)
@pytest.fixture
def renamed_estate(tmp_path):
    """An estate root whose approvals rename CompleteTech-Pokemon to CompleteTech-TCG (org-005)."""
    dec = tmp_path / "decisions"
    dec.mkdir()
    shutil.copy(FIXC / "approved.tcg.yaml", dec / "APPROVED_ACTIONS.yaml")
    shutil.copy(FIXC / "estate-actions.json", dec / "estate-actions.json")
    return tmp_path


def test_project_capture_query_follows_an_approved_rename(renamed_estate):
    p = cli("project", "capture-query", "--owner", "CompleteTech-Pokemon", "--number", "1",
            env={"SHOWCASE_ESTATE_ROOT": str(renamed_estate)})
    res = json.loads(p.stdout)
    assert p.returncode == 0 and res["owner"] == "CompleteTech-TCG"
    assert "org-alias:CompleteTech-Pokemon->CompleteTech-TCG" in res["logs"]
    assert any("orgs/CompleteTech-TCG/projectsV2/1" in " ".join(r["argv"]) for r in res["reads"])


def test_repository_commands_keep_the_brand_row_after_a_rename(renamed_estate, tmp_path, monkeypatch):
    from ctshowcase.config import load_brand
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(renamed_estate))
    b = load_brand()
    old, new = b.org("CompleteTech-Pokemon"), b.org("CompleteTech-TCG")
    assert new["known"] and new["family"] == old["family"] and new.get("display_name") == old.get("display_name")
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"owner": "CompleteTech-TCG", "repo": "deck-tool", "description": "Build decks.",
                                "visibility": "public", "topics": []}))
    p = cli("--meta", meta, "--no-repo-dir", "meta", "--out", tmp_path / "o.json",
            env={"SHOWCASE_ESTATE_ROOT": str(renamed_estate)})
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["detected"]["family"] == old["family"]


def test_owner_status_survives_a_rename(brand):
    import copy

    from ctshowcase.config import Brand
    raw = copy.deepcopy(brand.raw)
    watching = raw["owners"]["watching"][0]
    raw["orgs"][watching + "-renamed"] = dict(raw["orgs"].get(watching) or {"family": "romgenie"}, former_slugs=[watching])
    raw["orgs"].pop(watching, None)
    b = Brand(raw, brand.path)
    assert b.owner_status(watching + "-renamed") == "watching" and b.owner_status(watching) == "watching"
    assert b.org(watching)["owner"] == watching + "-renamed"
