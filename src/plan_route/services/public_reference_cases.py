"""P10D: bounded public-reference examples, never automatic code interpretation."""

from dataclasses import dataclass
from math import isfinite

from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import Point3
from plan_route.services.benchmark_changes import fixture_approval

UFGS_URL = "https://www.wbdg.org/FFC/DOD/UFGS/UFGS%2023%2022%2026.00%2020.pdf"
OSHA_URL = "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.303"
BHEL_URL = (
    "https://www.bhel.com/sites/default/files/"
    "1-technical-specification-part-1-1511852976.pdf"
)


@dataclass(frozen=True)
class PublicReferenceCase:
    case_id: str
    project: EngineeringProject
    source_url: str
    applicability: dict
    normalization: str
    probe_axis: int
    probe_boundary_m: float
    probe_side: int
    normalized_touch_valid: bool


def _base(case_id: str, *, height: float = 3, z: float = 1.25) -> dict:
    return {
        "schema_version": "1.0.0",
        "project_id": case_id,
        "study_type": "synthetic_benchmark",
        "unit_system": "SI",
        "coordinate_frame": {
            "name": "SYNTHETIC",
            "unit": "m",
            "up_axis": "z",
            "origin_m": [0, 0, 0],
        },
        "building": {
            "bounds_m": {"min_m": [0, 0, 0], "max_m": [6, 4, height]},
            "floors": [{"id": "L1", "z_min_m": 0, "z_max_m": height}],
        },
        "obstacles": [],
        "zones": [],
        "constraints": [],
        "equipment": [
            {
                "id": "EQ-A",
                "kind": "synthetic_terminal",
                "ports": [
                    {"id": "PORT-A", "position_m": [0.75, 1.25, z], "orientation": "+x"}
                ],
            },
            {
                "id": "EQ-B",
                "kind": "synthetic_terminal",
                "ports": [
                    {"id": "PORT-B", "position_m": [4.75, 1.25, z], "orientation": "-x"}
                ],
            },
        ],
        "pipes": [
            {
                "id": "PIPE-101",
                "from_port_id": "PORT-A",
                "to_port_id": "PORT-B",
                "outer_diameter_m": 0.1143,
                "insulation_thickness_m": 0.04,
                "clearance_margin_m": 0,
            }
        ],
        "routing_config": {
            "grid_resolution_m": 0.5,
            "cost_weights": {
                "length_per_m": 1,
                "bend_per_event": 2,
                "preferred_zone_factor": 1,
            },
            "search_limits": {"max_expansions": 400000},
        },
    }


def _rule(
    document: str,
    revision: str,
    clause: str,
    target: str,
    evidence: str,
    distance: float | None = None,
) -> dict:
    return fixture_approval(
        {
            "id": "RULE-PUBLIC",
            "type": "KEEP_OUT" if distance is None else "MIN_CLEARANCE",
            "severity": "hard",
            "scope": {"pipe_ids": ["PIPE-101"], "target_ids": [target]},
            "parameters": {}
            if distance is None
            else {
                "distance_m": distance,
                "distance_basis": "insulated_pipe_surface_to_target_surface",
            },
            "source": {
                "source_type": "public_reference",
                "document_id": document,
                "document_revision": revision,
                "clause_id": clause,
                "evidence_text": evidence,
            },
            "status": "draft",
        }
    )


def wall_working_clearance_case(
    nominal_size_mm: float, *, service: str = "building_heating_steam"
) -> PublicReferenceCase:
    """Manually scoped UFGS example; nominal size is NOT inferred from OD."""
    if service not in {"building_heating_steam", "building_heating_condensate"}:
        raise ValueError("UFGS example excludes process/main steam and boiler feed")
    if (
        isinstance(nominal_size_mm, bool)
        or not isfinite(nominal_size_mm)
        or nominal_size_mm <= 0
    ):
        raise ValueError("nominal_size_mm must be finite and positive")
    distance = 0.15 if nominal_size_mm <= 100 else 0.25
    case_id = "P10D-WALL-SMALL" if nominal_size_mm <= 100 else "P10D-WALL-LARGE"
    data = _base(case_id)
    # Example dimensions are authored, not a nominal-size/OD lookup table.
    if nominal_size_mm > 100:
        data["pipes"][0]["outer_diameter_m"] = 0.1683
    data["obstacles"] = [
        {
            "id": "WORK-WALL",
            "kind": "wall",
            "shape": {"min_m": [2.5, 1.7, 0], "max_m": [3.5, 3.9, 3]},
        }
    ]
    data["constraints"] = [
        _rule(
            "UFGS-23-22-26-00-20",
            "02-2010-CHG1-05-2015",
            "SEC-3-1-1",
            "WORK-WALL",
            "Welding access clearance by nominal size. "
            "Synthetic normalization measures outside insulation; "
            "not plant-code compliance.",
            distance,
        )
    ]
    return PublicReferenceCase(
        case_id,
        EngineeringProject.model_validate(data),
        UFGS_URL,
        {
            "service": service,
            "nominal_size_mm": nominal_size_mm,
            "purpose": "joint_welding_access",
            "target": "WORK-WALL",
            "source_pdf_page_1based": 24,
            "source_gap_m": distance,
            "nominal_size_supplied_by_author": True,
            "excluded": ["process_steam", "main_steam", "boiler_feed", "penetrations"],
        },
        "Study policy: the published welding gap is required "
        "outside finished insulation. "
        "This is a conservative interpretation, not a proven exact surface definition.",
        1,
        1.7,
        -1,
        True,
    )


def electrical_dedicated_space_case(
    *,
    indoor: bool = True,
    protected_foreign_system: bool = False,
    sprinkler: bool = False,
) -> PublicReferenceCase:
    if not indoor or protected_foreign_system or sprinkler:
        raise ValueError("This example only covers indoor, unprotected foreign piping")
    data = _base("P10D-ELECTRICAL", height=4, z=1.75)
    data["obstacles"] = [
        {
            "id": "CABINET",
            "kind": "electrical_cabinet",
            "shape": {"min_m": [2.5, 1, 0], "max_m": [3.5, 2.5, 1]},
        }
    ]
    data["zones"] = [
        {
            "id": "DEDICATED-SPACE",
            "zone_type": "electrical_dedicated",
            "shape": {"min_m": [2.5, 1, 0], "max_m": [3.5, 2.5, 2.83]},
        }
    ]
    data["constraints"] = [
        _rule(
            "OSHA-29-CFR-1910-303",
            "accessed-2026-10-13",
            "G-1-VII-A-1",
            "DEDICATED-SPACE",
            "Indoor switchboard dedicated space; unprotected foreign "
            "piping only. Synthetic closed-boundary interpretation; "
            "exceptions excluded.",
        )
    ]
    return PublicReferenceCase(
        "P10D-ELECTRICAL",
        EngineeringProject.model_validate(data),
        OSHA_URL,
        {
            "equipment": "indoor_switchboard",
            "foreign_piping": True,
            "protective_isolation": False,
            "sprinkler": False,
            "ceiling_m": 4,
            "equipment_height_m": 1,
            "dedicated_top_m": 2.83,
            "excluded": [
                "protected_foreign_systems",
                "sprinklers",
                "outdoor_equipment",
            ],
        },
        "Zone shares cabinet footprint; top=min(1+1.83,4). "
        "Closed-boundary exclusion is an explicit study interpretation, "
        "not a legal label.",
        2,
        2.83,
        1,
        False,
    )


def thermal_walkway_case(*, crossing: str = "walkway") -> PublicReferenceCase:
    if crossing != "walkway":
        raise ValueError("This example excludes roads, railways and buried piping")
    data = _base("P10D-THERMAL-WALKWAY", height=4, z=1.75)
    data["zones"] = [
        {
            "id": "WALKWAY-HEADROOM",
            "zone_type": "walkway_headroom",
            "shape": {"min_m": [2.5, 0, 0], "max_m": [3.5, 4, 2.5]},
        }
    ]
    data["constraints"] = [
        _rule(
            "BHEL-PE-TS-425-166-A001",
            "REV-00-2017-10-25",
            "SEC-13-5-3",
            "WALKWAY-HEADROOM",
            "Uppur project LP overhead piping: walkway headroom "
            "2.5 m. Synthetic stationary envelope; supports and movements excluded.",
        )
    ]
    return PublicReferenceCase(
        "P10D-THERMAL-WALKWAY",
        EngineeringProject.model_validate(data),
        BHEL_URL,
        {
            "project": "Uppur_2x800MW",
            "service": "LP_piping",
            "overhead": True,
            "crossing": crossing,
            "walking_surface_z_m": 0,
            "headroom_m": 2.5,
            "source_pdf_page_1based": 83,
            "source_printed_page": "Vol.III:304",
            "excluded": ["roads", "railways", "supports", "thermal_movement", "buried"],
        },
        "Study defines vertical clearance to the stationary insulated underside. "
        "KEEP_OUT rejects exact touching, stricter than the "
        "normalized >=2.5 m criterion.",
        2,
        2.5,
        1,
        True,
    )


def public_reference_cases() -> list[PublicReferenceCase]:
    return [
        wall_working_clearance_case(100),
        wall_working_clearance_case(150),
        electrical_dedicated_space_case(),
        thermal_walkway_case(),
    ]


def authored_witness(case: PublicReferenceCase) -> list[Point3]:
    """Explicit orthogonal detour, authored before invoking any search/mask."""
    start = case.project.equipment[0].ports[0].position_m
    end = case.project.equipment[1].ports[0].position_m
    if case.case_id.startswith("P10D-WALL"):
        y, z = 0.75, start[2]
    elif case.case_id == "P10D-ELECTRICAL":
        y, z = 0.5, start[2]
    else:
        y, z = start[1], 3.25
    return [
        start,
        (1.75, start[1], start[2]),
        (1.75, y, z),
        (4.25, y, z),
        (4.25, end[1], end[2]),
        end,
    ]


def gold_probes(case: PublicReferenceCase) -> list[dict]:
    """Axis-parallel analytical labels; no solver grid/distance routine is used."""
    pipe = case.project.pipes[0]
    radius = (
        pipe.outer_diameter_m / 2
        + pipe.insulation_thickness_m
        + pipe.clearance_margin_m
    )
    rule = case.project.constraints[0]
    clearance = rule.parameters.distance_m or 0
    probes = []
    for offset in (-0.02, 0, 0.02):
        coordinate = case.probe_boundary_m + case.probe_side * (
            radius + clearance + offset
        )
        start, end = [0.75, 1.25, 1.25], [4.75, 1.25, 1.25]
        start[case.probe_axis] = end[case.probe_axis] = coordinate
        for split in (False, True):
            points: list[Point3] = [tuple(start), tuple(end)]
            if split:
                points.insert(1, (3, start[1], start[2]))
            contract_valid = (
                offset >= 0 if rule.type.value == "MIN_CLEARANCE" else offset > 0
            )
            normalized_valid = offset > 0 or (
                offset == 0 and case.normalized_touch_valid
            )
            data = case.project.model_dump(mode="json")
            data["equipment"][0]["ports"][0]["position_m"] = start
            data["equipment"][1]["ports"][0]["position_m"] = end
            probes.append(
                {
                    "probe_id": f"gap-{offset:+.2f}-split-{int(split)}",
                    "project": EngineeringProject.model_validate(data),
                    "points_m": points,
                    "normalized_valid": normalized_valid,
                    "contract_valid": contract_valid,
                    "expected_rule_segments": []
                    if contract_valid
                    else list(range(len(points) - 1)),
                    "expected_distance_m": radius + clearance + offset,
                    "expected_required_m": radius + clearance,
                }
            )
    return probes
