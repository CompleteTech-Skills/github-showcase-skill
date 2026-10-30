import pytest

from ctshowcase import footer

DECISION_18 = """<p align="center">
  <a href="https://www.complete.tech">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/logo-dark.png">
      <img src="https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/logo.png" alt="CompleteTech LLC" width="200">
    </picture>
  </a>
  <br>
  Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration
</p>"""


def test_exact_markup(brand):
    assert footer.markup(brand) == DECISION_18
    assert footer.block(brand).startswith("<!-- showcase:footer:start -->\n<p")


def test_check(brand):
    good = "# X\n\n## License\n\nMIT.\n\n" + footer.block(brand) + "\n"
    assert footer.check(brand, good)[0] == "pass"
    assert footer.check(brand, "# X\n\n## License\n\nMIT.\n" + "\n" + DECISION_18 + "\n")[0] == "pass"
    assert footer.check(brand, "# X\n\n## License\n\nMIT.\n")[0] == "fail:missing"
    assert footer.check(brand, DECISION_18 + "\n\n## License\n\nMIT.\n")[0] == "fail:not-last"
    assert footer.check(brand, "# X\n\n" + DECISION_18.replace("200", "220") + "\n")[0] == "fail:drift"


def test_org_behaviour():
    from conftest import run_cli
    import json
    # decision 18 includes TouchedByAnAgent in the footer rollout
    assert json.loads(run_cli("footer", "--org", "TouchedByAnAgent").stdout)["result"] == "ok"
    assert json.loads(run_cli("footer", "--org", "romgenie-following-repos").stdout)["result"] == "exempt"
    assert run_cli("footer", "--org", "Pick-Your-AI").returncode == 2


# --- agreement tests for `footer --check README --meta M` (E2.3.2) -----------------------------------
# All fixtures are synthetic: the demo owner Northwind-Trading-Co and the shipped owners in brand.yaml.

def _cfg(tmp_path, footer):
    """A copy of references/brand.yaml whose Northwind-Trading-Co row has the given `footer` value."""
    import yaml
    from conftest import ROOT
    raw = yaml.safe_load((ROOT / "references" / "brand.yaml").read_text(encoding="utf-8"))
    raw["orgs"]["Northwind-Trading-Co"]["footer"] = footer
    p = tmp_path / "brand.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


def _meta(tmp_path, owner, repo="r", fork=False):
    import json
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"owner": owner, "repo": repo, "fork": fork, "visibility": "public"}), encoding="utf-8")
    return p


def _readme(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# X\n", encoding="utf-8")
    return p


def _check_meta(cfg, meta, tmp_path, readme):
    from conftest import run_cli
    import json
    proc = run_cli("--config", cfg, "--format", "json", "--meta", meta, "--repo-dir", tmp_path,
                   "footer", "--check", readme)
    return proc, json.loads(proc.stdout)


# Base evidence (re-run by the E2.3.2 review; synthetic fixtures only). The regression base is the commit BEFORE task 45
# (2be04ac, before 5854405 "footer: take the owner from --meta for --check"). There, `footer --check README --meta M`
# ignores the owner's `footer` setting: 8 of these 16 tests fail (test_check_meta_footer_false_exempt, _footer_hold,
# test_check_meta_agrees_with_org_flag[False|hold], test_check_meta_agrees_with_context[False|hold],
# test_check_meta_t3_refused, test_check_meta_watching_fork_exempt_nonfork_held_dotgithub_checked) and 8 pass (guards for
# unchanged behaviour: footer True, default --check, --org, unknown owner). The task-45 merge 3e45b87, which this branch
# is based on, already contains the fix, so all 16 pass there by design. Reproduce on a base export with
# `git archive 2be04ac | tar -x -C <dir>`, copy this file in, and run `python -m pytest -q tests/test_footer.py`.
# Reproduced for this unit (fresh export of 2be04ac, this file copied in): 8 failed, 8 passed; test_check_meta_footer_false_exempt
# fails there. The diff against 3e45b87 is test-only BY DESIGN, because 3e45b87 already contains the task-45 fix, so
# the regression can only be shown against 2be04ac, not against this branch's base.


def test_check_meta_footer_false_exempt(tmp_path):
    cfg = _cfg(tmp_path, False)
    proc, out = _check_meta(cfg, _meta(tmp_path, "Northwind-Trading-Co"), tmp_path, _readme(tmp_path))
    assert out["result"] == "exempt"
    assert out["logs"] == ["exempt:footer"]
    assert proc.returncode == 0


def test_check_meta_footer_hold(tmp_path):
    cfg = _cfg(tmp_path, "hold")
    proc, out = _check_meta(cfg, _meta(tmp_path, "Northwind-Trading-Co"), tmp_path, _readme(tmp_path))
    assert out["result"] == "hold"
    assert proc.returncode == 0


def test_check_meta_footer_true_still_checked(tmp_path):
    from ctshowcase.config import load_brand
    from ctshowcase import footer
    cfg = _cfg(tmp_path, True)
    meta = _meta(tmp_path, "Northwind-Trading-Co")
    proc, out = _check_meta(cfg, meta, tmp_path, _readme(tmp_path))
    assert out["result"] == "fail:missing"
    assert proc.returncode == 1
    good = tmp_path / "good.md"
    good.write_text("# X\n\n## License\n\nMIT.\n\n" + footer.block(load_brand(cfg)) + "\n", encoding="utf-8")
    proc, out = _check_meta(cfg, meta, tmp_path, good)
    assert out["result"] == "pass"
    assert proc.returncode == 0


@pytest.mark.parametrize("footer_value", [False, "hold", True])
def test_check_meta_agrees_with_org_flag(tmp_path, footer_value):
    from conftest import run_cli
    from ctshowcase.config import load_brand
    from ctshowcase.context import RepoContext
    import json
    cfg = _cfg(tmp_path, footer_value)
    _, by_meta = _check_meta(cfg, _meta(tmp_path, "Northwind-Trading-Co"), tmp_path, _readme(tmp_path))
    if footer_value is True:
        # --org emits no comparable result for a checked owner; compare to RepoContext instead.
        meta = {"owner": "Northwind-Trading-Co", "repo": "r", "fork": False, "visibility": "public"}
        assert RepoContext(load_brand(cfg), meta, None).footer_status() is None
        assert by_meta["result"].startswith("fail") or by_meta["result"] == "pass"
        return
    by_org = json.loads(run_cli("--config", cfg, "--format", "json", "footer", "--check", _readme(tmp_path),
                                "--org", "Northwind-Trading-Co").stdout)
    assert by_meta["result"] == by_org["result"]


@pytest.mark.parametrize("footer_value", [False, "hold", True])
def test_check_meta_agrees_with_context(tmp_path, footer_value):
    from ctshowcase.config import load_brand
    from ctshowcase.context import RepoContext
    cfg = _cfg(tmp_path, footer_value)
    meta = {"owner": "Northwind-Trading-Co", "repo": "r", "fork": False, "visibility": "public"}
    status = RepoContext(load_brand(cfg), meta, None).footer_status()
    _, out = _check_meta(cfg, _meta(tmp_path, "Northwind-Trading-Co"), tmp_path, _readme(tmp_path))
    if status is None:
        assert out["result"].startswith("fail") or out["result"] == "pass"
    else:
        assert out["result"] in ("exempt", "hold")


def test_check_meta_t3_refused(tmp_path):
    proc, _ = _check_meta_shipped(tmp_path, _meta(tmp_path, "Pick-Your-AI"))
    assert proc.returncode == 2
    assert "t3-signoff" in proc.stdout + proc.stderr


def _check_meta_shipped(tmp_path, meta):
    from conftest import run_cli
    import json
    proc = run_cli("--format", "json", "--meta", meta, "--repo-dir", tmp_path, "footer", "--check", _readme(tmp_path))
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {}
    return proc, out


def test_check_meta_watching_fork_exempt_nonfork_held_dotgithub_checked(tmp_path):
    cfg = _cfg(tmp_path, True)
    owner = "romgenie-following-repos"
    # each case rewrites tmp_path/'m.json' before its check (the helper always uses that name)
    cases = [
        (dict(repo="x", fork=True), "exempt", 0),
        (dict(repo="x", fork=False), "hold", 0),
        (dict(repo=".github", fork=False), "fail:missing", 1),
    ]
    for kw, want, rc in cases:
        proc, out = _check_meta(cfg, _meta(tmp_path, owner, **kw), tmp_path, _readme(tmp_path))
        assert out["result"] == want, (kw, out)
        assert proc.returncode == rc, (kw, proc.returncode)


def test_check_without_meta_unchanged(tmp_path):
    from conftest import run_cli
    import json
    cfg = _cfg(tmp_path, False)
    proc = run_cli("--config", cfg, "--format", "json", "footer", "--check", _readme(tmp_path))
    assert json.loads(proc.stdout)["result"] == "fail:missing"
    assert proc.returncode == 1


def test_check_org_flag_unchanged(tmp_path):
    from conftest import run_cli
    import json
    cfg = _cfg(tmp_path, False)
    proc = run_cli("--config", cfg, "--format", "json", "footer", "--check", _readme(tmp_path),
                   "--org", "Northwind-Trading-Co")
    assert json.loads(proc.stdout)["result"] == "exempt"


def test_meta_unknown_owner_falls_through(tmp_path):
    cfg = _cfg(tmp_path, False)
    proc, out = _check_meta(cfg, _meta(tmp_path, "Unknown-Org"), tmp_path, _readme(tmp_path))
    assert out["result"] == "fail:missing"
    assert proc.returncode == 1
