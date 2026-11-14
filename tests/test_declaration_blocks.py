"""GFM type-4 declarations require uppercase independently of case-insensitive HTML tag names."""
import json

import pytest

from conftest import run_cli
from ctshowcase import mdcode, readmelint

IMAGE = '![Shot](docs/images/missing.png)'
MISSING = 'R7 local image does not resolve: docs/images/missing.png'


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('prefix', ['', '> ', '- ', '> - '])
@pytest.mark.parametrize('name', ['a', 'abc', 'A', 'ABC'])
def test_declaration_cli_block_case(tmp_path, ending, prefix, name):
    source = ('# Probe\n\n' + prefix + '<!' + name + ' ' + IMAGE + ' >\n').replace('\n', ending)
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'files': ['README.md']}),
                    encoding='utf-8')
    path = tmp_path / 'README.md'
    path.write_bytes(source.encode('utf-8'))
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1 and not result.stderr
    assert (MISSING in json.loads(result.stdout)['fails']) == name.islower()
    assert path.read_bytes() == source.encode('utf-8')


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('name', ['a', 'A'])
def test_only_uppercase_declaration_interrupts_an_open_code_paragraph(ending, name):
    source = ('text `\n<!' + name + ' declaration >\n' + IMAGE + '\n`\n').replace('\n', ending)
    found = readmelint._images(readmelint._outside_code(source), source)
    assert found == ([('Shot', 'docs/images/missing.png')] if name == 'A' else [])
    assert bool(mdcode.html_block_spans(source)) == (name == 'A')


@pytest.mark.parametrize('tag', ['script', 'SCRIPT', 'p', 'P', 'DiV'])
def test_normal_tag_names_still_interrupt_without_case_sensitivity(tag):
    source = 'text `\n<' + tag + '>\n' + IMAGE + '\n</' + tag + '>\n'
    assert mdcode.html_block_spans(source)
    assert readmelint._images(readmelint._outside_code(source), source) == []
