"""`brand add-family` and `brand add-org`: onboard a non-CompleteTech family or organization into references/brand.yaml.

Dry run by default: the command prints the unified diff and writes nothing. `--write` inserts the new block as text, so
the comments in brand.yaml survive, then validates the result against brand.schema.json and builds the family before the
file is written. Only the default config also regenerates references/brand.lock.json (the same copy `config --write-lock`
writes). `add-org` never edits `owners:`; owner status stays a hand-reviewed decision.
"""
from __future__ import annotations

import difflib
import json
import re

from .color import contrast, hexstr, luminance, mix
from .config import DEFAULT_CONFIG, LOCK, Brand, load_brand, load_yaml_text, lock_text, schema_errors
from .errors import OK, ShowcaseError

FAMILY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ORG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")  # GitHub login shape
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
TIERS = ("T1", "T1-user", "T2", "T2-R", "T3")
DARK_MAX = 0.1  # relative luminance ceiling: dark designs are the estate standard (decision 21)


def _block_family(name: str, label: str, accent: str, background: str) -> list[str]:
    q = lambda s: json.dumps(s, ensure_ascii=False)  # noqa: E731 - YAML double-quoted scalar
    # the attribute chip is the accent tinted 25% into the background: derived, so no colour literal lives in code and a
    # new family never inherits CompleteTech's blue chip
    tint = hexstr(mix(background, accent, 0.25))
    return [
        f"  {name}:",
        "    measured: false   # new family: art is refused until its colours are measured (--allow-unmeasured)",
        f"    company_label: {q(label)}",
        f'    canvas: {{kind: flat, color: "{background}"}}',
        "    tokens:",
        f'      eyebrow: "{accent}"',
        f'      accent: "{accent}"',
        f'      accent_mid: "{accent}"',
        f'      accent_deep: "{accent}"',
        f'      gold_trace: "{accent}"',
        f'      plate_low: "{background}"',
        # icon ink and spark sit on the light icon card, so they take the dark background colour; measure before art
        f'      icon_ink: "{background}"',
        f'      icon_spark: "{background}"',
        f'      chip_key: {{bg: "{accent}"}}',
        f'      chip_attr: {{bg: "{tint}"}}',
        f'      bar: {{from: "{accent}", to: "{accent}", height: 6}}',
        f'      edge: {{color: "{accent}", opacity: 0.28}}',
    ]


def _block_org(name: str, family: str, tier: str, display: str) -> list[str]:
    q = lambda s: json.dumps(s, ensure_ascii=False)  # noqa: E731
    return [
        f"  {name}:",
        f"    family: {family}",
        "    former_slugs: []",
        f"    tier: {tier}",
        f"    display_name: {q(display)}",
        f"    nav_name: {q(display)}",
        "    description: null",
        "    eyebrow: null",
        "    brand_topic: null",
        "    family_topics: []",
        "    footer: hold   # decision 18 footer waits for real logo URLs; set true or false once decided",
    ]


def _insert_before(text: str, eol: str, anchor: str, block: list[str]) -> str:
    """Insert `block` above the top-level `anchor:` key. The block goes after the previous section's last entry and
    before the blank lines and column-0 comments that introduce `anchor:` (for example the "One row per owner" note)."""
    lines = text.split(eol)
    idx = next((i for i, line in enumerate(lines) if line == f"{anchor}:"), None)
    if idx is None:
        raise ShowcaseError(f"brand.yaml has no top-level `{anchor}:` section", log="config")
    j = idx
    while j > 0 and (lines[j - 1].strip() == "" or lines[j - 1].startswith("#")):
        j -= 1
    return eol.join(lines[:j] + block + lines[j:])


def _apply(args, action: str, section: str, anchor: str, block: list[str], check) -> tuple[dict, int]:
    b = load_brand(args.config)
    path = b.path
    with open(path, encoding="utf-8", newline="") as fh:
        old = fh.read()
    eol = "\r\n" if "\r\n" in old else "\n"
    new = _insert_before(old, eol, anchor, block)
    raw = load_yaml_text(new)
    errors = schema_errors(raw)
    if errors:
        raise ShowcaseError("brand.yaml would not validate, nothing written: " + "; ".join(errors[:5]),
                            log="brand-invalid")
    check(Brand(raw, path))  # builds the new family or org: a bad colour or missing key is refused before any write
    diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        f"a/{path.name}", f"b/{path.name}"))
    out = {"command": "brand", "action": action, "section": section, "config": str(path),
           "result": "written" if args.write else "dry-run", "diff": diff, "logs": [], "text": diff}
    if args.write:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
        if path == DEFAULT_CONFIG:  # the lock copy is the default config's only; an explicit --config leaves it alone
            LOCK.write_text(lock_text(raw), encoding="utf-8")
            out["lock"] = str(LOCK)
        else:
            out["lock"] = "not regenerated: --config names a file other than references/brand.yaml"
    else:
        out["next"] = "dry run: nothing written; repeat with --write to apply"
    return out, OK


def cmd_add_family(args):
    if not FAMILY_RE.match(args.name):
        raise ShowcaseError(f"family name {args.name!r}: use lowercase letters, digits and hyphens", log="usage")
    for label, value in (("--accent", args.accent), ("--background", args.background)):
        if not HEX_RE.match(value or ""):
            raise ShowcaseError(f"{label} {value!r} is not a #RRGGBB colour", log="usage")
    if not (args.company_label or "").strip():
        raise ShowcaseError("--company-label must not be empty", log="usage")
    bg_lum = luminance(args.background)
    if bg_lum > DARK_MAX:
        raise ShowcaseError(f"--background {args.background} is too light for a dark design (decision 21)", log="usage")
    existing = load_brand(args.config).raw.get("families", {})
    if args.name in existing:
        raise ShowcaseError(f"family {args.name!r} already exists in brand.yaml", log="usage")
    block = _block_family(args.name, args.company_label.strip(), args.accent, args.background)

    def check(brand: Brand):
        brand.family(args.name)  # raises ConfigError when the merged family cannot be built

    obj, code = _apply(args, "add-family", "families", "orgs", block, check)
    obj["family"] = args.name
    obj["accent_contrast"] = round(contrast(args.accent, args.background), 2)
    return obj, code


def cmd_add_org(args):
    if not ORG_RE.match(args.name):
        raise ShowcaseError(f"org login {args.name!r}: use letters, digits and single hyphens", log="usage")
    if not (args.display_name or "").strip():
        raise ShowcaseError("--display-name must not be empty", log="usage")
    raw = load_brand(args.config).raw
    if args.family not in raw.get("families", {}):
        raise ShowcaseError(f"family {args.family!r} is not in brand.yaml; run `brand add-family` first", log="usage")
    if any(name.lower() == args.name.lower() for name in raw.get("orgs", {})):
        raise ShowcaseError(f"org {args.name!r} already exists in brand.yaml", log="usage")
    block = _block_org(args.name, args.family, args.tier, args.display_name.strip())

    def check(brand: Brand):
        if brand.org(args.name).get("family") != args.family:
            raise ShowcaseError("the new org row did not resolve to its family", log="config")

    obj, code = _apply(args, "add-org", "orgs", "owners", block, check)
    obj["org"] = args.name
    obj["owners_edited"] = False
    return obj, code


def register(sub) -> None:
    p = sub.add_parser("brand", help="onboard a non-CompleteTech family or org into brand.yaml "
                                     "(dry run by default; --write applies)")
    bs = p.add_subparsers(dest="brand_action", required=True, metavar="{add-family,add-org}")

    f = bs.add_parser("add-family", help="add a dark family block (measured: false) to brand.yaml")
    f.add_argument("name", help="family key, e.g. acme-widgets")
    f.add_argument("--company-label", required=True, help="eyebrow company label, e.g. \"Acme Widgets\"")
    f.add_argument("--accent", required=True, help="accent colour #RRGGBB")
    f.add_argument("--background", required=True, help="dark canvas colour #RRGGBB")
    f.add_argument("--write", action="store_true", help="write brand.yaml and regenerate brand.lock.json")
    f.set_defaults(func=cmd_add_family)

    o = bs.add_parser("add-org", help="add an org row to brand.yaml (never edits owners:)")
    o.add_argument("name", help="org login, e.g. Acme-Widgets")
    o.add_argument("--family", required=True, help="an existing family key in brand.yaml")
    o.add_argument("--display-name", required=True)
    o.add_argument("--tier", choices=TIERS, default="T2")
    o.add_argument("--write", action="store_true", help="write brand.yaml and regenerate brand.lock.json")
    o.set_defaults(func=cmd_add_org)
