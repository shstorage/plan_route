"""Seeded translations of eleven analytically specified P10A scenes."""

from datetime import datetime, timezone
from itertools import product
from random import Random

from plan_route.models.benchmark import BenchmarkCase, ReferenceGraph
from plan_route.models.constraints import Constraint, RuleApproval
from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import GridIndex, Point3
from plan_route.models.results import RouteStatus


def pilot_cases(seed: int) -> list[BenchmarkCase]:
    rng = Random(seed)
    offset = tuple(rng.randint(-10, 10) for _ in range(3))

    def world(index: GridIndex) -> Point3:
        return tuple(a + b + 0.5 for a, b in zip(offset, index))

    def box(low: Point3, high: Point3) -> dict:
        return {
            "min_m": [a + b for a, b in zip(offset, low)],
            "max_m": [a + b for a, b in zip(offset, high)],
        }

    cases = []
    names = [
        "straight",
        "bend",
        "ordered",
        "duplicate",
        "wall_detour",
        "closed_wall",
        "keep_out",
        "clearance",
        "budget",
        "unapproved",
        "vertical",
    ]
    for name in names:
        vertical = name == "vertical"
        height = 5 if vertical else 3
        source = (1, 1, 1)
        goal = (
            (5, 1, 3)
            if vertical
            else (
                (5, 5, 1)
                if name in {"bend", "ordered", "duplicate", "clearance", "budget"}
                else (5, 1, 1)
            )
        )
        arrival = 4 if vertical else (2 if goal[1] == 5 else 0)
        cells = set(product(range(1, 6), range(1, 6), range(1, height - 1)))
        via, axes = [], []
        if name == "ordered":
            via, axes = [(3, 1, 1), (5, 3, 1)], [0, 1]
        elif name == "duplicate":
            via, axes = [(3, 1, 1), (3, 1, 1)], [0, 0]
        witness = [source, (5, 1, 1), goal] if arrival else [source, goal]
        if name == "wall_detour" or name == "keep_out":
            cells -= {(3, y, 1) for y in range(1, 4)}
            witness = [source, (2, 1, 1), (2, 4, 1), (4, 4, 1), (4, 1, 1), goal]
        elif name == "closed_wall":
            cells -= {(3, y, 1) for y in range(1, 6)}
            witness = []
        elif name == "clearance":
            cells -= set(product(range(2, 5), range(2, 5), [1]))

        obstacles, zones, rules = [], [], []
        if name in {"wall_detour", "closed_wall"}:
            obstacles = [
                {
                    "id": "WALL",
                    "kind": "wall",
                    "shape": box(
                        (3.45, 0, 0), (3.55, 7 if name == "closed_wall" else 3, 3)
                    ),
                }
            ]
        if name in {"keep_out", "unapproved", "clearance"}:
            clearance = name == "clearance"
            target = "BLOCK" if clearance else "ZONE"
            shape = (
                box((3.4, 3.4, 0), (3.6, 3.6, 3))
                if clearance
                else box((3.45, 0, 0), (3.55, 3, 3))
            )
            if clearance:
                obstacles = [{"id": target, "kind": "equipment", "shape": shape}]
            else:
                zones = [{"id": target, "zone_type": "synthetic", "shape": shape}]
            rule = Constraint.model_validate(
                {
                    "id": "RULE",
                    "type": "MIN_CLEARANCE" if clearance else "KEEP_OUT",
                    "severity": "hard",
                    "scope": {"pipe_ids": ["PIPE-101"], "target_ids": [target]},
                    "parameters": {
                        "distance_m": 0.5,
                        "distance_basis": "insulated_pipe_surface_to_target_surface",
                    }
                    if clearance
                    else {},
                    "source": {
                        "source_type": "synthetic_assumption",
                        "document_id": "P10A-FIXTURE",
                        "document_revision": "1",
                        "clause_id": name,
                        "evidence_text": (
                            "Synthetic pilot assumption; not a regulatory requirement."
                        ),
                    },
                    "status": "draft" if name == "unapproved" else "approved",
                }
            )
            if name != "unapproved":
                event = RuleApproval(
                    definition_revision=1,
                    content_sha256=rule.content_sha256(),
                    approved_by="synthetic-fixture",
                    approved_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
                )
                rule = rule.model_copy(
                    update={
                        "approved_content_sha256": event.content_sha256,
                        "approved_by": event.approved_by,
                        "approved_at": event.approved_at.isoformat(),
                        "approval_history": [event],
                    }
                )
            rules = [rule.model_dump(mode="json")]

        project = EngineeringProject.model_validate(
            {
                "schema_version": "1.0.0",
                "project_id": f"P10A-{name}",
                "study_type": "synthetic_benchmark",
                "unit_system": "SI",
                "coordinate_frame": {
                    "name": "PILOT_LOCAL",
                    "unit": "m",
                    "up_axis": "z",
                    "origin_m": offset,
                },
                "building": {
                    "bounds_m": box((0, 0, 0), (7, 7, height)),
                    "floors": [
                        {
                            "id": "F1",
                            "z_min_m": offset[2],
                            "z_max_m": offset[2] + height,
                        }
                    ],
                },
                "obstacles": obstacles,
                "zones": zones,
                "constraints": rules,
                "equipment": [
                    {
                        "id": "EQ-A",
                        "kind": "synthetic",
                        "ports": [
                            {
                                "id": "PORT-A",
                                "position_m": world(source),
                                "orientation": "+x",
                            }
                        ],
                    },
                    {
                        "id": "EQ-B",
                        "kind": "synthetic",
                        "ports": [
                            {
                                "id": "PORT-B",
                                "position_m": world(goal),
                                "orientation": "-z"
                                if vertical
                                else ("-y" if arrival == 2 else "-x"),
                            }
                        ],
                    },
                ],
                "pipes": [
                    {
                        "id": "PIPE-101",
                        "from_port_id": "PORT-A",
                        "to_port_id": "PORT-B",
                        "outer_diameter_m": 0.2,
                        "insulation_thickness_m": 0,
                        "waypoints": [
                            {
                                "id": f"WP-{i}",
                                "position_m": world(point),
                                "pass_axis": "xyz"[axis],
                            }
                            for i, (point, axis) in enumerate(zip(via, axes))
                        ],
                    }
                ],
                "routing_config": {
                    "grid_resolution_m": 1.0,
                    "cost_weights": {
                        "length_per_m": 1.0,
                        "bend_per_event": 2.0,
                        "preferred_zone_factor": 1.0,
                    },
                    "search_limits": {"max_expansions": 10000},
                },
            }
        )
        expected = {
            "closed_wall": RouteStatus.NO_PATH,
            "budget": RouteStatus.SEARCH_LIMIT_REACHED,
            "unapproved": RouteStatus.UNAPPROVED_RULE,
        }.get(name, RouteStatus.SUCCESS)
        cases.append(
            BenchmarkCase(
                case_id=f"P10A-{name}",
                description=name,
                project=project,
                expected_status=expected,
                feasibility_label=(
                    "SEPARATING_WALL"
                    if name == "closed_wall"
                    else ("PRECONDITION" if name == "unapproved" else "WITNESS")
                ),
                truth_basis=(
                    "Wall spans the entire y/z cross-section and separates the ports."
                    if name == "closed_wall"
                    else "Unapproved rule blocks execution before search."
                    if name == "unapproved"
                    else (
                        "Explicit centreline witness and manually enumerated "
                        "unit grid; no solver-derived labels."
                    )
                ),
                witness_m=[world(point) for point in witness]
                if name != "unapproved"
                else [],
                reference_graph=ReferenceGraph(
                    cells=sorted(cells),
                    start=source,
                    goal=goal,
                    departure=0,
                    arrival=arrival,
                    waypoints=via,
                    waypoint_axes=axes,
                ),
                max_expansions=1 if name == "budget" else None,
            )
        )
    return cases
