"""HTTP endpoints for searching and independently checking pipe routes."""

from typing import Literal

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import Field

from plan_route.api.projects import load_demo_project
from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import ContractModel, Identifier, Point3
from plan_route.models.results import (
    PathValidationResult,
    RouteSolveReport,
    RouteStatus,
    ValidationStatus,
)
from plan_route.services.path_validator import validate_path
from plan_route.services.report_store import save_report
from plan_route.services.routing import route_project

router = APIRouter(prefix="/api/routing", tags=["routing"])


class SolveRequest(ContractModel):
    project: EngineeringProject
    pipe_id: Identifier
    algorithm: Literal["astar", "dijkstra"] = "astar"
    max_expansions: int | None = Field(default=None, gt=0, strict=True)
    max_snap_distance_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ValidateRequest(ContractModel):
    project: EngineeringProject
    pipe_id: Identifier
    points_m: list[Point3] = Field(min_length=2)


def _status_code(status: RouteStatus | ValidationStatus) -> int:
    if isinstance(status, RouteStatus):
        if status is RouteStatus.INVALID_INPUT:
            return 422
        if status in (
            RouteStatus.UNAPPROVED_RULE,
            RouteStatus.RULE_CONFLICT,
            RouteStatus.INVALID_ROUTE,
            RouteStatus.WAYPOINT_BLOCKED,
        ):
            return 409
    elif status is ValidationStatus.INVALID_INPUT:
        return 422
    elif status is ValidationStatus.UNAPPROVED_RULE:
        return 409
    return 200


@router.post(
    "/solve",
    response_model=RouteSolveReport,
    responses={409: {"model": RouteSolveReport}, 422: {"model": RouteSolveReport}},
)
def solve(
    request: SolveRequest = Body(
        openapi_examples={
            "synthetic_demo": {
                "summary": "Solve the synthetic demo pipe",
                "value": {
                    "project": load_demo_project().model_dump(mode="json"),
                    "pipe_id": "PIPE-101",
                },
            }
        }
    ),
) -> RouteSolveReport | JSONResponse:
    report = route_project(
        request.project,
        request.pipe_id,
        algorithm=request.algorithm,
        max_expansions=request.max_expansions,
        max_snap_distance_m=request.max_snap_distance_m,
    )
    report = save_report(report, request)
    code = _status_code(report.status)
    if code != 200:
        return JSONResponse(status_code=code, content=report.model_dump(mode="json"))
    return report


@router.post(
    "/validate",
    response_model=PathValidationResult,
    responses={
        409: {"model": PathValidationResult},
        422: {"model": PathValidationResult},
    },
)
def validate(
    request: ValidateRequest = Body(
        openapi_examples={
            "crossing_wall": {
                "summary": "Reject a direct path through the synthetic demo wall",
                "value": {
                    "project": load_demo_project().model_dump(mode="json"),
                    "pipe_id": "PIPE-101",
                    "points_m": [[1, 2, 1], [11, 2, 1]],
                },
            }
        }
    ),
) -> PathValidationResult | JSONResponse:
    report = validate_path(request.project, request.pipe_id, tuple(request.points_m))
    report = save_report(report, request)
    code = _status_code(report.status)
    if code != 200:
        return JSONResponse(status_code=code, content=report.model_dump(mode="json"))
    return report
