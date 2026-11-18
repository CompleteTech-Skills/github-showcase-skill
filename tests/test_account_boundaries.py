"""Account output and consent regressions: real offline renders, synthetic mocked capture only."""
from __future__ import annotations

import functools
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import showcase
from conftest import ROOT, run_cli

from ctshowcase import account as A
from ctshowcase import chart as C
from ctshowcase.errors import Refused
from ctshowcase.resolver import Resolver


def snapshot(**org_overrides):
    return {"schema": A.SCHEMA, "captured": "2026-11-18", "account": {"login": "northwind-dev"},
            "repositories": [{"name": "synthetic-personal"}], "not_public": 0, "enterprises": [],
            "organizations": [{"login": "Northwind-Labs", "captured": True, "repositories": [],
                               "not_public": 0, **org_overrides}]}


def source(tmp_path, **overrides):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot(**overrides)), encoding="utf-8")
    return path


def render_args(path, out, *extra):
    return ["account-chart", "render", "--snapshot", str(path), "--out-dir", str(out),
            "--width", "1600", "--scale", "1", *map(str, extra)]


def invoke(capsys, *args):
    code = showcase.main(list(map(str, args)))
    return code, json.loads(capsys.readouterr().out)


def symlink(path, target, *, directory=False):
    try:
        path.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")


@pytest.mark.parametrize("suffix", ["mmd", "svg", "md", "png", "mermaid.png"])
def test_real_cli_rejects_every_output_symlink_before_any_write(tmp_path, suffix):
    src = source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    victim = tmp_path / "authored.txt"
    victim.write_bytes(b"Synthetic authored content\r\n")
    existing = out / "account-chart.mmd"
    if suffix != "mmd":
        existing.write_bytes(b"Existing generated source\r\n")
    link = out / f"account-chart.{suffix}"
    symlink(link, victim)
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    extra = ["--mmdc", "not-installed-mmdc"] if suffix == "mermaid.png" else []
    run = run_cli(*render_args(src, out, *extra))
    assert run.returncode == 2, run.stdout + run.stderr
    assert json.loads(run.stdout)["logs"] == ["account-chart:path"]
    assert victim.read_bytes() == b"Synthetic authored content\r\n"
    assert link.is_symlink()
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


@pytest.mark.parametrize("kind", ["ancestor", "dangling", "file-parent", "directory", "hardlink", "fifo"])
def test_real_cli_rejects_nonregular_paths_and_ancestors(tmp_path, kind):
    src = source(tmp_path)
    out = tmp_path / "out"
    victim = tmp_path / "authored.txt"
    victim.write_bytes(b"Authored sentinel")
    if kind in ("ancestor", "dangling"):
        target = tmp_path / "external"
        if kind == "ancestor":
            target.mkdir()
        symlink(out, target, directory=True)
        out = out / "nested"
    elif kind == "file-parent":
        out.write_bytes(b"Not a directory")
        out = out / "nested"
    else:
        out.mkdir()
        leaf = out / "account-chart.md"
        if kind == "directory":
            leaf.mkdir()
        elif kind == "hardlink":
            leaf.hardlink_to(victim)
        else:
            if not hasattr(os, "mkfifo"):
                pytest.skip("FIFO creation unavailable")
            os.mkfifo(leaf)
    run = run_cli(*render_args(src, out, "--no-png"))
    assert run.returncode == 2, run.stdout + run.stderr
    assert victim.read_bytes() == b"Authored sentinel"
    assert not (out / "account-chart.mmd").exists()
    assert not (tmp_path / "external" / "nested").exists()


@pytest.mark.parametrize("option", ["snapshot", "avatar", "mmdc-config", "registry", "approved", "approved-yaml",
                                   "actions", "decisions", "config", "t3-signoff-file", "mmdc"])
def test_real_cli_rejects_input_output_aliases(tmp_path, option):
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
    run = run_cli(*pre, *render_args(src, out, "--no-png", *extra))
    assert run.returncode == 2, run.stdout + run.stderr
    assert json.loads(run.stdout)["logs"] == ["account-chart:path"]
    assert dest.read_bytes() == before
    assert sorted(p.name for p in out.iterdir()) == [dest.name]


def test_input_symlink_to_regular_destination_is_also_an_alias(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    dest = out / "account-chart.md"
    dest.write_text(json.dumps(snapshot()), encoding="utf-8")
    src = tmp_path / "snapshot.json"
    symlink(src, dest)
    before = dest.read_bytes()
    run = run_cli(*render_args(src, out, "--no-png"))
    assert run.returncode == 2 and dest.read_bytes() == before
    assert list(out.iterdir()) == [dest]


def test_real_cli_success_is_repeatable_and_retains_source(tmp_path):
    src = source(tmp_path)
    before = src.read_bytes()
    out = tmp_path / "out"
    digest = None
    for _ in range(2):
        run = run_cli(*render_args(src, out))
        assert run.returncode == 0, run.stdout + run.stderr
        result = json.loads(run.stdout)
        assert result["lint"]["result"] == "PASS"
        current = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
        assert len(current) == 4 and (digest is None or current == digest)
        digest = current
    assert src.read_bytes() == before
    assert "no public repositories" in (out / "account-chart.md").read_text(encoding="utf-8")


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


@pytest.mark.parametrize("success", [False, True])
def test_optional_mmdc_uses_scratch_and_only_publishes_success(tmp_path, monkeypatch, capsys, success):
    src = source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    mermaid = out / "account-chart.mermaid.png"
    mermaid.write_bytes(b"Previous optional render")
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


def fake_capture(calls, *, viewer="northwind-dev", orgs=(), page=None):
    def run(name, **values):
        calls.append((name, values))
        def conn(nodes):
            return {"nodes": nodes, "pageInfo": {"hasNextPage": False}}
        repos = conn([{"name": "northwind-kept"}, {"name": "northwind-withdrawn"}])
        counts = {"all": {"totalCount": 2}, "public": {"totalCount": 2}}
        if name == "account_viewer":
            return {"viewer": {"login": viewer}}
        if name == "account_user":
            return {"user": {"login": values["login"], "repositories": repos, **counts}}
        if name == "account_orgs":
            return {"user": {"organizations": conn([{"login": o} for o in orgs])}}
        if name == "account_enterprises":
            return {"viewer": {"enterprises": conn([])}}
        if name == "account_org":
            return {"organization": {"login": values["org"], "repositories": page or repos, **counts}}
        raise AssertionError(name)
    return run


@pytest.mark.parametrize("owner", ["BunsDev", "Pick-Your-AI", "TouchedByAnAgent", "Northwind-Excluded"])
def test_explicit_restricted_capture_has_no_reads(owner, brand):
    calls = []
    resolver = Resolver(brand, {"orgs": {"BunsDev": {"former_slugs": ["Northwind-Excluded"]}}})
    with pytest.raises(Refused):
        A.capture(owner, run=fake_capture(calls), resolver=resolver)
    assert calls == []


def test_default_excluded_viewer_stops_before_repository_reads():
    calls = []
    with pytest.raises(Refused):
        A.capture(run=fake_capture(calls, viewer="BunsDev"))
    assert [name for name, _ in calls] == ["account_viewer"]


def test_cli_capture_gates_nested_owners_and_preserves_allowed_general_accounts(tmp_path, monkeypatch, capsys):
    calls = []
    run = fake_capture(calls, orgs=["BunsDev", "Pick-Your-AI", "TouchedByAnAgent", "Northwind-Labs"])
    monkeypatch.setattr(A, "capture", functools.partial(A.capture, run=run, today="2026-11-18"))
    dest = tmp_path / "snapshot.json"
    code, _ = invoke(capsys, "account-chart", "capture", "--out", dest)
    assert code == 0
    assert [v["org"] for name, v in calls if name == "account_org"] == ["Northwind-Labs"]
    snap = A.load_snapshot(dest)
    assert snap["account"]["login"] == "northwind-dev" and len(snap["repositories"]) == 2
    for org in snap["organizations"]:
        assert len(org["repositories"]) == (2 if org["login"] == "Northwind-Labs" else 0)


def test_cli_t3_requires_flag_and_valid_record_and_honors_withdrawals(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(A, "capture", functools.partial(A.capture, run=fake_capture(calls)))
    records = ROOT / "tests/fixtures/t3-signoff/valid.yaml"
    dest = tmp_path / "snapshot.json"
    for pre in (["--t3-signoff-file", records], ["--allow-t3", "--t3-signoff-file", tmp_path / "missing.yaml"]):
        code, _ = invoke(capsys, *pre, "account-chart", "capture", "Pick-Your-AI", "--out", dest)
        assert code == 2 and calls == [] and not dest.exists()
    code, _ = invoke(capsys, "--allow-t3", "--t3-signoff-file", records,
                     "account-chart", "capture", "Pick-Your-AI", "--out", dest)
    assert code == 0
    assert [r["name"] for r in A.load_snapshot(dest)["repositories"]] == ["northwind-kept"]


def test_capture_output_preflight_precedes_mocked_network(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(A, "capture", functools.partial(A.capture, run=fake_capture(calls)))
    victim = tmp_path / "authored.json"
    victim.write_bytes(b"Synthetic original")
    dest = tmp_path / "snapshot.json"
    symlink(dest, victim)
    code, _ = invoke(capsys, "account-chart", "capture", "northwind-dev", "--out", dest)
    assert code == 2 and calls == [] and victim.read_bytes() == b"Synthetic original"


@pytest.mark.parametrize(("state", "label"), [("uncaptured", "not captured"), ("unknown", "capture status unknown"),
                                           ("partial", "partially captured")])
def test_capture_states_agree_in_model_markdown_mermaid_and_real_svg(tmp_path, brand, state, label):
    src = source(tmp_path, captured=state != "uncaptured", capture_state=state, not_public=None)
    model, _ = A.build(A.load_snapshot(src), brand)
    node = model["orgs"][0]
    assert node["capture_state"] == state and node["public"] is None
    assert "empty" not in node["notes"]
    assert label in [item["text"] for item in C._items(node, brand.raw["chart"]["labels"])]
    out = tmp_path / "out"
    run = run_cli(*render_args(src, out, "--no-png"))
    assert run.returncode == 0, run.stdout + run.stderr
    for suffix in ("md", "mmd", "svg"):
        text = (out / f"account-chart.{suffix}").read_text(encoding="utf-8")
        assert label in text and "no public repositories" not in text


def test_partial_pagination_does_not_claim_empty_or_full_capture(brand):
    calls = []
    page = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": None}}
    snap = A.capture(run=fake_capture(calls, orgs=["Northwind-Labs"], page=page))
    assert snap["organizations"][0]["capture_state"] == "partial"
    model, _ = A.build(A.validate(snap), brand)
    assert model["orgs"][0]["notes"] == ["partial"]


def test_unknown_counts_and_missing_capture_flags_stay_unknown(brand):
    snap = snapshot()
    org = snap["organizations"][0]
    del org["captured"]
    del org["not_public"]
    model, _ = A.build(A.validate(snap), brand)
    assert model["orgs"][0]["capture_state"] == "unknown"
    assert model["orgs"][0]["not_public"] is None
    assert model["counts"]["unknown_not_public"] == 1
    assert A._not_public({"all": {"totalCount": 2}}) is None


def test_enterprise_reference_without_an_org_capture_stays_visible_as_uncaptured(brand):
    snap = snapshot()
    snap["enterprises"] = [{"slug": "northwind-enterprise", "organizations": ["Northwind-Missing"]}]
    model, _ = A.build(A.validate(snap), brand)
    org = model["enterprises"][0]["orgs"][0]
    assert org["login"] == "Northwind-Missing" and org["capture_state"] == "uncaptured"
    assert "Northwind-Missing: not captured" in model["coverage"]


def test_uncaptured_snapshot_never_repeats_stale_repository_names(brand):
    snap = snapshot(captured=False, repositories=[{"name": "synthetic-stale"}], not_public=10)
    model, _ = A.build(A.validate(snap), brand)
    assert model["orgs"][0]["repos"] == [] and model["orgs"][0]["not_public"] is None
    assert model["counts"]["public"] == 1 and model["counts"]["not_public"] == 0


def test_repository_connection_failure_after_one_page_preserves_partial_evidence(brand):
    calls = []
    first = fake_capture(calls, orgs=["Northwind-Labs"], page={
        "nodes": [{"name": "synthetic-first-page"}], "pageInfo": {"hasNextPage": True, "endCursor": "more"}})

    def run(name, **values):
        if name == "account_org" and values.get("after"):
            from ctshowcase.errors import ShowcaseError
            raise ShowcaseError("Synthetic interrupted pagination")
        return first(name, **values)
    snap = A.capture(run=run)
    model, _ = A.build(A.validate(snap), brand)
    org = model["orgs"][0]
    assert org["capture_state"] == "partial" and org["public"] is None
    assert [r["name"] for r in org["repos"]] == ["synthetic-first-page"]
