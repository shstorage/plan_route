"""Analytic pilot cases, independent cost oracle and immutable run artifacts."""

import csv
import hashlib
import json
from zipfile import ZipFile

import pytest

from plan_route.models.benchmark import BenchmarkConfig, BenchmarkRun
from plan_route.models.engineering import EngineeringProject
from plan_route.services import benchmark, routing
from plan_route.services.benchmark_cases import pilot_cases
from plan_route.services.benchmark_reference import reference_cost

EXPECTED_COSTS = [4, 10, 10, 10, 18, None, 18, 10, 10, 4, 8]


@pytest.mark.parametrize("index,expected", list(enumerate(EXPECTED_COSTS)))
def test_pilot_cases_match_analytic_reference_and_both_algorithms(index, expected):
    case = pilot_cases(42)[index]
    reference = reference_cost(case.reference_graph)
    assert reference.objective_cost == expected
    for algorithm in ("astar", "dijkstra"):
        report = routing.route_project(
            case.project,
            case.pipe_id,
            algorithm=algorithm,
            max_expansions=case.max_expansions,
        )
        evaluation, _ = benchmark.evaluate(case, report, reference)
        assert evaluation.passed, evaluation.errors
        assert report.timings.total_ms >= (
            report.timings.compile_ms
            + report.timings.search_ms
            + report.timings.validate_ms
        )
        if case.case_id.endswith("budget"):
            assert reference.status == "PATH"
            assert report.status == "SEARCH_LIMIT_REACHED"
        if case.case_id.endswith("unapproved"):
            assert report.search_mode == "NOT_RUN"
            assert report.timings.validate_ms == 0
        if case.case_id.endswith("closed_wall"):
            assert case.feasibility_label == "SEPARATING_WALL"
            assert reference.status == "NO_PATH"


def test_seeded_translation_is_repeatable_and_does_not_change_reference_costs():
    first, second = pilot_cases(42), pilot_cases(7)
    assert [case.model_dump() for case in first] == [
        case.model_dump() for case in pilot_cases(42)
    ]
    assert first[0].project.building != second[0].project.building
    assert [
        reference_cost(case.reference_graph).objective_cost for case in second
    ] == EXPECTED_COSTS


@pytest.mark.parametrize("index", [0, 1, 4, 6])
def test_injected_violation_probes_have_independent_expected_codes(index):
    probes = benchmark._probes(pilot_cases(42)[index])
    assert probes and all(probe["passed"] for probe in probes)


def test_route_timings_use_separate_outer_stage_boundaries(monkeypatch):
    ticks = iter([0.0, 1.0, 3.0, 6.0, 10.0])
    monkeypatch.setattr(routing, "perf_counter", lambda: next(ticks))
    case = pilot_cases(42)[0]
    report = routing.route_project(case.project, case.pipe_id)
    assert report.timings.model_dump() == {
        "compile_ms": 1000,
        "search_ms": 2000,
        "validate_ms": 3000,
        "total_ms": 10000,
    }


def test_repeats_and_new_batches_preserve_inputs_results_environment_and_csv(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(benchmark, "_command", lambda args: "test-metadata")
    monkeypatch.setattr(benchmark, "_memory_bytes", lambda: 1024)
    config = BenchmarkConfig(repeats=2, algorithms=["astar"])
    batch = benchmark.run_benchmark(config, tmp_path)
    files = sorted(batch.glob("P10A-*/*/run.json"))
    assert len(files) == 22
    original_bytes = {file: file.read_bytes() for file in files}
    runs = [
        BenchmarkRun.model_validate_json(file.read_text(encoding="utf-8"))
        for file in files
    ]
    assert len({run.run_id for run in runs}) == 22
    assert all(run.evaluation.passed for run in runs)
    summary = json.loads((batch / "summary.json").read_text(encoding="utf-8"))
    assert summary["state"] == "COMPLETE" and summary["passed_runs"] == 22
    assert summary["status_counts"]["SEARCH_LIMIT_REACHED"] == 2
    assert summary["status_counts"]["NO_PATH"] == 2
    env = json.loads((batch / "environment.json").read_text(encoding="utf-8"))
    assert env["git_dirty"] is True
    with ZipFile(batch / "source.zip") as archive:
        for item in env["source_manifest"]:
            assert (
                hashlib.sha256(archive.read(item["path"])).hexdigest() == item["sha256"]
            )
    for file, run in zip(files, runs):
        request = json.loads(file.with_name("input.json").read_text(encoding="utf-8"))
        EngineeringProject.model_validate(request["project"])
        standalone = file.parent.parent / "project.json"
        assert json.loads(standalone.read_text(encoding="utf-8")) == request["project"]
        canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(canonical.encode()).hexdigest() == run.input_sha256
    for case_id in {run.case_id for run in runs}:
        pair = [run for run in runs if run.case_id == case_id]
        assert pair[0].input_sha256 == pair[1].input_sha256
        assert pair[0].report.points_m == pair[1].report.points_m
        assert pair[0].report.cost_breakdown == pair[1].report.cost_breakdown
    second_batch = benchmark.run_benchmark(config, tmp_path)
    assert second_batch != batch
    assert all(file.read_bytes() == payload for file, payload in original_bytes.items())
    with (batch / "runs.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 22
    by_id = {run.run_id: run for run in runs}
    for row in rows:
        run = by_id[row["run_id"]]
        assert row["status"] == run.report.status
        assert row["search_mode"] == run.report.search_mode
        assert row["input_sha256"] == run.input_sha256
        assert float(row["total_ms"]) == run.report.timings.total_ms
        assert row["objective_cost"] == (
            str(run.report.cost_breakdown.total_objective_cost)
            if run.report.cost_breakdown
            else ""
        )


def test_evaluation_does_not_hide_bad_reference_or_status():
    case = pilot_cases(42)[0]
    report = routing.route_project(case.project, case.pipe_id)
    reference = reference_cost(case.reference_graph).model_copy(
        update={"objective_cost": 999}
    )
    evaluation, _ = benchmark.evaluate(case, report, reference)
    assert not evaluation.passed and not evaluation.cost_matches_reference
    wrong = case.model_copy(update={"expected_status": "NO_PATH"})
    evaluation, _ = benchmark.evaluate(wrong, report, reference)
    assert not evaluation.status_matches


def test_bad_config_and_bad_reference_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        BenchmarkConfig(repeats=0)
    with pytest.raises(ValueError):
        BenchmarkConfig.model_validate({"unsupported": True})
    with pytest.raises(ValueError, match="duplicates"):
        benchmark.run_benchmark(
            BenchmarkConfig(algorithms=["astar", "astar"]), tmp_path
        )
    assert not list(tmp_path.iterdir())
    graph = pilot_cases(42)[2].reference_graph.model_copy(update={"waypoint_axes": []})
    with pytest.raises(ValueError, match="equal length"):
        reference_cost(graph)
