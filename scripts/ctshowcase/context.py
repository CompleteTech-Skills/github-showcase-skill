"""Everything a generator or check needs about one repository, assembled once."""
from __future__ import annotations

from pathlib import Path

from .config import Brand, load_repo_override, override_from_manifests
from .detect import detect
from .errors import ConfigError, NeedsInput
from .facts import RepoFacts


class RepoContext:
    def __init__(self, brand: Brand, meta: dict, repo_dir: str | Path | None = None, type_override: str | None = None):
        self.brand, self.meta = brand, meta
        self.repo_dir = Path(repo_dir) if repo_dir else None
        self.facts = RepoFacts(meta, repo_dir)
        self.override, self.override_sha = load_repo_override(repo_dir) if repo_dir else ({}, None)
        if not self.override and not repo_dir:
            # metadata only: the override `meta --from-gh` captured (either spelling), validated like a checkout's
            self.override = override_from_manifests(meta.get("manifests"))
        # GitHub logins are case-insensitive (an origin URL may be lower-cased): take the org's own spelling so every
        # literal org rule (README variant, nav line, R6, R9) matches. Only the case is fixed; a former login is not
        # rewritten here, since the rename may not have happened on GitHub yet (CQ-03).
        self.owner, self.repo = self._spelled(meta.get("owner", "unknown")), meta.get("repo", "unknown")
        scoped = (self.override or {}).get("for")
        if scoped and not self.same_repo(scoped):
            # overrides written for another repository (a template's own chips and subtitle) do not apply here
            self.override = {}
            self._scoped_away = scoped
        else:
            self._scoped_away = None
        self.org = brand.org(self.owner)
        self.style = brand.style(self.owner)
        self.det = detect(meta if self.owner == meta.get("owner") else dict(meta, owner=self.owner), self.facts,
                          self.override, type_override, same_owner=self.same_owner)
        self.logs: list[str] = []
        if not self.org.get("known"):
            self.log("needs-input:org-row")
        if type_override:
            self.log(f"type-override:{type_override}")
        elif self.override.get("type"):
            self.log(f"type-config:{self.override['type']}")
        if self._scoped_away:
            self.log(f"override-for:{self._scoped_away}")
        if self.det.get("provisional"):
            self.log("needs-input:file-tree")
        if meta.get("visibility") not in ("public", "private", "internal"):
            self.log("needs-input:visibility")

    def log(self, code: str):
        if code not in self.logs:
            self.logs.append(code)

    def _resolver(self):
        try:
            return self.brand.resolver()
        except Exception:  # noqa: BLE001 - no resolver data: plain, case-insensitive comparisons
            return None

    def _spelled(self, login: str) -> str:
        res = self._resolver()
        canon = res.canonical(login) if res and login else login
        return canon if canon and canon.lower() == (login or "").lower() else login

    def same_owner(self, a: str, b: str | None = None) -> bool:
        """True when two logins name the same org (any case, any former login; the shared resolver, CQ-03)."""
        b = self.owner if b is None else b
        res = self._resolver()
        return res.same(a, b) if res else bool(a and b) and a.lower() == b.lower()

    def same_repo(self, full_name: str) -> bool:
        """True when OWNER/REPO names this repository: the owner through the resolver, the name case-insensitively,
        or the slug an approved repository rename or transfer gives it (`Resolver.repo_before`)."""
        if not isinstance(full_name, str) or full_name.count("/") != 1:
            return False
        o, r = full_name.split("/")
        if r.lower() == str(self.repo).lower() and self.same_owner(o):
            return True
        res = self._resolver()
        for a, b in ((full_name, f"{self.owner}/{self.repo}"), (f"{self.owner}/{self.repo}", full_name)):
            hit = res.repo_before(a) if res else None
            if hit and res.repo_action_approved(hit[1]):
                ho, hr = hit[0].split("/", 1)
                bo, br = b.split("/", 1)
                if hr.lower() == br.lower() and self.same_owner(ho, bo):
                    return True
        return False

    # -- identity --------------------------------------------------------------------------------------
    @property
    def tier(self) -> str:
        return self.org.get("tier", "unknown")

    @property
    def company(self) -> str:
        """Alt-text company: CompleteTech LLC for T1, the §2.3 display name for T2."""
        if self.tier.startswith("T2") or self.tier == "T3":
            return self.org.get("display_name") or self.owner
        return self.brand.strings["company"]

    @property
    def public(self) -> bool:
        # an unknown visibility is treated as public (needs-input:visibility is logged): a public README is the
        # reversible choice; the internal callout and proprietary licence are only written for a known private repo
        return self.meta.get("visibility", "public") not in ("private", "internal")

    def require_measured(self, allow_unmeasured: bool):
        if not self.style.get("measured", True) and not allow_unmeasured:
            raise NeedsInput("palette-v1.1", f"family {self.style['name']} palette is not measured; pass --allow-unmeasured")

    def require_description(self) -> str:
        d = (self.meta.get("description") or "").strip()
        if not d:
            raise NeedsInput("description", "the repository has no description")
        return d

    # -- which generated surfaces apply ------------------------------------------------------------------
    @property
    def is_fork(self) -> bool:
        """Type rule 1 (GitHub's fork flag or a `-fork` slug, even under a repo-config type override) or a detected
        `fork` type: doctor, adopt, labels, the social preview and the watching-org rules all use this one test, and
        org labels and the estate proposals use rule 1 itself, so a fork is never a fork to only some of them."""
        from .detect import is_fork
        return is_fork(dict(self.meta, repo=self.repo)) or self.det["type"] == "fork"

    def social_applicable(self) -> bool:
        """R10: public product repositories, including the personal-profile capstone."""
        return (self.public and not self.meta.get("archived") and not self.is_fork and self.repo != ".github"
                and not self.repo.lower().endswith(".github.io")
                and self.tier in ("T1", "T1-user", "T2"))

    def art_status(self) -> dict:
        """{"banner": None | code, "card": None | code, "icon": None | code}: None when the surface applies, else why it
        does not (exempt:*, hold, t3-signoff). Shared by banner, card, lint all and doctor so they never disagree.

        Decisions 12, 13 and 18 (STANDARD R13, R14, R16): only watching-org forks skip the banner and the icon. Forks
        outside the watching org (G, q27), backups and archived repositories (H) and `.github` repositories (J) get the
        hero banner, their own icon and the footer; they have no card (§5.4). `CompleteDotTech/CompleteDotTech` opens
        with the intro instead of a banner, and a placeholder org's `.github` holds only its profile."""
        status = self.brand.owner_status(self.owner)
        out: dict = {"banner": None, "card": None, "icon": None}
        watching = self.watching_status()
        if watching == "exempt:watching-fork":
            return {"banner": "exempt", "card": "exempt", "icon": "exempt:watching-fork"}
        if watching:  # a watching-org repository that is not a fork and not its `.github`: decided explicitly
            return {"banner": watching, "card": watching, "icon": watching}
        if status in ("t3", "hold", "excluded"):
            code = {"t3": "t3-signoff", "hold": "hold", "excluded": "exempt"}[status]
            return {"banner": code, "card": code, "icon": code}
        if self.is_fork or self.det["type"] in ("backup", "github-profile"):
            out["card"] = "exempt:no-card"
        if self.det["type"] == "github-profile" and self.repo.lower() == self.owner.lower():
            out["banner"] = "exempt:profile-readme"  # the personal profile README opens with the intro (decision 15)
        if self.repo == ".github" and self.placeholder_org():
            out["banner"] = out["icon"] = "exempt:placeholder-org"
        if self.preserve_unchanged() and self.style.get("banner") == "keep-existing" and self.own_banner():
            out["banner"] = "exempt:keep-existing"  # only when q57 `pres` is "Leave them unchanged"
        if self.style.get("hold"):
            out = {k: v or "hold" for k, v in out.items()}
        return out

    def watching_status(self) -> str | None:
        """Decisions 12, 13 and 18 exempt only the watching org's forks (metadata only). Its `.github` gets the icon,
        banner and footer like any `.github` (J). Any other repository there that is not a fork (a detached upstream
        copy, or the user's own work) is held (`hold:watching-non-fork`) until decided explicitly: `--allow-hold` on a
        generator; nothing is exempted by owner alone. None outside the watching org."""
        if self.brand.owner_status(self.owner) != "watching":
            return None
        if self.is_fork:
            return "exempt:watching-fork"
        if self.repo == ".github":
            return None
        return "hold:watching-non-fork"

    def footer_status(self) -> str | None:
        """None when the decision 18 footer applies, else why not: `exempt:watching-fork`, `hold:watching-non-fork`,
        `t3-signoff`, `hold` (org row `footer: hold`) or `exempt:footer` (org row `footer: false`). The watching org's
        `footer: false` exempts only its forks (org.md), so its `.github` needs the footer."""
        if self.brand.owner_status(self.owner) == "t3":
            return "t3-signoff"
        watching = self.watching_status()
        if watching or self.brand.owner_status(self.owner) == "watching":
            return watching
        fv = self.org.get("footer", True)
        if fv is True:
            return None
        return "hold" if fv == "hold" else "exempt:footer"

    def preserve_unchanged(self) -> bool:
        """Review q57 `pres` = "Leave them unchanged": preserve-list READMEs get no hero banner (banner n/a)."""
        return self.brand.readme_opts.get("preserve_banner") == "unchanged"

    def placeholder_org(self) -> bool:
        try:
            return bool(self.brand.resolver().is_placeholder(self.owner))
        except Exception:  # no resolver data: not a placeholder
            return False

    def readme_text(self) -> str:
        if self.repo_dir is not None:
            p = self.repo_dir / "README.md"
            text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        else:
            text = self.meta.get("readme_head") or ""
        return text[1:] if text.startswith("\ufeff") else text  # a UTF-8 BOM is not part of the H1 (as readme.py)

    def own_banner(self) -> bool:
        """True when the README opens with its own banner image (not docs/images/banner.png, a logo or a badge)."""
        from .readme import _leading_banner, _strip_markers, split_sections
        body, _ = _strip_markers(self.readme_text().replace("\r\n", "\n"))
        pre, _ = split_sections(body)
        return _leading_banner(pre)

    # -- icons (A3.4) ----------------------------------------------------------------------------------
    def light_icon(self, cli_icon: str | None = None) -> tuple[Path | None, str]:
        """Icon for the light card surface (banner card and card tile). First match wins.

        Returns (None, "family-wordmark") for a non-CompleteTech family with no icon and no org mark: the caller
        typesets the family name instead (iconbox.wordmark); a T2 surface never carries the CompleteTech logo."""
        if cli_icon:
            p = Path(cli_icon)
            if not p.is_file():
                raise ConfigError(f"--icon not found: {cli_icon}")
            return p, "cli"
        if self.repo_dir is not None:
            rel = self.override.get("icon")
            if rel:
                p = self.repo_dir / rel
                if p.is_file():
                    return p, "override"
                self.log("needs-input:repo-icon")
            p = self.repo_dir / "assets" / "icon.png"
            if p.is_file():
                return p, "repo"
        self.log("needs-input:repo-icon")
        mark = self.brand.asset(self.org.get("mark"))
        if mark and mark.is_file():
            return mark, "org-mark"
        if self.style.get("name") != "completetech":
            return None, "family-wordmark"
        return self.brand.logo_light(), "brand-logo"

    def dark_mark(self) -> tuple[Path, str]:
        """Mark for navy surfaces: mark_dark when committed, else the full dark master (never cropped)."""
        m = self.brand.mark_dark()
        if m:
            return m, "mark-dark"
        self.log("needs-input:mark-dark")
        return self.brand.dark_master(), "dark-master"
