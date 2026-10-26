"""CompleteTech GitHub showcase toolkit (implementation package for scripts/showcase.py)."""
from pathlib import Path

__version__ = "1.0.0"
STANDARD = "ct-std-v1"
ROOT = Path(__file__).resolve().parents[2]  # the skill checkout
REFERENCES = ROOT / "references"
ASSETS = ROOT / "assets"


def estate_candidates() -> list[Path]:
    """Folders that may hold the estate hand-off bundle: the skill's parent (a `skill/` checkout inside the bundle),
    or the bundle root when this is the installed copy at `<bundle>/.claude/skills/<name>/`."""
    out = [ROOT.parent]
    if ROOT.parent.name == "skills" and ROOT.parents[1].name == ".claude":
        out.append(ROOT.parents[2])
    return out
