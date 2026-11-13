"""Independent-review regressions for image references and malformed input."""
import pytest

from ctshowcase import readme, readmelint


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
