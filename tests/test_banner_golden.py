"""Layout-mask comparison against the golden banner: card and chip masks IoU >= 0.90 (colours not compared, C-3)."""
import pytest
from PIL import Image

from conftest import EX, FIX, GOLDEN, ROOT, run_cli

pytestmark = pytest.mark.skipif(not GOLDEN.is_file(), reason="golden banner not present outside the handoff tree")


def _masks(im):
    px = im.load()
    card, chips = set(), set()
    for y in range(360):
        white = [x for x in range(500) if min(px[x, y]) > 235]
        if len(white) > 20:  # filled card silhouette: logo ink inside the card does not count
            card.update((x, y) for x in range(white[0], white[-1] + 1))
        for x in range(510, 1280):
            r, g, b = px[x, y]
            if 236 <= y <= 290 and 236 <= y <= 290 and ((r > 200 and g > 150 and b < 90) or (b > 180 and r < 80)):
                chips.add((x, y))
    return card, chips


def _fill_rows(m):
    """Chip silhouettes: fill each chip row between its coloured ends (chip text fonts differ from the golden)."""
    out, rows = set(), {}
    for x, y in m:
        rows.setdefault(y, []).append(x)
    for y, xs in rows.items():
        xs.sort()
        start = prev = xs[0]
        for x in xs[1:] + [10 ** 6]:
            if x - prev > 14:
                out.update((i, y) for i in range(start, prev + 1))
                start = x
            prev = x
    return out


def _iou(a, b):
    return len(a & b) / max(1, len(a | b))


def test_layout_matches_golden(tmp_path):
    out = tmp_path / "b.png"
    p = run_cli("--meta", FIX / "CompleTetech-Security__php2shell-check.json", "--repo-dir", EX / "repos" / "php2shell-check",
                "banner", "--out", out, "--icon", ROOT / "assets" / "brand" / "logo.png")  # the golden's white card
    assert p.returncode == 0, p.stderr
    ours = Image.open(out).convert("RGB").resize((1280, 360), Image.LANCZOS)
    gold = Image.open(GOLDEN).convert("RGB")
    c1, h1 = _masks(ours)
    c2, h2 = _masks(gold)
    card_iou = _iou(c1, c2)
    chip_iou = _iou(_fill_rows(h1), _fill_rows(h2))
    assert card_iou >= 0.90, card_iou
    assert chip_iou >= 0.90, chip_iou
