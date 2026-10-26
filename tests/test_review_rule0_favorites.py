"""Review round 1 (integration) regressions. Synthetic Northwind data only (tests/fixtures, brand.yaml's public rows).

- §6.4 rule 0 trusts a captured file list as proof of absence only when GitHub returned the whole recursive tree
  (`files_complete: true`); a truncated capture holds the rename, and the .github health check reads unlisted files as
  unknown.
- Rule 0 also reads the owner's `.github` repository, whose default issue forms apply to a repository without a
  `.github/ISSUE_TEMPLATE/` of its own.
- Whether a form, Markdown template or dependabot.yml assigns a label is decided by parsing the YAML, so multi-line
  flow sequences, quoted keys, a BOM and aliases are recognised; an unparseable file holds the rename.
- A favorite of a placeholder or excluded owner, or any favorite whose captured metadata is not public, is never named.
- `content icon` refuses a family on hold, as banner and card do.
"""
import copy
import json

import pytest

from conftest import ROOT, meta_dict, run_cli
from ctshowcase import labels
from ctshowcase import meta as M
from ctshowcase import org as O
from ctshowcase.config import Brand, load_yaml_text
from ctshowcase.resolver import Resolver

FIX = ROOT / "tests" / "fixtures" / "org"
N, L = "Northwind-Trading-Co", "Northwind-Labs"
GH = f"{N}/.github"
HOLD = "needs-input:label-references"
LIVE = [{"name": "bug", "color": "d73a4a", "description": "Something isn't working"}]
CLEAN = labels.defaults_source(GH, meta={"files": ["README.md", "profile/README.md"], "files_complete": True})


def _renames(ops):
    return {o["name"]: o["new_name"] for o in ops if o["op"] == "rename"}


def _write(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")
    return root


# ------------------------------------------------------------------------------------------- truncated tree
def _fake_gh(truncated):
    def gh(path, paginate=False, raw=False):
        if path == f"repos/{N}/big-monorepo":
            return {"name": "big-monorepo", "full_name": f"{N}/big-monorepo", "owner": {"login": N},
                    "default_branch": "main", "private": False, "visibility": "public"}
        if path.endswith("/labels?per_page=100"):
            return LIVE
        if "git/trees" in path:
            return {"sha": "x", "truncated": truncated, "tree": [{"path": "README.md", "type": "blob", "size": 1},
                                                                 {"path": "src/a.py", "type": "blob", "size": 1}]}
        return None
    return gh


def test_truncated_tree_is_not_proof_of_absence(monkeypatch):
    monkeypatch.setattr(M, "_gh", _fake_gh(True))
    m = M.from_gh(f"{N}/big-monorepo")
    assert m["files"] == ["README.md", "src/a.py"] and m["files_complete"] is False
    assert labels.reference_files(m["files"], m["files_complete"]) == ([], False)
    ops, logs = labels.plan(m["labels"], None, files=m["files"], complete=m["files_complete"], defaults=CLEAN)
    assert _renames(ops) == {} and HOLD in logs
    assert next(o for o in ops if o["name"] == "bug")["check_files"] == list(labels.REFERENCE_PATTERNS)
    # the whole tree (truncated: false) proves it, as before
    monkeypatch.setattr(M, "_gh", _fake_gh(False))
    m = M.from_gh(f"{N}/big-monorepo")
    assert m["files_complete"] is True
    ops, logs = labels.plan(m["labels"], None, files=m["files"], complete=True, defaults=CLEAN)
    assert _renames(ops) == {"bug": "type:bug"} and HOLD not in logs


def test_unmarked_file_list_is_not_complete():
    assert O._captured_files({"files": ["README.md"]})[1] is False
    assert O._captured_files({"files": ["README.md"], "files_complete": False})[1] is False
    assert O._captured_files({"files": ["README.md"], "files_complete": True})[1] is True
    ops, logs = labels.plan(LIVE, files=["README.md"], defaults=CLEAN)  # a list with no completeness marker
    assert _renames(ops) == {} and HOLD in logs


@pytest.fixture
def labs_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][L] = dict(raw["orgs"][N], display_name="Northwind Labs", nav_name="Northwind Labs", eyebrow="LABS")
    raw["owners"] = dict(raw["owners"], excluded=list(raw["owners"]["excluded"]) + ["Northwind-Departed"])
    return Brand(raw, brand.path)


def _estate(labs_brand, favorites=(), placeholders=None):
    reg = load_yaml_text((FIX / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"][N]["favorites"] = list(reg["orgs"][N]["favorites"]) + [{"full_name": f} for f in favorites]
    if placeholders:
        reg["placeholders"] = placeholders
    est = O.Estate(labs_brand, Resolver(labs_brand, reg, {"rows": set(), "ids": set(), "answers": {}, "extra": [],
                                                          "actions": []}))
    O.load_metas(FIX / "meta", est)
    return est


def test_truncated_dot_github_capture_reads_unlisted_files_as_unknown(labs_brand):
    est = _estate(labs_brand)
    raw = json.loads((FIX / "meta" / f"{N}__.github.json").read_text(encoding="utf-8"))
    raw.update(files=["CONTRIBUTING.md", "LICENSE", "README.md", "profile/README.md"], files_complete=False,
               visibility="public")
    est.add_meta(raw)
    res, _ = O.health(est, N)
    assert res["cells"]["SECURITY.md"] == "unknown" and "SECURITY.md" not in res["add"]
    est.meta(GH)["files_complete"] = True  # the whole tree: an unlisted file is missing
    res, _ = O.health(est, N)
    assert res["cells"]["SECURITY.md"] == "missing" and "SECURITY.md" in res["add"]


# ---------------------------------------------------------------------------------- the owner's .github forms
def test_org_labels_reads_the_org_default_forms(labs_brand):
    est = _estate(labs_brand)
    full = f"{N}/support-triage-agent"
    est.meta(full).update(files=["README.md", "src/app.py"], files_complete=True)  # no forms of its own
    est.meta(GH).update(files=["profile/README.md", ".github/ISSUE_TEMPLATE/bug.yml"], files_complete=True)
    res, code = O.labels_plan(est, N)
    by = {r["repo"]: r for r in res["repos"]}
    argvs = [j.get("argv") or [] for j in res["jobs"] if j.get("repo") == full]
    assert not any(a[:3] == ["gh", "label", "edit"] and "--name" in a for a in argvs), argvs
    assert by[full]["needs_checkout"][0]["check_files"] == [f"{GH}:.github/ISSUE_TEMPLATE/bug.yml"]
    assert HOLD in res["logs"]
    # no capture of the org's .github at all: held too, naming where its default forms may live
    del est.metas[GH.lower()]
    res, _ = O.labels_plan(est, N)
    by = {r["repo"]: r for r in res["repos"]}
    assert by[full]["needs_checkout"][0]["check_files"] == [f"{GH}:{p}" for p in labels.DEFAULT_PATTERNS]
    # a whole .github tree with no default form proves rule 0 has nothing to find there
    est.add_meta({"owner": N, "repo": ".github", "visibility": "public", "files": ["profile/README.md"],
                  "files_complete": True})
    res, _ = O.labels_plan(est, N)
    first = next(j for j in res["jobs"] if j.get("repo") == full)
    assert first["argv"][:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"]


def test_own_forms_override_the_org_defaults(tmp_path):
    repo = _write(tmp_path / "repo", {".github/ISSUE_TEMPLATE/config.yml": "blank_issues_enabled: false\n"})
    ops, _ = labels.plan(LIVE, repo)  # the org's .github is unknown, but GitHub ignores it here
    assert _renames(ops) == {"bug": "type:bug"}


def test_default_form_in_the_org_checkout_holds_the_rename(tmp_path):
    repo = _write(tmp_path / "repo", {"src/app.py": "print(1)\n"})
    gh = _write(tmp_path / "dot-github", {".github/ISSUE_TEMPLATE/bug_report.yml": "name: Bug\nlabels: [bug]\n"})
    ops, logs = labels.plan(LIVE, repo, defaults=labels.defaults_source(GH, repo_dir=gh))
    held = next(o for o in ops if o["name"] == "bug")
    assert held["op"] == "skip" and held["log"] == "label-rewrite-first"
    assert held["rewrite_references"] == [{"repo": GH, "path": ".github/ISSUE_TEMPLATE/bug_report.yml", "line": 2,
                                           "text": "labels: [bug]"}]
    # without the org checkout the rename is held, never emitted bare
    ops, logs = labels.plan(LIVE, repo)
    assert _renames(ops) == {} and HOLD in logs
    # once the org form is rewritten, the rename leaves
    (gh / ".github/ISSUE_TEMPLATE/bug_report.yml").write_text("name: Bug\nlabels: [type:bug]\n")
    ops, _ = labels.plan(LIVE, repo, defaults=labels.defaults_source(GH, repo_dir=gh))
    assert _renames(ops) == {"bug": "type:bug"}


def test_labels_and_adopt_cli_take_the_org_defaults(tmp_path):
    repo = _write(tmp_path / "repo", {"src/app.py": "print(1)\n"})
    gh = _write(tmp_path / "dot-github", {"ISSUE_TEMPLATE/bug.md": "---\nname: Bug\nlabels: bug\n---\nText\n"})
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(labels=LIVE)))
    p = run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan", "--org-defaults", gh)
    out = json.loads(p.stdout)
    assert out["argv"] == [] or not any(a[:4] == ["gh", "label", "edit", "bug"] for a in out["argv"])
    assert out["rewrite_first"][0]["repo"] == GH and out["rewrite_first"][0]["path"] == "ISSUE_TEMPLATE/bug.md"
    assert f"{GH}:ISSUE_TEMPLATE/bug.md" in p.stderr
    p = run_cli("--meta", m, "--repo-dir", repo, "adopt", f"{N}/support-triage-agent", "--org-defaults", gh)
    argvs = [j.get("argv") or [] for j in json.loads(p.stdout)["jobs"]]
    assert not any(a[:4] == ["gh", "label", "edit", "bug"] for a in argvs), argvs
    # the org's metadata JSON works too
    ghm = tmp_path / "dot-github.json"
    ghm.write_text(json.dumps({"owner": N, "repo": ".github", "files": ["README.md"], "files_complete": True}))
    out = json.loads(run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan",
                             "--org-defaults", ghm).stdout)
    assert any(a[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for a in out["argv"])
    # a metadata JSON of another repository is refused
    ghm.write_text(json.dumps({"owner": N, "repo": "order-ledger", "files": []}))
    assert run_cli("--meta", m, "--repo-dir", repo, "labels", "--plan", "--org-defaults", ghm).returncode == 2


# ------------------------------------------------------------------------------------------ YAML-aware forms
@pytest.mark.parametrize("rel,text", [
    (".github/ISSUE_TEMPLATE/bug.yml", "name: Bug\nlabels: [\n  bug,\n  triage\n]\nbody: []\n"),
    (".github/ISSUE_TEMPLATE/bug.yml", "﻿labels: [bug]\nname: Bug\n"),
    (".github/ISSUE_TEMPLATE/bug.md", "﻿---\nname: Bug\nlabels: bug\n---\nbody\n"),
    (".github/ISSUE_TEMPLATE/bug.yml", 'name: Bug\nlabels:\n  ["bug"]\n'),
    (".github/ISSUE_TEMPLATE/bug.yml", "x: &l [Bug]\nlabels: *l\n"),
    (".github/dependabot.yml", 'version: 2\nupdates:\n  - package-ecosystem: npm\n    directory: /\n    "labels": ["bug"]\n'),
    (".github/ISSUE_TEMPLATE/bug.yml", "name: Bug\nlabels: [bug\nbody: {\n"),  # unparseable: fails closed
])
def test_parsed_label_assignments_hold_the_rename(tmp_path, rel, text):
    repo = _write(tmp_path / "repo", {rel: text})
    ops, logs = labels.plan(LIVE, repo, defaults=CLEAN)
    held = next(o for o in ops if o["name"] == "bug")
    assert held["op"] == "skip" and held["log"] == "label-rewrite-first", held
    assert held["rewrite_references"] and all(h["path"] == rel for h in held["rewrite_references"])


def test_parsed_form_without_the_label_still_renames(tmp_path):
    form = 'name: Bug\n"labels": [type:bug]\nbody:\n  - type: textarea\n    attributes:\n      label: Describe the bug\n'
    repo = _write(tmp_path / "repo", {".github/ISSUE_TEMPLATE/bug.yml": "﻿" + form})
    ops, logs = labels.plan(LIVE, repo, defaults=CLEAN)
    assert _renames(ops) == {"bug": "type:bug"} and "label-rewrite-first" not in logs


# ------------------------------------------------------------------------------------------------ favorites
@pytest.mark.parametrize("slug", ["Northwind-Departed/secret-tool", "Northwind-Attic/hidden-tool",
                                  "someone-else/private-fork"])
def test_private_favorite_is_never_named(labs_brand, slug):
    est = _estate(labs_brand, [slug], placeholders=[{"login": "Northwind-Attic", "successor": L}])
    owner, repo = slug.split("/")
    est.add_meta({"owner": owner, "repo": repo, "visibility": "private", "description": "Internal."})
    data, logs = O.public_slice(est, N)
    assert slug not in data["favorites"] and "favorite-dropped:private-or-unknown" in logs
    res, code = O.profile(est, N)
    assert slug not in res["readme"] and slug not in json.dumps(res["data"]) and res["leaks"] == []
    assert slug in O._private_names(est, N, data)  # the leak check would catch it
    lists = json.loads((FIX / "star-lists-existing.json").read_text(encoding="utf-8"))
    plan, _ = O.pins(est, N, lists_capture=lists)
    assert slug not in json.dumps(plan)


def test_excluded_owner_favorite_without_metadata_is_dropped_not_pending(labs_brand):
    est = _estate(labs_brand, ["Northwind-Departed/other-tool"])
    data, logs = O.public_slice(est, N)
    assert "Northwind-Departed/other-tool" not in data["favorites"]
    assert "favorite-dropped:private-or-unknown" in logs and not any("favorite-visibility" in x for x in logs)


def test_outside_favorite_without_metadata_is_listed(labs_brand):
    data, _ = O.public_slice(_estate(labs_brand), N)
    assert "pallets/flask" in data["favorites"]


# ----------------------------------------------------------------------------------------- content icon hold
def test_content_icon_refuses_a_family_on_hold(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner="TouchedByAnAgent", repo="demo-tool")))
    cf = ROOT / "tests" / "fixtures" / "content"
    flags = ["--art-direction", cf / "ART_DIRECTION.min.md", "--registry", cf / "registry.min.yaml", "--approved",
             cf / "approved.empty.txt", "--approved-yaml", cf / "approved.empty.yaml", "--actions", cf / "estate-actions.json"]
    p = run_cli("--meta", meta, "--no-repo-dir", "content", "icon", "prompt", *flags)
    assert p.returncode == 2 and "hold" in json.loads(p.stdout)["logs"]
    p = run_cli("--meta", meta, "--no-repo-dir", "content", "icon", "prompt", "--allow-hold", *flags)
    assert p.returncode == 1 and json.loads(p.stdout)["result"] == "needs-writer"
