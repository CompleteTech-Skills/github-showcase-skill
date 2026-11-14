"""Verify outlined badge output and all-or-nothing refusal through the public CLI."""
import copy
import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from conftest import run_cli
from ctshowcase import badge
from ctshowcase.color import contrast

NS = {"s": "http://www.w3.org/2000/svg"}


def fixture(tmp_path, owner):
    target = tmp_path / "checkout"
    target.mkdir()
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": owner, "repo": "synthetic-tool", "visibility": "public",
                               "description": "Inspect synthetic records.", "license": "MIT", "language": "Python",
                               "files": ["main.py", "LICENSE"], "files_complete": True}), encoding="utf-8")
    return target, ["--format", "json", "--meta", meta, "--repo-dir", target]


@pytest.mark.parametrize("owner,expected", [
    ("CompleteTech-LLC", {"#1E3A8A", "#005ADD", "#64748B"}),
    ("Jev-Engineering", {"#8B5CF6", "#22D3EE", "#64748B"}),
    ("LibreEvolve", {"#065F46", "#10B981", "#64748B"}),
])
def test_cli_local_badge_actual_outlines_have_small_text_contrast(tmp_path, owner, expected):
    target, common = fixture(tmp_path, owner)
    result = run_cli(*common, "readme", "--mode", "scaffold", "--variant", "C", "--badges", "local", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    fills = set()
    for path in (target / "docs/images/badges").glob("*.svg"):
        svg = ET.fromstring(path.read_text(encoding="utf-8"))
        backgrounds = svg.findall("s:g/s:rect", NS)
        text_groups = [g for g in svg.findall("s:g", NS) if g.findall("s:use", NS)]
        assert len(backgrounds) == len(text_groups) == 2
        fills.add(backgrounds[1].attrib["fill"])
        for bg, text in zip(backgrounds, text_groups):
            assert contrast(bg.attrib["fill"], text.attrib["fill"]) >= 4.5
    assert fills == expected


def test_default_helper_keeps_passing_output_bytes(brand, fonts):
    # Independent historical composition: passing defaults must not change their SVG bytes.
    from ctshowcase.scene import Clip, Rect, Scene, Text, to_svg
    b = brand.raw["badges"]
    label, message, colour = "language", "Python", "#1E3A8A"
    lw = fonts.width(badge.FONT, label, badge.SIZE) + 2 * badge.PAD
    mw = fonts.width(badge.FONT, message, badge.SIZE) + 2 * badge.PAD
    w = round(lw + mw)
    base = badge.H / 2 + fonts.face(badge.FONT).cap * badge.SIZE / 2
    scene = Scene(w, badge.H, title=f"{label}: {message}")
    scene.add(Clip(w, badge.H, 3, [Rect(0, 0, lw, badge.H, b["local_label_bg"]),
                                 Rect(lw, 0, w - lw, badge.H, colour)]),
              Text(badge.FONT, label, badge.SIZE, badge.PAD, base, b["local_text"]),
              Text(badge.FONT, message, badge.SIZE, lw + badge.PAD, base, b["local_text"]))
    assert badge.svg(brand, fonts, label, message, colour) == to_svg(scene, fonts, prefix="b")


@pytest.mark.parametrize("write", [False, True])
def test_no_permitted_foreground_refuses_before_any_write(brand, tmp_path, write):
    target, common = fixture(tmp_path, "Jev-Engineering")
    readme = target / "README.md"
    original = b"# Authored\n\nKeep these facts.\n"
    readme.write_bytes(original)
    folder = target / "docs/images/badges"
    folder.mkdir(parents=True)
    sentinel = folder / "language-python.svg"
    sentinel.write_bytes(b"existing badge bytes")
    raw = copy.deepcopy(brand.raw)
    # Only allowed foregrounds now equal the type fill; earlier badge requests can still render.
    fill = raw["families"]["jev-engineering"]["badge_brand"]
    candidate = "#" + fill
    # Ensure language/license preflight succeeds before the final type request fails.
    dark = raw["families"]["jev-engineering"]["canvas"]["color"]
    raw["badges"]["local_label_bg"] = dark
    raw["badges"]["neutral"] = dark.lstrip("#")
    raw["families"]["jev-engineering"]["badge_accent"] = dark.lstrip("#")
    raw["badges"]["local_text"] = candidate
    raw["contrast_candidates"] = [candidate]
    fam = raw["families"]["jev-engineering"]
    for chip in ("chip_key", "chip_attr"):
        fam["tokens"][chip]["fg"] = candidate
    fam["canvas"]["color"] = candidate
    fam["canvas"]["from"] = candidate
    config = tmp_path / "brand.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    records = tmp_path / "records.jsonl"
    result = run_cli("--config", config, "--type", "cli", *common, "readme", "--mode", "header", "--badges", "local",
                     "--records", records, *(["--write"] if write else []))
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:badge-contrast" in result.stdout
    assert readme.read_bytes() == original
    assert sentinel.read_bytes() == b"existing badge bytes"
    assert list(folder.iterdir()) == [sentinel]
    assert not records.exists()
