"""A long account name leaves out only the optional summary, never the whole account chart."""
from __future__ import annotations

import json
import socket

import pytest
import showcase

from ctshowcase import account

LONG = "Northwind Developer Relations and Platform Engineering Team"  # GitHub allows up to 255 characters
SHORT = "Northwind Summary"


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    estate = tmp_path / "estate"
    estate.mkdir()
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(estate))
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)

    def blocked(*args, **kwargs):
        raise AssertionError("summary regressions must remain offline")

    for method in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, method, blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(account, "_gh", blocked)


def render(tmp_path, capsys, name, *, static=False):
    snapshot = tmp_path / "capture.json"
    snapshot.write_text(json.dumps({
        "schema": "account-chart/v1", "captured": "2026-11-18", "not_public": 0,
        "account": {"login": "northwind-long-name", "name": name},
        "repositories": [{"name": "synthetic-a", "language": "Python", "code": {"Python": 7000, "Shell": 1000}},
                         {"name": "synthetic-b", "language": "Rust", "code": {"Rust": 2000}}],
        "organizations": [], "enterprises": []}), encoding="utf-8")
    out = tmp_path / "out"
    args = ["account-chart", "render", "--snapshot", str(snapshot), "--out-dir", str(out), "--no-png"]
    if static:
        args.append("--static-summary")
    code = showcase.main(args)
    streams = capsys.readouterr()
    return code, json.loads(streams.out), out


@pytest.mark.parametrize("static", [False, True])
def test_long_name_keeps_chart_and_omits_only_summary(tmp_path, capsys, static):
    code, result, out = render(tmp_path, capsys, LONG, static=static)
    assert code == 0 and result["result"] == "ok", result
    assert "summary-skipped:type-does-not-fit" in result["logs"]
    assert result["summary_lint"] is None
    assert not (out / "account-chart-summary.svg").exists()
    for suffix in (".svg", ".mmd", ".md"):
        assert (out / f"account-chart{suffix}").stat().st_size > 0
    md = (out / "account-chart.md").read_text(encoding="utf-8")
    assert "account-chart-summary.svg" not in md
    # The chart itself still carries the full, uncut name.
    assert LONG in (out / "account-chart.svg").read_text(encoding="utf-8")


def test_fitting_name_still_writes_summary(tmp_path, capsys):
    code, result, out = render(tmp_path, capsys, SHORT)
    assert code == 0 and result["result"] == "ok", result
    assert not any(log.startswith("summary-skipped") for log in result["logs"])
    assert result["summary_lint"]["result"] == "PASS"
    assert (out / "account-chart-summary.svg").exists()
    assert "account-chart-summary.svg" in (out / "account-chart.md").read_text(encoding="utf-8")
