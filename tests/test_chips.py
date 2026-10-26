from ctshowcase import chips


def test_cve_extraction_max_two(make_ctx):
    ctx = make_ctx(owner="CompleTetech-Security", repo="x-cve-2026-11111-check",
                   description="Check X versions for CVE-2026-11111 and CVE-2026-22222 and CVE-2026-33333.")
    assert [k for k, _ in chips.key_chips(ctx)] == ["CVE-2026-11111", "CVE-2026-22222"]


def test_category_fallback(make_ctx):
    ctx = make_ctx(owner="jevplay-games", repo="jev-thing", description="Jev Thing: play a game against Jev at jevplay.games.")
    assert chips.key_chips(ctx) == []  # "Game" repeats the eyebrow "jevplay.games · Game" (P1.6)
    assert "needs-input:key-chip" in ctx.logs
    sec = make_ctx(owner="CompleTetech-Security", repo="acme-check", description="Check Acme Gateway versions offline.")
    assert chips.key_chips(sec) == [("CVE checker", "type")]  # differs from SECURITY TOOLS: kept
    ws = make_ctx(owner="CompleteTech-LLC")  # rule-25 Workspace: no gold chip and no eyebrow category
    assert chips.key_chips(ws) == [] and chips.eyebrow_text(ws) == "COMPLETETECH LLC"


def test_runtime_chip(make_ctx, tmp_path):
    (tmp_path / "SKILL.md").write_text("---\nname: x\n---\n")
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-Skills", repo="x-skill", topics=["claude-skill", "codex-skill"])
    assert ("Claude · Codex", "topics") in chips.attr_chips(ctx)


def test_requires_python_and_no_deps(make_ctx):
    from conftest import EX
    ctx = make_ctx(repo_dir=EX / "repos" / "northwind-support-triage-agent")
    a = [x for x, _ in chips.attr_chips(ctx)]
    assert a[:2] == ["Python 3.10+", "No dependencies"]


def test_license_rules(make_ctx):
    assert ("MIT", "license") in chips.attr_chips(make_ctx(language=None))
    assert not [a for a in chips.attr_chips(make_ctx(visibility="private", language=None)) if a[1] == "license"]
    sec = make_ctx(owner="CompleTetech-Security", repo="y-check", license="AGPL-3.0", language=None)
    assert ("AGPL-3.0 or commercial", "license") in chips.attr_chips(sec)


def test_override_replaces(make_ctx, tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/showcase.yml").write_text("chips: {key: [K1], attrs: [A1, A2]}\n")
    ctx = make_ctx(repo_dir=tmp_path)
    assert chips.derive(ctx) == ([("K1", "override")], [("A1", "override"), ("A2", "override")])
