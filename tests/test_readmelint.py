import shutil

from ctshowcase import footer, readme, readmelint
from conftest import EX


def good_readme(make_ctx, tmp_path, brand):
    shutil.copytree(EX / "repos" / "northwind-support-triage-agent", tmp_path, dirs_exist_ok=True)
    (tmp_path / "docs/images").mkdir(parents=True)
    (tmp_path / "docs/images/banner.png").write_bytes(b"x")
    ctx = make_ctx(repo_dir=tmp_path, description="Run the Northwind customer support email triage agent from the command line.")
    text = readme.scaffold(ctx, "")
    text = text.replace("## License", "## Usage\n\nRun `triage --help`.\n\n## License")
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    return ctx


def test_pass_then_each_failure(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = tmp_path / "README.md"
    r = readmelint.lint(ctx, p)
    assert r["result"] in ("pass", "incomplete"), r
    base = p.read_text(encoding="utf-8")
    cases = {
        "D13": base.replace('<img src="docs/images/banner.png"', '<picture><img src="docs/images/banner.png"').replace(
            'width="100%">\n</p>', 'width="100%"></picture>\n</p>'),
        "D18": base.replace("width=\"200\"", "width=\"220\""),
        "R7 placeholder": base.replace("## Install", "TODO later\n\n## Install"),
        "R7 emoji": base.replace("## Install", "Done ✅\n\n## Install"),
        "R7 code fence": base.replace("```bash\npip install .", "```\npip install ."),
        "R2": base.replace("**Run the Northwind", "**Runs the Northwind"),
        "R7 nav": base.split("\n", 3)[3],
        "R7 off-palette": base.replace("-005ADD)", "-8A2BE2)"),
    }
    for rule, text in cases.items():
        p.write_text(text, encoding="utf-8")
        res = readmelint.lint(ctx, p)
        assert res["result"] == "fail" and any(f.startswith(rule.split()[0]) for f in res["fails"]), (rule, res["fails"])


def test_incomplete_only_needs_input(make_ctx, tmp_path, brand):
    ctx = good_readme(make_ctx, tmp_path, brand)
    p = tmp_path / "README.md"
    p.write_text(p.read_text(encoding="utf-8").replace("## Usage\n\nRun `triage --help`.\n\n", ""), encoding="utf-8")
    r = readmelint.lint(ctx, p)
    assert r["result"] == "incomplete" and "needs-input:C:Usage" in r["logs"]
    assert footer.check(brand, p.read_text(encoding="utf-8"))[0] == "pass"
