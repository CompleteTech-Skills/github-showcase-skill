"""All inline constructs use the source classifier's container-aware block bounds."""
import pytest

from ctshowcase import mdcode, readmelint

IMAGE = '![Shot](docs/images/missing.png)'


def images(text):
    return readmelint._images(readmelint._outside_code(text), text)


@pytest.mark.parametrize('prefix', ['> ', '> - ', '- > ', '> > ', '- - '])
def test_link_opener_cannot_hide_image_in_a_new_nested_list_paragraph(prefix):
    text = prefix + '[Docs\n' + prefix + '- ](url "' + IMAGE + '")\n'
    assert [source for _, source in images(text)] == ['docs/images/missing.png']


@pytest.mark.parametrize('prefix', ['> ', '> - ', '- > ', '> > ', '- - '])
def test_alt_text_cannot_pair_brackets_across_nested_list_paragraphs(prefix):
    text = prefix + '![Shot\n' + prefix + '- test](docs/images/missing.png)\n'
    assert images(text) == []
    assert readmelint._closing_bracket(text, text.index('[')) is None


@pytest.mark.parametrize('prefix,continuation', [('> ', '> '), ('- > ', '  > '), ('> - ', '>   ')])
def test_same_paragraph_soft_breaks_still_pair_inline_brackets(prefix, continuation):
    text = prefix + '[Docs\n' + continuation + 'continued](url "' + IMAGE + '")\n'
    assert images(text) == []
    assert readmelint._closing_bracket(text, text.index('[')) == text.index(']')


@pytest.mark.parametrize('opener,closer', [('<!--', ' -->'), ('`', '`')])
@pytest.mark.parametrize('text', [
    '- Text {opener}\n- \n{image}{closer}\n',
    '- > Text {opener}\n    > \n{image}{closer}\n',
    '- > Text {opener}\n  <span>\n{image}{closer}\n',
])
def test_empty_container_or_new_type7_block_ends_old_inline_construct(text, opener, closer):
    assert images(text.format(opener=opener, closer=closer, image=IMAGE)) == [
        ('Shot', 'docs/images/missing.png')]


@pytest.mark.parametrize('tag', ['<span>', '<a href="https://example.test">', '</span>'])
def test_type7_html_cannot_interrupt_matching_paragraph_but_starts_after_leaving_item(tag):
    assert images('Text <!--\n' + tag + '\n' + IMAGE + ' -->\n') == []
    assert images('- Text <!--\n' + tag + '\n> ' + IMAGE + ' -->\n') == []
    assert images('- > Text <!--\n  ' + tag + '\n' + IMAGE + ' -->\n') == [
        ('Shot', 'docs/images/missing.png')]


def test_prefixed_blank_line_protects_real_markers_on_the_later_paragraph_only():
    text = '- > Text `\n    > \n<!-- showcase:header:start -->\nLive\n<!-- showcase:header:end -->`\n'
    from ctshowcase.readme import MARK
    assert not mdcode.inline_code_spans(text)
    assert mdcode.find_blocks(MARK, text)


@pytest.mark.parametrize('label,expected', [
    ('a[b]', ['docs/images/missing.png']),
    (r'a\[b\]', []),
    (' ', []),
    ('', ['docs/images/missing.png']),
    ('undefined', []),
    ('x' * 999, []),
    ('x' * 1000, ['docs/images/missing.png']),
    ('<b>x</b>', []),
    ('`[x]`', ['docs/images/missing.png']),
    ('a![Inner](inner.png)', ['docs/images/missing.png', 'inner.png']),
])
def test_invalid_full_labels_fall_back_without_consuming_following_rendered_text(label, expected):
    text = f'![Shot][{label}]\n\n[Shot]: docs/images/missing.png\n'
    assert [source for _, source in images(text)] == expected


def test_escaped_bracket_definition_is_valid_but_nested_unescaped_definition_is_not():
    text = r'![Shot][a\[b\]]' + '\n\n' + r'[a\[b\]]: other.png' + '\n'
    assert images(text) == [('Shot', 'other.png')]
    text = '![Shot][a[b]]\n\n[Shot]: docs/images/missing.png\n[a[b]]: other.png\n'
    assert images(text) == [('Shot', 'docs/images/missing.png')]


def test_container_boundary_reports_real_missing_image_in_cli_linter(make_ctx, tmp_path):
    from ctshowcase import readme
    ctx = make_ctx(repo_dir=tmp_path)
    path = tmp_path / 'README.md'
    prefix = readme.scaffold(ctx, '') + '\n'
    missing = 'R7 local image does not resolve: docs/images/missing.png'
    for body in ['> [Docs\n> - ](url "' + IMAGE + '")\n',
                 '- Text <!--\n- \n' + IMAGE + ' -->\n',
                 '![Shot][a[b]]\n\n[Shot]: docs/images/missing.png\n']:
        path.write_text(prefix + body, encoding='utf-8')
        assert missing in readmelint.lint(ctx, path)['fails']
    path.write_text(prefix + '- Text <!--\n<span>\n> ' + IMAGE + ' -->\n', encoding='utf-8')
    assert missing not in readmelint.lint(ctx, path)['fails']


@pytest.mark.parametrize('code', [
    '    {image}\n',
    '\t{image}\n',
    '>     {image}\n',
    '-     {image}\n',
    '- Text\n\n      {image}\n',
    '> Text\n>\n>     {image}\n',
])
def test_indented_code_is_not_an_inline_region_or_rendered_image(code):
    text = code.format(image=IMAGE)
    assert images(text) == []
    html = code.format(image='<img alt="Shot" src="docs/images/missing.png">')
    assert images(html) == []
    assert mdcode.code_block_spans(text)
    assert mdcode.fence_spans(text) == ()  # preserve the fenced-only API


@pytest.mark.parametrize('prefix', ['', '- ', '> '])
def test_indentation_cannot_interrupt_a_live_paragraph(prefix):
    continuation = '  ' if prefix == '- ' else '> ' if prefix == '> ' else ''
    text = prefix + 'Text\n' + continuation + '    ' + IMAGE + '\n'
    assert images(text) == [('Shot', 'docs/images/missing.png')]
    assert not mdcode.code_block_spans(text)


def test_indented_marker_examples_never_become_managed_blocks():
    from ctshowcase.readme import MARK
    text = '    <!-- showcase:header:start -->\n    Example\n    <!-- showcase:header:end -->\n'
    assert mdcode.find_blocks(MARK, text) == []
    live = '\n<!-- showcase:header:start -->\nLive\n<!-- showcase:header:end -->\n'
    assert mdcode.find_blocks(MARK, text + live)


def test_indented_reference_example_does_not_define_a_live_label():
    text = '    [x]: docs/images/missing.png\n\n![Shot][x]\n'
    assert images(text) == []


@pytest.mark.parametrize('first,blank', [
    ('- Text ', '> '), ('- Text ', '> > '),
    ('- > Text ', '> '), ('- > Text ', '> > '),
    ('1. Text ', '> '), ('1. Text ', '  > '), ('1. Text ', '> > '),
    ('- - Text ', '> '), ('- - Text ', '> > '),
    ('2. > Text ', '> '), ('2. > Text ', '  > '), ('2. > Text ', '> > '),
    ('- > - Text ', '> '), ('- > - Text ', '> > '),
])
@pytest.mark.parametrize('opening,closing', [('<!--', ' -->'), ('`', '`')])
def test_empty_new_quote_does_not_reuse_indent_of_a_list_it_has_left(first, blank, opening, closing):
    text = first + opening + '\n' + blank + '\n    ' + IMAGE + closing + '\n'
    assert images(text) == []
    assert mdcode.code_block_spans(text)


@pytest.mark.parametrize('first,second', [
    ('Text ', '## Heading '),
    ('> Text ', '> - '),
    ('- > Text ', '  > - '),
    ('- Text ', '- '),
])
def test_html_attribute_cannot_hide_markup_in_a_new_source_block(first, second):
    text = first + '<span title="\n' + second + IMAGE + '\n">\n'
    assert images(text) == [('Shot', 'docs/images/missing.png')]
    html = first + '<span title="\n' + second + '<img alt="Shot" src="docs/images/missing.png">\n">\n'
    assert images(html) == [('Shot', 'docs/images/missing.png')]


@pytest.mark.parametrize('first,continuation', [('Text ', ''), ('> Text ', '> '), ('- Text ', '  ')])
def test_complete_html_attribute_with_soft_lines_remains_literal(first, continuation):
    text = first + '<span title="\n' + continuation + IMAGE + '\n' + continuation + '">\n'
    assert images(text) == []


def test_unclosed_raw_html_tag_does_not_consume_the_following_markdown_block():
    text = '<div title="\n\n' + IMAGE + '\n">\n'
    assert images(text) == [('Shot', 'docs/images/missing.png')]


def test_reference_destination_cannot_be_borrowed_from_a_new_container_block():
    assert images('![Shot][x]\n\n[x]:\n> - docs/images/missing.png\n') == []
    assert images('![Shot][x]\n\n[x]:\n  docs/images/missing.png\n') == [
        ('Shot', 'docs/images/missing.png')]


def test_invalid_next_block_title_does_not_discard_a_valid_reference_destination():
    text = '![Shot][x]\n\n[x]: docs/images/missing.png\n> - "title ' + IMAGE + '"\n'
    assert images(text) == [('Shot', 'docs/images/missing.png'), ('Shot', 'docs/images/missing.png')]
