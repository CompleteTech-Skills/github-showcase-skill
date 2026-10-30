"""Badge counts follow rendered reference images, not unused URL definitions."""
import pytest

from ctshowcase import readme, readmelint

URL = "https://github.com/Northwind-Trading-Co/sample-library/actions/workflows/ci.yml/badge.svg"


def lint_reference(make_ctx, tmp_path, usage, definitions):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "docs/images").mkdir(parents=True)
    (tmp_path / "docs/images/banner.png").write_bytes(b"banner")
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
