"""Checks for the repository's own presentation assets, issue forms and code of conduct (#134).

Stdlib plus PyYAML only. No network, no subprocess, no conftest fixtures.
"""

import hashlib
import re
import struct
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

SOCIAL_PREVIEW = ROOT / "assets" / "social-preview.png"
SOCIAL_PREVIEW_SHA256 = "5d318b92b04518de4a86af0429ef864a97390f6e4cc245a9d7cf78b18a433152"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

ISSUE_TEMPLATE_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"
BUG_REPORT = ISSUE_TEMPLATE_DIR / "bug_report.yml"
FEATURE_REQUEST = ISSUE_TEMPLATE_DIR / "feature_request.yml"
CONFIG = ISSUE_TEMPLATE_DIR / "config.yml"
LABELS_STANDARD = ROOT / "references" / "standard" / "labels.yml"
CODE_OF_CONDUCT = ROOT / "CODE_OF_CONDUCT.md"

BODY_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}
EXPECTED_FORM_LABELS = {
    "bug_report": ["type:bug", "status:needs-triage"],
    "feature_request": ["type:feature", "status:needs-triage"],
}
CONTACT = "Timothy.Gregg@complete.tech"
EMAIL_PATTERN = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"


def _load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _documented_label_names():
    entries = _load_yaml(LABELS_STANDARD)
    assert isinstance(entries, list)
    return {entry["name"] for entry in entries}


def test_social_preview_dimensions():
    data = SOCIAL_PREVIEW.read_bytes()
    assert data[:8] == PNG_SIGNATURE
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (1280, 640)


def test_social_preview_hash_pinned():
    digest = hashlib.sha256(SOCIAL_PREVIEW.read_bytes()).hexdigest()
    assert digest == SOCIAL_PREVIEW_SHA256


def test_forms_parse_and_have_required_keys():
    for form_name, path in (("bug_report", BUG_REPORT), ("feature_request", FEATURE_REQUEST)):
        form = _load_yaml(path)
        assert isinstance(form, dict), path
        for key in ("name", "description", "title"):
            assert isinstance(form.get(key), str) and form[key].strip(), (path, key)
        assert isinstance(form.get("labels"), list), path
        assert form["labels"] == EXPECTED_FORM_LABELS[form_name], path
        body = form.get("body")
        assert isinstance(body, list) and body, path
        seen_ids = set()
        for element in body:
            assert isinstance(element, dict), path
            assert element.get("type") in BODY_TYPES, (path, element.get("type"))
            if element["type"] == "markdown":
                continue
            element_id = element.get("id")
            assert isinstance(element_id, str) and element_id, (path, element)
            assert element_id not in seen_ids, (path, element_id)
            seen_ids.add(element_id)


def test_issue_form_labels_exist_in_standard():
    documented = _documented_label_names()
    for path in (BUG_REPORT, FEATURE_REQUEST):
        form = _load_yaml(path)
        for label in form["labels"]:
            assert label in documented, (path, label)
    config = _load_yaml(CONFIG)
    assert "labels" not in config


def test_config_has_no_blank_issues_and_no_email():
    config = _load_yaml(CONFIG)
    assert config["blank_issues_enabled"] is False
    contact_links = config["contact_links"]
    assert isinstance(contact_links, list) and contact_links
    for link in contact_links:
        assert link["url"].startswith("https://github.com/"), link
    for path in (CONFIG, BUG_REPORT, FEATURE_REQUEST):
        assert "@" not in path.read_text(encoding="utf-8"), path


def test_code_of_conduct_names_documented_contact():
    text = CODE_OF_CONDUCT.read_text(encoding="utf-8")
    assert "Contributor Covenant" in text
    assert "version 2.1" in text
    assert CONTACT in text
    assert set(re.findall(EMAIL_PATTERN, text)) == {CONTACT}
