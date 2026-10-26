#!/usr/bin/env python3
"""Helpers for the composite Action (action.yml). Standard library only; acts on the current checkout.

  action_prepare.py foreign OWNER/REPO   print "true" when docs/images/.showcase.json was generated for another
                                         repository (files copied from the template), and remove a copied template
                                         icon (assets/icon.png whose sha256 is the one that sidecar recorded)
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


def _sidecar() -> dict:
    try:
        return json.loads(SIDECAR.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def foreign(full_name: str) -> bool:
    inp = _sidecar().get("inputs") or {}
    if not inp:
        return False
    if f"{inp.get('owner')}/{inp.get('repo')}".lower() == full_name.lower():
        return False
    icon = Path("assets/icon.png")
    if icon.is_file() and inp.get("icon_sha256") and hashlib.sha256(icon.read_bytes()).hexdigest() == inp["icon_sha256"]:
        icon.unlink()  # the template's icon must never stand for this repository (decision 12)
        print(f"::notice title=CompleteTech Showcase::removed the icon copied from {inp.get('owner')}/{inp.get('repo')}",
              file=sys.stderr)
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
