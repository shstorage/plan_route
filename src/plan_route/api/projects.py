"""Read-only demo project and project contract validation endpoints."""

import json
from datetime import datetime
from importlib.resources import files
from typing import Literal

from fastapi import APIRouter, Body, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import Identifier
from plan_route.services.project_store import (
    ProjectNotFoundError,
    load_project,
    save_project,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ValidationSuccess(BaseModel):
    valid: Literal[True] = True
    project_id: str
    schema_version: str


class ValidationIssue(BaseModel):
    location: list[str | int]
    message: str
    type: str


class InvalidInputResponse(BaseModel):
    error_code: Literal["INVALID_INPUT"] = "INVALID_INPUT"
    message: str
    details: list[ValidationIssue]


class ProjectSaveResponse(BaseModel):
    project_id: str
    schema_version: str
    revision: int
    updated_at: datetime
    document_hash: str


class ProjectNotFoundResponse(BaseModel):
    error_code: Literal["NOT_FOUND"] = "NOT_FOUND"
    message: str
    details: list[ValidationIssue] = Field(default_factory=list)


def _load_fixture(name: str) -> EngineeringProject:
    resource = files("plan_route").joinpath(f"fixtures/{name}")
    return EngineeringProject.model_validate(
        json.loads(resource.read_text(encoding="utf-8"))
    )


def load_demo_project() -> EngineeringProject:
    """Small 12 x 10 x 4 m test case used by unit tests."""
    return _load_fixture("demo_project.json")


def load_plant_starter_project() -> EngineeringProject:
    """Synthetic 60 x 40 x 12 m two-floor building used as the UI starting point."""
    return _load_fixture("plant_starter_project.json")


@router.get("/demo", response_model=EngineeringProject)
def get_demo_project() -> EngineeringProject:
    return load_demo_project()


@router.get("/starter", response_model=EngineeringProject)
def get_plant_starter_project() -> EngineeringProject:
    return load_plant_starter_project()


@router.post(
    "/validate",
    response_model=ValidationSuccess,
    responses={422: {"model": InvalidInputResponse}},
)
def validate_project(
    project: EngineeringProject = Body(
        openapi_examples={
            "synthetic_demo": {
                "summary": "Synthetic benchmark project",
                "value": json.loads(
                    files("plan_route")
                    .joinpath("fixtures/demo_project.json")
                    .read_text(encoding="utf-8")
                ),
            }
        }
    ),
) -> ValidationSuccess:
    return ValidationSuccess(
        project_id=project.project_id, schema_version=project.schema_version
    )


@router.post(
    "/save",
    response_model=ProjectSaveResponse,
    responses={422: {"model": InvalidInputResponse}},
)
def save_project_document(
    project: EngineeringProject = Body(
        openapi_examples={
            "synthetic_demo": {
                "summary": "Save the synthetic demo project",
                "value": json.loads(
                    files("plan_route")
                    .joinpath("fixtures/demo_project.json")
                    .read_text(encoding="utf-8")
                ),
            }
        }
    ),
) -> ProjectSaveResponse:
    saved = save_project(project)
    return ProjectSaveResponse(
        project_id=saved.project_id,
        schema_version=saved.schema_version,
        revision=saved.revision,
        updated_at=saved.updated_at,
        document_hash=saved.document_hash,
    )


@router.get(
    "/{project_id}",
    response_model=EngineeringProject,
    responses={404: {"model": ProjectNotFoundResponse}},
)
def get_project_document(
    project_id: Identifier, response: Response
) -> EngineeringProject | JSONResponse:
    try:
        saved = load_project(project_id)
    except ProjectNotFoundError as error:
        body = ProjectNotFoundResponse(message=str(error))
        return JSONResponse(status_code=404, content=body.model_dump())
    response.headers["X-Project-Revision"] = str(saved.revision)
    response.headers["X-Project-Updated-At"] = saved.updated_at.isoformat()
    response.headers["ETag"] = f'"{saved.document_hash}"'
    return saved.project
