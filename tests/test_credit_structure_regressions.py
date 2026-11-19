"""Live credit delimiters must form one owned block before any README write."""
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT, meta_dict
from ctshowcase import footer, readme
from ctshowcase.errors import NeedsInput


def damaged_credit(brand, kind):
    credit = footer.credit_block(brand)
    return {
        "missing-start": credit.replace(footer.CREDIT_START, ""),
        "missing-end": credit.replace(footer.CREDIT_END, ""),
        "duplicate": credit + "\n\n" + credit,
        "nested-start": footer.CREDIT_START + "\n" + credit,
        "stray-end": credit + "\n" + footer.CREDIT_END,
        "reversed": footer.CREDIT_END + "\n" + footer.CREDIT_START,
    }[kind]


@pytest.mark.parametrize("kind", ["missing-start", "missing-end", "duplicate", "nested-start", "stray-end", "reversed"])
def test_malformed_credit_is_not_generation_or_lint_evidence(brand, kind):
    text = "# Synthetic\n\n" + damaged_credit(brand, kind) + "\n\n" + footer.footer_block(brand) + "\n"
    with pytest.raises(NeedsInput, match="ownership"):
        readme.guard_credit_ownership(brand, text)
    assert footer.check(brand, text)[0] == "fail:credit-drift"


@pytest.mark.parametrize("example", [
    "```html\n<!-- showcase:credit:start -->\n```",
    "    <!-- showcase:credit:end -->",
    "`<!-- showcase:credit:start -->`",
    '<span title="<!-- showcase:credit:end -->">Literal attribute</span>',
    '<script>const example = "<!-- showcase:credit:start -->";</script>',
    '<!-- Documentation example: <!-- showcase:credit:end -->',
    '![Screenshot <!-- showcase:credit:start -->](diagram.svg)',
    '![Screenshot <!-- showcase:credit:end -->](diagram.svg)',
    '![Screenshot <!-- showcase:credit:start -->][shot]\n\n[shot]: diagram.svg',
    '![Screenshot <!-- showcase:credit:end -->][shot]\n\n[shot]: diagram.svg',
])
def test_inert_delimiter_examples_do_not_claim_a_credit_block(brand, example):
    text = "# Synthetic\n\n" + example + "\n\n" + footer.block(brand) + "\n"
    readme.guard_credit_ownership(brand, text)
    assert footer.check(brand, text)[0] == "pass"


@pytest.mark.parametrize("form", ["inline", "reference"])
@pytest.mark.parametrize("delimiter", [footer.CREDIT_START, footer.CREDIT_END])
def test_literal_image_does_not_hide_an_actual_neighboring_credit_delimiter(brand, form, delimiter):
    image = "![Screenshot " + delimiter + "]" + (
        "(diagram.svg)" if form == "inline" else "[shot]\n\n[shot]: diagram.svg")
    text = image + "\n\n" + delimiter + "\n\n" + footer.block(brand) + "\n"
    with pytest.raises(NeedsInput, match="ownership"):
        readme.guard_credit_ownership(brand, text)
    assert footer.check(brand, text)[0] == "fail:credit-drift"


@pytest.mark.parametrize("kind", ["missing-start", "missing-end", "duplicate"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("mode", ["header", "upgrade"])
def test_cli_refuses_ambiguous_credit_without_changing_any_file(brand, tmp_path, kind, newline, mode):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    text = "# Synthetic authored notes\n\n" + damaged_credit(brand, kind) + "\n\n" + footer.footer_block(brand) + "\n"
    (checkout / "README.md").write_bytes(b"\xef\xbb\xbf" + text.replace("\n", newline).encode())
    (checkout / "authored.txt").write_bytes(b"Keep these synthetic authored bytes.\n")
    estate = tmp_path / "empty-estate"
    (estate / "decisions").mkdir(parents=True)
    env = dict(os.environ, SHOWCASE_ESTATE_ROOT=str(estate), SHOWCASE_STATE_DIR=str(tmp_path / "state"),
               SHOWCASE_NO_STAR_PROMPT="1", PYTHONDONTWRITEBYTECODE="1")
    # The subprocess exercises the real CLI with supplied metadata. Any attempt
    # to read a live API is a test failure, not an available fallback.
    bootstrap = """import os, runpy, socket, subprocess, sys
from pathlib import Path
def blocked(*args, **kwargs):
    raise AssertionError('Network transport is unavailable in this synthetic test')
socket.create_connection = blocked
socket.socket.connect = blocked
real_popen = subprocess.Popen
class OfflinePopen(real_popen):
    def __init__(self, args, *a, **kw):
        command = args[0] if isinstance(args, (list, tuple)) else args.split()[0]
        if Path(os.fsdecode(command)).name.lower() in ('gh', 'gh.exe', 'gh.cmd'):
            blocked()
        super().__init__(args, *a, **kw)
subprocess.Popen = OfflinePopen
script = Path(sys.argv.pop(1))
sys.path.insert(0, str(script.parent))
runpy.run_path(str(script), run_name='__main__')
"""
    before = {p.relative_to(checkout): p.read_bytes() for p in checkout.rglob("*") if p.is_file()}
    result = subprocess.run([sys.executable, "-c", bootstrap, str(ROOT / "scripts/showcase.py"),
                             "--meta", str(meta), "--repo-dir", str(checkout), "--format", "json",
                             "readme", "--mode", mode, "--write"], cwd=ROOT, env=env,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 4, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "readme"
    assert "needs-input:credit-ownership" in payload["logs"]
    assert {p.relative_to(checkout): p.read_bytes() for p in checkout.rglob("*") if p.is_file()} == before
