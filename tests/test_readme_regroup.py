"""Exercise README proposal controls through the public CLI."""

import hashlib
import json

import pytest

from conftest import meta_dict, run_cli


def receipt(payload, ending="\n"):
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"<!-- showcase:tagline:generated sha256={digest} -->{ending}{payload}"


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(description="Run the updated workflow.")), encoding="utf-8")

    def invoke(*args, text=False):
        fmt = ("--format", "text") if text else ()
        return run_cli(*fmt, "--meta", meta, "--repo-dir", repo, "readme", *args)

    return repo, invoke


@pytest.mark.parametrize("mode", ["auto", "upgrade", "header"])
@pytest.mark.parametrize("owned", [False, True])
def test_no_regroup_keeps_mixed_endings_and_authored_bytes(checkout, mode, owned):
    repo, invoke = checkout
    readme = repo / "README.md"
    old = receipt("**Old.**", "\r") if owned else "**Old.**"
    fresh = receipt("**Run the updated workflow.**", "\r") if owned else old
    before = (
        "\ufeff# My Title\r\n\n## Unusual  heading\r Exact text.\r\n\r\n"
        f"<!-- showcase:tagline:start -->\r\n{old}\r<!-- showcase:tagline:end -->\n"
        "\r\n## Usage\rBody."
    )
    readme.write_bytes(before.encode("utf-8"))
    result = invoke("--write", "--no-regroup", "--mode", mode)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["heading_moves"] == []
    assert json.loads(result.stdout)["written"] is owned
    assert readme.read_bytes() == before.replace(old, fresh).encode("utf-8")
    again = invoke("--write", "--no-regroup", "--mode", mode)
    assert again.returncode == 0 and json.loads(again.stdout)["written"] is False


@pytest.mark.parametrize("args", [("--bootstrap",), ("--mode", "scaffold")])
def test_no_regroup_rejects_conflicting_modes(checkout, args):
    repo, invoke = checkout
    readme = repo / "README.md"
    before = b"# Original\n"
    readme.write_bytes(before)
    result = invoke("--write", "--no-regroup", *args)
    assert result.returncode == 2
    assert readme.read_bytes() == before


def test_no_regroup_leaves_unmarked_readme_and_badges_alone(checkout):
    repo, invoke = checkout
    before = b"# Original\r\n\r\n## Usage\r\nBody."
    (repo / "README.md").write_bytes(before)
    result = invoke("--write", "--no-regroup", "--badges", "local")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["written"] is False
    assert (repo / "README.md").read_bytes() == before
    assert not (repo / "docs").exists()


def test_section_config_supplies_missing_facts_and_preserves_existing_section(checkout):
    repo, invoke = checkout
    (repo / ".github").mkdir()
    (repo / ".github/showcase.yml").write_text(
        "readme:\n  sections:\n    Usage: Run the northwind command.\n    Install: Configure the sample first.\n",
        encoding="utf-8",
    )
    readme = repo / "README.md"
    readme.write_text(
        "# Project\n\n  ```markdown\n## Usage\n  ```\n\n## Installation\n\nFollow the existing guide.\n",
        encoding="utf-8",
    )
    result = invoke("--variant", "C", "--write")
    assert result.returncode == 0, result.stdout
    updated = readme.read_text(encoding="utf-8")
    assert "## Usage\n\nRun the northwind command." in updated
    assert "## Install\n\nFollow the existing guide." in updated
    assert "Configure the sample first." not in updated
    assert "needs-input:C:Usage" not in json.loads(result.stdout)["logs"]


def test_heading_summary_separates_demotions_from_added_sections(checkout):
    repo, invoke = checkout
    before = "# Project\n\n## Installation\n\nSet up the sample.\n\n## Benchmarks\n\nSynthetic results.\n"
    (repo / "README.md").write_text(before, encoding="utf-8")
    result = invoke("--variant", "C")
    assert result.returncode == 0, result.stdout
    plan = json.loads(result.stdout)
    assert {"heading": "Installation", "from": 2, "to": 2, "new_heading": "Install"} in plan["heading_moves"]
    assert {"heading": "Benchmarks", "from": 2, "to": 3, "new_heading": "Benchmarks"} in plan["heading_moves"]
    assert "+## Notes" in plan["diff"]
    assert all(move["heading"] != "Notes" for move in plan["heading_moves"])
    summary = invoke("--variant", "C", text=True)
    assert summary.returncode == 0, summary.stderr
    assert summary.stdout.index("Heading: Benchmarks (H2 -> H3: Benchmarks)") < summary.stdout.index("--- a/README.md")


def test_duplicate_heading_summary_is_ambiguous(checkout):
    repo, invoke = checkout
    (repo / "README.md").write_text("# Project\n\n## Custom\nFirst.\n\n### Custom\nSecond.\n", encoding="utf-8")
    result = invoke()
    assert result.returncode == 0, result.stdout
    assert {"heading": "Custom", "ambiguous": True, "old_levels": [2, 3], "new_levels": [3, 3]} in (
        json.loads(result.stdout)["heading_moves"]
    )


def test_no_regroup_refuses_authored_footer_before_writing(checkout):
    repo, invoke = checkout
    readme = repo / "README.md"
    before = (
        "# Project\r\n\r\n"
        "<!-- showcase:footer:start -->\r\n"
        "Thanks to the contributors who maintain this project.\r\n"
        "<!-- showcase:footer:end -->\r\n"
    )
    readme.write_bytes(before.encode("utf-8"))
    records = repo / "records.jsonl"
    result = invoke("--no-regroup", "--write", "--records", records)
    assert result.returncode == 1
    assert "readme-shrink" in json.loads(result.stdout)["logs"]
    assert readme.read_bytes() == before.encode("utf-8")
    assert not records.exists()


def test_heading_summary_includes_variant_status_rename(checkout):
    repo, invoke = checkout
    before = "# Project\n\n## Status\n\nSynthetic result.\n"
    (repo / "README.md").write_text(before, encoding="utf-8")
    result = invoke("--mode", "upgrade", "--variant", "D")
    assert result.returncode == 0, result.stdout
    assert {"heading": "Status", "from": 2, "to": 2, "new_heading": "Findings"} in (
        json.loads(result.stdout)["heading_moves"]
    )


@pytest.mark.parametrize("write", [False, True])
def test_no_regroup_rejects_readme_as_records_destination(checkout, write):
    repo, invoke = checkout
    path = repo / "README.md"
    generated = receipt("**Old.**", "\r\n")
    before = (f"# Project\r\n\r\n<!-- showcase:tagline:start -->\r\n{generated}\r\n"
              "<!-- showcase:tagline:end -->").encode("utf-8")
    path.write_bytes(before)
    result = invoke("--no-regroup", "--records", path, *(("--write",) if write else ()))
    assert result.returncode == 2
    assert path.read_bytes() == before
