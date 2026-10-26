"""Review sweep (cross-group hand-offs) regressions. Synthetic Northwind data and brand.yaml's public rows only.

- `labels --plan` and `adopt` read an `--org-defaults` capture through the run's own resolver (`--config`), so a
  former login of the owner is the owner.
- `content social --job` renders the footer with the resolver `content social` was given, so an approved rename that
  only the approvals files record still gets its upload job.
- `footer --check` fails `fail:duplicate` when an old footer-like block is kept beside the decision 18 footer.
- `RepoContext.readme_text` drops a UTF-8 BOM like readme.py does.
- `fingerprint` reads the override `icon:` as YAML, so a trailing comment does not hide the icon.
- The watching org's `.github` gets the footer (readme, lint readme); `content icon` holds a watching-org non-fork.
- `adopt` refuses a family on hold even when called directly; label and project text/status job ids follow their
  content, so a re-plan never queues one id with other content.
- `describe` P1 matches Pick-Your-AI in any case.
"""
import copy
import hashlib
import json
import re

import pytest
import yaml

from conftest import ROOT, meta_dict, run_cli
from ctshowcase import describe, footer, intake, readme, readmelint
from ctshowcase import fingerprint as fp
from ctshowcase import org as O
from ctshowcase import project as PJ
from ctshowcase.config import Brand, load_yaml_text
from ctshowcase.context import RepoContext
from ctshowcase.errors import Refused
from ctshowcase.meta import normalize
from ctshowcase.resolver import Resolver

N, L, OLD = "Northwind-Trading-Co", "Northwind-Labs", "Northwind-Old"
W = "romgenie-following-repos"
LIVE = [{"name": "bug", "color": "d73a4a", "description": "Something isn't working"}]
OFIX = ROOT / "tests" / "fixtures" / "org"
PFIX = ROOT / "tests" / "fixtures" / "project"
CFIX = ROOT / "tests" / "fixtures" / "content"
MFIX = ROOT / "tests" / "fixtures" / "meta"
HEX8 = "[0-9a-f]{8}"


def approvals(rows=(), ids=(), actions=()):
    return {"rows": set(rows), "ids": set(ids), "answers": {}, "actions": list(actions), "extra": []}


def _config_former(tmp_path):
    raw = yaml.safe_load((ROOT / "references" / "brand.yaml").read_text(encoding="utf-8"))
    raw["orgs"][N]["former_slugs"] = [OLD]
    p = tmp_path / "brand-former.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


def _repo(tmp_path, labels=LIVE):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print(1)\n")
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(labels=labels)))
    return repo, m


# ------------------------------------------------------------------------------- rule 0 under the run's resolver
def test_org_defaults_under_a_former_login_follow_the_config(tmp_path):
    repo, m = _repo(tmp_path)
    cfg = _config_former(tmp_path)
    ghm = tmp_path / "dot-github.json"
    ghm.write_text(json.dumps({"owner": OLD, "repo": ".github", "files": ["README.md"], "files_complete": True}))
    p = run_cli("--format", "json", "--config", cfg, "--meta", m, "--repo-dir", repo, "labels", "--plan",
                "--org-defaults", ghm)
    assert p.returncode != 2, p.stdout + p.stderr
    assert any(a[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for a in json.loads(p.stdout)["argv"])
    p = run_cli("--format", "json", "--config", cfg, "--meta", m, "--repo-dir", repo, "adopt", f"{N}/support-triage-agent",
                "--org-defaults", ghm)
    assert p.returncode != 2, p.stdout + p.stderr
    # another org is still refused
    ghm.write_text(json.dumps({"owner": L, "repo": ".github", "files": ["README.md"], "files_complete": True}))
    assert run_cli("--config", cfg, "--meta", m, "--repo-dir", repo, "labels", "--plan", "--org-defaults",
                   ghm).returncode == 2


# ------------------------------------------------------------------------------- social preview after a rename
def test_content_social_job_is_emitted_once_the_image_names_the_current_login(tmp_path):
    appr = tmp_path / "approved.yaml"
    appr.write_text("items:\n  - id: org-001\n    approved: true\n")
    p = run_cli("--format", "json", "--meta", MFIX / "CompleTetech-Security__php2shell-check.json", "--no-repo-dir",
                "content", "social", "--out", tmp_path / "sp.png", "--registry", CFIX / "registry.min.yaml", "--approved",
                CFIX / "approved.empty.txt", "--approved-yaml", appr, "--actions", CFIX / "estate-actions.json", "--job")
    res = json.loads(p.stdout)
    assert res.get("job") and res["footer"] == "github.com/" + res["job"]["repo"], res
    assert "needs-input:social-login" not in res["logs"]


# ------------------------------------------------------------------------------- footer --check duplicate
def test_footer_check_flags_an_old_footer_kept_beside_the_decision_18_one(brand):
    old = '<p align="center">\n  Built by <a href="https://complete.tech">CompleteTech LLC</a>\n</p>'
    text = f"# x\n\nSome text.\n\n{old}\n\n{footer.block(brand)}\n"
    assert footer.check(brand, text)[0] == "fail:duplicate"
    # an example in fenced code is not a footer, and a single footer passes
    example = f"# x\n\n```html\n{old}\n```\n\n{footer.block(brand)}\n"
    assert footer.check(brand, example)[0] == "pass"
    assert footer.check(brand, f"# x\n\nSome text.\n\n{footer.block(brand)}\n")[0] == "pass"


# ------------------------------------------------------------------------------- BOM
def test_readme_text_drops_a_bom(brand, tmp_path):
    (tmp_path / "README.md").write_text("﻿# support-triage-agent\n\nText.\n", encoding="utf-8")
    ctx = RepoContext(brand, normalize(meta_dict()), tmp_path)
    assert ctx.readme_text().startswith("# support-triage-agent")
    ctx = RepoContext(brand, normalize(meta_dict(readme_head="﻿# support-triage-agent\n")), None)
    assert ctx.readme_text().startswith("# support-triage-agent")


# ------------------------------------------------------------------------------- fingerprint override icon
def test_fingerprint_reads_an_override_icon_with_a_trailing_comment(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "showcase.yml").write_text("icon: assets/brand/mark.png  # the product mark\n",
                                                        encoding="utf-8")
    mark = tmp_path / "assets" / "brand" / "mark.png"
    mark.parent.mkdir(parents=True)
    mark.write_bytes(b"\x89PNG mark one")
    meta = meta_dict()
    first = fp.inputs(meta, tmp_path)["icon_sha256"]
    assert first == hashlib.sha256(b"\x89PNG mark one").hexdigest()
    mark.write_bytes(b"\x89PNG mark two")
    assert fp.inputs(meta, tmp_path)["icon_sha256"] not in (None, first)
    for text in ('icon: "assets/brand/mark.png" # quoted', "'icon': 'assets/brand/mark.png'"):
        assert fp.override_icon(text) == "assets/brand/mark.png"
    assert fp.override_icon("icon: null") is None and fp.override_icon("title: x") is None


# ------------------------------------------------------------------------------- watching org
def test_watching_dot_github_readme_and_lint_want_the_footer(brand, tmp_path):
    ctx = RepoContext(brand, normalize(meta_dict(owner=W, repo=".github")), None)
    assert readme.footer_wanted(ctx) is True
    held = RepoContext(brand, normalize(meta_dict(owner=W, repo="northwind-notes-kit")), None)
    assert readme.footer_wanted(held) is False and "hold:watching-non-fork" in held.logs
    fork = RepoContext(brand, normalize(meta_dict(owner=W, repo="northwind-agent-kit", fork=True)), None)
    assert readme.footer_wanted(fork) is False and "exempt:footer" in fork.logs
    (tmp_path / "README.md").write_text("# .github\n\nThe org's community files.\n", encoding="utf-8")
    res = readmelint.lint(RepoContext(brand, normalize(meta_dict(owner=W, repo=".github")), tmp_path),
                          tmp_path / "README.md")
    assert any(f.startswith("D18 footer") for f in res["fails"]), res["fails"]


def test_content_icon_holds_a_watching_org_non_fork(tmp_path):
    def run(**kw):
        m = tmp_path / "w.json"
        m.write_text(json.dumps(meta_dict(owner=W, **kw)))
        return run_cli("--format", "json", "--no-repo-dir", "--meta", m, "content", "icon", "prompt",
                       "--out", tmp_path / "p.md")
    p = run(repo="northwind-notes-kit")
    assert p.returncode == 2 and "hold:watching-non-fork" in p.stdout, p.stdout
    p = run(repo="northwind-agent-kit", fork=True)
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "exempt"


# ------------------------------------------------------------------------------- adopt: family on hold
def test_adopt_refuses_a_family_on_hold_when_called_directly(brand):
    ctx = RepoContext(brand, normalize(meta_dict(owner="TouchedByAnAgent", repo="northwind-notes", labels=LIVE)), None)
    assert ctx.style.get("hold")
    with pytest.raises(Refused) as e:
        intake.adopt(ctx, Resolver(brand, {}, approvals()))
    assert e.value.log == "hold"


# ------------------------------------------------------------------------------- content-derived job ids
def _same_id_same_content(a, b):
    by = {j["id"]: j for j in a}
    return all(j["id"] not in by or by[j["id"]].get("argv") == j.get("argv") for j in b)


def test_adopt_label_job_ids_follow_the_operation(brand):
    def plan(labels):
        ctx = RepoContext(brand, normalize(meta_dict(labels=labels, files=["README.md"], files_complete=True)), None)
        return [j for j in intake.adopt(ctx, Resolver(brand, {}, approvals()))["jobs"] if j["kind"] == "labels"]
    a, again = plan(LIVE), plan(LIVE)
    assert a and [j["id"] for j in a] == [j["id"] for j in again]
    assert all(re.search(f"label:[^:]+:(create|edit):.+:{HEX8}$", j["id"]) for j in a), [j["id"] for j in a]
    b = plan([{"name": "type:bug", "color": "000000", "description": ""}, *LIVE])
    assert _same_id_same_content(a, b)


@pytest.fixture
def labs_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][L] = dict(raw["orgs"][N], display_name="Northwind Labs", nav_name="Northwind Labs", eyebrow="LABS")
    return Brand(raw, brand.path)


def test_org_label_job_ids_follow_the_operation(labs_brand):
    def plan(first=None):
        reg = load_yaml_text((OFIX / "registry.yaml").read_text(encoding="utf-8"))
        est = O.Estate(labs_brand, Resolver(labs_brand, reg, approvals()))
        O.load_metas(OFIX / "meta", est)
        full = f"{N}/support-triage-agent"
        est.meta(full).update(files=["README.md"], files_complete=True)
        est.meta(f"{N}/.github").update(files=["README.md", "profile/README.md"], files_complete=True)
        if first:
            est.meta(full)["labels"] = [first, *est.meta(full)["labels"]]
        return [j for j in O.labels_plan(est, N)[0]["jobs"] if j.get("kind") == "labels"]
    a = plan()
    assert a and [j["id"] for j in a] == [j["id"] for j in plan()]
    assert all(re.search(f"-label-(create|edit)-.+-{HEX8}$", j["id"]) for j in a), [j["id"] for j in a]
    assert _same_id_same_content(a, plan({"name": "type:bug", "color": "000000", "description": ""}))


def test_copy_plan_text_id_changes_with_its_content(brand):
    res = Resolver(brand, {}, approvals())
    first = json.loads((PFIX / "copy-capture.json").read_text(encoding="utf-8"))
    later = copy.deepcopy(first)
    nodes = later["data"]["organization"]["projectV2"]["views"]["nodes"]
    for i, name in ((6, "My items"), (7, "Shipped")):  # re-captured after the view jobs ran
        nodes.append(dict(nodes[-1], id=f"PVTV_n{i}", number=i, name=name, filter=""))
    a = PJ.copy_plan(N, copied=first, resolver=res, reviewed="2026-10-25")["jobs"]
    b = PJ.copy_plan(N, copied=later, resolver=res, reviewed="2026-10-25")["jobs"]
    again = PJ.copy_plan(N, copied=first, resolver=res, reviewed="2026-10-25")["jobs"]
    assert [j["id"] for j in a] == [j["id"] for j in again]
    ia = [j["id"] for j in a if re.search(f"-text-{HEX8}$", j["id"])]
    ib = [j["id"] for j in b if re.search(f"-text-{HEX8}$", j["id"])]
    assert len(ia) == len(ib) == 1 and ia != ib, (ia, ib)
    assert any("--readme" in (j.get("argv") or []) for j in b)
    # the first status update waits for the Shipped view: none in the first plan, one in the re-plan
    assert not any("-status-1" in j["id"] for j in a) and len([j for j in b if "-status-1-" in j["id"]]) == 1


# ------------------------------------------------------------------------------- describe P1
def test_describe_p1_matches_pick_your_ai_in_any_case():
    text = "Demo Board: compare answers from several models side by side."
    for owner in ("Pick-Your-AI", "pick-your-ai"):
        rows = describe.checks(text, slug="demo-board", type_="web-app", has_brand_assets=None, owner=owner)
        assert next(r for r in rows if r["rule"] == "P1")["result"] == "pass", (owner, rows)
