import re

from ctshowcase import svglint
from conftest import run_cli


def test_animated_profile(tmp_path):
    out = tmp_path / "i.svg"
    assert run_cli("intro", "--profile", "CompleteDotTech", "--out", out).returncode == 0
    s = out.read_text()
    assert ".still" in s and "prefers-reduced-motion" in s
    assert svglint.lint_file("intro", out)["result"] == "PASS"
    assert list(tmp_path.iterdir()) == [out]  # exactly one file, no -dark sibling


def test_static_and_height(tmp_path):
    out = tmp_path / "s.svg"
    assert run_cli("intro", "--org", "CompleteTech-Data", "--height", "360", "--out", out).returncode == 0
    s = out.read_text()
    assert "@keyframes" not in s and "<animate" not in s
    assert 'viewBox="0 0 1280 360"' in s
    assert svglint.lint_file("intro", out)["result"] == "PASS"
    assert not re.search(r"<text\b", s)
