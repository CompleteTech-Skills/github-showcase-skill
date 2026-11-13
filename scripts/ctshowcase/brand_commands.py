"""Explicit, local-only onboarding of a brand family and organization."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from .color import best_fg, contrast, luminance
from .config import Brand, load_brand, load_yaml_text, lock_text, schema_errors, yaml
from .errors import ConfigError


def _colour(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ConfigError("palette inputs must be six-digit hex colours")
    return value.upper()


def family_row(brand: Brand, *, label: str, canvas: str, ink: str, accent: str,
               icon_ink: str | None = None, icon_spark: str | None = None) -> dict:
    """Derive every colour token; never inherit another business's palette."""
    canvas, ink, accent = map(_colour, (canvas, ink, accent))
    if not label.strip() or "\n" in label or "\r" in label:
        raise ConfigError("family label must be a non-empty single line")
    if luminance(canvas) > 0.18:
        raise ConfigError("canvas must be dark (decision 21)")
    if contrast(canvas, ink) < 4.5:
        raise ConfigError("ink needs at least 4.5:1 contrast against canvas")
    candidates = [ink, canvas, *brand.raw["contrast_candidates"]]
    chip_ink = best_fg(accent, candidates)
    if contrast(chip_ink, accent) < 4.5:
        raise ConfigError("accent needs a chip foreground with at least 4.5:1 contrast")
    # Both icon inks are measured against the dark icon card, with optional explicit values.
    icon_ink = _colour(icon_ink) if icon_ink else (accent if contrast(accent, canvas) >= 4.5 else ink)
    icon_spark = _colour(icon_spark) if icon_spark else ink
    if min(contrast(icon_ink, canvas), contrast(icon_spark, canvas)) < 4.5:
        raise ConfigError("icon ink and spark need at least 4.5:1 contrast against canvas")
    tokens = {k: ink for k in ("eyebrow", "title", "subtitle", "body", "muted", "card_ink", "card_edge", "signal_core")}
    tokens.update({k: canvas for k in ("ink", "plate_low", "card_fill")})
    tokens.update({k: accent for k in ("gold_trace", "accent", "accent_mid", "accent_deep")})
    tokens.update(icon_ink=icon_ink, icon_spark=icon_spark,
                  chip_key={"bg": accent, "fg": chip_ink}, chip_attr={"bg": canvas, "fg": ink},
                  bar={"from": accent, "to": accent, "height": 6}, edge={"color": accent, "opacity": 0.28},
                  card_shadow={"dx": 6, "dy": 8, "blur": 12, "color": canvas, "opacity": 0.35})
    return {"measured": False, "hold": False, "banner": "generate", "company_label": label.strip(),
            "eyebrow_case": "asis", "badge_brand": accent[1:], "badge_accent": accent[1:],
            "canvas": {"kind": "flat", "color": canvas}, "tokens": tokens}


def _new_org(brand: Brand, raw: dict, args) -> tuple[dict, tuple[Path, bytes] | None]:
    org = args.org
    if not org or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", org):
        raise ConfigError("org must be a GitHub login (1 to 39 letters, numbers or hyphens)")
    # The resolver prevents overwriting an old login or reclassifying a refused owner.
    if brand.org(org).get("known") or brand.owner_status(org):
        raise ConfigError("organization already exists or is reserved; onboarding cannot change its policy")
    family = args.name if args.brand_action == "add-family" else args.family
    if family not in raw["families"]:
        raise ConfigError("family must already exist (or be created by this add-family command)")
    if not args.display_name or not args.display_name.strip() or "\n" in args.display_name or "\r" in args.display_name:
        raise ConfigError("--display-name is required and must be a single line")
    if not args.tier or args.footer is None:
        raise ConfigError("--tier and --footer are required when adding an org")
    row = {"family": family, "tier": args.tier, "display_name": args.display_name.strip(),
           "nav_name": args.display_name.strip(), "brand_topic": None, "family_topics": [],
           "footer": {"yes": True, "no": False, "hold": "hold"}[args.footer]}
    mark = None
    if args.mark:
        source = Path(args.mark)
        try:
            data = source.read_bytes()
            from PIL import Image
            import io
            with Image.open(io.BytesIO(data)) as im:
                if im.format != "PNG":
                    raise ConfigError("mark must be a PNG; it is copied without conversion")
                im.verify()
        except (OSError, ValueError) as exc:
            raise ConfigError("mark must be a readable, valid PNG") from exc
        target = brand.path.resolve().parent.parent / "assets" / "orgs" / org / "mark.png"
        if target.exists():
            raise ConfigError("mark destination already exists; onboarding never overwrites assets")
        row["mark"] = f"assets/orgs/{org}/mark.png"
        mark = target, data
    return row, mark


def _append_mapping(text: str, key: str, name: str, row: dict) -> str:
    """Keep authored config comments and unrelated formatting while adding a mapping row."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if re.match(rf"^{re.escape(key)}:\s*(?:#.*)?$", line.rstrip())]
    if len(starts) != 1:
        raise ConfigError(f"{key} must use a block mapping before onboarding can append to it")
    end = next((i for i in range(starts[0] + 1, len(lines)) if re.match(r"^[A-Za-z_][A-Za-z_0-9-]*:", lines[i])), len(lines))
    entry = yaml.safe_dump({name: row}, sort_keys=False, allow_unicode=True)
    lines.insert(end, "".join("  " + line if line.strip() else line for line in entry.splitlines(keepends=True)) + "\n")
    return "".join(lines)


def cmd_brand(args):
    brand = load_brand(getattr(args, "config", None))
    original = brand.path.read_text(encoding="utf-8")
    raw = copy.deepcopy(brand.raw)
    text = original
    mark = None
    if not args.org and any(getattr(args, key, None) for key in ("tier", "display_name", "mark", "footer")):
        raise ConfigError("org-specific options require --org")
    if args.brand_action == "add-family":
        if not re.fullmatch(r"[a-z][a-z0-9-]*", args.name):
            raise ConfigError("family name must use lowercase letters, digits and hyphens")
        if args.name in raw["families"]:
            raise ConfigError("family already exists; onboarding never replaces a family")
        row = family_row(brand, label=args.label, canvas=args.canvas, ink=args.ink, accent=args.accent,
                         icon_ink=args.icon_ink, icon_spark=args.icon_spark)
        raw["families"][args.name] = row
        text = _append_mapping(text, "families", args.name, row)
    if args.org:
        row, mark = _new_org(brand, raw, args)
        raw["orgs"][args.org] = row
        text = _append_mapping(text, "orgs", args.org, row)
        if args.tier == "T3":
            raw["owners"]["t3"].append(args.org)
            # Keep the existing owner policy and render only its small mapping.
            match = re.search(r"(?ms)^owners:\s*\n.*?(?=^[A-Za-z_][A-Za-z_0-9-]*:|\Z)", text)
            if not match:
                raise ConfigError("owners must use a block mapping before onboarding a T3 org")
            replacement = yaml.safe_dump({"owners": raw["owners"]}, sort_keys=False, allow_unicode=True)
            text = text[:match.start()] + replacement + text[match.end():]
    elif args.brand_action == "add-org":
        raise ConfigError("--org is required")
    if load_yaml_text(text) != raw:
        raise ConfigError("could not preserve the configuration while appending onboarding rows")
    errs = schema_errors(raw)
    if errs:
        raise ConfigError("brand schema validation failed: " + "; ".join(errs))
    lock = brand.path.with_name("brand.lock.json")
    if args.write:
        # All input/schema checks finish before the first write. Roll back on a filesystem failure.
        old_lock = lock.read_bytes() if lock.exists() else None
        mark_created = False
        try:
            if mark:
                mark[0].parent.mkdir(parents=True, exist_ok=True)
                with mark[0].open("xb") as stream:
                    mark_created = True
                    stream.write(mark[1])
            brand.path.write_text(text, encoding="utf-8")
            lock.write_text(lock_text(raw), encoding="utf-8")
        except OSError as exc:
            brand.path.write_text(original, encoding="utf-8")
            if old_lock is not None:
                lock.write_bytes(old_lock)
            elif lock.exists():
                lock.unlink()
            if mark_created and mark[0].exists():
                mark[0].unlink()
            raise ConfigError("onboarding write failed; previous configuration restored") from exc
    return {"command": "brand", "action": args.brand_action, "result": "written" if args.write else "planned",
            "family": args.name if args.brand_action == "add-family" else args.family, "org": args.org,
            "config": str(brand.path), "lock": str(lock), "logs": ["palette-unmeasured"],
            "proposed": {"family": raw["families"].get(getattr(args, "name", None)),
                         "org": raw["orgs"].get(args.org)}}, 0


def register(sub) -> None:
    """Register the local onboarding group on showcase.py."""
    parser = sub.add_parser("brand", help="locally scaffold brand families and orgs (dry run until --write)")
    actions = parser.add_subparsers(dest="brand_action", required=True)
    family = actions.add_parser("add-family", help="derive an isolated dark palette, optionally adding its org")
    family.add_argument("--name", required=True)
    family.add_argument("--label", required=True)
    for key in ("canvas", "ink", "accent"):
        family.add_argument("--" + key, required=True)
    family.add_argument("--icon-ink")
    family.add_argument("--icon-spark")
    org = actions.add_parser("add-org", help="add an org to an existing family")
    org.add_argument("--family", required=True)
    for item in (family, org):
        item.add_argument("--org")
        item.add_argument("--tier", choices=("T1", "T1-user", "T2", "T2-R", "T3"))
        item.add_argument("--display-name")
        item.add_argument("--mark", help="copy this authorized PNG unchanged into assets/orgs/ORG/mark.png")
        item.add_argument("--footer", choices=("yes", "no", "hold"), help="explicit owner footer policy")
        item.add_argument("--write", action="store_true", help="write the validated local config, lock and optional mark")
        item.set_defaults(func=cmd_brand)
