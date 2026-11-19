"""Offline CLI acceptance: raw HTML must not acquire hard breaks or email links."""
import json

import pytest

from ctshowcase import mdcode
from test_personal_hero_badge_urls import generated as generated
from test_personal_hero_guard_paths import atomic_intro_order, checkout, readme
from test_personal_hero_order import snapshot
from test_personal_hero_url_authority import offline_cli as offline_cli


PAYLOADS = [
    pytest.param(b"First line.  \nSecond line.", id="hard-break-LF"),
    pytest.param(b"First line.  \r\nSecond line.\rThird line.", id="hard-break-mixed-endings"),
    pytest.param(b"user@example.test", id="bare-email"),
]


def in_one_raw_html_block(source, payload):
    """Use the existing public source-aligned parse API, never its implementation."""
    text, literal = source.decode("utf-8"), payload.decode("utf-8")
    start = text.index(literal)
    end = start + len(literal)
    return any(a <= start and end <= b for a, b in mdcode.html_block_spans(text))


@pytest.mark.parametrize("mode", ["scaffold", "upgrade"])
@pytest.mark.parametrize("payload", PAYLOADS)
def test_owned_hero_move_keeps_plain_tokens_in_their_original_html_context(tmp_path, generated, mode, payload):
    hero = generated["legacy_hero"].encode("utf-8")
    suffix = b" Authored  preface.\t\n" + payload + b"\n\nAuthored  tail.\t\r\n"
    source = hero + suffix
    assert in_one_raw_html_block(source, payload), "Fixture payload must originally be literal raw HTML"
    meta = checkout(tmp_path, source, generated["intro"])
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode)

    if result.returncode == 4:
        atomic_intro_order(result, tmp_path, before)
        return
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / "README.md").read_bytes()
    problems = []
    if updated.count(suffix) != 1:
        problems.append("complete authored suffix bytes changed or duplicated")
    if updated.count(payload) != 1 or not in_one_raw_html_block(updated, payload):
        problems.append("authored payload left its original literal raw HTML context")
    if updated.count(b'src="assets/intro.svg"') != 1 or b"docs/images/banner.png" in updated:
        problems.append("expected one applicable intro and no legacy banner")
    before_retry = snapshot(tmp_path)
    retry = readme(tmp_path, meta, mode)
    if retry.returncode != 0 or snapshot(tmp_path) != before_retry:
        problems.append("successful retry changed the whole checkout snapshot")
    # Diagnostics contain synthetic payloads/flags only, never generated identity.
    assert not problems, json.dumps({"problems": problems, "mode": mode,
                                    "payload": payload.decode("utf-8"), "retry_exit": retry.returncode})
