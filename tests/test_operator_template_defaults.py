"""Repository-template and README ownership defaults come from the selected brand config, never another operator's."""
import copy
import json

import pytest

from conftest import ROOT, meta_dict, run_cli
from ctshowcase import intake, readme
from ctshowcase.config import Brand, load_brand
from ctshowcase.context import RepoContext
from ctshowcase.detect import variant_for
from ctshowcase.errors import NeedsInput
from ctshowcase.meta import normalize

OUTSIDE = "octocat-labs"
SHIPPED_TEMPLATE = "CompleteTech-LLC/completetech-repo-template"


def _without_operator() -> Brand:
    base = load_brand()
    raw = copy.deepcopy(base.raw)
    raw.pop("operator", None)
    return Brand(raw, base.path)


def _ctx(b: Brand, owner: str, **kw) -> RepoContext:
    return RepoContext(b, normalize(meta_dict(owner=owner, repo="sample-skill", **kw)), None)


def test_no_estate_names_left_in_the_c1_modules():
    for rel, needle in (("scripts/ctshowcase/intake.py", "CompleteTech"), ("scripts/ctshowcase/doctor.py", "CompleteTech-Skills"),
                        ("scripts/ctshowcase/detect.py", "CompleteTech-Skills"), ("scripts/showcase.py", SHIPPED_TEMPLATE)):
        assert needle not in (ROOT / rel).read_text(encoding="utf-8"), rel
    src = (ROOT / "scripts" / "ctshowcase" / "readme.py").read_text(encoding="utf-8")
    for needle in ("@CompleteDotTech", "CompleteTech Repo Template", "CompleteTech LLC Skills"):
        assert needle not in src, needle


def test_estate_owner_keeps_the_shipped_template(brand):
    assert intake.default_template(brand, "CompleteTech-Skills") == SHIPPED_TEMPLATE


def test_outside_owner_needs_its_own_template(brand):
    with pytest.raises(NeedsInput) as e:
        intake.default_template(brand, OUTSIDE)
    assert e.value.log == "needs-input:template"


def test_config_without_operator_names_no_template():
    with pytest.raises(NeedsInput) as e:
        intake.default_template(_without_operator(), "CompleteTech-Skills")
    assert e.value.log == "needs-input:template"
    assert readme.template_titles(_without_operator()) == set()
    assert readme.template_owner(_without_operator()) is None


def test_new_for_an_outside_owner_exits_4_without_a_template(tmp_path):
    p = run_cli("--format", "json", "new", f"{OUTSIDE}/sample-cli", "--type", "cli")
    assert p.returncode == 4, p.stdout + p.stderr
    assert "needs-input:template" in p.stdout
    assert SHIPPED_TEMPLATE not in p.stdout


def test_new_for_an_outside_owner_with_its_own_template(tmp_path):
    p = run_cli("--format", "json", "new", f"{OUTSIDE}/sample-cli", "--type", "cli",
                "--template", f"{OUTSIDE}/repo-template")
    out = json.loads(p.stdout)
    assert out["template"] == f"{OUTSIDE}/repo-template"
    assert "CompleteTech" not in json.dumps(out["jobs"][0])


def test_ownership_line(brand):
    assert readme.section_facts(_ctx(brand, "CompleteTech-Skills"), "Ownership") == \
        "Owner: @CompleteDotTech · Organization: CompleteTech-Skills"
    assert readme.section_facts(_ctx(brand, OUTSIDE), "Ownership") == f"Organization: {OUTSIDE}"


def test_skills_library_flag_drives_variant_and_nav(brand):
    assert variant_for("agent-skills", {"owner": "CompleteTech-Skills"}) == "A"
    assert variant_for("agent-skills", {"owner": OUTSIDE}) == "C"
    assert variant_for("agent-skills", {"owner": "CompleteTech-Skills"}, skill_library=False) == "C"
    assert "CompleteTech LLC Skills" not in readme.nav_line(_ctx(brand, OUTSIDE))
