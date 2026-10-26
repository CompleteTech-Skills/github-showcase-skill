import json
import shutil

import pytest

from ctshowcase import footer, readme
from ctshowcase.context import RepoContext
from ctshowcase.meta import load_file
from conftest import FIX, ROOT, run_cli

READMES = sorted((ROOT / "tests" / "fixtures" / "readmes").glob("*.md"))


def ctx_for(brand, name, tmp_path, skill=False):
    shutil.copy(ROOT / "tests" / "fixtures" / "readmes" / f"{name}.md", tmp_path / "README.md")
    if skill:
        (tmp_path / "SKILL.md").write_text("---\nname: x\n---\n")
    return RepoContext(brand, load_file(FIX / f"{name}.json"), tmp_path)


@pytest.mark.parametrize("path", READMES, ids=lambda p: p.stem)
def test_preservation_and_idempotence(brand, tmp_path, path):
    ctx = ctx_for(brand, path.stem, tmp_path, skill=path.stem.startswith("CompleteTech-Skills"))
    before = path.read_text(encoding="utf-8")
    after, removed = readme.upgrade(ctx, before)
    assert readme.preservation(before, after, removed) == []
    again, _ = readme.upgrade(RepoContext(brand, ctx.meta, tmp_path), after)
    assert again == after
    assert after.rstrip().endswith("<!-- showcase:footer:end -->")
    # §7.1 order (q57 nav default): the hero banner block first, then the nav line
    lines = after.splitlines()
    assert lines[0] == "<!-- showcase:banner:start -->", lines[:3]
    assert lines.index("<!-- showcase:nav:start -->") == lines.index("<!-- showcase:banner:end -->") + 2


def test_variant_a_header_and_order(brand, tmp_path):
    ctx = ctx_for(brand, "CompleteTech-Skills__agentic-email-skill", tmp_path, skill=True)
    after, _ = readme.upgrade(ctx, (tmp_path / "README.md").read_text())
    assert ctx.det["variant"] == "A"
    assert "**CompleteTech LLC Skills** · [Start here](ONBOARDING.md)" in after
    lines = after.splitlines()
    assert lines.index("# Agentic Email Skill") > [i for i, x in enumerate(lines) if "docs/images/banner.png" in x][0]
    h2 = [x for x in lines if x.startswith("## ")]
    assert h2[-1] == "## License"


def test_renames_and_notes(brand, tmp_path, make_ctx):
    text = "# Thing\n\nIntro text.\n\n## Installation\n\npip install thing\n\n## Fun Stuff ✨\n\nKept.\n\n## Licence\n\nMIT.\n"
    (tmp_path / "README.md").write_text(text)
    ctx = make_ctx(repo_dir=tmp_path, description="Run the thing for teams.")
    after, removed = readme.upgrade(ctx, text)
    assert "## Install\n\npip install thing" in after and "## Notes\n\n### Fun Stuff" in after
    assert "✨" not in after and after.index("## Notes") < after.index("## License")
    assert "## About\n\nIntro text." in after
    assert readme.preservation(text, after, removed) == []


def test_shrink_guard(tmp_path):
    big = "# X\n\n" + "\n\n".join(f"## S{i}\n\n" + "word " * 40 for i in range(5))
    assert readme.preservation(big, "# X\n", []) != []


def test_preserve_list_banner_kept(brand, brand_with, tmp_path):
    ctx = ctx_for(brand, "jevplay-games__jev-minesweeper", tmp_path)
    before = (tmp_path / "README.md").read_text()
    after, _ = readme.upgrade(ctx, before)
    # q57 pres default: the hero goes above; the README's own banner stays directly under the new header
    assert "preserve-banner:kept-below-hero" in ctx.logs and "assets/banner.png" in after
    assert after.index("docs/images/banner.png") < after.index("<!-- showcase:nav:start -->") < after.index("assets/banner.png")
    # "Leave them unchanged": no hero, only the additive items
    ctx2 = RepoContext(brand_with(preserve_banner="unchanged"), ctx.meta, tmp_path)
    after2, _ = readme.upgrade(ctx2, before)
    assert "exempt:preserve-banner" in ctx2.logs and "assets/banner.png" in after2 and "docs/images/banner.png" not in after2


def test_g_h_and_bootstrap(brand, tmp_path, make_ctx):
    fork = make_ctx(fork=True, repo="llama.cpp")
    banner = readme.wrap("banner", readme.banner_html(fork)) + "\n\n"
    # no parent known: no callout (logged); the hero banner opens it and the decision 18 footer ends it (§7.4 G)
    out = readme.upgrade(fork, "# up\n")[0]
    assert out.startswith(banner + "# up\n") and "fork-parent-missing" in fork.logs
    assert footer.check(fork.brand, out)[0] == "pass"
    fork2 = make_ctx(fork=True, repo="llama.cpp", parent={"full_name": "ggml-org/llama.cpp", "default_branch": "master"},
                     ahead_by=3)
    out2 = readme.upgrade(fork2, "# up\n")[0]
    assert out2.startswith(banner + "> [!NOTE]\n> **Fork of [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)**")
    assert "compare/ggml-org:master...main" in out2 and "# up\n" in out2
    assert readme.upgrade(fork2, out2)[0] == out2  # idempotent
    # the template's README: the sibling template/ in the hand-off bundle, else the vendored copy in tests/fixtures
    tmpl = ROOT.parent / "template" / "README.md"
    if not tmpl.is_file():
        tmpl = ROOT / "tests" / "fixtures" / "template-README.md"
    text = tmpl.read_text(encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='a'\nrequires-python='>=3.10'\n[project.scripts]\na='a:main'\n")
    ctx = make_ctx(repo_dir=tmp_path, repo="support-triage-agent", description="Run the triage agent for teams.")
    out = readme.bootstrap(ctx, text)
    assert ctx.det["variant"] == "C" and "## Install" in out and "## Quick Start" in out and "Template." not in out
    assert readme.bootstrap(ctx, out) == readme.header_only(ctx, out)
    tctx = make_ctx(repo_dir=tmp_path, is_template=True)
    assert readme.bootstrap(tctx, text) == text


def test_cli_dry_run_and_write(tmp_path):
    shutil.copy(ROOT / "tests" / "fixtures" / "readmes" / "CompleteTech-LLC__LoL_OBS_Overlay.md", tmp_path / "README.md")
    meta = FIX / "CompleteTech-LLC__LoL_OBS_Overlay.json"
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme")
    assert p.returncode == 0 and json.loads(p.stdout)["diff"].startswith("--- a/README.md")
    before = (tmp_path / "README.md").read_text()
    p = run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--write", "--records", tmp_path / "rec.jsonl")
    assert p.returncode == 0 and (tmp_path / "README.md").read_text() != before
    rec = json.loads((tmp_path / "rec.jsonl").read_text().splitlines()[0])
    assert rec["std"] == "ct-std-v1" and rec["kind"] == "readme"


@pytest.mark.skipif(not (ROOT.parent / "template" / "README.md").is_file(), reason="template checkout not beside the skill")
def test_template_bootstrap_b9(tmp_path):
    from conftest import EX
    shutil.copytree(ROOT.parent / "template", tmp_path, dirs_exist_ok=True)
    shutil.copy(EX / "repos/northwind-support-triage-agent/pyproject.toml", tmp_path / "pyproject.toml")
    meta = EX / "meta/northwind-support-triage-agent.json"
    assert run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--bootstrap", "--write").returncode == 0
    lint = json.loads(run_cli("--meta", meta, "--repo-dir", tmp_path, "lint", "readme").stdout)
    assert lint["result"] == "incomplete", lint
    text = (tmp_path / "README.md").read_text()
    assert text.rstrip().endswith("<!-- showcase:footer:end -->") and "## Install" in text
    again = json.loads(run_cli("--meta", meta, "--repo-dir", tmp_path, "readme", "--bootstrap").stdout)
    assert again["result"] == "unchanged"
    assert "Northwind-Trading-Co/.github" in (tmp_path / "CONTRIBUTING.md").read_text()
