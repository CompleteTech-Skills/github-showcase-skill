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
