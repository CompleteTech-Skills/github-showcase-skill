"""Read-only target tooling discovery and explicitly requested, local Prettier formatting."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from contextlib import ExitStack, contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import CHECK_FAILED, NeedsInput, ShowcaseError

VALIDATOR_NAME = re.compile(r"(?:^|[:_-])(check|contracts|lint|test|typecheck|validate|format|verify)(?:$|[:_-])", re.I)
SCRIPT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_-]*")
VALIDATOR_COMMAND = re.compile(
    r"^(?:(?:uv run |poetry run )?(?:python[\d.]* -m )?(?:pytest|unittest|ruff|prettier|pyright|mypy|eslint)"
    r"|(?:npx |(?:npm|pnpm) exec )(?:prettier|eslint)"
    r"|(?:python[\d.]* )?(?:\./)?(?:scripts/)?validate[\w.-]*\.py"
    r"|python[\d.]* (?:\./)?scripts/showcase\.py (?:fonts|footer) --check"
    r"|(?:cargo|go|dotnet|npm|pnpm|yarn|bun|make|just)\s+(?:run\s+)?"
    r"(?:test|check|contracts|lint|typecheck|validate|verify|format)(?:[:_-][A-Za-z0-9:_-]+)?)(?=\s|$|[;&|])",
    re.I,
)
DISPLAY_ARGUMENTS = {".", "-q", "-v", "--", "--check", "--write", "--fix", "--quiet", "--verbose", "check", "discover"}


EXACT_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
                           r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
                           r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
PRETTIER_EXTENSIONS = {"json", "json5", "yaml", "yml", "toml", "js", "cjs", "mjs", "ts", "cts", "mts"}

PRETTIER_CONFIGS = (
    "package.json", "package.yaml", ".prettierrc", ".prettierrc.json", ".prettierrc.yaml",
    ".prettierrc.yml", ".prettierrc.json5", ".prettierrc.js", ".prettierrc.ts", ".prettierrc.mjs",
    ".prettierrc.mts", ".prettierrc.cjs", ".prettierrc.cts", "prettier.config.js", "prettier.config.ts",
    "prettier.config.mjs", "prettier.config.mts", "prettier.config.cjs", "prettier.config.cts", ".prettierrc.toml",
)


# Match Prettier's Markdown debug check, using the same formatter result for the write.
FORMAT_GENERATED = r"""
const fs = require("node:fs");
const path = require("node:path");
const { isDeepStrictEqual } = require("node:util");
async function main() {
    const [packagePath, config, editorFile, editorConfig, filepath] = process.argv.slice(1);
    const prettier = require(packagePath);
    const input = fs.readFileSync(0, "utf8");
    for (const ignorePath of [".gitignore", ".prettierignore"]) {
        if (fs.existsSync(ignorePath) && (await prettier.getFileInfo(filepath, { ignorePath, resolveConfig: false })).ignored) {
            process.stdout.write(JSON.stringify(input));
            return;
        }
    }
    const editor = editorFile ? await prettier.resolveConfig(editorFile, { config: editorConfig, editorconfig: true }) : {};
    const settings = await prettier.resolveConfig(filepath, { config, editorconfig: false });
    const extension = path.extname(filepath).toLowerCase();
    const markdown = extension === ".md";
    const options = { ...(markdown ? { parser: "markdown" } : {}), ...editor, ...settings, filepath };
    if (extension === ".svg") options.parser = "html";
    const formatted = await prettier.format(input, options);
    if (markdown) {
        const original = await prettier.__debug.parse(input, options, { massage: true });
        const candidate = await prettier.__debug.parse(formatted, options, { massage: true });
        if (!isDeepStrictEqual(original.ast, candidate.ast)) {
            process.exitCode = 1;
            return;
        }
    }
    process.stdout.write(JSON.stringify(formatted));
}
main().catch(() => { process.exitCode = 2; });
"""


def _exact_version(value) -> bool:
    return isinstance(value, str) and len(value) <= 128 and EXACT_VERSION.fullmatch(value) is not None


def _config_name(name: str) -> str | None:
    if name in (".editorconfig", ".prettierrc"):
        return name
    for prefix in (".prettierrc.", "prettier.config."):
        if name.startswith(prefix):
            return name if name[len(prefix):] in PRETTIER_EXTENSIONS else prefix + "*"
    return None


def protect_svg_title(drawing: str) -> str:
    """Preserve the exact accessible title of a generated drawing."""
    return drawing.replace("\n<title>", "\n<!-- prettier-ignore -->\n<title>", 1)


def same_svg(original: str, formatted: str) -> bool:
    """Compare SVG drawing nodes and reject unexpected XML directives."""

    class Drawing(ET.TreeBuilder):
        def __init__(self):
            super().__init__()
            self.comments = []

        def pi(self, target, text):
            raise ValueError("SVG processing instructions are not allowed")

        def doctype(self, name, pubid, system):
            raise ValueError("SVG document types are not allowed")

        def comment(self, text):
            if text.strip() != "prettier-ignore":
                self.comments.append(text)

    def structure(markup):
        target = Drawing()
        root = ET.fromstring(markup, parser=ET.XMLParser(target=target))
        nodes = [(node.tag, node.attrib,
                  (node.text or "") if node.tag.rsplit("}", 1)[-1] == "title" else " ".join((node.text or "").split()),
                  " ".join((node.tail or "").split()), len(node)) for node in root.iter()]
        return nodes, target.comments

    try:
        return structure(original) == structure(formatted)
    except (ET.ParseError, ValueError):
        return False


def target_relative(repo_dir: Path | None, destination: Path) -> Path:
    if repo_dir is None:
        raise NeedsInput("formatter", "formatting requires a target checkout")
    try:
        return destination.resolve().relative_to(Path(repo_dir).resolve())
    except ValueError as error:
        raise ShowcaseError("formatter destination must be inside the target checkout", log="usage") from error


def _file_state(path: Path) -> tuple[int, ...] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ShowcaseError("formatted output must be a regular file", log="formatter-output")
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def write_formatted_outputs(outputs: list[tuple[Path, bytes]], *,
                            repo_root: Path | None = None,
                            snapshots: dict[Path, bytes | None] | None = None) -> None:
    """Prepare every replacement on its destination filesystem, then publish or roll back the group."""
    snapshots = snapshots or {}
    with ExitStack() as scratch:
        prepared = []
        for destination, data in outputs:
            path = destination.parent.resolve() / destination.name
            if repo_root is not None and not path.is_relative_to(repo_root):
                raise ShowcaseError("formatter destination must be inside the target checkout", log="usage")
            initial = _file_state(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            working = Path(scratch.enter_context(tempfile.TemporaryDirectory(dir=path.parent)))
            replacement = working / "output"
            backup = working / "original"
            replacement.write_bytes(data)
            previous = None
            if initial is not None:
                # Keep the old entry's access check even where directory permissions allow replacing it.
                with path.open("r+b") as stream:
                    previous = stream.read()
                backup.write_bytes(previous)
                mode = stat.S_IMODE(initial[2])
                replacement.chmod(mode)
                backup.chmod(mode)
            if destination in snapshots and previous != snapshots[destination]:
                raise ShowcaseError("README inputs changed during formatting", log="formatter-source-changed",
                                    code=CHECK_FAILED)
            prepared.append((destination, path, initial, replacement, backup))
        written = []
        try:
            for destination, path, initial, replacement, backup in prepared:
                if destination.resolve() != path or _file_state(path) != initial:
                    raise ShowcaseError("output changed during formatting", log="formatter-source-changed",
                                        code=CHECK_FAILED)
                replacement.replace(path)
                written.append((path, backup))
        except (OSError, ShowcaseError):
            for path, backup in reversed(written):
                if backup.exists():
                    backup.replace(path)
                else:
                    path.unlink()
            raise


@contextmanager
def sidecar_lock(path: Path | None):
    """Serialize a sidecar read/format/write across local generator processes."""
    if path is None:
        yield
        return
    key = hashlib.sha256(os.fsencode(os.path.normcase(str(path.resolve())))).hexdigest()
    directory = Path(tempfile.gettempdir()) / "showcase-sidecar-locks"
    directory.mkdir(exist_ok=True)
    with (directory / key).open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + 90
            while True:
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise NeedsInput("formatter", "another generator still holds the sidecar lock")
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield  # closing the file releases the lock on both platforms


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
    configs = sorted({name for p in _children(root, root)
                      if (name := _config_name(p.name)) and _file_inside(root, p)})
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
        for details in _mapping(data.get("jobs")).values():
            steps = _mapping(details).get("steps")
            if not isinstance(steps, list):
                continue
            source = ".github/workflows"
            for step in steps:
                run = _mapping(step).get("run")
                if isinstance(run, str):
                    for line in run.splitlines():
                        command = line.strip()
                        if display := _display_validator(command):
                            validators.append({"source": source, "command": display, "status": "not run"})
    declared = _prettier_version(package)
    version = declared if _exact_version(declared) else None
    status = "exact" if version else ("unsupported" if declared is not None else "undeclared")
    return {"formatters": configs, "prettier_version": version, "prettier_version_status": status,
            "validators": validators, "status": "not run"}


def _configured_prettier(root: Path, destination: Path) -> tuple[Path, list[Path]]:
    """Use Prettier's config precedence without loading settings from checkout parents."""
    directory = destination.parent
    config = None
    editorconfigs = []
    editor_bounded = False
    while directory.is_relative_to(root):
        if not editor_bounded:
            editorconfig = directory / ".editorconfig"
            if editorconfig.exists() or editorconfig.is_symlink():
                if not _file_inside(root, editorconfig):
                    raise NeedsInput("formatter", "EditorConfig must be inside the target checkout")
                editorconfigs.append(editorconfig)
            editor_bounded = any((directory / name).is_dir() and not (directory / name).is_symlink()
                                 for name in (".git", ".hg"))
        if config is None:
            for name in PRETTIER_CONFIGS:
                candidate = directory / name
                if not candidate.exists() and not candidate.is_symlink():
                    continue
                if not _file_inside(root, candidate):
                    raise NeedsInput("formatter", "Prettier configuration must be inside the target checkout")
                if name in ("package.json", "package.yaml"):
                    if name == "package.yaml":
                        import yaml

                        try:
                            package = _mapping(yaml.safe_load(_read(root, candidate)))
                        except yaml.YAMLError:
                            continue
                    else:
                        package = _json(root, candidate)
                    value = package.get("prettier")
                    if not isinstance(value, dict) and not (isinstance(value, str) and value):
                        continue
                config = candidate
                break
        if directory == root:
            break
        directory = directory.parent
    # package.json supplies the pinned dependency. Passing it explicitly prevents ancestor discovery
    # even when it has no Prettier options.
    return config or root / "package.json", editorconfigs


def format_text(repo_dir: Path | None, destination: Path, text: str) -> str:
    """Format one generated text value with the target's exact pinned local Prettier.

    This uses the installed package and leaves the target files untouched. The caller writes only
    after its usual safety checks. Calling this function is the explicit opt-in.
    """
    destination = Path(destination)
    relative = target_relative(repo_dir, destination)
    root = Path(repo_dir).resolve()
    suffix = destination.suffix.lower()
    version = _prettier_version(_json(root, root / "package.json"))
    if not isinstance(version, str):
        raise NeedsInput("formatter", "declare prettier in the target package.json")
    if not _exact_version(version):
        for lockname in ("npm-shrinkwrap.json", "package-lock.json"):
            locked = _json(root, root / lockname)
            pin = _mapping(_mapping(locked.get("packages")).get("node_modules/prettier")).get("version")
            if _exact_version(pin):
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
    entry = next((resolved for name in ("index.cjs", "index.js")
                  if (resolved := _inside(package_root, package_root / name)) and resolved.is_file()), None)
    if entry is None:
        raise NeedsInput("formatter", "the installed Prettier API is unavailable")
    config, editorconfigs = _configured_prettier(root, root / relative)
    try:
        with ExitStack() as stack:
            editor_file = editor_config = ""
            if editorconfigs:
                # Resolve only checkout EditorConfig files in an isolated mirror.
                # The original filepath still selects the target Prettier overrides.
                mirror = Path(stack.enter_context(tempfile.TemporaryDirectory()))
                (mirror / ".git").mkdir()
                empty = mirror / "empty.json"
                empty.write_text("{}", encoding="utf-8")
                for item in editorconfigs:
                    copy = mirror / item.relative_to(root)
                    copy.parent.mkdir(parents=True, exist_ok=True)
                    copy.write_text(_read(root, item), encoding="utf-8")
                mirrored_destination = mirror / relative
                mirrored_destination.parent.mkdir(parents=True, exist_ok=True)
                editor_file, editor_config = str(mirrored_destination), str(empty)
            argv = [node, "--input-type=commonjs", "-e", FORMAT_GENERATED, str(entry), str(config),
                    editor_file, editor_config, str(relative)]
            result = subprocess.run(argv, cwd=root, input=text.encode("utf-8"),
                                    capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise NeedsInput("formatter", "the target's pinned Prettier could not run") from error
    if result.returncode == 1 and suffix == ".md":
        raise ShowcaseError("target Prettier could not verify Markdown content", log="formatter-content",
                            code=CHECK_FAILED)
    if result.returncode:
        raise ShowcaseError("target Prettier failed; verify its configuration and plugins", log="formatter-failed")
    try:
        formatted = json.loads(result.stdout.decode("utf-8"))
    except (ValueError, UnicodeError):
        formatted = None
    if not isinstance(formatted, str) or (text.strip() and not formatted.strip()):
        if suffix == ".md":
            raise ShowcaseError("target Prettier returned invalid Markdown output", log="formatter-content",
                                code=CHECK_FAILED)
        raise ShowcaseError("target Prettier returned invalid output", log="formatter-failed")
    return formatted
