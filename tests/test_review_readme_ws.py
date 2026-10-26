"""Review comment 4373670976: `readme --mode header` must leave authored text outside the marker blocks byte-identical
(fenced code included); blank lines are tidied only inside regenerated blocks and where a block meets authored text."""
import json

from conftest import meta_dict, run_cli
from ctshowcase import readme as R

FENCED = (
    "# Support Triage Agent\n\n"
    "Route Northwind support tickets.\n\n"
    "```python\n"
    'PROMPT = """first\n\n\n\nlast"""\n'
    "```\n\n\n"
    "## Usage\n\nRun it.\n"
)


def test_header_only_keeps_fenced_blank_lines_without_markers(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path)
    assert R.header_only(ctx, FENCED) == FENCED


def test_header_only_keeps_authored_text_between_blocks(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path)
    text = ("<!-- showcase:nav:start -->\nold nav\n<!-- showcase:nav:end -->\n\n" + FENCED +
            "\n<!-- showcase:footer:start -->\nold footer\n<!-- showcase:footer:end -->\n")
    out = R.header_only(ctx, text)
    assert 'PROMPT = """first\n\n\n\nlast"""' in out
    assert "```\n\n\n## Usage" in out  # authored blank lines away from any block stay as written
    assert "old nav" not in out and "old footer" not in out


def test_removed_block_seam_is_tidied(make_ctx, tmp_path):
    # a finished checklist block is removed: the blank lines it leaves behind collapse to one at that seam only
    ctx = make_ctx(tmp_path)
    text = ("Intro.\n\n<!-- showcase:checklist:start -->\n- [x] done\n<!-- showcase:checklist:end -->\n\n\n"
            "## Usage\n\n```text\na\n\n\n\nb\n```\n")
    out = R.header_only(ctx, text)
    assert out == "Intro.\n\n## Usage\n\n```text\na\n\n\n\nb\n```\n"
    assert R.header_only(ctx, out) == out


def test_cli_header_write_leaves_markerless_readme_unchanged(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "README.md").write_text(FENCED, encoding="utf-8")
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict()))
    p = run_cli("--meta", m, "--repo-dir", d, "--format", "json", "readme", "--mode", "header", "--write")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["result"] == "unchanged"
    assert (d / "README.md").read_text(encoding="utf-8") == FENCED
