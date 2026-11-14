"""CLI regressions for Markdown destinations and nested containers."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ctshowcase import mdcode

CLI = Path(__file__).resolve().parents[1] / 'scripts' / 'showcase.py'


def lint(tmp_path, source):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    readme = tmp_path / 'README.md'
    readme.write_bytes(('# Probe\n\n' + source + '\n').encode('utf-8'))
    result = subprocess.run([sys.executable, str(CLI), '--meta', str(meta), '--repo-dir', str(tmp_path),
                             'lint', 'readme', str(readme)], capture_output=True, encoding='utf-8', timeout=15)
    return json.loads(result.stdout)['fails']


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'])
def test_lint_fixture_preserves_bytes_with_windows_text_translation(tmp_path, monkeypatch, ending):
    write_text = Path.write_text

    def windows_write_text(path, data, encoding=None, **kwargs):
        return write_text(path, data, encoding=encoding, newline='\r\n', **kwargs)

    monkeypatch.setattr(Path, 'write_text', windows_write_text)
    source = f'![Shot](x©.png){ending}![Bad](https://img.shields.io/badge/x-x-ABCDEF)'
    fails = lint(tmp_path, source)
    assert (tmp_path / 'README.md').read_bytes() == ('# Probe\n\n' + source + '\n').encode('utf-8')
    assert 'R7 local image does not resolve: x©.png' in fails
    assert 'R7 off-palette badge colour ABCDEF' in fails


@pytest.mark.parametrize('reference', [False, True])
@pytest.mark.parametrize('written,actual,wrong', [
    (r'x\&amp;y', 'x&y', 'x&amp;y'),
    ('x&copy.png', 'x&copy.png', 'x©.png'),
    (r'x&copy\;png', 'x&copy;png', 'x©png'),
    (r'x&amp\;y', 'x&amp;y', 'x&y'),
    ('x&amp;y', 'x&y', 'x&amp;y'),
    ('x&#169;.png', 'x©.png', 'x&#169;.png'),
])
def test_destination_entities_cli(tmp_path, reference, written, actual, wrong):
    image = f'![Shot][r]\n\n[r]: {written}' if reference else f'![Shot]({written})'
    (tmp_path / wrong).write_bytes(b'wrong')
    assert f'R7 local image does not resolve: {actual}' in lint(tmp_path, image)
    (tmp_path / actual).write_bytes(b'correct')
    assert f'R7 local image does not resolve: {actual}' not in lint(tmp_path, image)


def test_lint_unicode_with_legacy_default_encoding(tmp_path, monkeypatch):
    # Simulate a Windows locale for both fixture writes and subprocess decoding.
    write_text = Path.write_text

    def legacy_write_text(path, data, encoding=None, **kwargs):
        return write_text(path, data, encoding=encoding or 'cp1252', **kwargs)

    monkeypatch.setattr(Path, 'write_text', legacy_write_text)
    monkeypatch.setattr(subprocess, '_text_encoding', lambda: 'cp1252')
    image = '![Shot](x©.png)'
    missing = 'R7 local image does not resolve: x©.png'
    assert missing in lint(tmp_path, image)
    assert 'x©.png'.encode('utf-8') in (tmp_path / 'README.md').read_bytes()
    (tmp_path / 'x©.png').write_bytes(b'correct')
    assert missing not in lint(tmp_path, image)


@pytest.mark.parametrize('image,problem', [
    ('> ![Shot](docs/images/missing.png\n> "title")', 'R7 local image does not resolve: docs/images/missing.png'),
    ('> ![Shot](\n> docs/images/missing.png)', 'R7 local image does not resolve: docs/images/missing.png'),
    ('> ![Bad](https://img.shields.io/badge/x-x-ABCDEF\n> "title")', 'R7 off-palette badge colour ABCDEF'),
])
def test_quoted_continuation_cli(tmp_path, image, problem):
    assert problem in lint(tmp_path, image)
    assert problem not in lint(tmp_path, '```\n' + image + '\n```')


def test_deep_list_cli_and_container_alignment(tmp_path):
    source = '- ' * 8000 + 'text\n\n![Shot](missing.png)'
    assert 'R7 local image does not resolve: missing.png' in lint(tmp_path, source)
    text = '- > - item\n  >   ```\n  >   ![hidden](missing.png)\n  >   ```\n\n![shown](missing.png)\n'
    assert mdcode._images(text, text) == [('shown', 'missing.png')]


@pytest.mark.parametrize('prefix,indent', [('', '    '), ('> ', '>     '), ('- ', '      ')])
def test_definition_followed_by_indented_code_cli(tmp_path, prefix, indent):
    source = (prefix + '[a]: /url\n' + indent + '`example\n'
              + '![Shot](missing.png)\n![Bad](https://img.shields.io/badge/x-x-ABCDEF)\n`')
    fails = lint(tmp_path, source)
    assert 'R7 local image does not resolve: missing.png' in fails
    assert 'R7 off-palette badge colour ABCDEF' in fails
    assert mdcode.code_block_spans(source)[0][0] == source.index(indent + '`example')


def test_definition_code_boundary_controls(tmp_path):
    image = '![Shot](missing.png)'
    missing = 'R7 local image does not resolve: missing.png'
    assert missing not in lint(tmp_path, '[a]: /url extra\n    `example\n' + image + '\n`')
    assert missing not in lint(tmp_path, 'paragraph\n[a]: /url\n    `example\n' + image + '\n`')
    assert missing in lint(tmp_path, '[a]: /url\n    "title"\n    `example\n' + image + '\n`')
    assert missing not in lint(tmp_path, '```\n[a]: /url\n    `example\n```\n`' + image + '`')


@pytest.mark.parametrize('ending', ['-', '*', '_'])
def test_nested_list_thematic_scan_is_bounded(monkeypatch, ending, tmp_path):
    original = mdcode._THEMATIC
    class Measured:
        characters = 0

        def match(self, value, *args):
            self.characters += len(value)
            return original.match(value, *args)

    measured = Measured()
    monkeypatch.setattr(mdcode, '_THEMATIC', measured)
    for depth in (1000, 2000):
        before = measured.characters
        path, rest = mdcode._container_path('- ' * depth + 'text' + ending)
        assert len(path) == depth and rest == 'text' + ending
        assert measured.characters - before <= 8 * depth
    assert 'R7 local image does not resolve: missing.png' in lint(
        tmp_path, '- ' * 2000 + 'text' + ending + '\n\n![Shot](missing.png)')


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'])
@pytest.mark.parametrize('prefix,destination,indent', [
    ('', '/url', '    '), ('> ', '> /url', '    '), ('- ', '  /url', '      '),
])
def test_split_destination_keeps_code_boundary_cli(tmp_path, ending, prefix, destination, indent):
    source = (prefix + '[a]:\n' + destination + '\n' + indent + '`\n'
              '![Shot](missing.png)\n![Bad](https://img.shields.io/badge/x-x-ABCDEF)\n`').replace('\n', ending)
    fails = lint(tmp_path, source)
    assert 'R7 local image does not resolve: missing.png' in fails
    assert 'R7 off-palette badge colour ABCDEF' in fails
    assert ('Shot', 'missing.png') in mdcode._images(mdcode._outside_code(source), source)


@pytest.mark.parametrize('opener,closer', [('\"', '\"'), ("'", "'"), ('(', ')')])
@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'])
def test_reference_title_literal_backslash_cli(tmp_path, opener, closer, ending):
    source = f'![Shot][r]\n\n[r]: missing.png {opener}first\\\nsecond{closer}'.replace('\n', ending)
    assert 'R7 local image does not resolve: missing.png' in lint(tmp_path, source)
    invalid = source.replace('second' + closer, 'second' + closer + ' extra')
    assert 'R7 local image does not resolve: missing.png' not in lint(tmp_path, invalid)


@pytest.mark.parametrize('prefix', ['', '> ', '> > '])
@pytest.mark.parametrize('extra,valid', [('', True), ('x', False)])
def test_definition_label_length_excludes_container_prefix_cli(tmp_path, prefix, extra, valid):
    a, b = 'a' * 499, 'b' * 499 + extra
    source = f'![Shot][{a} {b}]\n\n{prefix}[{a}\n{prefix}{b}]: missing.png'
    assert ('R7 local image does not resolve: missing.png' in lint(tmp_path, source)) is valid


def test_nested_container_suffix_copy_is_linear():
    class MeasuredString(str):
        copied = 0

        def __getitem__(self, key):
            result = super().__getitem__(key)
            if isinstance(key, slice):
                type(self).copied += len(result)
                return type(self)(result)
            return result

    for depth in (1000, 2000, 4000):
        MeasuredString.copied = 0
        path, rest = mdcode._container_path(MeasuredString('- ' * depth + 'text*'))
        assert len(path) == depth and rest == 'text*'
        assert MeasuredString.copied <= 4 * depth + 20
