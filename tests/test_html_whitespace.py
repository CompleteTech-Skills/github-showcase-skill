"""Raw HTML uses GFM ASCII whitespace, not Python's Unicode whitespace."""
import json

import pytest

from ctshowcase import readmelint
from conftest import run_cli


ASCII_SPACE = [' ', '\t', '\n', '\v', '\f', '\r']
UNICODE_SPACE = ['\x1c', '\x1d', '\x1e', '\x1f', '\x85', '\u00a0', '\u1680',
                 '\u2000', '\u2003', '\u2028', '\u2029', '\u202f', '\u205f', '\u3000']
TEMPLATES = ['text <!A{sep} {image} >', 'text <span{sep}title="{image}">',
             'text <span title{sep}="{image}">', 'text <span title={sep}"{image}">']
IMAGE = '![Shot](docs/images/missing.png)'


def images(source):
    return readmelint._images(readmelint._outside_code(source), source)


@pytest.mark.parametrize('template', TEMPLATES)
@pytest.mark.parametrize('sep', UNICODE_SPACE)
def test_non_gfm_whitespace_cannot_hide_rendered_images(template, sep):
    source = template.format(sep=sep, image=IMAGE)
    assert images(source) == [('Shot', 'docs/images/missing.png')]


@pytest.mark.parametrize('template', TEMPLATES)
@pytest.mark.parametrize('sep', ASCII_SPACE)
def test_all_gfm_whitespace_keeps_valid_raw_html_literal(template, sep):
    assert images(template.format(sep=sep, image=IMAGE)) == []


@pytest.mark.parametrize('sep', UNICODE_SPACE)
def test_unicode_whitespace_is_content_inside_unquoted_attribute_values(sep):
    # Unicode whitespace is allowed in an unquoted value. It neither ends the
    # value nor makes the Markdown-looking content in that value render.
    source = f'text <span title=a{sep}{IMAGE}>'
    assert images(source) == []
    assert images(f'<img src=docs/images/a{sep}b.png alt=Shot>') == [('Shot', f'docs/images/a{sep}b.png')]


@pytest.mark.parametrize('sep', [s for s in ASCII_SPACE if s not in ('\r', '\n')] + UNICODE_SPACE)
def test_closing_tag_space_controls_keep_the_enclosing_image(sep):
    alt = f'Shot </span{sep}>'
    assert images(f'![{alt}](docs/images/missing.png)') == [(alt, 'docs/images/missing.png')]


def test_closing_tag_newline_cannot_join_an_image_across_a_block_quote():
    # Native GFM starts a block quote at the second-line >. The block
    # boundary prevents the image description from closing across it.
    assert images('![Shot </span\n>](docs/images/missing.png)') == []


@pytest.mark.parametrize('template', TEMPLATES)
@pytest.mark.parametrize('sep', ['\u00a0', '\u2003'])
def test_production_lint_checks_images_and_authored_badges_inside_malformed_html(tmp_path, template, sep):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'license': 'MIT',
                                'description': 'Check synthetic inputs.', 'files': ['README.md']}), encoding='utf-8')
    badges = '\n'.join(template.format(sep=sep, image=f'![Badge](https://img.shields.io/badge/{value})')
                       for value in ['type-community-005ADD', 'license-MIT-64748B'])
    path = tmp_path / 'README.md'
    path.write_text('# Probe\n\n<img src="banner.png" alt="Probe">\n\n' + badges + '\n\n' +
                    template.format(sep=sep, image=IMAGE) + '\n\n---\n', encoding='utf-8')
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1
    failures = json.loads(result.stdout)['fails']
    assert 'R7 local image does not resolve: docs/images/missing.png' in failures
    assert not any('header badges required' in failure for failure in failures)


@pytest.mark.parametrize('sep', ['\u00a0', '\u2003'])
def test_production_lint_does_not_check_an_image_inside_valid_unicode_attribute(tmp_path, sep):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github', 'license': 'MIT',
                                'description': 'Check synthetic inputs.', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    path.write_text('# Probe\n\ntext <span title=a' + sep + IMAGE + '>\n', encoding='utf-8')
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert 'R7 local image does not resolve: docs/images/missing.png' not in json.loads(result.stdout)['fails']


@pytest.mark.parametrize("tag, renders", [
    ("<span title=a\u00a0b>", False),
    ("<span\vtitle=x>", False),
    ("<span\ftitle=x>", False),
    ("<span title\v=\fx>", False),
    ("<span title=x\v>", False),
    ("<span title=x>\f", False),
    ("<span xé=y>", True),
    ("<span title\u00a0=x>", True),
    ("<span\u2003title=x>", True),
])
@pytest.mark.parametrize("prefix", ["", "> ", "- "])
def test_html_block_tag_uses_the_same_ascii_lexical_classes(tag, renders, prefix):
    continuation = "  " if prefix == "- " else prefix
    source = prefix + tag + "\n" + continuation + IMAGE + "\n"
    assert images(source) == ([("Shot", "docs/images/missing.png")] if renders else [])


@pytest.mark.parametrize("tag, renders", [
    ("<span title=a\u00a0b>", False),
    ("<span\vtitle=x>", False),
    ("<span xé=y>", True),
])
def test_production_lint_honours_html_block_tag_lexical_classes(tmp_path, tag, renders):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github", "license": "MIT",
                                "description": "Check synthetic inputs.", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    path.write_text("# Probe\n\n" + tag + "\n" + IMAGE + "\n", encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "lint", "readme", path)
    failure = "R7 local image does not resolve: docs/images/missing.png"
    assert (failure in json.loads(result.stdout)["fails"]) is renders


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
def test_production_lint_respects_closing_tag_line_boundaries(tmp_path, ending):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github", "license": "MIT",
                                "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    # The lint loader normalizes CRLF before parsing. In both cases the >
    # starts a block quote and prevents a Markdown image from spanning it.
    path.write_bytes(("# Probe\n\n![Shot </span" + ending + ">](docs/images/missing.png)").encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "lint", "readme", path)
    assert result.returncode == 1
    assert "R7 local image does not resolve: docs/images/missing.png" not in json.loads(result.stdout)["fails"]
