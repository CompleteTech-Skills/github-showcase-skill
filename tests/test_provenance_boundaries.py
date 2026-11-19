"""Synthetic receipt, destination and offline boundaries; no live GET or writer execution."""
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ctshowcase import fingerprint as fp
from ctshowcase import ledger, provenance as P
from ctshowcase.errors import ShowcaseError
from ctshowcase.meta import load_file
from ctshowcase.resolver import Resolver

SLUG = "Northwind-Trading-Co/receipt-demo"
NOW = "2026-11-18T10:00:00Z"


def pending_job(repo=SLUG):
    return {"id": "synthetic-write", "phase": "1", "kind": "readme", "repo": repo,
            "argv": ["synthetic-writer", "pending"]}


@pytest.fixture
def receipt(tmp_path, brand):
    root = tmp_path / "export"
    (root / "docs/images").mkdir(parents=True)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"owner": "Northwind-Trading-Co", "repo": "receipt-demo",
                               "description": "Review synthetic receipts.", "topics": [], "visibility": "public",
                               "language": "Python", "license": "MIT"}), encoding="utf-8")
    # These bytes exercise receipts, not rendering, image validity, or production completion.
    (root / "README.md").write_text("# Receipt demo\n<!-- showcase:banner:start -->\n"
                                    "![Hero](docs/images/banner.png)\n", encoding="utf-8")
    (root / "docs/images/banner.png").write_bytes(b"synthetic-banner")
    (root / "docs/images/card.svg").write_bytes(b"synthetic-card")
    inp = fp.inputs(load_file(meta), root, same_owner=Resolver(brand).same, metadata_path=meta)
    doc = {}
    for name in ("banner.png", "card.svg"):
        doc = fp.update_sidecar(doc, inp, brand.sha256, name, fp.file_record(root / "docs/images" / name))
    (root / P.REPO_STAMP).write_text(fp.sidecar_text(doc), encoding="utf-8")
    return root, meta


def stamp(brand, receipt, **kwargs):
    root, meta = receipt
    return P.stamp_one(SLUG, brand, Resolver(brand), root=root, meta_path=str(meta), now=NOW, **kwargs)


def check(brand, receipt):
    root, meta = receipt
    return P.check_one(SLUG, brand, Resolver(brand), root=root, meta_path=str(meta))


@pytest.mark.parametrize("path", ["docs/images/banner.png", "docs/images/card.svg", "README.md"])
@pytest.mark.parametrize("mutation", ["delete", "edit"])
def test_recorded_bytes_and_readme_are_checked(brand, receipt, path, mutation):
    result, code = stamp(brand, receipt)
    assert code == 0 and result["completed"]
    fresh = check(brand, receipt)
    assert fresh["status"] == "fresh" and not fresh["skip"] and fresh["rerun"] == []
    output = receipt[0] / path
    if mutation == "delete":
        output.unlink()
    else:
        output.write_bytes(output.read_bytes() + b"edited")
    stale = check(brand, receipt)
    assert stale["status"] == "stale" and f"output:{path}" in stale["changed"]
    assert path in stale["rerun"] and not stale["skip"]


@pytest.mark.parametrize("target", [SLUG, "org:Northwind-Trading-Co", "user:northwind-demo", "enterprise:northwind"])
def test_empty_captures_remain_incomplete_for_every_kind(brand, receipt, tmp_path, target):
    root = tmp_path / "empty"
    root.mkdir()
    kwargs = {"meta_path": str(receipt[1])} if target == SLUG else {}
    out, code = P.stamp_one(target, brand, Resolver(brand), root=root, now=NOW, **kwargs)
    assert code == 0 and out["missing"] and not out["completed"]
    result = P.check_one(target, brand, Resolver(brand), root=root, **kwargs)
    assert result["status"] == "incomplete" and result["missing"] and not result["skip"]
    written = (root / out["stamp"]["path"]).read_bytes()
    again, _ = P.stamp_one(target, brand, Resolver(brand), root=root, now="2026-11-19T10:00:00Z", **kwargs)
    assert again["result"] == "incomplete" and again["written"] is None
    assert (root / out["stamp"]["path"]).read_bytes() == written


def test_stamp_cannot_bless_missing_selected_art_or_stale_generation(brand, receipt):
    root, meta = receipt
    doc = json.loads((root / P.REPO_STAMP).read_text())
    del doc["outputs"]["card.svg"]
    (root / P.REPO_STAMP).write_text(json.dumps(doc), encoding="utf-8")
    metadata = json.loads(meta.read_text())
    metadata["description"] = "Different synthetic input."
    meta.write_text(json.dumps(metadata), encoding="utf-8")
    result, _ = stamp(brand, receipt)
    assert not result["completed"]
    assert {"record:docs/images/card.svg", "generation:docs/images/banner.png"} <= set(result["missing"])
    assert check(brand, receipt)["status"] == "incomplete"


def test_arbitrary_recorded_art_is_checked_and_staged_art_is_incomplete(brand, receipt):
    root, _ = receipt
    doc = json.loads((root / P.REPO_STAMP).read_text())
    (root / "docs/images/tile.svg").write_bytes(b"synthetic-tile")
    doc["outputs"]["tile.svg"] = dict(fp.bytes_record(b"synthetic-tile"), fingerprint=doc["fingerprint"])
    doc["outputs"]["card.svg"]["staged_description"] = {}
    (root / P.REPO_STAMP).write_text(json.dumps(doc), encoding="utf-8")
    result, _ = stamp(brand, receipt)
    assert "staged:docs/images/card.svg" in result["missing"] and not result["completed"]
    (root / "docs/images/tile.svg").unlink()
    assert "output:docs/images/tile.svg" in check(brand, receipt)["changed"]


@pytest.mark.parametrize("target,readme,data", [("org:Northwind-Trading-Co", "profile/README.md", "profile/data.json"),
                                                ("user:northwind-demo", "README.md", "data.json")])
def test_profile_art_and_unavailable_about_are_explicit(brand, tmp_path, target, readme, data):
    root = tmp_path / "export"
    (root / readme).parent.mkdir(parents=True)
    (root / readme).write_text("<!-- showcase:banner:start -->\n![Hero](assets/hero.svg)\n", encoding="utf-8")
    (root / data).write_text("{}", encoding="utf-8")
    art = (root / readme).parent / "assets/hero.svg"
    art.parent.mkdir()
    art.write_bytes(b"synthetic-hero")
    result, _ = P.stamp_one(target, brand, Resolver(brand), root=root, now=NOW)
    assert "input:about" in result["missing"] and not result["completed"]
    art.unlink()
    result = P.check_one(target, brand, Resolver(brand), root=root)
    assert f"output:{art.relative_to(root).as_posix()}" in result["changed"]


def test_enterprise_digest_is_derived_from_sections_and_partial_snapshot_is_incomplete(brand, tmp_path):
    root = tmp_path / "registry"
    root.mkdir()
    snapshot = {"slug": "northwind", "sha256": {"profile": "stale-supplied-digest"},
                "sections": {"profile": {"slug": "northwind"}, "organizations": [], "members": [],
                             "outside_collaborators": []}}
    target, resolver = "enterprise:northwind", Resolver(brand)
    (root / "enterprise.snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    P.stamp_one(target, brand, resolver, root=root, snapshot=snapshot, now=NOW)
    assert P.check_one(target, brand, resolver, root=root, snapshot=snapshot)["status"] == "fresh"
    snapshot["sections"]["profile"]["name"] = "Changed"
    assert P.check_one(target, brand, resolver, root=root, snapshot=snapshot)["status"] == "stale"
    del snapshot["sections"]["members"]
    (root / "enterprise.snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    result, _ = P.stamp_one(target, brand, resolver, root=root, snapshot=snapshot, now=NOW)
    assert "snapshot:members" in result["missing"] and not result["completed"]


@pytest.mark.parametrize("rel", ["../outside", "/outside", "a/../../outside", "a\\outside", "a/%2e%2e/outside"])
def test_source_rejects_unsafe_paths_before_reading(tmp_path, rel):
    with pytest.raises(ShowcaseError, match="selected source"):
        P.Source(root=tmp_path).read(rel)


def test_output_and_evidence_paths_are_validated_before_traversal(brand, receipt):
    root, _ = receipt
    stamp(brand, receipt)
    doc = json.loads((root / P.REPO_STAMP).read_text())
    doc["evidence"]["outputs"]["../outside"] = {"sha256": "0" * 64}
    (root / P.REPO_STAMP).write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ShowcaseError):
        check(brand, receipt)
    del doc["evidence"]["outputs"]["../outside"]
    doc["outputs"]["../outside"] = {"sha256": "0" * 64}
    (root / P.REPO_STAMP).write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ShowcaseError):
        stamp(brand, receipt)


def test_descendant_symlink_cannot_supply_input_or_output_bytes(brand, receipt, tmp_path):
    root, _ = receipt
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "icon.png").write_bytes(b"outside sentinel")
    (root / "assets").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ShowcaseError, match="symlink"):
        stamp(brand, receipt)
    assert (outside / "icon.png").read_bytes() == b"outside sentinel"


@pytest.mark.parametrize("target,stamp_path", [(SLUG, P.REPO_STAMP), ("org:Northwind-Trading-Co", P.DOT_STAMP),
                                             ("user:northwind-demo", P.DOT_STAMP),
                                             ("enterprise:northwind", P.ENTERPRISE_STAMP)])
def test_every_target_rejects_symlink_ancestors(brand, receipt, tmp_path, target, stamp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "linked"
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ShowcaseError, match="symlink"):
        P.stamp_one(target, brand, Resolver(brand), root=root, meta_path=str(receipt[1]), now=NOW)
    assert not (outside / stamp_path).exists()


@pytest.mark.parametrize("origin", ["https://github.com/Northwind-Trading-Co/other.git", "https://example.test/x/y", ""])
@pytest.mark.parametrize("target", [SLUG, "org:Northwind-Trading-Co", "user:northwind-demo", "enterprise:northwind"])
def test_existing_checkout_requires_destination_identity(brand, receipt, tmp_path, origin, target):
    root = tmp_path / "checkout"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    if origin:
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", origin], check=True, capture_output=True)
    with pytest.raises(ShowcaseError):
        P.stamp_one(target, brand, Resolver(brand), root=root, meta_path=str(receipt[1]), now=NOW)
    assert not (root / P.REPO_STAMP).exists() and not (root / P.DOT_STAMP).exists()


def test_matching_checkout_identity_and_resolved_rename_are_allowed(brand, receipt):
    root, meta = receipt
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                    "git@github.com:Northwind-Trading-Old/receipt-demo.git"], check=True, capture_output=True)
    resolver = Resolver(brand, {"orgs": {"Northwind-Trading-Co": {"former_slugs": ["Northwind-Trading-Old"]}}}, None)
    result, code = P.stamp_one(SLUG, brand, resolver, root=root, meta_path=str(meta), now=NOW)
    assert code == 0 and result["completed"]
    assert P.check_one(SLUG.upper(), brand, resolver, root=root, meta_path=str(meta))["status"] == "fresh"


@pytest.mark.parametrize("mutation,missing", [("topics", "input:topics"), ("tree", "input:type")])
def test_partial_capture_inputs_never_become_fresh(brand, receipt, mutation, missing):
    root, meta = receipt
    data = json.loads(meta.read_text())
    if mutation == "tree":
        data["files_complete"] = False
    else:
        del data[mutation]
    meta.write_text(json.dumps(data), encoding="utf-8")
    result, _ = stamp(brand, receipt)
    assert missing in result["missing"] and not result["completed"]
    assert check(brand, receipt)["status"] == "incomplete"


def test_pending_writer_jobs_do_not_complete_or_become_fresh(brand, receipt, tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    jobs.write_text(json.dumps(pending_job()) + "\n", encoding="utf-8")
    result, _ = stamp(brand, receipt, jobs=str(jobs))
    assert result["missing"] == ["writer:pending"] and not result["completed"]
    assert check(brand, receipt)["status"] == "incomplete"


@pytest.mark.parametrize("tty,offline", [(False, False), (False, True), (True, True)])
def test_offline_and_non_tty_never_call_star_get_even_with_override(brand, tmp_path, tty, offline):
    def blocked(*args, **kwargs):
        pytest.fail("silent/offline contexts must not call gh")
    stream = io.StringIO()
    for _ in range(ledger.STAR_THRESHOLD + 1):
        result = ledger.record_run(brand, fresh=False, fmt="text", directory=tmp_path, isatty=lambda: tty,
                                   env={"SHOWCASE_STAR_PROMPT": "1"}, run=blocked, stream=stream, offline=offline)
    assert result["counted"] and not result["asked"] and stream.getvalue() == ""


def test_cli_threads_offline_to_ledger_after_verified_capture(brand, receipt, monkeypatch):
    calls = []
    monkeypatch.setattr(P, "GH", lambda **kw: pytest.fail("offline constructed a GitHub client"))
    monkeypatch.setattr(ledger, "record_run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(P, "_print_text", lambda result: None)
    args = SimpleNamespace(prov_format="text", format="text", repo_dir=receipt[0], meta=str(receipt[1]),
                           prov_action="stamp", offline=True, snapshot=None, target=SLUG, jobs=None, changed="auto",
                           force=False, propose_topic=False, quiet=False, no_star_prompt=False)
    _, code = P.cmd(args, lambda args: brand)
    assert code == 0 and len(calls) == 1 and calls[0]["offline"] is True


def test_pending_writer_cli_never_records_a_completed_run(brand, receipt, tmp_path, monkeypatch):
    jobs = tmp_path / "jobs.jsonl"
    jobs.write_text(json.dumps(pending_job()) + "\n", encoding="utf-8")
    monkeypatch.setattr(ledger, "record_run", lambda *a, **kw: pytest.fail("pending work counted as completed"))
    args = SimpleNamespace(prov_format="json", format="text", repo_dir=receipt[0], meta=str(receipt[1]),
                           prov_action="stamp", offline=True, snapshot=None, target=SLUG, jobs=str(jobs),
                           changed="auto", force=False, propose_topic=False, quiet=False, no_star_prompt=False)
    result, code = P.cmd(args, lambda args: brand)
    assert code == 0 and not result["completed"] and "writer:pending" in result["missing"]


def test_optional_topic_proposal_is_pending_even_without_jobs_file(brand, receipt, monkeypatch):
    monkeypatch.setattr(ledger, "record_run", lambda *a, **kw: pytest.fail("proposal counted as completed"))
    args = SimpleNamespace(prov_format="json", format="text", repo_dir=receipt[0], meta=str(receipt[1]),
                           prov_action="stamp", offline=True, snapshot=None, target=SLUG, jobs=None,
                           changed="auto", force=False, propose_topic=True, approval_id=None, quiet=False,
                           no_star_prompt=False)
    result, code = P.cmd(args, lambda args: brand)
    assert code == 0 and not result["completed"] and result["jobs"][0]["kind"] == "topics"
    assert "writer:pending" in check(brand, receipt)["missing"]


def test_invalid_stamp_is_preserved_and_invalid_pending_jobs_are_unknown(brand, receipt, tmp_path):
    path = receipt[0] / P.REPO_STAMP
    original = path.read_bytes()
    path.write_bytes(b"not JSON")
    with pytest.raises(ShowcaseError):
        stamp(brand, receipt)
    assert path.read_bytes() == b"not JSON"
    path.write_bytes(original)
    jobs = tmp_path / "jobs.jsonl"
    jobs.write_text("not JSON\n", encoding="utf-8")
    with pytest.raises(ShowcaseError):
        stamp(brand, receipt, jobs=str(jobs))


def test_unknown_get_resets_an_old_negative_and_empty_success_is_unknown(brand, tmp_path):
    state = ledger.empty()
    state["completed_runs"] = ledger.STAR_THRESHOLD
    state["star"]["status"] = "not-starred"
    ledger.save(state, tmp_path)
    result = ledger.record_run(brand, fresh=False, fmt="text", directory=tmp_path, env={}, isatty=lambda: True,
                               run=lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="offline"))
    assert result["star"] == "unknown" and not result["asked"]
    assert ledger.gh_starred("synthetic/demo", run=lambda *a, **kw: SimpleNamespace(returncode=0, stdout="", stderr="")) == "unknown"


def topic_args(receipt, jobs):
    return SimpleNamespace(prov_format="json", format="text", repo_dir=receipt[0], meta=str(receipt[1]),
                           prov_action="stamp", offline=True, snapshot=None, target=SLUG, jobs=str(jobs),
                           changed="auto", force=False, propose_topic=True, approval_id=None, quiet=False,
                           no_star_prompt=False)


@pytest.mark.parametrize("destination", ["meta", "snapshot", "README.md", "profile/README.md", P.REPO_STAMP,
                                         P.DOT_STAMP, "docs/images/banner.png", "recorded", "git-internals"])
def test_jobs_cannot_alias_captures_or_managed_outputs(brand, receipt, tmp_path, monkeypatch, destination):
    root, meta = receipt
    snapshot = tmp_path / "capture.json"
    snapshot.write_text(json.dumps({"slug": "northwind", "sections": {}}), encoding="utf-8")
    if destination == "recorded":
        queue = root / "exports/result.jsonl"
        queue.parent.mkdir()
        queue.write_text(json.dumps(pending_job()), encoding="utf-8")
        doc = json.loads((root / P.REPO_STAMP).read_text())
        doc["outputs"]["exports/result.jsonl"] = dict(fp.file_record(queue), fingerprint=doc["fingerprint"])
        (root / P.REPO_STAMP).write_text(json.dumps(doc), encoding="utf-8")
    elif destination == "git-internals":
        queue = tmp_path / "unrelated/.git/config"
        queue.parent.mkdir(parents=True)
        queue.write_text(json.dumps(pending_job()), encoding="utf-8")
    else:
        queue = meta if destination == "meta" else snapshot if destination == "snapshot" else root / destination
    before = {p: p.read_bytes() for p in (meta, snapshot, root / P.REPO_STAMP, queue) if p.is_file()}
    monkeypatch.setattr(ledger, "record_run", lambda *a, **kw: pytest.fail("invalid queue reached the ledger"))
    args = topic_args(receipt, queue)
    args.snapshot = str(snapshot)
    with pytest.raises(ShowcaseError):
        P.cmd(args, lambda args: brand)
    assert all(p.read_bytes() == data for p, data in before.items())
    assert queue in before or not queue.exists()


@pytest.mark.parametrize("kind", ["leaf-symlink", "parent-symlink", "hardlink", "directory"])
def test_jobs_need_unlinked_regular_files_and_safe_ancestors(brand, receipt, tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "queue.jsonl"
    sentinel.write_text(json.dumps(pending_job()) + "\n", encoding="utf-8")
    queue = tmp_path / "selected.jsonl"
    if kind == "leaf-symlink":
        queue.symlink_to(sentinel)
    elif kind == "parent-symlink":
        queue.symlink_to(outside, target_is_directory=True)
        queue /= "queue.jsonl"
    elif kind == "hardlink":
        queue.hardlink_to(sentinel)
    else:
        queue.mkdir()
    before, capture = sentinel.read_bytes(), (receipt[0] / P.REPO_STAMP).read_bytes()
    with pytest.raises(ShowcaseError):
        stamp(brand, receipt, jobs=queue)
    assert sentinel.read_bytes() == before and (receipt[0] / P.REPO_STAMP).read_bytes() == capture


@pytest.mark.parametrize("content", ['{"owner":"Northwind-Trading-Co"}', '[]', '{',
                                      '{"id":"x","phase":"1","kind":"readme","repo":"x/y"}'])
def test_non_job_json_never_authorizes_a_stamp_or_append(brand, receipt, tmp_path, content):
    queue = tmp_path / "queue.jsonl"
    queue.write_text(content, encoding="utf-8")
    before = (receipt[0] / P.REPO_STAMP).read_bytes()
    with pytest.raises(ShowcaseError):
        P.cmd(topic_args(receipt, queue), lambda args: brand)
    assert queue.read_text(encoding="utf-8") == content and (receipt[0] / P.REPO_STAMP).read_bytes() == before


def test_safe_jsonl_queue_appends_topic_once_and_keeps_capture_pending(brand, receipt, tmp_path):
    queue = tmp_path / "queue.jsonl"
    original = json.dumps(pending_job("Northwind-Trading-Co/another"))
    queue.write_text(original, encoding="utf-8")  # A complete last line without an LF stays appendable.
    result, code = P.cmd(topic_args(receipt, queue), lambda args: brand)
    lines = queue.read_text(encoding="utf-8").splitlines()
    assert code == 0 and len(lines) == 2 and lines[0] == original
    assert json.loads(lines[1]) == result["jobs"][0] and result["jobs"][0]["kind"] == "topics"
    assert not result["completed"] and "writer:pending" in check(brand, receipt)["missing"]
    again, _ = stamp(brand, receipt, jobs=queue)
    assert not again["completed"] and "writer:pending" in again["missing"]


def test_failed_queue_publication_restores_the_stamp_and_preserves_the_queue(brand, receipt, tmp_path, monkeypatch):
    queue = tmp_path / "queue.jsonl"
    queue.write_text(json.dumps(pending_job()) + "\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (queue, receipt[0] / P.REPO_STAMP)}
    replace = Path.replace

    def fail_queue(source, destination):
        if destination == queue and source.name == "output":
            raise OSError("synthetic append publication failure")
        return replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_queue)
    monkeypatch.setattr(ledger, "record_run", lambda *a, **kw: pytest.fail("failed publication reached the ledger"))
    with pytest.raises(OSError, match="synthetic"):
        P.cmd(topic_args(receipt, queue), lambda args: brand)
    assert all(path.read_bytes() == data for path, data in before.items())


def test_late_missing_evidence_cannot_be_stamped_even_when_hashes_match(brand, receipt, monkeypatch):
    original, collect = (receipt[0] / P.REPO_STAMP).read_bytes(), P.evidence_for
    calls = 0

    def unavailable(*args, **kwargs):
        nonlocal calls
        calls += 1
        evidence = collect(*args, **kwargs)
        if calls >= 3:
            evidence["missing"].append("input:unavailable-after-capture")
        return evidence

    monkeypatch.setattr(P, "evidence_for", unavailable)
    with pytest.raises(ShowcaseError, match="source changed"):
        stamp(brand, receipt)
    assert (receipt[0] / P.REPO_STAMP).read_bytes() == original


@pytest.mark.parametrize("field,value", [("skill", "another-skill"),
                                        ("skill_url", "https://github.com/Northwind-Trading-Co/another-skill")])
def test_foreign_provenance_identity_is_refused_and_preserved(brand, receipt, tmp_path, monkeypatch, field, value):
    stamp(brand, receipt)
    path = receipt[0] / P.REPO_STAMP
    document = json.loads(path.read_text())
    document["provenance"][field] = value
    path.write_text(json.dumps(document), encoding="utf-8")
    before = path.read_bytes()
    result = check(brand, receipt)
    assert result["status"] == "foreign" and "provenance:foreign-skill" in result["logs"]
    monkeypatch.setattr(ledger, "record_run", lambda *a, **kw: pytest.fail("foreign receipt reached the ledger"))
    queue = tmp_path / "queue.jsonl"
    result, code = P.cmd(topic_args(receipt, queue), lambda args: brand)
    assert code == 2 and result["result"] == "refused" and result["jobs"] == []
    assert path.read_bytes() == before and not queue.exists()
