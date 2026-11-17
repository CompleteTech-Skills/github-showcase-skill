#!/usr/bin/env python3
"""Helpers for the composite Action (action.yml). Standard library only; acts on the current checkout.

  action_prepare.py foreign OWNER/REPO   print "true" when docs/images/.showcase.json provably came from another
                                         repository (a template's sidecar, or another recorded repository id;
                                         $GITHUB_REPOSITORY_ID), and then remove the copied icon (assets/icon.png
                                         whose sha256 is the one that sidecar recorded). A sidecar that only names
                                         another slug (a rename or transfer) prints "false" and keeps every file.
  action_prepare.py foreign OWNER/REPO NAME  check a canonical banner or card without removing the icon
  action_prepare.py staged             report whether local output still carries a staged proposal
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

# Keep direct and runpy entry points equivalent when the caller's CWD is a target checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctshowcase.fingerprint import ART_NAMES, output_records, read_sidecar, replace_bytes, sidecar_lock  # noqa: E402

IMAGES = Path("docs/images")
SIDECAR = IMAGES / ".showcase.json"
TEMPLATE_REPO = "CompleteTech-LLC/completetech-repo-template"  # intake.TEMPLATE_REPO, the `new --template` default


def _sidecar() -> dict:
    return read_sidecar(IMAGES)


def _recorded_ids(data: dict) -> set[str]:
    """Repository IDs attached to the canonical banner and card artifacts."""
    return {str(record["repository_id"]) for name, record in output_records(data).items()
            if name in ART_NAMES and isinstance(record, dict) and not record.get("exempt")
            and record.get("repository_id") is not None}


def foreign(full_name: str, artifact: str | None = None) -> bool:
    """True only when the art provably came from another repository; then a copied icon is removed (decision 12).

    Proof is a template's sidecar (its recorded type is `template`, or it names the template repository) or a recorded
    repository id other than $GITHUB_REPOSITORY_ID. A sidecar that only names another slug is this repository's own
    art after a rename, a transfer or an org rename (the slug is not an identity): nothing is removed and the
    fingerprint, which changed with the slug, regenerates it. A template repository is never foreign to itself."""
    data = _sidecar()
    if os.environ.get("SHOWCASE_IS_TEMPLATE") == "true":
        return False
    rid = (os.environ.get("GITHUB_REPOSITORY_ID") or "").strip()
    if artifact is not None:
        record = output_records(data).get(artifact)
        if rid and isinstance(record, dict) and not record.get("exempt"):
            artifact_id = record.get("repository_id")
            if artifact_id is not None:
                return str(artifact_id) != rid

    inp = data.get("inputs") or {}
    if not isinstance(inp, dict) or not inp:
        return False
    named = f"{inp.get('owner')}/{inp.get('repo')}"
    ids = _recorded_ids(data)
    if rid and ids and ids == {rid}:
        return False  # the same repository under another name
    if named.lower() == full_name.lower():
        return False
    template = inp.get("type") == "template" or named.lower() == TEMPLATE_REPO.lower()
    other_id = bool(rid and ids and rid not in ids)
    if artifact is not None:
        return template or other_id
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



def has_staged_outputs() -> bool:
    # The grouped commit includes nested art and the two root Markdown files.
    candidates = {SIDECAR, Path(SIDECAR.name), *IMAGES.rglob(SIDECAR.name)}
    for path in candidates:
        if not path.exists() and not path.is_symlink():
            continue
        outputs = read_sidecar(path.parent).get("outputs")
        if not isinstance(outputs, dict):
            return True  # unreadable provenance cannot authorize publication
        if any(not isinstance(record, dict) or "staged_description" in record for record in outputs.values()):
            return True
    return False


def drop(name: str) -> None:
    with sidecar_lock(SIDECAR):
        p = IMAGES / name
        if p.is_file():
            p.unlink()
        data = _sidecar()
        if not data:
            return
        outs = dict(output_records(data))
        outs.pop(name, None)
        if outs:
            data["outputs"] = outs
            replace_bytes(SIDECAR, (json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
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
                           capture_output=True, text=True, encoding="utf-8")
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
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors=sys.stdout.errors)
        sys.stdout.write(text)


if __name__ == "__main__":
    if sys.argv[1:] == ["staged"]:
        print("true" if has_staged_outputs() else "false")
        sys.exit(0)
    if not (len(sys.argv) == 3 and sys.argv[1] in ("foreign", "drop", "summary")
            or len(sys.argv) == 4 and sys.argv[1] == "foreign" and sys.argv[3] in ART_NAMES):
        sys.exit(__doc__)
    if sys.argv[1] == "foreign":
        print("true" if foreign(*sys.argv[2:]) else "false")
    elif sys.argv[1] == "drop":
        drop(sys.argv[2])
    else:
        summary(sys.argv[2])
