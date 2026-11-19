"""Source-blind account capture contracts, using synthetic GraphQL responses only.

These tests exercise showcase.main and inspect the JSON actually persisted by capture.
No implementation files or proposed diff were read to construct these expectations.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.request
from pathlib import Path

import pytest
import showcase


PUBLIC_COLOR = "#123456"
OTHER_COLOR = "#456789"
WITHHELD_COLOR = "#ABCDEF"
SENTINEL = "NorthwindWithheldLanguage"
T3_OWNER = "Pick-Your-AI"


def repository(name, languages):
    return {
        "name": name, "description": "Synthetic account color privacy fixture.",
        "isFork": False, "isArchived": False, "stargazerCount": 0,
        "primaryLanguage": {"name": languages[0][0], "color": languages[0][1]},
        "languages": {
            "totalSize": len(languages) * 100,
            "edges": [{"size": 100, "node": {"name": language, "color": color}}
                      for language, color in languages],
        },
    }


def connection(nodes):
    return {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}


def consent(owner, *, repos=("*",), approved=True, identifier="synthetic-grant"):
    return {"id": identifier, "owner": owner, "repos": list(repos), "approved": approved,
            "approver": "synthetic-co-owner", "approved_on": "2020-01-01", "expires": "2099-12-31"}


@pytest.fixture
def synthetic_capture(tmp_path, monkeypatch, capsys):
    """Allow only mocked read argv; block real process launches and network calls."""
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "nonexistent-estate"))
    monkeypatch.setenv("SHOWCASE_T3_SIGNOFF_FILE", str(tmp_path / "nonexistent-signoffs.json"))
    blocked = []

    def forbid(*args, **kwargs):
        blocked.append("real transport attempted")
        raise AssertionError("Real process and network calls are forbidden in these synthetic capture tests")

    monkeypatch.setattr(subprocess, "Popen", forbid)
    monkeypatch.setattr(os, "system", forbid)
    for name in ("posix_spawn", "posix_spawnp", "spawnv", "spawnve", "spawnvp", "spawnvpe"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, forbid)
    monkeypatch.setattr(socket, "create_connection", forbid)
    monkeypatch.setattr(socket, "getaddrinfo", forbid)
    monkeypatch.setattr(socket.socket, "connect", forbid)
    monkeypatch.setattr(socket.socket, "connect_ex", forbid)
    monkeypatch.setattr(urllib.request, "urlopen", forbid)

    def capture(*, account="northwind-dev", org="Northwind-Labs", personal=(), organization=(),
                decisions=(), signoffs=(), unreadable_org=False):
        decisions_path = tmp_path / "synthetic-decisions.json"
        decisions_path.write_text(json.dumps(list(decisions)), encoding="utf-8")
        signoffs_path = tmp_path / "synthetic-signoffs.json"
        signoffs_path.write_text(json.dumps({"signoffs": list(signoffs)}), encoding="utf-8")
        calls = []

        def read(argv, **kwargs):
            assert argv[:3] == ["gh", "api", "graphql"], argv
            query = next(value for value in argv if str(value).startswith("query=@"))
            name = Path(query.removeprefix("query=@")).stem
            variables = dict(str(value).split("=", 1) for value in argv
                             if "=" in str(value) and not str(value).startswith("query=@"))
            calls.append((name, variables))
            if name == "account_viewer":
                data = {"viewer": {"login": account}}
            elif name == "account_user":
                assert variables["login"] == account
                data = {"user": {"login": account, "name": "Synthetic developer", "company": "",
                                 "location": "", "websiteUrl": "", "all": {"totalCount": len(personal)},
                                 "public": {"totalCount": len(personal)}, "repositories": connection(list(personal))}}
            elif name == "account_orgs":
                data = {"user": {"login": account, "organizations": connection([{"login": org}])}}
            elif name == "account_enterprises":
                data = {"viewer": {"login": account, "enterprises": connection([])}}
            elif name == "account_org":
                assert not unreadable_org, "An owner withdrawal must prevent the repository read"
                assert variables["org"] == org
                data = {"organization": {"login": org, "name": "Synthetic organization",
                                         "viewerCanAdminister": False,
                                         "all": {"totalCount": len(organization)},
                                         "public": {"totalCount": len(organization)},
                                         "repositories": connection(list(organization))}}
            else:
                raise AssertionError(f"Unexpected mocked read: {name}")
            return subprocess.CompletedProcess(argv, 0, json.dumps({"data": data}), "")

        monkeypatch.setattr(subprocess, "run", read)
        output = tmp_path / "synthetic-capture.json"
        prefix = ["--allow-t3", "--t3-signoff-file", str(signoffs_path)] if signoffs else []
        code = showcase.main([*prefix, "account-chart", "capture", account, "--decisions", str(decisions_path),
                              "--out", str(output)])
        printed = capsys.readouterr()
        assert code == 0, (code, printed.out, printed.err, calls)
        assert output.is_file(), (printed.out, printed.err)
        return json.loads(output.read_text(encoding="utf-8")), calls

    yield capture
    assert blocked == [], "The command attempted a real process or network operation"


def test_public_and_authorized_repositories_supply_both_capture_lanes(synthetic_capture):
    snapshot, calls = synthetic_capture(
        org=T3_OWNER,
        personal=[repository("synthetic-personal", [("Go", OTHER_COLOR)])],
        organization=[repository("synthetic-authorized", [("Python", PUBLIC_COLOR)])],
        signoffs=[consent(T3_OWNER)],
    )
    assert snapshot["language_colors"] == {"Go": OTHER_COLOR, "Python": PUBLIC_COLOR}
    assert [repo["name"] for repo in snapshot["repositories"]] == ["synthetic-personal"]
    org = next(item for item in snapshot["organizations"] if item["login"] == T3_OWNER)
    assert [repo["name"] for repo in org["repositories"]] == ["synthetic-authorized"]
    assert {name for name, _ in calls} >= {"account_user", "account_org"}


@pytest.mark.parametrize("lane", ["personal", "organization"])
@pytest.mark.parametrize("policy", ["exposure", "repository-withdrawal"])
@pytest.mark.parametrize("withheld_first", [False, True], ids=["withheld-last", "withheld-first"])
def test_withheld_repositories_never_persist_or_overwrite_language_colors(
    synthetic_capture, lane, policy, withheld_first,
):
    account = T3_OWNER if lane == "personal" and policy == "repository-withdrawal" else "northwind-dev"
    org = T3_OWNER if lane == "organization" and policy == "repository-withdrawal" else "Northwind-Labs"
    owner = account if lane == "personal" else org
    kept = repository("synthetic-permitted", [("Python", PUBLIC_COLOR)])
    withheld = repository("synthetic-withheld", [("Python", WITHHELD_COLOR), (SENTINEL, "#FEDCBA")])
    rows = [withheld, kept] if withheld_first else [kept, withheld]
    other = [repository("synthetic-other-lane", [("Go", OTHER_COLOR)])]
    decisions = [{"owner": owner, "repo": "synthetic-withheld", "flags": ["keep-private"]}]
    signoffs = [consent(owner), consent(owner, repos=["synthetic-withheld"], approved=False,
                                       identifier="synthetic-withdrawal")]
    snapshot, _ = synthetic_capture(
        account=account, org=org,
        personal=rows if lane == "personal" else other,
        organization=rows if lane == "organization" else other,
        decisions=decisions if policy == "exposure" else [],
        signoffs=signoffs if policy == "repository-withdrawal" else [],
    )
    captured = snapshot["repositories"] if lane == "personal" else next(
        item["repositories"] for item in snapshot["organizations"] if item["login"] == org
    )
    assert [repo["name"] for repo in captured] == ["synthetic-permitted"]
    assert snapshot["language_colors"] == {"Go": OTHER_COLOR, "Python": PUBLIC_COLOR}, (
        "Persisted language facts must come only from permitted repositories", snapshot["language_colors"]
    )
    assert SENTINEL not in json.dumps(snapshot)


def test_current_owner_withdrawal_cannot_supply_colors(synthetic_capture):
    snapshot, calls = synthetic_capture(
        org=T3_OWNER,
        personal=[repository("synthetic-permitted", [("Python", PUBLIC_COLOR)])],
        organization=[repository("synthetic-withheld", [(SENTINEL, WITHHELD_COLOR)])],
        signoffs=[consent(T3_OWNER), consent(T3_OWNER, approved=False, identifier="synthetic-owner-withdrawal")],
        unreadable_org=True,
    )
    assert snapshot["language_colors"] == {"Python": PUBLIC_COLOR}
    assert SENTINEL not in json.dumps(snapshot)
    assert not any(name == "account_org" for name, _ in calls)
