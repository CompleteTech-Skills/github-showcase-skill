"""The installed skill's icon defaults work without the private estate bundle."""
import json

import pytest
from conftest import ROOT, meta_dict

from ctshowcase import content as C
from ctshowcase.errors import NeedsInput


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
