"""Controlled P10C interventions, counterfactual evidence and retained outputs."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from plan_route.models.benchmark import (
    BenchmarkConfig,
    BenchmarkRun,
)
from plan_route.services import benchmark_change_analysis as analysis
from plan_route.services.benchmark import evaluate, run_benchmark
from plan_route.services.benchmark_changes import change_cases
from plan_route.services.benchmark_reference import reference_cost
from plan_route.services.routing import route_project


def config(**kwargs):
    return BenchmarkConfig(
        suite="changes",
        scene_seeds=[11],
        evaluation_seeds=[211],
        repeats=1,
        bootstrap_resamples=100,
        **kwargs,
    )


def record(case, algorithm="astar", **kwargs):
    report = route_project(case.project, case.pipe_id, algorithm=algorithm, **kwargs)
    reference = reference_cost(case.reference_graph, 600)
    evaluation, _ = evaluate(case, report, reference)
    return BenchmarkRun(
        run_id=case.case_id + algorithm,
        batch_id="test",
        case_id=case.case_id,
        repeat=1,
        algorithm=algorithm,
        started_at="test",
        completed_at="test",
        input_sha256="test",
        report=report,
        reference=reference,
        evaluation=evaluation,
        oracle_ms=0,
    )


@pytest.fixture(scope="module")
def experiment():
    cases = change_cases(config())
    cases = [case for case in cases if case.seed == 11]
    runs = [
        record(case, algorithm) for case in cases for algorithm in ("astar", "dijkstra")
    ]
    return cases, runs


def test_default_design_has_fixed_geometry_per_intervention_and_seed_split():
    conf = BenchmarkConfig.model_validate_json(
        Path("benchmarks/changes.json").read_text(encoding="utf-8")
    )
    cases = change_cases(conf)
    assert len(cases) == 168
    assert len({case.scene_id for case in cases}) == 7
    assert len(cases) * conf.repeats * len(conf.algorithms) == 1008
    assert cases == change_cases(conf)
    by_id = {case.case_id: case for case in cases}
    for case in cases:
        if case.comparison_parent_id:
            parent = by_id[case.comparison_parent_id]
            a, b = [item.project.model_dump() for item in (case, parent)]
            a.pop("constraints")
            b.pop("constraints")
            assert a == b
        for rule in case.project.constraints:
            if case.case_id.endswith("stale") and rule.id == "RULE-CLEAR":
                assert not rule.approval_is_current
            else:
                assert rule.approval_is_current
    assert {case.seed for case in cases if case.split == "development"}.isdisjoint(
        case.seed for case in cases if case.split == "evaluation"
    )


@pytest.mark.parametrize("resolution", [1.0, 0.5])
@pytest.mark.parametrize("algorithm", ["astar", "dijkstra"])
def test_all_variants_match_independent_graph_and_approval_contract(
    experiment, resolution, algorithm
):
    cases, runs = experiment
    selected = [
        case
        for case in cases
        if case.project.routing_config.grid_resolution_m == resolution
    ]
    assert len(selected) == 12
    for case in selected:
        run = next(
            item
            for item in runs
            if item.case_id == case.case_id and item.algorithm == algorithm
        )
        assert run.evaluation.passed, run.evaluation.errors
        assert run.report.search_mode == case.expected_search_mode
        assert analysis.audit_run(case, run)["applied_set_matches"]
        if case.case_id.endswith(("draft", "stale")):
            assert run.report.expanded_states == 0 and not run.report.applied_rule_ids


def test_rule_influence_requires_counterfactuals_and_preserves_neutral_controls(
    experiment,
):
    cases, runs = experiment
    stats, pairs, audits = analysis.analyse_changes(cases, runs, config())
    assert not stats["failures"]
    assert stats["comparison_count"] == 44
    assert stats["exact_success_pairs"] == 32
    assert stats["applied_trace"]["coverage"] == 1
    assert all(audit["complete_links"] == audit["expected_links"] for audit in audits)
    for pair in pairs:
        assert not pair["failures"]
        if pair["intervention"] == "SOURCE_EDIT":
            assert pair["objective_delta"] == 0 and not pair["path_changed"]
            assert (
                pair["rule_definition_changes"][0]["before"]["source"]
                != pair["rule_definition_changes"][0]["after"]["source"]
            )
        if pair["intervention"] == "ADD_RULE" and pair["changed_rule_ids"] == [
            "RULE-KEEP"
        ]:
            assert pair["objective_delta"] > 0 and pair["union_added_cells"] > 0
            check = pair["before_path_under_after_rules"]
            assert check["report"]["status"] == "INVALID_ROUTE"
            assert check["expected_links"] == check["complete_links"] > 0
            link = check["rule_violation_links"][0]
            assert link["object_id"] == "ZONE" and link["rule_id"] == "RULE-KEEP"
            assert (
                len(link["segment_m"]) == 2
                and link["source"]["document_id"] == "P10C-FIXTURE"
            )
        if pair["changed_rule_ids"] == ["RULE-DUPLICATE"]:
            assert pair["objective_delta"] == 0
            assert pair["union_added_cells"] == pair["union_removed_cells"] == 0
        if pair["intervention"] == "REMOVE_RULE" and pair["changed_rule_ids"] == [
            "RULE-CLEAR"
        ]:
            assert pair["objective_delta"] < 0
            assert (
                pair["after_path_under_before_rules"]["report"]["status"]
                == "INVALID_ROUTE"
            )
    assert all(
        row["n_scenes"] == row["n_seed_clusters"] == 1
        for row in stats["objective_delta_statistics"]
    )
    assert all(row["ci_low"] is None for row in stats["objective_delta_statistics"])


def test_failures_never_become_zero_cost_deltas(experiment):
    cases, runs = experiment
    stats, pairs, _ = analysis.analyse_changes(cases, runs, config())
    failed = [pair for pair in pairs if pair["after_status"] != "SUCCESS"]
    assert len(failed) == 12
    assert all(pair["objective_delta"] is None for pair in failed)
    base = next(case for case in cases if case.case_id.endswith("r1-base"))
    keep = next(case for case in cases if case.case_id.endswith("r1-keep"))
    old = record(base)
    limited = record(keep, max_expansions=1)
    assert limited.report.status == "SEARCH_LIMIT_REACHED"
    assert analysis.compare_pair(base, keep, old, limited)["objective_delta"] is None
    assert "SUCCESS->NO_PATH" in stats["status_transitions"]
    assert "SUCCESS->UNAPPROVED_RULE" in stats["status_transitions"]


def test_missing_applied_rules_and_nondeterministic_repeats_are_detected(experiment):
    cases, runs = experiment
    target = next(run for run in runs if run.case_id.endswith("r1-keep"))
    case = next(case for case in cases if case.case_id == target.case_id)
    broken = target.model_copy(
        update={"report": target.report.model_copy(update={"applied_rule_ids": []})}
    )
    assert not analysis.audit_run(case, broken)["applied_set_matches"]
    changed_report = target.report.model_copy(
        update={
            "cost_breakdown": replace(
                target.report.cost_breakdown, total_objective_cost=1000
            )
        }
    )
    extra = target.model_copy(
        update={"run_id": "changed", "repeat": 2, "report": changed_report}
    )
    stats, _, _ = analysis.analyse_changes(cases, [*runs, extra], config())
    assert any("nondeterministic" in error for error in stats["failures"])
    assert any("missing/duplicate repetitions" in error for error in stats["failures"])
    missing, _, _ = analysis.analyse_changes(cases, runs[1:], config())
    assert any("missing runs" in error for error in missing["failures"])


@pytest.mark.parametrize(
    "damage",
    [
        "source",
        "rule_id",
        "object_id",
        "segment_index",
        "measured_distance_m",
        "required_distance_m",
    ],
)
def test_incomplete_violation_links_are_not_reported_as_complete(
    monkeypatch, experiment, damage
):
    cases, _ = experiment
    case = next(case for case in cases if case.case_id.endswith("r1-keep"))
    points = [(1.5, 1.5, 1.5), (10.5, 1.5, 1.5)]
    result = analysis.validate_path(case.project, case.pipe_id, tuple(points))
    assert result.violations
    broken_value = {
        "source": None,
        "rule_id": None,
        "object_id": "MISSING",
        "segment_index": 99,
        "measured_distance_m": 99.0,
        "required_distance_m": 99.0,
    }[damage]
    broken = result.model_copy(
        update={
            "violations": [
                item.model_copy(update={damage: broken_value})
                for item in result.violations
            ]
        }
    )
    monkeypatch.setattr(analysis, "validate_path", lambda *args: broken)
    audit = analysis.trace_validation(case, points)
    assert audit["expected_links"] > 0 and audit["complete_links"] == 0


def test_wrong_in_range_segment_link_fails_independent_geometry_check(
    monkeypatch, experiment
):
    cases, _ = experiment
    case = next(case for case in cases if case.case_id.endswith("r1-keep"))
    points = [(1.5, 1.5, 1.5), (3.5, 1.5, 1.5), (10.5, 1.5, 1.5)]
    result = analysis.validate_path(case.project, case.pipe_id, tuple(points))
    assert all(item.segment_index == 1 for item in result.violations)
    corrupted = result.model_copy(
        update={
            "violations": [
                item.model_copy(update={"segment_index": 0})
                for item in result.violations
            ]
        }
    )
    monkeypatch.setattr(analysis, "validate_path", lambda *args: corrupted)
    audit = analysis.trace_validation(case, points)
    assert audit["expected_links"] > 0 and audit["complete_links"] == 0


def test_pairs_reject_geometry_changes_wrong_algorithms_and_wrong_metadata(experiment):
    cases, runs = experiment
    base = next(case for case in cases if case.case_id.endswith("r1-base"))
    keep = next(case for case in cases if case.case_id.endswith("r1-keep"))
    a = next(
        run for run in runs if run.case_id == base.case_id and run.algorithm == "astar"
    )
    b = next(
        run for run in runs if run.case_id == keep.case_id and run.algorithm == "astar"
    )
    bad_project = keep.project.model_copy(update={"project_id": "CHANGED"})
    for altered in (
        keep.model_copy(update={"project": bad_project}),
        keep.model_copy(update={"changed_rule_ids": ["MISSING"]}),
    ):
        with pytest.raises(ValueError):
            analysis.compare_pair(base, altered, a, b)
    with pytest.raises(ValueError):
        analysis.compare_pair(
            base, keep, a, b.model_copy(update={"algorithm": "dijkstra"})
        )


def test_vertex_distance_is_geometric_and_handles_no_paths():
    assert (
        analysis.vertex_distance(
            [(0, 0, 0), (2, 0, 0)], [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
        )
        == 0
    )
    assert analysis.vertex_distance([(0, 0, 0), (2, 0, 0)], [(0, 1, 0), (2, 1, 0)]) == 1
    assert analysis.vertex_distance([], [(0, 0, 0), (1, 0, 0)]) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"evaluation_seeds": [11]},
        {"scene_seeds": []},
        {"algorithms": ["astar"]},
        {"resolutions_m": [1, 1]},
        {"scene_seeds": [-1]},
    ],
)
def test_changes_config_rejects_invalid_experimental_design(kwargs):
    with pytest.raises(ValueError):
        BenchmarkConfig.model_validate(
            {
                "suite": "changes",
                "scene_seeds": [11],
                "evaluation_seeds": [211],
                **kwargs,
            }
        )


def test_cli_runner_retains_changes_with_trace_csv_report_and_figures(
    tmp_path, monkeypatch
):
    from plan_route.services import benchmark

    monkeypatch.setattr(benchmark, "_environment", lambda batch: {"test": True})
    conf = config(resolutions_m=[1.0])
    batch = run_benchmark(conf, tmp_path)
    summary = json.loads((batch / "summary.json").read_text(encoding="utf-8"))
    assert summary["run_count"] == summary["passed_runs"] == 48
    assert not summary["analysis"]["failures"]
    assert summary["analysis"]["comparison_count"] == 44
    assert summary["analysis"]["applied_trace"]["coverage"] == 1
    for name in (
        "change_metrics.csv",
        "change_report.md",
        "change_comparisons.json",
        "traceability_audit.json",
        "execution_plan.json",
    ):
        assert (batch / name).is_file()
    pairs = json.loads((batch / "change_comparisons.json").read_text(encoding="utf-8"))
    pair = pairs[0]
    assert (
        batch / pair["before_case_id"] / pair["before_run_id"] / "input.json"
    ).is_file()
    assert (batch / pair["after_case_id"] / pair["after_run_id"] / "run.json").is_file()
    assert (
        (batch / "figures/rule_change_objective.png")
        .read_bytes()
        .startswith(b"\x89PNG")
    )
    assert (
        (batch / "figures/rule_change_objective.pdf").read_bytes().startswith(b"%PDF")
    )
    # End-to-end execution writes another exclusive batch and retains old run IDs.
    second = run_benchmark(conf, tmp_path)
    assert second != batch and (batch / "summary.json").is_file()
