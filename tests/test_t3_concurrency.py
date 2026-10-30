"""T3 sign-off is context-local: concurrent threads and embedding hosts never see each other's `--allow-t3`.

Synthetic data only: the owner 'Pick-Your-AI' is the T3 owner already used by test_allow_t3_global.py. Ordering is
driven by threading.Event and join(timeout=...) only; no time.sleep races.

Status: these are regression guards, not a fix. The fix is commit be5cb14 (ContextVar sign-off), already in the base
efc43c9, so these tests pass on that base. Evidence that they catch the old behaviour: with config.py's sign-off
replaced by a process-wide module global (same public API, same tests), all 5 tests fail (test 1 reports
'allowed' == 'refused'). Reproduced in a scratch copy; the committed config.py is unchanged.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ctshowcase import config  # noqa: E402
from ctshowcase.config import (  # noqa: E402
    load_brand, reset_t3_signed_off, set_t3_signed_off, t3_signed_off,
)
from ctshowcase.errors import Refused  # noqa: E402

OWNER = "Pick-Your-AI"
TIMEOUT = 10


def _check_owner_outcome() -> str:
    """'refused' when the T3 owner is refused in the calling context, 'allowed' otherwise."""
    try:
        load_brand().check_owner(OWNER)
    except Refused as exc:
        assert exc.log == "t3-signoff", exc.log
        return "refused"
    return "allowed"


def test_unsigned_thread_is_refused_while_another_is_signed_off():
    a_signed = threading.Event()
    b_done = threading.Event()
    results: dict = {}
    errors: list[BaseException] = []

    def thread_a():
        try:
            token = set_t3_signed_off(True)
            try:
                results["A_signed_off"] = t3_signed_off()
                assert load_brand().check_owner(OWNER) == "t3"
                a_signed.set()
                assert b_done.wait(TIMEOUT), "thread B never finished"
            finally:
                reset_t3_signed_off(token)
        except BaseException as exc:  # re-raised in the main thread
            errors.append(exc)
            a_signed.set()

    def thread_b():
        try:
            assert a_signed.wait(TIMEOUT), "thread A never signed off"
            results["B"] = _check_owner_outcome()
            results["B_signed_off"] = t3_signed_off()
        except BaseException as exc:  # re-raised in the main thread
            errors.append(exc)
        finally:
            b_done.set()

    a = threading.Thread(target=thread_a, name="signed-off-A")
    b = threading.Thread(target=thread_b, name="unsigned-B")
    a.start()
    b.start()
    a.join(timeout=TIMEOUT)
    b.join(timeout=TIMEOUT)

    assert errors == []
    assert not a.is_alive()
    assert not b.is_alive()
    assert results["B"] == "refused"
    assert results["B_signed_off"] is False
    assert results["A_signed_off"] is True


def test_signoff_in_one_thread_does_not_change_main_thread():
    released = threading.Event()
    signed = threading.Event()
    errors: list[BaseException] = []

    def worker():
        try:
            set_t3_signed_off(True)
            assert t3_signed_off() is True
            signed.set()
            assert released.wait(TIMEOUT), "main thread never released the worker"
        except BaseException as exc:  # re-raised in the main thread
            errors.append(exc)
            signed.set()

    t = threading.Thread(target=worker)
    t.start()
    try:
        assert signed.wait(TIMEOUT), "worker never signed off"
        assert errors == []
        assert t3_signed_off() is False
        try:
            load_brand().check_owner(OWNER)
        except Refused as exc:
            assert exc.log == "t3-signoff"
        else:
            raise AssertionError("main thread must still refuse the T3 owner")
    finally:
        released.set()
        t.join(timeout=TIMEOUT)
    assert not t.is_alive()
    assert errors == []


def test_default_is_unsigned_after_main_returns(capsys):
    import showcase  # scripts/showcase.py, put on sys.path above

    results: dict = {}
    errors: list[BaseException] = []

    assert showcase.main(["--allow-t3", "config"]) in (0, 1)
    capsys.readouterr()
    assert t3_signed_off() is False
    try:
        load_brand().check_owner(OWNER)
    except Refused as exc:
        assert exc.log == "t3-signoff"
    else:
        raise AssertionError("T3 owner must be refused after main() returns")

    def run_in_thread():
        try:
            results["exit"] = showcase.main(["--allow-t3", "config"])
            results["signed_after_main"] = t3_signed_off()
            results["outcome"] = _check_owner_outcome()
        except BaseException as exc:  # re-raised in the main thread
            errors.append(exc)

    t = threading.Thread(target=run_in_thread)
    t.start()
    t.join(timeout=TIMEOUT)
    assert not t.is_alive()
    assert errors == []
    assert results["exit"] in (0, 1)
    assert results["signed_after_main"] is False
    assert results["outcome"] == "refused"
    capsys.readouterr()


def test_concurrent_main_calls_are_independent():
    """Embedding simulation (no concurrent main() calls: stdout is shared): a host sets and resets sign-off in a thread."""
    signed = threading.Event()
    go = threading.Event()
    results: dict = {}
    errors: list[BaseException] = []

    def host():
        try:
            token = set_t3_signed_off(True)
            results["during"] = t3_signed_off()
            signed.set()
            assert go.wait(TIMEOUT), "main thread never released the host"
            reset_t3_signed_off(token)
            results["after_reset"] = t3_signed_off()
        except BaseException as exc:  # re-raised in the main thread
            errors.append(exc)
            signed.set()

    t = threading.Thread(target=host)
    t.start()
    try:
        assert signed.wait(TIMEOUT), "host never signed off"
        assert errors == []
        assert results["during"] is True
        assert t3_signed_off() is False
    finally:
        go.set()
        t.join(timeout=TIMEOUT)
    assert not t.is_alive()
    assert errors == []
    assert results["after_reset"] is False
    assert t3_signed_off() is False


def test_no_module_level_mutable_approval_state():
    text = (ROOT / "scripts" / "ctshowcase" / "config.py").read_text(encoding="utf-8")
    assert "global _T3_SIGNED_OFF" not in text
    assert type(config._T3_SIGNED_OFF).__name__ == "ContextVar"
