"""Literal math after an owned hero must retain its original raw HTML context."""
import pytest
from types import SimpleNamespace

from test_personal_hero_badge_urls import generated as generated
from test_personal_hero_guard_paths import atomic_intro_order, checkout
from test_personal_hero_html_tokens import (
    test_owned_hero_move_keeps_plain_tokens_in_their_original_html_context as exercise_context,
)
from test_personal_hero_url_authority import offline_cli as offline_cli
from test_personal_hero_order import snapshot


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("payload", [pytest.param(b"Authored $x+1$.", id="inline-math"),
                                    pytest.param(b"$$\nx + y\n$$", id="block-math")])
def test_owned_hero_move_keeps_math_literal(tmp_path, generated, mode, payload):
    # The shared acceptance oracle checks original raw-HTML containment, then
    # atomic refusal or exact payload/context preservation and byte idempotence.
    exercise_context(tmp_path, generated, mode, payload)


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
def test_math_refusal_precedes_requested_formatter(tmp_path, generated, mode, monkeypatch, capsys):
    import showcase

    source = generated["legacy_hero"].encode() + b" Authored $x+1$.\n\nAuthored tail.\n"
    meta = checkout(tmp_path, source, generated["intro"])
    before = snapshot(tmp_path)

    def unexpected_formatter(*_args, **_kwargs):
        raise AssertionError("Unsafe math relocation reached the formatter")

    monkeypatch.setattr("ctshowcase.formatting.format_text", unexpected_formatter)
    code = showcase.main(["--format", "json", "--meta", str(meta), "--repo-dir", str(tmp_path),
                          "readme", "--mode", mode, "--variant", "J", "--badges", "local",
                          "--records", str(tmp_path / "records.jsonl"), "--write", "--format-generated"])
    output = capsys.readouterr()
    atomic_intro_order(SimpleNamespace(returncode=code, stdout=output.out, stderr=output.err), tmp_path, before)
