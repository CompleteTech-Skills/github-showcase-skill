"""Review corrections: synthetic response identities, rollback, stale data and scratch paths.

Publication/optional-render checks retain applicable controls from the comparison candidate;
all capture and browser transports are mocked, with no live account data or service access.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest
import showcase
from conftest import run_cli

from ctshowcase import account as A
from ctshowcase import chart as C
from ctshowcase.config import load_brand


def connection(nodes=(), more=False):
    return {"nodes": list(nodes), "pageInfo": {"hasNextPage": more, "endCursor": "synthetic-next" if more else None}}


def query_response(name, variables):
    def owner(login, repo):
        return {"login": login, "repositories": connection([{"name": repo}]),
                "all": {"totalCount": 1}, "public": {"totalCount": 1}}
    if name == "account_viewer":
        return {"viewer": {"login": "northwind-dev"}}
    if name == "account_user":
        return {"user": owner(variables["login"], "synthetic-personal")}
    if name == "account_orgs":
        return {"user": {"organizations": connection([{"login": "Northwind-Labs"}])}}
    if name == "account_enterprises":
        return {"viewer": {"enterprises": connection([{"slug": "northwind-enterprise"}])}}
    if name == "account_enterprise_orgs":
        return {"enterprise": {"organizations": connection([])}}
    if name == "account_org":
        return {"organization": owner(variables["org"], "synthetic-org")}
    raise AssertionError(name)


SOURCES = {
    "account_user": ("user", "login", "repositories", "northwind-dev"),
    "account_org": ("organization", "login", "repositories", "Northwind-Labs"),
    "account_orgs": ("user", "login", "organizations", "northwind-dev"),
    "account_enterprises": ("viewer", "login", "enterprises", "northwind-dev"),
    "account_enterprise_orgs": ("enterprise", "slug", "organizations", "northwind-enterprise"),
}


def invoke(capsys, *args):
    code = showcase.main(list(map(str, args)))
    return code, json.loads(capsys.readouterr().out)


def capture_with_response(tmp_path, monkeypatch, capsys, query, continuation, actual, *, registry=None, missing=False):
    dest = tmp_path / "capture.json"
    dest.write_bytes(b"Synthetic original capture\r\n")
    calls = []
    entity, field, conn, _ = SOURCES[query]

    def run(name, **variables):
        calls.append((name, variables))
        data = query_response(name, variables)
        if name == query:
            node = data[entity]
            if continuation and not variables.get("after"):
                node[conn]["pageInfo"] = connection(more=True)["pageInfo"]
            else:
                if missing:
                    node.pop(field, None)
                else:
                    node[field] = actual
                if conn == "repositories":
                    node[conn]["nodes"] = [{"name": "synthetic-untrusted-page"}]
        return data

    monkeypatch.setattr(A, "_gh", run)
    extra = ["--registry", registry] if registry else []
    code, result = invoke(capsys, "account-chart", "capture", "northwind-dev", "--out", dest, *extra)
    return code, result, dest, calls


@pytest.mark.parametrize("query", list(SOURCES))
@pytest.mark.parametrize("continuation", [False, True])
@pytest.mark.parametrize("actual", ["BunsDev", "TouchedByAnAgent", "Pick-Your-AI", "Northwind-Unrelated"])
def test_each_page_rejects_cross_source_identity_without_publishing(tmp_path, monkeypatch, capsys,
                                                                    query, continuation, actual):
    code, result, dest, calls = capture_with_response(tmp_path, monkeypatch, capsys, query, continuation, actual)
    assert code == 2 and result["logs"] == ["usage:capture-identity"]
    assert dest.read_bytes() == b"Synthetic original capture\r\n"
    assert actual not in json.dumps(result) and "synthetic-untrusted-page" not in json.dumps(result)
    assert len([name for name, _ in calls if name == query]) == (2 if continuation else 1)


@pytest.mark.parametrize("query", ["account_user", "account_org"])
@pytest.mark.parametrize("continuation", [False, True])
@pytest.mark.parametrize("actual", [None, "", False, "invalid login", "missing-field"])
def test_required_response_login_is_not_inferred_from_the_request(tmp_path, monkeypatch, capsys,
                                                                  query, continuation, actual):
    code, result, dest, _ = capture_with_response(tmp_path, monkeypatch, capsys, query, continuation, actual,
                                                 missing=actual == "missing-field")
    assert code == 2 and result["logs"] == ["usage:capture-identity"]
    assert dest.read_bytes() == b"Synthetic original capture\r\n"


@pytest.mark.parametrize("query", list(SOURCES))
@pytest.mark.parametrize("continuation", [False, True])
@pytest.mark.parametrize("spelling", ["same", "case"])
def test_matching_response_identity_preserves_success(tmp_path, monkeypatch, capsys, query, continuation, spelling):
    actual = SOURCES[query][3]
    if spelling == "case":
        actual = actual.swapcase()
    code, _, dest, _ = capture_with_response(tmp_path, monkeypatch, capsys, query, continuation, actual)
    assert code == 0
    assert A.load_snapshot(dest)["account"]["login"].casefold() == "northwind-dev"


@pytest.mark.parametrize("query", ["account_user", "account_org", "account_orgs", "account_enterprises"])
@pytest.mark.parametrize("continuation", [False, True])
def test_registered_owner_alias_is_accepted_on_each_page(tmp_path, monkeypatch, capsys, query, continuation):
    actual = "Northwind-Current"
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"orgs": {actual: {"former_slugs": [SOURCES[query][3]]}}}), encoding="utf-8")
    code, _, dest, _ = capture_with_response(tmp_path, monkeypatch, capsys, query, continuation, actual, registry=registry)
    assert code == 0 and A.load_snapshot(dest)["organizations"]


def snapshot(**overrides):
    return {"schema": A.SCHEMA, "captured": "2026-11-18", "account": {"login": "northwind-dev"},
            "repositories": [{"name": "synthetic-personal"}], "not_public": 0, "enterprises": [],
            "organizations": [{"login": "Northwind-Labs", "captured": True, "repositories": [],
                               "not_public": 0, **overrides}]}


def source(tmp_path, **overrides):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot(**overrides)), encoding="utf-8")
    return path


def render_args(path, out, *extra):
    return ["account-chart", "render", "--snapshot", str(path), "--out-dir", str(out),
            "--width", "1600", "--scale", "1", *map(str, extra)]


@pytest.mark.parametrize("failure", ["png", "commit"])
def test_generation_and_commit_failures_preserve_the_entire_output_set(tmp_path, monkeypatch, capsys, failure):
    src = source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    for suffix in ("mmd", "svg", "md", "png"):
        (out / f"account-chart.{suffix}").write_bytes(f"Previous {suffix}\r\n".encode())
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    if failure == "png":
        def fail_png(*args):
            raise OSError("synthetic encoding failure")
        monkeypatch.setattr(C, "png_image", fail_png)
    else:
        original = Path.replace

        def fail_commit(path, target):
            if path.name == "output" and Path(target).name == "account-chart.md":
                raise OSError("synthetic third-output commit failure")
            return original(path, target)
        monkeypatch.setattr(Path, "replace", fail_commit)
    code, _ = invoke(capsys, *render_args(src, out, *(["--no-png"] if failure == "commit" else [])))
    assert code == 2
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


def test_commit_failure_removes_new_outputs_as_well(tmp_path, monkeypatch, capsys):
    src = source(tmp_path)
    out = tmp_path / "out"
    original = Path.replace

    def fail_commit(path, target):
        if path.name == "output" and Path(target).name == "account-chart.md":
            raise OSError("synthetic third-output commit failure")
        return original(path, target)
    monkeypatch.setattr(Path, "replace", fail_commit)
    code, _ = invoke(capsys, *render_args(src, out, "--no-png"))
    assert code == 2 and list(out.iterdir()) == []


@pytest.mark.parametrize("action", ["capture", "render"])
def test_destination_edited_during_generation_is_preserved(tmp_path, monkeypatch, capsys, action):
    out = tmp_path / "out"
    out.mkdir()
    target = out / ("capture.json" if action == "capture" else "account-chart.md")
    target.write_bytes(b"Synthetic before")
    if action == "capture":
        def run(name, **variables):
            target.write_bytes(b"Synthetic concurrent edit")
            return query_response(name, variables)
        monkeypatch.setattr(A, "_gh", run)
        args = ["account-chart", "capture", "--out", target]
    else:
        original = C.svg
        def render(*args, **kwargs):
            target.write_bytes(b"Synthetic concurrent edit")
            return original(*args, **kwargs)
        monkeypatch.setattr(C, "svg", render)
        args = render_args(source(tmp_path), out, "--no-png")
    code, result = invoke(capsys, *args)
    assert code == 2 and result["logs"] == ["usage:account-chart-path"]
    assert target.read_bytes() == b"Synthetic concurrent edit"
    assert list(out.iterdir()) == [target]


@pytest.mark.parametrize("success", [False, True])
@pytest.mark.parametrize("symlinked_tmp", [False, True])
def test_optional_mmdc_uses_scratch_and_only_publishes_success(tmp_path, monkeypatch, capsys, success, symlinked_tmp):
    src = source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    mermaid = out / "account-chart.mermaid.png"
    mermaid.write_bytes(b"Previous optional render")
    if symlinked_tmp:
        actual = tmp_path / "real-temp"
        actual.mkdir()
        alias = tmp_path / "linked-temp"
        try:
            alias.symlink_to(actual, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")
        monkeypatch.setenv("TMPDIR", str(alias))
        monkeypatch.setattr(tempfile, "tempdir", str(alias))
    monkeypatch.setattr(A.shutil, "which", lambda _: "/synthetic/mmdc")

    def fake_run(cmd, **kwargs):
        target = Path(cmd[cmd.index("-o") + 1])
        assert target.parent != out and not (out / "account-chart.mmd").exists()
        assert mermaid.read_bytes() == b"Previous optional render"
        target.write_bytes(b"Synthetic browser output")
        return subprocess.CompletedProcess(cmd, 0 if success else 1, "", "")
    monkeypatch.setattr(A.subprocess, "run", fake_run)
    code, result = invoke(capsys, *render_args(src, out, "--no-png", "--mmdc"))
    assert code == 0
    assert mermaid.read_bytes() == (b"Synthetic browser output" if success else b"Previous optional render")
    assert str(mermaid) in result["outputs"] if success else str(mermaid) not in result["outputs"]


@pytest.mark.parametrize("status", ["uncaptured", "failed", "unknown"])
@pytest.mark.parametrize("scope", ["org", "personal"])
def test_unknown_inventory_never_repeats_stale_rows_or_counts(tmp_path, status, scope):
    data = snapshot()
    data["repositories"] = []
    target = data["organizations"][0] if scope == "org" else data
    target.update(repositories=[{"name": "synthetic-stale"}], not_public=19)
    if scope == "org":
        target.update(captured=False, capture_status=status)
    else:
        data["coverage"] = {"repositories": status}
    clean = A.validate(data)
    model, _ = A.build(clean, load_brand())
    node = model["orgs"][0] if scope == "org" else model["personal"]
    assert target["repositories"]  # the caller's original input is not mutated
    assert node["repos"] == [] and node["not_public"] is None and node["public"] is None
    assert model["counts"]["public"] == 0 and model["counts"]["not_public"] == 0
    src = tmp_path / "snapshot.json"
    src.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "out"
    result = run_cli(*render_args(src, out, "--no-png"))
    assert result.returncode == 0, result.stdout + result.stderr
    for suffix in ("md", "svg", "mmd"):
        assert "synthetic-stale" not in (out / f"account-chart.{suffix}").read_text(encoding="utf-8")


def test_partial_and_legacy_complete_evidence_remain_usable():
    for captured, state in ((False, "partial"), (True, "failed")):
        clean = A.validate(snapshot(captured=captured, capture_status=state,
                                    repositories=[{"name": "synthetic-observed"}], not_public=7))
        model, _ = A.build(clean, load_brand())
        node = model["orgs"][0]
        assert [r["name"] for r in node["repos"]] == ["synthetic-observed"]
        assert node["not_public"] == 7
        assert node["capture_status"] == ("complete" if captured else "partial")


@pytest.mark.parametrize("option", ["snapshot", "avatar", "mmdc-config", "registry", "approved", "approved-yaml",
                                   "actions", "decisions", "config", "t3-signoff-file", "mmdc"])
def test_all_named_source_aliases_keep_the_authored_output(tmp_path, option):
    from conftest import ROOT
    out = tmp_path / "out"
    out.mkdir()
    src = source(tmp_path)
    dest = out / "account-chart.md"
    dest.write_bytes(src.read_bytes() if option == "snapshot" else b"Synthetic input sentinel")
    extra, pre = [], []
    if option == "snapshot":
        src = dest
    elif option == "config":
        dest.write_bytes((ROOT / "references/brand.yaml").read_bytes())
        pre = ["--config", dest]
    elif option == "t3-signoff-file":
        pre = ["--t3-signoff-file", dest]
    else:
        extra = [f"--{option}", dest]
    before = dest.read_bytes()
    result = run_cli(*pre, *render_args(src, out, "--no-png", *extra))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["logs"] == ["usage:account-chart-path"]
    assert dest.read_bytes() == before
    assert sorted(p.name for p in out.iterdir()) == [dest.name]


def test_input_symlink_to_regular_destination_is_also_an_alias(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    dest = out / "account-chart.md"
    dest.write_text(json.dumps(snapshot()), encoding="utf-8")
    src = tmp_path / "capture.json"
    try:
        src.symlink_to(dest)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    before = dest.read_bytes()
    result = run_cli(*render_args(src, out, "--no-png"))
    assert result.returncode == 2 and dest.read_bytes() == before
    assert src.is_symlink() and list(out.iterdir()) == [dest]


def test_uncaptured_org_does_not_discard_other_observed_personal_data():
    data = snapshot(captured=False, repositories=[{"name": "synthetic-stale"}], not_public=10)
    model, _ = A.build(A.validate(data), load_brand())
    assert model["orgs"][0]["repos"] == [] and model["orgs"][0]["not_public"] is None
    assert model["counts"]["public"] == 1 and model["counts"]["not_public"] == 0


def test_enterprise_reference_without_org_capture_stays_unknown():
    data = snapshot()
    data["enterprises"] = [{"slug": "northwind-enterprise", "organizations": ["Northwind-Missing"]}]
    model, _ = A.build(A.validate(data), load_brand())
    org = model["enterprises"][0]["orgs"][0]
    assert org["login"] == "Northwind-Missing" and org["capture_status"] == "uncaptured"
    assert any("Northwind-Missing: not captured" in item for item in model["evidence"])
