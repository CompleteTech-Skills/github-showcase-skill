"""Art-direction keys (palette rows, trademark additions, seeds) come only from the selected brand config."""
import copy

from conftest import ROOT, meta_dict
from ctshowcase import content as C
from ctshowcase.config import Brand, load_brand
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize
from ctshowcase.resolver import Resolver

SKILL_ART = (ROOT / "references" / "art-direction.md").read_text(encoding="utf-8")
ART = (ROOT / "tests" / "fixtures" / "content" / "ART_DIRECTION.min.md").read_text(encoding="utf-8")
GLYPH = {"GLYPH_NAME": "x", "GLYPH_DESCRIPTION": "y", "SPARK_PLACEMENT": "z", "SIZE_CLASS": "wide",
         "SUBJECT": "s", "OBJECTS": "o"}


def _brand_with(org: str, row: dict, family: dict | None = None) -> Brand:
    base = load_brand()
    raw = copy.deepcopy(base.raw)
    raw["orgs"][org] = row
    if family:
        raw["families"].update(family)
    return Brand(raw, base.path)


def _prompt(b: Brand, owner: str, option: str) -> str:
    ctx = RepoContext(b, normalize(meta_dict(owner=owner, repo="card-shop", description="Run the card shop.")), None)
    return C.icon_prompt(ctx, Resolver(b, {}, None), ART, GLYPH, option, skill_art=SKILL_ART)["prompt"]


def test_no_hard_coded_estate_tables_remain():
    src = (ROOT / "scripts" / "ctshowcase" / "content.py").read_text(encoding="utf-8")
    for leftover in ("ART_FAMILY", "ART_OWNER", "add_map", "CompleteTech palette", '"completetech": "CompleteTech"'):
        assert leftover not in src, leftover


def test_org_art_merges_family_then_org(brand):
    row = Resolver(brand, {}, None).brand_org("CompleteTech-Pokemon")
    art = C.org_art(brand, row, "completetech")
    assert art == {"palette": "CompleteTech core", "seed": "CompleteTech", "prompt_palette": "CompleteTech",
                   "additions": "TCG"}
    assert C.org_art(brand, brand.org("Synthetic-Outside-Owner"), "neutral") == {}


def test_external_family_without_art_borrows_none_of_ours():
    row = {"family": "northwind", "tier": "T1", "display_name": "Northwind Cards"}
    b = _brand_with("Northwind-Cards", row, {"northwind": {"company_label": "Northwind"}})
    prompt = _prompt(b, "Northwind-Cards", "B")
    assert "#FFC300" not in prompt and "Gold #FFC300" not in prompt
    assert "Poké" not in prompt


def test_external_family_with_its_own_art_keys_uses_them():
    row = {"family": "northwind", "tier": "T1", "display_name": "Northwind Cards", "art": {"additions": "TCG"}}
    b = _brand_with("Northwind-Cards", row, {"northwind": {"company_label": "Northwind"}})
    assert "No Pokémon creatures, Poké Balls or real card designs." in _prompt(b, "Northwind-Cards", "B")
