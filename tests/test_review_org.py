"""Review regressions for the org module (PR #1 review comments 4373670972 and 4373670975).
Synthetic Northwind registry and metadata only (tests/fixtures/org)."""
import copy
import json

import pytest

from conftest import ROOT

from ctshowcase import org as O
from ctshowcase.config import Brand, load_yaml_text
from ctshowcase.errors import CHECK_FAILED, OK
from ctshowcase.resolver import Resolver

FIX = ROOT / "tests" / "fixtures" / "org"
N, L = "Northwind-Trading-Co", "Northwind-Labs"
PRIVATE_FAV = f"{L}/private-metrics-engine"   # synthetic: a private repository of another estate org
UNKNOWN_FAV = f"{L}/unmeasured-prototype"     # synthetic: an estate repository with no captured metadata


@pytest.fixture
def labs_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][L] = dict(raw["orgs"][N], display_name="Northwind Labs", nav_name="Northwind Labs", eyebrow="LABS")
    return Brand(raw, brand.path)


def _registry(favorites=()):
    reg = load_yaml_text((FIX / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"][N]["favorites"] = list(reg["orgs"][N]["favorites"]) + [{"full_name": f} for f in favorites]
    return reg


def _estate(labs_brand, reg):
    approvals = {"rows": set(), "ids": set(), "answers": {}, "extra": [],
                 "actions": [{"id": "ren-901", "owner": N, "repo": "ledger", "action": "rename", "new_name": "order-ledger"}]}
    est = O.Estate(labs_brand, Resolver(labs_brand, reg, approvals))
    O.load_metas(FIX / "meta", est)
    est.add_meta({"owner": L, "repo": "private-metrics-engine", "visibility": "private",
                  "description": "Internal metrics for the Northwind demo."})
    return est


# ------------------------------------------------------------------------------------------- P1 favorites
def test_private_estate_favorite_stays_out_of_the_public_slice(labs_brand):
    est = _estate(labs_brand, _registry([PRIVATE_FAV, UNKNOWN_FAV, f"{L}/lab-notebook"]))
    data, logs = O.public_slice(est, N)
    assert PRIVATE_FAV not in data["favorites"]
    assert UNKNOWN_FAV not in data["favorites"]  # unknown visibility fails closed
    assert data["favorites"] == ["pallets/flask", f"{L}/lab-notebook"]  # outside and public estate favorites stay
    assert "favorite-dropped:private-or-unknown" in logs
    assert f"needs-input:favorite-visibility:{UNKNOWN_FAV}" in logs
    res, code = O.profile(est, N)
    assert code == OK and res["leaks"] == []
    # the favorite with no metadata is omitted, so the run is not `ok` until it is captured (fails closed)
    assert res["result"] == "incomplete"
    assert "private-metrics-engine" not in res["readme"] and "unmeasured-prototype" not in res["readme"]
    assert "private-metrics-engine" not in json.dumps(res["data"])


def test_exposure_estate_favorite_is_dropped(labs_brand):
    est = _estate(labs_brand, _registry([f"{L}/lab-notebook"]))
    est.flags = {f"{L}/lab-notebook".lower(): ["exposure"]}
    data, logs = O.public_slice(est, N)
    assert data["favorites"] == ["pallets/flask"] and "favorite-dropped:private-or-unknown" in logs


def test_leak_check_knows_private_repositories_of_other_estate_orgs(labs_brand):
    est = _estate(labs_brand, _registry([PRIVATE_FAV]))
    data, _ = O.public_slice(est, N)
    priv = O._private_names(est, N, data)
    assert PRIVATE_FAV in priv and f"{L}/secret-lab" in priv
    assert f"{L}/lab-notebook" not in priv  # public and listed
    # the README the unfiltered slice used to write (the favorite linked) is now a leak for profile and lint alike
    res, code = O.profile(est, N)
    assert code == OK
    text = res["readme"] + f"- [{PRIVATE_FAV}](https://github.com/{PRIVATE_FAV})\n"
    assert f"private-slug:{PRIVATE_FAV}" in O.leak_check(text, priv, [], set())
    scope, _ = O.estate_leak_scope(est, [N])
    assert f"private-slug:{PRIVATE_FAV}" in O.public_leaks(text, scope)
    assert O.public_leaks(res["readme"], scope) == []


# ------------------------------------------------------------------------------------- P2 file-list metadata
GH_FILES = ["CONTRIBUTING.md", "LICENSE", "README.md", "profile/README.md", "profile/assets/banner.jpg",
            ".github/ISSUE_TEMPLATE/config.yml"]


def _list_estate(labs_brand):
    """The .github capture as `meta --from-gh` writes it: `files` is the sorted list of every blob path."""
    est = _estate(labs_brand, _registry())
    raw = json.loads((FIX / "meta" / f"{N}__.github.json").read_text(encoding="utf-8"))
    raw["files"] = list(GH_FILES)
    raw["visibility"] = "public"
    est.add_meta(raw)
    return est


def test_health_reads_the_file_list_capture(labs_brand):
    res, code = O.health(_list_estate(labs_brand), N)
    assert res["source"] == "capture" and code == CHECK_FAILED
    c = res["cells"]
    assert c["CONTRIBUTING.md"] == c["LICENSE"] == c["profile/README.md"] == "pass"
    assert c["SECURITY.md"] == c["SUPPORT.md"] == "missing"  # a recursive tree lists every file: absent is missing
    assert c["issue forms"] == "pass"  # as with a checkout: a .yml under .github/ISSUE_TEMPLATE/
    assert "SECURITY.md" in res["add"] and "banner:missing" not in res["logs"]


def test_profile_and_kept_banner_read_the_file_list_capture(labs_brand):
    est = _list_estate(labs_brand)
    assert O._kept_banner(est, N) is None  # a path list has no README text to read a banner from
    res, code = O.profile(est, N)
    assert code == OK and res["leaks"] == []


def test_profile_retemplate_gate_sees_the_listed_profile_readme(labs_brand, tmp_path):
    res, _ = O.profile(_list_estate(labs_brand), N, out_dir=tmp_path)
    assert res["result"] == "needs-approval" and "needs-approval:profile-retemplate" in res["logs"]
    assert not (tmp_path / "profile" / "README.md").exists()


# ------------------------------------------------------------------------- round 2: star List follows the slice
def _lists():
    return json.loads((FIX / "star-lists-existing.json").read_text(encoding="utf-8"))


IDS = {"pallets/flask": "R_flask", f"{L}/lab-notebook": "R_nb", PRIVATE_FAV: "R_priv", UNKNOWN_FAV: "R_unk"}


def test_star_list_never_adds_a_private_or_unknown_estate_favorite(labs_brand):
    est = _estate(labs_brand, _registry([PRIVATE_FAV, UNKNOWN_FAV, f"{L}/lab-notebook"]))
    res = O.star_list_plan(est, N, lists_capture=_lists(), repo_ids=IDS)
    blob = json.dumps(res["items"]) + json.dumps(res["jobs"]) + json.dumps(res["pending"]) + json.dumps(res["reads"])
    assert res["items"] == ["pallets/flask", f"{L}/lab-notebook"]  # outside and public estate favorites stay
    assert "private-metrics-engine" not in blob and "R_priv" not in blob  # a public List never names it
    assert "unmeasured-prototype" not in json.dumps(res["jobs"]) and "R_unk" not in blob
    assert "favorite-dropped:private-or-unknown" in res["logs"]  # logged without the name
    assert not any("private-metrics-engine" in x for x in res["logs"])
    # unknown visibility fails closed and leaves the plan incomplete, as `org profile` does
    assert f"needs-input:favorite-visibility:{UNKNOWN_FAV}" in res["logs"] and res["result"] == "incomplete"
    # the items the slice keeps still leave as union jobs
    assert any('"R_nb"' in " ".join(j["argv"]) for j in res["jobs"])


def test_star_list_drops_an_exposure_favorite_and_create_pending_follows_the_slice(labs_brand):
    est = _estate(labs_brand, _registry([PRIVATE_FAV, f"{L}/lab-notebook"]))
    est.flags = {f"{L}/lab-notebook".lower(): ["exposure"]}
    lists = _lists()
    lists["data"]["viewer"]["lists"]["nodes"] = [n for n in lists["data"]["viewer"]["lists"]["nodes"] if n["id"] != "UL_nw"]
    res = O.star_list_plan(est, N, lists_capture=lists)
    assert res["items"] == ["pallets/flask"] and [p["item"] for p in res["pending"]] == ["pallets/flask"]
    assert res["result"] == "ok" and "favorite-dropped:private-or-unknown" in res["logs"]
    # pins carries the star List plan; its jobs never name a dropped favorite
    pins, _ = O.pins(est, N, lists_capture=lists)
    assert "private-metrics-engine" not in json.dumps(pins["star_list"]) and "lab-notebook" not in json.dumps(pins["star_list"]["items"])
