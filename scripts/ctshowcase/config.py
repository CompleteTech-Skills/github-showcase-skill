"""Load brand.yaml (or its stdlib lock copy), merge family/org/repo layers, validate (spec A3)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from . import REFERENCES, ROOT
from .color import best_fg
from .errors import ConfigError, NeedsInput, Refused, ShowcaseError
from .schema import validate

try:  # pyyaml is optional for stdlib-only commands (meta, fingerprint)
    import yaml
except ImportError:  # pragma: no cover - exercised in the Action before pip install
    yaml = None

DEFAULT_CONFIG = REFERENCES / "brand.yaml"
LOCK = REFERENCES / "brand.lock.json"


def load_yaml_text(text: str):
    if yaml is None:
        raise ConfigError("PyYAML is required for this command (pip install -r requirements.txt)")
    return yaml.safe_load(text)


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


_T3_SIGNED_OFF = False


def set_t3_signed_off(value: bool) -> None:
    """Record the run's `--allow-t3`: set once by the CLI, read by every owner gate (check_owner, art_status,
    footer_status). Off by default, so a T3 owner is refused unless the caller passes the flag after an approved
    t3-metadata or t3-signoff row."""
    global _T3_SIGNED_OFF
    _T3_SIGNED_OFF = bool(value)


def t3_signed_off(owner: str | None = None, repo: str | None = None) -> bool:
    """The run's `--allow-t3`. With an owner and `--require-t3-signoff`, also needs a valid sign-off record
    (ctshowcase/signoff.py); without the opt-in flag the answer is the bare flag, as before."""
    if owner is not None and _T3_SIGNED_OFF:
        from . import signoff
        return signoff.granted(owner, repo)
    return _T3_SIGNED_OFF


class Brand:
    """Merged view over brand.yaml."""

    def __init__(self, raw: dict, path: Path):
        self.raw, self.path = raw, path
        self.root = ROOT

    # -- identity ---------------------------------------------------------------------------------
    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical(self.raw).encode()).hexdigest()

    @property
    def strings(self) -> dict:
        return self.raw["brand_strings"]

    @property
    def readme_opts(self) -> dict:
        """Review-page answers that shape README scaffolding (q57 nav and pres, q27); defaults are the page's."""
        return {"nav_first": False, "preserve_banner": "above", "fork_readme": "note", **(self.raw.get("readme") or {})}

    # -- owners -----------------------------------------------------------------------------------
    _resolver = None  # built on first need: old and new org logins resolve alike in every command (COVERAGE CQ-03)

    def resolver(self):
        """The shared org resolver (ctshowcase.resolver) over this config's `former_slugs` and the approved org renames and
        merges beside the skill. The private registry is not loaded here (the `org` commands load it); a malformed
        approvals file leaves only the `former_slugs` renames, and the `org` commands report the error."""
        if self._resolver is None:
            from .resolver import Resolver, load_approvals
            try:
                self._resolver = Resolver(self, {}, load_approvals())
            except ShowcaseError:
                self._resolver = Resolver(self, {}, None)
        return self._resolver

    def aliases(self, owner: str) -> list[str]:
        """Every login of the owner's org: the current one first, then former ones (just `owner` when none is known)."""
        return self.resolver().aliases(owner) if owner else [owner]

    def owner_status(self, owner: str) -> str | None:
        owners = self.raw.get("owners", {})
        for login in self.aliases(owner):
            low = (login or "").lower()
            for status in ("excluded", "hold", "t3", "watching"):
                if low in {o.lower() for o in owners.get(status, [])}:
                    return status
        return None

    def check_owner(self, owner: str, *, allow_t3: bool = False, repo: str | None = None) -> str | None:
        """Raise Refused for excluded/hold/T3 owners; return 'watching' or None."""
        status = self.owner_status(owner)
        if status == "excluded":
            raise Refused(f"{owner} is an excluded owner; every command refuses", log="exempt")
        if status == "hold":
            raise Refused(f"{owner} is on HOLD", log="hold")
        if status == "t3" and not (allow_t3 or t3_signed_off()):
            raise Refused(f"{owner} is T3; needs co-owner sign-off", log="t3-signoff")
        if status == "t3" and t3_signed_off():
            from . import signoff
            signoff.require(owner, repo, self.aliases(owner))  # no-op unless --require-t3-signoff
        return status

    def org(self, owner: str) -> dict:
        orgs = self.raw.get("orgs", {})
        if owner in orgs:
            return dict(orgs[owner], owner=owner, known=True)
        for name, row in orgs.items():
            if name.lower() == owner.lower():
                return dict(row, owner=name, known=True)
        for login in self.aliases(owner) if owner else ():  # a renamed org keeps its row under any login (CQ-03)
            for name, row in orgs.items():
                if login.lower() != owner.lower() and name.lower() == login.lower():
                    return dict(row, owner=name, known=True)
        return {"owner": owner, "family": "completetech", "tier": "unknown", "display_name": owner, "nav_name": owner,
                "eyebrow": None, "brand_topic": "completetech", "family_topics": [], "footer": True, "known": False}

    # -- families ---------------------------------------------------------------------------------
    def family(self, name: str) -> dict:
        fams = self.raw.get("families", {})
        if name not in fams:
            raise ConfigError(f"unknown family {name!r}")
        own = fams[name] or {}
        fam = deep_merge(self.raw.get("defaults", {}), own)
        for chip in ("chip_key", "chip_attr"):  # a family that sets a chip bg without fg gets a computed fg
            oc = (own.get("tokens") or {}).get(chip) or {}
            if oc.get("bg") and not oc.get("fg"):
                fam["tokens"][chip].pop("fg", None)
        fam["name"] = name
        cands = list(self.raw.get("contrast_candidates", []))
        tokens = fam["tokens"]
        for chip in ("chip_key", "chip_attr"):
            c = tokens[chip]
            if not c.get("fg"):
                c["fg"] = best_fg(c["bg"], [tokens["title"], *cands])
        return fam

    def style(self, owner: str) -> dict:
        org = self.org(owner)
        fam = self.family(org.get("family", "completetech"))
        if org.get("banner"):
            fam["banner"] = org["banner"]
        return fam

    # -- assets -----------------------------------------------------------------------------------
    def asset(self, rel: str | None) -> Path | None:
        if not rel:
            return None
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    def font_file(self, key: str) -> Path:
        fonts = self.raw["fonts"]
        if key not in fonts:
            raise ConfigError(f"unknown font key {key!r}")
        return self.root / "assets" / "fonts" / fonts[key]

    def dark_master(self) -> Path:
        ba = self.raw["brand_assets"]
        rel = ba["logo_dark_candidate"] if ba.get("dark_master") == "candidate" else ba["logo_dark"]
        return self.asset(rel)

    def mark_dark(self) -> Path | None:
        p = self.asset(self.raw["brand_assets"].get("mark_dark"))
        return p if p and p.is_file() else None

    def mark_light(self) -> Path | None:
        """Cloud-and-bulb crop of the light logo for icon boxes under 200 px (committed file; never cropped at runtime)."""
        p = self.asset(self.raw["brand_assets"].get("mark_light"))
        return p if p and p.is_file() else None

    def logo_light(self) -> Path:
        return self.asset(self.raw["brand_assets"]["logo_light"])


def load_brand(path: str | Path | None = None, *, prefer_lock: bool = False) -> Brand:
    path = Path(path) if path else DEFAULT_CONFIG
    if (prefer_lock or yaml is None) and path == DEFAULT_CONFIG and LOCK.is_file():
        return Brand(json.loads(LOCK.read_text(encoding="utf-8")), path)
    if not path.is_file():
        raise ConfigError(f"config not found: {path}")
    raw = load_yaml_text(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("brand config must be a mapping")
    return Brand(raw, path)


def _box(v, size: tuple[int, int], key: str) -> tuple[int, int, int, int]:
    if not (isinstance(v, list) and len(v) == 4 and all(isinstance(x, int) and not isinstance(x, bool) for x in v)):
        raise ConfigError(f"brand_assets.crops.{key} must be [x0, y0, x1, y1] integers, got {v!r}")
    x0, y0, x1, y1 = v
    if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
        raise ConfigError(f"brand_assets.crops.{key} {v} lies outside the {size[0]}x{size[1]} dark master")
    return x0, y0, x1, y1


def write_crops(brand: "Brand") -> dict:
    """`config --crop`: write mark_dark (cloud and bulb) and bulb_dark (bulb only, masked) from the measured boxes in
    brand_assets.crops on the dark master (STANDARD §9.2). The only crops the estate ever makes; never at render time."""
    from PIL import Image
    ba = brand.raw["brand_assets"]
    c = ba.get("crops") or {}
    if not c.get("measured") or c.get("mark_dark") is None:
        raise NeedsInput("brand-crops", "brand_assets.crops is not measured: re-measure the boxes on the q26 dark master "
                                        "(Phase 0.12), set measured: true, then run config --crop")
    master = brand.dark_master()
    with Image.open(master) as src:
        im = src.convert("RGBA")
    out: dict = {"master": str(master.relative_to(brand.root)) if master.is_relative_to(brand.root) else str(master)}
    for key in ("mark_dark", "bulb_dark"):
        if c.get(key) is None:
            out[key] = None
            continue
        crop = im.crop(_box(c[key], im.size, key))
        if key == "bulb_dark":
            m = {"b_min": 150, "r_max": 80, "b_minus_g_min": 20, **(c.get("bulb_mask") or {})}
            get = getattr(crop, "get_flattened_data", None)  # Pillow 13 deprecates getdata
            crop.putdata([(r, g, b, 0) if b >= m["b_min"] and r <= m["r_max"] and b - g >= m["b_minus_g_min"]
                          else (r, g, b, a) for r, g, b, a in (get() if get else crop.getdata())])
        dest = brand.asset(ba.get(key) or f"assets/brand/{key.replace('_', '-')}.png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        crop.save(dest, optimize=True)
        out[key] = {"path": str(dest.relative_to(brand.root)) if dest.is_relative_to(brand.root) else str(dest),
                    "box": list(c[key]), "size": list(crop.size), "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()}
    return out


def schema_errors(raw: dict) -> list[str]:
    schema = json.loads((REFERENCES / "brand.schema.json").read_text(encoding="utf-8"))
    return validate(raw, schema)


def lock_text(raw: dict) -> str:
    return json.dumps(raw, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def lock_in_sync(brand: Brand) -> bool:
    return LOCK.is_file() and LOCK.read_text(encoding="utf-8") == lock_text(brand.raw)


# -- repo override file (.github/showcase.yml, A3.5) -------------------------------------------------
REPO_CONFIG_NAMES = (".github/showcase.yml", ".github/showcase.yaml")


def load_repo_override(repo_dir: str | Path | None) -> tuple[dict, str | None]:
    """Return (override, sha256-of-file|None). Colours and fonts are rejected by the schema."""
    if not repo_dir:
        return {}, None
    for name in REPO_CONFIG_NAMES:
        p = Path(repo_dir) / name
        if p.is_file():
            data = p.read_bytes()
            return parse_repo_override(name, data.decode("utf-8")), hashlib.sha256(data).hexdigest()
    return {}, None


def parse_repo_override(name: str, text: str) -> dict:
    """One repository override file's text, parsed and checked against repo-config.schema.json (colours and fonts are
    rejected). Shared by the checkout and the metadata-only path (`manifests`), so both read the same override."""
    obj = load_yaml_text(text) or {}
    if not isinstance(obj, dict):
        raise ConfigError(f"{name} must be a mapping")
    schema = json.loads((REFERENCES / "repo-config.schema.json").read_text(encoding="utf-8"))
    errs = validate(obj, schema)
    if errs:
        raise ConfigError(f"{name}: " + "; ".join(errs), log="config")
    return obj


def override_from_manifests(manifests: dict | None) -> dict:
    """The repository override captured in metadata (`meta --from-gh` manifests), first of REPO_CONFIG_NAMES found."""
    for name in REPO_CONFIG_NAMES:
        text = (manifests or {}).get(name)
        if isinstance(text, str) and text.strip():
            return parse_repo_override(name, text)
    return {}
