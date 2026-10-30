import json
import re
import shutil

from ctshowcase import readme
from conftest import FIX, ROOT, run_cli

TEXT = ("# Thing\n\nIntro text.\n\n## Installation\n\npip install thing\n\n## Fun Stuff\n\nKept.\n\n"
        "## Usage\n\nrun it\n\n## License\n\nMIT.\n")
ANY_BLOCK = re.compile(r"<!-- showcase:([a-z-]+):start -->\n?.*?\n?<!-- showcase:\1:end -->\n?", re.S)


def strip_blocks(text):
    stripped = ANY_BLOCK.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", stripped).strip()


def test_no_regroup_keeps_headings_and_body(make_ctx, tmp_path):
    (tmp_path / "README.md").write_text(TEXT, encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, description="Run the thing for teams.")
    after, _ = readme.upgrade(ctx, TEXT, regroup=False)
    assert strip_blocks(after) == TEXT.strip()
    assert "## Installation" in after and "## Fun Stuff" in after and "## Usage" in after
    assert "## Notes" not in after and "## About" not in after and "## Install\n" not in after


def test_no_regroup_adds_only_marker_blocks(make_ctx, tmp_path):
    (tmp_path / "README.md").write_text(TEXT, encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, description="Run the thing for teams.")
    after, removed = readme.upgrade(ctx, TEXT, regroup=False)
    assert removed == []
    for block in ("banner", "nav", "footer"):
        assert f"<!-- showcase:{block}:start -->" in after, block
    assert after.index("<!-- showcase:banner:start -->") < after.index("<!-- showcase:nav:start -->") < after.index("# Thing")
    assert not any(x.startswith("needs-input:C:") for x in ctx.logs), ctx.logs


def test_no_regroup_idempotent(make_ctx, tmp_path):
    (tmp_path / "README.md").write_text(TEXT, encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, description="Run the thing for teams.")
    after, _ = readme.upgrade(ctx, TEXT, regroup=False)
    again, removed = readme.upgrade(ctx, after, regroup=False)
    assert again == after and removed == []
    assert readme.no_regroup(ctx, after) == (after, [])


def test_default_unchanged(make_ctx, tmp_path):
    (tmp_path / "README.md").write_text(TEXT, encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, description="Run the thing for teams.")
    after, _ = readme.upgrade(ctx, TEXT)
    assert "## Notes" in after and "## Install" in after


def test_preservation_ok(make_ctx, tmp_path):
    (tmp_path / "README.md").write_text(TEXT, encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, description="Run the thing for teams.")
    after, removed = readme.upgrade(ctx, TEXT, regroup=False)
    assert readme.preservation(TEXT, after, removed) == []


def test_marker_example_in_code_is_not_a_block(make_ctx, tmp_path):
    text = TEXT + "\n## Docs\n\n```md\n<!-- showcase:footer:start -->\nexample\n<!-- showcase:footer:end -->\n```\n"
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, description="Run the thing for teams.")
    after, removed = readme.upgrade(ctx, text, regroup=False)
    assert "<!-- showcase:footer:start -->\nexample" in after  # the documented example stays byte-identical
    assert after.count("<!-- showcase:footer:start -->") == 2  # the example plus the real footer block
    assert readme.preservation(text, after, removed) == []


def test_cli_flag_dry_run(tmp_path):
    shutil.copy(ROOT / "tests" / "fixtures" / "readmes" / "CompleteTech-LLC__LoL_OBS_Overlay.md", tmp_path / "README.md")
    meta = FIX / "CompleteTech-LLC__LoL_OBS_Overlay.json"
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--no-regroup")
    assert p.returncode == 0, p.stderr
    diff = json.loads(p.stdout)["diff"]
    assert "+## Notes" not in diff and "-## Notes" not in diff
    assert "-## " not in diff  # no authored heading is removed

    (tmp_path / "README.md").write_text(TEXT, encoding="utf-8")
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--no-regroup", "--write")
    assert p.returncode == 0, p.stderr
    written = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "## Fun Stuff" in written and "## Notes" not in written


def test_cli_scaffold_with_no_regroup_is_usage_error(tmp_path):
    shutil.copy(ROOT / "tests" / "fixtures" / "readmes" / "CompleteTech-LLC__LoL_OBS_Overlay.md", tmp_path / "README.md")
    meta = FIX / "CompleteTech-LLC__LoL_OBS_Overlay.json"
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "scaffold", "--no-regroup")
    assert p.returncode == 2, p.stdout + p.stderr
