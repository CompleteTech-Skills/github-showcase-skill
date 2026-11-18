"""Count actual run visits, including adversarial unmatched lengths, rather than relying on elapsed time."""
import json

import pytest

from conftest import run_cli
from ctshowcase import mdcode, readmelint


def unique_runs(count, ending='\n'):
    return 'text ' + ' '.join('`' * length for length in range(1, count + 1)) + ending


@pytest.mark.parametrize('count', [50, 100, 200, 400, 800])
def test_unique_unmatched_lengths_do_not_revisit_run_suffixes(monkeypatch, count):
    source = unique_runs(count)
    original = mdcode._run_end
    calls, chars = 0, 0

    def measured(text, pos):
        nonlocal calls, chars
        end = original(text, pos)
        calls += 1
        chars += end - pos
        return end

    monkeypatch.setattr(mdcode, '_run_end', measured)
    mdcode._backtick_index.cache_clear()
    mdcode.inline_code_spans.cache_clear()
    mdcode.WORK.clear()
    assert mdcode.code_spans(source) == []
    assert calls <= 2 * count
    assert chars <= 2 * source.count('`')
    assert mdcode.WORK['backtick_index_chars'] == len(source)
    assert mdcode.WORK['backtick_index_runs'] == count
    assert mdcode.WORK['backtick_close_lookups'] <= count


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
def test_large_unmatched_paragraph_still_checks_real_image_cli(tmp_path, ending):
    source = ('# Probe\n\n' + unique_runs(800) + '\n![Shot](docs/images/missing.png)\n').replace('\n', ending)
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'files': ['README.md']}),
                    encoding='utf-8')
    path = tmp_path / 'README.md'
    path.write_bytes(source.encode('utf-8'))
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1 and not result.stderr
    assert 'R7 local image does not resolve: docs/images/missing.png' in json.loads(result.stdout)['fails']
    assert path.read_bytes() == source.encode('utf-8')


@pytest.mark.parametrize('source,contents', [
    ('\\``code` tail', ['`code`']),
    ('`code\\` tail', ['`code\\`']),
    ('`one``two`` three`', ['`one``two`` three`']),
    ('`one\n\nother`', []),
    ('`one\n# Heading\nother`', []),
    ('<https://example.org/`> `code`', ['`code`']),
    ('`<https://example.org/`> `code`', ['`<https://example.org/`', '`code`']),
])
def test_index_preserves_raw_closers_escaped_openers_and_region_boundaries(source, contents):
    assert [source[a:b] for a, b in mdcode.inline_code_spans(source)] == contents


def test_image_path_uses_index_without_rebuilding_for_each_unmatched_length():
    source = unique_runs(400) + '\n![Shot](docs/images/missing.png)\n'
    mdcode._backtick_index.cache_clear()
    readmelint._outside_code.cache_clear()
    mdcode.WORK.clear()
    assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', 'docs/images/missing.png')]
    assert mdcode.WORK['backtick_index_chars'] <= 2 * len(source)
