"""The installed skill's icon defaults work without the private estate bundle."""
import json
import re
from pathlib import Path
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


GLYPH = {"glyph_name": "Inbox Tray", "glyph_description": "An open tray seen front-on.",
         "spark_placement": "held inside the tray", "size_class": "wide", "subject": "an inbox tray",
         "objects": "a tray and a card"}


@pytest.mark.parametrize("option", ["A", "B"])
@pytest.mark.parametrize("owner", ["CompleteTech-Skills", "AI-Ascension", "Jev-Engineering", "romgenie-archive-repostiory"])
def test_prompt_asks_for_one_image_and_asserts_no_seed_by_default(option, owner, brand, make_ctx):
    from ctshowcase.resolver import Resolver

    art = (C.SKILL_ART_DIRECTION.read_text(encoding="utf-8") if option == "B" else None)
    result = C.icon_prompt(make_ctx(owner=owner), Resolver(brand, {}, {}), C.load_art_direction(), GLYPH, option,
                           skill_art=art)
    p = result["prompt"]
    assert "Produce one image." in p
    assert "four candidates" not in p.lower() and "when supported" not in p and "seed" not in p.lower()
    assert result["requested"] == {"images": 1, "seed": "not supported"}
    md = C.prompt_markdown(result)
    assert "- Requested: 1 image; seed: not supported." in md


@pytest.mark.parametrize("option", ["A", "B"])
def test_requested_seed_is_in_the_prompt_and_provenance(option, brand, make_ctx):
    from ctshowcase.resolver import Resolver

    art = (C.SKILL_ART_DIRECTION.read_text(encoding="utf-8") if option == "B" else None)
    result = C.icon_prompt(make_ctx(owner="CompleteTech-Skills"), Resolver(brand, {}, {}), C.load_art_direction(),
                           GLYPH, option, skill_art=art, seed=4242)
    assert "Produce one image. Use seed 4242." in result["prompt"]
    assert "- Requested: 1 image; seed: 4242." in C.prompt_markdown(result)


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


@pytest.mark.parametrize("option", ["A", "B"])
def test_synthetic_legacy_template_via_override_still_asks_for_one_image(option, brand, make_ctx):
    """The fixture is a minimal synthetic legacy template that imitates the pre-#61 'Produce four candidates.' syntax
    and is not a production snapshot. As an explicit --art-direction override it must not leave the prompt requesting
    four while provenance records one image."""
    from ctshowcase.resolver import Resolver

    legacy = (Path(__file__).parent / "fixtures" / "content" / "ART_DIRECTION.synthetic-legacy.md").read_text(encoding="utf-8")
    assert "Produce four candidates." in legacy
    assert len(legacy.splitlines()) < 80
    assert legacy.count("Produce four candidates.") == 1
    assert not any(token in legacy for token in ("jev-reference", "jevplay", "AI Ascension", "Jev-Engineering", "#00A7FD", "1025")), \
        "the fixture must stay synthetic"
    result = C.icon_prompt(make_ctx(owner="CompleteTech-Skills"), Resolver(brand, {}, {}), legacy, GLYPH, option,
                           skill_art=(legacy if option == "B" else None))
    assert "four candidates" not in result["prompt"].lower()
    assert "Produce one image." in result["prompt"]
    assert "- Requested: 1 image; seed: not supported." in C.prompt_markdown(result)


def test_explicit_seed_is_requested_even_when_a_custom_template_has_no_seed_placeholder(brand, make_ctx):
    """A custom --art-direction without {SEED}/{SEED_INSTRUCTION} must still carry a seed that provenance records."""
    from ctshowcase.resolver import Resolver

    art = C.load_art_direction()
    art = re.sub(r"[^\n]*\{SEED(?:_INSTRUCTION)?\}[^\n]*", "", art)
    result = C.icon_prompt(make_ctx(owner="CompleteTech-Skills"), Resolver(brand, {}, {}), art, GLYPH, "A", seed=4242)
    assert "seed 4242" in result["prompt"].lower()
    assert "- Requested: 1 image; seed: 4242." in C.prompt_markdown(result)
    plain = C.icon_prompt(make_ctx(owner="CompleteTech-Skills"), Resolver(brand, {}, {}), art, GLYPH, "A")
    assert "seed" not in plain["prompt"].lower()


def test_legacy_conditional_seed_clause_in_a_custom_template_is_normalised(brand, make_ctx):
    """'Use seed {SEED} when supported.' must not assert a seed (or 'not supported') the caller never requested."""
    from ctshowcase.resolver import Resolver

    art = C.load_art_direction()
    art = re.sub(r"[^\n]*\{SEED(?:_INSTRUCTION)?\}[^\n]*", "", art)
    art = art.rstrip() + "\n\nUse seed {SEED} when supported.\n"
    ctx = make_ctx(owner="CompleteTech-Skills")
    plain = C.icon_prompt(ctx, Resolver(brand, {}, {}), art, GLYPH, "A")
    assert "seed" not in plain["prompt"].lower()
    seeded = C.icon_prompt(ctx, Resolver(brand, {}, {}), art, GLYPH, "A", seed=4242)
    assert "Use seed 4242." in seeded["prompt"]
    assert "when supported" not in seeded["prompt"]
