"""Continuous AABB geometry used to construct the conservative voxel grid."""

from math import isfinite

from plan_route.models.engineering import Pipe
from plan_route.models.geometry import AABB


def aabb_intersects(first: AABB, second: AABB) -> bool:
    """Return true for overlap or face/edge/point contact on every axis."""
    return all(
        first_min <= second_max and second_min <= first_max
        for first_min, first_max, second_min, second_max in zip(
            first.min_m, first.max_m, second.min_m, second.max_m, strict=True
        )
    )


def expand_aabb(box: AABB, radius_m: float) -> AABB:
    """Expand an AABB by an L-infinity margin in metres."""
    if not isfinite(radius_m) or radius_m < 0:
        raise ValueError("radius_m must be finite and nonnegative")
    return AABB(
        min_m=tuple(value - radius_m for value in box.min_m),
        max_m=tuple(value + radius_m for value in box.max_m),
    )


def effective_pipe_radius_m(pipe: Pipe) -> float:
    """Radius of the insulated pipe outside surface, excluding rule clearance."""
    return pipe.outer_diameter_m / 2 + pipe.insulation_thickness_m
