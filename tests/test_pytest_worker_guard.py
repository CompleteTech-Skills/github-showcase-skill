"""Real child-process checks for CI's worker-exit boundary; no external hosts."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_suite(tmp_path, *, hook="", failing=False, parallel=True):
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(hook, encoding="utf-8")
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    (tmp_path / "test_b.py").write_text(f"def test_b():\n    assert {not failing!r}\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), env.get("PYTHONPATH"))))
    command = [sys.executable, "-m", "pytest", "-p", "scripts.pytest_worker_guard", "-q"]
    if parallel:
        command += ["-p", "xdist.plugin", "-n", "2", "--dist", "loadfile", "--max-worker-restart", "0"]
    return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=60, check=False)


@pytest.mark.parametrize("parallel", [False, True])
def test_clean_completion_succeeds(tmp_path, parallel):
    result = run_suite(tmp_path, parallel=parallel)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
    assert "worker guard:" not in result.stdout


@pytest.mark.parametrize("parallel", [False, True])
def test_assertion_failure_stays_failed(tmp_path, parallel):
    result = run_suite(tmp_path, failing=True, parallel=parallel)
    assert result.returncode == 1, result.stdout + result.stderr
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
        f"    if getattr({config}, 'workerinput', {{}}).get('workerid') == 'gw0':\n"
        f"        os._exit({exit_code})\n"
    )
    result = run_suite(tmp_path, hook=hook)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "worker guard:" in result.stdout
    if phase == "finish":
        assert result.returncode == 1
        assert "2 passed" in result.stdout
