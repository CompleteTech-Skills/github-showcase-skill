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


@pytest.mark.parametrize("planning", ["planning/export.json", "issues/issue-42.json", ".github/issues/42.json"])
def test_administrative_json_is_not_a_dataset(planning):
    m = {"owner": "Northwind-Trading-Co", "repo": "pipeline", "files": [planning, "pipeline.py"],
         "file_sizes": {planning: 50_000, "pipeline.py": 100}}
    assert detect_type(m) == ("workspace", 25)


def test_docs_only_and_mobile_shapes(tmp_path):
    from ctshowcase.detect import detect, required_sections
    docs = {"owner": "Northwind-Trading-Co", "repo": "handbook", "files": ["README.md", "docs/guide.md"]}
    assert detect_type(docs) == ("documentation", 25)
    for f in ("README.md", "app/src/main/AndroidManifest.xml"):
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("mobile")
    mobile = detect({"owner": "Northwind-Trading-Co", "repo": "client"}, RepoFacts({}, tmp_path))
    names = [x[0] for x in required_sections(mobile)]
    assert mobile["type"] == "mobile-app" and mobile["variant"] == "B"
    assert "Platforms" in names and "Install" in names
    assert "Live Site" not in names


def test_dataset_local_and_metadata_agree(tmp_path):
    files = {"dataset.csv": "a,b\n" * 100, "README.md": "A dataset.", "planning/issues.json": "[]" * 2000}
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    m = {"owner": "Northwind-Trading-Co", "repo": "sample", "files": list(files),
         "file_sizes": {k: len(v) for k, v in files.items()}}
    assert detect_type(m) == detect_type(m, RepoFacts(m, tmp_path)) == ("dataset", 24)


def test_low_confidence_suggests_explicit_override():
    from ctshowcase.detect import detect
    meta = {"owner": "Northwind-Trading-Co", "repo": "sample", "files": ["main.py"]}
    guessed = detect(meta)
    assert guessed["confidence"] == "low"
    assert "type:" in guessed["suggestion"] and "--type" in guessed["suggestion"]
    assert "suggestion" not in detect(meta, type_override="cli")


def test_empty_or_malformed_sizes_do_not_claim_dataset():
    m = {"files": ["main.py"], "file_sizes": {"data.json": 0, "other.txt": "bad"}}
    assert detect_type(m) == ("workspace", 25)


@pytest.mark.parametrize("canonical,want,rule", [("CompleteTech-Security", "security-check", 6),
                                                ("CompleteTech-Games", "game", 12),
                                                ("CompleteTech-LLC-AI-Research", "research", 22)])
def test_owner_detection_uses_resolver(canonical, want, rule):
    meta = {"owner": "Northwind-Former", "repo": "sample", "files": ["probe.py"]}
    def same(a, b):
        return a == "Northwind-Former" and b == canonical
    assert detect_type(meta, same_owner=same) == (want, rule)


def test_context_reports_low_confidence_type(make_ctx):
    ctx = make_ctx(files=["README.md", "docs/guide.md"])
    assert ctx.det["type"] == "documentation"
    assert any(log.startswith("type-suggestion:documentation:") for log in ctx.logs)


def test_mobile_scaffold_uses_mobile_sections(make_ctx):
    from ctshowcase import readme
    ctx = make_ctx(files=["app/AndroidManifest.xml"])
    assert ctx.det["type"] == "mobile-app"
    readme.scaffold(ctx)
    assert "needs-input:B:Platforms" in ctx.logs
    assert "needs-input:B:Install" in ctx.logs


def test_mobile_explicit_variant_keeps_variant_contract():
    from ctshowcase.detect import required_sections
    mobile = {"type": "mobile-app", "variant": "C"}
    assert "Platforms" not in dict(required_sections(mobile))
    assert "Install" in dict(required_sections(mobile))
