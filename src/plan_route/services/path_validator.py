"""Independent continuous-geometry validation of pipe centreline paths."""

import hashlib
from math import isfinite, sqrt

from plan_route.models.constraints import ConstraintStatus, ConstraintType
from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import AABB, Point3
from plan_route.models.results import (
    PathValidationResult,
    PathViolation,
    ValidationStatus,
)
from plan_route.services.compiler import project_fingerprint
from plan_route.services.geometry import effective_pipe_radius_m

_EPS = 1e-9


def scenario_hash(project: EngineeringProject, pipe_id: str) -> str:
    """Stable ID for one project snapshot and selected pipe."""
    return hashlib.sha256(
        f"{project_fingerprint(project)}:{pipe_id}".encode()
    ).hexdigest()


def _point_box_distance_squared(point: Point3, box: AABB) -> float:
    return sum(
        max(low - value, 0.0, value - high) ** 2
        for value, low, high in zip(point, box.min_m, box.max_m, strict=True)
    )


def segment_aabb_distance_m(start: Point3, end: Point3, box: AABB) -> float:
    """Exact Euclidean minimum distance between a closed segment and AABB.

    The point-to-box squared distance is quadratic between each parameter
    where a segment coordinate crosses a box face. Minimize on each interval.
    This does not use the routing grid, cell masks, or L-infinity expansion.
    """
    direction = tuple(b - a for a, b in zip(start, end, strict=True))
    breaks = {0.0, 1.0}
    for origin, delta, low, high in zip(
        start, direction, box.min_m, box.max_m, strict=True
    ):
        if delta:
            for face in (low, high):
                t = (face - origin) / delta
                if 0 < t < 1:
                    breaks.add(t)
    ordered = sorted(breaks)
    candidates = set(ordered)
    for left, right in zip(ordered, ordered[1:]):
        middle = (left + right) / 2
        slope_norm = 0.0
        slope_offset = 0.0
        for origin, delta, low, high in zip(
            start, direction, box.min_m, box.max_m, strict=True
        ):
            value = origin + middle * delta
            bound = low if value < low else high if value > high else None
            if bound is not None:
                slope_norm += delta * delta
                slope_offset += delta * (origin - bound)
        if slope_norm:
            candidates.add(max(left, min(right, -slope_offset / slope_norm)))
    return sqrt(
        min(
            _point_box_distance_squared(
                tuple(a + t * delta for a, delta in zip(start, direction, strict=True)),
                box,
            )
            for t in candidates
        )
    )


def validate_path(
    project: EngineeringProject, pipe_id: str, points_m: tuple[Point3, ...]
) -> PathValidationResult:
    """Check the entire supplied polyline against original AABBs and hard rules."""
    fingerprint = scenario_hash(project, pipe_id)
    pipe = next((item for item in project.pipes if item.id == pipe_id), None)
    if pipe is None:
        return PathValidationResult(
            status=ValidationStatus.INVALID_INPUT,
            project_id=project.project_id,
            pipe_id=pipe_id,
            scenario_hash=fingerprint,
            message=f"unknown pipe ID: {pipe_id}",
        )
    if (
        len(points_m) < 2
        or any(
            len(point) != 3 or not all(isfinite(value) for value in point)
            for point in points_m
        )
        or any(first == second for first, second in zip(points_m, points_m[1:]))
    ):
        return PathValidationResult(
            status=ValidationStatus.INVALID_INPUT,
            project_id=project.project_id,
            pipe_id=pipe_id,
            scenario_hash=fingerprint,
            message="path needs at least two distinct finite 3D points",
        )
    rules = sorted(
        (rule for rule in project.constraints if pipe_id in rule.scope.pipe_ids),
        key=lambda rule: rule.id,
    )
    unapproved = [
        rule.id for rule in rules if rule.status is not ConstraintStatus.APPROVED
    ]
    if unapproved:
        return PathValidationResult(
            status=ValidationStatus.UNAPPROVED_RULE,
            project_id=project.project_id,
            pipe_id=pipe_id,
            scenario_hash=fingerprint,
            message=f"unapproved rules for pipe {pipe_id}: {', '.join(unapproved)}",
        )
    ports = {
        port.id: port.position_m
        for equipment in project.equipment
        for port in equipment.ports
    }
    violations: list[PathViolation] = []
    for index, (actual, expected) in enumerate(
        (
            (points_m[0], ports[pipe.from_port_id]),
            (points_m[-1], ports[pipe.to_port_id]),
        )
    ):
        if any(abs(a - b) > _EPS for a, b in zip(actual, expected, strict=True)):
            violations.append(
                PathViolation(
                    code="ENDPOINT_MISMATCH",
                    segment_index=0 if index == 0 else len(points_m) - 2,
                    object_id=pipe.from_port_id if index == 0 else pipe.to_port_id,
                    measured_distance_m=sqrt(
                        sum((a - b) ** 2 for a, b in zip(actual, expected, strict=True))
                    ),
                    required_distance_m=0,
                    message="path endpoint does not match its port position",
                )
            )
    radius = effective_pipe_radius_m(pipe)
    shapes = {
        **{item.id: item.shape for item in project.obstacles},
        **{item.id: item.shape for item in project.zones},
    }
    building = project.building.bounds_m
    for segment_index, (start, end) in enumerate(zip(points_m, points_m[1:])):
        for axis in range(3):
            clearance = min(start[axis], end[axis]) - building.min_m[axis]
            opposite = building.max_m[axis] - max(start[axis], end[axis])
            if min(clearance, opposite) <= radius + _EPS:
                violations.append(
                    PathViolation(
                        code="BUILDING_BOUNDARY",
                        segment_index=segment_index,
                        object_id="building",
                        measured_distance_m=min(clearance, opposite),
                        required_distance_m=radius,
                        message=(
                            "pipe envelope touches or crosses building "
                            f"{('x', 'y', 'z')[axis]} boundary"
                        ),
                    )
                )
        for obstacle in project.obstacles:
            distance = segment_aabb_distance_m(start, end, obstacle.shape)
            if distance <= radius + _EPS:
                violations.append(
                    PathViolation(
                        code="OBSTACLE_COLLISION",
                        segment_index=segment_index,
                        object_id=obstacle.id,
                        measured_distance_m=distance,
                        required_distance_m=radius,
                        message=(
                            "insulated pipe touches or intersects "
                            "physical obstacle"
                        ),
                    )
                )
        for rule in rules:
            required = radius + (
                rule.parameters.distance_m
                if rule.type is ConstraintType.MIN_CLEARANCE
                else 0.0
            )
            for target_id in rule.scope.target_ids:
                distance = segment_aabb_distance_m(start, end, shapes[target_id])
                violated = (
                    distance <= required + _EPS
                    if rule.type is ConstraintType.KEEP_OUT
                    else distance < required - _EPS
                )
                if violated:
                    violations.append(
                        PathViolation(
                            code=rule.type.value,
                            segment_index=segment_index,
                            object_id=target_id,
                            rule_id=rule.id,
                            source=rule.source,
                            measured_distance_m=distance,
                            required_distance_m=required,
                            message="approved hard rule violated",
                        )
                    )
    return PathValidationResult(
        status=ValidationStatus.INVALID_ROUTE if violations else ValidationStatus.VALID,
        project_id=project.project_id,
        pipe_id=pipe_id,
        scenario_hash=fingerprint,
        applied_rule_ids=[rule.id for rule in rules],
        checked_segments=len(points_m) - 1,
        violations=violations,
        message=f"{len(violations)} violation(s)" if violations else "",
    )
