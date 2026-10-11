"""Single-source EngineeringProject document and cross-reference validation."""

from typing import Literal

from pydantic import Field, model_validator

from plan_route.models.constraints import Constraint, ConstraintType
from plan_route.models.geometry import (
    AABB,
    ContractModel,
    CoordinateFrame,
    Identifier,
    Point3,
)


class Floor(ContractModel):
    id: Identifier
    z_min_m: float = Field(allow_inf_nan=False)
    z_max_m: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def check_height(self) -> "Floor":
        if self.z_min_m >= self.z_max_m:
            raise ValueError("floor z_min_m must be less than z_max_m")
        return self


class Building(ContractModel):
    bounds_m: AABB
    floors: list[Floor] = Field(min_length=1)

    @model_validator(mode="after")
    def check_floors(self) -> "Building":
        low, high = self.bounds_m.min_m[2], self.bounds_m.max_m[2]
        for floor in self.floors:
            if not (low <= floor.z_min_m < floor.z_max_m <= high):
                raise ValueError(f"floor {floor.id} lies outside building bounds_m")
        return self


class Obstacle(ContractModel):
    id: Identifier
    kind: Identifier
    shape: AABB


class Zone(ContractModel):
    id: Identifier
    zone_type: Identifier
    shape: AABB


class Port(ContractModel):
    id: Identifier
    position_m: Point3
    orientation: Literal["+x", "-x", "+y", "-y", "+z", "-z"]


class Equipment(ContractModel):
    id: Identifier
    kind: Identifier
    geometry_ref: Identifier | None = None
    ports: list[Port] = Field(min_length=1)


class Pipe(ContractModel):
    id: Identifier
    from_port_id: Identifier
    to_port_id: Identifier
    outer_diameter_m: float = Field(gt=0, allow_inf_nan=False)
    insulation_thickness_m: float = Field(ge=0, allow_inf_nan=False)
    clearance_margin_m: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description=(
            "User-chosen extra envelope thickness added outside the insulation "
            "for every geometric check; a study assumption, not a code value."
        ),
    )
    train_id: Identifier | None = None

    @model_validator(mode="after")
    def check_endpoints(self) -> "Pipe":
        if self.from_port_id == self.to_port_id:
            raise ValueError("pipe endpoints must reference different ports")
        return self


class CostWeights(ContractModel):
    length_per_m: float = Field(gt=0, allow_inf_nan=False)
    bend_per_event: float = Field(ge=0, allow_inf_nan=False)
    preferred_zone_factor: float = Field(gt=0, allow_inf_nan=False)


class SearchLimits(ContractModel):
    max_expansions: int = Field(gt=0, strict=True)


class RoutingConfig(ContractModel):
    grid_resolution_m: float = Field(gt=0, allow_inf_nan=False)
    cost_weights: CostWeights
    search_limits: SearchLimits


class EngineeringProject(ContractModel):
    schema_version: Literal["1.0.0"]
    project_id: Identifier
    study_type: Literal["synthetic_benchmark"]
    unit_system: Literal["SI"]
    coordinate_frame: CoordinateFrame
    building: Building
    obstacles: list[Obstacle]
    zones: list[Zone]
    equipment: list[Equipment]
    pipes: list[Pipe]
    constraints: list[Constraint]
    routing_config: RoutingConfig

    @model_validator(mode="after")
    def check_references(self) -> "EngineeringProject":
        ids: dict[str, str] = {self.project_id: "project"}

        def register(identifier: str, kind: str) -> None:
            if identifier in ids:
                raise ValueError(
                    f"duplicate ID {identifier}: {kind} conflicts with "
                    f"{ids[identifier]}"
                )
            ids[identifier] = kind

        bounds = self.building.bounds_m
        for floor in self.building.floors:
            register(floor.id, "floor")
        obstacle_ids = set()
        for obstacle in self.obstacles:
            register(obstacle.id, "obstacle")
            obstacle_ids.add(obstacle.id)
            if not bounds.contains_box(obstacle.shape):
                raise ValueError(
                    f"obstacle {obstacle.id} lies outside building bounds_m"
                )
        zone_ids = set()
        for zone in self.zones:
            register(zone.id, "zone")
            zone_ids.add(zone.id)
            if not bounds.contains_box(zone.shape):
                raise ValueError(f"zone {zone.id} lies outside building bounds_m")

        port_owners: dict[str, str] = {}
        for equipment in self.equipment:
            register(equipment.id, "equipment")
            if equipment.geometry_ref and equipment.geometry_ref not in obstacle_ids:
                raise ValueError(
                    f"equipment {equipment.id} geometry_ref "
                    f"{equipment.geometry_ref} does not reference an obstacle"
                )
            for port in equipment.ports:
                register(port.id, "port")
                port_owners[port.id] = equipment.id
                if not bounds.contains(port.position_m):
                    raise ValueError(f"port {port.id} lies outside building bounds_m")

        pipe_ids = set()
        for pipe in self.pipes:
            register(pipe.id, "pipe")
            pipe_ids.add(pipe.id)
            if pipe.from_port_id not in port_owners:
                raise ValueError(
                    f"pipe {pipe.id} from_port_id {pipe.from_port_id} is unknown"
                )
            if pipe.to_port_id not in port_owners:
                raise ValueError(
                    f"pipe {pipe.id} to_port_id {pipe.to_port_id} is unknown"
                )

        for rule in self.constraints:
            register(rule.id, "constraint")
            for pipe_id in rule.scope.pipe_ids:
                if pipe_id not in pipe_ids:
                    raise ValueError(
                        f"constraint {rule.id} references unknown pipe {pipe_id}"
                    )
            valid_targets = (
                zone_ids
                if rule.type is ConstraintType.KEEP_OUT
                else (zone_ids | obstacle_ids)
            )
            for target_id in rule.scope.target_ids:
                if target_id not in valid_targets:
                    raise ValueError(
                        f"constraint {rule.id} references invalid target {target_id}"
                    )
        return self


Project = EngineeringProject
