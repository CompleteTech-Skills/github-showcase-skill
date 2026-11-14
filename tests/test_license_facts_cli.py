"""Factual README license selection and policy reconciliation through the final CLI (#165)."""
import json

import pytest

from conftest import run_cli


def test_direct_license_selector_rejects_unnormalized_value(make_ctx):
    from ctshowcase.errors import NeedsInput
    from ctshowcase.readme import license_facts

    ctx = make_ctx()
    ctx.meta["license"] = ["MIT"]
    with pytest.raises(NeedsInput, match="license identifier must be a string"):
        license_facts(ctx)


def test_trimmed_spdx_remains_factual(tmp_path, monkeypatch):
    out, _, _ = invoke(tmp_path, monkeypatch, license="  MIT  ")
    assert "![License MIT]" in out["diff"]
    assert "needs-input:license" not in out["logs"]


@pytest.mark.parametrize("owner,visibility", [("LibreEvolve", "public"), ("LibreEvolve", "private"),
                                              ("CompleteTech-Security", "public")])
@pytest.mark.parametrize("license_value", [123, ["MIT"], {"spdx_id": ["MIT"]}, {"key": False}])
@pytest.mark.parametrize("operation", ["--diff", "--write"])
def test_invalid_license_refuses_before_writing(tmp_path, monkeypatch, owner, visibility, license_value, operation):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty-estate"))
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    sentinels = {"README.md": b"# Authored sentinel\n\nKeep this text.\n", "LICENSE": b"Unrecognized license sentinel\n",
                 "LICENSING.md": b"Owner terms sentinel\n"}
    for name, content in sentinels.items():
        (checkout / name).write_bytes(content)
    metadata = tmp_path / "meta.json"
    metadata.write_text(json.dumps({"owner": owner, "repo": "synthetic-license-control", "visibility": visibility,
                                    "description": "Inspect synthetic records.", "license": license_value}))
    before = metadata.read_bytes()
    result = run_cli("--meta", metadata, "--repo-dir", checkout, "readme", "--mode", "scaffold", operation)
    assert result.returncode == 4, (result.stdout, result.stderr)
    assert json.loads(result.stdout)["logs"] == ["needs-input:license"]
    assert "Traceback" not in result.stderr
    assert metadata.read_bytes() == before
    assert {p.name: p.read_bytes() for p in checkout.iterdir()} == sentinels


@pytest.mark.parametrize("owner,visibility", [("LibreEvolve", "public"), ("LibreEvolve", "private"),
                                              ("CompleteTech-Security", "public")])
@pytest.mark.parametrize("operation", ["--diff", "--write"])
def test_blank_license_is_unavailable(tmp_path, monkeypatch, owner, visibility, operation):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty-estate"))
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "LICENSE").write_text("Unrecognized license sentinel\n")
    metadata = tmp_path / "meta.json"
    metadata.write_text(json.dumps({"owner": owner, "repo": "synthetic-license-control", "visibility": visibility,
                                    "description": "Inspect synthetic records.", "license": "  \t "}))
    before = metadata.read_bytes()
    result = run_cli("--meta", metadata, "--repo-dir", checkout, "readme", "--mode", "scaffold", operation)
    assert result.returncode == 0, (result.stdout, result.stderr)
    out = json.loads(result.stdout)
    assert "needs-input:license" in out["logs"]
    text = out["diff"] if operation == "--diff" else (checkout / "README.md").read_text()
    assert "license-%20" not in text and "Licensed under the   " not in text
    assert metadata.read_bytes() == before
    assert (checkout / "LICENSE").read_text() == "Unrecognized license sentinel\n"


def invoke(tmp_path, monkeypatch, *, owner="LibreEvolve", visibility="public", license="MIT",
           license_file=True, licensing_file=False, variant=None, authored=None):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty-estate"))
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    if license_file:
        title = "MIT License" if license == "MIT" else "GNU AFFERO GENERAL PUBLIC LICENSE"
        (checkout / "LICENSE").write_text(title + "\nSynthetic Northwind test terms.\n", encoding="utf-8")
    if licensing_file:
        (checkout / "LICENSING.md").write_text("Synthetic configured-policy evidence.\n", encoding="utf-8")
    if authored:
        (checkout / "README.md").write_text(authored, encoding="utf-8")
    original_files = {p.name: p.read_bytes() for p in checkout.iterdir()}
    metadata = tmp_path / "meta.json"
    metadata.write_text(json.dumps({"owner": owner, "repo": "synthetic-license-control",
        "description": "Inspect synthetic Northwind records from the command line.",
        "license": license, "visibility": visibility, "language": "Python",
        "fork": False, "archived": False, "created_at": "2024-01-02T00:00:00Z"}), encoding="utf-8")
    args = ["--meta", metadata, "--repo-dir", checkout, "readme", "--mode", "upgrade" if authored else "scaffold",
            "--diff"]
    if variant:
        args += ["--variant", variant]
    result = run_cli(*args)
    assert result.returncode == 0, (result.stdout, result.stderr)
    output = json.loads(result.stdout)
    assert output["written"] is False
    assert {p.name: p.read_bytes() for p in checkout.iterdir()} == original_files
    return output, checkout, metadata


def test_private_mit_badge_uses_fact_without_legal_wording(tmp_path, monkeypatch):
    out, _, _ = invoke(tmp_path, monkeypatch, visibility="private")
    assert "![License MIT]" in out["diff"]
    assert "proprietary" not in out["diff"].lower()
    assert "## License" not in out["diff"]
    assert "needs-input:license-wording" in out["logs"]
    assert "Internal LibreEvolve repository. Not for distribution." in out["diff"]


@pytest.mark.parametrize("license, expected", [("MIT", "Code and documentation are licensed under the MIT License"),
                                              ("AGPL-3.0", "Licensed under the AGPL-3.0")])
def test_ordinary_license_facts_remain_factual(tmp_path, monkeypatch, license, expected):
    out, _, _ = invoke(tmp_path, monkeypatch, license=license)
    assert f"![License {license}]" in out["diff"]
    assert expected + "; see `LICENSE`." in out["diff"]
    assert "commercial" not in out["diff"]
    assert "needs-input:license-policy" not in out["logs"]


def test_security_mit_keeps_layout_and_reports_policy_conflict(tmp_path, monkeypatch):
    out, _, _ = invoke(tmp_path, monkeypatch, owner="CompleteTech-Security")
    assert out["variant"] == "F"
    assert "+# " not in out["diff"]
    assert 'alt="License MIT"' in out["diff"]
    assert "## Licensing" in out["diff"]
    assert "MIT License; see `LICENSE`." in out["diff"]
    assert "GNU AGPL" not in out["diff"] and "commercial" not in out["diff"]
    assert "LICENSING.md" not in out["diff"]
    assert "needs-input:license-policy" in out["logs"]


@pytest.mark.parametrize("owner, visibility", [("LibreEvolve", "public"), ("LibreEvolve", "private"),
                                              ("CompleteTech-Security", "public")])
def test_missing_license_has_no_invented_license_claim(tmp_path, monkeypatch, owner, visibility):
    out, _, _ = invoke(tmp_path, monkeypatch, owner=owner, visibility=visibility,
                       license=None, license_file=False)
    assert "needs-input:license" in out["logs"]
    assert "## Licens" not in out["diff"]
    assert "GNU AGPL" not in out["diff"] and "commercial" not in out["diff"]
    assert "proprietary" not in out["diff"].lower()


@pytest.mark.parametrize("license_file, licensing_file, missing", [
    (True, False, "needs-input:licensing-file"), (False, True, "needs-input:license-file"),
    (False, False, "needs-input:license-file")])
def test_security_policy_needs_both_referenced_files(tmp_path, monkeypatch, license_file, licensing_file, missing):
    out, _, _ = invoke(tmp_path, monkeypatch, owner="CompleteTech-Security", license="AGPL-3.0",
                       license_file=license_file, licensing_file=licensing_file)
    assert missing in out["logs"]
    assert 'alt="License AGPL-3.0"' in out["diff"]
    assert "commercial" not in out["diff"]
    assert "Available under the GNU" not in out["diff"]
    assert ("; see `LICENSE`" in out["diff"]) == license_file


@pytest.mark.parametrize("variant", [None, "C"])
def test_supported_configured_dual_policy_preserved(tmp_path, monkeypatch, variant):
    out, _, _ = invoke(tmp_path, monkeypatch, owner="CompleteTech-Security", license="AGPL-3.0",
                       licensing_file=True, variant=variant)
    assert 'AGPL-3.0 or commercial license' in out["diff"]
    assert "Available under the GNU AGPL-3.0 or a commercial license; see `LICENSE` and `LICENSING.md`." in out["diff"]
    assert 'href="LICENSING.md"' in out["diff"] if variant is None else "](LICENSING.md)" in out["diff"]
    assert not any(x in out["logs"] for x in ("needs-input:license-policy", "needs-input:license-file",
                                               "needs-input:licensing-file"))


def test_variant_alone_cannot_supply_commercial_policy(tmp_path, monkeypatch):
    out, _, _ = invoke(tmp_path, monkeypatch, license="AGPL-3.0", licensing_file=True, variant="F")
    assert "needs-input:license-policy" in out["logs"]
    assert "Licensed under the AGPL-3.0; see `LICENSE`." in out["diff"]
    assert "commercial" not in out["diff"]


def test_explicit_private_wording_preserved_without_inferring_badge(tmp_path, monkeypatch):
    out, _, _ = invoke(tmp_path, monkeypatch, owner="CompleteTech-LLC", visibility="private",
                       license=None, license_file=False)
    assert "Proprietary. Copyright (c) 2024 CompleteTech LLC. All rights reserved." in out["diff"]
    assert "![License proprietary]" not in out["diff"]
    assert "needs-input:license" in out["logs"]
    assert "needs-input:license-wording" not in out["logs"]


def test_known_license_without_file_does_not_invent_reference(tmp_path, monkeypatch):
    out, _, _ = invoke(tmp_path, monkeypatch, license_file=False)
    assert "Code and documentation are licensed under the MIT License." in out["diff"]
    assert "`LICENSE`" not in out["diff"]
    assert "needs-input:license-file" in out["logs"]


@pytest.mark.parametrize("owner, visibility, license, licensing_file", [
    ("LibreEvolve", "private", "MIT", False), ("CompleteTech-Security", "public", "MIT", False),
    ("CompleteTech-Security", "public", "AGPL-3.0", False)])
def test_authored_legal_text_survives_upgrade_and_marked_header(tmp_path, monkeypatch, owner, visibility,
                                                              license, licensing_file):
    authored = "# Synthetic Northwind Control\n\n## License\n\n<!-- showcase:license -->\nOwner-authored terms remain verbatim; see `LICENSE`.\n"
    out, checkout, metadata = invoke(tmp_path, monkeypatch, owner=owner, visibility=visibility, license=license,
                                     licensing_file=licensing_file, authored=authored)
    assert "-Owner-authored" not in out["diff"]
    result = run_cli("--meta", metadata, "--repo-dir", checkout, "readme", "--mode", "header", "--diff")
    assert result.returncode == 0, (result.stdout, result.stderr)
    header = json.loads(result.stdout)
    assert "-Owner-authored" not in header["diff"]
    assert (checkout / "README.md").read_text(encoding="utf-8") == authored


@pytest.mark.parametrize("owner, visibility", [("LibreEvolve", "private"), ("CompleteTech-Security", "public")])
def test_write_keeps_license_file_and_does_not_create_terms(tmp_path, monkeypatch, owner, visibility):
    _, checkout, metadata = invoke(tmp_path, monkeypatch, owner=owner, visibility=visibility)
    license_before = (checkout / "LICENSE").read_bytes()
    result = run_cli("--meta", metadata, "--repo-dir", checkout, "readme", "--mode", "scaffold", "--write")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert json.loads(result.stdout)["written"] is True
    generated = (checkout / "README.md").read_text(encoding="utf-8")
    assert "License MIT" in generated
    assert "GNU AGPL" not in generated and "commercial" not in generated
    assert "proprietary" not in generated.lower()
    assert (checkout / "LICENSE").read_bytes() == license_before
    assert not (checkout / "LICENSING.md").exists()


@pytest.mark.parametrize("license", ["AGPL-3.0-only", "AGPL-3.0-or-later"])
def test_supported_spdx_spellings_keep_configured_policy(tmp_path, monkeypatch, license):
    out, _, _ = invoke(tmp_path, monkeypatch, owner="CompleteTech-Security", license=license, licensing_file=True)
    assert "Available under the GNU AGPL-3.0 or a commercial license" in out["diff"]
    assert "needs-input:license-policy" not in out["logs"]


def test_different_agpl_version_is_not_rewritten_to_three(tmp_path, monkeypatch):
    out, _, _ = invoke(tmp_path, monkeypatch, owner="CompleteTech-Security", license="AGPL-1.0", licensing_file=True)
    assert "needs-input:license-policy" in out["logs"]
    assert "Licensed under the AGPL-1.0; see `LICENSE`." in out["diff"]
    assert "commercial" not in out["diff"]


@pytest.mark.parametrize("directory", ["LICENSE", "LICENSING.md", "both"])
def test_security_directories_are_not_license_evidence(tmp_path, monkeypatch, directory):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty-estate"))
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for name in ("LICENSE", "LICENSING.md"):
        path = checkout / name
        if directory in (name, "both"):
            path.mkdir()
            (path / "nested").write_text("Synthetic terms", encoding="utf-8")
        else:
            path.write_text("Synthetic terms", encoding="utf-8")
    authored = "# Synthetic\n\n## License\n\n<!-- showcase:license -->\nOwner-authored terms.\n"
    (checkout / "README.md").write_text(authored, encoding="utf-8")
    metadata = tmp_path / "meta.json"
    metadata.write_text(json.dumps({"owner": "CompleteTech-Security", "repo": "synthetic-control",
                                    "visibility": "public", "license": "AGPL-3.0",
                                    "description": "Inspect synthetic records."}), encoding="utf-8")
    for mode in ("scaffold", "header"):
        result = run_cli("--meta", metadata, "--repo-dir", checkout, "readme", "--mode", mode, "--diff")
        assert result.returncode == 0, (result.stdout, result.stderr)
        out = json.loads(result.stdout)
        assert "commercial" not in out["diff"]
        if directory in ("LICENSE", "both"):
            assert "needs-input:license-file" in out["logs"]
            assert "; see `LICENSE`" not in out["diff"]
        if directory in ("LICENSING.md", "both"):
            assert "needs-input:licensing-file" in out["logs"]
            assert 'href="LICENSING.md"' not in out["diff"]
        if mode == "header":
            assert "-Owner-authored terms." not in out["diff"]
    assert (checkout / "README.md").read_text(encoding="utf-8") == authored


@pytest.mark.parametrize("files, supported", [
    (["LICENSE", "LICENSING.md"], True),
    (["LICENSE/terms", "LICENSING.md/terms"], False),
    (["LICENSE", "LICENSE/terms", "LICENSING.md"], False),
    (["LICENSE", "LICENSING.md/terms"], False),
    ([], False),
    (None, False),
])
@pytest.mark.parametrize("complete", [True, False, None])
def test_captured_tree_requires_exact_unambiguous_files(brand, files, supported, complete):
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize
    from ctshowcase.readme import license_facts, license_reference

    meta = {"owner": "CompleteTech-Security", "repo": "synthetic-control", "visibility": "public",
            "license": "AGPL-3.0", "files": files, "files_complete": complete}
    ctx = RepoContext(brand, normalize(meta))
    assert license_facts(ctx) == ("AGPL-3.0", supported)
    license_present = files is not None and "LICENSE" in files and "LICENSE/terms" not in files
    assert ("`LICENSE`" in license_reference(ctx)) == license_present


@pytest.mark.parametrize("owner,license,licensing_file", [
    ("LibreEvolve", "MIT", False), ("CompleteTech-Security", "AGPL-3.0", True)])
def test_valid_header_preserves_unverified_authored_license(tmp_path, monkeypatch, owner, license, licensing_file):
    authored = "# Synthetic\n\n## License\n\n<!-- showcase:license -->\nOwner-authored terms.\n"
    _, checkout, metadata = invoke(tmp_path, monkeypatch, owner=owner, license=license,
                                   licensing_file=licensing_file, authored=authored)
    result = run_cli("--meta", metadata, "--repo-dir", checkout, "readme", "--mode", "header", "--write")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "Owner-authored terms." in (checkout / "README.md").read_text()
    assert "needs-input:license-policy" not in json.loads(result.stdout)["logs"]


def test_private_proprietary_policy_conflicts_with_captured_mit(tmp_path, monkeypatch):
    out, _, _ = invoke(tmp_path, monkeypatch, owner="CompleteTech-LLC", visibility="private")
    assert "![License MIT]" in out["diff"]
    assert "Proprietary. Copyright (c) 2024 CompleteTech LLC." in out["diff"]
    assert "needs-input:license-policy" in out["logs"]


def test_generated_license_updates_until_edited(tmp_path, monkeypatch):
    _, checkout, metadata = invoke(tmp_path, monkeypatch)
    args = ["--meta", metadata, "--repo-dir", checkout, "readme"]
    result = run_cli(*args, "--mode", "scaffold", "--write")
    assert result.returncode == 0
    readme = checkout / "README.md"
    assert "showcase:license:sha256=" in readme.read_text()
    meta = json.loads(metadata.read_text())
    meta["license"] = "AGPL-3.0"
    metadata.write_text(json.dumps(meta))
    result = run_cli(*args, "--mode", "header", "--write")
    assert result.returncode == 0
    assert "Licensed under the AGPL-3.0" in readme.read_text()
    edited = readme.read_text().replace("Licensed under the AGPL-3.0", "Owner-edited terms")
    readme.write_text(edited)
    meta["license"] = "MIT"
    metadata.write_text(json.dumps(meta))
    result = run_cli(*args, "--mode", "header", "--write")
    assert result.returncode == 0
    assert "Owner-edited terms" in readme.read_text()


def test_malformed_license_digest_preserves_authored_paragraph(tmp_path, monkeypatch):
    authored = ("# Synthetic\n\n## License\n\n<!-- showcase:license -->\n"
                "<!-- showcase:license:sha256=broken -->\nOwner terms.\n")
    _, checkout, metadata = invoke(tmp_path, monkeypatch, authored=authored)
    result = run_cli("--meta", metadata, "--repo-dir", checkout, "readme", "--mode", "header", "--write")
    assert result.returncode == 0
    assert "<!-- showcase:license:sha256=broken -->\nOwner terms." in (checkout / "README.md").read_text()
