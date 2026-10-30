"""Review round 2 (Codex 4373814810): `content links` proposed rewriting the decision 18 footer's shared logo URLs in
CompleteTech-Skills/.github to CompleteTech-Skills/.github/... because CompleteTech-LLC also has a `.github`. A link
is only "this repository under a former owner" when an approved transfer or rename records that exact move; the footer
and the other brand URLs are fixed content and are never rewritten. Synthetic Northwind data and public org names only."""
import json

from conftest import ROOT

from ctshowcase import content as C
from ctshowcase import footer as footermod
from ctshowcase import resolver as R

FIX = ROOT / "tests" / "fixtures" / "content"
ACTIONS = json.loads((FIX / "estate-actions.json").read_text(encoding="utf-8"))
NW = "Northwind-Trading-Co"
SKILLS = "CompleteTech-Skills"
REPO = "support-triage-agent"
OLD = f"https://github.com/CompleteTech-LLC/{REPO}/actions/workflows/ci.yml"


def resolver(brand, *extra_actions, approve=()):
    return R.Resolver(brand, {}, {"rows": set(), "ids": set(approve), "answers": {}, "actions": ACTIONS + list(extra_actions),
                                  "extra": []})


def transfer(old_owner, repo, new_owner, aid="repo-nw-001", new_name=""):
    return {"id": aid, "owner": old_owner, "repo": repo, "action": "transfer+rename" if new_name else "transfer",
            "target_owner": new_owner, "new_name": new_name, "default_approve": False}


def write(root, files):
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def footer_readme(brand, tmp_path):
    return write(tmp_path / "dotgithub", {"profile/README.md": f"# {SKILLS}\n\n{footermod.block(brand)}\n",
                                          "README.md": f"# .github\n\n{footermod.block(brand)}\n"})


def test_footer_logo_urls_are_not_this_repository_under_a_former_owner(brand, tmp_path):
    """The reproduction: CompleteTech-Skills/.github's footer names CompleteTech-LLC/.github; nothing moved."""
    tree = C.Tree(footer_readme(brand, tmp_path))
    res = C.links_report(tree, ["README.md", "profile/README.md"], resolver=resolver(brand), self_slug=(SKILLS, ".github"))
    assert res["counts"].get("moved") is None and "link-rewrite" not in res["logs"]
    assert res["proposals"] == [] and C.proposal_diff(tree, res["proposals"]).strip() == ""
    assert footermod.check(brand, (tree.root / "README.md").read_text(encoding="utf-8"))[0] == "pass"


def test_footer_urls_are_never_rewritten_even_with_a_recorded_move(brand, tmp_path):
    """Fixed content: even an approved move of a `.github` (or an org rename) never rewrites the decision 18 footer."""
    move = transfer("CompleteTech-LLC", ".github", SKILLS, aid="repo-nw-002")
    tree = C.Tree(footer_readme(brand, tmp_path))
    res = C.links_report(tree, ["README.md"], resolver=resolver(brand, move, approve=["repo-nw-002"]),
                         self_slug=(SKILLS, ".github"))
    assert res["proposals"] == [] and not any(x["status"] in ("moved", "renamed") for x in res["findings"])


def test_footer_urls_are_not_rewritten_online(brand, tmp_path):
    """A GitHub `full_name` answer for the footer's repository never turns into a rewrite of the fixed footer."""
    tree = C.Tree(footer_readme(brand, tmp_path))
    f = C.Fetcher(None, opener=lambda url, method: (200, url, None), gh=lambda o, r: (f"{SKILLS}/{r}", None),
                  sleep=lambda s: None, clock=lambda: 0.0, delay=0)
    res = C.links_report(tree, ["README.md"], resolver=resolver(brand), fetcher=f, online=True,
                         self_slug=(SKILLS, ".github"))
    assert res["proposals"] == [] and not any(x["status"] in ("moved", "renamed") for x in res["findings"])


def test_same_named_repository_in_another_estate_org_is_distinct(brand, tmp_path):
    """No transfer recorded: CompleteTech-LLC/support-triage-agent is another repository, not this one."""
    tree = C.Tree(write(tmp_path / "r", {"README.md": f"[![CI]({OLD}/badge.svg)]({OLD})\n"}))
    res = C.links_report(tree, ["README.md"], resolver=resolver(brand), self_slug=(NW, REPO))
    assert res["counts"].get("moved") is None and res["proposals"] == []


def test_unapproved_transfer_is_not_a_move(brand, tmp_path):
    tree = C.Tree(write(tmp_path / "r", {"README.md": f"[![CI]({OLD}/badge.svg)]({OLD})\n"}))
    res = C.links_report(tree, ["README.md"], resolver=resolver(brand, transfer("CompleteTech-LLC", REPO, NW)),
                         self_slug=(NW, REPO))
    assert res["counts"].get("moved") is None and res["proposals"] == []


def test_approved_transfer_rewrites_only_that_repository(brand, tmp_path):
    tree = C.Tree(write(tmp_path / "r", {"README.md": (
        f"[![CI]({OLD}/badge.svg)]({OLD})\n"
        f"[Docs](https://github.com/CompleteTech-LLC/{REPO}-docs) [Fork](https://github.com/CompleteTech-Data/{REPO})\n"
        f"{footermod.block(brand)}\n")}))
    r = resolver(brand, transfer("CompleteTech-LLC", REPO, NW), approve=["repo-nw-001"])
    res = C.links_report(tree, ["README.md"], resolver=r, self_slug=(NW, REPO))
    moved = [x for x in res["findings"] if x["status"] == "moved"]
    assert len(moved) == 2 and all(x["proposal"]["new"].count(f"{NW}/{REPO}") == 1 for x in moved)
    targets = {x["proposal"]["old"] for x in moved}
    assert targets == {OLD, f"{OLD}/badge.svg"}  # the -docs repo, the other org's same-named repo and the footer stay


def test_approved_transfer_with_rename_maps_the_old_name(brand, tmp_path):
    old = "https://github.com/CompleteTech-LLC/stt-app/releases"
    tree = C.Tree(write(tmp_path / "r", {"README.md": f"[Releases]({old})\n"}))
    r = resolver(brand, transfer("CompleteTech-LLC", "stt-app", NW, new_name=REPO), approve=["repo-nw-001"])
    res = C.links_report(tree, ["README.md"], resolver=r, self_slug=(NW, REPO))
    (row,) = res["findings"]
    assert row["status"] == "moved" and row["proposal"]["new"] == f"https://github.com/{NW}/{REPO}/releases"
