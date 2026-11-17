import json
import os
from types import SimpleNamespace

import pytest

from ctshowcase.errors import NeedsInput, ShowcaseError
from ctshowcase.formatting import discover, format_text, same_json


def test_discovery_is_read_only_and_reports_sources(tmp_path):
    (tmp_path / ".prettierrc.json").write_text('{}')
    (tmp_path / ".editorconfig").write_text('root = true')
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"lint": "never-execute-this", "start": "server"}}))
    (tmp_path / "AGENTS.md").write_text('```bash\npython -m pytest\n```\n')
    workflow = tmp_path / ".github/workflows/check.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text('jobs:\n  checks:\n    steps:\n      - run: make verify\n')
    result = discover(tmp_path)
    assert result["formatters"] == [".editorconfig", ".prettierrc.json"]
    assert [v["command"] for v in result["validators"]] == ["npm run lint", "python -m pytest", "make verify"]
    assert all(v["status"] == "not run" for v in result["validators"])


def test_json5_and_inline_instructions_are_passive(tmp_path, monkeypatch):
    (tmp_path / ".prettierrc.json5").write_text("{}")
    (tmp_path / "AGENTS.md").write_text(
        "Run `python -m pytest -q` before submitting.\n"
        "Example `ruff check .` is documentation.\n"
        "Run `touch should-not-exist` before testing.\n")
    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", lambda *a, **k: pytest.fail("executed"))
    result = discover(tmp_path)
    assert result["formatters"] == [".prettierrc.json5"]
    assert result["validators"] == [{"source": "AGENTS.md", "command": "python -m pytest -q", "status": "not run"}]
    assert not (tmp_path / "should-not-exist").exists()


def local_prettier(tmp_path, version="3.6.2", pin="3.6.2"):
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"prettier": pin}}))
    p = tmp_path / "node_modules/prettier"
    p.mkdir(parents=True)
    (p / "package.json").write_text(json.dumps({"version": version, "bin": "bin/prettier.cjs"}))
    (p / "index.cjs").write_text("")
    (p / "bin").mkdir()
    (p / "bin/prettier.cjs").write_text('')


@pytest.mark.parametrize("pin,version", [("^3.6.2", "3.6.2"), ("3.6.2", "3.0.0")])
def test_formatter_refuses_unpinned_or_mismatched_install(tmp_path, pin, version):
    local_prettier(tmp_path, version=version, pin=pin)
    with pytest.raises(NeedsInput):
        format_text(tmp_path, tmp_path / "README.md", "content")


def test_formatter_uses_stdin_local_exact_version_without_shell(tmp_path, monkeypatch):
    local_prettier(tmp_path)
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    called = []

    def run(argv, **kwargs):
        called.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps("# Formatted\n").encode(), stderr=b"")

    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", run)
    assert format_text(tmp_path, tmp_path / "README.md", "# Formatted") == "# Formatted\n"
    assert len(called) == 1
    argv, kwargs = called[0]
    assert argv[0] == "/node" and argv[-1] == "README.md"
    assert "isDeepStrictEqual(original.ast, candidate.ast)" in argv[3]
    assert kwargs["input"] == b"# Formatted" and not kwargs.get("shell")
    assert not (tmp_path / "README.md").exists()


def test_formatter_refuses_external_destination(tmp_path):
    with pytest.raises(ShowcaseError):
        format_text(tmp_path, tmp_path.parent / "README.md", "content")


def test_formatter_does_not_execute_escaping_package_bin(tmp_path):
    local_prettier(tmp_path)
    package = tmp_path / "node_modules/prettier/package.json"
    package.write_text(json.dumps({"version": "3.6.2", "bin": "../../outside.js"}))
    with pytest.raises(NeedsInput):
        format_text(tmp_path, tmp_path / "README.md", "content")


def test_malformed_metadata_is_reported_without_crash(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": [], "dependencies": "bad"}')
    assert discover(tmp_path)["validators"] == []


def test_malformed_workflow_steps_do_not_break_passive_preflight(tmp_path):
    workflow = tmp_path / ".github/workflows/check.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text('jobs:\n  malformed:\n    steps: 42\n  valid:\n    steps:\n      - run: make verify\n')
    assert discover(tmp_path)["validators"] == [{
        "source": ".github/workflows", "command": "make verify", "status": "not run"}]


def test_npm_lock_pin_is_supported(tmp_path, monkeypatch):
    local_prettier(tmp_path, pin="^3.6.2")
    (tmp_path / "package-lock.json").write_text(json.dumps({"packages": {"node_modules/prettier": {"version": "3.6.2"}}}))
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps("ok").encode(), stderr=b""))
    assert format_text(tmp_path, tmp_path / "README.md", "ok") == "ok"


def test_validation_discovery_filters_workflow_setup_and_deploy(tmp_path):
    (tmp_path / "CONTRIBUTING.md").write_text("Run `cargo test` and `npm test`.\n", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/release.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("""jobs:
  test:
    steps:
      - run: |
          npm ci
          npm test
          npm run deploy
      - run: echo cargo test
""", encoding="utf-8")
    assert [v["command"] for v in discover(tmp_path)["validators"]] == ["cargo test", "npm test", "npm test"]


def test_discovery_ignores_links_outside_target(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".github").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "notes.md").write_text("Run `cargo test`.\n", encoding="utf-8")
    (outside / "package.json").write_text('{"scripts":{"test":"synthetic out-of-scope command"}}', encoding="utf-8")
    (outside / "test.yml").write_text("jobs: {tests: {steps: [{run: npm test}]}}", encoding="utf-8")
    try:
        (root / "AGENTS.md").symlink_to(outside / "notes.md")
        (root / "CONTRIBUTING.md").symlink_to(outside / "notes.md")
        (root / "package.json").symlink_to(outside / "package.json")
        workflows = root / ".github" / "workflows"
        workflows.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    assert discover(root)["validators"] == []
    workflows.unlink()
    workflows.mkdir()
    (workflows / "test.yml").symlink_to(outside / "test.yml")
    assert discover(root)["validators"] == []


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes require POSIX")
def test_discovery_ignores_special_files(tmp_path):
    workflow = tmp_path / ".github/workflows/check.yml"
    workflow.parent.mkdir(parents=True)
    for path in (tmp_path / "package.json", tmp_path / "AGENTS.md", tmp_path / ".prettierrc", workflow):
        os.mkfifo(path)
    assert discover(tmp_path)["validators"] == []
    assert discover(tmp_path)["formatters"] == []


def test_formatter_refuses_prettier_package_outside_checkout(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    local_prettier(repo)
    package = repo / "node_modules/prettier"
    outside = package.rename(tmp_path / "prettier")
    try:
        package.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    with pytest.raises(NeedsInput, match="install the target's pinned Prettier"):
        format_text(repo, repo / "README.md", "# Hello")



def test_discovery_reports_prettier_wrappers_and_contracts_without_literal_args(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"contracts":"verify --token SYNTHETIC_SECRET"}}', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run `npx prettier --check . && echo SYNTHETIC_SECRET`.\n"
        "Run `npm exec prettier -- --check . --token SYNTHETIC_SECRET`.\n"
        "Run `npm run contracts SYNTHETIC_SECRET`.\n", encoding="utf-8")
    commands = discover(tmp_path)["validators"]
    assert [entry["command"] for entry in commands] == [
        "npm run contracts", "npx prettier --check .", "npm exec prettier -- --check .", "npm run contracts"]
    assert "SYNTHETIC_SECRET" not in str(commands)


@pytest.mark.parametrize("formatted", [
    '{"number":true,"flag":true}', '{"number":1.0,"flag":true}', '{"number":1,"flag":1}',
    '{"number":1,"flag":false,"flag":true}', '{"number":NaN,"flag":true}',
])
def test_sidecar_comparison_preserves_json_types_and_rejects_invalid_values(formatted):
    assert not same_json('{"number":1,"flag":true}', formatted)
    assert same_json('{"number":1,"flag":true}', '{ "flag": true, "number": 1 }')


@pytest.mark.parametrize("value", ["file:/synthetic/sensitive", "https://example.invalid/synthetic-private",
                                   "\ud800", {"unknown": "literal"}])
def test_discovery_reports_unsupported_pins_and_generic_metadata(tmp_path, value):
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"prettier": value}}), encoding="utf-8")
    (tmp_path / ".prettierrc.synthetic-private").write_text("{}", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/synthetic-private.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs: {synthetic-private: {steps: [{run: pnpm exec prettier --check .}, {run: npx eslint .}]}}",
                        encoding="utf-8")
    result = discover(tmp_path)
    assert result["prettier_version"] is None
    assert result["prettier_version_status"] == "unsupported"
    assert result["formatters"] == [".prettierrc.*"]
    assert result["validators"] == [
        {"source": ".github/workflows", "command": "pnpm exec prettier --check .", "status": "not run"},
        {"source": ".github/workflows", "command": "npx eslint .", "status": "not run"},
    ]
    assert "synthetic-private" not in str(result)


@pytest.mark.parametrize("stdout", [b"", b'""', b'"  "', b'logged output\n"# Title"'])
def test_markdown_rejects_empty_or_unframed_success(tmp_path, monkeypatch, stdout):
    local_prettier(tmp_path)
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    monkeypatch.setattr("ctshowcase.formatting.subprocess.run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout=stdout, stderr=b""))
    with pytest.raises(ShowcaseError, match="invalid Markdown output"):
        format_text(tmp_path, tmp_path / "README.md", "# Title")


@pytest.mark.parametrize("prefix", [
    '<?xml-stylesheet type="text/css" href="https://example.invalid/style.css"?>',
    '<!DOCTYPE svg SYSTEM "https://example.invalid/svg.dtd">',
    '<!-- unexpected artifact content -->',
])
def test_same_svg_rejects_nonformatting_xml_prefix(prefix):
    from ctshowcase.formatting import same_svg

    svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M 0 0"/></svg>'
    assert same_svg(svg, "<!-- prettier-ignore -->\n" + svg)
    assert not same_svg(svg, prefix + svg)


def test_preflight_reports_the_skills_own_check_commands(tmp_path):
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "validate.yml").write_text(
        "jobs:\n  validate:\n    steps:\n"
        "      - run: python scripts/showcase.py fonts --check\n"
        "      - run: python scripts/showcase.py footer --check README.md --online\n",
        encoding="utf-8",
    )
    assert [row["command"] for row in discover(tmp_path)["validators"]] == [
        "python scripts/showcase.py fonts --check",
        "python scripts/showcase.py footer --check",
    ]


@pytest.mark.parametrize("suffix", [".md", ".json", ".svg"])
def test_formatter_uses_explicit_config_inside_the_checkout(tmp_path, monkeypatch, suffix):
    repo = tmp_path / "repo"
    repo.mkdir()
    local_prettier(repo)
    outside = tmp_path / "prettier.config.cjs"
    outside.write_text("throw new Error('external config');", encoding="utf-8")
    calls = []
    nested = repo / "docs"
    nested.mkdir()
    destination = nested / f"test{suffix}"

    def run(argv, **kwargs):
        calls.append(argv)
        data = json.dumps("ok")
        return SimpleNamespace(returncode=0, stdout=data.encode(), stderr=b"")

    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", run)
    assert format_text(repo, destination, "ok") == "ok"
    assert str(repo / "package.json") in calls[-1] and str(outside) not in calls[-1]

    settings = nested / ".prettierrc.json"
    settings.write_text("{}", encoding="utf-8")
    assert format_text(repo, destination, "ok") == "ok"
    assert str(settings) in calls[-1]


def test_formatter_refuses_externally_linked_config(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    local_prettier(repo)
    outside = tmp_path / "outside.cjs"
    outside.write_text("module.exports = {};", encoding="utf-8")
    config = repo / "prettier.config.cjs"
    try:
        config.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", lambda *a, **k: pytest.fail("loaded escaping config"))
    with pytest.raises(NeedsInput, match="configuration must be inside"):
        format_text(repo, repo / "README.md", "# Example")


def test_formatted_writer_rejects_parent_retarget_before_creating_descendants(tmp_path):
    from ctshowcase.formatting import write_formatted_outputs

    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    images = repo / "images"
    try:
        images.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")
    with pytest.raises(ShowcaseError, match="inside the target checkout"):
        write_formatted_outputs([(images / "new" / "preview.png", b"preview")], repo_root=repo)
    assert not (outside / "new").exists()


def test_formatted_svg_accessible_title_preserves_internal_whitespace():
    from ctshowcase.formatting import protect_svg_title, same_svg

    original = ('<svg xmlns="http://www.w3.org/2000/svg" aria-label="license: AGPL-3.0 | commercial">\n'
                '<title>license: AGPL-3.0 | commercial</title>\n</svg>')
    protected = protect_svg_title(original)
    assert "<!-- prettier-ignore -->\n<title>" in protected
    assert same_svg(original, protected)
    assert not same_svg(original, protected.replace("AGPL-3.0 | commercial", "AGPL-3.0 |\ncommercial", 2))
    assert not same_svg(original, protected.replace("<title>license: ", "<title>license:\n"))


def test_editorconfig_mirror_retains_local_worktree_settings_without_parents(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    local_prettier(repo)
    (repo / ".git").write_text("gitdir: ../synthetic-worktree-git\n", encoding="utf-8")
    (tmp_path / ".editorconfig").write_text("[*]\nindent_size = 8\n", encoding="utf-8")
    settings = "[*.json]\nindent_style = space\nindent_size = 4\n"
    (repo / ".editorconfig").write_text(settings, encoding="utf-8")
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")

    def run(argv, **kwargs):
        from pathlib import Path

        editor_file = Path(argv[-3])
        root = Path(argv[-2]).parent
        assert root != repo and (root / ".git").is_dir()
        assert (root / ".editorconfig").read_text(encoding="utf-8") == settings
        assert editor_file.relative_to(root).as_posix() == "docs/images/sidecar.json"
        assert kwargs["cwd"] == repo
        return SimpleNamespace(returncode=0, stdout=json.dumps('{"ok":true}').encode(), stderr=b"")

    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", run)
    assert format_text(repo, repo / "docs/images/sidecar.json", '{"ok":true}') == '{"ok":true}'


@pytest.mark.parametrize("name", [".prettierignore", ".gitignore"])
def test_formatter_refuses_external_ignore_files(tmp_path, monkeypatch, name):
    repo = tmp_path / "repo"
    repo.mkdir()
    local_prettier(repo)
    outside = tmp_path / "outside.ignore"
    outside.write_text("README.md\n", encoding="utf-8")
    try:
        (repo / name).symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")
    monkeypatch.setattr("ctshowcase.formatting.shutil.which", lambda _: "/node")
    monkeypatch.setattr("ctshowcase.formatting.subprocess.run", lambda *a, **k: pytest.fail("loaded escaping ignore file"))
    with pytest.raises(NeedsInput, match="ignore files must be inside"):
        format_text(repo, repo / "README.md", "# Example")


def test_validation_discovery_keeps_workflow_names_as_strings(tmp_path):
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "malformed.yml").write_text("jobs: [", encoding="utf-8")
    (workflows / "checks.yml").write_text(
        "name: 2026-02-30\njobs: {test: {steps: [{run: make verify}]}}", encoding="utf-8")
    assert discover(tmp_path)["validators"] == [
        {"source": ".github/workflows", "command": "make verify", "status": "not run"}
    ]


@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_markdown_wrapper_protects_live_alerts_and_leaves_fenced_examples(tmp_path, bom):
    import shutil

    if shutil.which("node") is None:
        pytest.skip("Node.js is needed for the Markdown formatter")
    local_prettier(tmp_path)
    entry = tmp_path / "node_modules/prettier/index.cjs"
    entry.write_text(r'''
exports.resolveConfig = async () => ({});
exports.format = async (input) => input;
exports.__debug = {parse: async (input, options, details) => {
    if (details) return {ast: {}};
    const lines = input.split("\n");
    const index = lines.indexOf("> [!NOTE]");
    const offset = lines.slice(0, index).join("\n").length + (index ? 1 : 0);
    return {ast: {children: [{type: "blockquote", position: {start: {line: index + 1, offset}}},
                             {type: "code"}]}};
}};
''', encoding="utf-8")
    raw = bom + "# Example\n\n> [!NOTE]\n> Authored text.\n\n```text\n> [!TIP]\n> Example.\n```\n"
    formatted = format_text(tmp_path, tmp_path / "README.md", raw)
    assert formatted == raw.replace("> [!NOTE]", "<!-- prettier-ignore -->\n\n> [!NOTE]", 1)


def test_svg_wrapper_retains_the_target_parser_override(tmp_path):
    import shutil

    if shutil.which("node") is None:
        pytest.skip("Node.js is needed for the SVG formatter")
    local_prettier(tmp_path)
    entry = tmp_path / "node_modules/prettier/index.cjs"
    entry.write_text(
        'exports.resolveConfig = async () => ({parser: "target-xml"});\n'
        'exports.format = async (input, options) => {\n'
        '    if (options.parser !== "target-xml") throw new Error("target parser was overridden");\n'
        '    return input;\n'
        '};\n', encoding="utf-8")
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M 1 1"/></svg>\n'
    assert format_text(tmp_path, tmp_path / "card.svg", svg) == svg


def test_markdown_wrapper_rejects_a_non_idempotent_format(tmp_path):
    import shutil

    from ctshowcase.errors import ShowcaseError

    if shutil.which("node") is None:
        pytest.skip("Node.js is needed for the Markdown formatter")
    local_prettier(tmp_path)
    entry = tmp_path / "node_modules/prettier/index.cjs"
    entry.write_text(
        'exports.resolveConfig = async () => ({});\n'
        'exports.format = async (input) => input + "\\n";\n'
        'exports.__debug = {parse: async () => ({ast: {}})};\n', encoding="utf-8")
    with pytest.raises(ShowcaseError, match="could not verify Markdown content"):
        format_text(tmp_path, tmp_path / "README.md", "# Example\n")
