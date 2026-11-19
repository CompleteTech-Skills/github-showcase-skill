"""Deterministic cache-placement contract for ordinary CI pytest children.

This checks the cache topology behind a native Windows collection race. It does
not reproduce the scheduling or platform behavior of that historical failure.
"""
from __future__ import annotations

import json

import pytest

from test_pytest_worker_guard import run_suite


@pytest.mark.parametrize("parallel", [False, True], ids=["serial-child", "parallel-controller"])
def test_children_keep_enabled_individual_caches_outside_collected_source(tmp_path, parallel):
    source = tmp_path / "synthetic source with spaces"
    source.mkdir()
    observations = tmp_path / "cache-observations"
    observations.mkdir()
    hook = (
        "import hashlib, json, os, uuid\n"
        "from pathlib import Path\n"
        "def pytest_sessionstart(session):\n"
        "    config = session.config\n"
        "    cache = config.cache\n"
        "    cache.set('synthetic/isolation-probe', True)\n"
        "    cache_dir = Path(config.getini('cache_dir'))\n"
        "    if not cache_dir.is_absolute():\n"
        "        cache_dir = config.rootpath / cache_dir\n"
        "    cache_dir = cache_dir.resolve()\n"
        "    record = {\n"
        "        'outside_source': not cache_dir.is_relative_to(config.rootpath.resolve()),\n"
        "        'cache_identity': hashlib.sha256(os.fsencode(cache_dir)).hexdigest(),\n"
        "        'cache_roundtrip': cache.get('synthetic/isolation-probe', False) is True,\n"
        "        'collect_only': bool(config.option.collectonly),\n"
        "    }\n"
        f"    destination = Path({str(observations)!r}) / (uuid.uuid4().hex + '.json')\n"
        "    destination.write_text(json.dumps(record), encoding='utf-8')\n"
    )
    result = run_suite(source, hook=hook, parallel=parallel)
    succeeded = result.returncode == 0
    assert succeeded, {"controller_returncode": result.returncode}

    records = [json.loads(path.read_text(encoding="utf-8")) for path in observations.glob("*.json")]
    expected_children = 3 if parallel else 1
    observed_children = len(records)
    observation_count_matches = observed_children == expected_children
    assert observation_count_matches, {"observed_children": observed_children, "expected_children": expected_children}
    enabled_caches = sum(record["cache_roundtrip"] is True for record in records)
    all_caches_enabled = enabled_caches == expected_children
    assert all_caches_enabled, {"enabled_caches": enabled_caches, "expected_children": expected_children}
    collection_children = sum(record["collect_only"] is True for record in records)
    expected_collection_children = int(parallel)
    collection_count_matches = collection_children == expected_collection_children
    assert collection_count_matches, {"collection_children": collection_children,
                                      "expected_collection_children": expected_collection_children}

    report_name = "results/collection.json" if parallel else "serial.json"
    collection = json.loads((source / report_name).read_text(encoding="utf-8"))
    collection_succeeded = collection["exit_code"] == 0
    collected_count = len(collection["collected"])
    complete_inventory = collected_count == 2
    assert collection_succeeded, {"collection_exit_code": collection["exit_code"]}
    assert complete_inventory, {"collected_count": collected_count}
    if parallel:
        summary = json.loads((source / "results" / "summary.json").read_text(encoding="utf-8"))
        batches = summary["results"]
        batch_count = len(batches)
        successful_batches = sum(batch["process_exit"] == 0 and batch["error"] is None for batch in batches)
        completed_tests = sum(batch["stats"].get("passed", 0) for batch in batches)
        batches_succeeded = batch_count == successful_batches == 2
        inventory_completed = completed_tests == 2
        assert batches_succeeded, {"batch_count": batch_count, "successful_batches": successful_batches}
        assert inventory_completed, {"completed_tests": completed_tests}
        for index in range(2):
            receipt = json.loads((source / "results" / f"batch-{index:02d}.json").read_text(encoding="utf-8"))
            collected_ids = [item["nodeid"] for item in receipt["collected"]]
            finished_ids = receipt["finished"]
            receipt_complete = len(collected_ids) == len(finished_ids) == 1 and collected_ids == finished_ids
            assert receipt_complete, {"batch": index, "collected_count": len(collected_ids),
                                      "finished_count": len(finished_ids)}
    else:
        finished_count = len(collection["finished"])
        collected_ids = [item["nodeid"] for item in collection["collected"]]
        receipt_complete = finished_count == 2 and collected_ids == collection["finished"]
        assert receipt_complete, {"finished_count": finished_count, "collected_count": collected_count}

    outside_count = sum(record["outside_source"] is True for record in records)
    all_outside_source = outside_count == expected_children
    unique_cache_count = len({record["cache_identity"] for record in records})
    all_caches_distinct = unique_cache_count == expected_children
    assert all_outside_source, {"outside_count": outside_count, "expected_children": expected_children}
    assert all_caches_distinct, {"unique_cache_count": unique_cache_count, "expected_children": expected_children}
