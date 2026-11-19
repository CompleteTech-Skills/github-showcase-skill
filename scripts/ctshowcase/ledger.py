"""Operator-side local capture ledger and optional star note. Stdlib only.

The ledger is per operator, never in a target repository: `~/.config/github-showcase-skill/state.json`
(`$XDG_CONFIG_HOME` when set), `%APPDATA%\\github-showcase-skill\\state.json` on Windows, or
`$SHOWCASE_STATE_DIR/state.json`. It holds only `{completed_runs, fresh_runs, star: {status, checked_at, asked_at,
asked_at_run, declined}}`: no target names, no repository data, and nothing is ever sent anywhere.

What counts: a verified local output capture from `provenance stamp`, including an unchanged capture (`fresh_runs`
counts those separately). Pending writer jobs and incomplete captures never count. This is no claim of live
publication or whole-showcase completion. No other command counts. Nothing is counted in CI.

The nudge: from `completed_runs >= STAR_THRESHOLD`, one read-only `gh api user/starred/OWNER/REPO` GET (204 starred,
404 not starred; any other outcome is unknown and stays silent). Starred is recorded and never asked again. Not
starred prints one line on stderr at the end of the run with the link and the `gh repo star` command for the operator
to run; it is asked again at most once every STAR_REASK further runs, and never again after `provenance star
--decline`. The skill never stars on anyone's behalf: it never runs `gh repo star` and never sends `PUT /user/starred`.
Silent in CI (`CI`, `GITHUB_ACTIONS`), with `--format json`, `--quiet`, without a TTY on stderr, with
`--no-star-prompt` or `SHOWCASE_NO_STAR_PROMPT=1`. No environment variable overrides the TTY requirement.
Offline runs never check star status or print the star line.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STAR_THRESHOLD = 5      # verified local captures before the first ask
STAR_REASK = 5          # further verified captures between asks while not starred and not declined
STATE_FILE = "state.json"
APP = "github-showcase-skill"
COUNTED = ("provenance stamp",)   # only verified local captures from this command count


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def state_dir(env=None, platform: str | None = None) -> Path:
    env = os.environ if env is None else env
    platform = platform or sys.platform
    if env.get("SHOWCASE_STATE_DIR"):
        return Path(env["SHOWCASE_STATE_DIR"])
    if platform == "win32" and env.get("APPDATA"):
        return Path(env["APPDATA"]) / APP
    base = Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else Path.home() / ".config"
    return base / APP


def empty() -> dict:
    return {"completed_runs": 0, "fresh_runs": 0,
            "star": {"status": "unknown", "checked_at": None, "asked_at": None, "asked_at_run": None, "declined": False}}


def load(directory: Path | None = None) -> dict:
    p = (directory or state_dir()) / STATE_FILE
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty()
    out = empty()
    if isinstance(data, dict):
        for k in ("completed_runs", "fresh_runs"):
            if isinstance(data.get(k), int) and data[k] >= 0:
                out[k] = data[k]
        star = data.get("star") if isinstance(data.get("star"), dict) else {}
        if star.get("status") in ("unknown", "starred", "not-starred"):
            out["star"]["status"] = star["status"]
        for k in ("checked_at", "asked_at"):
            if isinstance(star.get(k), str):
                out["star"][k] = star[k]
        if isinstance(star.get("asked_at_run"), int):
            out["star"]["asked_at_run"] = star["asked_at_run"]
        out["star"]["declined"] = star.get("declined") is True
    return out


def save(state: dict, directory: Path | None = None) -> Path:
    d = directory or state_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / STATE_FILE
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def in_ci(env=None) -> bool:
    env = os.environ if env is None else env
    return any((env.get(k) or "").strip().lower() not in ("", "0", "false") for k in ("CI", "GITHUB_ACTIONS"))


def prompt_allowed(*, fmt: str | None, quiet: bool = False, no_prompt: bool = False, offline: bool = False,
                   env=None, isatty=None) -> bool:
    env = os.environ if env is None else env
    if offline or in_ci(env) or fmt == "json" or quiet or no_prompt or env.get("SHOWCASE_NO_STAR_PROMPT", "") not in ("", "0"):
        return False
    tty = isatty if isatty is not None else getattr(sys.stderr, "isatty", lambda: False)
    try:
        return bool(tty())
    except (OSError, ValueError):
        return False


def gh_starred(repo: str, run=subprocess.run) -> str:
    """'starred' | 'not-starred' | 'unknown', from one read-only GET. `gh` exits non-zero on a 404 too, so the 404 is
    told apart from every other failure by its status line; missing gh, no auth, offline or a 5xx are 'unknown'."""
    try:
        p = run(["gh", "api", "-X", "GET", "-i", f"user/starred/{repo}"], capture_output=True, text=True,
                encoding="utf-8", timeout=20)
    except (OSError, subprocess.SubprocessError, ValueError):
        return "unknown"
    out = f"{p.stdout or ''}\n{p.stderr or ''}"
    first = (p.stdout or "").lstrip().splitlines()[0] if (p.stdout or "").strip() else ""
    if p.returncode == 0 and " 204" in first:
        return "starred"
    if " 404" in first or "(HTTP 404)" in out:
        return "not-starred"
    return "unknown"


def star_line(brand) -> str | None:
    from .footer import attribution
    a = attribution(brand)
    if not a:
        return None
    return (f"{a['skill']}: {STAR_THRESHOLD}+ local showcase captures recorded. If it helped, a star helps others find it: "
            f"{a['skill_url']} (or run: gh repo star {a['skill_repo']}). "
            f"To stop this note: showcase.py provenance star --decline")


def should_ask(state: dict) -> bool:
    star, runs = state["star"], state["completed_runs"]
    if star["declined"] or star["status"] == "starred" or runs < STAR_THRESHOLD:
        return False
    last = star.get("asked_at_run")
    return last is None or runs - last >= STAR_REASK


def record_run(brand, *, fresh: bool, fmt: str | None, quiet: bool = False, no_prompt: bool = False, env=None,
               isatty=None, run=subprocess.run, directory: Path | None = None, stream=None, offline: bool = False,
               completed: bool = True) -> dict:
    """Count one verified local capture and, when allowed, print the star line. Pending jobs never count, and
    offline mode never checks star status. An unwritable state directory is skipped."""
    env = os.environ if env is None else env
    out = {"counted": False, "asked": False, "star": None}
    if in_ci(env) or not completed:
        return out
    try:
        directory = directory or state_dir(env)
        state = load(directory)
        state["completed_runs"] += 1
        if fresh:
            state["fresh_runs"] += 1
        out["counted"] = True
        star = state["star"]
        if should_ask(state) and prompt_allowed(fmt=fmt, quiet=quiet, no_prompt=no_prompt, offline=offline,
                                              env=env, isatty=isatty):
            from .footer import attribution
            a = attribution(brand)
            status = gh_starred(a["skill_repo"], run=run) if a else "unknown"
            star["checked_at"] = now_iso()
            star["status"] = status
            if status == "not-starred":
                line = star_line(brand)
                if line:
                    print(line, file=stream or sys.stderr)
                    star["asked_at"], star["asked_at_run"] = now_iso(), state["completed_runs"]
                    out["asked"] = True
            # unknown: silent, and never recorded as "not starred"
        out["star"] = star["status"]
        save(state, directory)
    except OSError:
        pass
    return out


def decline(directory: Path | None = None) -> dict:
    state = load(directory)
    state["star"]["declined"] = True
    save(state, directory)
    return state
