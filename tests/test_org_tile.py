from ctshowcase import svglint
from conftest import EX, run_cli


def test_tile(tmp_path):
    out = tmp_path / "t.svg"
    p = run_cli("org-tile", "--org", "CompleteTech-Skills", "--avatar", EX / "orgs/CompleteTech-Skills/avatar-500.png",
                "--out", out, "--png", tmp_path / "t.png")
    assert p.returncode == 0, p.stderr
    r = svglint.lint_file("tile", out)
    assert r["result"] == "PASS", r
    assert not any(ch.isdigit() for ch in out.read_text().split("<title>")[1].split("</title>")[0])
