"""Independent issue #201 contract, based on the documented PR #200 contract.

Only public CLI/API conventions and documented configuration inform these tests.
All targets are synthetic and offline.  The formatter below is an explicit double,
not evidence that an external native formatter has run.
"""
import json
import re

import pytest

from conftest import meta_dict, run_cli
from ctshowcase import footer
from test_footer import DECISION_18


CREDIT_START = "<!-- showcase:credit:start -->"
CREDIT_END = "<!-- showcase:credit:end -->"
FOOTER = "<!-- showcase:footer:start -->\n" + DECISION_18 + "\n<!-- showcase:footer:end -->"
URL = "https://github.com/CompleteTech-Skills/github-showcase-skill"
CREDIT_LINE = (f'<p align="center"><sub>README styled with <a href="{URL}">'
               "github-showcase-skill</a> by CompleteTech LLC"
               f' · <a href="{URL}#quick-start">Get the skill</a></sub></p>')
AUTHORED = "Keep this authored sentence and its punctuation."


def credit(version="1.0.0", line=CREDIT_LINE, generator="github-showcase-skill", standard="ct-std-v1"):
    return (f"{CREDIT_START}\n<!-- generated-by: {generator} v={version} std={standard} -->\n"
            f"{line}\n{CREDIT_END}")


def source(block=None, *, trailing=False):
    body = "# Synthetic Northwind Tool\n\n## Usage\n\n" + AUTHORED + "\n\n"
    if block is None:
        return body
    blocks = (FOOTER, block) if trailing else (block, FOOTER)
    return body + "\n\n".join(blocks) + "\n"


def target(tmp_path, text):
    repo = tmp_path / "repo"
    repo.mkdir()
    path = repo / "README.md"
    path.write_bytes(text.encode("utf-8"))
    (repo / "LICENSE").write_text("Synthetic MIT fixture.\n", encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(files=["README.md", "LICENSE"])), encoding="utf-8")
    return repo, meta, path


def args(repo, meta, *extra):
    return ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "upgrade",
            "--variant", "A", "--write", *extra]


def snapshot(repo):
    return {path.relative_to(repo).as_posix(): path.read_bytes()
            for path in repo.rglob("*") if path.is_file()}


def assert_final_footer(text):
    """Prove both the exact final configured block and its adjacent credit."""
    assert text.rstrip().endswith(FOOTER), text[-1800:]
    prefix = text.rstrip()[:-len(FOOTER)].rstrip()
    assert prefix.endswith(CREDIT_END), prefix[-800:]
    assert text.count(FOOTER) == 1
    assert text.count("<picture>") == 1
    assert text.count(CREDIT_START) == 1
    assert AUTHORED in text


def test_public_footer_api_keeps_exact_decision18_last(brand):
    block = footer.block(brand)
    assert block.rstrip().endswith(FOOTER)
    assert block[:block.index(FOOTER)].rstrip().endswith(CREDIT_END)
    assert footer.markup(brand) == DECISION_18
    assert footer.check(brand, source(credit()))[0] == "pass"
    assert footer.check(brand, source(credit(), trailing=True))[0] != "pass"


def test_cli_adds_credit_before_footer_and_is_byte_idempotent(tmp_path):
    repo, meta, path = target(tmp_path, source())
    result = run_cli(*args(repo, meta))
    assert result.returncode == 0, result.stdout + result.stderr
    assert_final_footer(path.read_bytes().decode("utf-8"))
    before = path.read_bytes()
    result = run_cli(*args(repo, meta))
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == before


def test_cli_migrates_proven_old_trailing_credit_with_harmless_whitespace(tmp_path):
    line = (f'<p align = "center">\n  <sub>README styled with\n'
            f'    <a href = "{URL}">github-showcase-skill</a>\n'
            f'    by CompleteTech LLC · <a href="{URL}#quick-start">Get the skill</a></sub>\n</p>')
    repo, meta, path = target(tmp_path, source(credit("0.8.2", line), trailing=True))
    result = run_cli(*args(repo, meta))
    assert result.returncode == 0, result.stdout + result.stderr
    assert_final_footer(path.read_bytes().decode("utf-8"))
    before = path.read_bytes()
    assert run_cli(*args(repo, meta)).returncode == 0
    assert path.read_bytes() == before


@pytest.mark.parametrize("case", ["foreign-generator", "different-standard", "text", "href", "attribute", "child"])
def test_unproven_full_credit_refuses_atomically_before_local_badges(tmp_path, case):
    edits = {
        "foreign-generator": credit(generator="northwind-docs"),
        "different-standard": credit(standard="northwind-std-v1"),
        "text": credit(line=CREDIT_LINE.replace("README styled with", "Maintained using")),
        "href": credit(line=CREDIT_LINE.replace(URL, "https://example.invalid/authored-tool")),
        "attribute": credit(line=CREDIT_LINE.replace('<a href=', '<a rel="nofollow" href=')),
        "child": credit(line=CREDIT_LINE.replace("</sub>", "<span>Authored attribution.</span></sub>")),
    }
    repo, meta, _ = target(tmp_path, source(edits[case], trailing=True))
    sidecar = repo / "docs/images/.showcase.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text('{"outputs": {}, "independent_sentinel": "keep exact bytes"}\n', encoding="utf-8")
    before = snapshot(repo)
    result = run_cli(*args(repo, meta, "--badges", "local"))
    assert snapshot(repo) == before, "Refused credit changed README, sidecar, badge, or another target file"
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input" in result.stdout + result.stderr


def test_marker_shaped_fenced_example_is_preserved_and_does_not_supply_ownership(tmp_path):
    example = "```html\n" + credit(generator="northwind-docs") + "\n```\n"
    repo, meta, path = target(tmp_path, source() + "\n" + example)
    result = run_cli(*args(repo, meta))
    assert result.returncode == 0, result.stdout + result.stderr
    text = path.read_bytes().decode("utf-8")
    assert example in text
    # Count only the real output after the fenced example.
    assert_final_footer(text.replace(example, ""))
    before = path.read_bytes()
    assert run_cli(*args(repo, meta)).returncode == 0
    assert path.read_bytes() == before


def test_formatter_double_output_remains_owned_and_footer_exact_on_retry(tmp_path, monkeypatch):
    import showcase

    repo, meta, path = target(tmp_path, source(credit("0.9.0")))
    calls = []

    def whitespace_formatter(root, destination, text):
        assert root == repo
        if destination == path:
            calls.append(destination)
            text = re.sub(r'(<p align="center"><sub>)(README styled with)', r"\1\n  \2", text)
            text = text.replace("github-showcase-skill</a> by CompleteTech", "github-showcase-skill</a>\n  by CompleteTech")
        return text

    monkeypatch.setattr("ctshowcase.formatting.format_text", whitespace_formatter)
    argv = args(repo, meta, "--format-generated")
    assert showcase.main(argv) == 0
    assert calls
    assert_final_footer(path.read_bytes().decode("utf-8"))
    before = path.read_bytes()
    assert showcase.main(argv) == 0
    assert path.read_bytes() == before


def test_native_format_option_cannot_wash_authored_credit_into_owned_credit(tmp_path, monkeypatch, capsys):
    import showcase

    authored = credit(line=CREDIT_LINE.replace("README styled with", "Authored using"))
    repo, meta, _ = target(tmp_path, source(authored))
    before = snapshot(repo)

    def ownership_washing_formatter(_root, _destination, text):
        return text.replace("Authored using", "README styled with")

    monkeypatch.setattr("ctshowcase.formatting.format_text", ownership_washing_formatter)
    code = showcase.main(args(repo, meta, "--badges", "local", "--format-generated"))
    output = capsys.readouterr()
    assert snapshot(repo) == before, "Formatting bypassed the input credit's ownership boundary"
    assert code == 4, output.out + output.err
    assert "needs-input" in output.out + output.err
