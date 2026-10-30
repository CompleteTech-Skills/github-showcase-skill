"""Schema contract for the per-org `topics_extra` key (E5.1.2).

Tests that pass on the base too (valid list, empty list, key optional) are intentional regression guards for the accept path;
the reject-path tests are the ones that fail on the base.

Length and charset are enforced by the schema only; merge() ignores invalid entries defensively (see test_topics_additive.py).
"""
import json
from pathlib import Path

import pytest

from ctshowcase.schema import validate

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "brand.schema.json"


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _org_errors(schema, topics_extra):
    row = {"family": "CompleteTech-Skills", "tier": "T1", "display_name": "CompleteTech Skills", "topics_extra": topics_extra}
    return validate(row, schema["$defs"]["org"], schema, "$")


def test_valid_list_is_accepted(schema):
    assert _org_errors(schema, ["security", "a", "x-y-9", "a" * 50]) == []


def test_empty_list_is_accepted(schema):
    assert _org_errors(schema, []) == []


def test_uppercase_entry_is_rejected(schema):
    assert _org_errors(schema, ["Security"])


def test_51_char_entry_is_rejected(schema):
    assert _org_errors(schema, ["a" * 51])


def test_entry_with_space_is_rejected(schema):
    assert _org_errors(schema, ["two words"])


def test_non_list_is_rejected(schema):
    assert _org_errors(schema, "security")


def test_more_than_20_entries_is_rejected(schema):
    assert _org_errors(schema, [f"t{i}" for i in range(21)])


def test_topics_extra_is_optional(schema):
    row = {"family": "CompleteTech-Skills", "tier": "T1", "display_name": "CompleteTech Skills"}
    assert validate(row, schema["$defs"]["org"], schema, "$") == []


def test_trailing_newline_is_rejected(schema):
    # Python's `$` matches before a final newline; the schema uses (?![\s\S]) so the charset check is strict
    assert _org_errors(schema, ["leaderboard\n"])
    assert _org_errors(schema, ["a" * 50 + "\n"])
    assert _org_errors(schema, [""])
