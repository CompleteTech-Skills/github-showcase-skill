"""Rendered reference destinations keep GFM lexical content and meaningful CLI image checks."""
import json

import pytest

from conftest import run_cli
from ctshowcase import readmelint


CASES = [
    ('docs/images/missing\u00a0shot.png', 'docs/images/missing\u00a0shot.png'),
    ('docs/images/missing\u2003shot.png', 'docs/images/missing\u2003shot.png'),
    ('docs/images/missing\x85shot.png', 'docs/images/missing\x85shot.png'),
    ('docs/images/missing.png', 'docs/images/missing.png'),
    ('<docs/images/missing\u00a0shot.png>', 'docs/images/missing\u00a0shot.png'),
    ('<docs/images/missing.png', None),
    ('<docs/images/a<b.png>', None),
    ('<>', ''),
    ('<> "Empty source title"', ''),
    (r'<docs/images/a\>b.png>', 'docs/images/a>b.png'),
    (r'<docs/images/a\<b.png>', 'docs/images/a<b.png'),
    (r'\<docs/images/missing.png', '<docs/images/missing.png'),
    ('docs/images/a<b.png', 'docs/images/a<b.png'),
    (r'<docs/images/a\\>b.png>', None),
    (r'docs/images/a\ b.png', None),
]


def cli_lint(tmp_path, source):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'files': ['README.md']}),
                    encoding='utf-8')
    path = tmp_path / 'README.md'
    written = source.encode('utf-8')
    path.write_bytes(written)
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1 and not result.stderr, result.stdout + result.stderr
    assert path.read_bytes() == written
    return json.loads(result.stdout)['fails']


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('destination,target', CASES)
def test_reference_destination_cli(tmp_path, ending, destination, target):
    source = ('# Probe\n\n![Shot][ref]\n\n[ref]: ' + destination + '\n').replace('\n', ending)
    expected = [] if target is None else [('Shot', target)]
    assert readmelint._images(readmelint._outside_code(source), source) == expected
    fails = cli_lint(tmp_path, source)
    missing = [f for f in fails if f.startswith('R7 local image does not resolve:')]
    assert missing == ([f'R7 local image does not resolve: {target}'] if target else [])


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('space', ['\u00a0', '\u2003'])
@pytest.mark.parametrize('form', ['reference', 'inline', 'angle'])
def test_unicode_filename_existing_control(tmp_path, ending, space, form):
    filename = f'docs/images/good{space}shot.png'
    path = tmp_path / filename
    path.parent.mkdir(parents=True)
    path.write_bytes(b'image')
    body = f'![Shot]({filename})' if form == 'inline' else '![Shot][ref]\n\n[ref]: ' + (
        f'<{filename}>' if form == 'angle' else filename)
    source = ('# Probe\n\n' + body + '\n').replace('\n', ending)
    assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', filename)]
    assert not any('local image' in f for f in cli_lint(tmp_path, source))


@pytest.mark.parametrize('destination', ['<docs/images/no-close ', '<docs/images/a<b.png> '])
def test_rejected_definition_keeps_its_rendered_inline_image_visible(tmp_path, destination):
    source = '# Probe\n\n[ref]: ' + destination + '![Real](docs/images/missing.png)\n'
    fails = cli_lint(tmp_path, source)
    assert 'R7 local image does not resolve: docs/images/missing.png' in fails


def test_empty_angle_reference_still_requires_alt_text(tmp_path):
    fails = cli_lint(tmp_path, '# Probe\n\n![][ref]\n\n[ref]: <>\n')
    assert any(f.startswith('R7 image without alt text:') for f in fails)
    assert not any('local image' in f for f in fails)
