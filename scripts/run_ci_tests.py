"""Run the complete pytest inventory in disjoint file batches, two at a time.

Each child uses ordinary pytest and writes its completion receipt only after
pytest.main returns, including final status and cleanup. A successful process
exit alone is insufficient: collection and completed node IDs must also match.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


class Inventory:
    def __init__(self):
        self.collected = []
        self.finished = []
        self.stats = {}

    def pytest_collection_finish(self, session):
        self.collected = [
            {"nodeid": item.nodeid, "file": item.path.relative_to(ROOT).as_posix()}
            for item in session.items
        ]

    def pytest_runtest_logfinish(self, nodeid, location):
        self.finished.append(nodeid)

    def pytest_terminal_summary(self, terminalreporter):
        self.stats = {key: len(value) for key, value in terminalreporter.stats.items()}


def child(report, files, collect_only):
    import pytest

    inventory = Inventory()
    # Pytest stages cache directories beside its cache target. Keep those
    # directories outside collected source and separate for every invocation,
    # so a finishing worker cannot remove a directory another worker is scanning.
    with tempfile.TemporaryDirectory(prefix="showcase-pytest-cache-") as cache_root:
        if Path(cache_root).resolve().is_relative_to(ROOT):
            raise ValueError("pytest cache must be outside collected source; select an external temporary directory")
        arguments = ["-q", "-o", f"cache_dir={Path(cache_root) / 'cache'}",
                     *(["--collect-only"] if collect_only else []), *files]
        code = int(pytest.main(arguments, plugins=[inventory]))
    # Deliberately after pytest.main: early os._exit(0), cleanup exceptions and
    # interrupted runs cannot leave a completed receipt for the parent to accept.
    with report.open("x", encoding="utf-8") as stream:
        json.dump({"exit_code": code, "collected": inventory.collected,
                   "finished": inventory.finished, "stats": inventory.stats}, stream)
    return code


def invoke(report, files, *, collect_only=False):
    command = [sys.executable, str(Path(__file__).resolve()), "--child-report", str(report)]
    if collect_only:
        command.append("--collect-only")
    command.extend(files)
    log = report.with_suffix(".log")
    with log.open("x", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT, check=False)
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    return {"process_exit": result.returncode, "report": data, "log": str(log)}


def inventory_of(result):
    data = result["report"]
    if result["process_exit"] != 0 or not isinstance(data, dict) or data.get("exit_code") != 0:
        raise ValueError("pytest failed or did not return a successful completion receipt")
    stats = data.get("stats")
    if not isinstance(stats, dict) or any(not isinstance(count, int) or count < 0 for count in stats.values()):
        raise ValueError("malformed pytest outcome counts")
    if stats.get("failed") or stats.get("error") or stats.get("subtests failed"):
        raise ValueError("pytest recorded failing tests or errors")
    collected, finished = data.get("collected"), data.get("finished")
    if not isinstance(collected, list) or not isinstance(finished, list):
        raise ValueError("malformed pytest inventory")
    if any(not isinstance(item, dict) or not isinstance(item.get("nodeid"), str)
           or not isinstance(item.get("file"), str) for item in collected):
        raise ValueError("malformed collected node")
    if any(not isinstance(node, str) for node in finished):
        raise ValueError("malformed completed node")
    ids = [item["nodeid"] for item in collected]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("empty or duplicate pytest inventory")
    return data


def run(report_dir):
    collection = invoke(report_dir / "collection.json", [], collect_only=True)
    try:
        inventory = inventory_of(collection)["collected"]
    except ValueError:
        print(Path(collection["log"]).read_text(encoding="utf-8", errors="replace"), flush=True)
        raise
    by_file = {}
    for item in inventory:
        by_file.setdefault(item["file"], []).append(item["nodeid"])
    # Whole files stay together. Small disjoint batches keep the two ordinary
    # pytest processes occupied without relying on a worker-status protocol.
    groups = [[] for _ in range(min(16, len(by_file)))]
    weights = [0] * len(groups)
    for file in sorted(by_file, key=lambda path: (-len(by_file[path]), path)):
        group = min(range(len(groups)), key=lambda index: (weights[index], index))
        groups[group].append(file)
        weights[group] += len(by_file[file])
    print(json.dumps({"collected": len(inventory), "files": len(by_file),
                      "batches": len(groups), "workers": 2}), flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(invoke, report_dir / f"batch-{index:02d}.json", files): (index, files)
                   for index, files in enumerate(groups)}
        for future in as_completed(pending):
            index, files = pending[future]
            result = future.result()
            expected = Counter(node for file in files for node in by_file[file])
            stats = {}
            try:
                data = inventory_of(result)
                stats = data.get("stats", {})
                if Counter(item["nodeid"] for item in data["collected"]) != expected:
                    raise ValueError("batch collection differs from the complete inventory")
                if Counter(data["finished"]) != expected:
                    raise ValueError("batch did not complete every assigned test exactly once")
                error = None
            except ValueError as exc:
                error = str(exc)
            record = {"batch": index, "files": files, "expected": len(expected),
                      "process_exit": result["process_exit"], "error": error,
                      "stats": stats}
            results.append(record)
            print(f"\n--- pytest batch {index + 1}/{len(groups)} ---", flush=True)
            print(Path(result["log"]).read_text(encoding="utf-8", errors="replace"), end="", flush=True)
            print(json.dumps(record), flush=True)
    summary = {"collected": len(inventory), "files": len(by_file), "results": results}
    with (report_dir / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    success = len(results) == len(groups) and all(result["error"] is None for result in results)
    print(f"CI inventory: {len(inventory)} tests; "
          + ("all batches completed exactly once" if success else "FAILED or incomplete"), flush=True)
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--child-report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--collect-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("files", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child_report:
        return child(args.child_report, args.files, args.collect_only)
    if args.files or args.collect_only:
        parser.error("the parent runner always selects the complete suite")
    if args.report_dir:
        args.report_dir.mkdir(parents=True, exist_ok=False)
        report_dir = args.report_dir.resolve()
    else:
        report_dir = Path(tempfile.mkdtemp(prefix="showcase-ci-tests-"))
    try:
        return run(report_dir)
    except (OSError, ValueError) as exc:
        print(f"CI inventory FAILED: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
