"""Synthetic plant-scale starter project and per-pipe clearance margin."""

import copy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from plan_route.api.projects import load_demo_project, load_plant_starter_project
from plan_route.main import app
from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteStatus, ValidationStatus
from plan_route.services.compiler import compile_constraints
from plan_route.services.geometry import effective_pipe_radius_m
from plan_route.services.path_validator import validate_path
from plan_route.services.routing import route_project
from plan_route.services.voxel_grid import voxelize_project


def test_starter_endpoint_returns_two_floor_plant_scale_project():
    response = TestClient(app).get("/api/projects/starter")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "SYNTH-PLANT-001"
    assert body["building"]["bounds_m"]["max_m"] == [60.0, 40.0, 12.0]
    assert [floor["id"] for floor in body["building"]["floors"]] == ["L1", "L2"]
    # Every starter rule is labelled as a synthetic study assumption.
    assert {rule["source"]["source_type"] for rule in body["constraints"]} == {
        "synthetic_assumption"
    }


@pytest.mark.parametrize("pipe_id", ["PIPE-101", "PIPE-102", "PIPE-103"])
def test_every_starter_pipe_routes_and_passes_independent_validation(pipe_id):
    report = route_project(load_plant_starter_project(), pipe_id)
    assert report.status is RouteStatus.SUCCESS, report.message
    assert report.validation.status is ValidationStatus.VALID


def test_starter_pipe_crosses_floors_through_the_slab_opening():
    report = route_project(load_plant_starter_project(), "PIPE-103")
    through_slab = [
        point
        for point in report.points_m
        if 5.7 <= point[2] <= 6.0
        and not (46 <= point[0] <= 49 and 14 <= point[1] <= 17)
    ]
    assert report.points_m[0][2] < 5.7 < 6.0 < report.points_m[-1][2]
    assert through_slab == []


def test_clearance_margin_defaults_to_zero_and_rejects_negative_or_non_finite():
    data = load_demo_project().model_dump(mode="json")
    del data["pipes"][0]["clearance_margin_m"]
    assert EngineeringProject.model_validate(data).pipes[0].clearance_margin_m == 0
    for bad in (-0.01, float("inf")):
        candidate = copy.deepcopy(data)
        candidate["pipes"][0]["clearance_margin_m"] = bad
        with pytest.raises(ValidationError):
            EngineeringProject.model_validate(candidate)


def _with_margin(project: EngineeringProject, margin_m: float) -> EngineeringProject:
    data = project.model_dump(mode="json")
    data["pipes"][0]["clearance_margin_m"] = margin_m
    return EngineeringProject.model_validate(data)


def test_margin_enlarges_envelope_for_grid_and_validator():
    base = load_demo_project()
    wide = _with_margin(base, 0.6)
    radius = effective_pipe_radius_m(wide.pipes[0])
    assert radius == pytest.approx(effective_pipe_radius_m(base.pipes[0]) + 0.6)
    assert (
        voxelize_project(base, "PIPE-101").obstacle_cells
        < voxelize_project(wide, "PIPE-101").obstacle_cells
    )
    assert compile_constraints(
        _with_margin(base, 0.3), "PIPE-101"
    ).grid.effective_radius_m == pytest.approx(0.07 + 0.3)

    # Detour 0.6 m below the building's north face: clear for the bare
    # insulated pipe, a violation once the 0.6 m margin is added.
    points = ((1, 2, 1), (1, 9.4, 1), (11, 9.4, 1), (11, 2, 1))
    # The manual detour departs +y and arrives -y.
    for project in (base, wide):
        for equipment in project.equipment:
            for port in equipment.ports:
                port.orientation = "+y"
    assert validate_path(base, "PIPE-101", points).status is ValidationStatus.VALID
    report = validate_path(wide, "PIPE-101", points)
    assert report.status is ValidationStatus.INVALID_ROUTE
    assert report.violations
    assert all(
        v.required_distance_m == pytest.approx(radius) for v in report.violations
    )


def test_large_margin_closes_a_narrow_gap():
    data = load_demo_project().model_dump(mode="json")
    data["obstacles"].append(
        {
            "id": "WALL-02",
            "kind": "wall",
            "shape": {"type": "aabb", "min_m": [5, 9.25, 0], "max_m": [5.5, 10, 4]},
        }
    )
    open_gap = EngineeringProject.model_validate(data)
    # 1.25 m gap above ZONE-A: open for the bare pipe, closed once the envelope grows.
    assert route_project(open_gap, "PIPE-101").status is RouteStatus.SUCCESS
    assert (
        route_project(_with_margin(open_gap, 0.2), "PIPE-101").status
        is RouteStatus.NO_PATH
    )
