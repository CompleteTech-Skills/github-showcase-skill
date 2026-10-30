"""The installed skill's icon defaults work without the private estate bundle."""
import json
import copy
import os
import subprocess
import sys

import pytest
from conftest import ROOT, meta_dict

from ctshowcase import content as C
from ctshowcase.errors import NeedsInput

FAMILIES = ["CompleteTech-Skills", "AI-Ascension", "Jev-Engineering", "jevplay-games",
            "LibreEvolve", "TouchedByAnAgent", "romgenie-archive-repostiory"]


def glyph_image(colour):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (1024, 1024))
    ImageDraw.Draw(image).rectangle((250, 250, 750, 750), outline=colour, width=40)
    return image


@pytest.mark.parametrize("owner", FAMILIES)
def test_bundled_inks_survive_normalization_and_qa(owner, brand, make_ctx):
    from ctshowcase.resolver import Resolver

    ctx = make_ctx(owner=owner)
    result = C.icon_prompt(ctx, Resolver(brand, {}, {}), C.load_art_direction())
    card = ctx.style["tokens"]["card_fill"]
    for role in ("ink", "spark"):
        colour = result["render"][role]
        normalized, _ = C.normalize_icon(glyph_image(colour), "transparent", card)
        qa = C.icon_qa(C.icon_bytes(normalized)[0], card=card, ink=[colour])
        assert qa["result"] == "pass", (owner, role, qa)
    assert result["render"]["ink"] != result["render"]["spark"]


@pytest.mark.parametrize("owner", FAMILIES)
def test_bundled_prompt_distinguishes_outline_and_spark(owner, brand, make_ctx):
    from ctshowcase.resolver import Resolver

    ctx = make_ctx(owner=owner)
    result = C.icon_prompt(ctx, Resolver(brand, {}, {}), C.load_art_direction())
    assert result["render"]["ink"] != result["render"]["spark"]
    assert f'outline {result["render"]["ink"]}' in result["prompt"]
    assert f'one spark in {result["render"]["spark"]}' in result["prompt"]
    assert f'core {result["render"]["spark"]}' not in result["prompt"]
    assert "only filled shape" in result["prompt"]


def test_bundled_normalize_and_check_are_utf8_safe(tmp_path, brand):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    source = tmp_path / "candidate.png"
    glyph_image(brand.style("Northwind-Trading-Co")["tokens"]["chip_attr"]["bg"]).save(source)
    output = tmp_path / "icon.png"
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    for action, extra in (("normalize", ["--in", str(source)]), ("check", [])):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "--meta", str(meta),
                               "--no-repo-dir", "content", "icon", action, "--out", str(output), *extra],
                              capture_output=True, env=env)
        assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
        result = json.loads(proc.stdout.decode("utf-8"))
        assert any("ΔE" in cell["detail"] for cell in result["qa"]["checks"] if cell["check"] == "family-ink")


def test_default_is_the_bundled_art_direction(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert C.DEFAULT_ART_DIRECTION == ROOT / "references" / "art-direction.md"
    assert C.load_art_direction() == C.DEFAULT_ART_DIRECTION.read_text(encoding="utf-8")


@pytest.mark.parametrize("option", ["A", "B"])
def test_bundled_icon_prompt_from_unrelated_directory(option, monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    glyph = tmp_path / "glyph.json"
    glyph.write_text(json.dumps({"glyph_name": "Inbox", "glyph_description": "An open tray.",
                                 "spark_placement": "inside the tray", "size_class": "wide",
                                 "subject": "An open tray.", "objects": "A tray and envelope."}), encoding="utf-8")
    out = tmp_path / "prompt.md"
    args = ["--meta", str(meta), "--no-repo-dir", "content", "icon", "prompt", "--option", option,
            "--out", str(out)]
    assert C.main(args) == 1
    needs_writer = json.loads(capsys.readouterr().out)
    assert needs_writer["result"] == "needs-writer"
    assert not out.exists()
    assert C.main([*args, "--glyph", str(glyph)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["missing"] == []
    assert "An open tray." in out.read_text(encoding="utf-8")
    assert result["render"]["ink"] is not None


def test_explicit_art_direction_overrides_default(tmp_path):
    custom = tmp_path / "custom.md"
    custom.write_text("# Custom art direction\n", encoding="utf-8")
    assert C.load_art_direction(custom) == "# Custom art direction\n"
    missing = tmp_path / "missing.md"
    with pytest.raises(NeedsInput, match="art direction not found") as error:
        C.load_art_direction(missing)
    assert str(missing) in str(error.value)


def test_explicit_missing_template_reports_the_required_sections(brand, make_ctx):
    from ctshowcase.resolver import Resolver

    ctx = make_ctx()
    with pytest.raises(NeedsInput, match="Shared prompt template.*Repository glyph prompt template"):
        C.icon_prompt(ctx, Resolver(brand, {}, {}), "# Empty custom art direction\n")


@pytest.mark.parametrize(("owner", "seed"), [
    ("CompleteTech-Skills", "1025"), ("AI-Ascension", None), ("Jev-Engineering", "3001"),
    ("jevplay-games", "3101"), ("LibreEvolve", "4001"), ("TouchedByAnAgent", "5001"),
    ("romgenie-archive-repostiory", "6001")])
def test_bundled_prompt_has_a_valid_seed_instruction(owner, seed, brand, make_ctx):
    from ctshowcase.resolver import Resolver

    result = C.icon_prompt(make_ctx(owner=owner), Resolver(brand, {}, {}), C.load_art_direction())
    expected = f"Use seed {seed} when supported." if seed else "Use the tool's default seed."
    assert expected in result["prompt"]
    assert "seed not set" not in result["prompt"]


@pytest.mark.parametrize("missing", [("icon_ink",), ("icon_spark",), ("icon_ink", "icon_spark")])
def test_legacy_config_keeps_normalize_and_check_usable(missing, brand, tmp_path, capsys):
    import yaml
    from ctshowcase.config import schema_errors

    raw = copy.deepcopy(brand.raw)
    for family in [raw["defaults"], *raw["families"].values()]:
        for token in missing:
            family.get("tokens", {}).pop(token, None)
    assert schema_errors(raw) == []
    config = tmp_path / "legacy-brand.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    source, output = tmp_path / "candidate.png", tmp_path / "icon.png"
    glyph_image(brand.style("Northwind-Trading-Co")["tokens"]["icon_ink"]).save(source)
    common = ["--config", str(config), "--meta", str(meta), "--no-repo-dir", "content", "icon"]
    for action, extra in (("normalize", ["--in", str(source)]), ("check", [])):
        assert C.main([*common, action, "--out", str(output), *extra]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["result"] == "pass"
        assert "needs-input:icon-palette" in result["logs"]
        assert not any(cell["check"] == "family-ink" for cell in result["qa"]["checks"])
    assert C.main([*common, "prompt"]) == 4
    result = json.loads(capsys.readouterr().out)
    assert result["logs"] == ["needs-input:icon-palette"]
    assert all(token in result["error"] for token in missing)
    # Explicit estate-format palettes continue to work with the same valid legacy config.
    assert C.main([*common, "prompt", "--art-direction", str(ROOT / "tests/fixtures/content/ART_DIRECTION.min.md")]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["result"] == "needs-writer"


@pytest.mark.parametrize("explicit_art_direction", [False, True])
def test_legacy_config_option_b_does_not_require_glyph_inks(explicit_art_direction, brand, tmp_path):
    import yaml
    from ctshowcase.config import schema_errors

    raw = copy.deepcopy(brand.raw)
    for family in [raw["defaults"], *raw["families"].values()]:
        for token in ("icon_ink", "icon_spark"):
            family.get("tokens", {}).pop(token, None)
    assert schema_errors(raw) == []
    config, meta = tmp_path / "legacy-brand.yaml", tmp_path / "meta.json"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    glyph, output = tmp_path / "glyph.json", tmp_path / "prompt.md"
    glyph.write_text(json.dumps({"subject": "A tray holding an envelope.", "objects": "A tray and envelope."}),
                     encoding="utf-8")
    args = [sys.executable, str(ROOT / "scripts/showcase.py"), "--config", str(config), "--meta", str(meta),
            "--no-repo-dir", "content", "icon", "prompt", "--option", "B", "--glyph", str(glyph),
            "--out", str(output)]
    if explicit_art_direction:
        args += ["--art-direction", str(C.SKILL_ART_DIRECTION)]
    proc = subprocess.run(args, capture_output=True)
    assert proc.returncode == 0, proc.stdout.decode("utf-8", errors="replace")
    result = json.loads(proc.stdout.decode("utf-8"))
    assert result["result"] == "ok" and result["missing"] == []
    assert "A tray holding an envelope." in output.read_text(encoding="utf-8")
