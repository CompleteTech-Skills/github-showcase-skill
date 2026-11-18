"""Formatter-boundary receipt regressions using offline, synthetic CLI fixtures.

The labelled formatter double reproduces Prettier 3.6.2's paragraph separator
reflow. It is not evidence that the real formatter or its AST checks executed.
Receipt construction and validation below use an independent SHA256 oracle.
"""
import hashlib
import json
import re

import pytest

from conftest import meta_dict, run_cli
from ctshowcase import tagline

START = "<!-- showcase:tagline:start -->"
END = "<!-- showcase:tagline:end -->"
DESCRIPTION = "Compare synthetic Northwind values offline."
UPDATED = "Check synthetic Northwind values deterministically."
R2 = "R2 bold tagline must equal the GitHub description"
ENDINGS = pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])


def normalize(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def receipt(payload):
    canonical = normalize(payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"<!-- showcase:tagline:generated sha256={digest} -->\n{canonical}"


def extract(text):
    # The controlled fixtures have one live block and no marker examples.
    return normalize(text).split(START + "\n", 1)[1].split("\n" + END, 1)[0]


def assert_receipt(body):
    marker, separator, payload = normalize(body).partition("\n")
    assert separator
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert marker == f"<!-- showcase:tagline:generated sha256={digest} -->"
    return payload


def target(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    meta = tmp_path / "meta.json"
    write_meta(meta, DESCRIPTION)
    return repo, meta


def write_meta(meta, description):
    meta.write_text(json.dumps(meta_dict(description=description)), encoding="utf-8")


def write_source(repo, body, ending):
    source = (f"# Synthetic Northwind Tool\n\n{START}\n{body}\n{END}\n\n"
              "## Usage\n\nKeep this authored sentence.  \n")
    data = source.replace("\n", ending).encode("utf-8")
    (repo / "README.md").write_bytes(data)
    return data


def lint_report(repo, meta):
    result = run_cli("--meta", meta, "--repo-dir", repo, "lint", "readme", repo / "README.md")
    assert result.returncode in (0, 1), result.stdout + result.stderr
    reports = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert len(reports) == 1, result.stdout + result.stderr
    assert "fails" in reports[0], reports
    return reports[0]


@ENDINGS
@pytest.mark.parametrize("variant", ["C", "F"])
def test_cli_scaffold_formatter_boundary_reflow_is_owned_and_r2_compliant(
        tmp_path, monkeypatch, ending, variant):
    """Run the real CLI pipeline with only the external formatter replaced."""
    import showcase

    repo, meta = target(tmp_path)
    path = repo / "README.md"
    calls = []

    def prettier_paragraph_boundary_double(root, destination, source):
        """Synthetic Prettier-style reflow; F's centered HTML is the control."""
        assert root == repo and destination == path
        source = normalize(source)
        before = extract(source)
        payload = assert_receipt(before)
        if variant == "C":
            assert payload == f"**{DESCRIPTION}**"
            # Leave the original stamp unchanged. The CLI must reseal the
            # payload, including both newly inserted separator blank lines.
            stamp = before.split("\n", 1)[0]
            after = stamp + "\n\n" + payload + "\n"
            source = source.replace(START + "\n" + before + "\n" + END,
                                    START + "\n" + after + "\n" + END, 1)
        else:
            assert payload == f'<p align="center"><b>{DESCRIPTION}</b></p>'
        calls.append(payload)
        return source.replace("\n", ending)

    monkeypatch.setattr("ctshowcase.formatting.format_text", prettier_paragraph_boundary_double)
    args = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "scaffold",
            "--variant", variant, "--write", "--format-generated"]
    assert showcase.main(args) == 0
    assert len(calls) == 1
    raw = path.read_bytes().decode("utf-8")
    assert raw == normalize(raw).replace("\n", ending)
    body = extract(raw)
    expected = (f"\n**{DESCRIPTION}**\n" if variant == "C"
                else f'<p align="center"><b>{DESCRIPTION}</b></p>')
    assert assert_receipt(body) == expected
    assert tagline.payload(body) == expected
    assert not (repo / "docs/images/.showcase.json").exists()
    report = lint_report(repo, meta)

    # Ownership must survive in a fresh CLI process with no formatter or
    # sidecar, so a description update can still refresh the generated block.
    write_meta(meta, UPDATED)
    refreshed = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "header", "--write")
    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    new_body = extract(path.read_bytes().decode("utf-8"))
    assert UPDATED in assert_receipt(new_body)
    assert DESCRIPTION not in assert_receipt(new_body)
    assert R2 not in report["fails"], report


@ENDINGS
@pytest.mark.parametrize("sidecar", [False, True], ids=["no-sidecar", "unrelated-sidecar"])
def test_verified_outer_blank_lines_and_soft_wraps_match_without_sidecar_authority(tmp_path, ending, sidecar):
    repo, meta = target(tmp_path)
    payload = "\n**Compare synthetic\nNorthwind values offline.**\n"
    body = receipt(payload).replace("\n", ending)
    write_source(repo, normalize(body), ending)
    if sidecar:
        path = repo / "docs/images/.showcase.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"schema": 1, "inputs": {"description": "Unrelated synthetic capture."},
                                    "outputs": {}}), encoding="utf-8")
    assert assert_receipt(body) == payload
    assert tagline.payload(body) == payload
    report = lint_report(repo, meta)
    assert R2 not in report["fails"], report
    assert tagline.matches_description(body, DESCRIPTION)


@ENDINGS
@pytest.mark.parametrize("case", ["edited-leading", "edited-trailing", "edited-both", "invalid-digest",
                                   "legacy-leading", "legacy-trailing", "legacy-both"])
def test_outer_blanks_do_not_launder_invalid_receipts_or_legacy_authorship(tmp_path, ending, case):
    repo, meta = target(tmp_path)
    plain = f"**{DESCRIPTION}**"
    stamp = receipt(plain).split("\n", 1)[0]
    side = case.rsplit("-", 1)[1]
    padded = ("\n" if side in ("leading", "both") else "") + plain
    padded += "\n" if side in ("trailing", "both") else ""
    if case == "invalid-digest":
        authored = re.sub(r"sha256=[0-9a-f]{64}", "sha256=" + "0" * 64, receipt("\n" + plain + "\n"))
    elif case.startswith("edited"):
        authored = stamp + "\n" + padded  # The old digest deliberately remains unsealed.
    else:
        authored = padded
    transported = authored.replace("\n", ending)
    assert tagline.payload(transported) is None
    assert not tagline.matches_description(transported, DESCRIPTION)
    before = write_source(repo, authored, ending)
    assert R2 in lint_report(repo, meta)["fails"]
    write_meta(meta, UPDATED)
    result = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "header",
                     "--no-regroup", "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    after = (repo / "README.md").read_bytes()
    assert extract(after.decode("utf-8")) == authored
    assert (START + ending + transported + ending + END).encode("utf-8") in after
    # Surrounding authored prose is byte-for-byte intact as well.
    suffix = (ending + END).encode("utf-8")
    assert before.split(suffix, 1)[1] == after.split(suffix, 1)[1]


@ENDINGS
@pytest.mark.parametrize("separator", ["\n\n", "\n \t\n", "  \n", "\\\n"],
                         ids=["blank-paragraph", "whitespace-paragraph", "two-space-break", "backslash-break"])
def test_valid_receipt_does_not_hide_interior_paragraphs_or_hard_breaks(tmp_path, ending, separator):
    repo, meta = target(tmp_path)
    payload = "\n**Compare synthetic" + separator + "Northwind values offline.**\n"
    body = receipt(payload).replace("\n", ending)
    assert assert_receipt(body) == payload
    assert tagline.payload(body) == payload  # Ownership and R2 are different claims.
    assert not tagline.matches_description(body, DESCRIPTION)
    write_source(repo, normalize(body), ending)
    assert R2 in lint_report(repo, meta)["fails"]


@pytest.mark.parametrize("payload", [
    " **Compare synthetic Northwind values offline.**",
    "\t**Compare synthetic Northwind values offline.**",
    "**Compare synthetic Northwind values offline.** ",
    "\n **Compare synthetic Northwind values offline.**\n",
])
def test_verified_receipt_does_not_allow_nonblank_outer_whitespace(payload):
    body = receipt(payload)
    assert assert_receipt(body) == payload
    assert tagline.payload(body) == payload
    assert not tagline.matches_description(body, DESCRIPTION)
