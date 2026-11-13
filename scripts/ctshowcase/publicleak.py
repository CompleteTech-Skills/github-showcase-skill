"""Registry-free, local denylist checks that never return matched private text."""
from __future__ import annotations

from pathlib import Path

from .errors import NeedsInput, ShowcaseError


def check_files(files: list[str], denylist: str | Path) -> list[dict]:
    """Check UTF-8 files against one literal, case-insensitive entry per nonblank line.

    The denylist is read only. Neither entries nor matched source lines leave this
    function. File names are redacted too when they contain an entry.
    """
    try:
        entries = {line.strip().casefold() for line in Path(denylist).read_text(encoding="utf-8-sig").splitlines()
                   if line.strip()}
    except (OSError, UnicodeError) as exc:
        raise ShowcaseError("cannot read denylist as UTF-8", log="usage") from exc
    if not entries:
        raise NeedsInput("denylist", "denylist contains no entries; no privacy check was performed")
    out = []
    for file in files:
        path = Path(file)
        display = "[redacted path]" if any(entry in str(path).casefold() for entry in entries) else str(path)
        result = {"file": display, "result": "fail", "hits": [], "logs": ["privacy:denylist-only"]}
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            result["fails"] = ["cannot read input as UTF-8"]
        else:
            result["hits"] = [{"line": number} for number, line in enumerate(source.splitlines(), 1)
                              if any(entry in line.casefold() for entry in entries)]
            result["result"] = "fail" if result["hits"] else "pass"
        out.append(result)
    return out
