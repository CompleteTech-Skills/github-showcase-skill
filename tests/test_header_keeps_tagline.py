"""`readme --mode header` (what the Action runs on every push) must never erase an authored tagline: when the
repository has no description yet, the existing tagline block stays as written and the run logs
needs-input:description (guardrail 6, improve never erase). With a description, the tagline is regenerated from it."""
from ctshowcase import readme as R

TAGLINE = "**Route Northwind support tickets to the right queue.**"
TEXT = (
    "# Support Triage Agent\n\n"
    "<!-- showcase:tagline:start -->\n" + TAGLINE + "\n<!-- showcase:tagline:end -->\n\n"
    "## Usage\n\nRun it.\n"
)


def test_no_description_keeps_the_authored_tagline(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, description="")
    out = R.header_only(ctx, TEXT)
    assert TAGLINE in out
    assert "needs-input:description" in ctx.logs
    assert R.header_only(ctx, out) == out  # stable on the next push


def test_missing_description_key_keeps_the_authored_tagline(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, description=None)
    assert TAGLINE in R.header_only(ctx, TEXT)


def test_description_regenerates_the_tagline(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, description="Run the Northwind triage agent.")
    out = R.header_only(ctx, TEXT)
    assert "**Run the Northwind triage agent.**" in out
    assert TAGLINE not in out


def test_empty_block_and_no_description_stays_empty(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, description="")
    text = "# T\n\n<!-- showcase:tagline:start -->\n<!-- showcase:tagline:end -->\n"
    out = R.header_only(ctx, text)
    assert "<!-- showcase:tagline:start -->" in out and "**" not in out


def test_untouched_template_copy_drops_the_template_tagline(make_ctx, tmp_path):
    # a repository fresh from the template still has the template's tagline and a pristine template body:
    # with no description of its own it must not keep another repository's line
    ctx = make_ctx(tmp_path, description="")
    text = TEXT + "\n" + R.pristine_block("## About\n\nTemplate body.") + "\n"
    out = R.header_only(ctx, text)
    assert TAGLINE not in out
    assert "needs-input:description" in ctx.logs


def test_template_repository_keeps_its_own_tagline(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, description="", is_template=True)
    text = TEXT + "\n" + R.pristine_block("## About\n\nTemplate body.") + "\n"
    assert TAGLINE in R.header_only(ctx, text)


def test_repository_generated_from_the_template_drops_the_inherited_tagline(make_ctx, tmp_path):
    # GitHub's template_repository marks a repository generated from the template, even after its body was edited
    ctx = make_ctx(tmp_path, description="", template_repository={"full_name": "Northwind-Trading-Co/northwind-template"})
    assert ctx.meta["template_repository"] == "Northwind-Trading-Co/northwind-template"
    assert TAGLINE not in R.header_only(ctx, TEXT)
