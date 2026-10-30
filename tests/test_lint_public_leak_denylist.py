"""E6.2.3: `lint public-leak --denylist FILE` tests with a synthetic denylist.

Every name here is synthetic (organisation `Northwind-Trading-Co`, repositories `northwind-secret-ledger` and
`Northwind-Trading-Co/private-pricing-engine`). No real private repository, organisation or e-mail is used, and no
test reads a private registry: the registry-free runs point SHOWCASE_ESTATE_ROOT at an empty directory and the
bootstrap below removes the sibling-estate fallback, so only the explicit synthetic root can be seen.

Baseline note (E6 review, check 3): the `--denylist` behaviour under test was added before this file (051c559,
E6.2.1), and this file lands with no production change (E6.2.3). These are characterization tests that pin the
existing behaviour, so they are expected to PASS on the base 8373122 too. Verified by exporting 8373122 to a temp
directory, copying this file in and running it: 13 passed. A regression in the denylist path is what they catch;
they do not demonstrate a new feature.

Non-vacuity evidence (E6.2.3 review, check 3): 051c559 is an ancestor of base 8373122, so the feature is already on
the base. To confirm these tests are not vacuous, three mutations of ctshowcase/org.py were each run against a scratch
copy of HEAD and each made this file fail (1 failed, 12 passed): dropping the bare-name word boundary in
denylist_leaks, dropping the `#` comment stripping in load_denylist, and returning an empty list instead of
needs-input for an empty denylist.
"""
import json
import os
import subprocess
import sys

from conftest import ROOT
from ctshowcase import org as O
from ctshowcase.errors import CHECK_FAILED, NEEDS_INPUT, OK, USAGE

ORG = "Northwind-Trading-Co"
SLUG = f"{ORG}/private-pricing-engine"
ESTATE = ROOT / "examples" / "estate"

# Same bootstrap as tests/test_org_registry_free.py cli(): the estate-candidates fallback returns nothing.
BOOTSTRAP = """import runpy, sys
from pathlib import Path
script = Path(sys.argv.pop(1))
sys.path.insert(0, str(script.parent))
import ctshowcase
ctshowcase.estate_candidates = lambda: []
from ctshowcase import resolver
resolver.estate_candidates = lambda: []
runpy.run_path(str(script), run_name="__main__")
"""


def _env(tmp_path, root=None):
    return dict(os.environ, SHOWCASE_ESTATE_ROOT=str(root if root is not None else tmp_path),
                PYTHONIOENCODING="utf-8")


def lint(tmp_path, *args):
    """`lint public-leak ARGS` with the empty synthetic estate root and no sibling-estate discovery."""
    proc = subprocess.run([sys.executable, "-c", BOOTSTRAP, str(ROOT / "scripts" / "showcase.py"),
                           "lint", "public-leak", *map(str, args)],
                          capture_output=True, encoding="utf-8", env=_env(tmp_path))
    return proc


def rows(proc):
    return [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]


def _write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


# ---- CLI behaviour -----------------------------------------------------------------------------------------------

def test_denylist_flags_listed_slug_without_registry(tmp_path):
    deny = _write(tmp_path, "deny.txt", f"{SLUG}\n")
    page = _write(tmp_path, "page.md", f"See github.com/{SLUG} for details.\n")
    proc = lint(tmp_path, page, "--denylist", deny)
    row = rows(proc)[0]
    assert proc.returncode == CHECK_FAILED
    assert row["result"] == "fail"
    assert f"private-slug:{SLUG}" in row["hits"]
    assert row["mode"] == "denylist"
    assert "registry-free:denylist-only" in row["logs"]


def test_denylist_bare_name_hits_on_word_boundary_only(tmp_path):
    deny = _write(tmp_path, "deny.txt", "ledgerx\n")  # short: leak_check's distinctiveness rule would skip it
    hit = _write(tmp_path, "hit.md", "ledgerx powers it\n")
    miss = _write(tmp_path, "miss.md", "ledgerxyz and my-ledgerx-x\n")
    proc = lint(tmp_path, hit, "--denylist", deny)
    assert proc.returncode == CHECK_FAILED
    assert rows(proc)[0]["hits"] == ["denied-name:ledgerx"]
    proc = lint(tmp_path, miss, "--denylist", deny)
    row = rows(proc)[0]
    assert proc.returncode == OK
    assert row["result"] == "pass" and row["hits"] == []


def test_denylist_clean_file_passes(tmp_path):
    deny = _write(tmp_path, "deny.txt", f"{SLUG}\n")
    page = _write(tmp_path, "page.md", "A public note about widgets and gardens.\n")
    proc = lint(tmp_path, page, "--denylist", deny)
    row = rows(proc)[0]
    assert proc.returncode == OK
    assert row["result"] == "pass" and row["hits"] == []


def test_denylist_comments_blank_lines_crlf_and_bom(tmp_path):
    text = (f"# synthetic list\r\n\r\n# another comment\r\n"
            f"{SLUG} # note\r\n\r\n")
    deny = tmp_path / "deny.txt"
    deny.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))  # UTF-8 BOM, CRLF endings
    page = _write(tmp_path, "page.md", f"Repository {SLUG} is internal.\n")
    proc = lint(tmp_path, page, "--denylist", deny)
    row = rows(proc)[0]
    assert proc.returncode == CHECK_FAILED
    assert row["hits"] == [f"private-slug:{SLUG}"]


def test_denylist_invalid_entry_exits_2(tmp_path):
    deny = _write(tmp_path, "deny.txt", "ledger-core\na/b/c\n")
    page = _write(tmp_path, "page.md", "widgets\n")
    proc = lint(tmp_path, page, "--denylist", deny)
    assert proc.returncode == USAGE
    combined = proc.stdout + proc.stderr
    assert "denylist line 2: invalid entry" in combined


def test_denylist_missing_or_empty_exits_4(tmp_path):
    page = _write(tmp_path, "page.md", "widgets\n")
    missing = lint(tmp_path, page, "--denylist", tmp_path / "absent.txt")
    assert missing.returncode == NEEDS_INPUT
    assert "needs-input:denylist" in missing.stdout + missing.stderr
    empty = _write(tmp_path, "empty.txt", "# only comments\n\n   \n")
    proc = lint(tmp_path, page, "--denylist", empty)
    assert proc.returncode == NEEDS_INPUT
    assert "needs-input:denylist" in proc.stdout + proc.stderr


def test_without_denylist_registry_still_required(tmp_path):
    page = _write(tmp_path, "x.md", "widgets\n")
    proc = lint(tmp_path, page)
    assert proc.returncode == NEEDS_INPUT
    assert "needs-input:registry" in proc.stdout + proc.stderr
    assert "registry-free" not in proc.stdout


def test_denylist_with_registry_unions_hits(tmp_path):
    # Real synthetic estate in examples/: the registry hit and the listed slug are both reported.
    deny = _write(tmp_path, "deny.txt", f"{ORG}/extra-secret-thing\n")
    page = _write(tmp_path, "page.md",
                  f"Uses private-pricing-engine and {ORG}/extra-secret-thing for quotes.\n")
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), "lint", "public-leak", str(page),
                           "--registry", str(ESTATE / "registry" / "estate.yaml"),
                           "--meta-dir", str(ESTATE / "meta"), "--denylist", str(deny)],
                          capture_output=True, encoding="utf-8", env=_env(tmp_path, ESTATE))
    row = rows(proc)[0]
    assert proc.returncode == CHECK_FAILED
    assert row["result"] == "fail" and row["mode"] == "registry+denylist"
    assert f"private-slug:{ORG}/extra-secret-thing" in row["hits"]
    assert any("private-pricing-engine" in hit for hit in row["hits"])
    assert row["hits"] == sorted(set(row["hits"]))


def test_denylist_missing_file_operand_row(tmp_path):
    deny = _write(tmp_path, "deny.txt", "ledger-core\n")
    proc = lint(tmp_path, tmp_path / "no-such-page.md", "--denylist", deny)
    row = rows(proc)[0]
    assert proc.returncode == CHECK_FAILED
    assert row["result"] == "fail" and row["fails"] == ["file not found"]


# ---- unit tests: ctshowcase.org ----------------------------------------------------------------------------------

def test_load_denylist_splits_slug_and_name(tmp_path):
    deny = _write(tmp_path, "deny.txt", f"{SLUG}\nnorthwind-secret-ledger\n")
    slugs, names = O.load_denylist(str(deny))
    assert slugs == {SLUG}
    assert names == {"northwind-secret-ledger"}


def test_denylist_leaks_slug_match_is_case_insensitive():
    hits = O.denylist_leaks(f"MOVED TO {SLUG.upper()} LAST WEEK", {SLUG}, set())
    assert hits == [f"private-slug:{SLUG}"]


def test_denylist_leaks_bare_name_match_is_case_insensitive():
    assert O.denylist_leaks("The NORTHWIND-SECRET-LEDGER ships.", set(), {"northwind-secret-ledger"}) == [
        "denied-name:northwind-secret-ledger"]


def test_denylist_leaks_github_login_masking_does_not_hide_listed_slug():
    # The bare-name pass masks github.com/<login>; the slug check must still see the full owner/repo.
    text = f"https://github.com/{SLUG}/tree/main and github.com/{SLUG}.git"
    hits = O.denylist_leaks(text, {SLUG}, set())
    assert f"private-slug:{SLUG}" in hits
