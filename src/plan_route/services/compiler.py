"""Compile approved hard rules into a separate forbidden-cell mask."""

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from math import isfinite

from plan_route.models.constraints import (
    Constraint,
    ConstraintStatus,
    ConstraintType,
    RuleSource,
)
from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import AABB, GridIndex
from plan_route.services.geometry import aabb_intersects, expand_aabb
from plan_route.services.voxel_grid import VoxelGrid, voxelize_project


class CompilationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    INVALID_INPUT = "INVALID_INPUT"
    UNAPPROVED_RULE = "UNAPPROVED_RULE"
    RULE_CONFLICT = "RULE_CONFLICT"


@dataclass(frozen=True)
class RuleImpact:
    rule_id: str
    rule_type: ConstraintType
    target_ids: tuple[str, ...]
    source: RuleSource
    affected_cells_count: int
    newly_blocked_cells_count: int


@dataclass(frozen=True)
class CompilationResult:
    status: CompilationStatus
    project_id: str
    pipe_id: str
    project_fingerprint: str
    grid: VoxelGrid | None
    applied_rule_ids: tuple[str, ...]
    impacts: tuple[RuleImpact, ...]
    message: str

    @property
    def rule_blocked_cells_count(self) -> int:
        return len(self.grid.rule_cells) if self.grid is not None else 0


def project_fingerprint(project: EngineeringProject) -> str:
    """Bind a compiled mask to the exact validated document it came from."""
    canonical = json.dumps(
        project.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _failure(
    status: CompilationStatus,
    project: EngineeringProject,
    pipe_id: str,
    fingerprint: str,
    message: str,
) -> CompilationResult:
    return CompilationResult(
        status=status,
        project_id=project.project_id,
        pipe_id=pipe_id,
        project_fingerprint=fingerprint,
        grid=None,
        applied_rule_ids=(),
        impacts=(),
        message=message,
    )


def _expanded_targets(
    rule: Constraint,
    shapes: dict[str, AABB],
    pipe_radius_m: float,
) -> tuple[AABB, ...]:
    if rule.type is ConstraintType.KEEP_OUT:
        extra_distance = 0.0
    elif rule.type is ConstraintType.MIN_CLEARANCE:
        extra_distance = rule.parameters.distance_m
        if (
            extra_distance is None
            or not isfinite(extra_distance)
            or extra_distance < 0
            or rule.parameters.distance_basis
            != "insulated_pipe_surface_to_target_surface"
        ):
            raise ValueError(
                f"rule {rule.id} has missing or invalid clearance basis/value"
            )
    else:
        raise ValueError(f"rule {rule.id} has unsupported type {rule.type}")
    try:
        return tuple(
            expand_aabb(shapes[target_id], pipe_radius_m + extra_distance)
            for target_id in rule.scope.target_ids
        )
    except KeyError as error:
        raise ValueError(
            f"rule {rule.id} references unknown target {error.args[0]}"
        ) from error


def compile_constraints(project: EngineeringProject, pipe_id: str) -> CompilationResult:
    """Compile relevant approved rules, failing closed on unapproved input.

    Affected counts include all interior cells covered by each rule. Newly
    blocked counts exclude physical obstacles and earlier rule masks.
    """
    fingerprint = project_fingerprint(project)
    pipe = next((item for item in project.pipes if item.id == pipe_id), None)
    if pipe is None:
        return _failure(
            CompilationStatus.INVALID_INPUT,
            project,
            pipe_id,
            fingerprint,
            f"unknown pipe ID: {pipe_id}",
        )
    relevant = sorted(
        (rule for rule in project.constraints if pipe_id in rule.scope.pipe_ids),
        key=lambda rule: rule.id,
    )
    unapproved = [
        rule.id for rule in relevant if rule.status is not ConstraintStatus.APPROVED
    ]
    if unapproved:
        return _failure(
            CompilationStatus.UNAPPROVED_RULE,
            project,
            pipe_id,
            fingerprint,
            f"unapproved rules for pipe {pipe_id}: {', '.join(unapproved)}",
        )
    grid = voxelize_project(project, pipe_id)
    shapes: dict[str, AABB] = {
        **{item.id: item.shape for item in project.obstacles},
        **{item.id: item.shape for item in project.zones},
    }
    zone_ids = {item.id for item in project.zones}
    blocked: set[GridIndex] = set()
    impacts: list[RuleImpact] = []
    rule_cells_by_id: dict[str, set[GridIndex]] = {}

    for rule in relevant:
        if (
            not rule.source.document_id
            or not rule.source.document_revision
            or not rule.source.clause_id
            or not rule.source.evidence_text
        ):
            return _failure(
                CompilationStatus.INVALID_INPUT,
                project,
                pipe_id,
                fingerprint,
                f"rule {rule.id} has incomplete source provenance",
            )
        if (
            rule.type is ConstraintType.KEEP_OUT
            and not set(rule.scope.target_ids) <= zone_ids
        ):
            return _failure(
                CompilationStatus.INVALID_INPUT,
                project,
                pipe_id,
                fingerprint,
                f"rule {rule.id} KEEP_OUT requires Zone targets",
            )
        if not rule.scope.target_ids:
            return _failure(
                CompilationStatus.INVALID_INPUT,
                project,
                pipe_id,
                fingerprint,
                f"rule {rule.id} has no targets",
            )
        try:
            targets = _expanded_targets(rule, shapes, grid.effective_radius_m)
        except ValueError as error:
            return _failure(
                CompilationStatus.INVALID_INPUT,
                project,
                pipe_id,
                fingerprint,
                str(error),
            )
        covered = {
            index
            for index in grid.interior_cells
            if any(
                aabb_intersects(grid.spec.cell_bounds(index), box) for box in targets
            )
        }
        rule_cells_by_id[rule.id] = covered
        newly_blocked = covered - grid.obstacle_cells - blocked
        blocked.update(covered)
        impacts.append(
            RuleImpact(
                rule_id=rule.id,
                rule_type=rule.type,
                target_ids=tuple(rule.scope.target_ids),
                source=rule.source,
                affected_cells_count=len(covered),
                newly_blocked_cells_count=len(newly_blocked),
            )
        )

    for equipment in project.equipment:
        for port in equipment.ports:
            if port.id not in (pipe.from_port_id, pipe.to_port_id):
                continue
            try:
                port_cell = grid.spec.world_to_grid(port.position_m)
            except ValueError as error:
                return _failure(
                    CompilationStatus.INVALID_INPUT,
                    project,
                    pipe_id,
                    fingerprint,
                    f"port {port.id}: {error}",
                )
            if not grid.is_traversable(port_cell):
                return _failure(
                    CompilationStatus.INVALID_INPUT,
                    project,
                    pipe_id,
                    fingerprint,
                    f"port {port.id} snaps to a physical blocked cell",
                )
            if port_cell in blocked:
                conflicting = [
                    impact.rule_id
                    for impact in impacts
                    if port_cell in rule_cells_by_id[impact.rule_id]
                ]
                return _failure(
                    CompilationStatus.RULE_CONFLICT,
                    project,
                    pipe_id,
                    fingerprint,
                    f"port {port.id} is blocked by approved rules: "
                    f"{', '.join(conflicting)}",
                )

    return CompilationResult(
        status=CompilationStatus.SUCCESS,
        project_id=project.project_id,
        pipe_id=pipe_id,
        project_fingerprint=fingerprint,
        grid=replace(grid, rule_cells=frozenset(blocked)),
        applied_rule_ids=tuple(rule.id for rule in relevant),
        impacts=tuple(impacts),
        message="",
    )
