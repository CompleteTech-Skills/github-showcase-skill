"""Profile badge refusals must leave requested outputs untouched (synthetic inputs only)."""
import copy
import json
import shutil
import xml.etree.ElementTree as ET

import pytest
import yaml

from conftest import run_cli
from ctshowcase.color import contrast
from ctshowcase.config import Brand

N = "Northwind-Trading-Co"


@pytest.fixture
def profile_inputs(tmp_path, monkeypatch, brand):
    # No real estate, credentials or approval records are discovered by these runs.
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty-estate"))
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"version": "synthetic", "orgs": {N: {
        "tier": "T1", "profile": {"name": "Northwind Trading Co.",
        "description": "Inspect synthetic records.", "blog": "https://example.invalid"},
        "final_repos": ["sample-tool", "synthetic-hidden-records"],
        "pins_public": [{"repo": "sample-tool"}], "sections": []}}}), encoding="utf-8")
    meta = tmp_path / "meta"
    meta.mkdir()
    for repo, visibility in (("sample-tool", "public"), ("synthetic-hidden-records", "private")):
        (meta / f"{repo}.json").write_text(json.dumps({"owner": N, "repo": repo, "visibility": visibility,
            "description": "Inspect synthetic records.", "language": "Python", "license": "MIT"}), encoding="utf-8")
    return copy.deepcopy(brand.raw), registry


def config_path(tmp_path, raw, name="config.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def arguments(registry, out, config=None, *extra):
    return [*(["--config", str(config)] if config else []), "--format", "json", "org", "profile", N,
            "--registry", str(registry), "--meta-dir", str(registry.parent / "meta"), "--out-dir", str(out), "--render", *map(str, extra)]


def unreadable(raw):
    # Every permitted candidate equals the label fill; never introduce a fallback colour.
    bg = raw["badges"]["local_label_bg"]
    raw["badges"]["local_text"] = bg
    raw["contrast_candidates"] = [bg]
    raw["families"]["completetech"].update({"canvas": {"kind": "flat", "color": bg},
        "tokens": {"chip_key": {"fg": bg}, "chip_attr": {"fg": bg}}})
    return raw


def snapshot(out):
    return {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}


def change_registry(registry):
    raw = yaml.safe_load(registry.read_text(encoding="utf-8"))
    raw["orgs"][N]["profile"].update(description="Inspect changed synthetic records.",
                                      blog="https://changed.example.invalid")
    registry.write_text(yaml.safe_dump(raw), encoding="utf-8")


def assert_refusal(result):
    assert result.returncode == 4, result.stdout + result.stderr
    assert json.loads(result.stdout)["logs"] == ["needs-input:badge-contrast"]


def test_cli_contrast_refusal_creates_no_destination(profile_inputs, tmp_path):
    raw, registry = profile_inputs
    out = tmp_path / "new-output"
    result = run_cli(*arguments(registry, out, config_path(tmp_path, unreadable(raw))))
    assert_refusal(result)
    assert not out.exists()


@pytest.mark.parametrize("authored", [False, True])
def test_cli_contrast_refusal_preserves_existing_outputs(profile_inputs, tmp_path, authored):
    raw, registry = profile_inputs
    out = tmp_path / "existing-output"
    seed = tmp_path / "generated-seed" if authored else out
    good = run_cli(*arguments(registry, seed))
    assert good.returncode == 0, good.stdout + good.stderr
    extra = []
    if authored:
        # Seed assets through the CLI; introduce a separate authored README as
        # synthetic input without editing any generated README or artwork.
        for source in seed.rglob("*"):
            if source.is_file() and source.relative_to(seed).as_posix() != "profile/README.md":
                target = out / source.relative_to(seed)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        (out / "profile" / "README.md").write_text("# Synthetic authored profile\n", encoding="utf-8")
        approved = tmp_path / "synthetic-approved.tsv"
        approved.write_text(f"profile-retemplate\t{N}\t.github\t\n", encoding="utf-8")
        extra = ["--approved", approved]
    before = snapshot(out)
    change_registry(registry)
    assert "profile/assets/badges/website.svg" in before
    assert "profile/assets/banner.jpg" in before
    assert f"profile/assets/cards/{N}__sample-tool.svg" in before
    result = run_cli(*arguments(registry, out, config_path(tmp_path, unreadable(raw)), *extra))
    assert_refusal(result)
    assert snapshot(out) == before


@pytest.mark.parametrize("existing", [False, True])
def test_cli_late_badge_refusal_writes_nothing(profile_inputs, tmp_path, monkeypatch, capsys, existing):
    import showcase
    from ctshowcase import badge
    from ctshowcase.errors import NeedsInput

    _, registry = profile_inputs
    out = tmp_path / "late-output"
    if existing:
        good = run_cli(*arguments(registry, out))
        assert good.returncode == 0, good.stdout + good.stderr
    before = snapshot(out)
    change_registry(registry)
    render, calls = badge.svg, []

    def fail_later(*args, **kwargs):
        calls.append(args[2])
        if len(calls) == 3:
            raise NeedsInput("badge-contrast", "Synthetic late renderer refusal")
        return render(*args, **kwargs)

    # All profile badges share their fills, so a configured contrast failure is
    # necessarily first. Exercise a third-badge refusal through the real parser,
    # consent/privacy/retemplate gates and CLI error handler, injecting only svg.
    monkeypatch.setattr(badge, "svg", fail_later)
    assert showcase.main(arguments(registry, out)) == 4
    assert json.loads(capsys.readouterr().out)["logs"] == ["needs-input:badge-contrast"]
    assert calls == ["Website", "X", "Steward"]
    assert snapshot(out) == before
    if not existing:
        assert not out.exists()


@pytest.mark.parametrize("family", ["completetech", "libreevolve"])
def test_cli_uses_family_foreground_without_recolouring_fills(profile_inputs, tmp_path, brand, family):
    raw, registry = profile_inputs
    raw["orgs"][N]["family"] = family
    # Global candidates cannot render even the label; the configured family's
    # existing white foreground can. The label/value background choices stay put.
    raw["badges"]["local_text"] = raw["badges"]["local_label_bg"]
    raw["contrast_candidates"] = [raw["badges"]["local_label_bg"]]
    out = tmp_path / "family-output"
    result = run_cli(*arguments(registry, out, config_path(tmp_path, raw)))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["leaks"] == []
    style = Brand(raw, brand.path).style(N)
    allowed = {style["tokens"][chip]["fg"] for chip in ("chip_key", "chip_attr")}
    badges = [a for a in payload["assets"] if a["kind"] == "badge"]
    for spec in badges:
        svg = ET.fromstring((out / spec["path"]).read_bytes())
        fills = [e.attrib["fill"] for e in svg.iter() if e.tag.endswith("rect") and "fill" in e.attrib]
        assert fills == [raw["badges"]["local_label_bg"], spec["colour"]]
        foregrounds = [e.attrib["fill"] for e in svg.iter() if e.tag.endswith("g") and "fill" in e.attrib]
        assert len(foregrounds) == 2
        assert all(fg in allowed for fg in foregrounds)
        assert all(contrast(fg, bg) >= 4.5 for fg, bg in zip(foregrounds, fills))
    before = snapshot(out)
    again = run_cli(*arguments(registry, out, config_path(tmp_path, raw)))
    assert again.returncode == 0
    assert snapshot(out) == before


@pytest.mark.parametrize("family", ["completetech", "ai-ascension"])
def test_cli_authored_profile_still_needs_approval(profile_inputs, tmp_path, family):
    raw, registry = profile_inputs
    raw["orgs"][N]["family"] = family
    out = tmp_path / "authored-output"
    (out / "profile").mkdir(parents=True)
    (out / "profile" / "README.md").write_text("# Synthetic authored profile\n", encoding="utf-8")
    before = snapshot(out)
    result = run_cli(*arguments(registry, out, config_path(tmp_path, unreadable(raw))))
    assert result.returncode == 4
    assert "needs-approval:profile-retemplate" in json.loads(result.stdout)["logs"]
    assert "needs-input:badge-contrast" not in json.loads(result.stdout)["logs"]
    assert snapshot(out) == before


@pytest.mark.parametrize("family", ["completetech", "ai-ascension"])
def test_cli_privacy_failure_still_precedes_badge_rendering(profile_inputs, tmp_path, family):
    raw, registry = profile_inputs
    raw["orgs"][N]["family"] = family
    reg = yaml.safe_load(registry.read_text(encoding="utf-8"))
    reg["orgs"][N]["profile"]["description"] = f"Inspect {N}/synthetic-hidden-records."
    registry.write_text(yaml.safe_dump(reg), encoding="utf-8")
    out = tmp_path / "privacy-output"
    result = run_cli(*arguments(registry, out, config_path(tmp_path, unreadable(raw))))
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["leaks"]
    assert not out.exists()


@pytest.mark.parametrize("state", ["t3", "excluded", "missing-identity"])
def test_cli_consent_and_pending_identity_still_refuse(profile_inputs, tmp_path, state):
    raw, registry = profile_inputs
    if state == "missing-identity":
        raw["orgs"][N]["family"] = "ticketstub"
    else:
        raw["owners"][state].append(N)
    out = tmp_path / "refused-output"
    result = run_cli(*arguments(registry, out, config_path(tmp_path, raw)))
    assert result.returncode == (4 if state == "missing-identity" else 2), result.stdout + result.stderr
    log = {"t3": "t3-signoff", "excluded": "exempt", "missing-identity": "needs-input:brand-identity"}[state]
    assert log in json.loads(result.stdout)["logs"]
    assert not out.exists()


def test_cli_default_badges_keep_passing_historical_bytes(profile_inputs, tmp_path, brand, fonts):
    from ctshowcase import badge

    _, registry = profile_inputs
    out = tmp_path / "default-output"
    result = run_cli(*arguments(registry, out))
    assert result.returncode == 0, result.stdout + result.stderr
    for spec in json.loads(result.stdout)["assets"]:
        if spec["kind"] == "badge":
            # The former call omitted style. Keep bytes whenever its foreground
            # already passed, including both configured background rectangles.
            historical = badge.svg(brand, fonts, spec["label"], spec["message"], spec["colour"])
            assert (out / spec["path"]).read_bytes() == historical.encode()

@pytest.mark.parametrize("family", ["ai-ascension", "jev-engineering"])
def test_foreign_family_badges_use_configured_fill_and_contrast(profile_inputs, tmp_path, brand, family):
    raw, registry = profile_inputs
    raw["orgs"][N]["family"] = family
    out = tmp_path / "foreign"
    result = run_cli(*arguments(registry, out, config_path(tmp_path, raw), "--allow-unmeasured", "--banner", "assets/existing.jpg"))
    assert result.returncode == 0, result.stdout + result.stderr
    style = Brand(raw, brand.path).style(N)
    allowed = {style["tokens"]["chip_attr"]["bg"], style["tokens"]["accent_deep"]}
    for spec in json.loads(result.stdout)["assets"]:
        if spec["kind"] != "badge":
            continue
        assert spec["colour"] in allowed
        assert spec["colour"].upper() != "#" + raw["badges"]["accent"].upper()
        svg = ET.fromstring((out / spec["path"]).read_bytes())
        fills = [e.attrib["fill"] for e in svg.iter() if e.tag.endswith("rect") and "fill" in e.attrib]
        foregrounds = [e.attrib["fill"] for e in svg.iter() if e.tag.endswith("g") and "fill" in e.attrib]
        assert all(contrast(fg, bg) >= 4.5 for fg, bg in zip(foregrounds, fills))
    before = snapshot(out)
    assert run_cli(*arguments(registry, out, config_path(tmp_path, raw), "--allow-unmeasured", "--banner", "assets/existing.jpg")).returncode == 0
    assert snapshot(out) == before


@pytest.mark.parametrize("existing", [False, True])
def test_foreign_impossible_fill_refuses_without_writes(profile_inputs, tmp_path, existing):
    raw, registry = profile_inputs
    raw["orgs"][N]["family"] = "ai-ascension"
    family = raw["families"]["ai-ascension"]
    family["tokens"]["chip_attr"]["bg"] = "#777777"
    family["tokens"]["accent_deep"] = "#777777"
    raw["badges"]["local_text"] = "#777777"
    raw["contrast_candidates"] = ["#777777"]
    family["tokens"]["chip_key"]["fg"] = family["tokens"]["chip_attr"]["fg"] = "#777777"
    family["canvas"]["color"] = "#777777"
    out = tmp_path / "foreign-impossible"
    if existing:
        result = run_cli(*arguments(registry, out))
        assert result.returncode == 0
    before = snapshot(out)
    result = run_cli(*arguments(registry, out, config_path(tmp_path, raw), "--banner", "assets/existing.jpg"))
    assert_refusal(result)
    assert snapshot(out) == before
    if not existing:
        assert not out.exists()
