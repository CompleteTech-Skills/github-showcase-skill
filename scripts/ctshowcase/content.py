"""`showcase.py content ...`: links (CQ-04, RP-09), linguist (RP-07, CQ-08), actions (RP-06, RP-01, CQ-13), images
(RP-03, RP-10), sidebar (RP-05), icon (RT-04) and social (R10; the contract name of the social preview, with the
hidden top-level `social-preview` kept as a deprecated alias).

Read-only toward GitHub, like every other module. Nothing here rewrites a README, edits `.gitattributes`, touches a
workflow file or uploads anything: each action reports facts and emits proposals (unified diffs, `gh` argv and
`scripts/writer.py` jobs `{id, phase, kind, repo|org, approval_id?, argv, note}`; UI-only steps are jobs of kind
`browser` with the exact click path in `steps`). The only files written are the paths given with `--report`, `--jobs`
(JSON lines, appended), `--out`, `--out-dir`, `--preview` and `--cache`. Network use is opt-in (`--online`): cached,
polite HEAD/GET requests and read-only `gh api` GETs.

Every org lookup goes through the shared `resolver.Resolver` (CQ-03): after an approved rename
(CompleTetech-Security -> CompleteTech-Security, CompleteTech-Pokemon -> CompleteTech-TCG) a repository keeps its
brand row, its owner status (watching, T3, excluded), its packages and its links, and jobs name the current login.
"""
from __future__ import annotations

import difflib
import hashlib
import html
import io
import json
import re
import subprocess
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import ROOT, STANDARD, __version__, estate_candidates
from .config import load_yaml_text
from .errors import CHECK_FAILED, OK, ArtFail, NeedsInput, Refused, ShowcaseError
from .resolver import Resolver

# the estate hand-off tree when the skill lives inside it (or is its installed copy); optional everywhere
ESTATE = next((c for c in estate_candidates() if (c / "art").is_dir()), ROOT.parent)
SKILL_ART_DIRECTION = ROOT / "references" / "art-direction.md"
DEFAULT_ART_DIRECTION = SKILL_ART_DIRECTION


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# =====================================================================================================
# Org lookups (CQ-03): always through the shared resolver.Resolver
# =====================================================================================================
def brand_key(r: Resolver | None, login: str) -> str:
    """The brand.yaml `orgs:` key for any login of the org (old or new), else the login itself."""
    return (r.brand_key(login) if r else None) or login


def current_login(r: Resolver | None, login: str) -> str:
    """The org's login after approved renames: what links, URLs and writer jobs name."""
    return r.canonical(login) if r else login


def org_row(r: Resolver | None, brand, login: str, require: bool = False) -> dict:
    if r is None:
        row = brand.org(login)
        if require and not row.get("known"):
            raise NeedsInput("org", f"{login} has no row in references/brand.yaml")
        return dict(row, brand_key=login)
    row = r.brand_org(login, strict=require)
    row.setdefault("brand_key", r.brand_key(login) or login)
    return row


def org_style(r: Resolver | None, brand, login: str) -> dict:
    return brand.style(brand_key(r, login))


def in_estate(r: Resolver | None, login: str) -> bool:
    """An org of the estate (a brand or registry row under any of its logins), not an excluded owner."""
    if r is None or not login:
        return False
    return (r.brand_key(login) is not None or r.registry_key(login) is not None) and r.owner_status(login) != "excluded"


def load_resolver(brand, registry=None, approved=None, approved_yaml=None, actions=None) -> Resolver:
    """The shared resolver from brand.yaml plus the registry and approvals (defaults: the estate bundle beside the
    skill, when present). Read-only: the registry is private data and is never copied anywhere."""
    return Resolver.from_paths(brand, registry, approved, approved_yaml, actions)


# =====================================================================================================
# Writer jobs
# =====================================================================================================
_JID = re.compile(r"[^A-Za-z0-9._:@/+-]+")
SAFETY_STEP = ("Never click a control inside a \"Danger Zone\" section and never type an owner, repository or org name "
               "into a confirmation field; if a dialog mentioning delete, transfer, archive, rename or visibility opens, "
               "press Escape and log ui-danger-dialog.")


def job_id(*parts) -> str:
    """A writer job id: letters, digits and ._:@/+- only (scripts/writer.py ID_RE), at most 200 characters."""
    s = _JID.sub("-", ":".join(str(p) for p in parts if p not in (None, ""))).strip("-.")
    return s[:200] or "job"


def writer_job(jid: str, phase, kind: str, target: str, argv: list, note: str, approval_id: str | None = None,
               **extra) -> dict:
    j = {"id": jid, "phase": str(phase), "kind": kind, ("repo" if "/" in target else "org"): target}
    if approval_id:
        j["approval_id"] = approval_id
    j["argv"] = [str(a) for a in argv]
    j["note"] = note
    j.update(extra)
    return j


def browser_job(jid: str, phase, target: str, url: str, ui_action: str, steps: list[str], note: str,
                approval: dict | None = None) -> dict:
    shot = "state/screens/" + re.sub(r"[^A-Za-z0-9._-]+", "_", jid) + ".png"
    steps = [*steps, f"Take a screenshot of the result and save it as {shot}.", SAFETY_STEP]
    j = writer_job(jid, phase, "browser", target, [], note, url=url, ui_action=ui_action, steps=steps)
    if approval:
        j["approval"] = approval
    return j


# =====================================================================================================
# Repository tree (what GitHub sees)
# =====================================================================================================
SKIP_WALK = {".git", "node_modules", ".venv", "venv", "__pycache__", ".showcase-cache"}


class Tree:
    """Files of a checkout as GitHub serves them: tracked plus untracked-but-not-ignored files that exist (git work
    tree), every file on disk (no git), or the tree at a git ref (`--base-ref`)."""

    def __init__(self, root: str | Path, ref: str | None = None):
        self.root, self.ref = Path(root), ref
        self.git = False
        self.files = self._list()
        self.lower: dict[str, list[str]] = {}
        self.dirs: set[str] = {""}
        for f in self.files:
            self.lower.setdefault(f.lower(), []).append(f)
            parts = f.split("/")
            for i in range(1, len(parts)):
                self.dirs.add("/".join(parts[:i]))
        self._cache: dict[str, str | None] = {}

    def _git(self, *args) -> str | None:
        try:
            p = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        return p.stdout.decode("utf-8", "surrogateescape") if p.returncode == 0 else None

    def _list(self) -> set[str]:
        if self.ref:
            out = self._git("ls-tree", "-r", "--name-only", "-z", self.ref)
            if out is None:
                raise ShowcaseError(f"cannot list {self.ref} in {self.root}", log="usage")
            self.git = True
            return {f for f in out.split("\0") if f}
        if (self.root / ".git").exists():
            out = self._git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
            if out is not None:
                self.git = True
                return {f for f in out.split("\0") if f and (self.root / f).is_file()}
        files = set()
        for p in self.root.rglob("*"):
            rel = p.relative_to(self.root)
            if p.is_file() and not (set(rel.parts) & SKIP_WALK):
                files.add(rel.as_posix())
        return files

    def is_file(self, rel: str) -> bool:
        return rel in self.files

    def is_dir(self, rel: str) -> bool:
        return rel.rstrip("/") in self.dirs

    def read(self, rel: str) -> str | None:
        if rel not in self._cache:
            if rel not in self.files:
                self._cache[rel] = None
            elif self.ref:
                self._cache[rel] = self._git("show", f"{self.ref}:{rel}")
            else:
                try:
                    self._cache[rel] = (self.root / rel).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    self._cache[rel] = None
        return self._cache[rel]

    def read_bytes(self, rel: str) -> bytes | None:
        if rel not in self.files:
            return None
        if self.ref:
            try:
                p = subprocess.run(["git", "-C", str(self.root), "show", f"{self.ref}:{rel}"], capture_output=True,
                                   timeout=60)
            except (OSError, subprocess.SubprocessError):
                return None
            return p.stdout if p.returncode == 0 else None
        try:
            return (self.root / rel).read_bytes()
        except OSError:
            return None

    def size(self, rel: str) -> int:
        if not self.ref:
            try:
                return (self.root / rel).stat().st_size
            except OSError:
                return 0
        b = self.read_bytes(rel)
        return len(b) if b is not None else 0


def displayed_readme(tree: Tree, given: str | None = None) -> str | None:
    """The README GitHub displays (RP-09): `.github/README.md`, then the root, then `docs/` (GitHub's precedence), or
    the `/readme` `.path` captured in metadata."""
    if given:
        return given if tree.is_file(given) else None
    for d in (".github/", "", "docs/"):
        for name in ("README.md", "readme.md", "Readme.md", "README.markdown", "README"):
            if tree.is_file(d + name):
                return d + name
    return None


def markdown_files(tree: Tree, readme: str | None) -> list[str]:
    """README (displayed path), docs/**/*.md, .github/*.md and the org profile README (CQ-04 scope)."""
    out = [readme] if readme else []
    for f in sorted(tree.files):
        low = f.lower()
        if not low.endswith((".md", ".markdown")) or f in out:
            continue
        if low.startswith("docs/") or (low.startswith(".github/") and low.count("/") == 1) or low in (
                "profile/readme.md", ".github/profile/readme.md"):
            out.append(f)
    return out


# =====================================================================================================
# Markdown scanning
# =====================================================================================================
FENCE = re.compile(r"^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,})")  # CommonMark: no backtick in a ``` info string
INLINE_CODE = re.compile(r"(`+)(?:.+?)\1")
ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
MD_LINK = re.compile(r"(!?)\[((?:[^\[\]\n]|\[[^\[\]\n]*\])*)\]\(\s*(<[^>\n]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)"
                     r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^)\n]*\)))?\s*\)")
REF_DEF = re.compile(r"^ {0,3}\[([^\]\n]+)\]:\s*(<[^>\n]*>|\S+)")
HTML_TAG = re.compile(r"<(a|img|source|link|video|audio|image|use)\b([^>]*)>", re.I)
ATTR = re.compile(r"""(?<![\w-])(href|src|srcset|alt|xlink:href|name|id)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
ANCHOR_ATTR = re.compile(r"""<[a-z][^>]*?(?<![\w-])(?:name|id)\s*=\s*["']([^"']+)["']""", re.I)
HTML_HEADING = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1>", re.I | re.S)
BARE_URL = re.compile(r"https?://[^\s<>()\[\]\"'`]+")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".bmp", ".ico")


def scan_lines(text: str) -> list[tuple[int, str | None, str | None]]:
    """(line number, text without HTML comments, the same with inline code blanked); both None inside a code fence."""
    out, fence, comment = [], None, False
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        m = FENCE.match(raw)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not raw.strip().strip(fence[0]):
                fence = None
            out.append((n, None, None))
            continue
        if m and not comment:
            fence = m.group(1)
            out.append((n, None, None))
            continue
        line, rest = "", raw
        while rest:
            if comment:
                end = rest.find("-->")
                if end < 0:
                    rest = ""
                    break
                rest, comment = rest[end + 3:], False
                continue
            start = rest.find("<!--")
            if start < 0:
                line += rest
                break
            line += rest[:start] + " "
            rest, comment = rest[start + 4:], True
        out.append((n, line, INLINE_CODE.sub(lambda mm: " " * len(mm.group(0)), line)))
    return out


def plain_heading(md: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"(`+)(.*?)\1", r"\2", s)
    s = re.sub(r"(\*\*|__|~~)(.+?)\1", r"\2", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    s = re.sub(r"(?<![\w])_(?!\s)(.+?)(?<!\s)_(?![\w])", r"\1", s)
    s = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", s)
    return html.unescape(s).strip()


def github_slug(text: str) -> str:
    """GitHub's heading anchor (github-slugger): lower-case; letters, digits, marks, '-' and '_' kept; every other
    character removed (stripped emoji leave their space); each space becomes '-'."""
    out = []
    for ch in text.lower():
        if ch == " ":
            out.append("-")
        elif ch in "-_" or unicodedata.category(ch)[0] in "LMN":
            out.append(ch)
    return "".join(out)


def headings(text: str) -> list[dict]:
    """Markdown headings in order with their GitHub anchors (duplicates get -1, -2 ...)."""
    rows, seen = [], {}
    lines = scan_lines(text)
    para = re.compile(r"^\s*([#<>|*+\-!\[]|\d+[.)]\s)")
    for i, (n, t, _) in enumerate(lines):
        if t is None:
            continue
        m = ATX.match(t)
        title = None
        if m:
            title = m.group(2) or ""
        elif i + 1 < len(lines) and lines[i + 1][1] is not None and SETEXT.match(lines[i + 1][1] or "") \
                and t.strip() and not para.match(t):
            title = t.strip()
        elif HTML_HEADING.search(t):
            title = HTML_HEADING.search(t).group(2)
        if title is None:
            continue
        base = github_slug(plain_heading(title))
        slug = base
        if base in seen:
            seen[base] += 1
            slug = f"{base}-{seen[base]}"
        else:
            seen[base] = 0
        rows.append({"line": n, "text": plain_heading(title), "slug": slug})
    return rows


def anchors(text: str) -> set[str]:
    out = {h["slug"] for h in headings(text)}
    for _, t, _ in scan_lines(text):
        if t:
            out |= {m.group(1) for m in ANCHOR_ATTR.finditer(t)}
    return out


def _attrs(s: str) -> dict:
    return {m.group(1).lower(): next(g for g in (m.group(3), m.group(4), m.group(5)) if g is not None)
            for m in ATTR.finditer(s)}


def extract_links(text: str) -> list[dict]:
    """Every link and image target outside code: inline, reference definitions, HTML and bare URLs."""
    found = []
    for n, _, masked in scan_lines(text):
        if not masked:
            continue
        spans = []

        def md(s: str, offset: int):
            for m in MD_LINK.finditer(s):
                target = m.group(3).strip("<>")
                found.append({"line": n, "target": target, "image": m.group(1) == "!", "alt": m.group(2),
                              "syntax": "markdown"})
                spans.append((offset + m.start(), offset + m.end()))
                md(m.group(2), offset + m.start(2))
        md(masked, 0)
        m = REF_DEF.match(masked)
        if m:
            found.append({"line": n, "target": m.group(2).strip("<>"), "image": False, "alt": m.group(1),
                          "syntax": "reference"})
            spans.append((m.start(), m.end()))
        for m in HTML_TAG.finditer(masked):
            tag, a = m.group(1).lower(), _attrs(m.group(2))
            for key in ("href", "src", "xlink:href", "srcset"):
                if key in a and a[key]:
                    target = a[key].split(",")[0].strip().split(" ")[0] if key == "srcset" else a[key]
                    found.append({"line": n, "target": target, "image": tag in ("img", "source", "image") or key == "src",
                                  "alt": a.get("alt"), "syntax": f"html-{tag}"})
            spans.append((m.start(), m.end()))
        rest = list(masked)
        for a, b in spans:
            rest[a:b] = " " * (b - a)
        for m in BARE_URL.finditer("".join(rest)):
            found.append({"line": n, "target": m.group(0).rstrip(".,;:!?*_~'\""), "image": False, "alt": None,
                          "syntax": "bare"})
    return found


# =====================================================================================================
# links (CQ-04)
# =====================================================================================================
LINK_ALLOW_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "example.com", "example.org", "example.net")
LINK_ALLOW_SUFFIX = (".home.complete.tech", ".example.com", ".localhost")
GITHUB_ROUTES = {"issues", "pulls", "pull", "actions", "wiki", "releases", "discussions", "security", "blob", "tree",
                 "raw", "compare", "graphs", "network", "projects", "stargazers", "tags", "commits", "commit",
                 "milestones", "labels", "branches", "packages", "deployments", "pulse", "forks", "watchers", "settings"}
GITHUB_RESERVED = {"orgs", "settings", "topics", "sponsors", "marketplace", "apps", "features", "about", "login",
                   "search", "explore", "collections", "trending", "notifications", "pricing", "enterprise", "users",
                   "site", "security", "contact", "readme", "codespaces", "new", "organizations", "account", "stars"}
OK_STATUS, BROKEN = "ok", "broken"


def _private_host(host: str) -> bool:
    return bool(re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)", host or ""))


class Fetcher:
    """Polite remote checks: a cached §10.2 GET (HEAD first; GET when HEAD is refused), `Mozilla/5.0` agent, at most
    one request per host per `delay` seconds, `max_requests` per run. The cache file (opt-in) keeps results for
    `ttl_days`; nothing else persists. `opener(url, method) -> (status|None, final_url, error|None)` is injectable."""

    def __init__(self, cache_path=None, ttl_days: float = 7, delay: float = 1.0, timeout: float = 20,
                 max_requests: int = 300, opener=None, gh=None, sleep=time.sleep, clock=time.time):
        self.cache_path = Path(cache_path) if cache_path else None
        self.ttl, self.delay, self.timeout, self.left = ttl_days * 86400, delay, timeout, max_requests
        self.opener, self.gh, self.sleep, self.clock = opener or self._open, gh or _gh_full_name, sleep, clock
        self.cache: dict = {}
        self._last: dict[str, float] = {}
        self.requests = 0
        if self.cache_path and self.cache_path.is_file():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except ValueError:
                self.cache = {}

    def _open(self, url: str, method: str):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                if method == "GET":
                    r.read(1024)
                return r.status, r.geturl(), None
        except urllib.error.HTTPError as e:
            return e.code, url, None
        except urllib.error.URLError as e:
            reason = str(e.reason)
            return None, url, ("dns" if "Name or service" in reason or "nodename" in reason or "getaddrinfo" in reason
                               else reason[:120])
        except (TimeoutError, OSError, ValueError) as e:
            return None, url, ("timeout" if "timed out" in str(e) else str(e)[:120])

    def _fresh(self, key: str):
        hit = self.cache.get(key)
        if hit and self.clock() - hit.get("t", 0) <= self.ttl:
            return dict(hit, cached=True)
        return None

    def _pace(self, host: str):
        last = self._last.get(host)
        if last is not None:
            wait = self.delay - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        self._last[host] = self.clock()

    def check(self, url: str) -> dict:
        hit = self._fresh(url)
        if hit:
            return hit
        if self.left <= 0:
            return {"status": None, "error": "budget", "cached": False}
        host = urllib.parse.urlsplit(url).hostname or ""
        self._pace(host)
        self.left -= 1
        self.requests += 1
        status, final, err = self.opener(url, "HEAD")
        if status in (400, 403, 405, 406, 429, 500, 501, 503) or (status is None and err not in ("dns",)):
            self._pace(host)
            self.requests += 1
            status, final, err = self.opener(url, "GET")
        res = {"status": status, "final": final, "error": err, "t": self.clock()}
        self.cache[url] = res
        return dict(res, cached=False)

    def full_name(self, owner: str, repo: str) -> dict:
        key = f"gh:{owner}/{repo}"
        hit = self._fresh(key)
        if hit:
            return hit
        if self.left <= 0:
            return {"full_name": None, "error": "budget"}
        self.left -= 1
        self.requests += 1
        name, err = self.gh(owner, repo)
        res = {"full_name": name, "error": err, "t": self.clock()}
        self.cache[key] = res
        return dict(res, cached=False)

    def save(self):
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, sort_keys=True, indent=0) + "\n", encoding="utf-8")


def _gh_full_name(owner: str, repo: str):
    """Read-only `gh api repos/<o>/<r> --jq .full_name` (STANDARD §7.1 link rule). Returns (full_name|None, error)."""
    try:
        p = subprocess.run(["gh", "api", "-X", "GET", f"repos/{owner}/{repo}", "--jq", ".full_name"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"gh: {exc}"
    if p.returncode != 0:
        return None, ("404" if "404" in (p.stderr or "") or "Not Found" in (p.stderr or "") else (p.stderr or "").strip()[:160])
    return p.stdout.strip() or None, None


def _resolve(file: str, target: str) -> tuple[str | None, str | None]:
    """(path relative to the repository root, GitHub route) for a relative link from `file`; (None, None) if it
    leaves the repository without landing on a repository route (../../issues from the root README is a route)."""
    base = PurePosixPath(file).parent
    path = target if not target.startswith("/") else target.lstrip("/")
    parts = [] if target.startswith("/") else [p for p in base.parts if p not in ("", ".")]
    up = 0
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            else:
                up += 1
            continue
        if up:
            return None, seg if up == 2 and seg in GITHUB_ROUTES else None
        parts.append(seg)
    if up:
        return None, None
    return "/".join(parts), None


class _FileInfo:
    def __init__(self, tree: Tree, rel: str):
        self.text = tree.read(rel) or ""
        self.slugs = anchors(self.text)
        self.heads = headings(self.text)


def _github_ref(url: str) -> tuple[str, str] | None:
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or "").lower()
    parts = [p for p in u.path.split("/") if p]
    if host in ("github.com", "www.github.com") and len(parts) >= 2 and parts[0].lower() not in GITHUB_RESERVED:
        return parts[0], re.sub(r"\.git$", "", parts[1])
    if host == "raw.githubusercontent.com" and len(parts) >= 2:
        return parts[0], parts[1]
    return None


def check_links(tree: Tree, files: list[str], *, resolver: Resolver | None = None, fetcher: Fetcher | None = None,
                online: bool = False, base: Tree | None = None, base_files: list[str] | None = None,
                self_slug: tuple[str, str] | None = None) -> dict:
    """Check every link, anchor and image target in `files`. Never rewrites: broken findings carry a proposal."""
    infos: dict[str, _FileInfo] = {}

    def info(rel: str) -> _FileInfo:
        if rel not in infos:
            infos[rel] = _FileInfo(tree, rel)
        return infos[rel]

    base_slugs: dict[str, set[str]] = {}
    if base is not None:
        for f in base_files or files:
            if base.is_file(f):
                base_slugs[f] = anchors(base.read(f) or "")
    findings: list[dict] = []
    for f in files:
        fi = info(f)
        for ln in extract_links(fi.text):
            findings.append(_check_one(tree, f, ln, info, resolver, fetcher if online else None, base_slugs,
                                       self_slug))
    return {"files": files, "findings": findings, "headings": {f: info(f).heads for f in files}}


def _check_one(tree: Tree, f: str, ln: dict, info, resolver, fetcher, base_slugs, self_slug=None) -> dict:
    target = ln["target"].strip()
    row = {"file": f, "line": ln["line"], "target": target, "image": ln["image"], "syntax": ln["syntax"],
           "kind": "relative", "status": OK_STATUS, "reason": "", "proposal": None}
    if ln["image"]:
        row["alt"] = ln.get("alt")
    low = target.lower()
    if not target:
        return dict(row, kind="empty", status=BROKEN, reason="empty link target")
    if re.match(r"^(mailto|tel|data|javascript|ftp|irc|news|sms):", low):
        return dict(row, kind="scheme", status="skipped", reason=low.split(":", 1)[0])
    if target.startswith("#"):
        frag = urllib.parse.unquote(target[1:])
        row["kind"] = "anchor"
        return _anchor(row, f, frag, info(f), base_slugs.get(f), info(f).heads)
    if re.match(r"^(https?:)?//", low):
        return _remote(row, target, resolver, fetcher, self_slug)
    if re.match(r"^[a-z][a-z0-9+.-]*:", low) and not re.match(r"^[a-z]:[\\/]", low):
        return dict(row, kind="scheme", status="skipped", reason=low.split(":", 1)[0])
    path, _, frag = target.partition("#")
    path = urllib.parse.unquote(path.split("?", 1)[0])
    if re.match(r"^[a-zA-Z]:[\\/]", path) or (path.startswith(("/mnt/", "/home/", "/Users/", "~"))
                                              and not tree.is_file(path.lstrip("/")) and not tree.is_dir(path.lstrip("/"))):
        return dict(row, status=BROKEN, reason="machine-local path", proposal=None)
    if not path:
        row["kind"] = "anchor"
        return _anchor(row, f, urllib.parse.unquote(frag), info(f), base_slugs.get(f), info(f).heads)
    rel, route = _resolve(f, path)
    if route:
        return dict(row, kind="github-route", status="skipped", reason=f"repository route /{route}")
    if rel is None:
        return dict(row, status=BROKEN, reason="leaves the repository")
    if tree.is_file(rel) or tree.is_dir(rel):
        if frag and rel.lower().endswith((".md", ".markdown")) and tree.is_file(rel) and not re.match(r"^L\d+", frag):
            row["kind"] = "anchor"
            return _anchor(row, rel, urllib.parse.unquote(frag), info(rel), None, info(rel).heads)
        return row
    row["status"] = BROKEN
    hits = tree.lower.get(rel.lower())
    if hits:
        fixed = _relpath(f, hits[0])
        return dict(row, reason="case differs from the git tree", proposal=_prop(f, ln["line"], path, fixed,
                                                                                    "§7.1 relative link case"))
    if (tree.root / rel).exists() and tree.git:
        return dict(row, reason="exists on disk but not in the git tree (untracked or ignored)")
    name = PurePosixPath(rel).name.lower()
    same = sorted(x for x in tree.files if PurePosixPath(x).name.lower() == name)
    if len(same) == 1:
        return dict(row, reason="target not found", proposal=_prop(f, ln["line"], path, _relpath(f, same[0]),
                                                                    "moved file (one file of that name in the tree)"))
    return dict(row, reason="target not found")


def _relpath(src_file: str, target: str) -> str:
    base = PurePosixPath(src_file).parent
    t = PurePosixPath(target)
    try:
        return str(t.relative_to(base)) if str(base) != "." else str(t)
    except ValueError:
        ups = len([p for p in base.parts if p not in ("", ".")])
        return "../" * ups + str(t)


def _prop(file: str, line: int, old: str, new: str, rule: str, op: str = "replace") -> dict:
    return {"file": file, "line": line, "op": op, "old": old, "new": new, "rule": rule}


def _anchor(row: dict, f: str, frag: str, fi: _FileInfo, base: set[str] | None, heads: list[dict]) -> dict:
    if frag in fi.slugs or frag.lower() in {s.lower() for s in fi.slugs} or re.match(r"^L\d+(-L\d+)?$", frag):
        return row
    row["status"] = BROKEN
    if base is not None and frag in base:
        row["reason"] = "heading renamed or emoji stripped by this change"
        row["introduced"] = True
    else:
        row["reason"] = "no heading or anchor with this slug"
    near = difflib.get_close_matches(frag.lower(), sorted(fi.slugs), n=1, cutoff=0.6)
    if near:
        old = f"#{frag}" if row["target"].startswith("#") else row["target"]
        new = f"#{near[0]}" if row["target"].startswith("#") else row["target"].split("#")[0] + f"#{near[0]}"
        row["proposal"] = _prop(row["file"], row["line"], old, new, "§7.1 rule 6: rewrite to the new slug")
        if row.get("introduced"):
            h = next((x for x in heads if x["slug"] == near[0]), None)
            if h:
                row["proposal_anchor"] = _prop(f, h["line"], "", f'<a name="{frag}"></a>',
                                               "§7.1 rule 6: keep inbound deep links", op="insert-before")
    return row


def _fixed_urls(resolver: Resolver | None) -> set[str]:
    """Every URL `references/brand.yaml` holds (the decision 18 footer's href and logo URLs, the brand site, the hub
    sites): fixed brand content, identical in every repository, so a link check never proposes rewriting one."""
    out: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, str) and re.match(r"^https?://", v.strip(), re.I):
            out.add(v.strip().rstrip("/").lower())
    walk((resolver.brand.raw if resolver is not None and resolver.brand is not None else None) or {})
    return out


def _self_moved(url: str, host: str, resolver: Resolver | None, self_slug) -> tuple[str, str] | None:
    """A link to this repository under its former slug (a transfer left its own README pointing at the old org:
    php2shell-check's badges still name CompleteTech-LLC). GitHub redirects it today, but the redirect breaks the day
    the old owner reuses the name, and the badge, release and clone URLs read wrong. Only an approved repository
    rename or transfer in the estate actions (`Resolver.repo_before`) that produces exactly this repository counts: a
    repository of the same name under another org is a different one (every org has its own `.github`). (old, new)."""
    if not self_slug or not resolver or not (host in ("github.com", "www.github.com", "raw.githubusercontent.com")
                                             or host.endswith("shields.io")):
        return None
    cur_owner, repo = current_login(resolver, self_slug[0]), self_slug[1]
    hit = resolver.repo_before(f"{cur_owner}/{repo}")
    if not hit or "/" not in hit[0] or not resolver.repo_action_approved(hit[1]):
        return None
    old_owner, old_repo = hit[0].split("/", 1)
    if resolver.same(old_owner, cur_owner) and old_repo.lower() == repo.lower():
        return None
    owners = "|".join(re.escape(a) for a in resolver.aliases(old_owner))
    m = re.search(r"/(" + owners + r")/(" + re.escape(old_repo) + r")(?=$|[/?#.])", urllib.parse.urlsplit(url).path,
                  re.I)
    return (f"{m.group(1)}/{m.group(2)}", f"{cur_owner}/{repo}") if m else None


def _remote(row: dict, url: str, resolver: Resolver | None, fetcher: Fetcher | None, self_slug=None) -> dict:
    full = url if not url.startswith("//") else "https:" + url
    u = urllib.parse.urlsplit(full)
    host = (u.hostname or "").lower()
    row["kind"] = "image" if row["image"] else "remote"
    if host in LINK_ALLOW_HOSTS or host.endswith(LINK_ALLOW_SUFFIX) or _private_host(host):
        return dict(row, status="allowlisted", reason="local or example host (§10.2 allowlist)")
    fixed = full.strip().rstrip("/").lower() in _fixed_urls(resolver)  # decision 18 footer and brand URLs: never rewritten
    if fixed:
        row["fixed"] = True
    moved = None if fixed else _self_moved(full, host, resolver, self_slug)
    if moved:
        if _github_ref(full):
            row["kind"] = "github"
        new = url.replace(f"/{moved[0]}", f"/{moved[1]}", 1)
        return dict(row, status="moved", reason=f"this repository under a former owner ({moved[0]}); it is now {moved[1]}",
                    proposal=_prop(row["file"], row["line"], url, new, "§7.1 links: rewrite to the current slug"))
    gh = _github_ref(full)
    if gh:
        row["kind"] = "github"
        owner, repo = gh
        if resolver is not None and not fixed:
            cur = resolver.canonical(owner)
            if cur != owner:
                renamed = cur.lower() != owner.lower()
                new = url.replace(f"/{owner}/", f"/{cur}/", 1)
                row.update(status="renamed", reason=f"org renamed: {owner} -> {cur}" if renamed else
                           f"owner spelled {cur} on GitHub", proposal=_prop(row["file"], row["line"], url, new,
                                                                             "§7.1 links: rewrite to the current owner"))
                return row
        if fetcher is not None and not fixed and in_estate(resolver, owner):
            res = fetcher.full_name(owner, repo)
            name = res.get("full_name")
            if name and name != f"{owner}/{repo}":
                new_owner, new_repo = name.split("/", 1)
                new = url.replace(f"/{owner}/{repo}", f"/{new_owner}/{new_repo}", 1)
                return dict(row, status="moved", reason=f"repository is now {name}",
                            proposal=_prop(row["file"], row["line"], url, new, "§7.1 links: full_name differs"))
            if res.get("error") == "404":
                return dict(row, status=BROKEN, reason="repository not found (dead-link; keep the link)")
    if fetcher is None:
        return dict(row, status="unchecked", reason="offline (pass --online for the cached §10.2 GET)")
    res = fetcher.check(full)
    st = res.get("status")
    row["http"] = st
    if st is not None and 200 <= st < 400:
        return row
    if st in (404, 410) or res.get("error") == "dns":
        return dict(row, status=BROKEN, reason=f"HTTP {st}" if st else "host does not resolve")
    return dict(row, status="unverified", reason=f"HTTP {st}" if st else (res.get("error") or "no answer"))


def links_report(tree: Tree, files: list[str], *, resolver=None, fetcher=None, online=False, base=None,
                 strict=False, self_slug: tuple[str, str] | None = None) -> dict:
    res = check_links(tree, files, resolver=resolver, fetcher=fetcher, online=online, base=base,
                      base_files=files if base is not None else None, self_slug=self_slug)
    broken = [x for x in res["findings"] if x["status"] == BROKEN]
    pre: set = set()
    if base is not None:
        bfiles = [f for f in files if base.is_file(f)]
        bres = check_links(base, bfiles, resolver=resolver, fetcher=None, online=False)
        pre = {(x["file"], x["target"]) for x in bres["findings"] if x["status"] == BROKEN}
    for x in broken:
        x["introduced"] = bool(x.get("introduced")) or (base is not None and (x["file"], x["target"]) not in pre)
    introduced = [x for x in broken if x["introduced"]]
    logs = sorted({"dead-link"} if broken else set())
    if any(x["status"] in ("renamed", "moved") for x in res["findings"]):
        logs.append("link-rewrite")
    if base is not None or strict:
        result = "fail" if (introduced if base is not None else broken) else ("warn" if broken else "pass")
    else:
        result = "warn" if broken else "pass"
    counts: dict[str, int] = {}
    for x in res["findings"]:
        counts[x["status"]] = counts.get(x["status"], 0) + 1
    proposals = [x["proposal"] for x in res["findings"] if x.get("proposal")] + \
        [x["proposal_anchor"] for x in res["findings"] if x.get("proposal_anchor")]
    rows = [[x["file"], str(x["line"]), x["kind"], x["target"], x["reason"], "introduced" if x["introduced"] else
             "pre-existing"] for x in broken]
    return {"result": result, "counts": counts, "findings": res["findings"], "broken": len(broken),
            "introduced": len(introduced), "proposals": proposals, "dead_links_tsv": rows,
            "baseline": "git ref" if base is not None else None, "logs": logs}


def proposal_diff(tree: Tree, proposals: list[dict]) -> str:
    """Unified diff of the proposals applied in memory (the file on disk is never changed)."""
    out = []
    by_file: dict[str, list[dict]] = {}
    for p in proposals:
        by_file.setdefault(p["file"], []).append(p)
    for f, props in sorted(by_file.items()):
        text = tree.read(f) or ""
        lines = text.split("\n")
        new = list(lines)
        inserts: dict[int, list[str]] = {}
        for p in props:
            i = p["line"] - 1
            if not 0 <= i < len(new):
                continue
            if p["op"] == "insert-before":
                if p["new"] not in inserts.setdefault(i, []):
                    inserts[i].append(p["new"])
            elif p["old"] and p["old"] in new[i]:
                # the whole target only: a link that is a prefix of another target on the line (`.../tests.yml` and
                # `.../tests.yml/badge.svg`) must not rewrite the longer one
                rx = re.compile(re.escape(p["old"]) + r"(?![\w/.%?#=&~:+-])")
                new[i] = rx.sub(lambda _m: p["new"], new[i], count=1) if rx.search(new[i]) else \
                    new[i].replace(p["old"], p["new"], 1)
        merged = []
        for i, ln in enumerate(new):
            merged += inserts.get(i, [])
            merged.append(ln)
        out += difflib.unified_diff([x + "\n" for x in lines], [x + "\n" for x in merged], f"a/{f}", f"b/{f}")
    return "".join(out)


# =====================================================================================================
# linguist (RP-07, CQ-08)
# =====================================================================================================
EXT_LANG = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript", ".tsx": "TSX",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "Sass", ".less": "Less", ".php": "PHP",
    ".rs": "Rust", ".go": "Go", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".swift": "Swift", ".c": "C",
    ".h": "C", ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++", ".cs": "C#", ".rb": "Ruby", ".sh": "Shell",
    ".bash": "Shell", ".zsh": "Shell", ".ps1": "PowerShell", ".psm1": "PowerShell", ".bat": "Batchfile",
    ".cmd": "Batchfile", ".ipynb": "Jupyter Notebook", ".mmd": "Mermaid", ".mermaid": "Mermaid", ".vim": "Vim Script",
    ".snippets": "Vim Snippet", ".lua": "Lua", ".dart": "Dart", ".vue": "Vue", ".svelte": "Svelte", ".astro": "Astro",
    ".r": "R", ".jl": "Julia", ".tex": "TeX", ".gd": "GDScript", ".scala": "Scala", ".ex": "Elixir", ".exs": "Elixir",
    ".hs": "Haskell", ".zig": "Zig", ".nix": "Nix", ".tf": "HCL", ".hcl": "HCL", ".m": "Objective-C",
    ".sol": "Solidity", ".pl": "Perl", ".clj": "Clojure", ".fs": "F#", ".ml": "OCaml", ".nim": "Nim", ".erl": "Erlang",
    ".groovy": "Groovy", ".roff": "Roff", ".1": "Roff", ".mdx": "MDX", ".svg": None, ".ejs": "EJS",
    ".hbs": "Handlebars", ".jinja": "Jinja", ".j2": "Jinja", ".twig": "Twig", ".cu": "Cuda", ".asm": "Assembly",
}
NAME_LANG = {"Dockerfile": "Dockerfile", "Makefile": "Makefile", "makefile": "Makefile", "GNUmakefile": "Makefile",
             "CMakeLists.txt": "CMake", "Jenkinsfile": "Groovy"}
# programming languages a chip or badge 1 may name (RP-07 rule 3); markup, config and snippet languages are left out
PROGRAMMING = {"Python", "JavaScript", "TypeScript", "TSX", "Go", "Rust", "PHP", "Shell", "PowerShell", "C", "C++",
               "C#", "Java", "Kotlin", "Swift", "Lua", "GDScript", "Ruby", "Dart", "Scala", "Elixir", "Haskell", "Zig",
               "R", "Julia", "Objective-C", "Vue", "Svelte", "Solidity", "Perl", "Clojure", "F#", "OCaml", "Nim",
               "Erlang", "Groovy", "Jupyter Notebook", "Cuda", "Assembly", "Nix", "HCL", "Astro"}
# Linguist's own vendored and documentation paths (vendor.yml, documentation.yml), approximated: never proposed again
LINGUIST_VENDORED = [re.compile(p) for p in (
    r"(^|/)node_modules/", r"(^|/)vendors?/", r"(^|/)(3rd|[Tt]hird)[-_]?[Pp]arty/", r"(^|/)bower_components/",
    r"(^|/)extern(al)?/", r"^deps/", r"^[Dd]ependencies/", r"(^|/)cache/", r"(\.|-)min\.(js|css)$",
    r"(^|/)jquery[^/]*\.js$", r"(^|/)bootstrap[^/]*\.(js|css)$", r"\.(js|css)\.map$", r"(^|/)\.(yarn|pnpm-store)/",
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|go\.sum)$")]
LINGUIST_DOCS = [re.compile(p) for p in (
    r"^[Dd]ocs?/", r"(^|/)[Dd]ocumentation/", r"(^|/)[Jj]avadoc/", r"^[Mm]an/", r"^[Ee]xamples/", r"^[Dd]emos?/",
    r"(^|/)inst/doc/", r"(^|/)CHANGE(S|LOG)?(\.|$)", r"(^|/)CONTRIBUTING(\.|$)", r"(^|/)COPYING(\.|$)",
    r"(^|/)INSTALL(\.|$)", r"(^|/)LICEN[CS]E(\.|$)", r"(^|/)README(\.|$)")]
# Candidates for the `# ct-std linguist` block (STANDARD §8.5): generated output and example or fixture material
GENERATED_DIRS = ("results", "reports", "report", "output", "outputs", "out", "build", "dist", "coverage", "htmlcov",
                  "_site", "site", "generated", "__generated__", "gen", "storybook-static", "artifacts", "runs")
DOC_DIRS = ("docs", "doc", "examples", "example", "demo", "demos", "samples", "sample", "assets/examples",
            "assets/diagrams", "fixtures", "testdata", "test-data", "__fixtures__", "__snapshots__", "snapshots")
GENERATED_MARK = re.compile(r"@generated|DO NOT EDIT|auto-?generated|generated by|<meta[^>]+name=[\"']generator", re.I)
MANIFEST_LANG = (("pyproject.toml", "Python"), ("setup.py", "Python"), ("setup.cfg", "Python"), ("Pipfile", "Python"),
                 ("requirements.txt", "Python"), ("Cargo.toml", "Rust"), ("go.mod", "Go"), ("composer.json", "PHP"),
                 ("Gemfile", "Ruby"), ("pubspec.yaml", "Dart"), ("Package.swift", "Swift"), ("mix.exs", "Elixir"),
                 ("project.godot", "GDScript"), ("package.json", "JavaScript"), ("pom.xml", "Java"),
                 ("build.gradle", "Java"), ("build.gradle.kts", "Kotlin"))
BLOCK_HEAD = "# ct-std linguist"


def file_language(path: str) -> str | None:
    name = PurePosixPath(path).name
    if name in NAME_LANG:
        return NAME_LANG[name]
    return EXT_LANG.get(PurePosixPath(name).suffix.lower())


def _gitattributes(text: str) -> list[tuple[re.Pattern, bool]]:
    """(pattern, excluded?) for linguist-vendored/-generated/-documentation lines; later lines win."""
    out = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        pat, *attrs = ln.split()
        for a in attrs:
            m = re.match(r"^(-|!)?linguist-(vendored|generated|documentation)(?:=(true|false))?$", a)
            if m:
                out.append((_gitglob(pat), not m.group(1) and m.group(3) != "false"))
    return out


def _gitglob(pat: str) -> re.Pattern:
    anchored = pat.startswith("/") or "/" in pat.rstrip("/")
    p = pat.lstrip("/")
    rx = ""
    i = 0
    while i < len(p):
        if p.startswith("**/", i):
            rx += "(?:.*/)?"
            i += 3
        elif p.startswith("/**", i) and i + 3 == len(p):
            rx += "/.*"
            i += 3
        elif p.startswith("**", i):
            rx += ".*"
            i += 2
        elif p[i] == "*":
            rx += "[^/]*"
            i += 1
        elif p[i] == "?":
            rx += "[^/]"
            i += 1
        else:
            rx += re.escape(p[i])
            i += 1
    if p.endswith("/"):
        rx += ".*"
    return re.compile(("^" if anchored else "(^|.*/)") + rx + "(/.*)?$")


def _excluded_by_linguist(path: str, attrs: list[tuple[re.Pattern, bool]]) -> bool:
    state = any(r.search(path) for r in LINGUIST_VENDORED + LINGUIST_DOCS) or path.startswith(".")
    for rx, excl in attrs:
        if rx.match(path):
            state = excl
    return state


def _candidate(path: str, head: str | None) -> tuple[str, str, str, str] | None:
    """(glob, attribute, reason, confidence) for a path the block should cover, else None."""
    parts = path.split("/")
    for i, seg in enumerate(parts[:-1]):
        low = seg.lower()
        prefix = "/".join(parts[:i + 1])
        if low in GENERATED_DIRS:
            return f"{prefix}/**", "linguist-generated", f"generated output ({seg}/)", "high"
        two = "/".join(p.lower() for p in parts[max(0, i - 1):i + 1])
        if low in DOC_DIRS or two in DOC_DIRS:
            conf = "review" if low in ("fixtures", "testdata", "test-data", "__fixtures__", "snapshots",
                                       "__snapshots__") else "high"
            return f"{prefix}/**", "linguist-documentation", f"examples, fixtures or docs ({prefix}/)", conf
    name = parts[-1].lower()
    if path.lower().endswith((".html", ".htm")) and re.search(r"(report|results?|output|coverage|sample)", name):
        return path, "linguist-generated", "generated HTML report", "review"
    if head and GENERATED_MARK.search(head):
        return path, "linguist-generated", "file says it is generated", "high"
    if path.lower().endswith((".mmd", ".mermaid")):
        return path, "linguist-documentation", "diagram source", "high"
    return None


def manifest_language(files: set[str], read, bytes_by_lang: dict | None = None) -> str | None:
    """RP-07 rule 1: the runtime named by a root manifest (TypeScript when package.json uses it)."""
    roots = {f for f in files if "/" not in f}
    found = []
    for name, lang in MANIFEST_LANG:
        if name in roots or (name == "requirements.txt" and any(re.fullmatch(r"requirements[^/]*\.txt", f) for f in roots)):
            if lang == "JavaScript":
                pj = read("package.json") or ""
                if "tsconfig.json" in roots or re.search(r'"typescript"\s*:', pj):
                    lang = "TypeScript"
                elif not re.search(r'"(main|bin|exports|module)"\s*:|"(dependencies)"\s*:\s*\{\s*"', pj):
                    continue  # a package.json for tooling only (lint, prettier) names no runtime
            if lang == "Java" and any(f.endswith(".kt") for f in files):
                lang = "Kotlin"
            if lang not in found:
                found.append(lang)
    if not found:
        return None
    if len(found) > 1 and bytes_by_lang:
        return max(found, key=lambda lg: (bytes_by_lang.get(lg, 0) + bytes_by_lang.get("TSX" if lg == "TypeScript"
                                                                                      else "", 0), -found.index(lg)))
    return found[0]


def primary_language(meta: dict, files: set[str] | None = None, read=None, override: dict | None = None,
                     corrected: dict | None = None) -> tuple[str | None, str]:
    """The language a banner chip, card dot or badge 1 may show (RP-07): manifest runtime, then a `language:`
    override (`.github/showcase.yml` or the registry), then the top language after the linguist correction if it is
    a programming language. (None, "language-omitted") when none applies."""
    if files:
        lang = manifest_language(files, read or (lambda _p: None), corrected or meta.get("languages") or {})
        if lang:
            return lang, "manifest"
    if override and override.get("language"):
        return str(override["language"]), "override"
    langs = corrected if corrected is not None else (meta.get("languages") or {})
    ranked = sorted(((v, k) for k, v in langs.items() if v > 0), reverse=True)
    for _, k in ranked[:1]:
        if k in PROGRAMMING:
            return ("TypeScript" if k == "TSX" else k), "linguist"
    if not ranked and meta.get("language") in PROGRAMMING:
        return meta["language"], "github"
    return None, "language-omitted"


def _bar(langs: dict) -> list[dict]:
    total = sum(v for v in langs.values() if v > 0) or 1
    return [{"language": k, "bytes": v, "share": round(v / total, 4)}
            for k, v in sorted(langs.items(), key=lambda kv: -kv[1]) if v > 0]


def linguist_report(meta: dict, tree: Tree | None = None, files: list[str] | None = None,
                    sizes: dict | None = None, override: dict | None = None, min_share: float = 0.02) -> dict:
    """Paths that distort the language bar, the proposed append-only `# ct-std linguist` block, and the corrected
    primary language. `tree` is a checkout; without one, `files`/`sizes` come from captured metadata."""
    if tree is not None:
        all_files = set(tree.files)
        size_of, read = tree.size, tree.read
    else:
        all_files = set(files or meta.get("files") or [])
        sizes = sizes or meta.get("file_sizes") or {}
        manifests = meta.get("manifests") or {}

        def size_of(p):
            return int(sizes.get(p, 0))

        def read(p):
            return manifests.get(p)
    if not all_files:
        raise NeedsInput("file-tree", "linguist needs a checkout (--repo-dir) or a captured file tree in the metadata")
    ga_text = read(".gitattributes") or ""
    attrs = _gitattributes(ga_text)
    counted: dict[str, int] = {}
    cands: dict[str, dict] = {}
    for p in sorted(all_files):
        lang = file_language(p)
        if not lang or _excluded_by_linguist(p, attrs):
            continue
        n = size_of(p)
        counted[lang] = counted.get(lang, 0) + n
        head = None
        if lang in ("HTML", "JavaScript", "TypeScript", "CSS", "Python") and tree is not None and n <= 2_000_000:
            head = (read(p) or "")[:1024]
        c = _candidate(p, head)
        if not c:
            continue
        glob, attr, reason, conf = c
        row = cands.setdefault(glob, {"pattern": glob, "attribute": attr, "reason": reason, "confidence": conf,
                                      "bytes": 0, "languages": {}, "files": 0})
        row["bytes"] += n
        row["files"] += 1
        row["languages"][lang] = row["languages"].get(lang, 0) + n
    github = {k: int(v) for k, v in (meta.get("languages") or {}).items()}
    before = github or counted
    total = sum(before.values()) or 1
    proposed = []
    for row in sorted(cands.values(), key=lambda r: -r["bytes"]):
        manifest_inside = any(f.startswith(row["pattern"][:-2]) and PurePosixPath(f).name in
                              ("package.json", "pyproject.toml", "Cargo.toml", "go.mod") for f in all_files) \
            if row["pattern"].endswith("/**") else False
        if manifest_inside:
            row["confidence"] = "review"
            row["reason"] += "; holds a manifest, so it may be real source"
        row["share"] = round(row["bytes"] / total, 4)
        if row["share"] >= min_share:
            proposed.append(row)
    after = dict(before)
    for row in proposed:
        for lg, n in row["languages"].items():
            if lg in after:
                after[lg] = max(0, after[lg] - n)
    old_primary = primary_language(meta, None, None, override, before)
    new_primary = primary_language(meta, all_files, read, override, after)
    raw_top = max(before, key=before.get) if before else meta.get("language")
    for row in proposed:
        row["changes_primary"] = bool(raw_top) and raw_top in row["languages"] and \
            (max(after, key=after.get) if any(after.values()) else None) != raw_top
    present = {ln.strip() for ln in ga_text.splitlines()}
    lines = [f"{r['pattern']} {r['attribute']}" for r in proposed]
    new_lines = [ln for ln in lines if ln not in present]
    diff = ""
    if new_lines:
        old = ga_text
        if BLOCK_HEAD in old:
            idx = old.split("\n")
            pos = idx.index(next(x for x in idx if x.strip() == BLOCK_HEAD)) + 1
            while pos < len(idx) and idx[pos].strip() and not idx[pos].startswith("#"):
                pos += 1
            new = "\n".join(idx[:pos] + new_lines + idx[pos:])
        else:
            new = old + ("" if not old or old.endswith("\n") else "\n") + ("\n" if old.strip() else "") + \
                BLOCK_HEAD + "\n" + "\n".join(new_lines) + "\n"
        diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "a/.gitattributes",
                                            "b/.gitattributes"))
    logs = []
    if new_primary[0] is None:
        logs.append("language-omitted")
    if new_lines:
        logs.append("linguist-proposal")
    return {"result": "proposal" if new_lines else "pass",
            "github_language": meta.get("language"), "bar_before": _bar(before), "bar_after": _bar(after),
            "primary": {"language": new_primary[0], "source": new_primary[1]},
            "primary_before": {"language": old_primary[0], "source": old_primary[1]},
            "candidates": sorted(cands.values(), key=lambda r: -r["bytes"]), "proposed": proposed,
            "gitattributes_lines": new_lines, "diff": diff,
            "note": "Append-only block; linguist-generated and linguist-documentation lines only; never on real source. "
                    "A writer confirms the list and the G1 report approves it; after the merge, re-read "
                    "GET /repos/{o}/{r}/languages before generating the banner and card (STANDARD §8.5).",
            "logs": logs}


# =====================================================================================================
# actions (RP-06, RP-01, CQ-13)
# =====================================================================================================
RED = {"failure", "timed_out", "startup_failure"}
POLISH_PATHS = ("README.md", "docs/images/banner.png", "docs/images/card.svg", "docs/images/.showcase.json",
                "assets/icon.png", "assets/social-preview.png", ".github/showcase.yml", "CONTRIBUTING.md")
DEPLOY_USES = ("actions/deploy-pages", "peaceiris/actions-gh-pages", "jamesives/github-pages-deploy-action",
               "amondnet/vercel-action", "vercel/", "netlify/", "nwtgck/actions-netlify", "cloudflare/wrangler-action",
               "cloudflare/pages-action", "aws-actions/", "azure/webapps-deploy", "azure/static-web-apps-deploy",
               "google-github-actions/deploy", "firebaseextended/action-hosting-deploy", "appleboy/ssh-action",
               "appleboy/scp-action", "easingthemes/ssh-deploy", "samkirkland/ftp-deploy-action",
               "docker/build-push-action", "pypa/gh-action-pypi-publish", "softprops/action-gh-release",
               "superfly/flyctl-actions", "akhileshns/heroku-deploy", "dokku/github-action", "burnett01/rsync-deployments")
DEPLOY_RUN = re.compile(r"\b(vercel\b[^\n]*--prod|netlify\s+deploy|wrangler\s+(pages\s+)?(deploy|publish)|firebase\s+deploy|"
                        r"gh-pages\b|npm\s+publish|yarn\s+publish|twine\s+upload|docker\s+push|rsync\b|scp\b|"
                        r"flyctl\s+deploy|kubectl\s+apply|helm\s+upgrade|gh\s+release\s+create|aws\s+s3\s+sync|"
                        r"curl\b[^\n]*(deploy|hook))", re.I)
UPSTREAM_USES = {"contributor-assistant/github-action": "CLA", "cla-assistant/": "CLA", "actions/labeler": "labeler",
                 "github/issue-labeler": "labeler", "actions/stale": "stale closer", "dessant/lock-threads": "lock threads",
                 "actions/first-interaction": "greeter", "release-drafter/release-drafter": "release drafter",
                 "peter-evans/close-": "issue closer", "dependabot/fetch-metadata": "dependabot auto-merge",
                 "amannn/action-semantic-pull-request": "PR title lint", "actions/add-to-project": "project automation",
                 "pozil/auto-assign-issue": "auto assign", "kentaro-m/auto-assign-action": "auto assign"}
UPSTREAM_NAMES = re.compile(r"(^|[-_/.])(cla|stale|labeler|label|lock|triage|greetings?|welcome|close[-_]?issues?|"
                            r"auto[-_]?assign|release[-_]?drafter)([-_.]|$)", re.I)
EXTERNAL_FILES = {"vercel.json": "Vercel", "netlify.toml": "Netlify", "wrangler.toml": "Cloudflare",
                  "wrangler.json": "Cloudflare", "wrangler.jsonc": "Cloudflare", "firebase.json": "Firebase",
                  "render.yaml": "Render", "fly.toml": "Fly.io", "app.yaml": "App Engine", "Procfile": "Heroku"}


def _filter_rx(pat: str) -> re.Pattern:
    """GitHub Actions filter pattern: `**`, `*`, `?` and `+` (quantifiers on the preceding character), `[...]`."""
    rx, i = "", 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**", i):
            rx += ".*"
            i += 2
            continue
        if c == "*":
            rx += "[^/]*"
        elif c in "?+":
            rx += c
        elif c == "[":
            j = pat.find("]", i)
            rx += pat[i:j + 1] if j > i else re.escape(c)
            i = j if j > i else i
        else:
            rx += re.escape(c)
        i += 1
    return re.compile("^" + rx + "$")


def _match_any(patterns, value: str) -> bool:
    pats = [patterns] if isinstance(patterns, str) else list(patterns or [])
    hit = False
    for p in pats:
        p = str(p)
        neg = p.startswith("!")
        if _filter_rx(p[1:] if neg else p).match(value):
            hit = not neg
    return hit


def _on(doc: dict) -> dict:
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {str(e): None for e in on}
    return dict(on) if isinstance(on, dict) else {}


def push_triggered(spec, branch: str, changed) -> bool:
    """Would a merge commit on `branch` touching only `changed` paths start this `on.push`?"""
    spec = spec if isinstance(spec, dict) else {}
    br, bri = spec.get("branches"), spec.get("branches-ignore")
    if br is None and bri is None and (spec.get("tags") is not None or spec.get("tags-ignore") is not None):
        return False
    if br is not None and not _match_any(br, branch):
        return False
    if bri is not None and _match_any(bri, branch):
        return False
    paths, ign = spec.get("paths"), spec.get("paths-ignore")
    if paths is not None:
        return any(_match_any(paths, c) for c in changed)
    if ign is not None:
        return not all(_match_any(ign, c) for c in changed)
    return True


def _walk_steps(doc: dict):
    for name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        yield name, job, None
        for st in job.get("steps") or []:
            if isinstance(st, dict):
                yield name, job, st


def workflow_facts(path: str, text: str, default_branch: str, changed=POLISH_PATHS, repo: str = "",
                   resolver: Resolver | None = None) -> dict:
    try:
        doc = load_yaml_text(text) or {}
    except Exception as exc:  # a malformed workflow is reported, never fixed
        return {"path": path, "error": f"yaml: {str(exc)[:120]}", "events": []}
    doc = doc if isinstance(doc, dict) else {}
    on = _on(doc)
    deploy, upstream, envs = [], [], []
    guards = set()
    for _jname, job, st in _walk_steps(doc):
        if st is None:
            env = job.get("environment")
            if env:
                envs.append(env.get("name") if isinstance(env, dict) else str(env))
            cond = str(job.get("if") or "")
        else:
            uses = str(st.get("uses") or "").lower()
            run = str(st.get("run") or "")
            cond = str(st.get("if") or "")
            deploy += [f"uses {uses}" for d in DEPLOY_USES if uses.startswith(d)]
            if DEPLOY_RUN.search(run):
                deploy.append(f"run {DEPLOY_RUN.search(run).group(0)[:40]}")
            upstream += [f"{label} ({uses})" for key, label in UPSTREAM_USES.items() if uses.startswith(key)]
        for m in re.finditer(r"github\.repository(_owner)?\s*==\s*['\"]([^'\"]+)['\"]", cond):
            guards.add(m.group(2))
    perms = json.dumps(doc.get("permissions") or {}) + json.dumps([j.get("permissions") for _, j, s in _walk_steps(doc)
                                                                  if s is None])
    if '"pages": "write"' in perms:
        deploy.append("permissions pages: write")
    if envs:
        deploy.append("environment " + ", ".join(sorted(set(map(str, envs)))))
    name = str(doc.get("name") or PurePosixPath(path).name)
    if not deploy and re.search(r"(deploy|publish|pages|release)", f"{name} {PurePosixPath(path).stem}", re.I):
        deploy.append("named deploy/publish/release/pages")
    if not upstream and UPSTREAM_NAMES.search(PurePosixPath(path).stem):
        upstream.append(f"named {PurePosixPath(path).stem}")
    def ours(g: str) -> bool:  # `github.repository[_owner] == '...'` names this repository or its org, under any login
        if resolver is not None and "/" in g and "/" in repo:
            return resolver.slug(g).lower() == resolver.slug(repo).lower()
        if resolver is not None and "/" not in g:
            return resolver.same(g, repo.split("/")[0])
        return g.lower() in (repo.lower(), repo.split("/")[0].lower())
    guarded = bool(guards) and not any(ours(g) for g in guards)
    return {"path": path, "name": name, "events": sorted(on), "push": "push" in on,
            "merge_triggers": "push" in on and push_triggered(on.get("push"), default_branch, changed),
            "workflow_run": list(((on.get("workflow_run") or {}) or {}).get("workflows") or []) if isinstance(
                on.get("workflow_run"), dict) else [],
            "schedule": "schedule" in on, "deploy": sorted(set(deploy)), "upstream": sorted(set(upstream)),
            "environments": sorted(set(map(str, envs))), "guarded_to": sorted(guards), "guarded": guarded}


def _norm_runs(obj) -> list[dict]:
    if isinstance(obj, dict):
        obj = obj.get("workflow_runs") or obj.get("runs") or []
    out = []
    for r in obj or []:
        if not isinstance(r, dict):
            continue
        out.append({"workflow": r.get("workflowName") or r.get("name") or "",
                    "path": (r.get("path") or "").split("@")[0],
                    "workflow_id": r.get("workflow_id") or r.get("workflowDatabaseId"),
                    "branch": r.get("head_branch") or r.get("headBranch"), "event": r.get("event"),
                    "status": r.get("status"), "conclusion": r.get("conclusion") or None,
                    "created_at": r.get("created_at") or r.get("createdAt") or "",
                    "sha": r.get("head_sha") or r.get("headSha"),
                    "url": r.get("html_url") or r.get("url")})
    return out


def _norm_workflows(obj) -> list[dict]:
    if isinstance(obj, dict):
        obj = obj.get("workflows") or []
    return [{"id": w.get("id"), "name": w.get("name"), "path": w.get("path"), "state": w.get("state"),
             "badge_url": w.get("badge_url")} for w in obj or [] if isinstance(w, dict)]


def readme_ci_badges(readme: str) -> list[str]:
    """Workflow files whose status badge the README shows."""
    return sorted(set(re.findall(r"/actions/workflows/([^/\s\"')]+?\.ya?ml)/badge\.svg", readme or "")))


def actions_report(meta: dict, *, runs=None, workflows=None, workflow_files: dict | None = None, readme: str = "",
                   root_files=(), pages: dict | None = None, resolver: Resolver | None = None,
                   changed=POLISH_PATHS, approval_ids: dict | None = None) -> dict:
    """Per-repo Actions health for the orchestrator: red badges, upstream-only automation in forks, and what a
    README merge would start (deploys first: RP-01)."""
    owner, repo = meta.get("owner", "unknown"), meta.get("repo", "unknown")
    full = f"{current_login(resolver, owner)}/{repo}"
    branch = meta.get("default_branch") or "main"
    runs_n, wfs = _norm_runs(runs), _norm_workflows(workflows)
    files = dict(workflow_files or {})
    by_path: dict[str, dict] = {}
    for w in wfs:
        if w.get("path"):
            by_path.setdefault(w["path"], {}).update(api=w)
    for p, text in files.items():
        by_path.setdefault(p, {})["facts"] = workflow_facts(p, text, branch, changed, full, resolver)
    name_to_path = {(v.get("api") or {}).get("name") or (v.get("facts") or {}).get("name"): p for p, v in by_path.items()}
    id_to_path = {(v.get("api") or {}).get("id"): p for p, v in by_path.items() if (v.get("api") or {}).get("id")}
    for r in runs_n:
        p = r["path"] or id_to_path.get(r["workflow_id"]) or name_to_path.get(r["workflow"])
        if not p:
            p = f"(dynamic) {r['workflow']}"
        by_path.setdefault(p, {}).setdefault("runs", []).append(r)
    fork = bool(meta.get("fork")) or repo.endswith("-fork")
    parent = (meta.get("parent") or {}).get("full_name") if isinstance(meta.get("parent"), dict) else meta.get("parent")
    parent_owner = parent.split("/")[0] if parent else None
    upstream_fork = fork and not (parent_owner and in_estate(resolver, parent_owner))
    badges = readme_ci_badges(readme)
    rows, deploy_rows, proposals, jobs, logs = [], [], [], [], []
    push_names = set()
    for p, v in by_path.items():
        f = v.get("facts") or {}
        if f.get("merge_triggers"):
            push_names.add(f.get("name"))
            push_names.add((v.get("api") or {}).get("name"))
    for p, v in sorted(by_path.items()):
        api, f = v.get("api") or {}, v.get("facts") or {}
        on_branch = [r for r in v.get("runs") or [] if r["branch"] == branch]
        on_branch.sort(key=lambda r: r["created_at"], reverse=True)
        done = [r for r in on_branch if r["status"] in (None, "completed")]
        latest = done[0] if done else None
        concl = (latest or {}).get("conclusion") or ("pending" if on_branch else "none")
        state = api.get("state") or ("unknown" if not api else None)
        flags = []
        if concl in RED:
            flags.append("ci-red")
        if state in ("disabled_manually", "disabled_inactivity", "disabled_fork"):
            flags.append(state)
        chained = [n for n in f.get("workflow_run") or [] if n in push_names]
        triggers = []
        if f.get("merge_triggers"):
            triggers.append("push")
        if chained:
            triggers.append("workflow_run:" + ",".join(chained))
        if f.get("schedule"):
            triggers.append("schedule")
        fname = PurePosixPath(p).name
        badge = fname in badges
        if badge and concl != "success":
            flags.append("badge-red" if concl in RED else "badge-unknown")
        is_deploy = bool(f.get("deploy"))
        if is_deploy and (f.get("merge_triggers") or chained):
            flags.append("deploy-on-merge")
            deploy_rows.append({"repo": full, "workflow": p, "trigger": "+".join(triggers),
                                "environment": ",".join(f.get("environments") or []) or "-",
                                "external": "-", "suppressed_by_skip_ci": True})
        if is_deploy and f.get("schedule"):
            deploy_rows.append({"repo": full, "workflow": p, "trigger": "schedule",
                                "environment": ",".join(f.get("environments") or []) or "-", "external": "-",
                                "suppressed_by_skip_ci": False})
        upstream = upstream_fork and not f.get("guarded") and state not in ("disabled_manually", "disabled_fork") and (
            bool(f.get("upstream")) or (f.get("schedule") and concl in RED))
        if upstream:
            flags.append("upstream-only")
            # the file name, never the numeric id: the guard matches the workflow-toggle approval's detail (the
            # workflow file) against this argument (scripts/guard.py B5)
            wid = fname
            reason = ", ".join(f.get("upstream") or ["failing upstream schedule"])
            jid = job_id("p0", "workflow-toggle", full, fname)
            job = writer_job(jid, "3", "workflow-toggle", full, ["gh", "workflow", "disable", str(wid), "-R", full],
                             f"Disable upstream-only automation in a kept fork ({reason}); never edit the workflow "
                             "file (RP-06, CQ-13, q79).", (approval_ids or {}).get(fname) or (approval_ids or {}).get(p))
            (jobs if job.get("approval_id") else proposals).append(job)
        rows.append({"path": p, "name": f.get("name") or api.get("name") or v.get("runs", [{}])[0].get("workflow"),
                     "state": state, "latest": concl, "latest_at": (latest or {}).get("created_at"),
                     "latest_url": (latest or {}).get("url"), "events": f.get("events") or [],
                     "merge_triggers": triggers, "deploy": f.get("deploy") or [], "upstream": f.get("upstream") or [],
                     "guarded_to": f.get("guarded_to") or [], "badge": badge, "flags": flags,
                     **({"error": f["error"]} if f.get("error") else {})})
    externals = sorted({EXTERNAL_FILES[n] for n in root_files if n in EXTERNAL_FILES})
    for ext in externals:
        deploy_rows.append({"repo": full, "workflow": "-", "trigger": "external integration", "environment": "-",
                            "external": ext, "suppressed_by_skip_ci": False})
    has_pages_wf = any("uses actions/deploy-pages" in (r["deploy"] or []) for r in rows)
    pages_src = (pages or {}).get("source") or {}
    if (pages or {}).get("build_type") == "legacy" or (meta.get("has_pages") and not pages and not has_pages_wf):
        if not pages or pages_src.get("branch") in (None, branch):
            deploy_rows.append({"repo": full, "workflow": "pages-build-deployment", "trigger": "branch-source Pages",
                                "environment": "github-pages", "external": "GitHub Pages" if pages else
                                "GitHub Pages (assumed: has_pages, no Pages workflow)", "suppressed_by_skip_ci": False})
    if any("ci-red" in r["flags"] for r in rows):
        logs.append("ci-red")
    if any(r["flags"] and set(r["flags"]) & {"disabled_manually", "disabled_inactivity"} for r in rows):
        logs.append("workflow-disabled")
    if proposals or jobs:
        logs.append("workflow-toggle")
    merge_runs = [r for r in rows if r["merge_triggers"] and set(r["merge_triggers"]) - {"schedule"}]
    not_suppressed = [d for d in deploy_rows if not d["suppressed_by_skip_ci"]]
    ci_ok = {r["path"]: r["latest"] == "success" for r in rows}
    for b in badges:  # a README badge with no run data is never shown as green (STANDARD §7.2 badge 4)
        if not any(PurePosixPath(p).name == b for p in ci_ok):
            ci_ok[f".github/workflows/{b}"] = False
            logs.append("needs-input:ci-status")
    if not by_path:
        logs.append("needs-input:workflows")
    post = []
    if any(d["suppressed_by_skip_ci"] for d in deploy_rows) or not_suppressed:
        post = [["gh", "api", f"repos/{full}/actions/runs?event=push&per_page=1"],
                ["gh", "api", f"repos/{full}/deployments?per_page=1"]]
    red = any("ci-red" in r["flags"] or "badge-red" in r["flags"] for r in rows)
    return {"result": "fail" if red else ("needs-input" if not by_path else
                                         ("warn" if deploy_rows or proposals else "pass")),
            "repo": full, "default_branch": branch, "fork": fork, "upstream_fork": upstream_fork, "parent": parent,
            "workflows": rows, "ci_badge_allowed": ci_ok, "readme_badges": badges,
            "redeploy": {"merge_starts": [r["path"] for r in merge_runs], "deploy_on_merge": deploy_rows,
                         "not_suppressed_by_skip_ci": not_suppressed,
                         "avoid_redeploy": bool(deploy_rows),
                         "merge_subject": "<PR title> [skip ci]",  # always (STANDARD §10.3; RP-01)
                         "post_merge_checks": post},
            "proposals": proposals, "jobs": jobs,
            "tsv": {"actions-health": [[full, r["path"], r["state"] or "-", r["latest"], r["latest_at"] or "-",
                                        ",".join(r["flags"]) or "-"] for r in rows],
                    "deploy-on-push": [[d["repo"], d["workflow"], d["trigger"], d["environment"], d["external"]]
                                       for d in deploy_rows]},
            "logs": logs}


# =====================================================================================================
# images (RP-03, RP-10)
# =====================================================================================================
IMG_LIMIT, EXAMPLE_LIMIT, EXAMPLE_WIDTH = 300_000, 600_000, 2600
PROTECTED_DIRS = ("public", "static", "src", "results", "notebooks")
EXEMPT_LOGOS = {  # STANDARD §9.2 brand pair (R9), exempt from the image weight rule
    "a5c3c4ef55336ed4b883d3bc3bb6e1e942b836469bd2b2933bc8cc230b321621",
    "0dc00c0e5159518ff1d552b7052293b4e545ddd35be489e6d114e3ea64db27ec"}


def _is_example(rel: str) -> bool:
    return rel.startswith("assets/examples/") or bool(re.search(r"(^|/)example[^/]*\.(png|jpe?g|webp|gif)$", rel, re.I))


def _png_lossless(data: bytes) -> tuple[bytes | None, str]:
    """A pixel-identical re-encode (zlib 9, filter search) to estimate what `oxipng -o4 --strip safe` saves."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as exc:  # unreadable images are reported, not fixed
        return None, f"unreadable: {str(exc)[:80]}"
    frames = getattr(im, "n_frames", 1)
    if getattr(im, "is_animated", False) or frames > 1:  # a re-save keeps one frame: no candidate (fail closed)
        return None, f"animated: {frames} frames; no lossless candidate (a re-encode would keep only the first frame)"
    b = io.BytesIO()
    kw = {"optimize": True}
    if im.info.get("icc_profile"):
        kw["icc_profile"] = im.info["icc_profile"]
    if im.mode == "P" and "transparency" in im.info:
        kw["transparency"] = im.info["transparency"]
    im.save(b, "PNG", **kw)
    new = b.getvalue()
    back = Image.open(io.BytesIO(new))
    back.load()
    if back.mode != im.mode or back.size != im.size or back.tobytes() != im.tobytes():
        return None, "re-encode not pixel-identical"
    return new, "ok"


def _dark_theme(rel: str, data: bytes) -> str | None:
    """RP-10 static heuristics: content that may vanish on GitHub's dark page."""
    low = rel.lower()
    if low.endswith(".svg"):
        text = data.decode("utf-8", "replace")
        fills = re.findall(r"(?:fill|stroke)\s*[:=]\s*[\"']?(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}\b|black)", text)
        from .color import luminance
        dark = [f for f in fills if f == "black" or luminance(f) < 0.05]
        has_bg = re.search(r"<rect[^>]*(width=[\"']100%|x=[\"']0)", text) or "prefers-color-scheme" in text
        if dark and not has_bg and len(dark) * 2 >= len(fills):
            return "svg: dark fills and no background rect or prefers-color-scheme"
        return None
    if not low.endswith((".png", ".gif", ".webp")):
        return None
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.thumbnail((256, 256))
        im = im.convert("RGBA")
    except Exception:  # unreadable images are reported elsewhere
        return None
    px = _px(im)
    clear = sum(1 for p in px if p[3] < 128)
    ink = [p for p in px if p[3] >= 128]
    if not ink or clear / len(px) <= 0.30:
        return None
    lum = sum(0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in ink) / len(ink)
    return f"png: {clear / len(px):.0%} transparent, mean ink luminance {lum:.0f} < 80" if lum < 80 else None


def _mermaid_flags(text: str) -> list[int]:
    out, inside = [], False
    for n, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if s.startswith("```mermaid") or s.startswith("~~~mermaid"):
            inside = True
            continue
        if inside and s.startswith(("```", "~~~")):
            inside = False
            continue
        if inside and re.search(r"\b(classDef|style)\b", s) and "fill:" in s and "color:" not in s:
            out.append(n)
    return out


def images_report(tree: Tree, files: list[str], *, new_paths: set[str] | None = None, approval_id: str | None = None,
                  out_dir: str | Path | None = None, fetcher: Fetcher | None = None) -> dict:
    """README and docs image budget (RP-03): bytes, pixels, alt text; lossless proposals; lossy only with an
    approval; dark-theme flags (RP-10)."""
    from PIL import Image
    refs: dict[str, dict] = {}
    remote, alt_missing, mermaid = [], [], []
    for f in files:
        text = tree.read(f) or ""
        for n in _mermaid_flags(text):
            mermaid.append({"file": f, "line": n, "flag": "mermaid fill without color"})
        for ln in extract_links(text):
            target = ln["target"].strip()
            is_img = ln["image"] or urllib.parse.urlsplit(target).path.lower().endswith(IMG_EXT)
            if not is_img or target.startswith("data:"):
                continue
            if ln["image"] and ln["syntax"] in ("markdown", "html-img") and not (ln.get("alt") or "").strip():
                alt_missing.append({"file": f, "line": ln["line"], "target": target})
            if re.match(r"^(https?:)?//", target, re.I):
                remote.append({"file": f, "line": ln["line"], "target": target})
                continue
            path = urllib.parse.unquote(target.split("#")[0].split("?")[0])
            rel, _ = _resolve(f, path)
            if rel is None:
                continue
            refs.setdefault(rel, {"path": rel, "referenced_from": []})["referenced_from"].append(f"{f}:{ln['line']}")
    rows, plan, needs_approval, logs = [], [], [], []
    for rel, row in sorted(refs.items()):
        data = tree.read_bytes(rel)
        if data is None:
            rows.append(dict(row, status="missing"))
            continue
        row["bytes"] = len(data)
        row["sha256"] = hashlib.sha256(data).hexdigest()
        try:
            if rel.lower().endswith(".svg"):
                m = re.search(r"<svg[^>]*\bwidth=[\"']?([\d.]+)[^>]*\bheight=[\"']?([\d.]+)", data.decode("utf-8", "replace"))
                row["px"] = [round(float(m.group(1))), round(float(m.group(2)))] if m else None
                row["format"] = "SVG"
            else:
                im = Image.open(io.BytesIO(data))
                row["px"], row["format"] = list(im.size), im.format
        except Exception:  # an image PIL cannot open is reported as such
            row["format"] = "unreadable"
        example = _is_example(rel)
        limit = EXAMPLE_LIMIT if example else IMG_LIMIT
        row["limit"] = limit
        row["new"] = rel in (new_paths or set())
        row["protected"] = any(seg in PROTECTED_DIRS for seg in rel.split("/")[:-1])
        flags = []
        if row["sha256"] in EXEMPT_LOGOS:
            flags.append("exempt:brand-logo")
        elif len(data) > limit:
            flags.append("fail:image-weight" if row["new"] else "warn:image-weight")
        if example and (row.get("px") or [0])[0] > EXAMPLE_WIDTH:
            flags.append("warn:example-width")
        dark = _dark_theme(rel, data)
        if dark:
            flags.append("warn:dark-theme")
            row["dark_theme"] = dark
        row["flags"] = flags
        over = any(fl.endswith("image-weight") for fl in flags)
        if over and not row["protected"]:
            fmt = (row.get("format") or "").upper()
            if fmt == "PNG":
                new, why = _png_lossless(data)
                saved = len(data) - len(new) if new else 0
                row["lossless"] = {"bytes": len(new) if new else None, "saved": saved, "check": why}
                plan.append({"path": rel, "kind": "lossless", "argv": ["oxipng", "-o4", "--strip", "safe", rel],
                             "estimate_bytes": len(new) if new else None, "meets_limit": bool(new) and len(new) <= limit,
                             "note": "identical pixels, same path (STANDARD §10.3)"})
                if out_dir and new and saved > 0:
                    dest = Path(out_dir) / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(new)
                    row["lossless"]["candidate"] = str(dest)
                fits = bool(new) and len(new) <= limit
            elif fmt == "GIF":
                plan.append({"path": rel, "kind": "lossless", "argv": ["gifsicle", "-O3", "--batch", rel],
                             "estimate_bytes": None, "meets_limit": None, "note": "identical frames, same path"})
                fits = False
            else:
                fits = False
            if not fits:
                lossy = {"path": rel, "kind": "lossy", "approval": "lossy-image", "bytes": len(data), "limit": limit,
                         "argv": (["pngquant", "--quality", "80-95", "--skip-if-larger", "--force", "--ext", ".png", rel]
                                  if fmt == "PNG" else ["cwebp", "-q", "85", rel, "-o", rel + ".webp"]),
                         "note": "lossy recompression needs a per-repo lossy-image approval (q69)"}
                if approval_id:
                    plan.append(dict(lossy, approval_id=approval_id))
                else:
                    needs_approval.append(lossy)
        elif over:
            row["note"] = "under public/, static/, src/, results/ or notebooks/: never touched (STANDARD §10.3)"
        rows.append(row)
    if fetcher is not None:
        for r in remote:
            res = fetcher.check(r["target"] if not r["target"].startswith("//") else "https:" + r["target"])
            r["http"] = res.get("status")
    fails = [r for r in rows if any(f.startswith("fail:") for f in r.get("flags", []))] + \
        [r for r in rows if r.get("status") == "missing"]
    warns = [r for r in rows if any(f.startswith("warn:") for f in r.get("flags", []))]
    if any("image-weight" in f for r in rows for f in r.get("flags", [])):
        logs.append("warn:image-weight" if not fails else "image-weight")
    if any("warn:dark-theme" in r.get("flags", []) for r in rows) or mermaid:
        logs.append("warn:dark-theme")
    if alt_missing:
        logs.append("warn:alt-missing")
    return {"result": "fail" if fails else ("warn" if warns or alt_missing or mermaid else "pass"),
            "images": rows, "remote": remote, "alt_missing": alt_missing, "mermaid": mermaid, "plan": plan,
            "needs_approval": needs_approval, "logs": logs}


def new_files(tree: Tree, base_ref: str | None) -> set[str]:
    """Files the run adds: not in `base_ref` (default HEAD) or untracked."""
    if not tree.git:
        return set()
    out = tree._git("ls-tree", "-r", "--name-only", "-z", base_ref or "HEAD")
    if out is None:
        return set(tree.files)
    return set(tree.files) - {f for f in out.split("\0") if f}


# =====================================================================================================
# sidebar (RP-05)
# =====================================================================================================
SIDEBAR_BOXES = ("releases", "packages", "deployments")


def _count(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, list):
        return len(v)
    if isinstance(v, dict):
        for k in ("total_count", "totalCount"):  # REST and GraphQL counts win over a (possibly paged) list
            n = v.get(k)
            if isinstance(n, int) and not isinstance(n, bool):
                return n
            if isinstance(n, str) and n.isdigit():
                return int(n)
        for k in ("environments", "releases", "deployments", "packages", "items", "nodes"):
            if isinstance(v.get(k), list):
                return len(v[k])
    return None


def packages_by_repo(packages, resolver: Resolver | None = None) -> dict[str, int]:
    """Org package listings (`gh api orgs/<org>/packages?package_type=...`, one or many) keyed by OWNER/REPO, owners
    folded through the resolver so a renamed org's packages still map to its repositories."""
    out: dict[str, int] = {}
    items = packages if isinstance(packages, list) else (packages or {}).get("packages") or []
    for p in items:
        if isinstance(p, list):
            for k, v in packages_by_repo(p, resolver).items():
                out[k] = out.get(k, 0) + v
            continue
        full = ((p or {}).get("repository") or {}).get("full_name")
        if not full:
            continue
        o, r = full.split("/", 1)
        key = f"{current_login(resolver, o).lower()}/{r.lower()}"
        out[key] = out.get(key, 0) + 1
    return out


def sidebar_plan(meta: dict, facts: dict, *, resolver: Resolver | None = None, packages: dict | None = None,
                 current: dict | None = None, phase="3.3") -> dict:
    """Target state of the About "Include in the home page" boxes (decision 7, STANDARD §10.1) and the browser job
    that sets them. GitHub's default shows all three; only repos whose target differs get a job."""
    owner, repo = meta.get("owner", "unknown"), meta.get("repo", "unknown")
    cur_owner = current_login(resolver, owner)
    full = f"{cur_owner}/{repo}"
    counts = {b: _count(facts.get(b)) for b in SIDEBAR_BOXES}
    if counts["packages"] is None and packages is not None:
        key = f"{cur_owner.lower()}/{repo.lower()}"
        counts["packages"] = packages.get(key, 0)
    target = {b: (None if counts[b] is None else counts[b] > 0) for b in SIDEBAR_BOXES}
    unknown = [b for b in SIDEBAR_BOXES if target[b] is None]
    default = {b: True for b in SIDEBAR_BOXES}
    base_state = {b: (current or {}).get(b, default[b]) for b in SIDEBAR_BOXES}
    differs = [b for b in SIDEBAR_BOXES if target[b] is not None and target[b] != base_state[b]]
    has_pages = bool(facts.get("has_pages", meta.get("has_pages")))
    public = meta.get("visibility", "public") == "public"
    row = {"repo": full, **{b: counts[b] for b in SIDEBAR_BOXES}, "environments": _count(facts.get("environments")),
           **{f"show_{b}": target[b] for b in SIDEBAR_BOXES}, "has_pages": has_pages,
           "differs_from_default": bool(differs), "unknown": unknown}
    logs = [f"needs-input:sidebar-facts:{b}" for b in unknown]
    job = None
    if differs and not unknown:
        word = {True: "checked", False: "unchecked"}
        steps = [f"Open https://github.com/{full} while signed in as an owner of {cur_owner}.",
                 "In the right-hand column, click the gear icon next to the \"About\" heading; the \"Edit repository "
                 "details\" dialog opens.",
                 "Do not change Description, Website or Topics in this dialog; the writer sets them."]
        if has_pages:
            steps.append("Tick \"Use your GitHub Pages website\" only if the Website field already holds this "
                         "repository's GitHub Pages URL; otherwise leave it as it is.")
        for b in SIDEBAR_BOXES:
            label = b.capitalize()
            steps.append(f"Under \"Include in the home page\", make sure \"{label}\" is {word[target[b]]} "
                         f"({counts[b]} {b} found).")
        steps.append("Click \"Save changes\".")
        if public:
            steps.append(f"Verify signed out (or with `curl -s https://github.com/{full}`): the page shows neither "
                         "\"No releases published\" nor \"No packages published\".")
        else:
            steps.append("Private repository: keep the screenshot of the About column for the per-org sample.")
        job = browser_job(job_id(f"p{phase}", "sidebar", full), phase, full, f"https://github.com/{full}",
                          "about-sidebar", steps,
                          "About sidebar: Releases, Packages and Deployments shown only where they exist (UD 7, RP-05; "
                          "STANDARD §10.1, §12.4).")
    tsv = [full] + ["?" if counts[b] is None else str(counts[b]) for b in SIDEBAR_BOXES] + \
        ["?" if target[b] is None else ("show" if target[b] else "hide") for b in SIDEBAR_BOXES] + \
        ["yes" if differs else "no"]
    return {"result": "needs-input" if unknown else ("proposal" if job else "pass"), "row": row, "tsv": tsv,
            "job": job, "logs": logs}


SIDEBAR_TSV_HEADER = ["repo", "releases", "packages", "deployments", "releases_box", "packages_box", "deployments_box",
                      "differs_from_default"]


# =====================================================================================================
# icon (RT-04): prompt file, normalize, QA
# =====================================================================================================
ICON_PX, ICON_BUDGET = 1024, 300_000
LIVE_MARGIN = round(82 * ICON_PX / 500)  # 168: the avatar live area (a.3) at 1024 px
LIVE = ICON_PX - 2 * LIVE_MARGIN          # 688
KEY_DE, CONTENT_DE = 6.0, 12.0
ART_FAMILY = {"completetech": "CompleteTech core", "ai-ascension": "AI-Ascension", "jev-engineering": "Jev",
              "jevplay-games": "Jev", "libreevolve": "LibreEvolve", "touchedbyanagent": "TouchedByAnAgent",
              "romgenie": "romgenie utility"}
ART_OWNER = {"CompleteDotTech": ("Founder", None), "Pick-Your-AI": ("Pick Your AI", None),
             "Jev-Engineering": ("Jev", "Jev-Engineering"), "jevplay-games": ("Jev", "jevplay-games"),
             "Jevelopers-neatHack-2026": ("Jev", "Jevelopers")}
WRITER_SLOTS = ("GLYPH_NAME", "GLYPH_DESCRIPTION", "SPARK_PLACEMENT", "SIZE_CLASS")
SIZE_CLASSES = {
    "WIDE": "the glyph spans close to the full 688 px width and is about 430 to 560 px tall",
    "TALL": "spans close to the full 688 px height and is about 400 to 600 px wide",
    "SQUARE": "a squarish glyph about 600 to 660 px on each side",
    "DIAGONAL": "the mass runs corner to corner inside a 656 × 656 px box"}
HEX = r"`(#[0-9A-Fa-f]{6})`"


def load_art_direction(path=None) -> str:
    p = Path(path) if path else DEFAULT_ART_DIRECTION
    if not p.is_file():
        raise NeedsInput("art-direction", f"art direction not found: {p} (pass --art-direction FILE to use another file)")
    return p.read_text(encoding="utf-8")


def _section(text: str, head: str) -> str:
    m = re.search(rf"^## {re.escape(head)}.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def palette_rows(text: str) -> list[dict]:
    """Rows of the (b) family palette table: family, role, name, hex values and notes."""
    rows, fam = [], ""
    for ln in _section(text, "(b) Family palette").splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 4 or not ln.lstrip().startswith("|") or set(cells[0]) <= set("-: ") and cells[0]:
            continue
        if cells[0] in ("Family",):
            continue
        fam = re.sub(r"\*\*|\(.*?\)", "", cells[0]).strip() or fam
        rows.append({"family": fam, "role": cells[1], "name": cells[2], "hex": re.findall(HEX, cells[3]),
                     "notes": cells[4] if len(cells) > 4 else ""})
    return rows


def family_colours(text: str, owner: str, family: str, aliases=()) -> dict:
    """The family palette for the org: its ART_OWNER row under any of its logins (`aliases`, CQ-03), else the family's."""
    owners = {k.lower(): v for k, v in ART_OWNER.items()}
    fam, prefix = next((owners[a.lower()] for a in (owner, *aliases) if a and a.lower() in owners),
                       (ART_FAMILY.get(family), None))
    rows = [r for r in palette_rows(text) if fam and r["family"].lower().startswith(fam.lower())]
    if prefix:
        own = [r for r in rows if r["role"].lower().startswith(prefix.lower())]
        rows = own + [r for r in rows if r["role"].lower().startswith("light-surface")]
    out: dict = {"family_label": fam}

    def note(r, key):
        m = re.search(rf"{key} `(#[0-9A-Fa-f]{{6}})`", r["notes"] if r else "")
        return m.group(1) if m else None
    line = next((r for r in rows if re.search(r"\bline\b", r["role"], re.I) and "second" not in r["role"].lower()
                 and r["hex"]), None)
    spark = next((r for r in rows if re.search(r"\bspark\b", r["role"], re.I) and "light-surface" not in r["role"].lower()
                  and r["hex"]), None)
    glow_row = next((r for r in rows if r["role"].lower() == "glow" and r["hex"]), None)
    if line:
        out.update(LINE_NAME=line["name"], LINE_HEX=line["hex"][0], CORE_HEX=note(line, "core"),
                   GLOW_HEX=note(line, "glow") or (glow_row["hex"][0] if glow_row else None))
    if spark:
        out.update(SPARK_NAME=spark["name"], SPARK_HEX=spark["hex"][0], SPARK_CORE_HEX=note(spark, "centre"),
                   SPARK_BLOOM_HEX=note(spark, "bloom"))
    ink = next((r for r in rows if r["role"].lower().startswith("light-surface")), None)
    out["INK"] = ink["hex"] if ink else []
    return out


def org_glyph(text: str, owner: str) -> str | None:
    for ln in _section(text, "(c) All 28 accounts").splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[1].split(" (")[0].lower() == owner.lower():
            return cells[5]
    return None


def icon_colours(ctx, text: str, org: dict, resolver: Resolver, *, require_palette: bool = True) -> dict:
    """Keep estate palettes explicit; the bundled template uses the committed brand tokens."""
    family = org_style(resolver, ctx.brand, ctx.owner)["name"]
    colours = family_colours(text, org["brand_key"], family, resolver.aliases(ctx.owner))
    if _section(text, "Repository glyph prompt template") and not _section(text, "(b) Family palette"):
        tokens = ctx.style["tokens"]
        missing = [key for key in ("icon_ink", "icon_spark") if not tokens.get(key)]
        if missing:
            if not require_palette:
                return colours
            raise NeedsInput("icon-palette", "selected brand config needs " + ", ".join(missing) +
                             " tokens for the bundled prompt; add them or pass --art-direction FILE "
                             "with a family palette")
        colours.update(family_label=family, LINE_NAME="family icon ink", LINE_HEX=tokens["icon_ink"],
                       CORE_HEX=tokens["title"], GLOW_HEX=tokens["accent_mid"],
                       SPARK_NAME="family icon spark", SPARK_HEX=tokens["icon_spark"],
                       SPARK_CORE_HEX=tokens["title"], SPARK_BLOOM_HEX=tokens["icon_spark"],
                       INK=[tokens["icon_ink"], tokens["icon_spark"]])
    return colours


def seed_for(text: str, owner: str | list[str], family: str) -> str | None:
    """The org's seed (any of its logins, CQ-03), else the family's."""
    m = re.search(r"seeds \(([^)]*)\)", text)
    if not m:
        return None
    seeds = dict((k.strip(), v) for k, v in re.findall(r"([A-Za-z][\w-]*)\s+`?(\d{3,5})`?", m.group(1)))
    for key in (*([owner] if isinstance(owner, str) else owner), {"completetech": "CompleteTech"}.get(family), family):
        for k, v in seeds.items():
            if key and k.lower() == str(key).lower():
                return v
    return None


def _template(text: str, section: str) -> str | None:
    m = re.search(r"```text\n(.*?)\n```", _section(text, section), re.S)
    return m.group(1) if m else None


def icon_prompt(ctx, resolver: Resolver, art_text: str, glyph: dict | None = None, option: str = "A",
                language: str | None = None, skill_art: str | None = None) -> dict:
    """The Codex prompt for a repository icon (f.3 option A: the (d) template with "repo icon" for "avatar"; option
    B: the illustration template on the light card). The tool fills every mechanical slot from the art direction and
    the repository's facts; the glyph itself is the writer's (needs-writer until `glyph` supplies it)."""
    glyph = {k.upper(): v for k, v in (glyph or {}).items() if v}
    owner, repo = ctx.owner, ctx.repo
    org = org_row(resolver, ctx.brand, owner, require=True)
    org["canonical"], org["current"] = org["brand_key"], current_login(resolver, owner)
    family = org_style(resolver, ctx.brand, owner)["name"]
    logins = [org["canonical"], *resolver.aliases(owner)]  # ART_DIRECTION may name the org by any of its logins (CQ-03)
    colours = icon_colours(ctx, art_text, org, resolver, require_palette=option.upper() == "A")
    org_mark = next((g for g in (org_glyph(art_text, x) for x in logins) if g), None)
    facts = {"repository": f"{org['current']}/{repo}", "description": ctx.meta.get("description") or "",
             "type": ctx.det.get("type"), "category": ctx.det.get("category"), "topics": ctx.meta.get("topics") or [],
             "language": language or ctx.meta.get("language"), "product": ctx.facts.h1(), "family": family,
             "org_glyph": org_mark}
    missing: list[str] = []
    if option.upper() == "B":
        tpl = _template(skill_art or "", "Prompt template for illustrations")
        if not tpl:
            raise NeedsInput("art-direction", "references/art-direction.md has no illustration template")
        lock = None
        names = {family, family.replace("-", " "), org["canonical"].lower(), str(org.get("display_name") or "").lower()}
        for ln in (skill_art or "").splitlines():
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) == 2 and cells[0].lower() in names:
                lock = cells[1]
        adds = dict(re.findall(r"(Security|TCG|Discord orgs|jevplay-games|TouchedByAnAgent) `([^`]*)`",
                               (re.search(r"Family additions:(.*)", skill_art or "") or re.match("", "")).group(0)))
        add_map = {"completetech-security": "Security", "completetech-pokemon": "TCG", "completetech-tcg": "TCG",
                   "completetech-discordapps": "Discord orgs", "completetechdiscord-games": "Discord orgs",
                   "jevplay-games": "jevplay-games", "touchedbyanagent": "TouchedByAnAgent"}
        add_names = {"completetech security": "Security", "completetech tcg": "TCG",
                     "completetech discord apps": "Discord orgs", "completetech discord games": "Discord orgs",
                     "jevplay.games": "jevplay-games", "touched by an agent": "TouchedByAnAgent"}
        # any login of the org (CQ-03), else its display name, so a re-keyed brand.yaml row keeps its negatives
        add_key = next((add_map[a.lower()] for a in logins if a and a.lower() in add_map), None) or \
            add_names.get(str(org.get("display_name") or "").lower())
        if add_key and not adds.get(add_key):
            # a trademark family whose negatives cannot be found: never a prompt without them (fail closed)
            raise NeedsInput("family-additions", f"{org['current']}: references/art-direction.md has no {add_key} "
                                                 "family addition (trademark negatives)")
        pal = re.search(r"CompleteTech palette: `([^`]*)`; highlight line `([^`]*)`", skill_art or "")
        card = ctx.style["tokens"]["card_fill"]
        prompt = tpl.replace("FAMILY STYLE LOCK, VERBATIM", lock or "{STYLE_LOCK}")
        prompt = prompt.replace("Square 1024x1024 | Wide 1536x1024", "Square 1024x1024")
        prompt = prompt.replace("untextured BG background", f"untextured {card} background")
        if family == "completetech" and pal:
            prompt = prompt.replace("PALETTE. HIGHLIGHT LINE", f"{pal.group(1)}. {pal.group(2)}")
        prompt = prompt.replace("One sentence: the single hero object or scene that represents the repository or "
                                "org's function.", glyph.get("SUBJECT") or "{SUBJECT}")
        prompt = re.sub(r"3–5 objects\.[^\n]*", glyph.get("OBJECTS") or "{OBJECTS}", prompt)
        prompt = prompt.replace("FAMILY ADDITIONS", " ".join(x for x in (adds.get(add_key), glyph.get("EXTRA_NEGATIVES"))
                                                             if x)).rstrip()
        prompt = prompt.replace("[STYLE LOCK — FAMILY]", f"[STYLE LOCK — {colours.get('family_label') or family}]")
    else:
        tpl = _template(art_text, "(d) Shared prompt template") or \
            _template(art_text, "Repository glyph prompt template")
        if not tpl:
            raise NeedsInput("art-direction", "selected art direction has no (d) Shared prompt template "
                             "or Repository glyph prompt template")
        seed = seed_for(art_text, logins, family)
        slots = {k: colours.get(k) for k in ("LINE_NAME", "LINE_HEX", "CORE_HEX", "GLOW_HEX", "SPARK_NAME", "SPARK_HEX",
                                              "SPARK_CORE_HEX", "SPARK_BLOOM_HEX")}
        slots.update(ACCOUNT=f"{org['current']}/{repo}", KIND="repository", CIRCLE_CLAUSE="",
                     CROP="repository icon, shown inside the light card of the README hero banner, the repo card and the "
                          "social preview", SECONDARY_LIGHT="", SECONDARY_LINE="", SPARK_D="94", SPARK_CORE_D="37",
                     TEXT_RULE="Any text, letters, numbers or words",
                     SEED=seed or "not set",
                     SEED_INSTRUCTION=f"Use seed {seed} when supported." if seed else "Use the tool's default seed.",
                     STYLE_REFERENCES="the three approved pilot renders from art/golden/neon-night/.",
                     BRAND_REFERENCE=f"Org avatar art/reference/avatars/{org['canonical']}.png for family consistency "
                                     "only: do not copy its glyph; this repository's silhouette must differ from it at "
                                     "48 px (f.3).")
        if slots.get("SPARK_NAME"):
            slots["SPARK_EXCLUSIVITY"] = f" and the only element in {slots['SPARK_NAME']}"
        if slots.get("GLOW_HEX"):
            slots["POOL"] = (f"one very soft round pool of {slots['GLOW_HEX']} light at about 10% strength, about 880 px "
                             "across, centred behind the glyph and fading to nothing well before the edges")
        size = str(glyph.get("SIZE_CLASS") or "").upper()
        if size in SIZE_CLASSES:
            slots["SIZE_CLASS"] = f"{size}: {SIZE_CLASSES[size]}"
        for k in ("GLYPH_NAME", "GLYPH_DESCRIPTION", "SPARK_PLACEMENT"):
            if glyph.get(k):
                slots[k] = glyph[k]
        neg = f"Do not draw the {org['canonical']} org glyph ({org_mark})." if org_mark else ""
        slots["EXTRA_NEGATIVES"] = " ".join(x for x in (glyph.get("EXTRA_NEGATIVES"), neg) if x)
        prompt = re.sub(r"\(a\) Geometry:.*?(?= \(b\) Style:)",
                        "(a) Geometry: none yet; this glyph is new, so section 7 is the geometry and the lock pass "
                        "traces the chosen candidate into the compositor.", tpl, flags=re.S)
        prompt = re.sub(r"output art/out/avatars/\S+", f"output art/out/icons/{org['current']}/{repo}-1024-c{{1..4}}.png",
                        prompt)
        prompt = re.sub(r"The pipeline downsamples your image[^.]*\.",
                        "The lock pass traces your image into the compositor, which renders the flat 1024 × 1024 px "
                        "assets/icon.png in the family light-surface inks.", prompt)
        prompt = prompt.replace("NEON NIGHT AVATAR", "NEON NIGHT REPO ICON")
        prompt = re.sub(r"\bavatars\b", "repo icons", prompt)
        prompt = re.sub(r"\bavatar\b", "repo icon", prompt)
        prompt = prompt.replace("It is one of 28 repo icons in a single matched family",
                                "It joins the 28 Neon Night avatars and its sibling repo icons as one matched family")
        prompt = prompt.replace("(identical in all 28 repo icons)", "(identical to the Neon Night avatars)")
        prompt = prompt.replace("same model and version for all 28", "same model and version as the avatar set")
        for k, v in slots.items():
            if v is not None:
                prompt = prompt.replace("{" + k + "}", str(v))
    missing = sorted(set(re.findall(r"\{([A-Z_]+)\}", prompt)))
    ink = colours.get("INK") or []
    return {"prompt": prompt, "missing": missing, "facts": facts, "option": option.upper(),
            "render": {"ink": ink[0] if ink else None, "spark": ink[1] if len(ink) > 1 else None,
                       "size": [ICON_PX, ICON_PX], "live_area": [LIVE_MARGIN, LIVE_MARGIN, ICON_PX - LIVE_MARGIN,
                                                                 ICON_PX - LIVE_MARGIN], "budget": ICON_BUDGET}}


def prompt_markdown(res: dict) -> str:
    f, r = res["facts"], res["render"]
    rows = "\n".join(f"| {k.replace('_', ' ').capitalize()} | {', '.join(v) if isinstance(v, list) else (v or '-')} |"
                     for k, v in f.items())
    return (f"# Repo icon prompt: {f['repository']}\n\n"
            f"- Standard {STANDARD}; github-showcase-skill {__version__}; option {res['option']} (q59); decision 12.\n"
            f"- Output `assets/icon.png`: {ICON_PX} × {ICON_PX} PNG RGBA, transparent, at most {ICON_BUDGET // 1000} KB, "
            "no text, one file for both GitHub themes (decision 21; no `-dark` or `-light` sibling).\n"
            f"- Render (lock pass): flat body in the light-surface ink {r['ink'] or '(see ART_DIRECTION (b))'}, spark in "
            f"{r['spark'] or '(see ART_DIRECTION (b))'}, no tile and no glow, centred in the live area "
            f"{r['live_area']}.\n"
            "- Then: `showcase.py content icon normalize --in <candidate.png>` and `showcase.py content icon check`.\n\n"
            "## Repository facts\n\n| Fact | Value |\n|---|---|\n" + rows + "\n\n## Prompt\n\n```text\n" +
            res["prompt"] + "\n```\n")


def _lab_cache():
    from .color import lab
    cache: dict = {}

    def get(rgb):
        v = cache.get(rgb)
        if v is None:
            v = cache[rgb] = lab(rgb)
        return v
    return get


def _px(im) -> list:
    """Pixel values in raster order (Pillow 13 deprecates getdata for get_flattened_data)."""
    get = getattr(im, "get_flattened_data", None)
    return list(get() if get else im.getdata())


def _de(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def normalize_icon(img, ground: str = "auto", card: str | None = None, pixel_art: bool = False):
    """(1024 px RGBA or RGB image, info). Transparent icons are keyed (ΔE ≤ 6 from the ground, 2 px feather),
    trimmed to their alpha box and fitted to the 688 px live area; an icon with its own opaque ground (an avatar-style
    night tile) is kept full-bleed (`ground="keep"`)."""
    from PIL import Image, ImageFilter
    from .color import rgb as hexrgb
    from .iconbox import corner_ground, native_pixels
    im = img.convert("RGBA")
    info: dict = {"source_px": list(im.size)}
    corners = [im.getpixel(p) for p in ((0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1))]
    has_alpha = any(c[3] < 255 for c in corners)
    gnd = None if has_alpha else corner_ground(im)
    mode = ground
    if mode == "auto":
        if has_alpha:
            mode = "transparent"
        elif gnd is None:
            raise ArtFail("icon-ground", "corners are neither transparent nor one opaque ground")
        else:
            lab = _lab_cache()
            near_card = card is not None and _de(lab(hexrgb(gnd)), lab(hexrgb(card))) <= CONTENT_DE
            mode = "transparent" if near_card else "keep"
    info["mode"] = mode
    if mode == "keep":
        if gnd is None:
            raise ArtFail("icon-ground", "--ground keep needs four opaque corners of one colour")
        side = max(im.size)
        sq = Image.new("RGBA", (side, side), hexrgb(gnd) + (255,))
        sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        out = sq.convert("RGB").resize((ICON_PX, ICON_PX), Image.LANCZOS)
        info.update(ground=gnd)
        return out, info
    if not has_alpha:
        if gnd is None:
            raise ArtFail("icon-ground", "no transparent or uniform ground to key out")
        lab = _lab_cache()
        g = lab(hexrgb(gnd))
        src = _px(im)
        mask = Image.new("L", im.size)
        mask.putdata([0 if _de(lab(p[:3]), g) <= KEY_DE else 255 for p in src])
        alpha = _min(mask, mask.filter(ImageFilter.GaussianBlur(2)))  # 2 px feather inside the edge, no ground halo
        gr, gg, gb = hexrgb(gnd)
        rgba = []
        for p, a in zip(src, _px(alpha)):
            if a == 0:
                rgba.append((0, 0, 0, 0))
            elif a == 255:
                rgba.append((p[0], p[1], p[2], 255))
            else:  # decontaminate the ground out of the feathered edge
                k = a / 255
                rgba.append(tuple(max(0, min(255, round((c - gc * (1 - k)) / k))) for c, gc in
                                  ((p[0], gr), (p[1], gg), (p[2], gb))) + (a,))
        im = Image.new("RGBA", im.size)
        im.putdata(rgba)
        info.update(keyed_from=gnd)
    box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not box:
        raise ArtFail("icon-empty", "nothing left after keying the ground")
    im = im.crop(box)
    native = native_pixels(im) if pixel_art else None
    canvas = Image.new("RGBA", (ICON_PX, ICON_PX), (0, 0, 0, 0))
    if native is not None:
        k = max(1, LIVE // max(native.size))
        im = native.resize((native.width * k, native.height * k), Image.NEAREST)
        info["resample"] = f"nearest x{k}"
    else:
        k = LIVE / max(im.size)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        info["resample"] = "lanczos"
    canvas.alpha_composite(im, ((ICON_PX - im.width) // 2, (ICON_PX - im.height) // 2))
    info["trim_box"] = list(box)
    return canvas, info


def _min(a, b):
    from PIL import ImageChops
    return ImageChops.darker(a, b)


def icon_bytes(img) -> tuple[bytes, list[str]]:
    from .scene import png_bytes
    data = png_bytes(img)
    logs = []
    if len(data) > ICON_BUDGET and img.mode == "RGBA":
        q = img.quantize(256, method=2)  # fast octree keeps alpha
        b = io.BytesIO()
        q.save(b, "PNG", optimize=True)
        data = b.getvalue()
        logs.append("icon-quantized")
    if len(data) > ICON_BUDGET:
        raise ArtFail("icon-budget", f"{len(data)} bytes > {ICON_BUDGET}")
    return data, logs


def _dhash(img, size: int = 16) -> int:
    from PIL import Image
    g = img.convert("RGBA")
    bg = Image.new("RGBA", g.size, (255, 255, 255, 255))
    bg.alpha_composite(g)
    s = bg.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = _px(s)
    bits = 0
    for y in range(size):
        for x in range(size):
            bits = (bits << 1) | (px[y * (size + 1) + x] > px[y * (size + 1) + x + 1])
    return bits


def icon_qa(data: bytes, *, card: str, ink: list[str] | None = None, org_mark: Path | None = None,
            siblings: list[str] | None = None, strict: bool = False) -> dict:
    """Automated icon checks (f.3, art QA): size, budget, alpha, live area, coverage, contrast on the card, family
    inks, not the org glyph, one file. OCR and the 48 px set sheet stay manual. `strict` makes a failing family-ink
    check fail the icon (default: warn); with no `ink` the family-ink check is not emitted at all."""
    from PIL import Image
    from .color import contrast, hexstr, rgb as hexrgb
    from .pnglint import validate_png
    checks: list[dict] = []

    def add(name, ok, detail="", level="fail"):
        checks.append({"check": name, "result": "pass" if ok else level, "detail": detail})
    try:
        w, h, colour = validate_png(data)
    except ValueError as exc:
        add("png", False, str(exc))
        return {"result": "fail", "checks": checks}
    add("png", True)
    add("size", (w, h) == (ICON_PX, ICON_PX), f"{w}x{h}")
    add("bytes", len(data) <= ICON_BUDGET, f"{len(data)} <= {ICON_BUDGET}")
    im = Image.open(io.BytesIO(data))
    im.load()
    rgba = im.convert("RGBA")
    alpha = rgba.getchannel("A")
    transparent = colour in (4, 6) or (colour == 3 and "transparency" in im.info)
    lab = _lab_cache()
    if transparent:
        corners = [alpha.crop((x, y, x + 16, y + 16)).getextrema()[1] for x, y in
                   ((0, 0), (w - 16, 0), (0, h - 16), (w - 16, h - 16))]
        add("transparent-corners", max(corners) == 0, f"max corner alpha {max(corners)}")
        box = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
        ink_px = [p for p in _px(rgba.resize((256, 256))) if p[3] >= 200]
        coverage = sum(1 for v in _px(alpha.resize((256, 256))) if v > 128) / 65536
    else:
        from .iconbox import corner_ground
        g = corner_ground(rgba)
        add("opaque-ground", g is not None, g or "corners differ")
        gl = lab(hexrgb(g)) if g else None
        small = rgba.convert("RGB").resize((256, 256))
        diff = Image.new("L", small.size)
        diff.putdata([255 if gl and _de(lab(p), gl) > CONTENT_DE else 0 for p in _px(small)])
        b = diff.getbbox()
        box = tuple(round(v * w / 256) for v in b) if b else None
        ink_px = [p + (255,) for p, d in zip(_px(small), _px(diff)) if d]
        coverage = len(ink_px) / 65536
        card = g or card
    tol = 4
    inside = bool(box) and box[0] >= LIVE_MARGIN - tol and box[1] >= LIVE_MARGIN - tol and \
        box[2] <= ICON_PX - LIVE_MARGIN + tol and box[3] <= ICON_PX - LIVE_MARGIN + tol
    add("live-area", inside, f"content box {list(box) if box else None}, live area {LIVE_MARGIN}..{ICON_PX - LIVE_MARGIN}")
    span = max(box[2] - box[0], box[3] - box[1]) if box else 0
    add("fills-live-area", span >= 0.75 * LIVE, f"longest side {span} px of {LIVE}", level="warn")
    add("coverage", 0.03 <= coverage <= 0.45, f"{coverage:.1%} of the canvas", level="warn")
    dom = None
    if ink_px:
        counts: dict = {}
        for p in ink_px:
            key = (p[0] // 16 * 16 + 8, p[1] // 16 * 16 + 8, p[2] // 16 * 16 + 8)
            counts[key] = counts.get(key, 0) + 1
        dom = hexstr(max(counts, key=counts.get))
        cr = contrast(dom, card)
        add("contrast-on-card", cr >= 3.0, f"dominant ink {dom} on {card}: {cr:.2f}:1 (>= 3:1)")
        if ink:
            near = min(_de(lab(hexrgb(dom)), lab(hexrgb(x))) for x in ink)
            add("family-ink", near <= 12, f"dominant ink {dom}, nearest family ink ΔE {near:.1f}",
                level="fail" if strict else "warn")
    else:
        add("contrast-on-card", False, "no opaque ink")
    if org_mark and Path(org_mark).is_file() and Path(org_mark).stat().st_size > 0:
        try:
            mk = Image.open(org_mark)
            mk.load()
            d = bin(_dhash(rgba) ^ _dhash(mk)).count("1")
            add("not-org-glyph", d > 24, f"dHash distance {d} to {Path(org_mark).name}")
        except Exception as exc:  # an unreadable org mark cannot be compared
            add("not-org-glyph", True, f"org mark unreadable: {str(exc)[:60]}", level="warn")
    bad = [s for s in siblings or [] if re.search(r"icon[-_.](dark|light)\.", s, re.I)]
    add("one-file", not bad, ", ".join(bad) or "no -dark or -light sibling (decision 21)")
    checks.append({"check": "no-text", "result": "manual", "detail": "OCR and the 48 px org sheet are reviewed (f.3, g)"})
    res = "fail" if any(c["result"] == "fail" for c in checks) else (
        "warn" if any(c["result"] == "warn" for c in checks) else "pass")
    return {"result": res, "checks": checks, "dominant_ink": dom}


# =====================================================================================================
# CLI (`showcase.py content ...`): wired by showcase.py with `content.add_parser(sub, <showcase module>)`
# =====================================================================================================
ACTIONS = ("social", "icon", "links", "linguist", "actions", "images", "sidebar")


def register(sub) -> None:
    """showcase.py wires `content` with register(sub), like `org` and `project`."""
    add_parser(sub)


def add_parser(sub, cli=None):
    """Register `content {social,icon,links,linguist,actions,images,sidebar}` on showcase.py's subparsers. `cli` is the
    showcase module (its context, repo_dir and cmd_social helpers); by default the running showcase.py."""
    import argparse
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--report", help="also write the JSON result to this file")
    common.add_argument("--registry", help="registry/estate.yaml (default: the bundle's, when present)")
    common.add_argument("--approved", help="decisions/approved.tsv (approved org renames, CQ-03)")
    common.add_argument("--approved-yaml", help="decisions/APPROVED_ACTIONS.yaml")
    common.add_argument("--actions", help="decisions/estate-actions.json")
    common.add_argument("--jobs", help="append the writer jobs (JSON lines) to FILE")
    s = sub.add_parser("content", help="content checks and proposals: social, icon, links, linguist, actions, images, "
                                       "sidebar (read-only; emits diffs, gh argv and writer jobs)")
    cs = s.add_subparsers(dest="content_action", required=True, metavar="<action>")

    a = cs.add_parser("social", parents=[common], help="1280x640 repo social preview (R10; same options and file as the deprecated "
                                                    "social-preview), plus the browser upload job")
    a.add_argument("--out")
    a.add_argument("--title")
    a.add_argument("--icon")
    a.add_argument("--allow-unmeasured", action="store_true")
    a.add_argument("--allow-hold", action="store_true")
    a.add_argument("--job", action="store_true", help="also emit the writer browser job that uploads it")

    a = cs.add_parser("icon", parents=[common], help="repo icon (RT-04): prompt file, normalize a candidate, QA check")
    a.add_argument("icon_action", choices=("prompt", "normalize", "check"))
    a.add_argument("--option", choices=("A", "B"), default="A", help="q59 option: A Neon Night glyph, B isometric")
    a.add_argument("--glyph", help="YAML/JSON with the writer's glyph_name, glyph_description, spark_placement, "
                                   "size_class (option B: subject, objects)")
    a.add_argument("--art-direction", help="art direction file (default: the skill's references/art-direction.md)")
    a.add_argument("--in", dest="src", help="normalize: the returned candidate PNG")
    a.add_argument("--ground", choices=("auto", "transparent", "keep"), default="auto")
    a.add_argument("--out", help="prompt: the prompt file (art/prompts/<org>/<repo>/icon.md); normalize: the icon "
                                 "(default assets/icon.png in the checkout); check: the icon to check")
    a.add_argument("--preview", help="normalize: also write a 48 px preview on the card colour")
    a.add_argument("--allow-hold", action="store_true", help="work on a family that is on hold (as banner and card)")
    a.add_argument("--strict", action="store_true", help="fail (not warn) when the dominant ink is not a family ink; "
                                                         "also set by the family key icon_strict_family_ink")

    a = cs.add_parser("links", parents=[common], help="CQ-04: relative links, anchors and remote targets")
    a.add_argument("files", nargs="*", help="Markdown files (default: displayed README, docs/**, .github/*.md, profile)")
    a.add_argument("--readme-path", help="the README GitHub displays (GET /repos/{o}/{r}/readme .path)")
    a.add_argument("--base-ref", help="git ref of the base: only breakage this change introduces fails")
    a.add_argument("--online", action="store_true", help="cached §10.2 GET of remote URLs and gh full_name checks")
    a.add_argument("--cache", help="remote-check cache file (JSON)")
    a.add_argument("--max-remote", type=int, default=300)
    a.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host")
    a.add_argument("--strict", action="store_true", help="fail on any broken link, even without --base-ref")
    a.add_argument("--diff", action="store_true", help="print the proposals as a unified diff (never applied)")

    a = cs.add_parser("linguist", parents=[common], help="RP-07: paths that distort the language bar")
    a.add_argument("--min-share", type=float, default=0.02)
    a.add_argument("--language", help="a registry `language:` override for the chip")

    a = cs.add_parser("actions", parents=[common], help="RP-06/RP-01: Actions health and merge side effects")
    a.add_argument("--runs", help="`gh run list --json ...` output or REST actions/runs JSON")
    a.add_argument("--workflows", help="REST actions/workflows JSON or `gh workflow list --json id,name,path,state`")
    a.add_argument("--pages", help="REST repos/{o}/{r}/pages JSON")
    a.add_argument("--changed", nargs="*", help="paths the merge changes (default: the estate polish set)")
    a.add_argument("--approval", action="append", default=[], metavar="WORKFLOW=ID",
                   help="approved workflow-toggle id for a workflow file (q79)")

    a = cs.add_parser("images", parents=[common], help="RP-03/RP-10: README image budget and dark-theme flags")
    a.add_argument("files", nargs="*")
    a.add_argument("--readme-path")
    a.add_argument("--base-ref", help="images not in this ref are new (default HEAD)")
    a.add_argument("--approval-id", help="per-repo lossy-image approval id (q69)")
    a.add_argument("--out-dir", help="write pixel-identical optimized candidates here for review")
    a.add_argument("--online", action="store_true")

    a = cs.add_parser("sidebar", parents=[common], help="RP-05: About sidebar target and browser job")
    a.add_argument("--facts", required=True, help="JSON: releases, deployments, environments, packages (per repo, or "
                                                  "keyed by OWNER/REPO for many)")
    a.add_argument("--packages", action="append", default=[], help="org packages JSON (repeatable)")
    a.add_argument("--current", help="JSON of known current box states (skip no-ops)")
    a.add_argument("--repo", dest="only", help="OWNER/REPO filter for an estate facts file")
    s.set_defaults(func=lambda args: cmd_content(args, cli))
    return s


def _load_json(path, flag: str):
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShowcaseError(f"cannot read {flag} {path}: {exc}", log="usage")


def _cli():
    import sys
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "context") and hasattr(main, "cmd_social"):
        return main
    import showcase  # scripts/ is on sys.path when ctshowcase is imported from showcase.py or the tests
    return showcase


def _owner_repo(args, cli, rd: Path | None) -> tuple[str | None, str | None, dict]:
    from .meta import from_repo_dir, load_file
    if args.meta:
        m = load_file(args.meta)
        return m.get("owner"), m.get("repo"), m
    if rd is not None:
        m = from_repo_dir(rd)
        return m.get("owner"), m.get("repo"), m
    return None, None, {}


def _resolver(args, cli):
    if getattr(args, "_content_resolver", None) is None:
        args._content_resolver = load_resolver(cli.brand(args), args.registry, args.approved, args.approved_yaml,
                                               args.actions)
    return args._content_resolver


def _ctx(args, cli, resolver):
    """RepoContext with the org row and style taken through the resolver (a renamed org keeps its row)."""
    ctx = cli.context(args)
    key = resolver.brand_key(ctx.owner)
    if key and key != ctx.owner and not ctx.org.get("known"):
        ctx.org = org_row(resolver, ctx.brand, ctx.owner)
        ctx.style = org_style(resolver, ctx.brand, ctx.owner)
        ctx.logs = [x for x in ctx.logs if x != "needs-input:org-row"]
        ctx.log(f"org-alias:{key}")
    return ctx


def _finish(args, obj: dict, code: int):
    jobs = list(obj.get("jobs") or []) + ([obj["job"]] if obj.get("job") else [])
    if getattr(args, "jobs", None) and jobs:  # writer jobs only; unapproved proposals stay in the report
        from .records import append
        append(args.jobs, jobs)
        obj["jobs_file"] = str(args.jobs)
    if getattr(args, "report", None):
        p = Path(args.report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return obj, code


def _code(result: str) -> int:
    return CHECK_FAILED if result in ("fail", "needs-writer") else OK


def cmd_content(args, cli=None):
    cli = cli or _cli()
    act = args.content_action
    resolver = _resolver(args, cli)
    head = {"command": "content", "action": act}
    if act == "social":
        owner, _, _ = _owner_repo(args, cli, None)
        if owner:
            resolver.check_owner(owner, allow_hold=args.allow_hold)
        obj, code = cli.cmd_social(args)
        obj = dict(head, **{k: v for k, v in obj.items() if k != "command"}, alias_of="social-preview")
        if args.job and obj.get("result") == "ok":
            ctx = _ctx(args, cli, resolver)
            job = social_job(ctx, resolver, obj["out"])
            if job and obj.get("footer") != f"github.com/{job['repo']}":
                # the image names another login than the repository it would be uploaded to (an approved rename the
                # render did not see): never upload it; re-render once the image names the current login
                obj["result"], code = "needs-input", CHECK_FAILED
                obj["logs"] = list(obj.get("logs") or []) + ["needs-input:social-login"]
                job = None
            obj["job"] = job
        return _finish(args, obj, code)
    if act in ("links", "images"):
        rd = cli.repo_dir(args)
        if rd is None:
            raise ShowcaseError(f"content {act} needs a checkout (--repo-dir)", log="usage")
        owner, repo, _ = _owner_repo(args, cli, rd)
        if owner:
            resolver.check_owner(owner)
        tree = Tree(rd)
        readme = displayed_readme(tree, args.readme_path)
        files = list(args.files) or markdown_files(tree, readme)
        missing = [f for f in files if not tree.is_file(f)]
        if missing:
            raise ShowcaseError(f"not in the checkout: {', '.join(missing)}", log="usage")
        if not files:  # the wrong directory (no README, no docs) must not read as a clean pass
            raise NeedsInput("readme", f"content {act}: {rd} has no README or Markdown file to check (run it inside the "
                                       "target checkout, or pass --repo-dir or FILE ...)")
        head.update(owner=owner, repo=repo, readme=readme)
        if act == "links":
            fetcher = Fetcher(args.cache, delay=args.delay, max_requests=args.max_remote) if args.online else None
            base = Tree(rd, args.base_ref) if args.base_ref else None
            res = links_report(tree, files, resolver=resolver, fetcher=fetcher, online=args.online, base=base,
                               strict=args.strict, self_slug=(owner, repo) if owner and repo else None)
            if fetcher:
                fetcher.save()
                res["requests"] = fetcher.requests
            if args.diff:
                res["diff"] = proposal_diff(tree, res["proposals"])
            obj = dict(head, **res)
        else:
            fetcher = Fetcher(None) if args.online else None
            res = images_report(tree, files, new_paths=new_files(tree, args.base_ref), approval_id=args.approval_id,
                                out_dir=args.out_dir, fetcher=fetcher)
            obj = dict(head, **res)
        return _finish(args, obj, _code(obj["result"]))
    if act == "linguist":
        ctx = _ctx(args, cli, resolver)
        resolver.check_owner(ctx.owner)
        tree = Tree(ctx.repo_dir) if ctx.repo_dir else None
        override = dict(ctx.override)
        if args.language:
            override["language"] = args.language
        res = linguist_report(ctx.meta, tree, override=override, min_share=args.min_share)
        return _finish(args, {**head, "owner": ctx.owner, "repo": ctx.repo, **res, "logs": ctx.logs + res["logs"]}, OK)
    if act == "actions":
        ctx = _ctx(args, cli, resolver)
        resolver.check_owner(ctx.owner)
        wf_files, root_files, readme = {}, (), ""
        if ctx.repo_dir:
            tree = Tree(ctx.repo_dir)
            wf_files = {f: tree.read(f) or "" for f in sorted(tree.files)
                        if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", f)}
            root_files = [f for f in tree.files if "/" not in f]
            rp = displayed_readme(tree)
            readme = tree.read(rp) if rp else ""
        else:
            readme = ctx.meta.get("readme_head") or ""
            root_files = [f for f in ctx.meta.get("files") or [] if "/" not in f]
        approvals = dict(x.split("=", 1) for x in args.approval if "=" in x)
        res = actions_report(ctx.meta, runs=_load_json(args.runs, "--runs"),
                             workflows=_load_json(args.workflows, "--workflows"), workflow_files=wf_files,
                             readme=readme, root_files=root_files, pages=_load_json(args.pages, "--pages"),
                             resolver=resolver, changed=tuple(args.changed) if args.changed else POLISH_PATHS,
                             approval_ids=approvals)
        obj = dict(head, owner=ctx.owner, **{k: v for k, v in res.items() if k != "logs"}, logs=ctx.logs + res["logs"])
        return _finish(args, obj, _code(res["result"]))
    if act == "sidebar":
        return _finish(args, *_cmd_sidebar(args, cli, resolver, head))
    if act == "icon":
        return _finish(args, *_cmd_icon(args, cli, resolver, head))
    raise ShowcaseError(f"unknown content action {act}", log="usage")


def social_job(ctx, resolver: Resolver, out: str) -> dict | None:
    """Browser job for the repository social preview upload (STANDARD §12.4; public T1/T2 repos only)."""
    if not ctx.social_applicable():
        return None
    full = f"{current_login(resolver, ctx.owner)}/{ctx.repo}"
    steps = [f"Open https://github.com/{full}/settings (the General page).",
             "Scroll to \"Social preview\" and click \"Edit\", then \"Upload an image…\".",
             f"Choose the file {out} from the repository checkout and confirm the dialog.",
             "Wait until the preview shows the new image; do not change any other setting on this page.",
             f"Verify with the read-only query: gh api graphql -f query='{{repository(owner:\"{full.split('/')[0]}\","
             f"name:\"{ctx.repo}\"){{usesCustomOpenGraphImage openGraphImageUrl}}}}' (usesCustomOpenGraphImage is true)."]
    return browser_job(job_id("p5", "social-preview", full), "5", full, f"https://github.com/{full}/settings",
                       "social-preview", steps, "Upload the repository social preview (R10; STANDARD §9.5, §12.4).")


def _cmd_sidebar(args, cli, resolver, head):
    facts = _load_json(args.facts, "--facts") or {}
    pk = None
    if args.packages:
        pk = {}
        for p in args.packages:
            for k, v in packages_by_repo(_load_json(p, "--packages"), resolver).items():
                pk[k] = pk.get(k, 0) + v
    current = _load_json(args.current, "--current") or {}
    keyed = isinstance(facts, dict) and facts and all(isinstance(k, str) and "/" in k for k in facts)
    if not keyed:
        ctx = _ctx(args, cli, resolver)
        resolver.check_owner(ctx.owner)
        res = sidebar_plan(ctx.meta, facts, resolver=resolver, packages=pk,
                           current=current.get(f"{ctx.owner}/{ctx.repo}") or current or None)
        obj = dict(head, owner=ctx.owner, repo=ctx.repo, **{k: v for k, v in res.items() if k != "logs"},
                   jobs=[res["job"]] if res["job"] else [], tsv_header=SIDEBAR_TSV_HEADER, logs=ctx.logs + res["logs"])
        return obj, OK
    rows, jobs, logs, skipped, unknown = [], [], [], [], 0
    for full, f in sorted(facts.items()):
        o, r = full.split("/", 1)
        if args.only and not (resolver.same(o, args.only.split("/")[0]) and r.lower() == args.only.split("/")[1].lower()):
            continue
        try:
            resolver.check_owner(o)
        except Refused as exc:
            skipped.append({"repo": full, "why": exc.log})
            continue
        meta = dict((f or {}).get("meta") or {}, owner=o, repo=r)
        meta.setdefault("visibility", (f or {}).get("visibility", "public"))
        res = sidebar_plan(meta, f or {}, resolver=resolver, packages=pk, current=current.get(full))
        rows.append(res["tsv"])
        if res["job"]:
            jobs.append(res["job"])
        unknown += res["result"] == "needs-input"
        logs += [f"{full}:{x}" for x in res["logs"]]
    # a repository whose facts are incomplete gets no job; the batch must say so instead of reading as a pass
    result = "proposal" if jobs else ("needs-input" if unknown else "pass")
    obj = dict(head, result=result, repos=len(rows), needs_input=unknown, tsv_header=SIDEBAR_TSV_HEADER, tsv=rows,
               jobs=jobs, skipped=skipped, logs=logs)
    return obj, OK


def _cmd_icon(args, cli, resolver, head):
    from PIL import Image
    ctx = _ctx(args, cli, resolver)
    resolver.check_owner(ctx.owner)
    # decision 12: the same applicability as banner, card, lint all and doctor (RepoContext.art_status); only
    # watching-org forks and a placeholder org's `.github` are exempt. Forks outside the watching org, backups and
    # `.github` repositories need their own icon. The resolver also sees the renames and placeholders passed here.
    why = ctx.art_status()["icon"]
    if resolver.owner_status(ctx.owner) == "watching":  # only its forks are exempt; its `.github` needs an icon
        why = "exempt:watching-fork" if ctx.is_fork else \
            why if ctx.repo == ".github" else "hold:watching-non-fork"
    elif ctx.repo == ".github" and resolver.is_placeholder(ctx.owner):
        why = "exempt:placeholder-org"
    if why and why.startswith("exempt"):
        return dict(head, owner=ctx.owner, repo=ctx.repo, result="exempt", logs=[why]), OK
    if why == "t3-signoff":
        raise Refused(f"{ctx.owner} is T3; needs co-owner sign-off", log="t3-signoff")
    if why and why.startswith("hold") and not getattr(args, "allow_hold", False):  # a family on hold (brand.yaml style
        # `hold`) or a watching-org non-fork (`hold:watching-non-fork`), as banner and card refuse
        raise ShowcaseError(f"{ctx.owner}/{ctx.repo} is held ({why}); pass --allow-hold", log=why)
    head.update(owner=ctx.owner, repo=ctx.repo, icon_action=args.icon_action)
    card = ctx.style["tokens"]["card_fill"]
    org = org_row(resolver, ctx.brand, ctx.owner)
    mark = ctx.brand.asset(org.get("mark"))
    strict = bool(getattr(args, "strict", False) or ctx.style.get("icon_strict_family_ink"))
    if args.icon_action == "prompt":
        art = load_art_direction(args.art_direction)
        glyph = None
        if args.glyph:
            try:
                glyph = load_yaml_text(Path(args.glyph).read_text(encoding="utf-8")) or {}
            except OSError as exc:
                raise ShowcaseError(f"cannot read --glyph {args.glyph}: {exc}", log="usage")
        lang = None
        if ctx.repo_dir or ctx.meta.get("files"):
            try:
                lang = linguist_report(ctx.meta, Tree(ctx.repo_dir) if ctx.repo_dir else None,
                                       override=ctx.override)["primary"]["language"]
            except NeedsInput:
                lang = None
        skill_art = SKILL_ART_DIRECTION.read_text(encoding="utf-8") if args.option == "B" else None
        res = icon_prompt(ctx, resolver, art, glyph, args.option, lang, skill_art)
        md = prompt_markdown(res)
        result = "needs-writer" if res["missing"] else "ok"
        out = None
        if args.out and not res["missing"]:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(md, encoding="utf-8")
        logs = ctx.logs + ([f"needs-writer:{s}" for s in res["missing"]])
        obj = dict(head, result=result, out=str(out) if out else None, missing=res["missing"], facts=res["facts"],
                   render=res["render"], prompt=res["prompt"], markdown=None if out else md, logs=logs,
                   note="The glyph is the writer's: fill glyph_name, glyph_description, spark_placement and size_class "
                        "(--glyph FILE) and re-run until the result is ok; nothing is written before then.")
        return obj, _code(result)
    ink = []
    try:
        art = load_art_direction(args.art_direction)
        ink = icon_colours(ctx, art, org, resolver).get("INK") or []
    except NeedsInput as exc:
        ctx.log(exc.log)
    rd = ctx.repo_dir
    siblings = [p.name for p in (rd / "assets").glob("icon*")] if rd and (rd / "assets").is_dir() else []
    if args.icon_action == "normalize":
        if not args.src:
            raise ShowcaseError("content icon normalize needs --in CANDIDATE.png", log="usage")
        src = Image.open(args.src)
        src.load()
        img, info = normalize_icon(src, args.ground, card, pixel_art=bool(ctx.style.get("icon_pixel_art")))
        data, qlogs = icon_bytes(img)
        qa = icon_qa(data, card=card, ink=ink, org_mark=mark, siblings=siblings, strict=strict)
        out = Path(args.out) if args.out else cli.default_out(args, "assets/icon.png")
        if qa["result"] == "fail":
            return dict(head, result="fail", out=None, info=info, qa=qa, logs=ctx.logs + qlogs + ["art-fail:icon-qa"],
                        note="nothing written"), CHECK_FAILED
        cli.write_bytes(out, data)
        if args.preview:
            prev = Image.new("RGBA", (48, 48), _hex_rgba(card))
            prev.alpha_composite(img.convert("RGBA").resize((48, 48), Image.LANCZOS))
            cli.write_bytes(Path(args.preview), _png(prev.convert("RGB")))
        return dict(head, result=qa["result"], out=str(out), bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(), info=info, qa=qa, logs=ctx.logs + qlogs), OK
    path = Path(args.out) if args.out else (rd / "assets" / "icon.png" if rd else None)
    if path is None or not path.is_file():
        return dict(head, result="fail", file=str(path) if path else None, logs=ctx.logs + ["needs-input:repo-icon"]), \
            CHECK_FAILED
    qa = icon_qa(path.read_bytes(), card=card, ink=ink, org_mark=mark, siblings=siblings, strict=strict)
    return dict(head, result=qa["result"], file=str(path), qa=qa, logs=ctx.logs), _code(qa["result"])


def _hex_rgba(value: str) -> tuple[int, int, int, int]:
    from .color import rgba
    return rgba(value)


def _png(img) -> bytes:
    from .scene import png_bytes
    return png_bytes(img)


def main(argv=None) -> int:
    """Standalone entry (`python -m ctshowcase.content ...` from scripts/) until showcase.py registers `content`."""
    import argparse
    import sys
    cli = _cli()
    p = cli.parser()
    sub = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    if "content" not in sub.choices:
        add_parser(sub, cli)
    args = p.parse_args(argv)
    if args.format is None:
        args.format = "text" if args.command in cli.GENERATORS else "json"
    try:
        obj, code = args.func(args)
    except ShowcaseError as exc:
        obj = {"command": args.command, "result": "refused" if exc.code == 2 and exc.log in ("hold", "t3-signoff", "exempt")
               else exc.log.split(":")[0], "error": str(exc), "logs": [exc.log]}
        code = exc.code
        if args.format == "text" and not args.quiet:
            print(f"{args.command}: {exc}", file=sys.stderr)
            return code
    if obj is not None:
        cli.emit(args, obj)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
