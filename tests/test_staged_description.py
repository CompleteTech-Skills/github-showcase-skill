"""Explicit staged-description provenance and drift, using synthetic public metadata."""
import hashlib
import json
from pathlib import Path

import pytest

from conftest import meta_dict, run_cli
from ctshowcase.readme import tagline_body
from ctshowcase.staged import SOCIAL_STAGING, prepare, record_output, tagline_drift, tagline_forms
from ctshowcase.errors import NeedsInput
from ctshowcase.fingerprint import read_sidecar


def test_prepare_does_not_change_capture():
    meta = meta_dict(description="Captured sentence.")
    proposed, info = prepare(meta, "Proposed sentence.")
    assert meta["description"] == "Captured sentence."
    assert proposed["description"] == "Proposed sentence."
    assert info["sha256"] == hashlib.sha256(b"Proposed sentence.").hexdigest()
    assert info["live_description_sha256"] == hashlib.sha256(b"Captured sentence.").hexdigest()


@pytest.mark.parametrize("text", [
    "", "  ", "First line.\nSecond line.", "A proposal. <!-- showcase:tagline:end -->",
])
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


def test_legacy_tagline_provenance_does_not_claim_horizontal_whitespace_edits(make_ctx, tmp_path):
    from ctshowcase.readme import _replaceable_tagline
    from ctshowcase.staged import recorded_tagline, tagline_digest

    ctx = make_ctx(repo_dir=tmp_path, description="New public description.")
    original_description = "Old generated description."
    original = f"**{original_description}**"
    images = tmp_path / "docs" / "images"
    images.mkdir(parents=True)
    record = {"tagline_sha256": tagline_digest(original),
              "description_sha256": tagline_digest(original_description)}
    (images / ".showcase.json").write_text(json.dumps({"outputs": {"README.md": record}}), encoding="utf-8")

    assert recorded_tagline(ctx, f"\n{original}\n")
    assert not recorded_tagline(ctx, "    " + original)
    assert not recorded_tagline(ctx, original + "  ")
    ctx.format_root = tmp_path
    reflowed = "**Old generated\ndescription.**"
    assert _replaceable_tagline(ctx, reflowed, original)
    assert not _replaceable_tagline(ctx, "    " + reflowed, original)
    assert not _replaceable_tagline(ctx, reflowed + "  ", original)


@pytest.mark.parametrize("edited", ["    **Route support requests.**", "**Route support requests.**  "])
def test_doctor_preserves_horizontal_whitespace_when_matching_tagline_proof(tmp_path, edited):
    from ctshowcase.staged import tagline_digest

    proposal = "Route support requests."
    original = f"**{proposal}**"
    capture = tmp_path / "meta.json"
    target = tmp_path / "repo"
    images = target / "docs" / "images"
    images.mkdir(parents=True)
    readme = target / "README.md"
    sidecar = images / ".showcase.json"
    entry = {"tagline_sha256": tagline_digest(original),
             "staged_description": {"text": proposal, "sha256": tagline_digest(proposal)}}
    sidecar.write_text(json.dumps({"outputs": {"README.md": entry}}), encoding="utf-8")

    def drift(description, body):
        capture.write_text(json.dumps(meta_dict(description=description)), encoding="utf-8")
        readme.write_text("# Support Triage Agent\n\n" + TAG.format(f"\n{body}\n"), encoding="utf-8")
        report = run_cli("--meta", capture, "--repo-dir", target, "doctor", "--format", "json")
        return "description-drift:readme" in json.loads(report.stdout)["logs"]

    assert not drift(proposal, original)
    assert drift("", original)
    assert drift(proposal, edited)
    assert not drift("", edited)


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


def test_cli_doctor_reports_verified_staged_tagline_against_empty_live_description(tmp_path):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict(description="")), encoding="utf-8")
    target = tmp_path / "repo"
    target.mkdir()
    common = ["--meta", capture, "--repo-dir", target, "--format", "json"]
    result = run_cli(*common, "readme", "--mode", "scaffold", "--write", "--description", "Route support requests.")
    assert result.returncode == 0, result.stdout + result.stderr

    report = json.loads(run_cli(*common, "doctor", "--format", "json").stdout)
    assert report["cells"]["R2"] == "fail"
    assert "description-drift:readme" in report["logs"]

    readme = target / "README.md"
    with readme.open("a", encoding="utf-8") as output:
        output.write("\nAn authored addition.\n")
    report = json.loads(run_cli(*common, "doctor", "--format", "json").stdout)
    assert "description-drift:readme" in report["logs"]

    readme.write_text(readme.read_text(encoding="utf-8").replace("Route support requests.", "An authored tagline."),
                      encoding="utf-8")
    report = json.loads(run_cli(*common, "doctor", "--format", "json").stdout)
    assert "description-drift:readme" not in report["logs"]


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
    out = target / (f"assets/{SOCIAL_STAGING}/social-preview.png" if surface == "social" else f"docs/images/{surface}." + ("svg" if surface == "card" else "png"))
    command = ["content", "social"] if surface == "social" else [surface]
    result = run_cli("--meta", capture, "--repo-dir", target, "--format", "json", *command,
                     "--description", "Route support requests.", "--out", out)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert "staged-description" in report["logs"]
    assert json.loads(capture.read_text())["description"] == "Run the Northwind triage agent."
    provenance = Path(report["out"]).parent if surface == "social" else target / "docs/images"
    records = read_sidecar(provenance)["outputs"]
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
    private = target / "assets" / SOCIAL_STAGING
    before = read_sidecar(sidecar)["outputs"]
    private_before = read_sidecar(private)
    keys = {"banner": ["banner.png"], "card": ["card.svg", "card.png"],
            "social": [], "readme": ["README.md"]}[surface]
    for key in keys:
        assert before[key]["staged_description"]["text"] == "Route support requests."
        if surface in ("banner", "card"):
            assert before[key]["repository_id"] == 12345
    ordinary = run_cli(*common, *command)
    assert ordinary.returncode == 0, ordinary.stdout + ordinary.stderr
    after = read_sidecar(sidecar)["outputs"]
    assert read_sidecar(private) == private_before
    if surface == "social":
        assert after == before
        assert (target / "assets/social-preview.png").is_file()
        return
    for key in keys:
        path = (target / "docs/images" / key) if "/" not in key and key != "README.md" else target / key
        assert after[key]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert "staged_description" not in after[key]


def test_fingerprint_uses_configured_output_records(tmp_path):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    target = tmp_path / "repo"
    (target / ".github").mkdir(parents=True)
    (target / ".github/showcase.yml").write_text("chips:\n  key: ['Triage']\n  attrs: ['Python']\n", encoding="utf-8")
    common = ["--meta", capture, "--repo-dir", target, "--format", "json"]
    commands = [("banner", "--description", "Route support requests."), ("card",)]

    def run(*args):
        result = run_cli(*common, *args)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    for command in commands:
        run(*command)
    assert run("fingerprint", "--outputs", "banner,card")["changed"] is True
    assert run("fingerprint", "--outputs", "card")["changed"] is False
    run("banner")
    assert run("fingerprint", "--outputs", "banner,card")["changed"] is False
    run("readme", "--mode", "scaffold", "--write", "--description", "Route support requests.")
    assert run("fingerprint", "--outputs", "banner,card", "--readme", "header")["changed"] is True
    assert run("fingerprint", "--outputs", "banner,card", "--readme", "none")["changed"] is False
    run("readme", "--mode", "header", "--write")
    assert run("fingerprint", "--outputs", "banner,card", "--readme", "header")["changed"] is False


def test_fingerprint_preserves_legacy_records_on_partial_write(tmp_path):
    from ctshowcase.fingerprint import fingerprint, outputs_changed, write_sidecar

    old = fingerprint({"description": "Old description."}, "config")
    sidecar = tmp_path / ".showcase.json"
    sidecar.write_text(json.dumps({"fingerprint": old, "outputs": {"banner.png": {"sha256": "b" * 64}}}),
                       encoding="utf-8")
    assert not outputs_changed(read_sidecar(tmp_path), old, {"banner.png"})
    inputs = {"description": "New description."}
    write_sidecar(tmp_path, inputs, "config", "card.svg", {"sha256": "c" * 64})
    current = fingerprint(inputs, "config")
    data = read_sidecar(tmp_path)
    assert outputs_changed(data, current, {"banner.png", "card.svg"})
    assert not outputs_changed(data, current, {"card.svg"})


def test_fingerprint_requires_selected_art_records_in_modern_sidecars(tmp_path):
    from ctshowcase.fingerprint import fingerprint, outputs_changed, write_sidecar

    inputs = {"description": "Captured description."}
    current = fingerprint(inputs, "config")
    legacy = {"fingerprint": current, "outputs": {"card.svg": {"sha256": "c" * 64}}}
    selected = {"banner.png", "card.svg", "README.md"}
    assert not outputs_changed(legacy, current, selected)

    write_sidecar(tmp_path, inputs, "config", "card.svg", {"sha256": "c" * 64})
    modern = read_sidecar(tmp_path)
    assert outputs_changed(modern, current, selected)
    assert not outputs_changed(modern, current, {"card.svg", "README.md"})
    write_sidecar(tmp_path, inputs, "config", "banner.png", {"sha256": "b" * 64})
    assert not outputs_changed(read_sidecar(tmp_path), current, selected)


@pytest.mark.parametrize("variant,mode,body", [
    ("B", "header", None),
    ("B", "header", "# An unmanaged README\n"),
    ("G", "upgrade", "# An unmanaged README\n\nA paragraph.\n"),
    ("H", "upgrade", "# An unmanaged README\n\nA paragraph.\n"),
])
def test_readme_only_records_a_rendered_tagline(tmp_path, variant, mode, body):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    path = tmp_path / "README.md"
    if body is not None:
        path.write_text(body, encoding="utf-8")
    common = ["--meta", capture, "--repo-dir", tmp_path, "readme", "--mode", mode, "--variant", variant, "--write"]
    for options in ([], ["--description", "Route support requests."]):
        result = run_cli(*common, *options)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (tmp_path / "docs/images/.showcase.json").exists()
    if body is None:
        assert not path.exists()


def test_staged_social_blocks_upload_jobs(tmp_path):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    output = tmp_path / "social.png"
    jobs = tmp_path / "jobs.jsonl"
    common = ["--meta", capture, "--repo-dir", tmp_path, "--format", "json", "content", "social",
              "--job", "--jobs", jobs, "--out", output]
    result = run_cli(*common, "--description", "Route support requests.")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "staged-description:upload" in json.loads(result.stdout)["logs"]
    assert not output.exists() and not jobs.exists()
    live = run_cli(*common)
    assert live.returncode == 0, live.stdout + live.stderr
    assert json.loads(jobs.read_text(encoding="utf-8"))["kind"] == "browser"

    capture_bytes = output.read_bytes()
    staged = run_cli("--meta", capture, "--repo-dir", tmp_path, "--format", "json", "content", "social",
                     "--description", "Route support requests.")
    assert staged.returncode == 0, staged.stdout + staged.stderr
    staged_path = Path(json.loads(staged.stdout)["out"])
    assert SOCIAL_STAGING in staged_path.parts and staged_path.is_file()
    assert output.read_bytes() == capture_bytes
    with_job = run_cli(*common, "--out", staged_path)
    assert with_job.returncode == 2, with_job.stdout + with_job.stderr
    assert "staged-description:upload" in json.loads(with_job.stdout)["logs"]
    staged_overwrite = run_cli("--meta", capture, "--repo-dir", tmp_path, "--format", "json", "content", "social",
                               "--description", "Route support requests.", "--out", output)
    assert staged_overwrite.returncode == 2, staged_overwrite.stdout + staged_overwrite.stderr
    assert output.read_bytes() == capture_bytes



def test_canonical_and_custom_outputs_have_independent_provenance(make_ctx, tmp_path):
    ctx = make_ctx(repo_dir=tmp_path, description="Captured description.")
    original_meta = ctx.meta
    canonical = tmp_path / "docs/images/banner.png"
    custom = tmp_path / "banner.png"
    ctx.meta, ctx.staged_description = prepare(original_meta, "Canonical proposal.")
    record_output(ctx, canonical, {"sha256": "canonical-hash"})
    original = read_sidecar(canonical.parent)
    ctx.meta, ctx.staged_description = prepare(original_meta, "Custom proposal.")
    record_output(ctx, custom, {"sha256": "custom-hash"})
    record_output(ctx, tmp_path / "README.md", {"sha256": "readme-hash"})
    record_output(ctx, tmp_path / "assets" / SOCIAL_STAGING / "social-preview.png", {"sha256": "social-hash"})
    updated = read_sidecar(canonical.parent)
    assert "fingerprint" not in original and "fingerprint" not in updated
    assert "inputs" not in original and "inputs" not in updated
    assert updated["outputs"]["banner.png"] == original["outputs"]["banner.png"]
    assert updated["outputs"]["./banner.png"]["staged_description"]["text"] == "Custom proposal."
    ctx.meta, ctx.staged_description = original_meta, None
    record_output(ctx, canonical, {"sha256": "refreshed-hash"})
    outputs = read_sidecar(canonical.parent)["outputs"]
    assert "staged_description" not in outputs["banner.png"]
    assert outputs["./banner.png"] == updated["outputs"]["./banner.png"]


@pytest.mark.parametrize("invalid", [None, [], {}, "invalid", {"exempt": "unknown"}])
def test_malformed_selected_record_is_stale(invalid):
    from ctshowcase.fingerprint import outputs_changed

    assert outputs_changed({"fingerprint": "current", "outputs": {"card.svg": invalid}}, "current", {"card.svg"})


def test_canonical_exempt_card_is_cached(tmp_path):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict(repo=".github")), encoding="utf-8")
    target = tmp_path / "repo"
    target.mkdir()
    common = ["--meta", capture, "--repo-dir", target, "--format", "json"]
    first = run_cli(*common, "fingerprint", "--outputs", "card")
    assert json.loads(first.stdout)["changed"] is True
    card = run_cli(*common, "card")
    assert card.returncode == 0, card.stdout + card.stderr
    assert json.loads(card.stdout)["result"] == "exempt"
    assert not (target / "docs/images/card.svg").exists()
    record = read_sidecar(target / "docs/images")["outputs"]["card.svg"]
    assert record["exempt"] == "exempt:no-card"
    second = run_cli(*common, "fingerprint", "--outputs", "card")
    assert json.loads(second.stdout)["changed"] is False
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    changed = run_cli(*common, "fingerprint", "--outputs", "card")
    assert json.loads(changed.stdout)["changed"] is True


@pytest.mark.parametrize("link_kind", ["hard", "symbolic"])
def test_sidecar_replacement_keeps_linked_live_preview(tmp_path, link_kind):
    from ctshowcase.fingerprint import write_sidecar

    live = tmp_path / "live.png"
    live.write_bytes(b"existing live preview")
    sidecar = tmp_path / ".showcase.json"
    try:
        if link_kind == "hard":
            sidecar.hardlink_to(live)
        else:
            sidecar.symlink_to(live)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"{link_kind} links are unavailable: {exc}")

    write_sidecar(tmp_path, {"description": "Staged preview."}, "config", "staged.png", {"sha256": "a" * 64})
    assert live.read_bytes() == b"existing live preview"
    assert not sidecar.is_symlink()
    assert read_sidecar(tmp_path)["outputs"]["staged.png"]["sha256"] == "a" * 64


def test_staged_preview_replacement_retains_posix_permissions(tmp_path):
    import os
    import stat

    from ctshowcase.fingerprint import replace_bytes

    if os.name != "posix":
        pytest.skip("POSIX permission bits required")
    path = tmp_path / "preview.png"
    replace_bytes(path, b"first proposal", private=True)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o640)
    replace_bytes(path, b"updated proposal", private=True)
    assert path.read_bytes() == b"updated proposal"
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_action_classifies_foreign_art_individually(tmp_path, monkeypatch):
    import action_prepare

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY_ID", "275")
    monkeypatch.delenv("SHOWCASE_IS_TEMPLATE", raising=False)
    images = tmp_path / "docs/images"
    images.mkdir(parents=True)
    data = {
        "inputs": {"owner": "Northwind", "repo": "current"},
        "outputs": {
            "banner.png": {"repository_id": 274},
            "card.svg": {"repository_id": 275},
        },
    }
    (images / ".showcase.json").write_text(json.dumps(data), encoding="utf-8")
    assert action_prepare.foreign("Northwind/current", "banner.png")
    assert not action_prepare.foreign("Northwind/current", "card.svg")
    assert not action_prepare.foreign("Northwind/current")


@pytest.mark.parametrize("surface, preview", [("banner", False), ("card", True), ("content", False)])
def test_staged_art_rejects_provenance_path_collision(tmp_path, surface, preview):
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    checkout = tmp_path / "repo"
    checkout.mkdir()
    external = tmp_path / ".showcase-staging"
    external.mkdir()
    sidecar = external / ".showcase.json"
    sidecar.write_text('{"existing": true}', encoding="utf-8")
    args = ["--meta", capture, "--repo-dir", checkout, "--format", "json", surface]
    if surface == "content":
        args.append("social")
    args += ["--description", "Route support requests."]
    if preview:
        args += ["--out", external / "card.svg", "--png", sidecar]
    else:
        args += ["--out", sidecar]
    result = run_cli(*args)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "staged-description:path" in json.loads(result.stdout)["logs"]
    assert sidecar.read_text(encoding="utf-8") == '{"existing": true}'
    assert not (external / "card.svg").exists()


def test_staged_banner_rejects_link_to_capture(tmp_path):
    capture = tmp_path / "meta.json"
    captured = json.dumps(meta_dict())
    capture.write_text(captured, encoding="utf-8")
    images = tmp_path / "repo/docs/images"
    images.mkdir(parents=True)
    try:
        (images / "banner.png").symlink_to(capture)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")
    result = run_cli("--meta", capture, "--repo-dir", tmp_path / "repo", "--format", "json", "banner",
                     "--description", "Route support requests.")
    assert result.returncode == 2, result.stdout + result.stderr
    assert capture.read_text(encoding="utf-8") == captured
    assert not (images / ".showcase.json").exists()


@pytest.mark.requires_bash
@pytest.mark.parametrize("staged_directory", ["docs/images", "docs/images/previews", "."])
def test_action_commit_step_skips_partial_live_refresh_with_staged_records(tmp_path, staged_directory):
    import os
    import yaml
    from conftest import ROOT, run_bash
    from ctshowcase.fingerprint import write_sidecar

    images = tmp_path / "docs/images"
    images.mkdir(parents=True)
    proposal = "Unpublished support process."
    directory = tmp_path / staged_directory
    directory.mkdir(parents=True, exist_ok=True)
    write_sidecar(directory, {"description": proposal}, "config", "banner.png",
                  {"sha256": "a" * 64, "staged_description": {"text": proposal}})
    write_sidecar(images, {"description": "Live description."}, "config", "card.svg", {"sha256": "b" * 64})
    definition = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    script = next(step["run"] for step in definition["runs"]["steps"]
                  if "action_commit.sh" in step.get("run", ""))
    env = {**os.environ, "GITHUB_ACTION_PATH": str(ROOT), "SHOWCASE_DRY_RUN": "1",
           "SHOWCASE_COMMIT_MESSAGE": "Synthetic no-op", "SHOWCASE_ON_PROTECTED": "fail"}
    result = run_bash(script, cwd=tmp_path, env=env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "commit skipped" in result.stdout
    assert proposal not in result.stdout + result.stderr
    assert read_sidecar(directory)["outputs"]["banner.png"]["staged_description"]["text"] == proposal


@pytest.mark.parametrize("collision", ["metadata", "sidecar", "records", "report", "preview-directory"])
def test_staged_destinations_fail_before_artifact_writes(tmp_path, collision):
    target = tmp_path / "repo"
    images = target / "docs/images"
    images.mkdir(parents=True)
    capture = images / ".showcase.json" if collision == "sidecar" else tmp_path / "capture.json"
    original = json.dumps(meta_dict())
    capture.write_text(original, encoding="utf-8")
    stage = ["--description", "Route support requests."]
    common = ["--meta", capture, "--repo-dir", target, "--format", "json"]
    if collision == "records":
        command = ["readme", "--mode", "scaffold", "--write", "--records", capture]
    elif collision == "report":
        command = ["content", "social", "--report", capture]
    elif collision == "preview-directory":
        preview = images / "card.png"
        preview.mkdir()
        command = ["card", "--png", preview]
    else:
        command = ["banner", "--allow-few-chips", "--out", capture if collision == "metadata" else images / "banner.png"]
    result = run_cli(*common, *command, *stage)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "staged-description:path" in json.loads(result.stdout)["logs"]
    assert capture.read_text(encoding="utf-8") == original
    assert not (images / "banner.png").exists()
    assert not (images / "card.svg").exists()
    assert not (target / "README.md").exists()


def test_staged_readme_only_uses_proposal_for_tagline(tmp_path):
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict(repo="acme-tool", description="Route support requests.")), encoding="utf-8")
    target = tmp_path / "repo"
    target.mkdir()
    common = ["--meta", capture, "--repo-dir", target, "--format", "json", "readme"]
    staged = run_cli(*common, "--mode", "scaffold", "--description", "Run the AcME tool.", "--write")
    assert staged.returncode == 0, staged.stdout + staged.stderr
    text = (target / "README.md").read_text(encoding="utf-8")
    assert "# Acme Tool" in text
    assert "**Run the AcME tool.**" in text
    live = run_cli(*common, "--mode", "header", "--write")
    assert live.returncode == 0, live.stdout + live.stderr
    assert "AcME" not in (target / "README.md").read_text(encoding="utf-8")
    assert "staged_description" not in read_sidecar(target / "docs/images")["outputs"]["README.md"]


def test_staged_render_marks_output_before_writing_bytes(make_ctx, monkeypatch, tmp_path):
    from showcase import write_rendered_art

    ctx = make_ctx(repo_dir=tmp_path)
    ctx.meta, ctx.staged_description = prepare(ctx.meta, "Unpublished support process.")
    art = tmp_path / "docs/images/card.svg"
    png = tmp_path / "docs/images/card.png"

    def fail_preview(_ctx, path, data):
        if path == png:
            raise PermissionError("synthetic write failure")
        path.write_bytes(data)

    monkeypatch.setattr("showcase.write_artifact", fail_preview)
    with pytest.raises(PermissionError, match="synthetic write failure"):
        write_rendered_art(ctx, (art, b"preview SVG", {}), (png, b"preview PNG", {}))

    assert art.read_bytes() == b"preview SVG"
    sidecar = read_sidecar(art.parent)
    assert "inputs" not in sidecar
    assert sidecar["outputs"]["card.svg"]["staged_description"]["text"] == "Unpublished support process."


def test_cli_fingerprint_checks_the_selected_canonical_art(tmp_path):
    from ctshowcase import fingerprint as fp
    from ctshowcase.meta import load_file

    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    target = tmp_path / "repo"
    images = target / "docs/images"
    images.mkdir(parents=True)
    card = images / "card.svg"
    card.write_bytes(b"canonical card")
    fp.write_sidecar(images, fp.inputs(load_file(capture), target), fp.config_sha256(),
                     card.name, fp.file_record(card))
    command = ["--meta", capture, "--repo-dir", target, "--format", "json", "fingerprint", "--outputs", "card"]

    def changed():
        result = run_cli(*command)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)["changed"]

    assert not changed()
    card.write_bytes(b"unexpected replacement")
    assert changed()
    card.unlink()
    assert changed()


def test_staged_report_rejects_a_hardlink_to_canonical_provenance(tmp_path):
    target = tmp_path / "repo"
    images = target / "docs/images"
    images.mkdir(parents=True)
    canonical = images / ".showcase.json"
    original = b'{"outputs":{"card.svg":{"staged_description":{"text":"Draft"}}}}'
    canonical.write_bytes(original)
    report = tmp_path / "external.json"
    try:
        report.hardlink_to(canonical)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"hard links are unavailable: {exc}")
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    result = run_cli("--meta", capture, "--repo-dir", target, "--format", "json",
                     "content", "social", "--description", "Route support requests.", "--report", report)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "staged-description:path" in json.loads(result.stdout)["logs"]
    assert canonical.read_bytes() == original


def test_concurrent_staged_updates_keep_each_record(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from ctshowcase import fingerprint as fp

    first_write = Event()
    release_first = Event()
    second_started = Event()
    second_read = Event()
    original_replace = fp.replace_bytes
    original_read = fp.read_sidecar

    def pause_first(path, data, **kwargs):
        if b'"banner.png":' in data and b'"card.svg":' not in data:
            first_write.set()
            assert release_first.wait(5)
        original_replace(path, data, **kwargs)

    def track_read(path):
        if second_started.is_set():
            second_read.set()
        return original_read(path)

    def write_card():
        second_started.set()
        fp.write_sidecar(tmp_path, {}, "config", "card.svg", {"staged_description": {"text": "Card proposal."}})

    monkeypatch.setattr(fp, "replace_bytes", pause_first)
    monkeypatch.setattr(fp, "read_sidecar", track_read)
    with ThreadPoolExecutor(max_workers=2) as threads:
        banner = threads.submit(fp.write_sidecar, tmp_path, {}, "config", "banner.png",
                                {"staged_description": {"text": "Banner proposal."}})
        assert first_write.wait(5)
        card = threads.submit(write_card)
        try:
            assert second_started.wait(5)
            assert not second_read.wait(0.2)
        finally:
            release_first.set()
        banner.result(5)
        card.result(5)
    assert set(original_read(tmp_path)["outputs"]) == {"banner.png", "card.svg"}


def test_exemption_rechecks_output_after_acquiring_sidecar_lock(tmp_path, make_ctx, monkeypatch):
    from contextlib import contextmanager

    import showcase
    from ctshowcase import staged

    ctx = make_ctx(repo_dir=tmp_path)
    proposal = make_ctx(repo_dir=tmp_path)
    proposal.meta, proposal.staged_description = prepare(proposal.meta, "Unpublished draft.")
    card = tmp_path / "docs/images/card.svg"
    guarded = staged.lock_outputs

    @contextmanager
    def staged_before_live_lock(context, *paths):
        with guarded(proposal, card):
            staged.record_output(proposal, card, {"sha256": "a" * 64})
            card.write_bytes(b"staged card drawing")
        with guarded(context, *paths):
            yield

    monkeypatch.setattr(staged, "lock_outputs", staged_before_live_lock)
    showcase.record_art_exemption(ctx, "card", None, "exempt:no-card")
    assert read_sidecar(card.parent)["outputs"][card.name]["staged_description"]["text"] == "Unpublished draft."


@pytest.mark.requires_bash
def test_action_refuses_a_staged_proposal_captured_in_the_git_index(tmp_path):
    import os
    import subprocess

    import yaml
    from conftest import ROOT, run_bash

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True).stdout

    git("init", "-q")
    git("-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "base")
    initial = git("rev-parse", "HEAD")
    (tmp_path / "docs/images").mkdir(parents=True)
    readme = tmp_path / "README.md"
    readme.write_text("pre-existing staged text", encoding="utf-8")
    git("add", "--", "README.md")
    index = tmp_path / ".git/index"
    original_index = index.read_bytes()
    readme.write_text("working tree text", encoding="utf-8")
    definition = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    script = next(step["run"] for step in definition["runs"]["steps"]
                  if "action_commit.sh" in step.get("run", ""))
    wrapper = tmp_path / "capture_index.py"
    wrapper.write_text(r'''
import runpy
import subprocess
import sys
from pathlib import Path

original_run = subprocess.run


def observe_add(argv, *args, **kwargs):
    if argv[:2] != ["git", "add"]:
        return original_run(argv, *args, **kwargs)
    sidecar = Path("docs/images/.showcase.json")
    sidecar.write_text('{"outputs":{"card.svg":{"staged_description":{"text":"Unpublished draft"}}}}',
                       encoding="utf-8")
    Path("docs/images/card.svg").write_text("staged drawing", encoding="utf-8")
    result = original_run(argv, *args, **kwargs)
    candidate = original_run(["git", "show", ":docs/images/.showcase.json"], env=kwargs["env"],
                             check=True, capture_output=True).stdout
    assert b"staged_description" in candidate
    assert original_run(["git", "show", ":README.md"], env=kwargs["env"],
                        check=True, capture_output=True).stdout == b"working tree text"
    sidecar.write_text('{"outputs":{}}', encoding="utf-8")
    return result


subprocess.run = observe_add
sys.argv.pop(0)
runpy.run_path(sys.argv[0], run_name="__main__")
''', encoding="utf-8")
    injected = '''
python() {
  command python "$SHOWCASE_TEST_INDEX_WRAPPER" "$@"
}
export -f python
'''
    env = {**os.environ, "GITHUB_ACTION_PATH": str(ROOT), "SHOWCASE_DRY_RUN": "1",
           "SHOWCASE_COMMIT_MESSAGE": "Synthetic no-op", "SHOWCASE_ON_PROTECTED": "fail",
           "SHOWCASE_TEST_INDEX_WRAPPER": str(wrapper)}
    result = run_bash(injected + script, cwd=tmp_path, env=env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "commit skipped" in result.stdout
    assert "Unpublished draft" not in result.stdout + result.stderr
    assert git("rev-parse", "HEAD") == initial
    assert index.read_bytes() == original_index
    assert git("diff", "--cached", "--name-only").splitlines() == ["README.md"]
    assert git("show", ":README.md") == "pre-existing staged text"
    assert "staged_description" not in (tmp_path / "docs/images/.showcase.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("another_checkout", [False, True])
def test_metadata_only_staged_report_refuses_action_managed_destinations(tmp_path, another_checkout):
    target = tmp_path / "repo"
    target.mkdir()
    if another_checkout:
        (target / ".git").mkdir()
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    report = target / "docs/images/proposed.json"
    output = tmp_path / ".showcase-staging" / "preview.png"
    result = run_cli("--meta", capture, "--no-repo-dir", "--format", "json", "content", "social",
                     "--description", "Unpublished draft.", "--out", output,
                     "--report", report if another_checkout else "docs/images/proposed.json",
                     cwd=tmp_path if another_checkout else target)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "staged-description:path" in json.loads(result.stdout)["logs"]
    assert not report.exists()
    assert not output.exists()


def test_staged_social_provenance_stays_outside_unrelated_action_commits(tmp_path, monkeypatch, make_ctx):
    import action_prepare

    ctx = make_ctx(repo_dir=tmp_path)
    ctx.meta, ctx.staged_description = prepare(ctx.meta, "Unpublished draft.")
    path = tmp_path / "assets" / SOCIAL_STAGING / "social-preview.png"
    record_output(ctx, path, {"sha256": "a" * 64})
    monkeypatch.chdir(tmp_path)
    assert read_sidecar(path.parent)["outputs"][path.name]["staged_description"]["text"] == "Unpublished draft."
    assert not action_prepare.has_staged_outputs()


@pytest.mark.parametrize("signature", [b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"])
def test_staged_report_does_not_replace_previously_rendered_social_image(tmp_path, signature):
    target = tmp_path / "repo"
    target.mkdir()
    capture = tmp_path / "meta.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    live = target / "queued-preview"
    original = signature + b"existing render"
    live.write_bytes(original)
    result = run_cli("--meta", capture, "--repo-dir", target, "--format", "json",
                     "content", "social", "--description", "Unpublished draft.", "--report", live)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "staged-description:path" in json.loads(result.stdout)["logs"]
    assert live.read_bytes() == original


def test_stale_live_readme_plan_cannot_clear_concurrent_staged_provenance(tmp_path, monkeypatch, make_ctx):
    from contextlib import contextmanager

    import showcase
    from ctshowcase import readme, staged

    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    target = tmp_path / "repo"
    target.mkdir()
    path = target / "README.md"
    common = ["--meta", str(capture), "--repo-dir", str(target), "readme"]
    assert showcase.main([*common, "--mode", "scaffold", "--write"]) == 0
    assert showcase.main([*common, "--mode", "header", "--write"]) == 0
    live = path.read_bytes()
    proposal = make_ctx(repo_dir=target)
    proposal.meta, proposal.staged_description = prepare(proposal.meta, "Unpublished draft.")
    staged_text = live.decode().replace("Run the Northwind triage agent.", "Unpublished draft.").encode()
    original_lock = staged.lock_outputs

    @contextmanager
    def stage_first(ctx, *paths):
        with original_lock(proposal, path):
            path.write_bytes(staged_text)
            fp_hash = hashlib.sha256(staged_text).hexdigest()
            record_output(proposal, path, {"sha256": fp_hash,
                                           "tagline_sha256": staged.tagline_digest(readme.tagline_body(proposal).strip())})
        with original_lock(ctx, *paths):
            yield

    monkeypatch.setattr(staged, "lock_outputs", stage_first)
    assert showcase.main([*common, "--mode", "header", "--write"]) == 1
    assert path.read_bytes() == staged_text
    assert "staged_description" in read_sidecar(target / "docs/images")["outputs"]["README.md"]


def test_staged_noop_readme_records_exact_existing_crlf_bytes(tmp_path):
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    target = tmp_path / "repo"
    target.mkdir()
    common = ["--meta", capture, "--repo-dir", target, "--format", "json", "readme",
              "--description", "Unpublished draft.", "--write"]
    assert run_cli(*common, "--mode", "scaffold").returncode == 0
    command = [*common, "--mode", "header"]
    first = run_cli(*command)
    assert first.returncode == 0, first.stdout + first.stderr
    path = target / "README.md"
    original = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    path.write_bytes(original)
    second = run_cli(*command)
    assert second.returncode == 0, second.stdout + second.stderr
    assert json.loads(second.stdout)["result"] == "unchanged"
    assert path.read_bytes() == original
    record = read_sidecar(target / "docs/images")["outputs"]["README.md"]
    assert record["sha256"] == hashlib.sha256(original).hexdigest()
    assert record["bytes"] == len(original)


@pytest.mark.parametrize("metadata_only", [False, True])
def test_social_preview_staging_cannot_land_inside_action_artifact_paths(tmp_path, metadata_only):
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    output = repo / "docs/images" / SOCIAL_STAGING / "preview.png"
    checkout = ["--no-repo-dir"] if metadata_only else ["--repo-dir", repo]
    result = run_cli("--meta", capture, *checkout, "--format", "json", "content", "social",
                     "--description", "Unpublished draft.", "--out", output, cwd=repo)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "staged-description:path" in json.loads(result.stdout)["logs"]
    assert not output.exists()


@pytest.mark.requires_bash
@pytest.mark.parametrize("pre_staged", [False, True])
def test_action_will_not_commit_a_private_preview_already_in_index(tmp_path, pre_staged):
    import os
    import subprocess

    import yaml
    from conftest import ROOT, run_bash

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True).stdout

    git("init", "-q")
    git("-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "base")
    initial = git("rev-parse", "HEAD")
    private = tmp_path / "assets" / SOCIAL_STAGING
    private.mkdir(parents=True)
    (private / "preview.png").write_bytes(b"synthetic staged preview")
    (private / ".showcase.json").write_text(
        '{"outputs":{"preview.png":{"staged_description":{"text":"Unpublished draft"}}}}', encoding="utf-8")
    if pre_staged:
        git("add", "--", f"assets/{SOCIAL_STAGING}")
    images = tmp_path / "docs/images"
    images.mkdir(parents=True)
    (images / "banner.png").write_bytes(b"live banner")
    definition = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    script = next(step["run"] for step in definition["runs"]["steps"]
                  if "action_commit.sh" in step.get("run", ""))
    env = {**os.environ, "GITHUB_ACTION_PATH": str(ROOT), "SHOWCASE_DRY_RUN": "1",
           "SHOWCASE_COMMIT_MESSAGE": "Synthetic no-op", "SHOWCASE_ON_PROTECTED": "fail"}
    result = run_bash(script, cwd=tmp_path, env=env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    if pre_staged:
        assert "commit skipped" in result.stdout
        assert git("rev-parse", "HEAD") == initial
        assert git("diff", "--cached", "--name-only").splitlines() == [
            f"assets/{SOCIAL_STAGING}/.showcase.json", f"assets/{SOCIAL_STAGING}/preview.png"]
    else:
        assert "would push" in result.stdout
        assert git("rev-parse", "HEAD^") == initial
        assert git("diff", "--cached", "--name-only") == ""
        assert git("show", "--format=", "--name-only", "HEAD").strip() == "docs/images/banner.png"


@pytest.mark.parametrize("location", ["canonical", "custom", "legacy"])
def test_staged_art_cannot_replace_a_queued_live_social_preview(tmp_path, location):
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict(description="Run the synthetic support queue.")), encoding="utf-8")
    checkout = tmp_path / "repo"
    checkout.mkdir()
    queue = tmp_path / "jobs.jsonl"
    destination = checkout / ("assets/social-preview.png" if location == "canonical" else "custom/queued.png")
    result = run_cli("--meta", capture, "--repo-dir", checkout, "--format", "json", "content", "social",
                     "--job", "--jobs", queue, "--out", destination)
    assert result.returncode == 0, result.stdout + result.stderr
    out = Path(json.loads(result.stdout)["out"])
    original = out.read_bytes()
    planned_jobs = queue.read_bytes()
    assert read_sidecar(out.parent)["outputs"][out.name]["live_social_preview"] is True
    if location == "legacy":
        (out.parent / ".showcase.json").unlink()

    attempt = run_cli("--meta", capture, "--no-repo-dir", "--format", "json", "banner",
                      "--allow-few-chips", "--description", "Unpublished staging exercise.", "--out", out)
    assert attempt.returncode == 2, attempt.stdout + attempt.stderr
    assert "staged-description:path" in json.loads(attempt.stdout)["logs"]
    assert out.read_bytes() == original
    assert queue.read_bytes() == planned_jobs


@pytest.mark.requires_bash
def test_action_stages_while_holding_the_renderers_lock(tmp_path):
    import os
    import subprocess
    import time

    from conftest import ROOT, find_bash
    from ctshowcase.fingerprint import sidecar_lock

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True).stdout

    git("init", "-q")
    git("-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid",
        "commit", "--allow-empty", "-qm", "base")
    initial = git("rev-parse", "HEAD")
    images = tmp_path / "docs/images"
    images.mkdir(parents=True)
    banner = images / "banner.png"
    banner.write_bytes(b"live banner")
    sidecar = images / ".showcase.json"
    sidecar.write_text('{"outputs":{"banner.png":{}}}', encoding="utf-8")
    env = {**os.environ, "SHOWCASE_DRY_RUN": "1"}
    with sidecar_lock(sidecar):
        action = subprocess.Popen([find_bash(), str(ROOT / "scripts/action_commit.sh"), "Synthetic", "fail",
                                   str(ROOT / "scripts/action_prepare.py")], cwd=tmp_path, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not any((tmp_path / ".git").glob("showcase-index.*")):
                assert action.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            assert git("diff", "--cached", "--name-only") == ""
            sidecar.write_text('{"outputs":{"banner.png":{"staged_description":{"text":"Draft"}}}}', encoding="utf-8")
            banner.write_bytes(b"staged banner")
        except BaseException:
            action.kill()
            action.communicate()
            raise
    with action:
        try:
            stdout, stderr = action.communicate(timeout=15)
        finally:
            if action.poll() is None:
                action.kill()
    assert action.returncode == 0, (stdout, stderr)
    assert "commit skipped" in stdout
    assert git("rev-parse", "HEAD") == initial
    assert git("diff", "--cached", "--name-only") == ""


@pytest.mark.requires_bash
@pytest.mark.parametrize("protection", ["signing", "hook", "config-hook", "staged"])
def test_action_leaves_checkout_untouched_when_publication_is_refused(tmp_path, protection):
    import os
    import subprocess

    from conftest import ROOT, run_bash

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()

    git("init", "-q")
    git("-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgSign=false",
        "commit", "--allow-empty", "-qm", "base")
    parent = git("rev-parse", "HEAD")
    images = tmp_path / "docs" / "images"
    images.mkdir(parents=True)
    card = images / "card.svg"
    if protection == "signing":
        git("config", "commit.gpgSign", "yes")
        git("config", "gpg.format", "openpgp")
        git("config", "gpg.program", str(tmp_path / "missing-signer"))
    elif protection == "hook":
        git("config", "core.hooksPath", "custom-hooks")
        hook = tmp_path / "custom-hooks" / "pre-commit"
        hook.parent.mkdir()
        hook.write_bytes(b"#!/bin/sh\nexit 1\n")
        hook.chmod(0o700)
    elif protection == "config-hook":
        git("config", "hook.synthetic.event", "pre-commit")
        git("config", "hook.synthetic.command", "false")
    else:
        card.write_bytes(b"previously staged card")
        git("add", "--", "docs/images/card.svg")
    staged = git("diff", "--cached", "--binary")
    card.write_bytes(b"candidate card")

    result = run_bash('bash "$1" Synthetic fail "$2"', str(ROOT / "scripts/action_commit.sh"),
                      str(ROOT / "scripts/action_prepare.py"), cwd=tmp_path,
                      env={**os.environ, "SHOWCASE_DRY_RUN": "1"})

    if protection == "signing":
        assert result.returncode != 0
        assert "missing-signer" in result.stderr
    else:
        assert result.returncode == 0, (result.stdout, result.stderr)
        reason = "local Git commit hooks" if protection.endswith("hook") else "conflicting index changes"
        assert reason in result.stdout
    assert git("rev-parse", "HEAD") == parent
    assert git("diff", "--cached", "--binary") == staged
    assert card.read_bytes() == b"candidate card"


@pytest.mark.requires_bash
def test_action_leaves_an_in_progress_merge_untouched(tmp_path):
    import os
    import subprocess

    from conftest import ROOT, run_bash

    def git(*args, check=True):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=check)

    git("init", "-q")
    git("config", "user.name", "Synthetic")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgSign", "false")
    card = tmp_path / "docs" / "images" / "card.svg"
    card.parent.mkdir(parents=True)
    card.write_bytes(b"base\n")
    git("add", "--", "docs/images/card.svg")
    git("commit", "-qm", "base")
    git("switch", "-q", "-c", "incoming")
    card.write_bytes(b"incoming\n")
    git("commit", "-qam", "incoming")
    git("switch", "-q", "-")
    card.write_bytes(b"current\n")
    git("commit", "-qam", "current")
    assert git("merge", "incoming", check=False).returncode == 1
    card.write_bytes(b"resolved\n")
    git("add", "--", "docs/images/card.svg")
    head = git("rev-parse", "HEAD", "MERGE_HEAD").stdout
    index = tmp_path / ".git" / "index"
    original_index = index.read_bytes()

    result = run_bash('bash "$1" Synthetic fail "$2"', str(ROOT / "scripts/action_commit.sh"),
                      str(ROOT / "scripts/action_prepare.py"), cwd=tmp_path,
                      env={**os.environ, "SHOWCASE_DRY_RUN": "1"})

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "Git operation is in progress" in result.stdout
    assert git("rev-parse", "HEAD", "MERGE_HEAD").stdout == head
    assert index.read_bytes() == original_index
    assert card.read_bytes() == b"resolved\n"


@pytest.mark.requires_bash
@pytest.mark.parametrize("concurrent_change", [
    "head", "index", "branch", "late-branch", "late-detached", "locked-branch", "ref-failure",
    "ref-failure-no-space", "ref-failure-restore-error",
])
def test_action_handles_concurrent_git_changes_during_commit(tmp_path, concurrent_change):
    import os
    import stat
    import subprocess

    from conftest import ROOT, run_bash

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Synthetic")
    git("config", "user.email", "fixture@example.invalid")
    git("commit", "--allow-empty", "-qm", "base")
    initial = git("rev-parse", "HEAD")
    original_ref = git("symbolic-ref", "HEAD")
    if concurrent_change in ("late-branch", "late-detached", "locked-branch"):
        git("branch", "competing")
    if concurrent_change == "late-detached":
        git("switch", "--detach", "-q")
    (tmp_path / "README.md").write_text("live README", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("concurrent staged text", encoding="utf-8")
    index = tmp_path / ".git/index"
    if os.name == "posix" and (concurrent_change == "locked-branch" or concurrent_change.startswith("ref-failure")):
        index.chmod(0o664)
    original_mode = stat.S_IMODE(index.stat().st_mode)
    original = index.read_bytes()
    wrapper = tmp_path / "update_git_state.py"
    wrapper.write_text(r'''
import errno
import os
import runpy
import subprocess
import sys
from pathlib import Path

original_run = subprocess.run
original_write_bytes = Path.write_bytes
original_replace = os.replace
ref_failed = False
change = os.environ["SHOWCASE_TEST_CONCURRENT_CHANGE"]


class ObserveRefUpdate(subprocess.Popen):
    def __init__(self, argv, *args, **kwargs):
        self.ref_transaction = argv[:2] == ["git", "update-ref"] and "--stdin" in argv
        if self.ref_transaction:
            assert not any(kwargs.get(key) for key in ("text", "universal_newlines", "encoding", "errors"))
        if self.ref_transaction and change == "head":
            parent = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            tree = subprocess.check_output(["git", "rev-parse", f"{parent}^{{tree}}"], text=True).strip()
            advanced = subprocess.check_output(["git", "commit-tree", tree, "-p", parent, "-m", "Concurrent"],
                                               text=True).strip()
            original_run(["git", "update-ref", "HEAD", advanced, parent], check=True)
        if self.ref_transaction and change in ("late-branch", "late-detached"):
            original_run(["git", "symbolic-ref", "HEAD", "refs/heads/competing"], check=True)
        super().__init__(argv, *args, **kwargs)

    def communicate(self, input=None, timeout=None):
        global ref_failed
        if self.ref_transaction and input == b"commit\n":
            assert Path(".git/index.lock").is_file()
            if change == "locked-branch":
                attempt = original_run(["git", "symbolic-ref", "HEAD", "refs/heads/competing"],
                                       capture_output=True, timeout=5)
                assert attempt.returncode, "HEAD switched during installation of the caller's index"
            if change.startswith("ref-failure"):
                candidate = original_run(["git", "show", ":README.md"], check=True, capture_output=True).stdout
                Path("failed-ref-candidate").write_bytes(candidate)
                output = super().communicate(b"abort\n", timeout)
                self.returncode = 1
                ref_failed = True
                return output
        return super().communicate(input, timeout)


def change_git_state(argv, *args, **kwargs):
    if argv[:2] == ["git", "write-tree"]:
        if change == "index":
            original_run(["git", "add", "--", "notes.txt"], check=True)
        if change == "branch":
            original_run(["git", "switch", "-qc", "competing"], check=True)
    return original_run(argv, *args, **kwargs)


def fail_rollback_write(path, content):
    if ref_failed and change == "ref-failure-no-space" and path.name.startswith("showcase-index."):
        raise OSError(errno.ENOSPC, "synthetic disk exhaustion")
    return original_write_bytes(path, content)


def fail_rollback_rename(source, destination):
    if ref_failed and change == "ref-failure-restore-error" and Path(destination).name == "index":
        raise OSError(errno.EACCES, "synthetic index restore failure")
    return original_replace(source, destination)


subprocess.Popen = ObserveRefUpdate
subprocess.run = change_git_state
Path.write_bytes = fail_rollback_write
os.replace = fail_rollback_rename
sys.argv.pop(0)
runpy.run_path(sys.argv[0], run_name="__main__")
''', encoding="utf-8")
    script = '''
python() {
  command python "$SHOWCASE_TEST_INDEX_WRAPPER" "$@"
}
export -f python
bash "$GITHUB_ACTION_PATH/scripts/action_commit.sh" "Synthetic" fail "$GITHUB_ACTION_PATH/scripts/action_prepare.py"
'''
    env = {**os.environ, "GITHUB_ACTION_PATH": str(ROOT), "SHOWCASE_DRY_RUN": "1",
           "SHOWCASE_TEST_INDEX_WRAPPER": str(wrapper), "SHOWCASE_TEST_CONCURRENT_CHANGE": concurrent_change}
    result = run_bash(script, cwd=tmp_path, env=env)
    lock = tmp_path / ".git/index.lock"
    if concurrent_change == "ref-failure-restore-error":
        assert result.returncode != 0, result.stdout + result.stderr
        assert "Its recovery lock remains" in result.stderr
        assert "would push" not in result.stdout
        assert git("rev-parse", "HEAD") == initial
        assert lock.read_bytes() == original
        assert stat.S_IMODE(lock.stat().st_mode) == original_mode
        return
    assert not lock.exists()
    if concurrent_change == "locked-branch":
        assert result.returncode == 0, result.stdout + result.stderr
        assert "would push" in result.stdout
        assert git("symbolic-ref", "HEAD") == original_ref
        assert git("rev-parse", "HEAD^") == initial
        assert git("rev-parse", "refs/heads/competing") == initial
        assert git("show", "HEAD:README.md") == "live README"
        assert stat.S_IMODE(index.stat().st_mode) == original_mode
        assert git("diff", "--cached", "--name-only") == ""
        return
    if concurrent_change.startswith("ref-failure"):
        assert result.returncode != 0, result.stdout + result.stderr
        assert (tmp_path / "failed-ref-candidate").read_bytes() == b"live README"
        assert "would push" not in result.stdout
        assert git("rev-parse", "HEAD") == initial
        assert index.read_bytes() == original
        assert stat.S_IMODE(index.stat().st_mode) == original_mode
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert "commit skipped because HEAD or the caller's Git index changed" in result.stdout
    assert "would push" not in result.stdout
    if concurrent_change == "head":
        assert git("rev-parse", "HEAD^") == initial
        assert git("log", "-1", "--format=%s") == "Concurrent"
        assert index.read_bytes() == original
        assert git("diff", "--cached", "--name-only") == ""
    elif concurrent_change in ("branch", "late-branch", "late-detached"):
        assert git("symbolic-ref", "--short", "HEAD") == "competing"
        assert git("rev-parse", "HEAD") == initial
        assert git("rev-parse", original_ref) == initial
        assert git("diff", "--cached", "--name-only") == ""
        if concurrent_change.startswith("late-"):
            assert index.read_bytes() == original
    else:
        assert git("rev-parse", "HEAD") == initial
        assert git("diff", "--cached", "--name-only") == "notes.txt"
        assert git("show", ":notes.txt") == "concurrent staged text"


def test_sidecar_lock_is_shared_across_process_temp_directories(tmp_path):
    import os
    import subprocess
    import sys
    import time

    from conftest import ROOT
    from ctshowcase.fingerprint import sidecar_lock

    child_temp = tmp_path / "child-temp"
    child_temp.mkdir()
    sidecar = tmp_path / ".showcase.json"
    started = tmp_path / "started"
    entered = tmp_path / "entered"
    code = (
        "from pathlib import Path\n"
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from ctshowcase.fingerprint import sidecar_lock\n"
        "Path(sys.argv[3]).touch()\n"
        "with sidecar_lock(Path(sys.argv[2])):\n"
        "    Path(sys.argv[4]).touch()\n"
    )
    env = {**os.environ, **dict.fromkeys(("TMPDIR", "TEMP", "TMP"), str(child_temp))}
    with sidecar_lock(sidecar):
        child = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "scripts"), str(sidecar),
                                  str(started), str(entered)], env=env)
        try:
            deadline = time.monotonic() + 12
            while not started.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert started.exists()
            assert child.poll() is None
            time.sleep(0.3)
            assert not entered.exists()
        except BaseException:
            child.kill()
            child.wait()
            raise
    with child:
        assert child.wait(timeout=15) == 0
        assert entered.exists()


def test_reflowed_taglines_record_exact_bodies_and_follow_the_live_capture(tmp_path, monkeypatch):
    import action_prepare
    import showcase
    from ctshowcase import readme
    from ctshowcase.staged import tagline_blocks, tagline_digest

    checkout = tmp_path / "repo"
    checkout.mkdir()
    path = checkout / "README.md"
    path.write_text("# Synthetic documentation\n\n" + readme.wrap("tagline", "**Old.**") + "\n\n"
                    "## Details\n\n" + readme.wrap("tagline", "**Another old.**") + "\n", encoding="utf-8")
    meta_path = tmp_path / "metadata.json"
    meta = meta_dict(description="")
    proposed = "Route synthetic support requests across multiple teams and keep queue ownership visible."

    def capture(description):
        meta["description"] = description
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    def reflow(root, target, source):
        if target != path:
            return source
        parts, offset = [], 0
        blocks = [block for block in readme.find_blocks(readme.MARK, source) if block.group(1) == "tagline"]
        for index, block in enumerate(blocks):
            words = block.group(2).split(" ")
            boundary = 4 + index
            parts.extend((source[offset:block.start(2)], " ".join(words[:boundary]), "\n", " ".join(words[boundary:])))
            offset = block.end(2)
        return "".join([*parts, source[offset:]])

    def recorded():
        return read_sidecar(checkout / "docs/images")["outputs"]["README.md"]

    def drift():
        result = run_cli("--meta", meta_path, "--repo-dir", checkout, "doctor", "--format", "json")
        return "description-drift:readme" in json.loads(result.stdout)["logs"]

    monkeypatch.setattr("ctshowcase.formatting.format_text", reflow)
    monkeypatch.chdir(checkout)
    args = ["--meta", str(meta_path), "--repo-dir", str(checkout), "readme", "--mode", "header",
            "--variant", "A", "--write", "--format-generated"]
    capture("")
    assert showcase.main([*args, "--description", proposed]) == 0
    expected = {tagline_digest(body) for body in tagline_blocks(path.read_text(encoding="utf-8"))}
    assert len(expected) == 2
    assert set(recorded()["tagline_sha256s"]) == expected
    assert recorded()["staged_description"]["text"] == proposed
    assert action_prepare.has_staged_outputs()
    assert drift()

    capture(proposed)
    assert not drift()
    capture(f"  {proposed}  ")
    assert not drift()
    assert action_prepare.has_staged_outputs()

    live = "Keep the live help queue available and route each synthetic request to the owner."
    capture(live)
    assert drift()
    assert showcase.main(args) == 0
    assert not action_prepare.has_staged_outputs()
    assert not drift()

    (checkout / "docs/images/.showcase.json").unlink()
    assert showcase.main(args) == 0
    assert not drift()
    assert recorded()["description_sha256"] == tagline_digest(live)
    capture(f"  {live}  ")
    assert not drift()
    edited = path.read_text(encoding="utf-8").replace("owner.**", "maintainer.**", 1)
    path.write_text(edited, encoding="utf-8")
    assert drift()


def test_exempt_card_does_not_write_provenance_through_an_external_image_directory(tmp_path):
    checkout = tmp_path / "repo"
    docs = checkout / "docs"
    docs.mkdir(parents=True)
    external = tmp_path / "shared-images"
    external.mkdir()
    try:
        (docs / "images").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"directory links unavailable: {error}")
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict(repo=".github")), encoding="utf-8")

    result = run_cli("--meta", capture, "--repo-dir", checkout, "--format", "json", "card")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["result"] == "exempt"
    assert list(external.iterdir()) == []


@pytest.mark.parametrize("explicit_output", [False, True])
def test_staged_card_rejects_output_outside_an_aliased_checkout(tmp_path, explicit_output):
    checkout = tmp_path / "repo"
    docs = checkout / "docs"
    docs.mkdir(parents=True)
    external = tmp_path / "shared-images"
    external.mkdir()
    alias = tmp_path / "checkout-alias"
    try:
        alias.symlink_to(checkout, target_is_directory=True)
        (docs / "images").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"directory links unavailable: {error}")
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(meta_dict()), encoding="utf-8")

    target = checkout if explicit_output else alias
    output = ("--out", alias / "docs/images/custom.svg") if explicit_output else ()
    result = run_cli("--meta", capture, "--repo-dir", target, "--format", "json", "card",
                     "--description", "Route synthetic requests.", *output)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "staged-description:path" in json.loads(result.stdout)["logs"]
    assert list(external.iterdir()) == []


@pytest.mark.parametrize("separator", ["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_staged_description_rejects_interior_line_separators(separator):
    with pytest.raises(NeedsInput, match="one non-empty line"):
        prepare(meta_dict(), f"First synthetic line.{separator}~~~{separator}Second synthetic line.")


def test_unicode_line_separator_cannot_write_staged_readme(tmp_path):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    meta = tmp_path / "capture.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    result = run_cli("--meta", meta, "--repo-dir", checkout, "--format", "json", "readme", "--mode", "scaffold",
                     "--variant", "A", "--write", "--description", "First.\u2028~~~\u2028Still private.")
    assert result.returncode == 4, result.stdout + result.stderr
    assert "needs-input:description" in json.loads(result.stdout)["logs"]
    assert not (checkout / "README.md").exists()
    assert not (checkout / "docs/images/.showcase.json").exists()


def test_untrackable_staged_tagline_refuses_before_writing_checkout(tmp_path, monkeypatch, capsys):
    import showcase
    from ctshowcase import readme

    checkout = tmp_path / "repo"
    checkout.mkdir()
    meta = tmp_path / "capture.json"
    meta.write_text(json.dumps(meta_dict()), encoding="utf-8")
    monkeypatch.setattr(readme, "scaffold", lambda ctx, text: "# Synthetic\n\n" + readme.tagline_body(ctx) + "\n")
    args = ["--meta", str(meta), "--repo-dir", str(checkout), "readme", "--mode", "scaffold",
            "--variant", "A", "--write", "--description", "Route a synthetic request."]
    assert showcase.main(args) == 1
    assert "staged-description:provenance" in json.loads(capsys.readouterr().out)["logs"]
    assert not (checkout / "README.md").exists()
    assert not (checkout / "docs/images/.showcase.json").exists()
