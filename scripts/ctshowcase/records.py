"""§12.6 change records for the orchestrator's single writer queue. The toolkit never writes to GitHub itself."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import STANDARD


def record(owner: str, repo: str, kind: str, target: str, before, after, rule: str) -> dict:
    b = before if isinstance(before, (bytes, str)) else json.dumps(before, sort_keys=True)
    if isinstance(b, str):
        b = b.encode("utf-8")
    rec = {"std": STANDARD, "owner": owner, "repo": repo, "kind": kind, "target": target,
           "before_sha256": hashlib.sha256(b).hexdigest(), "after": after, "rule": rule}
    # Public planners return these dictionaries before append()/CLI serialization.
    # Carry only a previously gated, still-valid target grant at that common seam;
    # constructing a record does not authorize the owner or register a new grant.
    from .signoff import stamp
    stamp([rec])
    return rec


def append(path: str | Path | None, recs: list[dict]) -> None:
    """Append JSON lines (change records or scripts/writer.py jobs) to PATH, creating its directory."""
    if not path or not recs:
        return
    from .signoff import stamp
    stamp(recs)  # jobs and change records of a signed-off T3 owner carry signoff_id
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
