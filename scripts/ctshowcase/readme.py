"""README scaffold / upgrade / header / bootstrap per STANDARD §7 with decision 13 header order (spec A6.6).

Generated blocks sit between `<!-- showcase:<block>:start -->` / `:end -->` markers so reruns replace only
those blocks. Content is never invented (§1.5 rule 2) and never lost (§7.1 restructuring, multiset check).
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict, deque
from html import escape
from pathlib import Path
from urllib.parse import quote

from . import footer as footermod
from . import tagline as taglinemod
from .context import RepoContext
from .detect import required_sections, standard
from .errors import ArtFail, ConfigError, NeedsInput
from .mdcode import (  # noqa: F401  (code_spans: re-exported for callers)
    MANAGED_BLOCK_PATTERN, _image_entries, after_line_end, code_block_spans, code_spans, find_blocks, html_block_spans,
    masked, top_level_heading_spans,
)

MARK = MANAGED_BLOCK_PATTERN
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
SHIELDS = "https://img.shields.io/badge/"
GENERATED_BADGES = re.compile(r"<!-- showcase:badges:generated sha256=([0-9a-f]{64})"
                              r"(?: replaces=([0-9a-f]{64}))? -->(?:\r\n|\r|\n)(.*)", re.S)
BOM = "\ufeff"
MANAGED_NOTICE = re.compile(r"\b(?:generated\s+by|do\s+not\s+edit)\b", re.I)
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_text(text: str) -> str:
    """README text as the tools read it: LF line endings, no leading UTF-8 byte order mark (a BOM would hide the H1
    from every `^#` match)."""
    text = normalize_line_endings(text)
    return text[1:] if text.startswith(BOM) else text


def source_lines(text: str) -> list[str]:
    """Split only at Markdown line endings, keeping other source characters."""
    lines = normalize_line_endings(text).split("\n")
    if not lines[-1]:
        lines.pop()
    return lines


def start(b):
    return f"<!-- showcase:{b}:start -->"


def end(b):
    return f"<!-- showcase:{b}:end -->"


def wrap(b, body):
    return f"{start(b)}\n{body}\n{end(b)}"


# ------------------------------------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------------------------------------
def shield(s: str) -> str:
    """A shields.io path segment: `-`/`_` doubled, then percent-encoded, so `#`, `?`, `/` and `%` (C#, F#) stay in
    the segment instead of ending the path."""
    return quote(s.replace("-", "--").replace("_", "__"), safe="()!*'.,;:@&=$~")


def title_case(s: str) -> str:
    rv = standard("readme-variants")
    small, keep = set(rv["title_small_words"]), {k.lower(): k for k in rv["title_keep_case"]}
    out = []
    for i, w in enumerate(re.split(r"(\s+)", s)):
        if not w.strip():
            out.append(w)
            continue
        low = w.lower()
        if low in keep:
            out.append(keep[low])
        elif i > 0 and low in small:
            out.append(low)
        else:
            out.append(w[:1].upper() + w[1:])
    return "".join(out)


def slug_title(slug: str) -> str:
    """Title from a slug; CVE ids keep their form ("acme-cve-2026-12345-check" -> "Acme CVE-2026-12345 Check")."""
    cves: list[str] = []

    def keep(m):
        cves.append(m.group(0).upper())
        return f"\x00{len(cves) - 1}\x00"
    s = re.sub(r"cve-\d{4}-\d+", keep, slug, flags=re.I)
    t = title_case(s.replace("-", " ").replace("_", " "))
    return re.sub(r"\x00(\d+)\x00", lambda m: cves[int(m.group(1))], t)


def cased_title(slug: str, description: str = "") -> str:
    """slug_title, with each word spelled the way the repository's own description spells it when that spelling is
    a deliberate one (mixed case, such as PHP2Shell or OpenClaw), so a brand name is never re-cased to "Php2shell"."""
    spelled = {}
    for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9+#]*", description or ""):
        if tok != tok.lower() and tok != tok[:1].upper() + tok[1:].lower():
            spelled.setdefault(tok.lower(), tok)
    return re.sub(r"[A-Za-z0-9][A-Za-z0-9+#]*", lambda m: spelled.get(m.group(0).lower(), m.group(0)), slug_title(slug))


def product_name(ctx: RepoContext) -> str:
    return ctx.facts.h1() or cased_title(ctx.repo, ctx.meta.get("description") or "")


def split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(preamble, [(heading text, body)]) split at H2 outside code fences."""
    pre, sections, cur_h, buf = [], [], None, []
    for line, visible in zip(source_lines(text), source_lines(masked(text)), strict=True):
        if re.match(r"^## (?!#)", visible):
            if cur_h is None:
                pre = buf
            else:
                sections.append((cur_h, "\n".join(buf)))
            cur_h, buf = line[3:].strip(), []
            continue
        buf.append(line)
    if cur_h is None:
        return "\n".join(buf), []
    sections.append((cur_h, "\n".join(buf)))
    return "\n".join(pre), sections


# ------------------------------------------------------------------------------------------------
# Header pieces
# ------------------------------------------------------------------------------------------------
def nav_line(ctx: RepoContext) -> str:
    org, owner = ctx.org, ctx.brand.resolver().canonical(ctx.owner)  # links name the org's current login (CQ-03)
    if ctx.same_owner("CompleteTech-Skills") and ctx.det["type"] == "agent-skills":
        line = ("**CompleteTech LLC Skills** · [Start here](ONBOARDING.md) · [Agent instructions](SKILL.md) · "
                "[Skill library](https://github.com/CompleteTech-Skills/agentic-services-orchestrator-skill/blob/main/"
                "references/skill-family.md) · [Contributing](CONTRIBUTING.md)")
        return line + (" · Internal" if not ctx.public else "")
    f = ctx.facts
    contrib = "CONTRIBUTING.md" if f.exists("CONTRIBUTING.md") else f"https://github.com/{owner}/.github/blob/main/CONTRIBUTING.md"
    sec = "SECURITY.md" if f.exists("SECURITY.md") else f"https://github.com/{owner}/.github/blob/main/SECURITY.md"
    if ctx.det["variant"] == "F":
        items = [f"**{org.get('nav_name') or org.get('display_name')}**", f"[All checkers](https://github.com/{owner})"]
        if f.exists("docs/REFERENCE.md"):
            items.append("[Reference](docs/REFERENCE.md)")
        if f.is_file("LICENSING.md"):
            items.append("[Licensing](LICENSING.md)")
        items.append(f"[Security]({sec})")
        return " · ".join(items)
    items = [f"**{org.get('nav_name') or org.get('display_name') or owner}**", f"[All repositories](https://github.com/{owner})"]
    hp = ctx.meta.get("homepage") or ""
    if ctx.det["variant"] == "B" and hp and ctx.meta.get("homepage_status") == 200:
        items.append(f"[Live site]({hp})")
    if ctx.det["variant"] == "E" and hp and ctx.meta.get("homepage_status") == 200:
        items.append(f"[Play]({hp})")
    docs = [x for x in f.files if x.startswith("docs/") and not re.search(r"\.(png|jpe?g|gif|webp|svg)$|/\.", x)] if f.known else []
    if docs:
        items.append("[Docs](docs/)")
    items += [f"[Contributing]({contrib})", f"[Security]({sec})"]
    line = " · ".join(items)
    return line + (" · Internal" if not ctx.public else "")


def personal_profile(ctx: RepoContext) -> bool:
    """Use the same personal-profile exemption as banner generation (decision 15, CQ-03)."""
    return ctx.personal_profile


def personal_intro_applies(ctx: RepoContext) -> bool:
    """The banner surface is exempt only because this is the personal profile, which opens with its intro instead."""
    return ctx.art_status()["banner"] == "exempt:profile-readme"


def hero_path(ctx: RepoContext) -> str:
    return "assets/intro.svg" if personal_profile(ctx) else "docs/images/banner.png"


def legacy_banner_html(ctx: RepoContext, repo: str | None = None) -> str:
    """The exact previously generated body; a similar authored image is not ours to migrate."""
    return f'<p align="center">\n  <img src="docs/images/banner.png" alt="{repo or ctx.repo} by {ctx.company}" width="100%">\n</p>'


def personal_intro_html(ctx: RepoContext) -> str:
    profile = ctx.org.get("profile") or {}
    name = profile.get("name") or ctx.org.get("display_name")
    if not ctx.org.get("known") or not (name or "").strip() or not (profile.get("eyebrow") or "").strip():
        raise NeedsInput("intro-identity", "Configure the personal profile name and eyebrow in brand.yaml first.")
    return f'<p align="center">\n  <img src="assets/intro.svg" alt="{escape(name, quote=True)}" width="100%">\n</p>'


def personal_generated_hero(ctx: RepoContext, body: str) -> bool:
    if body == legacy_banner_html(ctx) or not body.strip(" \t\n\r"):
        return True
    legacy = re.search(r' alt="([A-Za-z0-9-]+) by ', body)
    if legacy and body == legacy_banner_html(ctx, legacy.group(1)) and ctx.same_owner(legacy.group(1)):
        return True
    try:
        if body == personal_intro_html(ctx):
            return True
        if re.fullmatch(r'<p align="center">\n  <img src="assets/intro\.svg" alt="[^"\n]*" width="100%">\n</p>', body):
            raise NeedsInput("intro-identity", "Cannot establish ownership of the existing intro hero.")
        return False
    except NeedsInput:
        if "assets/intro.svg" in body:
            raise  # this may be our generated hero; ownership is unresolved
        return False


def banner_html(ctx: RepoContext) -> str:
    if not personal_profile(ctx):
        return legacy_banner_html(ctx)
    body = personal_intro_html(ctx)
    path = ctx.repo_dir / hero_path(ctx) if ctx.repo_dir is not None else None
    if path is None or path.parent.is_symlink() or path.is_symlink() or not path.is_file():
        raise NeedsInput("intro", "Generate the personal profile with intro --profile OWNER --out assets/intro.svg "
                         "as a regular file in the checkout.")
    # Matching the current default generator output establishes applicability, not asset rights.
    # Explicit generator overrides cannot be inferred from an SVG and require separate review.
    from . import intro, svglint
    from .typeset import Fonts
    try:
        if path.resolve() != path.parent.parent.resolve() / "assets" / "intro.svg":
            raise ValueError("intro is outside the checkout's assets directory")
        raw = path.read_bytes()
        if svglint.lint_bytes("intro", raw, str(path))["result"] != "PASS":
            raise ValueError("invalid intro")
        profile = ctx.org.get("profile") or {}
        chips = []
        for chip in profile.get("chips") or []:
            kind, _, value = chip.partition(":")
            if kind not in ("key", "attr") or not value:
                raise ValueError("invalid chips")
            chips.append((value, kind))
        complete = ctx.org.get("family") == "completetech"
        mark = (ctx.brand.mark_dark() or ctx.brand.dark_master()) if complete else ctx.brand.asset(ctx.org.get("mark"))
        tagline = profile.get("tagline") or (ctx.brand.strings["tagline"] if complete else None)
        if not mark or not tagline:
            raise ValueError("missing profile facts")
        name = profile.get("name") or ctx.org.get("display_name")
        fonts = Fonts(ctx.brand)
        variants = (False, True) if ctx.org.get("flagship") else (True,)
        if not any(raw == intro.build(ctx.brand, fonts, owner=ctx.owner, name=name,
                                      eyebrow=profile["eyebrow"], tagline=tagline, chips=chips,
                                      mark_path=mark, height=height, static=static).encode()
                   for height in (320, 360) for static in variants):
            raise ValueError("intro does not match configured profile")
    except (OSError, ValueError, KeyError, TypeError, ArtFail):
        raise NeedsInput("intro", "Generate an applicable default profile intro with showcase.py first.") from None
    return body


def license_facts(ctx: RepoContext) -> tuple[str | None, bool]:
    """Select captured SPDX and supported dual-license policy for both README surfaces.

    Visibility and variant describe presentation, not licensing. Legal prose is kept
    verbatim elsewhere; it is never parsed into a license or a commercial grant.
    """
    lic = ctx.meta.get("license")
    if lic is not None and not isinstance(lic, str):
        raise NeedsInput("license", "license identifier must be a string")
    lic = lic.strip() if lic else None
    if not lic or lic in ("NOASSERTION", "other"):
        lic = None
        ctx.log("needs-input:license")
    if lic and not ctx.facts.is_file("LICENSE"):
        ctx.log("needs-input:license-file")
    private_wording = ctx.org.get("private_license_wording")
    if (not ctx.public and lic and isinstance(private_wording, str)
            and re.search(r"\bproprietary\b", private_wording, re.I)
            and lic.lower() != "proprietary"):
        ctx.log("needs-input:license-policy")
    chip = ctx.org.get("license_chip")
    requested = ctx.public and (ctx.det["variant"] == "F" or bool(chip))
    dual = False
    if requested and lic:
        if lic.upper() not in ("AGPL-3.0", "AGPL-3.0-ONLY", "AGPL-3.0-OR-LATER") or chip != "AGPL-3.0 or commercial":
            ctx.log("needs-input:license-policy")
        else:
            if not ctx.facts.is_file("LICENSING.md"):
                ctx.log("needs-input:licensing-file")
            dual = ctx.facts.is_file("LICENSE") and ctx.facts.is_file("LICENSING.md")
    return lic, dual


def license_reference(ctx: RepoContext) -> str:
    """Never cite a LICENSE whose presence the input does not establish."""
    return "; see `LICENSE`." if ctx.facts.is_file("LICENSE") else "."


def badges(ctx: RepoContext) -> list[tuple[str, str, str | None]]:
    """[(alt, image url, link)] per §7.2: language, type, license, CI. 2-4."""
    b = dict(ctx.brand.raw["badges"])
    for k in ("brand", "accent"):  # a family outside CompleteTech carries its own badge colours (brand.yaml badge_brand, badge_accent)
        if ctx.style.get(f"badge_{k}"):
            b[k] = ctx.style[f"badge_{k}"]
    jev = ctx.style["name"] == "jevplay-games"
    extra = "?labelColor=1E1E1E" if jev else ""
    out = []
    f, lang = ctx.facts, ctx.meta.get("language")
    py, node = f.requires_python(), f.engines_node()
    if lang == "Python" and py:
        out.append((f"Python {py}+", f"{SHIELDS}python-{shield(py + '+')}-{b['accent']}?logo=python&logoColor=white", None))
    elif lang in ("JavaScript", "TypeScript") and node:
        out.append((f"Node {node}+", f"{SHIELDS}node-{shield(node + '+')}-{b['accent']}?logo=nodedotjs&logoColor=white", None))
    elif lang:
        out.append((f"Language {lang}", f"{SHIELDS}language-{shield(lang)}-{b['accent']}{extra}", None))
    if ctx.det["type"] == "agent-skills":
        topics = set(ctx.meta.get("topics") or [])
        rt = [n for t, n in (("claude-skill", "Claude"), ("codex-skill", "Codex")) if t in topics] or ["Claude", "Codex"]
        out.append(("Agent skill", f"{SHIELDS}agent%20skill-{shield(' | '.join(rt))}-{b['brand']}", None))
    else:
        category = standard("types")["types"][ctx.det["type"]].get("badge_category", ctx.det.get("category"))
        if category:
            out.append((f"Type {category}", f"{SHIELDS}type-{shield(category)}-{b['brand']}{extra}", None))
    lic, dual = license_facts(ctx)
    if dual:
        out.append(("AGPL-3.0 or commercial license", f"{SHIELDS}license-{shield('AGPL-3.0 | commercial')}-{b['neutral']}",
                    "LICENSING.md"))
    elif lic:
        out.append((f"License {lic}", f"{SHIELDS}license-{shield(lic)}-{b['neutral']}{extra}", None))
    if ctx.public and f.known:
        wf = sorted(x for x in f.files if x.startswith(".github/workflows/") and x.endswith((".yml", ".yaml")))
        pick = [x for x in wf if "test" in x.rsplit("/", 1)[-1]] or [x for x in wf if "ci" in x.rsplit("/", 1)[-1]]
        if pick:
            name = pick[0].rsplit("/", 1)[-1]
            base = f"https://github.com/{ctx.brand.resolver().canonical(ctx.owner)}/{ctx.repo}/actions/workflows/{name}"
            out.append(("Tests" if "test" in name else "CI", f"{base}/badge.svg", base))
    return out[:4]


def _local(ctx, url: str) -> str:
    """--badges local: render a shields.io badge URL to docs/images/badges/<slug>.svg (outlined text, no server)."""
    if not getattr(ctx, "local_badges", False) or not url.startswith(SHIELDS):
        return url
    from urllib.parse import unquote
    path = url[len(SHIELDS):].split("?", 1)[0]
    parts = re.split(r"(?<!-)-(?!-)", path)
    label, message, colour = (unquote(x).replace("--", "-").replace("__", "_") for x in (parts[0], "-".join(parts[1:-1]), parts[-1]))
    slug = re.sub(r"[^a-z0-9]+", "-", f"{label}-{message}".lower()).strip("-")
    rel = f"docs/images/badges/{slug}.svg"
    ctx.badge_files = getattr(ctx, "badge_files", {})
    ctx.badge_files[rel] = (label, message, "#" + colour)
    return rel


def badges_md(ctx) -> str:
    lines = []
    for alt, url, link in badges(ctx):
        url = _local(ctx, url)
        img = f"![{alt}]({url})"
        lines.append(f"[{img}]({link})" if link else img)
    return "\n".join(lines)


def badges_html(ctx) -> str:
    parts = []
    for alt, url, link in badges(ctx):
        url = _local(ctx, url)
        img = f'<img src="{url}" alt="{alt}">'
        parts.append(f'  <a href="{link}">{img}</a>' if link else f"  {img}")
    return '<p align="center">\n' + "\n".join(parts) + "\n</p>"


def _eol_normalized(body: str) -> str:
    """Line endings unified to LF and only the surrounding newline separators removed; spaces and tabs are kept
    because they are significant (an indented row is Markdown code, not the inherited template)."""
    return body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _legacy_badge_body(brand, body: str, style: dict | None = None, *, ci_matches=None) -> bool:
    return (legacy_profile_badges(brand, body, style, ci_matches=ci_matches)
            or _eol_normalized(body) in template_badge_bodies(brand))


def _legacy_ci_matches(ctx, owner: str, repo: str) -> bool:
    if ctx.same_repo(f"{owner}/{repo}"):
        return True
    # A personal profile repository can have the former account's spelling.
    return (repo.casefold() == owner.casefold() and ctx.same_owner(owner)
            and ctx.same_owner(ctx.owner, ctx.repo))


def badge_body(ctx: RepoContext, existing: str | None = None) -> str:
    """Refresh owned rows; a missing or changed digest makes a J block authored."""
    if ctx.det["variant"] != "J":
        return badges_html(ctx) if ctx.det["variant"] == "F" else badges_md(ctx)
    is_legacy = _legacy_badge_body(ctx.brand, existing or "", ctx.style,
                                  ci_matches=lambda owner, repo: _legacy_ci_matches(ctx, owner, repo))
    has_license_row = "![License " in (existing or "") or "![AGPL-3.0 or commercial license]" in (existing or "")
    metadata_license = ctx.meta.get("license")
    license_unknown = metadata_license is None or (
        isinstance(metadata_license, str) and metadata_license.upper() in ("", "NOASSERTION", "OTHER")
    )
    if is_legacy and has_license_row and ctx.public and license_unknown:
        return existing  # missing metadata cannot disprove an authored license claim
    if existing and existing.strip(" \t\r\n") and not generated_badges(existing) and not is_legacy:
        return existing
    body = badges_md(ctx)
    previous = GENERATED_BADGES.fullmatch(existing or "")
    # Record the exact prior body for the preservation check to independently verify.
    replaced_digest = badge_sha(existing) if is_legacy else previous.group(2) if previous else None
    replaces = f" replaces={replaced_digest}" if replaced_digest else ""
    return f"<!-- showcase:badges:generated sha256={badge_sha(body)}{replaces} -->\n{body}"


def template_badge_body(brand) -> str:
    """The exact inherited type row from the repository template, independent of body state."""
    category = standard("types")["types"]["template"]["category"]
    return f"![Type {category}]({SHIELDS}type-{shield(category)}-{brand.raw['badges']['brand']})"


def template_badge_bodies(brand) -> tuple[str, str]:
    """The inherited type row in its remote form and its exact `--badges local` equivalent."""
    category = standard("types")["types"]["template"]["category"]
    slug = re.sub(r"[^a-z0-9]+", "-", f"type-{category}".lower()).strip("-")
    return template_badge_body(brand), f"![Type {category}](docs/images/badges/{slug}.svg)"


def legacy_profile_badges(brand, body: str, style: dict | None = None, *, ci_matches=None) -> bool:
    """Recognize the old generator's ordered language/license/CI rows without today's metadata.

    A type row, custom markup, altered alt/URL pair or duplicate kind makes the block authored.
    Both historical remote and local badge paths are accepted.
    """
    lines = _eol_normalized(body).split("\n")
    if not 1 <= len(lines) <= 3:
        return False
    kinds = []
    colors = dict(brand.raw["badges"])
    family = {k: (style or {}).get(f"badge_{k}") for k in ("brand", "accent")}
    for line in lines:
        linked = line.startswith("[![")
        if not (linked or line.startswith("![")) or not line.endswith(")"):
            return False
        alt, marker, target = line[3 if linked else 2:-1].partition("](")
        if not marker or not alt or "]" in alt or not target:
            return False
        if linked:
            # The legacy generator uses this exact separator. Scan once from
            # the right to preserve the preceding URL without regex backtracking.
            url, delimiter, link = target.rpartition(")](")
            if not delimiter or not url or not link:
                return False
        else:
            url, link = target, None
        suffixes = ["", "?labelColor=1E1E1E"]
        expected_link = None
        if alt.startswith("License ") and alt[8:]:
            kind, label, message, color = 1, "license", alt[8:], colors["neutral"]
        elif alt == "AGPL-3.0 or commercial license":
            kind, label, message, color = 1, "license", "AGPL-3.0 | commercial", colors["neutral"]
            expected_link = "LICENSING.md"
            suffixes = [""]
        elif alt.startswith("Language ") and alt[9:]:
            kind, label, message, color = 0, "language", alt[9:], colors["accent"]
        elif re.fullmatch(r"Python \d+\.\d+\+", alt):
            kind, label, message, color = 0, "python", alt[7:], colors["accent"]
            suffixes = ["?logo=python&logoColor=white"]
        elif re.fullmatch(r"Node \d+\+", alt):
            kind, label, message, color = 0, "node", alt[5:], colors["accent"]
            suffixes = ["?logo=nodedotjs&logoColor=white"]
        elif alt in ("CI", "Tests"):
            ci = re.fullmatch(r"https://github\.com/([A-Za-z0-9-]+)/(\.github|[A-Za-z0-9-]+)/actions/workflows/([^/?#]+\.ya?ml)/badge\.svg", url)
            if (not ci or link != url.removesuffix("/badge.svg") or ci_matches is None
                    or not ci_matches(ci.group(1), ci.group(2))):
                return False
            name = ci.group(3)
            expected = "Tests" if "test" in name else "CI" if "ci" in name else None
            if alt != expected:
                return False
            kinds.append(2)
            continue
        else:
            return False
        shades = {color, family["accent"]} - {None} if kind == 0 else {color}  # a family palette recolours the language row
        urls = {f"{SHIELDS}{label}-{shield(message)}-{c}{suffix}" for suffix in suffixes for c in shades}
        slug = re.sub(r"[^a-z0-9]+", "-", f"{label}-{message}".lower()).strip("-")
        urls.add(f"docs/images/badges/{slug}.svg")
        if url not in urls or link != expected_link:
            return False
        kinds.append(kind)
    return kinds == sorted(set(kinds))


def generated_badges(body: str) -> bool:
    """The digest proves that the generated badge rows have not been edited."""
    match = GENERATED_BADGES.fullmatch(body)
    return bool(match and match.group(1) == badge_sha(match.group(3)))


def nav_first(ctx: RepoContext) -> bool:
    """§7.1 order: hero banner, then the nav line (review q57 `nav` default); brand.yaml `readme.nav_first` restores
    the nav-first order only if the user answers "Nav line first"."""
    return bool(ctx.brand.readme_opts.get("nav_first"))


def lead(ctx: RepoContext, banner: str, nav: str) -> list[str]:
    """The banner and nav blocks in the configured order."""
    return [nav, banner] if nav_first(ctx) else [banner, nav]


def inherited_tagline(ctx: RepoContext, body: str, text: str) -> bool:
    """Only exact captured template payloads prove inheritance.

    A pristine template-body receipt does not cover the independent tagline.
    Invalid tagline receipts always remain authored, including on template copies.
    """
    if ctx.meta.get("is_template"):
        return False
    value = taglinemod.inherited_payload(body)
    if value is None:
        return False
    known = [taglinemod.inherited_payload(x) for x in ctx.meta.get("template_taglines") or []
             if isinstance(x, str) and x.strip()]
    return value in known


def tagline_body(ctx: RepoContext, existing: str | None = None, text: str = "") -> str:
    """Refresh verified generated content; preserve ambiguous legacy or edited text."""
    desc = (ctx.meta.get("description") or "").strip()
    if desc:
        if existing and existing.strip() and taglinemod.payload(existing) is None:
            return existing
        payload = f'<p align="center"><b>{desc}</b></p>' if ctx.det["variant"] == "F" else f"**{desc}**"
        return taglinemod.generated(payload)
    ctx.log("needs-input:description")
    if existing is None or not existing.strip() or inherited_tagline(ctx, existing, text):
        return ""
    return existing


def header(ctx: RepoContext, keep_banner: str | None = None, title: str | None = None,
           tagline: str | None = None, existing_badges: str | None = None) -> str:
    """The §7.2 header. `tagline` is the tagline block body a caller already decided with tagline_body() (the body it
    carries over from the header it replaces); None writes the description's tagline, or an empty block."""
    tag = wrap("tagline", tagline_body(ctx) if tagline is None else tagline)
    banner = keep_banner if keep_banner is not None else wrap("banner", banner_html(ctx))
    if ctx.det["variant"] == "F":
        parts = [*lead(ctx, banner, wrap("nav", nav_line(ctx))), wrap("badges", badge_body(ctx, existing_badges)), tag, "---"]
        return "\n\n".join(p for p in parts if p)
    parts = [*lead(ctx, banner, wrap("nav", nav_line(ctx))), '<div align="center">', f"# {title or product_name(ctx)}",
             wrap("badges", badge_body(ctx, existing_badges)), tag, "</div>", "---"]
    return "\n\n".join(p for p in parts if p)


# ------------------------------------------------------------------------------------------------
# License (§7.6) and section facts
# ------------------------------------------------------------------------------------------------
def license_section(ctx: RepoContext) -> tuple[str, str] | None:
    rv = standard("readme-variants")["license_rows"]
    f = ctx.facts
    third = f.known and (ctx.repo.endswith("-fork") or any(x.startswith(("vendor/", "third_party/")) for x in f.files))
    if third:
        ctx.log("needs-input:upstream")
        return None
    # A license identifier is factual metadata. Trademark and copyright claims
    # require exact wording on this org's row; family membership cannot grant it.
    def configured_wording(key: str, fallback: str = "") -> str:
        value = ctx.org.get(key, fallback)
        if not isinstance(value, str):
            raise ConfigError(f"{key} must be a string for {ctx.owner}")
        return value.strip()

    lic, dual = license_facts(ctx)
    heading = "Licensing" if ctx.det["variant"] == "F" else "License"
    wording = configured_wording("license_wording")
    if not ctx.public:
        private = configured_wording("private_license_wording")
        if not private:
            ctx.log("needs-input:license-wording")
            return None
        if "<year>" in private:
            year = (ctx.meta.get("created_at") or "")[:4]
            if len(year) != 4 or not year.isdigit():
                ctx.log("needs-input:license-year")
                return None
            private = private.replace("<year>", year)
        return "License", private
    if dual:
        return "Licensing", rv["security"]
    if lic and lic != "NOASSERTION":
        if lic == "MIT":
            if f.exists("BRAND_ASSETS.md"):
                extra = configured_wording("skills_license_wording", wording)
                if not extra:
                    ctx.log("needs-input:license-wording")
                factual = "Code, templates, and documentation are licensed under the MIT License."
                paths = "`LICENSE` and `BRAND_ASSETS.md`" if f.is_file("LICENSE") else "`BRAND_ASSETS.md`"
                tail = f" See {paths}."
                return heading, factual + (" " + extra if extra else "") + tail
            factual = "Code and documentation are licensed under the MIT License" + license_reference(ctx)
        else:
            factual = f"Licensed under the {lic}" + license_reference(ctx)
        if not wording:
            ctx.log("needs-input:license-wording")
        return heading, factual + (" " + wording if wording else "")
    ctx.log("needs-input:license")
    return None


def section_facts(ctx: RepoContext, h2: str) -> str | None:
    """Body for a missing section from supplied or captured repository facts."""
    supplied = (ctx.override.get("readme") or {}).get("sections") or {}
    body = supplied.get(h2, "").strip("\r\n")
    if body.strip():
        return body
    f = ctx.facts
    if h2 == "Workflow Diagram" and f.read("assets/diagrams/workflow.mmd"):
        return ("Source: [assets/diagrams/workflow.mmd](assets/diagrams/workflow.mmd).\n\n```mermaid\n"
                + f.read("assets/diagrams/workflow.mmd").strip() + "\n```")
    if ctx.det["type"] == "mobile-app" and ctx.det["variant"] == "B" and h2 in ("Install", "Quick Start"):
        return None
    if h2 == "Install":
        cmds = []
        if f.exists("requirements.txt"):
            cmds.append("pip install -r requirements.txt")
        elif f.exists("pyproject.toml"):
            cmds.append("pip install .")
        if f.exists("package.json"):
            cmds.append("npm install")
        if cmds:
            return "```bash\n" + "\n".join(cmds) + "\n```"
    if h2 == "Quick Start" and f.known:
        scripts = list(((f.pyproject().get("project") or {}).get("scripts") or {}).keys())
        pj = f.package_json()
        if not scripts and isinstance(pj.get("bin"), dict):
            scripts = list(pj["bin"].keys())
        if scripts:
            return "```bash\n" + "\n".join(f"{s} --help" for s in scripts[:3]) + "\n```"
    if h2 == "Live Site":
        hp = ctx.meta.get("homepage") or ""
        if hp and ctx.meta.get("homepage_status") == 200:
            host = re.sub(r"^https?://", "", hp).rstrip("/")
            return f"**[{host}]({hp})**"
    if h2 == "Play":
        hp = ctx.meta.get("homepage") or ""
        if hp and ctx.meta.get("homepage_status") == 200:
            return f"**[{re.sub(r'^https?://', '', hp).rstrip('/')}]({hp})**"
    if h2 == "Ownership":
        if ctx.org.get("family") not in (None, "completetech"):
            return f"Organization: {ctx.owner}"
        return f"Owner: @CompleteDotTech · Organization: {ctx.owner}"
    if h2 == "Files" and ctx.det["variant"] == "J":
        rows = [("profile/README.md", f"Organization profile shown at github.com/{ctx.owner}")]
        rows = [r for r in rows if f.exists(r[0])]
        if f.exists("labels.yml"):
            rows.append(("labels.yml", "Label standard (ct-std-v1)"))
        if rows:
            return "| File | Purpose |\n|---|---|\n" + "\n".join(f"| `{a}` | {b} |" for a, b in rows)
    return None


def footer_wanted(ctx) -> bool:
    """Decision 18 footer wanted (RepoContext.footer_status): the watching org's `footer: false` exempts only its
    forks, so its `.github` gets the footer and its other non-fork repositories are held."""
    why = ctx.footer_status()
    if why is None:
        return True
    ctx.log("exempt:footer" if why.startswith("exempt") else why if why.startswith("hold:") else "hold")
    return False


def callout(ctx) -> str | None:
    if ctx.det["variant"] == "I" or (not ctx.public and ctx.det["variant"] in "ABCDE"):
        who = "Touched By An Agent" if ctx.same_owner("TouchedByAnAgent") else ctx.company
        return f"> [!IMPORTANT]\n> Internal {who} repository. Not for distribution."
    return None


# ------------------------------------------------------------------------------------------------
# Modes
# ------------------------------------------------------------------------------------------------
def scaffold(ctx: RepoContext, existing: str = "") -> str:
    if existing and personal_profile(ctx):
        normalized = normalize_text(existing)
        if _personal_has_authored_hero(ctx, normalized, find_blocks(MARK, normalized)):
            return header_only(ctx, existing, preserve_structure=True)
    variant = ctx.det["variant"]
    order = required_sections(ctx.det, meta=ctx.meta)
    parts = [header(ctx)]
    co = callout(ctx)
    if co:
        parts.append(co)
    keep = [ln for ln in source_lines(existing) if ln.strip(" \t") and not ln.startswith("# ")]
    for h2, req in order:
        if h2 in ("License", "Licensing"):
            continue
        body = section_facts(ctx, h2)
        if h2 == "About" and keep:
            body = "\n".join(keep)
        if body:
            parts.append(f"## {h2}\n\n{body}")
        elif req == "R":
            ctx.log(f"needs-input:{variant}:{h2}")
    lic = license_section(ctx)
    if lic:
        parts.append(f"## {lic[0]}\n\n{managed_license(lic[1])}")
    if footer_wanted(ctx):
        parts.append(footermod.block(ctx.brand))
    return "\n\n".join(parts) + "\n"


HEADER_LINE = re.compile(
    r"^\s*(\*\*[^*]+\*\*\s*·.*|#\s+.+|!\[[^\]]*\]\(https://img\.shields\.io[^)]*\)\s*|\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)\s*"
    r"|<img [^>]*(shields\.io|badge\.svg|logo)[^>]*>\s*|<a [^>]*>\s*<img [^>]*(shields\.io|badge\.svg)[^>]*>\s*</a>\s*"
    r"|</?picture>|<source [^>]*>|<img [^>]*alt=\"[^\"]*logo[^\"]*\"[^>]*>|<p align=\"center\">|</p>|<div align=\"center\">|</div>|---)$")


def _strip_markers(text: str, keep: dict[str, str] | None = None) -> tuple[str, dict]:
    """(text without its marker blocks, {block: body}); a marker example inside fenced or inline code stays. A block
    named in `keep` stays where it is, rewrapped around the body `keep` gives it."""
    blocks, out, pos = {}, [], 0
    for m in find_blocks(MARK, text):
        blocks[m.group(1)] = m.group(2)
        out.append(text[pos:m.start()])
        if keep and m.group(1) in keep:
            out.append(wrap(m.group(1), keep[m.group(1)]))
        pos = m.end()
    return "".join(out) + text[pos:], blocks


def _badge_or_logo(source: str, *, personal: bool = False) -> bool:
    if not personal:
        return bool(re.search(r"logo", source, re.I) or "shields.io" in source
                    or "badge.svg" in source or "docs/images/badges/" in source)
    location = re.split(r"[?#]", source, maxsplit=1)[0]
    return bool(re.search(r"(?:^|[/_.-])logo(?:$|[/_.-])", location, re.I)
                or re.match(r"https?://(?:img\.)?shields\.io/", location, re.I)
                or re.fullmatch(r"https://github\.com/[^/]+/[^/]+/actions/workflows/[^/]+/badge\.svg", location, re.I)
                or location.removeprefix("./").startswith("docs/images/badges/"))


def _leading_banner(pre: str) -> bool:
    """True when the README preamble opens with a third-party banner image (not ours, not a logo or badge)."""
    first_img = re.search(r"<(img|picture)\b[^>]*>|!\[[^\]]*\]\([^)]*\)", pre)
    return bool(first_img and "docs/images/banner.png" not in first_img.group(0)
                and not _badge_or_logo(first_img.group(0))
                and not pre[:first_img.start()].strip().replace("<p align=\"center\">", "").strip())


def fork_callout(ctx: RepoContext) -> str | None:
    """§7.4 G callout; None (logged fork-parent-missing) when the parent is unknown. A fork with commits ahead of its
    parent gets the full note with the compare link; a 0-ahead fork (§11.1 F1x) gets the short form, which claims no
    changes. When `ahead_by` is not in the metadata the short form is used too (never claim changes nobody counted)
    and `needs-input:ahead-by` is logged."""
    parent = ctx.meta.get("parent") or {}
    full = parent.get("full_name") if isinstance(parent, dict) else None
    if not full:
        ctx.log("fork-parent-missing")
        return None
    ahead = ctx.meta.get("ahead_by")
    if not ahead:
        if ahead is None:
            ctx.log("needs-input:ahead-by")
        return (f"> [!NOTE]\n> **Fork of [{full}](https://github.com/{full})**, kept by {ctx.company}. "
                "The upstream README follows unchanged; the upstream license applies.")
    pbranch = parent.get("default_branch") or "main"
    branch = ctx.meta.get("default_branch") or "main"
    powner = full.split("/")[0]
    return (f"> [!NOTE]\n> **Fork of [{full}](https://github.com/{full})** with {ctx.company} changes. Our changes: "
            f"[compare with upstream](https://github.com/{ctx.owner}/{ctx.repo}/compare/{powner}:{pbranch}...{branch}). "
            "The upstream README follows unchanged; the upstream license applies.")


def leading_banner_block(text: str) -> re.Match | None:
    """Return the paired banner with no authored content preceding it."""
    first = next(iter(find_blocks(MARK, text)), None)
    if (first is not None and first.group(1) == "banner" and not text[:first.start()].strip()
            and _block_on_separate_lines(text, first)):
        return first
    return None


def _personal_preamble_has_art(text: str) -> bool:
    unmarked, _ = _strip_markers(text)
    preamble, _ = split_sections(unmarked)
    return any(not _badge_or_logo(source, personal=True)
               for _, source, _ in _image_entries(masked(unmarked)[:len(preamble)], unmarked))


def _personal_has_authored_hero(ctx: RepoContext, text: str, markers: list[re.Match]) -> bool:
    return (any(m.group(1) == "banner" and not personal_generated_hero(ctx, m.group(2)) for m in markers)
            or _personal_preamble_has_art(text))


def _badges_precede_banner(text: str, banner: re.Match) -> bool:
    images = _image_entries(masked(text)[:banner.start()], text)
    return bool(images) and all(_badge_or_logo(source, personal=True) for _, source, _ in images)


def _heading_view(text: str) -> str:
    clean = list(masked(text))
    for start, end in html_block_spans(text):
        clean[start:end] = ["\n" if ch == "\n" else "\x00" for ch in clean[start:end]]
    return "".join(clean)


def personal_header_end(text: str) -> int:
    """End of the opening area, allowing an existing initial H1 title."""
    headings = iter(top_level_heading_spans(text))
    section = next(headings, None)
    if section is not None and section[2] == 1:
        section = next(headings, None)
    return section[0] if section is not None else len(text)


def callout_only(ctx: RepoContext, text: str, *, retain_personal_banner: bool = False) -> tuple[str, list[str]]:
    """Variants G and H (§7.4): the hero banner block, then the callout (unless one is already there), then the body
    unchanged, then the decision 18 footer. Nothing else changes. Watching-org forks never reach here (`readme`
    exempts them). Review q27 "Full CompleteTech treatment" (brand.yaml readme.fork_readme: full) means the fork
    follows its §5.4 variant instead: pass that variant with `readme --variant`.
    Returns (text, removed lines): a recognized old footer (marked or unmarked, `is_footer_copy`: for example one with
    the former logo URLs) is replaced by the current one, and only the removed footer lines that the replacement footer
    does not carry again are reported (multiset difference), so the preservation check accepts them. A re-emitted
    line is not reported, so it cannot weaken the never-drop-a-line guard. A marked footer that is not a footer copy
    (a partner image) is left as it is. The trailing unmarked footer additionally accepts the brand's own-site historical
    logo sources (`footer.legacy_logo_urls` entries and `docs/images/logo.svg`) under a vouching alt, while partner,
    foreign and look-alike images stay authored. A removed recognized footer is always replaced, even when fenced
    example text makes check() report drift."""
    if ctx.det["variant"] == "G" and ctx.brand.readme_opts.get("fork_readme") == "full":
        ctx.log("needs-input:fork-variant (q27 full treatment: pass readme --variant for the §5.4 variant)")
    body = text
    lead_banner = ""
    leading = leading_banner_block(text)
    personal = personal_intro_applies(ctx)
    banner_gap = "\n\n"
    replaced_hero: list[str] = []
    banners = [block for block in find_blocks(MARK, text) if block.group(1) == "banner"] if personal else []
    if not retain_personal_banner and len(banners) > 1:
        raise NeedsInput("intro", "Keep one managed personal hero block before refreshing the intro.")
    if (not retain_personal_banner and not leading and len(banners) == 1
            and personal_generated_hero(ctx, banners[0].group(2))):
        banner = banners[0]
        old_hero = banner.group(2)
        new_hero = banner_html(ctx)
        if _badges_precede_banner(text, banner) or personal_header_end(text) < banner.start():
            if not _block_on_separate_lines(text, banner):
                raise NeedsInput("intro-order", "Put the managed personal hero markers on their own lines before "
                                 "moving the hero into the opening area.")
            # Move only the owned hero; the authored preamble keeps its bytes and order.
            body = text[:banner.start()] + text[banner.end():]
            lead_banner = wrap("banner", new_hero) + banner_gap
        elif new_hero != old_hero:
            body = text[:banner.start(2)] + new_hero + text[banner.end(2):]
        replaced_hero = _unreemitted(source_lines(old_hero), Counter(line.strip() for line in source_lines(new_hero)))
    if leading:  # our banner block is already on top (a re-run): keep it, look for the callout below
        remainder = text[leading.end():]
        body = remainder.lstrip("\n")
        if personal and body != remainder:
            banner_gap = remainder[:len(remainder) - len(body)]
    first = next((ln for ln in source_lines(body) if ln.strip()), "")
    out = body
    if not first.lstrip().startswith(">"):
        if ctx.det["variant"] == "G":
            co = fork_callout(ctx)
        else:
            co = None  # the H callout needs the archive date and reason from the registry
            ctx.log("needs-input:archive-callout")
        if co:
            out = co + "\n\n" + (body if personal and not leading else body.lstrip("\n"))
    if ctx.art_status()["banner"] is None:
        lead_banner = wrap("banner", banner_html(ctx)) + "\n\n"  # decision 13: the hero banner opens G and H too
    elif leading:
        hero_body = leading.group(2)
        if personal and not retain_personal_banner and personal_generated_hero(ctx, hero_body):
            new_hero = banner_html(ctx)
            lead_banner = wrap("banner", new_hero) + banner_gap
            # Count only generated lines that the replacement does not carry again.
            replaced_hero = list((Counter(ln for ln in source_lines(hero_body) if ln.strip())
                                  - Counter(source_lines(new_hero))).elements())
        else:
            lead_banner = leading.group(0) + banner_gap
    elif personal and not retain_personal_banner and not banners and not _personal_preamble_has_art(text):
        lead_banner = wrap("banner", banner_html(ctx)) + "\n\n"
    out = lead_banner + (out if personal and not leading else out.lstrip("\n"))
    removed: list[str] = list(replaced_hero)
    if footer_wanted(ctx):
        had_footer = False
        if footermod.check(ctx.brand, out)[0] != "pass":
            pos, kept = 0, []
            for fm in find_blocks(MARK, out):
                if fm.group(1) == "footer" and is_footer_copy(fm.group(2), ctx.brand):
                    kept.append(out[pos:fm.start()])
                    removed += [ln for ln in source_lines(fm.group(2)) if ln.strip()]
                    had_footer = True
                    pos = fm.end()
            out = "".join(kept) + out[pos:]
            out, old_footer = drop_old_footer(out, ctx.brand, own_site=True)
            removed += old_footer
            if old_footer:
                had_footer = True
        if had_footer or footermod.check(ctx.brand, out)[0] == "fail:missing":
            out = out.rstrip("\n") + "\n\n" + footermod.block(ctx.brand) + "\n"
            # Report only the removed footer lines that the replacement footer does not carry again (multiset
            # difference), so a re-emitted line never counts as lost content in the preservation check.
            kept = Counter(ln.strip() for ln in source_lines(footermod.block(ctx.brand)) if ln.strip())
            rest = []
            for ln in removed:
                if kept[ln.strip()] > 0:
                    kept[ln.strip()] -= 1
                else:
                    rest.append(ln)
            removed = rest
    return out, removed


def preserved(ctx: RepoContext, text: str) -> bool:
    """§7.0 preserve list, decided the same way by `readme` (before) and `lint readme` (after the upgrade):
    the org's readme_preserve list, any README over 15,000 bytes, and every T2 product README that opens with its
    own banner image. Showcase marker blocks (our nav line) are ignored, so the answer survives an upgrade."""
    if ctx.repo in (ctx.org.get("readme_preserve") or []) or len(text.encode()) > 15000:
        return True
    if ctx.tier != "T2":
        return False
    body, _ = _strip_markers(text.replace("\r\n", "\n"))
    pre, _ = split_sections(body)
    return _leading_banner(pre)


CENTRED_OPEN = re.compile(r'(?m)^[ \t]*<(p|div) align="center">')


def is_footer_like(block: str, brand=None) -> bool:
    """A centred block that credits the company with a complete.tech link (or, given `brand`, a link to the configured
    footer host): the decision 18 footer, exact or drifted. A cheap pre-filter; `is_footer_copy` decides what is removed."""
    low = block.lower()
    hosts = ["complete.tech"]
    if brand is not None:
        from urllib.parse import urlsplit
        try:
            h = (urlsplit(brand.raw["footer"]["href"]).hostname or "").lower()
        except (KeyError, TypeError, ValueError):
            h = ""
        if h:
            hosts.append(h[4:] if h.startswith("www.") else h)
    return bool(re.match(r'\s*<(p|div) align="center">', block)) and "built by" in low and any(h in low for h in hosts)


FOOTER_TAG = re.compile(r"</?(p|div|a|picture|source|img|br|sub|sup|b|strong|em)\b([^>]*)>", re.I)


FOOTER_ATTR = re.compile(r"""\b(src|srcset|alt)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)

FOOTER_HREF = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)

# one whole attribute (name plus optional quoted or bare value), so a name or value inside another attribute's quotes
# (title="href=...") is never read as an attribute of its own
FOOTER_ATTR_TOKEN = re.compile(r"""\s*([^\s"'=>/]+)(\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?""")

FOOTER_IMG_ATTRS = ("alt", "src", "srcset")


def _footer_attrs(attrs: str) -> dict[str, str]:
    """The `alt`, `src` and `srcset` attributes of one tag's attribute text, parsed as whole attributes: exact
    (case-insensitive) names only, so `data-alt`, `xalt` or text inside another attribute's quoted value never count;
    the first occurrence of a name wins, as a browser reads it; the value is returned with its quotes removed. A
    recognised attribute with no value is recorded as an empty string, so a later duplicate cannot override it."""
    got: dict[str, str] = {}
    for tok in FOOTER_ATTR_TOKEN.finditer(attrs):
        name = tok.group(1).lower()
        if name not in FOOTER_IMG_ATTRS or name in got:
            continue
        if tok.group(2) is None:
            got[name] = ""
            continue
        val = tok.group(2).split("=", 1)[1].strip()
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        got[name] = val
    return got


OLD_LOCAL_LOGOS = {'assets/logo.png', 'logo.png', 'assets/logo-dark.png', 'logo-dark.png'}


def _old_local_logo(url: str) -> bool:
    """`url` is a former local footer logo file (`OLD_LOCAL_LOGOS`), relative and without a scheme, host or data URI."""
    url = url.strip()
    if "://" in url or url.startswith("//") or url.startswith("data:"):
        return False
    path = url.split("#", 1)[0].split("?", 1)[0]
    if path.startswith("./"):
        path = path[2:]
    elif path.startswith("/"):
        path = path[1:]
    return path in OLD_LOCAL_LOGOS


# A file CONVENTION (the logo a former own-site README layout kept beside the docs), not brand data.
OWN_SITE_LOCAL_LOGOS = {"docs/images/logo.svg"}


def _own_site_logo(url: str, brand) -> bool:
    """`url` is a configured historical logo source of this brand: it equals, exactly, an http(s) entry of
    `footer.legacy_logo_urls` in references/brand.yaml (scheme, host case-insensitively, port, path; query and
    fragment ignored; no userinfo), so no brand host or path lives in Python. The generic local `docs/images/logo.svg`
    (`OWN_SITE_LOCAL_LOGOS`) is a file convention, distinct from that configured data. Any other file on the same host
    (a team photo, a screenshot) is authored content and is kept."""
    from urllib.parse import urlsplit
    url = url.strip()
    if "://" not in url:
        path = url.split("#", 1)[0].split("?", 1)[0]
        return (path[2:] if path.startswith("./") else path) in OWN_SITE_LOCAL_LOGOS
    legacy = brand.raw.get("footer", {}).get("legacy_logo_urls") or []
    try:
        got = urlsplit(url)
        if got.username is not None or got.password is not None or not got.hostname:
            return False
        for entry in legacy:
            if not isinstance(entry, str):
                continue
            want = urlsplit(entry.strip())
            if (want.scheme in ("http", "https") and got.scheme == want.scheme and want.hostname
                    and got.hostname == want.hostname and got.port == want.port
                    and got.path == want.path):
                return True
    except ValueError:
        return False
    return False


def _footer_href_ok(href: str, brand) -> bool:
    """`href` is an http(s) link to the configured footer link host (`footer.href`, never hardcoded): the same hostname,
    case-insensitively, with a leading `www.` equivalent on either side; no userinfo, port or other host. Path, query
    and fragment are ignored. A suffix, look-alike or partner host, or a complete.tech mention outside the host, is not."""
    import html
    from urllib.parse import urlsplit
    try:
        got = urlsplit(html.unescape(href).strip())
        want = urlsplit(brand.raw["footer"]["href"])
        if got.scheme not in ("http", "https") or got.hostname is None:
            return False
        if got.username is not None or got.password is not None or got.port is not None:
            return False
        if want.hostname is None:
            return False

        def _norm(host: str) -> str:
            host = host.lower()
            return host[4:] if host.startswith("www.") else host

        return _norm(got.hostname) == _norm(want.hostname)
    except ValueError:
        return False


def _footer_logo_url(url: str, brand) -> bool:
    """`url` is one of the decision 18 footer's own logo files (brand footer `logo_light_url` or `logo_dark_url`),
    including explicitly configured legacy URLs, or drifted only in scheme, branch, query or the github.com
    blob/raw form of the same file."""
    url = url.strip().split("#", 1)[0].split("?", 1)[0]
    footer = brand.raw["footer"]
    urls = [footer[key] for key in ("logo_light_url", "logo_dark_url")]
    # Legacy publication copies of the footer logo (GitHub raw/blob) are recognized on their own; any other legacy
    # entry (a company-website logo) is an own-site source that only `_own_site_logo` accepts, under a vouching alt.
    urls.extend(u for u in footer.get("legacy_logo_urls") or []
                if isinstance(u, str) and u.startswith("https://raw.githubusercontent.com/"))
    for want in urls:
        if url == want:
            return True
        m = re.match(r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/[^/]+/(.+)$", want)
        if not m:
            continue
        own, repo, path = (re.escape(x) for x in m.groups())
        if re.fullmatch(rf"(?i:https?://raw\.githubusercontent\.com/{own}/{repo}/[^/]+/){path}", url) or \
                re.fullmatch(rf"(?i:https?://github\.com/{own}/{repo}/(?:blob|raw)/[^/]+/){path}", url):
            return True
    return False


def is_footer_copy(block: str, brand, loose_src: bool = False, own_site: bool = False) -> bool:
    """Every line of `block` is a line of the decision 18 footer or a drifted copy of one: only centring, link, logo,
    `<br>`/`<sub>` markup, with anchors that target the configured footer link host (`footer.href`), the footer's own logo image (its src or srcset is the brand footer
    logo URL or a drifted form of it; an image without src/srcset passes on an alt that is exactly the company) and as text only the credit line ("Built by
    <company>", optionally with the suffix). The former local logo files (assets/logo.png and the other `OLD_LOCAL_LOGOS`) are also recognized when the image's alt is exactly the company or the footer alt. A sponsor or partner image (whatever its file name), a thanks line or
    any other authored text makes it not a footer copy, so it is never removed. `loose_src=True` keeps the original
    rule that an alt exactly the company vouches for an image whatever its src (no caller in `upgrade()`: a generic
    alt is not provenance). `own_site=True` (`upgrade()`, for an unmarked trailing block that also passes
    `is_footer_like`) additionally recognizes, under an alt exactly the company or the footer alt, only the brand's
    own-site historical logo sources (`_own_site_logo`: the exact `footer.legacy_logo_urls` entries, plus the generic local
    `docs/images/logo.svg` convention; "historical logo sources" means those exact paths, not every
    file on the host); partner, foreign and look-alike hosts, and other files on the company host, stay authored. The
    default is strict."""
    import html
    f, company = brand.raw["footer"], brand.strings["company"]
    credit = {f"{f['line_prefix']} {company}", f"{f['line_prefix']} {company} {f['line_suffix']}"}

    def _alts(attrs: str) -> list[str]:
        alt = _footer_attrs(attrs).get("alt")
        return [] if alt is None else [html.unescape(alt).strip()]

    # a <source> carries no alt: the block's own <img> alt vouches for its former local logo files
    block_alt_ok = any(v in (company, f["alt"]) for m in FOOTER_TAG.finditer(block)
                       if m.group(1).lower() == "img" and not m.group(0).startswith("</") for v in _alts(m.group(2)))

    def tag_ok(m: re.Match) -> bool:
        name, attrs = m.group(1).lower(), m.group(2)
        if m.group(0).startswith("</") or name not in ("a", "img", "source"):
            return True
        if name == "a":
            href = None
            for tok in FOOTER_ATTR_TOKEN.finditer(attrs):  # first href attribute, as a browser reads it
                if tok.group(1).lower() == "href":
                    hm = FOOTER_HREF.search(tok.group(0))
                    href = next((g for g in hm.groups() if g is not None), None) if hm else None
                    break
            return href is not None and _footer_href_ok(href, brand)
        alt_ok, urls = False, []
        for key, raw in _footer_attrs(attrs).items():  # whole attributes, exact names; never a file name that merely contains "logo"
            val = html.unescape(raw).strip()
            if key == "alt":
                alt_ok = alt_ok or val in (company, f["alt"])
            else:
                urls.append([p.split()[0] for p in val.split(",") if p.split()])
        if name == "source":
            alt_ok = block_alt_ok
        if urls:  # a matching alt never vouches for another image (unless loose_src): every src/srcset must be a footer logo URL
            if loose_src and alt_ok and name == "img":
                return True
            return all(parts and all(_footer_logo_url(u, brand) or (alt_ok and (_old_local_logo(u) or (
                own_site and name == "img" and _own_site_logo(u, brand)))) for u in parts)
                       for parts in urls)
        return alt_ok

    for line in source_lines(block):
        if not line.strip():
            continue
        if not all(tag_ok(m) for m in FOOTER_TAG.finditer(line)):
            return False
        rest = " ".join(html.unescape(FOOTER_TAG.sub(" ", line)).split())
        if rest and rest not in credit:
            return False
    return True


def drop_old_footer(text: str, brand, loose_src: bool = False, own_site: bool = False) -> tuple[str, list[str]]:
    """(text, removed lines) with a trailing old footer (an unmarked or drifted decision 18 footer: every line a
    footer line, `is_footer_copy`) taken off the end, so the marked footer replaces it instead of following it. Any
    other block, a centred credits block with authored lines included, is left as it is (lint reports a second
    footer-like block as `fail:duplicate`). `loose_src` and `own_site` are passed through to `is_footer_copy` (strict by default)."""
    body = text.rstrip()
    opens = [m for m in CENTRED_OPEN.finditer(masked(body))]
    if not opens:
        return text, []
    m = opens[-1]
    tail = body[m.start():]
    if not tail.rstrip().endswith(f"</{m.group(1)}>") or not is_footer_like(tail, brand) or not is_footer_copy(tail, brand, loose_src, own_site):
        return text, []
    return body[:m.start()].rstrip() + "\n", [ln for ln in source_lines(tail) if ln.strip()]


def _unreemitted(lines: list[str], kept: Counter) -> list[str]:
    """`lines` minus the lines the emitted footer carries again: each non-empty line matched in the multiset `kept`
    (stripped text) is dropped and decrements `kept`; the others are returned with their original text."""
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if kept[s] > 0:
            kept[s] -= 1
        else:
            out.append(ln)
    return out


def _block_on_separate_lines(text: str, block: re.Match) -> bool:
    starts_line = block.start() == 0 or text[block.start() - 1] == "\n"
    ends_line = text[block.end():block.end() + 1] in ("", "\n")
    return starts_line and ends_line


def _badge_blocks_need_in_place_refresh(text: str, markers: list[re.Match]) -> bool:
    badges = [m for m in markers if m.group(1) == "badges"]
    return len(badges) > 1 or any(
        not _block_on_separate_lines(text, m) or m.group(0) != wrap("badges", m.group(2)) for m in badges
    )


def upgrade(ctx: RepoContext, text: str, *, already_normalized: bool = False) -> tuple[str, list[str]]:
    """Return (new text, header lines removed); callers run preservation checks before writing."""
    if not already_normalized:
        text = normalize_text(text)
    variant = ctx.det["variant"]
    rv = standard("readme-variants")
    personal = personal_profile(ctx)
    retain_personal_banner = personal and ctx.preserve_unchanged() and preserved(ctx, text)
    markers = find_blocks(MARK, text) if personal or variant == "J" else []
    if personal and _personal_has_authored_hero(ctx, text, markers):
        # Every personal variant preserves authored artwork and refreshes only existing owned blocks.
        return header_only(ctx, text, already_normalized=True, preserve_structure=True,
                           retain_personal_banner=retain_personal_banner), []
    if variant in ("G", "H"):
        return callout_only(ctx, text, retain_personal_banner=retain_personal_banner)
    if retain_personal_banner and any(block.group(1) == "banner" for block in markers):
        return header_only(ctx, text, already_normalized=True, retain_personal_banner=True), []
    if variant == "J" and _badge_blocks_need_in_place_refresh(text, markers):
        return header_only(ctx, text, already_normalized=True), []
    body, blocks = _strip_markers(text)
    want_footer = footer_wanted(ctx)
    removed: list[str] = []
    if personal_profile(ctx) and "banner" in blocks:
        removed += blocks["banner"].splitlines()  # only an exact generated hero reaches this branch
    # One multiset of the footer lines the emitted footer carries again, shared by the marked and the unmarked branch
    # because only one new footer is emitted. A compliant footer is re-emitted unchanged and must not weaken the
    # never-drop-a-line guard, so only the old lines it does not carry again are reported as removed.
    kept: Counter = Counter()
    if want_footer:
        kept = Counter(ln.strip() for ln in source_lines(footermod.block(ctx.brand)) if ln.strip())
    if want_footer and blocks.get("footer") and is_footer_copy(blocks["footer"], ctx.brand):
        # A configured publication-path change replaces only our recognized footer, not authored credits or partner
        # images inside a similarly named block.
        for ln in source_lines(blocks["footer"]):
            if ln.strip():
                if kept[ln.strip()] > 0:
                    kept[ln.strip()] -= 1
                else:
                    removed.append(ln)
    if want_footer:  # an unmarked or drifted footer at the end is replaced by the marked one, never kept beside it
        body, old_footer = drop_old_footer(body, ctx.brand, own_site=True)
        removed += _unreemitted(old_footer, kept)
    # preserve list / existing third-party banner
    preserve = ctx.repo in (ctx.org.get("readme_preserve") or []) or len(text.encode()) > 15000
    pre, sections = split_sections(body)
    keep_pre: list[str] = []
    lines = source_lines(pre)
    if _leading_banner(pre) and (ctx.tier == "T2" or preserve):
        preserve = True
        # q57 `pres`: the hero goes above the README's own banner (kept directly under it), or nothing is added
        ctx.log("exempt:preserve-banner" if ctx.preserve_unchanged() else "preserve-banner:kept-below-hero")
    desc = (ctx.meta.get("description") or "").strip()
    old_tag = blocks.get("tagline")
    if preserve and (old_tag is not None or (variant == "J" and "badges" in blocks)):
        # additive only, so the tagline block stays where it is, its body decided by the header rule (tagline_body)
        keep = {}
        if old_tag is not None:
            tag = tagline_body(ctx, old_tag, text)
            if old_tag.strip() and not tag:  # an inherited tagline, emptied on purpose (not a lost line)
                removed += [ln for ln in source_lines(old_tag) if ln.strip()]
            keep["tagline"] = tag
        if variant == "J" and "badges" in blocks:
            keep["badges"] = badge_body(ctx, blocks["badges"])
        body, _ = _strip_markers(text, keep=keep)
        if want_footer:
            body, _ = drop_old_footer(body, ctx.brand, own_site=True)  # its lines are already in `removed`
        pre, sections = split_sections(body)
        lines = source_lines(pre)
    # an unmarked bold line opening the preamble is an old tagline. With a description it is replaced; without one it
    # is carried into an empty tagline block (header rule), and a second one stays as authored text: never erased
    carry: list[str] = []
    # the pristine-body fallback alone would decide the tagline block (no known template taglines): a bare bold line
    # the template cannot have written must not be moved into a block that later runs would empty
    fallback_only = (not ctx.meta.get("is_template") and not [x for x in ctx.meta.get("template_taglines") or []
                                                               if isinstance(x, str) and x.strip()]
                     and bootstrap_state(text) == "pristine")

    def is_header_line(ln: str) -> bool:
        if HEADER_LINE.match(ln) or "docs/images/banner.png" in ln:
            return not personal or not any(_badge_or_logo(source, personal=True)
                                           for _, source, _ in _image_entries(masked(ln), ln))
        return False

    # group the preamble into units: centred HTML blocks and <picture> blocks are classified as a whole
    units: list[list[str]] = []
    i = 0
    while i < len(lines):
        s_ = lines[i].strip()
        closer = {"<p align=\"center\">": "</p>", "<div align=\"center\">": "</div>", "<picture>": "</picture>"}.get(s_)
        if closer:
            j = i + 1
            while j < len(lines) and lines[j].strip() != closer:
                j += 1
            units.append(lines[i:j + 1])
            i = j + 1
            continue
        units.append([lines[i]])
        i += 1
    for unit in units:
        if len(unit) == 1:
            ln = unit[0]
            s_ = ln.strip()
            bold = (old_tag is None and re.fullmatch(r"\*\*[^*]+\*\*", s_) is not None
                    and not "".join(keep_pre).strip())
            is_hdr = is_header_line(ln) or bold
            if preserve:  # additive only: just an old nav line is replaced
                is_hdr = s_.startswith("**") and " · " in s_ and not "".join(keep_pre).strip()
            elif bold and not is_header_line(ln):
                if desc or carry or fallback_only:
                    # Keep additional bold lines and text that the pristine-template fallback would empty.
                    keep_pre.append(ln)
                    continue
                carry.append(ln)
            (removed if is_hdr else keep_pre).append(ln)
            continue
        inner = unit[1:-1]
        if all(not x.strip() or is_header_line(x) or x.strip() in ("<picture>", "</picture>") or x.strip().startswith("<source ")
               for x in inner) and not preserve:
            removed.extend(unit)
        elif unit[0].strip() == "<div align=\"center\">" and not preserve:
            # old hero wrapper: drop the wrapper and header lines, keep anything else verbatim
            for x in unit:
                (removed if (x is unit[0] or x is unit[-1] or is_header_line(x)) else keep_pre).append(x)
        else:
            keep_pre.extend(unit)
    intro = "\n".join(keep_pre).strip(" \t\n")
    # sections: renames, mapping, Notes demotion, License last
    renames = rv["renames"]
    section_rows = required_sections(ctx.det, meta=ctx.meta)
    low_order = {h.lower(): h for h, _ in section_rows}
    placed: dict[str, str] = {}
    notes: list[str] = []
    license_body = None
    existing_notes = None
    for h, b in sections:
        clean = EMOJI.sub("", h).strip()
        name = renames.get(clean.lower(), clean)
        if name.lower() in ("license", "licensing", "licence"):
            license_body = (name if name != "Licence" else "License", b)
            continue
        if name.lower() == "notes":
            existing_notes = b.strip("\n")
            continue
        if name.lower() in low_order and low_order[name.lower()] not in placed:
            placed[low_order[name.lower()]] = b.strip("\n")
        else:
            if variant == "D" and name.lower() == "status" and "Findings" not in placed:
                placed["Findings"] = b.strip("\n")
                continue
            content = b.rstrip(" \t\n")
            notes.append(f"### {clean}\n{content}" if content else f"### {clean}")
    out = []
    if preserve:
        # §7.0 preserve list: additive only. The hero banner block goes on top (q57 `pres` default, "Banner above the
        # existing content"; none when the user answers "Leave them unchanged"), with the nav line in the §7.1 order;
        # the README's own banner and every section stay verbatim and in place; add License if missing, then footer.
        # The personal profile's banner exemption is not "no hero": it opens with its intro (decision 15), which
        # banner_html returns or refuses with needs-input before any write.
        if ctx.preserve_unchanged() or (ctx.art_status()["banner"] is not None and not personal_intro_applies(ctx)):
            out.append(wrap("nav", nav_line(ctx)))
        else:
            out += lead(ctx, wrap("banner", banner_html(ctx)), wrap("nav", nav_line(ctx)))
        if intro:
            out.append(intro)
        for h, b in sections:
            content = b.rstrip(" \t\n")
            out.append(f"## {h}\n{content}" if content else f"## {h}")
        if not any(h.strip().lower() in ("license", "licensing", "licence") for h, _ in sections):
            lic = license_section(ctx)
            if lic:
                out.append(f"## {lic[0]}\n\n{managed_license(lic[1])}")
        if want_footer:
            out.append(footermod.block(ctx.brand))
        return "\n\n".join(x for x in out if x) + "\n", removed
    else:
        if carry:  # an unmarked tagline with no description: it moves into the block (the move is not a lost line)
            old_tag = carry[0].strip()
            removed.remove(carry[0])
        new_tag = tagline_body(ctx, old_tag, text)
        if old_tag and old_tag.strip() and not new_tag:
            # an inherited tagline is emptied (header mode does the same): its lines are dropped on purpose, so the
            # never-delete check must not report them as lost
            removed += [ln for ln in source_lines(old_tag) if ln.strip()]
        out.append(header(ctx, tagline=new_tag, existing_badges=blocks.get("badges")))
        co = callout(ctx)
        if co and co not in intro:
            out.append(co)
        if intro:
            if variant == "A" or "About" in placed or "about" not in low_order:
                out.append(intro)
            else:
                placed["About"] = intro + ("\n\n" + placed["About"] if placed.get("About") else "")
    for h, req in section_rows:
        if h in ("License", "Licensing"):
            continue
        if h in placed:
            content = placed[h].strip(" \t\n")
            out.append(f"## {h}\n\n{content}" if content else f"## {h}")
        elif req == "R" and not preserve:
            body = section_facts(ctx, h)
            if body:
                out.append(f"## {h}\n\n{body}")
            else:
                ctx.log(f"needs-input:{variant}:{h}")
    if existing_notes or notes:
        nb = "\n\n".join(x for x in ([existing_notes] if existing_notes else []) + notes)
        out.append(f"## Notes\n\n{nb}")
    if license_body:
        content = license_body[1].strip(" \t\n")
        out.append(f"## {license_body[0]}\n\n{content}")
    else:
        lic = license_section(ctx)
        if lic:
            out.append(f"## {lic[0]}\n\n{managed_license(lic[1])}")
    if want_footer:
        out.append(footermod.block(ctx.brand))
    for b in ("template-body", "checklist"):  # inserted in reverse: the checklist stays above the body
        if b in blocks:
            out.insert(1 if not preserve else 1, wrap(b, blocks[b]))
    return "\n\n".join(x for x in out if x) + "\n", removed


def header_only(ctx: RepoContext, text: str, *, already_normalized: bool = False,
                preserve_structure: bool = False, retain_personal_banner: bool = False) -> str:
    """Replace only existing marker blocks (what the Action runs)."""
    original = text
    if not already_normalized:
        text = normalize_text(text)
    personal = personal_profile(ctx)
    if personal and not preserve_structure and not retain_personal_banner:
        markers = find_blocks(MARK, text)
        preserve_structure = (_personal_has_authored_hero(ctx, text, markers)
                              or any(m.group(1) == "banner" and not _block_on_separate_lines(text, m) for m in markers))
    gen = {"nav": nav_line(ctx), "footer": footermod.markup(ctx.brand)}
    if not personal:
        gen["banner"] = banner_html(ctx)
    if not personal and ctx.repo_dir is not None and not (ctx.repo_dir / hero_path(ctx)).is_file():
        gen["banner"] = ""  # no image yet (for example no description): an empty block, never a broken image
        ctx.log("needs-input:banner")
    # Preserve the existing preflight for other variants, even without a badge block.
    # Variant J must inspect its block first because authored badges are not generated.
    if ctx.det["variant"] != "J" and not preserve_structure:
        gen["badges"] = badge_body(ctx)

    def sub(m):
        b, body = m.group(1), m.group(2)
        if b == "badges" and (preserve_structure or ctx.det["variant"] == "J"):
            fresh = badge_body(ctx, body)
            return m.group(0) if fresh == body else wrap(b, fresh)
        if b == "checklist":
            if re.search(r"- \[ \]", body):
                return m.group(0)
            return ""
        if b == "tagline":  # tagline_body: the description's line, else the block as written unless inherited
            new = tagline_body(ctx, body, text)
            return m.group(0) if new == body else wrap(b, new)
        if b == "banner" and personal:
            owned = not retain_personal_banner and personal_generated_hero(ctx, body)
            fresh = banner_html(ctx) if owned else body
            if owned and (_badges_precede_banner(text, m)
                          or (ctx.det["variant"] in ("G", "H") and personal_header_end(text) < m.start())):
                raise NeedsInput("intro-order", "The personal intro belongs in the opening area. Use readme --mode "
                                 "upgrade without --no-regroup to request a complete header refresh.")
            return m.group(0) if fresh == body else wrap(b, fresh)
        if b in gen:
            return wrap(b, re.sub(r"\n{3,}", "\n\n", gen[b]))
        return m.group(0)
    if preserve_structure:
        return _replace_blocks_in_source(original, text, sub)
    refreshed = _sub_blocks(text, sub)
    return license_block(ctx, refreshed if retain_personal_banner else reorder_lead(ctx, refreshed))


def _replace_blocks_in_source(original: str, normalized: str, sub) -> str:
    """Splice blocks into their source spans, leaving all other bytes in place."""
    bom = int(original.startswith(BOM))
    dropped = [m.start() - bom - count
               for count, m in enumerate(re.finditer(r"\r\n", original))]

    def source_offset(index):
        return index + bom + bisect_left(dropped, index)

    out, pos = [], 0
    for match in find_blocks(MARK, normalized):
        replacement = sub(match)
        if replacement == match.group(0):
            continue
        start, end = source_offset(match.start()), source_offset(match.end())
        endings = re.findall(r"\r\n|[\r\n]", original[start:end])
        local = iter(endings)
        replacement = re.sub(r"\n", lambda _: next(local, endings[0] if endings else "\n"), replacement)
        out.extend((original[pos:start], replacement))
        pos = end
    return "".join(out) + original[pos:]


def _seam(left: str, right: str) -> str:
    """Join two pieces where a marker block meets authored text: the blank lines on both sides of the join count
    together and collapse to at most one blank line. Nothing else in either piece changes."""
    a, b = left.rstrip("\n"), right.lstrip("\n")
    n = min(len(left) - len(a) + len(right) - len(b), 2)
    return a + "\n" * n + b


def _sub_blocks(text: str, sub) -> str:
    """MARK.sub(sub, text), except that authored text between blocks comes back byte-identical (fenced code
    included, and a marker example inside code is never treated as a block); blank-line runs are tidied only at the
    seams around each block (a removed block leaves one blank line)."""
    out, pos = "", 0
    for m in find_blocks(MARK, text):
        out = text[:m.start()] if not pos else _seam(out, text[pos:m.start()])
        out = _seam(out, sub(m))
        pos = m.end()
    return _seam(out, text[pos:]) if pos else text


def reorder_lead(ctx: RepoContext, text: str) -> str:
    """Swap adjacent, genuinely managed leading blocks into the configured §7.1 order."""
    blocks = find_blocks(MARK, text)
    if len(blocks) < 2:
        return text
    first, second = blocks[:2]
    reverse = ("banner", "nav") if nav_first(ctx) else ("nav", "banner")
    if (first.group(1), second.group(1)) != reverse:
        return text
    prefix = text[:first.start()]
    seam = text[first.end():second.start()]
    if prefix.strip(" \t\n") or seam.strip(" \t\n"):
        return text
    return prefix + second.group(0) + seam + first.group(0) + text[second.end():]


LICENSE_MARK = "<!-- showcase:license -->"
LICENSE_BODY_START = "<!-- showcase:license:body:start -->"
LICENSE_BODY_END = "<!-- showcase:license:body:end -->"
LICENSE_MARKERS = re.compile("|".join(map(re.escape, (LICENSE_MARK, LICENSE_BODY_START, LICENSE_BODY_END))))
_LICENSE_BODY = re.compile(
    re.escape(LICENSE_MARK) + r"\n<!-- showcase:license:sha256=([0-9a-f]{64}) -->\n"
    + re.escape(LICENSE_BODY_START) + r"\n(.*?)\n" + re.escape(LICENSE_BODY_END),
    re.S,
)


def license_sha(body: str) -> str:
    import hashlib
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def managed_license(body: str) -> str:
    """Mark newly generated legal prose so later changes can be detected."""
    return (f"{LICENSE_MARK}\n<!-- showcase:license:sha256={license_sha(body)} -->\n"
            f"{LICENSE_BODY_START}\n{body}\n{LICENSE_BODY_END}")


def _owned_license_match(text: str, markers: list[re.Match]) -> re.Match | None:
    if [match.group() for match in markers] != [LICENSE_MARK, LICENSE_BODY_START, LICENSE_BODY_END]:
        return None
    match = _LICENSE_BODY.match(text, markers[0].start())
    if match and match.end() == markers[-1].end() and license_sha(match.group(2)) == match.group(1):
        return match
    return None


def generated_license(text: str) -> bool:
    source = normalize_line_endings(text)
    return _owned_license_match(source, find_blocks(LICENSE_MARKERS, source)) is not None


def license_block(ctx: RepoContext, text: str) -> str:
    """Refresh only an unambiguously bounded body with a matching digest."""
    markers = find_blocks(LICENSE_MARKERS, text)
    if [match.group() for match in markers] != [LICENSE_MARK, LICENSE_BODY_START, LICENSE_BODY_END]:
        return text
    i = markers[0].start()
    lic = license_section(ctx)
    if not lic or any(code in ctx.logs for code in ("needs-input:license-policy", "needs-input:license-file",
                                                    "needs-input:licensing-file")):
        return text
    m = _owned_license_match(text, markers)
    if m is None:
        return text
    text = text[:i] + managed_license(lic[1]) + text[m.end():]
    h = re.search(r"(?m)^## (?:License|Licensing|Licence)[ \t]*\n(\n?)\Z", text[:i])
    return text[:h.start()] + f"## {lic[0]}\n" + h.group(1) + text[i:] if h else text


TEMPLATE_H1 = "CompleteTech Repo Template"
PRISTINE = re.compile(r"<!-- showcase:template-body:pristine(?: sha256=([0-9a-f]{64}))? -->(?:\r\n|\r|\n)?")


def body_sha(body: str) -> str:
    import hashlib
    return hashlib.sha256(normalize_line_endings(body).encode("utf-8")).hexdigest()


def badge_sha(body: str) -> str:
    """Digest of generated badge rows. Preserves Markdown-significant leading and trailing whitespace on rows
    (four leading spaces make an indented code block) and normalises only line endings and the marker's
    separator newlines."""
    import hashlib
    return hashlib.sha256(normalize_line_endings(body).strip("\n").encode("utf-8")).hexdigest()


def pristine_block(body: str) -> str:
    """A template-body block whose marker carries the sha256 of the generated sections."""
    return wrap("template-body", f"<!-- showcase:template-body:pristine sha256={body_sha(body)} -->\n{body}")


def _template_block(text: str) -> re.Match | None:
    return next((block for block in find_blocks(MARK, text) if block.group(1) == "template-body"), None)


def _pristine_marker(text: str, block: re.Match) -> re.Match | None:
    expected_start = after_line_end(text, block.start() + len(start("template-body")))
    return next((marker for marker in find_blocks(PRISTINE, text)
                 if marker.start() == expected_start and marker.end() <= block.end(2) + 1), None)


def bootstrap_state(text: str) -> str:
    """Return the ownership state of the first genuine template-body block."""
    text = normalize_text(text)
    block = _template_block(text)
    if block is None or (marker := _pristine_marker(text, block)) is None:
        return "none"
    body = text[marker.end():block.end(2)]
    return "pristine" if marker.group(1) and marker.group(1) == body_sha(body) else "edited"


def reseal_formatted_taglines(text: str, before: list[re.Match], after: list[re.Match]) -> str | None:
    """The caller verified Markdown content; retain every block's ownership state."""
    replacements = []
    for original, formatted in zip(before, after, strict=True):
        if original.group(1) != "tagline":
            continue
        body = taglinemod.reseal(original.group(2), formatted.group(2))
        if body is None:
            return None
        replacements.append((*formatted.span(2), body))
    for start, end, body in reversed(replacements):
        text = text[:start] + body + text[end:]
    return text


def reseal_formatted_badges(ctx: RepoContext, text: str, before: list[re.Match], after: list[re.Match]) -> str | None:
    """Reseal generated badges and reject formatter changes that claim authored badges."""
    def legacy(body: str) -> bool:
        return _legacy_badge_body(ctx.brand, body, ctx.style,
                                  ci_matches=lambda owner, repo: _legacy_ci_matches(ctx, owner, repo))

    parts = []
    offset = 0
    for original, formatted in zip(before, after, strict=True):
        if original.group(1) != "badges":
            continue
        original_body, formatted_body = original.group(2), formatted.group(2)
        marker = GENERATED_BADGES.fullmatch(original_body)
        if marker is None or marker.group(1) != badge_sha(marker.group(3)):
            if generated_badges(formatted_body):
                return None
            if original_body != formatted_body and legacy(formatted_body) and not legacy(original_body):
                return None
            continue
        candidate = GENERATED_BADGES.fullmatch(formatted_body)
        if candidate is None or candidate.group(1, 2) != marker.group(1, 2):
            return None
        start, end = candidate.span(1)
        body_start = formatted.start(2)
        parts.extend((text[offset:body_start + start], badge_sha(candidate.group(3))))
        offset = body_start + end
    parts.append(text[offset:])
    return "".join(parts)


def reseal_pristine(text: str) -> str | None:
    """Refresh the existing digest after an approved transformation of a pristine body."""
    block = _template_block(text)
    if block is None or (marker := _pristine_marker(text, block)) is None or not marker.group(1):
        return None
    body_end = block.end() - len(end("template-body"))
    if text[body_end - 2:body_end] == "\r\n":
        body_end -= 2
    elif text[body_end - 1:body_end] in ("\r", "\n"):
        body_end -= 1
    body = text[marker.end():body_end]
    digest_start, digest_end = marker.span(1)
    return text[:digest_start] + body_sha(body) + text[digest_end:]


def drop_pristine(text: str) -> str:
    """Remove only a genuine ownership marker inside the first template body."""
    block = _template_block(text)
    if block is None or (marker := _pristine_marker(text, block)) is None:
        return text
    return text[:marker.start()] + text[marker.end():]


_HEADER_RULE = re.compile(r"\n+(?:</div>\n+)?---\n")
_HEADER_LAYOUT = re.compile(r'(?:<div align="center">\n+)?(?:# ([^\n]+)\n+)?(?:</div>\n+)?---\n')


def _header_region(text: str) -> tuple[int, list[re.Match], str | None] | None:
    """Identify a rebuildable header using live blocks and exact generated structure."""
    blocks = []
    seen = set()
    parts = []
    offset = 0
    for block in find_blocks(MARK, text):
        name = block.group(1)
        if name not in {"banner", "nav", "badges", "tagline"} or name in seen:
            return None
        if not _block_on_separate_lines(text, block):
            return None
        seen.add(name)
        blocks.append(block)
        parts.append(text[offset:block.start()])
        offset = block.end()
        if name == "tagline":
            rule = _HEADER_RULE.match(text, offset)
            if rule is None:
                return None
            parts.append(rule.group())
            layout = _HEADER_LAYOUT.fullmatch("".join(parts).lstrip("\n"))
            if layout is not None:
                return rule.end(), blocks, layout.group(1)
            return None
    return None


def bootstrap(ctx: RepoContext, text: str, *, already_normalized: bool = False) -> str:
    """Fill a README that still carries a generated (pristine) template body: the README variant's sections from
    repository facts, the variant's header (Variant F has no H1) and the license section. A pristine body is
    regenerated on later runs too, so a repository typed `workspace` on its creation commit is re-bootstrapped once
    its code (or `type:` in .github/showcase.yml) gives the real type. Any human edit inside the block changes its
    hash, and from then on the block is the repository's own: never overwritten (callers drop the marker)."""
    if not already_normalized:
        text = normalize_text(text)
    if ctx.meta.get("is_template") or bootstrap_state(text) != "pristine":
        return text
    variant = ctx.det["variant"]
    order = required_sections(ctx.det, meta=ctx.meta)
    secs = []
    for h2, req in order:
        if h2 in ("License", "Licensing"):
            continue
        body = section_facts(ctx, h2)
        if body:
            secs.append(f"## {h2}\n\n{body}")
        elif req == "R":
            secs.append(f"## {h2}\n\n<!-- needs-input: {variant}:{h2} -- write from repository facts only -->")
            ctx.log(f"needs-input:{variant}:{h2}")
    new = pristine_block("\n\n".join(secs))
    tb = _template_block(text)
    assert tb is not None  # bootstrap_state verified the template body
    text = text[:tb.start()] + new + text[tb.end():]
    # the header: rebuilt for this variant unless a person retitled the README
    region = _header_region(text)
    if region is not None:
        header_end, markers, old_title = region
        auto = cased_title(ctx.repo, ctx.meta.get("description") or "")
        if old_title is None or old_title.strip() in (TEMPLATE_H1, auto, slug_title(ctx.repo)):
            # Carry an authored tagline forward under the same rule as an in-place refresh.
            if variant == "J" and _badge_blocks_need_in_place_refresh(text, markers):
                return header_only(ctx, text, already_normalized=True)
            blocks = {m.group(1): m.group(2) for m in markers}
            old = blocks["tagline"]
            authored_hero = next((m.group(0) for m in markers
                                  if m.group(1) == "banner" and personal_profile(ctx)
                                  and not personal_generated_hero(ctx, m.group(2))), None)
            new_header = header(ctx, keep_banner=authored_hero, title=auto, tagline=tagline_body(ctx, old, text),
                                existing_badges=blocks.get("badges"))
            text = new_header + "\n\n" + text[header_end:].lstrip("\n")
    return header_only(ctx, text, already_normalized=True)


def bootstrap_contributing(ctx: RepoContext, text: str) -> str:
    """Point the template's own `.github` guide links at this org. Only links to the template owner's `.github` (any
    of its logins) change; a link to another org's or an upstream's guide or security policy stays as written."""
    from .intake import TEMPLATE_REPO
    tpl = TEMPLATE_REPO.split("/")[0]
    try:
        logins = {x.lower() for x in ctx.brand.resolver().aliases(tpl)}
    except AttributeError:  # a context without a brand: the template login alone
        logins = {tpl.lower()}

    def sub(m):
        return m.group(1) + ctx.owner + m.group(3) if m.group(2).lower() in logins else m.group(0)
    return re.sub(r"(https://github\.com/)([A-Za-z0-9-]+)(/\.github/blob/main/(?:CONTRIBUTING|SECURITY)\.md)", sub,
                  text).replace(f"[{tpl} contributing guide]", f"[{ctx.owner} contributing guide]")


# ------------------------------------------------------------------------------------------------
# Safety checks
# ------------------------------------------------------------------------------------------------
def managed_reason(ctx: RepoContext, text: str) -> str | None:
    """Detect an explicit generator ownership notice near the top of a README."""
    if (ctx.override.get("readme") or {}).get("managed") is True:
        return "readme.managed is true in the repository configuration"

    text = normalize_text(text)
    lines = text.split("\n")[:20]
    intro_end = len("\n".join(lines))
    notices = [text[comment.start():min(comment.end(), intro_end)]
               for comment in find_blocks(HTML_COMMENT, text) if comment.start() < intro_end]
    if lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() in ("---", "..."):
                break
            if re.match(r"\s*generated[_-]by\s*:\s*\S", line, re.I):
                return "generator ownership notice in the first 20 lines"
            notices.append(line)
    for line in masked(text)[:intro_end].split("\n"):
        line = line.lstrip(" \t#>*_")
        match = MANAGED_NOTICE.match(line)
        if match:
            notices.append(match.group(0))
    if any(MANAGED_NOTICE.search(notice) for notice in notices):
        return "generator ownership notice in the first 20 lines"
    return None


def heading_moves(before: str, after: str, variant: str) -> list[dict]:
    """Report changes to matched ATX headings, with duplicate matches marked as ambiguous."""
    if before == after:
        return []
    rules = standard("readme-variants")
    renames = rules["renames"]
    aliases = {alias.casefold(): heading.casefold()
               for heading, names in rules["aliases_for_status"].get(variant, {}).items() for alias in names}
    pattern = re.compile(r"(?m)^ {0,3}(#{1,6})[ \t]+(.*)$")

    def headings(text):
        text = normalize_text(text)
        groups = {}
        for match in pattern.finditer(_heading_view(text)):
            title = re.sub(r"[ \t]+#+[ \t]*$", "", text[match.start(2):match.end(2)]).strip()
            key = EMOJI.sub("", title).strip()
            key = renames.get(key.lower(), key).casefold()
            groups.setdefault(key, []).append((len(match[1]), title))
        return groups

    old, new = headings(before), headings(after)
    moves = []
    for key, previous in old.items():
        alternate = aliases.get(key)
        if key not in new and alternate and alternate not in old:
            key = alternate
        current = new.get(key)
        if not current or previous == current:
            continue
        if len(previous) != 1 or len(current) != 1:
            if Counter(previous) != Counter(current):
                moves.append({"heading": previous[0][1], "ambiguous": True,
                              "old_levels": [level for level, _ in previous],
                              "new_levels": [level for level, _ in current]})
            continue
        old_level, old_title = previous[0]
        new_level, new_title = current[0]
        moves.append({"heading": old_title, "from": old_level, "to": new_level, "new_heading": new_title})
    return moves


def nonws(s: str) -> int:
    return len(re.sub(r"\s", "", s))


def preservation(before: str, after: str, removed: list[str], *, ctx: RepoContext | None = None) -> list[str]:
    """Every original non-header line survives (heading lines may be renamed); size drop <= 10%."""
    # A digest in the output is only a claim. Exempt at most one prior block
    # per claim and independently verify that the prior rows are strict legacy.
    prior_blocks = [m for m in find_blocks(MARK, before) if m.group(1) == "badges"]
    prior_badges = Counter(m.group(2) for m in prior_blocks)
    current_blocks = [m for m in find_blocks(MARK, after) if m.group(1) == "badges"]
    current_badges = Counter(m.group(2) for m in current_blocks)
    replacements = Counter()
    for body, count in (current_badges - prior_badges).items():
        if generated_badges(body):
            match = GENERATED_BADGES.fullmatch(body)
            if match.group(2):
                replacements[match.group(2)] += count
    brand = ctx.brand if ctx else None
    style = ctx.style if ctx else None
    retained = Counter(m.group(0) for m in current_blocks)

    def ci_matches(owner, repo):
        return ctx is not None and _legacy_ci_matches(ctx, owner, repo)
    problems = []

    old_taglines = [m for m in find_blocks(MARK, before) if m.group(1) == "tagline"]
    new_taglines = [m for m in find_blocks(MARK, after) if m.group(1) == "tagline"]
    replace_tagline = (len(old_taglines) == len(new_taglines) == 1
                       and taglinemod.payload(old_taglines[0].group(2)) is not None
                       and taglinemod.payload(new_taglines[0].group(2)) is not None)
    remaining_taglines = Counter(normalize_line_endings(m.group(2)) for m in new_taglines)
    for block in old_taglines:
        body = normalize_line_endings(block.group(2))
        if not body.strip() or taglinemod.payload(body) is not None:
            continue
        if remaining_taglines[body]:
            remaining_taglines[body] -= 1
        elif ctx is not None and inherited_tagline(ctx, body, before) and remaining_taglines[""]:
            remaining_taglines[""] -= 1
        else:
            problems.append("lost authored tagline block")

    def omit_owned_tagline(m):
        return wrap("tagline", "") if m.group(1) == "tagline" else m.group(0)

    def omit_owned_badges(m):
        nonlocal brand
        body = m.group(2)
        if generated_badges(body):
            return wrap("badges", "")
        if retained[m.group(0)]:
            retained[m.group(0)] -= 1
            return m.group(0)
        digest = badge_sha(body)
        if replacements[digest]:
            if brand is None:
                from .config import load_brand
                brand = load_brand(prefer_lock=True)
            if _legacy_badge_body(brand, body, style, ci_matches=ci_matches):
                replacements[digest] -= 1
                return wrap("badges", "")
        authored = body.strip(" \t\r\n")
        if authored and (ctx is None or ctx.det["variant"] == "J"):
            problems.append(f"lost badge block: {authored[:60]}")
        return m.group(0)

    comparison = []
    offset = 0
    for block in prior_blocks:
        comparison.extend((before[offset:block.start()], omit_owned_badges(block)))
        offset = block.end()
    comparison.append(before[offset:])
    before = "".join(comparison)
    if replace_tagline:
        # Badge spans belong to the original source; use them before changing
        # tagline lengths. Generated output cannot stand in for authored text.
        before = _sub_blocks(before, omit_owned_tagline)
        after = _sub_blocks(after, omit_owned_tagline)
    before_lines = (line.strip(" \t") for line in source_lines(before))
    b_lines = Counter(line for line in before_lines if line and not line.startswith("<!-- showcase:"))
    for r in removed:
        b_lines[r.strip(" \t")] -= 1
    a_lines = Counter(line.strip(" \t") for line in source_lines(after) if line.strip(" \t"))
    for ln, n in b_lines.items():
        if n <= 0:
            continue
        if ln.startswith("#"):
            continue  # headings may be renamed / demoted / emoji-stripped
        if a_lines.get(ln, 0) < n:
            problems.append(f"lost line: {ln[:60]}")
    nb, na = nonws(before), nonws(after)
    if nb and na < nb * 0.9:
        problems.append(f"non-whitespace dropped {nb} -> {na}")
    return problems


def read_text(path: Path) -> str:
    """A README's text without a leading byte order mark ('' when missing)."""
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return text[1:] if text.startswith(BOM) else text


_LINE_END = re.compile(r"\r\n|\r|\n")


def _line_sections(text: str, lines: list[str]) -> list[str | None]:
    """Identify the H2 section owning each line, excluding literal code headings."""
    blocks = iter(code_block_spans(text)) if re.search(r"(?m)^## (?!#)", text) else iter(())
    block = next(blocks, None)
    section = None
    offset = 0
    names = []
    for line in lines:
        while block is not None and block[1] <= offset:
            block = next(blocks, None)
        if line.startswith("## ") and line[3:4] != "#" and (block is None or offset < block[0]):
            section = line[3:].strip()
        names.append(section)
        offset += len(line) + 1
    return names


def _managed_line_matches(before: str, after: str, old: list[str], new: list[str]) -> dict[int, int]:
    """Pair unchanged managed blocks before matching individual repeated lines."""
    originals = defaultdict(deque)
    old_offsets = [0, *(ending.end() for ending in re.finditer("\n", before))]
    new_offsets = [0, *(ending.end() for ending in re.finditer("\n", after))]
    for block in find_blocks(MARK, before):
        originals[block.group(0)].append(block.start())
    matched = {}
    used = set()
    for block in find_blocks(MARK, after):
        if not (origins := originals.get(block.group(0))):
            continue
        old_start = bisect_right(old_offsets, origins.popleft()) - 1
        start_line = bisect_right(new_offsets, block.start()) - 1
        end_line = min(bisect_right(new_offsets, block.end()), len(new) - 1)
        for new_index in range(start_line, end_line):
            old_index = old_start + new_index - start_line
            if (old_index < len(old) - 1 and old[old_index] == new[new_index]
                    and old_index not in used and new_index not in matched):
                matched[new_index] = old_index
                used.add(old_index)
    return matched


def restore_line_endings(raw: str, before: str, after: str) -> str:
    """`after` with the authored line endings of `raw` restored (#160).

    `read_text` decodes with universal newlines, so `before` holds one LF for
    every CRLF, lone CR or LF in `raw` (the file's own text).
    Each line `after` keeps unchanged from `before` takes its original
    ending back; a new or edited line takes the README's most common ending.
    An LF-only README is returned unchanged.
    """
    endings = _LINE_END.findall(raw)
    if not endings or all(e == "\n" for e in endings):
        return after
    counts = Counter(endings)
    common = counts.most_common(1)[0][0]
    if len(counts) == 1:
        return after.replace("\n", common)
    old, new = before.split("\n"), after.split("\n")
    # One ending follows every line but the last; the last line has none.
    if len(old) != len(endings) + 1:
        return after.replace("\n", common)  # not a universal-newline view of raw: keep the style only
    # Keep the unchanged edges anchored. Match the remaining equal lines
    # by occurrence, including lines moved during section reordering.
    old_count, new_count = len(old) - 1, len(new) - 1
    old_sections, new_sections = _line_sections(before, old), _line_sections(after, new)
    anchored = _managed_line_matches(before, after, old, new)
    used = set(anchored.values())

    def matches_edge(old_index, new_index):
        if (old[old_index], old_sections[old_index]) != (new[new_index], new_sections[new_index]):
            return False
        matched = anchored.get(new_index)
        return matched == old_index if matched is not None else old_index not in used

    head = 0
    while head < min(old_count, new_count) and matches_edge(head, head):
        head += 1
    tail = 0
    while tail < min(old_count, new_count) - head:
        if not matches_edge(old_count - 1 - tail, new_count - 1 - tail):
            break
        tail += 1
    old_middle = range(head, old_count - tail)
    new_middle = range(head, new_count - tail)

    def unique_context(lines, indexes, offsets, sections):
        keys = {}
        for i in indexes:
            if sections is not None and sections[i] is None:
                continue
            key = (sections[i] if sections is not None else None,
                   *(lines[i + offset] if i + offset >= 0 else None for offset in offsets))
            keys[key] = i if key not in keys else None
        return keys

    def match_context(old_scope, new_scope):
        for offsets in ((-1, 0, 1), (-1, 0), (0, 1)):
            old_keys = unique_context(old, old_middle, offsets, old_scope)
            for key, new_index in unique_context(new, new_middle, offsets, new_scope).items():
                old_index = old_keys.get(key)
                if new_index is not None and old_index is not None and new_index not in anchored and old_index not in used:
                    anchored[new_index] = old_index
                    used.add(old_index)

    # Pair repeated authored lines with their named section before allowing
    # matches across sections. Adjacent context still distinguishes repeats
    # within a section. Each pass visits each line at most once.
    if any(old_sections) and any(new_sections):
        match_context(old_sections, new_sections)
        section_rows = defaultdict(deque)
        for i in old_middle:
            if i not in used and old_sections[i] is not None:
                section_rows[(old_sections[i], old[i])].append(i)
        for i in new_middle:
            if i in anchored or new_sections[i] is None:
                continue
            if associated := section_rows.get((new_sections[i], new[i])):
                anchored[i] = associated.popleft()
                used.add(anchored[i])
    match_context(None, None)

    remaining = defaultdict(deque)
    for i in old_middle:
        if i not in used:
            remaining[old[i]].append(endings[i])
    out_ends = endings[:head]
    from_source = [True] * head
    for i in new_middle:
        if i in anchored:
            out_ends.append(endings[anchored[i]])
            from_source.append(True)
        elif source := remaining.get(new[i]):
            out_ends.append(source.popleft())
            from_source.append(True)
        else:
            out_ends.append(common)
            from_source.append(False)
    out_ends.extend(endings[old_count - tail:])
    from_source.extend([True] * tail)
    # CR and an adjacent LF would be read back as one CRLF. Use CRLF for a
    # newly rendered line first, preserving the ending of a retained line.
    for i in range(1, len(out_ends)):
        if not new[i] and out_ends[i - 1] == "\r" and out_ends[i] == "\n":
            target = i - 1 if from_source[i] and not from_source[i - 1] else i
            out_ends[target] = "\r\n"
    return "".join(line + end for line, end in zip(new, out_ends)) + new[-1]
