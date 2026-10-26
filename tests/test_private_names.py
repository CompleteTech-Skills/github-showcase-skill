"""Safety red team #10: the skill is published publicly, so it must not name private-only repositories of the estate.
Runs only inside the hand-off bundle (audit/inventory.tsv beside the skill); the published copy carries no list."""
import csv
import json
import re

import pytest

from conftest import ROOT

INVENTORY = ROOT.parent / "audit" / "inventory.tsv"
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".graphql", ".txt", ".toml", ".sh", ".svg", ".html"}


def _vocabulary() -> set[str]:
    """Words that are public on their own: topics, org logins and the brand domain (a private repo may share them)."""
    words: set[str] = set()

    def walk(v):
        if isinstance(v, str):
            words.add(v.lower())
        elif isinstance(v, dict):
            for k, x in v.items():
                words.add(str(k).lower())
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(json.loads((ROOT / "references" / "standard" / "standard.lock.json").read_text(encoding="utf-8"))["topics"])
    walk(list(json.loads((ROOT / "references" / "brand.lock.json").read_text(encoding="utf-8"))["orgs"]))
    words.add("complete.tech")
    return words


@pytest.mark.skipif(not INVENTORY.is_file(), reason="estate inventory not beside the skill")
def test_skill_names_no_private_only_repository():
    rows = list(csv.DictReader(INVENTORY.open(encoding="utf-8"), delimiter="\t"))
    public = {r["repo"].lower() for r in rows if r["visibility"] == "public"}
    vocab = _vocabulary()
    # distinctive names only (a separator and 8+ characters), so plain words such as `automation` do not match
    private = {r["repo"] for r in rows if r["visibility"] != "public" and r["repo"].lower() not in public
               and r["repo"].lower() not in vocab and len(r["repo"]) >= 8 and re.search(r"[-_.]", r["repo"])}
    pats = [(n, re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(n) + r"(?![A-Za-z0-9_-])", re.I)) for n in private]
    hits = []
    for base in (ROOT, ROOT.parent / "template"):
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in TEXT_SUFFIXES or {"__pycache__", ".pytest_cache"} & set(p.parts):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            hits += [f"{p.relative_to(base.parent)}: {n}" for n, rx in pats if rx.search(text)]
    assert hits == []
