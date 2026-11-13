"""Read-only target tooling discovery and explicitly requested, local Prettier formatting."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .errors import NeedsInput, ShowcaseError

FORMAT_CONFIGS = (".prettierrc", ".prettierrc.json", ".prettierrc.yaml", ".prettierrc.yml", ".prettierrc.js",
                  ".prettierrc.cjs", ".prettierrc.mjs", ".prettierrc.toml", "prettier.config.js",
                  "prettier.config.cjs", "prettier.config.mjs", ".editorconfig")
VALIDATOR_NAME = re.compile(r"(?:^|[:_-])(check|lint|test|typecheck|validate|format)(?:$|[:_-])", re.I)


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def discover(repo_dir: Path | None) -> dict:
    """Report declared tooling with source evidence. Never execute a discovered command."""
    if repo_dir is None:
        return {"formatters": [], "validators": [], "status": "needs-input:repo-dir"}
    root = Path(repo_dir)
    package = _json(root / "package.json")
    configs = [name for name in FORMAT_CONFIGS if (root / name).is_file()]
    if "prettier" in package:
        configs.append("package.json#prettier")
    validators = []
    for name, command in _mapping(package.get("scripts")).items():
        if VALIDATOR_NAME.search(name) and isinstance(command, str):
            validators.append({"source": f"package.json#scripts.{name}", "command": command, "status": "not run"})
    for name in ("AGENTS.md", "CONTRIBUTING.md"):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # Only fenced shell blocks: prose is evidence, not executable shell.
        for match in re.finditer(r"^```(?:bash|sh|shell|console)\s*\n(.*?)^```", text, re.M | re.S):
            for line in match.group(1).splitlines():
                command = line.strip().removeprefix("$ ")
                if re.search(r"(?:pytest|unittest|validate|\blint\b|\bcheck\b|typecheck|prettier|ruff)", command):
                    validators.append({"source": name, "command": command, "status": "not run"})
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        import yaml
        for path in sorted(workflows.iterdir()):
            if path.suffix not in (".yml", ".yaml") or not path.is_file():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(data, dict):
                continue
            jobs = data.get("jobs") or {}
            if not isinstance(jobs, dict):
                continue
            for job, details in jobs.items():
                if not isinstance(details, dict):
                    continue
                steps = details.get("steps") or []
                if not isinstance(steps, list):
                    continue
                for step in steps:
                    if isinstance(step, dict) and isinstance(step.get("run"), str):
                        validators.append({"source": f"{path.relative_to(root).as_posix()}#jobs.{job}",
                                           "command": step["run"].strip(), "status": "not run"})
    dependencies = {**_mapping(package.get("dependencies")), **_mapping(package.get("devDependencies"))}
    return {"formatters": configs, "prettier_version": dependencies.get("prettier"),
            "validators": validators, "status": "not run"}


def format_text(repo_dir: Path | None, destination: Path, text: str) -> str:
    """Format one generated text value with the target's exact pinned local Prettier.

    No install, package script, shell, or file write occurs here. The caller writes only
    after its usual safety checks. Calling this function is the explicit opt-in.
    """
    if repo_dir is None:
        raise NeedsInput("formatter", "formatting requires a target checkout")
    root = Path(repo_dir).resolve()
    destination = Path(destination).resolve()
    try:
        relative = destination.relative_to(root)
    except ValueError as error:
        raise ShowcaseError("formatter destination must be inside the target checkout", log="usage") from error
    details = discover(root)
    version = details.get("prettier_version")
    exact = r"\d+\.\d+\.\d+(?:-[\w.-]+)?"
    if not isinstance(version, str):
        raise NeedsInput("formatter", "declare prettier in the target package.json")
    if not re.fullmatch(exact, version):
        for lockname in ("npm-shrinkwrap.json", "package-lock.json"):
            locked = _json(root / lockname)
            pin = _mapping(_mapping(locked.get("packages")).get("node_modules/prettier")).get("version")
            if isinstance(pin, str) and re.fullmatch(exact, pin):
                version = pin
                break
        else:
            raise NeedsInput("formatter", "pin Prettier exactly or supply its npm lockfile")
    package_root = root / "node_modules" / "prettier"
    installed = _json(package_root / "package.json")
    if installed.get("version") != version:
        raise NeedsInput("formatter", "install the target's pinned Prettier before formatting")
    node = shutil.which("node")
    if node is None:
        raise NeedsInput("formatter", "Node.js is required for the target's pinned Prettier")
    binary = installed.get("bin")
    binary = binary.get("prettier") if isinstance(binary, dict) else binary
    if not isinstance(binary, str):
        raise NeedsInput("formatter", "the installed Prettier package has no CLI")
    cli = (package_root / binary).resolve()
    if not cli.is_relative_to(package_root.resolve()) or not cli.is_file():
        raise NeedsInput("formatter", "the installed Prettier CLI is unavailable")
    argv = [node, str(cli), "--stdin-filepath", str(relative)]
    if destination.suffix.lower() == ".svg":
        argv += ["--parser", "html"]
    try:
        result = subprocess.run(argv, cwd=root, input=text,
                                text=True, encoding="utf-8", capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise NeedsInput("formatter", "the target's pinned Prettier could not run") from error
    if result.returncode:
        raise ShowcaseError(f"target Prettier failed: {result.stderr.strip()}", log="formatter-failed")
    return result.stdout
