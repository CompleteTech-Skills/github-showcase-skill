from ctshowcase import footer

DECISION_18 = """<p align="center">
  <a href="https://www.complete.tech">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/CompleteTech-Skills/github-showcase-skill/main/assets/brand/logo-dark.png">
      <img src="https://raw.githubusercontent.com/CompleteTech-Skills/github-showcase-skill/main/assets/brand/logo.png" alt="CompleteTech LLC" width="200">
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
