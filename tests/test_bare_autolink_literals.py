"""Published GFM URL extension and native cmark-gfm precedence controls."""
import json

import pytest

from ctshowcase import mdcode, readmelint
from conftest import run_cli

IMAGE = '![Shot](docs/images/missing.png)'
MISSING = 'R7 local image does not resolve: docs/images/missing.png'


def images(source):
    outside = readmelint._outside_code(source)
    assert len(outside) == len(source)
    assert [i for i, c in enumerate(outside) if c in '\r\n'] == [i for i, c in enumerate(source) if c in '\r\n']
    return readmelint._images(outside, source)


@pytest.mark.parametrize('url', ['http://example.org/', 'https://example.org/', 'www.example.org/',
                                'HTTP://example.org/', 'ftp://example.org/', 'https://a/',
                                'https://x_y.a.b/', 'https://例え.テスト/'])
@pytest.mark.parametrize('prefix', ['', 'text ', '# Heading ', '> ', '> - ', '- ', '>'])
def test_url_contents_render_no_images(url, prefix):
    assert images(prefix + url + IMAGE) == []


@pytest.mark.parametrize('prefix', ['', 'text ', '*', '_', '~', '(', '\t', '\v', '\f'])
def test_www_supported_boundaries(prefix):
    # VT/FF do not delimit native bare URLs, and do not enable www starts.
    expected = [('Shot', 'docs/images/missing.png')] if prefix in ('\v', '\f') else []
    assert images(prefix + 'www.example.org/' + IMAGE) == expected


@pytest.mark.parametrize('prefix', ['x', '1', ':', '!', '/', '\\', '\u00a0'])
def test_www_rejected_boundaries_keep_real_images(prefix):
    assert images(prefix + 'www.example.org/' + IMAGE) == [('Shot', 'docs/images/missing.png')]


@pytest.mark.parametrize('prefix,resolves', [('x', False), ('1', True), (':', True), ('!', True),
                                           ('/', True), ('\\', True), ('\u00a0', True)])
def test_native_scheme_start_boundaries(prefix, resolves):
    assert images(prefix + 'https://example.org/' + IMAGE) == ([] if resolves else [('Shot', 'docs/images/missing.png')])


@pytest.mark.parametrize('url', ['https://bad_host.org/', 'www.bad_host.org/', 'https://_bad.org/',
                                'https://./', 'https:///', 'https://\fabc/', 'httpſ://example.org/', 'WWW.example.org/', 'custom://example.org/',
                                'a@b.c/', 'mailto:a@b.c/', 'xmpp:a@b.c/'])
def test_invalid_or_non_url_forms_do_not_mask_following_images(url):
    assert images('text ' + url + IMAGE) == [('Shot', 'docs/images/missing.png')]


@pytest.mark.parametrize('suffix', ['.', '?!.,:*_~', ')))', '.)))!', '&amp;', ';', ')))).&alpha;', '))x'])
def test_trailing_punctuation_and_balanced_parentheses_keep_url_contents_literal(suffix):
    assert images('https://example.org/' + IMAGE + suffix + ' ' + IMAGE) == [('Shot', 'docs/images/missing.png')]


@pytest.mark.parametrize('separator', [' ', '\t', '\n', '\r\n', '\r', '<'])
def test_url_ends_before_a_separate_real_image(separator):
    assert images('https://example.org/path' + separator + IMAGE) == [('Shot', 'docs/images/missing.png')]


@pytest.mark.parametrize('separator', ['\u00a0', '\x85', '\u2003', '\v', '\f', '\x01', '\x7f'])
def test_native_nonseparators_stay_inside_url(separator):
    assert images('https://example.org/path' + separator + IMAGE) == []


@pytest.mark.parametrize('prefix', ['<', '\\<'])
def test_malformed_or_escaped_http_angle_falls_back_to_bare_url(prefix):
    assert images(prefix + 'https://example.org/' + IMAGE) == []


@pytest.mark.parametrize('source,expected', [
    ('`https://example.org/' + IMAGE + '` ' + IMAGE, [('Shot', 'docs/images/missing.png')]),
    ('https://example.org/` `' + IMAGE + '` ' + IMAGE, [('Shot', 'docs/images/missing.png')]),
    ('`https://example.org/` `' + IMAGE + '` ' + IMAGE, [('Shot', 'docs/images/missing.png')]),
    ('<span title="https://example.org/`"> `' + IMAGE + '` ' + IMAGE, [('Shot', 'docs/images/missing.png')]),
    ('text <!-- https://example.org/` --> `' + IMAGE + '` ' + IMAGE, [('Shot', 'docs/images/missing.png')]),
    ('[Docs](target "https://example.org/' + IMAGE + '")', []),
    ('[Docs](https://example.org/' + IMAGE + ')', []),
    ('[https://example.org/' + IMAGE + '](target)', [('Shot', 'docs/images/missing.png')]),
    ('[www.example.org/' + IMAGE + '](target)', [('Shot', 'docs/images/missing.png')]),
    ('[unclosed https://example.org/' + IMAGE, [('Shot', 'docs/images/missing.png')]),
    ('![https://example.org/' + IMAGE + '](outer.png)', [('https://example.org/' + IMAGE, 'outer.png')]),
    ('![Shot][https://example.org/key]\n\n[https://example.org/key]: docs/images/missing.png\n',
     [('Shot', 'docs/images/missing.png')]),
    ('```\nhttps://example.org/' + IMAGE + '\n```\n' + IMAGE, [('Shot', 'docs/images/missing.png')]),
    ('<div>\nhttps://example.org/' + IMAGE + '\n</div>\n\n' + IMAGE, [('Shot', 'docs/images/missing.png')]),
])
def test_construct_precedence(source, expected):
    assert images(source) == expected


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('body,missing,bad_colour', [
    ('text https://example.org/' + IMAGE, False, False),
    ('text http://example.org/' + IMAGE, False, False),
    ('text www.example.org/' + IMAGE, False, False),
    ('text <https://example.org/' + IMAGE, False, False),
    ('https://example.org/![](docs/images/missing.png)', False, False),
    ('https://example.org/![Badge](https://img.shields.io/badge/type-bad-FF0000)', False, False),
    ('https://example.org/path ' + IMAGE, True, False),
    ('[https://example.org/' + IMAGE + '](target)', True, False),
    ('https://bad_host.org/' + IMAGE, True, False),
    ('https://example.org/path ![Badge](https://img.shields.io/badge/type-bad-FF0000)', False, True),
])
def test_real_cli_checks_only_rendered_images(tmp_path, ending, body, missing, bad_colour):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'files': ['README.md']}),
                    encoding='utf-8')
    path = tmp_path / 'README.md'
    path.write_bytes(('# Probe\n\n' + body + '\n').replace('\n', ending).encode('utf-8'))
    run = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert run.returncode == 1 and not run.stderr
    fails = json.loads(run.stdout)['fails']
    assert (MISSING in fails) == missing, fails
    assert any('off-palette badge colour FF0000' in f for f in fails) == bad_colour, fails
    assert not any('image without alt' in f for f in fails), fails
    if not bad_colour:
        assert 'R7 2-4 header badges required (found 0)' in fails, fails


@pytest.mark.parametrize('pattern', [
    'https://example.org/' * 30 + ')))' * 30,
    'https://bad_' * 30 + '.org/' + IMAGE,
    '[open https://example.org/' + IMAGE,
])
def test_bare_autolink_work_scales_with_source(pattern):
    measurements = []
    for n in (20, 40):
        doc = (pattern + '\n\n') * n
        mdcode.autolink_candidates.cache_clear()
        readmelint._inline_openers_and_autolinks.cache_clear()
        readmelint._outside_code.cache_clear()
        mdcode.WORK.clear()
        images(doc)
        measurements.append(dict(mdcode.WORK))
    small, large = measurements
    for counter in ('bare_index_chars', 'bare_starts', 'bare_trim_steps'):
        assert large.get(counter, 0) <= 2.2 * small.get(counter, 0), (counter, small, large)


def test_nested_url_candidates_share_long_suffix_work():
    measures = []
    for n in (200, 400):
        source = 'https://a/' * n + ')' * n
        mdcode.autolink_candidates.cache_clear()
        mdcode.WORK.clear()
        mdcode.autolink_candidates(source)
        measures.append(dict(mdcode.WORK))
    assert measures[1]['bare_trim_steps'] <= 2.2 * measures[0]['bare_trim_steps']
    assert measures[1]['bare_index_chars'] <= 2.2 * measures[0]['bare_index_chars']


@pytest.mark.parametrize('source,linked_text', [
    ('https://example.org/a?!.,:*_~', 'https://example.org/a'),
    ('www.example.org/a.', 'www.example.org/a'),
    ('https://example.org/a(b)))', 'https://example.org/a(b)'),
    ('https://example.org/a(b))x', 'https://example.org/a(b))x'),
    ('https://example.org/a)).!', 'https://example.org/a'),
    ('https://example.org/a&alpha;', 'https://example.org/a'),
    ('https://example.org/a&alpha1;', 'https://example.org/a&alpha1'),
    ('https://example.org/a;', 'https://example.org/a'),
    ('https://example.org/a<rest', 'https://example.org/a'),
])
def test_native_anchor_text_boundaries(source, linked_text):
    spans = readmelint._live_autolinks(source)
    assert [source[a:b] for a, b in spans] == [linked_text]


def test_html_image_after_url_terminator_still_renders():
    assert images('https://example.org/path<img src="docs/images/missing.png" alt="Shot">') == [
        ('Shot', 'docs/images/missing.png')]


def test_angle_precedence_keeps_nested_url_brackets_inert():
    source = ('![outer <https://example.org/https://a/[>](url "<!--")\n\n'
              '[ref]: docs/images/missing.png\n\n-->\n![Shot][ref]')
    assert images(source) == [('outer <https://example.org/https://a/[>', 'url'),
                              ('Shot', 'docs/images/missing.png')]
