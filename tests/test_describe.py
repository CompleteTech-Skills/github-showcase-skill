import pytest

from ctshowcase.describe import checks, propose


def rules(text, **kw):
    kw.setdefault("slug", "agentic-invoice-skill")
    kw.setdefault("type_", "agent-skills")
    kw.setdefault("has_brand_assets", True)
    return {c["rule"]: c["result"] for c in checks(text, **kw)}


GOOD = "Create branded CompleteTech LLC invoice PDFs for agentic development services, from deposit through final payment."


def test_keep_exemplar():
    assert propose(GOOD, slug="agentic-invoice-skill", type_="agent-skills", has_brand_assets=True)["action"] == "keep"


@pytest.mark.parametrize("text,rule", [
    ("x" * 141 + ".", "D1"), ("Create invoices", "D2"), ("Create invoices. Then send them.", "D3"),
    ("The invoice tool for teams.", "D4"), ("Create the best invoices.", "D5"), ("Create invoices — fast.", "D6"),
    ("Create invoices with v2.1 rules.", "D7"), ("Agentic invoice skill.", "D8"), ("Invoices for teams.", "V1"),
    ("Create invoices for teams, not affiliated with Acme.", "X1"),
])
def test_each_rule_fails(text, rule):
    assert rules(text)[rule] == "fail"


def test_b1_brand_mention():
    assert rules("Create invoices for teams.", has_brand_assets=True)["B1"] == "fail"
    assert rules("Create invoices for teams.", has_brand_assets=False)["B1"] == "pass"
    assert rules(GOOD + "", has_brand_assets=False)["B1"] == "fail"


def test_website_and_game_voice():
    assert rules("Source for complete.tech, the CompleteTech LLC company website.", slug="complete.tech",
                 type_="website", has_brand_assets=True)["V1"] == "pass"
    assert rules("Noul Who: play a browser deduction game against Jev at jevplay.games.", slug="jev-guess-who",
                 type_="game", has_brand_assets=False)["V1"] == "pass"


def test_edit_order_suffix():
    text = "Compile, de-duplicate, price and attribute local AI coding-agent usage into a ledger (CompleteTech LLC skill)."
    r = propose(text, slug="ai-usage-ledger-skill", type_="agent-skills", has_brand_assets=False)
    assert r["action"] == "edit" and "remove-skill-suffix" in r["edits"] and "(CompleteTech" not in r["text"]


def test_period_edit():
    r = propose("Create invoices for small teams", slug="x", type_="cli", has_brand_assets=False)
    assert r == {**r, "action": "edit", "text": "Create invoices for small teams."}


def test_needs_writer_never_composes():
    r = propose("", slug="netscaler-cve-2026-19489-check", type_="security-check", has_brand_assets=False)
    assert r["action"] == "needs-writer" and "text" not in r
    assert r["template"].startswith("Check <Product> versions for CVE-") and r["slots_known"]["id"] == "2026-19489"
