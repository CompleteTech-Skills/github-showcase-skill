"""Operator-provided fact chips use the same source and validation on every surface."""
import json

import pytest

from ctshowcase import banner, card, chips, social
from ctshowcase.errors import ArtFail, ConfigError
from conftest import meta_dict, run_cli


def test_explicit_chips_match_across_surfaces(make_ctx, fonts):
    ctx = make_ctx()
    keys, attrs = ["API"], ["Fast"]
    _, b = banner.layout(ctx, fonts, keys=keys, attrs=attrs)
    _, c = card.layout(ctx, fonts, keys=keys, attrs=attrs)
    _, s = social.social_layout(ctx, fonts, keys=keys, attrs=attrs)
    assert [x["text"] for x in b["chips"]] == keys + attrs
    assert [x["label"] for x in c["items"]] == keys + attrs
    assert [x["label"] for x in s["chips"]] == keys + attrs
    assert all(x["source"] == "cli" for x in s["chips"])


@pytest.mark.parametrize("keys,attrs", [([""], ["Fast"]), (["line\nbreak"], None), (["1", "2", "3"], None),
                                        (["1", "2"], ["3", "4", "5"])])
def test_chip_input_validation_shared(make_ctx, keys, attrs):
    with pytest.raises(ConfigError):
        chips.derive(make_ctx(), keys, attrs)


def test_banner_subtitle_without_description(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(description="")), encoding="utf-8")
    checkout = tmp_path / "repo"
    (checkout / ".github").mkdir(parents=True)
    (checkout / ".github/showcase.yml").write_text("subtitle: Run the Northwind service.\n", encoding="utf-8")
    out = tmp_path / "banner.png"
    p = run_cli("--meta", meta, "--repo-dir", checkout, "--format", "json", "banner", "--out", out,
                "--key-chip", "API", "--chip", "Fast")
    assert p.returncode == 0, p.stdout + p.stderr
    result = json.loads(p.stdout)
    assert result["subtitle"] == "Run the Northwind service."
    assert "description-missing" in result["logs"]
    assert out.is_file()


@pytest.mark.parametrize("command", [("card",), ("content", "social")])
def test_chip_cli_inputs(command, tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    p = run_cli("--meta", meta, "--no-repo-dir", "--format", "json", *command,
                "--key-chip", "API", "--chip", "Fast", "--out", tmp_path / ("card.svg" if command[0] == "card" else "social.png"))
    assert p.returncode == 0, p.stdout + p.stderr
    result = json.loads(p.stdout)
    values = result.get("items", result.get("chips"))
    assert [x["label"] for x in values] == ["API", "Fast"]


def test_card_never_silently_discards_explicit_chips(make_ctx, fonts):
    with pytest.raises(ArtFail, match="card-chips"):
        card.layout(make_ctx(), fonts, keys=["API"], attrs=["Far too wide to fit in this card " * 5] )


def test_missing_description_and_subtitle_still_needs_input(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(description="")), encoding="utf-8")
    out = tmp_path / "banner.png"
    p = run_cli("--meta", meta, "--no-repo-dir", "--format", "json", "banner", "--out", out)
    assert p.returncode == 4, p.stdout + p.stderr
    assert "needs-input:description" in p.stdout + p.stderr
    assert not out.exists()
