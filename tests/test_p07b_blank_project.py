"""Actual frontend edits -> Python contracts, routing and persistence."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plan_route.main import app
from plan_route.models.engineering import EngineeringProject
from plan_route.services import project_store, report_store
from plan_route.services.compiler import project_fingerprint


@pytest.fixture(scope="module")
def frontend_edits():
    node = shutil.which("node")
    if node is None:
        pytest.skip("P07b frontend/Python integration requires Node.js 22.18+")
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [node, "scripts/editor_blank_scenario.mjs"],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=30,
    )
    return json.loads(completed.stdout)


def test_blank_and_cleaned_ui_projects_are_valid_and_can_be_saved(
    frontend_edits, tmp_path, monkeypatch
):
    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        for name in ("blank", "cleaned"):
            data = frontend_edits[name]
            assert not data["equipment"] and not data["pipes"] and not data["obstacles"]
            assert client.post("/api/projects/validate", json=data).status_code == 200
            assert client.post("/api/projects/save", json=data).status_code == 200
            assert client.get(f"/api/projects/{data['project_id']}").status_code == 200


def test_built_and_translated_ui_layouts_route_and_roundtrip(
    frontend_edits, tmp_path, monkeypatch
):
    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(report_store, "RESULTS_DIR", tmp_path / "results")
    pipe_id = frontend_edits["pipeId"]
    reports = []
    with TestClient(app) as client:
        for name in ("built", "moved"):
            project = EngineeringProject.model_validate(frontend_edits[name])
            assert len(project.equipment) == 2 and len(project.obstacles) == 2
            saved = client.post(
                "/api/projects/save", json=project.model_dump(mode="json")
            )
            assert saved.status_code == 200
            loaded = client.get(f"/api/projects/{project.project_id}").json()
            assert EngineeringProject.model_validate(loaded) == project
            results = []
            for algorithm in ("astar", "dijkstra"):
                response = client.post(
                    "/api/routing/solve",
                    json={
                        "project": loaded,
                        "pipe_id": pipe_id,
                        "algorithm": algorithm,
                    },
                )
                assert response.status_code == 200, response.text
                result = response.json()
                assert (
                    result["status"] == "SUCCESS"
                    and result["validation"]["status"] == "VALID"
                )
                assert result["search_mode"] == "EXACT_GRID"
                results.append(result)
            assert results[0]["cost_breakdown"] == results[1]["cost_breakdown"]
            reports.append(results[0])
    assert reports[0]["scenario_hash"] != reports[1]["scenario_hash"]
    assert reports[0]["points_m"] != reports[1]["points_m"]
    assert (
        reports[1]["cost_breakdown"]["path_length_m"]
        > reports[0]["cost_breakdown"]["path_length_m"]
    )


def test_unsaved_close_equipment_rejects_blocked_endpoints_and_moving_it_repairs_route(
    frontend_edits, tmp_path, monkeypatch
):
    monkeypatch.setattr(report_store, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        blocked = client.post(
            "/api/routing/solve",
            json={
                "project": frontend_edits["blocked"],
                "pipe_id": frontend_edits["pipeId"],
            },
        ).json()
        assert blocked["status"] == "INVALID_INPUT"
        assert "snaps to a physical blocked cell" in blocked["message"]
        repaired = client.post(
            "/api/routing/solve",
            json={
                "project": frontend_edits["repaired"],
                "pipe_id": frontend_edits["pipeId"],
            },
        ).json()
        assert repaired["status"] == "SUCCESS"
        assert repaired["validation"]["status"] == "VALID"
    assert not (tmp_path / "projects").exists(), (
        "route calculations never require a saved project"
    )


def test_named_project_save_and_load_preserves_korean_name_and_legacy_hash(
    frontend_edits, tmp_path, monkeypatch
):
    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")
    legacy = frontend_edits["built"]
    model = EngineeringProject.model_validate(legacy)
    assert "project_name" not in model.model_dump(mode="json")
    assert EngineeringProject.model_validate({**legacy, "project_name": None}) == model
    assert project_fingerprint(model) == project_fingerprint(
        EngineeringProject.model_validate(model.model_dump(mode="json"))
    )
    with TestClient(app) as client:
        named = frontend_edits["named"]
        response = client.post("/api/projects/save", json=named)
        assert response.status_code == 200, response.text
        loaded = client.get(f"/api/projects/{named['project_id']}").json()
        assert loaded["project_name"] == "배관 연구 프로젝트"
        assert loaded["project_id"] == legacy["project_id"]
        for invalid in (" ", "가" * 101):
            response = client.post(
                "/api/projects/validate", json={**named, "project_name": invalid}
            )
            assert response.status_code == 422
