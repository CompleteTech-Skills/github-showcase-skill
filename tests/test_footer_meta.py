"""`footer --check README.md --meta FILE` takes the owner from the metadata and answers like `--org` (E2.3.1).

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


def test_watching_org_dot_github_still_checks_the_readme(tmp_path):
    code, out = _footer("footer", "--check", _readme(tmp_path),
                        "--meta", _meta(tmp_path, "romgenie-following-repos", repo=".github"))
    assert code == 1, out
    assert out["result"] == "fail:missing"


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
