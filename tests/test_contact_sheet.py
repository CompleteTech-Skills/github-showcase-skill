from PIL import Image

from conftest import ROOT, run_cli

EXA = ROOT / "assets" / "examples"


def test_stack_and_grid(tmp_path):
    p = run_cli("contact-sheet", EXA / "banner-php2shell.png", "--mode", "stack", "--widths", "1012,390", "--out", tmp_path / "s.png")
    assert p.returncode == 0, p.stderr
    dark = Image.open(tmp_path / "s.on-github-dark.png").convert("RGB")
    light = Image.open(tmp_path / "s.on-github-light.png").convert("RGB")
    assert dark.getpixel((2, 2)) == (13, 17, 23) and light.getpixel((2, 2)) == (255, 255, 255)
    assert dark.width == 24 + 1012 + 24
    p = run_cli("contact-sheet", EXA / "card-example.svg", EXA / "card-jev-minesweeper.svg", "--cols", "2", "--out", tmp_path / "g.png")
    assert p.returncode == 0 and Image.open(tmp_path / "g.on-github-dark.png").width == 24 + 2 * (400 + 24)


def test_avatar_masks_and_svg_without_preview(tmp_path):
    av = tmp_path / "a.png"
    Image.new("RGB", (500, 500), (0, 31, 63)).save(av)
    p = run_cli("contact-sheet", av, "--mode", "avatar", "--mask", "circle", "--out", tmp_path / "av.png")
    assert p.returncode == 0
    im = Image.open(tmp_path / "av.on-github-light.png").convert("RGB")
    assert im.getpixel((24, 24)) == (255, 255, 255)  # circle corner shows the page
    (tmp_path / "x.svg").write_text("<svg")  # no PNG sibling and not renderable: usage error, never a traceback
    assert run_cli("contact-sheet", tmp_path / "x.svg", "--out", tmp_path / "x.png").returncode == 2
