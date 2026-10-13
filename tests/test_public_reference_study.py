"""Meaningful applicability, normalized boundary and provenance regressions."""

import json
from pathlib import Path

import pytest

from plan_route.models.engineering import EngineeringProject
from plan_route.services.public_reference_cases import (
    electrical_dedicated_space_case,
    gold_probes,
    public_reference_cases,
    thermal_walkway_case,
    wall_working_clearance_case,
)
from plan_route.services.public_reference_study import (
    evaluate_probe,
    project_variant,
    run_public_reference_study,
)
from plan_route.services.routing import route_project


@pytest.mark.parametrize(
    "size,gap", [(80, 0.15), (100, 0.15), (101, 0.25), (150, 0.25)]
)
def test_nominal_size_threshold_and_heating_scope(size, gap):
    case = wall_working_clearance_case(size)
    assert case.project.constraints[0].parameters.distance_m == gap
    assert case.applicability["nominal_size_mm"] == size
    assert case.project.constraints[0].source.source_type == "public_reference"
    assert case.project.constraints[0].approval_is_current


@pytest.mark.parametrize("size", [0, -1, float("nan"), float("inf"), True])
def test_invalid_nominal_size_rejected(size):
    with pytest.raises(ValueError):
        wall_working_clearance_case(size)


@pytest.mark.parametrize("service", ["main_steam", "process_steam", "boiler_feed"])
def test_inapplicable_service_not_silently_treated_as_heating(service):
    with pytest.raises(ValueError):
        wall_working_clearance_case(100, service=service)


@pytest.mark.parametrize(
    "options",
    [{"indoor": False}, {"sprinkler": True}, {"protected_foreign_system": True}],
)
def test_electrical_exceptions_require_a_separate_interpretation(options):
    with pytest.raises(ValueError):
        electrical_dedicated_space_case(**options)


def test_thermal_source_and_excluded_crossings():
    case = thermal_walkway_case()
    assert case.project.zones[0].shape.max_m == (3.5, 4, 2.5)
    assert case.applicability["source_pdf_page_1based"] == 83
    with pytest.raises(ValueError):
        thermal_walkway_case(crossing="road")


@pytest.mark.parametrize("case", public_reference_cases(), ids=lambda c: c.case_id)
def test_analytical_rule_source_object_segment_and_distance_labels(case):
    for probe in gold_probes(case):
        result = evaluate_probe(case, probe)
        assert result["passed"], result
        assert not result["normalized_false_valid"]
    assert case == next(
        c for c in public_reference_cases() if c.case_id == case.case_id
    )


def test_minimum_height_equality_gap_is_reported_not_hidden():
    case = thermal_walkway_case()
    boundary = [
        p
        for p in gold_probes(case)
        if p["normalized_valid"] and not p["contract_valid"]
    ]
    assert len(boundary) == 2
    assert all(evaluate_probe(case, p)["normalized_false_invalid"] for p in boundary)


def test_probe_oracle_detects_wrong_segment_and_distance_labels():
    case = wall_working_clearance_case(100)
    probe = gold_probes(case)[0]
    assert evaluate_probe(case, probe)["passed"]
    assert not evaluate_probe(case, {**probe, "expected_rule_segments": [7]})["passed"]
    assert not evaluate_probe(case, {**probe, "expected_distance_m": 99})["passed"]


def test_neutral_source_edit_preserves_geometry_but_requires_current_approval():
    case = electrical_dedicated_space_case()
    a = project_variant(case, "reference", 0.5)
    b = project_variant(case, "source_note", 0.5)
    assert (
        a.building == b.building and a.obstacles == b.obstacles and a.zones == b.zones
    )
    assert a.constraints[0].scope == b.constraints[0].scope
    assert (
        a.constraints[0].approved_content_sha256
        != b.constraints[0].approved_content_sha256
    )
    assert b.constraints[0].approval_is_current
    assert not project_variant(case, "stale", 0.5).constraints[0].approval_is_current


def test_retained_study_has_explicit_normalization_gaps_and_unique_batches(tmp_path):
    batch = run_public_reference_study(tmp_path, repeats=1, resolutions=(0.5,))
    summary = json.loads((batch / "summary.json").read_text())
    assert summary["runs"] == 24
    assert not summary["failures"], summary
    assert summary["gold_probes"] == summary["contract_probe_matches"] == 24
    assert summary["normalized_false_invalid"] == 2
    assert summary["normalized_false_valid"] == 0
    assert summary["link_false_positives"] == summary["link_false_negatives"] == 0
    assert (batch / "source.zip").is_file()
    canonical = batch / "P10D-THERMAL-WALKWAY/project.json"
    assert (
        json.loads(canonical.read_text())["constraints"][0]["source"]["document_id"]
        == "BHEL-PE-TS-425-166-A001"
    )
    assert run_public_reference_study(tmp_path, repeats=1, resolutions=(0.5,)) != batch


def test_fine_grid_rejections_are_retained_and_excluded_from_valid_cost_deltas(
    tmp_path,
):
    batch = run_public_reference_study(tmp_path, repeats=1, resolutions=(0.25,))
    summary = json.loads((batch / "summary.json").read_text())
    assert not summary["failures"], summary
    assert summary["statuses"] == {"SUCCESS": 12, "INVALID_ROUTE": 12}
    assert summary["valid_authored_witnesses"] == 4
    comparisons = json.loads((batch / "comparisons.json").read_text())
    for item in comparisons:
        if item["after_status"] == "INVALID_ROUTE":
            assert not item["finite_valid_cost_pair"]
            assert "delta_objective" not in item and "delta_length_m" not in item


@pytest.mark.parametrize("case_id", [case.case_id for case in public_reference_cases()])
def test_exported_review_projects_are_drafts_and_cannot_run_before_approval(case_id):
    path = Path("benchmarks/public_examples") / f"{case_id}.json"
    project = EngineeringProject.model_validate_json(path.read_text(encoding="utf-8"))
    assert all(
        rule.status.value == "draft"
        and not rule.approval_history
        and rule.approved_content_sha256 is None
        for rule in project.constraints
    )
    assert route_project(project, "PIPE-101").status.value == "UNAPPROVED_RULE"
