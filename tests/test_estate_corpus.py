"""Corpus run over the scratch metadata (all 399 JSONs). Skipped unless SHOWCASE_CORPUS_DIR is set; writes nothing
into the package (outputs go to a temp dir) and never copies private metadata."""
import json
import os
from pathlib import Path

import pytest

from conftest import run_cli

CORPUS = os.environ.get("SHOWCASE_CORPUS_DIR")


@pytest.mark.skipif(not CORPUS, reason="set SHOWCASE_CORPUS_DIR to run the estate corpus")
def test_corpus(tmp_path):
    counts = {"ok": 0, "art-fail": [], "needs-input": 0, "refused": 0, "exempt": 0}
    for f in sorted(Path(CORPUS).glob("*.json")):
        for cmd, ext in (("banner", "png"), ("card", "svg")):
            p = run_cli("--meta", f, "--no-repo-dir", "--format", "json", cmd, "--out", tmp_path / f"{f.stem}.{ext}",
                        "--allow-unmeasured", "--allow-hold")
            assert p.returncode in (0, 2, 3, 4), (f.name, cmd, p.stdout, p.stderr)
            if p.returncode == 3:
                counts["art-fail"].append(f"{cmd}:{f.stem}")
            elif p.returncode == 4:
                counts["needs-input"] += 1
            elif p.returncode == 2:
                counts["refused"] += 1
            elif json.loads(p.stdout or "{}").get("result") == "exempt":
                counts["exempt"] += 1
            else:
                counts["ok"] += 1
        for cmd in ("topics", "describe"):
            # exit 4 is needs-input:metadata (a failed capture), documented in SKILL.md
            assert run_cli("--meta", f, "--no-repo-dir", cmd).returncode in (0, 1, 2, 4), (f.name, cmd)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in counts.items()}))
    print("art-fail:", counts["art-fail"])
