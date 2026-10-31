"""Issue 36: License rows write a rights sentence only when the org row sets `license_wording` (synthetic owners only).

The gating itself landed in a192d1f (issue 36), which is already in the base 6dbeef6. This file is therefore a
characterization suite: all 40 tests pass on base by design, and they cannot be red on base without a source change,
which task 39 (test-only) does not make.

Red evidence is taken from the pre-gating tree, reproduced for the t#39 review: `git archive 2be04ac` with this file
and tests/test_readme_scaffold.py copied in gives 26 failed and 14 passed for this file. The 26 failures are every
no-holder, factual-line, blank-wording, holder-substitution and schema-acceptance case. The 14 passes pin unchanged
CompleteTech, CompleteTech-Security, fork and private-holder output, which is the regression they guard against.
"""
import copy

import pytest

from ctshowcase import readme
from ctshowcase.config import Brand, schema_errors
from ctshowcase.context import RepoContext
from ctshowcase.detect import standard
from ctshowcase.meta import normalize

from conftest import meta_dict

FACTUAL_MIT = "Code and documentation are licensed under the MIT License; see `LICENSE`."
FACTUAL_MIT_SKILLS = "Code, templates, and documentation are licensed under the MIT License. See `LICENSE` and `BRAND_ASSETS.md`."
RV = standard("readme-variants")["license_rows"]


def set_wording(ctx, value):
    """Give the resolved org row a holder value (a test double for a brand.yaml edit)."""
    ctx.org = dict(ctx.org, license_wording=value)


def test_unknown_owner_public_mit_gets_factual_line_only(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT)
    assert "needs-input:license-wording" in ctx.logs


def test_unknown_owner_public_mit_scaffold_has_no_reserved_names(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    out = readme.scaffold(ctx)
    assert "## License\n\n" + FACTUAL_MIT in out
    assert "reserved" not in out


def test_unknown_owner_mit_with_brand_assets_gets_factual_skills_line(make_ctx, tmp_path):
    (tmp_path / "BRAND_ASSETS.md").write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT_SKILLS)
    assert "needs-input:license-wording" in ctx.logs


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_whitespace_wording_counts_as_absent(make_ctx, tmp_path, blank):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license="MIT")
    set_wording(ctx, blank)
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT)


def test_t2_org_without_wording_does_not_use_display_name(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
    assert ctx.org["display_name"] == "LibreEvolve" and "license_wording" not in ctx.org
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT)


def test_completetech_mit_keeps_reserved_names_sentence(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license="MIT")
    assert readme.license_section(ctx) == ("License", RV["t1_mit"])
    assert "needs-input:license-wording" not in ctx.logs


def test_configured_t2_wording_substitutes_holder_not_display_name(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
    set_wording(ctx, "Example Steward Inc.")
    assert readme.license_section(ctx) == ("License", RV["t2_mit"].replace("<Brand>", "Example Steward Inc."))


def test_configured_skills_wording_substitutes_holder(make_ctx, tmp_path):
    (tmp_path / "BRAND_ASSETS.md").write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-Skills", repo="x-skill", license="MIT")
    set_wording(ctx, "Acme Holdings")
    assert readme.license_section(ctx) == ("License", RV["skills_mit"].replace("CompleteTech LLC", "Acme Holdings"))


def test_unknown_owner_other_license_gets_factual_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="Apache-2.0")
    assert readme.license_section(ctx) == ("License", "Licensed under the Apache-2.0; see `LICENSE`.")
    assert "needs-input:license-wording" in ctx.logs


def test_configured_other_license_keeps_reserved_names(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license="Apache-2.0")
    assert readme.license_section(ctx) == (
        "License", RV["other"].replace("<license>", "Apache-2.0").replace("<path>", "LICENSE").replace("<Brand>", "CompleteTech LLC"))


def test_configured_other_license_substitutes_holder(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="Apache-2.0")
    set_wording(ctx, "Example Steward Inc.")
    assert readme.license_section(ctx) == (
        "License", "Licensed under the Apache-2.0; see `LICENSE`. Example Steward Inc. names and logos are reserved and are "
                   "not licensed for reuse except to identify this project.")


def test_private_unknown_owner_has_no_copyright_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) is None
    assert "needs-input:license-wording" in ctx.logs
    out = readme.scaffold(ctx)
    assert "## License" not in out and "Copyright" not in out


def test_private_unknown_owner_with_license_still_takes_private_branch(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT", visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) is None
    assert "needs-input:license-wording" in ctx.logs


def test_private_completetech_keeps_copyright_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) == ("License", "Proprietary. Copyright (c) 2025 CompleteTech LLC. All rights reserved.")


def test_private_configured_holder_replaces_copyright_name(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    set_wording(ctx, "Example Steward Ltd")
    assert readme.license_section(ctx) == ("License", "Proprietary. Copyright (c) 2025 Example Steward Ltd. All rights reserved.")


def test_touchedbyanagent_private_without_wording_omits_hold_row(make_ctx, tmp_path):
    # the "Proprietary. All rights reserved." hold row is a reserved-rights sentence, so it needs wording too (issue 36)
    ctx = make_ctx(repo_dir=tmp_path, owner="TouchedByAnAgent", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) is None
    assert "needs-input:license-wording" in ctx.logs


def test_touchedbyanagent_private_with_wording_keeps_hold_row(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="TouchedByAnAgent", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    set_wording(ctx, "Example Steward Ltd")
    assert readme.license_section(ctx) == ("License", RV["private_hold"])


def _template():
    from conftest import ROOT
    return (ROOT / "tests" / "fixtures" / "template-README.md").read_text(encoding="utf-8")


def test_bootstrap_private_without_wording_removes_managed_license(make_ctx, tmp_path):
    ctx = make_ctx(tmp_path, owner="LibreEvolve", repo="new-thing", description="", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    out = readme.bootstrap(ctx, _template())
    assert "## License" not in out and "showcase:license" not in out.split("showcase:footer")[0].split("template-body:pristine")[-1][-200:]
    assert "needs-input:license-wording" in ctx.logs


def test_header_refresh_private_without_wording_removes_license_and_lints(make_ctx, tmp_path):
    from ctshowcase import readmelint
    kw = dict(owner="LibreEvolve", repo="thing", description="A thing.", license="MIT", visibility="private",
              created_at="2025-01-01T00:00:00Z")
    text = readme.scaffold(make_ctx(tmp_path, **kw))
    assert "## License" not in text
    # an older managed License paragraph from before the opt-in is removed on refresh, not preserved
    block = "## License\n\n<!-- showcase:license -->\nProprietary. Copyright (c) 2025 X. All rights reserved.\n\n"
    old = text.replace("<!-- showcase:footer:start -->", block + "<!-- showcase:footer:start -->", 1)
    ctx = make_ctx(tmp_path, **kw)
    refreshed = readme.header_only(ctx, old)
    assert "All rights reserved" not in refreshed and "## License" not in refreshed
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    res = readmelint.lint(make_ctx(tmp_path, **kw), tmp_path / "README.md")
    assert not any("License must be the last H2" in f for f in res["fails"])


def test_fork_upstream_path_still_returns_none(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing-fork", license="MIT")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "LICENSE").write_text("x", encoding="utf-8")
    assert readme.license_section(ctx) is None
    assert "needs-input:upstream" in ctx.logs


def test_security_agpl_row_unchanged_for_renamed_org(make_ctx, tmp_path):
    (tmp_path / "LICENSING.md").write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleTetech-Security", repo="x-check", license="AGPL-3.0")
    assert readme.license_section(ctx) == ("Licensing", RV["security"])


def test_renamed_org_inherits_wording_for_private_copyright(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleTetech-Security", repo="x-check", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert ctx.org["known"] and ctx.org["owner"] == "CompleteTech-Security"
    assert readme.license_section(ctx) == ("License", "Proprietary. Copyright (c) 2025 CompleteTech LLC. All rights reserved.")


def test_unknown_owner_has_no_key_so_no_claim(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Nobody-Here", repo="thing", license="MIT")
    assert not ctx.org["known"] and "license_wording" not in ctx.org
    assert readme.license_section(ctx) == ("License", FACTUAL_MIT)


def test_wording_log_is_recorded_once_per_context(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    readme.license_section(ctx)
    readme.license_section(ctx)
    assert ctx.logs.count("needs-input:license-wording") == 1


# --- review round: upgrade must never delete authored License text, and must gate managed sections (issue 36) ---
AUTHORED = "Internal use only by the Example team; contact the owners before sharing."


def _readme_with_license(body):
    return f"# thing\n\nA thing.\n\n## Usage\n\nRun it.\n\n## License\n\n{body}\n"


def test_upgrade_private_no_wording_keeps_authored_license_section(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    text = _readme_with_license(AUTHORED)
    out, removed = readme.upgrade(ctx, text)
    assert AUTHORED in out and AUTHORED not in removed
    assert readme.preservation(text, out, removed) == []
    assert "needs-input:license-wording" in ctx.logs


def test_upgrade_private_no_wording_drops_only_generated_license_text(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    out, _ = readme.upgrade(ctx, _readme_with_license("<!-- showcase:license -->\nProprietary. Copyright (c) 2025 X. All rights reserved."))
    assert "All rights reserved" not in out and "## License" not in out


def test_upgrade_private_no_wording_keeps_unmarked_owner_rights_notice(make_ctx, tmp_path):
    # no showcase marker means the owner wrote it: never deleted silently (review of issue 36)
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    out, removed = readme.upgrade(ctx, _readme_with_license("Proprietary. All rights reserved."))
    assert "Proprietary. All rights reserved." in out and not any("Proprietary" in r or "Custom" in r or "Copyright" in r or "showcase:license" in r for r in removed)
    assert "needs-input:license-wording" in ctx.logs


def test_upgrade_public_managed_row_keeps_marker_so_wording_applies_later(make_ctx, tmp_path):
    text = _readme_with_license("<!-- showcase:license -->\n" + RV["t2_mit"].replace("<Brand>", "LibreEvolve"))
    for preserve in (False, True):
        c = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
        if preserve:
            c.org = dict(c.org, readme_preserve=["thing"])
        out, _ = readme.upgrade(c, text)
        assert "<!-- showcase:license -->\n" + FACTUAL_MIT in out


def test_upgrade_public_factual_line_logs_missing_wording_every_run(make_ctx, tmp_path):
    c = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
    out, _ = readme.upgrade(c, _readme_with_license(FACTUAL_MIT))
    assert FACTUAL_MIT in out and "needs-input:license-wording" in c.logs


def test_upgrade_private_keeps_literal_copyright_in_fence_after_prose(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    body = "Example:\n```text\n\nProprietary. Copyright (c) 2025 Example. All rights reserved.\n\n```"
    out, removed = readme.upgrade(ctx, _readme_with_license(body))
    assert body in out and not any("Proprietary" in r or "Custom" in r or "Copyright" in r or "showcase:license" in r for r in removed)


def test_upgrade_private_keeps_indented_marker_example(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    body = "Example:\n\n    <!-- showcase:license -->\n    Custom license example.\n\nEnd of example."
    out, removed = readme.upgrade(ctx, _readme_with_license(body))
    assert body in out and not any("Proprietary" in r or "Custom" in r or "Copyright" in r or "showcase:license" in r for r in removed)


def test_upgrade_public_managed_rights_sentence_becomes_factual_line(make_ctx, tmp_path):
    managed = "<!-- showcase:license -->\n" + RV["t1_mit"]
    text = _readme_with_license(managed)
    for preserve in (False, True):
        c = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
        if preserve:
            c.org = dict(c.org, readme_preserve=["thing"])
        out, removed = readme.upgrade(c, text)
        assert FACTUAL_MIT in out and "reserved" not in out
        assert "needs-input:license-wording" in c.logs


# --- review round 2: unmarked generated public rows, and mixed managed + authored License content (issue 36) ---
def test_upgrade_public_unmarked_generated_rights_sentence_becomes_factual(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
    old = RV["t2_mit"].replace("<Brand>", "LibreEvolve")
    out, removed = readme.upgrade(ctx, _readme_with_license(old))
    assert FACTUAL_MIT in out and "reserved" not in out
    assert "needs-input:license-wording" in ctx.logs
    assert any("reserved" in r for r in removed)


def test_upgrade_public_authored_after_generated_row_survives(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
    old = RV["t2_mit"].replace("<Brand>", "LibreEvolve")
    text = _readme_with_license(old + "\n\n" + AUTHORED)
    out, removed = readme.upgrade(ctx, text)
    assert AUTHORED in out and AUTHORED not in removed and "reserved" not in out
    assert readme.preservation(text, out, removed) == []


def test_upgrade_private_marked_section_keeps_authored_paragraph(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    managed = "<!-- showcase:license -->\nProprietary. Copyright (c) 2025 X. All rights reserved."
    text = _readme_with_license(managed + "\n\n" + AUTHORED)
    out, removed = readme.upgrade(ctx, text)
    assert AUTHORED in out and AUTHORED not in removed
    assert "All rights reserved" not in out
    assert readme.preservation(text, out, removed) == []
    assert "needs-input:license-wording" in ctx.logs


# --- review round 3: fenced/indented authored examples survive, preserve mode is gated too (issue 36) ---
def _libre(make_ctx, tmp_path, **kw):
    kw.setdefault("license", None)
    kw.setdefault("visibility", "private")
    return make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", created_at="2025-01-01T00:00:00Z", **kw)


def test_upgrade_keeps_fenced_example_with_blank_lines(make_ctx, tmp_path):
    ctx = _libre(make_ctx, tmp_path)
    ex = "```text\n\nProprietary. Copyright (c) 2025 Example. All rights reserved.\n\n```"
    text = _readme_with_license(ex)
    out, removed = readme.upgrade(ctx, text)
    assert ex in out and not any("Proprietary" in r for r in removed)
    assert readme.preservation(text, out, removed) == []


def test_upgrade_keeps_indentation_of_authored_code_after_generated_row(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Acme-Labs", repo="thing", license="MIT")
    code = "    SPDX-License-Identifier: MIT\n    Documented as literal text."
    text = _readme_with_license(RV["t2_mit"].replace("<Brand>", "Acme") + "\n\n" + code)
    out, removed = readme.upgrade(ctx, text)
    assert code in out and FACTUAL_MIT in out
    assert "Acme" not in out.split("## License")[1]


def test_preserve_mode_gates_unmarked_generated_license_row(make_ctx, tmp_path):
    ctx = _libre(make_ctx, tmp_path)
    text = _readme_with_license("Proprietary. Copyright (c) 2025 Example. All rights reserved.")
    text = text.replace("Run it.", "Run it. " + "x" * 16000)  # over 15,000 bytes: preserve mode
    out, removed = readme.upgrade(ctx, text)
    # an unmarked private "Proprietary..." paragraph cannot be told from an owner's notice: kept and flagged, never deleted
    assert "All rights reserved" in out and "needs-input:license-wording" in ctx.logs
    assert "Run it. xxx" in out


# --- epic 35 review: indented-code marks are authored, and the License heading stays over authored legal text ---
def test_upgrade_keeps_prefixed_marker_inside_indented_code(make_ctx, tmp_path):
    # `    prefix <!-- showcase:license -->` is indented code: on the epic base upgrade deleted the example line and
    # joined the next paragraph onto `prefix`, and recorded every lost line as intentional (preservation() == [])
    ctx = _libre(make_ctx, tmp_path)
    body = "Example:\n\n    prefix <!-- showcase:license -->\n    example line\n\nAuthored terms stay."
    text = _readme_with_license(body)
    out, removed = readme.upgrade(ctx, text)
    assert body in out
    assert not any("example line" in r or "Authored terms" in r or "showcase:license" in r for r in removed)
    assert readme.preservation(text, out, removed) == []


def test_upgrade_cli_keeps_prefixed_marker_inside_indented_code(tmp_path):
    import json
    from conftest import meta_dict, run_cli
    repo = tmp_path / "repo"
    repo.mkdir()
    body = "Example:\n\n    prefix <!-- showcase:license -->\n    example line\n\nAuthored terms stay."
    (repo / "README.md").write_text(_readme_with_license(body), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner="LibreEvolve", repo="thing", license=None, visibility="private",
                                         created_at="2025-01-01T00:00:00Z", description="A thing.")), encoding="utf-8")
    p = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "upgrade", "--write")
    after = (repo / "README.md").read_text(encoding="utf-8")
    assert body in after, p.stdout + p.stderr


def test_managed_removal_records_only_the_managed_span(make_ctx, tmp_path):
    ctx = _libre(make_ctx, tmp_path)
    text = ("# thing\n\n## License\n\n<!-- showcase:license -->\nProprietary. Copyright (c) 2025 X. All rights reserved."
            "\n\nInternal use only.\n")
    removed = []
    out = readme.gate_managed_license(ctx, text, removed)
    assert "Internal use only." in out
    assert set(removed) <= {"<!-- showcase:license -->", "Proprietary. Copyright (c) 2025 X. All rights reserved.",
                            "## License"}


def test_header_refresh_keeps_license_heading_over_authored_paragraph(make_ctx, tmp_path):
    # on the epic base header refresh dropped `## License`, leaving the authored terms under `## Usage`
    ctx = _libre(make_ctx, tmp_path, description="A thing.")
    text = _readme_with_license("<!-- showcase:license -->\nProprietary. Copyright (c) 2025 X. All rights reserved."
                                "\n\nInternal use only.")
    out = readme.header_only(ctx, text)
    assert "All rights reserved" not in out
    assert "## License\n\nInternal use only." in out
    up, _ = readme.upgrade(_libre(make_ctx, tmp_path, description="A thing."), text)
    assert "## License" in up and "Internal use only." in up  # upgrade agrees


def test_header_refresh_still_drops_heading_when_nothing_authored_remains(make_ctx, tmp_path):
    ctx = _libre(make_ctx, tmp_path, description="A thing.")
    text = _readme_with_license("<!-- showcase:license -->\nProprietary. Copyright (c) 2025 X. All rights reserved.")
    text += "\n## Next\n\nMore.\n"
    out = readme.header_only(ctx, text)
    assert "## License" not in out and "## Next\n\nMore." in out


# --- epic 35 review round 2: the generated row ends at a Markdown block boundary, not only at a blank line ---
# On the pre-fix HEAD `readme --mode upgrade --write` deleted `### Additional terms` and the attribution written right
# under the managed row (no blank line) and recorded them as intentionally removed; the epic base kept both lines.
TIGHT_TERMS = "### Additional terms\nPreserve this mandatory attribution."


def test_upgrade_cli_keeps_subsection_right_under_managed_row(tmp_path):
    import json
    from conftest import meta_dict, run_cli
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "LICENSE").write_text("MIT", encoding="utf-8")
    (repo / "README.md").write_text(
        _readme_with_license("<!-- showcase:license -->\n" + FACTUAL_MIT + "\n" + TIGHT_TERMS), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner="LibreEvolve", repo="thing", license="MIT", description="A thing.")),
                    encoding="utf-8")
    p = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "upgrade", "--write")
    after = (repo / "README.md").read_text(encoding="utf-8")
    assert p.returncode == 0, p.stdout + p.stderr
    assert TIGHT_TERMS in after and FACTUAL_MIT in after, after


def test_upgrade_keeps_subsection_under_generated_rights_row(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT")
    old = "<!-- showcase:license -->\n" + RV["t2_mit"].replace("<Brand>", "LibreEvolve") + "\n" + TIGHT_TERMS
    text = _readme_with_license(old)
    out, removed = readme.upgrade(ctx, text)
    assert TIGHT_TERMS in out and "reserved" not in out
    assert not any("attribution" in r or "Additional terms" in r for r in removed)
    assert readme.preservation(text, out, removed) == []


def test_private_omission_keeps_subsection_under_managed_row(make_ctx, tmp_path):
    ctx = _libre(make_ctx, tmp_path, description="A thing.")
    text = _readme_with_license("<!-- showcase:license -->\nProprietary. Copyright (c) 2025 X. All rights reserved.\n"
                                + TIGHT_TERMS)
    out = readme.header_only(ctx, text)  # license_block path (header refresh and bootstrap)
    assert "All rights reserved" not in out and TIGHT_TERMS in out
    up, removed = readme.upgrade(_libre(make_ctx, tmp_path, description="A thing."), text)
    assert TIGHT_TERMS in up and "All rights reserved" not in up
    assert readme.preservation(text, up, removed) == []


def test_header_refresh_rewrite_keeps_subsection_under_managed_row(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="CompleteTech-LLC", repo="thing", license="MIT", description="A thing.")
    text = _readme_with_license("<!-- showcase:license -->\n" + FACTUAL_MIT + "\n" + TIGHT_TERMS)
    out = readme.header_only(ctx, text)
    assert "<!-- showcase:license -->\n" + RV["t1_mit"] + "\n" + TIGHT_TERMS in out


# --- epic 35 review round 3: a blank line after the mark, and H3-H6 inside the License section ---
# On the round 2 HEAD a mark followed by a blank line and the old rights sentence left that sentence behind on header
# refresh (public: the factual line was inserted above it; private: only the mark went), and `### Additional terms`
# after the managed row made the section look empty, so header refresh dropped `## License` while upgrade kept it.
OLD_T2 = RV["t2_mit"].replace("<Brand>", "LibreEvolve")
PRIVATE_ROW = "Proprietary. Copyright (c) 2025 X. All rights reserved."


def test_header_refresh_replaces_rights_row_after_a_blank_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="MIT", description="A thing.")
    text = _readme_with_license("<!-- showcase:license -->\n\n" + OLD_T2)
    assert OLD_T2 not in readme.split_generated_license("<!-- showcase:license -->\n\n" + OLD_T2)[1]  # upgrade's view
    for out in (readme.header_only(ctx, text), readme.license_block(ctx, text)):  # header refresh; bootstrap's path
        assert "## License\n\n<!-- showcase:license -->\n" + FACTUAL_MIT in out
        assert "reserved" not in out and "CompleteTech" not in out and OLD_T2 not in out, out


def test_private_refresh_removes_rights_row_after_a_blank_line(make_ctx, tmp_path):
    ctx = _libre(make_ctx, tmp_path, description="A thing.")
    text = _readme_with_license("<!-- showcase:license -->\n\n" + PRIVATE_ROW) + "\n## Next\n\nMore.\n"
    out = readme.header_only(ctx, text)
    assert "All rights reserved" not in out and "## License" not in out and "## Next\n\nMore." in out, out


def test_blank_line_then_indented_code_after_mark_stays_authored(make_ctx, tmp_path):
    ctx = _libre(make_ctx, tmp_path, description="A thing.")
    code = "    Copyright (c) 2025 X. All rights reserved."
    text = _readme_with_license("<!-- showcase:license -->\n\n" + code)
    assert code in readme.header_only(ctx, text)


def test_header_refresh_keeps_license_heading_over_nested_subsection(make_ctx, tmp_path):
    ctx = _libre(make_ctx, tmp_path, description="A thing.")
    text = _readme_with_license("<!-- showcase:license -->\n" + PRIVATE_ROW + "\n\n### Additional terms\n\nKeep this.")
    out = readme.header_only(ctx, text)
    assert "All rights reserved" not in out
    assert "## License\n\n### Additional terms\n\nKeep this." in out, out
    up, _ = readme.upgrade(_libre(make_ctx, tmp_path, description="A thing."), text)
    assert "## License" in up and "### Additional terms" in up  # upgrade agrees
# ------------------------------------------------------------------------------------------------
# Spec E2.1.3: synthetic owners and a brand copy with a test-only license_wording holder
# ------------------------------------------------------------------------------------------------
NO_CLAIM_WORDS = ("reserved", "names and logos", "Copyright", "rights")


def brand_copy(brand, mutate):
    """A copy of the loaded brand with `mutate(raw)` applied; the real references/brand.yaml is never edited."""
    raw = copy.deepcopy(brand.raw)
    mutate(raw)
    return Brand(raw, brand.path)


def wording_brand(brand, owner, value):
    return brand_copy(brand, lambda raw: raw["orgs"][owner].__setitem__("license_wording", value))


def ctx_for(b, repo_dir, **kw):
    return RepoContext(b, normalize(meta_dict(**kw)), repo_dir)


def test_org_without_wording_gets_no_claim_public_mit(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Pick-Your-AI", repo="thing", license="MIT")
    result = readme.license_section(ctx)
    assert result == ("License", "Code and documentation are licensed under the MIT License; see `LICENSE`.")
    assert not any(word in result[1] for word in NO_CLAIM_WORDS)
    assert "needs-input:license-wording" in ctx.logs


def test_org_without_wording_gets_no_claim_other_license(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="LibreEvolve", repo="thing", license="Apache-2.0")
    result = readme.license_section(ctx)
    assert result == ("License", "Licensed under the Apache-2.0; see `LICENSE`.")
    assert not any(word in result[1] for word in NO_CLAIM_WORDS)
    assert "needs-input:license-wording" in ctx.logs


def test_org_without_wording_skills_mit_keeps_factual_brand_assets_pointer(make_ctx, tmp_path):
    (tmp_path / "BRAND_ASSETS.md").write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner="AI-Ascension", repo="thing", license="MIT")
    result = readme.license_section(ctx)
    assert result == ("License", "Code, templates, and documentation are licensed under the MIT License. "
                                 "See `LICENSE` and `BRAND_ASSETS.md`.")
    assert "reserved" not in result[1]


def test_private_repo_without_wording_gets_no_copyright_line(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, owner="Pick-Your-AI", repo="thing", visibility="private", license=None,
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) is None
    assert "needs-input:license-wording" in ctx.logs
    out = readme.scaffold(ctx)
    assert "Copyright" not in out and "## License" not in out


def test_private_repo_with_wording_gets_copyright_line(brand, tmp_path):
    b = wording_brand(brand, "Pick-Your-AI", "Example Holder LLC")
    ctx = ctx_for(b, tmp_path, owner="Pick-Your-AI", repo="thing", visibility="private", license=None,
                  created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) == ("License", "Proprietary. Copyright (c) 2025 Example Holder LLC. All rights reserved.")


def test_public_mit_with_wording_names_the_configured_holder(brand, tmp_path):
    b = wording_brand(brand, "Pick-Your-AI", "Example Holder LLC")
    ctx = ctx_for(b, tmp_path, owner="Pick-Your-AI", repo="thing", license="MIT")
    result = readme.license_section(ctx)
    assert result == ("License", "Code and documentation are licensed under the MIT License; see `LICENSE`. "
                                 "Example Holder LLC names and logos are reserved and are not licensed for reuse except to "
                                 "identify this project.")
    assert "Pick Your AI" not in result[1]
    assert "needs-input:license-wording" not in ctx.logs


def test_blank_wording_counts_as_absent(brand, tmp_path):
    b = wording_brand(brand, "Pick-Your-AI", "   ")
    ctx = ctx_for(b, tmp_path, owner="Pick-Your-AI", repo="thing", license="MIT")
    assert readme.license_section(ctx) == ("License", "Code and documentation are licensed under the MIT License; see `LICENSE`.")
    assert "needs-input:license-wording" in ctx.logs


@pytest.mark.parametrize("owner,files,heading,row", [
    ("CompleteTech-LLC", (), "License", "t1_mit"),
    # base behaviour: CompleteTech-Security is the F (security) layout, so even a public MIT repo takes the security row
    ("CompleteTech-Security", (), "Licensing", "security"),
    ("CompleteTech-Skills", ("BRAND_ASSETS.md",), "License", "skills_mit"),
])
def test_completetech_output_unchanged(make_ctx, tmp_path, owner, files, heading, row):
    for name in files:
        (tmp_path / name).write_text("x", encoding="utf-8")
    ctx = make_ctx(repo_dir=tmp_path, owner=owner, repo="thing", license="MIT")
    assert readme.license_section(ctx) == (heading, RV[row])
    assert "needs-input:license-wording" not in ctx.logs


@pytest.mark.parametrize("owner", [
    "CompleteTech-LLC",
    # deliberate former slug, not a typo: references/brand.yaml lists `former_slugs: [CompleTetech-Security]` on the
    # CompleteTech-Security row, and the resolver (CQ-03) must keep renamed orgs resolving to the same row
    "CompleTetech-Security",
])
def test_completetech_private_output_unchanged(make_ctx, tmp_path, owner):
    ctx = make_ctx(repo_dir=tmp_path, owner=owner, repo="thing", license=None, visibility="private",
                   created_at="2025-01-01T00:00:00Z")
    assert readme.license_section(ctx) == ("License", RV["private"].replace("<year>", "2025"))


def test_security_agpl_row_unchanged_without_wording(brand, tmp_path):
    b = brand_copy(brand, lambda raw: raw["orgs"]["CompleteTech-Security"].pop("license_wording"))
    ctx = ctx_for(b, tmp_path, owner="CompleteTech-Security", repo="thing", license="AGPL-3.0")
    assert readme.license_section(ctx) == ("Licensing", RV["security"])


@pytest.mark.parametrize("value,accepted", [("Example Holder LLC", True), ("", False), (123, False)])
def test_schema_accepts_and_rejects_license_wording(brand, value, accepted):
    # schema_errors is the repository's own validator (the same entry point test_config.py uses); no new dependency
    raw = copy.deepcopy(brand.raw)
    raw["orgs"]["Pick-Your-AI"]["license_wording"] = value
    errors = schema_errors(raw)
    assert (errors == []) is accepted
    if not accepted:
        assert any("license_wording" in e for e in errors)


def test_brand_yaml_sets_wording_only_on_completetech_t1_rows(brand):
    orgs = brand.raw["orgs"]
    for name, row in orgs.items():
        if "license_wording" in row:
            assert row["family"] == "completetech", name
            assert row["tier"] in ("T1", "T1-user"), name
            assert row["license_wording"] == "CompleteTech LLC", name
    for name in ("Pick-Your-AI", "LibreEvolve", "AI-Ascension", "TouchedByAnAgent"):
        assert "license_wording" not in orgs[name], name
