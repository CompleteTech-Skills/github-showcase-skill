import pytest

from ctshowcase.detect import card_category, detect_type, variant_for
from ctshowcase.facts import RepoFacts

CASES = [
    (dict(fork=True), [], "fork", 1), (dict(repo="host-backup-20260914"), [], "backup", 2), (dict(repo=".github"), [], "github-profile", 3),
    (dict(is_template=True), [], "template", 4), ({}, ["SKILL.md"], "agent-skills", 5),
    (dict(owner="CompleTetech-Security"), [], "security-check", 6),
    ({}, [("package.json", '{"dependencies": {"@modelcontextprotocol/sdk": "1"}}')], "mcp-server", 7),
    ({}, [("manifest.json", '{"manifest_version": 3}')], "chrome-extension", 8), ({}, ["plugin.json"], "plugin", 9),
    ({}, [("requirements.txt", "discord.py\n")], "discord-bot", 10), ({}, [("requirements.txt", "python-telegram-bot\n")], "bot", 11),
    (dict(owner="CompleteTech-Games"), [], "game", 12), ({}, ["app/src/main/AndroidManifest.xml"], "mobile-app", 13),
    (dict(repo="nas.home.complete.tech"), [], "infrastructure", 14), (dict(repo="northwind-trading.com"), [], "website", 15),
    ({}, ["board.kicad_pcb"], "hardware", 16), ({}, ["compose.yaml"], "infrastructure", 17),
    ({}, [("package.json", '{"dependencies": {"react": "18"}}')], "web-app", 18),
    ({}, [("requirements.txt", "fastapi\n")], "api", 19),
    ({}, [("pyproject.toml", "[project]\nname='x'\n[project.scripts]\nx='x:main'\n")], "cli", 20),
    ({}, [("pyproject.toml", "[project]\nname='x'\n")], "library", 21), (dict(owner="CompleteTech-LLC-AI-Research"), [], "research", 22),
    (dict(repo="build-ai-workflows-in-5-steps"), [], "tutorial", 23), ({}, [], "workspace", 25),
]


@pytest.mark.parametrize("meta,files,want,rule", CASES)
def test_rules(tmp_path, meta, files, want, rule):
    for f in files:
        name, content = f if isinstance(f, tuple) else (f, "x")
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    m = {"owner": "Northwind-Trading-Co", "repo": "thing", **meta}
    assert detect_type(m, RepoFacts(m, tmp_path)) == (want, rule)


def test_dataset_rule():
    m = {"owner": "Northwind-Trading-Co", "repo": "data", "files": ["a.csv", "b.py"], "file_sizes": {"a.csv": 900, "b.py": 100}}
    assert detect_type(m, RepoFacts(m)) == ("dataset", 24)


def test_variant_table():
    assert variant_for("agent-skills", {"owner": "CompleteTech-Skills"}) == "A"
    assert variant_for("agent-skills", {"owner": "CompleteTech-LLC"}) == "C"
    assert variant_for("workspace", {"visibility": "private"}) == "I"
    assert variant_for("workspace", {"visibility": "public"}) == "C"
    assert variant_for("security-check", {}) == "F" and card_category("security-check") == "CVE checker"
    assert card_category("fork") is None
