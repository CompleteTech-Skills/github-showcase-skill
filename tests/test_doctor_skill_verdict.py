"""Task #121: opt-in skill_complete / owner_pending columns on doctor output (E6.4.2). Synthetic values only."""
import json

from conftest import FIX, run_cli
from ctshowcase import doctor


def _row(**extra):
    cells = {c: "pass" for c in doctor.COLUMNS}
    r = {"repo": "octo/example", "type": "agent-skills", "variant": "plain", "cells": cells, "done": "yes", "logs": []}
    r.update(extra)
    return r


def test_default_row_has_no_verdict_keys_and_base_columns():
    r = _row()
    assert doctor.as_tsv(r, header=True) == (
        "owner/repo\ttype\tvariant\t" + "\t".join(doctor.COLUMNS) + "\tdone\n"
        "octo/example\tagent-skills\tplain\t" + "\t".join(["pass"] * len(doctor.COLUMNS)) + "\tyes")
    assert "skill_complete" not in doctor.as_md(_row(), header=True)


def test_tsv_with_verdict_keys_appends_two_columns_after_done():
    r = _row(skill_complete="no", owner_pending=["R2", "R5"])
    head, line = doctor.as_tsv(r, header=True).split("\n")
    assert head.split("\t")[-3:] == ["done", "skill_complete", "owner_pending"]
    assert line.split("\t")[-3:] == ["yes", "no", "R2,R5"]


def test_tsv_empty_owner_pending_is_dash():
    line = doctor.as_tsv(_row(skill_complete="yes", owner_pending=[]))
    assert line.split("\t")[-2:] == ["yes", "-"]


def test_md_with_verdict_keys_appends_two_columns_after_done():
    r = _row(skill_complete="yes", owner_pending=[])
    head, sep, line = doctor.as_md(r, header=True).split("\n")
    assert head.endswith("| done | skill_complete | owner_pending |")
    assert sep.count("---|") == 3 + len(doctor.COLUMNS) + 1 + 2  # owner/repo, type, variant, cells, done, two verdict columns
    assert line.endswith("| yes | yes | - |")


def test_row_signature_accepts_skill_verdict():
    import inspect
    p = inspect.signature(doctor.row).parameters["skill_verdict"]
    assert p.default is False


def test_cli_flag_adds_columns_to_json_with_two_extra_keys():
    meta = FIX / "CompleteTech-Skills__agentic-email-skill.json"
    base = json.loads(run_cli("--meta", meta, "--no-repo-dir", "doctor", "--format", "json").stdout)
    p = run_cli("--meta", meta, "--no-repo-dir", "doctor", "--format", "json", "--skill-verdict")
    r = json.loads(p.stdout)
    assert (r["skill_complete"], r["owner_pending"]) == doctor.verdict(r["cells"])
    assert {k: v for k, v in r.items() if k not in ("skill_complete", "owner_pending")} == base
    assert list(r)[-2:] == ["skill_complete", "owner_pending"]


def test_cli_without_flag_output_is_unchanged():
    meta = FIX / "CompleteTech-Skills__agentic-email-skill.json"
    p = run_cli("--meta", meta, "--no-repo-dir", "doctor", "--header")
    head, row = p.stdout.strip().splitlines()
    assert head.split("\t")[-1] == "done"
    assert len(row.split("\t")) == len(head.split("\t"))


def test_cli_flag_tsv_header_and_row_agree():
    meta = FIX / "CompleteTech-Skills__agentic-email-skill.json"
    p = run_cli("--meta", meta, "--no-repo-dir", "doctor", "--header", "--skill-verdict")
    head, row = p.stdout.strip().splitlines()
    assert head.split("\t")[-3:] == ["done", "skill_complete", "owner_pending"]
    assert len(row.split("\t")) == len(head.split("\t"))
