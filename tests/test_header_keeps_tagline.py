"""`readme --mode header` (what the Action runs on every push) must never erase a tagline written for the repository:
when the repository has no description yet, the tagline block stays as written and the run logs
needs-input:description (guardrail 6, improve never erase). Only an inherited tagline is emptied: the template body is
the block holds exactly a tagline of the template the repository was generated from (as generated, or as today), or,
only when those are unknown, the template body is still pristine. With a description, the tagline is regenerated."""
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
                   template_taglines=["**Start a Northwind repository.**"])
    assert ctx.meta["template_repository"] == "Northwind-Trading-Co/northwind-template"
    assert TAGLINE in R.header_only(ctx, TEXT)


def test_generated_repository_drops_the_template_tagline(make_ctx, tmp_path):
    inherited = "**Start a Northwind repository.**"
    ctx = make_ctx(tmp_path, description="", template_repository={"full_name": "Northwind-Trading-Co/northwind-template"},
                   template_taglines=[inherited])
    out = R.header_only(ctx, TEXT.replace(TAGLINE, inherited))
    assert inherited not in out and "needs-input:description" in ctx.logs


def test_pristine_body_does_not_override_a_known_template_tagline(make_ctx, tmp_path):
    # the owner wrote a tagline before editing the template body: the template's real tagline is known and different
    ctx = make_ctx(tmp_path, description="", template_taglines=["**Start a Northwind repository.**"])
    text = TEXT + "\n" + R.pristine_block("## About\n\nTemplate body.") + "\n"
    assert TAGLINE in R.header_only(ctx, text)


def test_tagline_inherited_before_the_template_changed_is_dropped(make_ctx, tmp_path):
    old, new = "**Start a Northwind repository.**", "**Start a repository, revised.**"
    ctx = make_ctx(tmp_path, description="", template_taglines=[old, new])
    assert old not in R.header_only(ctx, TEXT.replace(TAGLINE, old))


def test_from_gh_records_the_template_taglines(monkeypatch):
    import base64
    from ctshowcase import meta as M

    def b64(text):
        return {"path": "README.md", "content": base64.b64encode(text.encode()).decode()}

    def readme(tagline):
        return "\ufeff# T\r\n\r\n<!-- showcase:tagline:start -->\r\n" + tagline + "\r\n<!-- showcase:tagline:end -->\r\n"
    sha = "a" * 40
    calls = []

    def fake(path, paginate=False, raw=False):
        calls.append(path)
        if path == "repos/Northwind-Trading-Co/support-triage-agent":
            return {"name": "support-triage-agent", "owner": {"login": "Northwind-Trading-Co"}, "default_branch": "main",
                    "created_at": "2026-01-02T03:04:05Z",
                    "template_repository": {"full_name": "Northwind-Trading-Co/northwind-template"}}
        if path == "repos/Northwind-Trading-Co/northwind-template/readme":
            return b64(readme("**Start a repository, revised.**"))
        if path == "repos/Northwind-Trading-Co/northwind-template/commits?path=README.md&until=2026-01-02T03:04:05Z&per_page=1":
            return [{"sha": sha}]
        if path == f"repos/Northwind-Trading-Co/northwind-template/contents/README.md?ref={sha}":
            return b64(readme("**Start a Northwind repository.**"))
        return None
    monkeypatch.setattr(M, "_gh", fake)
    raw = M.from_gh("Northwind-Trading-Co/support-triage-agent")
    assert raw["template_taglines"] == ["**Start a Northwind repository.**", "**Start a repository, revised.**"]
    m = M.normalize(raw)
    assert m["template_repository"] == "Northwind-Trading-Co/northwind-template"
    assert m["template_taglines"] == raw["template_taglines"]
    assert all(c.startswith("repos/") for c in calls)  # read-only GETs through _gh only


def test_normalize_template_taglines_shapes():
    from ctshowcase import meta as M
    from conftest import meta_dict
    assert M.normalize(meta_dict(template_taglines="**One.**"))["template_taglines"] == ["**One.**"]
    assert M.normalize(meta_dict(template_taglines=[" **One.** ", "", None, 5, "**One.**"]))["template_taglines"] == ["**One.**"]
    assert M.normalize(meta_dict())["template_taglines"] == []
