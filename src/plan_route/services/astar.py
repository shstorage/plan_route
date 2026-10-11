"""Direction-aware deterministic 6-neighbour A* and Dijkstra grid search.

A search state is (i, j, k, incoming direction, visited waypoint count). The
waypoint count makes ordered mandatory waypoints part of one exact search, so
the returned route is optimal over the whole sequence, not leg by leg.

That exact search does not remember which cells it already used, so with
waypoints it can fold back beside (or onto) itself. When the found route comes
closer to itself than one envelope diameter, legs are searched again one at a
time, each avoiding the cells around the legs already laid; that route is
feasible more often but no longer guaranteed optimal.
"""

from heapq import heappop, heappush
from itertools import count
from math import ceil, dist, isfinite, pi, sqrt
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
from plan_route.services.geometry import effective_pipe_radius_m
from plan_route.services.voxel_grid import VoxelGrid, voxelize_project

Algorithm = Literal["astar", "dijkstra"]
State = tuple[int, int, int, int, int]
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
_AXES = {"x": 0, "y": 1, "z": 2}


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


def _chain(final_state: State, previous: dict[State, State]) -> list[State]:
    states = [final_state]
    while states[-1] in previous:
        states.append(previous[states[-1]])
    states.reverse()
    return states


def _self_conflicts(grid: VoxelGrid, states: list[State], radius: float) -> bool:
    """True if two parts of the route come within one envelope diameter.

    Pairs whose separation along the route is at most pi x radius (elbows,
    offsets) are exempt, mirroring the validator's SELF_CLEARANCE rule.
    """
    points = [grid.spec.grid_to_world(state[:3]) for state in states]
    arcs = [0.0]
    for first, second in zip(points, points[1:]):
        arcs.append(arcs[-1] + dist(first, second))
    reach = 2 * radius + 1e-9
    step = grid.spec.resolution_m
    span = max(1, ceil(reach / step))
    buckets: dict[GridIndex, list[int]] = {}
    for position, state in enumerate(states):
        index = state[:3]
        for di in range(-span, span + 1):
            for dj in range(-span, span + 1):
                for dk in range(-span, span + 1):
                    for other in buckets.get(
                        (index[0] + di, index[1] + dj, index[2] + dk), ()
                    ):
                        if (
                            arcs[position] - arcs[other] > pi * radius + 1e-9
                            and dist(points[position], points[other]) <= reach
                        ):
                            return True
        buckets.setdefault(index, []).append(position)
    return False


def _avoid_cells(grid: VoxelGrid, laid: list[State], radius: float) -> set[GridIndex]:
    """Cells a new leg starting at the end of ``laid`` may not enter.

    A cell is blocked if it lies within one envelope diameter of a laid cell
    and even the shortest continuation from the junction would be more than
    pi x radius along the route away from that cell (so the pair would be a
    self-clearance conflict, not an elbow).
    """
    points = [grid.spec.grid_to_world(state[:3]) for state in laid]
    arcs = [0.0]
    for first, second in zip(points, points[1:]):
        arcs.append(arcs[-1] + dist(first, second))
    junction = points[-1]
    reach = 2 * radius + 1e-9
    step = grid.spec.resolution_m
    span = max(1, ceil(reach / step))
    blocked: set[GridIndex] = set()
    for state, point, arc in zip(laid, points, arcs):
        behind = arcs[-1] - arc
        for di in range(-span, span + 1):
            for dj in range(-span, span + 1):
                for dk in range(-span, span + 1):
                    cell = (state[0] + di, state[1] + dj, state[2] + dk)
                    if cell in blocked or not grid.spec.contains_index(cell):
                        continue
                    centre = grid.spec.grid_to_world(cell)
                    if dist(centre, point) > reach:
                        continue
                    ahead = sum(
                        abs(a - b) for a, b in zip(centre, junction, strict=True)
                    )
                    if behind + ahead > pi * radius + 1e-9:
                        blocked.add(cell)
    return blocked


def _result_for_path(
    states: list[State],
    grid: VoxelGrid,
    source: Port,
    target: Port,
    length_weight: float,
    bend_weight: float,
    algorithm: Algorithm,
    started_at: float,
    expanded_states: int,
    applied_rule_ids: tuple[str, ...],
    message: str = "",
) -> RouteSearchResult:
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
        message,
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

    waypoint_cells: list[GridIndex] = []
    waypoint_axes: list[int | None] = []
    for waypoint in pipe.waypoints:
        try:
            cell = grid.spec.world_to_grid(waypoint.position_m)
        except ValueError as error:
            return _return_result(
                RouteStatus.INVALID_INPUT,
                pipe_id,
                algorithm,
                started_at,
                message=f"waypoint {waypoint.id}: {error}",
            )
        snap = dist(waypoint.position_m, grid.spec.grid_to_world(cell))
        if snap > snap_limit + 1e-12:
            return _return_result(
                RouteStatus.INVALID_INPUT,
                pipe_id,
                algorithm,
                started_at,
                message=f"waypoint {waypoint.id} snap distance exceeds tolerance",
            )
        if not grid.is_traversable(cell):
            return _return_result(
                RouteStatus.WAYPOINT_BLOCKED,
                pipe_id,
                algorithm,
                started_at,
                message=(
                    f"waypoint {waypoint.id} lies in a cell blocked by an obstacle, "
                    "the building boundary, or an approved hard rule for this pipe"
                ),
                applied_rule_ids=applied_rule_ids,
            )
        waypoint_cells.append(cell)
        waypoint_axes.append(
            None if waypoint.pass_axis is None else _AXES[waypoint.pass_axis]
        )
    waypoint_count = len(waypoint_cells)
    # Lower bound of the remaining length after reaching waypoint i: the
    # Manhattan chain through every later waypoint and on to the goal.
    chain_centres = [grid.spec.grid_to_world(cell) for cell in waypoint_cells]
    chain_centres.append(goal_centre)
    remaining_chain = [0.0] * (waypoint_count + 1)
    for position in range(waypoint_count - 1, -1, -1):
        remaining_chain[position] = remaining_chain[position + 1] + sum(
            abs(left - right)
            for left, right in zip(
                chain_centres[position], chain_centres[position + 1], strict=True
            )
        )

    def advance(index: GridIndex, direction: int, visited: int) -> int:
        """Count every next waypoint satisfied by entering ``index``."""
        while visited < waypoint_count and index == waypoint_cells[visited]:
            axis = waypoint_axes[visited]
            if axis is not None and (
                direction == _NO_DIRECTION or direction // 2 != axis
            ):
                break
            visited += 1
        return visited

    def locked_direction(index: GridIndex, direction: int, visited: int) -> bool:
        """A pass-through waypoint was just satisfied here: no bend allowed."""
        return (
            visited > 0
            and direction != _NO_DIRECTION
            and index == waypoint_cells[visited - 1]
            and waypoint_axes[visited - 1] is not None
        )

    start_state: State = (*start, _NO_DIRECTION, advance(start, _NO_DIRECTION, 0))
    first_direction = _PORT_DIRECTIONS[source.orientation]
    arrival_direction = _PORT_DIRECTIONS[target.orientation] ^ 1

    def heuristic(index: GridIndex, visited: int, stop: int | None) -> float:
        if algorithm == "dijkstra":
            return 0.0
        point = grid.spec.grid_to_world(index)
        next_centre = chain_centres[visited]
        return length_weight * (
            sum(
                abs(left - right)
                for left, right in zip(point, next_centre, strict=True)
            )
            + (remaining_chain[visited] if stop is None else 0.0)
        )

    def search(
        origin: State, stop: int | None, blocked: set[GridIndex], budget: int
    ) -> tuple[str, list[State], int]:
        """A* from ``origin``; stop on reaching waypoint count ``stop`` or the goal.

        Returns ("found" | "limit" | "none", states from origin, expansions).
        """
        sequence = count()
        frontier: list[tuple[float, float, int, State]] = [
            (heuristic(origin[:3], origin[4], stop), 0.0, next(sequence), origin)
        ]
        best_cost = {origin: 0.0}
        previous: dict[State, State] = {}
        expanded = 0
        while frontier:
            _, cost, _, state = heappop(frontier)
            if cost > best_cost[state] + 1e-12:
                continue
            index = (state[0], state[1], state[2])
            if stop is not None:
                if state[4] >= stop:
                    return "found", _chain(state, previous), expanded
            elif (
                index == goal
                and state[4] == waypoint_count
                and (start == goal or state[3] == arrival_direction)
            ):
                return "found", _chain(state, previous), expanded
            if expanded >= budget:
                return "limit", [], expanded
            expanded += 1
            centre = grid.spec.grid_to_world(index)
            for direction, offset in enumerate(_DIRECTIONS):
                if state[3] == _NO_DIRECTION and direction != first_direction:
                    continue
                if direction != state[3] and locked_direction(
                    index, state[3], state[4]
                ):
                    continue
                neighbor = tuple(left + right for left, right in zip(index, offset))
                if neighbor in blocked or not grid.is_traversable(neighbor):
                    continue
                neighbor_centre = grid.spec.grid_to_world(neighbor)
                step_length = dist(centre, neighbor_centre)
                bend = int(state[3] != _NO_DIRECTION and direction != state[3])
                new_cost = cost + length_weight * step_length + bend_weight * bend
                next_state: State = (
                    *neighbor,
                    direction,
                    advance(neighbor, direction, state[4]),
                )
                if new_cost + 1e-12 >= best_cost.get(next_state, float("inf")):
                    continue
                best_cost[next_state] = new_cost
                previous[next_state] = state
                heappush(
                    frontier,
                    (
                        new_cost + heuristic(neighbor, next_state[4], stop),
                        new_cost,
                        next(sequence),
                        next_state,
                    ),
                )
        return "none", [], expanded

    def finish(
        states: list[State], expanded: int, message: str = ""
    ) -> RouteSearchResult:
        return _result_for_path(
            states,
            grid,
            source,
            target,
            length_weight,
            bend_weight,
            algorithm,
            started_at,
            expanded,
            applied_rule_ids,
            message,
        )

    outcome, states, expanded = search(start_state, None, set(), limit)
    if outcome == "limit":
        return _return_result(
            RouteStatus.SEARCH_LIMIT_REACHED,
            pipe_id,
            algorithm,
            started_at,
            expanded,
            "search expansion limit reached",
            applied_rule_ids=applied_rule_ids,
        )
    if outcome == "none":
        return _return_result(
            RouteStatus.NO_PATH,
            pipe_id,
            algorithm,
            started_at,
            expanded,
            "no route exists in the compiled grid",
            applied_rule_ids=applied_rule_ids,
        )
    radius = effective_pipe_radius_m(pipe)
    if not waypoint_count or not _self_conflicts(grid, states, radius):
        return finish(states, expanded)

    # The optimal sequence folds back onto itself: lay the legs one by one,
    # each avoiding the envelope of the legs already laid.
    laid = [start_state]
    total = expanded
    while True:
        origin = laid[-1]
        stop = None if origin[4] >= waypoint_count else origin[4] + 1
        blocked = _avoid_cells(grid, laid, radius) if len(laid) > 1 else set()
        leg_outcome, leg, used = search(origin, stop, blocked, limit - total)
        total += used
        if leg_outcome != "found":
            reason = (
                "the search limit was reached"
                if leg_outcome == "limit"
                else "no leg avoided the earlier legs"
            )
            return finish(
                states,
                total,
                "route legs overlap and leg-by-leg re-search failed "
                f"({reason}); returning the overlapping optimal route",
            )
        laid.extend(leg[1:])
        if stop is None:
            break
    return finish(
        laid,
        total,
        "route legs overlapped; legs were re-searched one at a time avoiding "
        "earlier legs (no longer guaranteed optimal over the sequence)",
    )
