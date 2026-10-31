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
