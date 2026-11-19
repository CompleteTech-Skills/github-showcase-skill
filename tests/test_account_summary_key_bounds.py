"""Frozen source-blind PR211 fit contracts: synthetic offline CLI renders only.

Expectations come from the account-chart reference and accepted review finding,
not a proposed summary repair. Glyph outlines and their emitted positions prove
that the displayed key fits and spells the same entries as its alternative text.
"""
from __future__ import annotations

from collections import Counter
import html
import json
import os
import re
import socket
import subprocess
import xml.etree.ElementTree as ET

from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path
import pytest
import showcase

from conftest import ROOT
from ctshowcase import account as A

NS = "{http://www.w3.org/2000/svg}"
LONG_A = "M" * 180
LONG_B = "W" * 190
LONG_OTHER = "M" * 170


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "missing-estate"))
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(tmp_path / "missing-signoffs.json"))
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append("transport")
        raise AssertionError("synthetic summary test attempted a transport")

    monkeypatch.setattr(A, "_gh", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(os, "system", blocked)
    for name in ("posix_spawn", "posix_spawnp", "spawnv", "spawnve", "spawnvp", "spawnvpe"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    for name in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, name, blocked)
    yield
    assert not attempts, "the local render attempted a real transport"


def render(tmp_path, capsys, sizes, *, static, other=None, code_other=0, output=None):
    source = tmp_path / "synthetic-capture.json"
    source.write_text(json.dumps({
        "schema": "account-chart/v1", "captured": "2026-11-18",
        "account": {"login": "northwind-dev"}, "not_public": 0,
        "enterprises": [], "organizations": [],
        "repositories": [{"name": f"synthetic-code-{index}", "language": name,
                          "code": {name: size}, "code_other": code_other if index == 0 else 0,
                          "fork": False, "archived": False}
                         for index, (name, size) in enumerate(sizes.items())],
    }), encoding="utf-8")
    prefix = []
    if other is not None:
        raw = json.loads((ROOT / "references/brand.lock.json").read_text(encoding="utf-8"))
        raw["chart"]["labels"]["other_languages"] = other
        config = tmp_path / "synthetic-brand.json"
        config.write_text(json.dumps(raw), encoding="utf-8")
        prefix = ["--config", str(config)]
    output = output or tmp_path / "output"
    flags = ["--static-summary"] if static else []
    code = showcase.main([*prefix, "account-chart", "render", "--snapshot", str(source),
                          "--out-dir", str(output), "--width", "1600", "--no-png", *flags])
    captured = capsys.readouterr()
    assert not captured.err, "JSON CLI unexpectedly wrote stderr"
    report = json.loads(captured.out)
    return code, report, output


def key_entries(svg):
    desc = svg.find(NS + "desc").text
    text = desc.rsplit("excluding forks: ", 1)[1].removesuffix(".")
    return [(name, percentage) for name, percentage in
            (entry.rsplit(" ", 1) for entry in text.split("; "))]


def glyph_signature(fonts, key, text):
    shaped, _ = fonts.shape(key, text, 100)
    face = fonts.face(key)
    return [(face.glyph_svg(glyph), round(x, 1)) for glyph, x, _ in shaped if face.glyph_svg(glyph)]


def assert_key_fits_and_agrees(output, report, fonts, *, static, compacted):
    assert report["result"] == "ok"
    assert report["summary_lint"]["result"] == "PASS"
    assert report["summary_lint"]["animated"] is not static
    svg = ET.parse(output / "account-chart-summary.svg").getroot()
    assert svg.attrib["viewBox"] == "0 0 1280 360"
    entries = key_entries(svg)
    assert entries and sum(float(share.removesuffix("%")) for _, share in entries) == pytest.approx(100, abs=0.2)
    markdown = (output / "account-chart.md").read_text(encoding="utf-8")
    image = next(line for line in markdown.splitlines() if 'src="account-chart-summary.svg"' in line)
    alt = html.unescape(re.search(r'alt="([^"]*)"', image).group(1))
    expected = ", ".join(f"{name} {share}" for name, share in entries)
    assert alt.rsplit("excluding forks: ", 1)[1] == expected, "summary alternative text disagrees with its key"
    if compacted:
        lines = [line for line in markdown.splitlines() if line.startswith("<sub>Summary key")]
        assert len(lines) == 1, "compacted summary must include its actual key beside the image"
        assert html.unescape(lines[0]).split(": ", 1)[1].removesuffix(".</sub>") == expected

    # Inspect actual glyphs, including their complete outlines beyond the SVG's
    # viewport clip. A lint PASS or an accessible description cannot prove fit.
    track = svg.find(f".//{NS}clipPath[@id='track']/{NS}rect")
    left = float(track.attrib["x"])
    right = left + float(track.attrib["width"])
    bottom = float(track.attrib["y"]) + float(track.attrib["height"])
    definitions = {path.attrib["id"]: path.attrib.get("d", "")
                   for path in svg.findall(f".//{NS}defs/{NS}path")}
    expected_tokens = Counter(token for name, share in entries for token in (name, share))
    observed = Counter()
    for group in svg.iter(NS + "g"):
        uses = list(group)
        if not uses or any(child.tag != NS + "use" for child in uses):
            continue
        transform = re.fullmatch(r"translate\(([-.\d]+)[ ,]+([-.\d]+)\) scale\(([-.\d]+)\)",
                                 group.attrib.get("transform", ""))
        if transform is None:
            continue
        x, y, scale = map(float, transform.groups())
        if y <= bottom or x < left:
            continue
        signature = [(definitions[use.attrib["href"].removeprefix("#")],
                      round(float(use.attrib.get("x", "0")), 1)) for use in uses]
        matches = [token for token in expected_tokens
                   if any(signature == glyph_signature(fonts, face, token)
                          for face in ("poppins-regular", "poppins-medium", "poppins-semibold"))]
        assert len(matches) == 1, "displayed summary glyphs do not spell a complete key token"
        observed[matches[0]] += 1
        for outline, advance in signature:
            if not outline:
                continue
            pen = BoundsPen(None)
            parse_path(outline, pen)
            if pen.bounds is None:
                continue
            xmin, ymin, xmax, ymax = pen.bounds
            assert left <= x + scale * (advance + xmin) <= x + scale * (advance + xmax) <= right, \
                "displayed summary key glyphs overflow their horizontal region"
            assert bottom <= y + scale * ymin <= y + scale * ymax <= 340, \
                "displayed summary key glyphs overflow their vertical region"
    repetitions = 1 if static else 2
    assert observed == Counter({token: count * repetitions for token, count in expected_tokens.items()}), \
        "displayed summary key differs from the complete described key"
    return entries, markdown


@pytest.mark.parametrize("static", [False, True], ids=["animated", "static"])
def test_one_overwide_language_compacts_to_default_aggregate(tmp_path, capsys, fonts, static):
    assert fonts.width("poppins-regular", LONG_A, 15) > 1280
    code, report, output = render(tmp_path, capsys, {LONG_A: 100}, static=static)
    assert code == 0, "a valid long language must compact into a fitting aggregate"
    entries, markdown = assert_key_fits_and_agrees(output, report, fonts, static=static, compacted=True)
    assert entries == [("Other languages", "100.0%")], "the single overwide label was not aggregated"
    chart_line = next(line for line in markdown.splitlines() if line.startswith("<sub>Code across"))
    assert f"{LONG_A} 100.0%" in chart_line, "compaction lost the original chart's language facts"


@pytest.mark.parametrize("static", [False, True], ids=["animated", "static"])
def test_multiple_overwide_entries_fold_without_truncation(tmp_path, capsys, fonts, static):
    sizes = {LONG_A: 40, LONG_B: 30, "Python": 20, "Go": 10}
    assert all(fonts.width("poppins-regular", label, 15) > 1280 for label in (LONG_A, LONG_B))
    code, report, output = render(tmp_path, capsys, sizes, static=static)
    assert code == 0, "a fitting default aggregate should make this valid capture renderable"
    entries, markdown = assert_key_fits_and_agrees(output, report, fonts, static=static, compacted=True)
    shown = dict(entries)
    assert LONG_A not in shown and LONG_B not in shown
    assert "Other languages" in shown and float(shown["Other languages"].removesuffix("%")) >= 70
    for name, share in (("Python", "20.0%"), ("Go", "10.0%")):
        if name in shown:
            assert shown[name] == share, "a retained language changed share"
    chart_line = next(line for line in markdown.splitlines() if line.startswith("<sub>Code across"))
    assert all(f"{name} {size:.1f}%" in chart_line for name, size in sizes.items())


@pytest.mark.parametrize("static", [False, True], ids=["animated", "static"])
@pytest.mark.parametrize("reason", ["existing-aggregate", "compaction-needed", "single-overwide"])
def test_unfitting_configured_aggregate_is_atomic_artfail(tmp_path, capsys, fonts, static, reason):
    assert fonts.width("poppins-regular", LONG_OTHER, 15) > 1280
    if reason == "existing-aggregate":
        sizes, code_other = {"Python": 90}, 10
    elif reason == "single-overwide":
        sizes, code_other = {LONG_A: 100}, 0
    else:
        sizes = {f"SyntheticLanguage{index:02}": 100 for index in range(30)}
        code_other = 0
    output = tmp_path / "output"
    output.mkdir()
    for name in ("account-chart.mmd", "account-chart.svg", "account-chart.md", "account-chart.png",
                 "account-chart-summary.svg", "unrelated.txt"):
        (output / name).write_bytes(f"synthetic previous {name}\r\n".encode())
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    code, report, _ = render(tmp_path, capsys, sizes, static=static, other=LONG_OTHER,
                             code_other=code_other, output=output)
    after = {path.name: path.read_bytes() for path in output.iterdir()}
    assert after == before, "unfitting summary replaced pre-existing synthetic artifacts"
    assert code == 3 and report["result"] == "art-fail", "unfitting final key must use the existing ArtFail exit"
    assert report["logs"] == ["art-fail:summary-key"]
    assert LONG_OTHER not in json.dumps(report), "fit failure needlessly echoed the synthetic label"


@pytest.mark.parametrize("static", [False, True], ids=["animated", "static"])
@pytest.mark.parametrize("case", ["ordinary", "unused-overwide-aggregate", "fitting-custom-aggregate"])
def test_fitting_controls_preserve_full_labels_and_shares(tmp_path, capsys, fonts, static, case):
    labels = {"unused-overwide-aggregate": LONG_OTHER, "fitting-custom-aggregate": "Additional languages"}
    other = labels.get(case)
    sizes = {"Python": 60, "Go": 40} if case != "fitting-custom-aggregate" else {"Python": 90}
    code_other = 10 if case == "fitting-custom-aggregate" else 0
    code, report, output = render(tmp_path, capsys, sizes, static=static, other=other, code_other=code_other)
    assert code == 0, "a key that fits should render regardless of an unused aggregate label"
    entries, _ = assert_key_fits_and_agrees(output, report, fonts, static=static, compacted=False)
    expected = [("Python", "90.0%"), ("Additional languages", "10.0%")]
    if case != "fitting-custom-aggregate":
        expected = [("Python", "60.0%"), ("Go", "40.0%")]
    assert entries == expected, "ordinary labels and their shares changed"
