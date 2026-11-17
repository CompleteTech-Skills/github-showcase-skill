"""Read-only target tooling discovery and explicitly requested, local Prettier formatting."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import CHECK_FAILED, NeedsInput, ShowcaseError

VALIDATOR_NAME = re.compile(r"(?:^|[:_-])(check|contracts|lint|test|typecheck|validate|format|verify)(?:$|[:_-])", re.I)
SCRIPT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_-]*")
VALIDATOR_COMMAND = re.compile(
    r"^(?:(?:uv run |poetry run )?(?:python[\d.]* -m )?(?:pytest|unittest|ruff|prettier|pyright|mypy|eslint)"
    r"|(?:npx |npm exec )prettier"
    r"|(?:python[\d.]* )?(?:\./)?(?:scripts/)?validate[\w.-]*\.py"
    r"|(?:cargo|go|dotnet|npm|pnpm|yarn|bun|make|just)\s+(?:run\s+)?"
    r"(?:test|check|contracts|lint|typecheck|validate|verify|format)(?:[:_-][A-Za-z0-9:_-]+)?)(?=\s|$|[;&|])",
    re.I,
)
DISPLAY_ARGUMENTS = {".", "-q", "-v", "--", "--check", "--write", "--fix", "--quiet", "--verbose", "check", "discover"}


def _display_validator(command: str) -> str | None:
    """Report a command prefix and recognized flags without echoing arbitrary arguments or shell tails."""
    match = VALIDATOR_COMMAND.match(command.strip())
    if not match:
        return None
    command = command.strip()
    display = [match.group()]
    for arg in command[match.end():].split():
        if arg not in DISPLAY_ARGUMENTS:
            break
        display.append(arg)
    return " ".join(display)


def same_json(original: str, formatted: str) -> bool:
    """Compare JSON values without merging boolean, integer and decimal types."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("nonfinite JSON number")

    def decode(value):
        return json.loads(value, object_pairs_hook=unique_object, parse_constant=reject_constant,
                          parse_int=lambda number: ("integer", int(number)),
                          parse_float=lambda number: ("decimal", Decimal(number)))

    try:
        return decode(original) == decode(formatted)
    except (ValueError, InvalidOperation, RecursionError):
        return False


def _inside(root: Path, path: Path) -> Path | None:
    try:
        resolved = path.resolve(strict=True)
        return resolved if resolved.is_relative_to(root) else None
    except (OSError, RuntimeError):
        return None


def _read(root: Path, path: Path) -> str:
    resolved = _inside(root, path)
    try:
        if resolved is not None and resolved.is_file():
            return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        pass
    return ""


def _json(root: Path, path: Path) -> dict:
    try:
        data = json.loads(_read(root, path))
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _children(root: Path, path: Path) -> list[Path]:
    resolved = _inside(root, path)
    try:
        if resolved is not None and resolved.is_dir():
            return sorted(path.iterdir())
    except OSError:
        pass
    return []


def _file_inside(root: Path, path: Path) -> bool:
    resolved = _inside(root, path)
    try:
        return resolved is not None and resolved.is_file()
    except OSError:
        return False


def _mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def _prettier_version(package: dict):
    dependencies = {**_mapping(package.get("dependencies")), **_mapping(package.get("devDependencies"))}
    return dependencies.get("prettier")


def discover(repo_dir: Path | None) -> dict:
    """Report declared tooling with source evidence. Never execute a discovered command."""
    if repo_dir is None:
        return {"formatters": [], "validators": [], "status": "needs-input:repo-dir"}
    root = Path(repo_dir).resolve()
    package = _json(root, root / "package.json")
    configs = [p.name for p in _children(root, root)
               if (p.name.startswith((".prettierrc", "prettier.config.")) or p.name == ".editorconfig") and _file_inside(root, p)]
    if "prettier" in package:
        configs.append("package.json#prettier")
    validators = []
    for name, command in _mapping(package.get("scripts")).items():
        if SCRIPT_NAME.fullmatch(name) and VALIDATOR_NAME.search(name) and isinstance(command, str):
            validators.append({"source": f"package.json#scripts.{name}", "command": f"npm run {name}", "status": "not run"})
    for name in ("AGENTS.md", "CONTRIBUTING.md"):
        text = _read(root, root / name)
        # These are reported evidence, never executable instructions.
        for match in re.finditer(r"^```(?:bash|sh|shell|console)\s*\n(.*?)^```", text, re.M | re.S):
            for line in match.group(1).splitlines():
                command = line.strip().removeprefix("$ ")
                if display := _display_validator(command):
                    validators.append({"source": name, "command": display, "status": "not run"})
        prose = re.sub(r"^```[^\n]*\n.*?^```[^\n]*", "", text, flags=re.M | re.S)
        for line in prose.splitlines():
            if not re.search(r"\b(?:run|execute)\b", line, re.I):
                continue
            for command in re.findall(r"`([^`\n]+)`", line):
                if display := _display_validator(command):
                    validators.append({"source": name, "command": display, "status": "not run"})
    workflows = root / ".github" / "workflows"
    for path in _children(root, workflows):
        if path.suffix not in (".yml", ".yaml"):
            continue
        import yaml

        try:
            data = _mapping(yaml.safe_load(_read(root, path)))
        except yaml.YAMLError:
            continue
        for job, details in _mapping(data.get("jobs")).items():
            steps = _mapping(details).get("steps")
            if not isinstance(steps, list):
                continue
            source = f"{path.relative_to(root).as_posix()}#jobs.{job}"
            for step in steps:
                run = _mapping(step).get("run")
                if isinstance(run, str):
                    for line in run.splitlines():
                        command = line.strip()
                        if display := _display_validator(command):
                            validators.append({"source": source, "command": display, "status": "not run"})
    return {"formatters": configs, "prettier_version": _prettier_version(package),
            "validators": validators, "status": "not run"}


def format_text(repo_dir: Path | None, destination: Path, text: str) -> str:
    """Format one generated text value with the target's exact pinned local Prettier.

    No install, package script, shell, or file write occurs here. The caller writes only
    after its usual safety checks. Calling this function is the explicit opt-in.
    """
    if repo_dir is None:
        raise NeedsInput("formatter", "formatting requires a target checkout")
    root = Path(repo_dir).resolve()
    destination = Path(destination)
    suffix = destination.suffix.lower()
    try:
        relative = destination.resolve().relative_to(root)
    except ValueError as error:
        raise ShowcaseError("formatter destination must be inside the target checkout", log="usage") from error
    version = _prettier_version(_json(root, root / "package.json"))
    exact = r"\d+\.\d+\.\d+(?:-[\w.-]+)?"
    if not isinstance(version, str):
        raise NeedsInput("formatter", "declare prettier in the target package.json")
    if not re.fullmatch(exact, version):
        for lockname in ("npm-shrinkwrap.json", "package-lock.json"):
            locked = _json(root, root / lockname)
            pin = _mapping(_mapping(locked.get("packages")).get("node_modules/prettier")).get("version")
            if isinstance(pin, str) and re.fullmatch(exact, pin):
                version = pin
                break
        else:
            raise NeedsInput("formatter", "pin Prettier exactly or supply its npm lockfile")
    package_root = _inside(root, root / "node_modules" / "prettier")
    installed = _json(root, package_root / "package.json") if package_root is not None else {}
    if package_root is None or installed.get("version") != version:
        raise NeedsInput("formatter", "install the target's pinned Prettier before formatting")
    node = shutil.which("node")
    if node is None:
        raise NeedsInput("formatter", "Node.js is required for the target's pinned Prettier")
    binary = installed.get("bin")
    binary = binary.get("prettier") if isinstance(binary, dict) else binary
    if not isinstance(binary, str):
        raise NeedsInput("formatter", "the installed Prettier package has no CLI")
    cli = _inside(package_root, package_root / binary)
    if cli is None or not _file_inside(package_root, cli):
        raise NeedsInput("formatter", "the installed Prettier CLI is unavailable")
    argv = [node, str(cli), "--stdin-filepath", str(relative)]
    if suffix == ".svg":
        argv += ["--parser", "html"]
    def run(*flags: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run([*argv, *flags], cwd=root, input=text.encode("utf-8"),
                              capture_output=True, timeout=60, check=False)

    try:
        if suffix == ".md":
            semantic_check = run("--debug-check")
            if semantic_check.returncode:
                raise ShowcaseError("target Prettier could not verify Markdown content", log="formatter-content",
                                    code=CHECK_FAILED)
        result = run()
    except (OSError, subprocess.SubprocessError) as error:
        raise NeedsInput("formatter", "the target's pinned Prettier could not run") from error
    if result.returncode:
        raise ShowcaseError("target Prettier failed; verify its configuration and plugins", log="formatter-failed")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeError as error:
        raise ShowcaseError("target Prettier returned invalid UTF-8", log="formatter-failed") from error
