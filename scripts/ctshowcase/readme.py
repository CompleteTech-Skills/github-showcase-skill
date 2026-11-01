"""README scaffold / upgrade / header / bootstrap per STANDARD §7 with decision 13 header order (spec A6.6).

Generated blocks sit between `<!-- showcase:<block>:start -->` / `:end -->` markers so reruns replace only
those blocks. Content is never invented (§1.5 rule 2) and never lost (§7.1 restructuring, multiset check).
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from . import footer as footermod
from .context import RepoContext
from .detect import standard
from .mdcode import code_spans, find_blocks, masked  # noqa: F401  (code_spans: re-exported for callers)

MARK = re.compile(r"<!-- showcase:([a-z-]+):start -->\n?(.*?)\n?<!-- showcase:\1:end -->", re.S)
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
SHIELDS = "https://img.shields.io/badge/"
BOM = "\ufeff"


def normalize_text(text: str) -> str:
    """README text as the tools read it: LF line endings, no leading UTF-8 byte order mark (a BOM would hide the H1
    from every `^#` match)."""
    text = text.replace("\r\n", "\n")
    return text[1:] if text.startswith(BOM) else text


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
    fence = None
    for line in text.splitlines():
        m = re.match(r"^(```+|~~~+)", line)
        if m:
            fence = None if fence and line.startswith(fence) else (fence or m.group(1))
        if fence is None and re.match(r"^## (?!#)", line):
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
        if f.exists("LICENSING.md"):
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


def banner_html(ctx: RepoContext) -> str:
    return (f'<p align="center">\n  <img src="docs/images/banner.png" alt="{ctx.repo} by {ctx.company}" width="100%">\n</p>')


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
    elif ctx.det.get("category"):
        out.append((f"Type {ctx.det['category']}", f"{SHIELDS}type-{shield(ctx.det['category'])}-{b['brand']}{extra}", None))
    lic = ctx.meta.get("license")
    if not ctx.public:
        out.append(("License proprietary", f"{SHIELDS}license-proprietary-{b['neutral']}", None))
    elif lic and lic not in ("NOASSERTION", "other"):
        if ctx.org.get("license_chip") and lic.upper().startswith("AGPL"):
            out.append(("AGPL-3.0 or commercial license", f"{SHIELDS}license-{shield('AGPL-3.0 | commercial')}-{b['neutral']}",
                        "LICENSING.md" if f.exists("LICENSING.md") else None))
        else:
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


def nav_first(ctx: RepoContext) -> bool:
    """§7.1 order: hero banner, then the nav line (review q57 `nav` default); brand.yaml `readme.nav_first` restores
    the nav-first order only if the user answers "Nav line first"."""
    return bool(ctx.brand.readme_opts.get("nav_first"))


def lead(ctx: RepoContext, banner: str, nav: str) -> list[str]:
    """The banner and nav blocks in the configured order."""
    return [nav, banner] if nav_first(ctx) else [banner, nav]


def inherited_tagline(ctx: RepoContext, body: str, text: str) -> bool:
    """True when the tagline block `body` of README `text` came from the template this repository was generated from
    (never another repository's line is kept): it is one of meta template_taglines (the template's tagline when this
    repository was generated, and today); only when those are unknown, an untouched (pristine) template body stands in
    as the proof. The template repository's own tagline is never inherited."""
    if ctx.meta.get("is_template"):
        return False
    known = [x.strip() for x in ctx.meta.get("template_taglines") or [] if isinstance(x, str) and x.strip()]
    return body.strip() in known if known else bootstrap_state(text) == "pristine"


def tagline_body(ctx: RepoContext, existing: str | None = None, text: str = "") -> str:
    """The tagline block body, decided in this one place for header(), bootstrap(), upgrade() and header_only().
    R2: the tagline is the description. Without one (logged needs-input:description) the block keeps `existing`, the
    body it holds now in README `text`, unless that is inherited (guardrail 6: improve, never erase); nothing to keep
    gives an empty block, never "****"."""
    desc = (ctx.meta.get("description") or "").strip()
    if desc:
        return f'<p align="center"><b>{desc}</b></p>' if ctx.det["variant"] == "F" else f"**{desc}**"
    ctx.log("needs-input:description")
    if existing is None or not existing.strip() or inherited_tagline(ctx, existing, text):
        return ""
    return existing


def header(ctx: RepoContext, keep_banner: str | None = None, title: str | None = None,
           tagline: str | None = None) -> str:
    """The §7.2 header. `tagline` is the tagline block body a caller already decided with tagline_body() (the body it
    carries over from the header it replaces); None writes the description's tagline, or an empty block."""
    tag = wrap("tagline", tagline_body(ctx) if tagline is None else tagline)
    banner = keep_banner if keep_banner is not None else wrap("banner", banner_html(ctx))
    if ctx.det["variant"] == "F":
        parts = [*lead(ctx, banner, wrap("nav", nav_line(ctx))), wrap("badges", badges_html(ctx)), tag, "---"]
        return "\n\n".join(p for p in parts if p)
    parts = [*lead(ctx, banner, wrap("nav", nav_line(ctx))), '<div align="center">', f"# {title or product_name(ctx)}",
             wrap("badges", badges_md(ctx)), tag, "</div>", "---"]
    return "\n\n".join(p for p in parts if p)


# ------------------------------------------------------------------------------------------------
# License (§7.6) and section facts
# ------------------------------------------------------------------------------------------------
def license_section(ctx: RepoContext) -> tuple[str, str] | None:
    rv = standard("readme-variants")["license_rows"]
    lic, f = ctx.meta.get("license"), ctx.facts
    third = f.known and (ctx.repo.endswith("-fork") or any(x.startswith(("vendor/", "third_party/")) for x in f.files))
    if third:
        ctx.log("needs-input:upstream")
        return None
    # visibility first: a private repository is proprietary in every org, Security included (LICENSE-POLICY.md)
    if ctx.public and (ctx.det["variant"] == "F" or (ctx.org.get("license_chip") and lic and lic.upper().startswith("AGPL"))):
        return "Licensing", rv["security"]
    if not ctx.public:
        if ctx.same_owner("TouchedByAnAgent"):
            return "License", rv["private_hold"]
        year = (ctx.meta.get("created_at") or "")[:4]
        if not year:
            ctx.log("needs-input:license-year")
            return None
        private = rv["private"].replace("<year>", year)
        if ctx.org.get("family") not in (None, "completetech"):
            private = private.replace("CompleteTech LLC", ctx.org.get("display_name") or ctx.owner)
        return "License", private
    if lic == "MIT":
        if f.exists("BRAND_ASSETS.md"):
            return "License", rv["skills_mit"]
        if ctx.tier.startswith("T2") or ctx.org.get("family") not in (None, "completetech"):
            return "License", rv["t2_mit"].replace("<Brand>", ctx.org.get("display_name") or ctx.owner)
        return "License", rv["t1_mit"]
    if lic and lic not in ("NOASSERTION",):
        brand = ctx.company
        return "License", rv["other"].replace("<license>", lic).replace("<path>", "LICENSE").replace("<Brand>", brand)
    ctx.log("needs-input:license")
    return None


def section_facts(ctx: RepoContext, h2: str) -> str | None:
    """Body for a scaffolded section, only from repo facts; None means omit + needs-input."""
    f = ctx.facts
    if h2 == "Workflow Diagram" and f.read("assets/diagrams/workflow.mmd"):
        return ("Source: [assets/diagrams/workflow.mmd](assets/diagrams/workflow.mmd).\n\n```mermaid\n"
                + f.read("assets/diagrams/workflow.mmd").strip() + "\n```")
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
    variant = ctx.det["variant"]
    order = standard("readme-variants")["variants"].get(variant, [])
    parts = [header(ctx)]
    co = callout(ctx)
    if co:
        parts.append(co)
    keep = [ln for ln in existing.splitlines() if ln.strip() and not ln.startswith("# ")]
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
        parts.append(f"## {lic[0]}\n\n{lic[1]}")
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


def _leading_banner(pre: str) -> bool:
    """True when the README preamble opens with a third-party banner image (not ours, not a logo or badge)."""
    first_img = re.search(r"<(img|picture)\b[^>]*>|!\[[^\]]*\]\([^)]*\)", pre)
    return bool(first_img and "docs/images/banner.png" not in first_img.group(0)
                and not re.search(r"logo", first_img.group(0), re.I)
                and "shields.io" not in first_img.group(0) and "badge.svg" not in first_img.group(0)
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


BANNER_BLOCK = re.compile(re.escape(start("banner")) + r".*?" + re.escape(end("banner")) + r"\n*", re.S)


def callout_only(ctx: RepoContext, text: str) -> tuple[str, list[str]]:
    """Variants G and H (§7.4): the hero banner block, then the callout (unless one is already there), then the body
    unchanged, then the decision 18 footer. Nothing else changes. Watching-org forks never reach here (`readme`
    exempts them). Review q27 "Full CompleteTech treatment" (brand.yaml readme.fork_readme: full) means the fork
    follows its §5.4 variant instead: pass that variant with `readme --variant`.
    Returns (text, removed lines): a recognized old footer (marked or unmarked, `is_footer_copy`: for example one with
    the former logo URLs) is replaced by the current one, and only the removed footer lines that the replacement footer
    does not carry again are reported (multiset difference), so the preservation check accepts them. A re-emitted
    line is not reported, so it cannot weaken the never-drop-a-line guard. A marked footer that is not a footer copy
    (a partner image) is left as it is. A removed recognized footer is always replaced, even when fenced example text makes check() report drift."""
    if ctx.det["variant"] == "G" and ctx.brand.readme_opts.get("fork_readme") == "full":
        ctx.log("needs-input:fork-variant (q27 full treatment: pass readme --variant for the §5.4 variant)")
    body = text
    lead_banner = ""
    m = BANNER_BLOCK.match(text.lstrip("\n"))
    if m:  # our banner block is already on top (a re-run): keep it, look for the callout under it
        body = text.lstrip("\n")[m.end():]
    first = next((ln for ln in body.splitlines() if ln.strip()), "")
    out = body
    if not first.lstrip().startswith(">"):
        if ctx.det["variant"] == "G":
            co = fork_callout(ctx)
        else:
            co = None  # the H callout needs the archive date and reason from the registry
            ctx.log("needs-input:archive-callout")
        if co:
            out = co + "\n\n" + body.lstrip("\n")
    if ctx.art_status()["banner"] is None:
        lead_banner = wrap("banner", banner_html(ctx)) + "\n\n"  # decision 13: the hero banner opens G and H too
    elif m:
        lead_banner = text.lstrip("\n")[:m.end()].rstrip("\n") + "\n\n"
    out = lead_banner + out.lstrip("\n")
    removed: list[str] = []
    if footer_wanted(ctx):
        had_footer = False
        if footermod.check(ctx.brand, out)[0] != "pass":
            pos, kept = 0, []
            for fm in find_blocks(MARK, out):
                if fm.group(1) == "footer" and is_footer_copy(fm.group(2), ctx.brand):
                    kept.append(out[pos:fm.start()])
                    removed += [ln for ln in fm.group(2).splitlines() if ln.strip()]
                    had_footer = True
                    pos = fm.end()
            out = "".join(kept) + out[pos:]
            out, old_footer = drop_old_footer(out, ctx.brand)
            removed += old_footer
            if old_footer:
                had_footer = True
        if had_footer or footermod.check(ctx.brand, out)[0] == "fail:missing":
            out = out.rstrip("\n") + "\n\n" + footermod.block(ctx.brand) + "\n"
            # Report only the removed footer lines that the replacement footer does not carry again (multiset
            # difference), so a re-emitted line never counts as lost content in the preservation check.
            kept = Counter(ln.strip() for ln in footermod.block(ctx.brand).splitlines() if ln.strip())
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

    for line in block.splitlines():
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
    return body[:m.start()].rstrip() + "\n", [ln for ln in tail.splitlines() if ln.strip()]


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


def upgrade(ctx: RepoContext, text: str) -> tuple[str, list[str]]:
    """Return (new text, header lines removed). Raises nothing; callers run the shrink checks."""
    variant = ctx.det["variant"]
    rv = standard("readme-variants")
    if variant in ("G", "H"):
        return callout_only(ctx, normalize_text(text))
    text = normalize_text(text)
    body, blocks = _strip_markers(text)
    want_footer = footer_wanted(ctx)
    removed: list[str] = []
    # One multiset of the footer lines the emitted footer carries again, shared by the marked and the unmarked branch
    # because only one new footer is emitted. A compliant footer is re-emitted unchanged and must not weaken the
    # never-drop-a-line guard, so only the old lines it does not carry again are reported as removed.
    kept: Counter = Counter()
    if want_footer:
        kept = Counter(ln.strip() for ln in footermod.block(ctx.brand).splitlines() if ln.strip())
    if want_footer and blocks.get("footer") and is_footer_copy(blocks["footer"], ctx.brand):
        # A configured publication-path change replaces only our recognized footer, not authored credits or partner
        # images inside a similarly named block.
        for ln in blocks["footer"].splitlines():
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
    lines = pre.splitlines()
    if _leading_banner(pre) and (ctx.tier == "T2" or preserve):
        preserve = True
        # q57 `pres`: the hero goes above the README's own banner (kept directly under it), or nothing is added
        ctx.log("exempt:preserve-banner" if ctx.preserve_unchanged() else "preserve-banner:kept-below-hero")
    desc = (ctx.meta.get("description") or "").strip()
    old_tag = blocks.get("tagline")
    if preserve and old_tag is not None:
        # additive only, so the tagline block stays where it is, its body decided by the header rule (tagline_body)
        tag = tagline_body(ctx, old_tag, text)
        if old_tag.strip() and not tag:  # an inherited tagline, emptied on purpose (not a lost line)
            removed += [ln for ln in old_tag.splitlines() if ln.strip()]
        body, _ = _strip_markers(text, keep={"tagline": tag})
        if want_footer:
            body, _ = drop_old_footer(body, ctx.brand, own_site=True)  # its lines are already in `removed`
        pre, sections = split_sections(body)
        lines = pre.splitlines()
    # an unmarked bold line opening the preamble is an old tagline. With a description it is replaced; without one it
    # is carried into an empty tagline block (header rule), and a second one stays as authored text: never erased
    carry: list[str] = []
    # the pristine-body fallback alone would decide the tagline block (no known template taglines): a bare bold line
    # the template cannot have written must not be moved into a block that later runs would empty
    fallback_only = (not ctx.meta.get("is_template") and not [x for x in ctx.meta.get("template_taglines") or []
                                                               if isinstance(x, str) and x.strip()]
                     and bootstrap_state(text) == "pristine")

    def is_header_line(ln: str) -> bool:
        s_ = ln.strip()
        if HEADER_LINE.match(ln) or "docs/images/banner.png" in ln:
            return True
        return bool(desc) and s_ in (f"**{desc}**", f"<p align=\"center\"><b>{desc}</b></p>", f"<b>{desc}</b>")

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
            bold = re.fullmatch(r"\*\*[^*]+\*\*", s_) is not None and not "".join(keep_pre).strip()
            is_hdr = is_header_line(ln) or bold
            if preserve:  # additive only: just an old nav line is replaced
                is_hdr = s_.startswith("**") and " · " in s_ and not "".join(keep_pre).strip()
            elif bold and not is_header_line(ln) and not desc:
                if carry or (old_tag or "").strip() or fallback_only:
                    # the tagline block already has a line, or (an untouched template copy whose template taglines
                    # are unknown) the block rule would empty any line moved into it: this one stays authored text
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
    intro = "\n".join(keep_pre).strip()
    # sections: renames, mapping, Notes demotion, License last
    renames = rv["renames"]
    order = [h for h, _ in rv["variants"].get(variant, [])]
    low_order = {h.lower(): h for h in order}
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
            notes.append(f"### {clean}\n{b.rstrip()}" if b.strip() else f"### {clean}")
    out = []
    if preserve:
        # §7.0 preserve list: additive only. The hero banner block goes on top (q57 `pres` default, "Banner above the
        # existing content"; none when the user answers "Leave them unchanged"), with the nav line in the §7.1 order;
        # the README's own banner and every section stay verbatim and in place; add License if missing, then footer.
        if ctx.preserve_unchanged() or ctx.art_status()["banner"] is not None:
            out.append(wrap("nav", nav_line(ctx)))
        else:
            out += lead(ctx, wrap("banner", banner_html(ctx)), wrap("nav", nav_line(ctx)))
        if intro:
            out.append(intro)
        for h, b in sections:
            out.append(f"## {h}\n{b.rstrip()}" if b.strip() else f"## {h}")
        if not any(h.strip().lower() in ("license", "licensing", "licence") for h, _ in sections):
            lic = license_section(ctx)
            if lic:
                out.append(f"## {lic[0]}\n\n{lic[1]}")
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
            removed += [ln for ln in old_tag.splitlines() if ln.strip()]
        out.append(header(ctx, tagline=new_tag))
        co = callout(ctx)
        if co and co not in intro:
            out.append(co)
        if intro:
            if variant == "A" or "About" in placed or "About" not in order:
                out.append(intro)
            else:
                placed["About"] = intro + ("\n\n" + placed["About"] if placed.get("About") else "")
    for h in order:
        if h in ("License", "Licensing"):
            continue
        if h in placed:
            out.append(f"## {h}\n\n{placed[h].strip()}" if placed[h].strip() else f"## {h}")
        elif dict(rv["variants"][variant]).get(h) == "R" and not preserve:
            body = section_facts(ctx, h)
            if body:
                out.append(f"## {h}\n\n{body}")
            else:
                ctx.log(f"needs-input:{variant}:{h}")
    if existing_notes or notes:
        nb = "\n\n".join(x for x in ([existing_notes] if existing_notes else []) + notes)
        out.append(f"## Notes\n\n{nb}")
    if license_body:
        out.append(f"## {license_body[0]}\n\n{license_body[1].strip()}")
    else:
        lic = license_section(ctx)
        if lic:
            out.append(f"## {lic[0]}\n\n{lic[1]}")
    if want_footer:
        out.append(footermod.block(ctx.brand))
    for b in ("template-body", "checklist"):  # inserted in reverse: the checklist stays above the body
        if b in blocks:
            out.insert(1 if not preserve else 1, wrap(b, blocks[b]))
    return "\n\n".join(x for x in out if x) + "\n", removed


def header_only(ctx: RepoContext, text: str) -> str:
    """Replace only existing marker blocks (what the Action runs)."""
    text = normalize_text(text)
    desc = (ctx.meta.get("description") or "").strip()
    gen = {"nav": nav_line(ctx), "banner": banner_html(ctx), "footer": footermod.markup(ctx.brand)}
    if ctx.repo_dir is not None and not (ctx.repo_dir / "docs" / "images" / "banner.png").is_file():
        gen["banner"] = ""  # no image yet (for example no description): an empty block, never a broken image
        ctx.log("needs-input:banner")
    gen["badges"] = badges_html(ctx) if ctx.det["variant"] == "F" else badges_md(ctx)

    def sub(m):
        b, body = m.group(1), m.group(2)
        if b == "checklist":
            if re.search(r"- \[ \]", body):
                return m.group(0)
            return ""
        if b == "tagline":  # tagline_body: the description's line, else the block as written unless inherited
            new = tagline_body(ctx, body, text)
            return m.group(0) if not desc and new == body else wrap(b, re.sub(r"\n{3,}", "\n\n", new))
        if b in gen:
            return wrap(b, re.sub(r"\n{3,}", "\n\n", gen[b]))
        return m.group(0)
    return license_block(ctx, reorder_lead(ctx, _sub_blocks(text, sub)))


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


LEAD_PAIR = re.compile(r"\A(\s*)(" + re.escape(start("nav")) + r".*?" + re.escape(end("nav")) + r")(\s*)(" +
                       re.escape(start("banner")) + r".*?" + re.escape(end("banner")) + r")", re.S)
LEAD_PAIR_REV = re.compile(r"\A(\s*)(" + re.escape(start("banner")) + r".*?" + re.escape(end("banner")) + r")(\s*)(" +
                           re.escape(start("nav")) + r".*?" + re.escape(end("nav")) + r")", re.S)


def reorder_lead(ctx: RepoContext, text: str) -> str:
    """Swap a README's leading nav and banner marker blocks into the configured §7.1 order (q57 `nav`), so READMEs
    written before the order changed follow it on the next header refresh. Only the two adjacent top blocks move."""
    pat = LEAD_PAIR_REV if nav_first(ctx) else LEAD_PAIR
    return pat.sub(lambda m: m.group(1) + m.group(4) + m.group(3) + m.group(2), text, count=1)


LICENSE_MARK = "<!-- showcase:license -->"


def license_block(ctx: RepoContext, text: str) -> str:
    """Rewrite the paragraph after `<!-- showcase:license -->` (and its H2) from license_section(), with or without a
    LICENSE file: a private repository reads "Proprietary...", a Security repository gets "## Licensing". When the
    section cannot be derived (needs-input), the existing text stays."""
    i = masked(text).find(LICENSE_MARK)  # the first mark outside code (a documented example is left alone)
    if i < 0:
        return text
    lic = license_section(ctx)
    if not lic:
        return text
    m = re.compile(re.escape(LICENSE_MARK) + r"\n(.*?)(\n\n|\n?$)", re.S).match(text, i)
    if m:
        text = text[:i] + LICENSE_MARK + "\n" + lic[1] + m.group(2) + text[m.end():]
    h = re.search(r"(?m)^## (?:License|Licensing|Licence)[ \t]*\n(\n?)\Z", text[:i])
    return text[:h.start()] + f"## {lic[0]}\n" + h.group(1) + text[i:] if h else text


TEMPLATE_H1 = "CompleteTech Repo Template"
PRISTINE = re.compile(r"<!-- showcase:template-body:pristine(?: sha256=([0-9a-f]{64}))? -->\n?")
TEMPLATE_BODY = re.compile(re.escape(start("template-body")) + r"\n?(.*?)\n?" + re.escape(end("template-body")), re.S)


def body_sha(body: str) -> str:
    import hashlib
    return hashlib.sha256(body.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()


def pristine_block(body: str) -> str:
    """A template-body block whose marker carries the sha256 of the generated sections."""
    return wrap("template-body", f"<!-- showcase:template-body:pristine sha256={body_sha(body)} -->\n{body}")


def bootstrap_state(text: str) -> str:
    """'pristine' (the block is byte-for-byte what was generated), 'edited' (a marker without a matching hash: a person
    wrote in the block) or 'none' (no marker: the README is the repository's own)."""
    found = find_blocks(TEMPLATE_BODY, normalize_text(text))
    if not found:
        return "none"
    m = found[0]
    pm = PRISTINE.search(m.group(1))
    if not pm:
        return "none"
    rest = PRISTINE.sub("", m.group(1), count=1)
    return "pristine" if pm.group(1) and pm.group(1) == body_sha(rest) else "edited"


def drop_pristine(text: str) -> str:
    """`text` without the pristine marker of the first template-body block outside code; a marker shown as an example
    (inline or fenced code) stays byte-identical."""
    found = find_blocks(TEMPLATE_BODY, text)
    if not found:
        return text
    tb = found[0]
    return text[:tb.start(1)] + PRISTINE.sub("", tb.group(1), count=1) + text[tb.end(1):]


def _header_region(text: str) -> re.Match | None:
    """From the top of the README to the rule after the tagline block (the §7.2 header)."""
    return re.match(r"\A.*?" + re.escape(end("tagline")) + r"\n(?:.*?\n)??---\n", text, re.S)


def bootstrap(ctx: RepoContext, text: str) -> str:
    """Fill a README that still carries a generated (pristine) template body: the README variant's sections from
    repository facts, the variant's header (Variant F has no H1) and the license section. A pristine body is
    regenerated on later runs too, so a repository typed `workspace` on its creation commit is re-bootstrapped once
    its code (or `type:` in .github/showcase.yml) gives the real type. Any human edit inside the block changes its
    hash, and from then on the block is the repository's own: never overwritten (callers drop the marker)."""
    text = normalize_text(text)
    if ctx.meta.get("is_template") or bootstrap_state(text) != "pristine":
        return text
    variant = ctx.det["variant"]
    order = standard("readme-variants")["variants"].get(variant, [])
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
    tb = find_blocks(TEMPLATE_BODY, text)[0]  # bootstrap_state found it outside code
    text = text[:tb.start()] + new + text[tb.end():]
    # the header: rebuilt for this variant unless a person retitled the README
    hm = _header_region(text)
    if hm:
        h1 = re.search(r"(?m)^# (.+)$", hm.group(0))
        auto = cased_title(ctx.repo, ctx.meta.get("description") or "")
        if not h1 or h1.group(1).strip() in (TEMPLATE_H1, auto, slug_title(ctx.repo)):
            # the tagline block carries over (tagline_body), so a line the owner wrote survives the rebuild and only an
            # inherited one is emptied, exactly as header_only decides it
            old = next((m.group(2) for m in find_blocks(MARK, hm.group(0)) if m.group(1) == "tagline"), None)
            new_header = header(ctx, title=auto, tagline=tagline_body(ctx, old, text))
            text = new_header + "\n\n" + text[hm.end():].lstrip("\n")
    return header_only(ctx, text)


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
def nonws(s: str) -> int:
    return len(re.sub(r"\s", "", s))


def preservation(before: str, after: str, removed: list[str]) -> list[str]:
    """Every original non-header line survives (heading lines may be renamed); size drop <= 10%."""
    problems = []
    b_lines = Counter(ln.strip() for ln in before.splitlines() if ln.strip() and not ln.strip().startswith("<!-- showcase:"))
    for r in removed:
        b_lines[r.strip()] -= 1
    a_lines = Counter(ln.strip() for ln in after.splitlines() if ln.strip())
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
