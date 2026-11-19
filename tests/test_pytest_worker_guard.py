"""Real child-process checks for CI's completion boundary; no external hosts."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_suite(tmp_path, *, hook="", failing=False, parallel=True):
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(hook, encoding="utf-8")
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    (tmp_path / "test_b.py").write_text(f"def test_b():\n    assert {not failing!r}\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    runner = tmp_path / "scripts" / "run_ci_tests.py"
    shutil.copy2(ROOT / "scripts" / "run_ci_tests.py", runner)
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    command = [sys.executable, str(runner)]
    if parallel:
        command += ["--report-dir", str(tmp_path / "results")]
    else:
        command += ["--child-report", str(tmp_path / "serial.json")]
    return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=60, check=False)


@pytest.mark.parametrize("parallel", [False, True])
def test_clean_completion_succeeds(tmp_path, parallel):
    result = run_suite(tmp_path, parallel=parallel)
    assert result.returncode == 0, result.stdout + result.stderr
    if parallel:
        summary = json.loads((tmp_path / "results" / "summary.json").read_text())
        assert summary["collected"] == 2
        assert sum(batch["stats"]["passed"] for batch in summary["results"]) == 2
        assert all(batch["error"] is None for batch in summary["results"])
    else:
        assert "2 passed" in result.stdout


@pytest.mark.parametrize("parallel", [False, True])
def test_assertion_failure_stays_failed(tmp_path, parallel):
    result = run_suite(tmp_path, failing=True, parallel=parallel)
    assert result.returncode == 1, result.stdout + result.stderr
    if parallel:
        summary = json.loads((tmp_path / "results" / "summary.json").read_text())
        assert sorted(batch["process_exit"] for batch in summary["results"]) == [0, 1]
        assert len([batch for batch in summary["results"] if batch["error"]]) == 1
    else:
        assert "1 failed, 1 passed" in result.stdout


@pytest.mark.parametrize("phase", ["startup", "test", "finish"])
@pytest.mark.parametrize("exit_code", [0, 19])
def test_worker_crash_never_succeeds(tmp_path, phase, exit_code):
    hook_name = {
        "startup": "pytest_sessionstart(session)",
        "test": "pytest_runtest_call(item)",
        "finish": "pytest_sessionfinish(session, exitstatus)",
    }[phase]
    config = "item.config" if phase == "test" else "session.config"
    hook = (
        "import os\n"
        f"def {hook_name}:\n"
        f"    if not {config}.option.collectonly:\n"
        f"        os._exit({exit_code})\n"
    )
    result = run_suite(tmp_path, hook=hook)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAILED or incomplete" in result.stdout
    if phase == "finish":
        assert result.returncode == 1
    summary = json.loads((tmp_path / "results" / "summary.json").read_text())
    assert all(batch["error"] for batch in summary["results"])


@pytest.mark.parametrize("failure", ["exit", "exit0", "exception", "status", "atexit"])
def test_late_cleanup_or_final_status_failure_never_succeeds(tmp_path, failure):
    if failure == "status":
        hook = ("def pytest_sessionfinish(session, exitstatus):\n"
                "    if not session.config.option.collectonly:\n"
                "        session.exitstatus = 1\n")
    elif failure == "atexit":
        hook = ("import atexit, os\n"
                "def pytest_configure(config):\n"
                "    if not config.option.collectonly:\n"
                "        atexit.register(os._exit, 19)\n")
    else:
        action = {"exit": "os._exit(19)", "exit0": "os._exit(0)",
                  "exception": "raise RuntimeError('synthetic cleanup failure')"}[failure]
        hook = ("import os\n"
                "def pytest_unconfigure(config):\n"
                "    if not config.option.collectonly:\n"
                f"        {action}\n")
    result = run_suite(tmp_path, hook=hook)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAILED or incomplete" in result.stdout


def test_changed_batch_collection_is_rejected(tmp_path):
    hook = ("def pytest_collection_modifyitems(config, items):\n"
            "    if not config.option.collectonly:\n"
            "        items.clear()\n"
            "def pytest_sessionfinish(session, exitstatus):\n"
            "    session.exitstatus = 0\n")
    result = run_suite(tmp_path, hook=hook)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "empty or duplicate pytest inventory" in result.stdout


def test_missing_test_completion_is_rejected_even_with_zero_exit(tmp_path):
    hook = ("def pytest_runtestloop(session):\n"
            "    if not session.config.option.collectonly:\n"
            "        return True\n")
    result = run_suite(tmp_path, hook=hook)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "did not complete every assigned test exactly once" in result.stdout


def test_collection_failure_prevents_batch_execution(tmp_path):
    hook = "def pytest_collection_modifyitems(items):\n    raise RuntimeError('synthetic collection failure')\n"
    result = run_suite(tmp_path, hook=hook)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "CI inventory FAILED" in result.stderr
    assert not list((tmp_path / "results").glob("batch-*.json"))


def test_zeroed_exit_status_cannot_hide_a_failed_assertion(tmp_path):
    hook = "def pytest_sessionfinish(session, exitstatus):\n    session.exitstatus = 0\n"
    result = run_suite(tmp_path, hook=hook, failing=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "pytest recorded failing tests or errors" in result.stdout
