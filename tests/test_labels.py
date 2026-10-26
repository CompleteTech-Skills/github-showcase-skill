from pathlib import Path

from ctshowcase import labels

DEFAULTS = [("bug", "d73a4a", "Something isn't working"), ("documentation", "0075ca", "Improvements or additions to documentation"),
            ("duplicate", "cfd3d7", "This issue or pull request already exists"), ("enhancement", "a2eeef", "New feature or request"),
            ("good first issue", "7057ff", "Good first issues"), ("help wanted", "008672", "Extra attention needed"),
            ("invalid", "e4e669", "This doesn't seem right"), ("question", "d876e3", "Further information is requested"),
            ("wontfix", "ffffff", "This will not be worked on")]


def existing(rows=DEFAULTS):
    return [{"name": n, "color": c, "description": d} for n, c, d in rows]


def test_emit_yml_matches_standard():
    std = (Path(__file__).resolve().parents[2] / "STANDARD.md")
    text = labels.emit_yml()
    if std.is_file():
        s = std.read_text(encoding="utf-8")
        i = s.index("```yaml\n# CompleteTech label standard")
        assert s[i + 8: s.index("```", i + 8)] == text
    assert len(labels.standard_labels()) == 23


# the owner's .github captured whole with no default issue form: rule 0 has nothing to read there either
CLEAN = labels.defaults_source("Northwind-Trading-Co/.github", meta={"files": ["README.md"], "files_complete": True})


def test_github_defaults_plan():
    ops, logs = labels.plan(existing(), files=["README.md"], complete=True, defaults=CLEAN)  # nothing rule 0 reads
    kinds = [o["op"] for o in ops]
    assert kinds.count("rename") == 7 and kinds.count("create") == 14 and kinds.count("patch") == 2
    with_acc = existing(DEFAULTS + [("accessibility", "f143ab", "x")])
    kinds = [o["op"] for o in labels.plan(with_acc, files=["README.md"], complete=True, defaults=CLEAN)[0]]
    assert kinds.count("rename") == 8 and kinds.count("create") == 13


def test_conflict_and_referenced(tmp_path):
    ops, logs = labels.plan(existing(DEFAULTS + [("type:bug", "1d76db", "Type: something is broken or behaves incorrectly")]))
    assert "label-conflict" in logs
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/triage.yml").write_text("labels: [bug]\n")
    ops, logs = labels.plan(existing(), tmp_path)
    assert "label-referenced" in logs and not any(o["op"] == "rename" and o["name"] == "bug" for o in ops)


def test_no_force_no_delete():
    ops, _ = labels.plan(existing(), files=[])
    lines = labels.gh_lines("Northwind-Trading-Co", "x", ops)
    assert lines and all("--force" not in ln and " delete " not in ln for ln in lines)
