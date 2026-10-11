"""Deterministic, conservative grid derived from an EngineeringProject."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cached_property
from itertools import product
from math import ceil, floor, isclose, isfinite
from types import MappingProxyType

from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import AABB, GridIndex, Point3
from plan_route.services.geometry import effective_pipe_radius_m, expand_aabb

_GRID_TOLERANCE = 1e-9  # Relative to one cell, only for floating-point arithmetic.


def _cell_count(span_m: float, resolution_m: float) -> int:
    quotient = span_m / resolution_m
    nearest = round(quotient)
    if nearest >= 1 and isclose(quotient, nearest, rel_tol=0, abs_tol=_GRID_TOLERANCE):
        return nearest
    return ceil(quotient)


@dataclass(frozen=True)
class GridSpec:
    """Grid geometry; the final cell may be clipped at the building maximum."""

    bounds_m: AABB
    resolution_m: float

    def __post_init__(self) -> None:
        if not isfinite(self.resolution_m) or self.resolution_m <= 0:
            raise ValueError("resolution_m must be finite and positive")

    @cached_property
    def shape(self) -> GridIndex:
        return tuple(
            _cell_count(high - low, self.resolution_m)
            for low, high in zip(self.bounds_m.min_m, self.bounds_m.max_m, strict=True)
        )

    @cached_property
    def axis_intervals(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        """Per-axis (cell_min, cell_max) in metres; a cell box is their product."""
        return tuple(
            tuple(
                (
                    low + value * self.resolution_m,
                    high
                    if value == count - 1
                    else min(low + (value + 1) * self.resolution_m, high),
                )
                for value in range(count)
            )
            for low, high, count in zip(
                self.bounds_m.min_m, self.bounds_m.max_m, self.shape, strict=True
            )
        )

    def _axis_touching(self, axis: int, box_min: float, box_max: float) -> list[int]:
        intervals = self.axis_intervals[axis]
        # Index window is a superset; the exact closed-interval test decides.
        first = max(
            floor((box_min - self.bounds_m.min_m[axis]) / self.resolution_m) - 1, 0
        )
        last = min(
            floor((box_max - self.bounds_m.min_m[axis]) / self.resolution_m) + 1,
            len(intervals) - 1,
        )
        return [
            value
            for value in range(first, last + 1)
            if intervals[value][0] <= box_max and box_min <= intervals[value][1]
        ]

    def cells_touching(self, box: AABB) -> set[GridIndex]:
        """Cells whose closed box intersects `box`, same rule as aabb_intersects."""
        return set(
            product(
                *(
                    self._axis_touching(axis, box.min_m[axis], box.max_m[axis])
                    for axis in range(3)
                )
            )
        )

    def contains_index(self, index: GridIndex) -> bool:
        return (
            len(index) == 3
            and all(type(value) is int for value in index)
            and all(0 <= value < count for value, count in zip(index, self.shape))
        )

    def world_to_grid(self, point_m: Point3) -> GridIndex:
        if len(point_m) != 3 or not all(isfinite(value) for value in point_m):
            raise ValueError("point_m must contain three finite metre coordinates")
        result = []
        for value, low, high, count in zip(
            point_m, self.bounds_m.min_m, self.bounds_m.max_m, self.shape, strict=True
        ):
            if not low <= value < high:
                raise ValueError("point_m is outside grid bounds")
            quotient = (value - low) / self.resolution_m
            nearest = round(quotient)
            # Snap only to internal boundaries; never move an in-bounds point
            # across the exclusive building maximum.
            if 0 <= nearest < count and isclose(
                quotient, nearest, rel_tol=0, abs_tol=_GRID_TOLERANCE
            ):
                quotient = nearest
            result.append(min(floor(quotient), count - 1))
        return tuple(result)

    def cell_bounds(self, index: GridIndex) -> AABB:
        if not self.contains_index(index):
            raise ValueError("grid index is outside grid bounds")
        intervals = [
            self.axis_intervals[axis][value] for axis, value in enumerate(index)
        ]
        return AABB(
            min_m=tuple(low for low, _ in intervals),
            max_m=tuple(high for _, high in intervals),
        )

    def grid_to_world(self, index: GridIndex) -> Point3:
        if not self.contains_index(index):
            raise ValueError("grid index is outside grid bounds")
        return tuple(
            (low + high) / 2
            for low, high in (
                self.axis_intervals[axis][value] for axis, value in enumerate(index)
            )
        )

    def iter_indices(self) -> Iterator[GridIndex]:
        nx, ny, nz = self.shape
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    yield i, j, k


@dataclass(frozen=True)
class VoxelGrid:
    spec: GridSpec
    pipe_id: str
    effective_radius_m: float
    interior_cells: frozenset[GridIndex]
    obstacle_cells: frozenset[GridIndex]
    zone_cells: Mapping[str, frozenset[GridIndex]]
    rule_cells: frozenset[GridIndex] = frozenset()

    def is_traversable(self, index: GridIndex) -> bool:
        return (
            index in self.interior_cells
            and index not in self.obstacle_cells
            and index not in self.rule_cells
        )

    def zones_at(self, index: GridIndex) -> frozenset[str]:
        return frozenset(
            zone_id for zone_id, cells in self.zone_cells.items() if index in cells
        )

    def slice_text(self, k: int) -> str:
        """Render a z-slice for debugging. Y runs top-to-bottom."""
        nx, ny, nz = self.spec.shape
        if not 0 <= k < nz:
            raise ValueError("z slice is outside grid bounds")
        rows = []
        for j in range(ny - 1, -1, -1):
            row = []
            for i in range(nx):
                index = (i, j, k)
                if index not in self.interior_cells:
                    row.append("X")
                elif index in self.obstacle_cells:
                    row.append("#")
                elif index in self.rule_cells:
                    row.append("!")
                elif self.zones_at(index):
                    row.append("z")
                else:
                    row.append(".")
            rows.append("".join(row))
        return "\n".join(rows)


def voxelize_project(project: EngineeringProject, pipe_id: str) -> VoxelGrid:
    """Build independent interior, physical-obstacle and uncompiled Zone masks.

    A cell is physically blocked if its closed box touches an obstacle AABB
    expanded by the insulated pipe radius. A cell is interior only if its
    whole box plus that radius fits inside the building. Zone cells remain
    traversable here; approved-rule compilation is a later phase.
    """
    pipe = next((pipe for pipe in project.pipes if pipe.id == pipe_id), None)
    if pipe is None:
        raise ValueError(f"unknown pipe ID: {pipe_id}")
    radius = effective_pipe_radius_m(pipe)
    spec = GridSpec(
        bounds_m=project.building.bounds_m,
        resolution_m=project.routing_config.grid_resolution_m,
    )
    inflated_obstacles = [expand_aabb(item.shape, radius) for item in project.obstacles]
    building = project.building.bounds_m
    # The interior test is separable per axis, so the interior set is a product.
    interior = set(
        product(
            *(
                [
                    value
                    for value, (cell_low, cell_high) in enumerate(
                        spec.axis_intervals[axis]
                    )
                    if building.min_m[axis] + radius <= cell_low
                    and cell_high <= building.max_m[axis] - radius
                ]
                for axis in range(3)
            )
        )
    )
    obstacles: set[GridIndex] = set()
    for box in inflated_obstacles:
        obstacles |= spec.cells_touching(box)
    zones = {zone.id: spec.cells_touching(zone.shape) for zone in project.zones}

    return VoxelGrid(
        spec=spec,
        pipe_id=pipe.id,
        effective_radius_m=radius,
        interior_cells=frozenset(interior),
        obstacle_cells=frozenset(obstacles),
        zone_cells=MappingProxyType(
            {zone_id: frozenset(cells) for zone_id, cells in zones.items()}
        ),
    )
