"""`readme --mode header` (what the Action runs on every push) must never erase a tagline written for the repository:
when the repository has no description yet, the tagline block stays as written and the run logs
needs-input:description (guardrail 6, improve never erase). Only an inherited tagline is emptied:
the block holds exactly a tagline of the template the repository was generated from (as generated, or as today), or,
only when those are unknown, the template body is still pristine. With a description, the tagline is regenerated.
bootstrap (the template workflow's step before header mode) and upgrade (its rebuilt header and its additive preserve
mode) decide the tagline block by the same rule (readme.tagline_body). With no description, when upgrade rebuilds the
header (not in preserve mode), a single bare **...** line directly under the H1 moves into the block by that rule
instead of being erased; a bold line inside a centred <div>/<p> block, or in preserve mode, stays as authored text."""
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


# -- bootstrap (what every repository generated from the template runs on each push, before header mode) --------------
TEMPLATE_TAGLINE = ("**Create new CompleteTech repositories with the standard README, folder layout and showcase banner "
                    "Action.**")


def _set_tagline(text: str, body: str) -> str:
    import re
    return re.sub(r"(<!-- showcase:tagline:start -->\n).*?(<!-- showcase:tagline:end -->)", lambda m: m.group(1) + body +
                  ("\n" if body else "") + m.group(2), text, count=1, flags=re.S)


def _tagline_body(text: str) -> str:
    return next(m.group(2) for m in R.find_blocks(R.MARK, text) if m.group(1) == "tagline").strip()


def _bootstrapped_once(make_ctx, tmp_path, **kw):
    """The template fixture after its first bootstrap in a repository named new-thing (H1 "# New Thing")."""
    from conftest import ROOT
    text = (ROOT / "tests" / "fixtures" / "template-README.md").read_text(encoding="utf-8")
    ctx = make_ctx(tmp_path, repo="new-thing", description="", **kw)
    out = R.bootstrap(ctx, text)
    assert "# New Thing" in out and R.bootstrap_state(out) == "pristine"
    return out


def test_bootstrap_keeps_a_tagline_the_owner_wrote(make_ctx, tmp_path):
    kw = {"template_taglines": [TEMPLATE_TAGLINE]}
    text = _set_tagline(_bootstrapped_once(make_ctx, tmp_path, **kw), TAGLINE)
    ctx = make_ctx(tmp_path, repo="new-thing", description="", **kw)
    out = R.bootstrap(ctx, text)
    assert _tagline_body(out) == TAGLINE and "needs-input:description" in ctx.logs
    assert R.header_only(ctx, out) == out and R.bootstrap(ctx, out) == out  # stable on the next push


def test_bootstrap_drops_the_inherited_template_tagline(make_ctx, tmp_path):
    from conftest import ROOT
    text = (ROOT / "tests" / "fixtures" / "template-README.md").read_text(encoding="utf-8")
    for kw in ({"template_taglines": [TEMPLATE_TAGLINE]}, {}):  # known template tagline, or unknown (pristine body)
        ctx = make_ctx(tmp_path, repo="new-thing", description="", **kw)
        assert _tagline_body(R.bootstrap(ctx, text)) == "", kw
    # the inherited line is still dropped after the H1 was rebuilt (second push)
    once = _bootstrapped_once(make_ctx, tmp_path, template_taglines=[TEMPLATE_TAGLINE])
    ctx = make_ctx(tmp_path, repo="new-thing", description="", template_taglines=[TEMPLATE_TAGLINE])
    assert _tagline_body(R.bootstrap(ctx, _set_tagline(once, TEMPLATE_TAGLINE))) == ""


def test_bootstrap_with_a_description_writes_it(make_ctx, tmp_path):
    text = _set_tagline(_bootstrapped_once(make_ctx, tmp_path), TAGLINE)
    ctx = make_ctx(tmp_path, repo="new-thing", description="Route Northwind tickets.")
    assert _tagline_body(R.bootstrap(ctx, text)) == "**Route Northwind tickets.**"


def test_cli_bootstrap_then_header_keeps_the_authored_tagline(tmp_path):
    # the template workflow's `readme: bootstrap` step: `readme --bootstrap --write`, then `readme --mode header --write`
    import json
    from conftest import ROOT, meta_dict, run_cli
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text((ROOT / "tests" / "fixtures" / "template-README.md").read_text(encoding="utf-8"),
                                    encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(repo="new-thing", description="", language=None,
                                         template_taglines=[TEMPLATE_TAGLINE])), encoding="utf-8")
    steps = (("readme", "--bootstrap", "--write"), ("readme", "--mode", "header", "--write"))
    for step in steps:
        assert run_cli("--meta", meta, "--repo-dir", repo, *step).returncode == 0
    readme = repo / "README.md"
    assert "# New Thing" in readme.read_text(encoding="utf-8")
    readme.write_text(_set_tagline(readme.read_text(encoding="utf-8"), TAGLINE), encoding="utf-8")
    for step in steps:
        p = run_cli("--meta", meta, "--repo-dir", repo, *step)
        assert p.returncode == 0, p.stderr
        assert _tagline_body(readme.read_text(encoding="utf-8")) == TAGLINE, step


def test_variant_f_bootstrap_keeps_a_tagline_the_owner_wrote(make_ctx, tmp_path):
    authored = '<p align="center"><b>Check Northwind hosts for the advisory.</b></p>'
    ctx = make_ctx(tmp_path, repo="new-thing", description="")
    ctx.det["variant"] = "F"
    text = (R.header(ctx) + "\n\n" + R.pristine_block("## About\n\nTemplate body.") + "\n")
    text = _set_tagline(text, authored)
    assert _tagline_body(R.bootstrap(ctx, text)) == ""  # unknown template taglines + pristine body: inherited
    ctx = make_ctx(tmp_path, repo="new-thing", description="", template_taglines=[TEMPLATE_TAGLINE])
    ctx.det["variant"] = "F"
    assert _tagline_body(R.bootstrap(ctx, text)) == authored


# -- meta: the template README's tagline block is found the way readme.py finds it (outside code) ---------------------
def _readme_obj(text: str) -> dict:
    import base64
    return {"path": "README.md", "content": base64.b64encode(text.encode()).decode()}


def test_template_tagline_skips_marker_examples_in_code():
    from ctshowcase import meta as M
    real = "<!-- showcase:tagline:start -->\n**Start a Northwind repository.**\n<!-- showcase:tagline:end -->\n"
    fenced = ("# T\n\n```markdown\n<!-- showcase:tagline:start -->\n**Example.**\n<!-- showcase:tagline:end -->\n```\n\n"
              + real)
    inline = "# T\n\nThe Action rewrites `<!-- showcase:tagline:start -->` blocks.\n\n" + real
    open_only = "# T\n\nWrite the line under\n\n```\n<!-- showcase:tagline:start -->\n```\n\n" + real
    for text in (fenced, inline, open_only):
        assert M._tagline_of(_readme_obj(text)) == "**Start a Northwind repository.**", text
    only_code = "# T\n\n```\n<!-- showcase:tagline:start -->\n**Example.**\n<!-- showcase:tagline:end -->\n```\n"
    assert M._tagline_of(_readme_obj(only_code)) is None


def test_meta_stays_stdlib_only():
    # meta is imported by stdlib-only commands: it must not pull in the README stack (or yaml)
    import subprocess
    import sys
    from conftest import ROOT
    code = ("import sys; sys.path.insert(0, 'scripts'); import ctshowcase.meta; "
            "print(sorted(m for m in sys.modules if m.startswith('ctshowcase.') or m == 'yaml'))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert "ctshowcase.readme" not in out and "'yaml'" not in out, out


def test_upgrade_keeps_a_tagline_the_owner_wrote(make_ctx, tmp_path):
    # upgrade rebuilds the header too (readme --mode upgrade, and bootstrap once a person edited the template body):
    # the same rule decides the tagline, so the never-drop-a-line check has nothing to object to
    ctx = make_ctx(tmp_path, description="")
    out, removed = R.upgrade(ctx, TEXT)
    assert _tagline_body(out) == TAGLINE and not R.preservation(TEXT, out, removed)
    inherited = "**Start a Northwind repository.**"
    ctx = make_ctx(tmp_path, description="", template_taglines=[inherited])
    assert _tagline_body(R.upgrade(ctx, TEXT.replace(TAGLINE, inherited))[0]) == ""
    out, removed = R.upgrade(ctx, TEXT.replace(TAGLINE, inherited))
    assert not R.preservation(TEXT.replace(TAGLINE, inherited), out, removed)  # dropped on purpose, not lost


def test_cli_upgrade_empties_an_inherited_tagline(tmp_path):
    # readme --mode upgrade (and auto, which picks upgrade here) empties an inherited tagline as header mode does,
    # instead of failing the never-delete check with readme-shrink and leaving README.md unchanged
    import json
    from conftest import meta_dict, run_cli
    for mode in ("upgrade", "auto"):
        repo = tmp_path / mode
        repo.mkdir()
        (repo / "README.md").write_text(TEXT, encoding="utf-8")
        meta = tmp_path / f"meta-{mode}.json"
        meta.write_text(json.dumps(meta_dict(description="", template_taglines=[TAGLINE])), encoding="utf-8")
        p = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", mode, "--write")
        assert p.returncode == 0, p.stdout + p.stderr
        out = json.loads(p.stdout)
        assert out["result"] == "changed" and "readme-shrink" not in out["logs"], out
        after = (repo / "README.md").read_text(encoding="utf-8")
        assert _tagline_body(after) == "" and TAGLINE not in after and "Run it." in after


# -- upgrade's preserve branch (a README over 15000 bytes, or one on the org's readme_preserve list) ------------------
BIG = TEXT + "\n" + "\n\n".join(f"Paragraph {i} about the Northwind triage agent, written by its owner." for i in range(260)) + "\n"


def test_cli_upgrade_preserve_keeps_the_tagline_block_in_place(tmp_path):
    # preserve mode is additive only: the tagline block stays where it was, decided by the header rule, instead of
    # being dropped (which failed the never-delete check with readme-shrink and left README.md unchanged)
    import json
    from conftest import meta_dict, run_cli
    assert len(BIG.encode()) > 15000
    inherited = "**Start a Northwind repository.**"
    cases = (("authored", BIG, [], TAGLINE), ("inherited", BIG.replace(TAGLINE, inherited), [inherited], ""))
    for name, text, taglines, want in cases:
        repo = tmp_path / name
        repo.mkdir()
        (repo / "README.md").write_text(text, encoding="utf-8")
        meta = tmp_path / f"meta-{name}.json"
        meta.write_text(json.dumps(meta_dict(description="", template_taglines=taglines)), encoding="utf-8")
        p = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "upgrade", "--write")
        assert p.returncode == 0, p.stdout + p.stderr
        out = json.loads(p.stdout)
        assert out["result"] == "changed" and "readme-shrink" not in out["logs"], out
        after = (repo / "README.md").read_text(encoding="utf-8")
        assert _tagline_body(after) == want, name
        assert after.index("# Support Triage Agent") < after.index("<!-- showcase:tagline:start -->") < after.index(
            "## Usage"), name  # in place, under the README's own H1
        assert "Paragraph 259 about the Northwind triage agent" in after


# -- an unmarked bold tagline (a README adopted for the first time) ---------------------------------------------------
PLAIN = "# Support Triage Agent\n\n" + TAGLINE + "\n\n## Usage\n\nRun it.\n\n## Install\n\npip install it.\n"


def test_cli_upgrade_moves_an_unmarked_tagline_into_the_block(tmp_path):
    # header mode keeps the line byte for byte; upgrade (and auto) used to erase it silently with no description
    import json
    from conftest import meta_dict, run_cli
    for mode in ("upgrade", "auto"):
        repo = tmp_path / mode
        repo.mkdir()
        (repo / "README.md").write_text(PLAIN, encoding="utf-8")
        meta = tmp_path / f"meta-{mode}.json"
        meta.write_text(json.dumps(meta_dict(description="")), encoding="utf-8")
        p = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", mode, "--write")
        assert p.returncode == 0, p.stdout + p.stderr
        out = json.loads(p.stdout)
        assert out["result"] == "changed" and "needs-input:description" in out["logs"], out
        after = (repo / "README.md").read_text(encoding="utf-8")
        assert _tagline_body(after) == TAGLINE and after.count(TAGLINE) == 1, mode


def test_upgrade_unmarked_tagline_follows_the_header_rule(make_ctx, tmp_path):
    # a second bold line stays as authored text; an inherited unmarked line is emptied on purpose; a description
    # still replaces the old line
    second = "**Owned by the Northwind support team.**"
    text = PLAIN.replace(TAGLINE, TAGLINE + "\n\n" + second)
    ctx = make_ctx(tmp_path, description="")
    out, removed = R.upgrade(ctx, text)
    assert _tagline_body(out) == TAGLINE and second in out and not R.preservation(text, out, removed)
    marked = TEXT.replace("## Usage", second + "\n\n## Usage")  # a tagline block already holds the line
    out, removed = R.upgrade(make_ctx(tmp_path, description=""), marked)
    assert _tagline_body(out) == TAGLINE and second in out and not R.preservation(marked, out, removed)
    ctx = make_ctx(tmp_path, description="", template_taglines=[TAGLINE])
    out, removed = R.upgrade(ctx, PLAIN)
    assert _tagline_body(out) == "" and TAGLINE not in out and not R.preservation(PLAIN, out, removed)
    ctx = make_ctx(tmp_path, description="Route Northwind tickets.")
    out, removed = R.upgrade(ctx, PLAIN)
    assert _tagline_body(out) == "**Route Northwind tickets.**" and TAGLINE not in out


def test_upgrade_leaves_other_unmarked_taglines_as_authored_text(make_ctx, tmp_path):
    # the move is narrow (the documented contract): only a bare **...** line under the H1 on the rebuild path is
    # carried; a bold line in a centred <div>/<p> block, or a bare one in preserve mode, is kept, never erased
    centred = "<p align=\"center\"><b>Route Northwind support tickets to the right queue.</b></p>"
    div = PLAIN.replace("# Support Triage Agent\n\n" + TAGLINE,
                        "<div align=\"center\">\n\n# Support Triage Agent\n\n" + TAGLINE + "\n\n</div>")
    big = PLAIN + "\n" + "\n\n".join(f"Owner paragraph {i} about Northwind." for i in range(600)) + "\n"
    assert len(big.encode()) > 15000
    for name, text, line in (("div", div, TAGLINE), ("p", PLAIN.replace(TAGLINE, centred), centred),
                             ("preserve", big, TAGLINE)):
        out, removed = R.upgrade(make_ctx(tmp_path, description=""), text)
        assert line in out and not R.preservation(text, out, removed), name
        if name == "preserve":  # additive only: the line stays under the H1 and no tagline block is added
            assert "<!-- showcase:tagline:start -->" not in out
            assert out.index("# Support Triage Agent") < out.index(line) < out.index("## Usage"), name
        else:  # the rebuilt block stays empty and the line is kept below the header as authored text
            assert _tagline_body(out) == "" and out.count(line) == 1, name
