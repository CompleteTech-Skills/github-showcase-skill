"""E6.2.1: `lint public-leak --denylist FILE` checks public files against a hand-written list, without the registry.

Fixtures are synthetic (Northwind Trading Co.) stand-ins; no private repository name is used here."""
import json

import pytest

from conftest import run_cli
from ctshowcase import org as O
from ctshowcase.errors import CHECK_FAILED, NEEDS_INPUT, OK, USAGE, NeedsInput, ShowcaseError


def _write(tmp_path, name, text, encoding="utf-8"):
    p = tmp_path / name
    p.write_bytes(text.encode(encoding))
    return p


# ---- load_denylist -----------------------------------------------------------------------------------------------

def test_load_denylist_splits_slugs_and_bare_names(tmp_path):
    p = _write(tmp_path, "deny.txt", "# private list\nNorthwind-Trading-Co/private-pricing-engine\n\nledger-core\n")
    slugs, names = O.load_denylist(str(p))
    assert slugs == {"Northwind-Trading-Co/private-pricing-engine"}
    assert names == {"ledger-core"}


def test_load_denylist_strips_comments_crlf_and_bom(tmp_path):
    text = "﻿northwind/hidden-tool # internal\r\n  ledger-core  \r\n# whole-line comment\r\n"
    p = _write(tmp_path, "deny.txt", text)
    assert O.load_denylist(str(p)) == ({"northwind/hidden-tool"}, {"ledger-core"})


def test_load_denylist_dedupes_mixed_case_keeping_first_spelling(tmp_path):
    p = _write(tmp_path, "deny.txt", "Northwind/Hidden-Tool\nnorthwind/hidden-tool\nLedger\nledger\n")
    slugs, names = O.load_denylist(str(p))
    assert slugs == {"Northwind/Hidden-Tool"}
    assert names == {"Ledger"}


@pytest.mark.parametrize("bad", ["a/b/c", "/repo", "owner/", "two words", "owner/re po"])
def test_load_denylist_rejects_invalid_entries(tmp_path, bad):
    p = _write(tmp_path, "deny.txt", f"ok-name\n{bad}\n")
    with pytest.raises(ShowcaseError) as exc:
        O.load_denylist(str(p))
    assert exc.value.code == USAGE and exc.value.log == "usage"
    assert str(exc.value) == "denylist line 2: invalid entry"


def test_load_denylist_missing_file_needs_input(tmp_path):
    with pytest.raises(NeedsInput) as exc:
        O.load_denylist(str(tmp_path / "absent.txt"))
    assert exc.value.code == NEEDS_INPUT and exc.value.log == "needs-input:denylist"


@pytest.mark.parametrize("text", ["", "# only comments\n\n   \n"])
def test_load_denylist_empty_list_is_needs_input(tmp_path, text):
    p = _write(tmp_path, "deny.txt", text)
    with pytest.raises(NeedsInput, match="denylist is empty"):
        O.load_denylist(str(p))


# ---- denylist_leaks ----------------------------------------------------------------------------------------------

def test_denylist_leaks_slug_and_private_name_hits():
    slugs = {"Northwind-Trading-Co/private-pricing-engine"}
    text = "See https://github.com/Northwind-Trading-Co/private-pricing-engine and private-pricing-engine."
    hits = O.denylist_leaks(text, slugs, set())
    assert hits[0] == "denied-slug:L1"  # kinds and lines only: private entries are never echoed
    assert not any("pricing" in h.lower() for h in hits)


def test_denylist_leaks_bare_name_has_no_distinctiveness_requirement():
    # 'ledger' is short and plain: leak_check would not flag it, but the operator listed it explicitly.
    assert O.denylist_leaks("The ledger module ships.", set(), {"Ledger"}) == ["denied-name:L1"]
    assert O.leak_check("The ledger module ships.", {"northwind/ledger"}, [], set()) == []


def test_denylist_leaks_bare_name_respects_boundaries_and_owner_positions():
    names = {"ledger"}
    assert O.denylist_leaks("ledger-core is separate", set(), names) == []
    assert O.denylist_leaks("the ledger.v2 tag", set(), names) == []
    assert O.denylist_leaks("see github.com/ledger/readme", set(), names) == []
    assert O.denylist_leaks("the ledger-based tool", set(), names) == []  # hyphen continues the token: not the name
    assert O.denylist_leaks("the ledger tool", set(), names) == ["denied-name:L1"]
    assert O.denylist_leaks("the LEDGER tool", set(), names) == ["denied-name:L1"]


def test_denylist_leaks_clean_text_has_no_hits():
    assert O.denylist_leaks("A public note about widgets.", {"northwind/hidden-tool"}, {"ledger"}) == []


# ---- lint public-leak --denylist (CLI) ---------------------------------------------------------------------------

def _rows(p):
    return [json.loads(x) for x in p.stdout.splitlines() if x.startswith("{")]


def test_cli_denylist_only_runs_without_registry_and_fails_on_hit(tmp_path):
    deny = _write(tmp_path, "deny.txt", "northwind/hidden-tool\nledger\n")
    clean = _write(tmp_path, "clean.md", "A note about widgets.\n")
    leak = _write(tmp_path, "leak.md", "Our ledger powers quotes.\n")
    p = run_cli("lint", "public-leak", clean, leak, "--denylist", deny)
    rows = _rows(p)
    assert p.returncode == CHECK_FAILED
    assert rows[0]["result"] == "pass" and rows[0]["mode"] == "denylist"
    assert rows[1]["result"] == "fail" and rows[1]["hits"] == ["denied-name:L1"]
    assert "registry-free:denylist-only" in rows[0]["logs"]
    assert any(x.startswith("coverage:denylist-entries-only") for x in rows[0]["logs"])


def test_cli_denylist_clean_exits_zero(tmp_path):
    deny = _write(tmp_path, "deny.txt", "northwind/hidden-tool\n")
    clean = _write(tmp_path, "clean.md", "A note about widgets.\n")
    p = run_cli("lint", "public-leak", clean, "--denylist", deny)
    assert p.returncode == OK and _rows(p)[0]["result"] == "pass"


def test_cli_denylist_acknowledges_ignored_flags(tmp_path):
    deny = _write(tmp_path, "deny.txt", "ledger\n")
    clean = _write(tmp_path, "clean.md", "widgets\n")
    p = run_cli("lint", "public-leak", clean, "--denylist", deny, "--meta-dir", str(tmp_path), "--org", "northwind")
    logs = _rows(p)[0]["logs"]
    assert "ignored-in-denylist-mode:--meta-dir" in logs and "ignored-in-denylist-mode:--org" in logs
    assert "ignored-in-denylist-mode:--decisions" not in logs


def test_cli_denylist_missing_file_row_fails(tmp_path):
    deny = _write(tmp_path, "deny.txt", "ledger\n")
    p = run_cli("lint", "public-leak", tmp_path / "absent.md", "--denylist", deny)
    row = _rows(p)[0]
    assert p.returncode == CHECK_FAILED and row["fails"] == ["file not found"] and row["mode"] == "denylist"


def test_cli_denylist_without_files_is_usage_error(tmp_path):
    deny = _write(tmp_path, "deny.txt", "ledger\n")
    p = run_cli("lint", "public-leak", "--denylist", deny)
    assert p.returncode == USAGE and "lint public-leak needs FILE..." in p.stdout


def test_cli_missing_denylist_is_needs_input(tmp_path):
    clean = _write(tmp_path, "clean.md", "widgets\n")
    p = run_cli("lint", "public-leak", clean, "--denylist", tmp_path / "absent.txt")
    assert p.returncode == NEEDS_INPUT and "needs-input:denylist" in p.stdout


def test_cli_denylist_with_explicit_registry_still_requires_it(tmp_path):
    deny = _write(tmp_path, "deny.txt", "ledger\n")
    clean = _write(tmp_path, "clean.md", "widgets\n")
    p = run_cli("lint", "public-leak", clean, "--denylist", deny, "--registry", tmp_path / "no-registry.yaml")
    assert p.returncode == NEEDS_INPUT


def test_cli_without_denylist_keeps_registry_path(tmp_path):
    # The default stays OFF: no --denylist means the registry path, which still fails closed without metadata.
    clean = _write(tmp_path, "clean.md", "widgets\n")
    p = run_cli("lint", "public-leak", clean, "--registry", tmp_path / "no-registry.yaml")
    assert p.returncode == NEEDS_INPUT
    assert "registry-free" not in p.stdout and "denied-name" not in p.stdout


def test_cli_denylist_unions_with_explicit_registry(tmp_path):
    # --registry and --denylist together: the registry's private hits and the listed names are both reported.
    from conftest import ROOT
    estate = ROOT / "examples" / "estate"
    deny = _write(tmp_path, "deny.txt", "widget-quotes-v9\n")
    leak = _write(tmp_path, "leak.md", "Our private-pricing-engine and widget-quotes-v9 power quotes.\n")
    p = run_cli("lint", "public-leak", leak, "--registry", estate / "registry" / "estate.yaml",
                "--meta-dir", estate / "meta", "--denylist", deny)
    row = _rows(p)[0]
    assert p.returncode == CHECK_FAILED and row["result"] == "fail" and row["mode"] == "registry+denylist"
    assert "denied-name:L1" in row["hits"]  # the denylist hit is redacted
    assert any("private-pricing-engine" in h for h in row["hits"])  # the registry hit keeps its legacy form
    assert "widget-quotes-v9" not in " ".join(row["hits"])
    assert row["hits"] == sorted(set(row["hits"]))


# ---- review regressions (E6/#112): no echo, .git clone URLs, owner boundary -----------------------------------------

def _hits(text, slugs=(), names=()):
    return O.denylist_leaks(text, set(slugs), set(names))


def test_cli_denylist_never_echoes_private_entries(tmp_path):
    deny = _write(tmp_path, "deny.txt", "northwind/secret-tool-2\nledger-x\n")
    leak = _write(tmp_path, "leak.md", "ok\nThe secret-tool-2 service and ledger-x.\n")
    p = run_cli("lint", "public-leak", leak, "--denylist", deny)
    assert p.returncode == CHECK_FAILED
    assert "northwind" not in p.stdout and "secret-tool-2" not in p.stdout.replace("secret-tool-2 service", "")
    assert "ledger-x" not in p.stdout
    assert _rows(p)[0]["hits"] == ["denied-name:L2", "private-name:L2"]


def test_denylist_matches_git_clone_urls():
    assert _hits("git clone https://github.com/northwind/hidden-tool.git", ["northwind/hidden-tool"]) == ["denied-slug:L1"]
    assert _hits("git clone git@github.com:northwind/hidden-tool.git", names=["hidden-tool"]) == ["denied-name:L1"]
    assert _hits("see hidden-tool.git.md", names=["hidden-tool"]) == []


def test_denylist_slug_needs_whole_owner_token():
    assert _hits("https://github.com/notnorthwind/app", ["northwind/app"]) == []
    assert _hits("https://github.com/northwind/app", ["northwind/app"]) == ["denied-slug:L1"]
    assert _hits("https://github.com/x.northwind/app", ["northwind/app"]) == []
