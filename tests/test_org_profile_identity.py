"""Foreign organization profiles name only configured affiliations and public facts."""
import copy
import json

import pytest
import yaml

from conftest import run_cli

OWNER = "Pick-Your-AI"
ALIAS = "Northwind-AI-Alias"
FORBIDDEN = ("CompleteTech", "CompleteDotTech", "complete.tech")


@pytest.fixture
def inputs(tmp_path, monkeypatch, brand, t3_record):
    monkeypatch.setenv("SHOWCASE_ESTATE_ROOT", str(tmp_path / "empty-estate"))
    raw = copy.deepcopy(brand.raw)
    raw["orgs"][OWNER]["former_slugs"] = [ALIAS]
    registry = {"version": "synthetic", "orgs": {OWNER: {"tier": "T3", "profile": {
        "name": "Pick Your AI", "description": "Inspect synthetic model records.", "blog": "https://example.invalid"},
        "final_repos": [], "pins_public": [], "sections": []}}}
    meta = tmp_path / "meta"
    meta.mkdir()
    return raw, registry, meta


def generate(tmp_path, inputs, *, owner=OWNER, render=True, allow=True, extra=()):
    raw, registry, meta = inputs
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    reg = tmp_path / "registry.yaml"
    reg.write_text(yaml.safe_dump(registry), encoding="utf-8")
    out = tmp_path / "output"
    argv = ["--config", str(config), "--format", "json", *(["--allow-t3"] if allow else []), "org", "profile", owner,
            "--registry", str(reg), "--meta-dir", str(meta), "--out-dir", str(out),
            *(["--render"] if render else []), *map(str, extra)]
    result = run_cli(*argv)
    return result, out


def metadata(meta, owner, repo, visibility="public", **overrides):
    (meta / f"{owner}__{repo}.json").write_text(json.dumps({"owner": owner, "repo": repo, "visibility": visibility,
        "description": "Inspect synthetic records.", "language": "Python", "license": "MIT", **overrides}), encoding="utf-8")


def projects(inputs, visibility):
    _, registry, meta = inputs
    row = registry["orgs"][OWNER]
    row["final_repos"] = ["sample-tool"]
    row["pins_public"] = [{"repo": "sample-tool"}]
    row["sections"] = [{"title": "Tools", "repos": ["sample-tool"]}]
    metadata(meta, OWNER, "sample-tool", visibility)


@pytest.mark.parametrize("state,owner", [("public", OWNER), ("empty", OWNER), ("private", OWNER), ("public", ALIAS)])
def test_cli_unaffiliated_foreign_profile_stays_in_own_identity(inputs, tmp_path, state, owner):
    if state != "empty":
        projects(inputs, state)
    result, out = generate(tmp_path, inputs, owner=owner, extra=["--email-approved"])
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["leaks"] == []
    text = (out / "profile" / "README.md").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN:
        assert forbidden.lower() not in text.lower()
        assert forbidden.lower() not in json.dumps(payload["data"]).lower()
        assert forbidden.lower() not in json.dumps([a for a in payload["assets"] if a["kind"] == "badge"]).lower()
    assert "example.invalid" in text
    assert "Security" in text
    assert "showcase:footer:start" not in text
    badges = [a for a in payload["assets"] if a["kind"] == "badge"]
    assert all(a["colour"] in (inputs[0]["families"]["pickyourai"]["tokens"]["chip_attr"]["bg"],
                                inputs[0]["families"]["pickyourai"]["tokens"]["accent_deep"]) for a in badges)
    if state == "public":
        assert "sample-tool" in text and "## Featured" in text and "## All projects" in text
    else:
        assert "sample-tool" not in text and "No public repositories are currently showcased" in text
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    again, _ = generate(tmp_path, inputs, owner=owner, extra=["--email-approved"])
    assert again.returncode == 0
    assert {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("source", ["registry", "brand"])
@pytest.mark.parametrize("affiliation", ["A CompleteTech LLC organization", "Steward: CompleteTech LLC"])
def test_cli_exact_configured_affiliation_is_used_without_inventing_another(inputs, tmp_path, source, affiliation):
    if source == "registry":
        inputs[1]["orgs"][OWNER]["profile"]["description"] += " " + affiliation + "."
    else:
        inputs[0]["orgs"][OWNER]["description"] = "Inspect synthetic model records. " + affiliation + "."
        inputs[1]["orgs"][OWNER]["profile"]["description"] = None
    result, out = generate(tmp_path, inputs)
    assert result.returncode == 0, result.stdout + result.stderr
    text = (out / "profile" / "README.md").read_text(encoding="utf-8")
    assert affiliation in text
    if affiliation.startswith("A "):
        assert "Steward: CompleteTech LLC" not in text
    assert "All CompleteTech organizations" in text
    assert "showcase:footer:start" not in text  # affiliation does not override footer:false


def test_cli_configured_foreign_contact_and_cross_listing_are_factual_exceptions(inputs, tmp_path):
    projects(inputs, "public")
    _, registry, meta = inputs
    row = registry["orgs"][OWNER]
    row["profile"]["email"] = "contact@example.invalid"
    row["also_in_incoming"] = [{"repo": "Northwind-Trading-Co/shared-tool"}]
    metadata(meta, "Northwind-Trading-Co", "shared-tool", description="Uses CompleteTech public APIs.")
    # A named list does not establish whose account owns its URL.
    row["favorites"] = [{"full_name": "pallets/flask"}]
    row["star_list"] = {"name": "Synthetic favorite tools"}
    result, out = generate(tmp_path, inputs, extra=["--email-approved"])
    assert result.returncode == 0, result.stdout + result.stderr
    text = (out / "profile" / "README.md").read_text(encoding="utf-8")
    assert "mailto:contact@example.invalid" in text
    assert "https://github.com/Northwind-Trading-Co/shared-tool" in text
    assert "Uses CompleteTech public APIs." in text
    assert "## Related projects and organizations" in text
    assert "Steward: CompleteTech" not in text and "All CompleteTech" not in text
    assert "CompleteDotTech" not in text


def test_cli_footer_configuration_does_not_imply_stewardship(inputs, tmp_path):
    inputs[0]["orgs"][OWNER]["footer"] = True
    result, out = generate(tmp_path, inputs)
    assert result.returncode == 0, result.stdout + result.stderr
    text = (out / "profile" / "README.md").read_text(encoding="utf-8")
    body, footer = text.split("<!-- showcase:footer:start -->", 1)
    assert "CompleteTech LLC" in footer
    assert all(forbidden.lower() not in body.lower() for forbidden in FORBIDDEN)


@pytest.mark.parametrize("guard", ["consent", "privacy", "retemplate"])
def test_cli_existing_guards_still_apply(inputs, tmp_path, guard):
    extra = []
    if guard == "privacy":
        projects(inputs, "private")
        inputs[1]["orgs"][OWNER]["profile"]["description"] = f"Inspect {OWNER}/sample-tool records."
    elif guard == "retemplate":
        (tmp_path / "output" / "profile").mkdir(parents=True)
        (tmp_path / "output" / "profile" / "README.md").write_text("# Synthetic authored profile\n", encoding="utf-8")
    result, out = generate(tmp_path, inputs, allow=guard != "consent", extra=extra)
    assert result.returncode == {"consent": 2, "privacy": 1, "retemplate": 4}[guard]
    if guard == "retemplate":
        assert (out / "profile" / "README.md").read_text(encoding="utf-8") == "# Synthetic authored profile\n"
    else:
        assert not out.exists()


@pytest.mark.parametrize("denial", ["Not A CompleteTech LLC organization.", "No affiliation: Steward: CompleteTech LLC."])
def test_cli_negated_or_incidental_affiliation_is_not_a_grant(inputs, tmp_path, denial):
    inputs[1]["orgs"][OWNER]["profile"]["description"] += " " + denial
    result, out = generate(tmp_path, inputs)
    assert result.returncode == 0, result.stdout + result.stderr
    text = (out / "profile" / "README.md").read_text(encoding="utf-8")
    assert all(forbidden.lower() not in text.lower() for forbidden in FORBIDDEN)


def test_cli_current_registry_description_overrides_brand_affiliation(inputs, tmp_path):
    inputs[0]["orgs"][OWNER]["description"] = "Inspect records. Steward: CompleteTech LLC."
    result, out = generate(tmp_path, inputs)
    assert result.returncode == 0
    text = (out / "profile" / "README.md").read_text(encoding="utf-8")
    assert all(forbidden.lower() not in text.lower() for forbidden in FORBIDDEN)


@pytest.mark.parametrize("private", [False, True])
@pytest.mark.parametrize("source", ["url", "viewer"])
def test_cli_foreign_star_list_uses_only_captured_public_url(inputs, tmp_path, private, source):
    projects(inputs, "public")
    row = inputs[1]["orgs"][OWNER]
    row["favorites"] = [{"full_name": "pallets/flask"}]
    row["star_list"] = {"name": "Synthetic tools"}
    capture = tmp_path / "lists.json"
    account = "Northwind-Demo" if source == "url" else "CompleteDotTech"
    url = f"https://github.com/stars/{account}/lists/synthetic-tools"
    node = {"name": "Synthetic tools", "slug": "synthetic-tools", "isPrivate": private}
    viewer = {"lists": {"nodes": [node]}}
    if source == "url":
        node["url"] = url
    else:
        viewer["login"] = account
    capture.write_text(json.dumps({"data": {"viewer": viewer}}), encoding="utf-8")
    result, out = generate(tmp_path, inputs, extra=["--lists", capture])
    assert result.returncode == 0
    text = (out / "profile" / "README.md").read_text(encoding="utf-8")
    assert (url in text) is (not private)
    assert ("CompleteDotTech" in text) is (not private and source == "viewer")


def test_cli_foreign_empty_profile_agrees_with_doctor(inputs, tmp_path):
    result, out = generate(tmp_path, inputs)
    assert result.returncode == 0
    doctor = run_cli("--config", tmp_path / "config.yaml", "--format", "json", "--allow-t3", "org", "doctor", OWNER,
        "--registry", tmp_path / "registry.yaml", "--meta-dir", inputs[2], "--dot-github", out)
    payload = json.loads(doctor.stdout)
    assert payload["cells"]["O3"] == "pass", doctor.stdout + doctor.stderr
