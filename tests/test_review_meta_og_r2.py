"""Review round 2 (Codex 4373814824): meta.normalize() must keep every key a downstream consumer reads.

The social-preview flag (R10), the GitHub Pages flag and the About sidebar counts (adopt, sidebar), and the REST
`size` (doctor --estate empty-repository rule) were dropped, so supplied evidence never reached its check.
Synthetic Northwind fixtures only."""
import json

from conftest import EX, ROOT, run_cli
from ctshowcase import intake
from ctshowcase.meta import normalize

BASE = {"owner": "Northwind-Trading-Co", "repo": "support-triage-agent", "visibility": "public"}


def _doctor_r10(tmp_path, **extra) -> str:
    raw = json.loads((EX / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))
    raw.update(extra)
    m = tmp_path / "meta.json"
    m.write_text(json.dumps(raw), encoding="utf-8")
    p = run_cli("--meta", m, "--no-repo-dir", "doctor", "--format", "json")
    return json.loads(p.stdout)["cells"]["R10"]


def test_snake_case_og_flag_survives_normalize():
    assert normalize(dict(BASE, uses_custom_og_image=True))["uses_custom_og_image"] is True
    assert normalize(dict(BASE, uses_custom_og_image=False))["uses_custom_og_image"] is False


def test_graphql_og_spelling_is_mapped():
    assert normalize(dict(BASE, usesCustomOpenGraphImage=True))["uses_custom_og_image"] is True
    assert normalize(dict(BASE, usesCustomOpenGraphImage=False))["uses_custom_og_image"] is False


def test_og_flag_fails_closed_when_absent_ambiguous_or_not_boolean():
    assert "uses_custom_og_image" not in normalize(dict(BASE))
    assert "uses_custom_og_image" not in normalize(dict(BASE, uses_custom_og_image="true"))
    assert "uses_custom_og_image" not in normalize(dict(BASE, uses_custom_og_image=None))
    # two spellings that disagree prove nothing: R10 stays unknown rather than picking one
    assert "uses_custom_og_image" not in normalize(dict(BASE, uses_custom_og_image=True, usesCustomOpenGraphImage=False))


def test_og_flag_round_trips_through_normalize():
    once = normalize(dict(BASE, usesCustomOpenGraphImage=True))
    assert normalize(once)["uses_custom_og_image"] is True


def test_doctor_r10_reads_supplied_evidence(tmp_path):
    assert _doctor_r10(tmp_path) == "unknown"
    assert _doctor_r10(tmp_path, uses_custom_og_image=True) == "pass"
    assert _doctor_r10(tmp_path, usesCustomOpenGraphImage=True) == "pass"
    assert _doctor_r10(tmp_path, usesCustomOpenGraphImage=False) == "fail"


def test_pages_and_sidebar_counts_survive_normalize():
    m = normalize(dict(BASE, has_pages=True, releases=2, deployments=0, packages=0, environments=["github-pages"]))
    assert m["has_pages"] is True
    assert (m["releases"], m["deployments"], m["packages"], m["environments"]) == (2, 0, 0, ["github-pages"])
    assert not {"has_pages", "releases", "deployments", "packages", "environments"} & set(normalize(dict(BASE)))


def test_adopt_sidebar_uses_counts_from_metadata(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps(dict(BASE, description="Run the Northwind triage agent.", topics=["wip"],
                                 language="Python", license="MIT", has_issues=True, delete_branch_on_merge=True,
                                 labels=[{"name": "bug", "color": "d73a4a", "description": ""}],
                                 releases=2, deployments=0, packages=0, has_pages=True)), encoding="utf-8")
    p = run_cli("--meta", m, "--no-repo-dir", "adopt", "Northwind-Trading-Co/support-triage-agent")
    assert p.returncode == 0, p.stdout + p.stderr
    r = json.loads(p.stdout)
    assert not [lg for lg in r.get("logs", []) if lg.startswith("needs-input:sidebar-facts")]
    sidebar = [j for j in r["jobs"] if "sidebar" in j.get("id", "")]
    assert sidebar, [j.get("id") for j in r["jobs"]]
    assert any("GitHub Pages" in s for s in sidebar[0]["steps"])


def test_rest_size_survives_for_the_estate_empty_repository_rule(brand):
    m = normalize(dict(BASE, repo="empty-sandbox", size=0))
    assert m["size"] == 0
    assert [p["kind"] for p in intake.classify(m, brand, None)] == ["delete"]


def test_schema_lists_the_preserved_keys():
    props = json.loads((ROOT / "references" / "meta.schema.json").read_text(encoding="utf-8"))["properties"]
    for k in ("uses_custom_og_image", "has_pages", "size", "releases", "deployments", "packages", "environments",
              "files", "files_complete", "manifests", "file_sizes", "homepage_status"):
        assert k in props, k
