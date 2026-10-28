"""STANDARD §5.4 type detection (rules 1-25), README variant and card category."""
from __future__ import annotations

import json
import re
from functools import lru_cache

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


def detect_type(meta: dict, facts: RepoFacts | None = None) -> tuple[str, int]:
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

    if is_fork(meta):
        return "fork", 1
    if re.search(r"-backup-\d{8}$", slug):
        return "backup", 2
    if slug == ".github" or (_same_login(owner, "CompleteDotTech") and _same_login(slug, "CompleteDotTech")):
        return "github-profile", 3
    if meta.get("is_template"):
        return "template", 4
    if "SKILL.md" in roots:
        return "agent-skills", 5
    if not facts.known and re.search(r"\]\((?:\./)?SKILL\.md\)", meta.get("readme_head") or ""):
        # tree unknown (partial metadata): the README links a root SKILL.md, the rule 5 evidence available
        return "agent-skills", 5
    if owner.lower() == t["security_owner"].lower():
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
    if owner.lower() in {o.lower() for o in t["game_owners"]}:
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
    if owner.lower() == t["research_owner"].lower() or (files and len(nb) * 2 >= len(files)):
        return "research", 22
    if re.search(r"-in-\d+-steps$", slug):
        return "tutorial", 23
    sizes = meta.get("file_sizes") or {}
    if sizes:
        data = sum(v for k, v in sizes.items() if k.endswith((".csv", ".json", ".parquet")))
        if data * 2 >= sum(sizes.values()):
            return "dataset", 24
    return "workspace", 25


def _same_login(a, b) -> bool:
    return bool(a and b) and str(a).lower() == str(b).lower()


def variant_for(type_: str, meta: dict, same_owner=None) -> str:
    """README variant for the type. `same_owner(a, b)` compares org logins (RepoContext passes the shared resolver's,
    CQ-03); without it the compare is case-insensitive, as GitHub logins are."""
    row = standard("types")["types"][type_]
    same = same_owner or _same_login
    if type_ == "agent-skills" and not same(meta.get("owner"), "CompleteTech-Skills"):
        return row.get("variant_elsewhere", "C")
    if meta.get("visibility") == "private" and row.get("variant_private"):
        return row["variant_private"]
    return row["variant"]


def card_category(type_: str) -> str | None:
    return standard("types")["types"][type_]["category"]


def detect(meta: dict, facts: RepoFacts | None = None, override: dict | None = None, type_override: str | None = None,
           same_owner=None) -> dict:
    facts = facts or RepoFacts(meta)
    type_override = type_override or (override or {}).get("type")
    if type_override:
        if type_override not in standard("types")["types"]:
            from .errors import ShowcaseError
            raise ShowcaseError(f"unknown type {type_override!r}", log="usage")
        type_, rule = type_override, 0
    else:
        type_, rule = detect_type(meta, facts)
    variant = (override or {}).get("variant") or variant_for(type_, meta, same_owner)
    out = {"type": type_, "rule": rule, "variant": variant, "category": card_category(type_)}
    if not facts.known and not type_override:
        # rules 5, 8-11 and 13-24 need the file tree; without it the type is provisional
        out["provisional"] = True
    return out
