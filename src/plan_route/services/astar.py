"""Direction-aware deterministic 6-neighbour A* and Dijkstra grid search."""

from heapq import heappop, heappush
from itertools import count
from math import dist, isfinite, sqrt
from time import perf_counter
from typing import Literal

from plan_route.models.constraints import ConstraintStatus
from plan_route.models.engineering import EngineeringProject, Port
from plan_route.models.geometry import GridIndex, Point3
from plan_route.models.results import CostBreakdown, RouteSearchResult, RouteStatus
from plan_route.services.compiler import (
    CompilationResult,
    CompilationStatus,
    project_fingerprint,
)
from plan_route.services.voxel_grid import VoxelGrid, voxelize_project

Algorithm = Literal["astar", "dijkstra"]
State = tuple[int, int, int, int]
_NO_DIRECTION = -1
_DIRECTIONS: tuple[GridIndex, ...] = (
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (0, 0, 1),
    (0, 0, -1),
)
_PORT_DIRECTIONS = {"+x": 0, "-x": 1, "+y": 2, "-y": 3, "+z": 4, "-z": 5}


def _port_for_id(project: EngineeringProject, port_id: str) -> Port:
    for equipment in project.equipment:
        for port in equipment.ports:
            if port.id == port_id:
                return port
    raise ValueError(f"unknown port ID: {port_id}")


def _point_path_length(points: tuple[Point3, ...]) -> float:
    return sum(dist(first, second) for first, second in zip(points, points[1:]))


def _return_result(
    status: RouteStatus,
    pipe_id: str,
    algorithm: str,
    started_at: float,
    expanded_states: int = 0,
    message: str = "",
    *,
    grid_indices: tuple[GridIndex, ...] = (),
    grid_points_m: tuple[Point3, ...] = (),
    points_m: tuple[Point3, ...] = (),
    bend_count: int | None = None,
    cost_breakdown: CostBreakdown | None = None,
    applied_rule_ids: tuple[str, ...] = (),
) -> RouteSearchResult:
    return RouteSearchResult(
        status=status,
        pipe_id=pipe_id,
        algorithm=algorithm,
        points_m=points_m,
        grid_points_m=grid_points_m,
        grid_indices=grid_indices,
        bend_count=bend_count,
        cost_breakdown=cost_breakdown,
        expanded_states=expanded_states,
        runtime_ms=(perf_counter() - started_at) * 1000,
        message=message,
        applied_rule_ids=applied_rule_ids,
    )


def _result_for_path(
    final_state: State,
    previous: dict[State, State],
    grid: VoxelGrid,
    source: Port,
    target: Port,
    length_weight: float,
    bend_weight: float,
    algorithm: Algorithm,
    started_at: float,
    expanded_states: int,
    applied_rule_ids: tuple[str, ...],
) -> RouteSearchResult:
    states = [final_state]
    while states[-1] in previous:
        states.append(previous[states[-1]])
    states.reverse()
    indices = tuple((state[0], state[1], state[2]) for state in states)
    grid_points = tuple(grid.spec.grid_to_world(index) for index in indices)
    grid_length = _point_path_length(grid_points)
    connector_length = dist(source.position_m, grid_points[0]) + dist(
        grid_points[-1], target.position_m
    )
    bends = sum(
        first[3] != second[3] and first[3] != _NO_DIRECTION
        for first, second in zip(states, states[1:])
    )
    points = [source.position_m]
    for point in (*grid_points, target.position_m):
        if point != points[-1]:
            points.append(point)
    path_length = grid_length + connector_length
    length_cost = path_length * length_weight
    bend_cost = bends * bend_weight
    breakdown = CostBreakdown(
        grid_length_m=grid_length,
        connector_length_m=connector_length,
        path_length_m=path_length,
        length_cost=length_cost,
        bend_cost=bend_cost,
        total_objective_cost=length_cost + bend_cost,
    )
    return _return_result(
        RouteStatus.SUCCESS,
        grid.pipe_id,
        algorithm,
        started_at,
        expanded_states,
        grid_indices=indices,
        grid_points_m=grid_points,
        points_m=tuple(points),
        bend_count=bends,
        cost_breakdown=breakdown,
        applied_rule_ids=applied_rule_ids,
    )


def solve_route(
    project: EngineeringProject,
    pipe_id: str,
    *,
    algorithm: Algorithm = "astar",
    max_expansions: int | None = None,
    max_snap_distance_m: float | None = None,
    compilation: CompilationResult | None = None,
) -> RouteSearchResult:
    """Search physical free space, optionally including compiled hard rules.

    Search begins/ends at the snapped cell centres. Connector segments from
    the original ports are included in distance and cost, but their bends are
    not counted. The P05 validator must inspect the final continuous path.
    """
    started_at = perf_counter()
    if algorithm not in ("astar", "dijkstra"):
        return _return_result(
            RouteStatus.INVALID_INPUT,
            pipe_id,
            algorithm,
            started_at,
            message=f"unknown algorithm: {algorithm}",
        )
    limit = (
        project.routing_config.search_limits.max_expansions
        if max_expansions is None
        else max_expansions
    )
    weights = project.routing_config.cost_weights
    length_weight = weights.length_per_m
    bend_weight = weights.bend_per_event
    if (
        type(limit) is not int
        or limit <= 0
        or not isfinite(length_weight)
        or length_weight <= 0
        or not isfinite(bend_weight)
        or bend_weight < 0
    ):
        return _return_result(
            RouteStatus.INVALID_INPUT,
            pipe_id,
            algorithm,
            started_at,
            message="search limit and cost weights must be finite and nonnegative",
        )
    if max_snap_distance_m is not None and (
        not isfinite(max_snap_distance_m) or max_snap_distance_m < 0
    ):
        return _return_result(
            RouteStatus.INVALID_INPUT,
            pipe_id,
            algorithm,
            started_at,
            message="max_snap_distance_m must be finite and nonnegative",
        )
    pipe = next((item for item in project.pipes if item.id == pipe_id), None)
    if pipe is None:
        return _return_result(
            RouteStatus.INVALID_INPUT,
            pipe_id,
            algorithm,
            started_at,
            message=f"unknown pipe ID: {pipe_id}",
        )
    pending_rule_ids = sorted(
        rule.id
        for rule in project.constraints
        if rule.status is ConstraintStatus.APPROVED and pipe_id in rule.scope.pipe_ids
    )
    if compilation is None and pending_rule_ids:
        return _return_result(
            RouteStatus.RULES_NOT_COMPILED,
            pipe_id,
            algorithm,
            started_at,
            message=f"approved rules are not compiled: {', '.join(pending_rule_ids)}",
        )
    if compilation is not None:
        if (
            compilation.project_id != project.project_id
            or compilation.pipe_id != pipe_id
            or compilation.project_fingerprint != project_fingerprint(project)
        ):
            return _return_result(
                RouteStatus.INVALID_INPUT,
                pipe_id,
                algorithm,
                started_at,
                message="compilation does not match project or pipe",
            )
        if compilation.status is not CompilationStatus.SUCCESS:
            status = {
                CompilationStatus.UNAPPROVED_RULE: RouteStatus.UNAPPROVED_RULE,
                CompilationStatus.RULE_CONFLICT: RouteStatus.RULE_CONFLICT,
            }.get(compilation.status, RouteStatus.INVALID_INPUT)
            return _return_result(
                status, pipe_id, algorithm, started_at, message=compilation.message
            )
        if (
            compilation.grid is None
            or compilation.grid.pipe_id != pipe_id
            or compilation.applied_rule_ids != tuple(pending_rule_ids)
        ):
            return _return_result(
                RouteStatus.INVALID_INPUT,
                pipe_id,
                algorithm,
                started_at,
                message="compilation is incomplete for approved rules",
            )
        grid = compilation.grid
        applied_rule_ids = compilation.applied_rule_ids
    else:
        grid = voxelize_project(project, pipe_id)
        applied_rule_ids = ()
    source = _port_for_id(project, pipe.from_port_id)
    target = _port_for_id(project, pipe.to_port_id)
    try:
        start = grid.spec.world_to_grid(source.position_m)
        goal = grid.spec.world_to_grid(target.position_m)
    except ValueError as error:
        return _return_result(
            RouteStatus.INVALID_INPUT,
            pipe_id,
            algorithm,
            started_at,
            message=str(error),
        )
    if not grid.is_traversable(start) or not grid.is_traversable(goal):
        return _return_result(
            RouteStatus.INVALID_INPUT,
            pipe_id,
            algorithm,
            started_at,
            message="start or goal port snaps to a blocked cell",
        )
    snap_limit = (
        sqrt(3) * grid.spec.resolution_m / 2
        if max_snap_distance_m is None
        else max_snap_distance_m
    )
    start_centre = grid.spec.grid_to_world(start)
    goal_centre = grid.spec.grid_to_world(goal)
    if (
        dist(source.position_m, start_centre) > snap_limit + 1e-12
        or dist(target.position_m, goal_centre) > snap_limit + 1e-12
    ):
        return _return_result(
            RouteStatus.INVALID_INPUT,
            pipe_id,
            algorithm,
            started_at,
            message="port-to-cell snap distance exceeds tolerance",
        )

    start_state: State = (*start, _NO_DIRECTION)
    first_direction = _PORT_DIRECTIONS[source.orientation]
    arrival_direction = _PORT_DIRECTIONS[target.orientation] ^ 1
    sequence = count()
    frontier: list[tuple[float, float, int, State]] = []

    def heuristic(index: GridIndex) -> float:
        if algorithm == "dijkstra":
            return 0.0
        point = grid.spec.grid_to_world(index)
        return length_weight * sum(
            abs(left - right) for left, right in zip(point, goal_centre, strict=True)
        )

    heappush(frontier, (heuristic(start), 0.0, next(sequence), start_state))
    best_cost = {start_state: 0.0}
    previous: dict[State, State] = {}
    expanded = 0
    while frontier:
        _, cost, _, state = heappop(frontier)
        if cost > best_cost[state] + 1e-12:
            continue
        index = (state[0], state[1], state[2])
        if index == goal and (start == goal or state[3] == arrival_direction):
            return _result_for_path(
                state,
                previous,
                grid,
                source,
                target,
                length_weight,
                bend_weight,
                algorithm,
                started_at,
                expanded,
                applied_rule_ids,
            )
        if expanded >= limit:
            return _return_result(
                RouteStatus.SEARCH_LIMIT_REACHED,
                pipe_id,
                algorithm,
                started_at,
                expanded,
                "search expansion limit reached",
                applied_rule_ids=applied_rule_ids,
            )
        expanded += 1
        centre = grid.spec.grid_to_world(index)
        for direction, offset in enumerate(_DIRECTIONS):
            if state[3] == _NO_DIRECTION and direction != first_direction:
                continue
            neighbor = tuple(left + right for left, right in zip(index, offset))
            if not grid.is_traversable(neighbor):
                continue
            neighbor_centre = grid.spec.grid_to_world(neighbor)
            step_length = dist(centre, neighbor_centre)
            bend = int(state[3] != _NO_DIRECTION and direction != state[3])
            new_cost = cost + length_weight * step_length + bend_weight * bend
            next_state: State = (*neighbor, direction)
            if new_cost + 1e-12 >= best_cost.get(next_state, float("inf")):
                continue
            best_cost[next_state] = new_cost
            previous[next_state] = state
            heappush(
                frontier,
                (new_cost + heuristic(neighbor), new_cost, next(sequence), next_state),
            )
    return _return_result(
        RouteStatus.NO_PATH,
        pipe_id,
        algorithm,
        started_at,
        expanded,
        "no route exists in the compiled grid",
        applied_rule_ids=applied_rule_ids,
    )
