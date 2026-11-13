"""Reference labels contain literal HTML-looking text, not parsed inline markup."""
import pytest

from ctshowcase import readme, readmelint


@pytest.mark.parametrize("label", ["<!--x-->", "before<!--x-->after", "<!--never closed", "<!--x-->`literal`"])
def test_comment_syntax_in_reference_labels_resolves_as_literal_text(label):
    text = f"![Shot][{label}]\n\n[{label}]: docs/images/missing.png\n"
    assert readmelint._images(readmelint._outside_code(text), text) == [("Shot", "docs/images/missing.png")]


def test_comment_label_license_badge_satisfies_variant_j(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, repo=".github", files=["README.md"], license="MIT")
    text = readme.scaffold(ctx, "")
    # Replace the real generated license image with equivalent reference syntax;
    # this tests badge recognition through the public README lint entry point.
    import re
    text, count = re.subn(r"!\[License MIT\]\([^\n]+?\)", "![License][<!--x-->]", text)
    assert count == 1
    text += "\n[<!--x-->]: https://img.shields.io/badge/license-MIT-64748B\n"
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    assert not any("badge" in failure.lower() for failure in readmelint.lint(ctx, path)["fails"])


@pytest.mark.parametrize("text", [
    "<!--\n[shot]: docs/images/missing.png\n-->\n\n![Shot][shot]\n",
    "<!-- [shot]: docs/images/missing.png -->\n\n![Shot][shot]\n",
    "text\n[<!--x-->]: docs/images/missing.png\n\n![Shot][<!--x-->]\n",
    "```markdown\n[<!--x-->]: docs/images/missing.png\n```\n\n![Shot][<!--x-->]\n",
])
def test_actual_comments_code_and_paragraph_continuations_do_not_define_labels(text):
    assert readmelint._images(readmelint._outside_code(text), text) == []
