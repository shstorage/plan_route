"""Independent explicit-graph relaxation oracle for regular-grid cases.

No search, voxel, compiler, geometry, or cost helper is imported. Cells and
edge lengths are stated separately. Self-clearance is outside this
reference graph's objective, matching the declared exact-grid domain.
"""

from itertools import product
from math import isfinite

from plan_route.models.benchmark import ReferenceGraph, ReferenceResult

State = tuple[tuple[int, int, int], int, int]
MOVES = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def reference_cost(
    graph: ReferenceGraph, max_cells: int | None = None
) -> ReferenceResult:
    if len(graph.waypoints) != len(graph.waypoint_axes):
        raise ValueError("reference waypoint cells and axes must have equal length")
    cells = set(graph.cells)
    if graph.start not in cells or graph.goal not in cells:
        return ReferenceResult(status="NO_PATH")
    # An undirected disconnect proves no path even with direction/waypoint states.
    reached, pending = {graph.start}, [graph.start]
    while pending:
        position = pending.pop()
        for move in MOVES:
            neighbor = tuple(a + b for a, b in zip(position, move))
            if neighbor in cells and neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    if graph.goal not in reached:
        return ReferenceResult(status="NO_PATH")
    if max_cells is not None and len(cells) > max_cells:
        return ReferenceResult(status="NOT_COMPUTED")

    def progress(position: tuple[int, int, int], direction: int, count: int) -> int:
        while count < len(graph.waypoints) and position == graph.waypoints[count]:
            axis = graph.waypoint_axes[count]
            if axis is not None and direction // 2 != axis:
                break
            count += 1
        return count

    origin: State = (graph.start, -1, progress(graph.start, graph.departure, 0))
    states = [
        origin,
        *product(sorted(cells), range(6), range(len(graph.waypoints) + 1)),
    ]
    edges: list[tuple[State, State, float]] = []
    for position, incoming, count in states:
        for outgoing, move in enumerate(MOVES):
            if incoming == -1 and outgoing != graph.departure:
                continue
            if incoming >= 0 and outgoing == (incoming ^ 1):
                continue
            if (
                count
                and position == graph.waypoints[count - 1]
                and graph.waypoint_axes[count - 1] is not None
                and incoming >= 0
                and outgoing != incoming
            ):
                continue
            neighbor = tuple(a + b for a, b in zip(position, move))
            if neighbor not in cells:
                continue
            target: State = (neighbor, outgoing, progress(neighbor, outgoing, count))
            cost = graph.length_weight * graph.edge_length_m + graph.bend_weight * (
                incoming >= 0 and incoming != outgoing
            )
            edges.append(((position, incoming, count), target, cost))
    costs: dict[State, float] = {origin: 0.0}
    for _ in range(len(states) - 1):
        changed = False
        for left, right, weight in edges:
            candidate = costs.get(left, float("inf")) + weight
            if candidate < costs.get(right, float("inf")):
                costs[right] = candidate
                changed = True
        if not changed:
            break
    final: State = (graph.goal, graph.arrival, len(graph.waypoints))
    cost = (
        0.0
        if graph.start == graph.goal and origin[2] == len(graph.waypoints)
        else costs.get(final, float("inf"))
    )
    return (
        ReferenceResult(status="PATH", objective_cost=cost + graph.connector_cost)
        if isfinite(cost)
        else (ReferenceResult(status="NO_PATH"))
    )
