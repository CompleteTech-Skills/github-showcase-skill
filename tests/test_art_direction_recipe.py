"""E3.4.1: the Codex image-generation recipe in references/art-direction.md (doc contract, no behaviour)."""
import re

from conftest import ROOT

ART = ROOT / "references" / "art-direction.md"
HEAD = "## Codex image-generation recipe"
GLYPH = "## Repository glyph prompt template"


def _text():
    return ART.read_text(encoding="utf-8")


def _recipe(text):
    start = text.find(HEAD)
    if start < 0:
        return ""
    body = text[start + len(HEAD):]
    m = re.search(r"^## ", body, re.M)
    return HEAD + body[: m.start()] if m else HEAD + body


def test_recipe_section_exists_before_glyph_template():
    text = _text()
    assert text.count(HEAD) == 1, "recipe heading must appear exactly once"
    assert text.find(HEAD) < text.find(GLYPH)
    assert _recipe(text), "recipe section not found"


def test_recipe_has_codex_exec_command():
    section = _recipe(_text())
    assert "codex exec" in section
    assert "--json" in section
    assert "--skip-git-repo-check" in section
    fence = re.search(r"```bash\n(.*?)```", section, re.S)
    assert fence, "command must sit in a ```bash fence"
    assert "codex exec" in fence.group(1)
    assert "--json" in fence.group(1)
    assert "--skip-git-repo-check" in fence.group(1)


def test_recipe_reads_path_from_run_output_not_newest():
    lowered = _recipe(_text()).lower()
    assert "never pick the newest" in lowered
    assert "run output" in lowered


def test_recipe_retry_limit():
    section = _recipe(_text())
    assert "2 retries" in section
    assert "3 attempts" in section


def test_recipe_has_no_local_paths():
    section = _recipe(_text())
    assert not re.search(r"[A-Za-z]:\\Users|/home/|/Users/", section)


def test_existing_sections_intact():
    text = _text()
    for heading in ("## Prompt template for illustrations", GLYPH, "## Pipeline rules (MUST)"):
        assert text.count(heading) == 1, heading
