"""Actual source NUL is U+FFFD before grammar; authored bytes and prefix masks remain distinct."""
import json

import pytest

from conftest import run_cli
from ctshowcase import mdcode, readme, readmelint

MISSING = 'R7 local image does not resolve: '
PALETTE = 'https://img.shields.io/badge/probe-test-FF0000?x=a\x00b'


def lint_cli(tmp_path, source):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'license': 'MIT',
                                'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    written = source.encode('utf-8')
    path.write_bytes(written)
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1 and not result.stderr, result.stdout + result.stderr
    assert path.read_bytes() == written
    return json.loads(result.stdout)['fails']


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('form', ['reference', 'inline', 'angle', 'html'])
def test_nul_source_target_is_checked_cli_at_same_offsets(tmp_path, ending, form):
    target = 'docs/x\x00z.png'
    if form == 'reference':
        usage = '![Shot][ref]'
        body = usage + '\n\n[ref]: ' + target
    elif form == 'html':
        usage = '<img src="' + target + '" alt="Shot">'
        body = usage
    else:
        usage = '![Shot](' + ('<' + target + '>' if form == 'angle' else target) + ')'
        body = usage
    source = ('# Probe\n\n' + body + '\n').replace('\n', ending)
    view = mdcode._source_view(source)
    assert len(view) == len(source) and '\x00' not in view
    assert [i for i, c in enumerate(view) if c in '\r\n'] == [i for i, c in enumerate(source) if c in '\r\n']
    assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', 'docs/x\ufffdz.png')]
    fails = lint_cli(tmp_path, source)
    assert MISSING + 'docs/x\ufffdz.png' in fails
    if form != 'html':
        image, = readmelint._markdown_images(readmelint._outside_code(source), source)
        assert source[image[2]:image[3]] == usage


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
@pytest.mark.parametrize('reference', [False, True])
def test_nul_does_not_hide_off_palette_badges_cli(tmp_path, ending, reference):
    body = '![Probe][ref]\n\n[ref]: ' + PALETTE if reference else '![Probe](' + PALETTE + ')'
    fails = lint_cli(tmp_path, ('# Probe\n\n' + body + '\n').replace('\n', ending))
    assert 'R7 off-palette badge colour FF0000' in fails


@pytest.mark.parametrize('reference', [False, True])
def test_source_nul_and_authored_replacement_character_resolve_same_existing_file(tmp_path, reference):
    path = tmp_path / 'docs/x\ufffdz.png'
    path.parent.mkdir(parents=True)
    from PIL import Image
    Image.new('RGB', (1, 1), 'white').save(path)
    body = '![Shot][ref]\n\n[ref]: docs/x\x00z.png' if reference else '![Shot](docs/x\x00z.png)'
    for source in [body, body.replace('\x00', '\ufffd')]:
        assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', 'docs/x\ufffdz.png')]
        assert not any(f.startswith(MISSING) for f in lint_cli(tmp_path, '# Probe\n\n' + source + '\n'))


@pytest.mark.parametrize('prefix', ['> ', '- ', '> - ', '1. '])
def test_nul_preprocessing_precedes_definition_peeling_and_keeps_prefix_sentinels(prefix):
    source = '![Shot][a\x00b]\n\n' + prefix + '[a\x00b]: docs/x\x00z.png\n'
    candidate = readmelint._definition_candidates(source)
    at = source.index(prefix + '[a')
    assert candidate[at:at + len(prefix)] == '\x00' * len(prefix)
    assert 'docs/x\ufffdz.png' in candidate
    assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', 'docs/x\ufffdz.png')]
    definition, = readmelint._definitions(source)
    assert definition.group(1) == 'a\ufffdb'
    assert readmelint._definition_key(definition, mdcode._source_view(source)) == 'a\ufffdb'


def test_masked_code_nul_is_not_reinterpreted_as_literal_source():
    source = '`![Fake](docs/fake.png)` ![Real](docs/x\x00z.png)'
    masked = mdcode.masked(source)
    text, document = mdcode._parse_views(masked, source)
    code_end = source.index('`', 1) + 1
    assert text[:code_end] == '\x00' * code_end
    assert text[source.index('\x00')] == '\ufffd'
    assert readmelint._images(text, document) == [('Real', 'docs/x\ufffdz.png')]


@pytest.mark.parametrize('body', [
    '`![Fake](docs/x\x00z.png)`',
    '`![Fake][ref]`\n\n[ref]: docs/x\x00z.png',
    '`![Fake](' + PALETTE + ')`',
    'text <!-- ![Fake](docs/x\x00z.png) -->',
    'https://example.org/![Fake](docs/x\x00z.png)',
    '![NoLink](docs/x\x00z.png \x00)',
])
def test_nul_preprocessing_keeps_code_comment_url_and_malformed_controls_inert_cli(tmp_path, body):
    source = '# Probe\n\n' + body + '\n\n![Real](docs/images/missing.png)\n'
    fails = lint_cli(tmp_path, source)
    assert [f for f in fails if f.startswith(MISSING)] == [MISSING + 'docs/images/missing.png']
    assert not any('off-palette' in f for f in fails)


def test_actual_nul_line_is_not_a_synthetic_blank_line():
    source = '`code\n\x00\n![Fake](docs/images/missing.png)`'
    assert readmelint._images(readmelint._outside_code(source), source) == []
    code, = mdcode.inline_code_spans(source)
    assert source[code[0]:code[1]] == source


@pytest.mark.parametrize('mode', ['header', 'upgrade'])
def test_actual_readme_writes_keep_authored_nul_bytes_and_marker_examples(tmp_path, mode):
    authored = 'https://example.org/x\x00z` `<!-- showcase:nav:start --> AUTHORED <!-- showcase:nav:end -->`'
    source = '# Probe\n\n## Usage\n\n' + authored + '\n\nKeep these instructions.\n'
    path = tmp_path / 'README.md'
    path.write_bytes(source.encode())
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'license': 'MIT',
                                'description': 'Maintain synthetic records.', 'files': ['README.md']}), encoding='utf-8')
    args = ('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', mode, '--write')
    first = run_cli(*args)
    assert first.returncode == 0, first.stdout + first.stderr
    written = path.read_bytes()
    assert authored.encode() in written and written.count(b'\x00') == 1
    second = run_cli(*args)
    assert second.returncode == 0, second.stdout + second.stderr
    assert path.read_bytes() == written
    blocks = mdcode.find_blocks(readme.MARK, written.decode())
    assert not any('AUTHORED' in block.group(2) for block in blocks)


def test_source_view_is_cached_and_bounded_across_marker_and_image_consumers():
    source = '\n\n'.join(f'![Real](docs/x\x00{number}.png)' for number in range(100))
    mdcode._source_view.cache_clear()
    mdcode._parse_views.cache_clear()
    mdcode.inline_code_spans.cache_clear()
    mdcode._outside_code.cache_clear()
    mdcode._definitions.cache_clear()
    mdcode.WORK.clear()
    assert mdcode.find_blocks(readme.MARK, source) == []
    assert len(readmelint._images(readmelint._outside_code(source), source)) == 100
    assert len(source) <= mdcode.WORK['source_view_chars'] <= 2 * len(source)
    assert mdcode.WORK['inline_precedence_builds'] == 1


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'], ids=['LF', 'CRLF', 'CR'])
def test_dry_plan_and_marker_groups_preserve_original_nul_source_bytes(tmp_path, ending):
    real = '<!-- showcase:nav:start -->\nAUTHORED \x00 CONTENT\n<!-- showcase:nav:end -->'
    source = ('# Probe\n\n```markdown\n' + real + '\n```\n\n' + real + '\n').replace('\n', ending)
    block, = mdcode.find_blocks(readme.MARK, source)
    assert block.group() == real.replace('\n', ending)
    assert source[block.start():block.end()].encode() == block.group().encode()
    assert '\x00' in block.group(2) and '\ufffd' not in block.group(2)
    path = tmp_path / 'README.md'
    written = source.encode()
    path.write_bytes(written)
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'license': 'MIT',
                                'files': ['README.md']}), encoding='utf-8')
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', 'header', '--diff')
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['written'] is False
    assert path.read_bytes() == written
