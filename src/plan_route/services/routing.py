"""Compile, search, and independently validate a route in one transaction."""

from typing import Literal

from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteSolveReport, RouteStatus, ValidationStatus
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
    compilation = compile_constraints(project, pipe_id)
    result = solve_route(
        project,
        pipe_id,
        algorithm=algorithm,
        max_expansions=max_expansions,
        max_snap_distance_m=max_snap_distance_m,
        compilation=compilation,
    )
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
            )
    return RouteSolveReport(
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
    )
