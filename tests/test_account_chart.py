"""`account-chart`: read-only capture, privacy by construction, the estate gates and deterministic renders.

Synthetic data only: the Northwind snapshot in examples/account-chart and fake GraphQL runners (no network). Estate org
logins (BunsDev, Pick-Your-AI, TouchedByAnAgent, AI-Ascension, CompleteTech-Skills) come from brand.yaml and carry
made-up repository names, so the gates can be exercised without any real repository metadata.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess

import pytest
from conftest import EX, ROOT, run_cli

from ctshowcase import account as A
from ctshowcase import chart as C
from ctshowcase import svglint
from ctshowcase.config import load_brand
from ctshowcase.errors import ShowcaseError

SNAP = EX / "account-chart" / "northwind.snapshot.json"
QUERIES = ROOT / "scripts" / "ctshowcase" / "queries"
SIGNOFFS = ROOT / "tests" / "fixtures" / "t3-signoff" / "valid.yaml"


def base() -> dict:
    return json.loads(SNAP.read_text(encoding="utf-8"))


def org(login: str, *names: str, role: str = "owner", not_public: int = 0, **repo) -> dict:
    return {"login": login, "name": "", "member": True, "role": role, "captured": True, "not_public": not_public,
            "repositories": [{"name": n, "description": f"Synthetic {n}.", "language": "Python", "fork": False,
                              "archived": False, **repo} for n in names]}


def with_orgs(*orgs: dict, enterprises: list | None = None) -> dict:
    d = base()
    d["organizations"] = list(orgs)
    d["enterprises"] = enterprises or []
    return d


def write(tmp_path, snap: dict, name: str = "snap.json"):
    p = tmp_path / name
    p.write_text(json.dumps(snap), encoding="utf-8")
    return p


def render(tmp_path, snap: dict | None = None, *extra, out: str = "out", pre: tuple = ()):
    p = write(tmp_path, snap or base())
    r = run_cli(*pre, "account-chart", "render", "--snapshot", p, "--out-dir", tmp_path / out, *extra)
    return r, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else None)


# =====================================================================================================
# queries and capture (fake runner, no network)
# =====================================================================================================
def test_queries_are_reads_and_name_public_repositories_only():
    files = sorted(QUERIES.glob("account_*.graphql"))
    assert len(files) == 6
    for f in files:
        body = re.sub(r"(?m)#.*$", "", f.read_text(encoding="utf-8"))
        assert not re.search(r"\bmutation\b", body, re.I), f.name
        for chunk in body.split("repositories(")[1:]:  # each connection up to the next one
            if "nodes" in chunk:  # a connection that returns names must ask for public repositories only
                assert "privacy: PUBLIC" in chunk.split(")", 1)[0], f.name


def test_argv_passes_strings_raw_and_the_checked_query_file():
    argv = A.argv("account_user", login="1234", after="Y3Vyc29y")
    assert argv[:3] == ["gh", "api", "graphql"]
    assert ["-f", "login=1234"] == argv[3:5] and ["-f", "after=Y3Vyc29y"] == argv[5:7]
    assert argv[-2] == "-F" and argv[-1].startswith("query=@") and argv[-1].endswith("account_user.graphql")
    assert "after" not in " ".join(A.argv("account_user", login="x", after=None))


def test_capture_query_prints_reads_without_running_them():
    r = run_cli("account-chart", "capture-query", "northwind-dev")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert [x["name"] for x in out["reads"]] == ["viewer", "account", "organizations", "enterprises",
                                                 "enterprise-organizations", "organization"]
    assert all(x["argv"][:3] == ["gh", "api", "graphql"] for x in out["reads"])


def _repo_nodes(names):
    return [{"name": n, "description": f"  Synthetic   {n} ", "isFork": n.endswith("fork"), "isArchived": False,
             "primaryLanguage": {"name": "Go"}} for n in names]


def fake_gh(calls: list, viewer: str = "northwind-dev"):
    def run(name, **v):
        calls.append((name, v))
        after = v.get("after")
        if name == "account_viewer":
            return {"viewer": {"login": viewer}}
        if name == "account_user":
            if v["login"] == "missing-user":
                return {"user": None}
            page = _repo_nodes([f"r{i:03d}" for i in range(100)]) if after is None else _repo_nodes(["zz-fork"])
            return {"user": {"login": v["login"], "name": " Northwind  Developer ", "company": "@Northwind-Trading-Co",
                             "location": "", "websiteUrl": "https://northwind.example",
                             "all": {"totalCount": 110}, "public": {"totalCount": 101},
                             "repositories": {"nodes": page, "pageInfo": {"hasNextPage": after is None,
                                                                          "endCursor": "c1" if after is None else None}}}}
        if name == "account_orgs":
            return {"user": {"organizations": {"nodes": [{"login": "Northwind-Labs"}, {"login": "Northwind-Trading-Co"}],
                                               "pageInfo": {"hasNextPage": False}}}}
        if name == "account_enterprises":
            return {"viewer": {"enterprises": {"nodes": [{"slug": "northwind-holdings", "name": "Northwind Holdings",
                                                          "viewerIsAdmin": True}], "pageInfo": {"hasNextPage": False}}}}
        if name == "account_enterprise_orgs":
            return {"enterprise": {"organizations": {"nodes": [{"login": "Northwind-Trading-Co"},
                                                               {"login": "Northwind-Extra"}],
                                                     "pageInfo": {"hasNextPage": False}}}}
        if name == "account_org":
            if v["org"] == "Northwind-Extra":
                raise ShowcaseError("account_org: SAML enforcement", log="needs-input:gh")
            admin = v["org"] == "Northwind-Trading-Co"
            return {"organization": {"login": v["org"], "name": v["org"].replace("-", " "), "viewerCanAdminister": admin,
                                     "all": {"totalCount": 5}, "public": {"totalCount": 2},
                                     "repositories": {"nodes": _repo_nodes(["b-repo", "a-repo"]),
                                                      "pageInfo": {"hasNextPage": False}}}}
        raise AssertionError(name)
    return run


def test_capture_pages_counts_and_roles_with_a_fake_runner():
    calls: list = []
    snap = A.capture(None, run=fake_gh(calls), today="2026-11-18")
    assert snap["schema"] == A.SCHEMA and snap["captured"] == "2026-11-18" and snap["viewer"] == "northwind-dev"
    assert len(snap["repositories"]) == 101 and snap["repositories"][-1]["name"] == "zz-fork"
    assert snap["repositories"][-1]["fork"] is True and snap["repositories"][0]["description"] == "Synthetic r000"
    assert snap["not_public"] == 9  # all minus public: a count, never a name
    assert ("account_user", {"login": "northwind-dev", "after": "c1"}) in calls
    assert snap["account"]["name"] == "Northwind Developer"
    orgs = {o["login"]: o for o in snap["organizations"]}
    assert set(orgs) == {"Northwind-Labs", "Northwind-Trading-Co", "Northwind-Extra"}
    assert orgs["Northwind-Trading-Co"]["role"] == "owner" and orgs["Northwind-Labs"]["role"] == "member"
    assert [r["name"] for r in orgs["Northwind-Labs"]["repositories"]] == ["a-repo", "b-repo"]
    assert orgs["Northwind-Labs"]["not_public"] == 3
    assert orgs["Northwind-Extra"]["captured"] is False and orgs["Northwind-Extra"]["member"] is False
    assert "org-uncaptured:Northwind-Extra" in snap["notes"]
    assert snap["enterprises"][0]["role"] == "owner"
    A.validate(json.loads(A.snapshot_text(snap)))  # the written file round-trips


def test_capture_of_another_account_has_no_enterprises_or_roles():
    calls: list = []
    snap = A.capture("someone-else", run=fake_gh(calls), today="2026-11-18")
    assert snap["enterprises"] == [] and "enterprises:viewer-only" in snap["notes"]
    assert all(o["role"] is None for o in snap["organizations"])
    assert not any(name == "account_enterprises" for name, _ in calls)


@pytest.mark.parametrize("login", ["-bad", "a" * 40, "has space"])
def test_capture_refuses_an_invalid_login(login):
    with pytest.raises(ShowcaseError):
        A.capture(login, run=fake_gh([]), today="2026-11-18")


def test_capture_needs_a_visible_user():
    with pytest.raises(ShowcaseError) as e:
        A.capture("missing-user", run=fake_gh([]), today="2026-11-18")
    assert e.value.log == "needs-input:account"


# =====================================================================================================
# snapshot validation
# =====================================================================================================
@pytest.mark.parametrize("flag", [{"private": True}, {"visibility": "private"}, {"isPrivate": True},
                                  {"visibility": "internal"}])
def test_a_snapshot_naming_a_non_public_repository_is_refused(tmp_path, flag):
    d = base()
    d["organizations"][0]["repositories"][0].update(flag)
    with pytest.raises(ShowcaseError) as e:
        A.validate(d)
    assert e.value.log == "privacy:not-public-repository"
    r, out = render(tmp_path, d)
    assert r.returncode == 2 and not (tmp_path / "out").exists()


@pytest.mark.parametrize("mutate", [lambda d: d.update(schema="other"), lambda d: d.update(captured="yesterday"),
                                    lambda d: d["organizations"].append(dict(d["organizations"][0])),
                                    lambda d: d["account"].update(login="no spaces allowed"),
                                    lambda d: d["organizations"][0].update(not_public=-1)])
def test_malformed_snapshots_are_refused(mutate):
    d = base()
    mutate(d)
    with pytest.raises(ShowcaseError):
        A.validate(d)


# =====================================================================================================
# the model: estate gates, styles and order
# =====================================================================================================
@pytest.fixture(scope="module")
def brand():
    return load_brand()


def build(brand, snap, **kw):
    return A.build(A.validate(snap), brand, **kw)


def names(model) -> set[str]:
    nodes = [model["personal"], *model["orgs"], *[o for e in model["enterprises"] for o in e["orgs"]]]
    return {rp["full_name"] for n in nodes for rp in n["repos"]}


def logins(model) -> list[str]:
    return [o["login"] for o in model["orgs"]] + [o["login"] for e in model["enterprises"] for o in e["orgs"]]


def test_excluded_and_unsigned_t3_orgs_are_left_out(brand):
    m, logs = build(brand, with_orgs(org("BunsDev", "northwind-synthetic"), org("Pick-Your-AI", "northwind-synthetic"),
                                     org("Northwind-Labs", "demand-model")))
    assert logins(m) == ["Northwind-Labs"]
    assert "exempt:BunsDev" in logs and "t3-signoff:Pick-Your-AI" in logs
    assert m["counts"]["omitted_orgs"] == 2
    assert not any(n.startswith(("BunsDev/", "Pick-Your-AI/")) for n in names(m))


def test_an_excluded_account_is_refused(brand, tmp_path):
    d = base()
    d["account"]["login"] = "BunsDev"
    with pytest.raises(ShowcaseError) as e:
        build(brand, d)
    assert e.value.log == "exempt"
    r, out = render(tmp_path, d)
    assert r.returncode == 2 and out["result"] == "refused"


def test_a_hold_org_is_left_off_unless_allow_hold(brand):
    """User decision (2026-11-18): a HOLD org is not on the chart at all by default; --allow-hold shows it normally."""
    d = with_orgs(org("TouchedByAnAgent", "northwind-held-a", "northwind-held-b"), org("Northwind-Games", "arcade"))
    m, logs = build(brand, d)
    assert [o["login"] for o in m["orgs"]] == ["Northwind-Games"] and "hold:TouchedByAnAgent" in logs
    assert m["counts"]["omitted_orgs"] == 1 and m["counts"]["withheld"] == 0
    md = A.markdown(m, {"mmd": "a.mmd", "svg": "a.svg", "md": "a.md"})
    mmd, _ = C.mermaid(m, brand)
    assert not any(x in md + mmd for x in ("TouchedByAnAgent", "northwind-held", "on hold"))
    m, logs = build(brand, d, allow_hold=True)
    held = next(o for o in m["orgs"] if o["login"] == "TouchedByAnAgent")
    assert not held["held"] and [rp["name"] for rp in held["repos"]] == ["northwind-held-a", "northwind-held-b"]
    assert "hold-allowed:TouchedByAnAgent" in logs and "hold:TouchedByAnAgent" not in logs


def test_exposure_flagged_repositories_are_withheld_without_their_name(brand):
    m, logs = build(brand, base(), flags={"Northwind-Labs/demand-model": ["secrets-risk"]})
    assert "Northwind-Labs/demand-model" not in names(m)
    assert "exposure-withheld" in logs and not any("demand-model" in x for x in logs)
    md = A.markdown(m, {"mmd": "a.mmd", "svg": "a.svg", "md": "a.md"})
    mmd, _ = C.mermaid(m, brand)
    assert "demand-model" not in md and "demand-model" not in mmd


def lanes(model) -> list[dict]:
    return [model["personal"], *model["orgs"], *[o for e in model["enterprises"] for o in e["orgs"]]]


def test_hide_drops_forks_and_archived(brand):
    m, logs = build(brand, base(), hide=("forks", "archived"))
    assert m["counts"]["hidden_by"] == {".github": 1, "forks": 2, "archived": 1}
    assert m["counts"]["hidden"] == 4
    assert not any(rp["fork"] or rp["archived"] for n in lanes(m) for rp in n["repos"])
    # Northwind-Archive holds only archived repositories: with them hidden it has nothing to show, so it is left off
    assert "no-public:Northwind-Archive" in logs and m["counts"]["orgs_without_public"] == 3


def test_defaults_leave_out_private_work_github_repositories_and_orgs_without_public(brand):
    m, logs = build(brand, base())
    assert not any("private" in n["notes"] for n in lanes(m))  # no 'private work' pill by default
    assert not any(rp["name"] == ".github" for n in lanes(m) for rp in n["repos"])
    # terminal-theme forks an outside repository: hidden; vector-search-lab forks a Northwind repository: shown
    assert m["counts"]["hidden_by"] == {".github": 1, "external-forks": 1}
    assert "northwind-dev/terminal-theme" not in names(m) and "Northwind-Labs/vector-search-lab" in names(m)
    assert {o["login"] for o in m["orgs"]} == {"Northwind-Games"}  # Community (private only) and Sandbox (empty) left off
    assert {"no-public:Northwind-Community", "no-public:Northwind-Sandbox"} <= set(logs)
    assert m["counts"]["orgs_without_public"] == 2 and m["counts"]["organizations"] == 4
    assert m["counts"]["not_public"] == 8  # an org left off contributes nothing to the map's totals
    assert not any(x.endswith(("Northwind-Community", "Northwind-Sandbox")) for x in logs if x.startswith("needs-input"))


def test_show_brings_back_each_default(brand):
    m, logs = build(brand, base(), show=("all-orgs", "private-work", ".github", "external-forks"))
    assert "private" in m["personal"]["notes"] and "northwind-dev/terminal-theme" in names(m)
    assert any(rp["name"] == ".github" for n in lanes(m) for rp in n["repos"])
    by = {o["login"]: o for o in m["orgs"]}
    assert set(by) == {"Northwind-Community", "Northwind-Games", "Northwind-Sandbox"}
    assert by["Northwind-Community"]["notes"] == ["private"] and by["Northwind-Sandbox"]["notes"] == ["empty"]
    assert m["counts"]["orgs_without_public"] == 0 and m["counts"]["hidden"] == 0 and m["counts"]["not_public"] == 11
    m, _ = build(brand, base(), show=("all-orgs",))  # an org shown without private work says what is true
    assert next(o for o in m["orgs"] if o["login"] == "Northwind-Community")["notes"] == ["empty"]


def test_an_org_whose_only_public_repository_is_hidden_is_left_off(brand):
    # the fork's upstream is another org of the account, so it is the account's own fork and shown by default
    d = with_orgs(org("Northwind-Labs", ".github"), org("Northwind-Games", "arcade", fork=True, parent="Northwind-Labs/arc"))
    m, logs = build(brand, d)
    assert [o["login"] for o in m["orgs"]] == ["Northwind-Games"]
    assert "no-public:Northwind-Labs" in logs
    m, _ = build(brand, d, hide=("forks",))
    assert m["orgs"] == [] and m["counts"]["orgs_without_public"] == 2
    m, _ = build(brand, d, show=(".github",))
    assert {o["login"] for o in m["orgs"]} == {"Northwind-Labs", "Northwind-Games"}


def test_an_org_without_complete_capture_is_never_left_off(brand):
    d = with_orgs(dict(org("Northwind-Labs"), captured=False, capture_status="failed"),
                  dict(org("Northwind-Games"), captured=False, capture_status="partial"))
    m, logs = build(brand, d)
    assert {o["login"]: o["notes"] for o in m["orgs"]} == {"Northwind-Labs": ["failed"], "Northwind-Games": ["partial"]}
    assert not any(x.startswith("no-public:") for x in logs)


def test_the_chart_hold_list_works_like_hold_for_the_chart_only(brand):
    """`chart.hold` (user, 2026-11-18: the romgenie archive and following orgs) hides them like HOLD on the chart,
    and changes nothing else: their brand family is not on HOLD."""
    assert brand.raw["chart"]["hold"] == ["romgenie-archive-repostiory", "romgenie-following-repos"]
    assert not brand.resolver().family_hold("romgenie-following-repos")
    d = with_orgs(org("romgenie-following-repos", "northwind-watched"), org("romgenie-archive-repostiory", "old-tool"))
    m, logs = build(brand, d)
    assert m["orgs"] == [] and {"hold:romgenie-following-repos", "hold:romgenie-archive-repostiory"} <= set(logs)
    m, _ = build(brand, d, allow_hold=True)
    assert {o["login"] for o in m["orgs"]} == {"romgenie-following-repos", "romgenie-archive-repostiory"}
    m, logs = build(brand, with_orgs(org("TouchedByAnAgent")), show=("all-orgs",))
    assert m["orgs"] == [] and "hold:TouchedByAnAgent" in logs  # HOLD precedes --show all-orgs


def test_an_enterprise_stays_when_none_of_its_orgs_has_public_repositories(brand, tmp_path):
    d = with_orgs(org("Northwind-Labs"), enterprises=[{"slug": "northwind-holdings", "name": "Northwind Holdings",
                                                       "role": "owner", "organizations": ["Northwind-Labs"]}])
    m, _ = build(brand, d)
    assert [e["slug"] for e in m["enterprises"]] == ["northwind-holdings"] and m["enterprises"][0]["orgs"] == []
    r, out = render(tmp_path, d, "--no-png")
    assert r.returncode == 0 and out["lint"]["result"] == "PASS", r.stdout + r.stderr


def test_legend_explains_only_the_markers_drawn(brand):
    m, _ = build(brand, base())
    assert C.markers(m) == {"fork", "archived"}
    m, _ = build(brand, base(), hide=("forks", "archived"), show=("private-work",))
    assert C.markers(m) == {"private"}


def test_family_neutral_and_pending_styles(brand):
    st, neutral, fam = A.org_style(brand, "AI-Ascension")
    assert (neutral, fam) == (False, "ai-ascension") and st["fonts"]["display"] == "fraunces-semibold"
    st, neutral, fam = A.org_style(brand, "Northwind-Labs")
    assert neutral and fam is None
    _, neutral, fam = A.org_style(brand, "Jevelopers-neatHack-2026")  # identity pending: never CompleteTech art
    assert neutral and fam is None
    m, logs = build(brand, base())
    assert "needs-input:org-row:Northwind-Labs" in logs


def test_orgs_are_ordered_account_family_first_then_families_then_neutral(brand):
    m, _ = build(brand, with_orgs(org("Northwind-Labs", "a"), org("AI-Ascension", "northwind-b"),
                                  org("CompleteTech-Skills", "northwind-c")))
    assert logins(m) == ["CompleteTech-Skills", "AI-Ascension", "Northwind-Labs"]


def test_enterprise_orgs_hang_under_their_enterprise(brand):
    m, _ = build(brand, base())
    assert [e["slug"] for e in m["enterprises"]] == ["northwind-holdings"]
    assert {o["login"] for o in m["enterprises"][0]["orgs"]} == {"Northwind-Archive", "Northwind-Labs",
                                                                  "Northwind-Trading-Co"}
    assert {o["login"] for o in m["orgs"]} == {"Northwind-Games"}
    m, _ = build(brand, base(), show=("all-orgs",))
    assert {o["login"] for o in m["orgs"]} == {"Northwind-Community", "Northwind-Games", "Northwind-Sandbox"}
    assert m["roles"] == ["member", "owner"]


def test_signed_off_t3_org_is_shown_and_a_withdrawn_repository_stays_unnamed(tmp_path):
    d = with_orgs(org("Pick-Your-AI", "northwind-kept", "northwind-withdrawn"))
    r, out = render(tmp_path, d, "--no-png", pre=("--allow-t3", "--t3-signoff-file", SIGNOFFS))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "t3-signoff:Pick-Your-AI/northwind-withdrawn" in out["logs"]
    text = "".join((tmp_path / "out" / f"account-chart.{k}").read_text(encoding="utf-8") for k in ("mmd", "md"))
    assert "northwind-kept" in text and "northwind-withdrawn" not in text


# =====================================================================================================
# renders
# =====================================================================================================
def _digests(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_render_writes_five_deterministic_files_that_pass_lint(tmp_path):
    r1, out = render(tmp_path, None, out="a")
    r2, _ = render(tmp_path, None, out="b")
    assert r1.returncode == 0 and r2.returncode == 0, r1.stdout + r1.stderr
    assert out["result"] == "ok" and out["lint"]["result"] == "PASS" and out["summary_lint"]["result"] == "PASS"
    a, b = _digests(tmp_path / "a"), _digests(tmp_path / "b")
    assert set(a) == {"account-chart.mmd", "account-chart.svg", "account-chart.png", "account-chart.md",
                      "account-chart-summary.svg"}
    assert a == b  # S07: byte-identical
    assert svglint.lint_file("chart", tmp_path / "a" / "account-chart.svg")["result"] == "PASS"
    summary = svglint.lint_file("intro", tmp_path / "a" / "account-chart-summary.svg")
    assert summary["result"] == "PASS" and summary["animated"]
    w, h = out["size"]["width"], out["size"]["height"]
    assert out["size"]["png"] == [w * 2, h * 2]
    svg = (tmp_path / "a" / "account-chart.svg").read_text(encoding="utf-8")
    assert "<text" not in svg and f'viewBox="0 0 {w} {h}"' in svg


def test_markdown_repeats_every_named_repository_as_a_link_with_the_counts(brand, tmp_path):
    r, out = render(tmp_path, None, "--no-png")
    md = (tmp_path / "out" / "account-chart.md").read_text(encoding="utf-8")
    m, _ = build(brand, base())
    for full in names(m):
        assert f"(https://github.com/{full})" in md
    assert f"{out['counts']['named']} public repositories across 1 enterprise and 4 organizations" in md
    assert "private or internal" not in md  # private work is shown only on request
    assert ("Not shown: organizations with no public repositories shown, `.github` repositories and forks of "
            "repositories outside this account") in md
    assert "/.github)" not in md and "Northwind-Sandbox" not in md and "/terminal-theme)" not in md
    assert 'href="account-chart.svg"' in md  # without a PNG the image links to the SVG
    assert "<sub>Code across the repositories shown, excluding forks: Python " in md  # S15: the key's percentages
    assert "`support-triage-agent`](https://github.com/Northwind-Trading-Co/support-triage-agent) <sub>128 stars</sub>" in md
    assert md.rstrip().endswith("</p>") and 'src="account-chart-summary.svg"' in md  # the closing summary visual
    r, out = render(tmp_path, None, "--no-png", "--show", "all-orgs", "--show", "private-work", "--show", ".github",
                    "--show", "external-forks", out="all")
    md = (tmp_path / "all" / "account-chart.md").read_text(encoding="utf-8")
    assert r.returncode == 0 and "Not shown" not in md and "/.github)" in md and "/terminal-theme)" in md
    assert "11 private or internal repositories are counted, never named" in md
    assert "across 1 enterprise and 6 organizations" in md


def test_mermaid_source_is_themed_ordered_and_unique(brand):
    m, _ = build(brand, base())
    text, info = C.mermaid(m, brand)
    assert text.startswith("%%{init: ") and "\nflowchart LR\n" in text
    init = json.loads(text.split("%%{init: ", 1)[1].split("}%%", 1)[0])
    assert init["fontFamily"] == brand.raw["chart"]["mermaid"]["font_family"]  # top level: Mermaid ignores it elsewhere
    assert init["flowchart"]["wrappingWidth"] >= 400
    defined = re.findall(r"^\s+([A-Za-z][\w]*)(?:\(|\{\{)", text, re.M)
    assert len(defined) == len(set(defined)) and "end" not in defined
    assert "accTitle: GitHub account map of Northwind Developer (@northwind-dev)" in text
    assert "hub([" in text  # orgs outside the enterprise hang off one hub
    labs = re.search(r"subgraph (e1o\d+_r) \[\" \"\]\n(.*?)\n    end", text, re.S)
    assert labs  # rows of pills inside the lane cluster
    assert info["bytes"] == len(text.encode()) and info["edges"] + info["invisible_links"] < 500
    rows = [ln.strip() for ln in labs.group(2).splitlines() if "~~~" in ln or "([" in ln]
    pills = [re.search(r'\(\["([^"]+)"\]\)', r).group(1) for row in rows for r in row.split(" ~~~ ")]
    repos = [p.split(" · ")[0] for p in pills if not p.startswith(("private", "no public"))]
    assert repos == sorted(repos, key=str.lower)  # alphabetical, row by row


def test_mermaid_escapes_labels():
    assert C._mq('A "quoted" <b> #tag') == "A #quot;quoted#quot; #lt;b#gt; #35;tag"
    assert C._cls("l_", "C++") == "l_cpp" and C._cls("l_", "C#") == "l_csharp"


@pytest.mark.parametrize("extra", [("--name", "chart-dark"), ("--name", "Bad Name"), ("--width", "900")])
def test_invalid_render_options_are_usage_errors(tmp_path, extra):
    r, out = render(tmp_path, None, "--no-png", *extra)
    assert r.returncode == 2 and not (tmp_path / "out").exists()


def test_chart_kind_lint_bounds(tmp_path):
    def svg(w, h):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
                f'aria-label="map"><title>map</title></svg>').encode()
    assert svglint.lint_bytes("chart", svg(2400, 1186))["result"] == "PASS"
    for w, h in ((800, 1000), (2400, 100), (6000, 2000)):
        assert any(f.startswith("S02") for f in svglint.lint_bytes("chart", svg(w, h))["fails"])
    assert svglint.lint_bytes("card", svg(2400, 1186))["result"] == "FAIL"  # fixed kinds are unchanged
    f = tmp_path / "x.svg"
    f.write_bytes(svg(2400, 1186))
    r = run_cli("lint", "svg", "--kind", "chart", f)
    assert r.returncode == 0, r.stdout


def test_png_scale_is_lowered_for_huge_canvases():
    big = C.Chart(4800, 30000, [], [], "t", "d", {})
    assert C.png_scale(big, 4) == 1
    assert C.png_scale(C.Chart(2400, 1200, [], [], "t", "d", {}), 2) == 2


# =====================================================================================================
# optional mermaid-cli render
# =====================================================================================================
class _Args:
    def __init__(self, mmdc, config=None):
        self.mmdc, self.mmdc_config = mmdc, config


def test_mmdc_missing_is_needs_input(tmp_path):
    logs: list = []
    assert A._mmdc(_Args("no-such-mmdc-binary"), tmp_path, "a.mmd", "a.mermaid.png", "#000000", 2, logs) == []
    assert logs == ["needs-input:mmdc"]


def test_mmdc_runs_at_natural_size(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        conf = cmd[cmd.index("-c") + 1]
        seen["conf"] = json.loads(open(conf, encoding="utf-8").read())
        (tmp_path / "a.mermaid.png").write_bytes(b"png")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(A.shutil, "which", lambda exe: "/usr/bin/mmdc")
    monkeypatch.setattr(A.subprocess, "run", fake_run)
    logs: list = []
    out = A._mmdc(_Args("mmdc", "puppeteer.json"), tmp_path, "a.mmd", "a.mermaid.png", "#0F172A", 3, logs)
    assert out == [str(tmp_path / "a.mermaid.png")] and logs == ["mmdc:not-deterministic"]
    assert seen["conf"] == {"flowchart": {"useMaxWidth": False}}
    cmd = seen["cmd"]
    assert cmd[cmd.index("-s") + 1] == "3" and cmd[cmd.index("-b") + 1] == "#0F172A"
    assert cmd[cmd.index("-p") + 1] == "puppeteer.json"


# =====================================================================================================
# language shares, stars, fork upstreams and the summary SVG (user requests, 2026-11-18)
# =====================================================================================================
def test_capture_records_sizes_stars_upstreams_and_colours():
    def node(name, *, fork=False, parent=None, stars=0, langs=()):
        return {"name": name, "description": "", "isFork": fork, "isArchived": False, "stargazerCount": stars,
                "primaryLanguage": {"name": langs[0][0]} if langs else None,
                "parent": {"nameWithOwner": parent} if parent else None,
                "languages": {"totalSize": sum(s for _, s, _ in langs) + 50,
                              "edges": [{"size": s, "node": {"name": n, "color": c}} for n, s, c in langs]}}

    def run(name, **v):
        if name == "account_viewer":
            return {"viewer": {"login": "northwind-dev"}}
        if name == "account_user":
            nodes = [node("app", stars=42, langs=(("Go", 900, "#00add8"), ("Shell", 100, "#89e051"))),
                     node("theme", fork=True, parent="someone-else/theme", langs=(("Lua", 10, "#000080"),)),
                     node("gone", fork=True)]
            return {"user": {"login": "northwind-dev", "all": {"totalCount": 3}, "public": {"totalCount": 3},
                             "repositories": {"nodes": nodes, "pageInfo": {"hasNextPage": False}}}}
        if name in ("account_orgs", "account_enterprises"):
            key = "user" if name == "account_orgs" else "viewer"
            conn = "organizations" if name == "account_orgs" else "enterprises"
            return {key: {conn: {"nodes": [], "pageInfo": {"hasNextPage": False}}}}
        raise AssertionError(name)
    snap = A.capture(None, run=run, today="2026-11-18")
    repos = {r["name"]: r for r in snap["repositories"]}
    assert repos["app"]["stars"] == 42 and repos["app"]["code"] == {"Go": 900, "Shell": 100}
    assert repos["app"]["code_other"] == 50 and "parent" not in repos["app"]
    assert repos["theme"]["parent"] == "someone-else/theme" and repos["gone"]["parent"] is None
    assert snap["language_colors"] == {"Go": "#00ADD8", "Lua": "#000080", "Shell": "#89E051"}
    assert A.validate(json.loads(A.snapshot_text(snap)))["repositories"] == snap["repositories"]


@pytest.mark.parametrize("mutate", [lambda r: r.update(stars=-1), lambda r: r.update(code={"Go": "9"}),
                                    lambda r: r.update(code={"Go": 1}, code_other=-2),
                                    lambda r: r.update(parent="not a slug")])
def test_malformed_sizes_stars_and_upstreams_are_refused(mutate):
    d = base()
    mutate(d["organizations"][0]["repositories"][0])
    with pytest.raises(ShowcaseError):
        A.validate(d)
    d = base()
    d["language_colors"] = {"Go": "blue"}
    with pytest.raises(ShowcaseError):
        A.validate(d)


def test_code_share_counts_named_repositories_that_are_not_forks(brand):
    d = with_orgs(org("Northwind-Labs", "a", code={"Python": 600, "Shell": 4}),
                  org("Northwind-Games", "b", code={"Go": 390, "Python": 0}, code_other=6),
                  org("Northwind-Archive", "c", fork=True, parent="Northwind-Labs/c", code={"Rust": 5000}),
                  org("Northwind-Sandbox", ".github", code={"HTML": 9000}))
    d["repositories"] = []
    m, logs = build(brand, d)
    share = {e["name"]: e["share"] for e in m["legend"]}
    # 1000 bytes: forks and the hidden .github are not counted; Shell (0.4%) folds into Other with code_other
    assert share == {"Python": 0.6, "Go": 0.39, "Other languages": 0.01}
    assert [e["name"] for e in m["code_share"]] == ["Python", "Go", "Other languages"]
    assert C.percent(0.6) == "60.0%" and C.percent(0.0004) == "<0.1%" and C.percent(0) == ""
    old = with_orgs(org("Northwind-Labs", "a"))  # a snapshot from before sizes were captured
    m, logs = build(brand, old)
    assert "needs-input:language-sizes" in logs and all(e["share"] is None for e in m["legend"])


def test_stars_show_only_on_non_forks_with_more_than_ten(brand):
    d = with_orgs(org("Northwind-Labs", "popular", stars=128), org("Northwind-Games", "quiet", stars=10),
                  org("Northwind-Archive", "forked", fork=True, parent="Northwind-Labs/popular", stars=500))
    d["repositories"] = []
    m, _ = build(brand, d)
    stars = {rp["name"]: rp["star_count"] for n in lanes(m) for rp in n["repos"]}
    assert stars == {"popular": 128, "quiet": None, "forked": None}
    mmd, _ = C.mermaid(m, brand)
    assert "popular · 128 stars" in mmd and "quiet ·" not in mmd
    assert [C.stars_text(n) for n in (42, 1000, 1234, 15400)] == ["42", "1k", "1.2k", "15k"]


def test_external_forks_are_hidden_by_default(brand):
    d = with_orgs(org("Northwind-Labs", "own-fork", fork=True, parent="Northwind-Games/tool"),
                  org("Northwind-Games", "tool", "outside-fork", fork=False))
    d["organizations"][1]["repositories"][1].update(fork=True, parent="someone-else/outside")
    d["repositories"] = []
    m, logs = build(brand, d)
    assert names(m) == {"Northwind-Labs/own-fork", "Northwind-Games/tool"}
    assert m["counts"]["hidden_by"] == {"external-forks": 1} and "needs-input:fork-parents" not in logs
    m, _ = build(brand, d, show=("external-forks",))
    assert "Northwind-Games/outside-fork" in names(m)
    old = with_orgs(org("Northwind-Labs", "keep"), org("Northwind-Games", "legacy-fork", fork=True))  # no parent key
    old["repositories"] = []
    m, logs = build(brand, old)
    assert names(m) == {"Northwind-Labs/keep"} and "needs-input:fork-parents" in logs


def test_summary_svg_is_an_intro_kind_asset_animated_or_static(brand):
    from ctshowcase import summary
    from ctshowcase.typeset import Fonts
    m, _ = build(brand, base())
    fonts = Fonts(brand)
    animated, still = summary.build(brand, fonts, m), summary.build(brand, fonts, m, static=True)
    a, s = svglint.lint_bytes("intro", animated.encode()), svglint.lint_bytes("intro", still.encode())
    assert a["result"] == "PASS" and a["animated"] and s["result"] == "PASS" and not s["animated"]
    assert 'viewBox="0 0 1280 360"' in animated and "prefers-reduced-motion" in animated
    assert summary.build(brand, fonts, m) == animated  # deterministic
    assert summary.build(brand, fonts, build(brand, with_orgs(org("Northwind-Labs", "a")))[0]) is None  # no sizes
