"""Shared scanners recognize Markdown endings while retaining authored offsets."""
import hashlib
import json

import pytest

from ctshowcase import mdcode, readme, readmelint
from conftest import run_cli


ENDINGS = ['\n', '\r\n', '\r']
IMAGE = '![Shot](docs/images/missing.png)'
# Each expectation describes rendered images, rather than overall README validity.
CASES = [
    ('text ![Shot </span\n>](docs/images/missing.png)', False),
    (IMAGE, True),
    ('![Shot\ncontinued](docs/images/missing.png)', True),
    ('![Shot\n\ncontinued](docs/images/missing.png)', False),
    ('```md\n' + IMAGE + '\n```\n', False),
    ('> ```md\n> ' + IMAGE + '\n> ```\n', False),
    ('- > ```md\n  > ' + IMAGE + '\n  > ```\n', False),
    ('- x\n  ```md\n  hidden\n' + IMAGE, True),
    ('    ' + IMAGE + '\n', False),
    ('`code\n' + IMAGE + '`', False),
    ('`code\n# heading\n' + IMAGE + '`', True),
    ('<div>\n' + IMAGE + '\n\n', False),
    ('<div>\nhidden\n\n' + IMAGE, True),
    ('> <div>\n> hidden\n\n' + IMAGE, True),
    ('text <span title="soft\n' + IMAGE + '">', False),
    ('text <!-- soft\n' + IMAGE + ' -->', False),
    ('text <!-- blank\n\n' + IMAGE + ' -->', True),
    ('[docs](x "blank\n\n' + IMAGE + '")', True),
    ('[docs](x "soft\n' + IMAGE + '")', False),
    ('![Shot][shot]\n\n[shot]: docs/images/missing.png\n', True),
    ('![Shot][shot]\n\n[other]: x\n[shot]: docs/images/missing.png\n', True),
    ('![Shot][shot]\n\n> [shot]: docs/images/missing.png\n', True),
    ('![Shot][shot]\n\n- item\n  [shot]: docs/images/missing.png\n', False),
    ('![Shot][shot]\n\n- item\n\n  [shot]: docs/images/missing.png\n', True),
    ('![Shot][shot]\n\n```md\n[shot]: docs/images/missing.png\n```\n', False),
    ('![Shot][shot]\n\n<div>\n[shot]: docs/images/missing.png\n\n', False),
    ('![Shot][soft label]\n\n[soft\nlabel]: docs/images/missing.png\n', True),
    ('![Shot](<docs/images/missing\n.png>)', False),
]


@pytest.mark.parametrize('ending', ENDINGS)
@pytest.mark.parametrize('template, renders', CASES)
def test_shared_image_semantics(template, renders, ending):
    source = template.replace('\n', ending)
    found = readmelint._images(readmelint._outside_code(source), source)
    assert bool(found) is renders
    if renders:
        assert len(found) == 1
        assert found[0][1] == 'docs/images/missing.png'


@pytest.mark.parametrize('ending', ENDINGS)
@pytest.mark.parametrize('template, renders', CASES)
def test_actual_lint_reports_only_rendered_missing_images(tmp_path, ending, template, renders):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    authored = ('# Probe\n\n' + template).replace('\n', ending).encode()
    path.write_bytes(authored)
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert result.returncode == 1  # this minimal fixture intentionally lacks the required scaffold
    failures = json.loads(result.stdout)['fails']
    assert ('R7 local image does not resolve: docs/images/missing.png' in failures) is renders
    assert path.read_bytes() == authored


@pytest.mark.parametrize('ending', ENDINGS)
def test_reference_and_mask_offsets_index_original_source(ending):
    source = ('```md\n' + IMAGE + '\n```\n\n> [shot]: docs/images/missing.png\n\n![Shot][shot]\n').replace('\n', ending)
    for masked in (mdcode.masked(source), readmelint._outside_code(source), readmelint._definition_candidates(source)):
        assert len(masked) == len(source)
        assert [(i, c) for i, c in enumerate(masked) if c in '\r\n'] == [
            (i, c) for i, c in enumerate(source) if c in '\r\n']
    definition, = readmelint._definitions(source)
    assert source[definition.start():definition.end()] == '> [shot]: docs/images/missing.png'
    assert source[slice(*definition.span(3))] == 'docs/images/missing.png'
    image, = readmelint._markdown_images(readmelint._outside_code(source), source)
    assert source[image[2]:image[3]] == '![Shot][shot]'


def test_mixed_endings_and_unicode_separators_retain_source_lines():
    source = 'a\r\nb\rc\nd\v\f\x85\u2028\u2029'
    assert list(mdcode.source_lines(source)) == ['a\r\n', 'b\r', 'c\n', 'd\v\f\x85\u2028\u2029']
    assert readmelint._blank_line_starts('a\r\nb') == ()
    assert readmelint._blank_line_starts('a\r\n\rb') == (1,)
    assert readmelint._blank_line_starts('a\r\r\nb') == (1,)


@pytest.mark.parametrize('ending', ENDINGS)
def test_marker_search_preserves_authored_group_bytes_and_excludes_code(ending):
    marker = '<!-- showcase:nav:start -->\nAuthored text  \n<!-- showcase:nav:end -->'
    source = ('```md\n' + marker + '\n```\n\n' + marker + '\n').replace('\n', ending)
    found = mdcode.find_blocks(readme.MARK, source)
    assert len(found) == 1
    assert found[0].group() == marker.replace('\n', ending)
    assert source[found[0].start():found[0].end()].encode() == found[0].group().encode()
    # Replacing the real managed span leaves every other authored byte intact.
    prefix = source[:found[0].start()]
    assert prefix == ('```md\n' + marker + '\n```\n\n').replace('\n', ending)


@pytest.mark.parametrize('ending', ENDINGS)
def test_boundary_helper_advances_over_the_complete_line_ending(ending):
    source = 'text' + ending + '# heading'
    for index in range(4, 4 + len(ending)):
        assert readmelint._block_boundary(source, index, ()) is True


@pytest.mark.parametrize('ending', ENDINGS)
def test_rejected_comments_remain_bounded_across_line_endings(ending):
    counts = []
    for n in (100, 400):
        source = ('text <!--' + ending * 2) * n + '-->' + ending * 2 + IMAGE
        mdcode.WORK.clear()
        assert readmelint._images(readmelint._outside_code(source), source) == [('Shot', 'docs/images/missing.png')]
        counts.append(mdcode.WORK['comment_scan_chars'])
        assert 0 < counts[-1] <= 9 * len(source)
    assert counts[1] <= 4.1 * counts[0]


@pytest.mark.parametrize('ending', ENDINGS)
def test_readme_plan_does_not_rewrite_authored_line_endings(tmp_path, ending):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    authored = ('# Probe\n\n```md\n<!-- showcase:nav:start -->\nExample\n'
                '<!-- showcase:nav:end -->\n```\n\nAuthored text  \n').replace('\n', ending).encode()
    path.write_bytes(authored)
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', 'header')
    assert result.returncode in (0, 1), result.stderr
    assert json.loads(result.stdout)['command'] == 'readme'
    assert path.read_bytes() == authored


@pytest.mark.parametrize('ending', ENDINGS)
@pytest.mark.parametrize('bom', [b'', b'\xef\xbb\xbf'], ids=['without-bom', 'with-bom'])
def test_readme_write_preserves_authored_line_endings(tmp_path, ending, bom):
    # #160: `readme --write` refreshes a managed block without rewriting the
    # README's authored CRLF or lone-CR endings as LF.
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    authored = ('# Probe\n\n<!-- showcase:badges:start -->\n<!-- showcase:badges:end -->\n\n'
                'Authored text  \nMore\n').replace('\n', ending)
    authored_bytes = bom + authored.encode()
    path.write_bytes(authored_bytes)
    plan = tmp_path / 'plan.jsonl'
    changes = tmp_path / 'changes.jsonl'
    command = ('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', 'header')
    planned = run_cli(*command, '--records', plan)
    assert json.loads(planned.stdout)['diff'].startswith('--- a/README.md')
    assert path.read_bytes() == authored_bytes
    result = run_cli(*command, '--write', '--records', changes)
    assert result.returncode in (0, 1), result.stderr
    assert json.loads(result.stdout)['written'] is True
    written_bytes = path.read_bytes()
    assert written_bytes.startswith(b'\xef\xbb\xbf') is bool(bom)
    record = json.loads(plan.read_text(encoding='utf-8'))
    assert record == json.loads(changes.read_text(encoding='utf-8'))
    assert record['before_sha256'] == hashlib.sha256(authored_bytes).hexdigest()
    assert record['after'].encode('utf-8') == written_bytes
    written = written_bytes[len(bom):].decode()
    assert '![Type GitHub profile]' in written
    assert written.endswith(('\n\nAuthored text  \nMore\n').replace('\n', ending))
    # every line ending in the written file is the authored one
    assert written.count(ending) == written.replace('\r\n', '\n').replace('\r', '\n').count('\n')
    again = run_cli('--meta', meta, '--repo-dir', tmp_path, 'readme', '--write', '--mode', 'header')
    assert json.loads(again.stdout)['result'] == 'unchanged'
    assert path.read_bytes() == written_bytes


def test_restore_line_endings_keeps_each_unchanged_line_ending():
    raw = '# Probe\r\n\rold\nkept\r\nlast'
    before = '# Probe\n\nold\nkept\nlast'
    after = '# Probe\n\nnew\nadded\nkept\nlast'
    assert readme.restore_line_endings(raw, before, after) == '# Probe\r\n\rnew\r\nadded\r\nkept\r\nlast'
    assert readme.restore_line_endings('a\nb\n', 'a\nb\n', 'a\nc\n') == 'a\nc\n'



def test_restore_line_endings_preserves_paragraph_after_lone_cr():
    raw = 'A\rB\nC\n'
    after = 'A\n\nB\nC\n'
    restored = readme.restore_line_endings(raw, readme.normalize_text(raw), after)
    assert restored == 'A\r\r\nB\nC\n'
    assert readme.normalize_text(restored) == after



def test_restore_line_endings_preserves_moved_authored_lines():
    raw = 'top\n## License\nold\n## About\nabout\r\n'
    after = 'top\n## About\nabout\n## License\nold\n'
    restored = readme.restore_line_endings(raw, readme.normalize_text(raw), after)
    assert restored == 'top\n## About\nabout\r\n## License\nold\n'



def test_restore_line_endings_pairs_repeated_rows_in_occurrence_order():
    raw = 'start\n' + 'repeat\rrepeat\r\nrepeat\n' * 20_000 + 'end\n'
    after = 'new start\n' + 'repeat\n' * 60_000 + 'new end\n'
    restored = readme.restore_line_endings(raw, readme.normalize_text(raw), after)
    assert restored == raw.replace('start', 'new start').replace('end', 'new end')


def test_restore_line_endings_uses_context_for_surviving_duplicate():
    raw = 'start\rshared\r\nmanaged anchor\nshared\rauthored anchor\nend\n'
    after = 'start\nchanged\nmanaged anchor\nshared\nauthored new\nend\n'
    restored = readme.restore_line_endings(raw, readme.normalize_text(raw), after)
    assert '\nmanaged anchor\nshared\rauthored new\n' in restored


def test_restore_line_endings_keeps_authored_copy_of_new_nav_row():
    raw = '<!-- showcase:nav:start -->\nold nav\n<!-- showcase:nav:end -->\n\nrow\r\n\nnext\n'
    after = readme.normalize_text(raw).replace('old nav', 'row')
    restored = readme.restore_line_endings(raw, readme.normalize_text(raw), after)
    assert restored == raw.replace('old nav', 'row')


@pytest.mark.parametrize('ending', ENDINGS)
def test_markup_on_managed_comment_line_is_not_a_rendered_markdown_image(tmp_path, ending):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    line = '<!-- showcase:badges:start -->![Shot](missing.png)<!-- showcase:badges:end -->'
    path.write_bytes(('# Probe\n\n' + line + '\n').replace('\n', ending).encode('utf-8'))
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert 'R7 local image does not resolve: missing.png' not in json.loads(result.stdout)['fails']
    path.write_bytes(('# Probe\n\n' + line.replace('-->![', '-->\n![').replace('png)<!--', 'png)\n<!--') + '\n')
                     .replace('\n', ending).encode('utf-8'))
    control = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    assert 'R7 local image does not resolve: missing.png' in json.loads(control.stdout)['fails']


@pytest.mark.parametrize('ending', ENDINGS)
def test_dry_run_patch_applies_to_original_readme_bytes(tmp_path, ending):
    import shutil
    import subprocess

    git = shutil.which('git')
    if not git:
        pytest.skip('Git is required to verify application of the unified diff')
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    original = ('\ufeff# Probe\n\n<!-- showcase:badges:start -->\n<!-- showcase:badges:end -->\n\n'
                'Authored text without final newline').replace('\n', ending).encode('utf-8')
    path.write_bytes(original)
    args = ('--meta', meta, '--repo-dir', tmp_path, 'readme', '--mode', 'header')
    plan = run_cli(*args)
    assert plan.returncode in (0, 1), plan.stderr
    patch = tmp_path / 'plan.patch'
    patch.write_bytes(json.loads(plan.stdout)['diff'].encode('utf-8'))
    written = run_cli(*args, '--write')
    assert json.loads(written.stdout)['written']
    expected = path.read_bytes()
    path.write_bytes(original)
    # Test patch bytes independently of the Git installation's working-tree EOL policy.
    git_apply = [git, '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'apply', '--whitespace=nowarn']
    applied = subprocess.run([*git_apply, str(patch)], cwd=tmp_path, capture_output=True)
    assert applied.returncode == 0, applied.stderr
    assert path.read_bytes() == expected


def test_bare_reference_controls_check_visible_images_and_palette(tmp_path):
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'owner': 'Northwind-Trading-Co', 'repo': '.github',
                                'license': 'MIT', 'files': ['README.md']}), encoding='utf-8')
    path = tmp_path / 'README.md'
    source = ('# Probe\n\n![Shot][x] ![Badge][y]\n\n'
              '[x]: docs/miss\x01ing.png\n[y]: https://img.shields.io/badge/type-a\x01-FF0000\n')
    path.write_bytes(source.encode('utf-8'))
    result = run_cli('--meta', meta, '--repo-dir', tmp_path, 'lint', 'readme', path)
    failures = json.loads(result.stdout)['fails']
    assert 'R7 local image does not resolve: docs/miss%01ing.png' in failures
    assert 'R7 off-palette badge colour FF0000' in failures


def test_readme_upgrade_keeps_mixed_endings_with_reordered_identical_sections(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    raw = (b"# Probe\n\n## Files\n\nShared above\nRepeated line\rShared below\n\n"
           b"## About\n\nShared above\nRepeated line\r\nShared below\n")
    path.write_bytes(raw)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    written = path.read_bytes()
    assert b"## About\n\nShared above\nRepeated line\r\nShared below" in written
    assert b"## Files\n\nShared above\nRepeated line\rShared below" in written
    assert written.index(b"## About") < written.index(b"## Files")


@pytest.mark.parametrize("tag", ["script", "style", "textarea", "title"])
@pytest.mark.parametrize("ending", ENDINGS)
def test_markers_in_raw_html_text_are_authored(tag, ending):
    marker = readme.wrap("badges", "authored example")
    inside = f"<{tag}>\n{marker}\n</{tag}>"
    ordinary = f"<div>\n{readme.wrap('tagline', 'real marker')}\n</div>"
    text = f"{inside}\n\n{ordinary}".replace("\n", ending)
    assert [block.group(1) for block in mdcode.find_blocks(readme.MARK, text)] == ["tagline"]


@pytest.mark.parametrize("ending", ENDINGS)
def test_readme_write_does_not_rewrite_markers_inside_textarea(tmp_path, ending):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    example = "<textarea>\n" + readme.wrap("badges", "") + "\n</textarea>"
    raw = ("# Probe\n\n" + example + "\n").replace("\n", ending).encode("utf-8")
    path.write_bytes(raw)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert raw in path.read_bytes()
    assert b"showcase:badges:generated" not in path.read_bytes()


@pytest.mark.parametrize("ending", ENDINGS)
def test_unclosed_raw_text_in_quote_does_not_hide_later_managed_block(tmp_path, ending):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    quote = "# Probe\n\n> <script>\n> authored raw text\n\n"
    raw = (quote + readme.wrap("badges", "") + "\n").replace("\n", ending).encode("utf-8")
    path.write_bytes(raw)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    written = path.read_bytes()
    assert written.startswith(quote.replace("\n", ending).encode("utf-8"))
    assert b"![Type GitHub profile]" in written and b"![License MIT]" in written


def test_managed_marker_expansion_keeps_the_authored_lf_blank(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    original = (b"# Probe\r\r<!-- showcase:badges:start --><!-- showcase:badges:end -->"
                b"\r\n\nAuthored A\rAuthored B\rAuthored C\r")
    path.write_bytes(original)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes().endswith(b"<!-- showcase:badges:end -->\r\n\nAuthored A\rAuthored B\rAuthored C\r")


@pytest.mark.parametrize("ending", ENDINGS)
def test_readme_upgrade_retains_non_markdown_separators(tmp_path, ending):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    authored = "Authored A\u2028and B\u2029and C\u0085and D\vwith final separator\u2028"
    raw = ("# Probe\n\n## About\n\n" + authored + "\n").replace("\n", ending).encode("utf-8")
    path.write_bytes(raw)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (authored + ending).encode("utf-8") in path.read_bytes()


@pytest.mark.parametrize("ending", ENDINGS)
def test_authored_license_marker_examples_in_textarea_are_never_rewritten(tmp_path, ending):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md", "LICENSE"]}), encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Synthetic license file.", encoding="utf-8")
    path = tmp_path / "README.md"
    example = "<textarea>\n" + readme.managed_license("This is authored demonstration text.") + "\n</textarea>"
    live = readme.managed_license("Old generated license prose.")
    path.write_bytes(("# Probe\n\n" + example + "\n\n## License\n\n" + live + "\n")
                     .replace("\n", ending).encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert example.replace("\n", ending).encode("utf-8") in path.read_bytes()
    assert b"Old generated license prose." not in path.read_bytes()


def test_lead_reorder_cannot_modify_indented_marker_examples(make_ctx):
    ctx = make_ctx()
    assert not readme.nav_first(ctx)
    example = readme.wrap("nav", "sample") + "\n\n" + readme.wrap("banner", "sample")
    authored = "\n".join("    " + line for line in example.split("\n"))
    assert readme.reorder_lead(ctx, authored) == authored


@pytest.mark.parametrize("ending", ENDINGS)
def test_markers_inside_other_html_comments_cannot_authorize_a_write(tmp_path, ending):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    authored = ("<!-- Outer documentation comment with a specimen opener:\n"
                "<!-- showcase:nav:start -->\n"
                "Authored navigation prose.\n<!-- showcase:nav:end -->")
    genuine = readme.wrap("badges", "")
    raw = ("# Probe\n\n" + authored + "\n\n" + genuine + "\n").replace("\n", ending)
    path.write_bytes(raw.encode("utf-8"))
    assert [block.group(1) for block in mdcode.find_blocks(readme.MARK, raw)] == ["badges"]
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    written = path.read_bytes()
    assert authored.replace("\n", ending).encode("utf-8") in written
    assert b"![Type GitHub profile]" in written


def test_escaped_closing_comment_is_not_a_real_marker():
    example = "<!-- showcase:nav:start -->\n\nAuthored paragraph.\n\\<!-- showcase:nav:end -->\n"
    assert not mdcode.find_blocks(readme.MARK, example)


def test_readme_header_preserves_escaped_marker_examples(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    literal = (b"# Probe\r\r\\<!-- showcase:nav:start -->\rAuthored marker example should stay."
               b"\r\\<!-- showcase:nav:end -->\r\rAfter.\r")
    path.write_bytes(literal)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == literal


@pytest.mark.parametrize("existing_block", [False, True])
def test_readme_header_keeps_an_authored_bom_after_the_encoding_bom(tmp_path, existing_block):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    prefix = b"\xef\xbb\xbf\xef\xbb\xbf# Authored\r"
    original = prefix + (("\r" + readme.wrap("badges", "").replace("\n", "\r") + "\r").encode()
                         if existing_block else b"")
    path.write_bytes(original)
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes().startswith(prefix)
    if existing_block:
        assert b"![Type GitHub profile]" in path.read_bytes()
    else:
        assert path.read_bytes() == original


def test_unmatched_managed_openers_do_not_rescan_the_remaining_document():
    import subprocess
    import sys

    from conftest import ROOT

    probe = """
import sys
sys.path.insert(0, sys.argv[1])
from ctshowcase import mdcode, readme
text = (readme.start("nav") + "\\n") * 10000
assert mdcode.find_blocks(readme.MARK, text) == []
assert [m.group(1) for m in mdcode.find_blocks(readme.MARK, text + readme.wrap("tagline", "A live row."))] == ["tagline"]
"""
    result = subprocess.run([sys.executable, "-c", probe, str(ROOT / "scripts")],
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bootstrap_preserves_the_authored_bom_prefix(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": ".github",
                                "license": "MIT", "files": ["README.md"]}), encoding="utf-8")
    path = tmp_path / "README.md"
    authored_title = "\ufeff\ufeff# Authored"
    original = (authored_title + "\n\n" + readme.wrap("tagline", "Old generated tagline.") + "\n\n---\n\n"
                + readme.pristine_block("## Install\n\nPlaceholder.") + "\n")
    path.write_bytes(original.encode("utf-8"))
    result = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--bootstrap", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes().startswith((authored_title + "\n").encode("utf-8"))
