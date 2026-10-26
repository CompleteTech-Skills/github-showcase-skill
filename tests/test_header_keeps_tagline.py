"""`readme --mode header` (what the Action runs on every push) must never erase a tagline written for the repository:
when the repository has no description yet, the tagline block stays as written and the run logs
needs-input:description (guardrail 6, improve never erase). Only an inherited tagline is emptied: the template body is
still pristine, or the block holds exactly the tagline of the template the repository was generated from. With a
description, the tagline is regenerated from it."""
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


def test_generated_repository_keeps_a_tagline_its_owner_wrote(make_ctx, tmp_path):
    # GitHub never clears template_repository, so that alone must not erase what the owner wrote later
    ctx = make_ctx(tmp_path, description="", template_repository={"full_name": "Northwind-Trading-Co/northwind-template"},
                   template_tagline="**Start a Northwind repository.**")
    assert ctx.meta["template_repository"] == "Northwind-Trading-Co/northwind-template"
    assert TAGLINE in R.header_only(ctx, TEXT)


def test_generated_repository_drops_the_template_tagline(make_ctx, tmp_path):
    inherited = "**Start a Northwind repository.**"
    ctx = make_ctx(tmp_path, description="", template_repository={"full_name": "Northwind-Trading-Co/northwind-template"},
                   template_tagline=inherited)
    out = R.header_only(ctx, TEXT.replace(TAGLINE, inherited))
    assert inherited not in out and "needs-input:description" in ctx.logs


def test_from_gh_records_the_template_tagline(monkeypatch):
    import base64
    from ctshowcase import meta as M

    def b64(text):
        return {"content": base64.b64encode(text.encode()).decode()}

    template_readme = "\ufeff# T\r\n\r\n<!-- showcase:tagline:start -->\r\n**Start a Northwind repository.**\r\n<!-- showcase:tagline:end -->\r\n"

    def fake(path, paginate=False, raw=False):
        if path == "repos/Northwind-Trading-Co/support-triage-agent":
            return {"name": "support-triage-agent", "owner": {"login": "Northwind-Trading-Co"}, "default_branch": "main",
                    "template_repository": {"full_name": "Northwind-Trading-Co/northwind-template"}}
        if path == "repos/Northwind-Trading-Co/northwind-template/readme":
            return b64(template_readme)
        return None
    monkeypatch.setattr(M, "_gh", fake)
    raw = M.from_gh("Northwind-Trading-Co/support-triage-agent")
    assert raw["template_tagline"] == "**Start a Northwind repository.**"
    m = M.normalize(raw)
    assert m["template_repository"] == "Northwind-Trading-Co/northwind-template"
    assert m["template_tagline"] == "**Start a Northwind repository.**"
