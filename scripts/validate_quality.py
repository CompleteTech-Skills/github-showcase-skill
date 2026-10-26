#!/usr/bin/env python3
"""Validate lint, parser, diagram, showcase render/lint, and ClawHub bundle gates (spec A8.2)."""

from __future__ import annotations

import argparse
import os
import configparser
import fnmatch
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

try:
    import yaml
except ImportError:  # pragma: no cover - reported clearly at runtime
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "env", "ENV", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
URL_SAFE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".ttf", ".otf", ".woff", ".woff2"}
TEXT_SUFFIXES = {
    "", ".css", ".cfg", ".csv", ".gitignore", ".gitattributes", ".html", ".ini", ".j2", ".js", ".json",
    ".graphql", ".md", ".mmd", ".ps1", ".py", ".sh", ".svg", ".toml", ".tsv", ".txt", ".yaml", ".yml",
}
SPECIAL_TEXT_FILES = {"LICENSE", "README", "SKILL.md", "QUALITY.md", "CLAW_HUB_PUBLISHING.md", ".clawhubignore"}
DEFAULT_CLAWHUBIGNORE_PATTERNS = [
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.pdf", "*.docx", "*.ipynb", "*.ttf", "*.otf", "*.woff", "*.woff2",
    "preview/", "output/", "__pycache__/", "*.py[cod]", "*$py.class", ".mypy_cache/", ".pytest_cache/", ".ruff_cache/",
    ".venv/", "venv/", "env/", "ENV/", ".env", ".env.*", "secrets.json", "*_secret.ini", "*_local.ini", "*.tmp",
    ".DS_Store", "Thumbs.db", "desktop.ini",
]


def iter_files(*suffixes: str) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix in suffixes:
            files.append(path)
    return sorted(files)


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def run_ruff() -> None:
    if shutil.which("ruff"):
        run(["ruff", "check", "."])
        return
    raise RuntimeError("ruff is required for quality validation")


def compile_python() -> None:
    for path in iter_files(".py"):
        py_compile.compile(str(path), doraise=True)
    print("python compile ok")


def parse_structured_files() -> None:
    yaml_files = iter_files(".yaml", ".yml")
    yaml_module = cast(Any, yaml)
    if yaml_files and yaml_module is None:
        raise RuntimeError("PyYAML is required to parse YAML files")
    for path in yaml_files:
        yaml_module.safe_load(path.read_text(encoding="utf-8"))
    for path in iter_files(".json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in iter_files(".ini"):
        parser = configparser.RawConfigParser()
        with path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    print("structured files ok")


def mermaid_command() -> list[str] | None:
    if shutil.which("mmdc"):
        return ["mmdc"]
    return None


def mermaid_puppeteer_config(out_dir: Path) -> Path:
    config_path = out_dir / "puppeteer-config.json"
    config_path.write_text(
        json.dumps({"args": ["--no-sandbox", "--disable-setuid-sandbox"]}),
        encoding="utf-8",
    )
    return config_path


def validate_mermaid(skip: bool) -> None:
    diagrams = iter_files(".mmd")
    if not diagrams:
        print("mermaid skipped: no .mmd files")
        return
    cmd = mermaid_command()
    if skip or cmd is None:
        reason = "requested" if skip else "mmdc not available"
        print(f"mermaid skipped: {reason}")
        return
    with tempfile.TemporaryDirectory(prefix="skill-mermaid-") as tmp:
        out_dir = Path(tmp)
        puppeteer_config = mermaid_puppeteer_config(out_dir)
        for index, path in enumerate(diagrams, start=1):
            run([
                *cmd,
                "-i", str(path),
                "-o", str(out_dir / f"diagram-{index}.svg"),
                "-b", "white",
                "-p", str(puppeteer_config),
            ])
    print("mermaid ok")


SHOWCASE = [sys.executable, str(ROOT / "scripts" / "showcase.py")]
SUBCOMMANDS = ["banner", "card", "org-banner", "org-tile", "intro", "footer", "readme", "describe", "topics",
               "labels", "meta", "fingerprint", "fonts", "lint", "contact-sheet", "doctor", "enterprise", "config",
               "org", "project", "content", "new", "adopt"]
# hidden, deprecated aliases: still parse (`--help` works) but are not listed or documented as commands
DEPRECATED_ALIASES = {"social-preview": "content social"}
# the command-group contract other workstreams call by name (org/project/enterprise/content); every action is documented
GROUP_ACTIONS = {"org": ("profile", "about", "pins", "labels", "health", "doctor"),
                 "project": ("capture-query", "normalize", "copy-plan", "readme", "lint", "estate-plan"),
                 "enterprise": ("snapshot-query", "doctor", "plan", "discover", "snapshot", "seat-check", "diff"),
                 "content": ("social", "icon", "links", "linguist", "actions", "images", "sidebar")}
# Checks specific to this package. The family's scripts/validate_package.py is a shared, drift-audited file and stays
# byte-identical to its siblings; everything this package needs beyond it lives here (review A8).
PACKAGE_FILES = ("action.yml", "references/brand.yaml", "references/standard/labels.yml", "docs/images/banner.png",
                 "docs/images/card.svg", "scripts/action_commit.sh", "scripts/action_prepare.py")
LOGO_SHA256 = {  # STANDARD §9.2 brand pair (R9)
    "assets/logo.png": "a5c3c4ef55336ed4b883d3bc3bb6e1e942b836469bd2b2933bc8cc230b321621",
    "assets/logo-dark.png": "0dc00c0e5159518ff1d552b7052293b4e545ddd35be489e6d114e3ea64db27ec",
}
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
SECTION_6_5_SHA256 = "1a081fd129b7f58c369cd83d1ee35848a6fbfd9970b5f8ce781501c3d7d14c40"


def showcase(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    cmd = [*SHOWCASE, *args]
    print("$", " ".join(cmd[1:]))
    return subprocess.run(cmd, cwd=ROOT, check=check, capture_output=capture, text=True)


def gate_help() -> None:
    top = showcase("--help").stdout
    for sub in SUBCOMMANDS:
        if sub not in top:
            raise RuntimeError(f"showcase.py --help does not list {sub}")
        showcase(sub, "--help")
    for action in GROUP_ACTIONS["content"]:
        showcase("content", action, "--help")
    for alias in DEPRECATED_ALIASES:
        showcase(alias, "--help")
        if re.search(rf"^\s+{re.escape(alias)}\s", top, re.M):
            raise RuntimeError(f"showcase.py --help lists the deprecated alias {alias}")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    ref = skill[skill.index("## Command Reference"):]
    for sub in SUBCOMMANDS:
        if not re.search(rf"^{re.escape(sub)}\b", ref, re.M):
            raise RuntimeError(f"SKILL.md Command Reference does not document {sub}")
    for group, actions in GROUP_ACTIONS.items():
        group_help = showcase(group, "--help").stdout
        for action in actions:
            if action not in group_help:
                raise RuntimeError(f"showcase.py {group} --help does not offer {action}")
            if not re.search(rf"^{group} [^\n]*\b{re.escape(action)}\b", ref, re.M):
                raise RuntimeError(f"SKILL.md Command Reference does not document {group} {action}")
    print("help ok")


def gate_config() -> None:
    showcase("config")
    print("brand.yaml schema and lock ok")


def gate_no_hex_in_scripts() -> None:
    for path in iter_files(".py", ".sh"):
        rel = path.relative_to(ROOT).as_posix()
        if not rel.startswith("scripts/") or rel.endswith("validate_quality.py"):
            continue
        m = HEX_RE.search(path.read_text(encoding="utf-8"))
        if m:
            raise RuntimeError(f"hex colour literal {m.group(0)} in {rel}; colours belong in references/brand.yaml")
    print("no hex literals in scripts ok")


def gate_fonts() -> None:
    showcase("fonts", "--check")
    for ttf in (ROOT / "assets" / "fonts").glob("*.ttf"):
        family = ttf.stem.split("-")[0]
        if not (ttf.parent / f"{family}-OFL.txt").is_file():
            raise RuntimeError(f"missing {family}-OFL.txt beside {ttf.name}")
    print("fonts ok")


def gate_render_examples() -> None:
    """Render every examples/meta fixture twice into a temp dir; lint and compare sha256 (determinism)."""
    import hashlib
    metas = sorted((ROOT / "examples" / "meta").glob("*.json"))
    with tempfile.TemporaryDirectory(prefix="showcase-quality-") as tmp:
        t = Path(tmp)
        for meta in metas:
            for run in ("a", "b"):
                for kind, ext in (("banner", "png"), ("card", "svg")):
                    out = t / run / f"{meta.stem}-{kind}.{ext}"
                    p = showcase("--meta", str(meta), "--no-repo-dir", kind, "--out", str(out), check=False)
                    if p.returncode not in (0, 3, 4):
                        raise RuntimeError(f"{kind} {meta.name} exited {p.returncode}: {p.stdout}{p.stderr}")
            for kind, ext in (("banner", "png"), ("card", "svg")):
                a, b = t / "a" / f"{meta.stem}-{kind}.{ext}", t / "b" / f"{meta.stem}-{kind}.{ext}"
                if a.exists() != b.exists() or (a.exists() and hashlib.sha256(a.read_bytes()).digest() != hashlib.sha256(b.read_bytes()).digest()):
                    raise RuntimeError(f"non-deterministic {kind} for {meta.name}")
                if a.exists():
                    if kind == "card":
                        showcase("lint", "svg", "--kind", "card", str(a))
                    else:
                        showcase("lint", "banner", str(a))
        showcase("org-tile", "--org", "CompleteTech-Skills", "--out", str(t / "tile.svg"))
        showcase("lint", "svg", "--kind", "tile", str(t / "tile.svg"))
        showcase("intro", "--profile", "CompleteDotTech", "--out", str(t / "intro.svg"))
        showcase("lint", "svg", "--kind", "intro", str(t / "intro.svg"))
    print(f"render gates ok ({len(metas)} fixtures, rendered twice)")


def gate_package_extras() -> None:
    import hashlib
    sys.path.insert(0, str(ROOT / "scripts"))
    from ctshowcase.pnglint import lint_banner, validate_png
    missing = [p for p in PACKAGE_FILES if not (ROOT / p).is_file()]
    if missing:
        raise RuntimeError(f"missing package files: {missing}")
    for png in ("assets/logo.png", "assets/logo-dark.png", "docs/images/banner.png"):
        validate_png((ROOT / png).read_bytes())
    for png, digest in LOGO_SHA256.items():
        if hashlib.sha256((ROOT / png).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"{png} is not byte-identical to the brand file (R9)")
    if lint_banner(ROOT / "docs" / "images" / "banner.png")["result"] != "PASS":
        raise RuntimeError("docs/images/banner.png fails lint banner")
    if "docs/images/banner.png" not in (ROOT / "README.md").read_text(encoding="utf-8"):
        raise RuntimeError("README.md must open with the decision 13 hero banner (docs/images/banner.png)")
    print("package extras ok (logo pair, hero banner, Action files)")


def gate_labels() -> None:
    import hashlib
    out = showcase("labels", "--emit-yml").stdout
    if hashlib.sha256(out.encode()).hexdigest() != SECTION_6_5_SHA256:
        raise RuntimeError("labels --emit-yml differs from STANDARD §6.5")
    print("labels.yml ok")


def gate_action() -> None:
    yaml_module = cast(Any, yaml)
    action = yaml_module.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    inputs = set((action.get("inputs") or {}).keys())
    want = {"token", "outputs", "readme", "commit", "commit-message", "on-protected", "force", "python-version"}
    if not want <= inputs:
        raise RuntimeError(f"action.yml inputs missing: {sorted(want - inputs)}")
    if set((action.get("outputs") or {}).keys()) < {"changed", "fingerprint"}:
        raise RuntimeError("action.yml outputs must include changed and fingerprint")
    if (action.get("runs") or {}).get("using") != "composite":
        raise RuntimeError("action.yml must be a composite action")
    print("action.yml ok")


def gate_privacy() -> None:
    """Fixtures are public or synthetic Northwind; optional hashed deny-list from the orchestrator."""
    import hashlib
    for folder in (ROOT / "tests" / "fixtures" / "meta", ROOT / "examples" / "meta", ROOT / "examples" / "estate" / "meta"):
        for path in sorted(folder.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("visibility", "public") != "public" and data.get("owner") != "Northwind-Trading-Co":
                raise RuntimeError(f"private metadata in fixture {path.relative_to(ROOT)}")
    deny = os.environ.get("SHOWCASE_PRIVATE_DENYLIST")
    if not deny or not Path(deny).is_file():
        print("privacy ok (deny-list check skipped: SHOWCASE_PRIVATE_DENYLIST not set)")
        return
    hashes = {ln.strip() for ln in Path(deny).read_text(encoding="utf-8").splitlines() if ln.strip()}
    for path in iter_files(*TEXT_SUFFIXES - {""}):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", text):
            if hashlib.sha256(m.group(0).lower().encode()).hexdigest() in hashes:
                raise RuntimeError(f"private owner/repo referenced in {path.relative_to(ROOT)}")
    print("privacy ok")


def gate_dogfood_readme() -> None:
    meta = ROOT / "examples" / "meta" / "github-showcase-skill.json"
    p = showcase("--meta", str(meta), "--repo-dir", str(ROOT), "lint", "readme", str(ROOT / "README.md"), check=False)
    print(p.stdout.strip())
    if p.returncode:
        raise RuntimeError("README.md fails lint readme")
    showcase("footer", "--check", str(ROOT / "README.md"))
    print("dogfood README ok")


def run_pyright() -> None:
    if not (ROOT / "pyrightconfig.json").exists():
        print("pyright skipped: no pyrightconfig.json")
        return
    if shutil.which("pyright"):
        run(["pyright"])
        return
    raise RuntimeError("pyrightconfig.json exists, but pyright is unavailable")


def frontmatter() -> dict[str, Any]:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        raise RuntimeError("SKILL.md must start with YAML frontmatter")
    yaml_module = cast(Any, yaml)
    if yaml_module is None:
        raise RuntimeError("PyYAML is required to parse SKILL.md frontmatter")
    data = yaml_module.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        raise RuntimeError("SKILL.md frontmatter must be a mapping")
    return data


def ignore_patterns() -> list[str]:
    ignore_file = ROOT / ".clawhubignore"
    if not ignore_file.exists():
        if (ROOT / ".git").exists():
            raise RuntimeError(".clawhubignore is required for ClawHub publishing")
        print("clawhub ignore defaults used: .clawhubignore is not present in this installed package")
        return DEFAULT_CLAWHUBIGNORE_PATTERNS.copy()
    patterns = []
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def ignored(rel: str, patterns: list[str]) -> bool:
    rel = rel.replace("\\", "/")
    for pattern in patterns:
        negated = pattern.startswith("!")
        candidate = pattern[1:] if negated else pattern
        if candidate.endswith("/"):
            matched = rel == candidate[:-1] or rel.startswith(candidate)
        elif "/" in candidate:
            matched = fnmatch.fnmatch(rel, candidate)
        else:
            matched = fnmatch.fnmatch(Path(rel).name, candidate)
        if matched:
            return not negated
    return False


def publish_candidate_files(patterns: list[str]) -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in Path(rel).parts):
            continue
        if ignored(rel, patterns):
            continue
        files.append(path)
    return sorted(files)


def package_name(spec: str) -> str:
    return re.split(r"[<>=!~]", spec, maxsplit=1)[0].strip().lower()


def assert_dependency(openclaw: dict[str, Any], package: str) -> None:
    installs = openclaw.get("install") or []
    packages = {package_name(str(item.get("package", ""))) for item in installs if isinstance(item, dict)}
    if package.lower() not in packages:
        raise RuntimeError(f"metadata.openclaw.install must declare {package}")


def validate_clawhub_bundle() -> None:
    data = frontmatter()
    name = data.get("name")
    version = data.get("version")
    metadata = data.get("metadata") or {}
    openclaw = metadata.get("openclaw") or {}
    for field in ["name", "description", "version"]:
        if not data.get(field):
            raise RuntimeError(f"SKILL.md frontmatter missing {field}")
    if not URL_SAFE_RE.fullmatch(str(name)):
        raise RuntimeError(f"skill name is not a URL-safe ClawHub slug: {name}")
    if not SEMVER_RE.fullmatch(str(version)):
        raise RuntimeError(f"version is not semver: {version}")
    if openclaw.get("skillKey") != name:
        raise RuntimeError("metadata.openclaw.skillKey must match name")
    homepage = openclaw.get("homepage")
    if not homepage or not str(homepage).startswith("https://github.com/CompleteTech-Skills/"):
        raise RuntimeError("metadata.openclaw.homepage must point to the CompleteTech GitHub repo")
    requires = openclaw.get("requires") or {}
    bins = requires.get("bins") or []
    if list(ROOT.glob("*.py")) or list((ROOT / "scripts").glob("*.py")):
        if "python3" not in bins:
            raise RuntimeError("Python-backed skills must declare requires.bins: python3")
    py_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in iter_files(".py"))
    for module, package in (("fontTools", "fonttools"), ("uharfbuzz", "uharfbuzz"), ("PIL", "pillow")):
        if re.search(rf"(?m)^\s*(?:from|import)\s+{module}\b", py_text):
            assert_dependency(openclaw, package)
    pins = {package_name(x): x.strip() for x in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.startswith("#")}
    for item in openclaw.get("install") or []:
        spec = str(item.get("package", ""))
        if pins.get(package_name(spec)) != spec:
            raise RuntimeError(f"metadata.openclaw.install {spec} does not match requirements.txt")
    if re.search(r"(?m)^\s*import\s+yaml\b", py_text):
        assert_dependency(openclaw, "pyyaml")

    patterns = ignore_patterns()
    for required_pattern in ["*.png", "*.pdf", "*.docx", "*.ttf", "preview/", "output/", ".env", "*.tmp"]:
        if required_pattern not in patterns:
            raise RuntimeError(f".clawhubignore missing required pattern: {required_pattern}")
    candidate_files = publish_candidate_files(patterns)
    for path in candidate_files:
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in BINARY_SUFFIXES:
            raise RuntimeError(f"binary file would be included in ClawHub bundle: {rel}")
        if path.name in SPECIAL_TEXT_FILES or path.suffix.lower() in TEXT_SUFFIXES:
            continue
        raise RuntimeError(f"non-text or unknown file would be included in ClawHub bundle: {rel}")
    license_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if "per-skill pricing" in license_text.lower() or "paid skill" in license_text.lower():
        raise RuntimeError("SKILL.md appears to contain unsupported ClawHub pricing language")
    if not (ROOT / "CLAW_HUB_PUBLISHING.md").exists():
        raise RuntimeError("CLAW_HUB_PUBLISHING.md is required")
    print(f"clawhub bundle ok ({len(candidate_files)} text files)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-mermaid", action="store_true", help="Skip Mermaid render validation when local tooling is unavailable.")
    parser.add_argument("--skip-dogfood", action="store_true", help="Skip the README dogfood lint (while the README is drafted).")
    args = parser.parse_args()

    compile_python()
    run_ruff()
    parse_structured_files()
    validate_mermaid(args.skip_mermaid)
    gate_help()
    gate_config()
    gate_no_hex_in_scripts()
    gate_fonts()
    gate_package_extras()
    gate_labels()
    gate_action()
    gate_privacy()
    gate_render_examples()
    if not args.skip_dogfood:
        gate_dogfood_readme()
    run_pyright()
    validate_clawhub_bundle()
    print("quality validation ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
