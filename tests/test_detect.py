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
import subprocess  # noqa: E402
import sys  # noqa: E402

from conftest import ROOT, meta_dict, run_cli  # noqa: E402
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


@pytest.mark.parametrize("name", ["issues.json", "generated-issues-data.json", "data/issues.json", "data/issues/records.parquet"])
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



@pytest.mark.parametrize("size, expected", [({}, "workspace"), ({"size": None}, "workspace"),
                                          ({"size": True}, "workspace"), ({"size": 0}, "dataset")])
def test_remote_capture_does_not_infer_sizes_for_unmeasured_blobs(monkeypatch, size, expected):
    from ctshowcase import meta as capture

    name = "Northwind-Trading-Co/sample-data"
    responses = {
        f"repos/{name}": {"full_name": name, "default_branch": "main"},
        f"repos/{name}/git/trees/main?recursive=1": {
            "truncated": False,
            "tree": [
                {"type": "blob", "path": "rows.csv", "size": 90},
                {"type": "blob", "path": "main.py", **size},
            ],
        },
    }
    monkeypatch.setattr(capture, "_gh", lambda path, **_: responses.get(path))
    result = capture.from_gh(name)
    assert result["files_complete"] is True
    assert result["files"] == ["main.py", "rows.csv"]
    assert detect_type(result)[0] == expected
    if expected == "dataset":
        assert result["file_sizes"]["main.py"] == 0
    else:
        assert "main.py" not in result["file_sizes"]


def test_legacy_size_only_capture_can_still_identify_dataset():
    assert detect_type({"file_sizes": {"rows.csv": 90, "main.py": 10}}) == ("dataset", 24)


@pytest.mark.parametrize("missing", [{}, {"main.py": "10"}, {"main.py": False}, {"main.py": -10}])
def test_dataset_requires_valid_sizes_for_all_substantive_tree_paths(missing):
    meta = {"files": ["rows.csv", "main.py", "planning/backlog.json"],
            "file_sizes": {"rows.csv": 90, **missing}}
    assert detect_type(meta) == ("workspace", 25)
    meta["file_sizes"]["main.py"] = 10
    assert detect_type(meta) == ("dataset", 24)


def test_empty_or_malformed_sizes_do_not_claim_dataset():
    assert detect_type({"files": ["main.py"], "file_sizes": {"data.json": 0, "other.txt": "bad"}}) == ("workspace", 25)
    assert detect_type({"files": ["data.json"], "file_sizes": ["data.json"]}) == ("workspace", 25)



@pytest.mark.parametrize("fields", [
    {"files": None}, {"files": ["rows.csv", None]}, {"files": ["rows.csv", "./main.py"]},
    {"files_complete": None}, {"files_complete": 0}, {"files_complete": "true"},
])
def test_explicitly_invalid_capture_is_not_a_legacy_size_map(fields):
    meta = {"file_sizes": {"rows.csv": 90, "main.py": 10}, **fields}
    assert detect_type(meta) == ("workspace", 25)



@pytest.mark.parametrize("fields", [
    {"files": None}, {"files": ["rows.csv", "main.py"], "files_complete": None},
])
def test_metadata_cli_preserves_explicitly_unknown_capture(tmp_path, fields):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(file_sizes={"rows.csv": 90, "main.py": 10}, **fields)), encoding="utf-8")
    result = run_cli("--meta", meta, "--no-repo-dir", "meta")
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert "files" in output
    assert output["detected"]["type"] == "workspace"
    if "files_complete" in fields:
        assert output["files_complete"] is None
        assert "file-tree-incomplete" in output["detected"]["suggestion"]


def test_dataset_share_keeps_the_inclusive_cutoff_exact():
    large = 2 ** 54
    meta = {"file_sizes": {"rows.csv": large - 1, "main.py": large}}
    assert detect_type(meta) == ("workspace", 25)
    meta["file_sizes"]["rows.csv"] = large
    assert detect_type(meta) == ("dataset", 24)


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
        "rows.csv": 1, "main.py": 1000, "linked.csv": 10000, "./rows.csv": 10000,
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


@pytest.mark.parametrize("visibility,variant", [("public", "C"), ("private", "I")])
def test_dedicated_docs_repo_gets_documentation_type_and_sections(make_ctx, visibility, variant):
    files = ["README.md", "docs/guide.md", "docs/faq.rst", "LICENSE", ".gitignore", ".gitattributes", ".editorconfig",
             "CODEOWNERS"]
    ctx = make_ctx(files=files, visibility=visibility)
    assert ctx.det["variant"] == variant
    assert (ctx.det["type"], ctx.det["rule"]) == ("documentation", 25)
    assert "type-suggestion:documentation:docs-only:override-key=type" in ctx.logs
    from ctshowcase.detect import required_sections, standard
    assert "documentation" in standard("topics")["type_topics"]
    assert [name for name, _ in required_sections(ctx.det, meta=ctx.meta)] == ["About", "Documentation", "License"]
    alternative = "I" if variant == "C" else "C"
    assert required_sections(ctx.det, alternative, meta=ctx.meta) == standard("readme-variants")["variants"][alternative]
    assert detect({"files": files + ["src/main.py"]})["type"] == "workspace"
    assert "suggestion" not in detect({"files": files + ["src/main.py"]})



@pytest.mark.parametrize("checkout", [False, True])
def test_showcase_outputs_do_not_change_documentation_type(tmp_path, checkout):
    files = {
        "README.md": "# Guide\n",
        "docs/guide.md": "# Maintainer guide\n",
        "docs/images/.showcase.json": '{"captured_bytes":"' + "x" * 2000 + '"}',
        "docs/images/banner.png": "synthetic banner bytes",
        "docs/images/card.svg": "synthetic card bytes",
        "docs/images/badges/type-documentation.svg": "synthetic badge bytes",
        "assets/icon.png": "synthetic icon bytes",
        "assets/intro.svg": "synthetic introduction bytes",
        "assets/social-preview.jpg": "synthetic JPEG preview bytes",
    }
    if checkout:
        _tree(tmp_path, files)
    meta = _sized(files, files_complete=True)
    facts = RepoFacts(meta, tmp_path if checkout else None)
    assert detect_type(meta, facts) == ("documentation", 25)
    if checkout:
        _tree(tmp_path, {"docs/catalog.json": json.dumps(["x"] * 300)})
    files["docs/catalog.json"] = json.dumps(["x"] * 300)
    meta = _sized(files, files_complete=True)
    facts = RepoFacts(meta, tmp_path if checkout else None)
    assert detect_type(meta, facts) == ("dataset", 24)


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



def test_mobile_readme_explicit_variant_keeps_its_verified_manifest_facts(tmp_path, make_ctx):
    from ctshowcase.readme import section_facts

    files = {
        "app/src/main/AndroidManifest.xml": "<manifest />",
        "requirements.txt": "example-dependency==1.0",
        "package.json": json.dumps({"bin": {"northwind": "app.js"}}),
    }
    _tree(tmp_path, files)
    mobile = make_ctx(repo_dir=tmp_path)
    assert (mobile.det["type"], mobile.det["variant"]) == ("mobile-app", "B")
    assert section_facts(mobile, "Install") is None
    _tree(tmp_path, {".github/showcase.yml": "variant: C"})
    explicit = make_ctx(repo_dir=tmp_path)
    assert (explicit.det["type"], explicit.det["variant"]) == ("mobile-app", "C")
    assert "pip install -r requirements.txt" in section_facts(explicit, "Install")
    assert "npm install" in section_facts(explicit, "Install")
    assert "northwind --help" in section_facts(explicit, "Quick Start")


def test_owner_rules_use_the_resolver():
    from ctshowcase.resolver import Resolver
    resolver = Resolver(registry={"orgs": {"CompleteTech-Security": {"former_slugs": ["Northwind-Old-Security"]}}})
    assert detect({"owner": "Northwind-Old-Security", "files": ["main.py"]}, same_owner=resolver.same)["type"] == \
        "security-check"


def test_early_rules_do_not_load_brand_config(monkeypatch):
    from ctshowcase import config

    def unexpected_load(**kwargs):
        pytest.fail("rules 1 and 2 do not need owner resolution")

    monkeypatch.setattr(config, "load_brand", unexpected_load)
    assert detect_type({"fork": True}) == ("fork", 1)
    assert detect_type({"repo": "sample-backup-20261015"}) == ("backup", 2)


def test_meta_and_fingerprint_use_selected_brand_aliases(tmp_path, brand):
    from copy import deepcopy

    from ctshowcase import fingerprint as fp
    from ctshowcase.config import load_brand

    raw = deepcopy(brand.raw)
    raw["orgs"]["CompleteTech-Security"]["former_slugs"].append("Northwind-Old-Security")
    config = tmp_path / "brand.yaml"
    config.write_text(json.dumps(raw), encoding="utf-8")
    meta = meta_dict(owner="Northwind-Old-Security", files=["main.py"])
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(meta), encoding="utf-8")

    args = ("--meta", path, "--no-repo-dir", "--config", config)
    result = run_cli(*args, "meta")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["detected"]["type"] == "security-check"

    result = run_cli(*args, "fingerprint", "--out-dir", tmp_path)
    assert result.returncode == 0, result.stderr
    expected = fp.inputs(meta, None)
    expected["type"] = "security-check"
    assert json.loads(result.stdout)["fingerprint"] == fp.fingerprint(expected, load_brand(config).sha256)



def test_meta_explicit_type_resolves_low_confidence_suggestion(tmp_path):
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(meta_dict(files=["README.md"])), encoding="utf-8")
    args = ("--meta", path, "--no-repo-dir")
    automatic = run_cli(*args, "meta")
    assert automatic.returncode == 0, automatic.stderr
    assert "type-suggestion:workspace:docs-only" in automatic.stdout
    explicit = run_cli(*args, "--type", "cli", "meta")
    assert explicit.returncode == 0, explicit.stderr
    detected = json.loads(explicit.stdout)["detected"]
    assert (detected["type"], detected["rule"]) == ("cli", 0)
    assert "suggestion" not in detected


@pytest.mark.parametrize("checkout", [False, True])
@pytest.mark.parametrize("files,want,log", [
    (PLANNING, "workspace", None),
    ({"README.md": "# Northwind handbook\n", "docs/guide.md": "Guide.\n", ".gitignore": "*.pyc\n"}, "documentation",
     "type-suggestion:documentation:docs-only:override-key=type"),
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


@pytest.mark.parametrize("tracked_capture", [False, True])
def test_docs_only_cli_excludes_only_its_uncaptured_metadata_input(tmp_path, tracked_capture):
    children = {"README.md": "# Northwind\n", "docs/guide.md": "# Guide\n"}
    name = "capture.snapshot.json"
    _tree(tmp_path, children)
    captured = list(children) + ([name] if tracked_capture else [])
    capture = tmp_path / name
    capture.write_text(json.dumps(meta_dict(files=captured, files_complete=True)), encoding="utf-8")
    args = ["--meta", capture, "--repo-dir", tmp_path]
    expected = "workspace" if tracked_capture else "documentation"
    result = run_cli(*args, "meta")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["detected"]["type"] == expected
    doctor = run_cli(*args, "doctor", "--format", "json")
    assert json.loads(doctor.stdout)["type"] == expected

    if not tracked_capture:
        _tree(tmp_path, {"genuine-data.json": "{}"})
        with_code = run_cli(*args, "meta")
        assert json.loads(with_code.stdout)["detected"]["type"] == "workspace"


def test_docs_only_adopt_matches_topics_with_local_metadata_input(tmp_path):
    files = {"README.md": "# Northwind handbook\n", "docs/guide.md": "# Maintainer guide\n"}
    _tree(tmp_path, files)
    capture = tmp_path / "capture.snapshot.json"
    owner, repo = "CompleteTech-Skills", "northwind-handbook"
    capture.write_text(json.dumps(meta_dict(owner=owner, repo=repo, files=list(files), files_complete=True)),
                       encoding="utf-8")
    args = ["--meta", capture, "--repo-dir", tmp_path, "--format", "json"]
    topics = run_cli(*args, "topics")
    adopted = run_cli(*args, "adopt", f"{owner}/{repo}")
    assert topics.returncode == 1, topics.stdout + topics.stderr
    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    assert "documentation" in json.loads(topics.stdout)["proposed"]
    result = json.loads(adopted.stdout)
    assert result["type"] == "documentation"
    assert any(log.startswith("type-suggestion:documentation:docs-only") for log in result["logs"])


def test_documentation_type_ignores_linked_worktree_checkout_pointer(tmp_path):
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    _tree(primary, {"README.md": "# Northwind\n", "docs/guide.md": "# Maintainer guide\n"})

    def git(*args):
        return subprocess.run(["git", "-C", str(primary), *args], capture_output=True, text=True, check=True)

    git("init", "-q")
    git("add", "README.md", "docs/guide.md")
    git("-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Docs fixture")
    git("worktree", "add", "--detach", str(worktree), "HEAD")
    assert (worktree / ".git").is_file()
    facts = RepoFacts({}, worktree)
    assert facts.files == ["README.md", "docs/guide.md"]
    assert detect_type({}, facts) == ("documentation", 25)


@pytest.mark.parametrize("checkout", [False, True])
@pytest.mark.parametrize("scope,expected", [("", "workspace"),
                                            ("for: Northwind-Trading-Co/other-repo\n", "documentation")])
def test_meta_advice_respects_scoped_repository_type(tmp_path, checkout, scope, expected):
    config = "type: workspace\n" + scope
    files = {"README.md": "# Handbook\n", "docs/guide.md": "# Guide\n", ".github/showcase.yml": config}
    repo = tmp_path / "repo"
    if checkout:
        _tree(repo, files)
    capture = tmp_path / "capture.json"
    data = meta_dict(files=list(files))
    data["manifests"] = {".github/showcase.yml": config}
    capture.write_text(json.dumps(data), encoding="utf-8")
    args = ["--meta", capture, *(["--repo-dir", repo] if checkout else ["--no-repo-dir"])]
    snapshot = run_cli(*args, "meta")
    assert snapshot.returncode == 0, snapshot.stderr
    detected = json.loads(snapshot.stdout)["detected"]
    assert detected["type"] == expected
    assert ("suggestion" in detected) == (expected == "documentation")
    doctor = run_cli(*args, "doctor", "--format", "json")
    assert json.loads(doctor.stdout)["type"] == expected

    explicit = run_cli(*args, "--type", "cli", "meta")
    assert json.loads(explicit.stdout)["detected"]["type"] == "cli"


@pytest.mark.parametrize("checkout", [False, True])
@pytest.mark.parametrize("manifest", [False, True])
def test_authored_build_code_prevents_docs_only_classification(tmp_path, checkout, manifest):
    files = {"README.md": "# Handbook\n", "docs/guide.md": "# Guide\n", "build/tool.js": "console.log('guide');\n"}
    manifests = {"package.json": '{"scripts":{"build":"node build/tool.js"}}'} if manifest else {}
    files.update(manifests)
    repo = tmp_path / "repo"
    if checkout:
        _tree(repo, files)
    capture = tmp_path / "capture.json"
    data = _sized(files, manifests=manifests) if not checkout else meta_dict()
    capture.write_text(json.dumps(data), encoding="utf-8")
    args = ["--meta", capture, *(["--repo-dir", repo] if checkout else ["--no-repo-dir"])]
    snapshot = run_cli(*args, "meta")
    detected = json.loads(snapshot.stdout)["detected"]
    assert detected["type"] == "workspace"
    assert "suggestion" not in detected
    doctor = run_cli(*args, "doctor", "--format", "json")
    assert json.loads(doctor.stdout)["type"] == "workspace"


def test_meta_out_repeated_inside_docs_checkout_keeps_type_and_logs(tmp_path):
    _tree(tmp_path, {"README.md": "# Handbook\n", "docs/guide.md": "# Guide\n"})
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    output = tmp_path / "capture.snapshot.json"
    args = ["--repo-dir", tmp_path, "meta", "--out", output]
    first = run_cli(*args)
    assert first.returncode == 0, first.stderr
    payload = output.read_bytes()
    second = run_cli(*args)
    assert second.returncode == 0, second.stderr
    assert output.read_bytes() == payload
    result = json.loads(second.stdout)
    assert result == json.loads(first.stdout)
    assert result["detected"]["type"] == "documentation"
    assert result["logs"] == ["type-suggestion:documentation:docs-only:override-key=type"]

    subprocess.run(["git", "-C", str(tmp_path), "add", "--", output.name], check=True, capture_output=True)
    tracked = run_cli(*args)
    assert tracked.returncode == 0, tracked.stderr
    assert json.loads(tracked.stdout)["detected"]["type"] == "workspace"


def test_meta_counts_tracked_input_without_captured_file_list(tmp_path):
    capture = "tracked[1].json"
    _tree(tmp_path, {"README.md": "# Handbook\n", "docs/guide.md": "# Guide\n", capture: json.dumps(meta_dict())})
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", f":(literal){capture}"], check=True, capture_output=True)
    args = ["--meta", tmp_path / capture, "--repo-dir", tmp_path]
    snapshot = run_cli(*args, "meta")
    assert snapshot.returncode == 0, snapshot.stderr
    assert json.loads(snapshot.stdout)["detected"]["type"] == "workspace"
    doctor = run_cli(*args, "doctor", "--format", "json")
    assert json.loads(doctor.stdout)["type"] == "workspace"


@pytest.mark.parametrize("primary", ["", "  # No override\n"])
def test_meta_empty_yml_override_takes_precedence_over_yaml(tmp_path, primary):
    manifests = {".github/showcase.yml": primary, ".github/showcase.yaml": "type: workspace\n"}
    files = {"README.md": "# Handbook\n", "docs/guide.md": "# Guide\n", **manifests}
    checkout = tmp_path / "repo"
    _tree(checkout, files)
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict(files=list(files), manifests=manifests)), encoding="utf-8")
    local = run_cli("--meta", capture, "--repo-dir", checkout, "meta")
    offline = run_cli("--meta", capture, "--no-repo-dir", "meta")
    assert local.returncode == offline.returncode == 0, local.stderr + offline.stderr
    detected = json.loads(offline.stdout)["detected"]
    assert detected == json.loads(local.stdout)["detected"]
    assert detected["type"] == "documentation"


@pytest.mark.parametrize("manifests", [
    [], ["invalid"], 42, "invalid", {".github/showcase.yml": ["type: workspace"]},
])
def test_meta_preserves_malformed_manifests_for_config_aware_validation(tmp_path, manifests):
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict(files=["README.md", "docs/guide.md"], manifests=manifests)), encoding="utf-8")
    args = ["--meta", capture, "--no-repo-dir"]
    snapshot = run_cli(*args, "meta")
    assert snapshot.returncode == 0, snapshot.stderr
    result = json.loads(snapshot.stdout)
    assert result["manifests"] == manifests
    assert "suggestion" not in result["detected"]
    doctor = run_cli(*args, "doctor", "--format", "json")
    assert doctor.returncode != 0, doctor.stdout
    assert json.loads(doctor.stdout)["logs"] == ["config"]


def test_stdlib_meta_preserves_override_for_later_validation(tmp_path):
    manifests = {".github/showcase.yml": "type: workspace\n"}
    capture = tmp_path / "input.json"
    output = tmp_path / "output.json"
    capture.write_text(json.dumps(meta_dict(files=["README.md", "docs/guide.md", *manifests], manifests=manifests)),
                       encoding="utf-8")
    snapshot = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/showcase.py"), "--meta", str(capture), "--no-repo-dir",
         "meta", "--out", str(output)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    assert snapshot.returncode == 0, snapshot.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["manifests"] == manifests
    assert "suggestion" not in result["detected"]
    assert json.loads(snapshot.stdout)["logs"] == []
