from ctshowcase.topics import merge


def test_invoice_worked_example(make_ctx, tmp_path):
    (tmp_path / "SKILL.md").write_text("---\nname: agentic-invoice-skill\n---\n")
    (tmp_path / "requirements.txt").write_text("reportlab==4.5.1\npyyaml==6.0.3\n")
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-Skills", repo="agentic-invoice-skill",
                   description="Create branded CompleteTech LLC invoice PDFs for agentic development services, from deposit through final payment.",
                   topics=["agentic-development", "agentic-workflows", "billing", "claude-skill", "codex-skill", "completetech",
                           "invoice", "pdf-generator"])
    r = merge(ctx)
    assert r["proposed"] == ["completetech", "claude-skill", "codex-skill", "agentic-ai", "agent-skills", "invoice", "billing",
                             "python", "reportlab", "pdf-generator"]


def test_security_example(make_ctx):
    ctx = make_ctx(owner="CompleTetech-Security", repo="netscaler-cve-2026-19489-check", topics=[],
                   description="Check NetScaler versions for CVE-2026-19489 (LSN SIP ALG memory corruption), offline and dependency-free.")
    assert merge(ctx)["proposed"] == ["completetech", "security", "cve", "security-check", "netscaler", "python"]


def test_jevplay_example(make_ctx):
    ctx = make_ctx(owner="jevplay-games", repo="jev-connect-four", topics=[], language="JavaScript",
                   description="Connect Four: play a board game against Jev at jevplay.games.")
    assert merge(ctx)["proposed"] == ["jev", "browser-game", "game", "board-game", "javascript"]


def test_fork_path(make_ctx):
    ctx = make_ctx(owner="CompleteTech-LLC-AI-Research", repo="llama.cpp", fork=True,
                   parent={"full_name": "ggml-org/llama.cpp", "topics": ["llm", "cpp", "ggml", "large-language-models"]})
    assert merge(ctx)["proposed"] == ["fork", "llm", "cpp"]


def test_drops_aliases_and_private_safety(make_ctx):
    ctx = make_ctx(owner="CompleteTech-Pokemon", repo="card-shop", visibility="private",
                   topics=["pokemon", "wip", "completetech-pokemon", "2024", "reactjs", "trading-cards"],
                   description="Trading-card shop inventory tools.")
    p = merge(ctx)["proposed"]
    assert "pokemon" not in p and "wip" not in p and "2024" not in p and "completetech-pokemon" not in p
    assert "react" in p and "trading-cards" in p and len(p) <= 8


def test_truncate_and_equal(make_ctx):
    ctx = make_ctx(topics=["completetech", "workspace", "python"], description="Northwind workspace.")
    r = merge(ctx)
    assert r["equal_as_set"] and "topics-short" in r["logs"]
