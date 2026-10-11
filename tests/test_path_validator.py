"""P05 independent geometry and routing API regression tests."""

import json
from importlib.resources import files
from math import isclose, sqrt

import pytest
from fastapi.testclient import TestClient

from plan_route.api.projects import load_demo_project
from plan_route.main import app
from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import AABB
from plan_route.models.results import RouteStatus, ValidationStatus
from plan_route.services import report_store
from plan_route.services.astar import solve_route
from plan_route.services.path_validator import segment_aabb_distance_m, validate_path
from plan_route.services.routing import route_project


@pytest.fixture
def open_data():
    data = json.loads(
        files("plan_route")
        .joinpath("fixtures/demo_project.json")
        .read_text(encoding="utf-8")
    )
    data["building"]["bounds_m"]["max_m"] = [7, 5, 3]
    data["building"]["floors"][0]["z_max_m"] = 3
    data["obstacles"] = []
    data["zones"] = []
    data["constraints"] = []
    data["equipment"][0]["ports"][0]["position_m"] = [1.5, 1.5, 1.5]
    data["equipment"][1]["ports"][0]["position_m"] = [5.5, 1.5, 1.5]
    data["pipes"][0]["outer_diameter_m"] = 0.2
    data["pipes"][0]["insulation_thickness_m"] = 0.1
    data["routing_config"]["grid_resolution_m"] = 1
    return data


@pytest.fixture(autouse=True)
def isolated_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "RESULTS_DIR", tmp_path / "results")


def test_segment_box_distance_is_euclidean_and_detects_touch():
    box = AABB(min_m=(1, 0, 0), max_m=(1.2, 0.2, 1))
    assert isclose(
        segment_aabb_distance_m((0, 0, 0), (2, 2, 0), box),
        0.8 / sqrt(2),
    )
    assert segment_aabb_distance_m((0, 0.1, 0.5), (1, 0.1, 0.5), box) == 0
    assert segment_aabb_distance_m((0, 0.1, 0.5), (2, 0.1, 0.5), box) == 0
    assert segment_aabb_distance_m((0, 0, 0), (0, 0, 0), box) == 1


def test_valid_demo_route_has_no_continuous_violations():
    report = route_project(load_demo_project(), "PIPE-101")
    assert report.status is RouteStatus.SUCCESS
    assert report.validation.status is ValidationStatus.VALID
    assert report.validation.checked_segments == len(report.points_m) - 1
    assert report.validation.violations == []
    assert report.applied_rule_ids == ["RULE-001"]
    assert len(report.scenario_hash) == 64


def test_manual_path_through_obstacle_reports_segment_and_measurement(open_data):
    open_data["obstacles"] = [
        {
            "id": "WALL-01",
            "kind": "wall",
            "shape": {
                "type": "aabb",
                "min_m": [3, 1, 1],
                "max_m": [4, 2, 2],
            },
        }
    ]
    project = EngineeringProject.model_validate(open_data)
    report = validate_path(project, "PIPE-101", ((1.5, 1.5, 1.5), (5.5, 1.5, 1.5)))
    assert report.status is ValidationStatus.INVALID_ROUTE
    assert report.checked_segments == 1
    assert len(report.violations) == 1
    violation = report.violations[0]
    assert violation.code == "OBSTACLE_COLLISION"
    assert violation.segment_index == 0
    assert violation.object_id == "WALL-01"
    assert violation.measured_distance_m == 0
    assert isclose(violation.required_distance_m, 0.2)


def test_tangent_contact_is_collision_and_just_clear_is_valid(open_data):
    open_data["obstacles"] = [
        {
            "id": "WALL-01",
            "kind": "wall",
            "shape": {
                "type": "aabb",
                "min_m": [3, 1.7, 1],
                "max_m": [4, 2, 2],
            },
        }
    ]
    project = EngineeringProject.model_validate(open_data)
    points = ((1.5, 1.5, 1.5), (5.5, 1.5, 1.5))
    contact = validate_path(project, "PIPE-101", points)
    assert contact.status is ValidationStatus.INVALID_ROUTE
    assert isclose(contact.violations[0].measured_distance_m, 0.2)

    open_data["obstacles"][0]["shape"]["min_m"][1] = 1.701
    clear = validate_path(
        EngineeringProject.model_validate(open_data), "PIPE-101", points
    )
    assert clear.status is ValidationStatus.VALID


def test_keep_out_and_min_clearance_use_original_zone_distance(open_data):
    open_data["zones"] = [
        {
            "id": "ZONE-A",
            "zone_type": "restricted",
            "shape": {
                "type": "aabb",
                "min_m": [3, 1.8, 1],
                "max_m": [4, 2.2, 2],
            },
        }
    ]
    rule = load_demo_project().model_dump(mode="json")["constraints"][0]
    open_data["constraints"] = [rule]
    points = ((1.5, 1.5, 1.5), (5.5, 1.5, 1.5))
    keep_out = validate_path(
        EngineeringProject.model_validate(open_data), "PIPE-101", points
    )
    assert (
        keep_out.status is ValidationStatus.VALID
    )  # Centreline distance 0.3 > radius 0.2.

    rule["type"] = "MIN_CLEARANCE"
    rule["parameters"] = {
        "distance_m": 0.2,
        "distance_basis": "insulated_pipe_surface_to_target_surface",
    }
    clearance = validate_path(
        EngineeringProject.model_validate(open_data), "PIPE-101", points
    )
    assert clearance.status is ValidationStatus.INVALID_ROUTE
    assert clearance.violations[0].code == "MIN_CLEARANCE"
    assert clearance.violations[0].rule_id == "RULE-001"
    assert clearance.violations[0].source.document_id == "DEMO-SPEC"
    assert isclose(clearance.violations[0].measured_distance_m, 0.3)
    assert isclose(clearance.violations[0].required_distance_m, 0.4)


def test_endpoints_building_boundary_and_unapproved_rule(open_data):
    project = EngineeringProject.model_validate(open_data)
    wrong = validate_path(project, "PIPE-101", ((0.1, 1.5, 1.5), (5.5, 1.5, 1.5)))
    assert wrong.status is ValidationStatus.INVALID_ROUTE
    assert {item.code for item in wrong.violations} == {
        "ENDPOINT_MISMATCH",
        "BUILDING_BOUNDARY",
    }
    assert (
        validate_path(project, "MISSING", ((1.5, 1.5, 1.5), (5.5, 1.5, 1.5))).status
        is ValidationStatus.INVALID_INPUT
    )
    assert (
        validate_path(project, "PIPE-101", ((1.5, 1.5, 1.5),)).status
        is ValidationStatus.INVALID_INPUT
    )

    open_data["zones"] = [
        {
            "id": "ZONE-A",
            "zone_type": "restricted",
            "shape": {"type": "aabb", "min_m": [3, 1, 1], "max_m": [4, 2, 2]},
        }
    ]
    draft = load_demo_project().model_dump(mode="json")["constraints"][0]
    draft["status"] = "draft"
    open_data["constraints"] = [draft]
    blocked = validate_path(
        EngineeringProject.model_validate(open_data),
        "PIPE-101",
        ((1.5, 1.5, 1.5), (5.5, 1.5, 1.5)),
    )
    assert blocked.status is ValidationStatus.UNAPPROVED_RULE
    assert blocked.violations == []


def test_routing_service_distinguishes_no_path_limit_and_failed_validation(
    open_data, monkeypatch
):
    open_data["obstacles"] = [
        {
            "id": "WALL-ALL",
            "kind": "wall",
            "shape": {"type": "aabb", "min_m": [3, 0, 0], "max_m": [4, 5, 3]},
        }
    ]
    project = EngineeringProject.model_validate(open_data)
    assert route_project(project, "PIPE-101").status is RouteStatus.NO_PATH
    open_data["obstacles"] = []
    project = EngineeringProject.model_validate(open_data)
    assert (
        route_project(project, "PIPE-101", max_expansions=1).status
        is RouteStatus.SEARCH_LIMIT_REACHED
    )

    genuine_search = solve_route(project, "PIPE-101")
    forged = genuine_search.__class__(
        **{
            **genuine_search.__dict__,
            "points_m": ((1.5, 1.5, 1.5), (3.5, 0.1, 1.5), (5.5, 1.5, 1.5)),
        }
    )
    monkeypatch.setattr(
        "plan_route.services.routing.solve_route", lambda *a, **kw: forged
    )
    rejected = route_project(project, "PIPE-101")
    assert rejected.status is RouteStatus.INVALID_ROUTE
    assert rejected.validation.status is ValidationStatus.INVALID_ROUTE
    assert any(
        item.code == "BUILDING_BOUNDARY" for item in rejected.validation.violations
    )


def test_routing_api_reports_and_saves_results(open_data):
    with TestClient(app) as client:
        request = {"project": open_data, "pipe_id": "PIPE-101"}
        solved = client.post("/api/routing/solve", json=request)
        assert solved.status_code == 200
        data = solved.json()
        assert data["status"] == "SUCCESS"
        assert data["validation"]["status"] == "VALID"
        assert data["result_id"] is not None
        artifact = report_store.RESULTS_DIR / f"{data['result_id']}.json"
        assert (
            json.loads(artifact.read_text(encoding="utf-8"))["scenario_hash"]
            == data["scenario_hash"]
        )

        manual = client.post(
            "/api/routing/validate",
            json={**request, "points_m": data["points_m"]},
        )
        assert manual.status_code == 200
        assert manual.json()["status"] == "VALID"
        assert manual.json()["result_id"] != data["result_id"]

        limited = client.post(
            "/api/routing/solve", json={**request, "max_expansions": 1}
        )
        assert limited.status_code == 200
        assert limited.json()["status"] == "SEARCH_LIMIT_REACHED"

        barrier = json.loads(json.dumps(request))
        barrier["project"]["obstacles"] = [
            {
                "id": "WALL-ALL",
                "kind": "wall",
                "shape": {
                    "type": "aabb",
                    "min_m": [3, 0, 0],
                    "max_m": [4, 5, 3],
                },
            }
        ]
        no_path = client.post("/api/routing/solve", json=barrier)
        assert no_path.status_code == 200
        assert no_path.json()["status"] == "NO_PATH"

        unknown = client.post(
            "/api/routing/solve", json={**request, "pipe_id": "MISSING"}
        )
        assert unknown.status_code == 422
        assert unknown.json()["status"] == "INVALID_INPUT"

        invalid_ref = json.loads(json.dumps(request))
        invalid_ref["project"]["pipes"][0]["from_port_id"] = "MISSING"
        bad = client.post("/api/routing/solve", json=invalid_ref)
        assert bad.status_code == 422
        assert bad.json()["error_code"] == "INVALID_INPUT"


def test_routing_api_unapproved_and_invalid_manual_path(open_data):
    open_data["zones"] = [
        {
            "id": "ZONE-A",
            "zone_type": "restricted",
            "shape": {"type": "aabb", "min_m": [3, 1, 1], "max_m": [4, 2, 2]},
        }
    ]
    rule = load_demo_project().model_dump(mode="json")["constraints"][0]
    rule["status"] = "draft"
    open_data["constraints"] = [rule]
    with TestClient(app) as client:
        body = {"project": open_data, "pipe_id": "PIPE-101"}
        blocked = client.post("/api/routing/solve", json=body)
        assert blocked.status_code == 409
        assert blocked.json()["status"] == "UNAPPROVED_RULE"
        rule["status"] = "approved"
        open_data["zones"][0]["shape"] = {
            "type": "aabb",
            "min_m": [1.3, 1.3, 1.3],
            "max_m": [1.7, 1.7, 1.7],
        }
        conflict = client.post("/api/routing/solve", json=body)
        assert conflict.status_code == 409
        assert conflict.json()["status"] == "RULE_CONFLICT"
        open_data["zones"][0]["shape"] = {
            "type": "aabb",
            "min_m": [3, 1, 1],
            "max_m": [4, 2, 2],
        }
        manual = client.post(
            "/api/routing/validate",
            json={**body, "points_m": [[1.5, 1.5, 1.5], [5.5, 1.5, 1.5]]},
        )
        assert manual.status_code == 200
        assert manual.json()["status"] == "INVALID_ROUTE"
        assert manual.json()["violations"][0]["rule_id"] == "RULE-001"
