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
    readme.write_text('# Probe\n\n' + source + '\n', encoding='utf-8')
    result = subprocess.run([sys.executable, str(CLI), '--meta', str(meta), '--repo-dir', str(tmp_path),
                             'lint', 'readme', str(readme)], capture_output=True, encoding='utf-8', timeout=15)
    return json.loads(result.stdout)['fails']


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
