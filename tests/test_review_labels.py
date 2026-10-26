"""Review regression (comment 4373670978): a legacy label that an issue form or dependabot.yml names must not leave as a
bare rename job. The rewrite is a content change for the estate/polish PR; the rename waits for it. Synthetic data only."""
import json

from conftest import meta_dict, run_cli
from ctshowcase import labels

LIVE = [{"name": "bug", "color": "d73a4a", "description": "Something isn't working"},
        {"name": "enhancement", "color": "a2eeef", "description": "New feature or request"}]
FORM = ("name: Bug report\ndescription: Report something that is broken\nlabels: [bug]\nbody:\n"
        "  - type: textarea\n    attributes:\n      label: What happened?\n")


def _repo(tmp_path, form=FORM, dependabot=None):
    d = tmp_path / "repo"
    (d / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
    (d / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").write_text(form)
    if dependabot:
        (d / ".github" / "dependabot.yml").write_text(dependabot)
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(labels=LIVE)))
    return d, m


def _plan(tmp_path, d, m):
    jobs = tmp_path / "jobs.jsonl"
    p = run_cli("--format", "json", "--meta", m, "--repo-dir", d, "labels", "--plan", "--jobs", jobs)
    out = json.loads(p.stdout)
    lines = [json.loads(x) for x in jobs.read_text().splitlines()] if jobs.is_file() else []
    return p, out, lines


def test_form_label_rename_is_withheld_from_jobs(tmp_path):
    d, m = _repo(tmp_path)
    p, out, jobs = _plan(tmp_path, d, m)
    renames = [j["argv"] for j in jobs if j["argv"][:4] == ["gh", "label", "edit", "bug"]]
    assert not renames, f"bare rename job emitted while the form still says labels: [bug]: {renames}"
    assert not any(a[:4] == ["gh", "label", "edit", "bug"] for a in out["argv"])
    # the unreferenced alias still leaves as a job
    assert any(a[:4] == ["gh", "label", "edit", "enhancement"] for a in out["argv"])
    # the plan names exactly which file and line the PR must rewrite first, and does not pass
    held = out["rewrite_first"]
    assert held == [{"label": "bug", "new_name": "type:bug", "path": ".github/ISSUE_TEMPLATE/bug_report.yml", "line": 3,
                     "text": "labels: [bug]"}]
    assert out["result"] == "fail" and p.returncode == 1 and "label-rewrite-first" in out["logs"]
    # no create for the standard name either: it arrives by the rename once the PR has merged
    assert not any(a[:4] == ["gh", "label", "create", "type:bug"] for a in out["argv"])


def test_rename_returns_once_the_form_is_rewritten(tmp_path):
    d, m = _repo(tmp_path, form=FORM.replace("labels: [bug]", "labels: [type:bug]"))
    _, out, jobs = _plan(tmp_path, d, m)
    assert any(j["argv"][:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for j in jobs)
    assert "rewrite_first" not in out


def test_dependabot_and_epic_references_are_withheld(tmp_path):
    ops, logs = labels.plan(LIVE + [{"name": "epic", "color": "000000", "description": ""}],
                            _repo(tmp_path, form="labels: [epic]\n",
                                  dependabot="version: 2\nupdates:\n  - package-ecosystem: pip\n    labels: [enhancement]\n")[0])
    held = {o["name"]: o for o in ops if o.get("rewrite_references")}
    assert set(held) == {"enhancement", "epic"} and all(o["op"] == "skip" for o in held.values())
    assert held["enhancement"]["rewrite_references"] == [{"path": ".github/dependabot.yml", "line": 4,
                                                          "text": "labels: [enhancement]"}]
    assert "label-rewrite-first" in logs
    assert not [o for o in ops if o["op"] != "skip" and o["name"] in held]


def test_adopt_holds_the_same_rename(tmp_path):
    d, m = _repo(tmp_path)
    p = run_cli("--meta", m, "--repo-dir", d, "adopt", "Northwind-Trading-Co/support-triage-agent")
    out = json.loads(p.stdout)
    argvs = [j.get("argv") or [] for j in out["jobs"]]
    assert not any(a[:4] == ["gh", "label", "edit", "bug"] for a in argvs), argvs
    assert any(a[:4] == ["gh", "label", "edit", "enhancement"] for a in argvs)
    assert "label-rewrite-first" in out["logs"]


# Reviewer follow-up: only a structured `labels:` entry is a reference. Prose that happens to contain a label word (GitHub's
# default "Describe the bug" form text, a PR template's "bug fix" / "documentation update") must never hold a rename,
# or a re-plan of the merged checkout could never emit it.
PROSE_LIVE = LIVE + [{"name": "documentation", "color": "0075ca", "description": "Improvements or additions to documentation"}]
PROSE_FORM = ("name: Bug report\ndescription: File a bug report\nlabels: [type:bug]\nbody:\n  - type: textarea\n"
              "    attributes:\n      label: Describe the bug\n      description: A clear description of the bug.\n")
PR_TEMPLATE = ("## Type of change\n- [ ] bug fix (non-breaking change which fixes an issue)\n- [ ] new feature\n"
               "- [ ] This change requires a documentation update\n")


def _prose_repo(tmp_path, form=PROSE_FORM, extra=None):
    d = tmp_path / "repo"
    (d / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
    (d / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").write_text(form)
    (d / ".github" / "pull_request_template.md").write_text(PR_TEMPLATE)
    (d / ".github" / "CONTRIBUTING.md").write_text("Open a bug report; documentation fixes are welcome.\n")
    for rel, text in (extra or {}).items():
        (d / rel).write_text(text)
    return d


def test_prose_mentions_do_not_hold_renames(tmp_path):
    ops, logs = labels.plan(PROSE_LIVE, _prose_repo(tmp_path))
    renames = {o["name"]: o["new_name"] for o in ops if o["op"] == "rename"}
    assert renames.get("bug") == "type:bug" and renames.get("documentation") == "type:docs"
    assert "label-rewrite-first" not in logs and not any(o.get("rewrite_references") for o in ops)


def test_prose_mentions_do_not_fail_the_cli_plan(tmp_path):
    d = _prose_repo(tmp_path)
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(labels=PROSE_LIVE)))
    p, out, jobs = _plan(tmp_path, d, m)
    # the plan still reports pending writes (result fail, as any plan with jobs does), but nothing is held
    assert "rewrite_first" not in out and "label-rewrite-first" not in out["logs"]
    argvs = [j["argv"] for j in jobs]
    assert any(a[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for a in argvs)
    assert any(a[:6] == ["gh", "label", "edit", "documentation", "--name", "type:docs"] for a in argvs)


def test_block_list_and_markdown_front_matter_labels_still_hold(tmp_path):
    form = PROSE_FORM.replace("labels: [type:bug]\n", "labels:\n  - Bug  # triage\n  - needs-triage\n")
    md = "---\nname: Docs request\nabout: Ask for a documentation fix\nlabels: documentation, help wanted\n---\nThe documentation is wrong.\n"
    ops, logs = labels.plan(PROSE_LIVE, _prose_repo(tmp_path, form=form, extra={".github/ISSUE_TEMPLATE/docs.md": md}))
    held = {o["name"]: o["rewrite_references"] for o in ops if o.get("rewrite_references")}
    assert held == {"bug": [{"path": ".github/ISSUE_TEMPLATE/bug_report.yml", "line": 4, "text": "- Bug  # triage"}],
                    "documentation": [{"path": ".github/ISSUE_TEMPLATE/docs.md", "line": 4,
                                       "text": "labels: documentation, help wanted"}]}
    assert "label-rewrite-first" in logs
