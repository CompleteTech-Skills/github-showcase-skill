"""Org module: profile README from the public slice, About plan, pins and star Lists, labels, health and doctor.
Synthetic Northwind registry and metadata only (tests/fixtures/org)."""
import argparse
import copy
import json
import re

import pytest

from conftest import ROOT

from ctshowcase import org as O
from ctshowcase.config import Brand, load_yaml_text
from ctshowcase.errors import CHECK_FAILED, OK, Refused
from ctshowcase.resolver import Resolver

FIX = ROOT / "tests" / "fixtures" / "org"
N, L = "Northwind-Trading-Co", "Northwind-Labs"
PRIVATE = ("private-pricing-engine", "legacy-importer", "secret-lab")
ACTIONS = [{"id": "ren-901", "owner": N, "repo": "ledger", "action": "rename", "new_name": "order-ledger"}]


def approvals(rows=(), ids=()):
    return {"rows": set(rows), "ids": set(ids), "answers": {}, "actions": ACTIONS, "extra": []}


@pytest.fixture
def labs_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][L] = dict(raw["orgs"][N], display_name="Northwind Labs", nav_name="Northwind Labs", eyebrow="LABS")
    return Brand(raw, brand.path)


@pytest.fixture
def make_estate(labs_brand):
    def _make(rows=(), ids=(), registry=None):
        reg = registry or load_yaml_text((FIX / "registry.yaml").read_text(encoding="utf-8"))
        est = O.Estate(labs_brand, Resolver(labs_brand, reg, approvals(rows, ids)))
        assert O.load_metas(FIX / "meta", est) == 9
        return est
    return _make


# ----------------------------------------------------------------------------------------------- profile
def test_public_slice_never_holds_private_names(make_estate):
    data, logs = O.public_slice(make_estate(), N)
    blob = json.dumps(data)
    for name in PRIVATE:
        assert name not in blob
    assert [e["repo"] for e in data["featured"]] == ["support-triage-agent", "order-ledger"]
    assert [s["title"] for s in data["sections"]] == ["Agents", "Ledgers"]
    assert [e["repo"] for e in data["forks"]] == ["upstream-fork"] and [e["repo"] for e in data["archived"]] == ["inventory-sync"]
    assert [e["full_name"] for e in data["also_from"]] == [f"{L}/lab-notebook"]
    assert data["siblings"] == [{"login": L, "name": "Northwind Labs"}]
    assert data["star_list"]["name"] == "Northwind: built on"  # the reviewed profile entry wins
    assert data["star_list"]["url"].endswith("/lists/northwind-built-on")
    assert "featured-dropped:private-pricing-engine" in logs and "also-in-dropped:private-or-unknown" in logs
    assert "why" not in blob and "evidence" not in blob


def test_profile_readme_follows_the_kit(make_estate):
    res, code = O.profile(make_estate(), N)
    assert code == OK and res["result"] == "ok" and res["variant"] == "kit" and res["leaks"] == []
    text = res["readme"]
    order = [text.index(s) for s in ('<img src="https://raw.githubusercontent.com/Northwind-Trading-Co/.github/main/profile/'
                                     'assets/banner.jpg"', "Trading tools and support agents for the Northwind demo.",
                                     "## Featured", "## All projects", "### Agents", "### Forks", "### Archived",
                                     O.AS_IS_LINE, "## Also from CompleteTech", "## Favorites", "Contributing</a>",
                                     "<!-- showcase:footer:start -->")]
    assert order == sorted(order)
    assert text.rstrip().endswith("<!-- showcase:footer:end -->")
    assert "<picture>" in text and text.count("<picture>") == 1  # decision 18 footer only
    assert "img.shields.io" not in text and "github-readme-stats" not in text
    for name in PRIVATE:
        assert name not in text
    assert "explains the private pricing plan" not in text and "Test Steward" not in text
    assert "| [`support-triage-agent`](https://github.com/Northwind-Trading-Co/support-triage-agent) |" in text
    assert "| [`upstream-fork`](https://github.com/Northwind-Trading-Co/upstream-fork) | Fork of an upstream ticket parser. | — |" in text
    assert "[Northwind Labs](https://github.com/Northwind-Labs)" in text and "- [pallets/flask](https://github.com/pallets/flask)" in text
    badges = [a for a in res["assets"] if a["kind"] == "badge"]
    assert 3 <= len(badges) <= 5 and all(not re.search(r"#[0-9A-Fa-f]{6}", b["path"]) for b in badges)
    cards = [a["repo"] for a in res["assets"] if a["kind"] == "card"]
    assert cards == [f"{N}/support-triage-agent", f"{N}/order-ledger", f"{L}/lab-notebook"]
    assert "--no-repo-dir" in res["assets"][1]["argv"] and res["assets"][0]["kind"] == "org-banner"
    assert "<p>" in text and text.count('width="400"') == 3


def test_profile_private_variant(make_estate):
    reg = load_yaml_text((FIX / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"][L]["final_repos"] = [".github", "secret-lab"]
    reg["orgs"][L]["sections"] = []
    reg["orgs"][N]["also_in_incoming"] = []
    est = make_estate(registry=reg)
    res, code = O.profile(est, L)
    text = res["readme"]
    assert code == OK and res["variant"] == "private" and O.PRIVATE_LINE in text
    assert "## Featured" not in text and "## All projects" not in text and "## Favorites" not in text
    assert "secret-lab" not in text and text.rstrip().endswith("<!-- showcase:footer:end -->")


def test_profile_fails_closed_on_a_leak(make_estate):
    est = make_estate()
    est.metas[f"{N}/support-triage-agent".lower()]["description"] = "Uses Northwind-Trading-Co/private-pricing-engine."
    res, code = O.profile(est, N, out_dir="/nonexistent/never-written")
    assert code == CHECK_FAILED and res["result"] == "fail"
    assert "private-slug:Northwind-Trading-Co/private-pricing-engine" in res["leaks"] and "outputs" not in res


def test_leak_check_ignores_owner_positions_and_public_text():
    hits = O.leak_check("see https://github.com/acme-tools/x and `secret-tool-2`", {"acme/acme-tools", "acme/secret-tool-2"},
                        ["This internal sentence is long enough to be checked by the leak lint."], set(), {"acme"})
    assert hits == ["private-name:acme/secret-tool-2"]
    assert O.leak_check("Changelog for widget.ai-docs", {"acme/widget.ai"}, [], set()) == []
    assert O.leak_check("Product widget.ai is live.", {"acme/widget.ai"}, [], set(), public_texts=["Product widget.ai is live."]) == []
    assert O.leak_check("x", set(), ["This internal sentence is long enough to be checked by the leak lint."], set()) == []


def test_profile_writes_and_renders(make_estate, tmp_path):
    res, code = O.profile(make_estate(rows=[("profile-retemplate", N, "*", "")]), N, out_dir=tmp_path, render=True)
    assert code == OK
    assert (tmp_path / "profile" / "README.md").read_text(encoding="utf-8") == res["readme"]
    data = json.loads((tmp_path / "profile" / "data.json").read_text(encoding="utf-8"))
    assert data["org"] == N and "pins_members" not in data
    assert (tmp_path / "profile" / "assets" / "badges" / "website.svg").is_file()
    assert (tmp_path / "profile" / "assets" / "cards" / f"{N}__support-triage-agent.svg").read_text().startswith("<svg")
    assert (tmp_path / "profile" / "assets" / "banner.jpg").stat().st_size > 1000


def test_profile_never_references_a_card_it_cannot_render(make_estate, tmp_path):
    """Round-2 defect: a card that fails (art-fail, unmeasured palette) left a broken <img> on a profile marked ok."""
    est = make_estate(rows=[("profile-retemplate", N, "*", "")])
    est.metas[f"{L}/lab-notebook".lower()]["description"] = "Notebook " + "with a very long and winding explanation " * 9
    res, code = O.profile(est, N, out_dir=tmp_path, render=True)
    text = res["readme"]
    assert code == OK and res["result"] == "incomplete"
    assert any(x.startswith(f"card-fallback:{L}/lab-notebook:art-fail") for x in res["logs"])
    assert f"cards/{L}__lab-notebook.svg" not in text and f"- [`lab-notebook`](https://github.com/{L}/lab-notebook): " in text
    assert [a["repo"] for a in res["assets"] if a["kind"] == "card"] == [f"{N}/support-triage-agent", f"{N}/order-ledger"]
    for src in re.findall(r'src="https://raw\.githubusercontent\.com/[^/]+/\.github/main/profile/(assets/cards/[^"]+)"', text):
        assert (tmp_path / "profile" / src).is_file()


def test_profile_keep_existing_uses_the_kept_dark_banner(make_estate, labs_brand):
    """Round-2 defect: `banner: keep-existing` without --banner pointed the README at a banner.jpg that never exists."""
    labs_brand.raw["orgs"][N]["banner"] = "keep-existing"
    est = make_estate()
    gh = est.metas[f"{N}/.github".lower()]
    gh["files"]["profile/README.md"] = {"bytes": 300, "head": (
        '<picture>\n  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/'
        f'{N}/.github/main/profile/assets/banner-dark.svg">\n  <img src="https://raw.githubusercontent.com/{N}/.github/'
        'main/profile/assets/banner-light.svg" alt="x">\n</picture>\n')}
    res, code = O.profile(est, N)
    assert code == OK and res["result"] == "ok" and "banner:keep-existing:assets/banner-dark.svg" in res["logs"]
    assert f'src="https://raw.githubusercontent.com/{N}/.github/main/profile/assets/banner-dark.svg"' in res["readme"]
    assert "banner.jpg" not in res["readme"] and not [a for a in res["assets"] if a["kind"] in ("org-banner", "intro")]
    gh["files"]["profile/README.md"] = {"bytes": 10, "head": "# Northwind"}  # nothing to keep: no hero, needs-input
    res, code = O.profile(est, N)
    assert code == OK and res["result"] == "incomplete" and 'width="100%"' not in res["readme"]  # no hero image
    assert any(x.startswith("needs-input:banner") for x in res["logs"])


def test_profile_refuses_t3_and_excluded(make_estate):
    est = make_estate()
    with pytest.raises(Refused):
        O.profile(est, "Pick-Your-AI")
    with pytest.raises(Refused):
        O.profile(est, "MetatronAngelAgent")


# ----------------------------------------------------------------------------------------------- about
def test_about_payload_and_job(make_estate):
    res, code = O.about(make_estate(), N)
    assert code == OK and res["payload"] == {
        "name": "Northwind Trading Co.", "description": "Trading tools and support agents for the Northwind demo. A CompleteTech "
        "LLC organization.", "blog": "https://www.complete.tech", "location": "Cincinnati, OH", "twitter_username": "CompleteTechLLC"}
    j = res["jobs"][0]
    assert j["kind"] == "org-about" and j["org"] == N and j["phase"] == "1.2"
    assert j["argv"][:5] == ["gh", "api", "-X", "PATCH", f"orgs/{N}"] and "email" not in " ".join(j["argv"])
    assert res["verified_domain"]["reason"] == "email-blank" and "needs-approval:org-email" in res["logs"]


def test_about_email_only_when_approved_and_badge_condition(make_estate):
    res, _ = O.about(make_estate(rows=[("org-email", N, "*", "")]), N)
    assert res["payload"]["email"] == O.STEWARD_EMAIL
    assert res["verified_domain"] == {"blog_domain": "www.complete.tech", "email_domain": "complete.tech",
                                      "verified_domains": ["complete.tech", "www.complete.tech"], "badge_eligible": True,
                                      "reason": None}
    assert O.verified_domain("https://jevplay.games", "a@complete.tech", ["complete.tech"])["reason"] == "blog-other-domain"
    assert O.verified_domain("https://complete.tech", "a@example.com", ["complete.tech"])["reason"] == "email-mismatch"


def test_about_rejects_a_long_description_and_follows_renames(make_estate):
    reg = load_yaml_text((FIX / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"][N]["profile"]["description"] = "x" * 161
    res, code = O.about(make_estate(registry=reg), N)
    assert code == CHECK_FAILED and res["jobs"] == []
    est = make_estate(rows=[("org-rename", N, "*", "Northwind-Trade")])
    res, _ = O.about(est, "Northwind-Trade")
    assert res["owner"] == "Northwind-Trade" and res["jobs"][0]["argv"][4] == "orgs/Northwind-Trade"


# ----------------------------------------------------------------------------------------------- pins
def test_pins_validate_and_emit_browser_jobs(make_estate):
    res, code = O.pins(make_estate(), N)
    assert code == CHECK_FAILED  # a private repo in the public row
    by = {(c["target"], c["position"]): c for c in res["checks"]}
    assert by[("public", 1)]["result"] == "pass"
    assert by[("public", 2)]["result"] == "fail" and by[("public", 2)]["detail"] == "public pin is private"
    assert by[("public", 3)]["repo"] == "ledger" and "pin-current-slug:ledger:ren-901" in res["logs"]
    assert by[("members", 1)]["result"] == "pass"
    ids = [j["id"] for j in res["jobs"]]
    assert "p6.2-Northwind-Trading-Co-pin-public-2" not in ids
    j = res["jobs"][0]
    assert j["kind"] == "browser" and j["url"] == f"https://github.com/{N}/support-triage-agent"
    assert any("Edit Pins" in s for s in j["steps"]) and any("'Public pins'" in s for s in j["steps"])
    order = next(x for x in res["jobs"] if x["id"].endswith("pin-public-order"))
    assert "1. support-triage-agent" in order["steps"][2] and "private-pricing-engine" not in order["steps"][2]
    for x in res["jobs"]:
        assert not re.search(r"\b(delete|transfer|archive)\b", " ".join(x.get("steps", [])), re.I)


def test_pins_follow_an_approved_dependency(make_estate):
    res, _ = O.pins(make_estate(ids=["ren-901"]), N)
    c = next(c for c in res["checks"] if c["position"] == 3 and c["target"] == "public")
    assert c["repo"] == "order-ledger" and c["gate"] == "after ren-901 runs"


def test_pins_count_limit(make_estate):
    reg = load_yaml_text((FIX / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"][N]["pins_public"] = [{"repo": "support-triage-agent", "depends_on": ""}] * 7
    res, code = O.pins(make_estate(registry=reg), N)
    assert code == CHECK_FAILED and any(c.get("check") == "count" for c in res["checks"])


# ----------------------------------------------------------------------------------------------- star lists
def test_star_list_reads_existing_lists_first(make_estate):
    res = O.star_list_plan(make_estate(), N)
    assert res["result"] == "needs-input" and res["jobs"] == []
    assert res["reads"][0]["argv"][-1].endswith("star_lists.graphql")


def test_star_list_create_then_union(make_estate):
    est = make_estate()
    lists = json.loads((FIX / "star-lists.json").read_text())
    res = O.star_list_plan(est, N, lists_capture=lists)
    assert [j["id"] for j in res["jobs"]] == ["p6.4-Northwind-Trading-Co-list-create"]
    argv = res["jobs"][0]["argv"]
    assert "createUserList" in argv[4] and "name=Northwind: built on" in argv and res["pending"]
    lists2 = json.loads((FIX / "star-lists-existing.json").read_text())
    res = O.star_list_plan(est, N, lists_capture=lists2)
    q = " ".join(res["jobs"][-1]["argv"])
    assert res["list_id"] == "UL_nw" and "updateUserListsForItem" in q
    assert '"UL_nw"' in q and '"UL_other"' in q and '"R_flask"' in q  # union with the item's existing list
    assert any("updateUserList(" in " ".join(j["argv"]) for j in res["jobs"])  # description aligned


def test_star_list_reads_missing_repo_ids(make_estate):
    est = make_estate()
    lists = json.loads((FIX / "star-lists-existing.json").read_text())
    for n in lists["data"]["viewer"]["lists"]["nodes"]:
        n["items"]["nodes"] = []
    res = O.star_list_plan(est, N, lists_capture=lists)
    read = next(r for r in res["reads"] if r["name"] == "repo-id:pallets/flask")["argv"]
    assert "owner=pallets" in read and "name=flask" in read and read[-1].endswith("repo_id.graphql")
    assert res["pending"] == [{"item": "pallets/flask", "why": "repository node id (pass --repo-ids)"}]
    res = O.star_list_plan(est, N, lists_capture=lists, repo_ids={"pallets/flask": "R_flask"})
    assert '"R_flask"' in res["jobs"][-1]["argv"][4] and not res["pending"]


def test_star_list_cap_and_holds(make_estate):
    est = make_estate()
    lists = json.loads((FIX / "star-lists.json").read_text())
    lists["data"]["viewer"]["lists"]["totalCount"] = 32
    assert O.star_list_plan(est, N, lists_capture=lists)["result"] == "fail"
    reg = load_yaml_text((FIX / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"]["Pick-Your-AI"] = {"star_list": {"name": "Pick Your AI: built on", "description": "x"}, "favorites": []}
    assert O.star_list_plan(make_estate(registry=reg), "Pick-Your-AI")["result"] == "hold"


# ----------------------------------------------------------------------------------------------- labels
def test_labels_plan_per_repository(make_estate):
    est = make_estate()
    # complete trees of the repository and of the org's .github: rule 0 has nothing to read in either
    est.meta(f"{N}/support-triage-agent").update(files=["README.md"], files_complete=True)
    est.meta(f"{N}/.github").update(files=["README.md", "profile/README.md"], files_complete=True)
    res, code = O.labels_plan(est, N)
    assert code == OK
    by = {r["repo"].split("/")[1]: r for r in res["repos"]}
    assert by["upstream-fork"]["log"] == "fork" and by["inventory-sync"]["log"] == "archived"
    assert by["support-triage-agent"]["result"] == "plan"
    first = next(j for j in res["jobs"] if j["repo"] == f"{N}/support-triage-agent")
    assert first["argv"][:4] == ["gh", "label", "edit", "bug"] and first["argv"][-2:] == ["-R", f"{N}/support-triage-agent"]
    assert all("--force" not in j.get("argv", []) and "delete" not in j.get("argv", []) for j in res["jobs"])
    repos = [r["repo"] for r in res["repos"]]
    assert repos.index(f"{N}/private-pricing-engine") > repos.index(f"{N}/support-triage-agent")  # public first
    assert res["jobs"][-1]["kind"] == "browser" and res["jobs"][-1]["url"].endswith("/settings/repository-defaults")


def test_labels_na_for_romgenie(brand):
    reg = {"orgs": {"romgenie-archive-repostiory": {"final_repos": []}}}
    est = O.Estate(brand, Resolver(brand, reg, approvals()))
    res, _ = O.labels_plan(est, "romgenie-archive-repostiory")
    assert res["result"] == "n/a" and res["jobs"] == []


# ----------------------------------------------------------------------------------------------- health and doctor
def test_health_from_capture_and_checkout(make_estate, tmp_path):
    est = make_estate()
    res, code = O.health(est, N)
    assert code == CHECK_FAILED and res["cells"]["SECURITY.md"] == "missing" and "SECURITY.md" in res["add"]
    assert res["cells"]["CONTRIBUTING.md"] == "pass" and res["cells"]["SUPPORT.md"] == "unknown"
    for p in O.T1_FILES + O.FORMS:
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("x")
    res, code = O.health(est, N, repo_dir=tmp_path)
    assert code == OK and res["result"] == "pass"
    (tmp_path / "SUPPORT.md").unlink()
    (tmp_path / ".github" / "SUPPORT.md").write_text("x")  # an accepted alternative place
    assert O.health(est, N, repo_dir=tmp_path)[0]["cells"]["SUPPORT.md"] == "pass"


def test_health_missing_dot_github(make_estate):
    reg = load_yaml_text((FIX / "registry.yaml").read_text(encoding="utf-8"))
    reg["orgs"][L]["final_repos"] = ["lab-notebook"]
    res, code = O.health(make_estate(registry=reg), L)
    assert code == CHECK_FAILED and res["source"] == "missing" and "needs-approval:create-repo:.github" in res["logs"]


def test_doctor_row(make_estate):
    est = make_estate()
    snap = json.loads((FIX / "snapshot.json").read_text())
    readme, _ = O.profile(est, N)
    snap["profile_readme"] = readme["readme"]
    row = O.doctor(est, N, snap)
    c = row["cells"]
    assert c["O2"] == "fail" and any("description" in n for n in row["notes"])
    assert c["O3"] == "pass" and c["O4"] == "fail" and c["O1"] == "unknown"
    assert c["O6"] == "fail"  # order-ledger is still unpinned
    assert c["O11"] == "warn" and row["done"] == "no"
    tsv = O.as_tsv(row, header=True).splitlines()
    assert tsv[0].startswith("org\ttier\tO1 avatar") and tsv[1].startswith(f"{N}\tT1\t")
    assert O.as_md(row).startswith(f"| {N} | T1 |")


def test_avatar_colour_test(tmp_path):
    from PIL import Image
    p = tmp_path / "a.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(p)
    assert O.avatar_colours(p) == 1
    im = Image.new("RGB", (64, 64), (10, 20, 30))
    for x in range(64):
        for y in range(0, 64, 3):
            im.putpixel((x, y), (200, 40, 40) if x % 2 else (40, 200, 40))
    im.save(p)
    assert O.avatar_colours(p) >= 3


# ----------------------------------------------------------------------------------------------- CLI layer
def test_register_and_cmd_org(tmp_path):
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    O.register(p.add_subparsers(dest="command"))
    jobs = tmp_path / "jobs.jsonl"
    args = p.parse_args(["org", "about", N, "--registry", str(FIX / "registry.yaml"), "--meta-dir", str(FIX / "meta"),
                         "--approved", str(tmp_path / "none.tsv"), "--approved-yaml", str(tmp_path / "none.yaml"),
                         "--actions", str(tmp_path / "none.json"), "--decisions", str(tmp_path / "none.json"),
                         "--jobs", str(jobs)])
    res, code = args.func(args)
    assert code == OK and res["owner"] == N
    line = json.loads(jobs.read_text().splitlines()[0])
    assert set(line) >= {"id", "phase", "kind", "org", "argv", "note"}
