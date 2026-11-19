"""Consent precedes omission diagnostics; synthetic subprocess CLI renders with transport blocked."""
from __future__ import annotations

import json
import os

import pytest

from conftest import run_cli


REPOSITORIES = {
    ".github": {"name": ".github"},
    "forks": {"name": "northwind-fork-canary", "fork": True},
    "archived": {"name": "northwind-archive-canary", "archived": True},
}
WORDING = {".github": "`.github` repositories", "forks": "forks", "archived": "archived repositories"}
HIDE = ("--hide", "forks", "--hide", "archived")


@pytest.fixture(autouse=True)
def isolated_cli(tmp_path, monkeypatch):
    """The real CLI may render local files, but cannot launch transports or open network connections."""
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "missing-estate"))
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(tmp_path / "missing-signoffs.yaml"))
    guard = tmp_path / "transport-guard"
    guard.mkdir()
    active, attempted = guard / "active", guard / "attempted"
    (guard / "sitecustomize.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        f"Path({str(active)!r}).touch()\n"
        "def block(event, args):\n"
        "    if event in {'subprocess.Popen', 'socket.connect', 'socket.getaddrinfo', 'os.system', 'os.posix_spawn'}:\n"
        f"        Path({str(attempted)!r}).write_text(event, encoding='utf-8')\n"
        "        raise AssertionError('blocked test transport: ' + event)\n"
        "sys.addaudithook(block)\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, (str(guard), os.environ.get("PYTHONPATH")))))
    yield
    assert active.is_file(), "subprocess CLI did not load the transport guard"
    assert not attempted.exists(), attempted.read_text(encoding="utf-8")


def snapshot(repos, *, owner="Northwind-Labs", status="complete"):
    return {"schema": "account-chart/v1", "captured": "2026-11-18",
            "account": {"login": "northwind-dev"}, "repositories": [], "not_public": 0, "enterprises": [],
            "organizations": [{"login": owner, "captured": status == "complete", "capture_status": status,
                               "not_public": 9, "repositories": repos}]}


def render(tmp_path, data, *, exposed=(), show_all=False, pre=()):
    source, decisions = tmp_path / "snapshot.json", tmp_path / "decisions.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    owner = data["organizations"][0]["login"]
    decisions.write_text(json.dumps([{"owner": owner, "repo": name, "flags": ["keep-private"]}
                                     for name in exposed]), encoding="utf-8")
    output = tmp_path / ("all-orgs" if show_all else "default")
    show = ("--show", "all-orgs") if show_all else ()
    result = run_cli(*pre, "account-chart", "render", "--snapshot", source, "--decisions", decisions,
                     "--out-dir", output, "--no-png", *HIDE, *show)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["result"] == "ok" and report["lint"]["result"] == "PASS"
    assert {path.name for path in output.iterdir()} == {f"account-chart.{ext}" for ext in ("md", "mmd", "svg")}
    markdown = (output / "account-chart.md").read_text(encoding="utf-8")
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in sorted(output.iterdir()))
    return report, markdown, rendered


def assert_categories(markdown, expected):
    for category, wording in WORDING.items():
        assert (wording in markdown) == (category in expected), markdown


def assert_counts(report, *, shown, public=0, withheld=0, hidden_by=None):
    hidden_by = hidden_by or {}
    assert report["counts"] == {
        "public": public, "named": 0, "withheld": withheld, "hidden": sum(hidden_by.values()),
        "not_public": 9 if shown else 0, "organizations": int(shown), "enterprises": 0,
        "omitted_orgs": 0, "incomplete_orgs": 0, "orgs_without_public": int(not shown), "hidden_by": hidden_by,
    }


@pytest.mark.parametrize("category", REPOSITORIES)
def test_cli_exposure_diagnostic_survives_omission_without_counts_or_hidden_category(tmp_path, category):
    repo = REPOSITORIES[category]
    data = snapshot([repo])
    for shown in (False, True):
        report, markdown, rendered = render(tmp_path, data, exposed=(repo["name"],), show_all=shown)
        assert_counts(report, shown=shown, public=int(shown), withheld=int(shown))
        assert "exposure-withheld" in report["logs"]
        assert ("no-public:Northwind-Labs" in report["logs"]) == (not shown)
        assert repo["name"] not in rendered + "\n".join(report["logs"])
        assert_categories(markdown, ())
        assert ("organizations with no public repositories shown" in markdown) == (not shown)
        assert ("public repositories are withheld" in markdown) == shown
        assert ("Northwind-Labs" in rendered) == shown


@pytest.mark.parametrize("category", REPOSITORIES)
def test_cli_permitted_hidden_repositories_keep_their_category_and_omitted_zero_totals(tmp_path, category):
    data = snapshot([REPOSITORIES[category]])
    for shown in (False, True):
        report, markdown, _ = render(tmp_path, data, show_all=shown)
        assert_counts(report, shown=shown, public=int(shown), hidden_by={category: 1} if shown else {})
        assert "exposure-withheld" not in report["logs"]
        assert_categories(markdown, (category,))


@pytest.mark.parametrize(("withheld", "permitted"), [(".github", "forks"), ("forks", "archived"),
                                                      ("archived", ".github")])
def test_cli_mixed_omitted_repositories_report_only_the_permitted_hidden_category(tmp_path, withheld, permitted):
    repo = REPOSITORIES[withheld]
    data = snapshot([repo, REPOSITORIES[permitted]])
    for shown in (False, True):
        report, markdown, rendered = render(tmp_path, data, exposed=(repo["name"],), show_all=shown)
        assert_counts(report, shown=shown, public=2 if shown else 0, withheld=int(shown),
                      hidden_by={permitted: 1} if shown else {})
        assert "exposure-withheld" in report["logs"]
        assert_categories(markdown, (permitted,))
        assert repo["name"] not in rendered + "\n".join(report["logs"])


def test_cli_exposure_alone_does_not_newly_omit_an_unfiltered_org(tmp_path):
    name = "northwind-unfiltered-canary"
    report, markdown, rendered = render(tmp_path, snapshot([{"name": name}, REPOSITORIES[".github"]]),
                                       exposed=(name,))
    assert_counts(report, shown=True, public=2, withheld=1, hidden_by={".github": 1})
    assert "exposure-withheld" in report["logs"] and "no-public:Northwind-Labs" not in report["logs"]
    assert name not in rendered + "\n".join(report["logs"])
    assert_categories(markdown, (".github",))


def t3_options(tmp_path, withdrawn=()):
    """Synthetic wildcard consent and optional per-repository withdrawals; never a real approval."""
    common = {"owner": "Pick-Your-AI", "approver": "synthetic-co-owner", "approved_on": "2026-01-15",
              "expires": "2099-12-31"}
    records = [{**common, "id": "synthetic-grant", "repos": ["*"], "approved": True}]
    records += [{**common, "id": f"synthetic-withdrawal-{i}", "repos": [name], "approved": False}
                for i, name in enumerate(withdrawn)]
    path = tmp_path / "signoffs.json"
    path.write_text(json.dumps({"signoffs": records}), encoding="utf-8")
    return "--allow-t3", "--t3-signoff-file", path


@pytest.mark.parametrize("category", REPOSITORIES)
@pytest.mark.parametrize("also_exposed", (False, True), ids=("withdrawn", "withdrawn-and-exposed"))
def test_cli_t3_repository_withdrawal_precedes_omission_categories_and_exposure(tmp_path, category, also_exposed):
    repo = REPOSITORIES[category]
    data = snapshot([repo], owner="Pick-Your-AI")
    pre = t3_options(tmp_path, (repo["name"],))
    for shown in (False, True):
        report, markdown, rendered = render(tmp_path, data, exposed=(repo["name"],) if also_exposed else (),
                                           show_all=shown, pre=pre)
        assert_counts(report, shown=shown, public=int(shown), withheld=int(shown))
        # Preserve the existing T3 diagnostic convention; only exposure diagnostics must be unnamed.
        assert f"t3-signoff:Pick-Your-AI/{repo['name']}" in report["logs"]
        assert "exposure-withheld" not in report["logs"]
        assert ("no-public:Pick-Your-AI" in report["logs"]) == (not shown)
        assert repo["name"] not in rendered
        assert_categories(markdown, ())


@pytest.mark.parametrize("category", REPOSITORIES)
def test_cli_t3_grant_preserves_permitted_hidden_category(tmp_path, category):
    data = snapshot([REPOSITORIES[category]], owner="Pick-Your-AI")
    pre = t3_options(tmp_path)
    for shown in (False, True):
        report, markdown, _ = render(tmp_path, data, show_all=shown, pre=pre)
        assert_counts(report, shown=shown, public=int(shown), hidden_by={category: 1} if shown else {})
        assert not any(log.startswith("t3-signoff:") for log in report["logs"])
        assert_categories(markdown, (category,))


@pytest.mark.parametrize("status", ("partial", "uncaptured", "failed", "unknown"))
def test_cli_incomplete_org_keeps_observed_exposure_gating_and_unknown_totals(tmp_path, status):
    repo = REPOSITORIES["forks"]
    report, markdown, rendered = render(tmp_path, snapshot([repo], status=status), exposed=(repo["name"],))
    observed = status == "partial"
    assert report["counts"] == {
        "public": int(observed), "named": 0, "withheld": int(observed), "hidden": 0,
        "not_public": 9 if observed else 0, "organizations": 1, "enterprises": 0,
        "omitted_orgs": 0, "incomplete_orgs": 1, "orgs_without_public": 0, "hidden_by": {},
    }
    assert ("exposure-withheld" in report["logs"]) == observed
    assert "no-public:Northwind-Labs" not in report["logs"]
    assert "Counts cover observed data only" in markdown
    assert repo["name"] not in rendered + "\n".join(report["logs"])
    assert_categories(markdown, ())


@pytest.mark.parametrize("category", REPOSITORIES)
def test_cli_hold_keeps_precedence_over_exposure_and_visibility(tmp_path, category):
    repo = REPOSITORIES[category]
    report, markdown, rendered = render(tmp_path, snapshot([repo], owner="TouchedByAnAgent"),
                                       exposed=(repo["name"],))
    assert_counts(report, shown=True, public=1, withheld=1)
    assert "hold:TouchedByAnAgent" in report["logs"]
    assert "exposure-withheld" not in report["logs"] and "no-public:TouchedByAnAgent" not in report["logs"]
    assert "on hold" in markdown and repo["name"] not in rendered + "\n".join(report["logs"])
    assert_categories(markdown, ())
