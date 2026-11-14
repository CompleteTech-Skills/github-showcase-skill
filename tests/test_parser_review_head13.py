"""Regressions for reference boundaries and bounded parser materialization."""
import pytest

from ctshowcase import mdcode
from test_reference_label_whitespace import cli_fails, MISSING


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
def test_multiline_reference_offsets_resolve_both_images_cli(tmp_path, ending):
    source = ("> ![First][aaa\n> bbb]\n\n> ![Second][ccc\n> ddd]\n\n"
              "[aaa bbb]: good.png\n[ccc ddd]: docs/images/missing.png\n")
    assert MISSING in cli_fails(tmp_path, source, ending)


@pytest.mark.parametrize("title", ['"bad" extra', "(bad) extra", "'bad' extra"])
def test_invalid_optional_title_keeps_definition_boundary_cli(tmp_path, title):
    source = f'[a]: /url\n    {title}\n    `\n![Shot](docs/images/missing.png)\n`\n'
    assert MISSING in cli_fails(tmp_path, source, "\n")


def test_nested_continuations_materialize_linear_amount():
    for depth in (500, 1000):
        source = '- ' * depth + 'x\n' + '  ' * depth + 'y\n'
        mdcode._layout.cache_clear()
        mdcode.WORK.clear()
        mdcode._layout(source)
        assert mdcode.WORK['container_materialized_chars'] <= 8 * len(source)


def test_unresolved_nested_image_alt_is_not_copied():
    source = '![' * 2000 + 'x' + ']' * 2000
    mdcode.WORK.clear()
    assert mdcode._markdown_images(source, source) == []
    assert mdcode.WORK['image_alt_materialized_chars'] == 0


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
@pytest.mark.parametrize("opener", ['"', "'", "("])
@pytest.mark.parametrize("prefix", ["", "> ", "- "])
def test_unterminated_optional_title_falls_back_cli(tmp_path, ending, opener, prefix):
    continuation = "  " if prefix == "- " else prefix
    source = (f'{prefix}[a]: /url\n{continuation}    {opener}unfinished\n'
              f'{continuation}    `\n{continuation}![Shot](docs/images/missing.png)\n'
              f'{continuation}`\n')
    assert MISSING in cli_fails(tmp_path, source, ending)


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
@pytest.mark.parametrize("opener,closer", [('"', '"'), ("'", "'"), ("(", ")")])
def test_completed_multiline_optional_title_hides_image_cli(tmp_path, ending, opener, closer):
    source = (f'[a]: /url\n    {opener}title\n![Shot](docs/images/missing.png)\n'
              f'end{closer}\n\n![Other](docs/images/missing.png)\n')
    fails = cli_fails(tmp_path, source, ending)
    assert sum(MISSING in fail for fail in fails) == 1


def test_unterminated_title_does_not_cross_quote_boundary_cli(tmp_path):
    source = '> [a]: /url\n> "unfinished\n# boundary\n![Shot](docs/images/missing.png)\n'
    assert MISSING in cli_fails(tmp_path, source, '\n')
