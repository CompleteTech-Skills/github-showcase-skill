"""Decision 25 (PROPOSAL): provenance stamp, run-once check, public credit and the operator-side star nudge.
Synthetic Northwind fixtures and brand.yaml's public rows only; every gh call is mocked and must be a GET."""
import base64
import io
import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import EX, ROOT, run_bash, run_cli
from ctshowcase import fingerprint as fp
from ctshowcase import footer, ledger, readme, readmelint
from ctshowcase import provenance as P
from ctshowcase.errors import NeedsInput
from ctshowcase.resolver import Resolver

META = EX / "meta" / "northwind-support-triage-agent.json"
FIXTURE = EX / "repos" / "northwind-support-triage-agent"
SLUG = "Northwind-Trading-Co/support-triage-agent"
T0, T1 = "2026-11-01T10:00:00Z", "2026-11-02T11:30:00Z"


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env)


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def generate(repo):
    for args in (("banner", "--allow-few-chips"), ("card",), ("readme", "--write")):
        p = run_cli("--meta", META, "--repo-dir", repo, *args)
        assert p.returncode in (0, 4), p.stdout + p.stderr


def commit(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "art", "--allow-empty")


def check(brand, repo, meta=META, resolver=None, text=SLUG):
    return P.check_one(text, brand, resolver or Resolver(brand), root=repo, meta_path=str(meta), gh=None)


def stamp(brand, repo, now=T0, resolver=None, **kw):
    return P.stamp_one(SLUG, brand, resolver or Resolver(brand), root=repo, meta_path=str(META), gh=None, now=now, **kw)


def edited_meta(tmp_path, **changes):
    m = json.loads(META.read_text(encoding="utf-8"))
    m.update(changes)
    p = tmp_path / "meta-edited.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------------------------- check statuses
def test_every_repository_status(brand, checkout, tmp_path):
    assert check(brand, checkout)["status"] == "never"
    generate(checkout)
    r = check(brand, checkout)
    assert r["status"] == "untracked" and "provenance:backfill-available" in r["logs"]
    res, code = stamp(brand, checkout)
    assert code == 0 and res["result"] == "stamped" and res["written"]
    commit(checkout)
    assert check(brand, checkout)["status"] == "fresh"
    stale = check(brand, checkout, meta=edited_meta(tmp_path, description="Route Northwind support email to queues."))
    assert stale["status"] == "stale" and "inputs:description" in stale["changed"]
    assert P.EXIT["fresh"] == 0 and P.EXIT["stale"] == P.EXIT["never"] == P.EXIT["untracked"] == 1


@pytest.mark.parametrize("target,log", [("BunsDev/anything", "exempt"), ("Pick-Your-AI/board", "t3-signoff")])
def test_foreign_owners_are_refused_before_anything_is_read(brand, target, log):
    class NoGh:
        def json(self, path):
            raise AssertionError(f"a foreign target must not be read: {path}")

        def file(self, repo, path):
            raise AssertionError(f"a foreign target must not be read: {repo}/{path}")
    r = P.check_one(target, brand, Resolver(brand), gh=NoGh())
    assert r["status"] == "foreign" and log in r["logs"] and P.EXIT["foreign"] == 2


def test_watching_org_fork_is_foreign(brand, tmp_path):
    meta = tmp_path / "w.json"
    meta.write_text(json.dumps({"owner": "romgenie-following-repos", "repo": "tool", "fork": True,
                                "visibility": "public", "description": "A followed tool."}), encoding="utf-8")
    r = P.check_one("romgenie-following-repos/tool", brand, Resolver(brand), root=tmp_path, meta_path=str(meta))
    assert r["status"] == "foreign" and "exempt:watching-fork" in r["logs"]


def test_a_renamed_org_still_finds_its_stamp(brand, tmp_path):
    """CQ-03: the stamp was written under the org's current login; a lookup by the former login resolves to it."""
    reg = {"orgs": {"Northwind-Trading-Co": {"former_slugs": ["Northwind-Trading-Old"]}}}
    res = Resolver(brand, reg, None)
    dot = tmp_path / "dot-github"
    (dot / "profile").mkdir(parents=True)
    (dot / "profile" / "README.md").write_text("# Northwind\n\n" + footer.block(brand) + "\n", encoding="utf-8")
    out, code = P.stamp_one("Northwind-Trading-Co", brand, res, root=dot, gh=None, now=T0)
    assert code == 0 and out["target"] == "Northwind-Trading-Co"
    old = P.check_one("Northwind-Trading-Old", brand, res, root=dot, gh=None)
    assert old["status"] == "fresh" and old["target"] == "Northwind-Trading-Co"
    assert "resolved:Northwind-Trading-Old->Northwind-Trading-Co" in old["logs"]
    repo_t = P.parse_target("northwind-trading-old/support-triage-agent", res)
    assert repo_t.id == "Northwind-Trading-Co/support-triage-agent"


def test_profile_and_org_statuses(brand, tmp_path):
    prof = tmp_path / "profile"
    prof.mkdir()
    res = Resolver(brand)
    assert P.check_one("user:northwind-demo", brand, res, root=prof)["status"] == "never"
    (prof / "README.md").write_text("# Hi\n\n" + footer.block(brand) + "\n", encoding="utf-8")
    assert P.check_one("user:northwind-demo", brand, res, root=prof)["status"] == "untracked"
    out, _ = P.stamp_one("user:northwind-demo", brand, res, root=prof, now=T0)
    assert (prof / ".github" / "showcase.json").is_file() and out["stamp"]["repo"] == "northwind-demo/northwind-demo"
    assert P.check_one("user:northwind-demo", brand, res, root=prof)["status"] == "fresh"
    (prof / "README.md").write_text("# Hi, edited\n\n" + footer.block(brand) + "\n", encoding="utf-8")
    r = P.check_one("user:northwind-demo", brand, res, root=prof)
    assert r["status"] == "stale" and "inputs:readme_sha256" in r["changed"]


def test_enterprise_stamp_is_private_and_needs_a_snapshot(brand, tmp_path):
    snap = json.loads((ROOT / "tests/fixtures/enterprise/snapshot-before.json").read_text(encoding="utf-8"))
    reg = tmp_path / "registry"
    reg.mkdir()
    res = Resolver(brand)
    assert P.check_one("enterprise:completetech", brand, res, root=reg, snapshot=snap)["status"] == "never"
    out, code = P.stamp_one("enterprise:completetech", brand, res, root=reg, snapshot=snap, now=T0,
                            jobs=str(tmp_path / "jobs.jsonl"))
    assert code == 0 and out["jobs"] == [] and out["stamp"]["repo"] is None  # never a public repository, never a job
    assert (reg / "enterprise.showcase.json").is_file() and not (tmp_path / "jobs.jsonl").exists()
    assert P.check_one("enterprise:completetech", brand, res, root=reg, snapshot=snap)["status"] == "fresh"
    snap["sections"]["profile"]["description"] = "Changed"
    assert P.check_one("enterprise:completetech", brand, res, root=reg, snapshot=snap)["status"] == "stale"
    with pytest.raises(NeedsInput):
        P.check_one("enterprise:completetech", brand, res, root=reg, snapshot=None)


# ---------------------------------------------------------------------------------------------- the stamp
def test_timestamps_and_run_count_stay_out_of_the_fingerprint(brand, checkout):
    generate(checkout)
    first, _ = stamp(brand, checkout, now=T0)
    sidecar_fp = fp.read_sidecar(checkout / "docs/images")["fingerprint"]
    second, _ = stamp(brand, checkout, now=T1, force=True)
    a, b = first["provenance"], second["provenance"]
    assert a["fingerprint"] == b["fingerprint"] == sidecar_fp
    assert (a["last_run_at"], b["last_run_at"], b["first_run_at"], b["run_count"]) == (T0, T1, T0, 2)
    p = run_cli("--meta", META, "--repo-dir", checkout, "fingerprint", "--outputs", "banner,card")
    assert json.loads(p.stdout)["changed"] is False  # the Action sees no change after a stamp: no loop


def test_stamp_output_is_deterministic_and_idempotent(brand, checkout):
    generate(checkout)
    stamp(brand, checkout, now=T0)
    commit(checkout)
    path = checkout / "docs/images/.showcase.json"
    before = path.read_bytes()
    text = before.decode("utf-8")
    assert text == fp.sidecar_text(json.loads(text))  # sorted keys, the sidecar's own format
    res, code = stamp(brand, checkout, now=T1)
    assert code == 0 and res["result"] == "fresh" and "provenance:fresh-no-write" in res["logs"]
    assert path.read_bytes() == before  # nothing changed: no write, no commit just to bump the time
    target = P.parse_target(SLUG, Resolver(brand))
    doc = json.loads(text)
    again = P.stamp_text(P.stamp_document(brand, target, doc, {}, doc["provenance"]))
    assert again == text


def test_other_changes_bump_last_run_at_but_not_last_changed_at(brand, checkout):
    generate(checkout)
    stamp(brand, checkout, now=T0)
    commit(checkout)
    with (checkout / "README.md").open("a", encoding="utf-8") as fh:
        fh.write("\n")  # the run changed something else in a managed path
    res, _ = stamp(brand, checkout, now=T1)
    prov = res["provenance"]
    assert (prov["last_run_at"], prov["last_changed_at"], prov["run_count"]) == (T1, T0, 2)


def test_a_repository_stamped_before_any_art_is_fresh(brand, checkout):
    res, _ = stamp(brand, checkout, now=T0)
    assert res["status"] == "never" and json.loads((checkout / P.REPO_STAMP).read_text(encoding="utf-8"))["outputs"] == {}
    commit(checkout)
    assert check(brand, checkout)["status"] == "fresh"


def test_regenerated_art_is_a_change(brand, checkout, tmp_path):
    generate(checkout)
    stamp(brand, checkout, now=T0)
    commit(checkout)
    meta = edited_meta(tmp_path, description="Route Northwind support email to the right queue.")
    run_cli("--meta", meta, "--repo-dir", checkout, "card")  # the art follows the new description
    assert "unstamped-generation" in check(brand, checkout, meta=meta)["changed"]
    res, _ = P.stamp_one(SLUG, brand, Resolver(brand), root=checkout, meta_path=str(meta), now=T1)
    assert (res["provenance"]["last_changed_at"], res["provenance"]["run_count"]) == (T1, 2)


def test_generators_keep_the_provenance_block(brand, checkout):
    generate(checkout)
    stamp(brand, checkout, now=T0)
    run_cli("--meta", META, "--repo-dir", checkout, "card")
    assert fp.read_sidecar(checkout / "docs/images")["provenance"]["last_run_at"] == T0


def test_schema_validation(brand, checkout):
    import jsonschema
    jsonschema.Draft202012Validator.check_schema(P.schema())
    generate(checkout)
    res, _ = stamp(brand, checkout)
    good = {"provenance": res["provenance"]}
    assert P.validate(good) == [] and not list(jsonschema.Draft202012Validator(P.schema()).iter_errors(good))
    for bad in ({"run_count": 0}, {"last_run_at": "2026-11-01 10:00"}, {"fingerprint": "x"}, {"extra": 1},
                {"target": {"kind": "fork", "id": "x"}}):
        doc = {"provenance": {**res["provenance"], **bad}}
        assert P.validate(doc), bad
    assert set(res["provenance"]) == set(P.schema()["properties"]["provenance"]["required"])
    assert res["provenance"]["publisher"] == "CompleteTech LLC"
    assert res["provenance"]["skill_url"] == brand.raw["attribution"]["skill_url"]


# ---------------------------------------------------------------------------------------------- writer jobs (remote)
class FakeGh:
    """A recorded `subprocess.run` stand-in for `gh api -X GET` (contents API JSON, 404 for anything else)."""

    def __init__(self, files=None, extra=None):
        self.files, self.extra, self.argv = dict(files or {}), dict(extra or {}), []

    def __call__(self, argv, **kw):
        self.argv.append(list(argv))
        path = argv[-1]
        if path in self.extra:
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.extra[path]), stderr="")
        for (repo, rel), data in self.files.items():
            if path == f"repos/{repo}/contents/{rel}":
                body = {"type": "file", "sha": "b" * 40, "content": base64.b64encode(data).decode()}
                return SimpleNamespace(returncode=0, stdout=json.dumps(body), stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")


def only_gets(calls):
    for argv in calls:
        assert argv[:4] == ["gh", "api", "-X", "GET"], argv
        assert "star" not in argv and "PUT" not in argv


def test_remote_stamp_is_a_writer_job_and_reads_only_with_get(brand, tmp_path):
    meta = json.loads(META.read_text(encoding="utf-8"))
    run = FakeGh(files={(SLUG, "README.md"): ("# x\n\n" + footer.block(brand) + "\n").encode()},
                 extra={f"repos/{SLUG}": {**meta, "full_name": SLUG}})
    gh = P.GH(run=run)
    jobs = tmp_path / "jobs.jsonl"
    res, code = P.stamp_one(SLUG, brand, Resolver(brand), gh=gh, jobs=str(jobs), now=T0)
    assert code == 0 and res["result"] == "stamped" and res["written"] is None
    only_gets(run.argv)
    (job,) = [json.loads(x) for x in jobs.read_text(encoding="utf-8").splitlines()]
    assert {"id", "phase", "kind", "repo", "argv", "note"} <= set(job) and job["kind"] == "provenance"
    assert job["repo"] == SLUG and job["argv"][:5] == ["gh", "api", "-X", "PUT",
                                                       f"repos/{SLUG}/contents/docs/images/.showcase.json"]
    content = next(a for a in job["argv"] if a.startswith("content="))[len("content="):]
    doc = json.loads(base64.b64decode(content))
    assert doc["provenance"]["target"] == {"kind": "repo", "id": SLUG} and doc["outputs"] == {}


def test_attribution_topic_is_off_by_default_and_needs_approval(brand):
    target = P.parse_target(SLUG, Resolver(brand))
    meta = {"visibility": "public", "topics": ["northwind", "python"]}
    job, logs = P.topic_job(brand, target, meta, "provenance-topic")
    assert job["approval_id"] == "provenance-topic" and "names[]=github-showcase-skill" in job["argv"]
    assert "names[]=northwind" in job["argv"]  # authored topics stay, in order
    assert P.topic_job(brand, target, {"visibility": "private", "topics": []}, "x")[0] is None
    full = {"visibility": "public", "topics": [f"t{i}" for i in range(10)]}
    assert P.topic_job(brand, target, full, "x") == (None, ["needs-input:topics-capacity"])
    help_text = run_cli("provenance", "stamp", "--help").stdout
    assert "off by default" in help_text


def test_batch_check_spaces_requests_and_stops_on_a_rate_limit(brand, tmp_path):
    targets = tmp_path / "targets.txt"
    targets.write_text("# estate\nBunsDev/a\nNorthwind-Trading-Co/one\nNorthwind-Trading-Co/two\n", encoding="utf-8")
    sleeps = []

    def run(argv, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="gh: API rate limit exceeded (HTTP 403)")
    gh = P.GH(run=run, sleep=sleeps.append)
    args = SimpleNamespace(from_file=str(targets))
    res, code = P._batch(args, brand, Resolver(brand), gh, None)
    rows = res["targets"]
    assert rows[0]["status"] == "foreign" and rows[1]["logs"] == ["needs-input:gh-rate-limit"]
    assert len(rows) == 2 and code == 4  # stopped instead of hammering the API
    assert gh.delay == 0.25


# ---------------------------------------------------------------------------------------------- the public credit
def test_credit_follows_the_unchanged_decision_18_footer(brand):
    from test_footer import DECISION_18
    assert footer.markup(brand) == DECISION_18.strip()  # byte-identical, decision 18
    block = footer.block(brand)
    assert block.startswith(footer.footer_block(brand) + "\n\n" + footer.CREDIT_START)
    assert block.count("<picture>") == 1  # the footer stays the only <picture>
    assert footer.credit_line(brand) == (
        '<p align="center"><sub>README styled with <a href="https://github.com/CompleteTech-Skills/'
        'github-showcase-skill">github-showcase-skill</a> by CompleteTech LLC</sub></p>')
    assert footer.generated_by(brand) == "<!-- generated-by: github-showcase-skill v=1.0.0 std=ct-std-v1 -->"
    assert footer.check(brand, "# X\n\n" + block + "\n")[0] == "pass"
    assert footer.check(brand, "# X\n\n" + footer.footer_block(brand) + "\n")[0] == "fail:credit-missing"
    drift = block.replace("README styled with", "Styled by")
    assert footer.check(brand, "# X\n\n" + drift + "\n")[0] == "fail:credit-drift"
    older = block.replace("v=1.0.0", "v=0.9.0")
    assert footer.check(brand, "# X\n\n" + older + "\n")[0] == "pass"  # a release never fails every README


def test_old_footer_migrates_in_one_regeneration(brand, make_ctx):
    old = readme.scaffold(make_ctx()).split(footer.CREDIT_START)[0].rstrip() + "\n"
    assert footer.CREDIT_START not in old and footer.check(brand, old)[0] == "fail:credit-missing"
    once = readme.header_only(make_ctx(), old)  # what the Action runs
    assert footer.check(brand, once)[0] == "pass" and once.count(footer.CREDIT_START) == 1
    assert readme.header_only(make_ctx(), once) == once  # idempotent
    up, removed = readme.upgrade(make_ctx(), old)
    assert footer.check(brand, up)[0] == "pass" and up.count(footer.CREDIT_START) == 1
    assert readme.preservation(old, up, removed) == []
    stale = once.replace("v=1.0.0", "v=0.9.0").replace("README styled with", "Styled with")
    again, removed = readme.upgrade(make_ctx(), stale)
    assert footer.check(brand, again)[0] == "pass" and readme.preservation(stale, again, removed) == []


def test_readme_lint_requires_the_credit(brand, make_ctx, tmp_path):
    ctx = make_ctx()
    text = readme.scaffold(ctx)
    p = tmp_path / "README.md"
    p.write_text(text.split(footer.CREDIT_START)[0].rstrip() + "\n", encoding="utf-8")
    assert "D18 footer fail:credit-missing" in readmelint.lint(ctx, p)["fails"]
    p.write_text(text, encoding="utf-8")
    assert not [f for f in readmelint.lint(ctx, p)["fails"] if f.startswith("D18")]


def test_profile_readmes_carry_the_credit(brand):
    from ctshowcase import org as O
    reg = {"orgs": {"Northwind-Trading-Co": {"tier": "T1", "final_repos": [".github"], "profile": {"name": "Northwind"}}}}
    est = O.Estate(brand, Resolver(brand, reg, None))
    res, code = O.profile(est, "Northwind-Trading-Co")
    text = res["readme"]
    assert footer.split_credit(text)[1] is not None and text.count("<picture>") == 1


# ---------------------------------------------------------------------------------------------- the Action
def _action_generate(repo, rt, out):
    import yaml
    step = next(s for s in yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))["runs"]["steps"]
                if s.get("id") == "generate")
    env = dict(os.environ, GITHUB_ACTION_PATH=str(ROOT), RUNNER_TEMP=str(rt), GITHUB_OUTPUT=str(out),
               GITHUB_REPOSITORY=SLUG, SHOWCASE_OUTPUTS="banner,card", SHOWCASE_README="header",
               SHOWCASE_IS_TEMPLATE="false", SHOWCASE_ALLOW_UNMEASURED="false", CI="true", GITHUB_ACTIONS="true",
               PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""))
    return run_bash(step["run"], cwd=repo, env=env)


@pytest.mark.requires_bash
def test_action_writes_the_stamp_in_the_same_single_commit(brand, checkout, tmp_path):
    rt, out = tmp_path / "rt", tmp_path / "gh_out"
    rt.mkdir()
    out.write_text("", encoding="utf-8")
    shutil.copy(META, rt / "meta.json")
    p = _action_generate(checkout, rt, out)
    assert p.returncode == 0, p.stdout + p.stderr
    commit_sh = (ROOT / "scripts" / "action_commit.sh").read_text(encoding="utf-8")
    env = dict(os.environ, SHOWCASE_DRY_RUN="1", PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"])
    head = git(checkout, "rev-parse", "HEAD").stdout.strip()
    c = run_bash(commit_sh, "docs: regenerate [skip ci]", "fail", cwd=checkout, env=env)
    assert c.returncode == 0, c.stdout + c.stderr
    assert git(checkout, "rev-list", "--count", f"{head}..HEAD").stdout.strip() == "1"  # one commit
    files = git(checkout, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert "docs/images/.showcase.json" in files and "docs/images/banner.png" in files
    side = json.loads(git(checkout, "show", "HEAD:docs/images/.showcase.json").stdout)
    assert side["provenance"]["run_count"] == 1 and side["provenance"]["target"]["id"] == SLUG
    # A second run that changes nothing writes nothing: no commit just to bump the time.
    p = _action_generate(checkout, rt, out)
    assert p.returncode == 0 and '"result": "fresh"' in p.stdout
    c = run_bash(commit_sh, "docs: regenerate [skip ci]", "fail", cwd=checkout, env=env)
    assert git(checkout, "rev-list", "--count", f"{head}..HEAD").stdout.strip() == "1", c.stdout
    state = ledger.load()
    assert state["completed_runs"] == 0  # CI never counts toward the operator's ledger


# ---------------------------------------------------------------------------------------------- the star nudge
class StarGh:
    def __init__(self, outcome):
        self.outcome, self.argv = outcome, []

    def __call__(self, argv, **kw):
        self.argv.append(list(argv))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        rc, out, err = self.outcome
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


STARRED = (0, "HTTP/2.0 204 No Content\r\nServer: GitHub.com\r\n\r\n", "")
NOT_STARRED = (1, "HTTP/2.0 404 Not Found\r\n\r\n{\"message\":\"Not Found\"}", "gh: Not Found (HTTP 404)")


def nudge(brand, d, gh, *, env=None, tty=True, fmt="text", **kw):
    stream = io.StringIO()
    r = ledger.record_run(brand, fresh=False, fmt=fmt, env=env or {}, isatty=lambda: tty, run=gh, directory=d,
                          stream=stream, **kw)
    return r, stream.getvalue()


def never_writes(gh):
    for argv in gh.argv:
        assert argv[:4] == ["gh", "api", "-X", "GET"] and argv[-1].startswith("user/starred/"), argv
        assert "repo" not in argv[:3] and "PUT" not in argv and "star" not in argv[1:3]


def test_below_the_threshold_nothing_is_checked(brand, tmp_path):
    gh = StarGh(NOT_STARRED)
    for _ in range(ledger.STAR_THRESHOLD - 1):
        r, line = nudge(brand, tmp_path, gh)
        assert r["counted"] and not line
    assert gh.argv == [] and ledger.load(tmp_path)["completed_runs"] == ledger.STAR_THRESHOLD - 1


def test_not_starred_asks_once_then_every_ten_runs(brand, tmp_path):
    gh = StarGh(NOT_STARRED)
    lines = [nudge(brand, tmp_path, gh)[1] for _ in range(ledger.STAR_THRESHOLD + 2 * ledger.STAR_REASK)]
    asked = [i + 1 for i, line in enumerate(lines) if line]
    assert asked == [5, 15, 25]
    assert "gh repo star CompleteTech-Skills/github-showcase-skill" in lines[4]
    assert "https://github.com/CompleteTech-Skills/github-showcase-skill" in lines[4]
    never_writes(gh)


def test_starred_is_recorded_and_never_asked_again(brand, tmp_path):
    gh = StarGh(STARRED)
    for _ in range(ledger.STAR_THRESHOLD):
        r, line = nudge(brand, tmp_path, gh)
    assert r["star"] == "starred" and not line and len(gh.argv) == 1
    for _ in range(30):
        assert not nudge(brand, tmp_path, gh)[1]
    assert len(gh.argv) == 1  # never checked again
    never_writes(gh)


def test_declined_is_never_asked_again(brand, tmp_path):
    gh = StarGh(NOT_STARRED)
    for _ in range(ledger.STAR_THRESHOLD):
        nudge(brand, tmp_path, gh)
    ledger.decline(tmp_path)
    calls = len(gh.argv)
    assert not any(nudge(brand, tmp_path, gh)[1] for _ in range(40)) and len(gh.argv) == calls


@pytest.mark.parametrize("outcome", [
    FileNotFoundError("gh"),                                                     # gh missing
    (4, "", "To get started with GitHub CLI, please run:  gh auth login"),      # unauthenticated
    (1, "", "error connecting to api.github.com"),                              # offline
    (1, "HTTP/2.0 401 Unauthorized\r\n\r\n", "gh: Bad credentials (HTTP 401)"),
    (1, "HTTP/2.0 502 Bad Gateway\r\n\r\n", "gh: HTTP 502"),
])
def test_gh_errors_stay_silent_and_never_mean_not_starred(brand, tmp_path, outcome):
    gh = StarGh(outcome)
    for _ in range(ledger.STAR_THRESHOLD):
        r, line = nudge(brand, tmp_path, gh)
    assert not line and r["star"] == "unknown" and ledger.load(tmp_path)["star"]["status"] == "unknown"


@pytest.mark.parametrize("env,tty,fmt,kw", [
    ({"CI": "true"}, True, "text", {}),
    ({"GITHUB_ACTIONS": "true"}, True, "text", {}),
    ({}, False, "text", {}),                         # no TTY
    ({}, True, "json", {}),                          # --format json
    ({}, True, "text", {"no_prompt": True}),         # --no-star-prompt
    ({"SHOWCASE_NO_STAR_PROMPT": "1"}, True, "text", {}),
    ({}, True, "text", {"quiet": True}),
])
def test_silent_contexts_never_prompt(brand, tmp_path, env, tty, fmt, kw):
    gh = StarGh(NOT_STARRED)
    for _ in range(ledger.STAR_THRESHOLD + 1):
        r, line = nudge(brand, tmp_path, gh, env=env, tty=tty, fmt=fmt, **kw)
        assert not line
    assert gh.argv == []
    if "CI" in env or "GITHUB_ACTIONS" in env:
        assert ledger.load(tmp_path)["completed_runs"] == 0  # CI never counts
    else:
        assert ledger.load(tmp_path)["completed_runs"] == ledger.STAR_THRESHOLD + 1


def test_an_agent_can_relay_the_line_without_a_tty(brand, tmp_path):
    gh = StarGh(NOT_STARRED)
    for _ in range(ledger.STAR_THRESHOLD):
        r, line = nudge(brand, tmp_path, gh, env={"SHOWCASE_STAR_PROMPT": "1"}, tty=False)
    assert line and r["asked"]


def test_ledger_location_and_contents(tmp_path):
    assert ledger.state_dir({"SHOWCASE_STATE_DIR": str(tmp_path)}) == tmp_path
    assert ledger.state_dir({"APPDATA": "C:/AppData"}, "win32").as_posix() == "C:/AppData/github-showcase-skill"
    assert ledger.state_dir({"XDG_CONFIG_HOME": "/x"}, "linux").as_posix() == "/x/github-showcase-skill"
    ledger.save(ledger.empty(), tmp_path)
    data = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert set(data) == {"completed_runs", "fresh_runs", "star"}  # no target names, nothing else


def test_only_a_successful_stamp_counts(brand, checkout):
    d = os.environ["SHOWCASE_STATE_DIR"]
    run_cli("--meta", META, "--repo-dir", checkout, "provenance", "check", SLUG, "--offline")
    run_cli("--meta", META, "--repo-dir", checkout, "doctor")
    generate(checkout)
    assert ledger.load(ledger.state_dir({"SHOWCASE_STATE_DIR": d}))["completed_runs"] == 0
    p = run_cli("--meta", META, "--repo-dir", checkout, "provenance", "stamp", SLUG, "--offline")
    assert p.returncode == 0, p.stdout + p.stderr
    p = run_cli("--meta", META, "--repo-dir", checkout, "provenance", "stamp", "BunsDev/x", "--offline")
    assert p.returncode == 2
    assert ledger.load(ledger.state_dir({"SHOWCASE_STATE_DIR": d}))["completed_runs"] == 1


def test_the_skill_never_stars_or_writes_to_github():
    src = "\n".join((ROOT / "scripts" / "ctshowcase" / n).read_text(encoding="utf-8") for n in ("ledger.py", "provenance.py"))
    assert '"repo", "star"' not in src and "'repo', 'star'" not in src
    assert '"-X", "GET"' in src
    for line in src.splitlines():
        if '"-X", "PUT"' in line:  # only inside writer-job argv that the writer runs after approval
            assert "argv = [" in line, line
