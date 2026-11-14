"""Shared scanners recognize Markdown endings while retaining authored offsets."""
import json

import pytest

from ctshowcase import mdcode, readme, readmelint
from conftest import run_cli


ENDINGS = ['\n', '\r\n', '\r']
IMAGE = '![Shot](docs/images/missing.png)'
# Each expectation describes rendered images, rather than overall README validity.
CASES = [
    ('text ![Shot </span\n>](docs/images/missing.png)', False),
    (IMAGE, True),
    ('![Shot\ncontinued](docs/images/missing.png)', True),
    ('![Shot\n\ncontinued](docs/images/missing.png)', False),
    ('```md\n' + IMAGE + '\n```\n', False),
    ('> ```md\n> ' + IMAGE + '\n> ```\n', False),
    ('- > ```md\n  > ' + IMAGE + '\n  > ```\n', False),
    ('- x\n  ```md\n  hidden\n' + IMAGE, True),
    ('    ' + IMAGE + '\n', False),
    ('`code\n' + IMAGE + '`', False),
    ('`code\n# heading\n' + IMAGE + '`', True),
    ('<div>\n' + IMAGE + '\n\n', False),
    ('<div>\nhidden\n\n' + IMAGE, True),
    ('> <div>\n> hidden\n\n' + IMAGE, True),
    ('text <span title="soft\n' + IMAGE + '">', False),
    ('text <!-- soft\n' + IMAGE + ' -->', False),
    ('text <!-- blank\n\n' + IMAGE + ' -->', True),
    ('[docs](x "blank\n\n' + IMAGE + '")', True),
    ('[docs](x "soft\n' + IMAGE + '")', False),
    ('![Shot][shot]\n\n[shot]: docs/images/missing.png\n', True),
    ('![Shot][shot]\n\n[other]: x\n[shot]: docs/images/missing.png\n', True),
    ('![Shot][shot]\n\n> [shot]: docs/images/missing.png\n', True),
    ('![Shot][shot]\n\n- item\n  [shot]: docs/images/missing.png\n', False),
    ('![Shot][shot]\n\n- item\n\n  [shot]: docs/images/missing.png\n', True),
    ('![Shot][shot]\n\n```md\n[shot]: docs/images/missing.png\n```\n', False),
    ('![Shot][shot]\n\n<div>\n[shot]: docs/images/missing.png\n\n', False),
    ('![Shot][soft label]\n\n[soft\nlabel]: docs/images/missing.png\n', True),
    ('![Shot](<docs/images/missing\n.png>)', False),
]


@pytest.mark.parametrize('ending', ENDINGS)
@pytest.mark.parametrize('template, renders', CASES)
def test_shared_image_semantics(template, renders, ending):
    source = template.replace('\n', ending)
    found = readmelint._images(readmelint._outside_code(source), source)
    assert bool(found) is renders
    if renders:
        assert len(found) == 1
        assert found[0][1] == 'docs/images/missing.png'


@pytest.mark.parametrize('ending', ENDINGS)
@pytest.mark.parametrize('template, renders', CASES)
def test_actual_lint_reports_only_rendered_missing_images(tmp_path, ending, template, renders):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    authored = ('# Probe\n\n' + template).replace('\n', ending).encode()
    path.write_bytes(authored)
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1  # this minimal fixture intentionally lacks the required scaffold
    failures = json.loads(result.stdout)['fails']
    assert ('R7 local image does not resolve: docs/images/missing.png' in failures) is renders
    assert path.read_bytes() == authored


@pytest.mark.parametrize('ending', ENDINGS)
def test_reference_and_mask_offsets_index_original_source(ending):
    source = ('```md\n' + IMAGE + '\n```\n\n> [shot]: docs/images/missing.png\n\n![Shot][shot]\n').replace('\n', ending)
    for masked in (mdcode.masked(source), readmelint._outside_code(source), readmelint._definition_candidates(source)):
        assert len(masked) == len(source)
        assert [(i, c) for i, c in enumerate(masked) if c in '\r\n'] == [
            (i, c) for i, c in enumerate(source) if c in '\r\n']
    definition, = readmelint._definitions(source)
    assert source[definition.start():definition.end()] == '> [shot]: docs/images/missing.png'
    assert source[slice(*definition.span(3))] == 'docs/images/missing.png'
    image, = readmelint._markdown_images(readmelint._outside_code(source), source)
    assert source[image[2]:image[3]] == '![Shot][shot]'


def test_mixed_endings_and_unicode_separators_retain_source_lines():
    source = 'a\r\nb\rc\nd\v\f\x85\u2028\u2029'
    assert list(mdcode.source_lines(source)) == ['a\r\n', 'b\r', 'c\n', 'd\v\f\x85\u2028\u2029']
    assert readmelint._blank_line_starts('a\r\nb') == ()
    assert readmelint._blank_line_starts('a\r\n\rb') == (1,)
    assert readmelint._blank_line_starts('a\r\r\nb') == (1,)


@pytest.mark.parametrize('ending', ENDINGS)
def test_marker_search_preserves_authored_group_bytes_and_excludes_code(ending):
    marker = '<!-- showcase:nav:start -->\nAuthored text  \n<!-- showcase:nav:end -->'
    source = ('```md\n' + marker + '\n```\n\n' + marker + '\n').replace('\n', ending)
    found = mdcode.find_blocks(readme.MARK, source)
    assert len(found) == 1
    assert found[0].group() == marker.replace('\n', ending)
    assert source[found[0].start():found[0].end()].encode() == found[0].group().encode()
    # Replacing the real managed span leaves every other authored byte intact.
    prefix = source[:found[0].start()]
    assert prefix == ('```md\n' + marker + '\n```\n\n').replace('\n', ending)


@pytest.mark.parametrize('ending', ENDINGS)
def test_boundary_helper_advances_over_the_complete_line_ending(ending):
    source = 'text' + ending + '# heading'
    for index in range(4, 4 + len(ending)):
        assert readmelint._block_boundary(source, index, ()) is True


@pytest.mark.parametrize('ending', ENDINGS)
def test_rejected_comments_remain_bounded_across_line_endings(ending):
    counts = []
    for n in (100, 400):
        source = ('text <!--' + ending * 2) * n + '-->' + ending * 2 + IMAGE
        mdcode.WORK.clear()
        assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', 'docs/images/missing.png')]
        counts.append(mdcode.WORK['comment_scan_chars'])
        assert 0 < counts[-1] <= 9 * len(source)
    assert counts[1] <= 4.1 * counts[0]


@pytest.mark.parametrize('ending', ENDINGS)
def test_readme_plan_does_not_rewrite_authored_line_endings(tmp_path, ending):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    authored = ('# Probe\n\n```md\n<!-- showcase:nav:start -->\nExample\n'
                '<!-- showcase:nav:end -->\n```\n\nAuthored text  \n').replace('\n', ending).encode()
    path.write_bytes(authored)
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', 'header')
    assert result.returncode in (0, 1), result.stderr
    assert json.loads(result.stdout)['command'] == 'readme'
    assert path.read_bytes() == authored
