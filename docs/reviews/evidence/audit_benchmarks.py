"""Read preserved P10 batches and emit the evidence used by the thesis review.

Run from the repository root; this does not execute the solver or modify batches.
Assertions check archive hashes and CSV/summary agreement, not solver correctness.
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
BATCHES = {
    "P10B": "20261011T135415Z-0ee8d964e0764083be8e249dd079c18a",
    "P10C": "20261012T080959Z-d110cef3f05242e7b9a7acc6fdcda1bf",
}
CORE = (
    "src/plan_route/services/astar.py",
    "src/plan_route/services/compiler.py",
    "src/plan_route/services/geometry.py",
    "src/plan_route/services/path_validator.py",
    "src/plan_route/services/routing.py",
    "uv.lock",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit(phase: str, batch_id: str) -> dict:
    batch = ROOT / "data/benchmarks" / batch_id
    summary = read_json(batch / "summary.json")
    environment = read_json(batch / "environment.json")
    with (batch / "runs.csv").open(encoding="utf-8-sig", newline="") as stream:
        runs = list(csv.DictReader(stream))
    assert summary["batch_id"] == batch_id
    assert summary["state"] == "COMPLETE"
    assert len(runs) == summary["run_count"]
    assert len({run["run_id"] for run in runs}) == len(runs)
    assert all(run["batch_id"] == batch_id for run in runs)
    assert sum(run["passed"] == "True" for run in runs) == summary["passed_runs"]
    for field, summary_field in (
        ("status", "status_counts"), ("search_mode", "search_mode_counts")
    ):
        counts = Counter(run[field] for run in runs)
        assert counts == {
            key: value for key, value in summary[summary_field].items() if value
        }
    assert not summary["failed_runs"]
    assert not summary["probe_failures"]
    assert not summary["analysis"]["failures"]
    with ZipFile(batch / "source.zip") as archive:
        manifest = environment["source_manifest"]
        assert all(
            digest(archive.read(item["path"])) == item["sha256"]
            for item in manifest
        )
        # A missing core file must fail instead of silently shrinking the audit.
        current_core_matches = {
            path: digest((ROOT / path).read_bytes()) == digest(archive.read(path))
            for path in CORE
        }
    stats_file = (
        "comparison_statistics.json" if phase == "P10B" else "change_statistics.json"
    )
    stats = read_json(batch / stats_file)
    assert not stats["failures"]
    selected = (
        (
            "physical_scene_count", "diagnostic_case_count", "oracle_coverage",
            "validator_trials", "success_rates", "paired_exact_comparisons",
        )
        if phase == "P10B"
        else (
            "physical_scene_count", "comparison_count", "exact_success_pairs",
            "status_transitions", "applied_trace", "counterfactual_trace",
        )
    )
    result = {
        "batch_id": batch_id,
        "git_commit_at_execution": environment["git_commit"],
        "git_dirty_at_execution": environment["git_dirty"],
        "archive_manifest_files_verified": len(manifest),
        "current_core_matches_archive": current_core_matches,
        "case_count": summary["case_count"],
        "run_count": len(runs),
        "passed_runs": summary["passed_runs"],
        "status_counts": summary["status_counts"],
        "search_mode_counts": summary["search_mode_counts"],
        "artifact_sha256": {
            name: digest((batch / name).read_bytes())
            for name in ("summary.json", "environment.json", "source.zip",
                         "runs.csv", stats_file)
        },
        "statistics": {key: stats[key] for key in selected},
    }
    if phase == "P10C":
        result["statistics"]["evaluation_astar_objective_deltas"] = [
            row for row in stats["objective_delta_statistics"]
            if row["split"] == "evaluation" and row["algorithm"] == "astar"
        ]
    return result


if __name__ == "__main__":
    print(json.dumps({
        "scope": "Preserved batch audit; no new benchmark execution",
        "batches": {phase: audit(phase, batch) for phase, batch in BATCHES.items()},
    }, ensure_ascii=False, indent=2))
