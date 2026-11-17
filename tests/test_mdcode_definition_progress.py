"""Definition block boundaries and bounded incremental parsing."""
import json

import pytest

from conftest import run_cli
from ctshowcase import mdcode


# GFM oracle (cmarkgfm 2025.10.22; PR #13 review r1.1.F1): the indented lazy line continues the paragraph the
# definition is removed from, so its backtick pairs with the last line and both images are code
# ('<p>    <code>![Shot](docs/images/missing.png) ![Bad](...)</code></p>'). An image on that lazy line renders.
@pytest.mark.parametrize('prefix,indent', [('> ', 4), ('- > ', 6), ('> - ', 4)])
def test_cli_definition_container_end(tmp_path, prefix, indent):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'files': ['README.md']}))
    path = tmp_path / 'README.md'

    def fails(source):
        path.write_text('# Probe\n\n' + source)
        result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
        return json.loads(result.stdout)['fails']

    hidden = fails(prefix + '[a]: /url\n' + ' ' * indent + '`\n'
                   '![Shot](docs/images/missing.png)\n'
                   '![Bad](https://img.shields.io/badge/x-x-ABCDEF)\n`\n')
    assert 'R7 local image does not resolve: docs/images/missing.png' not in hidden
    assert 'R7 off-palette badge colour ABCDEF' not in hidden
    shown = fails(prefix + '[a]: /url\n' + ' ' * indent + '![Shot](docs/images/missing.png) '
                  '![Bad](https://img.shields.io/badge/x-x-ABCDEF)\n')
    assert 'R7 local image does not resolve: docs/images/missing.png' in shown
    assert 'R7 off-palette badge colour ABCDEF' in shown


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
    # cmark-gfm keeps both lazy lines in the quote paragraph, so the image is code.
    ('> [a]: /url\n    `\n![x](missing.png)\n`\n', []),
    ('> [a]: /url\n    ![x](missing.png)\n', [('x', 'missing.png')]),
    ('> [a]: /url\n\n    `\n![x](missing.png)\n`\n', [('x', 'missing.png')]),
    ('[a]: /url (bad (title)\n![x](missing.png)\n', [('x', 'missing.png')]),
])
def test_definition_and_invalid_controls(source, expected):
    assert mdcode._images(mdcode._outside_code(source), source) == expected
