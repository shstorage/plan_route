"""P10B physical scenes and an independent whole-cell reference discretization."""

from datetime import datetime, timezone
from itertools import product
from math import dist, floor
from random import Random

from plan_route.models.benchmark import BenchmarkCase, BenchmarkConfig, ReferenceGraph
from plan_route.models.constraints import Constraint, RuleApproval
from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteStatus
from plan_route.services.benchmark_cases import pilot_cases

FAMILIES = (
    "sparse",
    "dense",
    "keep_out",
    "clearance",
    "ordered",
    "closed_wall",
    "narrow_gate",
)


def explicit_graph(project: EngineeringProject) -> ReferenceGraph:
    """Algebraic cell/AABB intersection; no production geometry or mask helpers.

    Restricted to complete regular cells and this suite's single pipe.
    This is a second discretization, not a continuous-space optimality oracle.
    """
    bounds, step = project.building.bounds_m, project.routing_config.grid_resolution_m
    pipe = project.pipes[0]
    radius = (
        pipe.outer_diameter_m / 2
        + pipe.insulation_thickness_m
        + pipe.clearance_margin_m
    )
    shape = tuple(round((b - a) / step) for a, b in zip(bounds.min_m, bounds.max_m))
    if any(
        abs(n * step - (b - a)) > 1e-9
        for n, a, b in zip(shape, bounds.min_m, bounds.max_m)
    ):
        raise ValueError("reference requires complete regular cells")
    boxes = [(item.shape, radius) for item in project.obstacles]
    targets = {item.id: item.shape for item in [*project.obstacles, *project.zones]}
    for rule in project.constraints:
        if rule.status.value == "approved":
            extra = rule.parameters.distance_m or 0.0
            boxes.extend(
                (targets[target], radius + extra) for target in rule.scope.target_ids
            )
    cells = []
    for index in product(*(range(n) for n in shape)):
        low = tuple(a + i * step for a, i in zip(bounds.min_m, index))
        high = tuple(a + step for a in low)
        if any(
            a < b + radius or c > d - radius
            for a, b, c, d in zip(low, bounds.min_m, high, bounds.max_m)
        ):
            continue
        if any(
            all(
                a <= d + padding and c >= b - padding
                for a, c, b, d in zip(low, high, box.min_m, box.max_m)
            )
            for box, padding in boxes
        ):
            continue
        cells.append(index)

    def cell(point):
        return tuple(
            min(n - 1, floor((p - a) / step))
            for p, a, n in zip(point, bounds.min_m, shape)
        )

    def centre(index):
        return tuple(a + (i + 0.5) * step for a, i in zip(bounds.min_m, index))

    ports = {port.id: port for eq in project.equipment for port in eq.ports}
    source, target = ports[pipe.from_port_id], ports[pipe.to_port_id]
    start, goal = cell(source.position_m), cell(target.position_m)
    directions = {
        name: i for i, name in enumerate(("+x", "-x", "+y", "-y", "+z", "-z"))
    }
    return ReferenceGraph(
        cells=cells,
        start=start,
        goal=goal,
        departure=directions[source.orientation],
        arrival=directions[target.orientation] ^ 1,
        waypoints=[cell(wp.position_m) for wp in pipe.waypoints],
        waypoint_axes=[
            None if wp.pass_axis is None else "xyz".index(wp.pass_axis)
            for wp in pipe.waypoints
        ],
        edge_length_m=step,
        length_weight=project.routing_config.cost_weights.length_per_m,
        bend_weight=project.routing_config.cost_weights.bend_per_event,
        connector_cost=project.routing_config.cost_weights.length_per_m
        * (
            dist(source.position_m, centre(start))
            + dist(target.position_m, centre(goal))
        ),
    )


def analytic_witness_clear(project: EngineeringProject, points: list[tuple]) -> bool:
    """Exact distance for axis-parallel segments; an independent fixture check.

    Does not establish self-clearance, directions or arbitrary polyline feasibility.
    The specified witnesses have separated nonadjacent runs by construction.
    """
    pipe = project.pipes[0]
    radius = (
        pipe.outer_diameter_m / 2
        + pipe.insulation_thickness_m
        + pipe.clearance_margin_m
    )
    bounds = project.building.bounds_m
    boxes = [(item.shape, radius) for item in project.obstacles]
    targets = {item.id: item.shape for item in [*project.obstacles, *project.zones]}
    for rule in project.constraints:
        boxes.extend(
            (targets[target], radius + (rule.parameters.distance_m or 0))
            for target in rule.scope.target_ids
        )
    for start, end in zip(points, points[1:]):
        if sum(a != b for a, b in zip(start, end)) != 1:
            return False
        if any(
            min(a, b) <= low + radius or max(a, b) >= high - radius
            for a, b, low, high in zip(start, end, bounds.min_m, bounds.max_m)
        ):
            return False
        for box, required in boxes:
            squared = sum(
                max(low - max(a, b), min(a, b) - high, 0) ** 2
                for a, b, low, high in zip(start, end, box.min_m, box.max_m)
            )
            if squared <= required**2:
                return False
    return True


def _approved_rule(rule_type: str, target: str, distance: float | None = None) -> dict:
    rule = Constraint.model_validate(
        {
            "id": f"RULE-{target}",
            "type": rule_type,
            "severity": "hard",
            "scope": {"pipe_ids": ["PIPE-101"], "target_ids": [target]},
            "parameters": {}
            if distance is None
            else {
                "distance_m": distance,
                "distance_basis": "insulated_pipe_surface_to_target_surface",
            },
            "source": {
                "source_type": "synthetic_assumption",
                "document_id": "P10B-FIXTURE",
                "document_revision": "1",
                "clause_id": target,
                "evidence_text": "Study assumption only.",
            },
            "status": "approved",
        }
    )
    event = RuleApproval(
        definition_revision=1,
        content_sha256=rule.content_sha256(),
        approved_by="synthetic-fixture",
        approved_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    return rule.model_copy(
        update={
            "approved_content_sha256": event.content_sha256,
            "approved_by": event.approved_by,
            "approved_at": event.approved_at.isoformat(),
            "approval_history": [event],
        }
    ).model_dump(mode="json")


def _physical_scene(seed: int, family: str) -> tuple[dict, list[tuple]]:
    rng = Random(seed)
    data = pilot_cases(0)[0].project.model_dump(mode="json")
    data["coordinate_frame"]["origin_m"] = [0, 0, 0]
    data["building"] = {
        "bounds_m": {"min_m": [0, 0, 0], "max_m": [12, 10, 4]},
        "floors": [{"id": "F1", "z_min_m": 0, "z_max_m": 4}],
    }
    data.update(obstacles=[], zones=[], constraints=[])
    source, goal = (1.5, 1.5, 1.5), (10.5, 1.5, 1.5)
    witness = [
        source,
        (2.5, 1.5, 1.5),
        (2.5, 8.5, 1.5),
        (9.5, 8.5, 1.5),
        (9.5, 1.5, 1.5),
        goal,
    ]
    wall_height = rng.choice([5.5, 6.0, 6.5])

    def obstacle(name, low, high):
        return {"id": name, "kind": "synthetic", "shape": {"min_m": low, "max_m": high}}

    if family == "narrow_gate":
        y = rng.choice([4.75, 5.75])
        source, goal = (1.5, y, 1.5), (10.5, y, 1.5)
        witness = [source, goal]
        data["obstacles"] = [
            obstacle("WALL-LOW", (5.6, 0, 0), (6.4, y - 0.6, 4)),
            obstacle("WALL-HIGH", (5.6, y + 0.6, 0), (6.4, 10, 4)),
        ]
    elif family == "closed_wall":
        data["obstacles"] = [obstacle("WALL", (5.6, 0, 0), (6.4, 10, 4))]
        witness = []
    elif family == "ordered":
        goal = (10.5, 8.5, 1.5)
        witness = [source, (10.5, 1.5, 1.5), goal]
        data["pipes"][0]["waypoints"] = [
            {"id": "WP-X", "position_m": [5.5, 1.5, 1.5], "pass_axis": "x"},
            {"id": "WP-Y", "position_m": [10.5, 5.5, 1.5], "pass_axis": "y"},
        ]
    elif family == "keep_out":
        data["zones"] = [
            {
                "id": "ZONE",
                "zone_type": "synthetic",
                "shape": {"min_m": [5.6, 0, 0], "max_m": [6.4, wall_height, 4]},
            }
        ]
        data["constraints"] = [_approved_rule("KEEP_OUT", "ZONE")]
    else:
        data["obstacles"] = [obstacle("WALL", (5.6, 0, 0), (6.4, wall_height, 4))]
    if family not in {"closed_wall", "narrow_gate"}:
        for i in range(10 if family == "dense" else 3):
            x, y = rng.uniform(3.5, 7.5), rng.uniform(3.0, 5.5)
            width, depth = rng.uniform(0.3, 0.8), rng.uniform(0.3, 0.8)
            data["obstacles"].append(
                obstacle(f"BLOCK-{i}", (x, y, 0.75), (x + width, y + depth, 3.25))
            )
        if family == "clearance":
            data["constraints"] = [
                _approved_rule("MIN_CLEARANCE", "BLOCK-0", rng.choice([0.25, 0.5]))
            ]
    data["equipment"][0]["ports"][0].update(position_m=source, orientation="+x")
    data["equipment"][1]["ports"][0].update(
        position_m=goal, orientation="-y" if family == "ordered" else "-x"
    )
    data["routing_config"]["search_limits"]["max_expansions"] = 200000
    return data, witness


def comparison_cases(config: BenchmarkConfig) -> list[BenchmarkCase]:
    cases = []
    for split, seeds in (
        ("development", config.scene_seeds),
        ("evaluation", config.evaluation_seeds),
    ):
        for seed in seeds:
            for family in FAMILIES:
                physical, witness = _physical_scene(seed, family)
                scene_id = f"P10B-{split}-{family}-s{seed}"
                for step in config.resolutions_m:
                    data = {
                        **physical,
                        "project_id": scene_id,
                        "routing_config": {
                            **physical["routing_config"],
                            "grid_resolution_m": step,
                        },
                    }
                    project = EngineeringProject.model_validate(data)
                    if witness and not analytic_witness_clear(project, witness):
                        raise ValueError(f"analytic witness is obstructed: {scene_id}")
                    graph = explicit_graph(project)
                    expected = (
                        RouteStatus.NO_PATH
                        if family == "closed_wall"
                        or (family == "narrow_gate" and step == 1)
                        else RouteStatus.SUCCESS
                    )
                    cases.append(
                        BenchmarkCase(
                            case_id=f"{scene_id}-r{str(step).replace('.', 'p')}",
                            scene_id=scene_id,
                            split=split,
                            family=family,
                            seed=seed,
                            description=f"{family}, seed={seed}, resolution={step} m",
                            project=project,
                            expected_status=expected,
                            reference_graph=graph,
                            feasibility_label="SEPARATING_WALL"
                            if family == "closed_wall"
                            else "WITNESS",
                            witness_m=witness,
                            truth_basis=(
                                "Full y/z wall separates ports."
                                if family == "closed_wall"
                            else (
                                "A 1.2 m opening admits the physical witness; "
                                "1 m whole cells cannot fit, 0.5 m cells can."
                            )
                                if family == "narrow_gate"
                            else (
                                "Explicit orthogonal witness stays outside all "
                                "inflated boxes; independent segment/AABB check."
                            )
                            ),
                        )
                    )
    cases.extend(_diagnostic_cases())
    return cases


def _diagnostic_cases() -> list[BenchmarkCase]:
    data = pilot_cases(0)[0].project.model_dump(mode="json")
    data["coordinate_frame"]["origin_m"] = [0, 0, 0]
    data["building"] = {
        "bounds_m": {"min_m": [0, 0, 0], "max_m": [8, 6, 4]},
        "floors": [{"id": "F1", "z_min_m": 0, "z_max_m": 4}],
    }
    data["routing_config"]["grid_resolution_m"] = 0.5
    data["routing_config"]["search_limits"]["max_expansions"] = 200000
    data["pipes"][0].update(
        outer_diameter_m=0.1,
        insulation_thickness_m=0.02,
        waypoints=[
            {"id": "WP-FAR", "position_m": [5.75, 4.75, 2.75]},
            {"id": "WP-NEAR", "position_m": [2.25, 4.75, 1.25]},
        ],
    )
    data["equipment"][0]["ports"][0].update(
        position_m=[1.25, 1.25, 1.25], orientation="+x"
    )
    data["equipment"][1]["ports"][0].update(
        position_m=[6.75, 1.25, 1.25], orientation="-x"
    )
    data["project_id"] = "P10B-diagnostic-heuristic"
    project = EngineeringProject.model_validate(data)
    witness = [
        (1.25, 1.25, 1.25),
        (2.25, 1.25, 1.25),
        (2.25, 2.25, 1.25),
        (5.75, 2.25, 1.25),
        (5.75, 4.75, 1.25),
        (5.75, 4.75, 2.75),
        (2.25, 4.75, 2.75),
        (2.25, 4.75, 1.25),
        (2.25, 5.25, 1.25),
        (6.25, 5.25, 1.25),
        (6.25, 1.25, 1.25),
        (6.75, 1.25, 1.25),
    ]
    heuristic = BenchmarkCase(
        description="Ordered retracing diagnostic",
        case_id=data["project_id"],
        scene_id=data["project_id"],
        split="diagnostic",
        family="heuristic",
        project=project,
        expected_status=RouteStatus.SUCCESS,
        expected_search_mode="HEURISTIC_LEGS",
        reference_graph=explicit_graph(project),
        feasibility_label="WITNESS",
        witness_m=witness,
        truth_basis=(
            "Explicit separated 3D witness; ordered distant waypoints "
            "induce retracing of the initial grid optimum."
        ),
    )
    data["project_id"] = "P10B-diagnostic-self-contact"
    data["equipment"][1]["ports"][0].update(
        position_m=[1.25, 1.75, 1.25], orientation="+x"
    )
    data["pipes"][0].update(
        outer_diameter_m=0.6,
        waypoints=[{"id": "WP-EAST", "position_m": [6.75, 1.25, 1.25]}],
    )
    project = EngineeringProject.model_validate(data)
    contact = BenchmarkCase(
        description="Port envelope self-contact diagnostic",
        case_id=data["project_id"],
        scene_id=data["project_id"],
        split="diagnostic",
        family="self-contact",
        project=project,
        expected_status=RouteStatus.INVALID_ROUTE,
        reference_graph=explicit_graph(project),
        feasibility_label="PRECONDITION",
        truth_basis=(
            "Predeclared envelope-contact regression: ports are 0.5 m apart "
            "and diameter is 0.64 m; not a continuous-space infeasibility theorem."
        ),
    )
    return [heuristic, contact]
