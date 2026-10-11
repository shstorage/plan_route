"""P03 search correctness, failure-state and cost tests."""

import copy
import json
from importlib.resources import files
from math import isclose

import pytest

from plan_route.api.projects import load_demo_project
from plan_route.models.constraints import ConstraintStatus
from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteStatus
from plan_route.services.astar import solve_route


@pytest.fixture
def open_project_data():
    path = files("plan_route").joinpath("fixtures/demo_project.json")
    data = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    data["building"]["bounds_m"]["max_m"] = [5, 5, 3]
    data["building"]["floors"][0]["z_max_m"] = 3
    data["obstacles"] = []
    data["zones"] = []
    data["constraints"] = []
    data["equipment"][0]["ports"][0]["position_m"] = [1.5, 1.5, 1.5]
    data["equipment"][0]["ports"][0]["orientation"] = "+x"
    data["equipment"][1]["ports"][0]["position_m"] = [3.5, 1.5, 1.5]
    data["equipment"][1]["ports"][0]["orientation"] = "-x"
    data["pipes"][0]["outer_diameter_m"] = 0.1
    data["pipes"][0]["insulation_thickness_m"] = 0
    data["routing_config"]["grid_resolution_m"] = 1
    data["routing_config"]["cost_weights"]["length_per_m"] = 1
    data["routing_config"]["cost_weights"]["bend_per_event"] = 2
    return data


def _solve(data, **kwargs):
    project = EngineeringProject.model_validate(data)
    return solve_route(project, "PIPE-101", **kwargs)


@pytest.mark.parametrize("algorithm", ["astar", "dijkstra"])
def test_straight_route_known_optimum(open_project_data, algorithm):
    result = _solve(open_project_data, algorithm=algorithm)
    assert result.status is RouteStatus.SUCCESS
    assert result.grid_indices == ((1, 1, 1), (2, 1, 1), (3, 1, 1))
    assert result.points_m == ((1.5, 1.5, 1.5), (2.5, 1.5, 1.5), (3.5, 1.5, 1.5))
    assert result.bend_count == 0
    assert result.cost_breakdown.path_length_m == 2
    assert result.cost_breakdown.length_cost == 2
    assert result.cost_breakdown.bend_cost == 0
    assert result.cost_breakdown.total_objective_cost == 2
    assert result.expanded_states > 0
    assert result.runtime_ms >= 0


def test_one_bend_cost_and_dijkstra_agree(open_project_data):
    open_project_data["equipment"][1]["ports"][0]["position_m"] = [3.5, 3.5, 1.5]
    open_project_data["equipment"][1]["ports"][0]["orientation"] = "-y"
    astar = _solve(open_project_data)
    dijkstra = _solve(open_project_data, algorithm="dijkstra")
    for result in (astar, dijkstra):
        assert result.status is RouteStatus.SUCCESS
        assert result.bend_count == 1
        assert result.cost_breakdown.grid_length_m == 4
        assert result.cost_breakdown.bend_cost == 2
        assert result.cost_breakdown.total_objective_cost == 6
        assert result.grid_indices[0] == (1, 1, 1)
        assert result.grid_indices[-1] == (3, 3, 1)
        assert result.grid_indices[1] == (2, 1, 1)  # Source port faces +x.
        assert result.grid_indices[-2] == (3, 2, 1)  # Target port faces -y.


def test_cost_matches_exhaustive_simple_paths(open_project_data):
    """A small exhaustive oracle avoids relying on either search implementation."""
    open_project_data["equipment"][1]["ports"][0]["position_m"] = [3.5, 3.5, 1.5]
    open_project_data["equipment"][1]["ports"][0]["orientation"] = "-y"
    moves = ((1, 0), (-1, 0), (0, 1), (0, -1))
    costs = []

    def walk(position, previous_direction, visited, steps, bends):
        if position == (3, 3):
            if previous_direction == 2:  # Enter goal along +y.
                costs.append(steps + 2 * bends)
            return
        for direction, offset in enumerate(moves):
            if previous_direction is None and direction != 0:  # Start port +x.
                continue
            neighbor = (position[0] + offset[0], position[1] + offset[1])
            if not all(1 <= value <= 3 for value in neighbor):
                continue
            if neighbor in visited:
                continue
            walk(
                neighbor,
                direction,
                visited | {neighbor},
                steps + 1,
                bends
                + int(
                    previous_direction is not None and previous_direction != direction
                ),
            )

    walk((1, 1), None, {(1, 1)}, 0, 0)
    assert min(costs) == 6
    assert _solve(open_project_data).cost_breakdown.total_objective_cost == min(costs)
    assert _solve(
        open_project_data, algorithm="dijkstra"
    ).cost_breakdown.total_objective_cost == min(costs)


def test_bend_weight_changes_reported_optimum(open_project_data):
    open_project_data["equipment"][1]["ports"][0]["position_m"] = [3.5, 3.5, 1.5]
    open_project_data["equipment"][1]["ports"][0]["orientation"] = "-y"
    low = _solve(open_project_data)
    open_project_data["routing_config"]["cost_weights"]["bend_per_event"] = 9
    high = _solve(open_project_data)
    assert low.status is high.status is RouteStatus.SUCCESS
    assert low.bend_count == high.bend_count == 1
    assert low.cost_breakdown.total_objective_cost == 6
    assert high.cost_breakdown.total_objective_cost == 13


def test_obstacle_detour_has_expected_cost(open_project_data):
    open_project_data["obstacles"] = [
        {
            "id": "BLOCK-01",
            "kind": "wall",
            "shape": {
                "type": "aabb",
                "min_m": [2.2, 1.2, 1.2],
                "max_m": [2.8, 1.8, 1.8],
            },
        }
    ]
    open_project_data["equipment"][0]["ports"][0]["orientation"] = "+y"
    open_project_data["equipment"][1]["ports"][0]["orientation"] = "+y"
    astar = _solve(open_project_data)
    dijkstra = _solve(open_project_data, algorithm="dijkstra")
    for result in (astar, dijkstra):
        assert result.status is RouteStatus.SUCCESS
        assert (2, 1, 1) not in result.grid_indices
        assert result.grid_indices[1] == (1, 2, 1)
        assert result.grid_indices[-2] == (3, 2, 1)
        assert result.cost_breakdown.path_length_m == 4
        assert result.bend_count == 2
        assert result.cost_breakdown.total_objective_cost == 8


def test_complete_wall_is_no_path_not_search_limit(open_project_data):
    open_project_data["obstacles"] = [
        {
            "id": "WALL-ALL",
            "kind": "wall",
            "shape": {"type": "aabb", "min_m": [2.2, 0, 0], "max_m": [2.8, 5, 3]},
        }
    ]
    result = _solve(open_project_data)
    assert result.status is RouteStatus.NO_PATH
    assert result.cost_breakdown is None
    assert result.grid_indices == ()
    assert result.expanded_states > 0


def test_expansion_budget_is_distinct_from_no_path(open_project_data):
    limited = _solve(open_project_data, max_expansions=1)
    assert limited.status is RouteStatus.SEARCH_LIMIT_REACHED
    assert limited.expanded_states == 1
    assert limited.cost_breakdown is None
    enough = _solve(open_project_data, max_expansions=2)
    assert enough.status is RouteStatus.SUCCESS
    assert enough.expanded_states == 2


def test_same_cell_and_connector_cost(open_project_data):
    open_project_data["equipment"][0]["ports"][0]["position_m"] = [1.25, 1.25, 1.5]
    open_project_data["equipment"][1]["ports"][0]["position_m"] = [1.75, 1.75, 1.5]
    result = _solve(open_project_data)
    assert result.status is RouteStatus.SUCCESS
    assert result.grid_indices == ((1, 1, 1),)
    assert result.bend_count == 0
    assert result.cost_breakdown.grid_length_m == 0
    assert isclose(result.cost_breakdown.connector_length_m, 2**0.5 / 2)
    assert result.cost_breakdown.length_cost == result.cost_breakdown.path_length_m
    assert result.points_m[0] == (1.25, 1.25, 1.5)
    assert result.points_m[-1] == (1.75, 1.75, 1.5)


def test_offcentre_ports_are_included_in_length_and_cost(open_project_data):
    open_project_data["equipment"][0]["ports"][0]["position_m"] = [1.2, 1.5, 1.5]
    open_project_data["equipment"][1]["ports"][0]["position_m"] = [3.8, 1.5, 1.5]
    result = _solve(open_project_data)
    assert result.status is RouteStatus.SUCCESS
    assert isclose(result.cost_breakdown.connector_length_m, 0.6)
    assert isclose(result.cost_breakdown.path_length_m, 2.6)
    assert isclose(result.cost_breakdown.total_objective_cost, 2.6)


@pytest.mark.parametrize(
    ("change", "kwargs", "expected_message"),
    [
        (None, {"max_expansions": 0}, "search limit"),
        (None, {"max_snap_distance_m": -1}, "max_snap_distance_m"),
        (None, {"max_snap_distance_m": 0.1}, "snap distance"),
        ("blocked_start", {}, "blocked cell"),
        ("outside_goal", {}, "outside grid bounds"),
    ],
)
def test_invalid_input_status(open_project_data, change, kwargs, expected_message):
    if change == "blocked_start":
        open_project_data["obstacles"] = [
            {
                "id": "BLOCK-START",
                "kind": "wall",
                "shape": {
                    "type": "aabb",
                    "min_m": [1.2, 1.2, 1.2],
                    "max_m": [1.8, 1.8, 1.8],
                },
            }
        ]
    elif change == "outside_goal":
        open_project_data["equipment"][1]["ports"][0]["position_m"] = [5, 1.5, 1.5]
    elif "max_snap_distance_m" in kwargs and kwargs["max_snap_distance_m"] == 0.1:
        open_project_data["equipment"][0]["ports"][0]["position_m"] = [1.2, 1.5, 1.5]
    result = _solve(open_project_data, **kwargs)
    assert result.status is RouteStatus.INVALID_INPUT
    assert expected_message in result.message
    assert result.cost_breakdown is None


def test_unknown_pipe_and_negative_cost_are_invalid(open_project_data):
    project = EngineeringProject.model_validate(open_project_data)
    result = solve_route(project, "MISSING")
    assert result.status is RouteStatus.INVALID_INPUT
    assert "unknown pipe" in result.message

    # model_copy can bypass Pydantic validation; the solver still rejects it.
    bad_weights = project.routing_config.cost_weights.model_copy(
        update={"bend_per_event": -1.0}
    )
    bad_config = project.routing_config.model_copy(update={"cost_weights": bad_weights})
    bad_project = project.model_copy(update={"routing_config": bad_config})
    assert solve_route(bad_project, "PIPE-101").status is RouteStatus.INVALID_INPUT

    unknown_algorithm = solve_route(project, "PIPE-101", algorithm="unknown")
    assert unknown_algorithm.status is RouteStatus.INVALID_INPUT
    assert unknown_algorithm.algorithm == "unknown"


def test_port_orientation_can_make_route_infeasible(open_project_data):
    open_project_data["equipment"][0]["ports"][0]["orientation"] = "-x"
    result = _solve(open_project_data)
    assert result.status is RouteStatus.NO_PATH


def test_approved_rule_is_not_silently_ignored():
    result = solve_route(load_demo_project(), "PIPE-101")
    assert result.status is RouteStatus.RULES_NOT_COMPILED
    assert "RULE-001" in result.message
    assert result.cost_breakdown is None


def test_unapproved_rule_is_never_applied():
    project = load_demo_project()
    rule = project.constraints[0].model_copy(update={"status": ConstraintStatus.DRAFT})
    draft_project = project.model_copy(update={"constraints": [rule]})
    result = solve_route(draft_project, "PIPE-101")
    assert result.status is RouteStatus.SUCCESS
