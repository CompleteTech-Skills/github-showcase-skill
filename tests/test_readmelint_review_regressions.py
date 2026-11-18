"""Independent-review regressions for image references and malformed input."""
import pytest

from ctshowcase import readme, readmelint
from test_reference_badge_count import lint_reference


@pytest.mark.parametrize("nested", [
    '[docs](https://example.test/[)',
    '[docs](https://example.test/])',
    '[docs](https://example.test "[")',
    "[docs](https://example.test ']')",
])
def test_nested_link_destination_brackets_do_not_hide_image(make_ctx, tmp_path, nested):
    target = "https://img.shields.io/badge/example-bad-FF0000"
    alt = f"Shot {nested}"
    text = f"![{alt}]({target})"
    assert readmelint._images(readmelint._outside_code(text), text) == [(alt, target)]
    failures = lint_reference(make_ctx, tmp_path, text, "")["fails"]
    assert "R7 off-palette badge colour FF0000" in failures
    assert "R7 2-4 header badges required (found 1)" not in failures


def test_nested_link_destinations_keep_bracket_work_bounded():
    counts = []
    for count in (100, 200, 400):
        text = ('![Shot [docs](https://example.test "[")](image.png) ' * count)
        readmelint._bracket_pairs.cache_clear()
        readmelint._BRACKET_STEPS = 0
        assert len(readmelint._images(readmelint._outside_code(text), text)) == count
        counts.append(readmelint._BRACKET_STEPS)
    assert counts[2] <= counts[1] * 2.1


@pytest.mark.parametrize("first,second", [(r"a\!", "a!"), ("a&amp;", "a&"), ("a&#33;", "a!")])
def test_distinct_reference_labels_do_not_alias(first, second):
    text = f"![Shot][{second}]\n\n[{first}]: https://example.test/ok.png\n[{second}]: docs/images/missing.png\n"
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "docs/images/missing.png")]
    # The literal escaped/entity spelling remains independently addressable.
    text = text.replace(f"![Shot][{second}]", f"![Shot][{first}]")
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "https://example.test/ok.png")]


def test_reference_collision_cannot_hide_a_missing_file(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, description="Run the Northwind customer support email triage agent from the command line.")
    text = readme.scaffold(ctx, "")
    text += "\n![Shot][a!]\n\n[a\\!]: https://example.test/ok.png\n[a!]: docs/images/missing.png\n"
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    assert "R7 local image does not resolve: docs/images/missing.png" in readmelint.lint(ctx, path)["fails"]


def test_reference_labels_still_fold_case_and_collapse_whitespace():
    text = "![Shot][  MiXeD\n label ]\n\n[mixed label]: <docs/images/a&amp;b.png>\n"
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "docs/images/a&b.png")]


@pytest.mark.parametrize("tail", ["", "![Shot](docs/images/missing.png)", "\n\n![Shot](docs/images/missing.png)"])
def test_unmatched_image_openers_have_bounded_work_and_keep_nested_images(tail):
    counts = []
    for count in (1000, 2000, 4000):
        text = "![" * count + tail
        readmelint._bracket_pairs.cache_clear()
        readmelint._BRACKET_STEPS = 0
        images = readmelint._images(readmelint._outside_code(text), text)
        expected = [("Shot", "docs/images/missing.png")] if tail else []
        assert images == expected
        assert readmelint._BRACKET_STEPS <= len(text) * 3
        counts.append(readmelint._BRACKET_STEPS)
    assert counts[2] <= counts[1] * 2.1


@pytest.mark.parametrize("link_text", ["Docs", "![Visible](visible.png)"])
def test_html_image_in_resolved_full_reference_label_is_literal(link_text):
    label = '<img src="missing.png" alt="Shot">'
    text = f"[{link_text}][{label}]\n\n[{label}]: /docs\n"
    expected = [("Visible", "visible.png")] if link_text.startswith("![") else []
    assert readmelint._images(readmelint._outside_code(text), text) == expected


def test_html_image_in_unresolved_full_reference_label_remains_visible():
    text = '[Docs][<img src="missing.png" alt="Shot">]'
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "missing.png")]


def test_html_image_in_full_reference_link_text_remains_visible():
    text = '[<img src="missing.png" alt="Shot">][Docs]\n\n[Docs]: /docs\n'
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "missing.png")]


@pytest.mark.parametrize("resolved", [False, True])
def test_reference_label_html_only_reports_a_rendered_missing_image(make_ctx, tmp_path, resolved):
    ctx = make_ctx(repo_dir=tmp_path, description="Run the Northwind customer support email triage agent from the command line.")
    label = '<img src="missing.png" alt="Shot">'
    text = readme.scaffold(ctx, "") + f"\n[Docs][{label}]\n"
    if resolved:
        text += f"\n[{label}]: /docs\n"
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    failures = readmelint.lint(ctx, path)["fails"]
    assert ("R7 local image does not resolve: missing.png" in failures) is not resolved
