"""Projects boards take the operator's account, reference board, template and Estate wording from the brand config."""
import copy

import pytest

from conftest import ROOT
from ctshowcase import project as PJ
from ctshowcase.config import Brand, load_brand
from ctshowcase.errors import NeedsInput
from ctshowcase.resolver import Resolver

VIEWS = {v["name"]: i + 1 for i, v in enumerate(PJ.VIEWS)}
EVIEWS = {v["name"]: i + 1 for i, v in enumerate(PJ.ESTATE_VIEWS)}


def _brand_without(*keys) -> Brand:
    base = load_brand()
    raw = copy.deepcopy(base.raw)
    for k in keys:
        raw["operator"].pop(k, None)
    return Brand(raw, base.path)


def test_no_estate_names_left_in_project_py():
    src = (ROOT / "scripts" / "ctshowcase" / "project.py").read_text(encoding="utf-8")
    for needle in ("CompleteDotTech", "CompleteTech-LLC", "CompleteTech Estate", "CompleteTech LLC initiatives",
                   "Timothy", "complete.tech", 'REFERENCE = ("Pick-Your-AI"'):
        assert needle not in src, needle


def test_our_config_keeps_our_values():
    assert PJ.is_user("CompleteDotTech") and PJ.is_user("@me") and not PJ.is_user("Jev-Engineering")
    text, logs = PJ.readme("@me", "CompleteTech Estate", 4, EVIEWS, estate=True, reviewed="2026-11-01")
    assert "rolls up CompleteTech LLC initiatives" in text and "https://github.com/CompleteDotTech" in text
    assert "needs-input:steward" not in logs


def test_board_readme_without_a_steward_leaves_the_contact_out():
    op = _brand_without("steward").operator()
    text, logs = PJ.readme("Northwind-Trading-Co", "Northwind Trading", 3, VIEWS, reviewed="2026-11-01", op=op)
    assert "Contact:" not in text and "needs-input:steward" in logs


def test_estate_readme_without_projects_config_is_needs_input():
    op = _brand_without("projects").operator()
    with pytest.raises(NeedsInput) as e:
        PJ.readme("@me", "Somebody Estate", 4, EVIEWS, estate=True, reviewed="2026-11-01", op=op)
    assert e.value.log == "needs-input:projects-estate-purpose"


def test_copy_plan_without_projects_config_borrows_nothing():
    b = _brand_without("projects")
    r = Resolver(b, {}, None)
    b._resolver = r
    with pytest.raises(NeedsInput) as e:
        PJ.copy_plan("Northwind-Trading-Co", role="org", resolver=r)
    assert e.value.log == "needs-input:projects-reference"
    with pytest.raises(NeedsInput) as e:
        PJ.copy_plan("Northwind-Trading-Co", role="template", source="Northwind-Trading-Co/7", resolver=r)
    assert e.value.log == "needs-input:projects-template-description"


def test_without_an_operator_login_only_at_me_is_the_user():
    assert PJ.is_user("@me", "") and not PJ.is_user("CompleteDotTech", "")
    with pytest.raises(NeedsInput) as e:
        PJ.project_url("@me", 4, "")
    assert e.value.log == "needs-input:operator-login"
    with pytest.raises(NeedsInput):
        PJ.capture_query("@me", 4, op={})
