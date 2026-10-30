"""A global `--allow-t3` lifts the T3 refusal for every repository command; the default still refuses (exit 2)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]
META = json.loads((ROOT / "examples" / "meta" / "northwind-support-triage-agent.json").read_text(encoding="utf-8"))


def _run(tmp_path, *argv, owner="Pick-Your-AI"):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(dict(META, owner=owner, repo="northwind-synthetic")), encoding="utf-8")
    return subprocess.run([*SHOWCASE, "--meta", str(meta), "--no-repo-dir", *argv], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")


def test_t3_owner_is_refused_without_the_flag(tmp_path):
    for cmd in (["describe"], ["topics"], ["readme"],
                ["banner", "--out", str(tmp_path / "b.png")]):
        r = _run(tmp_path, *cmd)
        assert r.returncode == 2, (cmd, r.stdout, r.stderr)
        assert "co-owner sign-off" in r.stdout + r.stderr or "t3-signoff" in r.stdout + r.stderr


def test_global_flag_lets_repository_commands_run(tmp_path):
    for cmd in (["describe"], ["topics"]):
        r = _run(tmp_path, "--allow-t3", *cmd)
        assert r.returncode != 2, (cmd, r.stdout, r.stderr)
        assert "t3-signoff" not in r.stdout + r.stderr


def test_global_flag_renders_art_for_a_t3_owner(tmp_path):
    out = tmp_path / "banner.png"
    r = _run(tmp_path, "--allow-t3", "banner", "--out", str(out), "--allow-unmeasured", "--allow-few-chips")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out.is_file() and out.stat().st_size > 10_000
    assert "t3-signoff" not in r.stdout + r.stderr


def test_flag_does_not_lift_excluded_owners(tmp_path):
    r = _run(tmp_path, "--allow-t3", "describe", owner="BunsDev")
    assert r.returncode == 2, (r.stdout, r.stderr)


def test_doctor_reports_t3_cells_as_held_only_without_the_flag(tmp_path):
    held = _run(tmp_path, "doctor", "--format", "json")
    assert json.loads(held.stdout)["cells"]["R7"] == "hold", held.stdout
    signed = _run(tmp_path, "--allow-t3", "doctor", "--format", "json")
    assert json.loads(signed.stdout)["cells"]["R7"] != "hold", signed.stdout


def test_signoff_does_not_outlive_the_invocation(tmp_path, capsys):
    """`--allow-t3` holds for one main() call only: a later library call in the same process is refused again."""
    import pytest
    sys.path.insert(0, str(ROOT / "scripts"))
    import showcase
    from ctshowcase.config import load_brand, t3_signed_off
    from ctshowcase.errors import Refused
    assert showcase.main(["--allow-t3", "config"]) in (0, 1)
    capsys.readouterr()
    assert t3_signed_off() is False
    with pytest.raises(Refused):
        load_brand().check_owner("Pick-Your-AI")


def test_signed_off_t3_org_joins_also_in_and_star_lists(brand):
    from ctshowcase.config import set_t3_signed_off
    from ctshowcase.org import _star_held
    from ctshowcase.resolver import Resolver
    est = type("E", (), {"resolver": Resolver(brand, {"orgs": {}}, None)})()
    assert _star_held(est, "Pick-Your-AI") == "t3"
    assert _star_held(est, "Pick-Your-AI", allow_t3=True) is None
    set_t3_signed_off(True)
    try:
        assert _star_held(est, "Pick-Your-AI") is None
        assert _star_held(est, "BunsDev") == "excluded"  # sign-off never lifts an excluded owner
    finally:
        set_t3_signed_off(False)


# Evidence note for reviewers: the seven tests above this line predate the ContextVar change
# (they exist at 2be04ac, before be5cb14) and are regression guards for the CLI contract that
# must keep passing. The five tests from here down are the discriminating ones: run against the
# tree before be5cb14 they fail with ImportError on `reset_t3_signed_off`.


def test_token_reset_restores_each_prior_value():
    """set_t3_signed_off returns a token; reset_t3_signed_off restores exactly the value before that set."""
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off, t3_signed_off
    assert t3_signed_off() is False
    outer = set_t3_signed_off(True)
    inner = set_t3_signed_off(False)
    assert t3_signed_off() is False
    reset_t3_signed_off(inner)
    assert t3_signed_off() is True
    reset_t3_signed_off(outer)
    assert t3_signed_off() is False


def test_sign_off_is_invisible_to_a_separate_context():
    """Sign-off is context-local: code run in a fresh copy of the context (as an embedding host would) stays unsigned."""
    import contextvars
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off, t3_signed_off
    seen = []
    token = set_t3_signed_off(True)
    try:
        assert t3_signed_off() is True
        contextvars.Context().run(lambda: seen.append(t3_signed_off()))
        assert seen == [False]
        contextvars.copy_context().run(lambda: seen.append(t3_signed_off()))
        assert seen == [False, True]
    finally:
        reset_t3_signed_off(token)
    assert t3_signed_off() is False


def test_sign_off_does_not_leak_to_a_thread_started_with_an_empty_context():
    """A thread started while signed off must not see the sign-off on interpreters that do not inherit context."""
    import sys
    import threading
    import pytest
    if getattr(sys.flags, "thread_inherit_context", False):
        pytest.skip("this interpreter's threads inherit the caller's context")
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off, t3_signed_off
    seen = []
    token = set_t3_signed_off(True)
    try:
        worker = threading.Thread(target=lambda: seen.append(t3_signed_off()))
        worker.start()
        worker.join()
    finally:
        reset_t3_signed_off(token)
    assert seen == [False]


def test_main_restores_the_caller_sign_off_value(capsys):
    """main() wraps one call in a token: whatever --allow-t3 set inside it is undone, and the caller's value is kept."""
    import sys
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off, t3_signed_off
    sys.path.insert(0, str(ROOT / "scripts"))
    import showcase
    assert showcase.main(["--allow-t3", "config"]) in (0, 1)
    capsys.readouterr()
    assert t3_signed_off() is False
    token = set_t3_signed_off(True)
    try:
        assert showcase.main(["config"]) in (0, 1)
        capsys.readouterr()
        assert t3_signed_off() is True
    finally:
        reset_t3_signed_off(token)


def test_two_concurrent_threads_have_independent_sign_off_at_the_owner_gate(brand):
    """Acceptance: one thread signed off and one not behave independently; the unsigned one is refused for a T3 owner.

    Each thread sets its own state explicitly, so this also runs where threads inherit the caller's context. The barrier
    makes both threads hold their state at the same time before either calls the gate."""
    import threading
    from ctshowcase.config import reset_t3_signed_off, set_t3_signed_off, t3_signed_off
    from ctshowcase.errors import Refused
    barrier = threading.Barrier(2, timeout=10)
    out: dict[str, tuple] = {}

    def worker(name, signed):
        token = set_t3_signed_off(signed)
        try:
            barrier.wait()  # both states are live at once
            try:
                result = ("passed", brand.check_owner("Pick-Your-AI"))
            except Refused as exc:
                result = ("refused", exc.log)
            barrier.wait()  # neither resets until both have checked
            out[name] = (*result, t3_signed_off())
        finally:
            reset_t3_signed_off(token)

    threads = [threading.Thread(target=worker, args=("signed", True)),
               threading.Thread(target=worker, args=("unsigned", False))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert out["signed"] == ("passed", "t3", True), out
    assert out["unsigned"] == ("refused", "t3-signoff", False), out
    assert t3_signed_off() is False
