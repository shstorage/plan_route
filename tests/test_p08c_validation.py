"""Geometric counterexamples and invariants identified in the thesis review."""

import json
from importlib.resources import files

import pytest

from plan_route.models.engineering import EngineeringProject
from plan_route.services.path_validator import segment_segment_closest, validate_path


def make_project(start, end, waypoints=None):
    data = json.loads(
        files("plan_route")
        .joinpath("fixtures/demo_project.json")
        .read_text(encoding="utf-8")
    )
    data["building"] = {
        "bounds_m": {"min_m": [0, 0, 0], "max_m": [10, 10, 10]},
        "floors": [{"id": "F1", "z_min_m": 0, "z_max_m": 10}],
    }
    data.update(obstacles=[], zones=[], constraints=[])
    data["equipment"][0]["ports"][0].update(position_m=start, orientation="+x")
    data["equipment"][1]["ports"][0].update(position_m=end, orientation="-x")
    data["pipes"][0].update(
        outer_diameter_m=0.2,
        insulation_thickness_m=0,
        clearance_margin_m=0,
        waypoints=waypoints or [],
    )
    data["routing_config"]["grid_resolution_m"] = 1.0
    return EngineeringProject.model_validate(data)


def self_hits(project, points):
    return [
        item
        for item in validate_path(project, "PIPE-101", points).violations
        if item.code == "SELF_CLEARANCE"
    ]


def test_reverse_is_detected_independently_of_collinear_subdivision():
    project = make_project((2, 2, 2), (3, 2, 2))
    for points in (
        ((2, 2, 2), (6, 2, 2), (3, 2, 2)),
        ((2, 2, 2), (4, 2, 2), (6, 2, 2), (5, 2, 2), (3, 2, 2)),
        ((2, 2, 2), (2.01, 2, 2), (2.02, 2, 2), (2.015, 2, 2)),
    ):
        assert self_hits(project, points)


def test_self_distance_minimizes_over_arc_separated_points_not_one_closest_pair():
    project = make_project((2, 2, 2), (3, 3, 2))
    project.pipes[0].outer_diameter_m = 1.2
    # The closest pair near the U-bend is exempt; remote parallel runs still touch.
    coarse = ((2, 2, 2), (6, 2, 2), (6, 3, 2), (3, 3, 2))
    fine = ((2, 2, 2), (4, 2, 2), (6, 2, 2), (6, 3, 2), (4, 3, 2), (3, 3, 2))
    assert self_hits(project, coarse)
    assert self_hits(project, fine)


def test_later_valid_waypoint_pass_is_found_after_an_earlier_nearby_corner():
    project = make_project(
        (2.5, 4.5, 2.5),
        (6.5, 3.5, 2.5),
        [{"id": "WP1", "position_m": [4.1, 3.9, 2.5], "pass_axis": "x"}],
    )
    points = (
        (2.5, 4.5, 2.5),
        (3.5, 4.5, 2.5),
        (3.5, 3.5, 2.5),
        (4.5, 3.5, 2.5),
        (5.5, 3.5, 2.5),
        (6.5, 3.5, 2.5),
    )
    assert not [
        v
        for v in validate_path(project, "PIPE-101", points).violations
        if v.code.startswith("WAYPOINT")
    ]


@pytest.mark.parametrize(
    "points,code",
    [
        (((2, 2, 2), (2, 6, 2)), "PORT_DIRECTION"),
        (((2, 2, 2), (6, 6, 2)), "NON_ORTHOGONAL"),
    ],
)
def test_port_and_orthogonal_contract_is_checked(points, code):
    project = make_project(points[0], points[-1])
    assert code in {
        v.code for v in validate_path(project, "PIPE-101", points).violations
    }


def test_only_the_canonical_port_to_cell_connector_gets_direction_exemption():
    project = make_project((2.1, 2.2, 2.3), (6.1, 2.2, 2.3))
    points = (
        (2.1, 2.2, 2.3),
        (2.5, 2.5, 2.5),
        (6.5, 2.5, 2.5),
        (6.9, 2.2, 2.3),
    )
    project.equipment[1].ports[0].position_m = points[-1]
    assert validate_path(project, "PIPE-101", points).status == "VALID"
    incorrect = (points[0], (3.5, 2.5, 2.5), *points[2:])
    assert "NON_ORTHOGONAL" in {
        v.code for v in validate_path(project, "PIPE-101", incorrect).violations
    }


def test_waypoint_axis_reversal_is_not_a_straight_pass():
    project = make_project(
        (2, 2, 2),
        (3, 2, 2),
        [{"id": "WP1", "position_m": [6, 2, 2], "pass_axis": "x"}],
    )
    result = validate_path(project, "PIPE-101", ((2, 2, 2), (6, 2, 2), (3, 2, 2)))
    assert "WAYPOINT_DIRECTION" in {v.code for v in result.violations}


def test_waypoint_at_a_bend_remains_invalid_after_collinear_subdivision():
    project = make_project(
        (2, 2, 2),
        (6, 6, 2),
        [{"id": "WP1", "position_m": [6, 2, 2], "pass_axis": "x"}],
    )
    for points in (
        ((2, 2, 2), (6, 2, 2), (6, 6, 2)),
        ((2, 2, 2), (5.9, 2, 2), (6, 2, 2), (6, 6, 2)),
    ):
        assert "WAYPOINT_DIRECTION" in {
            v.code for v in validate_path(project, "PIPE-101", points).violations
        }


def test_ordered_waypoints_may_share_one_projection_on_an_overlapping_tolerance():
    project = make_project(
        (2, 2, 2),
        (6, 2, 2),
        [
            {"id": "WP1", "position_m": [4.1, 2.2, 2], "pass_axis": "x"},
            {"id": "WP2", "position_m": [4.0, 2.3, 2], "pass_axis": "x"},
        ],
    )
    # Order is nondecreasing within the declared snap tolerance, not exact point visits.
    assert not [
        v
        for v in validate_path(project, "PIPE-101", ((2, 2, 2), (6, 2, 2))).violations
        if v.code.startswith("WAYPOINT")
    ]


@pytest.mark.parametrize("scale", [1.0, 0.001, 0.000001])
def test_segment_intersection_does_not_depend_on_metre_scale(scale):
    s, t, distance = segment_segment_closest(
        (-scale, 0, 0),
        (scale, 0, 0),
        (0, -scale, 0),
        (0, scale, 0),
    )
    assert distance == pytest.approx(0, abs=1e-12)
    assert s == t == pytest.approx(0.5)
