"""Independent continuous-geometry validation of pipe centreline paths."""

import hashlib
from math import ceil, dist, floor, isclose, isfinite, sqrt

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
    if a == 0 and e == 0:
        return 0.0, 0.0, dist(p1, p2)
    if a == 0:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = sum(u * v for u, v in zip(d1, offset, strict=True))
        if e == 0:
            s, t = max(0.0, min(1.0, -c / a)), 0.0
        else:
            b = sum(u * v for u, v in zip(d1, d2, strict=True))
            denominator = a * e - b * b
            s = (
                max(0.0, min(1.0, (b * f - c * e) / denominator))
                if denominator > 1e-14 * a * e
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


def _arc_separated_distance(
    first: tuple[Point3, Point3],
    second: tuple[Point3, Point3],
    length_first: float,
    length_second: float,
    offset: float,
    separation: float,
) -> float:
    """Minimize distance on [0,1]^2 clipped by offset+t*L2-s*L1 >= separation.

    Squared distance is convex quadratic. Its minimum is either the free
    segment-pair minimum or a minimum on one edge of the clipped polygon.
    This examines all arc-separated point pairs, not just one closest pair.
    """

    def gap(point):
        return offset + point[1] * length_second - point[0] * length_first

    polygon = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    clipped = []
    for left, right in zip(polygon, polygon[1:] + polygon[:1]):
        gl, gr = gap(left) - separation, gap(right) - separation
        if gl >= 0:
            clipped.append(left)
        if (gl >= 0) != (gr >= 0):
            alpha = gl / (gl - gr)
            clipped.append(tuple(a + alpha * (b - a) for a, b in zip(left, right)))
    if not clipped:
        return float("inf")
    delta1 = tuple(b - a for a, b in zip(*first))
    delta2 = tuple(b - a for a, b in zip(*second))

    def difference(point):
        s, t = point
        return tuple(
            a + s * d1 - b - t * d2
            for a, b, d1, d2 in zip(first[0], second[0], delta1, delta2)
        )

    s, t, free_distance = segment_segment_closest(*first, *second)
    candidates = [free_distance] if gap((s, t)) >= separation else []
    for left, right in zip(clipped, clipped[1:] + clipped[:1]):
        start, end = difference(left), difference(right)
        change = tuple(b - a for a, b in zip(start, end))
        norm = sum(value * value for value in change)
        alpha = (
            max(0.0, min(1.0, -sum(a * d for a, d in zip(start, change)) / norm))
            if norm
            else 0.0
        )
        candidates.append(
            sqrt(sum((a + alpha * d) ** 2 for a, d in zip(start, change)))
        )
    return min(candidates)


def _straight_runs(points_m):
    """Merge forward-collinear subdivisions and retain original segment indices."""
    segments, original_indices = [], []
    for index, (start, end) in enumerate(zip(points_m, points_m[1:])):
        if segments:
            first = tuple(b - a for a, b in zip(*segments[-1]))
            second = tuple(b - a for a, b in zip(start, end))
            cosine = sum(a * b for a, b in zip(first, second)) / (
                dist(*segments[-1]) * dist(start, end)
            )
            if cosine >= 1 - 1e-12:
                segments[-1] = (segments[-1][0], end)
                continue
        segments.append((start, end))
        original_indices.append(index)
    return segments, original_indices


def _self_clearance_violations(
    pipe_id: str, points_m: tuple[Point3, ...], radius: float
) -> list[PathViolation]:
    """Study envelope policy on maximal straight runs, independent of subdivision.

    Adjacent non-reversing runs are joints and exempt. Other point pairs with
    path separation > 2*sqrt(3)*r must stay more than a diameter apart. This
    bound exempts monotone 3D offsets: L1 <= sqrt(3)*L2. It is a declared
    polyline policy, not an elbow fabrication/bend-radius model.
    """
    segments, original_indices = _straight_runs(points_m)
    lengths = [dist(start, end) for start, end in segments]
    offsets = [0.0]
    for length in lengths:
        offsets.append(offsets[-1] + length)
    required = 2 * radius
    violations: list[PathViolation] = []
    for later in range(1, len(segments)):
        for earlier in range(later):
            first, second = segments[earlier], segments[later]
            reverse = False
            if earlier == later - 1:
                delta1 = tuple(b - a for a, b in zip(*first))
                delta2 = tuple(b - a for a, b in zip(*second))
                cosine = sum(a * b for a, b in zip(delta1, delta2)) / (
                    lengths[earlier] * lengths[later]
                )
                reverse = cosine <= -1 + 1e-12
                if not reverse:
                    continue
            # Cheap lower bound using the two segment bounding boxes.
            lower = sum(
                max(min(a, b) - max(c, d), min(c, d) - max(a, b), 0.0) ** 2
                for a, b, c, d in zip(*first, *second)
            )
            if not reverse and lower > (required + _EPS) ** 2:
                continue
            if reverse:
                distance = 0.0
            else:
                separation = 2 * sqrt(3) * radius + 2 * _EPS
                offset = offsets[later] - offsets[earlier]
                if offset + lengths[later] < separation:
                    continue
                distance = _arc_separated_distance(
                    first, second, lengths[earlier], lengths[later], offset, separation
                )
            if distance > required + _EPS:
                continue
            violations.append(
                PathViolation(
                    code="SELF_CLEARANCE",
                    segment_index=original_indices[later],
                    object_id=pipe_id,
                    measured_distance_m=distance,
                    required_distance_m=required,
                    message=(
                        f"pipe envelope overlaps its own segment "
                        f"{original_indices[earlier]}; "
                        "adjacent reversal or arc-separated envelope contact"
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


def _signed_segment_axis(start: Point3, end: Point3) -> tuple[int, int] | None:
    axis = _segment_axis(start, end)
    return None if axis is None else (axis, 1 if end[axis] > start[axis] else -1)


def _port_cell_centre(project: EngineeringProject, point: Point3) -> Point3:
    """Connector contract geometry only; no voxelizer/mask/search state reused."""
    bounds = project.building.bounds_m
    step = project.routing_config.grid_resolution_m
    centre = []
    for value, low, high in zip(point, bounds.min_m, bounds.max_m):
        quotient = (value - low) / step
        span = (high - low) / step
        count = (
            round(span)
            if round(span) >= 1 and isclose(span, round(span), abs_tol=1e-9, rel_tol=0)
            else ceil(span)
        )
        nearest = round(quotient)
        if 0 <= nearest < count and isclose(quotient, nearest, abs_tol=1e-9, rel_tol=0):
            quotient = nearest
        index = min(count - 1, max(0, floor(quotient)))
        centre.append((low + index * step + min(high, low + (index + 1) * step)) / 2)
    return tuple(centre)


def _direction_violations(project, pipe, points) -> list[PathViolation]:
    ports = {p.id: p for equipment in project.equipment for p in equipment.ports}
    source, target = ports[pipe.from_port_id], ports[pipe.to_port_id]
    first, stop = 0, len(points) - 1

    def same(a, b):
        return all(abs(x - y) <= _EPS for x, y in zip(a, b))

    start_centre = _port_cell_centre(project, source.position_m)
    end_centre = _port_cell_centre(project, target.position_m)
    # Only exactly the declared source/target-to-containing-cell links are exempt.
    if not same(source.position_m, start_centre) and same(points[1], start_centre):
        first += 1
    if not same(target.position_m, end_centre) and same(points[-2], end_centre):
        stop -= 1
    violations = []
    for index in range(first, stop):
        if _segment_axis(points[index], points[index + 1]) is None:
            violations.append(
                PathViolation(
                    code="NON_ORTHOGONAL",
                    segment_index=index,
                    object_id=pipe.id,
                    measured_distance_m=0,
                    required_distance_m=0,
                    message="route core must consist of axis-parallel segments",
                )
            )
    if first < stop:
        for index, port, sign in (
            (first, source, 1),
            (stop - 1, target, -1),
        ):
            expected = (
                "xyz".index(port.orientation[1]),
                sign * (1 if port.orientation[0] == "+" else -1),
            )
            if _signed_segment_axis(points[index], points[index + 1]) != expected:
                violations.append(
                    PathViolation(
                        code="PORT_DIRECTION",
                        segment_index=index,
                        object_id=port.id,
                        measured_distance_m=0,
                        required_distance_m=0,
                        message="route core direction disagrees with port orientation",
                    )
                )
    return violations


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
    segments, original_indices = _straight_runs(points_m)
    violations: list[PathViolation] = []
    cursor_segment, cursor_t = 0, 0.0
    axes = {"x": 0, "y": 1, "z": 2}
    for waypoint in pipe.waypoints:
        match: tuple[int, float] | None = None
        nearest = float("inf")
        near_segment: int | None = None
        for index in range(cursor_segment, len(segments)):
            start, end = segments[index]
            t_min = cursor_t if index == cursor_segment else 0.0
            t, distance = _closest_on_segment(waypoint.position_m, start, end, t_min)
            nearest = min(nearest, distance)
            if distance > tolerance + _EPS:
                continue
            if near_segment is None:
                near_segment = index
            if waypoint.pass_axis is not None:
                touching = [index]
                if t <= _EPS and index > 0:
                    touching.append(index - 1)
                if t >= 1 - _EPS and index + 1 < len(segments):
                    touching.append(index + 1)
                axis = axes[waypoint.pass_axis]
                directions = [
                    _signed_segment_axis(*segments[item]) for item in touching
                ]
                if (
                    any(item is None or item[0] != axis for item in directions)
                    or len(set(directions)) != 1
                ):
                    continue
            match = (index, t)
            break
        if match is None:
            violations.append(
                PathViolation(
                    code="WAYPOINT_DIRECTION"
                    if near_segment is not None
                    else "WAYPOINT_MISSED",
                    segment_index=original_indices[
                        near_segment
                        if near_segment is not None
                        else min(cursor_segment, len(segments) - 1)
                    ],
                    object_id=waypoint.id,
                    measured_distance_m=nearest,
                    required_distance_m=tolerance,
                    message=(
                        "no ordered waypoint pass satisfies distance and direction"
                    ),
                )
            )
            continue
        cursor_segment, cursor_t = match
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
        rule.id
        for rule in rules
        if rule.status is not ConstraintStatus.APPROVED or not rule.approval_is_current
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
    violations.extend(_direction_violations(project, pipe, points_m))
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
        waypoint_tolerance_m=waypoint_tolerance_m(project),
        violations=violations,
        message=f"{len(violations)} violation(s)" if violations else "",
    )
