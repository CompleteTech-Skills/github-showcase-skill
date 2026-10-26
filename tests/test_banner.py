import io
import json

import pytest
from PIL import Image

from conftest import EX, FIX, ROOT, run_cli

LOGO = ROOT / "assets" / "brand" / "logo.png"  # the golden's configuration: the full logo on the white card


def _render(tmp_path, meta, *extra, repo_dir=None, name="banner.png"):
    out = tmp_path / "docs" / "images" / name
    args = ["--meta", meta] + (["--repo-dir", repo_dir] if repo_dir else ["--no-repo-dir"]) + ["--format", "json", "banner",
                                                                                               "--out", out, *extra]
    p = run_cli(*args)
    return p, out


@pytest.fixture(scope="module")
def php2shell(tmp_path_factory):
    t = tmp_path_factory.mktemp("php")
    p, out = _render(t, FIX / "CompleTetech-Security__php2shell-check.json", "--icon", LOGO,
                     repo_dir=EX / "repos" / "php2shell-check")
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout), Image.open(out).convert("RGB").resize((1280, 360), Image.LANCZOS), out


def test_size_budget_opaque(php2shell):
    info, im, out = php2shell
    raw = out.read_bytes()
    big = Image.open(io.BytesIO(raw))
    assert big.size in ((2560, 720), (1280, 360)) and big.mode in ("RGB", "P") and len(raw) <= 300_000


def test_white_card_geometry(php2shell):
    _, im, _ = php2shell
    px = im.load()
    rows = [y for y in range(360) if px[260, y][0] > 240 and px[260, y][2] > 240]
    cols = [x for x in range(0, 520) if px[x, 180][0] > 240 and px[x, 180][2] > 240]
    assert abs(min(rows) - 70) <= 2 and abs(max(rows) - 289) <= 2
    assert abs(min(cols) - 56) <= 2 and abs(max(cols) - 475) <= 2


def test_text_column_chips_and_bar(php2shell, brand):
    info, im, _ = php2shell
    px = im.load()
    chips = info["chips"]
    assert [c["text"] for c in chips] == ["CVE-2026-109618", "CVE-2026-109619", "No exploit payloads"]
    assert abs(chips[0]["box"][0] - 520) <= 4 and abs(chips[0]["box"][1] - 243) <= 3
    gold = brand.family("completetech")["tokens"]["chip_key"]["bg"].lstrip("#")
    g = tuple(int(gold[i:i + 2], 16) for i in (0, 2, 4))
    assert sum(1 for x in range(520, 900) if all(abs(px[x, 248][k] - g[k]) <= 6 for k in range(3))) > 250
    bar = brand.family("completetech")["tokens"]["bar"]["from"].lstrip("#")
    b = tuple(int(bar[i:i + 2], 16) for i in (0, 2, 4))
    for y in (355, 358):
        assert all(abs(px[640, y][k] - b[k]) <= 3 for k in range(3))
    assert info["eyebrow"] == "COMPLETETECH LLC\u2002·\u2002SECURITY TOOLS"
    assert info["subtitle"] == "Passive PHP2Shell exposure triage for websites"


def test_sidecar_and_fingerprint_stable(tmp_path):
    meta = FIX / "CompleteTech-Skills__agentic-email-skill.json"
    _render(tmp_path, meta)
    side = json.loads((tmp_path / "docs/images/.showcase.json").read_text())
    p = run_cli("--meta", meta, "--no-repo-dir", "fingerprint", "--out-dir", tmp_path / "docs/images")
    assert json.loads(p.stdout)["changed"] is False
    assert json.loads(p.stdout)["fingerprint"] == side["fingerprint"]


def test_long_slug_two_lines(tmp_path):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "northwind-customer-support-email-triage-agent-pilot-x",
                                "description": "Run the Northwind triage agent.", "visibility": "public", "license": "MIT"}))
    p, out = _render(tmp_path, meta, "--chip", "Python", "--chip", "MIT")
    assert p.returncode == 0, p.stdout + p.stderr
    assert len(json.loads(p.stdout)["title_lines"]) == 2


def test_empty_description_exit_4(tmp_path):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "x", "description": ""}))
    p, out = _render(tmp_path, meta)
    assert p.returncode == 4 and not out.exists()


def test_keep_existing_and_refusals(tmp_path):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"owner": "AI-Ascension", "repo": "sts2-agent", "description": "Play Slay the Spire 2 with agents.",
                                "visibility": "public", "language": "Python", "license": "MIT"}))
    repo = tmp_path / "repo"
    repo.mkdir()
    # q57 aia/pres defaults: the hero in AI-Ascension's own palette goes above the README's own banner ...
    (repo / "README.md").write_text('<p align="center"><img src="assets/hero.png" alt="STS2"></p>\n\n# STS2 Agent\n')
    p, out = _render(tmp_path, meta, repo_dir=repo)
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "ok" and out.exists(), p.stdout + p.stderr
    out.unlink()
    # ... keep-existing keeps the README's own banner instead only when q57 `pres` is "Leave them unchanged"
    from conftest import brand_config
    p = run_cli("--config", brand_config(tmp_path, preserve_banner="unchanged"), "--meta", meta, "--repo-dir", repo,
                "--format", "json", "banner", "--out", out)
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "exempt" and not out.exists()
    # ... and a README without one gets the family-palette banner (decision 13)
    (repo / "README.md").write_text("# STS2 Agent\n\nPlay it.\n")
    p, out = _render(tmp_path, meta, repo_dir=repo)
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "ok" and out.exists(), p.stdout + p.stderr
    meta.write_text(json.dumps({"owner": "BunsDev", "repo": "x", "description": "Something."}))
    assert _render(tmp_path, meta)[0].returncode == 2
    meta.write_text(json.dumps({"owner": "romgenie-following-repos", "repo": "x", "description": "Fork.", "fork": True}))
    assert json.loads(_render(tmp_path, meta)[0].stdout)["result"] == "exempt"


def test_deterministic(tmp_path):
    meta = FIX / "jevplay-games__jev-minesweeper.json"
    _, a = _render(tmp_path, meta, repo_dir=EX / "repos" / "jev-minesweeper", name="a.png")
    _, b = _render(tmp_path, meta, repo_dir=EX / "repos" / "jev-minesweeper", name="b.png")
    assert a.read_bytes() == b.read_bytes()


def test_org_mark_fills_the_card(tmp_path):
    """A T1 org mark (Neon Night avatar) brings its own ground: the card takes it, the avatar is full-bleed (P1.2/P1.4)."""
    p, out = _render(tmp_path, FIX / "CompleTetech-Security__php2shell-check.json", repo_dir=EX / "repos" / "php2shell-check")
    info = json.loads(p.stdout)
    assert p.returncode == 0 and info["icon"]["source"] == "org-mark" and info["icon"]["full_bleed"] is True
    im = Image.open(out).convert("RGB").resize((1280, 360), Image.LANCZOS)
    r, g, b = im.getpixel((80, 180))  # inside the card, left of the avatar: the avatar's own dark ground, not white
    assert max(r, g, b) < 60


def test_fewer_than_two_chips(tmp_path):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "tiny", "description": "Run the tiny tool.",
                                "visibility": "public"}))
    p, out = _render(tmp_path, meta)
    assert p.returncode == 4 and "banner-chips" in p.stdout and not out.exists()
    p, out = _render(tmp_path, meta, "--allow-few-chips")
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "incomplete" and out.exists()
    from ctshowcase import pnglint
    assert pnglint.lint_banner(out)["result"] == "INCOMPLETE"


def test_subtitle_prefers_one_line(make_ctx, fonts):
    from ctshowcase import banner
    ctx = make_ctx(repo="jev-311-heatmap", description="NYC 311 complaint heatmaps built with Jev, with borough filters, "
                   "time sliders and a shareable static export for every neighbourhood.", language="Python")
    _, info = banner.layout(ctx, fonts, attrs=["Python", "MIT"])
    assert len(info["subtitle_lines"]) == 1 and info["subtitle"].startswith("NYC 311 complaint heatmaps built with Jev")
    assert info["subtitle"].split()[-1] not in banner.HEAD_STOP
    assert banner.description_heads("NYC 311 complaint heatmaps built with Jev") == []
