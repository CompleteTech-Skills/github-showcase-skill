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
    definition = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    script = next(step["run"] for step in definition["runs"]["steps"]
                  if "action_commit.sh" in step.get("run", ""))
    injected = r'''
git() {
  if [ "$1" = "add" ]; then
    printf '%s\n' '{"outputs":{"card.svg":{"staged_description":{"text":"Unpublished draft"}}}}' > docs/images/.showcase.json
    printf '%s\n' 'staged drawing' > docs/images/card.svg
    command git "$@" || return "$?"
    printf '%s\n' '{"outputs":{}}' > docs/images/.showcase.json
  else
    command git "$@"
  fi
}
export -f git
'''
    env = {**os.environ, "GITHUB_ACTION_PATH": str(ROOT), "SHOWCASE_DRY_RUN": "1",
           "SHOWCASE_COMMIT_MESSAGE": "Synthetic no-op", "SHOWCASE_ON_PROTECTED": "fail"}
    result = run_bash(injected + script, cwd=tmp_path, env=env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "commit skipped" in result.stdout
    assert "Unpublished draft" not in result.stdout + result.stderr
    assert git("rev-parse", "HEAD") == initial
    assert "staged_description" in git("show", ":docs/images/.showcase.json")
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
        assert f"assets/{SOCIAL_STAGING}/preview.png" in git("diff", "--cached", "--name-only")
    else:
        assert "would push" in result.stdout
        assert git("rev-parse", "HEAD") != initial
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
