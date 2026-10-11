"""World-coordinate geometry contracts. Coordinates and dimensions use metres."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

Point3 = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
GridIndex = tuple[int, int, int]
Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AABB(ContractModel):
    type: Literal["aabb"] = "aabb"
    min_m: Point3
    max_m: Point3

    @model_validator(mode="after")
    def check_order(self) -> "AABB":
        if any(low >= high for low, high in zip(self.min_m, self.max_m, strict=True)):
            raise ValueError("AABB min_m must be less than max_m on every axis")
        return self

    def contains(self, point: Point3) -> bool:
        return all(
            low <= value <= high
            for low, value, high in zip(self.min_m, point, self.max_m, strict=True)
        )

    def contains_box(self, other: "AABB") -> bool:
        return all(
            low <= other_low and other_high <= high
            for low, other_low, other_high, high in zip(
                self.min_m, other.min_m, other.max_m, self.max_m, strict=True
            )
        )


class CoordinateFrame(ContractModel):
    name: Identifier
    unit: Literal["m"]
    up_axis: Literal["z"]
    origin_m: Point3
