import json

import pytest

from conftest import FIX, run_cli
from ctshowcase import doctor


def passing_cells():
    return dict.fromkeys(doctor.COLUMNS, "pass")


def test_owner_pending_does_not_hide_completed_skill_work():
    cells = passing_cells()
    cells.update(R2="fail", R3="warn", R5="unknown", R7="incomplete", R8="warn")
    assert doctor.completion(cells) == {"skill_complete": "yes", "owner_pending": ["R2", "R3", "R5", "R7", "R8"]}
    assert set(doctor.OWNER_COLUMNS).isdisjoint(doctor.SKILL_COLUMNS)
    assert set(doctor.OWNER_COLUMNS + doctor.SKILL_COLUMNS) == set(doctor.COLUMNS)


@pytest.mark.parametrize("column", doctor.SKILL_COLUMNS)
@pytest.mark.parametrize("status", ["warn", "incomplete", "fail", "hold", "unknown"])
def test_local_output_must_actually_pass(column, status):
    cells = passing_cells()
    cells[column] = status
    assert doctor.completion(cells)["skill_complete"] == "no"


def test_non_applicable_surfaces_do_not_block_completion():
    cells = passing_cells()
    cells.update(dict.fromkeys(doctor.SKILL_COLUMNS, "n/a"))
    assert doctor.completion(cells) == {"skill_complete": "yes", "owner_pending": []}
    assert doctor.completion({})["skill_complete"] == "no"


def test_all_formats_report_the_same_verdict(make_ctx):
    row = doctor.row(make_ctx())
    header, values = doctor.as_tsv(row, header=True).splitlines()
    tsv = dict(zip(header.split("\t"), values.split("\t")))
    assert tsv["skill_complete"] == row["skill_complete"] == "no"
    assert tsv["owner_pending"].split(",") == row["owner_pending"]
    md = doctor.as_md(row, header=True)
    assert "| skill_complete | owner_pending |" in md
    assert ",".join(row["owner_pending"]) in md


def test_cli_json_keeps_done_and_lists_owner_cells():
    proc = run_cli("--meta", FIX / "CompleteTech-Skills__agentic-email-skill.json", "--no-repo-dir", "doctor", "--format", "json")
    row = json.loads(proc.stdout)
    assert row["done"] == "no" and row["skill_complete"] == "no"
    assert "R7" in row["owner_pending"]
    assert isinstance(row["owner_pending"], list)


def test_unmeasured_flag_accepts_existing_output_audit():
    args = ("--meta", FIX / "CompleteTech-Skills__agentic-email-skill.json", "--no-repo-dir", "doctor", "--format", "json")
    normal = run_cli(*args)
    allowed = run_cli(*args, "--allow-unmeasured")
    assert allowed.returncode == normal.returncode
    assert json.loads(allowed.stdout) == json.loads(normal.stdout)
