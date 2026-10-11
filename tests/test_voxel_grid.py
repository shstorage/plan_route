"""P02 world-grid geometry and conservative collision-mask tests."""

import copy
import json
from importlib.resources import files
from math import inf, isclose

import pytest

from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import AABB
from plan_route.services.geometry import (
    aabb_intersects,
    effective_pipe_radius_m,
    expand_aabb,
)
from plan_route.services.voxel_grid import GridSpec, voxelize_project


@pytest.fixture
def demo_data():
    path = files("plan_route").joinpath("fixtures/demo_project.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_grid_origin_centre_and_exact_internal_boundary():
    spec = GridSpec(AABB(min_m=(-2, 5, -1), max_m=(1, 7, 2)), 1)
    assert spec.shape == (3, 2, 3)
    assert spec.world_to_grid((-2, 5, -1)) == (0, 0, 0)
    assert spec.grid_to_world((0, 0, 0)) == (-1.5, 5.5, -0.5)
    assert spec.world_to_grid((-1, 6, 0)) == (1, 1, 1)
    assert spec.world_to_grid(spec.grid_to_world((2, 1, 2))) == (2, 1, 2)
    assert spec.world_to_grid((1 - 1e-12, 6, 0)) == (2, 1, 1)
    assert list(spec.iter_indices())[0] == (0, 0, 0)
    assert list(spec.iter_indices())[-1] == (2, 1, 2)


@pytest.mark.parametrize(
    "point", [(-2.001, 5, 0), (1, 5, 0), (0, 7, 0), (0, 5, 2), (inf, 5, 0)]
)
def test_world_to_grid_rejects_out_of_bounds(point):
    spec = GridSpec(AABB(min_m=(-2, 5, -1), max_m=(1, 7, 2)), 1)
    with pytest.raises(ValueError):
        spec.world_to_grid(point)


@pytest.mark.parametrize("index", [(-1, 0, 0), (3, 0, 0), (0, 2, 0), (0, 0, 3)])
def test_grid_to_world_rejects_out_of_bounds(index):
    spec = GridSpec(AABB(min_m=(-2, 5, -1), max_m=(1, 7, 2)), 1)
    with pytest.raises(ValueError, match="grid index"):
        spec.grid_to_world(index)


def test_float_boundary_and_partial_last_cell():
    spec = GridSpec(AABB(min_m=(0, 0, 0), max_m=(0.3, 1, 1)), 0.1)
    assert spec.shape[0] == 3
    assert spec.world_to_grid((0.3 - 1e-12, 0.5, 0.5))[0] == 2
    assert spec.world_to_grid((0.1 + 0.1, 0.5, 0.5))[0] == 2
    with pytest.raises(ValueError):
        spec.world_to_grid((0.3, 0.5, 0.5))

    partial = GridSpec(AABB(min_m=(0, 0, 0), max_m=(2.3, 1, 1)), 1)
    assert partial.shape == (3, 1, 1)
    assert partial.cell_bounds((2, 0, 0)).max_m[0] == 2.3
    assert isclose(partial.grid_to_world((2, 0, 0))[0], 2.15)
    assert partial.world_to_grid(partial.grid_to_world((2, 0, 0))) == (2, 0, 0)


def test_invalid_grid_resolution_and_tiny_valid_bounds():
    bounds = AABB(min_m=(0, 0, 0), max_m=(0.000000000001, 1, 1))
    assert GridSpec(bounds, 1).shape == (1, 1, 1)
    for invalid in (0, -1, inf):
        with pytest.raises(ValueError, match="resolution_m"):
            GridSpec(bounds, invalid)


def test_aabb_contact_and_inflation():
    first = AABB(min_m=(0, 0, 0), max_m=(1, 1, 1))
    touching = AABB(min_m=(1, 1, 1), max_m=(2, 2, 2))
    separate = AABB(min_m=(1.01, 1, 1), max_m=(2, 2, 2))
    assert aabb_intersects(first, touching)
    assert aabb_intersects(touching, first)
    assert not aabb_intersects(first, separate)
    assert expand_aabb(first, 0.2).min_m == (-0.2, -0.2, -0.2)
    assert expand_aabb(first, 0.2).max_m == (1.2, 1.2, 1.2)
    for invalid in (-0.1, inf):
        with pytest.raises(ValueError, match="radius_m"):
            expand_aabb(first, invalid)


def _small_project(demo_data):
    data = copy.deepcopy(demo_data)
    data["building"]["bounds_m"]["max_m"] = [5, 3, 3]
    data["building"]["floors"][0]["z_max_m"] = 3
    data["obstacles"][0]["shape"] = {
        "type": "aabb",
        "min_m": [2.2, 0, 0],
        "max_m": [2.8, 3, 3],
    }
    data["zones"][0]["shape"] = {
        "type": "aabb",
        "min_m": [1.1, 1.1, 1.1],
        "max_m": [1.4, 1.4, 1.4],
    }
    data["equipment"][0]["ports"][0]["position_m"] = [1.5, 1.5, 1.5]
    data["equipment"][1]["ports"][0]["position_m"] = [3.5, 1.5, 1.5]
    data["pipes"][0]["outer_diameter_m"] = 0.2
    data["pipes"][0]["insulation_thickness_m"] = 0
    data["routing_config"]["grid_resolution_m"] = 1
    return data


def test_wall_without_opening_blocks_every_crossing_cell(demo_data):
    project = EngineeringProject.model_validate(_small_project(demo_data))
    grid = voxelize_project(project, "PIPE-101")
    assert grid.spec.shape == (5, 3, 3)
    assert grid.is_traversable((1, 1, 1))
    assert grid.is_traversable((3, 1, 1))
    assert all((2, j, k) in grid.obstacle_cells for j in range(3) for k in range(3))
    assert all(not grid.is_traversable((2, j, k)) for j in range(3) for k in range(3))
    assert not grid.is_traversable((0, 1, 1))  # Pipe radius clips building edge.


def test_zone_is_separate_and_does_not_block_before_compilation(demo_data):
    project = EngineeringProject.model_validate(_small_project(demo_data))
    grid = voxelize_project(project, "PIPE-101")
    cell = (1, 1, 1)
    assert cell in grid.zone_cells["ZONE-A"]
    assert grid.zones_at(cell) == frozenset({"ZONE-A"})
    assert cell not in grid.obstacle_cells
    assert grid.is_traversable(cell)
    assert "z" in grid.slice_text(1)
    with pytest.raises(ValueError, match="z slice"):
        grid.slice_text(3)


def test_larger_insulated_radius_blocks_more_cells(demo_data):
    data = _small_project(demo_data)
    data["obstacles"][0]["shape"] = {
        "type": "aabb",
        "min_m": [2.4, 1.4, 1.4],
        "max_m": [2.6, 1.6, 1.6],
    }
    small = EngineeringProject.model_validate(data)
    data["pipes"][0]["insulation_thickness_m"] = 1.0
    large = EngineeringProject.model_validate(data)
    small_grid = voxelize_project(small, "PIPE-101")
    large_grid = voxelize_project(large, "PIPE-101")
    assert effective_pipe_radius_m(small.pipes[0]) == 0.1
    assert effective_pipe_radius_m(large.pipes[0]) == 1.1
    assert small_grid.obstacle_cells < large_grid.obstacle_cells
    assert large_grid.interior_cells < small_grid.interior_cells


def test_voxelization_is_deterministic_and_unknown_pipe_fails(demo_data):
    project = EngineeringProject.model_validate(_small_project(demo_data))
    first = voxelize_project(project, "PIPE-101")
    second = voxelize_project(project, "PIPE-101")
    assert first.spec == second.spec
    assert first.interior_cells == second.interior_cells
    assert first.obstacle_cells == second.obstacle_cells
    assert dict(first.zone_cells) == dict(second.zone_cells)
    assert first.slice_text(1) == second.slice_text(1)
    with pytest.raises(ValueError, match="unknown pipe ID"):
        voxelize_project(project, "MISSING")
