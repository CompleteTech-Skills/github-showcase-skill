"""Package files and metadata contract (stdlib only; runs under unittest too)."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["SKILL.md", "CHANGELOG.md", "AGENTS.md", "README.md", "LICENSE", "BRAND_ASSETS.md", "BRANDING.md", "ONBOARDING.md",
            "CONTRIBUTING.md", "QUALITY.md", "CLAW_HUB_PUBLISHING.md", "action.yml", "agents/openai.yaml",
            "skill-package.json", "requirements.txt", "pyproject.toml", "scripts/showcase.py", "scripts/validate_package.py",
            "scripts/validate_quality.py", "references/brand.yaml", "references/brand.lock.json", "references/brand.schema.json",
            "references/repo-config.schema.json", "references/meta.schema.json", "references/standard/labels.yml",
            "references/standard/topics.yaml", "references/standard/types.yaml", "references/standard/descriptions.yaml",
            "references/standard/readme-variants.yaml", "references/standard/naming.yaml",
            "references/standard/standard.lock.json", "assets/fonts/FONTS.json", "docs/images/banner.png",
            "docs/images/card.svg", "docs/images/.showcase.json"]


def frontmatter():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


class PackageFiles(unittest.TestCase):
    def test_required_files(self):
        missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
        self.assertEqual(missing, [])

    def test_frontmatter_keys(self):
        fm = frontmatter()
        for key in ("name: github-showcase-skill", "description:", "version:", "skillKey: github-showcase-skill",
                    "homepage: https://github.com/CompleteTech-Skills/github-showcase-skill"):
            self.assertIn(key, fm)
        v = re.search(r"(?m)^version:\s*(\S+)", fm).group(1)
        self.assertRegex(v, r"^\d+\.\d+\.\d+$")

    def test_install_pins_match_requirements(self):
        pins = sorted(ln.strip() for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
                      if ln.strip() and not ln.startswith("#"))
        declared = sorted(re.findall(r"(?m)^\s+package:\s*(\S+)", frontmatter()))
        self.assertEqual(pins, declared)

    def test_openai_yaml(self):
        text = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        for key in ("display_name:", "short_description:", "default_prompt:", "allow_implicit_invocation: true"):
            self.assertIn(key, text)
        self.assertIn("$github-showcase-skill", text)

    def test_manifest(self):
        m = json.loads((ROOT / "skill-package.json").read_text(encoding="utf-8"))
        # the package lives in CompleteTech-Skills, as SKILL.md's homepage, approved create-001 and the template Action say;
        # the family validator accepts CompleteTech-Skills/<name> (and still CompleteTech-LLC/<name> for older siblings)
        self.assertEqual(m["repository"], "CompleteTech-Skills/github-showcase-skill")
        self.assertEqual(m["kind"], "catalog-renderer")
        for p in m["entrypoints"] + m["example_inputs"]:
            self.assertTrue((ROOT / p).is_file(), p)

    def test_every_ttf_has_ofl(self):
        for ttf in (ROOT / "assets/fonts").glob("*.ttf"):
            self.assertTrue((ttf.parent / f"{ttf.stem.split('-')[0]}-OFL.txt").is_file(), ttf.name)


if __name__ == "__main__":
    unittest.main()


def test_quality_gate_requires_changelog_entry_for_version(tmp_path):
    # the shared family validator stays byte-identical to the siblings', so the CHANGELOG check lives in
    # validate_quality.py (AGENTS.md); the package contract still passes on a full copy of this checkout
    import importlib.util
    import shutil
    import sys

    import pytest
    sys.path.insert(0, str(ROOT / "scripts"))
    import validate_package as V
    spec = importlib.util.spec_from_file_location("validate_quality_changelog", ROOT / "scripts" / "validate_quality.py")
    Q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(Q)
    dst = tmp_path / "pkg"
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "tests", "output", "preview"))
    assert V.validate(dst) == []
    Q.gate_changelog(dst)
    (dst / "CHANGELOG.md").write_text("# Changelog\n\n## 0.9.0\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="CHANGELOG.md"):
        Q.gate_changelog(dst)
    (dst / "CHANGELOG.md").unlink()
    with pytest.raises(RuntimeError, match="CHANGELOG.md"):
        Q.gate_changelog(dst)
