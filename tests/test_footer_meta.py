"""`footer --check README.md --meta FILE` takes the owner from the metadata and answers like `--org` (E2.3.1).

Every test here fails on the base commit 2be04ac (verified: 7 failed on base; two more detectors, the org-row tests,
live in tests/test_footer_meta_guards.py and fail on base too). The tests
that pin behaviour which must NOT change (default paths, unknown owner, `.github` of the watching org) live in
tests/test_footer_meta_guards.py: they pass on base by design (apart from the org-row detectors noted above).

The checkout tests at the end (issue 44 without --meta) were added in the epic 35 review: three fail on the epic base
(checkout owner with --repo-dir, from the cwd, unsigned T3 refusal); test_no_repo_dir_keeps_checking_the_readme and
test_checkout_of_a_footer_owner_still_checks_the_readme pass there by design (behaviour that must not change).

Synthetic metadata only: owners are public org rows of references/brand.yaml; repository names are invented.
"""
import json

from conftest import run_cli
from ctshowcase import footer
from ctshowcase.config import load_brand


def _meta(tmp_path, owner, repo="synthetic-tool", fork=False):
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"owner": owner, "repo": repo, "fork": fork, "visibility": "public",
                                "description": "Synthetic fixture", "_synthetic": True}), encoding="utf-8")
    return str(path)


def _readme(tmp_path, with_footer=False):
    body = "# X\n\n## License\n\nMIT.\n"
    if with_footer:
        body += "\n" + footer.block(load_brand(None)) + "\n"
    path = tmp_path / "README.md"
    path.write_text(body, encoding="utf-8")
    return str(path)


def _footer(*argv):
    # --meta and --allow-t3 are global options: they go before the subcommand
    argv = list(argv)
    glob = []
    if "--allow-t3" in argv:
        argv.remove("--allow-t3")
        glob.append("--allow-t3")
    if "--meta" in argv:
        i = argv.index("--meta")
        glob += argv[i:i + 2]
        del argv[i:i + 2]
    argv.remove("footer")
    p = run_cli("--format", "json", *glob, "footer", *argv)
    return p.returncode, json.loads(p.stdout)


def test_watching_fork_is_exempt_without_reading_the_readme(tmp_path):
    code, out = _footer("footer", "--check", str(tmp_path / "missing.md"),
                        "--meta", _meta(tmp_path, "romgenie-following-repos", fork=True))
    assert code == 0, out
    assert out["result"] == "exempt" and out["logs"] == ["exempt:watching-fork"]


def test_watching_non_fork_is_held(tmp_path):
    code, out = _footer("footer", "--check", _readme(tmp_path),
                        "--meta", _meta(tmp_path, "romgenie-following-repos"))
    assert code == 0, out
    assert out["result"] == "hold" and out["logs"] == ["hold:watching-non-fork"]


def test_t3_owner_is_refused_without_signoff(tmp_path):
    p = run_cli("--meta", _meta(tmp_path, "Pick-Your-AI"), "footer", "--check", _readme(tmp_path, with_footer=True))
    assert p.returncode == 2, (p.stdout, p.stderr)
    assert "t3-signoff" in p.stdout + p.stderr or "co-owner sign-off" in p.stdout + p.stderr


def test_excluded_owner_is_refused(tmp_path):
    p = run_cli("--meta", _meta(tmp_path, "BunsDev"), "footer", "--check", _readme(tmp_path))
    assert p.returncode == 2, (p.stdout, p.stderr)


def test_footer_false_owner_is_exempt_once_signed_off(tmp_path):
    # Pick-Your-AI is T3 with `footer: false`; the global --allow-t3 signs it off for this invocation
    code, out = _footer("--allow-t3", "footer", "--check", str(tmp_path / "missing.md"),
                        "--meta", _meta(tmp_path, "Pick-Your-AI"))
    assert code == 0, out
    assert out["result"] == "exempt" and out["logs"] == ["exempt:footer"]


def test_same_owner_answers_like_org(tmp_path):
    code, meta_out = _footer("--allow-t3", "footer", "--check", str(tmp_path / "missing.md"),
                             "--meta", _meta(tmp_path, "Pick-Your-AI"))
    code_org, org_out = _footer("--allow-t3", "footer", "--org", "Pick-Your-AI")
    assert (code, meta_out["result"], meta_out["logs"]) == (code_org, org_out["result"], org_out["logs"])


def test_exempt_owner_makes_no_online_requests(tmp_path):
    code, out = _footer("--allow-t3", "footer", "--check", str(tmp_path / "missing.md"), "--online",
                        "--meta", _meta(tmp_path, "Pick-Your-AI"))
    assert code == 0, out
    assert out["result"] == "exempt" and "online" not in out


def test_type_override_agrees_with_repocontext(tmp_path):
    """`--type fork` is part of the verdict: footer --check must agree with RepoContext(type_override=...)."""
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import load_file
    path = _meta(tmp_path, "romgenie-following-repos")
    want = RepoContext(load_brand(None), load_file(path), None, type_override="fork").footer_status()
    assert want == "exempt:watching-fork"
    p = run_cli("--format", "json", "--meta", path, "--type", "fork", "footer", "--check", _readme(tmp_path))
    out = json.loads(p.stdout)
    assert p.returncode == 0, out
    assert out["result"] == "exempt" and out["logs"] == [want]


# -- issue 44, no --meta: the owner comes from the checkout `doctor` reads (--repo-dir, else cwd) -------------------
# Fails on the epic base: there `footer --check` without --meta/--org never resolved an owner and answered fail:missing
# for a Pick-Your-AI checkout while `doctor` on the same checkout reported the footer n/a.
def _checkout(tmp_path, owner, repo="synthetic-tool", with_footer=False):
    import subprocess
    rd = tmp_path / "checkout"
    rd.mkdir()
    subprocess.run(["git", "init", "-q", str(rd)], check=True)
    subprocess.run(["git", "-C", str(rd), "remote", "add", "origin", f"https://github.com/{owner}/{repo}.git"], check=True)
    body = "# X\n\nSynthetic fixture.\n\n## License\n\nMIT.\n"
    if with_footer:
        body += "\n" + footer.block(load_brand(None)) + "\n"
    (rd / "README.md").write_text(body, encoding="utf-8")
    return rd


def test_checkout_owner_without_meta_agrees_with_doctor(tmp_path):
    rd = _checkout(tmp_path, "Pick-Your-AI")
    p = run_cli("--format", "json", "--allow-t3", "--repo-dir", rd, "footer", "--check", rd / "README.md")
    out = json.loads(p.stdout)
    assert p.returncode == 0, out
    assert out["result"] == "exempt" and out["logs"] == ["exempt:footer"]
    d = run_cli("--allow-t3", "--repo-dir", rd, "doctor", "--format", "json")
    assert json.loads(d.stdout)["cells"]["footer"] == "n/a", d.stdout


def test_checkout_owner_from_cwd_without_repo_dir(tmp_path):
    rd = _checkout(tmp_path, "Pick-Your-AI")
    p = run_cli("--format", "json", "--allow-t3", "footer", "--check", "README.md", cwd=rd)
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "exempt", p.stdout + p.stderr


def test_no_repo_dir_keeps_checking_the_readme(tmp_path):
    rd = _checkout(tmp_path, "Pick-Your-AI")
    p = run_cli("--format", "json", "--allow-t3", "--no-repo-dir", "footer", "--check", rd / "README.md", cwd=rd)
    assert p.returncode == 1 and json.loads(p.stdout)["result"] == "fail:missing", p.stdout + p.stderr


def test_checkout_of_a_footer_owner_still_checks_the_readme(tmp_path):
    rd = _checkout(tmp_path, "LibreEvolve", with_footer=True)
    p = run_cli("--format", "json", "--repo-dir", rd, "footer", "--check", rd / "README.md")
    assert p.returncode == 0 and json.loads(p.stdout)["result"] == "pass", p.stdout + p.stderr
    rd2 = tmp_path / "other"
    rd2.mkdir()
    (rd2 / "README.md").write_text("# X\n", encoding="utf-8")
    p = run_cli("--format", "json", "--repo-dir", rd, "footer", "--check", rd2 / "README.md")
    assert p.returncode == 1 and json.loads(p.stdout)["result"] == "fail:missing", p.stdout + p.stderr


def test_unsigned_t3_checkout_is_refused_like_doctor(tmp_path):
    rd = _checkout(tmp_path, "Pick-Your-AI")
    p = run_cli("--format", "json", "--repo-dir", rd, "footer", "--check", rd / "README.md")
    assert p.returncode == 2, p.stdout + p.stderr
