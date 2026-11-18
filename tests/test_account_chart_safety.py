"""Synthetic boundary checks for account capture, complete output plans and truthful coverage.

All capture calls use fake query runners; no account credentials or network are used.
"""
from __future__ import annotations

import json
import os

import pytest
import showcase
from conftest import EX, run_cli

from ctshowcase import account as A
from ctshowcase import chart as C
from ctshowcase import signoff
from ctshowcase.config import load_brand
from ctshowcase.errors import ShowcaseError
from ctshowcase.resolver import Resolver


def snapshot():
    return json.loads((EX / "account-chart/northwind.snapshot.json").read_text(encoding="utf-8"))


def saved_snapshot(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot()), encoding="utf-8")
    return path


def link(source, target, *, directory=False, hard=False):
    try:
        if hard:
            os.link(target, source)
        else:
            source.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"filesystem links unavailable: {exc}")


@pytest.mark.parametrize("suffix", ["mmd", "svg", "md", "png", "mermaid.png"])
@pytest.mark.parametrize("hard", [False, True])
def test_every_output_is_checked_before_any_authored_file_changes(tmp_path, suffix, hard):
    source = saved_snapshot(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "account-chart.mmd"
    sentinel.write_bytes(b"authored Mermaid")
    outside = tmp_path / "authored.txt"
    outside.write_bytes(b"authored outside")
    dest = output / f"account-chart.{suffix}"
    if dest == sentinel:
        sentinel.unlink()
    link(dest, outside, hard=hard)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    extra = ("--mmdc", "unavailable-synthetic-mmdc") if suffix == "mermaid.png" else ()
    result = run_cli("account-chart", "render", "--snapshot", source, "--out-dir", output, *extra)
    assert result.returncode == 2, result.stdout + result.stderr
    assert outside.read_bytes() == b"authored outside"
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


@pytest.mark.parametrize("nested", [False, True])
def test_symlinked_output_ancestor_is_refused_without_creating_children(tmp_path, nested):
    source = saved_snapshot(tmp_path)
    target = tmp_path / "outside"
    target.mkdir()
    alias = tmp_path / "alias"
    link(alias, target, directory=True)
    output = alias / "new" if nested else alias
    result = run_cli("account-chart", "render", "--snapshot", source, "--out-dir", output, "--no-png")
    assert result.returncode == 2
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_late_nonregular_output_preserves_earlier_artifacts(tmp_path, kind):
    source = saved_snapshot(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    earlier = output / "account-chart.mmd"
    earlier.write_bytes(b"authored")
    dest = output / "account-chart.md"
    if kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO unavailable on this platform")
        os.mkfifo(dest)
    else:
        dest.mkdir()
    result = run_cli("account-chart", "render", "--snapshot", source, "--out-dir", output, "--no-png")
    assert result.returncode == 2
    assert earlier.read_bytes() == b"authored"
    assert sorted(p.name for p in output.iterdir()) == ["account-chart.md", "account-chart.mmd"]


def test_source_in_a_planned_output_slot_is_not_overwritten(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    source = output / "account-chart.svg"
    original = json.dumps(snapshot()).encode()
    source.write_bytes(original)
    result = run_cli("account-chart", "render", "--snapshot", source, "--out-dir", output, "--no-png")
    assert result.returncode == 2 and source.read_bytes() == original
    assert list(output.iterdir()) == [source]


def test_optional_mmdc_input_alias_is_rejected_as_part_of_the_whole_plan(tmp_path):
    source = saved_snapshot(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    config = output / "account-chart.mermaid.png"
    config.write_bytes(b'{"synthetic":true}')
    result = run_cli("account-chart", "render", "--snapshot", source, "--out-dir", output, "--no-png",
                     "--mmdc", "synthetic-unavailable", "--mmdc-config", config)
    assert result.returncode == 2 and config.read_bytes() == b'{"synthetic":true}'
    assert list(output.iterdir()) == [config]


def test_safe_repeat_render_preserves_identical_bytes(tmp_path):
    source = saved_snapshot(tmp_path)
    output = tmp_path / "nested" / "out"
    args = ("account-chart", "render", "--snapshot", source, "--out-dir", output, "--no-png")
    first = run_cli(*args)
    assert first.returncode == 0, first.stdout + first.stderr
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    second = run_cli(*args)
    assert second.returncode == 0, second.stdout + second.stderr
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def fake_capture(calls, *, viewer="northwind-dev", orgs=(), fail_after=False):
    def connection(nodes, more=False):
        return {"nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": "next" if more else None}}

    def run(name, **variables):
        calls.append((name, variables))
        if name == "account_viewer":
            return {"viewer": {"login": viewer}}
        if name == "account_user":
            return {"user": {"login": variables["login"], "repositories": connection([]),
                             "all": {"totalCount": 0}, "public": {"totalCount": 0}}}
        if name == "account_orgs":
            return {"user": {"organizations": connection([{"login": o} for o in orgs])}}
        if name == "account_enterprises":
            return {"viewer": {"enterprises": connection([])}}
        if name == "account_org":
            if fail_after and variables.get("after"):
                raise ShowcaseError("synthetic continuation unavailable", log="needs-input:gh")
            return {"organization": {"login": variables["org"], "all": {"totalCount": 2}, "public": {"totalCount": 2},
                                     "repositories": connection([{"name": "northwind-known"}], fail_after)}}
        raise AssertionError(name)
    return run


@pytest.mark.parametrize("owner", ["BunsDev", "Pick-Your-AI", "TouchedByAnAgent"])
def test_explicit_refused_owner_is_gated_before_any_query(owner):
    calls = []
    with pytest.raises(ShowcaseError):
        A.capture(owner, run=fake_capture(calls))
    assert calls == []


@pytest.mark.parametrize("owner", ["BunsDev", "Pick-Your-AI", "TouchedByAnAgent"])
def test_default_refused_viewer_only_permits_identity_bootstrap(owner):
    calls = []
    with pytest.raises(ShowcaseError):
        A.capture(run=fake_capture(calls, viewer=owner))
    assert calls == [("account_viewer", {})]


def test_discovered_refused_orgs_do_not_trigger_repository_reads():
    calls = []
    snap = A.capture(run=fake_capture(calls, orgs=("BunsDev", "Pick-Your-AI", "TouchedByAnAgent", "Northwind-Labs")))
    queried = [v["org"] for name, v in calls if name == "account_org"]
    assert queried == ["Northwind-Labs"]
    assert all(not o["repositories"] for o in snap["organizations"] if o["login"] != "Northwind-Labs")


def test_registry_rename_cannot_bypass_exclusion():
    brand = load_brand()
    resolver = Resolver(brand, {"orgs": {"Northwind-Blocked-Alias": {"former_slugs": ["BunsDev"]}}})
    calls = []
    with pytest.raises(ShowcaseError) as exc:
        A.capture("Northwind-Blocked-Alias", resolver=resolver, brand=brand, run=fake_capture(calls))
    assert exc.value.log == "exempt" and calls == []


@pytest.mark.parametrize("record", ["missing", "expired", "scope", "valid"])
def test_capture_uses_existing_signoff_records(tmp_path, record):
    path = tmp_path / "signoffs.json"
    grant = {"id": "northwind-synthetic-grant", "owner": "Pick-Your-AI", "repos": ["*"], "approved": True,
             "approver": "synthetic-co-owner", "approved_on": "2020-01-01", "expires": "2099-12-31"}
    if record == "expired":
        grant["expires"] = "2021-01-01"
    if record == "scope":
        grant["repos"] = ["northwind-only"]
    path.write_text(json.dumps({"signoffs": [] if record == "missing" else [grant]}), encoding="utf-8")
    token, state = signoff.set_file(path), signoff.reset()
    calls = []
    try:
        if record == "valid":
            snap = A.capture("Pick-Your-AI", allow_t3=True, run=fake_capture(calls))
            assert snap["account"]["login"] == "Pick-Your-AI"
            assert any(name == "account_user" for name, _ in calls)
        else:
            with pytest.raises(ShowcaseError) as exc:
                A.capture("Pick-Your-AI", allow_t3=True, run=fake_capture(calls))
            assert exc.value.log == f"t3-signoff:{record}"
            assert calls == []
    finally:
        signoff.restore(state)
        signoff.reset_file(token)


def test_capture_destination_is_validated_before_network_or_write(tmp_path, monkeypatch, capsys):
    target = tmp_path / "authored.json"
    target.write_bytes(b"authored")
    dest = tmp_path / "capture.json"
    link(dest, target)
    calls = []
    monkeypatch.setattr(A, "_gh", fake_capture(calls))
    assert showcase.main(["account-chart", "capture", "--out", str(dest)]) == 2
    assert calls == [] and target.read_bytes() == b"authored"
    assert json.loads(capsys.readouterr().out)["logs"] == ["usage:account-chart-path"]


def test_partial_capture_keeps_observations_and_coverage():
    calls = []
    snap = A.capture(run=fake_capture(calls, orgs=("Northwind-Labs",), fail_after=True))
    node = snap["organizations"][0]
    assert node["capture_status"] == "partial" and node["captured"] is False
    assert [r["name"] for r in node["repositories"]] == ["northwind-known"]
    model, _ = A.build(A.validate(snap), load_brand())
    md = A.markdown(model, {"svg": "a.svg", "mmd": "a.mmd"})
    mermaid, _ = C.mermaid(model, load_brand())
    assert "partially captured" in md and "partially captured" in mermaid
    assert "northwind-known" in md and "northwind-known" in mermaid
    assert "map is incomplete" in model["desc"]


@pytest.mark.parametrize("status", ["uncaptured", "failed", "partial", "unknown"])
def test_missing_capture_never_becomes_an_empty_inventory(status):
    snap = snapshot()
    snap["enterprises"] = []
    snap["organizations"] = [{"login": "Northwind-Labs", "captured": False, "capture_status": status,
                               "repositories": [], "not_public": 0}]
    brand = load_brand()
    model, _ = A.build(A.validate(snap), brand)
    node = model["orgs"][0]
    assert node["capture_status"] == status and node["notes"] == [status]
    md = A.markdown(model, {"svg": "a.svg", "mmd": "a.mmd"})
    lane = md.split("### Organizations", 1)[1]
    assert "no public repositories" not in lane
    assert A._coverage_text(status) in lane
    mermaid, _ = C.mermaid(model, brand)
    assert A._coverage_text(status) in model["desc"]
    assert C._mq(A._coverage_text(status)) in mermaid


def test_missing_discovery_connection_is_reported_unknown():
    calls = []
    runner = fake_capture(calls)

    def unavailable(name, **variables):
        if name == "account_orgs":
            return {"user": {"organizations": None}}
        return runner(name, **variables)

    snap = A.capture(run=unavailable)
    assert snap["coverage"]["organizations"] == "uncaptured"
    model, _ = A.build(A.validate(snap), load_brand())
    assert any("Organization membership: not captured" in e for e in model["evidence"])
    assert "map is incomplete" in model["desc"]
