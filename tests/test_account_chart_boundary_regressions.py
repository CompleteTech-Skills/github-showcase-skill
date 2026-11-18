"""Issue 203: independent black-box boundaries; synthetic CLI/GraphQL evidence only.

Written from issue 203, the account-chart reference and existing test interfaces,
without reading the account/chart implementation or a proposed implementation diff.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
import showcase

from conftest import EX, ROOT


@pytest.fixture(autouse=True)
def isolated_estate(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "nonexistent-estate"))
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(tmp_path / "missing-signoffs.yaml"))


def snapshot_file(tmp_path, *, captured=True, repos=(), notes=()):
    data = json.loads((EX / "account-chart/northwind.snapshot.json").read_text(encoding="utf-8"))
    data.update(enterprises=[], repositories=[], not_public=0, notes=list(notes))
    data["organizations"] = [{"login": "Northwind-Labs", "name": "Northwind Labs", "member": True,
        "role": "member", "captured": captured, "not_public": 0,
        "repositories": [{"name": name, "description": "Synthetic test repository.", "language": "Python",
                          "fork": False, "archived": False} for name in repos]}]
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def tree_state(root):
    """Never follow symlinks or open special files; include every synthetic entry."""
    result = {}

    def walk(path):
        info = path.lstat()
        content = (os.readlink(path) if stat.S_ISLNK(info.st_mode) else
                   hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None)
        result[path.relative_to(root).as_posix()] = (info.st_mode, info.st_ino, info.st_nlink, content)
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir()):
                walk(child)
    walk(root)
    return result


def render_cli(snapshot, out, *extra):
    return subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "account-chart", "render",
                           "--snapshot", str(snapshot), "--out-dir", str(out), "--width", "1600",
                           *map(str, extra)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)


def assert_atomic_refusal(proc, root, before):
    # Check preservation even if the process incorrectly reports success or crashes.
    assert tree_state(root) == before, "Refusal changed synthetic fixture entries, links or authored bytes"
    assert proc.returncode == 2, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["result"] in {"refused", "usage"}, report


@pytest.mark.parametrize("leaf", ["mmd", "svg", "md", "png", "mermaid.png"])
def test_render_preflights_every_symlink_leaf_before_any_write(tmp_path, leaf):
    snapshot = snapshot_file(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    authored = tmp_path / "authored.txt"
    authored.write_bytes(b"Synthetic authored content; preserve exactly.\n")
    (out / f"account-chart.{leaf}").symlink_to(authored)
    (out / "unrelated.txt").write_bytes(b"Synthetic unrelated file.\n")
    before = tree_state(tmp_path)
    extra = ("--mmdc", "no-such-synthetic-mmdc") if leaf == "mermaid.png" else ()
    proc = render_cli(snapshot, out, *extra)
    assert_atomic_refusal(proc, tmp_path, before)


@pytest.mark.parametrize("kind", ["output-root", "parent", "dangling-root"])
def test_render_refuses_symlinked_output_ancestors(tmp_path, kind):
    snapshot = snapshot_file(tmp_path)
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(tmp_path / "absent" if kind == "dangling-root" else actual, target_is_directory=True)
    out = link / "nested" if kind == "parent" else link
    before = tree_state(tmp_path)
    assert_atomic_refusal(render_cli(snapshot, out, "--no-png"), tmp_path, before)


@pytest.mark.parametrize("kind", ["directory", "fifo", "socket", "device"])
def test_render_refuses_nonregular_late_destination_atomically(tmp_path, kind):
    snapshot = snapshot_file(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    target = out / "account-chart.md"
    sock = None
    if kind == "directory":
        target.mkdir()
        (target / "authored.txt").write_bytes(b"Synthetic authored descendant.\n")
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("requires POSIX FIFO support")
        os.mkfifo(target)
    elif kind == "socket":
        import socket
        if not hasattr(socket, "AF_UNIX"):
            pytest.skip("requires local Unix socket support")
        try:
            sock = socket.socket(socket.AF_UNIX)
            sock.bind(str(target))
        except PermissionError:
            if sock is not None:
                sock.close()
            pytest.skip("sandbox does not permit creating a synthetic Unix socket")
    else:
        if not hasattr(os, "mknod"):
            pytest.skip("requires POSIX device-node support")
        try:
            os.mknod(target, stat.S_IFCHR | 0o600, os.makedev(1, 3))
        except PermissionError:
            pytest.skip("sandbox does not permit creating a synthetic null-device node")
    before = tree_state(tmp_path)
    try:
        assert_atomic_refusal(render_cli(snapshot, out, "--no-png"), tmp_path, before)
    finally:
        if sock is not None:
            sock.close()


@pytest.mark.parametrize("leaf", ["mmd", "svg", "md", "png"])
@pytest.mark.parametrize("alias", ["same-path", "hardlink"])
def test_render_refuses_snapshot_output_aliases_before_writing(tmp_path, leaf, alias):
    snapshot = snapshot_file(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    target = out / f"account-chart.{leaf}"
    if alias == "same-path":
        snapshot.rename(target)
        snapshot = target
    else:
        os.link(snapshot, target)
    before = tree_state(tmp_path)
    assert_atomic_refusal(render_cli(snapshot, out), tmp_path, before)


def test_render_refuses_two_outputs_sharing_an_authored_inode(tmp_path):
    snapshot = snapshot_file(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "account-chart.mmd").write_bytes(b"Synthetic authored content.\n")
    os.link(out / "account-chart.mmd", out / "account-chart.md")
    before = tree_state(tmp_path)
    assert_atomic_refusal(render_cli(snapshot, out, "--no-png"), tmp_path, before)


def test_render_refuses_optional_input_output_alias_before_writing(tmp_path):
    snapshot = snapshot_file(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    config = tmp_path / "puppeteer.json"
    config.write_text("{}\n", encoding="utf-8")
    os.link(config, out / "account-chart.md")
    before = tree_state(tmp_path)
    proc = render_cli(snapshot, out, "--no-png", "--mmdc", "no-such-synthetic-mmdc", "--mmdc-config", config)
    assert_atomic_refusal(proc, tmp_path, before)


def test_eligible_offline_render_retry_and_separate_directory_are_identical(tmp_path):
    snapshot = snapshot_file(tmp_path, repos=("synthetic-visible",))
    source = snapshot.read_bytes()
    out = tmp_path / "out"
    first = render_cli(snapshot, out)
    assert first.returncode == 0, first.stdout + first.stderr
    expected = {p.name: p.read_bytes() for p in out.iterdir()}
    assert set(expected) == {f"account-chart.{suffix}" for suffix in ("mmd", "svg", "png", "md")}
    for destination in (out, tmp_path / "independent"):
        result = render_cli(snapshot, destination)
        assert result.returncode == 0, result.stdout + result.stderr
        assert {p.name: p.read_bytes() for p in destination.iterdir()} == expected
    assert snapshot.read_bytes() == source
    assert "Northwind-Labs/synthetic-visible" in expected["account-chart.md"].decode("utf-8")


def mock_capture_transport(monkeypatch, *, viewer="northwind-dev", org_state=None):
    """Stub gh's transport, leaving the actual CLI, owner gates and capture code intact."""
    calls = []

    def run(argv, **kwargs):
        assert argv[:3] == ["gh", "api", "graphql"], argv
        query = next(arg for arg in argv if str(arg).startswith("query=@"))
        name = Path(query.removeprefix("query=@")).stem
        variables = dict(str(arg).split("=", 1) for arg in argv if "=" in str(arg) and not str(arg).startswith("query=@"))
        calls.append((name, variables))
        page = {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}
        if name == "account_viewer":
            data = {"viewer": {"login": viewer}}
        elif name == "account_user":
            data = {"user": {"login": variables["login"], "name": "Synthetic account", "company": "",
                    "location": "", "websiteUrl": "", "all": {"totalCount": 0}, "public": {"totalCount": 0},
                    "repositories": page}}
        elif name == "account_orgs":
            data = {"user": {"organizations": {**page, "nodes": [{"login": "Northwind-Labs"}] if org_state else []}}}
        elif name == "account_enterprises":
            data = {"viewer": {"enterprises": page}}
        elif name == "account_org":
            if org_state == "failed" or variables.get("after"):
                return subprocess.CompletedProcess(argv, 1, "", "Synthetic inaccessible page")
            connection = {"nodes": [{"name": "synthetic-first-page", "description": "Synthetic.",
                "isFork": False, "isArchived": False, "primaryLanguage": {"name": "Python"}}],
                "pageInfo": {"hasNextPage": True, "endCursor": "synthetic-next"}}
            data = {"organization": {"login": "Northwind-Labs", "name": "Northwind Labs", "viewerCanAdminister": False,
                    "all": {"totalCount": 2}, "public": {"totalCount": 2}, "repositories": connection}}
        else:
            raise AssertionError(f"Unexpected mocked query: {name}")
        return subprocess.CompletedProcess(argv, 0, json.dumps({"data": data}), "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


@pytest.mark.parametrize(("owner", "consent"), [("BunsDev", "none"), ("Pick-Your-AI", "none"),
    ("Pick-Your-AI", "flag-only"), ("Pick-Your-AI", "revoked")])
def test_capture_refuses_ineligible_explicit_owner_before_any_mocked_read(tmp_path, monkeypatch, capsys, owner, consent):
    calls = mock_capture_transport(monkeypatch)
    output = tmp_path / "capture.json"
    output.write_bytes(b"Synthetic preexisting capture; preserve on refusal.\n")
    extra = []
    if consent != "none":
        extra.append("--allow-t3")
    if consent == "revoked":
        record = tmp_path / "signoffs.yaml"
        record.write_text('signoffs:\n  - id: synthetic-revoked\n    owner: Pick-Your-AI\n    repos: ["*"]\n'
                          '    approved: false\n    approver: synthetic-co-owner\n    approved_on: 2026-01-01\n', encoding="utf-8")
        extra += ["--t3-signoff-file", str(record)]
    before = tree_state(tmp_path)
    code = showcase.main([*extra, "account-chart", "capture", owner, "--out", str(output)])
    report = capsys.readouterr()
    assert tree_state(tmp_path) == before, report.out + report.err
    assert calls == [], f"Ineligible owner was read before consent refusal: {calls}"
    assert code == 2, report.out + report.err


def test_capture_resolves_default_viewer_then_refuses_excluded_owner(tmp_path, monkeypatch, capsys):
    calls = mock_capture_transport(monkeypatch, viewer="BunsDev")
    before = tree_state(tmp_path)
    code = showcase.main(["account-chart", "capture", "--out", str(tmp_path / "capture.json")])
    report = capsys.readouterr()
    assert tree_state(tmp_path) == before, report.out + report.err
    assert [name for name, _ in calls] == ["account_viewer"], calls
    assert code == 2, report.out + report.err


@pytest.mark.parametrize("owner", ["northwind-dev", "Pick-Your-AI"])
def test_capture_permits_eligible_or_explicitly_consented_owner(tmp_path, monkeypatch, capsys, t3_record, owner):
    calls = mock_capture_transport(monkeypatch)
    output = tmp_path / "capture.json"
    extra = ["--allow-t3", "--t3-signoff-file", str(t3_record)] if owner == "Pick-Your-AI" else []
    code = showcase.main([*extra, "account-chart", "capture", owner, "--out", str(output)])
    report = capsys.readouterr()
    assert code == 0, report.out + report.err
    snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert snapshot["schema"] == "account-chart/v1" and snapshot["account"]["login"] == owner
    assert any(name == "account_user" and values["login"] == owner for name, values in calls)


def assert_unknown_outputs(out, report, snapshot):
    # Text is outlined in SVG. Compare the actual glyph paths with a same-data
    # observed-empty control rather than requiring a new SVG metadata format.
    control = json.loads(snapshot.read_text(encoding="utf-8"))
    control["organizations"][0].update(captured=True, repositories=[], not_public=0)
    control_snapshot = snapshot.with_name("observed-empty.snapshot.json")
    control_snapshot.write_text(json.dumps(control), encoding="utf-8")
    control_out = out.with_name("observed-empty")
    proc = render_cli(control_snapshot, control_out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    md = (out / "account-chart.md").read_text(encoding="utf-8")
    mmd = (out / "account-chart.mmd").read_text(encoding="utf-8")
    svg = ET.parse(out / "account-chart.svg").getroot()
    empty_svg = ET.parse(control_out / "account-chart.svg").getroot()
    def paths(root):
        return [node.attrib.get("d") for node in root.iter() if node.tag.endswith("}path")]
    assert paths(svg) != paths(empty_svg), "Unknown and observed-empty rendered glyphs must differ"
    from PIL import Image, ImageDraw
    with Image.open(out / "account-chart.png") as unknown, Image.open(control_out / "account-chart.png") as empty:
        sheet = Image.new("RGB", (1600, 1164), "#202020")
        draw = ImageDraw.Draw(sheet)
        for index, (label, picture) in enumerate((("Unknown / failed capture", unknown), ("Observed empty control", empty))):
            thumb = picture.convert("RGB")
            thumb.thumbnail((1580, 532))
            sheet.paste(thumb, (10, index * 582 + 30))
            draw.text((10, index * 582 + 8), label, fill="white")
        sheet.save(out.parent / "unknown-versus-observed-empty.png")
    svg_evidence = " ".join(svg.itertext())
    org_md = md.split("https://github.com/Northwind-Labs)", 1)[1]
    assert "not captured" in org_md.lower(), md
    assert "no public repositories" not in org_md.lower(), md
    assert "not captured" in mmd.lower(), mmd
    assert not re.search(r"northwind[\s-]+labs[^.\n]*no public repositories", svg_evidence, re.I), svg_evidence
    assert re.search(r"uncaptured|not.captured|partial|incomplete", json.dumps(report), re.I), report


def test_uncaptured_snapshot_is_unknown_in_markdown_svg_and_cli_evidence(tmp_path):
    snapshot = snapshot_file(tmp_path, captured=False, notes=("org-uncaptured:Northwind-Labs",))
    out = tmp_path / "out"
    proc = render_cli(snapshot, out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert_unknown_outputs(out, json.loads(proc.stdout), snapshot)


@pytest.mark.parametrize("state", ["failed", "partial"])
def test_mocked_failed_or_partial_org_read_never_becomes_observed_empty(tmp_path, monkeypatch, capsys, state):
    real_run = subprocess.run
    calls = mock_capture_transport(monkeypatch, org_state=state)
    snapshot = tmp_path / "capture.json"
    code = showcase.main(["account-chart", "capture", "northwind-dev", "--out", str(snapshot)])
    report = capsys.readouterr()
    assert code == 0, report.out + report.err
    captured = json.loads(snapshot.read_text(encoding="utf-8"))
    org = next(item for item in captured["organizations"] if item["login"] == "Northwind-Labs")
    assert org["captured"] is False, captured
    if state == "partial":
        assert any(name == "account_org" and values.get("after") == "synthetic-next" for name, values in calls)
    # Restore only the transport so this subsequent command is a real offline subprocess CLI render.
    monkeypatch.setattr(subprocess, "run", real_run)
    out = tmp_path / "out"
    proc = render_cli(snapshot, out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert_unknown_outputs(out, json.loads(proc.stdout), snapshot)


def test_observed_empty_org_retains_truthful_empty_label(tmp_path):
    snapshot = snapshot_file(tmp_path, captured=True)
    out = tmp_path / "out"
    proc = render_cli(snapshot, out, "--no-png")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no public repositories" in (out / "account-chart.md").read_text(encoding="utf-8").lower()
    assert "not captured" not in (out / "account-chart.md").read_text(encoding="utf-8").lower()
