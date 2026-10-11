"""Approval binding and research-facing result contracts."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from plan_route.api.projects import load_demo_project
from plan_route.main import app
from plan_route.models.engineering import EngineeringProject
from plan_route.services import project_store
from plan_route.services.approval import approve_rule
from plan_route.services.compiler import compile_constraints, project_fingerprint
from plan_route.services.path_validator import validate_path
from plan_route.services.routing import route_project


def test_approval_binds_current_revision_and_reapproval_records_change():
    approved = approve_rule(load_demo_project(), "RULE-001", "Research reviewer")
    rule = approved.constraints[0]
    assert rule.approval_is_current
    assert rule.approved_content_sha256 == rule.content_sha256()
    assert rule.approval_history[0].approved_at.tzinfo is not None
    changed_data = approved.model_dump(mode="json")
    changed_data["constraints"][0]["source"]["evidence_text"] += " revised"
    changed = EngineeringProject.model_validate(changed_data)
    assert not changed.constraints[0].approval_is_current
    assert compile_constraints(changed, "PIPE-101").status == "UNAPPROVED_RULE"
    assert validate_path(changed, "PIPE-101", ((1, 2, 1), (11, 2, 1))).status == (
        "UNAPPROVED_RULE"
    )
    again = approve_rule(changed, "RULE-001", "Second reviewer")
    assert again.constraints[0].definition_revision == 2
    assert len(again.constraints[0].approval_history) == 2
    assert again.constraints[0].approval_is_current
    assert again.constraints[0].approval_history[0] == rule.approval_history[0]


def test_bound_approval_cannot_be_reused_by_clearing_the_hash_only():
    approved = approve_rule(load_demo_project(), "RULE-001", "Reviewer")
    approved.constraints[0].approved_content_sha256 = None
    assert compile_constraints(approved, "PIPE-101").status == "UNAPPROVED_RULE"


@pytest.mark.parametrize("reviewer,rule_id", [(" ", "RULE-001"), ("R", "MISSING")])
def test_approval_api_rejects_missing_reviewer_or_rule(reviewer, rule_id):
    with TestClient(app) as client:
        response = client.post(
            "/api/constraints/approve",
            json={
                "project": load_demo_project().model_dump(mode="json"),
                "rule_id": rule_id,
                "approved_by": reviewer,
            },
        )
    assert response.status_code == 422


def test_approval_api_returns_normalized_project_and_bound_event():
    with TestClient(app) as client:
        response = client.post(
            "/api/constraints/approve",
            json={
                "project": load_demo_project().model_dump(mode="json"),
                "rule_id": "RULE-001",
                "approved_by": "Reviewer",
            },
        )
    assert response.status_code == 200
    assert (
        EngineeringProject.model_validate(response.json())
        .constraints[0]
        .approval_is_current
    )


def test_exact_search_and_legacy_import_are_explicit_in_results():
    project = load_demo_project()
    report = route_project(project, "PIPE-101")
    assert report.status == "SUCCESS"
    assert report.search_mode == "EXACT_GRID"
    assert report.optimality_guarantee == "GRID_OBJECTIVE_EXCLUDING_SELF_CLEARANCE"
    assert report.feasibility_domain == "COMPILED_GRID_6_NEIGHBOUR"
    assert report.initial_search_status == "SUCCESS"
    assert report.fallback_status is None
    assert report.expanded_states == report.initial_expanded_states
    assert report.legacy_approval_rule_ids == ["RULE-001"]
    rebound = route_project(approve_rule(project, "RULE-001", "R"), "PIPE-101")
    assert rebound.legacy_approval_rule_ids == []


def test_initial_search_budget_failure_is_not_a_feasibility_claim():
    report = route_project(load_demo_project(), "PIPE-101", max_expansions=1)
    assert report.status == report.initial_search_status == "SEARCH_LIMIT_REACHED"
    assert report.optimality_guarantee == "NONE"
    assert report.fallback_status is None
    assert report.validation is None


def test_legacy_stored_document_hash_is_checked_before_adding_new_defaults(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path)
    saved = project_store.save_project(load_demo_project())
    data = saved.model_dump(mode="json")
    for rule in data["project"]["constraints"]:
        for key in (
            "definition_revision",
            "approved_content_sha256",
            "approval_history",
        ):
            rule.pop(key)
    data["document_hash"] = hashlib.sha256(
        json.dumps(data["project"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path = tmp_path / f"{saved.project_id}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = project_store.load_project(saved.project_id)
    assert loaded.document_hash == project_fingerprint(loaded.project)
    assert loaded.revision == saved.revision
    data["project"]["pipes"][0]["outer_diameter_m"] += 0.01
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        project_store.load_project(saved.project_id)
