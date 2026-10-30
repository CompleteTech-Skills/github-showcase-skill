"""E5.2.1: `--description` renders banner, card, content social and readme from a proposed (staged) one-sentence
description. Off by default; the live metadata file is never modified. Fixtures are synthetic (Northwind)."""
import json
import shutil

from conftest import EX, run_cli

META = EX / "meta" / "northwind-support-triage-agent.json"
REPO = EX / "repos" / "northwind-support-triage-agent"


def _repo(tmp_path):
    shutil.copytree(REPO, tmp_path, dirs_exist_ok=True)
    return tmp_path


def _json(proc):
    return json.loads(proc.stdout)


def test_banner_card_accept_description(tmp_path):
    rd = _repo(tmp_path)
    text = "Triage support tickets with an agent."
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", text)
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"]
    assert r["staged_description"]["text"] == text

    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                "--out", rd / "docs/images/card.svg", "--description", text)
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"]
    assert r["staged_description"]["text"] == text


def test_readme_uses_staged_tagline(tmp_path):
    rd = _repo(tmp_path)
    before_meta = META.read_text(encoding="utf-8")
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
                "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"]
    readme = (rd / "README.md").read_text(encoding="utf-8")
    start = readme.index("<!-- showcase:tagline:start -->")
    end = readme.index("<!-- showcase:tagline:end -->")
    assert "**Staged sentence.**" in readme[start:end]
    assert META.read_text(encoding="utf-8") == before_meta


def test_content_social_accepts_description(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "content", "social",
                "--out", rd / "assets/social-preview.png", "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"]


def test_default_unchanged(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner", "--out", rd / "docs/images/banner.png")
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged_description" not in r
    assert "staged-description" not in r["logs"]


def test_empty_description_is_usage_error(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", "  ")
    assert p.returncode == 2


def test_description_is_stripped(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                "--out", rd / "docs/images/card.svg", "--description", "  Padded sentence.  ")
    assert p.returncode == 0, p.stderr
    assert _json(p)["staged_description"]["text"] == "Padded sentence."


def test_live_description_reported_and_meta_untouched(tmp_path):
    rd = _repo(tmp_path)
    before_meta = META.read_text(encoding="utf-8")
    live = json.loads(before_meta).get("description") or ""
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                "--out", rd / "docs/images/card.svg", "--description", "A different sentence.")
    assert p.returncode == 0, p.stderr
    staged = _json(p)["staged_description"]
    assert staged["live_differs"] is (live.strip() != "A different sentence.")
    assert META.read_text(encoding="utf-8") == before_meta
