"""Operator chip/subtitle facts must not be silently omitted by a successful CLI."""
import json

import pytest
import yaml

from conftest import meta_dict, run_cli
from ctshowcase import banner, card, chips
from ctshowcase.errors import ArtFail, ConfigError, NeedsInput


COMMANDS = [("banner",), ("card",), ("content", "social"), ("social-preview",)]


def target(tmp_path, override, **metadata):
    checkout = tmp_path / "checkout"
    (checkout / ".github").mkdir(parents=True)
    (checkout / ".github" / "showcase.yml").write_text(yaml.safe_dump(override), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(**metadata)), encoding="utf-8")
    return meta, checkout


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("source", ["cli-attrs", "config-attrs", "config-both"])
def test_count_overflow_combines_selected_sources_without_writing(tmp_path, command, source):
    config = {"chips": {"key": ["A", "B"]}}
    flags = ["--chip", "C", "--chip", "D", "--chip", "E"]
    if source != "cli-attrs":
        config["chips"]["attrs"] = ["C", "D", "E"]
        flags = ["--key-chip", "A", "--key-chip", "B"] if source == "config-attrs" else []
    # Social's default layout intentionally uses a category instead of a chip
    # row. An explicit key opts into that row and selects configured attrs.
    if source == "config-both" and command in [("content", "social"), ("social-preview",)]:
        flags = ["--key-chip", "A", "--key-chip", "B"]
    meta, checkout = target(tmp_path, config)
    out = tmp_path / ("card.svg" if command == ("card",) else "surface.png")
    out.write_bytes(b"existing operator output")
    before = out.read_bytes()

    result = run_cli("--meta", meta, "--repo-dir", checkout, "--format", "json", *command, *flags, "--out", out)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "at most four fact chips" in result.stdout + result.stderr
    assert out.read_bytes() == before
    assert not (checkout / "docs" / "images" / ".showcase.json").exists()


def test_inferred_keys_cannot_silently_trim_explicit_attributes(make_ctx):
    ctx = make_ctx(description="Check CVE-2026-11111 and CVE-2026-22222.")
    with pytest.raises(ConfigError, match="at most four fact chips"):
        chips.derive(ctx, cli_attrs=["C", "D", "E"])


def test_automatic_attributes_keep_existing_priority_selection(make_ctx):
    ctx = make_ctx(description="Check CVE-2026-11111 and CVE-2026-22222.")
    derived_keys, derived_attrs = chips.derive(ctx)
    assert len(derived_keys) == 2
    assert derived_attrs == chips.attr_chips(ctx)[:2]
    assert all(source not in ("cli", "override") for _, source in derived_attrs)


@pytest.mark.parametrize("surface", ["banner", "card"])
def test_configured_width_overflow_preserves_operator_attributes(make_ctx, fonts, surface):
    ctx = make_ctx()
    ctx.override["chips"] = {"key": ["API"], "attrs": ["Wide operator fact " * 10]}
    renderer = banner.layout if surface == "banner" else card.layout
    with pytest.raises(ArtFail, match="chips"):
        renderer(ctx, fonts)


@pytest.mark.parametrize("description", ["", "Run the Northwind triage agent."])
@pytest.mark.parametrize("source", ["cli", "config"])
@pytest.mark.parametrize("blank", ["", " \t "])
def test_blank_selected_subtitle_refuses_before_output(tmp_path, description, source, blank):
    override = {"subtitle": blank if source == "config" else "Valid configured fallback."}
    meta, checkout = target(tmp_path, override, description=description)
    flags = ["--subtitle", blank] if source == "cli" else []
    out = tmp_path / "banner.png"
    out.write_bytes(b"existing operator output")

    result = run_cli("--meta", meta, "--repo-dir", checkout, "--format", "json", "banner",
                     *flags, "--key-chip", "API", "--chip", "Fast", "--out", out)

    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:subtitle" in result.stdout + result.stderr
    assert out.read_bytes() == b"existing operator output"
    assert not (checkout / "docs" / "images" / ".showcase.json").exists()


def test_direct_banner_layout_rejects_blank_selected_subtitle(make_ctx, fonts):
    with pytest.raises(NeedsInput, match="nonempty single-line"):
        banner.layout(make_ctx(description=""), fonts, subtitle="   ", keys=["API"], attrs=["Fast"])


def test_valid_cli_subtitle_overrides_unused_blank_config(tmp_path):
    meta, checkout = target(tmp_path, {"subtitle": "   "}, description="")
    out = tmp_path / "banner.png"
    result = run_cli("--meta", meta, "--repo-dir", checkout, "--format", "json", "banner", "--out", out,
                     "--subtitle", "Run the Northwind service.", "--key-chip", "API", "--chip", "Fast")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["subtitle"] == "Run the Northwind service."
    assert payload["subtitle_source"] == "cli"
    assert "description-missing" in payload["logs"]
    assert out.is_file()


def test_invalid_unused_config_is_not_a_rendering_fallback(make_ctx):
    ctx = make_ctx()
    ctx.override["subtitle"] = "First line\nSecond line"
    candidates = banner.subtitle_candidates(ctx, "Valid CLI text.")
    assert candidates[0] == ("Valid CLI text.", "cli")
    assert all(source != "override" for _, source in candidates)
    assert all(text.strip() and "\n" not in text and "\r" not in text for text, _ in candidates)


@pytest.mark.parametrize("command", [("card",), ("content", "social"), ("social-preview",)])
def test_valid_combined_chips_all_survive(tmp_path, command):
    meta, checkout = target(tmp_path, {"chips": {"key": ["A", "B"]}})
    out = tmp_path / ("card.svg" if command == ("card",) else "social.png")
    result = run_cli("--meta", meta, "--repo-dir", checkout, "--format", "json", *command,
                     "--chip", "C", "--chip", "D", "--out", out)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert [item["label"] for item in payload.get("items", payload.get("chips"))] == ["A", "B", "C", "D"]
