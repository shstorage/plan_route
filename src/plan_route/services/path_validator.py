"""Independent continuous-geometry validation of pipe centreline paths."""

import hashlib
from math import dist, isfinite, pi, sqrt

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


def segment_segment_closest(
    p1: Point3, q1: Point3, p2: Point3, q2: Point3
) -> tuple[float, float, float]:
    """Exact closest points of two closed 3D segments: (s, t, distance).

    s and t are the parameters on [p1, q1] and [p2, q2]. Standard clamped
    solution of the 2x2 least-squares system (Ericson, Real-Time Collision
    Detection, 5.1.9), including degenerate and parallel segments.
    """
    d1 = tuple(b - a for a, b in zip(p1, q1, strict=True))
    d2 = tuple(b - a for a, b in zip(p2, q2, strict=True))
    offset = tuple(a - b for a, b in zip(p1, p2, strict=True))
    a = sum(v * v for v in d1)
    e = sum(v * v for v in d2)
    f = sum(u * v for u, v in zip(d2, offset, strict=True))
    if a <= _EPS and e <= _EPS:
        return 0.0, 0.0, dist(p1, p2)
    if a <= _EPS:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = sum(u * v for u, v in zip(d1, offset, strict=True))
        if e <= _EPS:
            s, t = max(0.0, min(1.0, -c / a)), 0.0
        else:
            b = sum(u * v for u, v in zip(d1, d2, strict=True))
            denominator = a * e - b * b
            s = (
                max(0.0, min(1.0, (b * f - c * e) / denominator))
                if denominator > _EPS
                else 0.0
            )
            t = (b * s + f) / e
            if t < 0:
                t, s = 0.0, max(0.0, min(1.0, -c / a))
            elif t > 1:
                t, s = 1.0, max(0.0, min(1.0, (b - c) / a))
    first = tuple(x + s * v for x, v in zip(p1, d1, strict=True))
    second = tuple(x + t * v for x, v in zip(p2, d2, strict=True))
    return s, t, dist(first, second)


def _self_clearance_violations(
    pipe_id: str, points_m: tuple[Point3, ...], radius: float
) -> list[PathViolation]:
    """Distinct parts of one pipe must not let their envelopes touch.

    Two centreline points closer than one envelope diameter (2 x radius) are
    a conflict only if the path between them is longer than half a circle of
    that radius (pi x radius). Any plain elbow or offset stays below that
    bound (at most 2 x sqrt(2) x radius of path for points within one
    diameter), so only genuine fold-backs and crossings are reported. One
    violation is reported per later segment, against its earliest conflict.
    """
    segments = list(zip(points_m, points_m[1:]))
    lengths = [dist(start, end) for start, end in segments]
    offsets = [0.0]
    for length in lengths:
        offsets.append(offsets[-1] + length)
    required = 2 * radius
    violations: list[PathViolation] = []
    for later in range(2, len(segments)):
        for earlier in range(later - 1):
            s, t, distance = segment_segment_closest(
                *segments[earlier], *segments[later]
            )
            if distance > required + _EPS:
                continue
            along = (offsets[later] + t * lengths[later]) - (
                offsets[earlier] + s * lengths[earlier]
            )
            if along <= pi * radius + _EPS:
                continue
            violations.append(
                PathViolation(
                    code="SELF_CLEARANCE",
                    segment_index=later,
                    object_id=pipe_id,
                    measured_distance_m=distance,
                    required_distance_m=required,
                    message=(
                        f"pipe envelope overlaps its own segment {earlier} "
                        "(centrelines closer than one envelope diameter)"
                    ),
                )
            )
            break
    return violations


def _closest_on_segment(
    point: Point3, start: Point3, end: Point3, t_min: float
) -> tuple[float, float]:
    """Parameter in [t_min, 1] and distance of the closest segment point."""
    direction = tuple(b - a for a, b in zip(start, end, strict=True))
    length_squared = sum(value * value for value in direction)
    t = (
        sum((p - a) * d for p, a, d in zip(point, start, direction, strict=True))
        / length_squared
        if length_squared
        else 0.0
    )
    t = max(t_min, min(1.0, t))
    closest = tuple(a + t * d for a, d in zip(start, direction, strict=True))
    return t, sqrt(sum((p - c) ** 2 for p, c in zip(point, closest, strict=True)))


def _segment_axis(start: Point3, end: Point3) -> int | None:
    """World axis of an axis-parallel segment, else None."""
    moving = [axis for axis in range(3) if abs(end[axis] - start[axis]) > _EPS]
    return moving[0] if len(moving) == 1 else None


def waypoint_tolerance_m(project: EngineeringProject) -> float:
    """Allowed centreline offset from a waypoint: half a grid cell diagonal.

    Waypoints are meant to be placed on cell centres (the editor snaps them);
    the tolerance only absorbs an off-centre placement within one cell.
    """
    return sqrt(3) * project.routing_config.grid_resolution_m / 2


def _waypoint_violations(
    project: EngineeringProject, pipe_id: str, points_m: tuple[Point3, ...]
) -> list[PathViolation]:
    """Each waypoint must be passed, in order, along its pass_axis if given."""
    pipe = next(item for item in project.pipes if item.id == pipe_id)
    tolerance = waypoint_tolerance_m(project)
    segments = list(zip(points_m, points_m[1:]))
    violations: list[PathViolation] = []
    cursor_segment, cursor_t = 0, 0.0
    axes = {"x": 0, "y": 1, "z": 2}
    for waypoint in pipe.waypoints:
        match: tuple[int, float] | None = None
        nearest = float("inf")
        for index in range(cursor_segment, len(segments)):
            start, end = segments[index]
            t_min = cursor_t if index == cursor_segment else 0.0
            t, distance = _closest_on_segment(waypoint.position_m, start, end, t_min)
            nearest = min(nearest, distance)
            if distance <= tolerance + _EPS:
                match = (index, t)
                break
        if match is None:
            violations.append(
                PathViolation(
                    code="WAYPOINT_MISSED",
                    segment_index=min(cursor_segment, len(segments) - 1),
                    object_id=waypoint.id,
                    measured_distance_m=nearest,
                    required_distance_m=tolerance,
                    message=("path does not pass this waypoint after the previous one"),
                )
            )
            continue
        cursor_segment, cursor_t = match
        if waypoint.pass_axis is None:
            continue
        index, t = match
        touching = [index]
        if t <= _EPS and index > 0:
            touching.append(index - 1)
        if t >= 1 - _EPS and index + 1 < len(segments):
            touching.append(index + 1)
        axis = axes[waypoint.pass_axis]
        if any(_segment_axis(*segments[item]) != axis for item in touching):
            violations.append(
                PathViolation(
                    code="WAYPOINT_DIRECTION",
                    segment_index=index,
                    object_id=waypoint.id,
                    measured_distance_m=0,
                    required_distance_m=0,
                    message=(
                        f"path must run straight along {waypoint.pass_axis} "
                        "through this waypoint"
                    ),
                )
            )
    return violations


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
    violations.extend(_waypoint_violations(project, pipe_id, points_m))
    radius = effective_pipe_radius_m(pipe)
    violations.extend(_self_clearance_violations(pipe.id, points_m, radius))
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
                            "insulated pipe touches or intersects physical obstacle"
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
