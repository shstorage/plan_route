"""P01 contract and HTTP validation regression tests."""

import copy
import json
from importlib.resources import files
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from plan_route.api.projects import load_demo_project
from plan_route.main import app
from plan_route.models.engineering import EngineeringProject


@pytest.fixture
def demo_data() -> dict:
    path = files("plan_route").joinpath("fixtures/demo_project.json")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_demo_is_single_valid_document(demo_data):
    project = load_demo_project()
    assert project.project_id == "SYNTH-DEMO-001"
    assert project.model_dump(mode="json")["coordinate_frame"]["unit"] == "m"
    assert (
        project.model_dump(mode="json")["constraints"][0]["source"]["source_type"]
        == "synthetic_assumption"
    )
    assert project == EngineeringProject.model_validate(demo_data)


def test_json_round_trip_preserves_meaning(demo_data):
    project = EngineeringProject.model_validate(demo_data)
    restored = EngineeringProject.model_validate_json(project.model_dump_json())
    assert restored == project


def test_demo_and_validate_api(client, demo_data):
    demo_response = client.get("/api/projects/demo")
    assert demo_response.status_code == 200
    assert (
        EngineeringProject.model_validate(demo_response.json()) == load_demo_project()
    )

    response = client.post("/api/projects/validate", json=demo_data)
    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "project_id": "SYNTH-DEMO-001",
        "schema_version": "1.0.0",
    }


@pytest.mark.parametrize(
    ("field_path", "value", "expected"),
    [
        (("pipes", 0, "from_port_id"), "MISSING", "from_port_id MISSING"),
        (("equipment", 0, "geometry_ref"), "MISSING", "geometry_ref MISSING"),
        (("constraints", 0, "scope", "pipe_ids"), ["MISSING"], "unknown pipe MISSING"),
        (
            ("constraints", 0, "scope", "target_ids"),
            ["MISSING"],
            "invalid target MISSING",
        ),
        (("pipes", 0, "outer_diameter_m"), -0.1, "outer_diameter_m"),
        (("obstacles", 0, "shape", "max_m"), [5, 7, 4], "AABB min_m"),
        (("constraints", 0, "type"), "NOT_A_RULE", "type"),
        (("coordinate_frame", "unit"), "mm", "unit"),
        (("coordinate_frame", "up_axis"), "y", "up_axis"),
        (("schema_version",), "2.0.0", "schema_version"),
        (("equipment", 0, "ports", 0, "position_m"), [13, 2, 1], "PORT-A"),
        (("zones", 0, "shape", "max_m"), [13, 8, 4], "ZONE-A"),
        (("obstacles", 0, "id"), "ZONE-A", "duplicate ID ZONE-A"),
        (
            ("constraints", 0, "scope", "target_ids"),
            ["WALL-01"],
            "invalid target WALL-01",
        ),
        (("pipes", 0, "insulation_thickness_m"), -0.01, "insulation_thickness_m"),
        (("routing_config", "search_limits", "max_expansions"), 0, "max_expansions"),
    ],
)
def test_invalid_values_get_specific_422(
    client, demo_data, field_path, value, expected
):
    candidate = copy.deepcopy(demo_data)
    field = candidate
    for part in field_path[:-1]:
        field = field[part]
    field[field_path[-1]] = value
    response = client.post("/api/projects/validate", json=candidate)
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INVALID_INPUT"
    assert body["details"]
    assert any(
        expected in f"{issue['location']} {issue['message']}"
        for issue in body["details"]
    )


@pytest.mark.parametrize(
    ("field_path", "expected"),
    [
        (("constraints", 0, "source", "source_type"), "source_type"),
        (("constraints", 0, "status"), "status"),
        (("equipment", 0, "ports", 0, "orientation"), "orientation"),
        (("pipes", 0, "outer_diameter_m"), "outer_diameter_m"),
    ],
)
def test_missing_fields_get_422(client, demo_data, field_path, expected):
    candidate = copy.deepcopy(demo_data)
    field = candidate
    for part in field_path[:-1]:
        field = field[part]
    del field[field_path[-1]]
    response = client.post("/api/projects/validate", json=candidate)
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_INPUT"
    assert any(
        expected in str(issue["location"]) for issue in response.json()["details"]
    )


def test_unapproved_rule_is_preserved_as_data(client, demo_data):
    for status in ("draft", "needs_review", "rejected"):
        candidate = copy.deepcopy(demo_data)
        candidate["constraints"][0]["status"] = status
        response = client.post("/api/projects/validate", json=candidate)
        assert response.status_code == 200
        assert (
            EngineeringProject.model_validate(candidate).constraints[0].status == status
        )


def test_clearance_requires_distance_and_basis(client, demo_data):
    candidate = copy.deepcopy(demo_data)
    candidate["constraints"][0]["type"] = "MIN_CLEARANCE"
    candidate["constraints"][0]["scope"]["target_ids"] = ["WALL-01"]
    response = client.post("/api/projects/validate", json=candidate)
    assert response.status_code == 422
    assert "distance_m" in response.json()["details"][0]["message"]

    candidate["constraints"][0]["parameters"] = {
        "distance_m": 0.15,
        "distance_basis": "insulated_pipe_surface_to_target_surface",
    }
    assert client.post("/api/projects/validate", json=candidate).status_code == 200


def test_reject_extra_fields_and_nonfinite_coordinate(demo_data):
    candidate = copy.deepcopy(demo_data)
    candidate["pixel_x"] = 42
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EngineeringProject.model_validate(candidate)

    candidate = copy.deepcopy(demo_data)
    candidate["coordinate_frame"]["origin_m"][0] = float("inf")
    with pytest.raises(ValidationError, match="finite_number"):
        EngineeringProject.model_validate(candidate)


def test_schema_export_matches_model(demo_data):
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "docs/schema/engineering_project_v1.schema.json"
    )
    exported = json.loads(schema_path.read_text(encoding="utf-8"))
    assert exported == EngineeringProject.model_json_schema()
    assert "constraints" in exported["properties"]
    assert EngineeringProject.model_validate(demo_data)


def test_api_schema_and_post_preflight(client):
    schema = client.get("/openapi.json").json()
    assert "/api/projects/validate" in schema["paths"]
    assert "422" in schema["paths"]["/api/projects/validate"]["post"]["responses"]
    preflight = client.options(
        "/api/projects/validate",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
