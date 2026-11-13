"""Intro identity and overflow regressions (#139)."""
import pytest

from conftest import run_cli


def test_foreign_intro_requires_own_mark_and_tagline(tmp_path):
    from PIL import Image
    out = tmp_path / "intro.svg"
    base = ("--format", "json", "intro", "--org", "Jev-Engineering", "--out", out)
    missing = run_cli(*base)
    assert missing.returncode == 4 and "needs-input:org-mark" in missing.stdout
    assert not out.exists()
    mark = tmp_path / "synthetic.png"
    Image.new("RGB", (64, 64), "red").save(mark)
    missing = run_cli(*base, "--mark", mark)
    assert missing.returncode == 4 and "needs-input:tagline" in missing.stdout
    assert not out.exists()
    rendered = run_cli(*base, "--mark", mark, "--tagline", "Synthetic example")
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    svg = out.read_text(encoding="utf-8")
    assert "Jev Engineering mark" in svg
    assert "CompleteTech" not in svg
    assert "Innovation at Every Integration" not in svg


@pytest.mark.parametrize("flag,code", [("--eyebrow", "intro-eyebrow"), ("--tagline", "intro-tagline")])
def test_intro_overflow_writes_nothing(tmp_path, flag, code):
    out = tmp_path / "intro.svg"
    result = run_cli("--format", "json", "intro", "--org", "CompleteTech-Data", "--out", out,
                     flag, "Unbreakable" * 300)
    assert result.returncode == 3
    assert f"art-fail:{code}" in result.stdout
    assert not out.exists()
