"""Offline CLI regressions for summary identity and the S11c reveal deadline."""
from __future__ import annotations

import base64
import io
import json
import re
import socket
import xml.etree.ElementTree as ET

import pytest
import showcase
from PIL import Image
from conftest import ROOT

from ctshowcase import account

NS = "{http://www.w3.org/2000/svg}"
OWNER = "Northwind-Summary"


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


def render(tmp_path, capsys, sizes, *, config=None, static=False, login=OWNER):
    snapshot = tmp_path / "capture.json"
    snapshot.write_text(json.dumps({"schema": "account-chart/v1", "captured": "2026-11-18",
                                   "account": {"login": login}, "not_public": 0,
                                   "repositories": [{"name": f"synthetic-{i}", "language": name, "code": {name: size}}
                                                    for i, (name, size) in enumerate(sizes.items())],
                                   "organizations": [], "enterprises": []}), encoding="utf-8")
    out = tmp_path / ("static" if static else "animated")
    args = ["--config", str(config)] if config else []
    args += ["account-chart", "render", "--snapshot", str(snapshot), "--out-dir", str(out), "--no-png"]
    if static:
        args.append("--static-summary")
    code = showcase.main(args)
    streams = capsys.readouterr()
    assert code == 0, streams
    assert not streams.err
    result = json.loads(streams.out)
    assert result["summary_lint"]["result"] == "PASS"
    raw = (out / "account-chart-summary.svg").read_bytes()
    return ET.fromstring(raw), raw


@pytest.mark.parametrize("static", [False, True])
@pytest.mark.parametrize("identity", ["unknown", "completetech", "custom-completetech", "custom-family", "family-no-mark",
                                      "former-completetech"])
def test_summary_uses_only_applicable_account_identity(tmp_path, capsys, identity, static):
    raw = json.loads((ROOT / "references/brand.lock.json").read_text(encoding="utf-8"))
    login = OWNER
    expected = None
    if identity != "unknown":
        row = {**raw["orgs"]["Northwind-Trading-Co"], "display_name": "Northwind Summary"}
        row.pop("mark", None)
        row["family"] = "ai-ascension" if identity in {"custom-family", "family-no-mark"} else "completetech"
        if identity.startswith("custom-"):
            mark = tmp_path / "synthetic-mark.png"
            Image.new("RGB", (40, 20), (32, 128, 192)).save(mark)
            row["mark"] = str(mark)
            expected = (32, 128, 192)
        elif identity in {"completetech", "former-completetech"}:
            expected = "master"
        if identity == "former-completetech":
            row["former_slugs"] = ["Northwind-Summary-Former"]
            login = "northwind-summary-former"
        raw["orgs"][OWNER] = row
    config = tmp_path / "synthetic-brand.json"
    config.write_text(json.dumps(raw), encoding="utf-8")
    svg, first = render(tmp_path, capsys, {"Python": 100}, config=config, static=static, login=login)
    images = svg.findall(f".//{NS}image")
    description = svg.find(NS + "desc").text
    if expected is None:
        assert not images, "an account without an applicable mark must use its monogram"
        assert "account monogram" in description
    else:
        assert len(images) == 1
        if isinstance(expected, tuple):
            raster = Image.open(io.BytesIO(base64.b64decode(images[0].attrib["href"].split(",", 1)[1])))
            assert all(abs(a - b) <= 4 for a, b in zip(raster.convert("RGB").getpixel((0, 0)), expected))
    _, second = render(tmp_path, capsys, {"Python": 100}, config=config, static=static, login=login)
    assert first == second


def delay(element):
    return float(re.search(r"animation-delay:([0-9.]+)s", element.attrib["style"])[1])


@pytest.mark.parametrize("count", [1, 2, 8, 13, 30, 80])
def test_complete_summary_reveal_settles_by_2_5_seconds(tmp_path, capsys, count):
    # Short names exercise larger unmerged keys; 80 names exercise three-row compaction.
    sizes = {f"L{i}": 100 if i else 300 for i in range(count)}
    svg, _ = render(tmp_path, capsys, sizes)
    still, _ = render(tmp_path, capsys, sizes, static=True)
    css = svg.find(NS + "style").text
    bar_duration = float(re.search(r"animation:gr ([0-9.]+)s", css)[1])
    key_duration = float(re.search(r"animation:fi ([0-9.]+)s", css)[1])
    bars = svg.findall(f".//{NS}rect[@class='gr']")
    keys = [child for group in svg.findall(f".//{NS}g[@class='anim']")
            for child in group if child.attrib.get("class") == "f" and child.find(".//" + NS + "use") is not None]
    assert len(bars) == len(keys) and bars
    if count == 13:
        assert len(bars) == 13
    ends = [delay(bar) + bar_duration for bar in bars] + [delay(key) + key_duration for key in keys]
    assert max(ends) <= 2.5, f"{len(bars)} entries finish at {max(ends):.2f}s"
    assert [delay(bar) for bar in bars] == sorted(delay(bar) for bar in bars)
    assert "@media (prefers-reduced-motion:reduce){.anim{display:none}.still{display:inline}}" in css
    assert ".still{display:none}" in css and "backwards" in css
    assert "to{opacity:1}" in css and "to{transform:scaleX(1)}" in css
    assert still.find(NS + "style") is None and not still.findall(f".//{NS}g[@class='anim']")
    groups = svg.findall(f".//{NS}g[@clip-path='url(#track)']")
    groups += still.findall(f".//{NS}g[@clip-path='url(#track)']")
    geometry = [[{k: v for k, v in rect.attrib.items() if k not in {"class", "style"}} for rect in group]
                for group in groups]
    assert len(geometry) == 3 and geometry[0] == geometry[1] == geometry[2]
    track = svg.find(f".//{NS}clipPath[@id='track']/{NS}rect")
    left = float(track.attrib["x"])
    right = left + float(track.attrib["width"])
    for rect in geometry[0]:
        x, width = float(rect["x"]), float(rect["width"])
        assert width >= 0 and left <= x <= x + width <= right
    if count <= 13:
        available = sum(float(rect["width"]) for rect in geometry[0])
        assert float(geometry[0][0]["width"]) == pytest.approx(available * 300 / sum(sizes.values()), abs=0.1)
