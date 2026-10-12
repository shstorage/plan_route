"""P06 project persistence, versioning, reload, and path safety tests."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from plan_route.api.projects import load_demo_project
from plan_route.main import app
from plan_route.services import project_store
from plan_route.services.routing import route_project


@pytest.fixture(autouse=True)
def isolated_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")


def test_save_reload_same_project_and_same_routing_result():
    project = load_demo_project()
    before = route_project(project, "PIPE-101")
    first = project_store.save_project(project)
    assert first.revision == 1
    assert first.schema_version == "1.0.0"
    assert first.updated_at.tzinfo is not None
    saved_path = project_store.PROJECTS_DIR / f"{project.project_id}.json"
    assert saved_path.exists()
    assert project_store.load_project(project.project_id) == first

    after = route_project(
        project_store.load_project(project.project_id).project, "PIPE-101"
    )
    assert before.status == after.status
    assert before.points_m == after.points_m
    assert before.cost_breakdown == after.cost_breakdown
    assert before.scenario_hash == after.scenario_hash
    assert before.validation.status == after.validation.status

    second = project_store.save_project(project)
    assert second.revision == 2
    assert second.updated_at >= first.updated_at
    assert second.document_hash == first.document_hash
    assert len(list(project_store.PROJECTS_DIR.glob("*.json"))) == 1
    assert list(project_store.PROJECTS_DIR.glob("*.tmp")) == []


def test_invalid_ids_cannot_escape_store_directory(tmp_path):
    project = load_demo_project()
    for malicious in ("../outside", "..\\outside", "/tmp/outside", "A/B", "A.B"):
        with pytest.raises(ValueError, match="project_id"):
            project_store.load_project(malicious)
        changed = project.model_copy(update={"project_id": malicious})
        with pytest.raises(ValueError, match="project_id"):
            project_store.save_project(changed)
    assert not project_store.PROJECTS_DIR.exists()
    assert not (tmp_path / "outside.json").exists()


def test_corrupt_hash_is_rejected():
    project = load_demo_project()
    project_store.save_project(project)
    path = project_store.PROJECTS_DIR / f"{project.project_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["document_hash"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity validation"):
        project_store.load_project(project.project_id)


def test_failed_atomic_replace_preserves_previous_revision(monkeypatch):
    project = load_demo_project()
    project_store.save_project(project)

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(project_store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        project_store.save_project(project)
    assert project_store.load_project(project.project_id).revision == 1
    assert list(project_store.PROJECTS_DIR.glob("*.tmp")) == []


def test_project_api_save_get_revisions_and_errors():
    project = load_demo_project().model_dump(mode="json")
    with TestClient(app) as client:
        origin = {"Origin": "http://127.0.0.1:5173"}
        saved = client.post("/api/projects/save", json=project, headers=origin)
        assert saved.status_code == 200
        assert saved.json()["revision"] == 1
        assert saved.json()["project_id"] == project["project_id"]
        assert len(saved.json()["document_hash"]) == 64

        loaded = client.get(f"/api/projects/{project['project_id']}", headers=origin)
        assert loaded.status_code == 200
        assert loaded.json() == project
        assert loaded.headers["x-project-revision"] == "1"
        assert loaded.headers["etag"].strip('"') == saved.json()["document_hash"]
        assert (
            "x-project-revision"
            in loaded.headers["access-control-expose-headers"].lower()
        )

        updated = client.post("/api/projects/save", json=project)
        assert updated.status_code == 200
        assert updated.json()["revision"] == 2
        assert (
            client.get(f"/api/projects/{project['project_id']}").headers[
                "x-project-revision"
            ]
            == "2"
        )

        missing = client.get("/api/projects/MISSING")
        assert missing.status_code == 404
        assert missing.json()["error_code"] == "NOT_FOUND"
        assert "data/projects" not in missing.text

        bad = {**project, "project_id": "../escape"}
        invalid = client.post("/api/projects/save", json=bad)
        assert invalid.status_code == 422
        assert invalid.json()["error_code"] == "INVALID_INPUT"
        assert not (project_store.PROJECTS_DIR.parent / "escape.json").exists()


def test_project_list_updates_names_counts_and_revision_after_saving():
    project = load_demo_project().model_dump(mode="json")
    project.update(project_id="NAMED-LIST", project_name="test1")
    with TestClient(app) as client:
        assert client.get("/api/projects").json() == {"projects": [], "issues": []}
        assert client.post("/api/projects/save", json=project).status_code == 200
        first = client.get("/api/projects").json()["projects"]
        assert len(first) == 1
        assert first[0]["project_name"] == "test1"
        assert first[0]["equipment_count"] == len(project["equipment"])
        assert first[0]["pipe_count"] == len(project["pipes"])
        project["project_name"] = "test11"
        assert client.post("/api/projects/save", json=project).status_code == 200
        latest = client.get("/api/projects").json()["projects"]
        assert len(latest) == 1 and latest[0]["project_name"] == "test11"
        assert latest[0]["project_id"] == "NAMED-LIST"
        assert latest[0]["revision"] == 2
        loaded = client.get("/api/projects/NAMED-LIST").json()
        assert loaded["project_name"] == "test11"
        assert loaded["equipment"] == project["equipment"]


def test_list_keeps_legacy_projects_and_reports_corrupt_files_without_deleting():
    project = load_demo_project()
    project_store.save_project(project)
    bad = project_store.PROJECTS_DIR / "BROKEN.json"
    bad.write_text("broken JSON", encoding="utf-8")
    with TestClient(app) as client:
        response = client.get("/api/projects")
        assert response.status_code == 200
        listing = response.json()
        assert listing["projects"][0]["project_name"] is None
        assert listing["issues"][0]["filename"] == "BROKEN.json"
        assert client.get("/api/projects/demo").status_code == 200
    assert bad.read_text(encoding="utf-8") == "broken JSON"


def test_list_verifies_hash_and_sorts_latest_saved_first(monkeypatch):
    start = datetime(2026, 10, 12, tzinfo=timezone.utc)
    instants = iter([start, start + timedelta(seconds=1)])

    class Clock:
        @staticmethod
        def now(_timezone):
            return next(instants)

    monkeypatch.setattr(project_store, "datetime", Clock)
    project = load_demo_project()
    other = project.model_copy(update={"project_id": "SECOND"})
    project_store.save_project(project)
    project_store.save_project(other)
    listing = project_store.list_projects()
    assert [item.project_id for item in listing.projects] == [
        "SECOND", project.project_id
    ]
    path = project_store.PROJECTS_DIR / "SECOND.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["project"]["project_name"] = "changed without updating hash"
    path.write_text(json.dumps(raw), encoding="utf-8")
    listing = project_store.list_projects()
    assert [item.project_id for item in listing.projects] == [project.project_id]
    assert listing.issues[0].filename == "SECOND.json"
