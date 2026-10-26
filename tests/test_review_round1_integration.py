"""Review round 1 regressions: the Action's held README, the pristine marker, CommonMark fences, label plans from
unknown labels, archived repositories, authored centred blocks, public boards and the watching org's footer check.
Synthetic Northwind fixtures only."""
import importlib.util
import json
import os
import subprocess
import sys

import yaml

from conftest import EX, ROOT, run_cli
from ctshowcase import content as C
from ctshowcase import readme, readmelint

WATCH = "romgenie-following-repos"
PRIV = "private-pricing-engine"


def _cli():
    spec = importlib.util.spec_from_file_location("showcase_cli_r1", ROOT / "scripts" / "showcase.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


# ------------------------------------------------------------------------- Action: a held README keeps the run green
def _generate(tmp_path, mode):
    step = next(s for s in yaml.safe_load((ROOT / "action.yml").read_text())["runs"]["steps"] if s.get("id") == "generate")
    repo, rt = tmp_path / "repo", tmp_path / "rt"
    repo.mkdir(parents=True)
    rt.mkdir()
    (repo / "README.md").write_text("# northwind-tools\n\nDemo tools.\n")
    (rt / "meta.json").write_text(json.dumps({"owner": WATCH, "repo": "northwind-tools", "description": "Northwind demo tools.",
                                              "topics": [], "fork": False, "archived": False, "visibility": "public",
                                              "language": "Python"}))
    out = tmp_path / "gh_out"
    out.write_text("")
    env = dict(os.environ, GITHUB_ACTION_PATH=str(ROOT), RUNNER_TEMP=str(rt), GITHUB_OUTPUT=str(out),
               GITHUB_REPOSITORY=f"{WATCH}/northwind-tools", SHOWCASE_OUTPUTS="banner,card", SHOWCASE_README=mode,
               SHOWCASE_IS_TEMPLATE="false", SHOWCASE_ALLOW_UNMEASURED="false",
               PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""))
    p = subprocess.run(["bash", "-c", step["run"]], cwd=repo, env=env, capture_output=True, text=True)
    return p, out.read_text(), (repo / "README.md").read_text()


def test_action_skips_a_held_readme_instead_of_failing(tmp_path):
    for mode in ("header", "bootstrap"):
        p, outputs, text = _generate(tmp_path / mode, mode)
        assert p.returncode == 0, p.stdout + p.stderr
        assert "skipped=1" in outputs and "README skipped" in p.stdout
        assert text == "# northwind-tools\n\nDemo tools.\n"  # held: the README is untouched


# ------------------------------------------------------------------------- bootstrap `edited`: the example stays
def test_drop_pristine_keeps_a_marker_shown_as_an_example():
    ex = "<!-- showcase:template-body:pristine sha256=" + "0" * 64 + " -->"
    real = "<!-- showcase:template-body:pristine sha256=" + "1" * 64 + " -->"
    text = (f"# Demo\n\nThe template marks its body with `{ex}` until a person edits it.\n\n"
            f"<!-- showcase:template-body:start -->\n{real}\n## About\n\nEdited by a person.\n"
            "<!-- showcase:template-body:end -->\n")
    assert readme.bootstrap_state(text) == "edited"
    out = readme.drop_pristine(text)
    assert ex in out and real not in out
    fenced = f"```markdown\n{real}\n```\n"
    assert readme.drop_pristine(fenced) == fenced  # no real block: nothing changes


# ------------------------------------------------------------------------- CommonMark: ```x``` is inline code
def test_a_line_opening_with_inline_triple_backticks_is_not_a_fence(make_ctx):
    t = "# A\n\n```npm test``` runs the suite.\n\n<!-- showcase:nav:start -->\nX\n<!-- showcase:nav:end -->\n"
    assert len(readme.find_blocks(readme.MARK, t)) == 1
    assert all(b <= t.index("<!-- showcase:nav") for _, b in readme.code_spans(t))
    # upgrade sees the marked footer and keeps one
    once = readme.scaffold(make_ctx())
    text = once.replace("## ", "```npm test``` runs the suite.\n\n## ", 1)
    out, _ = readme.upgrade(make_ctx(), text)
    assert out.count("<!-- showcase:footer:start -->") == 1
    # lint and content scanning see what follows the line
    assert "# Second" in readmelint._outside_code("```npm test``` runs.\n\n# Second\n\n```sh\nx\n```\n")
    rows = C.scan_lines("```npm test``` runs.\n[docs](docs/a.md)\n")
    assert rows[1][1] == "[docs](docs/a.md)"
    # a real fence (info string without backticks) still opens
    fence = "```sh\n<!-- showcase:nav:start -->\n```\n"
    assert readme.code_spans(fence) == [(0, len(fence))]


# ------------------------------------------------------------------------- labels: never planned against []
def test_labels_jobs_without_plan_read_the_live_labels(tmp_path, monkeypatch):
    cli = _cli()
    from ctshowcase import meta as M
    m = tmp_path / "meta.json"
    m.write_text(json.dumps({"owner": "CompleteTech-LLC", "repo": "northwind-demo", "visibility": "public",
                             "description": "Run the Northwind demo.", "labels": [], "has_issues": True,
                             "files": ["README.md"], "files_complete": True}))
    gh = tmp_path / "dot-github.json"
    gh.write_text(json.dumps({"owner": "CompleteTech-LLC", "repo": ".github", "files": ["README.md"], "files_complete": True}))
    jobs = tmp_path / "jobs.jsonl"
    for flags in (["--jobs", str(jobs)], ["--records", str(tmp_path / "rec.jsonl")], ["--gh"]):
        monkeypatch.setattr(M, "_gh", lambda path, paginate=False, raw=False: None)  # the GET fails
        args = cli.parser().parse_args(["--meta", str(m), "--no-repo-dir", "labels", *flags, "--org-defaults", str(gh)])
        args.format = "json"
        try:
            cli.cmd_labels(args)
            raise AssertionError(f"{flags}: planned against []")
        except cli.ShowcaseError as e:
            assert e.code == 4 and e.log == "needs-input:gh"
    assert not jobs.exists()
    live = [{"name": "bug", "color": "d73a4a", "description": ""}]
    monkeypatch.setattr(M, "_gh", lambda path, paginate=False, raw=False: live)
    args = cli.parser().parse_args(["--meta", str(m), "--no-repo-dir", "labels", "--jobs", str(jobs), "--org-defaults", str(gh)])
    args.format = "json"
    out, _ = cli.cmd_labels(args)
    assert any(o["op"] == "rename" and o["name"] == "bug" for o in out["ops"])
    assert not any(o["op"] == "create" and o["name"] == "type:bug" for o in out["ops"])


def test_labels_answer_na_for_an_archived_repository(tmp_path):
    m = tmp_path / "arch.json"
    m.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "order-ledger", "visibility": "public",
                             "description": "Record Northwind orders.", "archived": True,
                             "labels": [{"name": "bug", "color": "d73a4a", "description": ""}]}))
    p = run_cli("--meta", m, "--no-repo-dir", "labels", "--plan", "--jobs", tmp_path / "j.jsonl")
    out = json.loads(p.stdout)
    assert p.returncode == 0 and out["result"] == "n/a" and out["logs"] == ["archived"]
    assert not (tmp_path / "j.jsonl").exists()


# ------------------------------------------------------------------------- an authored centred block survives
def test_upgrade_keeps_an_authored_centred_credits_block(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    block = ('<p align="center">\n  <img src="docs/sponsors.png" alt="Our sponsors" width="400"><br>\n'
             "  Thanks to Acme Corp and Globex for funding the 2026 roadmap.<br>\n"
             "  Built by the Northwind volunteers, hosted on complete.tech infrastructure.\n</p>\n")
    (repo / "README.md").write_text("# Support Triage Agent\n\nTriage agent.\n\n## Usage\n\nRun it.\n\n" + block)
    p = run_cli("--meta", EX / "meta" / "northwind-support-triage-agent.json", "--repo-dir", repo, "--format", "json",
                "readme", "--mode", "upgrade")
    out = json.loads(p.stdout)
    removed = [ln for ln in out.get("diff", "").splitlines() if ln.startswith("-") and not ln.startswith("---")]
    assert p.returncode == 0 and out["result"] == "changed" and "readme-shrink" not in out["logs"]
    assert not removed, removed  # no authored line leaves; the decision 18 footer follows the block


def test_drop_old_footer_takes_only_footer_lines(brand):
    old = ('<p align="center">\n  <a href="https://complete.tech"><img src="assets/logo.png" alt="CompleteTech LLC" '
           'width="160"></a><br>\n  <sub>Built by <a href="https://complete.tech">CompleteTech LLC</a> · Innovation at '
           "Every Integration</sub>\n</p>\n")
    _, removed = readme.drop_old_footer("# A\n\n" + old, brand)
    assert len(removed) == 4
    authored = old.replace("<br>\n", "<br>\n  Thanks to Acme Corp.<br>\n", 1)
    assert readme.drop_old_footer("# A\n\n" + authored, brand) == ("# A\n\n" + authored, [])


# ------------------------------------------------------------------------- a public board lists no repository
def test_a_public_board_without_approval_names_no_repository(brand):
    import test_review_sweep_org_project as T
    c = T.pcap_all_views()
    c["data"]["organization"]["projectV2"]["public"] = True
    plan = T.PJ.copy_plan(T.N, copied=c, resolver=T.presolver(brand), repositories=[f"{T.N}/support-triage-agent",
                                                                                    f"{T.N}/{PRIV}"], reviewed="2026-10-25")
    text_job = next(j for j in plan["jobs"] if j["id"].startswith(f"{T.PRE}-text-"))
    assert PRIV not in json.dumps(text_job) and PRIV not in (plan["readme"] or "")
    assert "readme-links:repositories-omitted (the board may go public)" in plan["logs"]
    assert "visibility:public (no approval)" in plan["logs"] and "visibility:private (no approval)" not in plan["logs"]


# ------------------------------------------------------------------------- footer --check for the watching org
def test_footer_check_reads_the_watching_orgs_readme(tmp_path):
    r = tmp_path / "README.md"
    r.write_text("# .github\n\nProfile of the watching org.\n")
    p = run_cli("footer", "--check", r, "--org", WATCH)
    assert p.returncode == 1 and json.loads(p.stdout)["result"] == "fail:missing"
    p = run_cli("--format", "json", "footer", "--org", WATCH)  # printing the markup: still exempt
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "exempt"
