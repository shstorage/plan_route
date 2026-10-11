"""Independent discretization, held-out scenes and non-pseudoreplicated statistics."""

import json
from collections import defaultdict
from pathlib import Path

import pytest

from plan_route.models.benchmark import BenchmarkConfig, BenchmarkRun, ReferenceGraph
from plan_route.models.results import RouteStatus
from plan_route.services.benchmark import evaluate
from plan_route.services.benchmark_reference import reference_cost
from plan_route.services.benchmark_scenes import (
    FAMILIES,
    analytic_witness_clear,
    comparison_cases,
)
from plan_route.services.benchmark_statistics import analyse, cluster_interval
from plan_route.services.routing import route_project


def small_config(**updates):
    return BenchmarkConfig(
        suite="comparison",
        scene_seeds=[11],
        evaluation_seeds=[211],
        bootstrap_resamples=100,
        **updates,
    )


def test_fixed_physical_scenes_and_disjoint_evaluation_seeds():
    config = BenchmarkConfig.model_validate_json(
        Path("benchmarks/comparison.json").read_text(encoding="utf-8")
    )
    cases = comparison_cases(config)
    groups = defaultdict(list)
    for case in cases:
        if case.split != "diagnostic":
            groups[case.scene_id].append(case)
    assert len(groups) == 49
    assert len({case.scene_id for case in cases if case.split == "development"}) == 35
    assert len({case.scene_id for case in cases if case.split == "evaluation"}) == 14
    assert len({case.case_id for case in cases}) == 100
    for pair in groups.values():
        assert len(pair) == 2
        a, b = [case.project.model_dump() for case in pair]
        a.pop("routing_config")
        b.pop("routing_config")
        assert a == b
    sparse = [
        case
        for case in cases
        if case.family == "sparse"
        and case.project.routing_config.grid_resolution_m == 1
    ]
    assert (
        len(
            {
                json.dumps(
                    case.project.model_dump(mode="json")["obstacles"], sort_keys=True
                )
                for case in sparse
            }
        )
        == 7
    )
    assert cases == comparison_cases(config)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("resolution", [1.0, 0.5])
def test_scene_truth_and_independent_discretization_match_route(family, resolution):
    case = next(
        case
        for case in comparison_cases(small_config())
        if case.family == family
        and case.seed == 11
        and case.project.routing_config.grid_resolution_m == resolution
    )
    assert not case.witness_m or analytic_witness_clear(case.project, case.witness_m)
    reference = reference_cost(case.reference_graph, 600)
    report = route_project(case.project, case.pipe_id)
    evaluation, _ = evaluate(case, report, reference)
    assert evaluation.passed, evaluation.errors
    if family == "narrow_gate":
        assert case.feasibility_label == "WITNESS"
        assert report.status == ("NO_PATH" if resolution == 1 else "SUCCESS")
    if reference.status == "NOT_COMPUTED":
        assert evaluation.cost_matches_reference is None


def test_diagnostic_heuristic_and_invalid_route_stay_outside_exact_claim():
    cases = [
        case for case in comparison_cases(small_config()) if case.split == "diagnostic"
    ]
    for case in cases:
        reference = reference_cost(case.reference_graph, 600)
        for algorithm in ("astar", "dijkstra"):
            report = route_project(case.project, case.pipe_id, algorithm=algorithm)
            evaluation, _ = evaluate(case, report, reference)
            assert evaluation.passed, evaluation.errors
            assert report.optimality_guarantee == "NONE"
            assert evaluation.cost_matches_reference is None


def test_cluster_bootstrap_keeps_seed_blocks_and_single_cluster_has_no_ci():
    values = {1: [1.0, 3.0], 2: [5.0, 7.0]}
    result = cluster_interval(values, 1000, 42)
    assert result["mean"] == 4
    assert result["n_scenes"] == 4 and result["n_seed_clusters"] == 2
    assert result["ci_low"] == 2 and result["ci_high"] == 6
    assert result == cluster_interval(values, 1000, 42)
    assert cluster_interval({1: [1, 2, 3]}, 100, 42)["ci_low"] is None


def test_reference_scales_edges_adds_connectors_and_preserves_disconnect_proof():
    graph = ReferenceGraph(
        cells=[(1, 1, 1), (2, 1, 1), (3, 1, 1)],
        start=(1, 1, 1),
        goal=(3, 1, 1),
        departure=0,
        arrival=0,
        edge_length_m=0.5,
        length_weight=2,
        connector_cost=0.75,
    )
    assert reference_cost(graph).objective_cost == 2.75
    skipped = reference_cost(graph, max_cells=1)
    assert skipped.status == "NOT_COMPUTED" and skipped.objective_cost is None
    disconnected = graph.model_copy(update={"cells": [(1, 1, 1), (3, 1, 1)]})
    assert reference_cost(disconnected, max_cells=1).status == "NO_PATH"


def test_comparison_config_rejects_overlap_duplicates_empty_and_excessive_runs():
    for kwargs in (
        {"evaluation_seeds": [11]},
        {"scene_seeds": []},
        {"resolutions_m": [1, 1]},
        {"scene_seeds": [-1]},
        {"algorithms": ["astar"]},
        {"repeats": 100, "scene_seeds": list(range(50)), "evaluation_seeds": [200]},
    ):
        with pytest.raises(ValueError):
            config = {
                "suite": "comparison",
                "scene_seeds": [11],
                "evaluation_seeds": [211],
                **kwargs,
            }
            BenchmarkConfig.model_validate(config)


def test_repeated_measurements_are_collapsed_and_diagnostics_are_excluded():
    config = small_config(resolutions_m=[1.0])
    cases = comparison_cases(config)
    case = next(case for case in cases if case.family == "sparse" and case.seed == 11)
    reports = {
        algorithm: route_project(case.project, case.pipe_id, algorithm=algorithm)
        for algorithm in ("astar", "dijkstra")
    }
    runs = []
    reference = reference_cost(case.reference_graph)
    for algorithm, report in reports.items():
        for repeat, time in enumerate([1.0, 3.0, 100.0], 1):
            timings = report.timings.model_copy(update={"total_ms": time})
            recorded = report.model_copy(update={"timings": timings})
            evaluation, _ = evaluate(case, recorded, reference)
            runs.append(
                BenchmarkRun(
                    run_id=f"{algorithm}-{repeat}",
                    batch_id="test",
                    case_id=case.case_id,
                    repeat=repeat,
                    algorithm=algorithm,
                    started_at="test",
                    completed_at="test",
                    input_sha256="test",
                    report=recorded,
                    reference=reference,
                    evaluation=evaluation,
                    oracle_ms=0,
                )
            )
    stats, rows = analyse([case], runs, config)
    assert all(row["median_total_ms"] == 3 for row in rows)
    pair = stats["paired_exact_comparisons"][0]
    assert pair["n_scenes"] == 1 and pair["n_seed_clusters"] == 1
    assert pair["mean"] == 0 and pair["ci_low"] is None
    duplicate = [
        *runs,
        *[run.model_copy(update={"run_id": f"extra-{run.run_id}"}) for run in runs],
    ]
    doubled, _ = analyse([case], duplicate, config)
    assert doubled["paired_exact_comparisons"] == stats["paired_exact_comparisons"]
    altered = runs[0].model_copy(
        update={
            "report": runs[0].report.model_copy(
                update={"status": RouteStatus.INVALID_ROUTE}
            )
        }
    )
    changed, _ = analyse([case], [altered, *runs[1:]], config)
    assert any("nondeterministic" in error for error in changed["failures"])


def test_comparison_runner_exports_schedule_statistics_and_real_figures(
    tmp_path, monkeypatch
):
    from plan_route.services import benchmark

    monkeypatch.setattr(benchmark, "_environment", lambda batch: {"test": True})
    config = small_config(resolutions_m=[1.0], repeats=1)
    batch = benchmark.run_benchmark(config, tmp_path)
    summary = json.loads((batch / "summary.json").read_text(encoding="utf-8"))
    assert summary["run_count"] == 32 and summary["passed_runs"] == 32
    assert not summary["analysis"]["failures"]
    assert summary["analysis"]["physical_scene_count"] == 14
    assert summary["analysis"]["validator_trials"]["false_valid"] == 0
    plan = json.loads((batch / "execution_plan.json").read_text(encoding="utf-8"))
    assert [row["execution_index"] for row in plan] == list(range(32))
    assert (
        len({(row["case_id"], row["repeat"], row["algorithm"]) for row in plan}) == 32
    )
    sorted_plan = sorted(
        plan, key=lambda row: (row["case_id"], row["repeat"], row["algorithm"])
    )
    assert plan != sorted_plan
    stats = json.loads(
        (batch / "comparison_statistics.json").read_text(encoding="utf-8")
    )
    assert stats["oracle_coverage"]["NOT_COMPUTED"] == 2
    assert all(
        pair["max_absolute_objective_gap"] == 0
        for pair in stats["paired_exact_comparisons"]
    )
    assert (batch / "scene_metrics.csv").is_file() and (
        batch / "comparison_report.md"
    ).is_file()
    figures = list((batch / "figures").iterdir())
    assert len(figures) == 6
    for file in figures:
        payload = file.read_bytes()
        assert (
            payload.startswith(b"%PDF")
            if file.suffix == ".pdf"
            else payload.startswith(b"\x89PNG")
        )
