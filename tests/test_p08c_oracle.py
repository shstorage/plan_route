"""Small explicit graph oracle using relaxation, independent of search code."""

from itertools import product

import pytest

from plan_route.api.projects import load_demo_project
from plan_route.models.engineering import EngineeringProject
from plan_route.services.astar import solve_route


def oracle(waypoints, axis):
    # Analytically known interior: one z layer and nine XY cells. No voxelizer,
    # heuristic, frontier, parent map, or cost helper from the solver is used.
    moves = ((1, 0), (-1, 0), (0, 1), (0, -1))
    cells = set(product(range(1, 4), repeat=2))
    states = list(product(cells, range(4), range(len(waypoints) + 1)))
    source = ((1, 1), -1, 0)
    edges = []
    for position, incoming, visited in [source, *states]:
        for outgoing, (dx, dy) in enumerate(moves):
            if incoming == -1 and outgoing != 0:
                continue
            if incoming >= 0 and outgoing == (incoming ^ 1):
                continue
            if (
                visited
                and position == waypoints[visited - 1]
                and axis[visited - 1] is not None
                and outgoing != incoming
            ):
                continue
            neighbor = (position[0] + dx, position[1] + dy)
            if neighbor not in cells:
                continue
            progress = visited
            while progress < len(waypoints) and neighbor == waypoints[progress]:
                if axis[progress] is not None and outgoing // 2 != axis[progress]:
                    break
                progress += 1
            cost = 1 + (2 if incoming >= 0 and incoming != outgoing else 0)
            edges.append(
                ((position, incoming, visited), (neighbor, outgoing, progress), cost)
            )
    costs = {source: 0}
    for _ in range(len(states)):
        changed = False
        for left, right, weight in edges:
            candidate = costs.get(left, float("inf")) + weight
            if candidate < costs.get(right, float("inf")):
                costs[right] = candidate
                changed = True
        if not changed:
            break
    return costs.get(((3, 3), 2, len(waypoints)), float("inf"))


@pytest.mark.parametrize(
    "via,axes",
    [
        ([], []),
        ([(2, 1), (3, 2)], [0, 1]),
        ([(2, 1), (2, 1)], [0, 0]),
        ([(2, 2)], [None]),
    ],
)
def test_ordered_direction_search_matches_independent_explicit_graph(via, axes):
    data = load_demo_project().model_dump(mode="json")
    data["building"] = {
        "bounds_m": {"min_m": [0, 0, 0], "max_m": [5, 5, 3]},
        "floors": [{"id": "F1", "z_min_m": 0, "z_max_m": 3}],
    }
    data.update(obstacles=[], zones=[], constraints=[])
    data["equipment"][0]["ports"][0].update(
        position_m=[1.5, 1.5, 1.5], orientation="+x"
    )
    data["equipment"][1]["ports"][0].update(
        position_m=[3.5, 3.5, 1.5], orientation="-y"
    )
    data["routing_config"]["grid_resolution_m"] = 1.0
    data["pipes"][0]["waypoints"] = [
        {
            "id": f"WP-{index}",
            "position_m": [x + 0.5, y + 0.5, 1.5],
            "pass_axis": None if axis is None else "xy"[axis],
        }
        for index, ((x, y), axis) in enumerate(zip(via, axes))
    ]
    project = EngineeringProject.model_validate(data)
    expected = oracle(via, axes)
    for algorithm in ("astar", "dijkstra"):
        result = solve_route(project, "PIPE-101", algorithm=algorithm)
        assert result.search_mode == "EXACT_GRID"
        assert result.cost_breakdown.total_objective_cost == expected
