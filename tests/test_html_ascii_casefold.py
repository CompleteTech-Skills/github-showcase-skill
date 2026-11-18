"""Known GFM HTML block tags fold ASCII case only; Unicode lookalikes stay Markdown."""
import json

import pytest

from conftest import run_cli
from ctshowcase import mdcode, readmelint

IMAGE = '![Shot](docs/images/missing.png)'
MISSING = 'R7 local image does not resolve: docs/images/missing.png'


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('prefix,continuation', [('', ''), ('> ', '> '), ('- ', '  ')])
@pytest.mark.parametrize('tag,rendered', [('dİv', True), ('lı', True), ('ſection', True), ('blocKquote', True),
                                        ('DIV', False), ('dIv', False), ('LI', False), ('SeCtIoN', False)])
def test_html_tag_casefold_cli(tmp_path, ending, prefix, continuation, tag, rendered):
    source = ('# Probe\n\n' + prefix + '<' + tag + '>\n' + continuation + IMAGE + '\n').replace('\n', ending)
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'files': ['README.md']}),
                    encoding='utf-8')
    path = tmp_path / 'README.md'
    path.write_bytes(source.encode())
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1 and not result.stderr
    assert (MISSING in json.loads(result.stdout)['fails']) == rendered
    assert path.read_bytes() == source.encode()


@pytest.mark.parametrize('tag', ['dİv', 'lı', 'ſection', 'blocKquote', 'ſcript', 'scrİpt', 'scrıpt', 'ſtyle'])
@pytest.mark.parametrize('close', ['', '/'])
def test_unicode_lookalike_does_not_interrupt_an_inline_code_paragraph(tag, close):
    source = 'text `\n<' + close + tag + '>\n' + IMAGE + '\n`\n'
    span, = mdcode.inline_code_spans(source)
    assert source[span[0]:span[1]] == '`\n<' + close + tag + '>\n' + IMAGE + '\n`'
    assert readmelint._images(readmelint._outside_code(source), source) == []


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('closer', ['scrİpt', 'scrıpt', 'ſcript'])
def test_non_ascii_script_closer_does_not_release_html_block(ending, closer):
    source = ('<script>\n</' + closer + '>\n' + IMAGE + '\n</SCRIPT>\n\n' + IMAGE + '\n').replace('\n', ending)
    assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', 'docs/images/missing.png')]
    block, = mdcode.html_block_spans(source)
    assert source[block[0]:block[1]].endswith('</SCRIPT>' + ending)


@pytest.mark.parametrize('opener,closer', [('SCRIPT', 'sCrIpT'), ('Style', 'STYLE'), ('PRE', 'pre')])
def test_mixed_ascii_type_one_tags_and_closers_still_work(opener, closer):
    source = '<' + opener + '>\n' + IMAGE + '\n</' + closer + '>\n' + IMAGE + '\n'
    assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', 'docs/images/missing.png')]
