"""`brand add-family` / `brand add-org`: propose (dry run, the default) or write (`--write`) one new block in
references/brand.yaml. A write regenerates references/brand.lock.json (the `config --write-lock` code path) and the
standard lock, schema-validates the result, and restores every touched file byte-for-byte when that fails."""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from . import config as C
from .errors import CHECK_FAILED, OK, ConfigError, Refused, ShowcaseError

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
FAMILY_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
LOGIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
TIERS = ("T1", "T1-user", "T2", "T2-R", "T3")


def _q(value: str) -> str:
    """A YAML double-quoted scalar (JSON strings are valid YAML), so free text can never break the document."""
    return json.dumps(value, ensure_ascii=False)


def _hex(flag: str, value: str) -> str:
    if not HEX.match(value or ""):
        raise ShowcaseError(f"{flag} must be a #RRGGBB colour, got {value!r}", log="usage")
    return value.upper()


def family_block(name: str, *, company_label: str, canvas: str, accent: str, accent_deep: str | None = None,
                 title: str, eyebrow_case: str = "upper") -> list[str]:
    """A new family: a flat dark canvas, one accent, `measured: false` (no golden layout measured yet)."""
    if not FAMILY_NAME.match(name or ""):
        raise ShowcaseError(f"family name must be lowercase letters, digits and hyphens, got {name!r}", log="usage")
    canvas, accent, title = _hex("--canvas", canvas), _hex("--accent", accent), _hex("--title", title)
    deep = _hex("--accent-deep", accent_deep) if accent_deep else accent
    return [
        f"  {_q(name)}:",  # quoted: `yes`/`true`/`123` must stay string keys
        "    measured: false",
        f"    company_label: {_q(company_label)}",
        f"    eyebrow_case: {eyebrow_case}",
        f"    canvas: {{kind: flat, color: {_q(canvas)}}}",
        "    tokens:",
        f"      eyebrow: {_q(accent)}",
        f"      title: {_q(title)}",
        f"      plate_low: {_q(canvas)}",
        f"      chip_key: {{bg: {_q(accent)}, fg: {_q(canvas)}}}",
        f"      chip_attr: {{bg: {_q(deep)}, fg: {_q(title)}}}",
        f"      bar: {{from: {_q(deep)}, to: {_q(accent)}, height: 6}}",
        f"      edge: {{color: {_q(accent)}, opacity: 0.28}}",
        f"      gold_trace: {_q(accent)}",
        f"      accent: {_q(accent)}",
        f"      accent_mid: {_q(accent)}",
        f"      accent_deep: {_q(deep)}",
    ]


def org_block(owner: str, *, family: str, tier: str, display_name: str, nav_name: str | None = None,
              description: str | None = None, eyebrow: str | None = None, brand_topic: str | None = None) -> list[str]:
    if not LOGIN.match(owner or ""):
        raise ShowcaseError(f"org login must be letters, digits and hyphens, got {owner!r}", log="usage")
    if tier not in TIERS:
        raise ShowcaseError(f"tier must be one of {', '.join(TIERS)}", log="usage")
    return [
        f"  {_q(owner)}:",
        f"    family: {_q(family)}",
        "    former_slugs: []",
        f"    tier: {tier}",
        f"    display_name: {_q(display_name)}",
        f"    nav_name: {_q(nav_name or display_name)}",
        f"    description: {_q(description) if description else 'null'}",
        f"    eyebrow: {_q(eyebrow) if eyebrow else 'null'}",
        f"    brand_topic: {_q(brand_topic or family)}",  # default: the family slug, no hardcoded brand
        "    family_topics: []",
        "    footer: true",
    ]


def check_new_family(raw: dict, name: str) -> None:
    for existing in (raw.get("families") or {}):
        if existing.lower() == name.lower():
            raise Refused(f"family {existing!r} already exists in brand.yaml; nothing to add", log="duplicate")


def check_new_org(brand: C.Brand, owner: str, family: str) -> None:
    raw = brand.raw
    if family not in (raw.get("families") or {}):
        raise Refused(f"unknown family {family!r}; add it first with `brand add-family`", log="unknown-family")
    low = owner.lower()
    for name, row in (raw.get("orgs") or {}).items():
        if name.lower() == low or low in {s.lower() for s in (row.get("former_slugs") or [])}:
            raise Refused(f"{owner} is already in brand.yaml (orgs.{name}); nothing to add", log="duplicate")
    for status, logins in (raw.get("owners") or {}).items():
        if low in {s.lower() for s in logins}:
            raise Refused(f"{owner} is already listed under owners.{status}; resolve that decision first", log="duplicate")
    if brand.org(owner)["known"]:
        raise Refused(f"{owner} already resolves to a brand.yaml org (renamed login); nothing to add", log="duplicate")


def add_t3_owner(text: str, owner: str) -> str:
    """Register `owner` under owners.t3: the co-owner sign-off gate (Brand.check_owner) reads only that list, so a T3 org
    row alone would pass every owner gate."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    top = next((i for i, ln in enumerate(lines) if ln.startswith("owners:")), None)
    if top is None:
        raise ConfigError("brand.yaml has no top-level `owners:` key")
    for i in range(top + 1, len(lines)):
        if re.match(r"^[A-Za-z_]", lines[i]):
            break
        m = re.match(r"^(  t3:\s*\[)([^\]#]*)(\]\s*(?:#.*)?)$", lines[i])
        if m:
            items = [x for x in (m.group(2).strip(),) if x]
            lines[i] = f"{m.group(1)}{', '.join(items + [_q(owner)])}{m.group(3)}"
            return nl.join(lines)
    raise ConfigError("brand.yaml owners.t3 must be a one-line flow list (`t3: [a, b]`)")


def insert(text: str, section: str, block: list[str]) -> str:
    """Append `block` to the end of top-level `section:` (just before the next top-level key's comment lead-in). Line
    endings and every other byte are kept."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    starts = [i for i, ln in enumerate(lines) if ln.startswith(f"{section}:")]
    if len(starts) != 1:
        raise ConfigError(f"brand.yaml must have exactly one top-level `{section}:` key")
    nxt = next((i for i in range(starts[0] + 1, len(lines)) if re.match(r"^[A-Za-z_]", lines[i])), None)
    j = len(lines) if nxt is None else nxt  # the last top-level section ends at end of file
    while nxt is not None and j > starts[0] + 1 and lines[j - 1].startswith("#"):  # comments that introduce the next key stay with it
        j -= 1
    while j > starts[0] + 1 and lines[j - 1].strip() == "":
        j -= 1
    return nl.join(lines[:j] + block + lines[j:])


def unified(old: str, new: str, label: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{label}", f"b/{label}"))


def _errors(text: str) -> list[str]:
    try:
        raw = C.load_yaml_text(text)
    except Exception as exc:  # malformed YAML is a failed check, not a crash
        return [f"brand.yaml does not parse: {exc}"]
    return C.schema_errors(raw) if isinstance(raw, dict) else ["brand config must be a mapping"]


def write(brand_path: Path, new_text: str, locks: list[tuple[Path, "callable"]]) -> list[str]:
    """Write brand.yaml, then each (path, text-from-raw) lock; restore every file byte-for-byte on failure.
    Returns the schema errors (empty when the write was kept)."""
    originals = {p: (p.read_bytes() if p.is_file() else None) for p in [brand_path, *(p for p, _ in locks)]}

    def restore():
        for p, data in originals.items():
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(data)

    try:
        brand_path.write_bytes(new_text.encode("utf-8"))
        errs = _errors(new_text)
        if errs:
            restore()
            return errs
        raw = C.load_yaml_text(new_text)
        for p, make in locks:
            p.write_text(make(raw), encoding="utf-8")
    except BaseException:
        restore()
        raise
    return []


def run(args, brand) -> tuple[dict, int]:
    """Shared by both subcommands; `args.brand_action` is add-family or add-org."""
    from .detect import STANDARD_LOCK, standard_lock_text
    action = args.brand_action
    path = Path(brand.path)
    if action == "add-family":
        check_new_family(brand.raw, args.name)
        section, key = "families", args.name
        block = family_block(args.name, company_label=args.company_label, canvas=args.canvas, accent=args.accent,
                             accent_deep=args.accent_deep,
                             title=args.title or brand.raw["defaults"]["tokens"]["title"], eyebrow_case=args.eyebrow_case)
    else:
        check_new_org(brand, args.owner, args.family)
        section, key = "orgs", args.owner
        block = org_block(args.owner, family=args.family, tier=args.tier, display_name=args.display_name,
                          nav_name=args.nav_name, description=args.description, eyebrow=args.eyebrow,
                          brand_topic=args.brand_topic)
    old = path.read_bytes().decode("utf-8")
    new = insert(old, section, block)
    if action == "add-org" and args.tier == "T3":  # T3 needs co-owner sign-off: owners.t3 is what the gates read
        new = add_t3_owner(new, args.owner)
    diff, errs = unified(old, new, "references/brand.yaml"), _errors(new)
    out = {"command": "brand", "action": action, "key": key, "path": str(path), "yaml": "\n".join(block) + "\n",
           "diff": diff, "schema_errors": errs, "written": False, "logs": []}
    out["text"], out["proposed"] = diff, out["yaml"]
    if not args.write:
        out["result"] = "dry-run" if not errs else "fail"
        return out, OK if not errs else CHECK_FAILED
    locks = []
    if path.resolve() == C.DEFAULT_CONFIG.resolve():  # the skill's own config: same lock set as `config --write-lock`
        locks = [(C.LOCK, C.lock_text), (STANDARD_LOCK, lambda _raw: standard_lock_text())]
    else:
        out["logs"].append("custom --config: no lock copies regenerated")
    errs = write(path, new, locks)
    out["schema_errors"] = errs
    out["written"] = not errs
    out["result"] = "written" if not errs else "rolled-back"
    return out, OK if not errs else CHECK_FAILED


def register(sub, func) -> None:
    s = sub.add_parser("brand", help="propose or add a family / org block in references/brand.yaml (dry run unless --write)")
    bs = s.add_subparsers(dest="brand_action", required=True, metavar="<action>")

    def common(p):
        p.add_argument("--write", action="store_true",
                       help="edit references/brand.yaml and regenerate its lock copies (default: print the block and diff only)")
        p.set_defaults(func=func)

    f = bs.add_parser("add-family", help="add a design family (flat dark canvas, one accent; measured: false)")
    f.add_argument("name", help="family key: lowercase letters, digits, hyphens")
    f.add_argument("--company-label", required=True)
    f.add_argument("--canvas", required=True, help="#RRGGBB banner canvas colour")
    f.add_argument("--accent", required=True, help="#RRGGBB accent colour")
    f.add_argument("--accent-deep", help="#RRGGBB second accent (default: the accent)")
    f.add_argument("--title", help="#RRGGBB title colour (default: the brand.yaml defaults title)")
    f.add_argument("--eyebrow-case", choices=("upper", "asis"), default="upper")
    common(f)
    o = bs.add_parser("add-org", help="add an org row (the org must not exist; its family must)")
    o.add_argument("owner", help="GitHub login")
    o.add_argument("--family", required=True)
    o.add_argument("--tier", required=True, choices=TIERS)
    o.add_argument("--display-name", required=True)
    o.add_argument("--nav-name")
    o.add_argument("--description")
    o.add_argument("--eyebrow")
    o.add_argument("--brand-topic", default=None, help="topic for the org (default: the family name)")
    common(o)
