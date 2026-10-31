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
