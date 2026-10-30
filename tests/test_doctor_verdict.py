"""Task #120: skill-controlled vs owner-controlled split of doctor cells (E6.4.1). Synthetic values only; no I/O."""
from ctshowcase import doctor


OWNER_IDS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R10", "R11"]


def test_cell_lists_partition_columns():
    assert doctor.SKILL_CELLS == ["R9", "banner", "icon", "card", "footer"]
    assert doctor.OWNER_CELLS == OWNER_IDS
    assert sorted(doctor.SKILL_CELLS + doctor.OWNER_CELLS) == sorted(doctor.COLUMNS)
    assert len(set(doctor.SKILL_CELLS) & set(doctor.OWNER_CELLS)) == 0
    # OWNER_CELLS keeps COLUMNS order
    assert doctor.OWNER_CELLS == [c for c in doctor.COLUMNS if c in doctor.OWNER_CELLS]


def test_empty_dict_is_no_and_all_owner_pending():
    assert doctor.verdict({}) == ("no", OWNER_IDS)


def test_all_pass_is_yes_and_nothing_pending():
    cells = {c: "pass" for c in doctor.COLUMNS}
    assert doctor.verdict(cells) == ("yes", [])


def test_skill_values_pass_warn_na_are_complete():
    cells = {c: "pass" for c in doctor.COLUMNS}
    cells["banner"] = "warn"
    cells["icon"] = "n/a"
    cells["card"] = "n/a"
    assert doctor.verdict(cells)[0] == "yes"


def test_banner_incomplete_is_not_skill_complete():
    cells = {c: "pass" for c in doctor.COLUMNS}
    cells["banner"] = "incomplete"
    assert doctor.verdict(cells)[0] == "no"


def test_each_non_done_value_makes_skill_incomplete():
    for bad in ("incomplete", "fail", "unknown", "hold"):
        cells = {c: "pass" for c in doctor.COLUMNS}
        cells["footer"] = bad
        assert doctor.verdict(cells)[0] == "no", bad


def test_missing_skill_key_is_no():
    cells = {c: "pass" for c in doctor.COLUMNS if c != "card"}
    assert doctor.verdict(cells)[0] == "no"


def test_missing_owner_key_is_pending_in_order():
    cells = {c: "pass" for c in doctor.COLUMNS}
    del cells["R7"]
    del cells["R1"]
    assert doctor.verdict(cells) == ("yes", ["R1", "R7"])


def test_owner_pending_values_and_order():
    cells = {c: "pass" for c in doctor.COLUMNS}
    cells.update({"R11": "hold", "R2": "fail", "R5": "unknown", "R8": "incomplete", "R3": "warn", "R4": "n/a",
                  "R10": "pass", "footer": "fail"})
    skill, pending = doctor.verdict(cells)
    assert skill == "no"
    assert pending == ["R2", "R5", "R8", "R11"]


def test_pass_warn_na_are_not_pending():
    cells = {c: "warn" for c in doctor.COLUMNS}
    cells.update({c: "n/a" for c in OWNER_IDS})
    assert doctor.verdict(cells) == ("yes", [])
