"""Definition block boundaries and bounded incremental parsing."""
import json

import pytest

from conftest import run_cli
from ctshowcase import mdcode


@pytest.mark.parametrize('prefix,indent', [('> ', 4), ('- > ', 6), ('> - ', 4)])
def test_cli_definition_container_end(tmp_path, prefix, indent):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'files': ['README.md']}))
    path = tmp_path / 'README.md'
    path.write_text('# Probe\n\n' + prefix + '[a]: /url\n' + ' ' * indent + '`\n'
                    '![Shot](docs/images/missing.png)\n'
                    '![Bad](https://img.shields.io/badge/x-x-ABCDEF)\n`\n')
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    fails = json.loads(result.stdout)['fails']
    assert 'R7 local image does not resolve: docs/images/missing.png' in fails
    assert 'R7 off-palette badge colour ABCDEF' in fails


@pytest.mark.parametrize('head,tail', [
    ('[a]: /url extra\n', ''),
    ('[a]: /url "title\n', '    end"\n'),
    ("[a]: /url 'title\n", "    end'\n"),
    ('[a]: /url (title\n', '    end)\n'),
])
def test_definition_progress_bounded(head, tail):
    def work(n):
        text = head + '    continuation\n' * n + tail + '\n![x](missing.png)\n'
        mdcode._layout.cache_clear()
        mdcode.WORK.clear()
        images = mdcode._images(mdcode._outside_code(text), text)
        assert ('x', 'missing.png') in images
        return mdcode.WORK['definition_progress_chars']
    small, large = work(300), work(600)
    assert large <= 2 * small + 100


@pytest.mark.parametrize('source,expected', [
    ('[a]: /url extra\n    `\n![x](missing.png)\n`\n', []),
    ('> [a]: /url\n> "title\n> ![x](missing.png)\n> end"\n', []),
    ('> [a]: /url\n    `\n![x](missing.png)\n`\n', [('x', 'missing.png')]),
    ('[a]: /url (bad (title)\n![x](missing.png)\n', [('x', 'missing.png')]),
])
def test_definition_and_invalid_controls(source, expected):
    assert mdcode._images(mdcode._outside_code(source), source) == expected
