"""P04 rule compilation, provenance, API, and routing behavior tests."""

import json
from importlib.resources import files

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from plan_route.main import app
from plan_route.models.constraints import ConstraintStatus
from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteStatus
from plan_route.services.astar import solve_route
from plan_route.services.compiler import CompilationStatus, compile_constraints
from plan_route.services.voxel_grid import voxelize_project


@pytest.fixture
def project_data():
    data = json.loads(
        files("plan_route")
        .joinpath("fixtures/demo_project.json")
        .read_text(encoding="utf-8")
    )
    data["building"]["bounds_m"]["max_m"] = [7, 5, 3]
    data["building"]["floors"][0]["z_max_m"] = 3
    data["obstacles"] = []
    data["zones"] = [
        {
            "id": "ZONE-A",
            "zone_type": "restricted",
            "shape": {
                "type": "aabb",
                "min_m": [3.3, 1.3, 1.3],
                "max_m": [3.7, 1.7, 1.7],
            },
        }
    ]
    data["equipment"][0]["ports"][0]["position_m"] = [1.5, 1.5, 1.5]
    data["equipment"][1]["ports"][0]["position_m"] = [5.5, 1.5, 1.5]
    data["pipes"][0]["outer_diameter_m"] = 0.1
    data["pipes"][0]["insulation_thickness_m"] = 0
    data["routing_config"]["grid_resolution_m"] = 1
    return data


def _project(data):
    return EngineeringProject.model_validate(data)


def test_approved_keep_out_changes_route_and_preserves_source(project_data):
    project = _project(project_data)
    without_rule = _project({**project_data, "constraints": []})
    plain = solve_route(without_rule, "PIPE-101")
    assert plain.status is RouteStatus.SUCCESS
    assert (3, 1, 1) in plain.grid_indices
    assert solve_route(project, "PIPE-101").status is RouteStatus.RULES_NOT_COMPILED

    compilation = compile_constraints(project, "PIPE-101")
    assert compilation.status is CompilationStatus.SUCCESS
    assert compilation.applied_rule_ids == ("RULE-001",)
    assert compilation.grid.rule_cells == frozenset({(3, 1, 1)})
    assert voxelize_project(project, "PIPE-101").is_traversable((3, 1, 1))
    assert compilation.impacts[0].affected_cells_count == 1
    assert compilation.impacts[0].newly_blocked_cells_count == 1
    assert compilation.impacts[0].source.document_id == "DEMO-SPEC"
    assert compilation.grid.slice_text(1).count("!") == 1

    for method in ("astar", "dijkstra"):
        routed = solve_route(
            project, "PIPE-101", compilation=compilation, algorithm=method
        )
        assert routed.status is RouteStatus.SUCCESS
        assert routed.applied_rule_ids == ("RULE-001",)
        assert (3, 1, 1) not in routed.grid_indices
        assert (
            routed.cost_breakdown.total_objective_cost
            > plain.cost_breakdown.total_objective_cost
        )


def test_clearance_expands_target_by_radius_plus_distance(project_data):
    project_data["constraints"][0]["type"] = "MIN_CLEARANCE"
    project_data["constraints"][0]["scope"]["target_ids"] = ["WALL-01"]
    project_data["constraints"][0]["parameters"] = {
        "distance_m": 0.2,
        "distance_basis": "insulated_pipe_surface_to_target_surface",
    }
    project_data["obstacles"] = [
        {
            "id": "WALL-01",
            "kind": "wall",
            "shape": {
                "type": "aabb",
                "min_m": [3.4, 2.2, 1.4],
                "max_m": [3.6, 2.4, 1.6],
            },
        }
    ]
    project = _project(project_data)
    physical = voxelize_project(project, "PIPE-101")
    assert physical.is_traversable((3, 1, 1))
    assert (3, 2, 1) in physical.obstacle_cells
    compiled = compile_constraints(project, "PIPE-101")
    assert compiled.status is CompilationStatus.SUCCESS
    assert (3, 1, 1) in compiled.grid.rule_cells
    assert compiled.impacts[0].newly_blocked_cells_count >= 1
    route = solve_route(project, "PIPE-101", compilation=compiled)
    assert route.status is RouteStatus.SUCCESS
    assert (3, 1, 1) not in route.grid_indices


def test_unapproved_rule_fails_closed(project_data):
    project_data["constraints"][0]["status"] = "draft"
    project = _project(project_data)
    compiled = compile_constraints(project, "PIPE-101")
    assert compiled.status is CompilationStatus.UNAPPROVED_RULE
    assert compiled.grid is None
    assert compiled.applied_rule_ids == ()
    assert (
        solve_route(project, "PIPE-101", compilation=compiled).status
        is RouteStatus.UNAPPROVED_RULE
    )
    # The P03 physical-only solver still does not apply draft rules.
    assert (3, 1, 1) in solve_route(project, "PIPE-101").grid_indices


def test_rule_conflict_with_port_is_distinct_from_physical_invalid_input(project_data):
    project_data["zones"][0]["shape"] = {
        "type": "aabb",
        "min_m": [1.3, 1.3, 1.3],
        "max_m": [1.7, 1.7, 1.7],
    }
    project = _project(project_data)
    compiled = compile_constraints(project, "PIPE-101")
    assert compiled.status is CompilationStatus.RULE_CONFLICT
    assert "PORT-A" in compiled.message
    assert "RULE-001" in compiled.message
    assert (
        solve_route(project, "PIPE-101", compilation=compiled).status
        is RouteStatus.RULE_CONFLICT
    )


def test_full_rule_barrier_yields_no_path_not_search_limit(project_data):
    project_data["zones"][0]["shape"] = {
        "type": "aabb",
        "min_m": [3.3, 0, 0],
        "max_m": [3.7, 5, 3],
    }
    project = _project(project_data)
    compiled = compile_constraints(project, "PIPE-101")
    assert compiled.status is CompilationStatus.SUCCESS
    result = solve_route(project, "PIPE-101", compilation=compiled)
    assert result.status is RouteStatus.NO_PATH
    assert result.applied_rule_ids == ("RULE-001",)


def test_invalid_references_and_missing_clearance_are_rejected(project_data):
    project = _project(project_data)
    assert (
        compile_constraints(project, "MISSING").status
        is CompilationStatus.INVALID_INPUT
    )
    project_data["constraints"][0]["scope"]["target_ids"] = ["MISSING"]
    with pytest.raises(ValidationError, match="invalid target MISSING"):
        _project(project_data)
    project_data["constraints"][0]["scope"]["target_ids"] = ["ZONE-A"]
    project_data["constraints"][0]["type"] = "MIN_CLEARANCE"
    with pytest.raises(ValidationError, match="requires parameters.distance_m"):
        _project(project_data)
    project_data["constraints"][0]["parameters"] = {"distance_m": 0.2}
    with pytest.raises(ValidationError, match="requires parameters.distance_basis"):
        _project(project_data)


def test_stale_compilation_and_missing_provenance_are_rejected(project_data):
    project = _project(project_data)
    compiled = compile_constraints(project, "PIPE-101")
    changed = _project({**project_data, "project_id": "SYNTH-CHANGED"})
    assert (
        solve_route(changed, "PIPE-101", compilation=compiled).status
        is RouteStatus.INVALID_INPUT
    )
    source = project.constraints[0].source.model_copy(update={"evidence_text": ""})
    rule = project.constraints[0].model_copy(update={"source": source})
    invalid_project = project.model_copy(update={"constraints": [rule]})
    assert (
        compile_constraints(invalid_project, "PIPE-101").status
        is CompilationStatus.INVALID_INPUT
    )


def test_compile_api_success_and_failure_statuses(project_data):
    with TestClient(app) as client:
        body = {"project": project_data, "pipe_id": "PIPE-101"}
        success = client.post("/api/constraints/compile", json=body)
        assert success.status_code == 200
        assert success.json()["status"] == "SUCCESS"
        assert success.json()["rule_blocked_cells_count"] == 1
        assert success.json()["impacts"][0]["source"]["document_id"] == "DEMO-SPEC"

        body["project"]["constraints"][0]["status"] = "draft"
        unapproved = client.post("/api/constraints/compile", json=body)
        assert unapproved.status_code == 409
        assert unapproved.json()["status"] == "UNAPPROVED_RULE"

        body["pipe_id"] = "MISSING"
        invalid = client.post("/api/constraints/compile", json=body)
        assert invalid.status_code == 422
        assert invalid.json()["status"] == "INVALID_INPUT"

        body["pipe_id"] = "PIPE-101"
        body["project"]["constraints"][0]["scope"]["target_ids"] = ["MISSING"]
        invalid_ref = client.post("/api/constraints/compile", json=body)
        assert invalid_ref.status_code == 422
        assert invalid_ref.json()["error_code"] == "INVALID_INPUT"


def test_irrelevant_unapproved_rule_does_not_affect_other_pipe(project_data):
    project = _project(project_data)
    other_pipe = project.pipes[0].model_copy(update={"id": "PIPE-OTHER"})
    draft_rule = project.constraints[0].model_copy(
        update={"status": ConstraintStatus.DRAFT}
    )
    changed = project.model_copy(
        update={"pipes": [*project.pipes, other_pipe], "constraints": [draft_rule]}
    )
    compiled = compile_constraints(changed, "PIPE-OTHER")
    assert compiled.status is CompilationStatus.SUCCESS
    assert compiled.applied_rule_ids == ()
    assert compiled.grid.rule_cells == frozenset()
