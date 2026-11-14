"""Real CLI writes and stdlib meta use the image scanner's accepted literal/code decisions."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import run_cli
from ctshowcase import mdcode, readme, readmelint

ROOT = Path(__file__).resolve().parents[1]


def example(block='badges'):
    return f'<!-- showcase:{block}:start --> AUTHORED {block} EXAMPLE <!-- showcase:{block}:end -->'


@pytest.mark.parametrize('mode', ['header', 'upgrade'])
@pytest.mark.parametrize('block', ['nav', 'banner', 'badges', 'tagline', 'footer'])
def test_cli_write_preserves_authored_code_and_refreshes_only_real_markers(tmp_path, mode, block):
    authored = 'https://example.org/` `' + example(block) + '`'
    initial = '# Probe\n\n## Usage\n\n' + authored + '\n\nKeep these authored instructions.\n'
    path = tmp_path / 'README.md'
    path.write_text(initial, encoding='utf-8')
    meta = tmp_path / 'meta.json'
    facts = {'owner': 'Northwind-Trading-Co', 'repo': '.github', 'license': 'MIT', 'files': ['README.md'],
             'description': 'Maintain synthetic documentation.'}
    meta.write_text(json.dumps(facts), encoding='utf-8')
    args = ('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', mode, '--write')
    first = run_cli(*args)
    assert first.returncode == 0, first.stdout + first.stderr
    assert 'readme-shrink' not in first.stdout
    assert authored.encode() in path.read_bytes()
    assert 'Keep these authored instructions.' in path.read_text(encoding='utf-8')
    # Alter only input metadata. Generated marker blocks are never hand-edited.
    if mode == 'header':
        # Header mode refreshes an existing header. Establish it via the CLI.
        generated = run_cli('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', 'upgrade', '--write')
        assert generated.returncode == 0, generated.stdout + generated.stderr
        facts['description'] = 'Maintain updated synthetic documentation.'
        meta.write_text(json.dumps(facts), encoding='utf-8')
    second = run_cli(*args)
    assert second.returncode == 0, second.stdout + second.stderr
    refreshed = path.read_bytes()
    assert authored.encode() in refreshed
    blocks = mdcode.find_blocks(readme.MARK, refreshed.decode())
    counts = Counter(m.group(1) for m in blocks)
    assert all(counts[kind] == 1 for kind in ('nav', 'banner', 'badges', 'tagline', 'footer')), counts
    assert facts['description'] in next(m.group(2) for m in blocks if m.group(1) == 'tagline')
    third = run_cli(*args)
    assert third.returncode == 0, third.stdout + third.stderr
    assert path.read_bytes() == refreshed


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('prefix', ['https://example.org/` ', 'http://example.org/` ', 'www.example.org/` ',
                                 '<https://example.org/`> ', '<span title="https://example.org/`"> ',
                                 'text <!-- https://example.org/` --> '])
def test_marker_and_image_projections_share_code_precedence(ending, prefix):
    source = (prefix + '`' + example() + ' ![Fake](docs/images/fake.png)`\n\n'
              '![Real](docs/images/missing.png)\n').replace('\n', ending)
    assert mdcode.find_blocks(readme.MARK, source) == []
    assert readme._strip_markers(source)[0] == source
    found = readmelint._images(readmelint._outside_code(source), source)
    assert found == [('Real', 'docs/images/missing.png')]
    for projection in (mdcode.masked(source), mdcode._marker_projection(source), readmelint._outside_code(source)):
        assert len(projection) == len(source)
        assert [i for i, c in enumerate(projection) if c in '\r\n'] == [i for i, c in enumerate(source) if c in '\r\n']


@pytest.mark.parametrize('source', [
    '[Docs](target "' + example() + '")',
    '<span title="' + example() + '">',
    'text <span title="' + example() + '">',
    '[Docs][' + example() + ']\n\n[' + example() + ']: target\n',
    '[key]: target "' + example() + '"\n',
    '```markdown\n' + example() + '\n```\n',
    '    ' + example() + '\n',
])
def test_data_and_code_cannot_supply_marker_delimiters(source):
    assert mdcode.find_blocks(readme.MARK, source) == []


def test_real_marker_after_bare_url_and_code_example_is_still_active():
    real = '<!-- showcase:nav:start -->\nREAL NAV\n<!-- showcase:nav:end -->'
    source = 'https://example.org/` `' + example('nav') + '`\n\n' + real + '\n'
    block, = mdcode.find_blocks(readme.MARK, source)
    assert block.group(0) == real and block.group(2) == 'REAL NAV'


def test_code_opened_before_url_uses_raw_closer_and_keeps_later_real_markers():
    source = '`https://example.org/` ' + example('nav') + '\n'
    block, = mdcode.find_blocks(readme.MARK, source)
    assert 'AUTHORED nav EXAMPLE' in block.group(2)


def test_meta_and_marker_core_remain_stdlib_only_without_import_cycle():
    # -S removes site-packages. An inline import test is a development probe;
    # the production write behavior is exercised above through showcase.py.
    script = r'''
import base64, sys
sys.path.insert(0, sys.argv[1])
from ctshowcase import mdcode, meta
fake = 'https://example.org/` `<!-- showcase:tagline:start --> FAKE <!-- showcase:tagline:end -->`'
real = '<!-- showcase:tagline:start -->\nREAL\n<!-- showcase:tagline:end -->'
source = fake + '\n\n' + real
value = meta._tagline_of({'content': base64.b64encode(source.encode()).decode()})
assert value == 'REAL', value
assert 'ctshowcase.readme' not in sys.modules
assert 'ctshowcase.readmelint' not in sys.modules
assert 'yaml' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-S', '-c', script, str(ROOT / 'scripts')],
                            encoding='utf-8', capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('count', [30, 60])
def test_marker_and_image_consumers_share_one_bounded_precedence_pass(count):
    source = '\n\n'.join('https://example.org/` `' + example() + '` ![Real](missing.png)' for _ in range(count))
    mdcode.inline_code_spans.cache_clear()
    mdcode._outside_code.cache_clear()
    mdcode._bracket_pairs.cache_clear()
    mdcode.WORK.clear()
    assert mdcode.find_blocks(readme.MARK, source) == []
    builds = mdcode.WORK['inline_precedence_builds']
    assert builds == 1
    assert len(readmelint._images(readmelint._outside_code(source), source)) == count
    assert mdcode.WORK['inline_precedence_builds'] == builds
    assert mdcode.WORK['marker_projection_chars'] <= len(source)
    assert mdcode.WORK['backtick_index_chars'] <= 2 * len(source)


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('prefix', ['> ', '- ', '> - ', '1. ', '- > '])
def test_container_marker_examples_stay_code_without_hiding_later_images(prefix, ending):
    source = (prefix + 'https://example.org/` `' + example() + '`\n\n'
              '![Real](docs/images/missing.png)\n').replace('\n', ending)
    assert mdcode.find_blocks(readme.MARK, source) == []
    assert readmelint._images(readmelint._outside_code(source), source) == [('Real', 'docs/images/missing.png')]
