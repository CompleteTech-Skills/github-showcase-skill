"""preservation() (the never-drop-a-line check) ignores the body of generated marker blocks that still exist in the
output: a refreshed tagline is a regenerated value, not a lost line. Lines outside generated blocks, a generated block
that disappears, and unknown or template blocks stay guarded.

Test kinds (verified by reverting scripts/ctshowcase/readme.py to the pre-change base, commit 2be04ac, and running this
file there: 3 failed, 3 passed):
- Fail on base, pass on HEAD (the behaviour change itself): test_refreshed_tagline_is_not_a_lost_line,
  test_line_outside_generated_block_is_still_guarded, test_crlf_input_is_handled.
- Pass on base and on HEAD by design (regression guards that the change must NOT relax the check): the other three.
  They pin the existing behaviour for the boundary cases, so a future over-broad exclusion turns them red. They are
  not expected to fail on the base."""
from ctshowcase import readme as R

OLD = "**Route Northwind support tickets to the right queue.**"
NEW = "**Run the Northwind triage agent.**"
TEXT = (
    "# Support Triage Agent\n\n"
    "<!-- showcase:tagline:start -->\n" + OLD + "\n<!-- showcase:tagline:end -->\n\n"
    "## Usage\n\nRun it.\n"
)
# long enough that dropping one short block stays inside the 10% non-whitespace size check
PAD = "\n\n".join(f"Owner paragraph {i} describing the Northwind triage queue in detail." for i in range(20))


def lost(problems):
    return [p for p in problems if p.startswith("lost line")]


def test_refreshed_tagline_is_not_a_lost_line(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, description="Run the Northwind triage agent.")
    out, removed = R.upgrade(ctx, TEXT)
    assert NEW in out and OLD not in out
    assert R.preservation(TEXT, out, removed) == []


def test_generated_block_removed_from_output_still_guards_its_lines(make_ctx, tmp_path):
    # the tagline block is gone from the output: its old line counts as lost unless it is listed in `removed`
    before = TEXT + "\n" + PAD + "\n"
    after = "# Support Triage Agent\n\n## Usage\n\nRun it.\n\n" + PAD + "\n"
    assert lost(R.preservation(before, after, [])) == [f"lost line: {OLD[:60]}"]
    assert lost(R.preservation(before, after, [OLD])) == []


def test_line_outside_generated_block_is_still_guarded(make_ctx, tmp_path):
    # the stale authored line is outside any block and must survive, even though a refreshed block is present
    before = TEXT.replace("Run it.", "Authored sentence to keep.") + "\n" + PAD + "\n"
    after = "# Support Triage Agent\n\n<!-- showcase:tagline:start -->\n" + NEW + \
        "\n<!-- showcase:tagline:end -->\n\n## Usage\n\n" + PAD + "\n"
    assert lost(R.preservation(before, after, [])) == ["lost line: Authored sentence to keep."]


def test_unknown_and_template_blocks_stay_guarded(make_ctx, tmp_path):
    for name in ("license", "template-body", "made-up-block"):
        before = f"# T\n\n<!-- showcase:{name}:start -->\nKeep this line.\n<!-- showcase:{name}:end -->\n"
        after = "# T\n\n" + f"<!-- showcase:{name}:start -->\nChanged.\n<!-- showcase:{name}:end -->\n"
        assert lost(R.preservation(before, after, [])) == ["lost line: Keep this line."], name


def test_marker_example_in_code_is_not_stripped(make_ctx, tmp_path):
    before = "# T\n\n```\n<!-- showcase:tagline:start -->\nDocumented example.\n<!-- showcase:tagline:end -->\n```\n"
    after = "# T\n"
    assert "lost line: Documented example." in R.preservation(before, after, [])


def test_crlf_input_is_handled(make_ctx, tmp_path):
    before = (TEXT + "\n" + PAD + "\n").replace("\n", "\r\n")
    after = (TEXT + "\n" + PAD + "\n").replace(OLD, NEW)
    assert R.preservation(before, after, []) == []
