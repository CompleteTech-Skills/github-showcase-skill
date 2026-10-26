"""Review round 3 regressions: the `readme` hold message names no option the `readme` command rejects, and the
standalone `project readme` applies the same privacy gate as copy-plan (a board that is public or may go public names
no repository in its README). Synthetic Northwind fixtures only."""
import copy
import json
import re

from conftest import ROOT, meta_dict, run_cli

N = "Northwind-Trading-Co"
W = "romgenie-following-repos"
PFIX = ROOT / "tests" / "fixtures" / "project"
REPOS = [f"{N}/support-triage-agent", f"{N}/private-pricing-engine"]


# ======================================================================================== readme hold remedy
def test_readme_hold_message_names_only_options_readme_accepts(tmp_path):
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(meta_dict(owner=W, repo="northwind-tools", fork=False)), encoding="utf-8")
    rd = tmp_path / "w"
    rd.mkdir()
    (rd / "README.md").write_text("# northwind-tools\n\nA Northwind tool.\n", encoding="utf-8")
    p = run_cli("--meta", m, "--repo-dir", rd, "--format", "json", "readme", "--mode", "header", "--write")
    out = json.loads(p.stdout)
    assert p.returncode == 2 and out["result"] == "hold" and out["logs"] == ["hold:watching-non-fork"], p.stdout
    assert (rd / "README.md").read_text(encoding="utf-8") == "# northwind-tools\n\nA Northwind tool.\n"
    accepted = set(re.findall(r"--[a-z][a-z-]*", run_cli("readme", "--help").stdout))
    named = set(re.findall(r"--[a-z][a-z-]*", out["error"]))
    assert named <= accepted, f"the hold message names options readme rejects: {sorted(named - accepted)}"
    assert "--allow-hold" not in out["error"]


# ======================================================================================== project readme privacy
def _capture(tmp_path, public):
    c = json.loads((PFIX / "copy-capture.json").read_text(encoding="utf-8"))
    p = c["data"]["organization"]["projectV2"]
    nodes = p["views"]["nodes"]
    for i, name in ((6, "My items"), (7, "Shipped")):
        nodes.append(dict(copy.deepcopy(nodes[-1]), id=f"PVTV_n{i}", number=i, name=name, filter=""))
    p["public"] = public
    p["repositories"] = {"nodes": [{"nameWithOwner": r} for r in REPOS]}
    f = tmp_path / f"board-{'public' if public else 'private'}.json"
    f.write_text(json.dumps(c), encoding="utf-8")
    return f


def _project_readme(tmp_path, capture, rows=(), extra=()):
    tsv = tmp_path / "approved.tsv"
    tsv.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    p = run_cli("project", "readme", "--capture", capture, "--owner", N, "--display-name", "Northwind Trading Co.",
                "--reviewed", "2026-10-26", "--approved", tsv, "--approved-yaml", tmp_path / "none.yaml",
                "--actions", tmp_path / "none.json", *extra)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout)


def test_project_readme_on_a_public_board_names_no_repository(tmp_path):
    for extra in ((), ("--repos", ",".join(REPOS))):
        out = _project_readme(tmp_path, _capture(tmp_path, public=True), extra=extra)
        assert "private-pricing-engine" not in out["readme"] and "support-triage-agent" not in out["readme"]
        assert "readme-links:repositories-omitted (the board may go public)" in out["logs"]
        assert "## Links" in out["readme"]


def test_project_readme_on_a_board_approved_to_go_public_names_no_repository(tmp_path):
    out = _project_readme(tmp_path, _capture(tmp_path, public=False), rows=[("project-visibility", N, "*")])
    assert "private-pricing-engine" not in out["readme"]
    assert "readme-links:repositories-omitted (the board may go public)" in out["logs"]


def test_project_readme_on_a_private_board_keeps_the_repository_list(tmp_path):
    out = _project_readme(tmp_path, _capture(tmp_path, public=False))
    assert f"{N}/private-pricing-engine" in out["readme"]
    assert not any(x.startswith("readme-links:") for x in out["logs"])
