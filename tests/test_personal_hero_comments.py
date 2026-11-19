"""Public CLI regressions: commented images cannot satisfy a personal hero."""
import json
import re

import pytest

from conftest import run_cli


HTML_ART = b'<img src="assets/old-hero.svg" alt="Hidden example">'
MARKDOWN_ART = b'![Hidden example](assets/old-hero.svg)'
BADGE = b'![Build](https://img.shields.io/badge/build-passing-green)'
BODY = b'> [!NOTE]\n> Synthetic callout.\n\n# Profile\n\nAuthored  notes.  \r\n\tLiteral note.\n'
BLOCK = re.compile(br'<!-- showcase:banner:start -->.*?<!-- showcase:banner:end -->', re.S)
MODES = [
    pytest.param('upgrade', 'J', (), id='upgrade-J'),
    pytest.param('upgrade', 'G', (), id='upgrade-G'),
    pytest.param('upgrade', 'H', (), id='upgrade-H'),
    pytest.param('scaffold', 'J', (), id='scaffold-J'),
    pytest.param('header', 'J', (), id='header-J'),
    pytest.param('upgrade', 'J', ('--no-regroup',), id='no-regroup-J'),
]


def setup_repo(directory, source, intro=None, *, owner='CompleteDotTech', repo='CompleteDotTech'):
    meta = directory / 'meta.json'
    meta.write_text(json.dumps({
        'owner': owner, 'repo': repo, 'visibility': 'public',
        'license': 'MIT', 'description': 'Show synthetic public projects.',
        'topics': [], 'files': [], 'files_complete': True,
    }), encoding='utf-8')
    files = {'README.md': source, 'records.jsonl': b'{"id":"synthetic-existing"}\n',
             'docs/images/.showcase.json': b'{"outputs":{}}\n',
             'CONTRIBUTING.md': b'Synthetic  contribution notes.  \r\n'}
    if intro is not None:
        files['assets/intro.svg'] = intro
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return meta


def generate(directory, meta, mode, variant, options=()):
    return run_cli('--format', 'json', '--meta', meta, '--repo-dir', directory,
                   'readme', '--mode', mode, '--variant', variant, *options,
                   '--badges', 'local', '--records', directory / 'records.jsonl', '--write')


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob('*') if p.is_file()}


def assert_refusal(result, directory, before, code):
    assert result.returncode == 4, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report['result'] == 'needs-input' and code in result.stdout, report
    assert snapshot(directory) == before, 'Refusal must create or change no files'


@pytest.fixture(scope='module')
def generated_intro(tmp_path_factory):
    directory = tmp_path_factory.mktemp('comment-intro')
    path = directory / 'assets/intro.svg'
    path.parent.mkdir()
    result = run_cli('intro', '--profile', 'CompleteDotTech', '--static', '--out', path)
    assert result.returncode == 0, result.stdout + result.stderr
    intro = path.read_bytes()
    meta = setup_repo(directory, b'', intro)
    result = generate(directory, meta, 'scaffold', 'J')
    assert result.returncode == 0, result.stdout + result.stderr
    block, = BLOCK.findall((directory / 'README.md').read_bytes())
    return intro, block


@pytest.mark.parametrize('mode,variant,options', MODES)
@pytest.mark.parametrize('image', [HTML_ART, MARKDOWN_ART], ids=['HTML', 'Markdown'])
@pytest.mark.parametrize('has_intro', [False, True], ids=['missing-intro', 'applicable-intro'])
def test_commented_art_requires_real_intro(tmp_path, generated_intro, mode, variant, options, image, has_intro):
    comment = b'<!-- Hidden example.  \r\n' + image + b'\n-->\n\n'
    # In-place modes refresh existing owned blocks; they do not create markers.
    owned = generated_intro[1] + b'\n\n' if mode == 'header' or options else b''
    meta = setup_repo(tmp_path, comment + owned + BODY, generated_intro[0] if has_intro else None)
    before = snapshot(tmp_path)
    result = generate(tmp_path, meta, mode, variant, options)
    if not has_intro:
        assert_refusal(result, tmp_path, before, 'needs-input:intro')
        return
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / 'README.md').read_bytes()
    block, = BLOCK.findall(updated)
    assert b'src="assets/intro.svg"' in block
    assert b'docs/images/banner.png' not in updated and 'exempt' not in result.stdout
    assert comment in updated and b'Authored  notes.  \r\n\tLiteral note.\n' in updated


@pytest.mark.parametrize('mode,variant,options', MODES)
@pytest.mark.parametrize('image', [HTML_ART, MARKDOWN_ART], ids=['HTML', 'Markdown'])
@pytest.mark.parametrize('has_intro', [False, True], ids=['missing-intro', 'applicable-intro'])
def test_visible_authored_art_stays_authored(tmp_path, generated_intro, mode, variant, options, image, has_intro):
    source = image + b'  \r\n\n' + BODY
    meta = setup_repo(tmp_path, source, generated_intro[0] if has_intro else None)
    result = generate(tmp_path, meta, mode, variant, options)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'README.md').read_bytes() == source
    assert 'exempt' not in result.stdout


@pytest.mark.parametrize('mode,variant,options', [MODES[4], MODES[5]])
@pytest.mark.parametrize('badge', [BADGE, b'<img src="https://img.shields.io/badge/build-passing-green" alt="Build">'],
                         ids=['Markdown', 'HTML'])
@pytest.mark.parametrize('hidden', [False, True], ids=['visible-badge', 'commented-badge'])
def test_only_visible_badge_blocks_in_place_intro_order(
        tmp_path, generated_intro, mode, variant, options, badge, hidden):
    prefix = (b'<!-- Hidden badge.\n' + badge + b'\n-->' if hidden else badge) + b'  \r\n\n'
    suffix = b'\n\n' + BODY
    meta = setup_repo(tmp_path, prefix + generated_intro[1] + suffix, generated_intro[0])
    before = snapshot(tmp_path)
    result = generate(tmp_path, meta, mode, variant, options)
    if not hidden:
        assert_refusal(result, tmp_path, before, 'needs-input:intro-order')
        return
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / 'README.md').read_bytes()
    block, = BLOCK.finditer(updated)
    assert b'src="assets/intro.svg"' in block.group()
    assert updated[:block.start()] == prefix and updated[block.end():] == suffix
    lint = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', tmp_path / 'README.md')
    assert lint.returncode in (0, 1), lint.stdout + lint.stderr
    assert not [f for f in json.loads(lint.stdout)['fails'] if f.startswith('D13 ')], lint.stdout


def test_organization_readme_still_uses_repository_banner(tmp_path):
    meta = setup_repo(tmp_path, b'', owner='CompleteTech-LLC', repo='.github')
    result = generate(tmp_path, meta, 'scaffold', 'J')
    assert result.returncode == 0, result.stdout + result.stderr
    updated = (tmp_path / 'README.md').read_bytes()
    assert b'src="docs/images/banner.png"' in updated
    assert b'assets/intro.svg' not in updated and 'needs-input:intro' not in result.stdout
