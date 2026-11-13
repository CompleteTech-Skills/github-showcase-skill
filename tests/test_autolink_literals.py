"""Autolinks are inline literals, with raw-code and reference-label precedence."""
import json

import pytest

from ctshowcase import mdcode, readme, readmelint
from conftest import run_cli

IMAGE = '![probe](missing.png)'


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


@pytest.mark.parametrize('scheme', ['http', 'https', 'aa', 'a1', 'a+', 'a.', 'a-', 'a' * 32])
@pytest.mark.parametrize('prefix', ['', '# Heading ', '> ', '- ', '> - '])
def test_uri_autolinks_do_not_render_nested_markdown_images(scheme, prefix):
    assert images(prefix + f'<{scheme}://example.test/{IMAGE}>') == []


@pytest.mark.parametrize('scheme', ['a', '1a', '+a', 'a' * 33])
def test_invalid_schemes_leave_real_images_visible(scheme):
    assert images(f'<{scheme}://example.test/{IMAGE}>') == [('probe', 'missing.png')]


@pytest.mark.parametrize('control', [chr(i) for i in range(1, 33)] + ['\x7f'])
def test_ascii_space_and_controls_invalidate_a_uri_autolink(control):
    assert images(f'<https://example.test/{control}{IMAGE}>') == [('probe', 'missing.png')]


@pytest.mark.parametrize('space', ['\u00a0', '\u2003'])
def test_non_ascii_spaces_are_permitted_in_uri_autolinks(space):
    assert images(f'<https://example.test/{space}{IMAGE}>') == []


@pytest.mark.parametrize('source', [
    rf'\<https://example.test/{IMAGE}>',
    f'<https://example.test/{IMAGE}',
    f'<https://example.test/<{IMAGE}>',
    f'<https://example.test/\n{IMAGE}>',
])
def test_escaped_unclosed_and_malformed_angles_do_not_hide_images(source):
    assert images(source) == [('probe', 'missing.png')]


def test_only_the_autolink_opener_can_be_escaped():
    assert images(rf'\\<https://example.test/{IMAGE}\> {IMAGE}') == [('probe', 'missing.png')]


@pytest.mark.parametrize('uri', ['https://example.test/`', 'mailto:x`@example.test', 'x`@example.test'])
def test_autolink_backticks_do_not_consume_the_following_code_span(uri):
    literal = f'<{uri}>'
    source = literal + f' `{IMAGE}` {IMAGE}'
    assert images(source) == [('probe', 'missing.png')]
    assert [source[a:b] for a, b in mdcode.inline_code_spans(source)] == [f'`{IMAGE}`']


@pytest.mark.parametrize('uri', ['https://example.test/`', 'x`@example.test'])
def test_code_opened_before_an_autolink_uses_its_raw_backtick_closer(uri):
    source = f'`<{uri}> {IMAGE}'
    assert images(source) == [('probe', 'missing.png')]
    assert mdcode.inline_code_spans(source) == ((0, source.index('`', 1) + 1),)


@pytest.mark.parametrize('suffix', [']', '[', '![nested](hidden.png)'])
def test_autolink_brackets_in_alt_text_do_not_close_or_unbalance_the_outer_image(suffix):
    alt = f'Outer <https://example.test/{suffix}>'
    assert images(f'![{alt}](visible.png)') == [(alt, 'visible.png')]


def test_autolink_in_link_text_does_not_expose_literal_titles():
    source = f'[Docs <https://example.test/>](url "{IMAGE}")'
    assert images(source) == []
    assert images('![Docs <https://example.test/>](visible.png)') == [('Docs <https://example.test/>', 'visible.png')]


def test_uri_content_cannot_supply_an_opener_for_a_later_destination():
    source = '<https://example.test/[>](url "<!--")\n\n[ref]: visible.png\n\n-->\n![Shot][ref]'
    assert images(source) == [('Shot', 'visible.png')]
    assert readmelint._inline_link_spans(source, ()) == ()


def test_reference_label_validity_uses_raw_nested_brackets():
    source = '![Shot][<https://example.test/![not](hidden.png)>]\n\n[Shot]: visible.png\n'
    assert images(source) == [('Shot', 'visible.png')]


@pytest.mark.parametrize('resolved', [False, True])
def test_reference_labels_keep_raw_backticks_and_autolink_spelling(resolved):
    label = '<https://example.test/`>'
    source = f'![Shot][{label}]\n\n'
    if resolved:
        source += f'[{label}]: visible.png\n'
    assert images(source) == ([('Shot', 'visible.png')] if resolved else [])


@pytest.mark.parametrize('opening,closing', [
    ('<span title="', '">'),
    ('inline <!-- ', ' -->'),
    ('[Docs](url "', '")'),
])
def test_an_earlier_literal_construct_wins_over_uri_contents(opening, closing):
    source = opening + '<https://example.test/`>' + closing + f' `{IMAGE}` {IMAGE}'
    assert images(source) == [('probe', 'missing.png')]


def test_html_attributes_and_images_keep_their_existing_behavior():
    source = f'<img src="visible.png" alt="<https://example.test/{IMAGE}>"> {IMAGE}'
    assert images(source) == [('probe', 'missing.png'), (f'<https://example.test/{IMAGE}>', 'visible.png')]


def test_literal_uri_backtick_cannot_expose_authored_code_markers():
    code = '`<!-- showcase:badges:start --> AUTHORED <!-- showcase:badges:end -->`'
    source = '<https://example.test/`> ' + code + '\n'
    assert mdcode.find_blocks(readme.MARK, source) == []
    assert readme._strip_markers(source)[0] == source


@pytest.mark.parametrize('body', [
    '<https://example.test/![](missing.png)>',
    '<https://example.test/![probe](https://img.shields.io/badge/type-probe-FF0000)>',
    '<https://example.test/![probe](https://img.shields.io/badge/type-probe-005ADD)>\n'
    '<https://example.test/![probe](https://img.shields.io/badge/license-MIT-64748B)>',
])
def test_production_lint_does_not_accept_literal_uri_badges_or_report_their_files(tmp_path, body):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': 'probe', 'license': 'MIT',
                                'description': 'Run the synthetic probe.'}), encoding='utf-8')
    path = tmp_path / 'README.md'
    path.write_text('# Probe\n\n<img src="banner.png" alt="Probe">\n\n' + body + '\n\n---\n', encoding='utf-8')
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1
    failures = json.loads(result.stdout)['fails']
    assert 'R7 2-4 header badges required (found 0)' in failures
    assert not any('missing.png' in failure or 'FF0000' in failure or 'empty alt' in failure for failure in failures)


def test_nul_preprocessing_preserves_uri_literal_and_source_offsets():
    source = '<https://example.test/\x00' + IMAGE + '> `' + IMAGE + '`'
    assert images(source) == []
    assert [source[a:b] for a, b in mdcode.inline_code_spans(source)] == [f'`{IMAGE}`']


def test_raw_uri_bracket_closes_a_reference_label_even_when_its_autolink_is_literal():
    source = '![Shot][<https://example.test/]>]\n\n[Shot]: visible.png\n'
    assert images(source) == []


def test_code_closing_inside_a_uri_does_not_activate_the_consumed_uri_opener():
    source = '`<https://example.test/` `' + IMAGE + '`> ' + IMAGE
    assert images(source) == [('probe', 'missing.png')]
    assert [source[a:b] for a, b in mdcode.inline_code_spans(source)] == [
        '`<https://example.test/`', f'`{IMAGE}`']


@pytest.mark.parametrize('address', [
    'a`@example.test', 'a.b+_`@example.test', 'a`@x', 'a`@a-b.example', 'a`@' + 'x' * 63,
])
def test_valid_email_autolinks_keep_backticks_literal(address):
    source = f'<{address}> `{IMAGE}` {IMAGE}'
    assert images(source) == [('probe', 'missing.png')]
    assert mdcode.autolink_candidates(source) == ((0, len(address) + 2),)


@pytest.mark.parametrize('address,count', [
    ('a\\`@example.test', 1), ('a`@-x.test', 2), ('a`@x-.test', 2), ('a`@x..test', 2),
    ('a`@' + 'x' * 64, 2), ('a`@example.test\x7f', 2), ('a`@example.test\t', 2),
    ('a`@example.test\n', 1), ('a`\x00@example.test', 2),
])
def test_malformed_email_angles_do_not_hide_real_images(address, count):
    source = f'<{address}> `{IMAGE}` {IMAGE}'
    assert mdcode.autolink_candidates(source) == ()
    # Escapes and block boundaries still govern the raw local-part backtick.
    assert images(source) == [('probe', 'missing.png')] * count


def test_production_header_refresh_preserves_code_markers_after_a_uri(tmp_path):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': 'probe', 'license': 'MIT',
                                'description': 'Run the synthetic probe.'}), encoding='utf-8')
    authored = '<https://example.test/`> `<!-- showcase:badges:start --> AUTHORED <!-- showcase:badges:end -->`'
    path = tmp_path / 'README.md'
    path.write_text('# Probe\n\n' + authored + '\n\n## Usage\n\nAuthored instructions.\n', encoding='utf-8')
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', 'header', '--write')
    assert result.returncode == 0, result.stdout + result.stderr
    refreshed = path.read_text(encoding='utf-8')
    assert authored in refreshed
    assert 'Authored instructions.' in refreshed
    assert 'readme-shrink' not in result.stdout
