"""Receipt/staged integration with offline CLI runs and independent SHA256 oracles.

The one formatter double exercises the CLI boundary, not the external formatter.
All metadata and checkout contents are synthetic; no network is used.
"""
import hashlib
import json
import re

import pytest

from conftest import meta_dict, run_cli
from ctshowcase import staged, tagline

START = "<!-- showcase:tagline:start -->"
END = "<!-- showcase:tagline:end -->"
OLD = "Compare synthetic Northwind values offline."
PROPOSAL = "Route synthetic Northwind requests across teams and retain clear ownership."
NEW = "Check synthetic Northwind values deterministically."
ENDINGS = pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])


def normalize(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def receipt(payload):
    return f"<!-- showcase:tagline:generated sha256={sha(payload)} -->\n{normalize(payload)}"


def verify(body):
    marker, separator, payload = normalize(body).partition("\n")
    assert separator
    assert marker == f"<!-- showcase:tagline:generated sha256={sha(payload)} -->"
    return payload


def bodies(text):
    # Independent extraction for controlled fixtures (no nested/fenced markers).
    return [chunk.split("\n" + END, 1)[0]
            for chunk in normalize(text).split(START + "\n")[1:]]


def source(*blocks):
    return ("# Synthetic Northwind Tool\n\n"
            + "\n\n".join(f"{START}\n{body}\n{END}" for body in blocks)
            + "\n\n## Usage\n\nKeep this authored sentence.  \n")


def target(tmp_path, description=OLD):
    repo = tmp_path / "repo"
    repo.mkdir()
    meta = tmp_path / "meta.json"
    capture(meta, description)
    return repo, meta


def capture(meta, description):
    meta.write_text(json.dumps(meta_dict(description=description)), encoding="utf-8")


def doctor(repo, meta):
    result = run_cli("--meta", meta, "--repo-dir", repo, "doctor", "--format", "json")
    assert result.returncode in (0, 1), result.stdout + result.stderr
    return "description-drift:readme" in json.loads(result.stdout)["logs"]


def write_record(repo, body, description=OLD, *, staged_record=True):
    record = {"tagline_sha256": sha(body)}
    if staged_record:
        record["staged_description"] = {"text": description, "sha256": sha(description)}
    else:
        record["description_sha256"] = sha(description)
    sidecar = repo / "docs/images/.showcase.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps({"outputs": {"README.md": record}}), encoding="utf-8")
    return sidecar


def read_record(repo):
    return json.loads((repo / "docs/images/.showcase.json").read_text(encoding="utf-8"))["outputs"]["README.md"]


@ENDINGS
@pytest.mark.parametrize("variant", ["A", "F"])
def test_cli_generated_staged_live_receipts_and_exact_provenance(tmp_path, ending, variant):
    repo, meta = target(tmp_path)
    args = ("--meta", meta, "--repo-dir", repo, "readme", "--variant", variant, "--write")
    generated = run_cli(*args, "--mode", "scaffold")
    assert generated.returncode == 0, generated.stdout + generated.stderr
    path = repo / "README.md"
    raw = path.read_bytes().decode("utf-8")
    assert OLD in verify(bodies(raw)[0])
    path.write_bytes(normalize(raw).replace("\n", ending).encode("utf-8"))
    captured = meta.read_bytes()
    rendered = run_cli(*args, "--mode", "header", "--description", PROPOSAL)
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    assert "staged-description" in rendered.stdout + rendered.stderr
    assert meta.read_bytes() == captured
    raw = path.read_bytes()
    actual = bodies(raw.decode("utf-8"))[0]
    assert PROPOSAL in verify(actual)
    record = read_record(repo)
    assert record["sha256"] == hashlib.sha256(raw).hexdigest()
    assert record["tagline_sha256"] == sha(actual)
    assert record["staged_description"]["text"] == PROPOSAL
    assert record["staged_description"]["sha256"] == sha(PROPOSAL)
    assert doctor(repo, meta)
    capture(meta, PROPOSAL)
    assert not doctor(repo, meta)
    # A separate output's staged record must survive the README's live refresh.
    sidecar = repo / "docs/images/.showcase.json"
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    card = {"sha256": "a" * 64, "fingerprint": "b" * 64,
            "staged_description": record["staged_description"]}
    data["outputs"]["card.svg"] = card
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    capture(meta, NEW)
    refreshed = run_cli(*args, "--mode", "header")
    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    assert NEW in verify(bodies(path.read_bytes().decode("utf-8"))[0])
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert "staged_description" not in data["outputs"].get("README.md", {})
    assert data["outputs"]["card.svg"] == card
    before = path.read_bytes()
    again = run_cli(*args, "--mode", "header")
    assert again.returncode == 0, again.stdout + again.stderr
    assert path.read_bytes() == before


@ENDINGS
@pytest.mark.parametrize("centered", [False, True], ids=["bold", "centered"])
def test_cli_verified_boundaries_match_without_sidecar_and_hash_exactly(tmp_path, ending, centered):
    repo, meta = target(tmp_path)
    content = "Compare synthetic\nNorthwind values offline."
    payload = f'\n<p align="center">\n<b>{content}</b>\n</p>\n' if centered else f"\n**{content}**\n"
    body = receipt(payload)
    raw = source(body).replace("\n", ending)
    (repo / "README.md").write_bytes(raw.encode("utf-8"))
    assert staged.tagline_blocks(raw) == [body]
    assert staged.tagline_digest(body.replace("\n", ending)) == sha(body)
    assert staged.tagline_digest(body) != sha(body.rstrip("\n"))
    assert verify(body) == payload
    assert not doctor(repo, meta)
    # Even an unrelated provenance record cannot invalidate a verified body.
    write_record(repo, receipt("**Unrelated synthetic text.**"), "Unrelated synthetic text.")
    assert not doctor(repo, meta)


@ENDINGS
@pytest.mark.parametrize("edit", ["leading-payload", "trailing-payload", "leading-receipt", "space",
                                  "digest", "duplicate"])
def test_cli_invalid_receipts_cannot_be_certified_by_matching_sidecar(tmp_path, ending, edit):
    repo, meta = target(tmp_path)
    original = receipt(f"**{OLD}**")
    marker, payload = original.split("\n", 1)
    variants = {
        "leading-payload": marker + "\n\n" + payload,
        "trailing-payload": original + "\n",
        "leading-receipt": "\n" + original,
        "space": original + " ",
        "digest": original.replace("sha256=", "sha256=0", 1),
        "duplicate": original + "\n" + original,
    }
    edited = variants[edit]
    assert tagline.payload(edited) is None
    path = repo / "README.md"
    path.write_bytes(source(edited).replace("\n", ending).encode("utf-8"))
    # Deliberately matching evidence cannot repair a malformed/edited receipt.
    write_record(repo, edited)
    assert doctor(repo, meta)
    capture(meta, "")
    assert not doctor(repo, meta)
    capture(meta, NEW)
    before = path.read_bytes()
    result = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "header",
                     "--no-regroup", "--write", "--description", PROPOSAL)
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_bytes()
    exact = (START + ending + edited.replace("\n", ending) + ending + END).encode("utf-8")
    assert exact in before and exact in after
    assert before.split((ending + END).encode(), 1)[1] == after.split((ending + END).encode(), 1)[1]
    assert bodies(after.decode("utf-8")) == [edited]


@pytest.mark.parametrize("separator", ["\n\n", "\n \t\n", "  \n", "\\\n"])
@pytest.mark.parametrize("receipted", [False, True], ids=["legacy", "receipt"])
def test_cli_exact_sidecar_cannot_hide_paragraph_or_hard_break(tmp_path, separator, receipted):
    repo, meta = target(tmp_path)
    payload = "**Compare synthetic" + separator + "Northwind values offline.**"
    body = receipt(payload) if receipted else payload
    (repo / "README.md").write_text(source(body), encoding="utf-8")
    write_record(repo, body, staged_record=False)
    if receipted:
        assert verify(body) == payload
    assert doctor(repo, meta)


@pytest.mark.parametrize("body", [f"**{OLD}**", f'<p align="center"><b>{OLD}</b></p>',
                                  "**Compare synthetic\nNorthwind values offline.**"])
def test_cli_legacy_sidecar_separator_compatibility_never_grants_ownership(tmp_path, body):
    repo, meta = target(tmp_path)
    path = repo / "README.md"
    authored = "\n" + body + "\n"
    path.write_bytes(source(authored).encode("utf-8"))
    assert doctor(repo, meta)  # Outer blanks alone have no semantic trim fallback.
    write_record(repo, body)
    assert not doctor(repo, meta)  # Explicit historical separator/digest compatibility.
    capture(meta, "")
    assert doctor(repo, meta)
    capture(meta, NEW)
    before = path.read_bytes()
    result = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "header",
                     "--no-regroup", "--write", "--description", PROPOSAL)
    assert result.returncode == 0, result.stdout + result.stderr
    after = path.read_bytes()
    assert bodies(after.decode("utf-8")) == [authored]
    assert "showcase:tagline:generated" not in after.decode("utf-8")
    assert before.split(("\n" + END).encode(), 1)[1] == after.split(("\n" + END).encode(), 1)[1]


@ENDINGS
def test_cli_formatter_double_reseals_multiple_bodies_before_exact_provenance(tmp_path, monkeypatch, ending):
    """CLI execution with a labelled external-formatter double, no real formatter."""
    import showcase

    repo, meta = target(tmp_path, "")
    path = repo / "README.md"
    path.write_text(source(receipt(f"**{OLD}**"), receipt(f"**{NEW}**")), encoding="utf-8")
    calls = []

    def formatter_double(root, destination, text):
        assert root == repo
        if destination != path:
            assert destination == repo / "docs/images/.showcase.json"
            return text
        text = normalize(text)
        for index, body in enumerate(bodies(text)):
            marker, payload = body.split("\n", 1)
            words = payload.split(" ")
            boundary = index + 3
            changed = marker + "\n\n" + " ".join(words[:boundary]) + "\n" + " ".join(words[boundary:]) + "\n"
            text = text.replace(START + "\n" + body + "\n" + END,
                                START + "\n" + changed + "\n" + END, 1)
        calls.append(True)
        return text.replace("\n", ending)

    monkeypatch.setattr("ctshowcase.formatting.format_text", formatter_double)
    args = ["--meta", str(meta), "--repo-dir", str(repo), "readme", "--mode", "header", "--variant", "A",
            "--write", "--format-generated", "--description", PROPOSAL]
    assert showcase.main(args) == 0
    assert calls == [True]
    raw = path.read_bytes()
    final = bodies(raw.decode("utf-8"))
    assert len(final) == 2 and len(set(final)) == 2
    for body in final:
        assert verify(body).startswith("\n**")
        assert verify(body).endswith("**\n")
    record = read_record(repo)
    assert set(record["tagline_sha256s"]) == {sha(body) for body in final}
    assert record["sha256"] == hashlib.sha256(raw).hexdigest()
    assert doctor(repo, meta)
    # Per-body evidence survives edits outside the managed blocks.
    path.write_bytes(raw + "\nExtra authored context.\n".replace("\n", ending).encode("utf-8"))
    assert doctor(repo, meta)
    capture(meta, PROPOSAL)
    assert not doctor(repo, meta)
    # Receipt ownership and R2 work in a fresh subprocess without any sidecar.
    (repo / "docs/images/.showcase.json").unlink()
    assert not doctor(repo, meta)
    capture(meta, NEW)
    refreshed = run_cli("--meta", meta, "--repo-dir", repo, "readme", "--mode", "header", "--write")
    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    assert all(NEW in verify(body) for body in bodies(path.read_bytes().decode("utf-8")))


def test_multiple_blocks_and_fenced_examples_are_independent(make_ctx):
    valid = receipt(f"\n**{OLD}**\n")
    invalid = re.sub(r"sha256=[0-9a-f]{64}", "sha256=" + "0" * 64, valid)
    ctx = make_ctx(description=OLD)
    assert not staged.tagline_drift(ctx, source(valid) + "\n```md\n" + source(invalid) + "```\n")
    assert staged.tagline_drift(ctx, source(valid, invalid))
    assert staged.tagline_drift(ctx, source(valid, receipt(f"**{NEW}**")))


@pytest.mark.parametrize("change", ["remove-leading", "remove-trailing", "prepend", "append"])
def test_recorded_receipt_never_trims_payload_evidence(make_ctx, tmp_path, change):
    repo, _ = target(tmp_path)
    body = receipt(f"\n**{OLD}**\n")
    write_record(repo, body)
    ctx = make_ctx(repo_dir=repo, description="")
    assert staged.recorded_tagline(ctx, body)
    assert staged.tagline_drift(ctx, source(body), repo / "README.md")
    marker, payload = body.split("\n", 1)
    changes = {
        "remove-leading": marker + "\n" + payload[1:],
        "remove-trailing": body[:-1],
        "prepend": "\n" + body,
        "append": body + "\n",
    }
    edited = changes[change]
    assert not staged.recorded_tagline(ctx, edited)
    assert not staged.tagline_drift(ctx, source(edited), repo / "README.md")
    # A matching edited digest still cannot certify an invalid receipt.
    write_record(repo, edited)
    assert not staged.recorded_tagline(ctx, edited)
    assert not staged.tagline_drift(ctx, source(edited), repo / "README.md")


def test_empty_live_requires_staged_proof_and_whole_file_fallback_stays_exact(tmp_path):
    repo, meta = target(tmp_path, "")
    body = receipt(f"\n**{OLD}**\n")
    path = repo / "README.md"
    raw = source(body).encode("utf-8")
    path.write_bytes(raw)
    assert not doctor(repo, meta)
    sidecar = write_record(repo, body)
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    record = data["outputs"]["README.md"]
    record.pop("tagline_sha256")
    record["sha256"] = hashlib.sha256(raw).hexdigest()
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    assert doctor(repo, meta)
    path.write_bytes(raw + b"\nUnrelated authored edit.\n")
    assert not doctor(repo, meta)  # Older whole-file-only evidence is now stale.
    write_record(repo, body)
    assert doctor(repo, meta)  # Exact body evidence survives the same edit.
