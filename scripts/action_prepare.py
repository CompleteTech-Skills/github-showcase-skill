#!/usr/bin/env python3
"""Helpers for the composite Action (action.yml). Standard library only; acts on the current checkout.

  action_prepare.py foreign OWNER/REPO   print "true" when docs/images/.showcase.json provably came from another
                                         repository (a template's sidecar, or another recorded repository id;
                                         $GITHUB_REPOSITORY_ID), and then remove the copied icon (assets/icon.png
                                         whose sha256 is the one that sidecar recorded). A sidecar that only names
                                         another slug (a rename or transfer) prints "false" and keeps every file.
  action_prepare.py drop NAME            remove docs/images/NAME and its sidecar record (the sidecar too when empty)
  action_prepare.py summary META_JSON    append the describe and topics proposals to $GITHUB_STEP_SUMMARY
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

IMAGES = Path("docs/images")
SIDECAR = IMAGES / ".showcase.json"
TEMPLATE_REPO = "CompleteTech-LLC/completetech-repo-template"  # intake.TEMPLATE_REPO, the `new --template` default


def _sidecar() -> dict:
    try:
        return json.loads(SIDECAR.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _recorded_ids(data: dict) -> set[str]:
    """Repository ids the sidecar's output records carry (showcase.py writes `repository_id` from `meta --from-gh`)."""
    outs = data.get("outputs") if isinstance(data.get("outputs"), dict) else {}
    return {str(r["repository_id"]) for r in outs.values() if isinstance(r, dict) and r.get("repository_id") is not None}


def foreign(full_name: str) -> bool:
    """True only when the art provably came from another repository; then a copied icon is removed (decision 12).

    Proof is a template's sidecar (its recorded type is `template`, or it names the template repository) or a recorded
    repository id other than $GITHUB_REPOSITORY_ID. A sidecar that only names another slug is this repository's own
    art after a rename, a transfer or an org rename (the slug is not an identity): nothing is removed and the
    fingerprint, which changed with the slug, regenerates it. A template repository is never foreign to itself."""
    data = _sidecar()
    inp = data.get("inputs") or {}
    if not inp or os.environ.get("SHOWCASE_IS_TEMPLATE") == "true":
        return False
    named = f"{inp.get('owner')}/{inp.get('repo')}"
    ids, rid = _recorded_ids(data), (os.environ.get("GITHUB_REPOSITORY_ID") or "").strip()
    if rid and ids and ids == {rid}:
        return False  # the same repository under another name
    if named.lower() == full_name.lower():
        return False
    template = inp.get("type") == "template" or named.lower() == TEMPLATE_REPO.lower()
    other_id = bool(rid and ids and rid not in ids)
    icon = Path("assets/icon.png")
    copied = icon.is_file() and inp.get("icon_sha256") and \
        hashlib.sha256(icon.read_bytes()).hexdigest() == inp["icon_sha256"]
    if not (template or other_id):
        print(f"::notice title=CompleteTech Showcase::docs/images/.showcase.json names {named}, not {full_name} (a rename "
              "or transfer?); kept the art" + (" and assets/icon.png" if copied else "") + ", which regenerate under "
              "this name", file=sys.stderr)
        return False
    if copied:
        icon.unlink()  # another repository's icon must never stand for this one (decision 12)
        print(f"::notice title=CompleteTech Showcase::removed the icon copied from {named}", file=sys.stderr)
    return True


def drop(name: str) -> None:
    p = IMAGES / name
    if p.is_file():
        p.unlink()
    data = _sidecar()
    if not data:
        return
    outs = dict(data.get("outputs") or {})
    outs.pop(name, None)
    if outs:
        data["outputs"] = outs
        SIDECAR.write_text(json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        SIDECAR.unlink()


def summary(meta: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    script = Path(__file__).resolve().parent / "showcase.py"
    lines = ["## CompleteTech Showcase: proposals", "",
             "The Action never edits the About box. Apply these by hand (or through the estate orchestrator).", ""]
    for cmd in ("describe", "topics"):
        p = subprocess.run([sys.executable, str(script), "--meta", meta, "--repo-dir", ".", cmd, "--gh"] if cmd == "topics"
                           else [sys.executable, str(script), "--meta", meta, "--repo-dir", ".", cmd],
                           capture_output=True, text=True)
        try:
            r = json.loads(p.stdout)
        except ValueError:
            lines += [f"- `{cmd}`: no result ({p.stderr.strip()[:200]})"]
            continue
        if cmd == "describe":
            if r.get("action") == "keep":
                lines.append("- **Description:** passes the standard.")
            elif r.get("action") == "edit":
                lines.append(f"- **Description:** suggested edit: `{r.get('proposed') or r.get('text')}`")
            else:
                tpl = r.get("template") or ""
                lines.append("- **Description:** needs a new sentence" + (f" (template: `{tpl}`)" if tpl else "") + ".")
        else:
            if r.get("result") == "pass":
                lines.append("- **Topics:** match the standard.")
            else:
                lines.append(f"- **Topics:** proposed `{' '.join(r.get('proposed') or [])}`")
                if r.get("gh"):
                    lines += ["", "```bash", r["gh"], "```"]
    text = "\n".join(lines) + "\n"
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("foreign", "drop", "summary"):
        sys.exit(__doc__)
    if sys.argv[1] == "foreign":
        print("true" if foreign(sys.argv[2]) else "false")
    elif sys.argv[1] == "drop":
        drop(sys.argv[2])
    else:
        summary(sys.argv[2])
