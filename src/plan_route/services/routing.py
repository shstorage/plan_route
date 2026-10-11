"""Compile, search, and independently validate a route in one transaction."""

from time import perf_counter
from typing import Literal

from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import (
    OptimalityGuarantee,
    RouteSolveReport,
    RouteStatus,
    StageTimings,
    ValidationStatus,
)
from plan_route.services.astar import solve_route
from plan_route.services.compiler import compile_constraints
from plan_route.services.path_validator import scenario_hash, validate_path


def route_project(
    project: EngineeringProject,
    pipe_id: str,
    *,
    algorithm: Literal["astar", "dijkstra"] = "astar",
    max_expansions: int | None = None,
    max_snap_distance_m: float | None = None,
) -> RouteSolveReport:
    started = perf_counter()
    compilation = compile_constraints(project, pipe_id)
    compiled_at = perf_counter()
    result = solve_route(
        project,
        pipe_id,
        algorithm=algorithm,
        max_expansions=max_expansions,
        max_snap_distance_m=max_snap_distance_m,
        compilation=compilation,
    )
    searched_at = perf_counter()
    validation = None
    status = result.status
    message = result.message
    if result.status is RouteStatus.SUCCESS:
        validation = validate_path(project, pipe_id, result.points_m)
        if validation.status is not ValidationStatus.VALID:
            status = RouteStatus.INVALID_ROUTE
            message = (
                f"continuous geometry validation failed: "
                f"{len(validation.violations)} violation(s)"
                + (f"; {result.message}" if result.message else "")
            )
    validated_at = perf_counter()
    report = RouteSolveReport(
        status=status,
        project_id=project.project_id,
        pipe_id=pipe_id,
        algorithm=algorithm,
        grid_resolution_m=project.routing_config.grid_resolution_m,
        points_m=list(result.points_m),
        grid_points_m=list(result.grid_points_m),
        grid_indices=list(result.grid_indices),
        bend_count=result.bend_count,
        cost_breakdown=result.cost_breakdown,
        expanded_states=result.expanded_states,
        runtime_ms=result.runtime_ms,
        applied_rule_ids=list(result.applied_rule_ids),
        scenario_hash=scenario_hash(project, pipe_id),
        validation=validation,
        message=message,
        legacy_approval_rule_ids=[
            rule.id
            for rule in project.constraints
            if pipe_id in rule.scope.pipe_ids
            and rule.status.value == "approved"
            and rule.approved_content_sha256 is None
        ],
        search_mode=result.search_mode,
        optimality_guarantee=(
            result.optimality_guarantee
            if status is RouteStatus.SUCCESS
            else OptimalityGuarantee.NONE
        ),
        initial_search_status=result.initial_search_status,
        fallback_reason=result.fallback_reason,
        fallback_status=result.fallback_status,
        initial_expanded_states=result.initial_expanded_states,
        fallback_expanded_states=result.fallback_expanded_states,
    )
    return report.model_copy(
        update={
            "timings": StageTimings(
                compile_ms=(compiled_at - started) * 1000,
                search_ms=(searched_at - compiled_at) * 1000,
                validate_ms=(validated_at - searched_at) * 1000
                if validation is not None
                else 0.0,
                total_ms=(perf_counter() - started) * 1000,
            )
        }
    )
