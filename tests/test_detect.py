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


# -- issues #79-#82: planning-heavy, docs-only and mobile shapes, low-confidence suggestions -------------------------
import json  # noqa: E402

from conftest import meta_dict, run_cli  # noqa: E402
from ctshowcase.detect import detect, required_sections  # noqa: E402


def _tree(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Match captured byte counts even on platforms that translate text newlines.
        path.write_bytes(content.encode("utf-8"))


def _sized(files, **kw):
    return meta_dict(files=list(files), file_sizes={k: len(v.encode("utf-8")) for k, v in files.items()}, **kw)


PLANNING = {"pipeline.py": "print('Northwind')\n", "planning/backlog.json": "[]" * 5000,
            "issues/issue-42.json": "{}" * 5000, ".github/issues/7.json": "{}" * 5000,
            "exports/generated-issues.json": "[]" * 5000, "Exported-Planning.json": "[]" * 5000}


@pytest.mark.parametrize("checkout", [False, True])
def test_planning_heavy_repo_is_not_a_dataset(tmp_path, checkout):
    _tree(tmp_path, PLANNING)
    meta = _sized(PLANNING)
    det = detect(meta, RepoFacts(meta, tmp_path if checkout else None))
    assert (det["type"], det["rule"]) == ("workspace", 25)
    assert "suggestion" not in det  # an ordinary workspace fallback is not low confidence


@pytest.mark.parametrize("name", ["issues.json", "generated-issues-data.json", "data/issues.json"])
@pytest.mark.parametrize("data_size,want", [(49, "workspace"), (50, "dataset"), (51, "dataset")])
def test_other_issue_data_stays_eligible_at_inclusive_threshold(name, data_size, want):
    meta = {"files": [name, "main.py"], "file_sizes": {name: data_size, "main.py": 100 - data_size}}
    assert detect_type(meta)[0] == want


@pytest.mark.parametrize("data_size,suggested", [(50, True), (59, True), (60, False), (90, False)])
def test_dataset_near_threshold_suggests_override(data_size, suggested):
    meta = {"files": ["rows.csv", "main.py"], "file_sizes": {"rows.csv": data_size, "main.py": 100 - data_size}}
    det = detect(meta)
    assert det["type"] == "dataset"
    assert det.get("suggestion") == ("type-suggestion:dataset:dataset-near-threshold:override-key=type" if suggested else None)


def test_empty_or_malformed_sizes_do_not_claim_dataset():
    assert detect_type({"files": ["main.py"], "file_sizes": {"data.json": 0, "other.txt": "bad"}}) == ("workspace", 25)
    assert detect_type({"files": ["data.json"], "file_sizes": ["data.json"]}) == ("workspace", 25)


def test_checkout_sizes_only_measure_captured_paths(tmp_path):
    # Regression: the composite Action writes meta.json into the checkout. Without captured sizes rule 24 is skipped
    # (main's behaviour), and an uncaptured local file never counts towards the data share.
    _tree(tmp_path, {"meta.json": json.dumps(meta_dict()) * 50})
    assert detect_type(meta_dict(), RepoFacts(meta_dict(), tmp_path)) == ("workspace", 25)
    _tree(tmp_path, {"main.py": "print('Northwind')\n"})
    meta = meta_dict(files=["main.py"], file_sizes={"main.py": 19})
    assert detect_type(meta, RepoFacts(meta, tmp_path)) == ("workspace", 25)


def test_checkout_uses_captured_sizes_without_stat_calls(tmp_path, monkeypatch):
    from pathlib import Path

    repo = tmp_path / "repo"
    _tree(repo, {"rows.csv": "a,b\n" * 100, "main.py": "print(1)"})
    outside = tmp_path / "outside.csv"
    meta = meta_dict(files=["rows.csv", "main.py"], file_sizes={
        "rows.csv": 1, "main.py": 1000, "linked.csv": 1,
        str(outside): 10000, "../outside.csv": 10000, "C:/outside.csv": 10000,
    })
    stat = Path.stat

    def guard_stat(path, *args, **kwargs):
        assert path.name not in ("rows.csv", "main.py", "linked.csv", "outside.csv")
        return stat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", guard_stat)
        assert detect_type(meta) == ("workspace", 25)
        assert detect_type(meta, RepoFacts(meta, repo)) == ("workspace", 25)


@pytest.mark.parametrize("name", ["README.md", "rows.csv"])
@pytest.mark.parametrize("checkout", [False, True])
def test_incomplete_tree_does_not_claim_docs_only_or_dataset(tmp_path, name, checkout):
    files = {name: "Northwind rows."}
    _tree(tmp_path, files)
    meta = _sized(files, files_complete=False)
    det = detect(meta, RepoFacts(meta, tmp_path if checkout else None))
    assert (det["type"], det["rule"]) == ("workspace", 25)
    assert det["suggestion"] == "type-suggestion:workspace:file-tree-incomplete:override-key=type"


def test_docs_only_repo_stays_workspace_with_suggestion(make_ctx):
    files = ["README.md", "docs/guide.md", "docs/faq.rst", "LICENSE", ".gitignore", ".gitattributes", ".editorconfig",
             "CODEOWNERS"]
    ctx = make_ctx(files=files)
    assert (ctx.det["type"], ctx.det["rule"]) == ("workspace", 25)
    assert "type-suggestion:workspace:docs-only:override-key=type" in ctx.logs
    assert "suggestion" not in detect({"files": files + ["src/main.py"]})


def test_unknown_tree_suggests_override_and_explicit_type_suppresses_it():
    assert detect({"owner": "Northwind-Trading-Co"})["suggestion"] == "type-suggestion:workspace:file-tree-unknown:override-key=type"
    assert "suggestion" not in detect({"files": ["README.md"]}, type_override="cli")
    assert "suggestion" not in detect({"files": ["README.md"]}, override={"type": "workspace"})


def test_mobile_keeps_variant_b_with_mobile_sections():
    mobile = detect({"files": ["app/src/main/AndroidManifest.xml"]})
    assert (mobile["type"], mobile["variant"]) == ("mobile-app", "B")
    names = [h for h, _ in required_sections(mobile)]
    assert {"Install", "Platforms"} <= set(names) and not {"Live Site", "Tech Stack"} & set(names)
    assert required_sections({"type": "mobile-app", "variant": "C"}) == required_sections({"type": "cli", "variant": "C"})
    assert required_sections({"type": "web-app", "variant": "B"})[1][0] == "Live Site"


def test_owner_rules_use_the_resolver():
    from ctshowcase.resolver import Resolver
    resolver = Resolver(registry={"orgs": {"CompleteTech-Security": {"former_slugs": ["Northwind-Old-Security"]}}})
    assert detect({"owner": "Northwind-Old-Security", "files": ["main.py"]}, same_owner=resolver.same)["type"] == \
        "security-check"


@pytest.mark.parametrize("checkout", [False, True])
@pytest.mark.parametrize("files,want,log", [
    (PLANNING, "workspace", None),
    ({"README.md": "# Northwind handbook\n", "docs/guide.md": "Guide.\n", ".gitignore": "*.pyc\n"}, "workspace",
     "type-suggestion:workspace:docs-only:override-key=type"),
    ({"rows.csv": "a,b\n" * 30, "main.py": "x" * 100}, "dataset", "type-suggestion:dataset:dataset-near-threshold:override-key=type")])
def test_cli_doctor_type_and_suggestion(tmp_path, checkout, files, want, log):
    repo = tmp_path / "repo"
    _tree(repo, files)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(_sized(files)), encoding="utf-8")
    result = run_cli("--meta", meta, *(["--repo-dir", repo] if checkout else ["--no-repo-dir"]), "doctor", "--format", "json")
    row = json.loads(result.stdout)
    assert row["type"] == want, result.stderr
    suggestions = [x for x in row["logs"] if x.startswith("type-suggestion:")]
    assert suggestions == ([log] if log else [])


def test_cli_checkout_holding_only_the_meta_file_is_not_a_dataset(tmp_path):
    # The composite Action's describe path: --meta inside the checkout, --repo-dir ".", no captured sizes.
    (tmp_path / "meta.json").write_text(json.dumps(meta_dict(description="Run the Northwind exports.")), encoding="utf-8")
    result = run_cli("--meta", "meta.json", "--repo-dir", ".", "doctor", "--format", "json", cwd=tmp_path)
    row = json.loads(result.stdout)
    assert row["type"] == "workspace", result.stderr
