"""Every inline raw-HTML form binds before image-description brackets."""
import json

import pytest

from ctshowcase import mdcode, readmelint
from conftest import run_cli


def images(source):
    return readmelint._images(readmelint._outside_code(source), source)


RAW = ['<?p {} ?>', '<!A {} >', '<![CDATA[ {} ]]>', '<!-- {} -->', '<span title="{}">']


@pytest.mark.parametrize('template', RAW)
@pytest.mark.parametrize('body', ['[', ']', '[[', ']]', '[]', '![Phantom](hidden.png)'])
@pytest.mark.parametrize('form', ['inline', 'reference'])
def test_all_raw_html_forms_are_literal_inside_image_descriptions(template, body, form):
    alt = 'Shot ' + template.format(body)
    source = f'![{alt}]' + ('(visible.png)' if form == 'inline' else '[shot]\n\n[shot]: visible.png\n')
    assert images(source) == [(alt, 'visible.png')]


@pytest.mark.parametrize('template', RAW[:3])
def test_images_and_html_images_inside_raw_html_are_not_rendered(template):
    raw = template.format('![Phantom](hidden.png) <img src="hidden-too.png" alt="Hidden">')
    assert images('text ' + raw + ' ![Visible](visible.png)') == [('Visible', 'visible.png')]


@pytest.mark.parametrize('template', RAW[:3])
def test_code_opened_before_raw_html_keeps_its_raw_closing_backtick(template):
    source = '`before ' + template.format('`') + ' ![Visible](visible.png)'
    assert images(source) == [('Visible', 'visible.png')]


@pytest.mark.parametrize('template', RAW[:3])
def test_backtick_inside_raw_html_cannot_consume_a_later_real_code_opener(template):
    source = 'text ' + template.format('`') + ' `![Hidden](hidden.png)` ![Visible](visible.png)'
    assert images(source) == [('Visible', 'visible.png')]


@pytest.mark.parametrize('raw', ['<?p [ >', '<!3 [ >', '<!a [ >', '<!A[>', '<![CDATA[ [ >'])
def test_malformed_raw_html_keeps_its_real_brackets(raw):
    assert images(f'![Shot {raw}](hidden.png) ![Visible](visible.png)') == [('Visible', 'visible.png')]


@pytest.mark.parametrize('template', RAW[:3])
def test_escaped_raw_html_opener_keeps_its_real_brackets(template):
    raw = '\\' + template.format('[')
    actual = images(f'![Shot {raw}](hidden.png) ![Visible](visible.png)')
    # Escaping CDATA exposes its internal ![CDATA[ as an ordinary image opener.
    assert [src for _, src in actual] == (['hidden.png', 'visible.png'] if 'CDATA' in template else ['visible.png'])


@pytest.mark.parametrize('template', RAW[:3])
def test_raw_html_cannot_cross_a_paragraph_or_container_boundary(template):
    for body in ['[\n\n', '[\n> ']:
        source = 'text ' + template.format(body + '![Visible](visible.png)')
        assert images(source) == [('Visible', 'visible.png')]


@pytest.mark.parametrize('template', RAW[:3])
def test_full_reference_labels_still_use_raw_lexical_brackets(template):
    invalid = template.format('[')
    assert images(f'![Shot][{invalid}]\n\n[Shot]: visible.png\n') == [('Shot', 'visible.png')]
    # A ] inside the second label closes that raw label; it is not HTML here.
    unresolved = template.format(']')
    # CDATA starts with a nested [ already, so either spelling is invalid and
    # leaves the shortcut available instead of forming an unresolved full label.
    assert images(f'![Shot][{unresolved}]\n\n[Shot]: visible.png\n') == ([('Shot', 'visible.png')] if 'CDATA' in template else [])


@pytest.mark.parametrize('template', RAW[:2])
def test_resolved_full_reference_labels_keep_literal_backticks(template):
    label = template.format('`')
    source = f'![Shot][{label}]\n\n[{label}]: visible.png\n\n![Visible](second.png)\n'
    assert images(source) == [('Shot', 'visible.png'), ('Visible', 'second.png')]


@pytest.mark.parametrize('opener', ['<?p', '<![CDATA['])
def test_unterminated_raw_block_stops_with_its_container(opener):
    source = '> ' + opener + '\n> <img src="hidden.png" alt="Hidden">\n\n![Visible](visible.png)'
    assert images(source) == [('Visible', 'visible.png')]


@pytest.mark.parametrize('template', RAW[:3])
def test_production_lint_keeps_missing_file_checks_and_authored_badge_counts(tmp_path, template):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'license': 'MIT',
                                'description': 'Run the synthetic probe.', 'files': ['README.md']}), encoding='utf-8')
    alt = 'Shot ' + template.format('[')
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


def test_rejected_raw_html_candidates_do_not_rescan_distant_closers():
    counts = []
    for n in [100, 400]:
        source = ('text <? [\n\n' * n) + '?>\n\n![Visible](visible.png)'
        mdcode.WORK.clear()
        assert images(source) == [('Visible', 'visible.png')]
        counts.append(mdcode.WORK['raw_html_scan_chars'])
    assert counts[0] > 0
    assert counts[1] <= 4.1 * counts[0]
