"""Ordered mandatory waypoints: schema, exact search, and independent checks."""

import json
from importlib.resources import files
from math import isclose

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from plan_route.main import app
from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteStatus, ValidationStatus
from plan_route.services.astar import solve_route
from plan_route.services.path_validator import validate_path
from plan_route.services.routing import route_project

START = (1.25, 1.25, 1.25)
GOAL = (6.75, 1.25, 1.25)
SLEEVE = (3.75, 4.75, 2.25)


@pytest.fixture
def open_data():
    """8 x 6 x 4 m empty room, 0.5 m grid, ports facing each other."""
    data = json.loads(
        files("plan_route")
        .joinpath("fixtures/demo_project.json")
        .read_text(encoding="utf-8")
    )
    data["building"]["bounds_m"]["max_m"] = [8, 6, 4]
    data["obstacles"] = []
    data["zones"] = []
    data["constraints"] = []
    data["equipment"][0]["ports"][0]["position_m"] = list(START)
    data["equipment"][1]["ports"][0]["position_m"] = list(GOAL)
    data["routing_config"]["grid_resolution_m"] = 0.5
    return data


def wall_with_door_and_sleeve() -> list[dict]:
    """A wall at x 3.5-4.0 with a low door (y 0-2) and a high sleeve (y 4-5.5).

    Without guidance the shortest route uses the door; the sleeve is the
    planned penetration that the pipe must use.
    """

    def box(name, low, high):
        return {
            "id": name,
            "kind": "wall",
            "shape": {"type": "aabb", "min_m": low, "max_m": high},
        }

    return [
        box("WALL-DOOR-HEAD", [3.5, 0, 2.5], [4, 2, 4]),
        box("WALL-MID", [3.5, 2, 0], [4, 4, 4]),
        box("WALL-SLEEVE-LOW", [3.5, 4, 0], [4, 5.5, 1.5]),
        box("WALL-SLEEVE-HIGH", [3.5, 4, 3], [4, 5.5, 4]),
        box("WALL-NORTH", [3.5, 5.5, 0], [4, 6, 4]),
    ]


def waypoint(name, position, axis=None, note=None):
    item = {"id": name, "position_m": list(position)}
    if axis:
        item["pass_axis"] = axis
    if note:
        item["note"] = note
    return item


def solve(data, **kwargs):
    return route_project(EngineeringProject.model_validate(data), "PIPE-101", **kwargs)


def first_index(points, target):
    return next(index for index, point in enumerate(points) if point == target)


def test_pipe_without_waypoints_is_unchanged(open_data):
    project = EngineeringProject.model_validate(open_data)
    assert project.pipes[0].waypoints == []
    assert (
        "waypoints"
        not in json.loads(
            files("plan_route")
            .joinpath("fixtures/demo_project.json")
            .read_text("utf-8")
        )["pipes"][0]
    )
    assert route_project(project, "PIPE-101").status is RouteStatus.SUCCESS


def test_route_visits_waypoints_in_the_given_order(open_data):
    first, second = (2.25, 4.75, 1.25), (5.75, 4.75, 2.75)
    open_data["pipes"][0]["waypoints"] = [
        waypoint("WP-1", first),
        waypoint("WP-2", second),
    ]
    report = solve(open_data)
    assert report.status is RouteStatus.SUCCESS, report.message
    assert report.validation.status is ValidationStatus.VALID
    points = [tuple(point) for point in report.points_m]
    assert first_index(points, first) < first_index(points, second)
    direct = solve({**open_data, "pipes": [{**open_data["pipes"][0], "waypoints": []}]})
    assert report.cost_breakdown.path_length_m > direct.cost_breakdown.path_length_m

    open_data["pipes"][0]["waypoints"] = [
        waypoint("WP-2", second),
        waypoint("WP-1", first),
    ]
    reversed_report = solve(open_data)
    assert reversed_report.status is RouteStatus.SUCCESS
    points = [tuple(point) for point in reversed_report.points_m]
    assert first_index(points, second) < first_index(points, first)
    assert (
        reversed_report.cost_breakdown.total_objective_cost
        > report.cost_breakdown.total_objective_cost
    )


def test_waypoint_astar_matches_dijkstra_optimum(open_data):
    open_data["obstacles"] = wall_with_door_and_sleeve()
    open_data["pipes"][0]["waypoints"] = [
        waypoint("WP-1", (2.25, 4.25, 3.25)),
        waypoint("WP-2", SLEEVE, "x"),
        waypoint("WP-3", (6.25, 2.75, 0.75)),
    ]
    project = EngineeringProject.model_validate(open_data)
    astar = solve_route(project, "PIPE-101")
    dijkstra = solve_route(project, "PIPE-101", algorithm="dijkstra")
    assert astar.status is dijkstra.status is RouteStatus.SUCCESS
    assert isclose(
        astar.cost_breakdown.total_objective_cost,
        dijkstra.cost_breakdown.total_objective_cost,
    )
    assert astar.expanded_states <= dijkstra.expanded_states


def test_sleeve_waypoint_forces_straight_pass_through_planned_penetration(open_data):
    open_data["obstacles"] = wall_with_door_and_sleeve()
    unguided = solve(open_data)
    assert unguided.status is RouteStatus.SUCCESS
    assert all(point[1] < 2 for point in unguided.points_m), "uses the door"

    open_data["pipes"][0]["waypoints"] = [
        waypoint("SLEEVE-1", SLEEVE, "x", note="synthetic sleeve from civil drawing")
    ]
    report = solve(open_data)
    assert report.status is RouteStatus.SUCCESS, report.message
    assert report.validation.status is ValidationStatus.VALID
    points = [tuple(point) for point in report.points_m]
    at = first_index(points, SLEEVE)
    before, after = points[at - 1], points[at + 1]
    # Straight along x on both sides of the sleeve centre.
    assert before[1:] == SLEEVE[1:] == after[1:]
    assert before[0] < SLEEVE[0] < after[0]


def test_pass_axis_that_cannot_be_satisfied_is_no_path(open_data):
    # The top cell row touches the ceiling and is blocked, so a vertical pass
    # through the row below cannot continue: a valid input with no route.
    open_data["pipes"][0]["waypoints"] = [waypoint("WP-TOP", (4.25, 3.25, 3.75), "z")]
    assert solve(open_data).status is RouteStatus.WAYPOINT_BLOCKED
    open_data["pipes"][0]["waypoints"] = [waypoint("WP-TOP", (4.25, 3.25, 3.25), "z")]
    assert solve(open_data).status is RouteStatus.NO_PATH
    open_data["pipes"][0]["waypoints"][0]["pass_axis"] = "y"
    assert solve(open_data).status is RouteStatus.SUCCESS


def test_blocked_waypoint_is_an_explicit_failure(open_data):
    open_data["obstacles"] = wall_with_door_and_sleeve()
    open_data["pipes"][0]["waypoints"] = [waypoint("WP-IN-WALL", (3.75, 3.25, 1.25))]
    report = solve(open_data)
    assert report.status is RouteStatus.WAYPOINT_BLOCKED
    assert "WP-IN-WALL" in report.message
    assert report.points_m == []
    with TestClient(app) as client:
        response = client.post(
            "/api/routing/solve", json={"project": open_data, "pipe_id": "PIPE-101"}
        )
    assert response.status_code == 409
    assert response.json()["status"] == "WAYPOINT_BLOCKED"


def test_waypoint_inside_approved_keep_out_zone_is_blocked(open_data):
    demo = json.loads(
        files("plan_route")
        .joinpath("fixtures/demo_project.json")
        .read_text(encoding="utf-8")
    )
    open_data["zones"] = [
        {
            "id": "ZONE-A",
            "zone_type": "restricted",
            "shape": {"type": "aabb", "min_m": [5, 3, 0], "max_m": [7, 5, 4]},
        }
    ]
    open_data["constraints"] = demo["constraints"]
    open_data["pipes"][0]["waypoints"] = [waypoint("WP-ZONE", (6.25, 4.25, 1.25))]
    report = solve(open_data)
    assert report.status is RouteStatus.WAYPOINT_BLOCKED
    assert report.applied_rule_ids == ["RULE-001"]
    open_data["constraints"][0]["status"] = "draft"
    assert solve(open_data).status is RouteStatus.UNAPPROVED_RULE


def test_search_limit_with_waypoints(open_data):
    open_data["pipes"][0]["waypoints"] = [waypoint("WP-1", (4.25, 4.75, 1.25))]
    assert solve(open_data, max_expansions=3).status is RouteStatus.SEARCH_LIMIT_REACHED


def test_source_goal_and_duplicate_cell_waypoints_have_one_sided_passes(open_data):
    open_data["pipes"][0]["waypoints"] = [
        waypoint("WP-S", START, "x"),
        waypoint("WP-S2", START, "x"),
        waypoint("WP-E", GOAL, "x"),
    ]
    report = solve(open_data)
    assert report.status == "SUCCESS", report.message
    assert report.search_mode == "EXACT_GRID"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda wp: wp.update(position_m=[9, 1, 1]), "outside building"),
        (lambda wp: wp.update(id="PORT-A"), "duplicate ID"),
        (lambda wp: wp.update(pass_axis="w"), "pass_axis"),
        (lambda wp: wp.update(position_m=[1, 1]), "position_m"),
        (lambda wp: wp.update(extra=1), "extra"),
    ],
)
def test_invalid_waypoints_are_rejected_by_the_schema(open_data, change, message):
    item = waypoint("WP-1", (4.25, 4.75, 1.25))
    change(item)
    open_data["pipes"][0]["waypoints"] = [item]
    with pytest.raises(ValidationError, match=message):
        EngineeringProject.model_validate(open_data)


def test_duplicate_waypoint_ids_across_pipes_are_rejected(open_data):
    second = {**open_data["pipes"][0], "id": "PIPE-102"}
    open_data["pipes"][0]["waypoints"] = [waypoint("WP-1", (4.25, 4.75, 1.25))]
    second["waypoints"] = [waypoint("WP-1", (4.25, 4.75, 1.25))]
    open_data["pipes"].append(second)
    with pytest.raises(ValidationError, match="duplicate ID WP-1"):
        EngineeringProject.model_validate(open_data)


def test_validator_checks_waypoint_order_and_direction_on_continuous_path(open_data):
    # These manually supplied polylines arrive along -y, so the port faces +y.
    open_data["equipment"][1]["ports"][0]["orientation"] = "+y"
    first, second = (2.25, 4.75, 1.25), (5.75, 4.75, 1.25)
    open_data["pipes"][0]["waypoints"] = [
        waypoint("WP-1", first),
        waypoint("WP-2", second),
    ]
    project = EngineeringProject.model_validate(open_data)

    in_order = (START, (2.25, 1.25, 1.25), first, second, (6.75, 4.75, 1.25), GOAL)
    assert validate_path(project, "PIPE-101", in_order).status is ValidationStatus.VALID

    skipped = (START, (2.25, 1.25, 1.25), first, (2.25, 1.25, 1.25), GOAL)
    result = validate_path(project, "PIPE-101", skipped)
    assert [
        (item.code, item.object_id)
        for item in result.violations
        if item.code.startswith("WAYPOINT")
    ] == [("WAYPOINT_MISSED", "WP-2")]

    wrong_order = (
        START,
        (5.75, 1.25, 1.25),
        second,
        first,
        (2.25, 3.0, 1.25),
        (6.75, 3.0, 1.25),
        GOAL,
    )
    result = validate_path(project, "PIPE-101", wrong_order)
    assert [
        (item.code, item.object_id)
        for item in result.violations
        if item.code.startswith("WAYPOINT")
    ] == [("WAYPOINT_MISSED", "WP-2")]

    open_data["pipes"][0]["waypoints"] = [waypoint("WP-1", first, "y")]
    project = EngineeringProject.model_validate(open_data)
    straight = (START, (2.25, 1.25, 1.25), (2.25, 5.25, 1.25), (6.75, 5.25, 1.25), GOAL)
    assert validate_path(project, "PIPE-101", straight).status is ValidationStatus.VALID
    bent = (START, (2.25, 1.25, 1.25), first, (6.75, 4.75, 1.25), GOAL)
    result = validate_path(project, "PIPE-101", bent)
    assert [
        (item.code, item.object_id)
        for item in result.violations
        if item.code.startswith("WAYPOINT")
    ] == [("WAYPOINT_DIRECTION", "WP-1")]


def big_pipe(data, outer_diameter_m=0.6):
    data["pipes"][0]["outer_diameter_m"] = outer_diameter_m
    return data


def test_validator_flags_a_pipe_folding_back_onto_itself(open_data):
    # Envelope diameter 0.64 m; the first two legs are only 0.5 m apart.
    project = EngineeringProject.model_validate(big_pipe(open_data))

    def self_hits(points):
        return [
            item
            for item in validate_path(project, "PIPE-101", points).violations
            if item.code == "SELF_CLEARANCE"
        ]

    tail = ((2.25, 3.25, 1.25), (6.25, 3.25, 1.25), (6.25, 1.25, 1.25), GOAL)
    folded = (START, (4.25, 1.25, 1.25), (4.25, 1.75, 1.25), (2.25, 1.75, 1.25), *tail)
    hits = self_hits(folded)
    assert [item.segment_index for item in hits] == [2, 3]
    assert hits[0].object_id == "PIPE-101"
    assert isclose(hits[0].required_distance_m, 0.64)
    assert isclose(hits[0].measured_distance_m, 0.5)
    # Same shape with the legs 1.0 m apart is clear.
    wide = (START, (4.25, 1.25, 1.25), (4.25, 2.25, 1.25), (2.25, 2.25, 1.25), *tail)
    assert self_hits(wide) == []


def test_plain_elbows_and_offsets_are_not_self_conflicts(open_data):
    # Envelope 1.04 m is wider than the 0.5 m offset, yet nothing folds back.
    project = EngineeringProject.model_validate(big_pipe(open_data, 1.0))
    for points in (
        (START, (3.25, 1.25, 1.25), (3.25, 1.75, 1.25), (5.25, 1.75, 1.25)),
        (START, (3.25, 1.25, 1.25), (3.25, 4.25, 1.25)),
        (START, (3.25, 1.25, 1.25), (3.25, 1.25, 1.75), (3.25, 3.25, 1.75)),
    ):
        assert not [
            item
            for item in validate_path(project, "PIPE-101", points).violations
            if item.code == "SELF_CLEARANCE"
        ], points


def test_overlapping_waypoint_legs_are_re_searched_apart(open_data):
    # Visiting the far waypoint first makes the optimal sequence run back over
    # its own cells; the legs are then laid one at a time, avoiding each other.
    open_data["pipes"][0]["waypoints"] = [
        waypoint("WP-2", (5.75, 4.75, 2.75)),
        waypoint("WP-1", (2.25, 4.75, 1.25)),
    ]
    project = EngineeringProject.model_validate(open_data)
    exact = solve_route(project, "PIPE-101")
    assert "re-searched one at a time" in exact.message
    report = route_project(project, "PIPE-101")
    assert report.status is RouteStatus.SUCCESS
    assert report.validation.status is ValidationStatus.VALID
    assert len(set(report.points_m)) == len(report.points_m), "no cell is reused"
    assert report.search_mode == "HEURISTIC_LEGS"
    assert report.optimality_guarantee == "NONE"
    assert report.fallback_reason == "SELF_CLEARANCE"
    assert report.fallback_status == "SUCCESS"
    assert report.expanded_states == (
        report.initial_expanded_states + report.fallback_expanded_states
    )
    limited = route_project(
        project,
        "PIPE-101",
        max_expansions=report.initial_expanded_states,
    )
    assert limited.status == "INVALID_ROUTE"
    assert limited.search_mode == "EXACT_GRID_RETURNED"
    assert limited.initial_search_status == "SUCCESS"
    assert limited.fallback_status == "SEARCH_LIMIT_REACHED"
    assert limited.optimality_guarantee == "NONE"


def test_unavoidable_self_overlap_is_reported_not_hidden(open_data):
    # End port 0.5 m from the start port with a 0.64 m envelope: any route
    # back to it must touch the outgoing leg.
    open_data = big_pipe(open_data)
    open_data["equipment"][1]["ports"][0].update(
        position_m=[1.25, 1.75, 1.25], orientation="+x"
    )
    open_data["pipes"][0]["waypoints"] = [waypoint("WP-EAST", (6.75, 1.25, 1.25))]
    report = solve(open_data)
    assert report.status is RouteStatus.INVALID_ROUTE
    assert any(item.code == "SELF_CLEARANCE" for item in report.validation.violations)
    assert report.points_m, "the overlapping route is still returned for inspection"
    assert report.optimality_guarantee == "NONE"
