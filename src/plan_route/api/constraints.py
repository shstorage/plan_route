"""HTTP interface for compiling approved hard rules for one pipe."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from plan_route.models.constraints import ConstraintType, RuleSource
from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import Identifier
from plan_route.services.compiler import CompilationStatus, compile_constraints

router = APIRouter(prefix="/api/constraints", tags=["constraints"])


class CompileRequest(BaseModel):
    project: EngineeringProject
    pipe_id: Identifier


class RuleImpactResponse(BaseModel):
    rule_id: str
    rule_type: ConstraintType
    target_ids: list[str]
    source: RuleSource
    affected_cells_count: int
    newly_blocked_cells_count: int


class CompileResponse(BaseModel):
    status: CompilationStatus
    project_id: str
    pipe_id: str
    applied_rule_ids: list[str]
    impacts: list[RuleImpactResponse]
    rule_blocked_cells_count: int
    message: str


@router.post(
    "/compile",
    response_model=CompileResponse,
    responses={409: {"model": CompileResponse}, 422: {"model": CompileResponse}},
)
def compile_project_rules(request: CompileRequest) -> CompileResponse | JSONResponse:
    result = compile_constraints(request.project, request.pipe_id)
    response = CompileResponse(
        status=result.status,
        project_id=result.project_id,
        pipe_id=result.pipe_id,
        applied_rule_ids=list(result.applied_rule_ids),
        impacts=[
            RuleImpactResponse(
                rule_id=impact.rule_id,
                rule_type=impact.rule_type,
                target_ids=list(impact.target_ids),
                source=impact.source,
                affected_cells_count=impact.affected_cells_count,
                newly_blocked_cells_count=impact.newly_blocked_cells_count,
            )
            for impact in result.impacts
        ],
        rule_blocked_cells_count=result.rule_blocked_cells_count,
        message=result.message,
    )
    if result.status is CompilationStatus.SUCCESS:
        return response
    status_code = 422 if result.status is CompilationStatus.INVALID_INPUT else 409
    return JSONResponse(
        status_code=status_code, content=response.model_dump(mode="json")
    )
