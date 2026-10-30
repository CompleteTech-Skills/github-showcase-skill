"""E5.2.1: `--description` renders banner, card, content social and readme from a proposed (staged) one-sentence
description. Off by default; the live metadata file is never modified. Fixtures are synthetic (Northwind)."""
import json
import shutil

from conftest import EX, run_cli

META = EX / "meta" / "northwind-support-triage-agent.json"
REPO = EX / "repos" / "northwind-support-triage-agent"


def _repo(tmp_path):
    shutil.copytree(REPO, tmp_path, dirs_exist_ok=True)
    return tmp_path


def _json(proc):
    return json.loads(proc.stdout)


def test_banner_card_accept_description(tmp_path):
    rd = _repo(tmp_path)
    text = "Triage support tickets with an agent."
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", text)
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"]
    assert r["staged_description"]["text"] == text

    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                "--out", rd / "docs/images/card.svg", "--description", text)
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"]
    assert r["staged_description"]["text"] == text


def test_readme_uses_staged_tagline(tmp_path):
    rd = _repo(tmp_path)
    before_meta = META.read_text(encoding="utf-8")
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
                "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"]
    readme = (rd / "README.md").read_text(encoding="utf-8")
    start = readme.index("<!-- showcase:tagline:start -->")
    end = readme.index("<!-- showcase:tagline:end -->")
    assert "**Staged sentence.**" in readme[start:end]
    assert META.read_text(encoding="utf-8") == before_meta


def test_content_social_accepts_description(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "content", "social",
                "--out", rd / "assets/social-preview.png", "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"]


def test_default_unchanged(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner", "--out", rd / "docs/images/banner.png")
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged_description" not in r
    assert "staged-description" not in r["logs"]


def test_empty_description_is_usage_error(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", "  ")
    assert p.returncode == 2


def test_description_is_stripped(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                "--out", rd / "docs/images/card.svg", "--description", "  Padded sentence.  ")
    assert p.returncode == 0, p.stderr
    assert _json(p)["staged_description"]["text"] == "Padded sentence."


def test_live_description_reported_and_meta_untouched(tmp_path):
    rd = _repo(tmp_path)
    before_meta = META.read_text(encoding="utf-8")
    live = json.loads(before_meta).get("description") or ""
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                "--out", rd / "docs/images/card.svg", "--description", "A different sentence.")
    assert p.returncode == 0, p.stderr
    staged = _json(p)["staged_description"]
    assert staged["live_differs"] is (live.strip() != "A different sentence.")
    assert META.read_text(encoding="utf-8") == before_meta


def _watching_fork(tmp_path, monkeypatch):
    """Synthetic watching-fork case: the fixture owner is marked `watching` and the repo is a fork, so the
    generators take their `exempt:watching-fork` branch. Only the owner lookup is patched; no real owner is named."""
    import showcase
    from ctshowcase import config
    orig = config.Brand.owner_status
    monkeypatch.setattr(config.Brand, "owner_status",
                        lambda self, owner: "watching" if owner == "Northwind-Trading-Co" else orig(self, owner))
    meta = tmp_path / "fork-meta.json"
    data = json.loads(META.read_text(encoding="utf-8"))
    data["fork"] = True
    meta.write_text(json.dumps(data), encoding="utf-8")
    rd = tmp_path / "repo"
    shutil.copytree(REPO, rd)
    return showcase, meta, rd


def test_exempt_readme_keeps_staged_log(tmp_path, monkeypatch, capsys):
    # regression: the exempt branch passes its own logs=, which used to drop staged-description while the
    # staged_description object was still written
    showcase, meta, rd = _watching_fork(tmp_path, monkeypatch)
    rc = showcase.main(["--meta", str(meta), "--repo-dir", str(rd), "--format", "json", "readme",
                        "--mode", "scaffold", "--description", "  Staged sentence.  "])
    r = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert r["result"] == "exempt"
    assert "staged-description" in r["logs"] and "exempt" in r["logs"]
    assert r["staged_description"]["text"] == "Staged sentence."


def test_exempt_banner_keeps_staged_log(tmp_path, monkeypatch, capsys):
    showcase, meta, rd = _watching_fork(tmp_path, monkeypatch)
    rc = showcase.main(["--meta", str(meta), "--repo-dir", str(rd), "--format", "json", "banner",
                        "--out", str(rd / "docs/images/banner.png"), "--description", "Staged sentence."])
    r = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert r["result"] == "exempt"
    assert "staged-description" in r["logs"]
    assert r["staged_description"]["text"] == "Staged sentence."


def test_exempt_without_description_is_unchanged(tmp_path, monkeypatch, capsys):
    showcase, meta, rd = _watching_fork(tmp_path, monkeypatch)
    rc = showcase.main(["--meta", str(meta), "--repo-dir", str(rd), "--format", "json", "readme",
                        "--mode", "scaffold"])
    r = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert r["logs"] == ["exempt"]
    assert "staged_description" not in r


# -- E5.2.2: the sidecar records the staged sentence (text and hash) per output -----------------------------------------
import hashlib  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from conftest import ROOT  # noqa: E402
from ctshowcase import fingerprint as fp  # noqa: E402
from ctshowcase.meta import merged  # noqa: E402

PREP = [sys.executable, str(ROOT / "scripts" / "action_prepare.py")]
SIDE = "docs/images/.showcase.json"
# Synthetic Northwind staged sentence; sha256 of this text is what the sidecar must carry.
STAGED = "Triage Northwind support tickets with an agent."
# The plain (no --description) fingerprint of the Northwind fixture, computed on the base commit 2be04ac.
PLAIN_FINGERPRINT = "197b2bde0c9bb312a39e5f47727e27d6f677e574476ecc713b7aa01dc2d3b0cc"


def _sidecar(rd):
    return json.loads((rd / SIDE).read_text(encoding="utf-8"))


def _staged(text):
    return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def test_sidecar_records_staged_text_and_hash(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", STAGED)
    assert p.returncode == 0, p.stderr
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                "--out", rd / "docs/images/card.svg", "--description", STAGED)
    assert p.returncode == 0, p.stderr
    data = _sidecar(rd)
    assert data["outputs"]["banner.png"]["staged_description"] == _staged(STAGED)
    assert data["outputs"]["card.svg"]["staged_description"] == _staged(STAGED)
    assert data["inputs"]["description"] == STAGED


def test_sidecar_unchanged_without_description(tmp_path):
    rd = _repo(tmp_path)
    args = ("--meta", META, "--repo-dir", rd, "--format", "json", "banner", "--out", rd / "docs/images/banner.png")
    assert run_cli(*args).returncode == 0
    first = (rd / SIDE).read_bytes()
    assert "staged_description" not in _sidecar(rd)["outputs"]["banner.png"]
    assert run_cli(*args).returncode == 0
    assert (rd / SIDE).read_bytes() == first  # determinism: a second identical run writes the same bytes


def test_stale_staged_record_on_other_output_is_kept(tmp_path):
    # Intended (E5.2.2 item 5): a plain re-render replaces only its own output's record; nothing is cleaned up.
    rd = _repo(tmp_path)
    assert run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                   "--out", rd / "docs/images/banner.png", "--description", STAGED).returncode == 0
    assert run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                   "--out", rd / "docs/images/card.svg").returncode == 0
    outs = _sidecar(rd)["outputs"]
    assert outs["banner.png"]["staged_description"] == _staged(STAGED)
    assert "staged_description" not in outs["card.svg"]


def test_readme_write_records_staged_when_images_dir_exists(tmp_path):
    rd = _repo(tmp_path)
    (rd / "docs" / "images").mkdir(parents=True)
    assert run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                   "--out", rd / "docs/images/banner.png").returncode == 0  # a sidecar must already exist
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
                "--description", "  " + STAGED + "  ")
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description" in r["logs"] and "staged-description-unrecorded" not in r["logs"]
    data = _sidecar(rd)
    assert data["outputs"]["README.md"]["staged_description"] == _staged(STAGED)
    assert set(data["outputs"]["README.md"]) <= {"staged_description", "repository_id"}  # no sha256/bytes for a README
    assert data["inputs"]["description"] != STAGED  # the art's inputs are untouched by a README-only write


def test_readme_dry_run_writes_nothing(tmp_path):
    rd = _repo(tmp_path)
    (rd / "docs" / "images").mkdir(parents=True)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold",
                "--description", STAGED)
    assert p.returncode == 0, p.stderr
    assert not (rd / SIDE).exists()
    assert run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                   "--out", rd / "docs/images/banner.png").returncode == 0
    before = (rd / SIDE).read_bytes()
    assert run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold",
                   "--description", "A different sentence.").returncode == 0
    assert (rd / SIDE).read_bytes() == before  # no sidecar change without --write


def test_readme_without_images_dir_logs_unrecorded(tmp_path):
    rd = _repo(tmp_path)
    assert not (rd / "docs" / "images").exists()
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
                "--description", STAGED)
    assert p.returncode == 0, p.stderr
    r = _json(p)
    assert "staged-description-unrecorded" in r["logs"]
    assert not (rd / "docs" / "images").exists()  # never created


def test_fingerprint_unchanged_for_plain_runs(tmp_path):
    inp = fp.inputs(merged(META, None), None)
    assert "staged_description" not in inp  # no staged key in the fingerprint inputs
    assert fp.fingerprint(inp, fp.config_sha256()) == PLAIN_FINGERPRINT
    p = run_cli("--meta", META, "--no-repo-dir", "--format", "json", "fingerprint", "--out-dir", tmp_path / "none")
    assert p.returncode == 0, p.stderr
    assert _json(p)["fingerprint"] == PLAIN_FINGERPRINT


def test_staged_record_hashes_utf8_text_exactly():
    text = "Résumé triage für Northwind — agent café."
    rec = fp.staged_record(text)
    assert rec == {"text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    assert rec["sha256"] == fp.description_sha256(text)


def test_description_sha256_strips_before_hashing():
    assert fp.description_sha256("  " + STAGED + "\n") == hashlib.sha256(STAGED.encode("utf-8")).hexdigest()


def test_staged_text_is_recorded_stripped(tmp_path):
    rd = _repo(tmp_path)
    assert run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                   "--out", rd / "docs/images/card.svg", "--description", "  " + STAGED + "  ").returncode == 0
    assert _sidecar(rd)["outputs"]["card.svg"]["staged_description"] == _staged(STAGED)


def test_action_prepare_ignores_staged_description_key(tmp_path):
    # action_prepare reads only inputs and repository_id: a staged record on an output is never a recorded id
    repo = tmp_path / "repo"
    (repo / "docs" / "images").mkdir(parents=True)
    inp = {"owner": "Northwind-Trading-Co", "repo": "northwind-widget", "type": "cli"}
    outputs = {"banner.png": {"sha256": "x", "repository_id": 4242},
               "card.svg": {"sha256": "y", "staged_description": _staged(STAGED)},
               "README.md": {"staged_description": _staged(STAGED)}}
    (repo / SIDE).write_text(json.dumps({"inputs": inp, "outputs": outputs}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "SHOWCASE_IS_TEMPLATE"}
    env["GITHUB_REPOSITORY_ID"] = "4242"  # the same repository under another name: not foreign, art kept
    p = subprocess.run([*PREP, "foreign", "Northwind-Trading-Co/northwind-gadget"], cwd=repo, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "false"
    # only staged records, no repository_id: no recorded id, so no proof of foreign art either
    outputs2 = {"banner.png": {"sha256": "x", "staged_description": _staged(STAGED)}}
    (repo / SIDE).write_text(json.dumps({"inputs": inp, "outputs": outputs2}), encoding="utf-8")
    env["GITHUB_REPOSITORY_ID"] = "9999"
    p = subprocess.run([*PREP, "foreign", "Northwind-Trading-Co/northwind-gadget"], cwd=repo, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "false"


def test_readme_write_keeps_art_fingerprint(tmp_path):
    # Review finding (E5.2.2 A): a README-only staged write must not move the art's recorded fingerprint. banner.png
    # was rendered from the live About, so the sidecar keeps that fingerprint and inputs; only outputs['README.md'] changes.
    rd = _repo(tmp_path)
    assert run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                   "--out", rd / "docs/images/banner.png").returncode == 0
    before = _sidecar(rd)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
                "--description", STAGED)
    assert p.returncode == 0, p.stderr
    after = _sidecar(rd)
    assert after["fingerprint"] == before["fingerprint"]
    assert after["inputs"] == before["inputs"]
    assert after["config_sha256"] == before["config_sha256"]
    assert after["outputs"]["banner.png"] == before["outputs"]["banner.png"]
    assert after["outputs"]["README.md"]["staged_description"] == _staged(STAGED)
    # the art still answers as up to date against the live About: the gate does not regenerate it
    f = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "fingerprint", "--out-dir", rd / "docs/images")
    assert f.returncode == 0, f.stderr
    assert _json(f)["changed"] is False


def test_staged_record_strips_padded_text_and_hash_matches_text():
    # Review finding (E5.2.2 B): the recorded hash must be the hash of the recorded text, stripped the same way
    padded = "  " + STAGED + "\n"
    rec = fp.staged_record(padded)
    assert rec == {"text": STAGED, "sha256": hashlib.sha256(STAGED.encode("utf-8")).hexdigest()}
    assert rec["sha256"] == fp.description_sha256(padded) == fp.staged_record(STAGED)["sha256"]


def test_readme_with_empty_images_dir_and_no_sidecar_logs_unrecorded(tmp_path):
    # Review finding (E5.2.2 R2 A): no sidecar means no rendered art; a fresh sidecar would make the Action's
    # fingerprint step report changed=false for banner/card nobody rendered. Do not create one.
    rd = _repo(tmp_path)
    (rd / "docs" / "images").mkdir(parents=True)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
                "--description", STAGED)
    assert p.returncode == 0, p.stderr
    assert "staged-description-unrecorded" in _json(p)["logs"]
    assert not (rd / SIDE).exists()


def test_readme_write_preserves_old_version_sidecar_and_adds_no_repository_id(tmp_path):
    # Review finding (E5.2.2 R2 B): an existing sidecar keeps its skill_version/fingerprint/standard (older art must
    # still read as changed), and the README record carries no repository_id (it could mask foreign art ids).
    rd = _repo(tmp_path)
    assert run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                   "--out", rd / "docs/images/banner.png").returncode == 0
    data = _sidecar(rd)
    data["skill_version"] = "0.9.0"
    data["outputs"]["banner.png"]["repository_id"] = 4242
    (rd / SIDE).write_text(json.dumps(data, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    before = _sidecar(rd)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
                "--description", STAGED)
    assert p.returncode == 0, p.stderr
    after = _sidecar(rd)
    assert after["skill_version"] == "0.9.0"
    for k in ("fingerprint", "standard", "inputs", "config_sha256", "schema"):
        assert after[k] == before[k]
    assert after["outputs"]["README.md"] == {"staged_description": _staged(STAGED)}
    env = {k: v for k, v in os.environ.items() if k != "SHOWCASE_IS_TEMPLATE"}
    env["GITHUB_REPOSITORY_ID"] = "9999"  # banner says 4242: still provably foreign after the README write
    q = subprocess.run([*PREP, "foreign", "Northwind-Trading-Co/northwind-gadget"], cwd=rd, env=env,
                       capture_output=True, text=True)
    assert q.stdout.strip() == "true", q.stderr


def test_readme_record_without_repository_id_keeps_foreign_art_provable(tmp_path):
    # Review round 3 (B asked for repository_id on the README record; A/decision: merge-only, no id). Evidence for
    # declining: action_prepare.foreign() joins the ids of ALL output records. Art copied from repository 1111 carries
    # that id; a README record stamped with this repository's id (4242) would make the set {1111, 4242}, contain the
    # runner's id, and stop foreign() from proving the copy, so the copied banner/icon would be kept.
    repo = tmp_path / "repo"
    (repo / "docs" / "images").mkdir(parents=True)
    inp = {"owner": "Northwind-Trading-Co", "repo": "northwind-widget", "type": "cli"}
    env = {k: v for k, v in os.environ.items() if k != "SHOWCASE_IS_TEMPLATE"}
    env["GITHUB_REPOSITORY_ID"] = "4242"

    def foreign(outputs):
        (repo / SIDE).write_text(json.dumps({"inputs": inp, "outputs": outputs}), encoding="utf-8")
        p = subprocess.run([*PREP, "foreign", "Northwind-Trading-Co/northwind-gadget"], cwd=repo, env=env,
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        return p.stdout.strip()

    copied = {"banner.png": {"sha256": "x", "repository_id": 1111}}
    assert foreign({**copied, "README.md": {"staged_description": _staged(STAGED)}}) == "true"  # what the code writes
    assert foreign({**copied, "README.md": {"staged_description": _staged(STAGED), "repository_id": 4242}}) == "false"
