import pytest

from ctshowcase import readme
from ctshowcase.detect import standard

LICENSE_ROWS = [
    (dict(owner="CompleTetech-Security", repo="x-check", license="AGPL-3.0"), "## Licensing", "GNU AGPL-3.0"),
    (dict(owner="CompleteTech-LLC", repo="thing-fork"), None, None),
    (dict(owner="CompleteTech-Skills", repo="x-skill", license="MIT", brand_assets=True), "## License", "seals, and brand assets"),
    (dict(owner="CompleteTech-LLC", repo="thing", license="MIT"), "## License", "CompleteTech LLC names and logos"),
    (dict(owner="LibreEvolve", repo="thing", license="MIT"), "## License", "LibreEvolve names and logos"),
    (dict(owner="CompleteTech-LLC", repo="thing", license="Apache-2.0"), "## License", "Licensed under the Apache-2.0"),
    (dict(owner="CompleteTech-LLC", repo="thing", license=None, visibility="private", created_at="2025-01-01T00:00:00Z"),
     "## License", "Copyright (c) 2025 CompleteTech LLC"),
    (dict(owner="CompleteTech-LLC", repo="thing", license=None), None, None),
]


@pytest.mark.parametrize("kw,heading,text", LICENSE_ROWS)
def test_license_rows(make_ctx, tmp_path, kw, heading, text):
    kw = dict(kw)
    if kw.pop("brand_assets", False):
        (tmp_path / "BRAND_ASSETS.md").write_text("x")
    if kw.get("repo", "").endswith("-fork"):
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "LICENSE").write_text("x")
    ctx = make_ctx(repo_dir=tmp_path, **kw)
    out = readme.scaffold(ctx)
    if heading:
        assert heading in out and text in out
    else:
        assert "## License" not in out and any(x.startswith("needs-input:") for x in ctx.logs)


@pytest.mark.parametrize("variant", list("ABCDEFIJ"))
def test_variant_order_and_needs_input(make_ctx, tmp_path, variant):
    ctx = make_ctx(repo_dir=tmp_path, license="MIT")
    ctx.det["variant"] = variant
    out = readme.scaffold(ctx)
    order = [h for h, _ in standard("readme-variants")["variants"][variant]]
    found = [ln[3:] for ln in out.splitlines() if ln.startswith("## ")]
    assert [order.index(h) for h in found] == sorted(order.index(h) for h in found)
    req = [h for h, r in standard("readme-variants")["variants"][variant] if r == "R" and h not in ("License", "Licensing")]
    for h in req:
        assert h in found or f"needs-input:{variant}:{h}" in ctx.logs
    assert "TBD" not in out and "TODO" not in out


def test_f_layout_parity(make_ctx, tmp_path):
    (tmp_path / "LICENSING.md").write_text("x")
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleTetech-Security", repo="netscaler-cve-2026-19489-check", license="AGPL-3.0",
                   description="Check NetScaler versions for CVE-2026-19489 (LSN SIP ALG memory corruption), offline and dependency-free.")
    out = readme.scaffold(ctx)
    assert not any(ln.startswith("# ") for ln in out.splitlines())  # no H1 in F
    assert '<p align="center"><b>Check NetScaler versions' in out
    assert "[All checkers](https://github.com/CompleteTech-Security)" in out and "[Licensing](LICENSING.md)" in out


def test_badges_local(tmp_path):
    import shutil
    from conftest import EX, run_cli
    from ctshowcase import svglint  # noqa: F401
    shutil.copytree(EX / "repos" / "northwind-support-triage-agent", tmp_path, dirs_exist_ok=True)
    p = run_cli("--meta", EX / "meta" / "northwind-support-triage-agent.json", "--repo-dir", tmp_path, "readme", "--mode",
                "scaffold", "--badges", "local", "--write")
    assert p.returncode == 0, p.stderr
    text = (tmp_path / "README.md").read_text()
    files = sorted((tmp_path / "docs/images/badges").glob("*.svg"))
    assert files and "img.shields.io" not in text
    for f in files:
        s = f.read_text()
        assert f"docs/images/badges/{f.name}" in text and "<text" not in s and 'role="img"' in s
