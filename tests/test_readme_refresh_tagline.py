"""A changed About description refreshes the generated tagline block without tripping the never-drop-a-line check.

`readme --mode upgrade` (the default, and `auto` when it picks upgrade) used to fail with `readme-shrink` once the
description changed, because the old tagline line inside the generated block was counted as a lost line. The check now
ignores the contents of the generated `banner`, `nav`, `tagline`, `badges` and `footer` blocks while the same block still
exists in the output. Every line outside those blocks, every line in another block (`template-body`), and every line of
a block that vanishes from the output is still guarded.

Which tests reproduce the bug and which are guards (checked against the base commit 2be04ac, where the fix is absent):
- Reproduce the bug (FAIL on the base with `lost line: **Research home for the old thing.**`):
  test_description_change_refreshes_tagline_without_readme_shrink and test_cli_default_mode_writes_new_tagline.
- Regression guards (PASS on the base by design; the base already guarded these lines, so the fix must not widen the
  exemption to them): test_user_line_outside_blocks_still_guarded, test_generated_block_removed_from_output_still_guarded,
  test_template_body_block_is_never_excluded, test_marker_example_in_code_fence_stays_guarded and
  test_header_mode_unchanged (the documented `--mode header` fallback, which never runs the shrink check).
- Review follow-up (the first version of the fix let generated text satisfy an authored line's count, and credited
  the emptied inherited tagline a second time, so an identical authored line could vanish unreported):
  test_generated_text_does_not_satisfy_a_dropped_authored_line FAILS on the base 2be04ac and on the first fix (the
  dropped authored bold line is not reported). test_inherited_tagline_credit_does_not_hide_identical_authored_line
  PASSES on the base (which reported it) and FAILED on the first fix, so it guards that regression.
  test_unmarked_tagline_moved_into_block_is_not_lost is the intentional move that the output-side exclusion would
  otherwise report; it PASSES on the base and must stay clean.
A guard failing on the new code means the exemption is too broad; a guard passing on the base is expected.
"""
import json
import re

from ctshowcase import readme as R
from conftest import meta_dict, run_cli

OLD = "**Research home for the old thing.**"
TEXT = (
    "# Support Triage Agent\n\n"
    "<!-- showcase:tagline:start -->\n" + OLD + "\n<!-- showcase:tagline:end -->\n\n"
    "---\n\n## Usage\n\nRun it.\n\n## License\n\nMIT\n"
)


def test_description_change_refreshes_tagline_without_readme_shrink(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, description="A brand new description.")
    out, removed = R.upgrade(ctx, TEXT)
    assert "**A brand new description.**" in out
    assert OLD not in out
    assert R.preservation(TEXT, out, removed) == []


def test_user_line_outside_blocks_still_guarded(make_ctx, tmp_path):
    text = TEXT.replace("Run it.\n", "Run it.\n\nKeep this authored sentence.\n")
    ctx = make_ctx(tmp_path, description="A brand new description.")
    out, removed = R.upgrade(ctx, text)
    assert "Keep this authored sentence." in out
    after = out.replace("Keep this authored sentence.\n", "")
    problems = R.preservation(text, after, removed)
    assert any(p.startswith("lost line: Keep this authored sentence.") for p in problems), problems


def test_generated_block_removed_from_output_still_guarded(make_ctx, tmp_path):
    # the tagline block vanishes from the output: its old line is not excluded, so losing it is reported
    ctx = make_ctx(tmp_path, description="A brand new description.")
    out, _ = R.upgrade(ctx, TEXT)
    after = re.sub(r"<!-- showcase:tagline:start -->.*?<!-- showcase:tagline:end -->\n*", "", out, flags=re.S)
    assert "<!-- showcase:tagline:start -->" not in after
    problems = R.preservation(TEXT, after, [])
    assert any(p.startswith("lost line: " + OLD) for p in problems), problems


def test_template_body_block_is_never_excluded(make_ctx, tmp_path):
    authored = "Authored in the block."
    text = TEXT + "\n" + R.wrap("template-body", authored) + "\n"
    ctx = make_ctx(tmp_path, description="A brand new description.")
    out, removed = R.upgrade(ctx, text)
    assert authored in out
    after = out.replace(authored + "\n", "")
    assert any(p.startswith("lost line: " + authored) for p in R.preservation(text, after, removed))


def test_marker_example_in_code_fence_stays_guarded(make_ctx, tmp_path):
    fence = (
        "```\n<!-- showcase:tagline:start -->\nExample line\n<!-- showcase:tagline:end -->\n```\n"
    )
    text = TEXT.replace("## Usage", fence + "\n## Usage")
    ctx = make_ctx(tmp_path, description="A brand new description.")
    out, removed = R.upgrade(ctx, text)
    assert "Example line" in out
    after = out.replace("Example line\n", "")
    assert any(p.startswith("lost line: Example line") for p in R.preservation(text, after, removed))


def test_cli_default_mode_writes_new_tagline(tmp_path):
    # `readme --write` with no --mode (auto, which picks upgrade for this README) refreshes the tagline
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(TEXT, encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(description="A brand new description.")), encoding="utf-8")
    p = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--write")
    assert p.returncode == 0, p.stdout + p.stderr
    out = json.loads(p.stdout)
    assert out["result"] != "fail", out
    after = (repo / "README.md").read_text(encoding="utf-8")
    assert "**A brand new description.**" in after and OLD not in after


def test_header_mode_unchanged(make_ctx, tmp_path):
    # the documented fallback: --mode header refreshes the generated block from the new description
    ctx = make_ctx(tmp_path, description="A brand new description.")
    out = R.header_only(ctx, TEXT)
    assert "**A brand new description.**" in out
    assert OLD not in out


def test_generated_text_does_not_satisfy_a_dropped_authored_line(make_ctx, tmp_path):
    # the second `## Notes` replaces the first one (upgrade keeps only the last), so the authored bold line in the
    # first section is lost. Its text equals the new generated tagline, which must not count as the authored copy.
    authored = "**Run the Northwind triage agent.**"
    text = (
        "# Support Triage Agent\n\n<!-- showcase:tagline:start -->\n**Old tagline here.**\n"
        "<!-- showcase:tagline:end -->\n\n## Usage\n\nRun it.\n\n"
        "## Notes\n\n" + authored + "\n\n## Notes\n\nKeep this other note.\n\n## License\n\nMIT\n"
    )
    ctx = make_ctx(tmp_path, description="Run the Northwind triage agent.")
    out, removed = R.upgrade(ctx, text)
    assert "Keep this other note." in out
    problems = R.preservation(text, out, removed)
    assert any(p.startswith("lost line: " + authored) for p in problems), problems


def test_inherited_tagline_credit_does_not_hide_identical_authored_line(make_ctx, tmp_path):
    # the inherited tagline is emptied (no description, template tagline known). Its line is excluded from the check
    # while the empty block stays, so an identical authored line in the first `## Notes` is still guarded.
    inherited = "**Start a Northwind repository.**"
    text = (
        "# Support Triage Agent\n\n<!-- showcase:tagline:start -->\n" + inherited + "\n<!-- showcase:tagline:end -->\n\n"
        "## Usage\n\nRun it.\n\n## Notes\n\n" + inherited + "\n\n## Notes\n\nKeep this other note.\n\n"
        "## License\n\nMIT\n"
    )
    ctx = make_ctx(tmp_path, description="", template_taglines=[inherited])
    out, removed = R.upgrade(ctx, text)
    assert inherited not in out and "Keep this other note." in out
    problems = R.preservation(text, out, removed)
    assert any(p.startswith("lost line: " + inherited) for p in problems), problems


def test_unmarked_tagline_moved_into_block_is_not_lost(make_ctx, tmp_path):
    # no description and no template tagline: the unmarked bold line moves into the tagline block (intentional move)
    line = "**Keep this tagline for now.**"
    text = "# Support Triage Agent\n\n" + line + "\n\n## Usage\n\nRun it.\n\n## License\n\nMIT\n"
    ctx = make_ctx(tmp_path, description="")
    out, removed = R.upgrade(ctx, text)
    assert "<!-- showcase:tagline:start -->\n" + line + "\n<!-- showcase:tagline:end -->" in out
    assert R.preservation(text, out, removed) == []
