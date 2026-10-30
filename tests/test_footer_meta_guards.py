"""Regression guards for `footer --check README.md --meta FILE` (E2.3.1).

These tests PASS on the base commit 2be04ac by design: each pins behaviour that the --meta change must not alter
(the default `--check` path, an applying owner's README check, an unknown owner, `--meta` without `--check`, and the
watching org's `.github`, which still gets its README checked). They are kept apart from tests/test_footer_meta.py,
whose tests all fail on base, so that a reviewer can see which tests detect the change.

Synthetic metadata only: owners are public org rows of references/brand.yaml; repository names are invented.
"""
import json

from ctshowcase import footer
from ctshowcase.config import load_brand
from test_footer_meta import _footer, _meta, _readme


def test_watching_org_dot_github_still_checks_the_readme(tmp_path):
    code, out = _footer("footer", "--check", _readme(tmp_path),
                        "--meta", _meta(tmp_path, "romgenie-following-repos", repo=".github"))
    assert code == 1, out
    assert out["result"] == "fail:missing"


def test_footer_applying_owner_still_checks_the_readme(tmp_path):
    code, out = _footer("footer", "--check", _readme(tmp_path, with_footer=True),
                        "--meta", _meta(tmp_path, "CompleteTech-LLC"))
    assert code == 0, out
    assert out["result"] == "pass"
    code, out = _footer("footer", "--check", _readme(tmp_path), "--meta", _meta(tmp_path, "CompleteTech-LLC"))
    assert code == 1 and out["result"] == "fail:missing"


def test_unknown_owner_falls_through_to_the_readme_check(tmp_path):
    code, out = _footer("footer", "--check", _readme(tmp_path, with_footer=True),
                        "--meta", _meta(tmp_path, "unknown"))
    assert code == 0, out
    assert out["result"] == "pass"


def test_meta_without_check_prints_the_markup_unchanged(tmp_path):
    code, out = _footer("footer", "--meta", _meta(tmp_path, "Pick-Your-AI"))
    assert code == 0, out
    assert out["result"] == "ok" and out["markup"] == footer.block(load_brand(None))


def test_default_check_without_meta_is_unchanged(tmp_path):
    code, out = _footer("footer", "--check", _readme(tmp_path, with_footer=True))
    assert code == 0, out
    assert out["result"] == "pass" and "exempt" not in json.dumps(out)
