"""CQ-03: one resolver for every org lookup, so renamed and merged orgs keep resolving (brand rows, the watching-org
exemption, the TCG disclaimer, registry keys and approvals). Synthetic approvals; public org logins only."""
import json
import re

import pytest

from ctshowcase import resolver as R
from ctshowcase.errors import NeedsInput, Refused, ShowcaseError

ACTIONS = [
    {"id": "org-001", "owner": "CompleTetech-Security", "action": "org-rename", "new_name": "CompleteTech-Security"},
    {"id": "org-003", "owner": "romgenie-following-repos", "action": "org-rename", "new_name": "CompleteTech-Following"},
    {"id": "org-004", "owner": "CompleteTechDiscord-Games", "action": "org-merge", "target_owner": "CompleteTech-Games"},
    {"id": "org-005", "owner": "CompleteTech-Pokemon", "action": "org-rename", "new_name": "CompleteTech-TCG"},
]


def approvals(rows=(), ids=(), actions=ACTIONS):
    return {"rows": set(rows), "ids": set(ids), "answers": {}, "actions": list(actions), "extra": []}


def test_approved_tsv_rename_resolves_brand_row_and_slugs(brand):
    r = R.Resolver(brand, {}, approvals(rows=[("org-rename", "CompleTetech-Security", "*", "CompleteTech-Security")]))
    assert r.canonical("CompleTetech-Security") == "CompleteTech-Security"
    assert r.canonical("completetech-security") == "CompleteTech-Security"
    assert r.brand_key("CompleteTech-Security") == "CompleTetech-Security"
    row = r.brand_org("CompleteTech-Security")
    assert row["owner"] == "CompleteTech-Security" and row["display_name"] == "CompleteTech Security" and row["known"]
    assert r.slug("CompleTetech-Security/php2shell-check") == "CompleteTech-Security/php2shell-check"
    assert r.same("CompleTetech-Security", "CompleteTech-Security")


def test_unapproved_rename_changes_nothing(brand):
    r = R.Resolver(brand, {}, approvals(ids=[]))  # org-001 exists but is not approved
    assert r.canonical("CompleTetech-Security") == "CompleTetech-Security"
    assert r.summary()["renames"] == {}


def test_approved_ids_keep_watching_exemption_and_disclaimer(brand):
    r = R.Resolver(brand, {}, approvals(ids=["org-003", "org-005"]))
    assert r.canonical("romgenie-following-repos") == "CompleteTech-Following"
    assert r.owner_status("CompleteTech-Following") == "watching"  # the exemption survives the rename
    tcg = r.brand_org("CompleteTech-TCG")
    assert tcg["brand_key"] == "CompleteTech-Pokemon" and tcg["owner"] == "CompleteTech-TCG"
    assert "Nintendo" in tcg["disclaimer"]
    assert r.aliases("CompleteTech-TCG") == ["CompleteTech-TCG", "CompleteTech-Pokemon"]


def test_merge_keeps_the_placeholder_and_names_the_successor(brand):
    r = R.Resolver(brand, {}, approvals(ids=["org-004"]))
    assert r.canonical("CompleteTechDiscord-Games") == "CompleteTechDiscord-Games"
    assert r.successor("CompleteTechDiscord-Games") == "CompleteTech-Games"
    assert r.is_placeholder("CompleteTechDiscord-Games") and not r.is_placeholder("CompleteTech-Games")


def test_former_slugs_placeholders_and_chains(brand):
    reg = {"orgs": {"Northwind-Labs": {"former_slugs": ["Northwind-Lab"]}},
           "placeholders": [{"login": "Northwind-Old", "successor": "Northwind-Labs"}]}
    rows = [("org-rename", "Northwind-Lab0", "*", "Northwind-Lab")]  # Lab0 -> Lab -> Labs
    r = R.Resolver(brand, reg, approvals(rows=rows, actions=[]))
    assert r.canonical("Northwind-Lab0") == "Northwind-Labs"
    assert r.registry_key("northwind-lab") == "Northwind-Labs"
    assert r.successor("Northwind-Old") == "Northwind-Labs"
    cyc = R.Resolver(brand, {}, approvals(rows=[("org-rename", "Aa-org", "*", "Bb-org"), ("org-rename", "Bb-org", "*", "Aa-org")],
                                          actions=[]))
    assert cyc.canonical("Aa-org") in ("Aa-org", "Bb-org")  # a cycle terminates


def test_unknown_org_is_needs_input_not_defaults(brand):
    r = R.Resolver(brand, {}, approvals())
    with pytest.raises(NeedsInput) as e:
        r.brand_org("Nobody-Knows-This-Org")
    assert e.value.log == "needs-input:org"
    assert r.brand_org("Nobody-Knows-This-Org", strict=False)["known"] is False
    with pytest.raises(NeedsInput):
        r.registry_org("Nobody-Knows-This-Org")


def test_check_owner_refuses_under_every_alias(brand):
    r = R.Resolver(brand, {}, approvals(rows=[("org-rename", "Pick-Your-AI", "*", "Pick-Your-Stack")], actions=[]))
    with pytest.raises(Refused) as e:
        r.check_owner("Pick-Your-Stack")
    assert e.value.log == "t3-signoff"
    assert r.check_owner("Pick-Your-Stack", allow_t3=True) == "t3"
    with pytest.raises(Refused):
        r.check_owner("MetatronAngelAgent")


def test_approved_checks_wildcards_and_aliases(brand):
    rows = [("create-project", "CompleTetech-Security", "*", ""), ("org-rename", "CompleTetech-Security", "*", "CompleteTech-Security")]
    r = R.Resolver(brand, {}, approvals(rows=rows, actions=[]))
    assert r.approved("create-project", "CompleteTech-Security")
    assert not r.approved("create-project", "CompleteTech-LLC")


def test_bad_login_in_approvals_is_refused(brand):
    with pytest.raises(ShowcaseError):
        R.Resolver(brand, {}, approvals(rows=[("org-rename", "Good-Org", "*", "bad org/name")], actions=[]))


def test_load_approvals_files(tmp_path, brand):
    tsv = tmp_path / "approved.tsv"
    tsv.write_text("# generated\norg-rename\tCompleTetech-Security\t*\tCompleteTech-Security\n", encoding="utf-8")
    yml = tmp_path / "APPROVED_ACTIONS.yaml"
    yml.write_text("actions:\n  - {id: org-005, approved: true}\n  - {id: org-003, approved: false}\n", encoding="utf-8")
    act = tmp_path / "estate-actions.json"
    act.write_text(json.dumps(ACTIONS), encoding="utf-8")
    ap = R.load_approvals(tsv, yml, act)
    assert ap["ids"] == {"org-005"}
    r = R.Resolver(brand, {}, ap)
    assert r.canonical("CompleTetech-Security") == "CompleteTech-Security"
    assert r.canonical("CompleteTech-Pokemon") == "CompleteTech-TCG"
    assert r.canonical("romgenie-following-repos") == "romgenie-following-repos"
    assert r.action_approved("org-005") and not r.action_approved("org-003")


def test_registry_is_needs_input_when_missing(tmp_path):
    with pytest.raises(NeedsInput):
        R.load_registry(tmp_path / "nope.yaml")


def test_query_files_are_reads_only():
    for f in R.QUERIES.glob("*.graphql"):
        body = re.sub(r"(?m)#.*$", "", f.read_text(encoding="utf-8"))
        assert not re.search(r"\bmutation\b", body, re.I), f.name
        assert re.match(r"\s*query\b", body), f.name
        R.query_text(f.stem)


def test_query_text_refuses_a_mutation(tmp_path, monkeypatch):
    (tmp_path / "evil.graphql").write_text("mutation { deleteProjectV2(input: {projectId: \"x\"}) { clientMutationId } }")
    monkeypatch.setattr(R, "QUERIES", tmp_path)
    with pytest.raises(ShowcaseError):
        R.query_text("evil")


def test_read_command_loads_the_query_from_a_file():
    argv = R.read_command("project_capture", org="Pick-Your-AI", number=1)
    assert argv[:3] == ["gh", "api", "graphql"]
    assert "org=Pick-Your-AI" in argv and "number=1" in argv
    assert argv[-1].startswith("query=@") and argv[-1].endswith("project_capture.graphql")


def test_enterprise_snapshot_query():
    r = R.enterprise_snapshot_query("completetech")
    names = [x["name"] for x in r["reads"]]
    assert names == ["discover", "snapshot", "drift", "romgenie"]
    assert all(a[-1].startswith("query=@") for a in (x["argv"] for x in r["reads"]))
    assert "slug=completetech" in r["reads"][1]["argv"] and "slug=completetech" not in r["reads"][0]["argv"]
    with pytest.raises(ShowcaseError):
        R.enterprise_snapshot_query("Bad Slug")


SCHEMA = __import__("os").environ.get("SHOWCASE_GRAPHQL_SCHEMA")


@pytest.mark.skipif(not SCHEMA, reason="set SHOWCASE_GRAPHQL_SCHEMA to a GitHub schema SDL (fpt) to validate the queries")
def test_queries_validate_against_the_schema():
    graphql = pytest.importorskip("graphql")
    from pathlib import Path
    schema = graphql.build_schema(Path(SCHEMA).read_text(encoding="utf-8"), assume_valid=True)
    schema._validation_errors = []  # GitHub's SDL has deprecation-inheritance warnings graphql-core treats as errors
    for f in R.QUERIES.glob("*.graphql"):
        if f.name.startswith("enterprise_") and "ghec" not in SCHEMA:
            continue
        errs = graphql.validate(schema, graphql.parse(f.read_text(encoding="utf-8")))
        assert not errs, (f.name, [e.message for e in errs])


def test_estate_root_found_from_installed_copy(tmp_path):
    """The installed copy at <bundle>/.claude/skills/<name>/ still finds the bundle's registry and decisions."""
    import os
    import shutil
    import subprocess
    import sys
    from ctshowcase import ROOT
    inst = tmp_path / ".claude" / "skills" / "github-showcase-skill"
    shutil.copytree(ROOT / "scripts", inst / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "references", inst / "references")
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "estate.yaml").write_text("orgs: {}\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "SHOWCASE_ESTATE_ROOT"}
    out = subprocess.run([sys.executable, "-c", "from ctshowcase.resolver import estate_root; print(estate_root())"],
                         cwd=inst / "scripts", env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert out == str(tmp_path)
