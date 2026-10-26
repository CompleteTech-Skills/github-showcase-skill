"""Shared pytest helpers. Fixtures are public metadata or synthetic Northwind data only (spec A9.1)."""
import json
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
                          capture_output=True, text=True)


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
