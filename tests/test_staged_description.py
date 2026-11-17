"""Explicit staged-description provenance and drift, using synthetic public metadata."""
import hashlib
import json

import pytest

from conftest import meta_dict, run_cli
from ctshowcase.readme import tagline_body
from ctshowcase.staged import prepare, record_output, tagline_drift, tagline_forms
from ctshowcase.errors import NeedsInput
from ctshowcase.fingerprint import read_sidecar


def test_prepare_does_not_change_capture():
    meta = meta_dict(description="Captured sentence.")
    proposed, info = prepare(meta, "Proposed sentence.")
    assert meta["description"] == "Captured sentence."
    assert proposed["description"] == "Proposed sentence."
    assert info["sha256"] == hashlib.sha256(b"Proposed sentence.").hexdigest()
    assert info["live_description_sha256"] == hashlib.sha256(b"Captured sentence.").hexdigest()


@pytest.mark.parametrize("text", ["", "  ", "First line.\nSecond line."])
def test_invalid_proposal_is_needs_input(text):
    with pytest.raises(NeedsInput):
        prepare(meta_dict(), text)


def test_output_records_are_independent(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path)
    ctx.meta, ctx.staged_description = prepare(ctx.meta, "Proposed sentence.")
    record_output(ctx, tmp_path / "assets/social-preview.png", {"sha256": "social-hash"})
    first = read_sidecar(tmp_path / "docs/images")
    ctx.meta, ctx.staged_description = prepare(ctx.meta, "A revised sentence.")
    record_output(ctx, tmp_path / "README.md", {"sha256": "readme-hash"})
    outputs = read_sidecar(tmp_path / "docs/images")["outputs"]
    assert outputs["assets/social-preview.png"] == first["outputs"]["assets/social-preview.png"]
    assert outputs["README.md"]["staged_description"]["text"] == "A revised sentence."


def test_drift_uses_managed_tagline_not_matching_body(make_ctx):
    ctx = make_ctx(description="Current sentence.")
    stale = "<!-- showcase:tagline:start -->\n**Old sentence.**\n<!-- showcase:tagline:end -->\nCurrent sentence.\n"
    assert tagline_drift(ctx, stale)
    assert not tagline_drift(ctx, stale.replace("Old sentence.", "Current sentence."))
    assert not tagline_drift(ctx, "```html\n" + stale + "```\n")
    assert not tagline_drift(ctx, "Unmanaged README.")


TAG = "<!-- showcase:tagline:start -->\n{}\n<!-- showcase:tagline:end -->\n"


def test_drift_forms_come_from_tagline_body(make_ctx):
    """The accepted forms are exactly what readme.tagline_body writes, for the detected and every other variant."""
    ctx = make_ctx(description="Current sentence.")
    forms = tagline_forms(ctx)
    assert tagline_body(ctx) in forms
    for variant in "ABCDEFGHIJ":
        other = make_ctx(description="Current sentence.")
        other.det = dict(other.det, variant=variant)
        assert tagline_body(other) in forms
        assert not tagline_drift(ctx, TAG.format(tagline_body(other)))
    assert forms == {"**Current sentence.**", '<p align="center"><b>Current sentence.</b></p>'}
    assert tagline_drift(ctx, TAG.format("<b>Current sentence.</b>"))  # readme would rewrite this form
    assert tagline_drift(ctx, TAG.format(""))  # an emptied block no longer carries the live description


def test_empty_live_description_keeps_authored_tagline_without_drift(make_ctx):
    """readme keeps an authored tagline under needs-input:description, so it is not description drift."""
    ctx = make_ctx(description="")
    authored = TAG.format("**An authored line the owner wrote.**")
    assert not tagline_drift(ctx, authored)
    assert not tagline_drift(ctx, TAG.format(""))
    assert "needs-input:description" not in ctx.logs  # the comparison itself logs nothing
    assert tagline_body(ctx, "**An authored line the owner wrote.**", authored) == "**An authored line the owner wrote.**"


def test_cli_doctor_empty_live_description_is_not_drift(tmp_path):
    capture = tmp_path / "meta.json"
    target = tmp_path / "repo"
    target.mkdir()
    (target / "README.md").write_text("# support-triage-agent\n\n" + TAG.format("**An authored line.**"),
                                      encoding="utf-8")
    capture.write_text(json.dumps(meta_dict(description="")), encoding="utf-8")
    doctor = run_cli("--meta", capture, "--repo-dir", target, "doctor", "--format", "json")
    report = json.loads(doctor.stdout)
    assert "description-drift:readme" not in report["logs"], report


@pytest.mark.parametrize("variant", ["G", "H"])
def test_cli_fork_and_archive_variants_write_no_tagline(tmp_path, variant):
    """G and H write a callout, not a tagline block, so there is nothing to drift; a leftover block is still checked."""
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    target = tmp_path / "repo"
    (target / ".github").mkdir(parents=True)
    (target / ".github/showcase.yml").write_text(f"variant: {variant}\n", encoding="utf-8")
    (target / "README.md").write_text("# support-triage-agent\n\nAuthored body.\n", encoding="utf-8")
    args = ["--meta", capture, "--repo-dir", target]
    result = run_cli(*args, "readme", "--mode", "upgrade", "--variant", variant, "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "showcase:tagline" not in readme
    report = json.loads(run_cli(*args, "doctor", "--format", "json").stdout)
    assert "description-drift:readme" not in report["logs"]
    (target / "README.md").write_text(readme + "\n" + TAG.format("**Old sentence.**"), encoding="utf-8")
    report = json.loads(run_cli(*args, "doctor", "--format", "json").stdout)
    assert "description-drift:readme" in report["logs"]


@pytest.mark.parametrize("surface", ["banner", "card", "social"])
def test_cli_staged_art_keeps_capture_and_records_proposal(surface, tmp_path):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict(description="Run the Northwind triage agent.")), encoding="utf-8")
    target = tmp_path / "repo"
    (target / ".github").mkdir(parents=True)
    (target / ".github/showcase.yml").write_text("chips:\n  key: ['Triage']\n  attrs: ['Python']\n", encoding="utf-8")
    out = target / ("assets/social-preview.png" if surface == "social" else f"docs/images/{surface}." + ("svg" if surface == "card" else "png"))
    command = ["content", "social"] if surface == "social" else [surface]
    result = run_cli("--meta", capture, "--repo-dir", target, "--format", "json", *command,
                     "--description", "Route support requests.", "--out", out)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert "staged-description" in report["logs"]
    assert json.loads(capture.read_text())["description"] == "Run the Northwind triage agent."
    records = read_sidecar(target / "docs/images")["outputs"]
    assert any(r.get("staged_description", {}).get("text") == "Route support requests." for r in records.values())


def test_readme_staged_dry_run_and_write(tmp_path):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict(description="Run the Northwind triage agent.")), encoding="utf-8")
    target = tmp_path / "repo"
    target.mkdir()
    args = ["--meta", capture, "--repo-dir", target, "--format", "json", "readme", "--mode", "scaffold",
            "--description", "Route support requests."]
    dry = run_cli(*args)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "staged-description" in json.loads(dry.stdout)["logs"]
    assert not (target / "docs/images/.showcase.json").exists()
    written = run_cli(*args, "--write")
    assert written.returncode == 0, written.stdout + written.stderr
    assert "**Route support requests.**" in (target / "README.md").read_text(encoding="utf-8")
    record = read_sidecar(target / "docs/images")["outputs"]["README.md"]
    assert record["staged_description"]["text"] == "Route support requests."
    doctor = run_cli("--meta", capture, "--repo-dir", target, "doctor", "--format", "json")
    assert doctor.returncode == 1, doctor.stdout + doctor.stderr
    report = json.loads(doctor.stdout)
    assert report["cells"]["R2"] == "fail"
    assert "description-drift:readme" in report["logs"]


@pytest.mark.parametrize("variant", list("ABCDEFIJ"))
def test_cli_generated_variant_tagline_has_no_drift(tmp_path, variant):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    target = tmp_path / "repo"
    (target / ".github").mkdir(parents=True)
    (target / ".github/showcase.yml").write_text(f"variant: {variant}\n", encoding="utf-8")
    args = ["--meta", capture, "--repo-dir", target]
    result = run_cli(*args, "readme", "--mode", "scaffold", "--write")
    assert result.returncode == 0, result.stderr
    doctor = run_cli(*args, "doctor", "--format", "json")
    report = json.loads(doctor.stdout)
    assert "description-drift:readme" not in report["logs"]


@pytest.mark.parametrize("surface", ["banner", "card", "social", "readme"])
def test_cli_ordinary_refresh_replaces_only_its_staged_records(tmp_path, surface):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict(id=12345)), encoding="utf-8")
    target = tmp_path / "repo"
    (target / ".github").mkdir(parents=True)
    (target / ".github/showcase.yml").write_text("chips:\n  key: ['Triage']\n  attrs: ['Python']\n", encoding="utf-8")
    common = ["--meta", capture, "--repo-dir", target, "--format", "json"]
    # A separate staged output must survive every refresh untouched.
    other = run_cli(*common, "content", "social", "--description", "A separate proposal.")
    assert other.returncode == 0, other.stderr
    if surface == "social":
        command = ["readme", "--mode", "scaffold", "--write"]
        other = run_cli(*common, *command, "--description", "A separate proposal.")
        assert other.returncode == 0, other.stderr
    commands = {"banner": ["banner"], "card": ["card", "--png", target / "docs/images/card.png"],
                "social": ["content", "social"], "readme": ["readme", "--mode", "scaffold", "--write"]}
    command = commands[surface]
    staged = run_cli(*common, *command, "--description", "Route support requests.")
    assert staged.returncode == 0, staged.stdout + staged.stderr
    sidecar = target / "docs/images"
    before = read_sidecar(sidecar)["outputs"]
    keys = {"banner": ["banner.png"], "card": ["card.svg", "card.png"],
            "social": ["assets/social-preview.png"], "readme": ["README.md"]}[surface]
    untouched = "README.md" if surface == "social" else "assets/social-preview.png"
    for key in keys:
        assert before[key]["staged_description"]["text"] == "Route support requests."
        if surface in ("banner", "card"):
            assert before[key]["repository_id"] == 12345
    ordinary = run_cli(*common, *command)
    assert ordinary.returncode == 0, ordinary.stdout + ordinary.stderr
    after = read_sidecar(sidecar)["outputs"]
    assert after[untouched] == before[untouched]
    for key in keys:
        path = (target / "docs/images" / key) if "/" not in key and key != "README.md" else target / key
        assert after[key]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert "staged_description" not in after[key]
