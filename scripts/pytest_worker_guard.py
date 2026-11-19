"""Make abnormal xdist worker termination fail CI even after its last test."""

import pytest


_FAILED_WORKERS = pytest.StashKey[list[str]]()


def pytest_configure(config):
    config.stash[_FAILED_WORKERS] = []


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    if error is not None or getattr(node, "workeroutput", {}).get("exitstatus") != 0:
        node.config.stash[_FAILED_WORKERS].append(node.gateway.id)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    yield
    if session.config.stash[_FAILED_WORKERS] and session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    failed = terminalreporter.config.stash[_FAILED_WORKERS]
    if failed:
        terminalreporter.write_sep("=", f"worker guard: {len(failed)} worker exit(s) were not clean")
