"""`showcase.py content ...` (links CQ-04, linguist RP-07, actions RP-06/RP-01, images RP-03/RP-10, sidebar RP-05,
icon RT-04, social R10) and the org resolver (CQ-03). Synthetic Northwind data and public org names only."""
import io
import json
import os
import random
import re
import subprocess
from pathlib import Path

import pytest
from conftest import ROOT, meta_dict

from ctshowcase import content as C
from ctshowcase import resolver as R
from ctshowcase.errors import ArtFail, NeedsInput, Refused

FIX = ROOT / "tests" / "fixtures" / "content"
ACTIONS = json.loads((FIX / "estate-actions.json").read_text(encoding="utf-8"))
ART = (FIX / "ART_DIRECTION.min.md").read_text(encoding="utf-8")
NW = "Northwind-Trading-Co"


def write(root: Path, files: dict):
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            p.write_bytes(body)
        else:
            p.write_text(body, encoding="utf-8")
    return root


def git(root: Path, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com", GIT_CONFIG_GLOBAL="/dev/null")
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env).stdout


def run_content(capsys, *argv):
    code = C.main(list(map(str, argv)))
    out = capsys.readouterr().out.strip()
    return code, (json.loads(out) if out.startswith("{") else out)


NO_ESTATE = ("--registry", FIX / "registry.min.yaml", "--approved", FIX / "approved.empty.txt", "--approved-yaml",
             FIX / "approved.empty.yaml", "--actions", FIX / "estate-actions.json")


# ---------------------------------------------------------------------------------------------------
# Org lookups through the shared resolver (CQ-03)
# ---------------------------------------------------------------------------------------------------
def resolver(brand, *ids, registry=None):
    return R.Resolver(brand, registry or {}, {"rows": set(), "ids": set(ids), "answers": {}, "actions": ACTIONS,
                                             "extra": []})


def test_lookups_follow_approved_renames(brand):
    r = resolver(brand, "org-001", "org-003", "org-005")
    assert C.current_login(r, "CompleTetech-Security") == "CompleteTech-Security"
    assert C.brand_key(r, "CompleteTech-Security") == "CompleteTech-Security"  # org-001 is done: the row is keyed by the new login
    assert C.org_row(r, brand, "CompleteTech-Security", require=True)["eyebrow"] == "SECURITY"
    assert C.org_style(r, brand, "CompleteTech-TCG")["name"] == brand.style("CompleteTech-Pokemon")["name"]
    assert r.owner_status("CompleteTech-Following") == "watching"  # the exemption survives the rename
    assert C.in_estate(r, "CompleteTech-TCG") and not C.in_estate(r, "BunsDev")
    assert C.current_login(resolver(brand), "CompleteTech-Pokemon") == "CompleteTech-Pokemon"  # not approved: unchanged
    assert C.current_login(None, "X") == "X" and C.brand_key(None, "X") == "X"
    with pytest.raises(NeedsInput):
        C.org_row(r, brand, "Someone-Unknown-Org", require=True)
    with pytest.raises(Refused):
        r.check_owner("Pick-Your-AI")


def test_load_resolver_from_files(brand):
    r = C.load_resolver(brand, FIX / "registry.min.yaml", FIX / "approved.empty.txt", FIX / "approved.tcg.yaml",
                        FIX / "estate-actions.json")
    assert C.current_login(r, "CompleteTech-Pokemon") == "CompleteTech-TCG"
    assert C.current_login(r, "CompleTetech-Security") == "CompleteTech-Security"  # former_slugs: the old login resolves without an approval
    assert C.in_estate(r, NW)


def test_job_ids_and_shapes():
    assert C.job_id("p3", "sidebar", "Northwind-Trading-Co/triage_agent_demo") == "p3:sidebar:Northwind-Trading-Co/triage_agent_demo"
    assert C.job_id("p5", "icon", "Org/repo name (copy)") == "p5:icon:Org/repo-name-copy"
    j = C.writer_job("x", 3, "workflow-toggle", f"{NW}/r", ["gh", "workflow", "disable", 7], "n", "q79-1")
    assert j == {"id": "x", "phase": "3", "kind": "workflow-toggle", "repo": f"{NW}/r", "approval_id": "q79-1",
                 "argv": ["gh", "workflow", "disable", "7"], "note": "n"}
    b = C.browser_job("p3:x", 3, NW, "https://github.com/" + NW, "about", ["step"], "n")
    assert b["kind"] == "browser" and b["org"] == NW and b["argv"] == [] and b["steps"][0] == "step"
    assert b["steps"][-1] == C.SAFETY_STEP and "state/screens/p3_x.png" in b["steps"][-2]


# ---------------------------------------------------------------------------------------------------
# Markdown slugs and link extraction
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("heading,slug", [
    ("Quick Start", "quick-start"), ("🚀 Install", "-install"), ("C++ & Rust", "c--rust"),
    ("`showcase.py` CLI", "showcasepy-cli"), ("**Bold** and _it_", "bold-and-it"), ("[Docs](docs/x.md) here", "docs-here"),
    ("Version 1.2 (beta)", "version-12-beta"), ("snake_case-name", "snake_case-name"), ("Café Ünïcode", "café-ünïcode")])
def test_github_slug(heading, slug):
    assert C.github_slug(C.plain_heading(heading)) == slug


def test_headings_duplicates_setext_and_code():
    text = "# A\n\n## Usage\n\n```md\n## Not a heading\n```\n\nUsage\n-----\n\n## Usage\n<a name=\"legacy\"></a>\n"
    slugs = [h["slug"] for h in C.headings(text)]
    assert slugs == ["a", "usage", "usage-1", "usage-2"]
    assert "legacy" in C.anchors(text)


def test_extract_links_kinds():
    text = ("[![CI](https://x.test/b.svg)](https://x.test/ci) see <https://a.test/p>. "
            "<img src=\"docs/i.png\" alt=\"\">\n[ref]: ./docs/r.md\n`[no](skip.md)` <!-- [no](hidden.md) -->\n"
            "```\n[no](code.md)\n```\n")
    found = [(x["target"], x["image"], x["syntax"]) for x in C.extract_links(text)]
    assert ("https://x.test/ci", False, "markdown") in found and ("https://x.test/b.svg", True, "markdown") in found
    assert ("https://a.test/p", False, "bare") in found and ("docs/i.png", True, "html-img") in found
    assert ("./docs/r.md", False, "reference") in found
    assert not [t for t, _, _ in found if t in ("skip.md", "hidden.md", "code.md")]


# ---------------------------------------------------------------------------------------------------
# links (CQ-04)
# ---------------------------------------------------------------------------------------------------
README = """# Support Triage Agent

[Install](#install) · [Usage](#usage) · [Gone](#quickstart) · [Guide](docs/Guide.md#setup) · [Bad case](docs/guide.md)
[Missing](docs/nowhere.md) · [Moved](old/config.md) · [Issues](../../issues) · [Local](C:\\Users\\me\\x.md)
[Dev](http://localhost:8080) · [Site](https://www.example.com/x) · [Upstream](https://github.com/CompleteTech-Pokemon/northwind-card-demo)
![Diagram](docs/img/flow.png) <img src="docs/img/missing.png" alt="Missing image">

```bash
cat [not-a-link](nope.md)
```

## Install

## Usage
"""


@pytest.fixture
def checkout(tmp_path):
    root = write(tmp_path / "repo", {"README.md": README, "docs/Guide.md": "# Guide\n\n## Setup\n\n[Back](../README.md#usage)\n",
                                     "docs/img/flow.png": b"\x89PNG", "conf/config.md": "# Config\n"})
    return root


def test_links_offline(brand, checkout):
    r = resolver(brand, "org-005")
    tree = C.Tree(checkout)
    files = C.markdown_files(tree, C.displayed_readme(tree))
    assert files == ["README.md", "docs/Guide.md"]
    res = C.links_report(tree, files, resolver=r)
    by = {(x["file"], x["target"]): x for x in res["findings"]}
    assert by[("README.md", "#install")]["status"] == "ok"
    assert by[("README.md", "docs/Guide.md#setup")]["status"] == "ok"
    assert by[("docs/Guide.md", "../README.md#usage")]["status"] == "ok"
    assert by[("README.md", "#quickstart")]["status"] == "broken"
    case = by[("README.md", "docs/guide.md")]
    assert case["status"] == "broken" and case["proposal"]["new"] == "docs/Guide.md"
    assert by[("README.md", "old/config.md")]["proposal"]["new"] == "conf/config.md"
    assert by[("README.md", "docs/nowhere.md")]["proposal"] is None
    assert by[("README.md", "../../issues")]["status"] == "skipped"
    assert by[("README.md", "C:\\Users\\me\\x.md")]["reason"] == "machine-local path"
    assert by[("README.md", "http://localhost:8080")]["status"] == "allowlisted"
    assert by[("README.md", "https://www.example.com/x")]["status"] == "allowlisted"
    up = by[("README.md", "https://github.com/CompleteTech-Pokemon/northwind-card-demo")]
    assert up["status"] == "renamed" and up["proposal"]["new"].startswith("https://github.com/CompleteTech-TCG/")
    assert by[("README.md", "docs/img/missing.png")]["status"] == "broken"
    assert not any("nope.md" in t for _, t in by)
    assert res["result"] == "warn" and "dead-link" in res["logs"] and "link-rewrite" in res["logs"]
    before = (checkout / "README.md").read_text(encoding="utf-8")
    diff = C.proposal_diff(tree, res["proposals"])
    assert "[Bad case](docs/Guide.md)" in diff and "[Moved](conf/config.md)" in diff and "CompleteTech-TCG" in diff
    assert "#quickstart" in diff  # no near slug: left as it is, reported only
    assert (checkout / "README.md").read_text(encoding="utf-8") == before  # never rewritten


def test_links_flag_this_repository_under_a_former_owner(brand, tmp_path):
    """Round-2 defect: php2shell-check's badges still named CompleteTech-LLC after its transfer; offline they read as
    unchecked. A prefix target on the same line must not rewrite the longer one only half-way."""
    old = "https://github.com/CompleteTech-LLC/support-triage-agent/actions/workflows/ci.yml"
    root = write(tmp_path / "r", {"README.md": (
        f"[![CI]({old}/badge.svg)]({old})\n"
        "![Release](https://img.shields.io/github/v/release/CompleteTech-LLC/support-triage-agent?color=1E3A8A)\n"
        "[Other](https://github.com/CompleteTech-LLC/support-triage-agent-docs) "
        "[Sibling](https://github.com/CompleteTech-LLC/stt-app)\n")})
    tree = C.Tree(root)
    move = {"id": "repo-nw-001", "owner": "CompleteTech-LLC", "repo": "support-triage-agent", "action": "transfer",
            "target_owner": NW, "new_name": ""}  # the recorded, approved transfer (a same name alone is not a move)
    moved_by = R.Resolver(brand, {}, {"rows": set(), "ids": {"repo-nw-001"}, "answers": {}, "actions": ACTIONS + [move],
                                      "extra": []})
    res = C.links_report(tree, ["README.md"], resolver=moved_by, self_slug=(NW, "support-triage-agent"))
    moved = [x for x in res["findings"] if x["status"] == "moved"]
    assert len(moved) == 3 and all(x["proposal"]["new"].count(f"{NW}/support-triage-agent") == 1 for x in moved)
    assert res["result"] == "pass" and "link-rewrite" in res["logs"]
    diff = C.proposal_diff(tree, res["proposals"])
    assert f"+[![CI](https://github.com/{NW}/support-triage-agent/actions/workflows/ci.yml/badge.svg)]" \
           f"(https://github.com/{NW}/support-triage-agent/actions/workflows/ci.yml)" in diff
    assert "release/Northwind-Trading-Co/support-triage-agent?color" in diff
    assert "CompleteTech-LLC/support-triage-agent-docs" in diff and "CompleteTech-LLC/stt-app" in diff  # untouched
    assert C.links_report(tree, ["README.md"], resolver=moved_by)["counts"].get("moved") is None  # needs the slug


def test_links_strict_fails(checkout):
    tree = C.Tree(checkout)
    assert C.links_report(tree, ["README.md"], strict=True)["result"] == "fail"


def test_displayed_readme_precedence(tmp_path):
    root = write(tmp_path, {"README.md": "# Root\n", ".github/README.md": "# Shown\n[Up](../docs/a.md)\n",
                            "docs/a.md": "# A\n"})
    tree = C.Tree(root)
    assert C.displayed_readme(tree) == ".github/README.md"
    res = C.links_report(tree, [".github/README.md"])
    assert res["findings"][0]["status"] == "ok"  # resolved from .github/, not the root


def test_untracked_ignored_target_is_broken_in_git(tmp_path):
    root = write(tmp_path, {"README.md": "[Out](build/out.md) [In](docs/in.md)\n", ".gitignore": "build/\n",
                            "build/out.md": "x", "docs/in.md": "y"})
    git(root, "init", "-q")
    tree = C.Tree(root)
    assert tree.git and "build/out.md" not in tree.files and "docs/in.md" in tree.files
    res = C.links_report(tree, ["README.md"])
    by = {x["target"]: x for x in res["findings"]}
    assert by["build/out.md"]["status"] == "broken" and "not in the git tree" in by["build/out.md"]["reason"]
    assert by["docs/in.md"]["status"] == "ok"


def test_base_ref_separates_introduced_from_preexisting(tmp_path):
    root = write(tmp_path, {"README.md": "# T\n\n[Start](#quickstart) [Old rot](docs/gone.md)\n\n## Quickstart\n"})
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    (root / "README.md").write_text("# T\n\n[Start](#quickstart) [Old rot](docs/gone.md)\n\n## Quick Start\n", encoding="utf-8")
    res = C.links_report(C.Tree(root), ["README.md"], base=C.Tree(root, "HEAD"))
    by = {x["target"]: x for x in res["findings"]}
    assert by["#quickstart"]["introduced"] and by["#quickstart"]["proposal"]["new"] == "#quick-start"
    assert by["#quickstart"]["proposal_anchor"]["new"] == '<a name="quickstart"></a>'
    assert by["docs/gone.md"]["introduced"] is False
    assert res["result"] == "fail" and res["introduced"] == 1 and res["broken"] == 2
    diff = C.proposal_diff(C.Tree(root), res["proposals"])
    assert '+<a name="quickstart"></a>' in diff and "+[Start](#quick-start)" in diff


def test_online_checks_are_cached_and_paced(brand, tmp_path):
    root = write(tmp_path / "r", {"README.md": "[a](https://a.test/ok) [b](https://a.test/gone) [c](https://b.test/head)"
                                               " [d](https://github.com/Northwind-Trading-Co/old-name)\n"})
    calls, sleeps = [], []

    def opener(url, method):
        calls.append((url, method))
        if url.endswith("/gone"):
            return 404, url, None
        if url.endswith("/head") and method == "HEAD":
            return 405, url, None
        return 200, url, None

    def gh(o, r):
        calls.append((f"gh:{o}/{r}", "GET"))
        return f"{o}/support-triage-agent", None
    cache = tmp_path / "cache.json"
    clock = iter(range(1000)).__next__
    f = C.Fetcher(cache, opener=opener, gh=gh, sleep=sleeps.append, clock=lambda: float(clock()), delay=5)
    res = C.links_report(C.Tree(root), ["README.md"], resolver=resolver(brand), fetcher=f, online=True)
    by = {x["target"]: x for x in res["findings"]}
    assert by["https://a.test/ok"]["status"] == "ok" and by["https://a.test/gone"]["status"] == "broken"
    assert by["https://b.test/head"]["status"] == "ok" and ("https://b.test/head", "GET") in calls
    moved = by["https://github.com/Northwind-Trading-Co/old-name"]
    assert moved["status"] == "moved" and moved["proposal"]["new"].endswith("/support-triage-agent")
    assert sleeps and all(s > 0 for s in sleeps)  # a second request to a.test waited
    f.save()
    n = len(calls)
    f2 = C.Fetcher(cache, opener=opener, gh=gh, clock=lambda: 50.0)
    C.links_report(C.Tree(root), ["README.md"], resolver=resolver(brand), fetcher=f2, online=True)
    assert len(calls) == n  # every answer came from the cache


def test_links_cli_follows_an_approved_rename(capsys, checkout):
    flags = [x if x != FIX / "approved.empty.yaml" else FIX / "approved.tcg.yaml" for x in NO_ESTATE]
    code, out = run_content(capsys, "--repo-dir", checkout, "content", "links", *flags)
    up = next(x for x in out["findings"] if "northwind-card-demo" in x["target"])
    assert up["status"] == "renamed" and "CompleteTech-TCG" in up["proposal"]["new"]
    code, out = run_content(capsys, "--repo-dir", checkout, "content", "links", *NO_ESTATE)
    up = next(x for x in out["findings"] if "northwind-card-demo" in x["target"])
    assert up["status"] == "unchecked"  # nothing approved: the live login stays


def test_links_cli(capsys, checkout):
    code, out = run_content(capsys, "--repo-dir", checkout, "content", "links", "--diff", *NO_ESTATE)
    assert code == 0 and out["action"] == "links" and out["result"] == "warn" and out["diff"]
    code, out = run_content(capsys, "--repo-dir", checkout, "content", "links", "--strict", *NO_ESTATE)
    assert code == 1
    code, out = run_content(capsys, "--repo-dir", checkout, "content", "links", "nope.md", *NO_ESTATE)
    assert code == 2 and out["result"] == "usage"


# ---------------------------------------------------------------------------------------------------
# linguist (RP-07)
# ---------------------------------------------------------------------------------------------------
def test_linguist_proposes_generated_and_example_paths(tmp_path):
    root = write(tmp_path, {"pyproject.toml": "[project]\nname='x'\n", "src/app.py": "x" * 3000,
                            "results/run-1/report.html": "<html>" + "r" * 20000, "assets/examples/demo.js": "j" * 4000,
                            "docs/site.html": "d" * 50000, "node_modules/x/index.js": "n" * 90000,
                            "assets/diagrams/flow.mmd": "graph TD" + "m" * 500,
                            ".gitattributes": "* text=auto\n"})
    meta = meta_dict(language="HTML", languages={"HTML": 20006, "Python": 3000, "JavaScript": 4000, "Mermaid": 508})
    res = C.linguist_report(meta, C.Tree(root), min_share=0.01)
    pats = {r["pattern"]: r["attribute"] for r in res["proposed"]}
    assert pats["results/**"] == "linguist-generated"
    assert pats["assets/examples/**"] == "linguist-documentation"
    assert pats["assets/diagrams/**"] == "linguist-documentation"
    assert not any(p.startswith(("docs/", "node_modules/")) for p in pats)  # Linguist already excludes them
    assert res["primary"] == {"language": "Python", "source": "manifest"}
    assert res["primary_before"]["language"] is None  # HTML is not a chip language
    assert res["bar_after"][0]["language"] == "Python"
    assert res["diff"].startswith("--- a/.gitattributes") and "+# ct-std linguist" in res["diff"]
    assert " * text=auto" in res["diff"]  # existing lines kept (append-only)
    assert not re.search(r"\b(eol|binary|filter=lfs)\b", "\n".join(res["gitattributes_lines"]))
    assert (root / ".gitattributes").read_text(encoding="utf-8") == "* text=auto\n"


def test_linguist_existing_block_and_overrides(tmp_path):
    ga = "# ct-std linguist\nresults/** linguist-generated\n\n*.png binary\n"
    root = write(tmp_path, {"results/a.html": "h" * 9000, "reports/b.html": "h" * 9000, "tool.go": "g" * 100,
                            ".gitattributes": ga})
    res = C.linguist_report(meta_dict(languages={"HTML": 9000, "Go": 100}), C.Tree(root))
    assert res["gitattributes_lines"] == ["reports/** linguist-generated"]
    assert "+reports/** linguist-generated" in res["diff"] and "*.png binary" in res["diff"]
    assert res["primary"]["language"] == "Go"


def test_primary_language_rules():
    assert C.primary_language({"languages": {"Mermaid": 900, "Python": 10}}) == (None, "language-omitted")
    assert C.primary_language({"languages": {"TSX": 900}}) == ("TypeScript", "linguist")
    assert C.primary_language({"languages": {"HTML": 9}}, override={"language": "PHP"}) == ("PHP", "override")
    files = {"package.json", "tsconfig.json", "src/a.ts"}
    assert C.primary_language({}, files, lambda p: '{"main": "a.js"}') == ("TypeScript", "manifest")
    tooling = {"package.json", "main.py", "requirements.txt"}
    assert C.primary_language({"languages": {"Python": 5}}, tooling, lambda p: '{"devDependencies": {}}' if p ==
                              "package.json" else "") == ("Python", "manifest")


def test_linguist_from_metadata_and_missing_tree():
    meta = meta_dict(languages={"HTML": 9000, "Python": 1000},
                     files=["main.py", "reports/out.html", "requirements.txt"],
                     file_sizes={"main.py": 1000, "reports/out.html": 9000, "requirements.txt": 10})
    res = C.linguist_report(meta)
    assert res["proposed"][0]["pattern"] == "reports/**" and res["primary"]["language"] == "Python"
    with pytest.raises(NeedsInput):
        C.linguist_report(meta_dict())


# ---------------------------------------------------------------------------------------------------
# actions (RP-06, RP-01, CQ-13)
# ---------------------------------------------------------------------------------------------------
WF = {
    ".github/workflows/tests.yml": "name: Tests\non:\n  push:\n    branches: [main]\n  pull_request:\njobs:\n  t:\n"
                                   "    runs-on: ubuntu-latest\n    steps:\n      - run: pytest\n",
    ".github/workflows/deploy.yml": "name: Deploy site\non:\n  push:\n    branches: [main]\npermissions:\n  pages: write\n"
                                    "jobs:\n  d:\n    environment: github-pages\n    runs-on: ubuntu-latest\n    steps:\n"
                                    "      - uses: actions/deploy-pages@v4\n",
    ".github/workflows/docs.yml": "name: Docs lint\non:\n  push:\n    paths-ignore: ['README.md', 'docs/**', 'assets/**',"
                                  " '.github/showcase.yml', 'CONTRIBUTING.md']\njobs:\n  l:\n    runs-on: x\n    steps:\n"
                                  "      - run: make lint\n",
    ".github/workflows/notify.yml": "name: Notify\non:\n  workflow_run:\n    workflows: [Deploy site]\n    types: [completed]\n"
                                    "jobs:\n  n:\n    runs-on: x\n    steps:\n      - run: curl -X POST https://hooks.example.com/deploy\n",
    ".github/workflows/nightly.yml": "name: Nightly publish\non:\n  schedule:\n    - cron: '0 3 * * *'\njobs:\n  p:\n"
                                     "    runs-on: x\n    steps:\n      - uses: pypa/gh-action-pypi-publish@release/v1\n",
}
BADGE = "[![Tests](https://github.com/Northwind-Trading-Co/support-triage-agent/actions/workflows/tests.yml/badge.svg)](x)"


def test_push_filters():
    assert C.push_triggered(None, "main", ["README.md"])
    assert not C.push_triggered({"tags": ["v*"]}, "main", ["README.md"])
    assert C.push_triggered({"branches": ["ma*"]}, "main", ["README.md"])
    assert not C.push_triggered({"branches": ["release/**"]}, "main", ["README.md"])
    assert not C.push_triggered({"branches-ignore": ["main"]}, "main", ["README.md"])
    assert C.push_triggered({"paths": ["src/**", "!src/x"]}, "main", ["src/a/b.py"])
    assert not C.push_triggered({"paths": ["src/**", "!src/x"]}, "main", ["src/x"])
    assert not C.push_triggered({"paths-ignore": ["**.md"]}, "main", ["README.md", "docs/a.md"])
    assert C.push_triggered({"paths-ignore": ["**.md"]}, "main", ["README.md", "assets/icon.png"])


@pytest.mark.parametrize("runs_file", ["runs-gh.json", "runs-rest.json"])
def test_actions_report(brand, runs_file):
    meta = meta_dict(default_branch="main", has_pages=False)
    res = C.actions_report(meta, runs=json.loads((FIX / runs_file).read_text(encoding="utf-8")),
                           workflows=json.loads((FIX / "workflows-rest.json").read_text(encoding="utf-8")), workflow_files=WF,
                           readme=BADGE, root_files=["vercel.json", "README.md"], resolver=resolver(brand))
    w = {r["path"]: r for r in res["workflows"]}
    tests = w[".github/workflows/tests.yml"]
    assert tests["latest"] == "failure" and {"ci-red", "badge-red"} <= set(tests["flags"])  # feature/x ignored
    assert res["ci_badge_allowed"][".github/workflows/tests.yml"] is False
    assert res["ci_badge_allowed"][".github/workflows/deploy.yml"] is True
    assert "deploy-on-merge" in w[".github/workflows/deploy.yml"]["flags"]
    assert w[".github/workflows/docs.yml"]["merge_triggers"] == []
    assert w[".github/workflows/notify.yml"]["merge_triggers"] == ["workflow_run:Deploy site"]
    assert "disabled_inactivity" in w[".github/workflows/nightly.yml"]["flags"]
    rd = res["redeploy"]
    assert rd["avoid_redeploy"] and rd["merge_subject"].endswith("[skip ci]") and rd["post_merge_checks"]
    kinds = {(d["workflow"], d["trigger"], d["suppressed_by_skip_ci"]) for d in rd["deploy_on_merge"]}
    assert (".github/workflows/deploy.yml", "push", True) in kinds
    assert (".github/workflows/nightly.yml", "schedule", False) in kinds
    assert ("-", "external integration", False) in kinds
    assert res["result"] == "fail" and "ci-red" in res["logs"] and "workflow-disabled" in res["logs"]
    assert res["tsv"]["actions-health"][0][0] == f"{NW}/support-triage-agent"
    assert all(x[0] == "gh" and x[1] == "api" for x in rd["post_merge_checks"])  # read-only GETs


def test_actions_without_workflow_data(brand):
    res = C.actions_report(meta_dict(), readme=BADGE, resolver=resolver(brand))
    assert res["result"] == "needs-input" and "needs-input:workflows" in res["logs"]
    assert res["ci_badge_allowed"] == {".github/workflows/tests.yml": False}
    assert res["redeploy"]["merge_subject"] == "<PR title> [skip ci]"


def test_branch_source_pages_is_not_suppressed(brand):
    res = C.actions_report(meta_dict(has_pages=True), workflow_files={}, resolver=resolver(brand),
                           pages={"build_type": "legacy", "source": {"branch": "main", "path": "/"}})
    pages = res["redeploy"]["not_suppressed_by_skip_ci"]
    assert pages and pages[0]["workflow"] == "pages-build-deployment"


FORK_WF = {
    ".github/workflows/cla.yml": "name: CLA\non: [pull_request_target]\njobs:\n  c:\n    runs-on: x\n    steps:\n"
                                 "      - uses: contributor-assistant/github-action@v2\n",
    ".github/workflows/stale.yml": "name: Stale\non:\n  schedule:\n    - cron: '0 0 * * *'\njobs:\n  s:\n    runs-on: x\n"
                                   "    steps:\n      - uses: actions/stale@v9\n",
    ".github/workflows/guarded.yml": "name: Labeler\non: [pull_request]\njobs:\n  l:\n"
                                     "    if: github.repository == 'upstream-org/tool'\n    runs-on: x\n    steps:\n"
                                     "      - uses: actions/labeler@v5\n",
    ".github/workflows/ci.yml": "name: CI\non: [push]\njobs:\n  t:\n    runs-on: x\n    steps:\n      - run: make\n",
}


def test_fork_upstream_automation_becomes_workflow_toggle_proposals(brand):
    meta = meta_dict(repo="tool-fork", fork=True, parent={"full_name": "upstream-org/tool"})
    wfs = {"workflows": [{"id": 21, "name": "CLA", "path": ".github/workflows/cla.yml", "state": "active"},
                         {"id": 22, "name": "Stale", "path": ".github/workflows/stale.yml", "state": "active"}]}
    res = C.actions_report(meta, workflows=wfs, workflow_files=FORK_WF, resolver=resolver(brand))
    props = {p["argv"][3]: p for p in res["proposals"]}
    # the workflow file name, not the numeric id: the guard's workflow-toggle approval detail is the workflow file
    assert set(props) == {"cla.yml", "stale.yml"} and not res["jobs"]
    assert props["cla.yml"]["kind"] == "workflow-toggle" and props["cla.yml"]["argv"][:3] == ["gh", "workflow", "disable"]
    assert props["cla.yml"]["repo"] == f"{NW}/tool-fork" and "approval_id" not in props["cla.yml"]
    approved = C.actions_report(meta, workflows=wfs, workflow_files=FORK_WF, resolver=resolver(brand),
                                approval_ids={"cla.yml": "q79-7"})
    assert [j["approval_id"] for j in approved["jobs"]] == ["q79-7"]
    estate_parent = C.actions_report(dict(meta, parent={"full_name": "CompleteTech-LLC/tool"}), workflows=wfs,
                                     workflow_files=FORK_WF, resolver=resolver(brand))
    assert not estate_parent["proposals"] and not estate_parent["upstream_fork"]  # F1x: the parent is ours


# ---------------------------------------------------------------------------------------------------
# images (RP-03, RP-10)
# ---------------------------------------------------------------------------------------------------
def _png(img, **kw) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG", **kw)
    return b.getvalue()


def _gradient(w=640, h=480):
    from PIL import Image
    im = Image.new("RGB", (w, h))
    im.putdata([(x * 255 // w, y * 255 // h, 128) for y in range(h) for x in range(w)])
    return im


def _noise(w=400, h=400):
    from PIL import Image
    rnd = random.Random(7)
    return Image.frombytes("RGB", (w, h), bytes(rnd.getrandbits(8) for _ in range(w * h * 3)))


def test_images_budget_lossless_and_lossy(tmp_path):
    from PIL import Image
    dark = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    dark.paste((20, 20, 30, 255), (10, 10, 40, 40))
    readme = ("![Flow](docs/big.png)\n<img src=\"docs/noise.png\" alt=\"\">\n![Logo](public/hero.png)\n"
              "![New](assets/examples/new.png)\n![Dark](docs/dark.png)\n![Remote](https://x.test/a.png)\n"
              "```mermaid\ngraph TD\nclassDef a fill:#000\n```\n")
    root = write(tmp_path, {"README.md": readme, "docs/big.png": _png(_gradient(), compress_level=0),
                            "docs/noise.png": _png(_noise()), "public/hero.png": _png(_noise()),
                            "assets/examples/new.png": _png(_noise(500, 500)), "docs/dark.png": _png(dark)})
    tree = C.Tree(root)
    out_dir = tmp_path / "candidates"
    res = C.images_report(tree, ["README.md"], new_paths={"assets/examples/new.png"}, out_dir=out_dir)
    by = {r["path"]: r for r in res["images"]}
    assert "warn:image-weight" in by["docs/big.png"]["flags"] and by["docs/big.png"]["lossless"]["check"] == "ok"
    plan = {(p["path"], p["kind"]): p for p in res["plan"]}
    assert plan[("docs/big.png", "lossless")]["meets_limit"] is True
    assert plan[("docs/big.png", "lossless")]["argv"][:4] == ["oxipng", "-o4", "--strip", "safe"]
    cand = Image.open(out_dir / "docs/big.png")
    assert cand.tobytes() == Image.open(root / "docs/big.png").tobytes()  # pixel-identical candidate
    assert (root / "docs/big.png").stat().st_size > (out_dir / "docs/big.png").stat().st_size
    assert by["public/hero.png"]["protected"] and not [p for p in res["plan"] if p["path"] == "public/hero.png"]
    assert "fail:image-weight" in by["assets/examples/new.png"]["flags"]
    assert {x["path"] for x in res["needs_approval"]} >= {"docs/noise.png"}
    assert "warn:dark-theme" in by["docs/dark.png"]["flags"]
    assert res["alt_missing"][0]["target"] == "docs/noise.png" and res["mermaid"]
    assert res["remote"][0]["target"] == "https://x.test/a.png"
    assert res["result"] == "fail"
    approved = C.images_report(tree, ["README.md"], approval_id="lossy-3")
    assert any(p["kind"] == "lossy" and p.get("approval_id") == "lossy-3" for p in approved["plan"])
    assert not approved["needs_approval"]


def test_new_files_from_git(tmp_path):
    root = write(tmp_path, {"README.md": "x", "a.png": b"1"})
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    (root / "b.png").write_bytes(b"2")
    assert C.new_files(C.Tree(root), None) == {"b.png"}


# ---------------------------------------------------------------------------------------------------
# sidebar (RP-05)
# ---------------------------------------------------------------------------------------------------
def test_sidebar_plan_single_repo(brand):
    r = resolver(brand)
    facts = json.loads((FIX / "sidebar-facts.json").read_text(encoding="utf-8"))
    pk = C.packages_by_repo(json.loads((FIX / "packages.json").read_text(encoding="utf-8")), r)
    res = C.sidebar_plan(meta_dict(), facts[f"{NW}/support-triage-agent"], resolver=r, packages=pk)
    assert res["row"]["show_releases"] is False and res["row"]["show_deployments"] is True
    assert res["row"]["show_packages"] is False and res["result"] == "proposal"
    job = res["job"]
    assert job["kind"] == "browser" and job["repo"] == f"{NW}/support-triage-agent" and job["argv"] == []
    assert job["url"] == f"https://github.com/{NW}/support-triage-agent" and job["ui_action"] == "about-sidebar"
    text = "\n".join(job["steps"])
    assert '"Releases" is unchecked' in text and '"Deployments" is checked' in text and "Save changes" in text
    assert "No releases published" in text and "Use your GitHub Pages website" in text
    assert res["tsv"] == [f"{NW}/support-triage-agent", "0", "0", "1", "hide", "hide", "show", "yes"]


def test_sidebar_defaults_unknown_and_current(brand):
    r = resolver(brand)
    full = {"releases": [1], "deployments": [1], "packages": 2}
    assert C.sidebar_plan(meta_dict(), full, resolver=r)["job"] is None  # all shown: GitHub's default
    unknown = C.sidebar_plan(meta_dict(), {"releases": []}, resolver=r)
    assert unknown["result"] == "needs-input" and unknown["job"] is None
    assert "needs-input:sidebar-facts:packages" in unknown["logs"]
    done = C.sidebar_plan(meta_dict(), {"releases": 0, "deployments": 0, "packages": 0}, resolver=r,
                          current={"releases": False, "packages": False, "deployments": False})
    assert done["job"] is None  # already as wanted: no-op


def test_sidebar_packages_follow_a_renamed_org(brand):
    r = resolver(brand, "org-005")
    pk = C.packages_by_repo([{"repository": {"full_name": "CompleteTech-Pokemon/northwind-card-demo"}}], r)
    res = C.sidebar_plan(meta_dict(owner="CompleteTech-TCG", repo="northwind-card-demo"), {"releases": 0, "deployments": 0},
                         resolver=r, packages=pk)
    assert res["row"]["packages"] == 1 and res["row"]["repo"] == "CompleteTech-TCG/northwind-card-demo"


def test_sidebar_cli_estate_file(capsys, tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    code, out = run_content(capsys, "--no-repo-dir", "content", "sidebar", "--facts", FIX / "sidebar-facts.json",
                            "--packages", FIX / "packages.json", "--jobs", jobs, *NO_ESTATE)
    lines = [json.loads(x) for x in jobs.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2 and all(j["kind"] == "browser" and j["steps"] for j in lines)
    assert code == 0 and out["repos"] == 3
    assert {s["repo"] for s in out["skipped"]} == {"Pick-Your-AI/pya-app", "BunsDev/someone-else"}
    ids = {j["repo"]: j for j in out["jobs"]}
    assert set(ids) == {f"{NW}/support-triage-agent", f"{NW}/ledger-sync"}
    ledger = "\n".join(ids[f"{NW}/ledger-sync"]["steps"])
    assert '"Releases" is checked' in ledger and '"Packages" is checked' in ledger and '"Deployments" is unchecked' in ledger
    assert "screenshot of the About column" in ledger  # private: no anonymous curl check
    assert any("unknown-facts" in x for x in out["logs"])


def test_sidebar_cli_batch_with_missing_facts_is_not_a_pass(capsys, tmp_path):
    """Round-2 defect: a batch where every repository lacked its packages count (so got no job) read as `pass`."""
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({f"{NW}/support-triage-agent": {"releases": [{"id": 1}], "deployments": []}}), encoding="utf-8")
    code, out = run_content(capsys, "--no-repo-dir", "content", "sidebar", "--facts", facts, *NO_ESTATE)
    assert code == 0 and out["result"] == "needs-input" and out["needs_input"] == 1 and out["jobs"] == []
    assert out["logs"] == [f"{NW}/support-triage-agent:needs-input:sidebar-facts:packages"]


# ---------------------------------------------------------------------------------------------------
# icon (RT-04)
# ---------------------------------------------------------------------------------------------------
def _candidate(card="#F8FAFC", ink=(0, 90, 221), size=800, box=(200, 260, 600, 560)):
    from PIL import Image, ImageDraw
    from ctshowcase.color import rgb
    im = Image.new("RGB", (size, size), rgb(card))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, radius=40, outline=ink, width=40)
    d.ellipse((380, 380, 420, 420), fill=(168, 124, 0))
    return im


@pytest.fixture
def icon_ctx(make_ctx):
    return make_ctx(owner=NW, repo="support-triage-agent", topics=["completetech", "email"])


def test_icon_prompt_needs_writer_then_ok(brand, icon_ctx):
    r = resolver(brand)
    res = C.icon_prompt(icon_ctx, r, ART)
    assert res["missing"] == ["GLYPH_DESCRIPTION", "GLYPH_NAME", "SIZE_CLASS", "SPARK_PLACEMENT"]
    glyph = {"glyph_name": "Inbox Tray", "glyph_description": "An open tray seen front-on.",
             "spark_placement": "held inside the tray", "size_class": "wide"}
    res = C.icon_prompt(icon_ctx, r, ART, glyph)
    p = res["prompt"]
    assert res["missing"] == [] and p.startswith("NEON NIGHT REPO ICON · STYLE LOCK v1.2 · Northwind-Trading-Co/")
    assert "#46B8FF" in p and "#CBEBFF" in p and "#0081ED" in p and "Bulb Gold #FFC300" in p
    assert "Size class WIDE:" in p and "seed 1025" in p and "GitHub avatar" not in p and "28 avatars in" not in p
    assert "art/reference/avatars/Northwind-Trading-Co.png" not in p.split("(b) Style")[0]
    assert "art/out/icons/Northwind-Trading-Co/support-triage-agent-1024-c{1..4}.png" in p
    assert "Do not draw the Northwind-Trading-Co org glyph (Compass rose" in p
    assert res["render"]["ink"] == "#005ADD" and res["render"]["live_area"] == [168, 168, 856, 856]
    md = C.prompt_markdown(res)
    assert md.startswith("# Repo icon prompt: Northwind-Trading-Co/support-triage-agent") and "```text" in md


def test_icon_prompt_states_the_flat_ground(brand, icon_ctx):
    """The option-A prompt names the family card colour as one flat ground and forbids vignette and glow."""
    glyph = {"glyph_name": "Inbox Tray", "glyph_description": "An open tray seen front-on.",
             "spark_placement": "held inside the tray", "size_class": "wide"}
    p = C.icon_prompt(icon_ctx, resolver(brand), C.load_art_direction(), glyph)["prompt"]
    assert "perfectly flat" in p
    assert brand.style(NW)["tokens"]["card_fill"].upper() in p
    assert "no vignette, texture, gradient, shadow or glow" in p
    assert "Keep the background empty" not in p
    assert "880 px" not in p  # the bundled template has no light pool to conflict with the flat ground


def test_icon_prompt_states_the_flat_ground_for_estate_template(brand, icon_ctx):
    """The estate-format (d) template's soft light pool becomes the flat card ground (review: #53 gap)."""
    glyph = {"glyph_name": "Inbox Tray", "glyph_description": "An open tray seen front-on.",
             "spark_placement": "held inside the tray", "size_class": "wide"}
    art = (Path(__file__).parent / "fixtures" / "content" / "ART_DIRECTION.min.md").read_text(encoding="utf-8")
    p = C.icon_prompt(icon_ctx, resolver(brand), art, glyph)["prompt"]
    assert "perfectly flat" in p and brand.style(NW)["tokens"]["card_fill"].upper() in p
    assert "no vignette, texture, gradient, shadow or glow" in p
    assert "880 px" not in p and "soft round pool" not in p
    # the heading no longer claims the avatars' night ground, which contradicts the flat card ground
    assert "identical to the Neon Night avatars" not in p
    assert "28 avatars" not in p and "28 repo icons" not in p
    bg = next(line for line in p.splitlines() if "BACKGROUND" in line)
    assert "one flat ground, not the avatar night tile" in bg


def test_icon_prompt_custom_template_states_the_exact_ground_clause(brand, icon_ctx):
    """An option-A template without {POOL} or the 'Keep the background empty' anchor, whose glyph text happens to
    contain 'perfectly flat', still gets the ground clause (review: the fallback must not key on loose text)."""
    glyph = {"glyph_name": "Inbox Tray", "glyph_description": "An open tray seen front-on.",
             "spark_placement": "held inside the tray", "size_class": "wide"}
    art = C.load_art_direction()
    anchor = "Keep the background empty and the glyph inside"
    assert anchor in art
    art = art.replace(anchor, "Draw a perfectly flat glyph. Keep the background empty.")
    assert anchor not in art
    card = brand.style(NW)["tokens"]["card_fill"]
    p = C.icon_prompt(icon_ctx, resolver(brand), art, glyph)["prompt"]
    assert C.ground_clause(card) in p
    assert card.upper() in p


def test_corner_ground_zero_tolerance_accepts_identical_corners():
    from ctshowcase.iconbox import corner_ground
    flat = _candidate("#F8FAFC", size=64, box=(16, 16, 48, 48))
    assert corner_ground(flat, 0) is not None
    off = flat.copy()
    off.putpixel((63, 63), (240, 240, 240))
    assert corner_ground(off, 0) is None


@pytest.mark.parametrize("mode", ["auto", "keep", "transparent"])
def test_icon_zero_tolerance_normalizes_a_flat_ground(mode):
    img = _candidate("#F8FAFC", size=64, box=(16, 16, 48, 48))
    out, info = C.normalize_icon(img, mode, "#0F172A", tolerance=0)
    assert out.size == (1024, 1024)


def test_icon_zero_tolerance_still_rejects_unequal_corners():
    img = _vignette("#F8FAFC", "#EEF0F2")
    with pytest.raises(ArtFail, match="icon-ground"):
        C.normalize_icon(img, "auto", "#0F172A", tolerance=0)


def test_icon_prompt_parses_the_bundled_art_direction(brand, fixture_meta):
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    ctx = RepoContext(brand, normalize(fixture_meta("CompleteTech-Skills__agentic-email-skill")), None)
    res = C.icon_prompt(ctx, resolver(brand), C.load_art_direction())
    assert res["missing"] == ["GLYPH_DESCRIPTION", "GLYPH_NAME", "SIZE_CLASS", "SPARK_PLACEMENT"]
    assert res["facts"]["org_glyph"] is None  # bundled defaults do not require the estate's avatar inventory
    assert res["render"]["ink"] == brand.style("CompleteTech-Skills")["tokens"]["icon_ink"]


def test_icon_normalize_keys_trims_and_passes_qa(brand):
    card = brand.style(NW)["tokens"]["card_fill"]
    img, info = C.normalize_icon(_candidate(card), "auto", card)
    assert info["mode"] == "transparent" and info["keyed_from"] and img.size == (1024, 1024) and img.mode == "RGBA"
    box = img.getchannel("A").getbbox()
    assert box[0] >= 168 and box[2] <= 856 and max(box[2] - box[0], box[3] - box[1]) >= 680
    data, logs = C.icon_bytes(img)
    qa = C.icon_qa(data, card=card, ink=["#005ADD", "#A87C00"])
    assert qa["result"] == "pass", qa
    assert any(c["check"] == "no-text" and c["result"] == "manual" for c in qa["checks"])


def test_icon_keep_ground_and_failures(brand):
    from PIL import Image
    card = brand.style(NW)["tokens"]["card_fill"]
    tile = _candidate("#171D28", ink=(70, 184, 255), size=1000, box=(250, 250, 750, 750))
    img, info = C.normalize_icon(tile, "auto", card)
    assert info["mode"] == "keep" and img.mode == "RGB"
    assert C.icon_qa(C.icon_bytes(img)[0], card=card)["result"] in ("pass", "warn")
    pale = C.normalize_icon(_candidate(card, ink=(212, 218, 226)), "transparent", card)[0]
    qa = C.icon_qa(C.icon_bytes(pale)[0], card=card)
    assert qa["result"] == "fail" and any(c["check"] == "contrast-on-card" and c["result"] == "fail" for c in qa["checks"])
    small = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    assert any(c["check"] == "size" and c["result"] == "fail" for c in C.icon_qa(_png(small), card=card)["checks"])
    edge = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    edge.paste((0, 90, 221, 255), (20, 300, 1000, 700))
    qa = C.icon_qa(_png(edge), card=card, siblings=["icon.png", "icon-dark.png"])
    fails = {c["check"] for c in qa["checks"] if c["result"] == "fail"}
    assert {"live-area", "one-file"} <= fails and "transparent-corners" not in fails
    with pytest.raises(ArtFail):
        noisy = _noise(64, 64)
        C.normalize_icon(noisy, "auto", card)


@pytest.mark.parametrize("ground,card,mode,reason", [
    ("#F8FAFC", "#0F172A", "transparent", "uniform-ground"),  # pale tile on a dark card: keyed out (#52)
    ("#E6EDF5", "#0F172A", "transparent", "uniform-ground"),
    ("#171D28", "#F8FAFC", "keep", "night-tile"),
    ("#0F172A", "#0F172A", "transparent", "near-card"),
    # Measured dE(#000000, #0F172A) is 16.5 > CONTENT_DE 12, so pure black on that card is a night tile.
    ("#000000", "#0F172A", "keep", "night-tile"),
    ("#171D28", None, "keep", "night-tile"),  # no card colour: the luminance rule decides
])
def test_icon_auto_ground_rule(ground, card, mode, reason):
    img = _candidate(ground, ink=(70, 184, 255), size=1000, box=(250, 250, 750, 750))
    info = C.normalize_icon(img, "auto", card)[1]
    assert info["mode"] == mode
    assert info["auto_reason"] == reason


def test_icon_pale_ground_on_dark_card_keys_to_small_rgba(brand):
    img, info = C.normalize_icon(_candidate("#F8FAFC", ink=(16, 185, 129), size=1024, box=(250, 250, 750, 750)),
                                 "auto", "#032530")
    assert info["mode"] == "transparent" and img.mode == "RGBA" and img.getpixel((0, 0))[3] == 0
    assert len(C.icon_bytes(img)[0]) <= 300_000
    # explicit modes are unchanged
    kept = C.normalize_icon(_candidate("#F8FAFC", size=1024, box=(250, 250, 750, 750)), "keep", "#032530")[0]
    assert kept.mode == "RGB"


def _noisy(ground, size=1024, seed=1, amp=2):
    """A generator-like ground: exact corners, seeded +/-amp per-channel noise elsewhere, one ink outline."""
    import random
    from PIL import Image, ImageDraw
    from ctshowcase.color import rgb
    g = rgb(ground)
    rnd = random.Random(seed)
    im = Image.new("RGB", (size, size))
    im.putdata([tuple(max(0, min(255, c + rnd.randint(-amp, amp))) for c in g) for _ in range(size * size)])
    ImageDraw.Draw(im).rounded_rectangle((250, 250, 750, 750), radius=40, outline=(16, 185, 129), width=40)
    for xy in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
        im.putpixel(xy, g)
    return im


def test_icon_noisy_dark_ground_falls_back_to_keying_inside_the_budget():
    """A noisy dark ground on a dark card would be kept as a night tile far over 300 KB; auto keys it instead."""
    from ctshowcase.scene import png_bytes
    img = _noisy("#0F172A")
    kept, kinfo = C.normalize_icon(img, "keep", "#032530")
    assert len(png_bytes(kept)) > 300_000  # the failure the issue reports
    out, info = C.normalize_icon(img, "auto", "#032530")
    assert info["mode"] == "transparent" and info["auto_reason"] == "budget-fallback"
    assert len(C.icon_bytes(out)[0]) <= 300_000


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_icon_ground_tolerance_rejects_non_finite_and_negative(bad):
    from ctshowcase.errors import ShowcaseError
    img = _candidate("#F8FAFC", size=256, box=(60, 60, 190, 190))
    with pytest.raises(ShowcaseError, match="--ground-tolerance"):
        C.normalize_icon(img, "auto", "#032530", tolerance=bad)


def test_corner_ground_boundary_matches_main_at_default():
    """Corners exactly GROUND_DE apart are not one ground, as on main (strict comparison)."""
    from PIL import Image
    from ctshowcase.iconbox import GROUND_DE, corner_ground, corner_spread
    im = Image.new("RGB", (8, 8), (200, 200, 200))
    for v in range(201, 230):
        im.putpixel((7, 7), (v, v, v))
        if corner_spread(im) >= GROUND_DE:
            break
    s = corner_spread(im)
    assert corner_ground(im) is None
    assert corner_ground(im, tolerance=s + 0.01) is not None
    assert corner_ground(im, tolerance=s) is None


def _vignette(top, bottom, size=1024):
    from PIL import Image, ImageDraw
    from ctshowcase.color import rgb
    t, b = rgb(top), rgb(bottom)
    im = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(im)
    for y in range(size):
        k = y / (size - 1)
        d.line([(0, y), (size, y)], fill=tuple(round(t[i] + (b[i] - t[i]) * k) for i in range(3)))
    d.rounded_rectangle((250, 250, 750, 750), radius=40, outline=(16, 185, 129), width=40)
    return im


def test_icon_ground_tolerance_boundaries():
    from ctshowcase.iconbox import corner_spread
    img = _vignette("#F8FAFC", "#EEF0F2")  # measured corner dE 3.48, above the default 3.0
    assert 3.1 < corner_spread(img) < 4.9
    with pytest.raises(ArtFail) as e:
        C.normalize_icon(img, "auto", "#032530")
    msg = str(e.value)
    assert "3.4" in msg and "--ground-tolerance 3" in msg
    out, info = C.normalize_icon(img, "auto", "#032530", tolerance=5)
    assert info["mode"] == "transparent" and out.getpixel((0, 0))[3] == 0 and out.getpixel((512, 100))[3] == 0
    far = _vignette("#F8FAFC", "#B0B8C4")  # corner dE far above 5
    with pytest.raises(ArtFail, match="--ground-tolerance 5"):
        C.normalize_icon(far, "auto", "#032530", tolerance=5)


def _radial(corner, centre, size=1024):
    from PIL import Image, ImageDraw
    from ctshowcase.color import rgb
    c, m = rgb(corner), rgb(centre)
    im = Image.new("RGB", (size, size))
    px = im.load()
    far = 2 * (size / 2) ** 2
    for y in range(size):
        for x in range(size):
            k = 1 - ((x - size / 2) ** 2 + (y - size / 2) ** 2) / far * 2
            k = max(0.0, k)
            px[x, y] = tuple(round(c[i] + (m[i] - c[i]) * k) for i in range(3))
    ImageDraw.Draw(im).rounded_rectangle((250, 250, 750, 750), radius=40, outline=(16, 185, 129), width=40)
    return im


def test_icon_radial_vignette_with_matching_corners_keys_at_raised_tolerance():
    """Review B: corners agree (dE 0) but the interior is darker; raising --ground-tolerance must widen the key
    so interior ground becomes transparent, while the default tolerance keeps the base key."""
    img = _radial("#EEF0F2", "#D8E0EA")
    base = C.normalize_icon(img, "auto", "#032530")[0]
    out, info = C.normalize_icon(img, "auto", "#032530", tolerance=5)
    assert info["mode"] == "transparent"
    assert out.getpixel((512, 512))[3] == 0  # empty interior of the outline
    assert base.getpixel((512, 512))[3] != 0  # default tolerance unchanged


def test_icon_vignetted_night_tile_passes_qa_after_flattening():
    """Review A/B: a kept (night-tile) ground vignetted past the default tolerance is flattened, so icon_qa and the
    banner/card tile code (default tolerance) accept what `normalize --ground-tolerance 5` accepted."""
    from ctshowcase.iconbox import corner_ground, corner_spread
    img = _vignette("#171D28", "#1F2530")
    assert 3.1 < corner_spread(img) < 4.9
    out, info = C.normalize_icon(img, "auto", "#F8FAFC", tolerance=5)
    assert info["mode"] == "keep" and info["auto_reason"] == "night-tile"
    assert corner_ground(out) is not None
    qa = C.icon_qa(C.icon_bytes(out)[0], card="#F8FAFC")
    assert not [c for c in qa["checks"] if c["check"] == "opaque-ground" and c["result"] != "pass"]


def test_icon_explicit_transparent_keeps_base_key_threshold():
    """Review A/B: within the default tolerance the key stays KEY_DE (6) in explicit modes; it only widens when
    --ground-tolerance is raised above the default."""
    from PIL import ImageDraw
    im = _vignette("#FFFFFF", "#F9F9F9")
    d = ImageDraw.Draw(im)
    d.rectangle((250, 250, 750, 750), fill=(234, 234, 234))
    out, info = C.normalize_icon(im, "transparent", "#032530")
    assert info["mode"] == "transparent" and out.getbbox() is not None


def test_icon_not_the_org_glyph(brand, tmp_path):
    card = brand.style(NW)["tokens"]["card_fill"]
    img = C.normalize_icon(_candidate(card), "auto", card)[0]
    data = C.icon_bytes(img)[0]
    mark = write(tmp_path, {"mark.png": data}) / "mark.png"
    qa = C.icon_qa(data, card=card, org_mark=mark)
    assert any(c["check"] == "not-org-glyph" and c["result"] == "fail" for c in qa["checks"])


def test_icon_cli_normalize_and_check(capsys, tmp_path, brand):
    card = brand.style(NW)["tokens"]["card_fill"]
    src = tmp_path / "cand.png"
    _candidate(card).save(src)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    out = tmp_path / "repo" / "assets" / "icon.png"
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "normalize", "--in", src,
                            "--out", out, "--preview", tmp_path / "p48.png", "--art-direction", FIX / "ART_DIRECTION.min.md",
                            *NO_ESTATE)
    assert code == 0 and res["result"] == "pass" and out.is_file() and (tmp_path / "p48.png").is_file()
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "check", "--out", out,
                            "--art-direction", FIX / "ART_DIRECTION.min.md", *NO_ESTATE)
    assert code == 0 and res["qa"]["result"] == "pass"
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "prompt",
                            "--art-direction", FIX / "ART_DIRECTION.min.md", "--out", tmp_path / "icon.md", *NO_ESTATE)
    assert code == 1 and res["result"] == "needs-writer" and res["out"] is None and not (tmp_path / "icon.md").exists()


def test_icon_watching_org_is_exempt(capsys, tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner="romgenie-following-repos", repo="tool", fork=True)), encoding="utf-8")
    code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "icon", "prompt", *NO_ESTATE)
    assert code == 0 and res["result"] == "exempt"


# ---------------------------------------------------------------------------------------------------
# CLI: refusals, linguist, actions, social alias
# ---------------------------------------------------------------------------------------------------
def test_cli_refuses_excluded_and_t3(capsys, tmp_path):
    for owner in ("BunsDev", "Pick-Your-AI"):
        meta = tmp_path / f"{owner}.json"
        meta.write_text(json.dumps(meta_dict(owner=owner, repo="x")), encoding="utf-8")
        code, res = run_content(capsys, "--meta", meta, "--no-repo-dir", "content", "linguist", *NO_ESTATE)
        assert code == 2 and res["result"] == "refused"


def test_cli_actions_and_linguist(capsys, tmp_path):
    root = write(tmp_path / "repo", {**WF, "README.md": BADGE + "\n", "pyproject.toml": "[project]\nname='x'\n",
                                     "src/a.py": "x" * 100, "reports/r.html": "h" * 9000})
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(languages={"HTML": 9000, "Python": 100})), encoding="utf-8")
    code, res = run_content(capsys, "--meta", meta, "--repo-dir", root, "content", "actions", "--runs",
                            FIX / "runs-rest.json", "--workflows", FIX / "workflows-rest.json", "--report",
                            tmp_path / "actions.json", *NO_ESTATE)
    assert code == 1 and res["result"] == "fail" and (tmp_path / "actions.json").is_file()
    assert res["redeploy"]["avoid_redeploy"]
    code, res = run_content(capsys, "--meta", meta, "--repo-dir", root, "content", "linguist", *NO_ESTATE)
    assert code == 0 and res["primary"]["language"] == "Python" and res["gitattributes_lines"] == [
        "reports/** linguist-generated"]


def test_cli_images(capsys, tmp_path):
    root = write(tmp_path / "repo", {"README.md": "![Big](docs/big.png)\n", "docs/big.png": _png(_noise(500, 500))})
    code, res = run_content(capsys, "--repo-dir", root, "content", "images", *NO_ESTATE)
    assert code == 0 and res["result"] == "warn" and res["needs_approval"]


def test_cli_social_alias_emits_upload_job(capsys, tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    out = tmp_path / "social.png"
    code, res = run_content(capsys, "--format", "json", "--meta", meta, "--no-repo-dir", "content", "social", "--out", out,
                            "--job", *NO_ESTATE)
    assert code == 0 and res["action"] == "social" and res["alias_of"] == "social-preview" and out.is_file()
    job = res["job"]
    assert job["kind"] == "browser" and job["url"].endswith("/support-triage-agent/settings")
    assert any("Social preview" in s for s in job["steps"]) and any("usesCustomOpenGraphImage" in s for s in job["steps"])


def test_add_parser_registers_every_action():
    import argparse
    import showcase
    p = showcase.parser()
    sub = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    if "content" not in sub.choices:
        C.add_parser(sub, showcase)
    content = sub.choices["content"]
    acts = next(a for a in content._actions if isinstance(a, argparse._SubParsersAction))
    assert set(acts.choices) == set(C.ACTIONS)
