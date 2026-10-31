"""Shared pytest helpers. Fixtures are public metadata or synthetic Northwind data only (spec A9.1)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
FIX = ROOT / "tests" / "fixtures" / "meta"
EX = ROOT / "examples"
GOLDEN = ROOT.parent / "art" / "golden" / "readme-banner-php2shell-check.png"


def run_cli(*args, cwd=ROOT):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py"), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8")


def find_bash(*, windows=None):
    """Use Git for Windows' shell, never Windows' unrelated WSL bash launcher."""
    if windows is None:
        windows = sys.platform == "win32"
    if not windows:
        return shutil.which("bash")
    git = shutil.which("git")
    if git:
        def bundled_bash(installation):
            for relative in ("bin/bash.exe", "usr/bin/bash.exe"):
                candidate = installation / relative
                if candidate.is_file():
                    return str(candidate)
            return None

        direct = bundled_bash(Path(git).resolve().parent.parent)
        if direct:
            return direct
        # A package-manager shim need not be a symlink. Ask Git where its own
        # binaries live rather than accidentally falling back to WSL's bash.
        try:
            result = subprocess.run([git, "--exec-path"], capture_output=True, text=True,
                                    encoding="utf-8", timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode == 0 and result.stdout.strip():
            for installation in Path(result.stdout.strip()).resolve().parents:
                candidate = bundled_bash(installation)
                if candidate:
                    return candidate
    return None


def run_bash(script, *args, cwd, env=None):
    """Feed shell source through stdin so Windows command-line quoting cannot change it."""
    bash = find_bash()
    if bash is None:
        pytest.skip("requires_bash: install Git for Windows (Windows) or bash (POSIX) to run Action shell tests")
    shell_env = dict(os.environ if env is None else env)
    for key in ("GITHUB_ACTION_PATH", "RUNNER_TEMP", "GITHUB_OUTPUT"):
        if key in shell_env:
            shell_env[key] = Path(shell_env[key]).as_posix()
    return subprocess.run([bash, "-s", "--", *args], input=script, cwd=cwd, env=shell_env,
                          capture_output=True, text=True, encoding="utf-8")


def meta_dict(**kw):
    base = {"owner": "Northwind-Trading-Co", "repo": "support-triage-agent", "description": "Run the Northwind triage agent.",
            "topics": [], "visibility": "public", "language": "Python", "license": "MIT", "labels": []}
    base.update(kw)
    return base


@pytest.fixture(scope="session")
def brand():
    from ctshowcase.config import load_brand
    return load_brand()


@pytest.fixture(scope="session")
def fonts(brand):
    from ctshowcase.typeset import Fonts
    return Fonts(brand)


@pytest.fixture
def make_ctx(brand):
    from ctshowcase.context import RepoContext
    from ctshowcase.meta import normalize

    def _make(repo_dir=None, **kw):
        return RepoContext(brand, normalize(meta_dict(**kw)), repo_dir)
    return _make


@pytest.fixture
def fixture_meta():
    def _load(name):
        return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    return _load


def brand_config(tmp_path, **readme_opts):
    """A copy of references/brand.yaml with review-page README answers changed (q57 nav/pres, q27), for --config."""
    import yaml
    raw = yaml.safe_load((ROOT / "references" / "brand.yaml").read_text(encoding="utf-8"))
    raw.setdefault("readme", {}).update(readme_opts)
    p = tmp_path / "brand-q57.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


@pytest.fixture
def brand_with():
    """Brand objects with README answers changed: brand_with(preserve_banner="unchanged")."""
    import copy
    from ctshowcase.config import Brand, load_brand
    base = load_brand()

    def _make(**readme_opts):
        raw = copy.deepcopy(base.raw)
        raw.setdefault("readme", {}).update(readme_opts)
        return Brand(raw, base.path)
    return _make
