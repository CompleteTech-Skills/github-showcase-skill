import json
import xml.etree.ElementTree as ET

from ctshowcase import card, svglint
from conftest import FIX, run_cli


def test_card_contract(tmp_path, brand):
    out = tmp_path / "card.svg"
    p = run_cli("--meta", FIX / "CompleteTech-Skills__agentic-email-skill.json", "--no-repo-dir", "--format", "json", "card",
                "--out", out, "--png", tmp_path / "card.png")
    assert p.returncode == 0, p.stdout + p.stderr
    raw = out.read_bytes()
    assert len(raw) <= 40_000 and svglint.lint_bytes("card", raw)["result"] == "PASS"
    root = ET.fromstring(raw)
    desc = json.loads((FIX / "CompleteTech-Skills__agentic-email-skill.json").read_text())["description"]
    assert root.get("viewBox") == "0 0 400 160" and root.get("aria-label") == f"agentic-email-skill: {desc}"
    assert b"<text" not in raw
    plate = json.loads(p.stdout)["icon"]["plate"]  # the org mark's own night ground (no plate inside a plate)
    assert f'rx="16" fill="{plate}"'.encode() in raw and json.loads(p.stdout)["icon"]["full_bleed"] is True
    assert (tmp_path / "card.png").is_file()


def test_card_deterministic(make_ctx, fonts):
    a = card.render(make_ctx(), fonts)[0]
    b = card.render(make_ctx(), fonts)[0]
    assert a == b


def test_drop_order(make_ctx, fonts):
    ctx = make_ctx(repo="acme-cve-2026-11111-check", description="Check CVE-2026-11111 and CVE-2026-22222 offline.",
                   stargazers_count=1234, language="Jupyter Notebook", license="AGPL-3.0")
    _, _, info = card.render(ctx, fonts)
    kinds = [i["kind"] for i in info["items"]]
    assert kinds[:2] == ["key", "key"]  # both CVE ids (P2.12)
    assert "stars" not in kinds  # stars drop first, then attributes from the end, then the second key folds to +1
    assert all(i["x"] + i["w"] <= 400 - 16 + 0.5 for i in info["items"])
    few = make_ctx(stargazers_count=12, language="Go", license="MIT")
    assert "stars" in [i["kind"] for i in card.render(few, fonts)[2]["items"]]


def test_art_fail_on_long_description(tmp_path):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "x", "description": "Word " * 60}))
    p = run_cli("--meta", meta, "--no-repo-dir", "card", "--out", tmp_path / "c.svg")
    assert p.returncode == 3 and not (tmp_path / "c.svg").exists()


def test_card_eyebrow_fixed_and_slug_split(make_ctx, fonts):
    a = card.render(make_ctx(), fonts)[2]
    b = card.render(make_ctx(repo="northwind-customer-support-email-triage-agent", description="Run it. " * 12), fonts)[2]
    assert a["eyebrow"] == b["eyebrow"]
    lines = card.split_slug(fonts, "mono-medium", "acme-cve-2026-12345-check", 20, 280)
    assert lines in (["acme-", "cve-2026-12345-check"], ["acme-cve-2026-12345-", "check"])  # never inside the CVE id


def test_card_matches_banner_eyebrow(make_ctx, fonts):
    from ctshowcase import banner
    ctx = make_ctx(owner="CompleTetech-Security", repo="x-cve-2026-11111-check", description="Check CVE-2026-11111.")
    assert card.render(ctx, fonts)[2]["eyebrow"] == banner.eyebrow_text(ctx)
