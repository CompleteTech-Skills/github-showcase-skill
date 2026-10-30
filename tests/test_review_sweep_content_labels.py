"""Review sweep (content, labels, README) regressions. Synthetic Northwind data and brand.yaml's public rows only.

- §6.4 rule 0 reads the OWNER's `.github`: an `--org-defaults` JSON or checkout of another org's `.github` is refused,
  and one whose owner cannot be told holds the rename.
- The option B icon prompt keeps its family addition (trademark negatives) after an org row is re-keyed to a new login.
- `content sidebar` reads a GraphQL `totalCount`.
- README tooling: marker blocks in fenced code are left alone, a BOM does not hide the H1, shields.io path segments
  are percent-encoded, an old footer is replaced rather than duplicated, `.github` links of other orgs stay as written,
  and the social preview and nav line name the org's current login.
- `lint readme` reads `~~~` fences and URL-encoded image paths.
- `content images` never offers a one-frame candidate for an animated PNG.
"""
import copy
import io
import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from conftest import FIX, ROOT, meta_dict, run_cli
from ctshowcase import content as C
from ctshowcase import labels
from ctshowcase import readme
from ctshowcase import readmelint
from ctshowcase import social
from ctshowcase.config import Brand, load_brand
from ctshowcase.context import RepoContext
from ctshowcase.errors import NeedsInput, ShowcaseError
from ctshowcase.meta import normalize
from ctshowcase.resolver import Resolver

N, L = "Northwind-Trading-Co", "Northwind-Labs"
HOLD = "needs-input:label-references"
LIVE = [{"name": "bug", "color": "d73a4a", "description": "Something isn't working"}]
CFIX = ROOT / "tests" / "fixtures" / "content"
SKILL_ART = (ROOT / "references" / "art-direction.md").read_text(encoding="utf-8")
ART = (CFIX / "ART_DIRECTION.min.md").read_text(encoding="utf-8")


def _git(root, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print(1)\n")
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(labels=LIVE)))
    return repo, m


def _renamed_brand(old: str, new: str, *, former: bool = True) -> Brand:
    """brand.yaml with the `old` org row re-keyed to `new` (former_slugs [old] unless former=False)."""
    base = load_brand()
    raw = copy.deepcopy(base.raw)
    row = raw["orgs"].pop(old)
    row["former_slugs"] = [old] if former else []
    raw["orgs"][new] = row
    return Brand(raw, base.path)


# ------------------------------------------------------------------------------------------ rule 0: whose .github
def test_org_defaults_json_of_another_org_is_refused(tmp_path):
    repo, m = _repo(tmp_path)
    ghm = tmp_path / "dot-github.json"
    ghm.write_text(json.dumps({"owner": L, "repo": ".github", "files": ["README.md"], "files_complete": True}))
    p = run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan", "--org-defaults", ghm)
    assert p.returncode == 2, p.stdout
    assert run_cli("--meta", m, "--repo-dir", repo, "adopt", f"{N}/support-triage-agent", "--org-defaults",
                   ghm).returncode == 2
    for raw in ({"owner": {"login": L}, "name": ".github"}, {"full_name": f"{L}/.github"}):
        ghm.write_text(json.dumps(dict(raw, files=["README.md"], files_complete=True)))
        with pytest.raises(ShowcaseError) as e:
            labels.defaults_for(N, "support-triage-agent", path=ghm)
        assert e.value.log == "usage"
    # the owner's own JSON (any case) is still read
    ghm.write_text(json.dumps({"owner": N.lower(), "repo": ".github", "files": ["README.md"], "files_complete": True}))
    out = json.loads(run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan",
                             "--org-defaults", ghm).stdout)
    assert any(a[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for a in out["argv"])


def test_org_defaults_json_under_a_former_login_is_the_owner(tmp_path):
    b = _renamed_brand("CompleteTech-Pokemon", "CompleteTech-TCG")
    ghm = tmp_path / "dot-github.json"
    ghm.write_text(json.dumps({"owner": "CompleteTech-Pokemon", "repo": ".github", "files": ["README.md"],
                               "files_complete": True}))
    d = labels.defaults_for("CompleteTech-TCG", "shop", path=ghm, resolver=b.resolver())
    assert d["complete"] is True and d["files"] == ["README.md"]


def test_org_defaults_json_without_an_owner_holds_the_rename(tmp_path):
    repo, m = _repo(tmp_path)
    ghm = tmp_path / "dot-github.json"
    ghm.write_text(json.dumps({"repo": ".github", "files": ["README.md"], "files_complete": True}))
    out = json.loads(run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan",
                             "--org-defaults", ghm).stdout)
    assert not any(a[:4] == ["gh", "label", "edit", "bug"] for a in out["argv"]) and HOLD in out["logs"]


def test_org_defaults_checkout_of_another_org_is_refused(tmp_path):
    repo, m = _repo(tmp_path)
    gh = tmp_path / "dot-github"
    (gh / "profile").mkdir(parents=True)
    (gh / "profile" / "README.md").write_text("# Labs\n")
    _git(gh, "init", "-q")
    _git(gh, "remote", "add", "origin", f"https://github.com/{L}/.github.git")
    p = run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan", "--org-defaults", gh)
    assert p.returncode == 2, p.stdout
    # the owner's own checkout is read: no default form, so the rename leaves
    _git(gh, "remote", "set-url", "origin", f"git@github.com:{N}/.github.git")
    out = json.loads(run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan",
                             "--org-defaults", gh).stdout)
    assert any(a[:6] == ["gh", "label", "edit", "bug", "--name", "type:bug"] for a in out["argv"])
    # a checkout whose origin names another repository of the owner is refused too
    _git(gh, "remote", "set-url", "origin", f"https://github.com/{N}/order-ledger.git")
    assert run_cli("--meta", m, "--repo-dir", repo, "labels", "--plan", "--org-defaults", gh).returncode == 2


def test_org_defaults_checkout_without_an_origin_holds_the_rename(tmp_path):
    repo, m = _repo(tmp_path)
    gh = tmp_path / "dot-github"
    (gh / "profile").mkdir(parents=True)
    (gh / "profile" / "README.md").write_text("# Org\n")
    out = json.loads(run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan",
                             "--org-defaults", gh).stdout)
    assert not any(a[:4] == ["gh", "label", "edit", "bug"] for a in out["argv"]) and HOLD in out["logs"]
    # a default form found in it still holds the rename with the line to rewrite
    (gh / "ISSUE_TEMPLATE").mkdir()
    (gh / "ISSUE_TEMPLATE" / "bug.yml").write_text("name: Bug\nlabels: [bug]\n")
    out = json.loads(run_cli("--format", "json", "--meta", m, "--repo-dir", repo, "labels", "--plan",
                             "--org-defaults", gh).stdout)
    assert out["rewrite_first"][0]["path"] == "ISSUE_TEMPLATE/bug.yml"


# ------------------------------------------------------------------------------------------ icon prompt B additions
def _icon_ctx(b: Brand, owner: str) -> RepoContext:
    return RepoContext(b, normalize(meta_dict(owner=owner, repo="card-shop", description="Run the card shop.")), None)


def test_icon_prompt_b_keeps_the_tcg_addition_after_the_row_moves():
    before = load_brand()
    res = C.icon_prompt(_icon_ctx(before, "CompleteTech-Pokemon"), Resolver(before, {}, None), ART, option="B",
                        skill_art=SKILL_ART)
    assert "No Pokémon creatures, Poké Balls or real card designs." in res["prompt"]
    after = _renamed_brand("CompleteTech-Pokemon", "CompleteTech-TCG")
    for owner in ("CompleteTech-TCG", "CompleteTech-Pokemon"):
        res = C.icon_prompt(_icon_ctx(after, owner), Resolver(after, {}, None), ART, option="B", skill_art=SKILL_ART)
        assert "No Pokémon creatures, Poké Balls or real card designs." in res["prompt"], owner


def test_icon_prompt_b_finds_the_addition_of_a_rekeyed_row_by_its_display_name():
    b = _renamed_brand("CompleteTech-Pokemon", "Northwind-Cards", former=False)  # re-keyed, no former_slugs
    res = C.icon_prompt(_icon_ctx(b, "Northwind-Cards"), Resolver(b, {}, None), ART, option="B", skill_art=SKILL_ART)
    assert "No Pokémon creatures, Poké Balls or real card designs." in res["prompt"]


def test_icon_prompt_b_holds_when_the_addition_text_is_missing():
    b = _renamed_brand("CompleteTech-Pokemon", "CompleteTech-TCG")
    art = SKILL_ART.replace("TCG `No Pokémon creatures, Poké Balls or real card designs.` ", "")
    assert art != SKILL_ART
    with pytest.raises(NeedsInput) as e:
        C.icon_prompt(_icon_ctx(b, "CompleteTech-TCG"), Resolver(b, {}, None), ART, option="B", skill_art=art)
    assert e.value.log == "needs-input:family-additions"


def test_family_colours_follow_the_org_aliases():
    assert C.family_colours(ART, "jevplay-games-new", "jevplay-games", ["jevplay-games-new", "jevplay-games"]) == \
        C.family_colours(ART, "jevplay-games", "jevplay-games")


# ------------------------------------------------------------------------------------------ sidebar totalCount
@pytest.mark.parametrize("v,n", [({"totalCount": 12, "nodes": []}, 12), ({"totalCount": 12}, 12),
                                 ({"totalCount": 12, "nodes": [{"id": 1}]}, 12), ({"total_count": 3}, 3),
                                 ({"nodes": [{"id": 1}]}, 1)])
def test_count_reads_graphql_total_count(v, n):
    assert C._count(v) == n


def test_sidebar_keeps_releases_with_a_graphql_total_count():
    res = C.sidebar_plan({"owner": N, "repo": "support-triage-agent", "visibility": "public"},
                         {"releases": {"totalCount": 12, "nodes": []}, "packages": 0, "deployments": 0})
    assert res["row"]["releases"] == 12 and res["row"]["show_releases"] is True, res


# ------------------------------------------------------------------------------------------ README: fenced markers
FENCED = ("```markdown\n<!-- showcase:tagline:start -->\n**My own tagline**\n<!-- showcase:tagline:end -->\n```\n\n"
          "~~~text\n<!-- showcase:license -->\nExample paragraph.\n~~~\n")


def test_header_mode_leaves_a_fenced_marker_example_alone(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    text = readme.scaffold(ctx).rstrip("\n").replace("## License", "## Usage\n\n" + FENCED + "\n## License")
    out = readme.header_only(make_ctx(repo_dir=tmp_path), text)
    assert FENCED in out and "**My own tagline**" in out
    body, blocks = readme._strip_markers(text)
    assert FENCED in body and "nav" in blocks


def test_bootstrap_state_ignores_a_fenced_template_body():
    ex = (f"```markdown\n{readme.pristine_block('## About')}\n```\n").replace("## About", "## About\n\nEdited.")
    assert readme.bootstrap_state("# Title\n\n" + ex) == "none"


# ------------------------------------------------------------------------------------------ README: BOM
BODY = ("# Support Triage Agent\n\n![CI](https://img.shields.io/badge/ci-passing-067647)\n\nTriage agent for the "
        "Northwind pilot.\n\n## Usage\n\nRun it.\n")


def test_upgrade_reads_a_readme_with_a_bom_like_one_without(make_ctx, tmp_path):
    plain, _ = readme.upgrade(make_ctx(), BODY)
    bom, _ = readme.upgrade(make_ctx(), "\ufeff" + BODY)
    assert bom == plain and "\ufeff" not in bom
    p = tmp_path / "README.md"
    p.write_bytes(("\ufeff" + BODY).encode("utf-8"))
    assert readme.read_text(p) == BODY


def test_lint_counts_the_h1_after_a_bom(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    text = "\ufeff# Old Title\n\n" + readme.scaffold(ctx)
    (tmp_path / "README.md").write_bytes(text.encode("utf-8"))
    res = readmelint.lint(make_ctx(repo_dir=tmp_path), tmp_path / "README.md")
    assert "R7 exactly one H1 required (found 2)" in res["fails"], res["fails"]


# ------------------------------------------------------------------------------------------ README: shields
@pytest.mark.parametrize("lang,seg", [("C#", "C%23"), ("F#", "F%23"), ("Q#", "Q%23")])
def test_language_badge_escapes_the_hash(make_ctx, lang, seg):
    url = next(u for a, u, _ in readme.badges(make_ctx(language=lang)) if a.startswith("Language"))
    assert f"/badge/language-{seg}-" in url and "#" not in url


def test_shield_keeps_the_existing_escapes():
    assert readme.shield("AGPL-3.0 | commercial") == "AGPL--3.0%20%7C%20commercial"
    assert readme.shield("3.11+") == "3.11%2B" and readme.shield("a_b c/d?e%") == "a__b%20c%2Fd%3Fe%25"


# ------------------------------------------------------------------------------------------ README: one footer
def test_upgrade_replaces_an_old_footer_instead_of_adding_a_second(brand, fixture_meta, tmp_path):
    src = (ROOT / "tests/fixtures/readmes/CompleTetech-Security__php2shell-check.md").read_text(encoding="utf-8")
    # Only a configured logo URL identifies a replaceable footer; an arbitrary
    # local asset with the company alt label must remain authored content.
    src = src.replace('src="assets/logo.png"', f'src="{brand.raw["footer"]["logo_light_url"]}"')
    ctx = RepoContext(brand, normalize(fixture_meta("CompleTetech-Security__php2shell-check")), None)
    out, removed = readme.upgrade(ctx, src)
    assert out.count("Built by") == 1 and out.rstrip().endswith("<!-- showcase:footer:end -->")
    assert readme.preservation(src, out, removed) == []
    (tmp_path / "README.md").write_text(out, encoding="utf-8")
    again, _ = readme.upgrade(RepoContext(brand, normalize(fixture_meta("CompleTetech-Security__php2shell-check")),
                                          None), out)
    assert again.count("Built by") == 1


def test_upgrade_keeps_an_exact_unmarked_footer_single(brand, make_ctx):
    from ctshowcase import footer as F
    text = BODY + "\n" + F.markup(brand) + "\n"
    out, removed = readme.upgrade(make_ctx(), text)
    assert out.count("<picture>") == 1 and readme.preservation(text, out, removed) == []


def test_lint_flags_a_second_footer(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    text = readme.scaffold(ctx)
    old = ('<p align="center">\n  <a href="https://complete.tech"><img src="assets/logo.png" alt="CompleteTech LLC" '
           'width="160"></a><br>\n  <sub>Built by <a href="https://complete.tech">CompleteTech LLC</a></sub>\n</p>')
    (tmp_path / "README.md").write_text(text.replace("<!-- showcase:footer:start -->",
                                                     old + "\n\n<!-- showcase:footer:start -->"), encoding="utf-8")
    res = readmelint.lint(make_ctx(repo_dir=tmp_path), tmp_path / "README.md")
    assert "D18 footer fail:duplicate" in res["fails"], res["fails"]


# ------------------------------------------------------------------------------------------ CONTRIBUTING links
def test_bootstrap_contributing_rewrites_only_the_template_links(brand):
    up_c = "https://github.com/Northwind-Upstream/.github/blob/main/CONTRIBUTING.md"
    up_s = "https://github.com/Northwind-Upstream/.github/blob/main/SECURITY.md"
    text = ("See the [CompleteTech-LLC contributing guide](https://github.com/CompleteTech-LLC/.github/blob/main/"
            f"CONTRIBUTING.md).\nUpstream: {up_c} and {up_s}\n")
    out = readme.bootstrap_contributing(SimpleNamespace(owner=N, brand=brand), text)
    assert f"https://github.com/{N}/.github/blob/main/CONTRIBUTING.md" in out and f"[{N} contributing guide]" in out
    assert up_c in out and up_s in out


# ------------------------------------------------------------------------------------------ current login
def test_social_preview_and_nav_line_name_the_current_login(fixture_meta, fonts):
    b = load_brand()  # the row is keyed by the current login; the old one is a former slug
    ctx = RepoContext(b, normalize(fixture_meta("CompleTetech-Security__php2shell-check")), None)
    sc, info = social.social_layout(ctx, fonts)
    texts = [n.text for n in sc.nodes if isinstance(n, social.Text)]
    assert info["footer"] == "github.com/CompleteTech-Security/php2shell-check" and info["footer"] in texts
    assert not any("CompleTetech" in t for t in texts)
    assert "github.com/CompleTetech-Security" not in readme.nav_line(ctx)


def test_content_social_job_never_uploads_a_preview_with_the_old_login(tmp_path):
    appr = tmp_path / "approved.yaml"
    appr.write_text("items:\n  - id: org-001\n    approved: true\n")
    out = tmp_path / "sp.png"
    p = run_cli("--format", "json", "--meta", FIX / "CompleTetech-Security__php2shell-check.json", "--no-repo-dir",
                "content", "social", "--out", out, "--registry", CFIX / "registry.min.yaml", "--approved",
                CFIX / "approved.empty.txt", "--approved-yaml", appr, "--actions", CFIX / "estate-actions.json", "--job")
    res = json.loads(p.stdout)
    if res.get("job"):
        assert res["footer"] == "github.com/" + res["job"]["repo"], res
    else:
        assert "needs-input:social-login" in res["logs"] and p.returncode != 0, res


# ------------------------------------------------------------------------------------------ lint readme
def test_lint_reads_tilde_fences_and_encoded_image_paths(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    shot = tmp_path / "docs" / "images" / "My Shot.png"
    shot.parent.mkdir(parents=True)
    from PIL import Image
    Image.new("RGB", (8, 8), (10, 20, 30)).save(shot)
    usage = ("## Usage\n\n~~~bash\n# install the extras first\npip install .[mail]\n~~~\n\n"
             "![Screenshot of the triage queue](docs/images/My%20Shot.png)\n\n## License")
    (tmp_path / "README.md").write_text(readme.scaffold(ctx).replace("## License", usage, 1), encoding="utf-8")
    res = readmelint.lint(make_ctx(repo_dir=tmp_path), tmp_path / "README.md")
    assert not any("H1" in f for f in res["fails"]), res["fails"]
    assert not any("My%20Shot.png" in f for f in res["fails"]), res["fails"]


# ------------------------------------------------------------------------------------------ APNG
def test_animated_png_gets_no_lossless_candidate(tmp_path):
    from PIL import Image
    frames = [Image.new("RGBA", (64, 64), c) for c in ((255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255))]
    b = io.BytesIO()
    frames[0].save(b, "PNG", save_all=True, append_images=frames[1:], duration=100, loop=0)
    new, why = C._png_lossless(b.getvalue())
    assert new is None and why.startswith("animated"), why
    # a still PNG keeps its candidate
    s = io.BytesIO()
    frames[0].save(s, "PNG")
    assert C._png_lossless(s.getvalue())[1] == "ok"


def test_upgrade_replaces_a_one_line_drifted_footer(make_ctx):
    text = BODY + '\n<p align="center"><sub>Built by <a href="https://complete.tech">CompleteTech LLC</a></sub></p>\n'
    out, removed = readme.upgrade(make_ctx(), text)
    assert out.count("Built by") == 1 and readme.preservation(text, out, removed) == []
    # a centred block that is not a footer is never taken
    other = BODY + '\n<p align="center">Made in Northwind</p>\n'
    out, _ = readme.upgrade(make_ctx(), other)
    assert '<p align="center">Made in Northwind</p>' in out
