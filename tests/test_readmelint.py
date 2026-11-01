import shutil

from ctshowcase import footer, readme, readmelint
from conftest import EX


def good_readme(make_ctx, tmp_path, brand):
    shutil.copytree(EX / "repos" / "northwind-support-triage-agent", tmp_path, dirs_exist_ok=True)
    (tmp_path / "docs/images").mkdir(parents=True)
    (tmp_path / "docs/images/banner.png").write_bytes(b"x")
    ctx = make_ctx(repo_dir=tmp_path, description="Run the Northwind customer support email triage agent from the command line.")
    text = readme.scaffold(ctx, "")
    text = text.replace("## License", "## Usage\n\nRun `triage --help`.\n\n## License")
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    return ctx


def test_pass_then_each_failure(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = tmp_path / "README.md"
    r = readmelint.lint(ctx, p)
    assert r["result"] in ("pass", "incomplete"), r
    base = p.read_text(encoding="utf-8")
    cases = {
        "D13": base.replace('<img src="docs/images/banner.png"', '<picture><img src="docs/images/banner.png"').replace(
            'width="100%">\n</p>', 'width="100%"></picture>\n</p>'),
        "D18": base.replace("width=\"200\"", "width=\"220\""),
        "R7 placeholder": base.replace("## Install", "TODO later\n\n## Install"),
        "R7 emoji": base.replace("## Install", "Done ✅\n\n## Install"),
        "R7 code fence": base.replace("```bash\npip install .", "```\npip install ."),
        "R2": base.replace("**Run the Northwind", "**Runs the Northwind"),
        "R7 nav": base.split("\n", 3)[3],
        "R7 off-palette": base.replace("-005ADD)", "-8A2BE2)"),
    }
    for rule, text in cases.items():
        p.write_text(text, encoding="utf-8")
        res = readmelint.lint(ctx, p)
        assert res["result"] == "fail" and any(f.startswith(rule.split()[0]) for f in res["fails"]), (rule, res["fails"])


def test_incomplete_only_needs_input(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = tmp_path / "README.md"
    p.write_text(p.read_text(encoding="utf-8").replace("## Usage\n\nRun `triage --help`.\n\n", ""), encoding="utf-8")
    r = readmelint.lint(ctx, p)
    assert r["result"] == "incomplete" and "needs-input:C:Usage" in r["logs"]
    assert footer.check(brand, p.read_text(encoding="utf-8"))[0] == "pass"


def _insert_usage(tmp_path, extra):
    p = tmp_path / "README.md"
    p.write_text(p.read_text(encoding="utf-8").replace("## License", extra + "\n\n## License", 1), encoding="utf-8")
    return p


def test_image_destination_with_backticks_is_read_unmasked(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    (tmp_path / "docs/images/build`draft`.png").write_bytes(b"x")
    p = _insert_usage(tmp_path, "![Shot](<docs/images/build`draft`.png>)")
    res = readmelint.lint(ctx, p)
    assert not any("local image" in f for f in res["fails"]), res["fails"]


def test_missing_image_with_backticks_is_reported_under_its_real_name(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "![Shot](<docs/images/build`draft`.png>)")
    res = readmelint.lint(ctx, p)
    assert "R7 local image does not resolve: docs/images/build`draft`.png" in res["fails"], res["fails"]


def test_multiline_inline_code_placeholder_is_not_flagged(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "Example ```sample\nTODO``` end.")
    res = readmelint.lint(ctx, p)
    assert not any("placeholder" in f.lower() for f in res["fails"]), res["fails"]
    assert not any("TODO" in f for f in res["fails"]), res["fails"]


def test_list_item_backtick_does_not_hide_a_missing_image_in_the_next_item(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "- Install `foo\n- See ![Logo](docs/images/missing.png) and `bar`")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_ordered_list_backtick_does_not_hide_a_missing_image_in_the_next_item(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "1. Install `foo\n2. See ![Logo](docs/images/missing.png) and `bar`")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_ordered_list_starting_at_one_second_item(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "1. Install `foo\n1. See ![Logo](docs/images/missing.png) and `bar`")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_angle_destination_backtick_pairs_with_nothing():
    text = "![A](<https://example.test/a`b.png>) ![B](<docs/images/missing.png>) `code`"
    found = readmelint._images(readmelint._outside_code(text), text)
    assert [source for _, source in found] == ["https://example.test/a`b.png", "docs/images/missing.png"]


def test_angle_destination_backtick_does_not_hide_the_missing_file(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "![A](<https://example.test/a`b.png>) ![B](<docs/images/missing.png>) `code`")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_plain_destination_backtick_does_not_hide_the_missing_file(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "![A](a`b.png) ![B](missing.png) `c`")
    assert "R7 local image does not resolve: missing.png" in readmelint.lint(ctx, p)["fails"]


def test_backtick_opener_before_the_closing_bracket_still_wins():
    text = "![A `x](docs/images/missing.png) y` tail"
    assert readmelint._images(readmelint._outside_code(text), text) == []


def test_reference_definition_inside_multiline_code_is_not_a_definition(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "![Shot][example]\n\nExample `syntax\n[example]: docs/images/missing.png\nend`")
    res = readmelint.lint(ctx, p)
    assert not any("local image" in f for f in res["fails"]), res["fails"]
    text = p.read_text(encoding="utf-8")
    assert readmelint._images(readmelint._outside_code(text), text) == [] or all(
        "missing.png" not in source for _, source in readmelint._images(readmelint._outside_code(text), text))


def test_reference_definition_with_backtick_label_still_defines_the_image(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "![Shot][`a`]\n\n[`a`]: docs/images/missing.png")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_off_palette_badge_colour_is_reported_once(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = tmp_path / "README.md"
    p.write_text("# X\n\n![Type](https://img.shields.io/badge/type-x-FF0000)\n", encoding="utf-8")
    assert readmelint.lint(ctx, p)["fails"].count("R7 off-palette badge colour FF0000") == 1


# --- Shields badge colour is the last structural segment of the complete destination ------------------------------
import pytest  # noqa: E402


def _badge_fails(make_ctx, tmp_path, brand, body):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = tmp_path / "README.md"
    p.write_text("# X\n\n" + body + "\n", encoding="utf-8")
    return readmelint.lint(ctx, p)["fails"]


@pytest.mark.parametrize("body", [
    "![Type](https://img.shields.io/badge/type-facade's-005ADD)",
    "![Type](https://img.shields.io/badge/type-DEADBE's-005ADD)",
    "![Type](https://img.shields.io/badge/my--label-a__b-005ADD)",
    "![Type](https://img.shields.io/badge/my__label-x--y-64748B)",
    "![Type](https://img.shields.io/badge/type-facade's-005ADD?style=flat)",
    '<img alt="Type" src="https://img.shields.io/badge/type-facade\'s-005ADD">',
], ids=["apostrophe-probe", "hex-message-before-apostrophe", "escaped-dashes-label", "escaped-underscores-label",
        "apostrophe-with-query", "html-img-apostrophe"])
def test_shields_colour_is_the_last_segment(make_ctx, tmp_path, brand, body):
    assert not any("off-palette" in f for f in _badge_fails(make_ctx, tmp_path, brand, body))


@pytest.mark.parametrize("body", [
    "![Type](https://img.shields.io/badge/type-facade's-123ABC)",
    "![Type](https://img.shields.io/badge/type-x-123ABC)",
    "![Type](https://img.shields.io/badge/my--label-x--y-123ABC)",
    '<img alt="Type" src="https://img.shields.io/badge/type-facade\'s-123ABC">',
])
def test_genuinely_off_palette_colour_still_fails(make_ctx, tmp_path, brand, body):
    assert "R7 off-palette badge colour 123ABC" in _badge_fails(make_ctx, tmp_path, brand, body)


def test_hex_shaped_message_is_not_taken_for_the_colour():
    assert readmelint._badge_colour("type-DEADBE's-005ADD") == "005ADD"
    assert readmelint._badge_colour("a--b-c__d-64748B?logo=x#frag") == "64748B"


# --- round-7 container, definition-context, encoded-badge and nested-image regressions ----------------------------
MISSING = "R7 local image does not resolve: docs/images/missing.png"
OFF_ABC = "R7 off-palette badge colour ABCDEF"


def _usage_fails(make_ctx, tmp_path, brand, snippet):
    ctx = good_readme(make_ctx, tmp_path, brand)
    return readmelint.lint(ctx, _insert_usage(tmp_path, snippet))["fails"]


@pytest.mark.parametrize("snippet", [
    "See the screenshot below.\n[shot]: ![Screenshot](docs/images/missing.png)",
    "Text\n[a]: https://example.test/a\nmore text\n[shot]: ![Screenshot](docs/images/missing.png)",
], ids=["probe", "after-a-definition-and-text"])
def test_definition_like_line_inside_a_paragraph_is_text(make_ctx, tmp_path, brand, snippet):
    assert MISSING in _usage_fails(make_ctx, tmp_path, brand, snippet)


@pytest.mark.parametrize("snippet", [
    "[shot]: ![Screenshot](docs/images/missing.png)",
    "Intro.\n\n[shot]: ![Screenshot](docs/images/missing.png)",
    "[a]: https://example.test/a\n[shot]: ![Screenshot](docs/images/missing.png)",
], ids=["block-start", "after-blank-line", "after-another-definition"])
def test_real_block_start_definition_is_not_an_image(make_ctx, tmp_path, brand, snippet):
    assert MISSING not in _usage_fails(make_ctx, tmp_path, brand, snippet)


@pytest.mark.parametrize("label", ["C%23", "C%3F", "C%23%3F"])
def test_encoded_hash_and_question_mark_in_a_label_do_not_hide_the_colour(make_ctx, tmp_path, brand, label):
    body = f"![L](https://img.shields.io/badge/language-{label}-FF0000)"
    assert "R7 off-palette badge colour FF0000" in _badge_fails(make_ctx, tmp_path, brand, body)


def test_literal_query_after_the_colour_still_fails(make_ctx, tmp_path, brand):
    bad = "![L](https://img.shields.io/badge/language-C-FF0000?style=flat)"
    assert "R7 off-palette badge colour FF0000" in _badge_fails(make_ctx, tmp_path, brand, bad)


def test_encoded_label_with_on_palette_colour_passes(make_ctx, tmp_path, brand):
    good = "![L](https://img.shields.io/badge/language-C%23-005ADD)"
    assert not any("off-palette" in f for f in _badge_fails(make_ctx, tmp_path, brand, good))


def test_badge_colour_decodes_only_after_removing_literal_delimiters():
    assert readmelint._badge_colour("language-C%23-FF0000?x=1#f") == "FF0000"
    assert readmelint._badge_colour("language-C%3F-005ADD") == "005ADD"


def test_backtick_in_a_definition_destination_does_not_hide_the_next_image(make_ctx, tmp_path, brand):
    snippet = "[unused]: https://example.test/a`b.png\n![Shot](<docs/images/missing.png>) `tail`"
    assert MISSING in _usage_fails(make_ctx, tmp_path, brand, snippet)


def test_definition_in_fence_stays_literal(make_ctx, tmp_path, brand):
    fenced = "```text\n[unused]: https://example.test/a`b.png\n```\n\n`tail` ![Shot](docs/images/missing.png)"
    assert MISSING in _usage_fails(make_ctx, tmp_path, brand, fenced)


def test_definition_like_line_in_a_code_span_stays_literal(make_ctx, tmp_path, brand):
    spanned = "Use `a\n[x]: ![S](docs/images/missing.png)` end"
    assert MISSING not in _usage_fails(make_ctx, tmp_path, brand, spanned)


def test_failed_outer_image_leaves_its_nested_image(make_ctx, tmp_path, brand):
    assert MISSING in _usage_fails(make_ctx, tmp_path, brand, "![outer ![inner](docs/images/missing.png)]")


def test_resolved_outer_reference_image_still_consumes_its_nested_text(make_ctx, tmp_path, brand):
    doc = "![outer ![inner](docs/images/missing.png)][ref]\n\n[ref]: https://example.test/ok.png\n"
    found = readmelint._images(readmelint._outside_code(doc), doc)
    assert [src for _, src in found] == ["https://example.test/ok.png"]


FENCE_TAIL = ["![x](docs/images/missing.png)", "![x](https://img.shields.io/badge/a-b-ABCDEF)"]


@pytest.mark.parametrize("opener,body,closer", [
    ("1. ```bash", "   npm test", "   ```"), ("- ```text", "  npm test", "  ```"),
    ("1. ~~~bash", "   npm test", "   ~~~"), ("- ~~~text", "  npm test", "  ~~~"),
    ("- - ```text", "    npm test", "    ```"), ("10. ```text", "    npm test", "    ```"),
], ids=["ordered", "bullet", "ordered-tilde", "bullet-tilde", "nested-item", "wide-marker"])
@pytest.mark.parametrize("tail", FENCE_TAIL, ids=["missing-image", "off-palette-badge"])
def test_item_fence_does_not_hide_what_follows(make_ctx, tmp_path, brand, opener, body, closer, tail):
    fails = _usage_fails(make_ctx, tmp_path, brand, f"{opener}\n{body}\n{closer}\n\n{tail}")
    assert MISSING in fails or OFF_ABC in fails


@pytest.mark.parametrize("snippet", [
    "- ```text\n  TODO\n  ```", "1. ```text\n   TODO\n   ```", "- > ```text\n  > TODO\n  > ```",
    "> - ```text\n>   TODO\n>   ```", "- ~~~text\n  TODO\n  ~~~", "- - ```text\n    TODO\n    ```",
], ids=["bullet", "ordered", "item-quote", "quote-item", "tilde", "nested-item"])
def test_placeholder_inside_an_item_fence_is_code(make_ctx, tmp_path, brand, snippet):
    assert not any("placeholder" in f for f in _usage_fails(make_ctx, tmp_path, brand, snippet))


def test_genuine_placeholder_outside_code_still_fails(make_ctx, tmp_path, brand):
    snippet = "- ```text\n  fine\n  ```\n\nTODO"
    assert any("placeholder" in f for f in _usage_fails(make_ctx, tmp_path, brand, snippet))


@pytest.mark.parametrize("path,colour", [
    ("type-example---FF0000", "FF0000"),
    ("x-a---005ADD", "005ADD"),
    ("type-example-005ADD", "005ADD"),
    ("my--label-a--b-64748B", "64748B"),
], ids=["trailing-dash-off-palette", "trailing-dash-on-palette", "plain", "escaped-dashes"])
def test_badge_colour_keeps_the_structural_separator_after_a_trailing_dash(path, colour):
    assert readmelint._badge_colour(path) == colour


def test_trailing_dash_message_with_off_palette_colour_is_reported(make_ctx, tmp_path, brand):
    body = "![Type](<https://img.shields.io/badge/type-example---FF0000>)"
    assert "R7 off-palette badge colour FF0000" in _badge_fails(make_ctx, tmp_path, brand, body)


def test_trailing_dash_message_with_palette_colour_passes(make_ctx, tmp_path, brand):
    body = "![Type](<https://img.shields.io/badge/type-example---005ADD>)"
    assert not any("off-palette" in f for f in _badge_fails(make_ctx, tmp_path, brand, body))


def test_extra_quote_markers_in_a_quoted_fence_do_not_hide_a_missing_image(make_ctx, tmp_path, brand):
    snippet = "> ```text\n> > ```\n> code\n> ```\n> ![Shot](<docs/images/missing.png>)"
    assert MISSING in _usage_fails(make_ctx, tmp_path, brand, snippet)


# --- a resolved full-reference label is literal text: its backticks never open inline code ---------------------------
REF_LABEL_DEFINITION = "[docs`ref]: https://example.test/docs"
REF_LABEL_LAYOUT = ("[Docs][docs`ref] ![Type](<https://img.shields.io/badge/type-GitHub%20profile-{type}>) "
                    "![License](<https://img.shields.io/badge/license-MIT-{license}>) `help`")


def test_backtick_in_a_resolved_reference_label_does_not_pair_with_later_code(make_ctx, tmp_path, brand):
    licence_off = REF_LABEL_LAYOUT.format(type="005ADD", license="FF0000") + "\n\n" + REF_LABEL_DEFINITION
    assert "R7 off-palette badge colour FF0000" in _badge_fails(make_ctx, tmp_path, brand, licence_off)
    type_off = REF_LABEL_LAYOUT.format(type="FF0000", license="64748B") + "\n\n" + REF_LABEL_DEFINITION
    second = tmp_path / "second"  # good_readme builds a fresh tree, so the second body gets its own directory
    second.mkdir()
    assert "R7 off-palette badge colour FF0000" in _badge_fails(make_ctx, second, brand, type_off)


# GFM expectation (test data): orphan junction renders 1 image, raw comment boundary 1, and the inline-comment,
# valid-reference and consecutive-reference controls (same label, distinct labels, three same label) render 0 images,
# matching GFM per the 6dcc adjudication.
IMAGE_IN_CODE = "`![Shot](<docs/images/missing.png>)`"
REF_DEF = "\n\n[ref`x]: https://example.test/"
ORPHAN_JUNCTION_CASES = {
    "orphan_reference_junction": ("][ref`x] " + IMAGE_IN_CODE + REF_DEF, True),
    "raw_comment_boundary": ("See [open\n<!-- note -->\n](a`b) " + IMAGE_IN_CODE, True),
    "inline_comment_control": ("[open <!-- note -->](a`b) " + IMAGE_IN_CODE, False),
    "valid_reference_control": ("[text][ref`x] " + IMAGE_IN_CODE + REF_DEF, False),
    "consecutive_reference_control": ("[a][ref`x] [b][ref`x] " + IMAGE_IN_CODE + REF_DEF, False),
    "consecutive_distinct_label_control": (
        "[a][one`x] [b][two`y] " + IMAGE_IN_CODE + "\n\n[one`x]: https://example.test/\n[two`y]: https://example.test/",
        False,
    ),
    "consecutive_three_same_label_control": ("[a][ref`x] [b][ref`x] [c][ref`x] " + IMAGE_IN_CODE + REF_DEF, False),
}


@pytest.mark.parametrize("extra,reported", list(ORPHAN_JUNCTION_CASES.values()), ids=list(ORPHAN_JUNCTION_CASES))
def test_orphan_reference_junction_and_comment_controls(make_ctx, tmp_path, brand, extra, reported):
    ctx = good_readme(make_ctx, tmp_path, brand)
    readme = tmp_path / "README.md"
    readme.write_text(readme.read_text(encoding="utf8").replace("## Usage", extra + "\n\n## Usage"), encoding="utf8")
    fails = readmelint.lint(ctx, readme)["fails"]
    if reported:
        assert MISSING in fails
    else:
        assert fails == []


def test_backtick_in_an_unresolved_reference_label_still_opens_code(make_ctx, tmp_path, brand):
    # no `[docs`ref]:` definition: the label is not a reference, so its backtick pairs with the one before `help`
    body = REF_LABEL_LAYOUT.format(type="005ADD", license="FF0000")
    assert "R7 off-palette badge colour FF0000" not in _badge_fails(make_ctx, tmp_path, brand, body)


def test_code_before_the_label_keeps_precedence(make_ctx, tmp_path, brand):
    # the code span opened before the label ends at the label's backtick (CommonMark), so the badge inside it is code
    body = ("![License](<https://img.shields.io/badge/license-MIT-FF0000>) `x ![Type](<https://img.shields.io/badge/type-x-ABCDEF>)"
            " [a][docs`ref] y`\n\n" + REF_LABEL_DEFINITION)
    fails = _badge_fails(make_ctx, tmp_path, brand, body)
    assert "R7 off-palette badge colour FF0000" in fails
    assert "R7 off-palette badge colour ABCDEF" not in fails


def test_resolved_reference_label_scan_stays_linear():
    text = "[a][docs`ref] " * 2000 + "\n\n" + REF_LABEL_DEFINITION + "\n"
    assert len(readmelint._outside_code(text)) == len(text)


# --- round-7 reference definitions inside blockquote and list containers --------------------------------------------
CONTAINER_DEFINITIONS = [
    "> [shot]: docs/images/missing.png",
    "- [shot]: docs/images/missing.png",
    "1. [shot]: docs/images/missing.png",
    "> - [shot]: docs/images/missing.png",
    "- > [shot]: docs/images/missing.png",
    "> > [shot]: docs/images/missing.png",
    "> [shot]: <docs/images/missing.png>",
]
CONTAINER_IDS = ["quote", "bullet", "ordered", "quote-bullet", "bullet-quote", "nested-quote", "quote-angle"]


@pytest.mark.parametrize("definition", CONTAINER_DEFINITIONS, ids=CONTAINER_IDS)
def test_container_reference_definition_reports_missing_local_image(make_ctx, tmp_path, brand, definition):
    assert MISSING in _usage_fails(make_ctx, tmp_path, brand, f"![Screenshot][shot]\n\n{definition}")


CONTAINER_CONTROLS = [
    ("fenced", "```text\n[shot]: docs/images/missing.png\n```"),
    ("inline-code", "Use `[shot]: docs/images/missing.png` here."),
    ("indented-code", "    [shot]: docs/images/missing.png"),
    ("paragraph-continuation", "> text\n> [shot]: docs/images/missing.png"),
]


@pytest.mark.parametrize("control", [c for _, c in CONTAINER_CONTROLS], ids=[i for i, _ in CONTAINER_CONTROLS])
def test_container_control_is_not_a_definition_and_renders_no_image(make_ctx, tmp_path, brand, control):
    fails = _usage_fails(make_ctx, tmp_path, brand, f"![Screenshot][shot]\n\n{control}")
    assert MISSING not in fails, fails
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert not any("missing.png" in source for _, source in readmelint._images(readmelint._outside_code(text), text))


BADGE_TYPE_LINE = "![Type](<https://img.shields.io/badge/type-GitHub%20profile-005ADD>)"
BADGE_LICENSE_LINE = "![License][lic]"
LICENSE_DEFINITION = "<https://img.shields.io/badge/license-MIT-64748B>"


def _variant_j_badge_fails(make_ctx, tmp_path, definition):
    # Inlined from the Variant J fixture in test_variant_j_badges.py: a profile repo with the header badges replaced
    # by the reference-style pair under test, and the definition placed after the header and before the footer.
    (tmp_path / "docs/images").mkdir(parents=True)
    (tmp_path / "docs/images/banner.png").write_bytes(b"banner")
    ctx = make_ctx(repo_dir=tmp_path, repo=".github", language=None,
                   description="Community health files for Northwind Trading Co.")
    text = readme.scaffold(ctx)
    original = next(m.group(2) for m in readme.MARK.finditer(text) if m.group(1) == "badges")
    text = text.replace(original, BADGE_TYPE_LINE + "\n" + BADGE_LICENSE_LINE + "\n")
    text = text.replace("<!-- showcase:footer:start -->", definition + "\n\n<!-- showcase:footer:start -->")
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    return readmelint.lint(ctx, path)["fails"]


@pytest.mark.parametrize("definition", [
    f"> [lic]: {LICENSE_DEFINITION}",
    f"- [lic]: {LICENSE_DEFINITION}",
], ids=["quote", "bullet"])
def test_container_definition_counts_its_header_badge(make_ctx, tmp_path, definition):
    fails = _variant_j_badge_fails(make_ctx, tmp_path, definition)
    assert not any("2-4 header badges required" in f for f in fails), fails


def test_missing_container_definition_still_reports_one_header_badge(make_ctx, tmp_path):
    fails = _variant_j_badge_fails(make_ctx, tmp_path, "")
    assert "R7 2-4 header badges required (found 1)" in fails, fails


RAW_HTML_IMG = '<img src="docs/images/missing.png" alt="Shot">'


def test_literal_backticks_in_a_raw_html_block_do_not_hide_a_missing_image(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "<div>\nUse a literal ` character.\n" + RAW_HTML_IMG + "\nAnother ` character.\n</div>")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_a_real_img_inside_an_html_block_is_still_counted_for_r7(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "<div>\n" + RAW_HTML_IMG + "\n</div>")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_backticks_after_the_html_block_ends_at_a_blank_line_still_hide_an_image(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "<div>\nraw\n</div>\n\nUse ` and " + RAW_HTML_IMG + " and `")
    assert not any("local image" in f for f in readmelint.lint(ctx, p)["fails"])


# Raw HTML blocks are literal HTML: no live reference definitions, and backslashes are not escapes there.
def test_definition_inside_a_raw_html_block_is_not_live(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "![Shot][shot]\n\n<div>\n[shot]: docs/images/missing.png\n</div>")
    assert not any("local image" in f for f in readmelint.lint(ctx, p)["fails"])


def test_definition_after_the_html_block_ends_is_live(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "![Shot][shot]\n\n<div>\nraw\n</div>\n\n[shot]: docs/images/missing.png")
    assert MISSING in readmelint.lint(ctx, p)["fails"]


def test_escaped_img_inside_a_raw_html_block_is_still_checked(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "<div>\n\\" + RAW_HTML_IMG + "\n</div>")
    assert MISSING in readmelint.lint(ctx, p)["fails"]


def test_escaped_img_in_an_ordinary_paragraph_is_not_checked(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "\\" + RAW_HTML_IMG)
    assert not any("local image" in f for f in readmelint.lint(ctx, p)["fails"])


DEDENTED_QUOTE_TAIL = "\n\nOrdinary paragraph."


def test_dedented_quote_after_a_list_item_fence_is_scanned_for_images(make_ctx, tmp_path, brand):
    # the unindented `>` cannot continue the list item, so the item and its unclosed fence end and a real quote begins
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "- ```text\n  example\n> ![Shot](<docs/images/missing.png>)" + DEDENTED_QUOTE_TAIL)
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_indented_quote_inside_a_list_item_fence_stays_code(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "- ```text\n  example\n  > ![Shot](<docs/images/missing.png>)\n  ```")
    assert not any("local image" in f for f in readmelint.lint(ctx, p)["fails"])


def test_dedented_quote_badges_after_a_list_item_fence_are_counted(make_ctx, tmp_path, brand):
    # the header badges become a dedented quote after an unclosed list-item fence: CommonMark renders both images
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = tmp_path / "README.md"
    text = p.read_text(encoding="utf-8")
    lines = text.split(chr(10))
    at = next(i for i, ln in enumerate(lines) if "img.shields.io/badge/" in ln)
    lines[at:at + 3] = [  # the three derived badges are replaced, so only the quoted pair can be counted
        "- ```text", "  example",
        "> ![A](<https://img.shields.io/badge/type-example-005ADD>)"
        " ![B](<https://img.shields.io/badge/license-MIT-64748B>)",
        "", "Ordinary paragraph.",
    ]
    p.write_text(chr(10).join(lines), encoding="utf-8")
    fails = readmelint.lint(ctx, p)["fails"]
    assert not any(f.startswith("R7 2-4 header badges") for f in fails), fails


# CommonMark 4.6 / GFM: the content of a raw HTML block is literal HTML, so Markdown image syntax there is plain text.
def _image_fails(make_ctx, tmp_path, brand, snippet):
    return [f for f in _usage_fails(make_ctx, tmp_path, brand, snippet) if "local image" in f]


@pytest.mark.parametrize("snippet", [
    "<pre>\n![Example][shot]\n</pre>\n\n[shot]: docs/images/missing.png",
    "<pre>\n![Example](docs/images/missing.png)\n</pre>",
    "<div>\n![Example](docs/images/missing.png)\n</div>",
    "<div>\n![Example][shot]\n</div>\n\n[shot]: docs/images/missing.png",
    "<table>\n<tr><td>\n![Example](<docs/images/missing.png>)\n</td></tr>\n</table>",
], ids=["pre-reference", "pre-inline", "div-inline", "div-reference", "table-angle"])
def test_markdown_image_syntax_inside_a_raw_html_block_is_literal_text(make_ctx, tmp_path, brand, snippet):
    assert _image_fails(make_ctx, tmp_path, brand, snippet) == []


@pytest.mark.parametrize("snippet", [
    "<pre>\n" + RAW_HTML_IMG + "\n</pre>",
    "<div>\n" + RAW_HTML_IMG + "\n</div>",
], ids=["pre", "div"])
def test_a_real_html_img_inside_a_raw_html_block_is_still_reported(make_ctx, tmp_path, brand, snippet):
    assert _image_fails(make_ctx, tmp_path, brand, snippet) == [MISSING]


@pytest.mark.parametrize("snippet", [
    "<div>\nraw\n\n![Example](docs/images/missing.png)",
    "<div>\nraw\n</div>\n\n![Example][shot]\n\n[shot]: docs/images/missing.png",
    "<pre>\nraw\n</pre>\n![Example](docs/images/missing.png)",
    "<pre>\nraw </pre>\n\n![Example](docs/images/missing.png)",
], ids=["after-blank-in-div", "reference-after-div", "line-after-pre-end", "after-pre-end-line"])
def test_markdown_image_after_a_raw_html_block_ends_is_still_reported(make_ctx, tmp_path, brand, snippet):
    assert _image_fails(make_ctx, tmp_path, brand, snippet) == [MISSING]


def test_markdown_image_inside_a_fence_stays_literal(make_ctx, tmp_path, brand):
    assert _image_fails(make_ctx, tmp_path, brand, "```text\n![Example](docs/images/missing.png)\n```") == []


def test_many_images_and_html_blocks_are_scanned_in_linear_work():
    from ctshowcase import mdcode

    def work(n):
        doc = "".join(f"<div>\n![a{i}](docs/images/x{i}.png)\n</div>\n\n![b{i}](docs/images/y{i}.png)\n\n" for i in range(n))
        before = mdcode.WORK["span_checks"]
        found = readmelint._images(doc, doc)
        assert [src for _, src in found] == [f"docs/images/y{i}.png" for i in range(n)]
        return mdcode.WORK["span_checks"] - before

    small, large = work(200), work(1600)
    assert large <= small * 8 * 2, (small, large)


# GFM evidence: gfm-a358-raw_comment_one.html, gfm-a358-raw_comment_three.html, gfm-a358-escaped_comment_outside.html, gfm-a358-bare_destination.html, gfm-a358-valid_destination_control.html; review-cases-a358707026b1de858620e75ee652612c54ae507f-vm.json
@pytest.mark.parametrize("backslashes", [1, 3])
def test_raw_html_block_backslash_comment_hides_image(make_ctx, tmp_path, brand, backslashes):
    ctx = good_readme(make_ctx, tmp_path, brand)
    usage = "<div>\n" + "\\" * backslashes + '<!-- <img alt="Hidden" src="docs/images/missing.png"> -->\n</div>'
    p = _insert_usage(tmp_path, usage)
    fails = readmelint.lint(ctx, p)["fails"]
    assert "R7 local image does not resolve: docs/images/missing.png" not in fails, fails
    assert not any(f.startswith("R7") for f in fails), fails


def test_backslash_comment_outside_raw_html_still_fails(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, '\\<!-- <img alt="Hidden" src="docs/images/missing.png"> -->')
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, p)["fails"]


def test_bare_link_destination_backtick_does_not_hide_the_missing_image(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "See ](a`b) `![Shot](<docs/images/missing.png>)`")
    res = readmelint.lint(ctx, p)
    assert "R7 local image does not resolve: docs/images/missing.png" in res["fails"], res["fails"]
    assert res["result"] == "fail", res


def test_valid_link_destination_backtick_still_hides_the_image(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = _insert_usage(tmp_path, "[See](a`b) `![Shot](<docs/images/missing.png>)`")
    fails = readmelint.lint(ctx, p)["fails"]
    assert "R7 local image does not resolve: docs/images/missing.png" not in fails, fails

# --- round-11 active link openers --------------------------------------------------------------------------------------
# GFM evidence: gfm-3e-code_opener.html, gfm-3e-attribute_opener.html (real missing image renders); VM-confirmed at 3e85537.
@pytest.mark.parametrize("body,expect_missing", [
    ("See `[x` ](a`b) `![Shot](<docs/images/missing.png>)`", True),
    ('See <span title="[">x</span> ](a`b) `![Shot](<docs/images/missing.png>)`', True),
    ("See [x](ok) ](a`b) `![Shot](<docs/images/missing.png>)`", True),
    ("[x[y]](a`b) `![Shot](<docs/images/missing.png>)`", False),
], ids=["code_opener", "attribute_opener", "closed_link_control", "nested_valid_control"])
def test_round11_active_link_opener(make_ctx, tmp_path, brand, body, expect_missing):
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    if expect_missing:
        assert MISSING in fails, fails
    else:
        assert MISSING not in fails, fails


@pytest.mark.parametrize("text,expected", [
    ("`[a](b`", False),  # opener inside inline code
    ('<span title="[">x</span> ](b)', False),  # opener inside a tag attribute
    ("[a]", True),  # plain active opener
    ("\\[a]", False),  # escaped opener
    ("[a\n\nb]", False),  # blank line separates the opener from the closer
], ids=["code-opener", "attribute-opener", "plain", "escaped", "blank-line"])
def test_has_link_opener_direct(text, expected):
    assert readmelint._has_link_opener(text, text.index("]")) is expected


def test_link_opener_lookup_work_is_linear():
    def work(n):
        text = "word ](d) " * n
        readmelint._active_openers.cache_clear()
        readmelint._outside_code.cache_clear()
        readmelint._OPENER_STEPS = 0
        readmelint._outside_code(text)
        return readmelint._OPENER_STEPS, len(text)

    w50, len50 = work(50)
    w100, _ = work(100)
    w200, len200 = work(200)
    assert w100 <= 2.5 * w50, (w50, w100)
    assert w200 <= 2.5 * w100, (w100, w200)
    assert w50 <= 10 * len50 and w100 <= 10 * len(("word ](d) " * 100)) and w200 <= 10 * len200, (w50, w100, w200)

# --- active link openers reset at real block boundaries ----------------------------------------------------------------
# GFM oracle (rendered by GitHub): gfm-4f-opener_across_quote.html, gfm-4f-opener_across_list.html,
# gfm-4f-opener_across_fence.html, gfm-4f-opener_across_heading.html, gfm-4f-opener_across_heading-h2.html and
# gfm-4f-opener_blank_control.html (showcase-orchestration 20261031 directory). The unmatched `[open` ends its paragraph
# at each block start, so the orphan `](a`b)` is not a link closer and the following real image renders.
# Adjudication: t7-adjudication-opener-block-boundary-4f32c0a.md.
@pytest.mark.parametrize("block", [
    "> quote",
    "- item",
    "~~~text\nfenced\n~~~",
    "### heading",
    "## heading",
    "1. item",
    "***",
    "",
], ids=["quote", "list", "fence", "heading", "heading-h2", "ordered-list", "thematic-break", "blank-control"])
def test_opener_resets_at_block_boundary(make_ctx, tmp_path, brand, block):
    readmelint._active_openers.cache_clear()
    text = f"See [open\n{block}\n](a`b) ![Shot](<docs/images/missing.png>)"
    assert readmelint._has_link_opener(text, text.index("](a")) is False
    fails = _usage_fails(make_ctx, tmp_path, brand, text)
    assert MISSING in fails, fails


# A `[` closed inside its own list item or blockquote is still an active opener there (the reset only cuts a stack
# across a real block boundary). GFM: the closed link renders inside the block. Adjudication:
# t7-adjudication-opener-block-boundary-4f32c0a.md.
@pytest.mark.parametrize("text", [
    "- [a](b)",
    "> [a](b)",
    "> [a\n> ](b)",
    "- item [x\n  continued ](b)",
    "[a\nb](c)",
], ids=["list-closed", "quote-closed", "quote-continued", "list-continued", "paragraph-control"])
def test_opener_closed_inside_block_stays_active(text):
    readmelint._active_openers.cache_clear()
    assert readmelint._has_link_opener(text, text.index("]", text.index("["))) is True


# A heading line that carries its own unmatched opener does not leak it into the following paragraph line.
def test_heading_opener_does_not_leak_into_following_paragraph():
    readmelint._active_openers.cache_clear()
    text = "## [open\nfoo ](x)"
    assert readmelint._has_link_opener(text, text.index("]")) is False


# --- round-1 (fix plan) raw HTML block openers and nested links ---
# GFM renders (GitHub, showcase-orchestration 20261031 directory), adjudication
# t7-adjudication-raw-pre-nested-link-2d3a866.md:
#   gfm-2d3-raw_pre_opener.html        -> test_raw_html_block_opener_does_not_leak[pre-no-blank]
#   gfm-2d3-nested_link_opener.html    -> test_resolved_inner_link_deactivates_enclosing_link_opener[nested-link]
#   gfm-2d3-raw_pre_inert_control.html -> test_raw_pre_inert_control_has_no_missing_image
#   gfm-2d3-valid_link_control.html    -> test_valid_link_control_hides_image_in_code_span
# Cases without a GFM file yet are marked 'GFM render pending (not yet executed)': they are CommonMark derivations,
# not verified renders. Other adjudications: t7-adjudication-link-opener-assess-3e855.md and
# t7-adjudication-opener-block-boundary-4f32c0a.md.
RAW_TAIL = "](a`b) `![Shot](<docs/images/missing.png>)`"


# A `[` inside a raw HTML block is literal text, so it must not stay active for an orphan `](a`b)` after the block.
# The `<pre>` case has no blank line before the orphan, so only the raw-block boundary separates them. The `<div>` and
# `<table>` cases end with a blank line, which already clears the stack; they guard the same rendered image.
@pytest.mark.parametrize("body", [
    "<pre>\n[open\n</pre>\n" + RAW_TAIL,
    "<div>\n[open\n</div>\n\n" + RAW_TAIL,
    "<table>\n<tr><td>[open</td></tr>\n</table>\n\n" + RAW_TAIL,
], ids=["pre-no-blank", "div-blank-after", "table-blank-after"])
def test_raw_html_block_opener_does_not_leak(make_ctx, tmp_path, brand, body):
    readmelint._active_openers.cache_clear()
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    assert MISSING in fails, fails


def test_raw_pre_opener_is_not_an_active_opener():
    readmelint._active_openers.cache_clear()
    text = "<pre>\n[open\n</pre>\n" + RAW_TAIL
    assert readmelint._has_link_opener(text, text.index("](a")) is False


# A balanced bracket pair inside a raw HTML block is inert, and a valid link after the block still hides the image.
def test_bracket_pair_inside_raw_html_block_does_not_change_later_markdown(make_ctx, tmp_path, brand):
    readmelint._active_openers.cache_clear()
    body = "<pre>\n[a](b)\n</pre>\n\n[See](a`b) `![Shot](<docs/images/missing.png>)`"
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    assert MISSING not in fails, fails


# Once an inner link forms, CommonMark deactivates every earlier link opener (links may not contain links), so the
# enclosing `](a`b)` is literal and its backtick pairs normally. An enclosing IMAGE opener stays active. Each body
# is a static CommonMark trace of the reviewer finding, not a VM run.
@pytest.mark.parametrize("body,expect_missing", [
    ("[outer [inner](ok)](a`b) `![Shot](<docs/images/missing.png>)`", True),
    ("[a [b [c](x)](y)](a`b) `![Shot](<docs/images/missing.png>)`", True),
    ("![alt [inner](ok)](a`b) `![Shot](<docs/images/missing.png>)`", False),
    ("[x[y]](a`b) `![Shot](<docs/images/missing.png>)`", False),
], ids=["nested-link", "three-deep", "image-encloses-link", "bracket-without-destination"])
def test_resolved_inner_link_deactivates_enclosing_link_opener(make_ctx, tmp_path, brand, body, expect_missing):
    readmelint._active_openers.cache_clear()
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    if expect_missing:
        assert MISSING in fails, fails
    else:
        assert MISSING not in fails, fails


def test_inner_link_closer_active_and_enclosing_link_closer_inactive():
    readmelint._active_openers.cache_clear()
    text = "[outer [inner](ok)](z)"
    active = readmelint._active_openers(text)
    assert text.rindex("]") not in active
    assert text.index("]") in active


def test_inner_link_does_not_deactivate_enclosing_image_opener():
    readmelint._active_openers.cache_clear()
    text = "![alt [inner](ok)](z)"
    active = readmelint._active_openers(text)
    assert text.index("]") in active
    assert text.rindex("]") in active


# Deterministic counter (not wall-clock): steps per input character must not grow with the nesting depth k.
def test_nested_link_deactivation_work_is_linear():
    def ratio(k):
        text = "[a " * k + "[b](c)" + "](d) " * k
        readmelint._active_openers.cache_clear()
        readmelint._OPENER_STEPS = 0
        readmelint._active_openers(text)
        return readmelint._OPENER_STEPS / len(text)

    ratios = [ratio(k) for k in (100, 200, 400)]
    assert max(ratios) <= 1.5 * min(ratios), ratios


# --- round-2 invariant table (2d3 fix2): raw block types, reference links, adjacent links, linear reference work ----
# Invariants covered: (1) raw HTML block text creates no openers, with the block-end conditions; (2) a completed link
# deactivates earlier LINK openers, including reference-style links, while IMAGE openers stay; (3) unmatched brackets and
# adjacent links behave as in CommonMark. GFM citations: the raw-pre inert control and the valid-link control above
# (gfm-2d3-raw_pre_inert_control.html, gfm-2d3-valid_link_control.html). Every other case is a CommonMark 4.6 / 6.3
# derivation (GFM render pending (not yet executed) unless a gfm-<sha>-* file is cited). The nine exact oracle cases of
# t7-adjudication-reference-links-e90d748.md are pinned, with their GFM files, in test_e90_gfm_oracle_cases.


# Raw HTML block types (CommonMark 4.6). Type 1 (script/pre/style/textarea) ends at its end tag, which may be on the start
# line, and it does NOT end at a blank line; type 7 ends at a blank line. The `[open` is raw text, so the orphan `](a`b)`
# after the block is not a closer and the following image renders (MISSING reported).
# GFM renders exist for script/style/textarea/type-7 (gfm-e90-raw_{script,style,textarea,type7}_opener.html, pinned in
# test_e90_gfm_oracle_cases); the other ids here are derivations: GFM render pending (not yet executed).
@pytest.mark.parametrize("body", [
    "<script>\n[open\n</script>\n" + RAW_TAIL,  # type 1 script, end tag on its own later line
    "<style>\n[open\n</style>\n" + RAW_TAIL,  # type 1 style, end tag on its own later line
    "<textarea>\n[open\n</textarea>\n" + RAW_TAIL,  # type 1 textarea, end tag on its own later line
    "<pre>[open</pre>\n" + RAW_TAIL,  # type 1 pre, end condition met on the start line
    "<pre>\n[open\n\nstill raw\n</pre>\n" + RAW_TAIL,  # type 1 pre, a blank line inside does NOT end the block
    "<custom-tag>\n[open\n\n" + RAW_TAIL,  # type 7, ends at the blank line
], ids=[
    "type1-script-end-tag-later-line",
    "type1-style-end-tag-later-line",
    "type1-textarea-end-tag-later-line",
    "type1-pre-end-tag-on-start-line",
    "type1-pre-blank-line-inside-not-an-end",
    "type7-custom-tag-ends-at-blank-line",
])
def test_raw_html_block_types_do_not_leak_openers(make_ctx, tmp_path, brand, body):
    readmelint._active_openers.cache_clear()
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    assert MISSING in fails, fails


# GFM render: gfm-2d3-raw_pre_inert_control.html (no image). Everything inside a raw <pre> block is literal text.
def test_raw_pre_inert_control_has_no_missing_image(make_ctx, tmp_path, brand):
    readmelint._active_openers.cache_clear()
    body = "<pre>\n[open\n![Shot](<docs/images/missing.png>)\n</pre>"
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    assert MISSING not in fails, fails


# GFM render: gfm-2d3-valid_link_control.html (no image). The valid link's destination holds a backtick, and the next
# backtick pair is a real code span that hides the image.
def test_valid_link_control_hides_image_in_code_span(make_ctx, tmp_path, brand):
    readmelint._active_openers.cache_clear()
    body = "[outer](a`b) `![Shot](<docs/images/missing.png>)`"
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    assert MISSING not in fails, fails


REF_DEFINITION = "\n\n[ref]: https://example.test/r"


# A completed reference link (full, collapsed or shortcut, with a live definition) deactivates the enclosing link
# opener, so the orphan `](a`b)` is literal and the image renders. The exact GFM-rendered cases are in
# test_e90_gfm_oracle_cases below (gfm-e90-inner_*_reference.html).
@pytest.mark.parametrize("usage", [
    "[outer [x][ref]](a`b) `![Shot](<docs/images/missing.png>)",
    "[outer [ref][]](a`b) `![Shot](<docs/images/missing.png>)",
    "[outer [ref]](a`b) `![Shot](<docs/images/missing.png>)",
], ids=["full", "collapsed", "shortcut"])
def test_reference_style_inner_link_deactivates_enclosing_link_opener(make_ctx, tmp_path, brand, usage):
    readmelint._active_openers.cache_clear()
    fails = _usage_fails(make_ctx, tmp_path, brand, usage + REF_DEFINITION)
    assert MISSING in fails, fails


# GFM render pending (not yet executed). Controls that must NOT report the image: an image opener inside a reference
# link keeps its own closer active, and an unresolved reference label completes no link, so the enclosing `](a`b)` is
# a link and the code span hides the image.
@pytest.mark.parametrize("usage", [
    "![alt [x][ref]](a`b) `![Shot](<docs/images/missing.png>)`",
    "[outer [x][nope]](a`b) `![Shot](<docs/images/missing.png>)`",
], ids=["image-opener-control", "unresolved-label-control"])
def test_reference_style_controls_do_not_report_the_image(make_ctx, tmp_path, brand, usage):
    readmelint._active_openers.cache_clear()
    fails = _usage_fails(make_ctx, tmp_path, brand, usage + REF_DEFINITION)
    assert MISSING not in fails, fails


# Direct opener state for the reference-style nested link (derived from the CommonMark rule that links may not contain
# links, matching gfm-e90-inner_full_reference.html): the inner closer stays active and the enclosing link closer is
# inactive.
def test_reference_inner_link_closer_active_and_enclosing_link_closer_inactive():
    readmelint._active_openers.cache_clear()
    text = "[outer [x][ref]](z)" + REF_DEFINITION
    active = readmelint._active_openers(text)
    assert text.index("]") in active
    assert text.index("]](z)") + 1 not in active


# GFM render pending (not yet executed). Adjacent links `[a](b)[c](d)` both complete, and a code span after them hides
# the image. An unmatched `[c` is closed by `](d`e)` (a valid link whose destination holds a backtick), so the code span
# after it still hides the image. Direct `_has_link_opener` assertions pin the closers.
@pytest.mark.parametrize("body,expect_missing", [
    ("[a](b)[c](d) `![Shot](<docs/images/missing.png>)`", False),
    ("[a](b)[c](d`e) `![Shot](<docs/images/missing.png>)`", False),
    ("[open text] more ![Shot](<docs/images/missing.png>)", True),  # unmatched bracket pair, no link: image renders
], ids=["adjacent-links", "adjacent-link-with-backtick-destination", "unmatched-bracket-pair"])
def test_adjacent_links_and_unmatched_brackets(make_ctx, tmp_path, brand, body, expect_missing):
    readmelint._active_openers.cache_clear()
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    if expect_missing:
        assert MISSING in fails, fails
    else:
        assert MISSING not in fails, fails


def test_adjacent_links_direct_openers():
    readmelint._active_openers.cache_clear()
    text = "[a](b)[c](d`e) `![Shot](<docs/images/missing.png>)`"
    assert readmelint._has_link_opener(text, text.index("]")) is True  # closes [a
    assert readmelint._has_link_opener(text, text.index("](d")) is True  # closes [c


# Deterministic counter (not wall-clock): reference-link work per character must not grow with the nesting depth k.
# The `[ref]: x` definition is appended so the reference labels are resolvable in the same text.
def test_reference_link_work_is_linear():
    def ratio(k):
        text = "[a " * k + "[b][ref]" + "](d) " * k + "\n\n[ref]: x"
        readmelint._active_openers.cache_clear()
        readmelint._OPENER_STEPS = 0
        readmelint._active_openers(text)
        return readmelint._OPENER_STEPS / len(text)

    ratios = [ratio(k) for k in (100, 200, 400)]
    assert max(ratios) <= 1.5 * min(ratios), ratios


# The nine cases of t7-adjudication-reference-links-e90d748.md. Each has a live GitHub GFM render in the
# showcase-orchestration 20261031 directory (gfm-e90-<id>.html): the eight True cases render one real image (so R7 must
# report it missing) and the undefined-reference control renders none (an unresolved reference is plain text, not a link,
# so it must NOT deactivate the enclosing opener).
_IMG = "`![Shot](<docs/images/missing.png>)`"
E90_CASES = [
    ("inner_full_reference", "[outer [inner][ref]](a`b) " + _IMG + "\n\n[ref]: ok", True),
    ("inner_collapsed_reference", "[outer [inner][]](a`b) " + _IMG + "\n\n[inner]: ok", True),
    ("inner_shortcut_reference", "[outer [ref]](a`b) " + _IMG + "\n\n[ref]: ok", True),
    ("undefined_reference_control", "[outer [inner][ref]](a`b) " + _IMG, False),
    ("raw_script_opener", "<script>\n[open\n</script>\n](a`b) " + _IMG, True),
    ("raw_style_opener", "<style>\n[open\n</style>\n](a`b) " + _IMG, True),
    ("raw_textarea_opener", "<textarea>\n[open\n</textarea>\n](a`b) " + _IMG, True),
    ("adjacent_links_opener", "[a](b)[c](d) ](a`b) " + _IMG, True),
    ("raw_type7_opener", "<custom>\n[open\n</custom>\n\n](a`b) " + _IMG, True),
]


@pytest.mark.parametrize("body,expect_missing", [(b, m) for _, b, m in E90_CASES], ids=[c[0] for c in E90_CASES])
def test_e90_gfm_oracle_cases(make_ctx, tmp_path, brand, body, expect_missing):
    readmelint._active_openers.cache_clear()
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    assert (MISSING in fails) is expect_missing, fails


# --- r4: list-continuation fences, setext boundaries, failed-destination work (#7) ---------------------------------------
# GFM oracle: gfm-77004-list_continuation_fence.html, gfm-77004-setext_boundary.html (each renders 1 image) and
# gfm-77004-list_fence_inert_control.html (0 images). Adjudication: t7-adjudication-blocks-failed-target-77004e6.md.
@pytest.mark.parametrize("snippet", [
    "- Example\n\n  ```text\n  code\n\n![Shot](<docs/images/missing.png>)",
    "1. x\n\n   ```text\n   code\n\n![Shot](<docs/images/missing.png>)",
    "[open\n--\n](a`b) `![Shot](<docs/images/missing.png>)`",
    "[open\n==\n](a`b) `![Shot](<docs/images/missing.png>)`",
], ids=["list-fence", "ordered-list-fence", "setext-dashes", "setext-equals"])
def test_r4_missing_image_is_reported(make_ctx, tmp_path, brand, snippet):
    assert MISSING in _usage_fails(make_ctx, tmp_path, brand, snippet)


def test_r4_list_fence_inert_control_reports_nothing(make_ctx, tmp_path, brand):
    snippet = "- Example\n\n  ```text\n  ![Shot](<docs/images/missing.png>)\n  ```"
    assert MISSING not in _usage_fails(make_ctx, tmp_path, brand, snippet)


@pytest.mark.parametrize("underline", ["--", "=="])
def test_r4_setext_underline_leaves_no_opener_for_the_orphan_bracket(underline):
    text = f"[open\n{underline}\n](a`b) `![Shot](<docs/images/missing.png>)`"
    readmelint._active_openers.cache_clear()
    assert text.index("]") not in readmelint._active_openers(text)


def test_r4_dashes_after_a_blank_line_are_not_a_setext_underline():
    text = "[open\n\n--\n[x](y)"
    assert readmelint._block_boundary(text, text.index("\n--"), ()) is False


def _failed_destination_steps(n, unit):
    text = unit * n
    readmelint._active_openers.cache_clear()
    readmelint._outside_code.cache_clear()
    readmelint._title_ends.cache_clear()
    readmelint._DEST_STEPS = 0
    readmelint._active_openers(text)
    openers = readmelint._DEST_STEPS
    readmelint._active_openers.cache_clear()
    readmelint._outside_code.cache_clear()
    readmelint._DEST_STEPS = 0
    readmelint._outside_code(text)
    return openers, readmelint._DEST_STEPS


@pytest.mark.parametrize("unit", ["[x](", "[x](a ("], ids=["unmatched-destination", "title-scan"])
def test_r4_failed_destination_work_per_candidate_is_constant(unit):
    steps = {n: _failed_destination_steps(n, unit) for n in (50, 100, 200, 400)}
    for index in (0, 1):  # _active_openers, then _outside_code (the next_destination path)
        assert steps[400][index] <= 2.5 * steps[200][index], steps
        assert steps[200][index] <= 2.5 * steps[100][index], steps
        assert steps[400][index] <= 300 * 400, steps  # a bounded number of reads per candidate (nesting limit 32)


def test_r4_opener_steps_stay_linear_for_unmatched_candidates():
    seen = []
    for n in (50, 100, 200):
        readmelint._active_openers.cache_clear()
        readmelint._outside_code.cache_clear()
        readmelint._OPENER_STEPS = 0
        readmelint._outside_code("[x](" * n + "x")
        seen.append(readmelint._OPENER_STEPS)
    assert seen == [251, 501, 1001], seen


def test_r4_destination_nesting_deeper_than_32_is_no_link():
    def target(depth):
        text = "x(" + "(" * depth + "a" + ")" * depth + ")"
        return readmelint._inline_image_target(text, 1)

    assert target(32) is not None  # 32 nested parentheses still form a destination
    assert target(33) is None  # 33 is beyond CommonMark's nesting limit: not a link


# --- r3 (8783e0e): nested containers, invalid reference labels, list-continuation HTML (#7) -------------------------------
# GFM oracle: gfm-878-nested-containers-summary.json (an image renders in each failing input; none in each control).
# Adjudication: t7-adjudication-nested-containers-8783.md.
_HTML_IMG = '<img alt="Shot" src="docs/images/missing.png">'
NESTED_CASES = [
    # 1. an unescaped opening bracket makes the label invalid, so the line is ordinary Markdown and the image renders
    ("invalid_label", "Intro.\n\n[bad[label]: ![Shot](docs/images/missing.png)", True),
    ("escaped_bracket_control", "Intro.\n\n[ok\\[label]: ![Shot](docs/images/missing.png)", False),
    # 2. raw HTML indented into a list item: the item's four spaces are container syntax, the backticks are literal
    ("item_html_backticks", "- Example\n\n    <div>\n    One ` character.\n    " + _HTML_IMG + "\n    Another ` character.\n    </div>", True),
    ("item_html_real_code_control", "- Example\n\n    <div>\n    One `code` here.\n    " + _HTML_IMG + "\n    </div>", True),
    ("item_inline_code_control", "- Example\n\n  Text `" + _HTML_IMG + "` more", False),
    ("item_fenced_control", "- Example\n\n  ```html\n  " + _HTML_IMG + "\n  ```", False),
    # 3. a fence opened on a list continuation line inside a quote ends where the line dedents out of the quote item
    ("quoted_list_fence", "> - Example\n>\n>   ```text\n>   code\n\n> ![Shot](docs/images/missing.png)", True),
    ("quoted_list_fence_quote_blank", "> - Example\n>\n>   ```text\n>   code\n>\n> ![Shot](docs/images/missing.png)", True),
    ("quoted_list_closed_fence_control", "> - Example\n>\n>   ```text\n>   ![Shot](docs/images/missing.png)\n>   ```", False),
]


@pytest.mark.parametrize("body,expect_missing", [(b, m) for _, b, m in NESTED_CASES], ids=[c[0] for c in NESTED_CASES])
def test_r3_nested_container_cases(make_ctx, tmp_path, brand, body, expect_missing):
    readmelint._active_openers.cache_clear()
    fails = _usage_fails(make_ctx, tmp_path, brand, body)
    assert (MISSING in fails) is expect_missing, fails
