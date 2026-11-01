"""Badge counts follow rendered reference images, not unused URL definitions."""
import pytest

from ctshowcase import readme, readmelint

URL = "https://github.com/Northwind-Trading-Co/sample-library/actions/workflows/ci.yml/badge.svg"


def lint_reference(make_ctx, tmp_path, usage, definitions, files=None):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "docs/images").mkdir(parents=True)
    (tmp_path / "docs/images/banner.png").write_bytes(b"banner")
    for name in files or []:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"image")
    ctx = make_ctx(repo_dir=tmp_path, repo="sample-library", language=None, license=None)
    ctx.det.update(type="library", variant="C", category="Library")
    text = readme.scaffold(ctx)
    original = next(m.group(2) for m in readme.MARK.finditer(text) if m.group(1) == "badges")
    type_badge = next(line for line in original.splitlines() if "badge/type-" in line)
    text = text.replace(original, type_badge + "\n" + usage)
    # References may be defined outside the header, before the required final footer.
    text = text.replace("<!-- showcase:footer:start -->", definitions + "\n\n<!-- showcase:footer:start -->")
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    return readmelint.lint(ctx, path)


@pytest.mark.parametrize("usage,definitions", [
    ("![CI][ci-status]", f"[ci-status]: {URL}"),
    ("![CI][]", f"[CI]: <{URL}>"),
    ("![CI]", f'[ci]: {URL} "Build status"'),
    ("![CI][  Build STATUS ]", f"[build status]:\n  {URL}"),
])
def test_reference_ci_images_count(make_ctx, tmp_path, usage, definitions):
    result = lint_reference(make_ctx, tmp_path, usage, definitions)
    assert not any("badge" in failure for failure in result["fails"]), result


@pytest.mark.parametrize("usage,definitions", [
    ("[CI][ci-status]", f"[ci-status]: {URL}"),
    (r"\![CI][ci-status]", f"[ci-status]: {URL}"),
    ("`![CI][ci-status]`", f"[ci-status]: {URL}"),
    ("![CI][missing]", f"[ci-status]: {URL}"),
    ("![CI][ci-status]", f"```markdown\n[ci-status]: {URL}\n```"),
    ("![CI][ci-status]", f"[ci-status]: https://example.test/not-a-badge.png\n[ci-status]: {URL}"),
])
def test_non_images_and_unresolved_references_do_not_count(make_ctx, tmp_path, usage, definitions):
    result = lint_reference(make_ctx, tmp_path, usage, definitions)
    assert "R7 2-4 header badges required (found 1)" in result["fails"]


@pytest.mark.parametrize("count", [3, 4])
def test_each_rendered_reference_image_counts_once(make_ctx, tmp_path, count):
    result = lint_reference(make_ctx, tmp_path, "\n".join(["![CI][ci-status]"] * count), f"[ci-status]: {URL}")
    if count == 3:
        assert not any("badge" in failure for failure in result["fails"]), result
    else:
        assert "R7 2-4 header badges required (found 5)" in result["fails"]


def test_reference_images_still_require_alt_and_existing_local_files(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![][ci-status]",
                            "[ci-status]: docs/images/badges/missing.svg")
    assert any(failure.startswith("R7 image without alt text") for failure in result["fails"])
    assert "R7 local image does not resolve: docs/images/badges/missing.svg" in result["fails"]


@pytest.mark.parametrize("usage", [
    f'<img src={URL} alt="CI">',
    f'<img SRC="{URL}" alt="CI">',
    f"<IMG ALT='CI' SRC='{URL}'>",
    f'<img\nalt="CI > build"\nsrc="{URL}">',
    f'![CI [build]]({URL} "Build status")',
    f'![CI [build [latest]]]({URL})',
    "![CI [build]][ci]",
    "![CI [build [latest]]][ci]",
])
def test_valid_html_and_balanced_markdown_badges_count(make_ctx, tmp_path, usage):
    result = lint_reference(make_ctx, tmp_path, usage, f"[ci]: {URL}")
    assert not any("badge" in failure or "without alt" in failure for failure in result["fails"]), result


@pytest.mark.parametrize("usage", [
    f'&lt;img src="{URL}" alt="CI"&gt;',
    f'```html\n<img src={URL} alt="CI">\n```',
    '<img alt="CI"',
    f'<span title="![CI]({URL})">Build status</span>',
    f'\\![CI [build]]({URL})',
])
def test_nonrendered_html_and_markdown_badges_do_not_count(make_ctx, tmp_path, usage):
    result = lint_reference(make_ctx, tmp_path, usage, f"[ci]: {URL}")
    assert "R7 2-4 header badges required (found 1)" in result["fails"]


def test_unfinished_html_at_end_has_no_image():
    assert readmelint._images(f'<img src="{URL}"', "") == []


def test_angle_markdown_destination_missing_file_is_reported(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path,
                            '![CI][ci]\n![Screenshot](<docs/images/missing.png>)', f"[ci]: {URL}")
    assert "R7 local image does not resolve: docs/images/missing.png" in result["fails"]


def test_angle_markdown_destination_existing_file_passes(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path,
                            '![CI][ci]\n![Screenshot](<docs/images/good shot.png>)', f"[ci]: {URL}",
                            files=["docs/images/good shot.png"])
    assert result["fails"] == [], result


@pytest.mark.parametrize("attribute", ['alt="`showcase.py --help`"', "ALT='`showcase.py --help`'"])
def test_html_attribute_backticks_are_literal_text(make_ctx, tmp_path, attribute):
    result = lint_reference(make_ctx, tmp_path, f'<img src="{URL}" {attribute}>', "")
    assert result["fails"] == [], result


@pytest.mark.parametrize("usage", [
    '`![Screenshot](<docs/images/missing.png>)`',
    f'``<img src="{URL}" alt="`showcase.py --help`">``',
])
def test_angle_destinations_and_html_inside_code_are_excluded(make_ctx, tmp_path, usage):
    result = lint_reference(make_ctx, tmp_path, usage, "")
    assert "R7 2-4 header badges required (found 1)" in result["fails"]
    assert not any("local image" in failure or "without alt" in failure for failure in result["fails"])


@pytest.mark.parametrize("usage", [f"![CI](<{URL}>)", f"[![CI](<{URL}>)](https://example.test/ci)"])
def test_angle_bracketed_inline_destinations_count(make_ctx, tmp_path, usage):
    result = lint_reference(make_ctx, tmp_path, usage, "")
    assert not any("badge" in failure for failure in result["fails"]), result


COMMENT = "<!-- showcase:badges:generated sha256=" + "a" * 64 + " -->"


@pytest.mark.parametrize("document, alts", [
    (COMMENT + "\n![`gh` screenshot](docs/images/s.png)\n", ["`gh` screenshot"]),
    ("<!-- note -->\n" + " " * 20 + "\n![Logo](docs/images/logo.png)\n", ["Logo"]),
    ("<!--x-->\n![ ](docs/images/shot.png)\n", [" "]),
    ("<!-- " + "c" * 60 + " -->\nprose\n![ ](https://example.com/b.png)\n", [" "]),
])
def test_alt_text_is_read_at_source_offsets_after_html_comments(document, alts):
    assert len(readmelint._outside_code(document)) == len(document)
    assert [alt for alt, _ in readmelint._images(readmelint._outside_code(document), document)] == alts


def test_comment_before_blank_alt_image_is_still_flagged(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, COMMENT + "\n![ ](docs/images/shot.png)", "[ci]: " + URL,
                            files=["docs/images/shot.png"])
    assert any(f.startswith("R7 image without alt text") for f in result["fails"]), result


def test_reference_destination_unescapes_markdown_punctuation(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![Shot][shot]", r"[shot]: docs/images/shot\(1\).png",
                            files=["docs/images/shot(1).png"])
    assert not any("does not resolve" in f for f in result["fails"]), result


@pytest.mark.parametrize("document, alts", [
    ("Use `<br>` for breaks.\n\n![ ](docs/images/screenshot.png)\n", [" "]),
    ("Use `<br>`, `<hr>` or `<wbr>` tags.\n\n![Architecture](docs/x.png)\n" + "\n" * 60, ["Architecture"]),
    ("`<br>`\n![Logo](docs/images/logo.png)\n", ["Logo"]),
    ("Use `<img src=\"examples/a-very-long-example-file.png\" alt=\"example\">` here\n\n![ ](docs/images/shot.png)\n", [" "]),
    ("```html\n<p class=\"x\">\n<img src=\"a.png\">\n```\n\n![Valid alt](docs/images/v.png)\n", ["Valid alt"]),
    ("```html\n<img src=\"example.png\"\n```\n![Screenshot](docs/images/missing.png)\n"
     "<img src=\"docs/images/shot.png\" alt=\"Shot\">\n", ["Screenshot", "Shot"]),
])
def test_html_inside_code_keeps_source_offsets(document, alts):
    outside = readmelint._outside_code(document)
    assert len(outside) == len(document)
    assert [alt for alt, _ in readmelint._images(outside, document)] == alts


def test_failed_inline_destination_falls_back_to_shortcut_reference(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![CI](current build)", f"[CI]: {URL}")
    assert not any("badge" in failure for failure in result["fails"]), result


def test_fallback_reference_with_local_definition_is_checked_for_existence(make_ctx, tmp_path):
    missing = lint_reference(make_ctx, tmp_path, "![CI](current build)", "[CI]: docs/images/badges/ci.svg")
    assert "R7 local image does not resolve: docs/images/badges/ci.svg" in missing["fails"], missing
    assert not any("header badges" in failure for failure in missing["fails"]), missing


def test_fallback_reference_with_existing_local_definition_passes(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![CI](current build)", "[CI]: docs/images/badges/ci.svg",
                            files=["docs/images/badges/ci.svg"])
    assert not any("local image" in failure or "header badges" in failure for failure in result["fails"]), result


LIC = "[lic]: https://img.shields.io/badge/license-MIT-64748B"


def _comment_definition_doc(body):
    return f"{body}\n\n{LIC}\n\n<!-- note -->"


def _count(make_ctx, tmp_path, body):
    result = lint_reference(make_ctx, tmp_path, "![License][lic]", _comment_definition_doc(body))
    return result


def test_code_span_comment_opener_does_not_hide_a_later_definition(make_ctx, tmp_path):
    result = _count(make_ctx, tmp_path, "Use `<!--` to document comments.")
    assert not any("header badges" in failure for failure in result["fails"]), result


def test_real_comment_containing_a_definition_still_hides_it(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![License][lic]", f"<!--\n{LIC}\n-->")
    assert "R7 2-4 header badges required (found 1)" in result["fails"]


def test_escaped_comment_opener_does_not_start_a_comment(make_ctx, tmp_path):
    result = _count(make_ctx, tmp_path, r"Write \<!-- to open a comment.")
    assert not any("header badges" in failure for failure in result["fails"]), result


MISSING_FAIL = "R7 local image does not resolve: docs/images/missing.png"


def test_definition_backtick_does_not_hide_a_later_rendered_image(make_ctx, tmp_path):
    block = "[ref]: https://example.test/a`b\n[Guide](`help) ![Shot](docs/images/missing.png) `code`"
    result = lint_reference(make_ctx, tmp_path, "![CI][ci]", f"[ci]: {URL}\n\n{block}")
    assert MISSING_FAIL in result["fails"], result


def test_control_without_definition_backtick_still_reports_the_missing_image(make_ctx, tmp_path):
    block = "[ref]: https://example.test/ab\n[Guide](`help) ![Shot](docs/images/missing.png) `code`"
    result = lint_reference(make_ctx, tmp_path, "![CI][ci]", f"[ci]: {URL}\n\n{block}")
    assert MISSING_FAIL in result["fails"], result


def test_definition_backtick_before_an_existing_rendered_image_passes(make_ctx, tmp_path):
    block = "[ref]: https://example.test/a`b\n[Guide](`help) ![Shot](docs/images/shot.png) `code`"
    result = lint_reference(make_ctx, tmp_path, "![CI][ci]", f"[ci]: {URL}\n\n{block}",
                            files=["docs/images/shot.png"])
    assert not any("local image" in failure for failure in result["fails"]), result


def test_unbalanced_bare_destination_is_not_a_definition_and_its_image_renders(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![CI][ci]",
                            f"[ci]: {URL}\n\n[ref]: ![Shot](docs/images/missing.png))")
    assert MISSING_FAIL in result["fails"], result


def test_unbalanced_license_definition_does_not_count_as_a_badge(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![License][lic]", LIC + ")")
    assert "R7 2-4 header badges required (found 1)" in result["fails"], result


def test_balanced_parenthesised_image_destination_is_reported_missing(make_ctx, tmp_path):
    # valid_balanced_reference control from the 585191 adjudication: a balanced `(foo)` in a
    # bare reference destination is a live definition, so the rendered image is checked (R7).
    result = lint_reference(make_ctx, tmp_path, "![CI][ci]",
                            f"[ci]: {URL}\n\n![Shot][ref]\n\n[ref]: docs/images/missing(foo).png")
    assert "R7 local image does not resolve: docs/images/missing(foo).png" in result["fails"], result


def test_balanced_license_definition_counts_as_a_badge(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![License][lic]", LIC)
    assert not any("header badges" in failure for failure in result["fails"]), result


@pytest.mark.parametrize("line", [
    "[ref]: https://example.test/a_(b)",
    r"[ref]: https://example.test/a\(b",
    r"[ref]: https://example.test/a\)b",
])
def test_balanced_or_escaped_destinations_remain_live_definitions(line):
    document = f"{line}\n[next]: https://example.test/n\n"
    assert len(readmelint._definitions(document)) == 2
    assert len(readmelint._definition_spans(document)) == 2


# --- Round 6: a reference image cannot span a paragraph boundary ------------------------------------------------
LICENSE_URL = "https://img.shields.io/badge/license-MIT-64748B"


def test_alt_text_split_by_a_blank_line_is_not_an_image_and_is_not_counted(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![License\n\n][lic]", f"[lic]: {LICENSE_URL}")
    assert "R7 2-4 header badges required (found 1)" in result["fails"], result


def test_label_split_by_a_blank_line_is_not_counted_as_a_reference_label(make_ctx, tmp_path):
    result = lint_reference(make_ctx, tmp_path, "![License][li\n\nc]", f"[lic]: {LICENSE_URL}")
    assert "R7 2-4 header badges required (found 1)" in result["fails"], result


@pytest.mark.parametrize("usage,definitions", [
    ("![a\nb](" + LICENSE_URL + ")", ""),
    ("![License][lic]", f"[lic]: {LICENSE_URL}"),
    ("![License\nbadge][lic]", f"[lic]: {LICENSE_URL}"),
], ids=["soft-break-inline", "split-reference", "soft-break-reference"])
def test_controls_soft_break_and_normal_reference_still_count(make_ctx, tmp_path, usage, definitions):
    result = lint_reference(make_ctx, tmp_path, usage, definitions)
    assert not any("badge" in failure for failure in result["fails"]), result
