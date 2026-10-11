"""Traceable design-rule contracts; no rule execution occurs here."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from plan_route.models.geometry import ContractModel, Identifier


class ConstraintType(StrEnum):
    KEEP_OUT = "KEEP_OUT"
    MIN_CLEARANCE = "MIN_CLEARANCE"


class ConstraintStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ConstraintScope(ContractModel):
    pipe_ids: list[Identifier] = Field(min_length=1)
    target_ids: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def check_duplicates(self) -> "ConstraintScope":
        if len(self.pipe_ids) != len(set(self.pipe_ids)):
            raise ValueError("scope.pipe_ids contains duplicate IDs")
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("scope.target_ids contains duplicate IDs")
        return self


class RuleParameters(ContractModel):
    distance_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    distance_basis: Literal["insulated_pipe_surface_to_target_surface"] | None = None


class RuleSource(ContractModel):
    source_type: Literal["synthetic_assumption", "public_reference"]
    document_id: Identifier
    document_revision: str = Field(min_length=1)
    clause_id: Identifier
    evidence_text: str = Field(min_length=1)


class Constraint(ContractModel):
    id: Identifier
    type: ConstraintType
    severity: Literal["hard"]
    scope: ConstraintScope
    parameters: RuleParameters
    source: RuleSource
    status: ConstraintStatus
    approved_by: str | None = None
    approved_at: str | None = None

    @model_validator(mode="after")
    def check_parameters(self) -> "Constraint":
        if self.type is ConstraintType.KEEP_OUT:
            if self.parameters.distance_m is not None or self.parameters.distance_basis:
                raise ValueError("KEEP_OUT parameters must be empty")
        elif self.type is ConstraintType.MIN_CLEARANCE:
            if self.parameters.distance_m is None:
                raise ValueError("MIN_CLEARANCE requires parameters.distance_m")
            if self.parameters.distance_basis is None:
                raise ValueError("MIN_CLEARANCE requires parameters.distance_basis")
        return self
