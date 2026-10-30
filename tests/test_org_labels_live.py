"""Registry-free org label planning uses only synthetic GitHub GET responses."""
import json
import subprocess

import pytest

from ctshowcase import org as O
from ctshowcase import labels as L
from ctshowcase.errors import ShowcaseError
from ctshowcase.resolver import Resolver

N = "Northwind-Trading-Co"


def listing(name, **extra):
    return {"name": name, "full_name": f"{N}/{name}", "owner": {"login": N},
            "private": False, "has_issues": True, "default_branch": "main", **extra}


def fake_api(monkeypatch, pages, *, forms=False, empty_labels=False):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert argv[:4] == ["gh", "api", "-X", "GET"]
        assert kwargs["encoding"] == "utf-8"
        endpoint = argv[4]
        if endpoint.startswith("orgs/"):
            assert "--paginate" in argv and "--slurp" in argv
            value = pages
        elif "/labels?" in endpoint:
            assert "--paginate" in argv and "--slurp" in argv
            value = [[]] if empty_labels else [[{"name": "bug", "color": "ff0000", "description": "old"}]]
        else:
            value = {"tree": [{"path": ".github/ISSUE_TEMPLATE/bug.yml" if forms else "README.md", "type": "blob"}],
                     "truncated": False}
        return subprocess.CompletedProcess(argv, 0, json.dumps(value), "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_live_discovers_every_page_and_only_emits_writer_jobs(brand, monkeypatch):
    calls = fake_api(monkeypatch, [[listing(".github"), listing("one")], [listing("two")]])
    estate = O.Estate(brand, Resolver(brand))
    O.capture_label_repos(estate, N)
    result, code = O.labels_plan(estate, N, registry_free=True)
    assert code == 0
    assert {r["repo"] for r in result["repos"]} == {f"{N}/{n}" for n in (".github", "one", "two")}
    assert all("--force" not in j.get("argv", []) and "delete" not in j.get("argv", []) for j in result["jobs"])
    assert all({"id", "phase", "kind", "repo", "argv", "note"} <= j.keys() for j in result["jobs"] if j["kind"] == "labels")
    assert len(calls) == 7


def test_live_skips_archived_forks_and_disabled_issues(brand, monkeypatch):
    fake_api(monkeypatch, [[listing(".github", has_issues=False), listing("old", archived=True),
                            listing("copy-fork"), listing("no-issues", has_issues=False)]])
    estate = O.Estate(brand, Resolver(brand))
    O.capture_label_repos(estate, N)
    result, _ = O.labels_plan(estate, N, registry_free=True)
    rows = {r["repo"].split("/")[-1]: r for r in result["repos"]}
    assert rows["old"]["log"] == "archived"
    assert rows["copy-fork"]["log"] == "fork"
    assert rows["no-issues"]["log"] == "has_issues:false"
    assert rows[".github"]["result"] == "plan"


def test_live_forms_hold_renames(brand, monkeypatch):
    fake_api(monkeypatch, [[listing(".github"), listing("one")]], forms=True)
    estate = O.Estate(brand, Resolver(brand))
    O.capture_label_repos(estate, N)
    result, _ = O.labels_plan(estate, N, registry_free=True)
    assert all(r.get("needs_checkout") for r in result["repos"])
    assert not any("--name" in j.get("argv", []) for j in result["jobs"])


def test_live_empty_labels_are_known_empty(brand, monkeypatch):
    fake_api(monkeypatch, [[listing("one")]], empty_labels=True)
    estate = O.Estate(brand, Resolver(brand))
    O.capture_label_repos(estate, N)
    result, _ = O.labels_plan(estate, N, registry_free=True)
    assert result["repos"][0]["result"] == "plan"
    assert sum(j["kind"] == "labels" for j in result["jobs"]) == 23


def test_live_canonicalizes_former_org_login(brand, monkeypatch):
    old = "CompleTetech-Security"
    new = "CompleteTech-Security"
    calls = fake_api(monkeypatch, [[]])
    estate = O.Estate(brand, Resolver(brand))
    O.capture_label_repos(estate, old)
    assert calls[0][4].startswith(f"orgs/{new}/repos?")


@pytest.mark.parametrize("pages", [[[listing("wrong", owner={"login": "Other"})]], [{"not": "a page"}]])
def test_live_rejects_untrusted_or_malformed_listing(brand, monkeypatch, pages):
    fake_api(monkeypatch, pages)
    with pytest.raises(ShowcaseError):
        O.capture_label_repos(O.Estate(brand, Resolver(brand)), N)


def test_cli_without_registry_writes_only_local_job_file(monkeypatch, tmp_path, capsys):
    import showcase
    fake_api(monkeypatch, [[listing(".github"), listing("one")]])
    monkeypatch.setattr(O, "load_flags", lambda *_: pytest.fail("live mode must not read estate flags"))
    jobs = tmp_path / "jobs.jsonl"
    assert showcase.main(["org", "labels", N, "--repos-from-gh", "--jobs", str(jobs)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"] == "plan"
    assert [json.loads(line) for line in jobs.read_text(encoding="utf-8").splitlines()] == result["jobs"]


def test_live_references_release_only_after_local_forms_are_rewritten(brand, monkeypatch, tmp_path):
    fake_api(monkeypatch, [[listing(".github"), listing("one")]], forms=True)
    estate = O.Estate(brand, Resolver(brand))
    O.capture_label_repos(estate, N)
    gh = tmp_path / N / ".github"
    repo = tmp_path / N / "one"
    gh.mkdir(parents=True)
    repo.mkdir()
    form = gh / ".github" / "ISSUE_TEMPLATE" / "bug.yml"
    form.parent.mkdir(parents=True)
    form.write_text("name: Bug\nlabels: [bug]\n", encoding="utf-8")
    monkeypatch.setattr(L, "_checkout_origin", lambda p: (N, p.name))
    held, _ = O.labels_plan(estate, N, registry_free=True, checkouts=str(tmp_path), dot_github=str(gh))
    assert not any("--name" in j.get("argv", []) for j in held["jobs"])
    form.write_text("name: Bug\nlabels: ['type:bug']\n", encoding="utf-8")
    released, _ = O.labels_plan(estate, N, registry_free=True, checkouts=str(tmp_path), dot_github=str(gh))
    renamed = [j for j in released["jobs"] if "--name" in j.get("argv", [])]
    assert {j["repo"] for j in renamed} == {f"{N}/.github", f"{N}/one"}
    assert renamed[0]["repo"] == f"{N}/.github"
    monkeypatch.setattr(L, "_checkout_origin", lambda p: ("Other", p.name))
    with pytest.raises(ShowcaseError, match="not .*github"):
        O.labels_plan(estate, N, registry_free=True, checkouts=str(tmp_path), dot_github=str(gh))


def test_failed_paginated_read_never_becomes_empty_success(brand, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "no access"))
    with pytest.raises(ShowcaseError, match="check GitHub access"):
        O.capture_label_repos(O.Estate(brand, Resolver(brand)), N)


def test_registry_mode_still_requires_the_org_row(brand):
    estate = O.Estate(brand, Resolver(brand, {"orgs": {}}), {
        "one": dict(listing("one"), labels=[{"name": "bug", "color": "ff0000"}], files=[], files_complete=True),
    })
    with pytest.raises(ShowcaseError, match="no row in registry"):
        O.labels_plan(estate, N)


@pytest.mark.parametrize("origin_name,valid", [("widget", True), ("OtherWidget", False)])
def test_member_checkout_origin_uses_github_case_rules(brand, tmp_path, origin_name, valid):
    repo = tmp_path / N / "Widget"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    f"https://github.com/{N}/{origin_name}.git"], check=True, capture_output=True)
    estate = O.Estate(brand, Resolver(brand, {"orgs": {N: {}}}), {
        "Widget": dict(listing("Widget"), labels=[{"name": "bug", "color": "ff0000"}], files=[], files_complete=True),
    })
    if valid:
        result, _ = O.labels_plan(estate, N, checkouts=str(tmp_path))
        assert result["repos"][0]["repo"] == f"{N}/Widget"
        assert result["repos"][0]["result"] == "plan"
    else:
        with pytest.raises(ShowcaseError, match="matching GitHub origin"):
            O.labels_plan(estate, N, checkouts=str(tmp_path))
