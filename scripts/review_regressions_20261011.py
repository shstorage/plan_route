"""Read-only counterexamples for the 2026-10-11 review; not a benchmark.

Run: uv run python scripts/review_regressions_20261011.py
Prints observations instead of asserting that known defects should persist.
No project files or stored route reports are changed.
"""

import json
from importlib.resources import files

from plan_route.models.engineering import EngineeringProject
from plan_route.services.path_validator import validate_path


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
    data["obstacles"] = []
    data["zones"] = []
    data["constraints"] = []
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


def main():
    cases = [
        (
            "immediate_reverse",
            make_project((2, 2, 2), (3, 2, 2)),
            ((2, 2, 2), (6, 2, 2), (3, 2, 2)),
        ),
        (
            "same_reverse_subdivided",
            make_project((2, 2, 2), (3, 2, 2)),
            ((2, 2, 2), (4, 2, 2), (6, 2, 2), (5, 2, 2), (3, 2, 2)),
        ),
        (
            "wrong_port_axis",
            make_project((2, 2, 2), (2, 6, 2)),
            ((2, 2, 2), (2, 6, 2)),
        ),
        (
            "diagonal",
            make_project((2, 2, 2), (6, 6, 2)),
            ((2, 2, 2), (6, 6, 2)),
        ),
        (
            "early_waypoint_match",
            make_project(
                (2.5, 4.5, 2.5),
                (6.5, 3.5, 2.5),
                [{"id": "WP1", "position_m": [4.1, 3.9, 2.5], "pass_axis": "x"}],
            ),
            (
                (2.5, 4.5, 2.5), (3.5, 4.5, 2.5), (3.5, 3.5, 2.5),
                (4.5, 3.5, 2.5), (5.5, 3.5, 2.5), (6.5, 3.5, 2.5),
            ),
        ),
    ]
    for name, project, points in cases:
        result = validate_path(project, "PIPE-101", points)
        print(json.dumps({
            "case": name,
            "status": result.status,
            "violations": [
                {"code": item.code, "segment": item.segment_index}
                for item in result.violations
            ],
        }))


if __name__ == "__main__":
    main()
