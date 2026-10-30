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


# ---------------------------------------------------------------------------------------------------
# E5.2.3: `doctor` logs drift between the artifacts and the live About text (logs only; cells, COLUMNS, TSV and
# the exit code are unchanged). Every fixture is a synthetic Northwind copy in tmp_path.
#
# Base-vs-HEAD evidence (the new tests run against base 9de238f, which has no drift logging): 8 fail there, proving
# the feature: test_doctor_no_drift_when_equal, test_doctor_flags_tagline_drift,
# test_doctor_applied_description_clears_drift, test_tagline_text_normalises_markup,
# test_tagline_in_fenced_code_is_ignored, test_doctor_sidecar_drift_without_readme,
# test_tagline_inline_markup_has_no_gap and test_staged_record_stores_digest_and_keeps_inputs_text.
# The other new tests pass on the base BY DESIGN: they are regression guards for "no drift code / row unchanged"
# (test_doctor_ignores_whitespace_difference, test_doctor_no_readme_or_no_tagline_block_is_silent,
# test_doctor_missing_live_description_is_silent, test_doctor_tsv_unchanged, test_doctor_inline_markup_is_not_drift,
# test_doctor_unreadable_sidecar_keeps_row, test_doctor_denied_sidecar_stat_keeps_row). They assert the absence of
# a log or a changed row, which the base also satisfies; they fail if the feature over-reports or alters the row.
# ---------------------------------------------------------------------------------------------------
import json as _jsonmod  # noqa: E402

from ctshowcase import doctor  # noqa: E402

DRIFT = ("drift:tagline-description", "drift:staged-description")


def _live_text():
    return _jsonmod.loads(META.read_text(encoding="utf-8"))["description"]


def _meta_with(tmp_path, description):
    data = _jsonmod.loads(META.read_text(encoding="utf-8"))
    data["description"] = description
    path = tmp_path / "live-meta.json"
    path.write_text(_jsonmod.dumps(data), encoding="utf-8")
    return path


def _doctor_logs(rd, meta=META):
    p = run_cli("--meta", meta, "--repo-dir", rd, "doctor", "--format", "json")
    assert p.returncode in (0, 1), p.stderr
    return _json(p)["logs"]


def _tagline_span(text):
    start = text.index("<!-- showcase:tagline:start -->") + len("<!-- showcase:tagline:start -->")
    end = text.index("<!-- showcase:tagline:end -->")
    return start, end


def test_doctor_no_drift_when_equal(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write")
    assert p.returncode == 0, p.stderr
    readme = (rd / "README.md").read_text(encoding="utf-8")
    assert doctor.tagline_text(readme) == " ".join(_live_text().split())  # the mechanism is really exercised
    logs = _doctor_logs(rd)
    assert not set(DRIFT) & set(logs)


def test_doctor_flags_tagline_drift(tmp_path):
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    assert "staged-description" in _json(p)["logs"]
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
                "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    logs = _doctor_logs(rd)  # the unmodified live meta
    assert "drift:tagline-description" in logs
    assert "drift:staged-description" in logs


def test_doctor_ignores_whitespace_difference(tmp_path):
    rd = _repo(tmp_path)
    run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write")
    readme_path = rd / "README.md"
    text = readme_path.read_text(encoding="utf-8")
    start, end = _tagline_span(text)
    body = text[start:end]
    spread = body.replace(" ", "  \n  ")  # double spaces and newlines inside the tagline block only
    assert spread != body
    readme_path.write_text(text[:start] + spread + text[end:], encoding="utf-8")
    logs = _doctor_logs(rd)
    assert not set(DRIFT) & set(logs)


def test_doctor_no_readme_or_no_tagline_block_is_silent(tmp_path):
    rd = _repo(tmp_path)  # fixture README has no tagline block
    assert not set(DRIFT) & set(_doctor_logs(rd, _meta_with(tmp_path, "A different sentence.")))
    (rd / "README.md").unlink()  # no README at all
    assert not set(DRIFT) & set(_doctor_logs(rd, _meta_with(tmp_path, "A different sentence.")))


def test_doctor_missing_live_description_is_silent(tmp_path):
    rd = _repo(tmp_path)
    run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
            "--out", rd / "docs/images/banner.png", "--description", "Staged sentence.")
    run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
            "--description", "Staged sentence.")
    logs = _doctor_logs(rd, _meta_with(tmp_path, "   "))
    assert not set(DRIFT) & set(logs)


def test_doctor_applied_description_clears_drift(tmp_path):
    rd = _repo(tmp_path)
    run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
            "--out", rd / "docs/images/banner.png", "--description", "Staged sentence.")
    run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write",
            "--description", "Staged sentence.")
    assert "drift:staged-description" in _doctor_logs(rd)
    applied = _meta_with(tmp_path, "Staged sentence.")  # the About text now equals the staged one
    assert not set(DRIFT) & set(_doctor_logs(rd, applied))


def test_doctor_tsv_unchanged(tmp_path):
    rd = _repo(tmp_path)
    run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
            "--out", rd / "docs/images/banner.png", "--description", "Staged sentence.")
    sidecar = rd / "docs/images/.showcase.json"
    assert sidecar.is_file()
    with_side = [run_cli("--meta", META, "--repo-dir", rd, "doctor", *f).stdout for f in ((), ("--header",))]
    md_with = run_cli("--meta", META, "--repo-dir", rd, "doctor", "--format", "md").stdout
    sidecar.unlink()
    without = [run_cli("--meta", META, "--repo-dir", rd, "doctor", *f).stdout for f in ((), ("--header",))]
    md_without = run_cli("--meta", META, "--repo-dir", rd, "doctor", "--format", "md").stdout
    assert with_side == without and md_with == md_without


def test_tagline_text_normalises_markup():
    text = '<!-- showcase:tagline:start -->\n<p align="center">\n  <b>**Hello   world.**</b>\n</p>\n<!-- showcase:tagline:end -->'
    assert doctor.tagline_text(text) == "Hello world."
    assert doctor.tagline_text("no markers here") is None
    assert doctor.tagline_text("<!-- showcase:tagline:start -->\n** **\n<!-- showcase:tagline:end -->") is None


def test_tagline_in_fenced_code_is_ignored(tmp_path):
    fenced = ("Example:\n\n```markdown\n<!-- showcase:tagline:start -->\n**Fenced example.**\n"
              "<!-- showcase:tagline:end -->\n```\n")
    assert doctor.tagline_text(fenced) is None
    rd = _repo(tmp_path)
    (rd / "README.md").write_text(fenced, encoding="utf-8")
    assert not set(DRIFT) & set(_doctor_logs(rd))


def test_doctor_sidecar_drift_without_readme(tmp_path):
    # review E5.2.3 (A P3 / B P2): the staged-render sidecar check depends only on docs/images/.showcase.json and a
    # non-empty live description, so it must still log drift when README.md is absent. The tagline check alone needs
    # the README.
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    assert (rd / "docs/images/.showcase.json").is_file()
    (rd / "README.md").unlink()
    logs = _doctor_logs(rd)
    assert "drift:staged-description" in logs
    assert "drift:tagline-description" not in logs


def test_tagline_inline_markup_has_no_gap():
    # regression (review E5.2.3 B P2): markup was replaced by a space, so "world</b>." normalised to "world ."
    text = ('<!-- showcase:tagline:start -->\n<p align="center">\n  <b>**Hello <b>world</b>.**</b>\n</p>\n'
            '<!-- showcase:tagline:end -->')
    assert doctor.tagline_text(text) == "Hello world."
    assert doctor.tagline_text("<!-- showcase:tagline:start -->\nHello<b>world</b>\n<!-- showcase:tagline:end -->") \
        == "Helloworld"


def test_doctor_inline_markup_is_not_drift(tmp_path):
    rd = _repo(tmp_path)
    run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "readme", "--mode", "scaffold", "--write")
    readme_path = rd / "README.md"
    text = readme_path.read_text(encoding="utf-8")
    start, end = _tagline_span(text)
    readme_path.write_text(text[:start] + "\n  <b>Hello <b>world</b>.</b>\n" + text[end:], encoding="utf-8")
    applied = _meta_with(tmp_path, "Hello world.")  # the live About text reads the same as the rendered tagline
    assert not set(DRIFT) & set(_doctor_logs(rd, applied))


def test_doctor_unreadable_sidecar_keeps_row(tmp_path, monkeypatch, capsys):
    # regression (review E5.2.3 B P2): an OSError from the optional sidecar read must not change the row or exit code
    import showcase
    from ctshowcase import fingerprint
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    base_rc = showcase.main(["--meta", str(META), "--repo-dir", str(rd), "doctor"])
    base_out = capsys.readouterr().out

    def denied(_out_dir):
        raise PermissionError("denied")
    monkeypatch.setattr(fingerprint, "read_sidecar", denied)
    rc = showcase.main(["--meta", str(META), "--repo-dir", str(rd), "doctor"])
    out = capsys.readouterr().out
    assert rc == base_rc
    assert out == base_out  # the TSV row (no drift log in TSV output) is unchanged


def test_doctor_denied_sidecar_stat_keeps_row(tmp_path, monkeypatch, capsys):
    # regression (review E5.2.3 B P2): a denied stat() of the optional sidecar is log-only, never a usage error
    import pathlib
    import sys
    import showcase
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "banner",
                "--out", rd / "docs/images/banner.png", "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    base_rc = showcase.main(["--meta", str(META), "--repo-dir", str(rd), "doctor", "--header"])
    base_out = capsys.readouterr().out
    real = pathlib.Path.is_file

    def guarded(self):
        # only the drift check in doctor.py is under test; pnglint's own sidecar stat predates E5.2.3
        if self.name == ".showcase.json" and sys._getframe(1).f_code.co_filename.endswith("doctor.py"):
            raise PermissionError(13, "denied")
        return real(self)
    monkeypatch.setattr(pathlib.Path, "is_file", guarded)
    rc = showcase.main(["--meta", str(META), "--repo-dir", str(rd), "doctor", "--header"])
    out = capsys.readouterr().out
    assert rc == base_rc
    assert out == base_out


def test_staged_record_stores_digest_and_keeps_inputs_text(tmp_path):
    # the claim in CHANGELOG and fingerprint.description_sha256: each output record adds a digest; inputs.description
    # still carries the rendered text (fingerprint inputs are not changed by this task)
    from ctshowcase import fingerprint as fp
    rd = _repo(tmp_path)
    p = run_cli("--meta", META, "--repo-dir", rd, "--format", "json", "card",
                "--out", rd / "docs/images/card.svg", "--description", "Staged sentence.")
    assert p.returncode == 0, p.stderr
    data = fp.read_sidecar(rd / "docs" / "images")
    rec = data["outputs"]["card.svg"]
    assert rec["staged_description"] == {"sha256": fp.description_sha256("Staged sentence.")}
    assert data["inputs"]["description"] == "Staged sentence."
