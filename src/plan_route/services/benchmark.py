"""Run and retain each synthetic experiment in an exclusive directory."""

import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from math import isclose
from pathlib import Path
from random import Random
from time import perf_counter
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from plan_route.models.benchmark import (
    BenchmarkCase,
    BenchmarkConfig,
    BenchmarkEvaluation,
    BenchmarkRun,
    ReferenceResult,
)
from plan_route.models.results import OptimalityGuarantee, RouteSolveReport, RouteStatus
from plan_route.services.benchmark_cases import pilot_cases
from plan_route.services.benchmark_reference import reference_cost
from plan_route.services.benchmark_scenes import comparison_cases
from plan_route.services.compiler import CompilationStatus, compile_constraints
from plan_route.services.path_validator import validate_path
from plan_route.services.routing import route_project

ROOT = Path(__file__).resolve().parents[3]


def _write_json(path: Path, value: dict | list) -> None:
    # Exclusive create protects completed runs even if IDs ever collide.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _command(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, timeout=5, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _memory_bytes() -> int | None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.DWORD),
                ("load", wintypes.DWORD),
                *[
                    (field, ctypes.c_ulonglong)
                    for field in (
                        "total_physical",
                        "available_physical",
                        "total_page",
                        "available_page",
                        "total_virtual",
                        "available_virtual",
                        "available_extended",
                    )
                ],
            ]

        state = MemoryStatus()
        state.length = ctypes.sizeof(state)
        return (
            state.total_physical
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state))
            else None
        )
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None


def _environment(batch: Path) -> dict:
    paths = sorted(
        [
            *ROOT.joinpath("src/plan_route").rglob("*.py"),
            *ROOT.joinpath("src/plan_route/fixtures").rglob("*.json"),
            *ROOT.joinpath("scripts").rglob("*.py"),
            ROOT / "pyproject.toml",
            ROOT / "uv.lock",
            ROOT / ".python-version",
            ROOT / "README.md",
            *ROOT.joinpath("benchmarks").rglob("*.json"),
            ROOT / "frontend/package.json",
            ROOT / "frontend/package-lock.json",
        ]
    )
    manifest = []
    with ZipFile(batch / "source.zip", "x", compression=ZIP_DEFLATED) as archive:
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            payload = path.read_bytes()
            manifest.append(
                {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
            )
            archive.writestr(relative, payload)
    git_status = _command(["git", "status", "--porcelain"])
    return {
        "benchmark_contract": "p10abc_benchmark_v3",
        "solver_contract": "directional_grid_p08c_v2",
        "validator_contract": "orthogonal_core_canonical_connectors_v2",
        "self_clearance_policy": "straight_runs_arc_2sqrt3_radius_v2",
        "reference_version": "explicit_graph_relaxation_v2",
        "git_commit": _command(["git", "rev-parse", "HEAD"]),
        "git_dirty": git_status != "" if git_status is not None else None,
        "git_status": git_status,
        "source_manifest": manifest,
        "source_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "python": sys.version,
        "python_implementation": platform.python_implementation(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
        "logical_cpus": os.cpu_count(),
        "ram_bytes": _memory_bytes(),
        "node": _command(["node", "--version"]),
        "uv": _command(["uv", "--version"]),
        "packages": {
            name: version(name) for name in ("plan-route", "fastapi", "pydantic")
        },
        "command": sys.argv,
    }


def evaluate(
    case: BenchmarkCase, report: RouteSolveReport, reference: ReferenceResult
) -> tuple[BenchmarkEvaluation, dict | None]:
    errors = []
    status_matches = report.status == case.expected_status
    if not status_matches:
        errors.append(f"expected {case.expected_status}, received {report.status}")
    if (
        case.expected_search_mode is not None
        and report.search_mode != case.expected_search_mode
    ):
        errors.append(
            f"expected search mode {case.expected_search_mode}, "
            f"received {report.search_mode}"
        )
    compilation = compile_constraints(case.project, case.pipe_id)
    cells_match = None
    if compilation.status is CompilationStatus.SUCCESS:
        grid = compilation.grid
        actual = grid.interior_cells - grid.obstacle_cells - grid.rule_cells
        cells_match = actual == set(case.reference_graph.cells)
        if not cells_match:
            errors.append(
                "compiled cells differ from the manually stated reference graph"
            )
    cost_matches = None
    if (
        report.status is RouteStatus.SUCCESS
        and reference.status != "NOT_COMPUTED"
        and report.optimality_guarantee
        is OptimalityGuarantee.GRID_OBJECTIVE_EXCLUDING_SELF_CLEARANCE
    ):
        cost_matches = (
            reference.status == "PATH"
            and report.cost_breakdown is not None
            and isclose(
                report.cost_breakdown.total_objective_cost,
                reference.objective_cost,
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
        )
        if not cost_matches:
            errors.append("exact-grid cost differs from independent reference")
    witness = None
    if case.witness_m:
        witness = validate_path(
            case.project, case.pipe_id, tuple(case.witness_m)
        ).model_dump(mode="json")
        if witness["status"] != "VALID":
            errors.append("analytic witness failed validator sanity check")
    if case.expected_status is RouteStatus.NO_PATH and reference.status != "NO_PATH":
        errors.append("separating-wall reference unexpectedly has a path")
    return BenchmarkEvaluation(
        passed=not errors,
        status_matches=status_matches,
        cost_matches_reference=cost_matches,
        compiled_cells_match_reference=cells_match,
        witness_validation=witness["status"] if witness else None,
        errors=errors,
    ), witness


def _probes(case: BenchmarkCase) -> list[dict]:
    start, end = (
        case.project.equipment[0].ports[0].position_m,
        case.project.equipment[1].ports[0].position_m,
    )
    candidates = []
    if case.case_id.endswith("straight"):
        middle = (end[0] - 2, end[1], end[2])
        candidates.append(
            ("adjacent_reversal", [start, end, middle, end], ["SELF_CLEARANCE"])
        )
    if case.case_id.endswith("bend"):
        candidates.append(("diagonal_core", [start, end], ["NON_ORTHOGONAL"]))
    if case.case_id.endswith("wall_detour"):
        candidates.append(("wall_crossing", [start, end], ["OBSTACLE_COLLISION"]))
    if case.case_id.endswith("keep_out"):
        candidates.append(("zone_crossing", [start, end], ["KEEP_OUT"]))
    records = []
    for name, points, expected in candidates:
        report = validate_path(case.project, case.pipe_id, tuple(points))
        codes = {item.code for item in report.violations}
        records.append(
            {
                "probe_id": name,
                "points_m": points,
                "expected_codes": expected,
                "truth_basis": (
                    "Deliberately injected analytic violation; "
                    "label is specified before validation."
                ),
                "passed": set(expected) <= codes,
                "report": report.model_dump(mode="json"),
            }
        )
    return records


CSV_FIELDS = [
    "batch_id",
    "run_id",
    "case_id",
    "repeat",
    "algorithm",
    "status",
    "search_mode",
    "optimality_guarantee",
    "initial_search_status",
    "fallback_status",
    "fallback_reason",
    "feasibility_label",
    "reference_status",
    "reference_cost",
    "objective_cost",
    "path_length_m",
    "bend_count",
    "expanded_states",
    "compile_ms",
    "search_ms",
    "validate_ms",
    "total_ms",
    "oracle_ms",
    "passed",
    "cost_matches_reference",
    "input_sha256",
    "scenario_hash",
    "scene_id",
    "split",
    "family",
    "scene_seed",
    "grid_resolution_m",
    "execution_index",
]


def run_benchmark(config: BenchmarkConfig, output: Path) -> Path:
    if len(set(config.algorithms)) != len(config.algorithms):
        raise ValueError("algorithms must not contain duplicates")
    output.mkdir(parents=True, exist_ok=True)
    batch_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex}"
    batch = output / batch_id
    batch.mkdir(exist_ok=False)
    _write_json(batch / "config.json", config.model_dump(mode="json"))
    _write_json(batch / "environment.json", _environment(batch))
    if config.suite == "changes":
        from plan_route.services.benchmark_changes import change_cases

        cases = change_cases(config)
    else:
        cases = (
            pilot_cases(config.seed)
            if config.suite == "pilot"
            else comparison_cases(config)
        )
    rows, runs, probe_failures = [], [], []
    _write_json(
        batch / "manifest.json",
        {
            "batch_id": batch_id,
            "state": "RUNNING",
            "cases": [case.case_id for case in cases],
            "planned_runs": len(cases) * config.repeats * len(config.algorithms),
        },
    )
    reference_cache = {}
    for case in cases:
        case_dir = batch / case.case_id
        case_dir.mkdir()
        _write_json(case_dir / "case.json", case.model_dump(mode="json"))
        _write_json(case_dir / "project.json", case.project.model_dump(mode="json"))
        probes = _probes(case)
        _write_json(case_dir / "validator_probes.json", probes)
        probe_failures.extend(
            f"{case.case_id}/{item['probe_id']}"
            for item in probes
            if not item["passed"]
        )
        if config.suite != "pilot":
            started = perf_counter()
            reference_cache[case.case_id] = (
                reference_cost(case.reference_graph, config.oracle_max_cells),
                (perf_counter() - started) * 1000,
            )
    jobs = [
        (case, repeat, algorithm)
        for case in cases
        for repeat in range(1, config.repeats + 1)
        for algorithm in config.algorithms
    ]
    if config.suite != "pilot":
        Random(config.seed).shuffle(jobs)
    _write_json(
        batch / "execution_plan.json",
        [
            {
                "execution_index": i,
                "case_id": case.case_id,
                "repeat": repeat,
                "algorithm": algorithm,
            }
            for i, (case, repeat, algorithm) in enumerate(jobs)
        ],
    )
    for execution_index, (case, repeat, algorithm) in enumerate(jobs):
        case_dir = batch / case.case_id
        run_id = uuid4().hex
        run_dir = case_dir / run_id
        run_dir.mkdir()
        started_at = datetime.now(timezone.utc).isoformat()
        request = {
            "project": case.project.model_dump(mode="json"),
            "pipe_id": case.pipe_id,
            "algorithm": algorithm,
            "max_expansions": case.max_expansions,
            "max_snap_distance_m": None,
        }
        canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
        input_sha = hashlib.sha256(canonical.encode()).hexdigest()
        _write_json(run_dir / "input.json", request)
        if config.suite != "pilot":
            reference, oracle_ms = reference_cache[case.case_id]
        else:
            started = perf_counter()
            reference = reference_cost(case.reference_graph)
            oracle_ms = (perf_counter() - started) * 1000
        report = route_project(
            case.project,
            case.pipe_id,
            algorithm=algorithm,
            max_expansions=case.max_expansions,
        )
        evaluation, witness = evaluate(case, report, reference)
        run = BenchmarkRun(
            run_id=run_id,
            batch_id=batch_id,
            case_id=case.case_id,
            repeat=repeat,
            algorithm=algorithm,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            input_sha256=input_sha,
            reference=reference,
            report=report,
            evaluation=evaluation,
            oracle_ms=oracle_ms,
            execution_index=execution_index,
            reference_timing_scope="run" if config.suite == "pilot" else "case",
        )
        _write_json(run_dir / "run.json", run.model_dump(mode="json"))
        if witness:
            _write_json(run_dir / "witness_validation.json", witness)
        runs.append(run)
        cost, timing = report.cost_breakdown, report.timings
        rows.append(
            dict(
                zip(
                    CSV_FIELDS,
                    [
                        batch_id,
                        run_id,
                        case.case_id,
                        repeat,
                        algorithm,
                        report.status,
                        report.search_mode,
                        report.optimality_guarantee,
                        report.initial_search_status,
                        report.fallback_status,
                        report.fallback_reason,
                        case.feasibility_label,
                        reference.status,
                        reference.objective_cost,
                        cost.total_objective_cost if cost else None,
                        cost.path_length_m if cost else None,
                        report.bend_count,
                        report.expanded_states,
                        timing.compile_ms,
                        timing.search_ms,
                        timing.validate_ms,
                        timing.total_ms,
                        oracle_ms,
                        evaluation.passed,
                        evaluation.cost_matches_reference,
                        input_sha,
                        report.scenario_hash,
                        case.scene_id,
                        case.split,
                        case.family,
                        case.seed,
                        report.grid_resolution_m,
                        execution_index,
                    ],
                )
            )
        )
    with (batch / "runs.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "batch_id": batch_id,
        "state": "COMPLETE",
        "case_count": len(cases),
        "run_count": len(runs),
        "passed_runs": sum(run.evaluation.passed for run in runs),
        "failed_runs": [run.run_id for run in runs if not run.evaluation.passed],
        "probe_failures": probe_failures,
        "status_counts": {
            status: sum(run.report.status == status for run in runs)
            for status in RouteStatus
        },
        "search_mode_counts": {
            mode: sum(run.report.search_mode == mode for run in runs)
            for mode in sorted({run.report.search_mode for run in runs})
        },
        "scope": (
            "Fixed synthetic scene comparison; repeats and resolutions "
            "are not independent scenes."
            if config.suite != "pilot"
            else "Pilot contract checks only; repeats are not independent scene "
            "samples or evidence of superiority."
        ),
    }
    if config.suite == "comparison":
        from plan_route.services.benchmark_statistics import write_comparison

        summary["analysis"] = write_comparison(batch, cases, runs, config)
    elif config.suite == "changes":
        from plan_route.services.benchmark_change_analysis import write_changes

        summary["analysis"] = write_changes(batch, cases, runs, config)
    _write_json(batch / "summary.json", summary)
    return batch
