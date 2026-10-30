"""Tests for `footer --check README.md --meta FILE` (E2.3.1) that are NOT claim tests.

Measured against the base commit 2be04ac (new tests dropped into a base checkout): 16 tests in this file and
test_footer_meta.py, 10 fail on base and 6 pass on base.

Pass on base, by design (regression guards: they pin behaviour the --meta change must not alter):
  test_watching_org_dot_github_still_checks_the_readme, test_footer_applying_owner_still_checks_the_readme,
  test_unknown_owner_falls_through_to_the_readme_check, test_meta_without_check_prints_the_markup_unchanged,
  test_default_check_without_meta_is_unchanged, and
  test_malformed_captured_rendering_config_does_not_change_the_footer_verdict (it guards against a RepoContext
  regression for an applying owner; base ignores --meta, so it passes there too).

Fail on base (they detect the change, because base ignores --meta): the 7 tests in test_footer_meta.py plus
  test_org_row_footer_hold_matches_org_verdict, test_org_row_footer_false_matches_org_verdict and
  test_watching_fork_with_malformed_captured_config_is_still_exempt (fail:missing, exit 1 on base).

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


def _cfg_with_llc_footer(tmp_path, value):
    """A synthetic copy of brand.yaml whose CompleteTech-LLC row says `footer: VALUE` (no real row has `hold`)."""
    from conftest import ROOT
    lines = (ROOT / "references" / "brand.yaml").read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if ln.startswith("  CompleteTech-LLC:"))
    i = next(i for i in range(start, len(lines)) if lines[i].strip() == "footer: true")
    lines[i] = lines[i].replace("true", value)
    cfg = tmp_path / "brand.yaml"
    cfg.write_text("".join(lines), encoding="utf-8")
    return str(cfg)


def _run(cfg, *argv):
    from conftest import run_cli
    p = run_cli("--config", cfg, "--format", "json", *argv)
    return p.returncode, json.loads(p.stdout)


def test_org_row_footer_hold_matches_org_verdict(tmp_path):
    cfg = _cfg_with_llc_footer(tmp_path, "hold")
    code, out = _run(cfg, "--meta", _meta(tmp_path, "CompleteTech-LLC"), "footer", "--check", _readme(tmp_path))
    ref_code, ref = _run(cfg, "footer", "--org", "CompleteTech-LLC")
    assert (code, out["result"], out["logs"]) == (0, "hold", ["hold"])
    assert (ref_code, ref["result"], ref["logs"]) == (0, "hold", ["hold"])


def test_org_row_footer_false_matches_org_verdict(tmp_path):
    cfg = _cfg_with_llc_footer(tmp_path, "false")
    code, out = _run(cfg, "--meta", _meta(tmp_path, "CompleteTech-LLC"), "footer", "--check", _readme(tmp_path))
    assert (code, out["result"], out["logs"]) == (0, "exempt", ["exempt:footer"])


def test_malformed_captured_rendering_config_does_not_change_the_footer_verdict(tmp_path):
    """Reviewer B: building a RepoContext parsed `.github/showcase.yml` from the metadata and failed with config/exit 2
    for an owner the footer applies to. The verdict for non-watching owners comes from the brand rows alone."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "CompleteTech-LLC", "repo": "synthetic-tool", "_synthetic": True,
                                "manifests": {".github/showcase.yml": "- not\n- a mapping\n"}}), encoding="utf-8")
    code, out = _footer("footer", "--check", _readme(tmp_path, with_footer=True), "--meta", str(meta))
    assert code == 0 and out["result"] == "pass", out


def test_watching_fork_with_malformed_captured_config_is_still_exempt(tmp_path):
    """Reviewer B: the fork exemption is decided from metadata before the captured config is parsed."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "romgenie-following-repos", "repo": "synthetic-tool", "fork": True,
                                "_synthetic": True,
                                "manifests": {".github/showcase.yml": "- not" + chr(10) + "- a mapping" + chr(10)}}), encoding="utf-8")
    code, out = _footer("footer", "--check", _readme(tmp_path), "--meta", str(meta))
    assert (code, out["result"], out["logs"]) == (0, "exempt", ["exempt:watching-fork"]), out
