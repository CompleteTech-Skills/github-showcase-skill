"""PR 211 boundaries through the CLI: synthetic captures and offline renders only."""
from __future__ import annotations

import copy
import json
import socket
import xml.etree.ElementTree as ET

import pytest
import showcase
from conftest import ROOT

from ctshowcase import account as A
from ctshowcase import config

CURRENT = "Northwind-Held"
FORMER = "Northwind-Former"
SVG_NS = "{http://www.w3.org/2000/svg}"


@pytest.fixture(autouse=True)
def offline_context(tmp_path, monkeypatch):
    estate = tmp_path / "estate"
    (estate / "decisions").mkdir(parents=True)
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(estate))
    monkeypatch.delenv("SHOWCASE_T3_SIGNOFF_FILE", raising=False)

    def blocked(*args, **kwargs):
        raise AssertionError("this regression must not contact a service")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket.socket, "sendto", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(A, "_gh", blocked)


def brand_config(tmp_path, *, held=(), legacy=False, labels=None):
    raw = json.loads((ROOT / "references/brand.lock.json").read_text(encoding="utf-8"))
    raw["chart"]["hold"] = list(held)
    raw["orgs"][CURRENT] = {**copy.deepcopy(raw["orgs"]["Northwind-Trading-Co"]),
                            "former_slugs": [FORMER], "display_name": "Northwind Held"}
    if legacy:
        for key in ("no_language", "other_languages"):
            raw["chart"]["labels"].pop(key)
    raw["chart"]["labels"].update(labels or {})
    path = tmp_path / "operator-brand.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def invoke(capsys, *argv):
    code = showcase.main(list(map(str, argv)))
    streams = capsys.readouterr()
    assert not streams.err
    return code, json.loads(streams.out)


def connection(nodes=(), *, more=False):
    return {"nodes": list(nodes), "pageInfo": {"hasNextPage": more,
                                               "endCursor": "synthetic-next" if more else None}}


def runner(calls, *, orgs=(), viewer="northwind-dev", org_page=None):
    def run(name, **variables):
        calls.append((name, variables))
        if name == "account_viewer":
            return {"viewer": {"login": viewer}}
        if name == "account_user":
            return {"user": {"login": variables["login"], "repositories": connection(),
                             "all": {"totalCount": 0}, "public": {"totalCount": 0}}}
        if name == "account_orgs":
            return {"user": {"organizations": connection({"login": owner} for owner in orgs)}}
        if name == "account_enterprises":
            return {"viewer": {"enterprises": connection()}}
        if name == "account_org":
            if org_page:
                return org_page(variables)
            more = not variables.get("after")
            repo = "synthetic-first" if more else "synthetic-second"
            return {"organization": {"login": variables["org"], "repositories": connection([{"name": repo}], more=more),
                                     "all": {"totalCount": 2}, "public": {"totalCount": 2}}}
        raise AssertionError(name)
    return run


def capture_args(config_path, dest, *extra):
    return ["--config", config_path, "account-chart", "capture", "--out", dest, *extra]


@pytest.mark.parametrize("owner", ["romgenie-following-repos", CURRENT, FORMER.lower()])
@pytest.mark.parametrize("allowed", [False, True])
def test_chart_only_hold_gates_discovered_org_before_repository_reads(tmp_path, monkeypatch, capsys, owner, allowed):
    path = brand_config(tmp_path, held=["romgenie-following-repos", FORMER])
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, orgs=[owner]))
    dest = tmp_path / "capture.json"
    extra = ["--allow-hold"] if allowed else []
    code, result = invoke(capsys, *capture_args(path, dest, *extra))
    assert code == 0 and result["result"] == "ok"
    snap = json.loads(dest.read_text(encoding="utf-8"))
    reads = [(name, values) for name, values in calls if name == "account_org"]
    if allowed:
        assert [values["after"] for _, values in reads] == [None, "synthetic-next"]
        assert [repo["name"] for repo in snap["organizations"][0]["repositories"]] == ["synthetic-first", "synthetic-second"]
    else:
        assert reads == [] and snap["organizations"][0]["repositories"] == []
        assert snap["organizations"][0]["capture_status"] == "uncaptured"
        assert f"hold:{owner}" in result["logs"]
        assert "synthetic-first" not in dest.read_text(encoding="utf-8")


@pytest.mark.parametrize("explicit", [False, True])
def test_chart_hold_account_refuses_before_capture_queries(tmp_path, monkeypatch, capsys, explicit):
    path = brand_config(tmp_path, held=[FORMER])
    dest = tmp_path / "capture.json"
    dest.write_bytes(b"synthetic original capture\r\n")
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, viewer=CURRENT))
    extra = [CURRENT] if explicit else []
    code, result = invoke(capsys, *capture_args(path, dest, *extra))
    assert code == 2 and result["logs"] == ["hold"]
    assert calls == ([] if explicit else [("account_viewer", {})])
    assert dest.read_bytes() == b"synthetic original capture\r\n"


@pytest.mark.parametrize("owner,log", [("BunsDev", "exempt"), ("Pick-Your-AI", "t3-signoff"),
                                      ("Northwind-Merged", "exempt")])
def test_allow_hold_does_not_lift_other_owner_refusals(tmp_path, monkeypatch, capsys, owner, log):
    path = brand_config(tmp_path, held=[owner])
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"orgs": {}, "placeholders": [{"login": "Northwind-Merged", "successor": CURRENT}]}),
                        encoding="utf-8")
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, orgs=[owner]))
    dest = tmp_path / "capture.json"
    code, result = invoke(capsys, *capture_args(path, dest, "--registry", registry, "--allow-hold"))
    assert code == 0 and f"{log}:{owner}" in result["logs"]
    assert not any(name == "account_org" for name, _ in calls)
    assert json.loads(dest.read_text(encoding="utf-8"))["organizations"][0]["repositories"] == []


@pytest.mark.parametrize("record,allow_t3,permitted", [("valid", False, False), ("missing", True, False),
                                                     ("revoked", True, False), ("valid", True, True)])
def test_chart_allowance_still_requires_t3_flag_and_current_signoff(tmp_path, monkeypatch, capsys,
                                                                  record, allow_t3, permitted):
    owner = "Pick-Your-AI"
    path = brand_config(tmp_path, held=[owner])
    signoffs = tmp_path / "synthetic-signoffs.json"
    grant = {"id": "northwind-grant", "owner": owner, "repos": ["*"], "approved": True,
             "approver": "synthetic-co-owner", "approved_on": "2020-01-01", "expires": "2099-12-31"}
    records = [] if record == "missing" else [grant]
    if record == "revoked":
        records.append({**grant, "id": "northwind-revocation", "approved": False, "approved_on": "2021-01-01"})
    signoffs.write_text(json.dumps({"signoffs": records}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, orgs=[owner]))
    dest = tmp_path / "capture.json"
    flags = ["--allow-t3"] if allow_t3 else []
    code, result = invoke(capsys, "--t3-signoff-file", signoffs,
                          *capture_args(path, dest, "--allow-hold", *flags))
    assert code == 0
    reads = [name for name, _ in calls if name == "account_org"]
    assert len(reads) == (2 if permitted else 0)
    if not permitted:
        assert any(log.startswith("t3-signoff:") for log in result["logs"])


@pytest.mark.parametrize("allowed", [False, True])
def test_chart_hold_is_rechecked_before_continuation_read(tmp_path, monkeypatch, capsys, allowed):
    path = brand_config(tmp_path)
    selected = config.load_brand(path)
    monkeypatch.setattr(config, "load_brand", lambda *args, **kwargs: selected)

    class ChangedPolicy(dict):
        def get(self, key, default=None):
            if key == "endCursor":
                selected.raw["chart"]["hold"] = [FORMER]
            return super().get(key, default)

    def page(values):
        first = not values.get("after")
        repos = connection([{"name": "synthetic-first" if first else "synthetic-second"}], more=first)
        if first:
            repos["pageInfo"] = ChangedPolicy(repos["pageInfo"])
        return {"organization": {"login": CURRENT, "repositories": repos,
                                 "all": {"totalCount": 2}, "public": {"totalCount": 2}}}

    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, orgs=[CURRENT], org_page=page))
    dest = tmp_path / "capture.json"
    dest.write_bytes(b"synthetic original capture\r\n")
    flags = ["--allow-hold"] if allowed else []
    code, result = invoke(capsys, *capture_args(path, dest, *flags))
    reads = [name for name, _ in calls if name == "account_org"]
    if allowed:
        assert code == 0 and len(reads) == 2
    else:
        assert code == 2 and result["logs"] == ["hold"] and len(reads) == 1
        assert dest.read_bytes() == b"synthetic original capture\r\n"


@pytest.mark.parametrize("continuation", [False, True])
def test_mismatched_chart_held_source_is_identity_error_before_hold(tmp_path, monkeypatch, capsys, continuation):
    path = brand_config(tmp_path, held=[FORMER])

    def page(values):
        first = continuation and not values.get("after")
        return {"organization": {"login": "Northwind-Labs" if first else CURRENT,
                                 "repositories": connection([{"name": "synthetic-untrusted"}], more=first),
                                 "all": {"totalCount": 2}, "public": {"totalCount": 2}}}

    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, orgs=["Northwind-Labs"], org_page=page))
    dest = tmp_path / "capture.json"
    dest.write_bytes(b"synthetic original capture\r\n")
    code, result = invoke(capsys, *capture_args(path, dest))
    assert code == 2 and result["logs"] == ["usage:capture-identity"]
    assert CURRENT not in json.dumps(result) and "synthetic-untrusted" not in json.dumps(result)
    assert dest.read_bytes() == b"synthetic original capture\r\n"
    assert len([name for name, _ in calls if name == "account_org"]) == (2 if continuation else 1)


def snapshot(tmp_path, repos):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"schema": A.SCHEMA, "captured": "2026-11-18", "account": {"login": "northwind-dev"},
                                "repositories": repos, "not_public": 0, "organizations": [], "enterprises": []}),
                    encoding="utf-8")
    return path


def render(capsys, src, out, *options):
    return invoke(capsys, *options, "account-chart", "render", "--snapshot", src,
                  "--out-dir", out, "--no-png")


@pytest.mark.parametrize("static", [False, True])
def test_compacted_summary_key_is_repeated_beside_image_without_losing_chart_shares(tmp_path, capsys, static):
    languages = ["Python", "JavaScript", "TypeScript", "C++", "C#", "Java", "Kotlin", "Swift", "Objective-C", "Rust",
                 "Go", "Haskell", "OCaml", "Clojure", "Common Lisp", "Shell", "PowerShell", "HTML", "CSS", "SCSS",
                 "Sass", "Lua", "Ruby", "Elixir", "Erlang", "Dart", "Julia", "R", "Fortran", "MATLAB"]
    # Fifteen languages per repository: every byte is within the capture's first-25 language limit.
    repos = [{"name": f"synthetic-polyglot-{i}", "language": names[0], "code": {name: 100 for name in names}}
             for i, names in enumerate((languages[:15], languages[15:]))]
    src = snapshot(tmp_path, repos)
    out = tmp_path / "render"
    flags = ["--static-summary"] if static else []
    code, result = invoke(capsys, "account-chart", "render", "--snapshot", src, "--out-dir", out, "--no-png", *flags)
    assert code == 0 and result["lint"]["result"] == result["summary_lint"]["result"] == "PASS"
    assert result["summary_lint"]["animated"] is not static
    summary = ET.parse(out / "account-chart-summary.svg").getroot()
    shares = summary.find(SVG_NS + "desc").text.rsplit("excluding forks: ", 1)[1].removesuffix(".")
    assert "Other languages" in shares
    markdown = (out / "account-chart.md").read_text(encoding="utf-8")
    chart_line = next(line for line in markdown.splitlines() if line.startswith("<sub>Code across"))
    summary_line = next(line for line in markdown.splitlines() if line.startswith("<sub>Summary key"))
    for name in languages:
        assert f"{name} 3.3%" in chart_line
    assert "Other languages" not in chart_line
    for entry in shares.split("; "):
        assert entry in summary_line
    assert markdown.index(summary_line) < markdown.index('src="account-chart-summary.svg"')
    assert f"excluding forks: {shares.replace('; ', ', ')}" in markdown


@pytest.mark.parametrize("custom", [False, True])
def test_pre211_operator_config_renders_with_generic_label_defaults_or_own_labels(tmp_path, capsys, custom):
    labels = {"no_language": "Unclassified code", "other_languages": "Additional languages"} if custom else None
    path = brand_config(tmp_path, legacy=True, labels=labels)
    original = path.read_bytes()
    src = snapshot(tmp_path, [{"name": "synthetic-no-primary", "language": None,
                               "code": {"Python": 95}, "code_other": 5}])
    out = tmp_path / "render"
    code, result = render(capsys, src, out, "--config", path)
    assert code == 0 and result["lint"]["result"] == result["summary_lint"]["result"] == "PASS"
    description = ET.parse(out / "account-chart-summary.svg").getroot().find(SVG_NS + "desc").text
    assert ("Additional languages 5.0%" if custom else "Other languages 5.0%") in description
    assert path.read_bytes() == original
    assert {file.name for file in out.iterdir()} == {"account-chart.mmd", "account-chart.md", "account-chart.svg",
                                                   "account-chart-summary.svg"}


@pytest.mark.parametrize("action", ["capture", "render"])
@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("owner", [CURRENT, FORMER.lower()])
def test_root_owner_hold_is_never_lifted_by_organization_allowance(tmp_path, monkeypatch, capsys, action, allowed, owner):
    path = brand_config(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["owners"]["hold"].append(FORMER)
    path.write_text(json.dumps(raw), encoding="utf-8")
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, viewer=owner))
    flags = ["--allow-hold"] if allowed else []
    dest = tmp_path / "capture.json"
    dest.write_bytes(b"synthetic original capture\r\n")
    if action == "capture":
        code, result = invoke(capsys, *capture_args(path, dest, owner, *flags))
        assert dest.read_bytes() == b"synthetic original capture\r\n"
    else:
        src = snapshot(tmp_path, [{"name": "synthetic-root", "code": {"Python": 100}}])
        data = json.loads(src.read_text(encoding="utf-8"))
        data["account"]["login"] = owner
        src.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "render"
        code, result = invoke(capsys, "--config", path, "account-chart", "render", "--snapshot", src,
                              "--out-dir", out, "--no-png", *flags)
        assert not out.exists()
    assert code == 2 and result["result"] == "refused" and result["logs"] == ["hold"]
    assert calls == []


@pytest.mark.parametrize("owner,expected", [("BunsDev", "exempt"), ("Pick-Your-AI", "t3-signoff")])
def test_root_exclusion_and_t3_refusals_survive_org_allowance(tmp_path, monkeypatch, capsys, owner, expected):
    path = brand_config(tmp_path)
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, viewer=owner))
    code, result = invoke(capsys, *capture_args(path, tmp_path / "capture.json", owner, "--allow-hold"))
    assert code == 2 and result["logs"] == [expected] and calls == []


@pytest.mark.parametrize("static", [False, True])
@pytest.mark.parametrize("case", ["skew", "zero", "single", "compacted"])
def test_summary_segment_budget_and_language_facts(tmp_path, capsys, static, case):
    tiny = ["C", "C++", "CSS", "Go", "HTML", "Java", "JavaScript", "Lua", "Ruby", "Rust"]
    names = ["Python", *tiny]
    if case == "compacted":
        names += ["TypeScript", "Kotlin", "Swift", "Objective-C", "Haskell", "OCaml", "Clojure", "Common Lisp",
                  "Shell", "PowerShell", "SCSS", "Sass", "Elixir", "Erlang", "Dart", "Julia", "R", "Fortran", "MATLAB"]
    if case == "single":
        names = ["Python"]
    sizes = {name: (1_000_000 if name == "Python" else 2) if case == "skew" else 0 if case == "zero" else 100
             for name in names}
    src = snapshot(tmp_path, [{"name": f"synthetic-language-{i}", "language": name, "code": {name: size}}
                              for i, (name, size) in enumerate(sizes.items())])
    out = tmp_path / "render"
    flags = ["--static-summary"] if static else []
    code, result = invoke(capsys, "account-chart", "render", "--snapshot", src, "--out-dir", out, "--no-png", *flags)
    assert code == 0 and result["lint"]["result"] == "PASS"
    markdown = (out / "account-chart.md").read_text(encoding="utf-8")
    if case == "zero":
        assert result["summary_lint"] is None and "summary-skipped:no-code-shares" in result["logs"]
        assert not (out / "account-chart-summary.svg").exists() and "<sub>Code across" not in markdown
        return
    assert result["summary_lint"]["result"] == "PASS"
    svg = ET.parse(out / "account-chart-summary.svg").getroot()
    track = svg.find(f".//{SVG_NS}clipPath[@id='track']/{SVG_NS}rect")
    left, right = float(track.attrib["x"]), float(track.attrib["x"]) + float(track.attrib["width"])
    groups = svg.findall(f".//{SVG_NS}g[@clip-path='url(#track)']")
    assert len(groups) == (1 if static else 2)
    geometry = []
    for group in groups:
        segments = [(float(rect.attrib["x"]), float(rect.attrib["width"])) for rect in group]
        assert segments
        for x, width in segments:
            assert width >= 0 and left <= x <= x + width <= right
        gaps = [nx - (x + width) for (x, width), (nx, _) in zip(segments, segments[1:])]
        assert all(gap >= -1e-9 for gap in gaps)
        assert sum(width for _, width in segments) + sum(gaps) == pytest.approx(right - left, abs=0.1)
        geometry.append(segments)
    assert all(segments == geometry[0] for segments in geometry)
    description = svg.find(SVG_NS + "desc").text
    for name in names:
        # Every original chart language remains in real Markdown even if the summary key compacts it.
        assert f"{name} " in markdown
    if case == "skew":
        assert len(geometry[0]) == len(names)
        available = sum(width for _, width in geometry[0])
        assert geometry[0][0][1] == pytest.approx(available * sizes["Python"] / sum(sizes.values()), abs=0.1)
        for name in tiny:
            assert f"{name} <0.1%" in description and f"{name} <0.1%" in markdown
    elif case == "single":
        assert geometry[0] == [(left, right - left)] and "Python 100.0%" in description
    else:
        assert "Other languages" in description and "<sub>Summary key" in markdown


def parent_capture(tmp_path, monkeypatch, capsys, path, parent, *, orgs=(), original=False, extra=()):
    calls = []
    base = runner(calls, orgs=orgs)

    def read(name, **variables):
        data = base(name, **variables)
        if name == "account_user":
            repos = [{"name": "synthetic-safe-fork", "isFork": True, "parent": {"nameWithOwner": parent}}]
            if original:
                repos.insert(0, {"name": "synthetic-withheld-origin", "isFork": False})
            data["user"].update(repositories=connection(repos), all={"totalCount": len(repos)},
                                public={"totalCount": len(repos)})
        return data

    monkeypatch.setattr(A, "_gh", read)
    dest = tmp_path / "capture.json"
    code, result = invoke(capsys, *capture_args(path, dest, *extra))
    assert code == 0
    snap = json.loads(dest.read_text(encoding="utf-8"))
    fork = next(repo for repo in snap["repositories"] if repo["name"] == "synthetic-safe-fork")
    return result, dest, snap, fork


@pytest.mark.parametrize("aliased", [False, True])
def test_exposure_withheld_parent_is_absent_from_capture_and_uses_unknown_fork_fallback(tmp_path, monkeypatch, capsys,
                                                                                     aliased):
    path = brand_config(tmp_path)
    owner = FORMER if aliased else "northwind-dev"
    flags = tmp_path / "decisions.json"
    flags.write_text(json.dumps([{"owner": CURRENT if aliased else owner, "repo": "synthetic-withheld-origin",
                                  "flags": ["keep-private"]}]), encoding="utf-8")
    result, dest, snap, fork = parent_capture(tmp_path, monkeypatch, capsys, path,
                                             f"{owner}/synthetic-withheld-origin", original=not aliased,
                                             extra=["--decisions", flags])
    assert "parent" not in fork
    assert "synthetic-withheld-origin" not in dest.read_text(encoding="utf-8") + json.dumps(result)
    assert {"fork-parent-withheld", "needs-input:fork-parents"} <= set(result["logs"])
    if not aliased:
        assert "exposure-withheld" in result["logs"] and snap["coverage"]["repositories"] == "partial"
    for restore in (False, True):
        out = tmp_path / ("restored" if restore else "default")
        extra = ["--show", "external-forks"] if restore else []
        code, rendered = invoke(capsys, "--config", path, "account-chart", "render", "--snapshot", dest,
                                "--out-dir", out, "--no-png", *extra)
        assert code == 0 and rendered["counts"]["named"] == int(restore)
        assert "needs-input:fork-parents" in rendered["logs"]
        assert all("synthetic-withheld-origin" not in file.read_text(encoding="utf-8") for file in out.iterdir())


@pytest.mark.parametrize("policy", ["excluded", "hold", "family-hold", "chart-hold", "placeholder", "public"])
def test_fork_parent_obeys_owner_policies_without_exposing_target_details(tmp_path, monkeypatch, capsys, policy):
    parent_owner = "TouchedByAnAgent" if policy == "family-hold" else CURRENT
    path = brand_config(tmp_path, held=[FORMER] if policy == "chart-hold" else [])
    raw = json.loads(path.read_text(encoding="utf-8"))
    if policy in ("excluded", "hold"):
        raw["owners"][policy].append(FORMER)
    path.write_text(json.dumps(raw), encoding="utf-8")
    extra = []
    if policy == "placeholder":
        registry = tmp_path / "registry.json"
        registry.write_text(json.dumps({"orgs": {}, "placeholders": [{"login": CURRENT,
                                                                      "successor": "Northwind-Successor"}]}),
                            encoding="utf-8")
        extra = ["--registry", registry]
    parent = f"{parent_owner}/synthetic-upstream-origin"
    result, dest, _, fork = parent_capture(tmp_path, monkeypatch, capsys, path, parent, extra=extra)
    if policy == "public":
        assert fork["parent"] == parent and "fork-parent-withheld" not in result["logs"]
    else:
        assert "parent" not in fork and "fork-parent-withheld" in result["logs"]
        assert "synthetic-upstream-origin" not in dest.read_text(encoding="utf-8") + json.dumps(result)


@pytest.mark.parametrize("allowed", [False, True])
def test_parent_hold_allowance_requires_a_discovered_organization(tmp_path, monkeypatch, capsys, allowed):
    path = brand_config(tmp_path, held=[FORMER])
    flags = ["--allow-hold"] if allowed else []
    result, _, _, fork = parent_capture(tmp_path, monkeypatch, capsys, path, f"{FORMER}/synthetic-upstream-origin",
                                        orgs=[CURRENT], extra=flags)
    assert ("parent" in fork) is allowed
    assert ("fork-parent-withheld" in result["logs"]) is not allowed


@pytest.mark.parametrize("record,flag,kept", [("valid", False, False), ("valid", True, True), ("revoked", True, False)])
def test_parent_t3_scope_and_alias_withdrawal_are_checked_before_persisting(tmp_path, monkeypatch, capsys,
                                                                         record, flag, kept):
    path = brand_config(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["orgs"]["Pick-Your-AI"].setdefault("former_slugs", []).append("Northwind-T3-Former")
    path.write_text(json.dumps(raw), encoding="utf-8")
    grant = {"id": "northwind-parent-grant", "owner": "Pick-Your-AI", "repos": ["*"], "approved": True,
             "approver": "synthetic-co-owner", "approved_on": "2020-01-01", "expires": "2099-12-31"}
    records = [grant]
    if record == "revoked":
        records.append({**grant, "id": "northwind-parent-withdrawal", "repos": ["synthetic-upstream-origin"],
                        "approved": False, "approved_on": "2021-01-01"})
    signoffs = tmp_path / "signoffs.json"
    signoffs.write_text(json.dumps({"signoffs": records}), encoding="utf-8")
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(signoffs))
    extra = ["--allow-t3"] if flag else []
    parent = "Northwind-T3-Former/synthetic-upstream-origin"
    result, dest, _, fork = parent_capture(tmp_path, monkeypatch, capsys, path, parent, extra=extra)
    if kept:
        assert fork["parent"] == parent and "fork-parent-withheld" not in result["logs"]
    else:
        assert "parent" not in fork and "fork-parent-withheld" in result["logs"]
        assert "synthetic-upstream-origin" not in dest.read_text(encoding="utf-8") + json.dumps(result)


def test_default_held_viewer_keeps_root_refusal_with_org_allowance(tmp_path, monkeypatch, capsys):
    path = brand_config(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["owners"]["hold"].append(CURRENT)
    path.write_text(json.dumps(raw), encoding="utf-8")
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, viewer=CURRENT))
    code, result = invoke(capsys, *capture_args(path, tmp_path / "capture.json", "--allow-hold"))
    assert code == 2 and result["logs"] == ["hold"] and calls == [("account_viewer", {})]


def test_root_hold_recheck_blocks_personal_continuation_with_org_allowance(tmp_path, monkeypatch, capsys):
    path = brand_config(tmp_path)
    selected = config.load_brand(path)
    monkeypatch.setattr(config, "load_brand", lambda *args, **kwargs: selected)

    class ChangedRootPolicy(dict):
        def get(self, key, default=None):
            if key == "endCursor":
                selected.raw["owners"]["hold"].append("northwind-dev")
            return super().get(key, default)

    calls = []
    base = runner(calls)

    def read(name, **variables):
        data = base(name, **variables)
        if name == "account_user":
            data["user"]["repositories"] = connection([{"name": "synthetic-first"}], more=True)
            conn = data["user"]["repositories"]
            conn["pageInfo"] = ChangedRootPolicy(conn["pageInfo"])
        return data

    monkeypatch.setattr(A, "_gh", read)
    dest = tmp_path / "capture.json"
    dest.write_bytes(b"synthetic original capture\r\n")
    code, result = invoke(capsys, *capture_args(path, dest, "--allow-hold"))
    assert code == 2 and result["logs"] == ["hold"]
    assert [name for name, _ in calls] == ["account_viewer", "account_user"]
    assert dest.read_bytes() == b"synthetic original capture\r\n"


def test_root_response_identity_error_precedes_returned_owner_hold(tmp_path, monkeypatch, capsys):
    path = brand_config(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["owners"]["hold"].append(CURRENT)
    path.write_text(json.dumps(raw), encoding="utf-8")
    calls = []
    base = runner(calls)

    def read(name, **variables):
        data = base(name, **variables)
        if name == "account_user":
            data["user"]["login"] = CURRENT
        return data

    monkeypatch.setattr(A, "_gh", read)
    code, result = invoke(capsys, *capture_args(path, tmp_path / "capture.json", "--allow-hold"))
    assert code == 2 and result["logs"] == ["usage:capture-identity"]
    assert CURRENT not in json.dumps(result)


def test_held_parent_is_not_admitted_without_organization_evidence(tmp_path, monkeypatch, capsys):
    path = brand_config(tmp_path, held=[FORMER])
    result, dest, _, fork = parent_capture(tmp_path, monkeypatch, capsys, path,
                                          f"{FORMER}/synthetic-upstream-origin", extra=["--allow-hold"])
    assert "parent" not in fork and "fork-parent-withheld" in result["logs"]
    assert "synthetic-upstream-origin" not in dest.read_text(encoding="utf-8") + json.dumps(result)


def test_public_external_parent_is_retained_as_observed(tmp_path, monkeypatch, capsys):
    path = brand_config(tmp_path)
    parent = "Northwind-External/synthetic-public-origin"
    result, _, _, fork = parent_capture(tmp_path, monkeypatch, capsys, path, parent)
    assert fork["parent"] == parent and "fork-parent-withheld" not in result["logs"]


@pytest.mark.parametrize("owner", [CURRENT, FORMER.lower()])
@pytest.mark.parametrize("record,allow_t3,expected", [("valid", False, 0), ("missing", True, 0),
                                                     ("expired", True, 0), ("revoked", True, 0),
                                                     ("valid", True, 2), ("withdrawn-repo", True, 1)])
def test_overlapping_hold_t3_requires_independent_consent_for_capture_and_render(
        tmp_path, monkeypatch, capsys, owner, record, allow_t3, expected):
    path = brand_config(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["owners"]["hold"].append(CURRENT)
    raw["owners"]["t3"].append(FORMER)
    path.write_text(json.dumps(raw), encoding="utf-8")
    grant = {"id": "northwind-overlap", "owner": FORMER, "repos": ["*"], "approved": True,
             "approver": "synthetic-co-owner", "approved_on": "2020-01-01", "expires": "2099-12-31"}
    records = [] if record == "missing" else [grant]
    if record == "expired":
        grant["approved_on"] = "1990-01-01"
        grant["expires"] = "2000-01-01"
    if record in ("revoked", "withdrawn-repo"):
        records.append({**grant, "id": "northwind-withdrawal", "approved": False,
                        "approved_on": "2021-01-01",
                        "repos": ["synthetic-second"] if record == "withdrawn-repo" else ["*"]})
    signoffs = tmp_path / "overlap-signoffs.json"
    signoffs.write_text(json.dumps({"signoffs": records}), encoding="utf-8")
    flags = ["--allow-t3"] if allow_t3 else []
    prefix = ["--config", path, "--t3-signoff-file", signoffs, *flags]
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, orgs=[owner]))
    dest = tmp_path / "overlap-capture.json"
    code, result = invoke(capsys, *prefix, "account-chart", "capture", "--out", dest, "--allow-hold")
    assert code == 0
    assert len([name for name, _ in calls if name == "account_org"]) == (2 if expected else 0)
    captured = json.loads(dest.read_text(encoding="utf-8"))
    assert len(captured["organizations"][0]["repositories"]) == expected
    if not expected:
        assert any(log.startswith("t3-signoff:") for log in result["logs"])
    # Previously captured data must be checked again, including a later repository withdrawal.
    captured["organizations"][0].update(capture_status="complete", captured=True, not_public=0, repositories=[
        {"name": "synthetic-first", "fork": False}, {"name": "synthetic-second", "fork": False}])
    dest.write_text(json.dumps(captured), encoding="utf-8")
    out = tmp_path / "overlap-render"
    code, result = invoke(capsys, *prefix, "account-chart", "render", "--snapshot", dest,
                          "--out-dir", out, "--no-png", "--allow-hold")
    assert code == 0
    assert result["counts"]["named"] == expected
    text = (out / "account-chart.md").read_text(encoding="utf-8")
    if expected < 2:
        assert "synthetic-second" not in text
    if not expected:
        assert "synthetic-first" not in text


@pytest.mark.parametrize("owner", [CURRENT, FORMER.lower()])
def test_overlapping_policy_alias_cannot_mask_exclusion(tmp_path, monkeypatch, capsys, owner):
    path = brand_config(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["owners"]["hold"].append(CURRENT)
    raw["owners"]["excluded"].append(FORMER)
    path.write_text(json.dumps(raw), encoding="utf-8")
    calls = []
    monkeypatch.setattr(A, "_gh", runner(calls, orgs=[owner]))
    dest = tmp_path / "excluded-overlap.json"
    code, result = invoke(capsys, *capture_args(path, dest, "--allow-hold", "--allow-t3"))
    assert code == 0
    assert not any(name == "account_org" for name, _ in calls)
    assert any(log.startswith("exempt:") for log in result["logs"])
    assert json.loads(dest.read_text(encoding="utf-8"))["organizations"][0]["repositories"] == []
