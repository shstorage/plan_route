"""Typed search and independent validation results."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

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


class SearchMode(StrEnum):
    NOT_RUN = "NOT_RUN"
    EXACT_GRID = "EXACT_GRID"
    HEURISTIC_LEGS = "HEURISTIC_LEGS"
    EXACT_GRID_RETURNED = "EXACT_GRID_RETURNED"


class OptimalityGuarantee(StrEnum):
    NONE = "NONE"
    GRID_OBJECTIVE_EXCLUDING_SELF_CLEARANCE = "GRID_OBJECTIVE_EXCLUDING_SELF_CLEARANCE"


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
    search_mode: SearchMode = SearchMode.NOT_RUN
    optimality_guarantee: OptimalityGuarantee = OptimalityGuarantee.NONE
    initial_search_status: RouteStatus | None = None
    fallback_reason: Literal["SELF_CLEARANCE"] | None = None
    fallback_status: RouteStatus | None = None
    initial_expanded_states: int = 0
    fallback_expanded_states: int = 0


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
    validation_contract: str = "orthogonal_core_canonical_connectors_v2"
    self_clearance_policy: str = "straight_runs_arc_2sqrt3_radius_v2"
    waypoint_tolerance_m: float | None = None


class StageTimings(ContractModel):
    compile_ms: float = Field(ge=0)
    search_ms: float = Field(ge=0)
    validate_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


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
    timings: StageTimings | None = None
    applied_rule_ids: list[str] = Field(default_factory=list)
    scenario_hash: str
    result_id: str | None = None
    validation: PathValidationResult | None = None
    message: str = ""
    qa_validator: str = "continuous_geometry_v2"
    legacy_approval_rule_ids: list[str] = Field(default_factory=list)
    search_mode: SearchMode = SearchMode.NOT_RUN
    optimality_guarantee: OptimalityGuarantee = OptimalityGuarantee.NONE
    feasibility_domain: Literal["COMPILED_GRID_6_NEIGHBOUR"] = (
        "COMPILED_GRID_6_NEIGHBOUR"
    )
    initial_search_status: RouteStatus | None = None
    fallback_reason: Literal["SELF_CLEARANCE"] | None = None
    fallback_status: RouteStatus | None = None
    initial_expanded_states: int = 0
    fallback_expanded_states: int = 0
