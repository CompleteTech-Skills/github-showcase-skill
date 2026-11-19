"""The composite Action carries a neutral product name; CompleteTech LLC appears only as its publisher and credit."""
import subprocess
import sys

from conftest import ROOT


def test_action_name_is_neutral_and_publisher_kept():
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "name: Repo Showcase"
    assert "author: CompleteTech LLC" in text
    for rel in ("action.yml", "scripts/action_commit.sh", "scripts/action_prepare.py"):
        assert "CompleteTech Showcase" not in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_pr_body_credit_comes_from_attribution(brand):
    a = brand.raw["attribution"]
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "action_prepare.py"), "credit"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
    assert out == f"Made with {a['skill']} by {a['publisher']}: {a['skill_url']}"
    assert "${credit:+ $credit}" in (ROOT / "scripts" / "action_commit.sh").read_text(encoding="utf-8")


def test_template_sidecar_check_follows_the_operator_block(brand):
    sys.path.insert(0, str(ROOT / "scripts"))
    import action_prepare
    assert action_prepare.template_repo() == brand.operator()["repo_template"]
