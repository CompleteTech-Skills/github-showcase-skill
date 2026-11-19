"""Public-work visibility regressions using synthetic snapshots and local CLI renders only."""
from __future__ import annotations

import copy
import hashlib
import json
import re

import pytest
import yaml
from PIL import Image

from conftest import run_cli
from ctshowcase import account as A
from ctshowcase import chart as C
from ctshowcase.config import Brand, load_brand


def repository(name, **flags):
    return {"name": name, "description": "Synthetic public repository.", "language": "Python",
            "fork": False, "archived": False, **flags}


GITHUB = repository(".github")
FORK = repository("northwind-filtered-fork", fork=True)
ARCHIVE = repository("northwind-filtered-archive", archived=True)
VISIBLE = repository("northwind-visible")
FILES = {"md": "map.md", "svg": "map.svg", "mmd": "map.mmd"}


def snapshot(repos=(), *, login="Northwind-Trading-Co", not_public=0, status="complete"):
    return {"schema": "account-chart/v1", "captured": "2026-11-18",
            "account": {"login": "northwind-dev", "name": "Synthetic Account"},
            "repositories": [], "not_public": 0, "enterprises": [],
            "organizations": [{"login": login, "name": "Synthetic Organization", "member": True, "role": "owner",
                               "captured": status == "complete", "capture_status": status,
                               "repositories": copy.deepcopy(list(repos)), "not_public": not_public}]}


@pytest.fixture(autouse=True)
def isolated_estate(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "nonexistent-estate"))
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(tmp_path / "missing-signoffs.yaml"))


def fixture_state(root):
    """Record every fixture entry and all authored bytes, including inputs outside the output directory."""
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            for path in sorted(root.rglob("*"))}


def source_fixture(tmp_path, repos, *, asset="org", relative=False):
    output = tmp_path / "output"
    output.mkdir()
    source = output / "source-mark.png"
    Image.new("RGB", (17, 19), (21, 67, 153)).save(source)
    for suffix in ("mmd", "svg", "md", "mermaid.png"):
        (output / f"source-mark.{suffix}").write_bytes(b"Synthetic authored companion; preserve exactly.\n")
    (tmp_path / "unrelated.txt").write_bytes(b"Synthetic unrelated content.\n")
    raw = copy.deepcopy(load_brand().raw)
    value = "output/source-mark.png" if relative else str(source)
    if asset in ("org", "absent-org"):
        raw["orgs"]["Northwind-Trading-Co"]["mark"] = value
    elif asset == "font":
        # An unused configured font remains an input even when no rendered node needs it.
        source.write_bytes(load_brand().font_file("poppins-semibold").read_bytes())
        raw["fonts"]["northwind-unused"] = str(source)
    else:
        raw["brand_assets"][asset] = value
    config = tmp_path / "references" / "brand.yaml"
    config.parent.mkdir()
    config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    data = snapshot(repos)
    if asset == "absent-org":
        data["organizations"] = []
    captured = tmp_path / "snapshot.json"
    captured.write_text(json.dumps(data), encoding="utf-8")
    return config, captured, output, source


def asset_render(config, captured, output, *extra, name="source-mark"):
    return run_cli("--config", config, "account-chart", "render", "--snapshot", captured,
                   "--out-dir", output, "--name", name, "--scale", "1", *extra)


ASSET_CASES = [
    pytest.param((), (), id="empty-omitted"),
    pytest.param((), ("--show", "all-orgs"), id="empty-restored"),
    pytest.param((GITHUB,), (), id="github-omitted"),
    pytest.param((GITHUB,), ("--show", "all-orgs"), id="github-org-restored"),
    pytest.param((GITHUB,), ("--show", ".github"), id="github-repository-restored"),
    pytest.param((FORK,), ("--hide", "forks"), id="fork-omitted"),
    pytest.param((FORK,), ("--hide", "forks", "--show", "all-orgs"), id="fork-org-restored"),
    pytest.param((FORK,), (), id="fork-repository-restored"),
    pytest.param((ARCHIVE,), ("--hide", "archived"), id="archive-omitted"),
    pytest.param((ARCHIVE,), ("--hide", "archived", "--show", "all-orgs"), id="archive-org-restored"),
    pytest.param((ARCHIVE,), (), id="archive-repository-restored"),
    pytest.param((GITHUB, FORK, ARCHIVE), ("--hide", "forks", "--hide", "archived"), id="mixed-omitted"),
    pytest.param((VISIBLE,), (), id="ordinary-visible"),
]


@pytest.mark.parametrize("relative", [False, True], ids=["absolute-mark", "relative-mark"])
@pytest.mark.parametrize(("repos", "extra"), ASSET_CASES)
def test_configured_org_mark_alias_is_refused_before_any_fixture_changes(tmp_path, repos, extra, relative):
    config, captured, output, _ = source_fixture(tmp_path, repos, relative=relative)
    before = fixture_state(tmp_path)
    result = asset_render(config, captured, output, *extra)
    assert fixture_state(tmp_path) == before, result.stdout + result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["result"] == "usage" and report["logs"] == ["usage:account-chart-path"]
    assert "aliases another output or an input" in report["error"]


@pytest.mark.parametrize("asset", ["absent-org", "logo_light", "logo_dark", "logo_dark_candidate",
                                  "mark_dark", "mark_light", "bulb_dark", "font"])
def test_configured_assets_are_protected_even_when_not_selected_for_rendering(tmp_path, asset):
    config, captured, output, _ = source_fixture(tmp_path, (), asset=asset)
    before = fixture_state(tmp_path)
    result = asset_render(config, captured, output)
    assert fixture_state(tmp_path) == before, result.stdout + result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["logs"] == ["usage:account-chart-path"]


@pytest.mark.parametrize(("repos", "extra"), [pytest.param((), (), id="omitted"),
                                             pytest.param((GITHUB,), ("--show", ".github"), id="restored")])
def test_configured_mark_allows_separate_outputs_and_deterministic_retry(tmp_path, repos, extra):
    config, captured, output, source = source_fixture(tmp_path, repos)
    before = fixture_state(tmp_path)
    first = asset_render(config, captured, output, *extra, name="separate-chart")
    assert first.returncode == 0, first.stdout + first.stderr
    after = fixture_state(tmp_path)
    assert {name: after[name] for name in before} == before
    assert after[source.relative_to(tmp_path).as_posix()] == before[source.relative_to(tmp_path).as_posix()]
    assert set(after) - set(before) == {f"output/separate-chart.{suffix}" for suffix in ("mmd", "svg", "md", "png")}
    second = asset_render(config, captured, output, *extra, name="separate-chart")
    assert second.returncode == 0, second.stdout + second.stderr
    assert fixture_state(tmp_path) == after


FILTER_CASES = [
    pytest.param((), (), (), id="empty"),
    pytest.param((GITHUB,), (), ("`.github` repositories",), id="github"),
    pytest.param((FORK,), ("forks",), ("forks",), id="fork"),
    pytest.param((ARCHIVE,), ("archived",), ("archived repositories",), id="archive"),
    pytest.param((GITHUB, FORK, ARCHIVE), ("forks", "archived"),
                 ("`.github` repositories", "forks", "archived repositories"), id="mixed"),
]


@pytest.mark.parametrize(("repos", "hide", "categories"), FILTER_CASES)
def test_omitted_org_categories_survive_without_contributing_numeric_counts(brand, repos, hide, categories):
    model, logs = A.build(A.validate(snapshot(repos, not_public=9)), brand, hide=hide)
    assert model["orgs"] == [] and logs == ["no-public:Northwind-Trading-Co"]
    assert model["counts"] == {"public": 0, "named": 0, "withheld": 0, "hidden": 0, "not_public": 0,
                               "organizations": 0, "enterprises": 0, "omitted_orgs": 0, "incomplete_orgs": 0,
                               "orgs_without_public": 1, "hidden_by": {}}
    md = A.markdown(model, FILES)
    sentence = re.search(r"Not shown: (.*?)\. Captured", md).group(1)
    assert "organizations with no public repositories shown" in sentence
    assert "organizations without public repositories" not in md
    assert not re.search(r"\d", sentence)
    assert "private or internal" not in md and "Northwind-Trading-Co" not in md
    for category in ("`.github` repositories", "forks", "archived repositories"):
        assert (category in sentence) == (category in categories)


@pytest.mark.parametrize(("repos", "hide", "categories"), FILTER_CASES)
def test_show_all_orgs_restores_lane_without_restoring_filtered_repositories(brand, repos, hide, categories):
    model, logs = A.build(A.validate(snapshot(repos, not_public=9)), brand, hide=hide, show=("all-orgs",))
    assert len(model["orgs"]) == 1 and model["orgs"][0]["repos"] == []
    assert "no-public:Northwind-Trading-Co" not in logs
    assert model["counts"]["organizations"] == 1 and model["counts"]["orgs_without_public"] == 0
    assert model["counts"]["public"] == model["counts"]["hidden"] == len(repos)
    assert model["counts"]["named"] == model["counts"]["withheld"] == 0
    assert model["counts"]["not_public"] == 9
    assert sum(model["counts"]["hidden_by"].values()) == len(repos)
    md = A.markdown(model, FILES)
    assert "organizations with no public repositories shown" not in md
    assert "private or internal" not in md
    for category in categories:
        assert category in md
    assert ("Not shown:" in md) == bool(categories)


@pytest.mark.parametrize(("repos", "hide", "categories"), FILTER_CASES)
def test_restoring_each_visibility_option_removes_its_omission_category(brand, repos, hide, categories):
    # every default-hidden category restored, including external forks (hidden by default since 2026-11-18)
    model, logs = A.build(A.validate(snapshot(repos, not_public=9)), brand,
                         show=("all-orgs", "private-work", ".github", "external-forks"))
    assert len(model["orgs"]) == 1 and model["orgs"][0]["notes"] == ["private"]
    assert model["counts"]["named"] == model["counts"]["public"] == len(repos)
    assert model["counts"]["hidden"] == 0 and model["counts"]["hidden_by"] == {}
    assert model["counts"]["not_public"] == 9 and model["counts"]["orgs_without_public"] == 0
    assert "no-public:Northwind-Trading-Co" not in logs
    md = A.markdown(model, FILES)
    assert "Not shown:" not in md and "9 private or internal repositories are counted, never named" in md
    for rp in repos:
        assert f"(https://github.com/Northwind-Trading-Co/{rp['name']})" in md


def test_mixed_visible_and_omitted_lanes_keep_categories_separate_from_counts(brand):
    data = snapshot((GITHUB,), not_public=9)
    data["organizations"] += [snapshot((FORK,), login="Northwind-Forks", not_public=7)["organizations"][0],
                              snapshot((), login="Northwind-Empty")["organizations"][0],
                              snapshot((VISIBLE, ARCHIVE), login="Northwind-Visible", not_public=5)["organizations"][0]]
    model, _ = A.build(A.validate(data), brand, hide=("forks", "archived"))
    assert [node["login"] for node in model["orgs"]] == ["Northwind-Visible"]
    assert model["counts"] == {"public": 2, "named": 1, "withheld": 0, "hidden": 1, "not_public": 5,
                               "organizations": 1, "enterprises": 0, "omitted_orgs": 0, "incomplete_orgs": 0,
                               "orgs_without_public": 3, "hidden_by": {"archived": 1}}
    md = A.markdown(model, FILES)
    assert "Not shown: organizations with no public repositories shown, `.github` repositories, forks and archived repositories" in md
    assert not any(login in md for login in ("Northwind-Trading-Co", "Northwind-Forks", "Northwind-Empty"))
    assert "(https://github.com/Northwind-Visible/northwind-visible)" in md


@pytest.mark.parametrize("kind", ["owner", "family"])
@pytest.mark.parametrize(("repos", "hide"), [pytest.param((GITHUB,), (), id="github"),
                                           pytest.param((FORK,), ("forks",), id="fork"),
                                           pytest.param((ARCHIVE,), ("archived",), id="archive"),
                                           pytest.param((GITHUB, FORK, ARCHIVE), ("forks", "archived"), id="mixed")])
def test_hold_precedes_visibility_filters_without_leaking_repository_names(kind, repos, hide):
    source_brand = load_brand()
    raw = copy.deepcopy(source_brand.raw)
    if kind == "owner":
        raw["owners"]["hold"].append("Northwind-Trading-Co")
    else:
        raw["orgs"]["Northwind-Trading-Co"]["family"] = "touchedbyanagent"
    brand = Brand(raw, source_brand.path)
    model, logs = A.build(A.validate(snapshot(repos)), brand, hide=hide)
    # user decision (2026-11-18): a HOLD organization is left off the chart whole, before any visibility filter, unless
    # --allow-hold; it was previously kept as an "on hold" lane
    assert model["orgs"] == [] and logs == ["hold:Northwind-Trading-Co"]
    assert model["counts"]["omitted_orgs"] == 1
    assert model["counts"]["public"] == model["counts"]["withheld"] == model["counts"]["named"] == 0
    assert model["counts"]["hidden"] == model["counts"]["orgs_without_public"] == 0 and model["counts"]["hidden_by"] == {}
    md = A.markdown(model, FILES)
    mmd, _ = C.mermaid(model, brand)
    assert "on hold" not in md and "Not shown:" not in md and "Northwind-Trading-Co" not in md + mmd
    rendered = md + mmd + "\n".join(logs)
    for rp in repos:
        assert rp["name"] not in rendered


def test_allow_hold_shows_a_hold_org_like_any_other():
    source_brand = load_brand()
    raw = copy.deepcopy(source_brand.raw)
    raw["owners"]["hold"].append("Northwind-Trading-Co")
    brand = Brand(raw, source_brand.path)
    model, logs = A.build(A.validate(snapshot((VISIBLE, GITHUB))), brand, allow_hold=True)
    node = model["orgs"][0]
    assert not node["held"] and node["notes"] == [] and [rp["name"] for rp in node["repos"]] == [VISIBLE["name"]]
    assert "hold-allowed:Northwind-Trading-Co" in logs and model["counts"]["hidden_by"] == {".github": 1}


@pytest.mark.parametrize(("rp", "extra"), [pytest.param(GITHUB, (), id="github"),
                                          pytest.param(FORK, ("--hide", "forks"), id="fork"),
                                          pytest.param(ARCHIVE, ("--hide", "archived"), id="archive")])
@pytest.mark.parametrize("restored", [False, True], ids=["default", "show-all"])
def test_cli_hold_leaves_the_org_off_and_never_names_it(tmp_path, rp, extra, restored):
    # user decision (2026-11-18): HOLD leaves the org off every output unless --allow-hold (previously an "on hold" lane)
    captured = tmp_path / "snapshot.json"
    captured.write_text(json.dumps(snapshot((rp,), login="TouchedByAnAgent")), encoding="utf-8")
    output = tmp_path / "output"
    show = ("--show", "all-orgs", "--show", "private-work", "--show", ".github", "--show", "external-forks") \
        if restored else ()
    result = run_cli("account-chart", "render", "--snapshot", captured, "--out-dir", output, "--no-png", *extra, *show)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["counts"]["organizations"] == 0 and report["counts"]["omitted_orgs"] == 1
    assert report["counts"]["public"] == report["counts"]["withheld"] == report["counts"]["named"] == 0
    assert report["counts"]["hidden"] == report["counts"]["orgs_without_public"] == 0
    assert "hold:TouchedByAnAgent" in report["logs"] and "no-public:TouchedByAnAgent" not in report["logs"]
    assert report["lint"]["result"] == "PASS"
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in sorted(output.iterdir()))
    assert "on hold" not in rendered and "TouchedByAnAgent" not in rendered
    assert rp["name"] not in rendered and rp["name"] not in result.stdout


@pytest.mark.parametrize("status", ["uncaptured", "failed", "partial", "unknown"])
def test_filtered_incomplete_org_remains_truthful(brand, status):
    model, logs = A.build(A.validate(snapshot((GITHUB, FORK, ARCHIVE), status=status)), brand,
                         hide=("forks", "archived"))
    assert len(model["orgs"]) == 1 and model["orgs"][0]["notes"] == [status]
    assert model["counts"]["orgs_without_public"] == 0 and model["counts"]["incomplete_orgs"] == 1
    assert not any(log.startswith("no-public:") for log in logs)
    assert model["counts"]["public"] == model["counts"]["hidden"] == (3 if status == "partial" else 0)
    md = A.markdown(model, FILES)
    assert "Counts cover observed data only" in md
    assert "organizations without public repositories" not in md
    assert "organizations with no public repositories shown" not in md
