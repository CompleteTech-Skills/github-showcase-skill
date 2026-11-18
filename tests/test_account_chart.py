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


def test_a_hold_org_is_shown_but_never_names_its_repositories(brand):
    m, logs = build(brand, with_orgs(org("TouchedByAnAgent", "northwind-held-a", "northwind-held-b")))
    node = m["orgs"][0]
    assert node["held"] and node["repos"] == [] and node["notes"] == ["held"]
    assert "hold:TouchedByAnAgent" in logs and m["counts"]["withheld"] == 2


def test_exposure_flagged_repositories_are_withheld_without_their_name(brand):
    m, logs = build(brand, base(), flags={"Northwind-Labs/demand-model": ["secrets-risk"]})
    assert "Northwind-Labs/demand-model" not in names(m)
    assert "exposure-withheld" in logs and not any("demand-model" in x for x in logs)
    md = A.markdown(m, {"mmd": "a.mmd", "svg": "a.svg", "md": "a.md"})
    mmd, _ = C.mermaid(m, brand)
    assert "demand-model" not in md and "demand-model" not in mmd


def test_hide_and_private_options(brand):
    m, _ = build(brand, base(), hide=("forks", "archived"))
    assert m["counts"]["hidden"] == 5
    assert not any(rp["fork"] or rp["archived"] for n in [m["personal"], *m["orgs"]] for rp in n["repos"])
    m, _ = build(brand, base(), private="omit")
    assert "private" not in m["personal"]["notes"]
    m, _ = build(brand, base())
    assert "private" in m["personal"]["notes"]
    sandbox = next(o for o in m["orgs"] if o["login"] == "Northwind-Sandbox")
    assert sandbox["notes"] == ["empty"]


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


def test_render_writes_four_deterministic_files_that_pass_lint(tmp_path):
    r1, out = render(tmp_path, None, out="a")
    r2, _ = render(tmp_path, None, out="b")
    assert r1.returncode == 0 and r2.returncode == 0, r1.stdout + r1.stderr
    assert out["result"] == "ok" and out["lint"]["result"] == "PASS"
    a, b = _digests(tmp_path / "a"), _digests(tmp_path / "b")
    assert set(a) == {"account-chart.mmd", "account-chart.svg", "account-chart.png", "account-chart.md"}
    assert a == b  # S07: byte-identical
    assert svglint.lint_file("chart", tmp_path / "a" / "account-chart.svg")["result"] == "PASS"
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
    assert f"{out['counts']['named']} public repositories across 1 enterprise and 6 organizations" in md
    assert "11 private or internal repositories are counted, never named" in md
    assert 'href="account-chart.svg"' in md  # without a PNG the image links to the SVG


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
