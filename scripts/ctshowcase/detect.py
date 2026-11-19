"""STANDARD §5.4 type detection (rules 1-25), README variant and card category."""
from __future__ import annotations

import json
import re
from fractions import Fraction
from functools import lru_cache
from pathlib import PurePosixPath

from . import REFERENCES
from .facts import RepoFacts

STANDARD_DIR = REFERENCES / "standard"
STANDARD_LOCK = STANDARD_DIR / "standard.lock.json"
STANDARD_FILES = ("types", "topics", "descriptions", "readme-variants", "naming")


@lru_cache(maxsize=None)
def standard(name: str) -> dict:
    """Load references/standard/<name>.yaml (pyyaml) or its stdlib lock copy."""
    try:
        import yaml
    except ImportError:
        yaml = None
    path = STANDARD_DIR / f"{name}.yaml"
    if yaml is not None and path.is_file():
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return json.loads(STANDARD_LOCK.read_text(encoding="utf-8"))[name]


def standard_lock_text() -> str:
    import yaml
    data = {n: yaml.safe_load((STANDARD_DIR / f"{n}.yaml").read_text(encoding="utf-8")) for n in STANDARD_FILES}
    return json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def is_fork(meta: dict) -> bool:
    """Type rule 1: GitHub's fork flag or a `-fork` slug. RepoContext.is_fork adds the detected `fork` type."""
    return bool(meta.get("fork")) or (meta.get("repo") or "").endswith("-fork")


def detect_type(meta: dict, facts: RepoFacts | None = None, same_owner=None) -> tuple[str, int]:
    """Return (type, rule number). Rules that need files are skipped when the tree is unknown."""
    t = standard("types")
    facts = facts or RepoFacts(meta)
    owner, slug = meta.get("owner", ""), meta.get("repo", "")
    tlds = "|".join(t["domain_tlds"])
    deps = set(facts.dependencies()) if facts.known else set()
    files = facts.files if facts.known else []
    roots = set(facts.root_files()) if facts.known else set()
    desc = meta.get("description") or ""
    h1 = facts.h1() or ""

    def dep(kind):
        return any(d.lower() in deps for d in t["deps"][kind])

    def owner_matches(login):
        nonlocal same_owner
        if not owner:
            return False
        if same_owner is None:
            from .config import load_brand
            same_owner = load_brand(prefer_lock=True).resolver().same
        return same_owner(owner, login)

    if is_fork(meta):
        return "fork", 1
    if re.search(r"-backup-\d{8}$", slug):
        return "backup", 2
    if slug == ".github" or (_same_login(slug, "CompleteDotTech") and owner_matches("CompleteDotTech")):
        return "github-profile", 3
    if meta.get("is_template"):
        return "template", 4
    if "SKILL.md" in roots:
        return "agent-skills", 5
    if not facts.known and re.search(r"\]\((?:\./)?SKILL\.md\)", meta.get("readme_head") or ""):
        # tree unknown (partial metadata): the README links a root SKILL.md, the rule 5 evidence available
        return "agent-skills", 5
    if owner_matches(t["security_owner"]):
        return "security-check", 6
    if dep("mcp-server") or "mcp server" in h1.lower() or "mcp server" in desc.lower():
        return "mcp-server", 7
    if "manifest.json" in roots and '"manifest_version"' in (facts.read("manifest.json") or ""):
        return "chrome-extension", 8
    if ".claude-plugin/plugin.json" in files or "plugin.json" in roots or any(r.endswith(".plugin.json") for r in roots):
        return "plugin", 9
    if dep("discord-bot"):
        return "discord-bot", 10
    if dep("bot"):
        return "bot", 11
    if any(owner_matches(other) for other in t["game_owners"]):
        return "game", 12
    if any(f.endswith("AndroidManifest.xml") or ".xcodeproj/" in f or f.endswith(".xcodeproj") for f in files):
        return "mobile-app", 13
    if slug.endswith(".home.complete.tech"):
        return "infrastructure", 14
    if re.search(rf"\.({tlds})$", slug):
        return "website", 15
    if any(f.endswith((".kicad_pro", ".kicad_pcb")) for f in files):
        return "hardware", 16
    if any(f.split("/")[-1] in ("compose.yaml", "docker-compose.yml") or f.endswith(".tf") for f in files):
        return "infrastructure", 17
    if dep("web-app"):
        return "web-app", 18
    if dep("api"):
        return "api", 19
    if facts.known and facts.has_scripts():
        return "cli", 20
    if facts.known and facts.is_library():
        return "library", 21
    nb = [f for f in files if f.endswith(".ipynb")]
    if owner_matches(t["research_owner"]) or (files and len(nb) * 2 >= len(files)):
        return "research", 22
    if re.search(r"-in-\d+-steps$", slug):
        return "tutorial", 23
    share = dataset_share(facts)
    if share is not None and share * 2 >= 1:
        return "dataset", 24
    return documentation_type(facts) or "workspace", 25


DATA_SUFFIXES = (".csv", ".json", ".parquet")
DOC_SUFFIXES = (".md", ".rst", ".txt", ".adoc")
_ISSUE_EXPORT_PATH = re.compile(r"issues/issue-[0-9]+\.json", re.IGNORECASE)
_EXPORT_NAME = re.compile(r"(?:generated|exported)-(?:issues|planning)\.json", re.IGNORECASE)


def captured_path(path: object) -> PurePosixPath | None:
    """A canonical checkout-relative path supplied by a capture."""
    if not isinstance(path, str):
        return None
    parsed = PurePosixPath(path)
    if (not parsed.parts or parsed.as_posix() != path or ".." in parsed.parts or parsed.is_absolute()
            or "\\" in path or "\0" in path or re.match(r"^[A-Za-z]:", path)):
        return None
    return parsed


def _generated_or_exported_path(parsed: PurePosixPath, spec: dict) -> bool:
    parts = parsed.parts
    return bool(parsed.as_posix() in spec.get("showcase_artifact_paths", [])
                or (parts[:-1] == ("docs", "images", "badges") and parsed.suffix == ".svg")
                or _EXPORT_NAME.fullmatch(parsed.name) or _ISSUE_EXPORT_PATH.fullmatch(parsed.as_posix()))


def substantive_path(parsed: PurePosixPath) -> bool:
    """False for administrative inputs excluded from rule 24's byte share."""
    spec = standard("types")
    excluded = set(spec.get("dataset_exclude_dirs", []))
    return (not _generated_or_exported_path(parsed, spec) and not any(part in excluded for part in parsed.parts[:-1])
            and parsed.name not in spec.get("dataset_exclude_files", []))


def substantive_sizes(facts: RepoFacts) -> dict[str, int]:
    """Use captured sizes without consulting the checkout, including legacy captures with only a size map."""
    captured = facts.meta.get("file_sizes")
    if facts.meta.get("files_complete", True) is not True or not isinstance(captured, dict):
        return {}
    files = facts.meta.get("files")
    if "files" not in facts.meta:
        files = captured.keys()
    elif not isinstance(files, list):
        return {}
    sizes = {}
    for path in files:
        parsed = captured_path(path)
        if parsed is None:
            return {}
        if not substantive_path(parsed):
            continue
        size = captured.get(path)
        if type(size) is not int or size < 0:
            return {}
        sizes[path] = size
    return sizes


def dataset_share(facts: RepoFacts) -> Fraction | None:
    """Share of substantive bytes in CSV, JSON and Parquet files, or None when no substantive byte is known."""
    sizes = substantive_sizes(facts)
    total = sum(sizes.values())
    if not total:
        return None
    return Fraction(sum(v for k, v in sizes.items() if k.endswith(DATA_SUFFIXES)), total)


def documentation_type(facts: RepoFacts) -> str | None:
    """Distinguish dedicated documentation from a workspace with a README and housekeeping files."""
    if not facts.known or facts.meta.get("files_complete", True) is not True:
        return None
    spec = standard("types")
    admin = set(spec.get("documentation_exclude_files", []))
    administrative_dirs = set(spec.get("documentation_exclude_dirs", []))
    if facts.dir is None:
        paths = [captured_path(path) for path in facts.meta.get("files", []) or []]
    else:
        paths = [captured_path(path) for path in facts.documentation_files()]
    if any(path is None for path in paths):
        return None
    rest = [path for path in paths if path is not None and path.name not in admin
            and not any(part in administrative_dirs for part in path.parts[:-1])
            and not _generated_or_exported_path(path, spec)]
    if not rest or any(path.suffix.lower() not in DOC_SUFFIXES and path.name not in ("LICENSE", "COPYING")
                       for path in rest):
        return None
    boilerplate = {"readme", "license", "copying", "contributing", "changelog", "code_of_conduct", "security"}
    if any(len(path.parts) > 1 or path.stem.lower() not in boilerplate for path in rest):
        return "documentation"
    return "workspace"


def type_suggestion(rule: int, facts: RepoFacts) -> str | None:
    """Return the reason for a low-confidence type, if any."""
    if not facts.known:
        return "file-tree-unknown"
    if facts.meta.get("files_complete", True) is not True and rule == 25:
        return "file-tree-incomplete"
    if rule == 24:
        share = dataset_share(facts)
        threshold = Fraction(str(standard("types").get("dataset_confident_share", 0.6)))
        if share is not None and share < threshold:
            return "dataset-near-threshold"
    if rule == 25 and documentation_type(facts):
        return "docs-only"
    return None


def required_sections(det: dict, variant: str | None = None, *, meta: dict | None = None) -> list:
    """H2 rows for a README: a type's `type_sections` when its default variant is in use, else the variant's rows."""
    rv = standard("readme-variants")
    variant = variant or det["variant"]
    specific = rv.get("type_sections", {}).get(det["type"])
    if specific is not None and variant == variant_for(det["type"], meta or {}):
        return specific
    return rv["variants"].get(variant, [])


def _same_login(a, b) -> bool:
    return bool(a and b) and str(a).lower() == str(b).lower()


def _skill_library_owner(owner, same) -> bool:
    """Whether the default config's row for `owner` carries `skill_library` (callers without a selected config)."""
    from .config import load_brand
    try:
        orgs = load_brand().raw.get("orgs") or {}
    except Exception:  # noqa: BLE001 - no readable config: no skills-library org
        return False
    return any((row or {}).get("skill_library") and same(owner, key) for key, row in orgs.items())


def variant_for(type_: str, meta: dict, same_owner=None, skill_library: bool | None = None) -> str:
    """README variant for the type. `same_owner(a, b)` compares org logins (RepoContext passes the shared resolver's,
    CQ-03); without it the compare is case-insensitive, as GitHub logins are. `skill_library` says whether the owner's
    org row carries `skill_library` (RepoContext passes it from the selected config)."""
    row = standard("types")["types"][type_]
    same = same_owner or _same_login
    if skill_library is None and type_ == "agent-skills":
        skill_library = _skill_library_owner(meta.get("owner"), same)
    if type_ == "agent-skills" and not skill_library:
        return row.get("variant_elsewhere", "C")
    if meta.get("visibility") == "private" and row.get("variant_private"):
        return row["variant_private"]
    return row["variant"]


def card_category(type_: str) -> str | None:
    return standard("types")["types"][type_]["category"]


def detect(meta: dict, facts: RepoFacts | None = None, override: dict | None = None, type_override: str | None = None,
           same_owner=None, skill_library: bool | None = None) -> dict:
    facts = facts or RepoFacts(meta)
    type_override = type_override or (override or {}).get("type")
    if type_override:
        if type_override not in standard("types")["types"]:
            from .errors import ShowcaseError
            raise ShowcaseError(f"unknown type {type_override!r}", log="usage")
        type_, rule = type_override, 0
    else:
        type_, rule = detect_type(meta, facts, same_owner)
    variant = (override or {}).get("variant") or variant_for(type_, meta, same_owner, skill_library)
    out = {"type": type_, "rule": rule, "variant": variant, "category": card_category(type_)}
    reason = None if type_override else type_suggestion(rule, facts)
    if reason:
        # the override key is `type:` in .github/showcase.yml (or --type); setting it suppresses the suggestion
        out["confidence"] = "low"
        out["suggestion"] = f"type-suggestion:{type_}:{reason}:override-key=type"
    if not facts.known and not type_override:
        # rules 5, 8-11 and 13-24 need the file tree; without it the type is provisional
        out["provisional"] = True
    return out
