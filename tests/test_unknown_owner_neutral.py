"""An owner with no brand row borrows no shipped identity: neutral style, own name, no footer, no brand topic."""
import json

import pytest

from conftest import run_cli

OWNER = "Synthetic-Outside-Owner"


@pytest.fixture
def outside_meta(tmp_path, monkeypatch):
    estate = tmp_path / "synthetic-estate"
    (estate / "decisions").mkdir(parents=True)
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(estate))
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": OWNER, "repo": "sample-cli", "visibility": "public", "fork": False,
                                "description": "Inspect synthetic records from the command line.",
                                "topics": ["cli", "python"], "language": "Python", "license": "MIT",
                                "files": ["main.py", "README.md"]}), encoding="utf-8")
    return meta


def test_org_row_is_neutral(brand):
    row = brand.org(OWNER)
    assert row["known"] is False
    assert row["family"] == "neutral"
    assert row["brand_topic"] is None
    assert row["footer"] is False


def test_style_uses_owner_name_not_shipped_label(brand):
    st = brand.style(OWNER)
    assert st["name"] == "neutral"
    assert st["company_label"] == OWNER
    shipped = brand.family("completetech")
    assert st["tokens"]["accent"] != shipped["tokens"]["accent"]
    assert st["tokens"]["chip_key"]["bg"] != shipped["tokens"]["chip_key"]["bg"]


def test_context_falls_back_to_wordmark_and_own_name(make_ctx):
    ctx = make_ctx(owner=OWNER, repo="sample-cli")
    assert "needs-input:org-row" in ctx.logs
    assert ctx.company == OWNER
    icon, source = ctx.light_icon()
    assert (icon, source) == (None, "family-wordmark")
    assert ctx.footer_status() == "exempt:footer"


def test_cli_outputs_carry_no_shipped_identity(brand, outside_meta, tmp_path):
    company, short = brand.strings["company"], brand.strings["short"]
    site = brand.raw["footer"]["href"]

    footer = run_cli("--meta", outside_meta, "--no-repo-dir", "footer")
    assert footer.returncode == 0, footer.stderr
    assert json.loads(footer.stdout)["logs"] == ["exempt:footer"]
    assert site not in footer.stdout

    topics = run_cli("--meta", outside_meta, "--no-repo-dir", "topics")
    data = json.loads(topics.stdout)
    assert "needs-input:brand-topic" in data["logs"]
    assert data["add"] == []

    card = tmp_path / "card.svg"
    res = run_cli("--meta", outside_meta, "--no-repo-dir", "card", "--out", card)
    assert res.returncode == 0, res.stderr
    svg = card.read_text(encoding="utf-8")
    assert company not in svg and short.upper() not in svg


def test_neutral_style_has_its_own_canvas(brand):
    """The house canvas is CompleteTech's navy gradient grid; an owner with no row gets the neutral canvas instead."""
    import json
    style = brand.style("Synthetic-Outside-Owner")
    house = brand.raw["defaults"]["canvas"]
    assert style["canvas"] == brand.raw["chart"]["neutral"]["canvas"] != house
    for colour in ("#001F3F", "#1E3A8A", "#00A7FD", "#0081ED", "#005ADD", "#FFC300"):
        assert colour.lower() not in json.dumps(style).lower(), colour
