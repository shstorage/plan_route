"""Typed search and independent validation results."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field

from plan_route.models.constraints import RuleSource
from plan_route.models.geometry import ContractModel, GridIndex, Point3


class RouteStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NO_PATH = "NO_PATH"
    SEARCH_LIMIT_REACHED = "SEARCH_LIMIT_REACHED"
    INVALID_INPUT = "INVALID_INPUT"
    RULES_NOT_COMPILED = "RULES_NOT_COMPILED"
    UNAPPROVED_RULE = "UNAPPROVED_RULE"
    RULE_CONFLICT = "RULE_CONFLICT"
    INVALID_ROUTE = "INVALID_ROUTE"
    WAYPOINT_BLOCKED = "WAYPOINT_BLOCKED"


@dataclass(frozen=True)
class CostBreakdown:
    grid_length_m: float
    connector_length_m: float
    path_length_m: float
    length_cost: float
    bend_cost: float
    total_objective_cost: float


@dataclass(frozen=True)
class RouteSearchResult:
    status: RouteStatus
    pipe_id: str
    algorithm: str
    points_m: tuple[Point3, ...]
    grid_points_m: tuple[Point3, ...]
    grid_indices: tuple[GridIndex, ...]
    bend_count: int | None
    cost_breakdown: CostBreakdown | None
    expanded_states: int
    runtime_ms: float
    message: str
    applied_rule_ids: tuple[str, ...] = ()


class ValidationStatus(StrEnum):
    VALID = "VALID"
    INVALID_ROUTE = "INVALID_ROUTE"
    INVALID_INPUT = "INVALID_INPUT"
    UNAPPROVED_RULE = "UNAPPROVED_RULE"


class PathViolation(ContractModel):
    code: str
    segment_index: int = Field(ge=0)
    object_id: str
    rule_id: str | None = None
    source: RuleSource | None = None
    measured_distance_m: float
    required_distance_m: float
    message: str


class PathValidationResult(ContractModel):
    status: ValidationStatus
    project_id: str
    pipe_id: str
    scenario_hash: str
    result_id: str | None = None
    applied_rule_ids: list[str] = Field(default_factory=list)
    checked_segments: int = 0
    violations: list[PathViolation] = Field(default_factory=list)
    message: str = ""


class RouteSolveReport(ContractModel):
    status: RouteStatus
    project_id: str
    pipe_id: str
    algorithm: str
    grid_resolution_m: float
    points_m: list[Point3] = Field(default_factory=list)
    grid_points_m: list[Point3] = Field(default_factory=list)
    grid_indices: list[GridIndex] = Field(default_factory=list)
    bend_count: int | None = None
    cost_breakdown: CostBreakdown | None = None
    expanded_states: int
    runtime_ms: float
    applied_rule_ids: list[str] = Field(default_factory=list)
    scenario_hash: str
    result_id: str | None = None
    validation: PathValidationResult | None = None
    message: str = ""
    qa_validator: str = "continuous_segment_aabb_v1"
