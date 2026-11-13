"""HTML attribute brackets are literal inside rendered image descriptions."""
import json

import pytest

from ctshowcase import readmelint
from conftest import run_cli


def images(source):
    return readmelint._images(readmelint._outside_code(source), source)


@pytest.mark.parametrize('attribute', ['[', ']', '[[', ']]', '[]', '![phantom](hidden.png)'])
@pytest.mark.parametrize('quote', ['"', "'"])
@pytest.mark.parametrize('form', ['inline', 'reference'])
def test_complete_html_tag_cannot_change_description_bracket_pairing(attribute, quote, form):
    alt = f'Shot <span title={quote}{attribute}{quote}>'
    source = f'![{alt}]' + ('(missing.png)' if form == 'inline' else '[shot]\n\n[shot]: missing.png\n')
    assert images(source) == [(alt, 'missing.png')]


@pytest.mark.parametrize('tag', ['<span title=[>', '<span title=]>', '<span data-note="[" />'])
def test_valid_unquoted_and_self_closing_tags_are_literals(tag):
    assert images(f'![Shot {tag}](missing.png)') == [(f'Shot {tag}', 'missing.png')]


@pytest.mark.parametrize('tag', ['<span title="["', r'\<span title="[">', '<span title=`[>'])
def test_malformed_or_escaped_tags_keep_their_real_bracket_openers(tag):
    assert images(f'![Shot {tag}](missing.png)') == []
    assert images(f'![Shot {tag}](outer.png) ![Visible](missing.png)') == [('Visible', 'missing.png')]


def test_ordinary_nested_brackets_still_balance():
    assert images('![Shot [detail]](missing.png)') == [('Shot [detail]', 'missing.png')]
    assert images('![Shot [detail](missing.png)') == []


@pytest.mark.parametrize('body', [
    '`![Shot <span title="[">](hidden.png)`',
    'inline <!-- ![Shot <span title="[">](hidden.png) -->',
    '<span title="![Shot [x]](hidden.png)">',
])
def test_literal_constructs_do_not_expose_attribute_images(body):
    assert images(body + ' ![Visible](missing.png)') == [('Visible', 'missing.png')]


@pytest.mark.parametrize('attribute', ['[', ']'])
def test_production_lint_checks_local_file_and_palette_badges_inside_html_descriptions(tmp_path, attribute):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'license': 'MIT',
                                'description': 'Run the synthetic probe.', 'files': ['README.md']}), encoding='utf-8')
    alt = f'Shot <span title="{attribute}">'
    badges = '\n'.join(f'![{alt}](https://img.shields.io/badge/{value})' for value in
                       ['type-community-005ADD', 'license-MIT-64748B'])
    path = tmp_path / 'README.md'
    path.write_text('# Probe\n\n<img src="banner.png" alt="Probe">\n\n' + badges +
                    f'\n\n![{alt}](docs/images/missing.png)\n\n---\n', encoding='utf-8')
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1
    failures = json.loads(result.stdout)['fails']
    assert 'R7 local image does not resolve: docs/images/missing.png' in failures
    assert not any('header badges required' in failure for failure in failures)


def test_full_reference_label_keeps_raw_html_attribute_bracket_semantics():
    # The second label is raw lexical text, unlike rendered description text.
    source = '![Shot][<span title="[">]\n\n[Shot]: visible.png\n'
    assert images(source) == [('Shot', 'visible.png')]
    source = '![Shot][<span title="]">]\n\n[Shot]: visible.png\n'
    assert images(source) == []
