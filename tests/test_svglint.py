from pathlib import Path

import pytest

from ctshowcase.svglint import lint_bytes, lint_file

PROTO = Path(__file__).resolve().parents[2] / "showcase" / "prototypes"
OK_CARD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 160" width="400" height="160" role="img" aria-label="x: y">'
           '<title>x: y</title><rect width="400" height="160" fill="#000"/></svg>')


@pytest.mark.skipif(not PROTO.is_dir(), reason="prototypes live outside the package")
@pytest.mark.parametrize("name,kind", [("completedottech-intro-dark.svg", "intro"), ("repo-card-example-dark.svg", "card")])
def test_prototypes_pass(name, kind):
    r = lint_bytes(kind, (PROTO / name).read_bytes(), name)
    assert r["result"] == "PASS", r["fails"]


def test_ok_card():
    assert lint_bytes("card", OK_CARD.encode())["result"] == "PASS"


NEG = {
    "S01": OK_CARD.replace("</svg>", ""),
    "S02": OK_CARD.replace('viewBox="0 0 400 160"', 'viewBox="0 0 400 150"'),
    "S03": OK_CARD.replace("<title>", "<!-- a -- b --><title>"),
    "S05 banned": OK_CARD.replace("</svg>", "<script>1</script></svg>"),
    "S05a": OK_CARD.replace("</svg>", "<text>x</text></svg>"),
    "S05d": OK_CARD.replace("</svg>", '<image href="https://x/y.png" width="1" height="1"/></svg>'),
    "S06": OK_CARD.replace("</svg>", '<line x1="0" x2="9" y1="1" y2="1" stroke="url(#g)"/></svg>'),
    "S10": OK_CARD.replace("</svg>", "<desc>" + "x" * 41000 + "</desc></svg>"),
    "S11": OK_CARD.replace("</svg>", '<circle r="1"><animate attributeName="r" dur="5s" values="1;2" repeatCount="indefinite"/></circle></svg>'),
    "S30": OK_CARD.replace("<title>x: y</title>", "<title>other</title>"),
    "S08": OK_CARD.replace('aria-label="x: y"', 'aria-label="x ★"').replace("<title>x: y</title>", "<title>x ★</title>"),
}


@pytest.mark.parametrize("rule", sorted(NEG))
def test_negative(rule):
    r = lint_bytes("card", NEG[rule].encode())
    assert r["result"] == "FAIL" and any(f.startswith(rule.split()[0]) for f in r["fails"]), r["fails"]


def test_intro_rules():
    base = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 320" width="1280" height="320" role="img" aria-label="a">'
            '<title>a</title><style>.d{animation:x 1s}</style><g class="d"/></svg>')
    fails = lint_bytes("intro", base.encode())["fails"]
    assert any(f.startswith("S20") for f in fails) and any(f.startswith("S21") for f in fails)
    fast = base.replace('<g class="d"/>', '<circle r="1"><animate attributeName="r" dur="2s" values="1;2" repeatCount="indefinite"/></circle>')
    assert any(f.startswith("S13") for f in lint_bytes("intro", fast.encode())["fails"])


def test_d21_pair(tmp_path):
    (tmp_path / "card.svg").write_text(OK_CARD)
    (tmp_path / "card-dark.svg").write_text(OK_CARD)
    assert "D21" in " ".join(lint_file("card", tmp_path / "card-dark.svg")["fails"])
