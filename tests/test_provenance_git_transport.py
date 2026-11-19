"""Public synthetic Git transport contract, without feature implementation imports.

Only local Git commands are used. Directory names with spaces exercise argument
preservation, and a direct call to the same installed Git supplies the failure
status oracle. These tests provide runtime evidence only on their executing OS.
"""
from __future__ import annotations

import configparser
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_provenance_contract_independent import Sandbox


@pytest.fixture(params=["fixture", "fixture root with spaces"], ids=["plain", "spaces"])
def transport_box(tmp_path, request):
    root = tmp_path / request.param
    root.mkdir()
    try:
        box = Sandbox(root)
    except (AssertionError, OSError, subprocess.SubprocessError):
        pytest.fail("constructor_completed=False", pytrace=False)
    yield box
    attempted = box.tripwire.exists()
    assert not attempted, {"tripwire_exists": attempted}
    box.no_network()


def run_local(box, executable, *args):
    """Capture status and output without disclosing them in failure diagnostics."""
    try:
        return subprocess.run(
            [*executable, *args], cwd=box.repo, env=box.env,
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.fail("local_process_completed=False", pytrace=False)


def transport(box, *args):
    return run_local(box, [sys.executable, str(box.transport), "git"], *args)


def local_config(box):
    config = configparser.ConfigParser(interpolation=None)
    try:
        with (box.repo / ".git" / "config").open(encoding="utf-8") as stream:
            config.read_file(stream)
    except (OSError, configparser.Error):
        pytest.fail("synthetic_config_read=False", pytrace=False)
    return config


def test_constructor_initializes_git_marker_and_config(transport_box):
    box = transport_box
    marker_exists = (box.repo / ".git").is_dir()
    config_exists = (box.repo / ".git" / "config").is_file()
    assert marker_exists, {"git_marker_exists": marker_exists}
    assert config_exists, {"git_config_exists": config_exists}
    config = local_config(box)
    initialized = config.has_section("core")
    assert initialized, {"git_core_configured": initialized}


def test_constructor_preserves_initial_origin_and_spaced_identity(transport_box):
    box = transport_box
    config = local_config(box)
    expected_origin = "https://github.com/Northwind-Trading-Co/support-triage-agent.git"
    identity_matches = config.get("user", "name", fallback="") == "Synthetic Northwind"
    origin_matches = config.get('remote "origin"', "url", fallback="") == expected_origin
    assert identity_matches, {"spaced_identity_matches": identity_matches}
    assert origin_matches, {"configured_origin_matches": origin_matches}
    result = transport(box, "remote", "get-url", "origin")
    succeeded = result.returncode == 0
    returned_origin_matches = result.stdout.rstrip("\r\n") == expected_origin
    assert succeeded, {"returncode": result.returncode}
    assert returned_origin_matches, {"returned_origin_matches": returned_origin_matches}


def test_set_url_persists_selected_foreign_synthetic_origin(transport_box):
    box = transport_box
    foreign_origin = "https://github.com/Northwind-Other/foreign-transport-fixture.git"
    try:
        box.git("remote", "set-url", "origin", foreign_origin)
    except (AssertionError, OSError, subprocess.SubprocessError):
        pytest.fail("local_set_url_completed=False", pytrace=False)
    configured_origin_matches = local_config(box).get('remote "origin"', "url", fallback="") == foreign_origin
    result = transport(box, "remote", "get-url", "origin")
    succeeded = result.returncode == 0
    returned_origin_matches = result.stdout.rstrip("\r\n") == foreign_origin
    assert configured_origin_matches, {"configured_foreign_origin_matches": configured_origin_matches}
    assert succeeded, {"returncode": result.returncode}
    assert returned_origin_matches, {"returned_foreign_origin_matches": returned_origin_matches}


def test_transport_toplevel_matches_selected_repository(transport_box):
    box = transport_box
    result = transport(box, "rev-parse", "--show-toplevel")
    succeeded = result.returncode == 0
    output_present = bool(result.stdout.rstrip("\r\n"))
    selected_root_matches = output_present and Path(result.stdout.rstrip("\r\n")).resolve() == box.repo.resolve()
    assert succeeded, {"returncode": result.returncode}
    assert selected_root_matches, {"output_present": output_present, "selected_root_matches": selected_root_matches}


def test_transport_propagates_exact_local_git_failure_status(transport_box):
    box = transport_box
    real_git = shutil.which("git")
    installed_git_found = real_git is not None
    assert installed_git_found, {"installed_git_found": installed_git_found}
    # Neither command reads a remote or changes the no-commit repository.
    direct = run_local(box, [real_git], "show", "HEAD:missing")
    routed = transport(box, "show", "HEAD:missing")
    direct_failed = direct.returncode != 0
    routed_failed = routed.returncode != 0
    statuses_match = routed.returncode == direct.returncode
    assert direct_failed, {"direct_returncode": direct.returncode}
    assert routed_failed, {"routed_returncode": routed.returncode}
    assert statuses_match, {"direct_returncode": direct.returncode, "routed_returncode": routed.returncode}
